# -*- coding: utf-8 -*-
"""
PHASE 2-A — §10 "피해야 할 물질" baseline 공식 고정 (재현 가능한 단일 버전)

기존에 존재하던 서로 다른 두 수치(docs/decisions.md §1.2a-upd의 55.3%/22.3%,
expand_by_reaction_frequency.py 주석의 47.6%/34.9%/23.0%)는 계산 코드가 남아있지
않아 재현 불가능했다(chemical_selection_audit_2026-08-08.md §5에서 발견).
이 스크립트가 그 자리를 대신하는 유일한 재현 가능 버전이다.

분류 규칙(S10_CATEGORIES)과 텍스트 판정 함수(s10_categories_for_text)는
02_classification/provenance_audit.py와 완전히 동일한 것을 그대로 import해서 쓴다
(같은 로직을 두 곳에 따로 유지하면 다시 불일치가 생기므로 단일 출처 원칙 적용).

읽기 전용 실행 — DB/CSV에 쓰기 없음. 산출물은 docs/section10_baseline_2026-08-08.md.
"""
import csv
import sqlite3
from collections import Counter, defaultdict

from provenance_audit import (
    DB_PATH, CSV_PATH, S10_CATEGORIES, SOURCE_MAP, s10_categories_for_text,
)

OUT_REPORT_MD = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\docs\section10_baseline_2026-08-08.md"


def main():
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        csv_rows = list(csv.DictReader(f))
    candidate_cas = {r["cas_number"]: r["source"] for r in csv_rows}

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # 분모 확정: "candidate CSV(475행)와 연결되며 4섹션(2/3/9/10) 전부 확보된 CAS"
    # (chemical_selection_audit_2026-08-08.md §0에서 확정한 정의 그대로 재사용 —
    # DB 전체를 그냥 세면 orphan 1건이 섞여 427이 나오는 문제를 피한다)
    section_count = Counter()
    for cas, cnt in cur.execute(
        "SELECT cas_number, COUNT(DISTINCT section) FROM msds_sections GROUP BY cas_number"
    ):
        section_count[cas] = cnt
    collected_cas = sorted(
        cas for cas in candidate_cas if section_count.get(cas, 0) == 4
    )

    s10_text = {}
    for cas, detail in cur.execute(
        "SELECT cas_number, item_detail FROM msds_sections "
        "WHERE section=10 AND item_name_kor='피해야 할 물질'"
    ):
        s10_text[cas] = detail or ""
    con.close()

    n = len(collected_cas)
    cat_hits = defaultdict(list)  # category -> [cas...]
    for cas in collected_cas:
        text = s10_text.get(cas, "")
        for cat in s10_categories_for_text(text):
            cat_hits[cat].append(cas)

    # wave 분해(원본 source -> wave)
    def wave_of(cas):
        return SOURCE_MAP.get(candidate_cas.get(cas), ("unknown", "unknown"))[0]

    cat_wave_breakdown = {}
    for cat, cas_list in cat_hits.items():
        cat_wave_breakdown[cat] = Counter(wave_of(c) for c in cas_list)

    # ---- 리포트 렌더링 ----
    lines = []
    lines.append("# §10 \"피해야 할 물질\" Baseline — 공식 고정 (PHASE 2-A)")
    lines.append("")
    lines.append("**작성일**: 2026-08-08")
    lines.append(
        "**실행 스크립트**: [`02_classification/section10_baseline.py`]"
        "(../02_classification/section10_baseline.py) (읽기 전용, DB/CSV 미변경)"
    )
    lines.append("")
    lines.append(
        "이 문서가 앞으로 §10 위험관계 빈도를 인용할 때 쓰는 **유일한 공식 baseline**"
        "이다. 기존에 인용됐던 두 수치(`docs/decisions.md` §1.2a-upd의 55.3%/22.3%, "
        "`01_collection/expand_by_reaction_frequency.py` 주석의 47.6%/34.9%/23.0%)는 "
        "계산 코드가 보존되지 않아 재현이 불가능하므로 더 이상 인용하지 않는다."
    )
    lines.append("")
    lines.append("## 1. 방법론 (재현에 필요한 전부)")
    lines.append("")
    lines.append("| 항목 | 값 |")
    lines.append("|---|---|")
    lines.append(
        "| 원본 문서 | `msds_sections` 테이블, `section=10` AND "
        "`item_name_kor='피해야 할 물질'` 행의 `item_detail` 컬럼 |"
    )
    lines.append(
        f"| 분모(모집단) | candidate CSV(`undergrad_target_chemicals.csv`, 475행)와 "
        f"연결되며 4섹션(2/3/9/10)을 전부 확보한 CAS = **{n}종** "
        f"(DB를 그냥 세면 orphan 1건이 섞여 427이 나옴 — "
        f"`chemical_selection_audit_2026-08-08.md` §0 참고, 이 문서는 그 orphan을 제외한 "
        f"{n}종을 분모로 쓴다) |"
    )
    lines.append(
        "| 청크/단위 | 물질(CAS) 단위 — 한 물질의 §10 \"피해야 할 물질\" 원문 전체를 "
        "하나의 텍스트로 보고, 카테고리별로 그 문자열이 포함되어 있는지만 판정(문장/청크 "
        "분할 없음) |"
    )
    lines.append(
        "| 분류 규칙 | 아래 표의 문자열이 원문에 **부분 문자열로 포함**되면 해당 "
        "카테고리 히트(대소문자 구분 없음 — 한국어라 해당 없음, 정규식 아닌 단순 `in` "
        "연산자) |"
    )
    lines.append(
        "| 중복 처리 | 한 물질의 §10 원문이 여러 카테고리에 동시 히트할 수 있음(예: "
        "\"가연성 물질(나무, 종이, 기름, 의류 등)\\|금속\\|물\"은 3개 카테고리 전부 "
        "히트) — 카테고리별 % 합이 100%를 넘는 것이 정상. 물질 자신을 두 번 세는 "
        "중복은 없음(카테고리 내부는 물질 CAS 집합, 즉 set 아님을 주의 — 카테고리당 "
        "물질 1개는 1회만 카운트됨) |"
    )
    lines.append(
        "| 재현 방법 | `python 02_classification/section10_baseline.py` (인자 없음, "
        "DB/CSV 경로는 `provenance_audit.py`의 상수를 그대로 import) |"
    )
    lines.append("")
    lines.append("### 카테고리별 키워드 정의 (코드: `provenance_audit.S10_CATEGORIES`)")
    lines.append("")
    lines.append("| 카테고리 | 매칭 문자열(하나라도 포함되면 히트) |")
    lines.append("|---|---|")
    for cat, needles in S10_CATEGORIES.items():
        lines.append(f"| {cat} | {', '.join(needles)} |")
    lines.append("")
    lines.append("## 2. 공식 Baseline 수치")
    lines.append("")
    lines.append(f"**분모: {n}종** (COLLECTED, candidate CSV와 연결됨)")
    lines.append("")
    lines.append("| 카테고리 | 분자(물질 수) | 비율 | wave 분해 |")
    lines.append("|---|---:|---:|---|")
    for cat in S10_CATEGORIES:
        cnt = len(cat_hits.get(cat, []))
        pct = cnt / n
        wb = dict(cat_wave_breakdown.get(cat, {}))
        lines.append(f"| {cat} | {cnt} | {pct:.1%} | {wb} |")
    lines.append("")
    lines.append("## 3. 기존 두 수치와의 차이 — 왜 다른가")
    lines.append("")
    lines.append("| 출처 | 표본 | water | metal | combustible/reducing | 재현 가능? |")
    lines.append("|---|---:|---:|---:|---:|:--:|")
    lines.append(
        "| `docs/decisions.md` §1.2a-upd | 197종 | 55.3% | 22.3% | (측정 안 함) | "
        "아니오 — SQL 쿼리 문자열만 텍스트로 기록, 스크립트 파일로 보존 안 됨 |"
    )
    lines.append(
        "| `expand_by_reaction_frequency.py` 주석 | 204종(명시) | 23.0% | 34.9% | 47.6% | "
        "아니오 — 스크립트 자체엔 §10 텍스트 분석 코드가 없고 docstring에 결과만 인용 |"
    )
    water_pct = len(cat_hits.get('water', [])) / n
    metal_pct = len(cat_hits.get('metal', [])) / n
    cr_pct = len(cat_hits.get('combustible_reducing', [])) / n
    lines.append(
        f"| **이 문서(공식 채택)** | {n}종(현재 전수) | {water_pct:.1%} | {metal_pct:.1%} | "
        f"{cr_pct:.1%} | **예 — 이 스크립트 재실행으로 동일 결과 재현** |"
    )
    lines.append("")
    lines.append(
        "표본 크기(197→204→"
        f"{n})와 키워드 정의 자체가 다른 세 측정을 직접 비교하는 것은 원래 무의미하다. "
        "이 문서는 어느 것이 '맞는' 수치인지 판정하지 않고, **앞으로 유일하게 재현 가능한 "
        "버전**을 공식으로 채택한다는 것만 결정한다."
    )
    lines.append("")
    lines.append(
        f"참고: `no_data`(§10 원문이 \"자료없음\") 비율은 "
        f"{len(cat_hits.get('no_data', []))}/{n} = "
        f"{len(cat_hits.get('no_data', []))/n:.1%} — 이 비율만큼은 §10 실측으로 "
        "선정 근거를 댈 수 있는 상한을 넘어선다(정보 자체가 없으므로)."
    )
    lines.append("")

    with open(OUT_REPORT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"분모(COLLECTED): {n}")
    for cat in S10_CATEGORIES:
        cnt = len(cat_hits.get(cat, []))
        print(f"  {cat}: {cnt}/{n} = {cnt/n:.1%}  wave={dict(cat_wave_breakdown.get(cat, {}))}")
    print("리포트 작성 완료:", OUT_REPORT_MD)


if __name__ == "__main__":
    main()
