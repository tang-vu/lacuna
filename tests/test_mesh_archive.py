from __future__ import annotations

import gzip
import hashlib

from pipeline.benchmark.pin_mesh import (
    descriptor_url,
    inspect_descriptor_archive,
    pin_descriptor_archive,
)

SAMPLE_XML = b"""<?xml version="1.0"?>
<DescriptorRecordSet>
  <DescriptorRecord DescriptorClass="1">
    <DescriptorUI>D000001</DescriptorUI>
    <DescriptorName><String>Example</String></DescriptorName>
  </DescriptorRecord>
</DescriptorRecordSet>
"""


class FakeRaw:
    def __init__(self, body: bytes):
        self.body = body
        self.decode_content = True

    def stream(self, chunk_size: int, decode_content: bool):
        assert not decode_content
        yield self.body[:chunk_size]
        yield self.body[chunk_size:]


class FakeResponse:
    status_code = 200

    def __init__(self, body: bytes):
        self.raw = FakeRaw(body)


class FakeSession:
    def __init__(self, body: bytes):
        self.body = body
        self.urls: list[str] = []

    def get(self, url: str, **kwargs):
        self.urls.append(url)
        return FakeResponse(self.body)


def test_descriptor_urls_handle_the_combined_legacy_directory():
    assert descriptor_url(2006).endswith("/1999-2010/xmlmesh/desc2006.gz")
    assert descriptor_url(2010).endswith("/1999-2010/xmlmesh/desc2010.gz")
    assert descriptor_url(2011).endswith("/2011/xmlmesh/desc2011.gz")


def test_inspection_hashes_compressed_bytes_and_counts_descriptors(tmp_path):
    path = tmp_path / "desc2011.gz"
    with gzip.open(path, "wb") as stream:
        stream.write(SAMPLE_XML)
    compressed = path.read_bytes()

    sha256, size, descriptor_count = inspect_descriptor_archive(path)

    assert sha256 == hashlib.sha256(compressed).hexdigest()
    assert size == len(compressed)
    assert descriptor_count == 1


def test_pin_downloads_to_cache_and_returns_reproducible_identity(tmp_path):
    compressed_path = tmp_path / "fixture.gz"
    with gzip.open(compressed_path, "wb") as stream:
        stream.write(SAMPLE_XML)
    body = compressed_path.read_bytes()
    cache_dir = tmp_path / "cache"
    session = FakeSession(body)

    pin = pin_descriptor_archive(2012, cache_dir=cache_dir, session=session)

    assert session.urls == [descriptor_url(2012)]
    assert pin.sha256 == hashlib.sha256(body).hexdigest()
    assert pin.descriptor_count == 1
    assert (cache_dir / "desc2012.gz").read_bytes() == body
