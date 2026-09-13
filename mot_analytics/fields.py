from mot_analytics.public_data import OPENALEX_QUERY, collect_kind, collect_openalex

FIELDS = {
    "반도체·AI 하드웨어": ("papers_semiconductor", OPENALEX_QUERY, True),
    "AI·소프트웨어": ("papers_ai", '"large language model" OR "generative AI"', False),
    "자동차·자율주행": ("papers_mobility", '"autonomous driving" OR "vehicle perception"', False),
    "바이오·의료 AI": ("papers_bio", '"drug discovery" OR "medical imaging"', False),
}
PERIODS = [("2025년 1~8월", "2025-01-01", "2025-08-31"), ("2026년 1~8월", "2026-01-01", "2026-08-31")]

def collect_fields():
    collect_kind()
    for field, (name, query, hardware) in FIELDS.items():
        collect_openalex(60, query, PERIODS, hardware, name, field)
        print(f"Collected {field}", flush=True)

if __name__ == "__main__":
    collect_fields()
