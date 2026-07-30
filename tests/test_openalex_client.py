from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pipeline.openalex_client as openalex
from pipeline.openalex_client import OpenAlexClient, sanitise_url


def query(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query)


def test_public_urls_never_contain_request_credentials(monkeypatch):
    monkeypatch.setattr(openalex, "MAILTO", "maintainer@example.test")
    monkeypatch.setattr(openalex, "API_KEY", "secret-key")
    client = object.__new__(OpenAlexClient)

    request_url = client.build_url("works", {"filter": "topics.id:T1"})
    public_url = client.build_public_url("works", {"filter": "topics.id:T1"})

    assert query(request_url)["mailto"] == ["maintainer@example.test"]
    assert query(request_url)["api_key"] == ["secret-key"]
    assert "mailto" not in query(public_url)
    assert "api_key" not in query(public_url)


def test_sanitise_url_removes_credentials_without_changing_query():
    url = (
        "https://api.openalex.org/works?filter=topics.id:T1,topics.id:T2"
        "&mailto=person@example.test&api_key=secret&per-page=1"
    )
    cleaned = sanitise_url(url)
    params = query(cleaned)

    assert params["filter"] == ["topics.id:T1,topics.id:T2"]
    assert params["per-page"] == ["1"]
    assert "mailto" not in params
    assert "api_key" not in params
