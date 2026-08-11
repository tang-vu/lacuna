from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from pipeline.benchmark.bioasq_download import (
    BioasqDownloadError,
    _stream_response,
    extract_csrf_token,
)


class _Response:
    def __init__(self, payload: bytes, *, content_type: str = "application/zip") -> None:
        self.payload = payload
        self.headers = {"Content-Type": content_type, "Content-Length": str(len(payload))}

    def raise_for_status(self) -> None:
        return None

    def iter_content(self, chunk_size: int):
        yield self.payload[:2]
        yield b""
        yield self.payload[2:]


def test_extract_csrf_token_uses_named_hidden_input():
    html = '<form><input value="token-123" type="hidden" name="csrfmiddlewaretoken"></form>'

    assert extract_csrf_token(html) == "token-123"


def test_extract_csrf_token_rejects_changed_login_form():
    with pytest.raises(BioasqDownloadError, match="CSRF"):
        extract_csrf_token("<form></form>")


def test_stream_response_writes_atomically_and_checks_digest(tmp_path: Path):
    payload = b"bioasq"
    output = tmp_path / "sample.json"

    result = _stream_response(
        _Response(payload),
        output,
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        expected_bytes=len(payload),
    )

    assert output.read_bytes() == payload
    assert not (tmp_path / "sample.json.part").exists()
    assert result["reused"] is False


def test_stream_response_rejects_login_html_without_writing(tmp_path: Path):
    output = tmp_path / "corpus.zip"

    with pytest.raises(BioasqDownloadError, match="login likely failed"):
        _stream_response(_Response(b"login", content_type="text/html"), output)

    assert not output.exists()
