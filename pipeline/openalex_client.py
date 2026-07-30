"""Rate-limit-aware, disk-cached client for the OpenAlex REST API.

Two properties matter more than speed here:

1. **Resumability.** The free tier allows ~1000 credits/day (measured 2026-07-27) while a full
   topic-level co-occurrence sweep needs 4,516 calls. So a sweep necessarily spans several days
   and must survive being killed at any point.

2. **Traceability.** Every cached response is stored next to the exact URL that produced it. A
   computed gap must be re-derivable by a reader clicking a link; that guarantee starts here.
   Nothing in this project reads OpenAlex except through this module.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

from pipeline.paths import CACHE_DIR

API_BASE = "https://api.openalex.org"

# Optional courtesy identity. Do not hard-code a maintainer's address into public artifacts.
MAILTO = os.environ.get("OPENALEX_MAILTO")

# Optional. Raises the daily credit ceiling; see docs/openalex-notes.md for the measured limits.
API_KEY = os.environ.get("OPENALEX_API_KEY")

# Stop before hitting zero so a run ends cleanly rather than in a wall of 429s.
CREDIT_FLOOR = 15
CREDENTIAL_PARAMS = {"api_key", "mailto"}


def sanitise_url(url: str) -> str:
    """Remove credentials and personal identifiers from an OpenAlex URL."""
    parts = urlsplit(url)
    query = [(key, value) for key, value in parse_qsl(parts.query) if key not in CREDENTIAL_PARAMS]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query, safe=",:"), ""))


class RateLimited(Exception):
    """Raised when the daily credit budget is exhausted. Callers should checkpoint and exit."""

    def __init__(self, reset_seconds: int | None = None):
        self.reset_seconds = reset_seconds
        hrs = f"{reset_seconds / 3600:.1f}h" if reset_seconds else "unknown"
        super().__init__(f"OpenAlex daily credits exhausted; resets in {hrs}")


class OpenAlexClient:
    """Fetches OpenAlex JSON, caching every response on disk keyed by its full URL."""

    def __init__(self, cache_dir: Path = CACHE_DIR, use_cache: bool = True):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.use_cache = use_cache
        self.session = requests.Session()
        identity = f" (mailto:{MAILTO})" if MAILTO else ""
        self.session.headers["User-Agent"] = f"lacuna/0.1{identity}"
        # Populated from response headers; lets a caller show progress against the daily budget.
        self.credits_remaining: int | None = None
        self.calls_made = 0
        self.cache_hits = 0

    # -- url construction ---------------------------------------------------

    def build_url(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        include_credentials: bool = True,
    ) -> str:
        """Build an API URL, optionally including request credentials."""
        params = dict(params or {})
        if include_credentials and MAILTO:
            params["mailto"] = MAILTO
        if include_credentials and API_KEY:
            params["api_key"] = API_KEY
        query = urlencode(params, safe=",:")
        return f"{API_BASE}/{path.lstrip('/')}?{query}"

    def build_public_url(self, path: str, params: dict[str, Any] | None = None) -> str:
        """Build the credential-free URL safe to store in caches and publish."""
        return self.build_url(path, params, include_credentials=False)

    def _cache_path(self, url: str) -> Path:
        # Credentials never affect the request semantics or cache identity.
        stable = sanitise_url(url)
        digest = hashlib.sha256(stable.encode()).hexdigest()[:20]
        return self.cache_dir / f"{digest}.json"

    # -- fetching -----------------------------------------------------------

    def get(self, path: str, params: dict[str, Any] | None = None, max_retries: int = 4) -> dict:
        """GET one OpenAlex endpoint, serving from disk cache when available.

        Raises RateLimited when the daily budget runs out, so a sweep can checkpoint and resume
        tomorrow instead of burning retries against a wall.
        """
        request_url = self.build_url(path, params)
        source_url = self.build_public_url(path, params)
        cache_file = self._cache_path(source_url)

        if self.use_cache and cache_file.exists():
            self.cache_hits += 1
            payload = json.loads(cache_file.read_text(encoding="utf-8"))
            stored_source = payload.get("_lacuna_source_url", source_url)
            public_source = sanitise_url(stored_source)
            payload["_lacuna_source_url"] = public_source
            # Older caches predate the public/private URL split. Clean them as they are touched so
            # a courtesy email or API key does not remain persisted after a cached run.
            if public_source != stored_source:
                cache_file.write_text(json.dumps(payload), encoding="utf-8")
            return payload

        if self.credits_remaining is not None and self.credits_remaining < CREDIT_FLOOR:
            raise RateLimited(self._reset_seconds)

        backoff = 2.0
        for attempt in range(max_retries):
            response = self.session.get(request_url, timeout=60)
            self._read_rate_limit_headers(response)
            self.calls_made += 1

            if response.status_code == 200:
                payload = response.json()
                # Write the URL into the cached artifact itself. Provenance travels with the data
                # rather than living in a separate index that can drift out of sync.
                payload["_lacuna_source_url"] = source_url
                cache_file.write_text(json.dumps(payload), encoding="utf-8")
                return payload

            if response.status_code == 429:
                raise RateLimited(self._reset_seconds)

            if response.status_code >= 500 or response.status_code == 408:
                time.sleep(backoff)
                backoff *= 2
                continue

            raise RuntimeError(
                f"OpenAlex {response.status_code} for {source_url}: {response.text[:300]}"
            )

        raise RuntimeError(f"OpenAlex unreachable after {max_retries} attempts: {source_url}")

    def _read_rate_limit_headers(self, response: requests.Response) -> None:
        remaining = response.headers.get("X-RateLimit-Remaining")
        if remaining is not None:
            try:
                self.credits_remaining = int(remaining)
            except ValueError:
                pass
        reset = response.headers.get("X-RateLimit-Reset")
        self._reset_seconds = int(reset) if reset and reset.isdigit() else None

    _reset_seconds: int | None = None

    # -- pagination ---------------------------------------------------------

    def paginate(self, path: str, params: dict[str, Any] | None = None, per_page: int = 200):
        """Yield every result across pages. per_page maxes at 200 (201 returns a pagination error).

        Uses plain page-numbering, which OpenAlex caps at 10,000 records. That is ample for the
        entity endpoints this project reads (the largest, /topics, holds 4,516). Paging through
        /works would need cursors instead — deliberately not supported here, because this project
        never enumerates works one by one.
        """
        page = 1
        while True:
            payload = self.get(path, {**(params or {}), "per-page": per_page, "page": page})
            results = payload.get("results", [])
            if not results:
                return
            yield from results
            if len(results) < per_page:
                return
            page += 1
