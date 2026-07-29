"""Download, validate, and fingerprint production-year MeSH descriptor archives.

Files are cached under gitignored ``data/mesh/``. The command prints candidate entries for
``benchmarks/v3/sources.json``; it never edits the reviewed source contract itself.

Run:
    python -m pipeline.benchmark.pin_mesh
    python -m pipeline.benchmark.pin_mesh 2007 2011 2012 2013
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from xml.etree import ElementTree

import requests

from pipeline.benchmark.validate_sources import SOURCES_PATH
from pipeline.paths import MESH_CACHE_DIR

MESH_ROOT = "https://nlmpubs.nlm.nih.gov/projects/mesh"
CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class MeshPin:
    year: int
    url: str
    sha256: str
    bytes: int
    descriptor_count: int


def descriptor_url(year: int) -> str:
    if year < 1999:
        raise ValueError("NLM's public XML archive used here begins in 1999")
    directory = "1999-2010" if year <= 2010 else str(year)
    return f"{MESH_ROOT}/{directory}/xmlmesh/desc{year}.gz"


def inspect_descriptor_archive(path: Path) -> tuple[str, int, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_SIZE), b""):
            digest.update(chunk)
            size += len(chunk)

    descriptor_count = 0
    try:
        with gzip.open(path, "rb") as stream:
            for _, element in ElementTree.iterparse(stream, events=("end",)):
                if element.tag.rsplit("}", 1)[-1] == "DescriptorRecord":
                    descriptor_count += 1
                    element.clear()
    except (OSError, ElementTree.ParseError) as exc:
        raise ValueError(f"{path.name}: not a valid gzip-compressed MeSH XML archive") from exc

    if descriptor_count == 0:
        raise ValueError(f"{path.name}: archive contains no DescriptorRecord elements")
    return digest.hexdigest(), size, descriptor_count


def pin_descriptor_archive(
    year: int,
    *,
    cache_dir: Path = MESH_CACHE_DIR,
    session: requests.Session | None = None,
) -> MeshPin:
    url = descriptor_url(year)
    cache_dir.mkdir(parents=True, exist_ok=True)
    destination = cache_dir / f"desc{year}.gz"
    partial = cache_dir / f"desc{year}.gz.part"

    if destination.exists():
        try:
            sha256, size, descriptor_count = inspect_descriptor_archive(destination)
        except ValueError:
            destination.unlink()
        else:
            return MeshPin(
                year=year,
                url=url,
                sha256=sha256,
                bytes=size,
                descriptor_count=descriptor_count,
            )

    if not destination.exists():
        client = session or requests.Session()
        try:
            response = client.get(url, stream=True, timeout=120)
        except requests.RequestException:
            raise RuntimeError(f"MeSH download failed for {url}") from None
        if response.status_code != 200:
            raise RuntimeError(f"MeSH download returned HTTP {response.status_code} for {url}")
        try:
            response.raw.decode_content = False
            with partial.open("wb") as stream:
                for chunk in response.raw.stream(CHUNK_SIZE, decode_content=False):
                    if chunk:
                        stream.write(chunk)
            partial.replace(destination)
        finally:
            with suppress(FileNotFoundError):
                partial.unlink()

    sha256, size, descriptor_count = inspect_descriptor_archive(destination)
    return MeshPin(
        year=year,
        url=url,
        sha256=sha256,
        bytes=size,
        descriptor_count=descriptor_count,
    )


def required_years(path: Path = SOURCES_PATH) -> list[int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    years = payload.get("required_baseline_years")
    if not isinstance(years, list) or not all(isinstance(year, int) for year in years):
        raise ValueError("sources.json does not contain valid required baseline years")
    return sorted(set(years))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("years", nargs="*", type=int)
    args = parser.parse_args()
    years = sorted(set(args.years)) if args.years else required_years()
    pins = [asdict(pin_descriptor_archive(year)) for year in years]
    print(
        json.dumps(
            {
                "source": "NLM production-year MeSH descriptor archives",
                "files": pins,
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
