from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

from pipeline.pubmed_client import (
    PubMedClient,
    PubMedConfigurationError,
    parse_pubmed_xml,
    sanitise_eutils_url,
)

SAMPLE_XML = """\
<PubmedArticleSet>
 <PubmedArticle>
  <MedlineCitation Status="MEDLINE" IndexingMethod="Manual">
   <PMID Version="1">3797213</PMID>
   <Article>
    <Journal><JournalIssue><PubDate><MedlineDate>1986 Autumn</MedlineDate></PubDate></JournalIssue></Journal>
    <ArticleTitle>Fish oil and <i>Raynaud's syndrome</i></ArticleTitle>
    <ELocationID EIdType="doi">10.1353/pbm.1986.0087</ELocationID>
   </Article>
   <MeshHeadingList>
    <MeshHeading>
     <DescriptorName UI="D005395" MajorTopicYN="Y">Fish Oils</DescriptorName>
     <QualifierName UI="Q000627" MajorTopicYN="Y">therapeutic use</QualifierName>
    </MeshHeading>
   </MeshHeadingList>
  </MedlineCitation>
 </PubmedArticle>
</PubmedArticleSet>
"""


class FakeResponse:
    status_code = 200
    text = SAMPLE_XML


class FakeSession:
    def __init__(self):
        self.urls = []

    def get(self, url, timeout):
        self.urls.append((url, timeout))
        return FakeResponse()


class FailingSession:
    def get(self, url, timeout):
        raise requests.ConnectionError(f"failed for {url}")


def test_parse_pubmed_xml_keeps_metadata_and_mesh_but_no_abstract():
    records = parse_pubmed_xml(SAMPLE_XML)

    assert records == [
        {
            "pmid": "3797213",
            "title": "Fish oil and Raynaud's syndrome",
            "publication_year": 1986,
            "doi": "10.1353/pbm.1986.0087",
            "citation_status": "MEDLINE",
            "indexing_method": "Manual",
            "mesh_headings": [
                {
                    "descriptor_ui": "D005395",
                    "descriptor_label": "Fish Oils",
                    "major_topic": True,
                    "qualifiers": [
                        {
                            "qualifier_ui": "Q000627",
                            "qualifier_label": "therapeutic use",
                            "major_topic": True,
                        }
                    ],
                }
            ],
        }
    ]
    assert "abstract" not in records[0]


def test_public_url_strips_email_and_api_key(tmp_path):
    client = PubMedClient(
        tmp_path,
        email="maintainer@example.test",
        api_key="secret",
    )
    request = client.build_url(["3797213"])
    public = client.build_public_url(["3797213"])

    assert parse_qs(urlsplit(request).query)["email"] == ["maintainer@example.test"]
    assert parse_qs(urlsplit(request).query)["api_key"] == ["secret"]
    assert "email" not in parse_qs(urlsplit(public).query)
    assert "api_key" not in parse_qs(urlsplit(public).query)
    assert sanitise_eutils_url(request) == public


def test_network_request_requires_registered_email(tmp_path):
    client = PubMedClient(tmp_path, email="", api_key="", use_cache=False)

    with pytest.raises(PubMedConfigurationError, match="NCBI_EMAIL is required"):
        client.fetch_records(["3797213"])


def test_invalid_pmids_fail_before_sorting_or_network(tmp_path):
    client = PubMedClient(tmp_path, email="", use_cache=False)

    with pytest.raises(ValueError, match="digits only"):
        client.fetch_records(["not-a-pmid"])


def test_cache_contains_trimmed_payload_and_public_url_only(tmp_path):
    session = FakeSession()
    client = PubMedClient(
        tmp_path,
        email="maintainer@example.test",
        api_key="secret",
        session=session,
    )

    payload = client.fetch_records(["3797213"])
    cache_text = next(tmp_path.glob("*.json")).read_text(encoding="utf-8")

    assert payload["mesh_basis"] == "maintained_current_pubmed"
    assert payload["records"][0]["pmid"] == "3797213"
    assert "maintainer@example.test" not in cache_text
    assert "secret" not in cache_text
    assert json.loads(cache_text)["source_url"] == client.build_public_url(["3797213"])
    assert session.urls[0][1] == 60


def test_network_error_does_not_echo_credentials(tmp_path):
    client = PubMedClient(
        tmp_path,
        email="maintainer@example.test",
        api_key="secret",
        use_cache=False,
        session=FailingSession(),
    )

    with pytest.raises(RuntimeError) as caught:
        client.fetch_records(["3797213"])

    message = str(caught.value)
    assert "maintainer@example.test" not in message
    assert "secret" not in message
    assert "https://eutils.ncbi.nlm.nih.gov/" in message
