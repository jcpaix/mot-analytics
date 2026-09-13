import numpy as np
import pandas as pd
import pytest

from mot_analytics.analysis import analyze, cooccurrences, neighbors, period_shares
from mot_analytics.arxiv import collect, parse_feed
from mot_analytics.dart import extract_business, validate_companies
from mot_analytics.storage import DATA, read_dataset, write_dataset


def test_company_similarity_and_projection():
    frame, _ = read_dataset(DATA.parent / "tests" / "fixtures" / "companies.csv")
    result = analyze(frame.text, language="ko")
    assert result.coordinates.shape == (12, 2)
    assert np.isfinite(result.coordinates).all()
    assert np.allclose(result.similarity, result.similarity.T)
    assert np.allclose(np.diag(result.similarity), 1)
    assert neighbors(result, 0, 1)[0][0] == 1
    assert 0 not in [index for index, _ in neighbors(result, 0)]


def test_empty_and_identical_documents_are_rejected():
    with pytest.raises(ValueError):
        analyze(["the and for with " * 4] * 4)
    with pytest.raises(ValueError, match="동일"):
        analyze(["memory hardware accelerator neural processing " * 3] * 4)


def test_period_denominators_use_each_actual_sample():
    frame = pd.DataFrame({"period": ["A", "A", "A", "B"]})
    shares = period_shares(frame, np.array([0, 0, 1, 1]), ["A", "B"])
    assert shares.loc[(shares.cluster == "1") & (shares.period == "A"), "share"].iloc[0] == 2 / 3
    assert shares.groupby("period").share.sum().eq(1).all()


def test_arxiv_versions_and_metadata():
    payload = b'''<feed xmlns="http://www.w3.org/2005/Atom" xmlns:os="http://a9.com/-/spec/opensearch/1.1/">
    <os:totalResults>9</os:totalResults><entry><id>http://arxiv.org/abs/2501.00001v3</id>
    <title>Hardware accelerator</title><summary>Neural network memory architecture</summary>
    <published>2025-01-02T00:00:00Z</published><updated>2025-03-01T00:00:00Z</updated>
    <author><name>Researcher</name></author><category term="cs.AR"/></entry></feed>'''
    rows, total = parse_feed(payload, "2026-09-13T00:00:00Z")
    assert total == 9
    assert rows[0]["paper_id"] == "2501.00001"
    assert rows[0]["version_id"] == "2501.00001v3"
    assert rows[0]["source_url"] == "https://arxiv.org/abs/2501.00001"


def test_overlapping_periods_fail_before_network():
    with pytest.raises(ValueError, match="겹치"):
        collect(periods=[("A", "2025-01-01", "2025-06-30"), ("B", "2025-06-01", "2025-12-31")])


def test_dart_extracts_business_section_only():
    business = "신경망 반도체 설계와 메모리 연구개발을 진행한다. " * 20
    payload = f"<document><title>I. 회사 개요</title><p>개요</p><title>II. 사업의 내용</title><p>{business}</p><title>III. 재무에 관한 사항</title><p>재무표제외</p></document>".encode()
    text = extract_business(payload)
    assert "신경망" in text
    assert "재무표제외" not in text
    assert "개요" not in text


def test_company_input_requires_provenance_and_no_duplicates():
    frame, _ = read_dataset(DATA.parent / "tests" / "fixtures" / "companies.csv")
    assert len(validate_companies(frame)) == 12
    with pytest.raises(ValueError):
        validate_companies(frame.drop(columns="source_url"))
    with pytest.raises(ValueError, match="중복"):
        validate_companies(pd.concat([frame, frame.iloc[[0]]]))


def test_dataset_integrity(tmp_path):
    path = tmp_path / "data.csv"
    write_dataset(pd.DataFrame({"text": ["원문"]}), path, {"source": "test"})
    assert read_dataset(path)[0].text.iloc[0] == "원문"
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="변경"):
        read_dataset(path)


def test_cooccurrences_are_document_counts():
    texts = ["memory neural hardware architecture design " * 2, "memory neural hardware inference accelerator " * 2,
             "optical quantum computing processor design " * 2, "quantum optical processor circuit fabrication " * 2]
    result = analyze(texts, clusters=2)
    edges = cooccurrences(result)
    pair = edges[((edges.keyword_a == "memory") & (edges.keyword_b == "neural")) | ((edges.keyword_a == "neural") & (edges.keyword_b == "memory"))]
    assert pair.documents.iloc[0] == 2
