"""Discover and seal the autonomous prospective benchmark's T0 source.

``discover`` captures the complete official PubMed checksum listing and the matching MeSH
descriptor transport. Its output is deliberately a zero-readiness remote inventory. ``download``
resumes into ``.part`` files on the destination volume, verifies every transport before promotion,
and never replaces a conflicting complete file. ``seal`` is the machine gate: it accepts only a
complete local release matching every official MD5, computes SHA-256 and record counts, verifies
the descriptor vocabulary, and creates a manifest with exclusive-create semantics.

Run:
    python -m pipeline.benchmark.autonomous_t0 audit
    python -m pipeline.benchmark.autonomous_t0 discover \
      --output benchmarks/autonomous/t0-2026-remote-inventory.json
    python -m pipeline.benchmark.autonomous_t0 download \
      --inventory benchmarks/autonomous/t0-2026-remote-inventory.json \
      --baseline-dir D:/lacuna-storage/autonomous/t0-2026/pubmed-baseline \
      --mesh D:/lacuna-storage/autonomous/t0-2026/mesh/desc2026.gz
    python -m pipeline.benchmark.autonomous_t0 seal \
      --inventory benchmarks/autonomous/t0-2026-remote-inventory.json \
      --baseline-dir D:/lacuna-sources/pubmed/baseline \
      --mesh D:/lacuna-sources/mesh/desc2026.gz \
      --output benchmarks/autonomous/t0-2026.json
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import threading
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree

import requests

from pipeline.paths import REPO_ROOT
from pipeline.provenance import sha256_payload

PUBMED_BASE_URL = "https://ftp.ncbi.nlm.nih.gov/pubmed/baseline/"
MESH_BASE_URL = "https://nlmpubs.nlm.nih.gov/projects/mesh/MESH_FILES/xmlmesh/"
USER_AGENT = "lacuna-autonomous-source-seal/0.1 (+https://github.com/tang-vu/lacuna)"
MD5 = re.compile(r"^[0-9a-f]{32}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
REMOTE_INVENTORY_PATH = (
    REPO_ROOT / "benchmarks" / "autonomous" / "t0-2026-remote-inventory.json"
)


class AutonomousT0Error(ValueError):
    """The source cannot advance the autonomous state machine."""


@dataclass(frozen=True)
class RemoteInventoryAudit:
    path: Path
    sha256: str
    release_year: int
    pubmed_file_count: int
    mesh_descriptor_count: int
    status: str
    readiness_contribution: int


@dataclass(frozen=True)
class DownloadAudit:
    release_year: int
    pubmed_file_count: int
    transport_count: int
    downloaded_count: int
    reused_count: int
    verified_bytes: int
    baseline_dir: Path
    mesh_path: Path
    readiness_contribution: int = 0


_SESSION_LOCAL = threading.local()


def _session_get(url: str, **kwargs) -> requests.Response:
    session = getattr(_SESSION_LOCAL, "session", None)
    if session is None:
        session = requests.Session()
        _SESSION_LOCAL.session = session
    return session.get(url, **kwargs)


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = next((value for name, value in attrs if name.lower() == "href"), None)
        if href:
            self.links.append(href)


def _bounded_get(
    url: str,
    *,
    fetch: Callable[..., requests.Response],
    maximum_bytes: int,
) -> bytes:
    response = None
    for attempt in range(3):
        try:
            response = fetch(
                url,
                headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"},
                timeout=60,
                stream=True,
            )
            response.raise_for_status()
            break
        except requests.RequestException as exc:
            if attempt == 2:
                raise AutonomousT0Error(f"official source request failed: {url}") from exc
            time.sleep(0.25 * (2**attempt))
    if response is None:
        raise AutonomousT0Error(f"official source request failed: {url}")
    raw = getattr(response, "raw", None)
    if raw is None:
        content = response.content
    else:
        raw.decode_content = False
        chunks = []
        size = 0
        while True:
            chunk = raw.read(min(1024 * 1024, maximum_bytes + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > maximum_bytes:
                break
        content = b"".join(chunks)
    close = getattr(response, "close", None)
    if callable(close):
        close()
    if not isinstance(content, bytes) or not content:
        raise AutonomousT0Error(f"official source returned no bytes: {url}")
    if len(content) > maximum_bytes:
        raise AutonomousT0Error(f"official source exceeded byte limit: {url}")
    return content


def _readme_file_count(readme: str, release_year: int) -> int:
    prefix = str(release_year)[-2:]
    pattern = re.compile(
        rf"complete baseline consists of files pubmed{prefix}n0001\.xml through "
        rf"pubmed{prefix}n(\d{{4}})\.xml",
        re.IGNORECASE,
    )
    match = pattern.search(readme)
    if match is None:
        raise AutonomousT0Error("README does not declare a complete contiguous baseline")
    if f"Last Updated" not in readme or str(release_year) not in readme:
        raise AutonomousT0Error("README release identity is missing")
    return int(match.group(1))


def _listed_release_files(index_html: str, release_year: int, file_count: int) -> list[str]:
    parser = _LinkParser()
    parser.feed(index_html)
    prefix = str(release_year)[-2:]
    expected = [
        f"pubmed{prefix}n{index:04d}.xml.gz" for index in range(1, file_count + 1)
    ]
    links = set(parser.links)
    listed_data = sorted(
        link for link in links if re.fullmatch(rf"pubmed{prefix}n\d{{4}}\.xml\.gz", link)
    )
    listed_checksums = sorted(
        link
        for link in links
        if re.fullmatch(rf"pubmed{prefix}n\d{{4}}\.xml\.gz\.md5", link)
    )
    if listed_data != expected:
        raise AutonomousT0Error("baseline data listing is not the complete README release")
    if listed_checksums != [f"{name}.md5" for name in expected]:
        raise AutonomousT0Error("baseline checksum listing is incomplete")
    return expected


def _parse_md5(content: bytes, expected_filename: str) -> str:
    try:
        value = content.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise AutonomousT0Error(f"{expected_filename}: MD5 response is not ASCII") from exc
    bsd = re.fullmatch(r"MD5\(([^)]+)\)=\s*([0-9a-fA-F]{32})", value)
    gnu = re.fullmatch(r"([0-9a-fA-F]{32})\s+\*?(.+)", value)
    if bsd:
        filename, digest = bsd.group(1), bsd.group(2)
    elif gnu:
        digest, filename = gnu.group(1), gnu.group(2)
    else:
        raise AutonomousT0Error(f"{expected_filename}: malformed official MD5")
    if filename != expected_filename:
        raise AutonomousT0Error(f"{expected_filename}: official MD5 names another file")
    return digest.lower()


def _inspect_mesh_bytes(content: bytes, filename: str) -> int:
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(content), mode="rb") as handle:
            context = ElementTree.iterparse(handle, events=("start", "end"))
            _event, root = next(context)
            if root.tag != "DescriptorRecordSet":
                raise AutonomousT0Error(f"{filename}: unexpected MeSH XML root")
            count = 0
            seen_uis: set[str] = set()
            for event, element in context:
                if event == "end" and element.tag == "DescriptorRecord":
                    ui = element.findtext("./DescriptorUI") or ""
                    if not re.fullmatch(r"D\d{6,9}", ui) or ui in seen_uis:
                        raise AutonomousT0Error(f"{filename}: invalid or duplicate descriptor UI")
                    seen_uis.add(ui)
                    count += 1
                    root.clear()
    except (OSError, ElementTree.ParseError, StopIteration) as exc:
        raise AutonomousT0Error(f"{filename}: invalid MeSH descriptor transport") from exc
    if count <= 0:
        raise AutonomousT0Error(f"{filename}: no MeSH descriptors parsed")
    return count


def discover_remote_inventory(
    *,
    release_year: int,
    observed_on: date | None = None,
    fetch: Callable[..., requests.Response] | None = None,
    workers: int = 16,
) -> dict:
    """Capture the official remote identities without claiming local T0 readiness."""
    if release_year < 2026:
        raise AutonomousT0Error("the active prospective track starts with release year 2026")
    if not 1 <= workers <= 32:
        raise AutonomousT0Error("workers must be between 1 and 32")
    fetch = fetch or _session_get
    observed_on = observed_on or date.today()
    readme_url = urljoin(PUBMED_BASE_URL, "README.txt")
    index_bytes = _bounded_get(
        PUBMED_BASE_URL,
        fetch=fetch,
        maximum_bytes=10_000_000,
    )
    readme_bytes = _bounded_get(readme_url, fetch=fetch, maximum_bytes=1_000_000)
    try:
        index_html = index_bytes.decode("utf-8")
        readme = readme_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AutonomousT0Error("official baseline metadata is not UTF-8") from exc
    file_count = _readme_file_count(readme, release_year)
    filenames = _listed_release_files(index_html, release_year, file_count)

    def checksum_item(filename: str) -> dict:
        checksum_url = urljoin(PUBMED_BASE_URL, f"{filename}.md5")
        checksum_bytes = _bounded_get(checksum_url, fetch=fetch, maximum_bytes=1024)
        return {
            "filename": filename,
            "url": urljoin(PUBMED_BASE_URL, filename),
            "official_md5": _parse_md5(checksum_bytes, filename),
            "checksum_url": checksum_url,
            "checksum_response_sha256": hashlib.sha256(checksum_bytes).hexdigest(),
        }

    with ThreadPoolExecutor(max_workers=workers) as executor:
        files = list(executor.map(checksum_item, filenames))

    mesh_filename = f"desc{release_year}.gz"
    mesh_url = urljoin(MESH_BASE_URL, mesh_filename)
    mesh_bytes = _bounded_get(mesh_url, fetch=fetch, maximum_bytes=100_000_000)
    descriptor_count = _inspect_mesh_bytes(mesh_bytes, mesh_filename)
    return {
        "schema_version": 1,
        "kind": "autonomous_t0_remote_inventory",
        "status": "remote_inventory_only_not_a_verified_t0",
        "release_year": release_year,
        "observed_on": observed_on.isoformat(),
        "readiness_contribution": 0,
        "human_dependencies": [],
        "pubmed_baseline": {
            "base_url": PUBMED_BASE_URL,
            "index_url": PUBMED_BASE_URL,
            "index_response_sha256": hashlib.sha256(index_bytes).hexdigest(),
            "readme_url": readme_url,
            "readme_response_sha256": hashlib.sha256(readme_bytes).hexdigest(),
            "expected_file_count": file_count,
            "files": files,
        },
        "mesh_descriptor": {
            "production_year": release_year,
            "filename": mesh_filename,
            "url": mesh_url,
            "bytes": len(mesh_bytes),
            "observed_transport_sha256": hashlib.sha256(mesh_bytes).hexdigest(),
            "descriptor_count": descriptor_count,
        },
        "machine_gate": {
            "state": "awaiting_local_source_bytes",
            "pass_condition": "every PubMed file matches its official MD5 and receives a local SHA-256 and record count; the complete matching MeSH transport matches this inventory",
            "failure_action": "abstain",
        },
        "claim_boundary": "This captures remote source identities only. It is not a T0 baseline, metric result, validation result, or knowledge-gap claim.",
    }


def _validate_remote_inventory(payload: dict) -> tuple[int, list[dict], dict]:
    if payload.get("schema_version") != 1 or payload.get("kind") != "autonomous_t0_remote_inventory":
        raise AutonomousT0Error("unsupported autonomous T0 inventory")
    if (
        payload.get("status") != "remote_inventory_only_not_a_verified_t0"
        or payload.get("readiness_contribution") != 0
        or payload.get("human_dependencies") != []
    ):
        raise AutonomousT0Error("remote inventory overstates readiness or adds a human gate")
    try:
        observed_on = date.fromisoformat(str(payload.get("observed_on")))
    except ValueError as exc:
        raise AutonomousT0Error("remote inventory observed_on must be YYYY-MM-DD") from exc
    if observed_on > date.today():
        raise AutonomousT0Error("remote inventory cannot claim a future observation")
    year = payload.get("release_year")
    if not isinstance(year, int) or year < 2026:
        raise AutonomousT0Error("invalid T0 release year")
    pubmed = payload.get("pubmed_baseline")
    if not isinstance(pubmed, dict) or pubmed.get("base_url") != PUBMED_BASE_URL:
        raise AutonomousT0Error("PubMed inventory must use the official baseline source")
    if (
        pubmed.get("index_url") != PUBMED_BASE_URL
        or pubmed.get("readme_url") != urljoin(PUBMED_BASE_URL, "README.txt")
    ):
        raise AutonomousT0Error("PubMed index identity drifted")
    for field in ("index_response_sha256", "readme_response_sha256"):
        if not SHA256.fullmatch(str(pubmed.get(field, ""))):
            raise AutonomousT0Error(f"PubMed {field} is missing")
    files = pubmed.get("files")
    file_count = pubmed.get("expected_file_count")
    if not isinstance(files, list) or not isinstance(file_count, int) or len(files) != file_count:
        raise AutonomousT0Error("remote inventory file count is incomplete")
    prefix = str(year)[-2:]
    expected_names = [
        f"pubmed{prefix}n{index:04d}.xml.gz" for index in range(1, file_count + 1)
    ]
    if [item.get("filename") for item in files if isinstance(item, dict)] != expected_names:
        raise AutonomousT0Error("remote inventory filenames are not contiguous")
    for item in files:
        filename = item["filename"]
        if (
            item.get("url") != urljoin(PUBMED_BASE_URL, filename)
            or item.get("checksum_url") != urljoin(PUBMED_BASE_URL, f"{filename}.md5")
            or not MD5.fullmatch(str(item.get("official_md5", "")))
            or not SHA256.fullmatch(str(item.get("checksum_response_sha256", "")))
        ):
            raise AutonomousT0Error(f"{filename}: invalid official source identity")
    mesh = payload.get("mesh_descriptor")
    mesh_filename = f"desc{year}.gz"
    if not isinstance(mesh, dict) or (
        mesh.get("production_year") != year
        or mesh.get("filename") != mesh_filename
        or mesh.get("url") != urljoin(MESH_BASE_URL, mesh_filename)
        or not isinstance(mesh.get("bytes"), int)
        or mesh["bytes"] <= 0
        or not SHA256.fullmatch(str(mesh.get("observed_transport_sha256", "")))
        or not isinstance(mesh.get("descriptor_count"), int)
        or mesh["descriptor_count"] <= 0
    ):
        raise AutonomousT0Error("invalid matching MeSH source identity")
    if payload.get("machine_gate") != {
        "state": "awaiting_local_source_bytes",
        "pass_condition": "every PubMed file matches its official MD5 and receives a local SHA-256 and record count; the complete matching MeSH transport matches this inventory",
        "failure_action": "abstain",
    }:
        raise AutonomousT0Error("remote inventory machine gate drifted")
    if payload.get("claim_boundary") != (
        "This captures remote source identities only. It is not a T0 baseline, metric result, "
        "validation result, or knowledge-gap claim."
    ):
        raise AutonomousT0Error("remote inventory claim boundary drifted")
    return year, files, mesh


def audit_remote_inventory(
    path: Path = REMOTE_INVENTORY_PATH,
) -> RemoteInventoryAudit:
    """Validate and summarize a versioned zero-readiness remote inventory."""
    raw = path.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AutonomousT0Error("remote inventory is not valid UTF-8 JSON") from exc
    year, files, mesh = _validate_remote_inventory(payload)
    return RemoteInventoryAudit(
        path=path,
        sha256=sha256_payload(payload),
        release_year=year,
        pubmed_file_count=len(files),
        mesh_descriptor_count=mesh["descriptor_count"],
        status=payload["status"],
        readiness_contribution=payload["readiness_contribution"],
    )


def _digest_file(path: Path, algorithm: str) -> str:
    if algorithm == "md5":
        digest = hashlib.md5(usedforsecurity=False)
    elif algorithm == "sha256":
        digest = hashlib.sha256()
    else:
        raise AutonomousT0Error(f"unsupported transport digest: {algorithm}")
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_transport_bytes(response: requests.Response):
    raw = getattr(response, "raw", None)
    if raw is not None:
        raw.decode_content = False
        while True:
            chunk = raw.read(1024 * 1024)
            if not chunk:
                return
            yield chunk
    iterator = getattr(response, "iter_content", None)
    if callable(iterator):
        for chunk in iterator(chunk_size=1024 * 1024):
            if chunk:
                yield chunk
        return
    content = getattr(response, "content", b"")
    if content:
        yield content


def _promote_verified_part(part: Path, destination: Path) -> None:
    try:
        # The part lives beside its destination, so a hard link is both same-volume and an
        # atomic no-clobber promotion. Path.rename() can replace an intervening destination on
        # POSIX, violating the downloader's evidence-preservation contract.
        os.link(part, destination)
    except FileExistsError:
        raise AutonomousT0Error(
            f"refusing to replace a file that appeared during download: {destination}"
        ) from None
    except OSError as exc:
        raise AutonomousT0Error(
            f"atomic no-clobber promotion failed: {destination}"
        ) from exc
    part.unlink()


def _download_verified_transport(
    *,
    url: str,
    destination: Path,
    algorithm: str,
    expected_digest: str,
    expected_bytes: int | None,
    fetch: Callable[..., requests.Response],
) -> tuple[str, int]:
    """Download one immutable transport, retaining an interrupted ``.part`` on its volume."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        actual = _digest_file(destination, algorithm)
        size = destination.stat().st_size
        if actual != expected_digest or (
            expected_bytes is not None and size != expected_bytes
        ):
            raise AutonomousT0Error(
                f"refusing to overwrite conflicting complete file: {destination}"
            )
        return "reused", size

    part = destination.with_name(f"{destination.name}.part")
    if part.exists():
        part_size = part.stat().st_size
        if (
            _digest_file(part, algorithm) == expected_digest
            and (expected_bytes is None or part_size == expected_bytes)
        ):
            _promote_verified_part(part, destination)
            return "downloaded", part_size

    last_error: Exception | None = None
    for attempt in range(3):
        response = None
        try:
            offset = part.stat().st_size if part.exists() else 0
            headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "identity"}
            if offset:
                headers["Range"] = f"bytes={offset}-"
            response = fetch(
                url,
                headers=headers,
                timeout=120,
                stream=True,
            )
            status_code = int(getattr(response, "status_code", 200))
            if not (offset and status_code == 416):
                response.raise_for_status()
            if offset and status_code == 206:
                content_range = str(getattr(response, "headers", {}).get("Content-Range", ""))
                if not content_range.startswith(f"bytes {offset}-"):
                    raise AutonomousT0Error(
                        f"server resumed at an unexpected byte for {destination.name}"
                    )
                mode = "ab"
            elif offset and status_code == 200:
                offset = 0
                mode = "wb"
            elif offset and status_code == 416:
                part.unlink()
                continue
            elif status_code == 200:
                mode = "wb"
            else:
                raise AutonomousT0Error(
                    f"unexpected HTTP status {status_code} for {destination.name}"
                )

            with part.open(mode) as handle:
                for chunk in _iter_transport_bytes(response):
                    handle.write(chunk)

            size = part.stat().st_size
            digest = _digest_file(part, algorithm)
            size_matches = expected_bytes is None or size == expected_bytes
            if digest == expected_digest and size_matches:
                _promote_verified_part(part, destination)
                return "downloaded", size
            if attempt < 2:
                part.unlink()
                time.sleep(0.25 * (2**attempt))
                continue
            raise AutonomousT0Error(
                f"downloaded transport checksum or byte count mismatch: {destination.name}"
            )
        except (OSError, requests.RequestException) as exc:
            last_error = exc
            if attempt == 2:
                break
            time.sleep(0.25 * (2**attempt))
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()
    raise AutonomousT0Error(f"download failed after retries: {destination.name}") from last_error


def download_t0_sources(
    inventory_path: Path,
    baseline_dir: Path,
    mesh_path: Path,
    *,
    workers: int = 4,
    minimum_free_bytes: int = 40 * 1024**3,
    fetch: Callable[..., requests.Response] | None = None,
    progress: Callable[[int, int, str, str], None] | None = None,
) -> DownloadAudit:
    """Acquire every pinned T0 transport without using CWD or a system temporary directory."""
    if not 1 <= workers <= 8:
        raise AutonomousT0Error("download workers must be between 1 and 8")
    if minimum_free_bytes < 0:
        raise AutonomousT0Error("minimum free bytes cannot be negative")
    payload = json.loads(inventory_path.read_text(encoding="utf-8"))
    year, remote_files, remote_mesh = _validate_remote_inventory(payload)
    if mesh_path.name != remote_mesh["filename"]:
        raise AutonomousT0Error(
            f"MeSH destination filename must be {remote_mesh['filename']}"
        )
    baseline_dir.mkdir(parents=True, exist_ok=True)
    mesh_path.parent.mkdir(parents=True, exist_ok=True)
    free_bytes = min(
        shutil.disk_usage(baseline_dir).free,
        shutil.disk_usage(mesh_path.parent).free,
    )
    if free_bytes < minimum_free_bytes:
        raise AutonomousT0Error(
            "destination volume has insufficient free space "
            f"({free_bytes} < {minimum_free_bytes} bytes)"
        )

    expected_names = [item["filename"] for item in remote_files]
    prefix = str(year)[-2:]
    existing_names = sorted(
        path.name
        for path in baseline_dir.iterdir()
        if path.is_file() and re.fullmatch(rf"pubmed{prefix}n\d{{4}}\.xml\.gz", path.name)
    )
    unexpected = sorted(set(existing_names) - set(expected_names))
    if unexpected:
        raise AutonomousT0Error(
            f"destination contains unexpected release file: {unexpected[0]}"
        )

    fetch = fetch or _session_get
    tasks = [
        (
            item["filename"],
            item["url"],
            baseline_dir / item["filename"],
            "md5",
            item["official_md5"],
            None,
        )
        for item in remote_files
    ]
    tasks.append(
        (
            remote_mesh["filename"],
            remote_mesh["url"],
            mesh_path,
            "sha256",
            remote_mesh["observed_transport_sha256"],
            remote_mesh["bytes"],
        )
    )
    downloaded = reused = verified_bytes = completed = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                _download_verified_transport,
                url=url,
                destination=destination,
                algorithm=algorithm,
                expected_digest=expected_digest,
                expected_bytes=expected_bytes,
                fetch=fetch,
            ): filename
            for filename, url, destination, algorithm, expected_digest, expected_bytes in tasks
        }
        for future in as_completed(futures):
            filename = futures[future]
            try:
                outcome, size = future.result()
            except Exception:
                for pending in futures:
                    pending.cancel()
                raise
            downloaded += int(outcome == "downloaded")
            reused += int(outcome == "reused")
            verified_bytes += size
            completed += 1
            if progress is not None:
                progress(completed, len(tasks), filename, outcome)
    return DownloadAudit(
        release_year=year,
        pubmed_file_count=len(remote_files),
        transport_count=len(tasks),
        downloaded_count=downloaded,
        reused_count=reused,
        verified_bytes=verified_bytes,
        baseline_dir=baseline_dir,
        mesh_path=mesh_path,
    )


def _hash_file(path: Path) -> tuple[str, str, int]:
    md5_digest = hashlib.md5(usedforsecurity=False)
    sha256_digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            md5_digest.update(chunk)
            sha256_digest.update(chunk)
            size += len(chunk)
    return md5_digest.hexdigest(), sha256_digest.hexdigest(), size


def _count_pubmed_rows(path: Path) -> dict[str, int]:
    counts = {
        "pubmed_article_count": 0,
        "pubmed_book_article_count": 0,
        "delete_citation_count": 0,
    }
    tags = {
        "PubmedArticle": "pubmed_article_count",
        "PubmedBookArticle": "pubmed_book_article_count",
        "DeleteCitation": "delete_citation_count",
    }
    try:
        with gzip.open(path, "rb") as handle:
            context = ElementTree.iterparse(handle, events=("start", "end"))
            _event, root = next(context)
            if root.tag != "PubmedArticleSet":
                raise AutonomousT0Error(f"{path.name}: unexpected PubMed XML root")
            for event, element in context:
                field = tags.get(element.tag)
                if event == "end" and field is not None:
                    counts[field] += 1
                    root.clear()
    except (OSError, ElementTree.ParseError, StopIteration) as exc:
        raise AutonomousT0Error(f"{path.name}: invalid PubMed XML transport") from exc
    counts["total_record_count"] = sum(counts.values())
    if counts["total_record_count"] <= 0:
        raise AutonomousT0Error(f"{path.name}: no PubMed rows parsed")
    return counts


def _seal_pubmed_file(task: tuple[Path, dict]) -> tuple[dict, int]:
    """Hash and parse one PubMed transport in a process-pool-safe worker."""
    path, remote = task
    measured_md5, sha256, size = _hash_file(path)
    if measured_md5 != remote["official_md5"]:
        raise AutonomousT0Error(f"{path.name}: official MD5 mismatch; abstaining")
    counts = _count_pubmed_rows(path)
    return (
        {
            "filename": path.name,
            "url": remote["url"],
            "official_md5": remote["official_md5"],
            "sha256": sha256,
            "bytes": size,
            **counts,
        },
        counts["total_record_count"],
    )


def write_new_json(output: Path, payload: dict) -> None:
    """Write one immutable evidence object; rendering occurs before the exclusive create."""
    rendered = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(rendered)
    except FileExistsError:
        raise AutonomousT0Error(f"refusing to overwrite existing evidence: {output}") from None


def seal_local_t0(
    inventory_path: Path,
    baseline_dir: Path,
    mesh_path: Path,
    output: Path,
    *,
    workers: int = 1,
    progress: Callable[[int, int, str], None] | None = None,
) -> dict:
    """Create the T0 manifest only after every local source passes the frozen machine gate."""
    if not 1 <= workers <= 8:
        raise AutonomousT0Error("seal workers must be between 1 and 8")
    if output.exists():
        raise AutonomousT0Error(f"refusing to overwrite existing evidence: {output}")
    inventory_bytes = inventory_path.read_bytes()
    payload = json.loads(inventory_bytes.decode("utf-8"))
    year, remote_files, remote_mesh = _validate_remote_inventory(payload)
    if not baseline_dir.is_dir():
        raise AutonomousT0Error(f"baseline directory is missing: {baseline_dir}")
    if not mesh_path.is_file() or mesh_path.name != remote_mesh["filename"]:
        raise AutonomousT0Error("matching local MeSH descriptor file is missing")
    expected_names = [item["filename"] for item in remote_files]
    prefix = str(year)[-2:]
    actual_names = sorted(
        path.name
        for path in baseline_dir.iterdir()
        if path.is_file() and re.fullmatch(rf"pubmed{prefix}n\d{{4}}\.xml\.gz", path.name)
    )
    if actual_names != expected_names:
        raise AutonomousT0Error("local PubMed files do not exactly cover the remote inventory")

    sealed_files = []
    total_records = 0
    tasks = [(baseline_dir / remote["filename"], remote) for remote in remote_files]

    def collect(results) -> None:
        nonlocal total_records
        # Both built-in map and executor.map preserve inventory order, so concurrency cannot alter
        # the manifest bytes.
        for completed, (sealed, record_count) in enumerate(results, start=1):
            sealed_files.append(sealed)
            total_records += record_count
            if progress is not None:
                progress(completed, len(remote_files), sealed["filename"])

    if workers == 1:
        collect(map(_seal_pubmed_file, tasks))
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            collect(executor.map(_seal_pubmed_file, tasks))

    mesh_md5, mesh_sha256, mesh_bytes = _hash_file(mesh_path)
    del mesh_md5
    if (
        mesh_sha256 != remote_mesh["observed_transport_sha256"]
        or mesh_bytes != remote_mesh["bytes"]
    ):
        raise AutonomousT0Error("MeSH descriptor transport differs from remote inventory")
    descriptor_count = _inspect_mesh_bytes(mesh_path.read_bytes(), mesh_path.name)
    if descriptor_count != remote_mesh["descriptor_count"]:
        raise AutonomousT0Error("MeSH descriptor count differs from remote inventory")

    manifest = {
        "schema_version": 1,
        "kind": "autonomous_prospective_t0",
        "status": "locally_verified_complete_t0",
        "protocol_id": "autonomous-prospective-pubmed-link-emergence-v1",
        "release_year": year,
        "remote_inventory": {
            "filename": inventory_path.name,
            "sha256": sha256_payload(payload),
            "canonicalisation": "canonical-json-v1",
        },
        "pubmed_baseline": {
            "file_count": len(sealed_files),
            "files": sealed_files,
        },
        "mesh_descriptor": {
            "filename": mesh_path.name,
            "url": remote_mesh["url"],
            "sha256": mesh_sha256,
            "bytes": mesh_bytes,
            "descriptor_count": descriptor_count,
        },
        "total_record_count": total_records,
        "human_dependencies": [],
        "readiness_contribution": 0,
        "state_transition": {
            "from": "awaiting_t0_baseline",
            "to": "awaiting_frozen_metric",
        },
        "claim_boundary": "This seals source identity only. It is not a metric result, validation result, or knowledge-gap claim.",
    }
    write_new_json(output, manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    discover = subparsers.add_parser("discover")
    discover.add_argument("--release-year", type=int, default=2026)
    discover.add_argument("--workers", type=int, default=16)
    discover.add_argument("--output", type=Path, required=True)
    audit = subparsers.add_parser("audit")
    audit.add_argument("--inventory", type=Path, default=REMOTE_INVENTORY_PATH)
    download = subparsers.add_parser("download")
    download.add_argument("--inventory", type=Path, default=REMOTE_INVENTORY_PATH)
    download.add_argument("--baseline-dir", type=Path, required=True)
    download.add_argument("--mesh", type=Path, required=True)
    download.add_argument("--workers", type=int, default=4)
    download.add_argument("--minimum-free-gib", type=float, default=40.0)
    seal = subparsers.add_parser("seal")
    seal.add_argument("--inventory", type=Path, required=True)
    seal.add_argument("--baseline-dir", type=Path, required=True)
    seal.add_argument("--mesh", type=Path, required=True)
    seal.add_argument("--output", type=Path, required=True)
    seal.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    try:
        if args.command == "discover":
            result = discover_remote_inventory(
                release_year=args.release_year,
                workers=args.workers,
            )
            write_new_json(args.output, result)
            print(f"remote inventory: {args.output}")
            print(f"release: {result['release_year']}")
            print(f"PubMed files: {result['pubmed_baseline']['expected_file_count']}")
            print(f"MeSH descriptors: {result['mesh_descriptor']['descriptor_count']}")
            print("readiness contribution: 0 (local source bytes are not sealed)")
        elif args.command == "audit":
            result = audit_remote_inventory(args.inventory)
            print(f"remote inventory: {result.path}")
            print(f"canonical JSON SHA-256: {result.sha256}")
            print(f"release: {result.release_year}")
            print(f"PubMed files: {result.pubmed_file_count}")
            print(f"MeSH descriptors: {result.mesh_descriptor_count}")
            print("readiness contribution: 0 (local source bytes are not sealed)")
        elif args.command == "download":
            if args.minimum_free_gib < 0:
                raise AutonomousT0Error("minimum free GiB cannot be negative")

            def show_progress(completed: int, total: int, filename: str, outcome: str) -> None:
                if completed % 25 == 0 or completed == total or filename.startswith("desc"):
                    print(
                        f"verified transports: {completed}/{total} · {filename} · {outcome}",
                        flush=True,
                    )

            result = download_t0_sources(
                args.inventory,
                args.baseline_dir,
                args.mesh,
                workers=args.workers,
                minimum_free_bytes=int(args.minimum_free_gib * 1024**3),
                progress=show_progress,
            )
            print(f"release: {result.release_year}")
            print(f"PubMed files verified: {result.pubmed_file_count}")
            print(f"downloaded: {result.downloaded_count}")
            print(f"reused: {result.reused_count}")
            print(f"verified bytes: {result.verified_bytes}")
            print("readiness contribution: 0 (run seal after complete acquisition)")
        else:
            def show_seal_progress(completed: int, total: int, filename: str) -> None:
                if completed % 25 == 0 or completed == total:
                    print(
                        f"sealed PubMed files: {completed}/{total} · {filename}",
                        flush=True,
                    )

            result = seal_local_t0(
                args.inventory,
                args.baseline_dir,
                args.mesh,
                args.output,
                workers=args.workers,
                progress=show_seal_progress,
            )
            print(f"sealed T0: {args.output}")
            print(f"PubMed files: {result['pubmed_baseline']['file_count']}")
            print(f"PubMed rows: {result['total_record_count']}")
            print("state: awaiting_frozen_metric")
    except (AutonomousT0Error, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
