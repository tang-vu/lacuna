"""Small, credential-safe PubMed EFetch client for benchmark metadata audits.

This client is not the v3 historical corpus pipeline. EFetch returns PubMed's maintained current
record, so every payload is stamped ``maintained_current_pubmed`` and must not be used as evidence
of period-appropriate indexing.

Only citation metadata and MeSH headings are retained. Abstract text is deliberately not cached.
NCBI asks software clients to include a registered email and tool name; set ``NCBI_EMAIL`` before
making a network request. ``NCBI_API_KEY`` is optional and only changes the supported request rate.

Run:
    NCBI_EMAIL=you@example.org python -m pipeline.pubmed_client 3797213 3075738
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from xml.etree import ElementTree

import requests

from pipeline.paths import PUBMED_CACHE_DIR

API_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
TOOL = "lacuna"
CREDENTIAL_PARAMS = {"api_key", "email"}
MAX_EFETCH_IDS = 200


def sanitise_eutils_url(url: str) -> str:
    """Remove personal identifiers and credentials without changing request semantics."""
    parts = urlsplit(url)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query)
        if key not in CREDENTIAL_PARAMS
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


class PubMedConfigurationError(RuntimeError):
    pass


def _text(element: ElementTree.Element | None) -> str:
    if element is None:
        return ""
    return " ".join("".join(element.itertext()).split())


def _publication_year(article: ElementTree.Element) -> int | None:
    year = article.findtext("./Journal/JournalIssue/PubDate/Year")
    if year and year.isdigit():
        return int(year)
    medline_date = article.findtext("./Journal/JournalIssue/PubDate/MedlineDate") or ""
    match = re.search(r"\b(18|19|20)\d{2}\b", medline_date)
    return int(match.group()) if match else None


def parse_pubmed_xml(xml_text: str) -> list[dict]:
    """Extract non-abstract citation metadata and maintained-current MeSH assignments."""
    root = ElementTree.fromstring(xml_text)
    records = []
    for item in root.findall("./PubmedArticle"):
        citation = item.find("./MedlineCitation")
        if citation is None:
            continue
        article = citation.find("./Article")
        if article is None:
            continue

        doi = ""
        for identifier in item.findall("./PubmedData/ArticleIdList/ArticleId"):
            if identifier.get("IdType") == "doi":
                doi = _text(identifier)
                break
        if not doi:
            for identifier in article.findall("./ELocationID"):
                if identifier.get("EIdType") == "doi":
                    doi = _text(identifier)
                    break

        headings = []
        for heading in citation.findall("./MeshHeadingList/MeshHeading"):
            descriptor = heading.find("./DescriptorName")
            if descriptor is None:
                continue
            headings.append(
                {
                    "descriptor_ui": descriptor.get("UI", ""),
                    "descriptor_label": _text(descriptor),
                    "major_topic": descriptor.get("MajorTopicYN") == "Y",
                    "qualifiers": [
                        {
                            "qualifier_ui": qualifier.get("UI", ""),
                            "qualifier_label": _text(qualifier),
                            "major_topic": qualifier.get("MajorTopicYN") == "Y",
                        }
                        for qualifier in heading.findall("./QualifierName")
                    ],
                }
            )

        records.append(
            {
                "pmid": citation.findtext("./PMID") or "",
                "title": _text(article.find("./ArticleTitle")),
                "publication_year": _publication_year(article),
                "doi": doi,
                "citation_status": citation.get("Status", ""),
                "indexing_method": citation.get("IndexingMethod", ""),
                "mesh_headings": headings,
            }
        )
    return records


class PubMedClient:
    """Fetch up to 200 PubMed records per request and cache a trimmed public payload."""

    def __init__(
        self,
        cache_dir: Path = PUBMED_CACHE_DIR,
        *,
        email: str | None = None,
        api_key: str | None = None,
        use_cache: bool = True,
        session: requests.Session | None = None,
    ):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.email = email if email is not None else os.environ.get("NCBI_EMAIL")
        self.api_key = api_key if api_key is not None else os.environ.get("NCBI_API_KEY")
        self.use_cache = use_cache
        self.session = session or requests.Session()

    def build_url(self, pmids: Iterable[str], *, include_credentials: bool = True) -> str:
        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
            "tool": TOOL,
        }
        if include_credentials and self.email:
            params["email"] = self.email
        if include_credentials and self.api_key:
            params["api_key"] = self.api_key
        return f"{API_BASE}/efetch.fcgi?{urlencode(params)}"

    def build_public_url(self, pmids: Iterable[str]) -> str:
        return self.build_url(pmids, include_credentials=False)

    def _cache_path(self, public_url: str) -> Path:
        digest = hashlib.sha256(public_url.encode("utf-8")).hexdigest()[:20]
        return self.cache_dir / f"{digest}.json"

    def fetch_records(self, pmids: Iterable[str]) -> dict:
        raw_ids = {str(pmid).strip() for pmid in pmids if str(pmid).strip()}
        if not raw_ids:
            raise ValueError("at least one PMID is required")
        if any(not pmid.isdigit() for pmid in raw_ids):
            raise ValueError("PMIDs must contain digits only")
        ids = sorted(raw_ids, key=int)
        if len(ids) > MAX_EFETCH_IDS:
            raise ValueError(f"EFetch batches are limited to {MAX_EFETCH_IDS} PMIDs")

        public_url = self.build_public_url(ids)
        cache_path = self._cache_path(public_url)
        if self.use_cache and cache_path.exists():
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            stored = payload.get("source_url", public_url)
            cleaned = sanitise_eutils_url(stored)
            payload["source_url"] = cleaned
            if cleaned != stored:
                cache_path.write_text(json.dumps(payload), encoding="utf-8")
            return payload

        if not self.email:
            raise PubMedConfigurationError(
                "NCBI_EMAIL is required for PubMed network requests; register the tool/email "
                "pair with NCBI before a bulk run"
            )

        try:
            response = self.session.get(self.build_url(ids), timeout=60)
        except requests.RequestException:
            # Requests exceptions often include the full request URL, including its query string.
            raise RuntimeError(f"PubMed EFetch request failed for {public_url}") from None
        if response.status_code != 200:
            # Do not include response text: upstream error bodies may echo the request URL.
            raise RuntimeError(f"PubMed EFetch returned HTTP {response.status_code} for {public_url}")

        response_bytes = response.content
        payload = {
            "schema_version": 1,
            "mesh_basis": "maintained_current_pubmed",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "source_url": public_url,
            "response_sha256": hashlib.sha256(response_bytes).hexdigest(),
            "response_bytes": len(response_bytes),
            "records": parse_pubmed_xml(response.text),
        }
        cache_path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        return payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pmids", nargs="+")
    parser.add_argument("--refresh", action="store_true", help="ignore a matching local cache")
    args = parser.parse_args()
    client = PubMedClient(use_cache=not args.refresh)
    try:
        payload = client.fetch_records(args.pmids)
    except PubMedConfigurationError as exc:
        raise SystemExit(str(exc)) from None
    print(json.dumps(payload, indent=1))


if __name__ == "__main__":
    main()
