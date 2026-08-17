"""프로토타입: CAS 쌍 -> CAMEO 반응성 그룹 -> compatibility_pairs 조회 -> verdict+사유.

reactivity_reference.db에 이미 있는 구조화 데이터(chemical_group_membership,
reactivity_groups, compatibility_pairs, self_reactivity, hazard_code_legend,
gas_product_legend)를 그대로 조회만 한다 — 새 온톨로지/규칙엔진/평가기 없음.

한 물질이 여러 CAMEO 그룹에 속할 수 있으므로, 두 물질의 그룹 데카르트곱 전체를
조회해 가장 위험한 카테고리(Incompatible > Caution > Compatible)를 채택한다
(matrix_verdict가 이미 이렇게 집계된 값으로 보이며, 검증 사례 3건이 이를 확인한다).
같은 그룹끼리의 조합(group_a == group_b)은 compatibility_pairs가 아니라
self_reactivity(대각선 전용 표, 68행)를 쓴다.

  python 04_rag_agent/cameo_group_lookup.py   # 검증 사례 3건 self-check
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "reactivity_reference.db"

SEVERITY = {"Compatible": 0, "Caution": 1, "Incompatible": 2}


@dataclass
class GroupPairReason:
    group_a: str
    group_b: str
    category: str
    detail: str  # 사람이 읽을 사유 텍스트(설명 + 코드 번역, 또는 self_reactivity 비고)


@dataclass
class LookupResult:
    cas_a: str
    cas_b: str
    groups_a: list[tuple[int, str]]
    groups_b: list[tuple[int, str]]
    category: str | None  # None = 그룹 정보가 없어 조회 불가(Abstain 대상)
    reasons: list[GroupPairReason] = field(default_factory=list)  # category와 동률(worst-case)인 근거만


def groups_of(cur: sqlite3.Cursor, cas: str) -> list[tuple[int, str]]:
    q = """select rg.group_id, rg.group_name from chemical_group_membership cgm
           join chemicals c on c.chemical_id = cgm.chemical_id
           join reactivity_groups rg on rg.group_id = cgm.group_id
           where c.cas_number = ?"""
    return cur.execute(q, (cas,)).fetchall()


def _translate_codes(cur: sqlite3.Cursor, table: str, code_col: str, raw: str) -> str:
    if not raw:
        return ""
    legend_table = "hazard_code_legend" if table == "hazard" else "gas_product_legend"
    codes = [c.strip() for c in raw.split(",") if c.strip()]
    out = []
    for c in codes:
        row = cur.execute(f"select description from {legend_table} where code=?" if table == "hazard"
                           else f"select full_name from {legend_table} where code=?", (c,)).fetchone()
        out.append(row[0] if row else c)
    return "; ".join(out)


def pair_category(cur: sqlite3.Cursor, ga: int, ga_name: str, gb: int, gb_name: str) -> GroupPairReason:
    if ga == gb:
        row = cur.execute("select category, notes from self_reactivity where group_id=?", (ga,)).fetchone()
        category, notes = row if row else ("Caution", "자기반응성 데이터 없음")
        return GroupPairReason(ga_name, gb_name, category, notes)

    row = cur.execute(
        """select category, description, hazard_codes_raw, gas_products_raw from compatibility_pairs
           where (group_a_id=? and group_b_id=?) or (group_a_id=? and group_b_id=?)""",
        (ga, gb, gb, ga),
    ).fetchone()
    if not row:
        return GroupPairReason(ga_name, gb_name, "Caution", "그룹쌍 데이터 없음")
    category, description, hazard_raw, gas_raw = row
    parts = [p for p in [description] if p]
    hz = _translate_codes(cur, "hazard", "hazard_codes_raw", hazard_raw)
    gp = _translate_codes(cur, "gas", "gas_products_raw", gas_raw)
    if hz:
        parts.append(f"위험코드: {hz}")
    if gp:
        parts.append(f"생성 가능 물질: {gp}")
    return GroupPairReason(ga_name, gb_name, category, " / ".join(parts) if parts else "특이사항 없음")


def lookup(cur: sqlite3.Cursor, cas_a: str, cas_b: str) -> LookupResult:
    ga_list = groups_of(cur, cas_a)
    gb_list = groups_of(cur, cas_b)
    if not ga_list or not gb_list:
        return LookupResult(cas_a, cas_b, ga_list, gb_list, None)

    all_reasons = [
        pair_category(cur, ga, ga_name, gb, gb_name)
        for ga, ga_name in ga_list
        for gb, gb_name in gb_list
    ]
    worst = max(SEVERITY[r.category] for r in all_reasons)
    worst_category = [k for k, v in SEVERITY.items() if v == worst][0]
    reasons = [r for r in all_reasons if r.category == worst_category]
    return LookupResult(cas_a, cas_b, ga_list, gb_list, worst_category, reasons)


# 카테고리별 절제된 사유 문구. 원본 hazard code(예: "Intense or explosive reaction",
# "Explosive")를 그대로 노출하면 LLM이 Caution 건에서도 그 단어를 보고 어조를 Incompatible
# 쪽으로 끌고 가거나("Generates heat"를 "폭발 위험"으로 부풀리는 식) reason을 과장하는
# 경향이 파일럿에서 관찰됨. verdict(카테고리)를 우선시하고 reason은 이 정도로만 뭉뚱그려
# 보조 정보로 제공한다 — 구체적 위험코드 나열/번역은 프롬프트에 넣지 않는다.
CATEGORY_REASON = {
    "Compatible": "알려진 위험한 반응 없음",
    "Caution": "잠재적으로 유해할 수 있음",
    "Incompatible": "위험한 반응이 확인됨",
}


_NO_DETAIL = {"특이사항 없음", "그룹쌍 데이터 없음", "자기반응성 데이터 없음"}


def format_context(result: LookupResult, name_a: str, name_b: str, *, detailed: bool = False) -> str:
    """Generation 프롬프트에 그대로 붙여넣을 수 있는 텍스트 블록.

    detailed=False(기본): 기존 동작 — CATEGORY_REASON 뭉뚱그린 문구만 제공. run_cameo_full.py
    등 기존 파이프라인과의 하위호환을 위해 기본값 유지.
    detailed=True: compatibility_pairs의 실제 reason/위험코드/생성물 텍스트를 그대로 노출.
    "번역만 하고 강화하지 마라"는 명시적 프롬프트 규칙과 짝을 이룰 때만 사용할 것 — 규칙
    없이 이 정보만 노출하면 과거 파일럿에서 어조 과장이 재현된 바 있음(§CATEGORY_REASON 주석).
    """
    if result.category is None:
        return (
            f"[CAMEO 반응성 그룹 조회] {name_a} 또는 {name_b}의 그룹 정보가 DB에 없어 조회 불가."
        )
    lines = [
        "[CAMEO 반응성 그룹 조회 — 이미 결정된 판정, 재판단하지 말고 아래를 근거로 서술할 것]",
        f"{name_a}({result.cas_a}) 소속 그룹: {', '.join(n for _, n in result.groups_a)}",
        f"{name_b}({result.cas_b}) 소속 그룹: {', '.join(n for _, n in result.groups_b)}",
        f"CAMEO 판정: {result.category}",
    ]
    details = sorted({r.detail for r in result.reasons if r.detail and r.detail not in _NO_DETAIL})
    if detailed and details:
        lines.append("CAMEO 위험 정보 원문(번역만 허용, 의미를 강화하지 말 것):")
        for d in details:
            lines.append(f"- {d}")
    else:
        lines.append(f"CAMEO 사유: {CATEGORY_REASON[result.category]}.")
        if result.category != "Compatible":
            lines.append("참고: 관련 위험 요소가 확인됨.")
    return "\n".join(lines)


CASES = [
    ("Barban", "101-27-9", "Tungsten", "7440-33-7", "Caution"),
    ("Barium chloride", "10361-37-2", "Potassium superoxide", "12030-88-5", "Incompatible"),
    ("Potassium chloride", "7447-40-7", "Aluminum phosphate", "7784-30-7", "Compatible"),
]


def demo() -> None:
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    ok = True
    for name_a, cas_a, name_b, cas_b, expected in CASES:
        result = lookup(cur, cas_a, cas_b)
        passed = result.category == expected
        ok &= passed
        print(f"{'PASS' if passed else 'FAIL'}  {name_a}+{name_b}: got={result.category} expected={expected}")
        print(format_context(result, name_a, name_b))
        print()
    con.close()
    assert ok, "검증 사례 실패 — lookup 로직 점검 필요"
    print("전체 통과")


if __name__ == "__main__":
    demo()
