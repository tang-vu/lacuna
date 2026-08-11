"""Acquire BioASQ Task 1a inputs without persisting credentials or extracting the corpus.

The five-record public sample is checksum-pinned and can be downloaded without an account.  The
full v2013 corpus is served only after BioASQ login; credentials are read exclusively from
``BIOASQ_USERNAME`` and ``BIOASQ_PASSWORD`` so they do not appear in shell history or manifests.

Run::

    python -m pipeline.benchmark.bioasq_download sample
    python -m pipeline.benchmark.bioasq_download full
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
from html.parser import HTMLParser
from pathlib import Path

import requests

from pipeline.paths import REPO_ROOT

BASE_URL = "https://participants-area.bioasq.org"
LOGIN_URL = f"{BASE_URL}/accounts/login/"
FULL_SNAPSHOT_URL = f"{BASE_URL}/raw_training_set/"
PUBLIC_SAMPLE_URL = f"{BASE_URL}/download/sampleData/task1a/"
PUBLIC_EFETCH_URL = (
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    "?db=pubmed&id=23479819,23483174,23483175,23483176,23483177&retmode=xml"
)
PUBLIC_SAMPLE_SHA256 = "85ea207918e3d09189d4fa23ab8cd1bac3b27ab02be8dbd9f67d73e541ccccc8"
PUBLIC_SAMPLE_BYTES = 14_104
DEFAULT_DIRECTORY = REPO_ROOT / "data" / "medline-baseline" / "bioasq"
DEFAULT_SAMPLE_PATH = DEFAULT_DIRECTORY / "BioASQ-SampleDataA.json"
DEFAULT_PUBMED_PATH = REPO_ROOT / "data" / "pubmed-cache" / "bioasq-sample-current-efetch.xml"
DEFAULT_FULL_PATH = DEFAULT_DIRECTORY / "PubMedWithMeSH.zip"
CHUNK_SIZE = 1024 * 1024
MIN_FREE_AFTER_DOWNLOAD = 1024 * 1024 * 1024
USER_AGENT = "lacuna-source-audit/1.0 (https://github.com/tang-vu/lacuna)"


class BioasqDownloadError(RuntimeError):
    pass


class _CsrfParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.token: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "input":
            return
        values = dict(attrs)
        if values.get("name") == "csrfmiddlewaretoken" and values.get("value"):
            self.token = values["value"]


def extract_csrf_token(html: str) -> str:
    parser = _CsrfParser()
    parser.feed(html)
    if not parser.token:
        raise BioasqDownloadError("BioASQ login page did not contain a CSRF token")
    return parser.token


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _verify_existing(path: Path, *, sha256: str, size: int) -> dict | None:
    if not path.exists():
        return None
    measured_sha256, measured_size = _sha256_file(path)
    if (measured_sha256, measured_size) != (sha256, size):
        raise BioasqDownloadError(
            f"refusing to overwrite unexpected existing file: {path} "
            f"({measured_size} bytes, sha256 {measured_sha256})"
        )
    return {"path": path, "sha256": measured_sha256, "bytes": measured_size, "reused": True}


def _stream_response(
    response: requests.Response,
    output: Path,
    *,
    expected_sha256: str | None = None,
    expected_bytes: int | None = None,
    expected_attachment: str | None = None,
) -> dict:
    response.raise_for_status()
    content_type = response.headers.get("Content-Type", "").casefold()
    disposition = response.headers.get("Content-Disposition", "")
    if "text/html" in content_type:
        raise BioasqDownloadError("BioASQ returned HTML instead of a data file; login likely failed")
    if expected_attachment and expected_attachment.casefold() not in disposition.casefold():
        raise BioasqDownloadError(
            f"unexpected BioASQ attachment header; expected {expected_attachment!r}"
        )
    if output.exists():
        raise BioasqDownloadError(f"refusing to overwrite existing file: {output}")

    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(f"{output.name}.part")
    if partial.exists():
        raise BioasqDownloadError(f"remove or inspect stale partial download first: {partial}")

    declared_length = response.headers.get("Content-Length")
    if declared_length and declared_length.isdigit():
        required = int(declared_length) + MIN_FREE_AFTER_DOWNLOAD
        available = shutil.disk_usage(output.parent).free
        if available < required:
            raise BioasqDownloadError(
                f"insufficient disk space: need {required} bytes including safety reserve; "
                f"have {available}"
            )

    digest = hashlib.sha256()
    measured_bytes = 0
    try:
        with partial.open("xb") as stream:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if not chunk:
                    continue
                stream.write(chunk)
                digest.update(chunk)
                measured_bytes += len(chunk)
        measured_sha256 = digest.hexdigest()
        if expected_bytes is not None and measured_bytes != expected_bytes:
            raise BioasqDownloadError(
                f"downloaded byte count drifted: expected {expected_bytes}, got {measured_bytes}"
            )
        if expected_sha256 is not None and measured_sha256 != expected_sha256:
            raise BioasqDownloadError(
                f"downloaded checksum drifted: expected {expected_sha256}, got {measured_sha256}"
            )
        partial.replace(output)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return {
        "path": output,
        "sha256": measured_sha256,
        "bytes": measured_bytes,
        "reused": False,
    }


def download_public_sample(
    output: Path = DEFAULT_SAMPLE_PATH,
    *,
    session: requests.Session | None = None,
) -> dict:
    existing = _verify_existing(
        output,
        sha256=PUBLIC_SAMPLE_SHA256,
        size=PUBLIC_SAMPLE_BYTES,
    )
    if existing:
        return existing
    client = session or requests.Session()
    response = client.get(
        PUBLIC_SAMPLE_URL,
        headers={"User-Agent": USER_AGENT},
        stream=True,
        timeout=60,
    )
    return _stream_response(
        response,
        output,
        expected_sha256=PUBLIC_SAMPLE_SHA256,
        expected_bytes=PUBLIC_SAMPLE_BYTES,
    )


def download_current_pubmed_sample(
    output: Path = DEFAULT_PUBMED_PATH,
    *,
    session: requests.Session | None = None,
) -> dict:
    if output.exists():
        sha256, size = _sha256_file(output)
        return {"path": output, "sha256": sha256, "bytes": size, "reused": True}
    client = session or requests.Session()
    response = client.get(
        PUBLIC_EFETCH_URL,
        headers={"User-Agent": USER_AGENT},
        stream=True,
        timeout=60,
    )
    return _stream_response(response, output)


def download_full_snapshot(
    output: Path = DEFAULT_FULL_PATH,
    *,
    session: requests.Session | None = None,
    username: str | None = None,
    password: str | None = None,
) -> dict:
    username = username or os.environ.get("BIOASQ_USERNAME")
    password = password or os.environ.get("BIOASQ_PASSWORD")
    if not username or not password:
        raise BioasqDownloadError(
            "full download requires BIOASQ_USERNAME and BIOASQ_PASSWORD in the process environment"
        )
    client = session or requests.Session()
    headers = {"User-Agent": USER_AGENT}
    login_page = client.get(LOGIN_URL, headers=headers, timeout=60)
    login_page.raise_for_status()
    token = extract_csrf_token(login_page.text)
    login = client.post(
        LOGIN_URL,
        data={
            "csrfmiddlewaretoken": token,
            "username": username,
            "password": password,
            "next": "",
        },
        headers={**headers, "Referer": LOGIN_URL},
        allow_redirects=True,
        timeout=60,
    )
    login.raise_for_status()
    if "/accounts/login" in login.url or "csrfmiddlewaretoken" in login.text:
        raise BioasqDownloadError("BioASQ login failed; no data request was attempted")
    response = client.get(FULL_SNAPSHOT_URL, headers=headers, stream=True, timeout=(60, 300))
    return _stream_response(response, output, expected_attachment="PubMedWithMeSH.zip")


def _print_result(label: str, result: dict) -> None:
    action = "verified existing" if result["reused"] else "downloaded"
    print(f"{label}: {action} {result['path']}")
    print(f"bytes: {result['bytes']}")
    print(f"sha256: {result['sha256']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    sample = subparsers.add_parser("sample", help="download public BioASQ and PubMed audit inputs")
    sample.add_argument("--output", type=Path, default=DEFAULT_SAMPLE_PATH)
    sample.add_argument("--pubmed-output", type=Path, default=DEFAULT_PUBMED_PATH)
    full = subparsers.add_parser("full", help="download registered v2013 corpus using environment")
    full.add_argument("--output", type=Path, default=DEFAULT_FULL_PATH)
    args = parser.parse_args()
    try:
        if args.command == "sample":
            _print_result("BioASQ public sample", download_public_sample(args.output))
            _print_result(
                "current PubMed comparison",
                download_current_pubmed_sample(args.pubmed_output),
            )
        else:
            _print_result("BioASQ v2013 corpus", download_full_snapshot(args.output))
    except (BioasqDownloadError, requests.RequestException) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
