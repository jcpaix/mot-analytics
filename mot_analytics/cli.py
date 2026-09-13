import argparse
import json
import os

from mot_analytics.analysis import analyze, neighbors, period_shares
from mot_analytics.arxiv import DEFAULT_QUERY, save_default
from mot_analytics.dart import collect_companies
from mot_analytics.storage import DATA, ROOT, read_dataset


def report():
    if (DATA/'processed/papers_ai.csv').exists():
        from mot_analytics.reporting import field_report
        field_report()
        return
    frame, manifest = read_dataset(DATA / "processed" / "papers.csv")
    result = analyze(frame["title"] + ". " + frame["abstract"])
    periods = [record["period"] for record in manifest["periods"]]
    shares = period_shares(frame, result.labels, periods)
    lines = ["# 첫 번째 실제 분석 — AI 반도체 논문", "", f"실제 arXiv 논문 {len(frame)}개를 분석했다. 수집 출처: {manifest['source']}.", "",
             f"검색식: `{manifest['query']}`", "", "방법: 제목과 초록의 영어 단어 TF-IDF(1~2그램), 코사인 유사도, KMeans(k=4, seed=42), SVD 2차원 투영.", "",
             "## 수집 조건", ""]
    for record in manifest["periods"]:
        lines.append(f"- {record['period']}: {record['start_date']} ~ {record['end_date']}, 검색 일치 {record['total_matches']}개 중 {record['retained']}개. 상한 적용: {record['capped']}. 수집 시점: {record['collected_at']}.")
    lines += ["", "버전 접미사를 제거한 arXiv ID로 중복을 제거했다. 원본 API 응답과 요청 조건을 data/raw 아래의 해당 수집기 폴더에 보존했다.", "", f"날짜 기준: {manifest.get('date_basis', 'arXiv first submitted date')}.", "", "## 표본 내 주제", ""]
    for label, keywords in result.keywords.items():
        group = shares[shares.cluster == str(label + 1)]
        values = "; ".join(f"{r.period}: {r['count']}/{r.sample_n} ({r.share:.1%})" for _, r in group.iterrows())
        lines.append(f"- 군집 {label + 1}, {', '.join(keywords[:4])}: {values}")
    lines += ["", f"코사인 기준 실루엣 점수: {result.silhouette:.3f}. 2차원 투영 설명 분산 비율: {result.explained_variance:.1%}.", "", "## 원문 대조용 유사 논문", ""]
    for index in [0, len(frame) // 2]:
        other, similarity = neighbors(result, index, 1)[0]
        lines += [f"- [{frame.iloc[index].title}]({frame.iloc[index].source_url}) ↔ [{frame.iloc[other].title}]({frame.iloc[other].source_url}), 코사인 유사도 {similarity:.3f}.",
                  f"  - 첫 원문: {frame.iloc[index].abstract[:400]}", f"  - 비교 원문: {frame.iloc[other].abstract[:400]}"]
    lines += ["", "## 해석과 한계", "", "검색식과 초록에 나타난 표현을 기준으로 묶은 탐색 결과다. 키워드는 자동 라벨이며 전문가가 확정한 기술 분류가 아니다. 각 기간의 최신순 제한 표본이므로 전체 연구량의 증가나 기술 시장의 성장으로 해석할 수 없다. 실루엣과 투영 설명 분산도 기술적 타당성을 입증하지 않는다.", "", "기업 지도에는 한국거래소 KIND의 실제 2025년 결산 사업보고서 10개를 연결했다. 원문 표지의 기업명·결산일을 확인했으며 사업 절과 재무 절의 경계를 기준으로 추출했다. 기업별 출처와 수집 시점은 companies.manifest.json 및 화면에 제공한다.", ""]
    output = ROOT / "reports" / "first_analysis.md"
    output.parent.mkdir(exist_ok=True)
    if result.silhouette is not None and result.silhouette < 0.05:
        lines += ["현재 표본의 실루엣 점수가 낮아 단어 기준 군집의 분리가 약하다. 뚜렷한 기술 분야나 주제 이동이 발견되었다고 결론내리지 않는다. 원문 검토와 검색 범위 조정이 필요하다.", ""]
    output.write_text("\n".join(line.rstrip() for line in lines), encoding="utf-8")
    print(output)


def main():
    parser = argparse.ArgumentParser(description="MOT Analytics data collection and report")
    parser.add_argument("command", choices=["arxiv", "dart", "report"])
    parser.add_argument("--query", default=DEFAULT_QUERY)
    parser.add_argument("--per-period", type=int, default=60)
    parser.add_argument("--fiscal-year", type=int, default=2025)
    args = parser.parse_args()
    try:
        if args.command == "arxiv":
            frame, manifest = save_default(args.query, args.per_period)
            print(json.dumps({"rows": len(frame), "periods": [{k: r[k] for k in ["period", "total_matches", "retained"]} for r in manifest["periods"]]}, ensure_ascii=False))
        elif args.command == "dart":
            frame, manifest = collect_companies(os.environ.get("DART_API_KEY", ""), fiscal_year=args.fiscal_year)
            print(json.dumps({"rows": len(frame), "errors": manifest["errors"]}, ensure_ascii=False))
        else:
            report()
    except (ValueError, RuntimeError, FileNotFoundError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
