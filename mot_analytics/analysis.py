from dataclasses import dataclass
import re
import unicodedata
from itertools import combinations

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import silhouette_score
from sklearn.metrics.pairwise import cosine_similarity
from threadpoolctl import threadpool_limits

KO_STOP = set("및 등 대한 통해 위한 관련 경우 당사 사업 회사 기업 제공 주요 해당 보고서 현재 또한 있다 한다 하고 있습니다 있는 합니다 이러한 것으로 분야 서비스를 서비스".split())
KO_STOP.update('있으며 당사는 따라 국내 등의 같습니다 다음과 다양한 대하여 대해 통하여 이에 이상 이하 미만 해당사항 없음 없습니다 사항 내용 기준 구분 합계 단위 백만원 천원 현재까지 지속적으로 당사의 회사의 사업의 통해서 이를 위해 아니라 되었습니다 하고자 위한 있도록 있는지 있다고 있습니다 등으로 대한 관한 따른 그리고 또는 모두 각각 총 중 내 년 월 일 원'.split())
KO_STOP.update('에서 에게 까지 부터 보다 처럼 으로 로서 로써 하고 하여 하며 등은 등이 등과 등을 하는 하게 되어 되는 하였으며 되었으며 있었다 있다 있고 있어 없이 이를 이는 위하여 것으로 때문에 있으나 따라서 그래서 그러나 다만 및에는 또한 그 외 본 제 따른다 있다면 합니다만 합니다 있습니다만'.split())


def normalize(text):
    text = unicodedata.normalize("NFKC", str(text)).lower()
    return re.sub(r"\s+", " ", text).strip()


def ko_tokens(text):
    return [token for token in re.findall(r"[가-힣a-z][가-힣a-z0-9]{1,}", normalize(text)) if token not in KO_STOP and not re.fullmatch(r'제\d+(?:기|회)',token)]


@dataclass
class Analysis:
    matrix: object
    vectorizer: object
    similarity: np.ndarray
    labels: np.ndarray
    coordinates: np.ndarray
    keywords: dict
    silhouette: float | None
    explained_variance: float


def analyze(texts, clusters=4, language="en"):
    texts = [normalize(text) for text in texts]
    if len(texts) < 4:
        raise ValueError("지도 분석에는 문서가 최소 4개 필요합니다.")
    if any(len(text) < 30 for text in texts):
        raise ValueError("각 문서는 분석 가능한 원문 30자 이상이어야 합니다.")
    options = dict(ngram_range=(1, 2), max_features=6000, sublinear_tf=True, min_df=1, max_df=1.0)
    if language == "ko":
        options.update(tokenizer=ko_tokens, token_pattern=None)
    else:
        options.update(stop_words="english", strip_accents="unicode")
    vectorizer = TfidfVectorizer(**options)
    try:
        matrix = vectorizer.fit_transform(texts)
    except ValueError as error:
        raise ValueError("전처리 후 유효한 단어가 없습니다. 원문과 언어 설정을 확인하세요.") from error
    if matrix.shape[1] < 2 or np.any(np.asarray(matrix.sum(axis=1)).ravel() == 0):
        raise ValueError("일부 문서의 유효 단어가 부족합니다. 더 긴 원문을 입력하세요.")
    unique = len({tuple(zip(row.indices, row.data)) for row in matrix})
    if unique < 2:
        raise ValueError("모든 문서가 동일합니다. 서로 다른 원문이 필요합니다.")
    k = min(max(2, int(clusters)), len(texts) - 1, unique)
    with threadpool_limits(limits=1):
        labels = KMeans(n_clusters=k, random_state=42, n_init=10).fit_predict(matrix)
    projection = TruncatedSVD(n_components=2, random_state=42)
    coordinates = projection.fit_transform(matrix)
    similarity = np.clip(cosine_similarity(matrix), 0, 1)
    names = vectorizer.get_feature_names_out()
    keywords = {}
    for label in sorted(set(labels)):
        scores = np.asarray(matrix[labels == label].mean(axis=0)).ravel()
        keywords[int(label)] = [str(names[i]) for i in scores.argsort()[::-1][:6] if scores[i] > 0]
    score = silhouette_score(matrix, labels, metric="cosine") if 1 < len(set(labels)) < len(texts) else None
    return Analysis(matrix, vectorizer, similarity, labels, coordinates, keywords, score,
                    float(np.nan_to_num(projection.explained_variance_ratio_).sum()))


def neighbors(result, index, count=3):
    order = np.argsort(-result.similarity[index], kind="stable")
    return [(int(i), float(result.similarity[index, i])) for i in order if i != index][:count]


def comparison_terms(result, left, right, count=8):
    a = result.matrix[left].toarray().ravel()
    b = result.matrix[right].toarray().ravel()
    names = result.vectorizer.get_feature_names_out()
    def top(scores):
        return [str(names[i]) for i in scores.argsort()[::-1][:count] if scores[i] > 0]
    return top(np.minimum(a, b)), top(np.maximum(a - b, 0)), top(np.maximum(b - a, 0))


def evidence(text, terms, count=3):
    sentences = re.split(r"(?<=[.!?。])\s+|\n+", str(text))
    ranked = sorted(enumerate(sentences), key=lambda item: (-sum(term in normalize(item[1]) for term in terms), item[0]))
    hits = [sentence.strip() for _, sentence in ranked if any(term in normalize(sentence) for term in terms)]
    return hits[:count] or [str(text)[:700]]


def representatives(result, label, count=3):
    indices = np.where(result.labels == label)[0]
    center = result.matrix[indices].mean(axis=0)
    scores = cosine_similarity(result.matrix[indices], np.asarray(center)).ravel()
    return [int(indices[i]) for i in np.argsort(-scores)[:count]]


def cooccurrences(result, top_n=16):
    # Reuse original unigram columns so counts refer to distinct documents.
    names = result.vectorizer.get_feature_names_out()
    unigram_indices = [i for i, name in enumerate(names) if " " not in name]
    counts = np.asarray((result.matrix[:, unigram_indices] > 0).sum(axis=0)).ravel()
    chosen = [unigram_indices[i] for i in counts.argsort()[::-1][:top_n]]
    binary = (result.matrix[:, chosen] > 0).astype(int)
    pair_counts = (binary.T @ binary).toarray()
    rows = [(names[chosen[i]], names[chosen[j]], int(pair_counts[i, j]))
            for i, j in combinations(range(len(chosen)), 2) if pair_counts[i, j] >= 2]
    return pd.DataFrame(rows, columns=["keyword_a", "keyword_b", "documents"]).sort_values("documents", ascending=False)


def period_shares(frame, labels, periods):
    table = pd.crosstab(pd.Series(labels, name="cluster"), frame["period"].reset_index(drop=True))
    table = table.reindex(columns=periods, fill_value=0)
    rows = []
    for period in periods:
        total = int(table[period].sum())
        for cluster in table.index:
            count = int(table.loc[cluster, period])
            rows.append({"cluster": str(cluster + 1), "period": period, "count": count,
                         "sample_n": total, "share": count / total if total else 0.0})
    return pd.DataFrame(rows)
