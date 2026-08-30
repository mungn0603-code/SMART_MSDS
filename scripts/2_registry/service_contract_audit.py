# -*- coding: utf-8 -*-
"""Registry 237종의 서비스 계약 5조건을 재대조하고 티어(A/B1/C/X)를 다시 계산한다.

조건 정의는 docs/REGISTRY.md 6절 그대로다.

    ① 식별        substance_registry
    ② KOSHA 등재  msds_chem_id_cache.chem_id
    ③ MSDS 상세   msds_sections §2/§3/§9/§10 전부
    ④ 검색 근거   rag_chunks §2 또는 §10 + rag_corpus_membership('173','core')
    ⑤ CAMEO 매핑  chemicals + chemical_group_membership

티어: X = ② 미충족(선택 목록 제외) / A = ③④⑤ 전부 / B1 = ④ 결여 / C = ⑤ 결여

    python scripts/service_contract_audit.py                    # 요약 + CSV
    python scripts/service_contract_audit.py --out <path.csv>
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "reactivity_reference.db"
CORE207 = ROOT / "data" / "collection" / "registry_core207.csv"
DEFAULT_OUT = ROOT / "results" / "registry_service_contract_recheck.csv"
MSDS_SECTIONS = (2, 3, 9, 10)

# §10 정형문구 — 물질과 무관하게 붙는다. 물질특이 정보량을 셀 때 뺀다.
S10_BOILERPLATE = "타는 동안 열분해 또는 연소에 의해 자극적이고 매우 유독한 가스가 발생될 수 있음"
S10_PLACEHOLDER = {"자료없음", "해당없음", ""}
# 이 값 미만이면 §10에 물질특이 반응성 정보가 사실상 없다(173 코퍼스 p5 = 27자).
# 편입 게이트가 아니라 표시용이다 — 2026-08-22에 게이트로 쓰려다 폐기했다. 나트륨·칼륨·
# 과산화나트륨·삼산화크로뮴처럼 이 도구가 가장 다뤄야 할 물질이 먼저 걸러져서,
# 이 값이 재는 게 근거 유무가 아니라 KOSHA가 §10을 채웠는지임이 드러났다.
S10_THIN = 27

TIERS = {
    "A": "A · 계약 4조건 전부 충족",
    "B1": "B1 · 검색 근거 결여",
    "C": "C · CAMEO 매핑 결여",
    "X": "X · KOSHA 미등재",
}


def audit(con: sqlite3.Connection) -> list[dict]:
    cur = con.cursor()
    kosha = {r[0] for r in cur.execute(
        "select cas_number from msds_chem_id_cache where ifnull(chem_id,'') <> ''")}
    msds = {r[0] for r in cur.execute(
        "select cas_number from msds_sections where section in (%s)"
        " group by cas_number having count(distinct section) = ?"
        % ",".join("?" * len(MSDS_SECTIONS)),
        (*MSDS_SECTIONS, len(MSDS_SECTIONS)))}
    # 2026-08-28: 코퍼스 태그 의존을 뺐다. 태그(=service 코퍼스 소속)를 조건에 두면
    # "태그를 만들기 위해 태그를 조건으로 쓰는" 순환이 된다. 검색 근거의 유무는
    # 청크 존재만으로 판단한다(태그는 그 결과를 담는 그릇일 뿐).
    # 실측: 태그 조건을 빼도 결과 동일(173종, 차이 0종).
    indexed = {r[0] for r in cur.execute(
        "select distinct cas_number from rag_chunks"
        " where section in (2, 10) and status = 'active'")}
    cameo = {r[0] for r in cur.execute(
        "select distinct c.cas_number from chemicals c"
        " join chemical_group_membership m on m.chemical_id = c.chemical_id")}
    groups = dict(cur.execute(
        "select c.cas_number, group_concat(rg.group_name, ' | ') from chemicals c"
        " join chemical_group_membership m on m.chemical_id = c.chemical_id"
        " join reactivity_groups rg on rg.group_id = m.group_id"
        " group by c.cas_number").fetchall())
    cameo_source = dict(cur.execute(
        "select c.cas_number, group_concat(distinct m.source) from chemicals c"
        " join chemical_group_membership m on m.chemical_id = c.chemical_id"
        " group by c.cas_number").fetchall())

    s10_spec: dict[str, int] = {}
    for cas, detail in cur.execute(
            "select cas_number, ifnull(item_detail,'') from msds_sections where section = 10"):
        text = detail.strip()
        if text in S10_PLACEHOLDER:
            continue
        s10_spec[cas] = s10_spec.get(cas, 0) + len(text.replace(S10_BOILERPLATE, ""))

    core207 = set()
    if CORE207.exists():
        with open(CORE207, encoding="utf-8-sig", newline="") as f:
            core207 = {r["cas_number"].strip() for r in csv.DictReader(f)}

    rows = []
    for cas, ko, axis in cur.execute(
            "select cas_number, name_ko, core_category from substance_registry"
            " order by cas_number"):
        has = dict(kosha=cas in kosha, msds=cas in msds,
                   indexed=cas in indexed, cameo=cas in cameo)
        if not has["kosha"]:
            tier = "X"
        elif has["msds"] and has["indexed"] and has["cameo"]:
            tier = "A"
        elif not has["cameo"]:
            tier = "C"
        else:
            tier = "B1"
        rows.append({
            "cas_number": cas, "name_ko": ko, "core_axis": axis,
            "origin": "CORE207" if cas in core207 else "add_2026-08-22",
            **has,
            "cameo_groups": groups.get(cas, ""),
            "cameo_source": cameo_source.get(cas, ""),
            "s10_specific_chars": s10_spec.get(cas, 0),
            "s10_thin": s10_spec.get(cas, 0) < S10_THIN,
            "tier": TIERS[tier], "tier_code": tier,
        })
    return rows


def summarize(rows: list[dict]) -> None:
    n = len(rows)
    tier = Counter(r["tier_code"] for r in rows)
    served = [r for r in rows if r["kosha"]]
    mapped = [r for r in served if r["cameo"]]
    m = len(mapped)
    s = len(served)
    print(f"Registry {n}종 / KOSHA 등재 {s}종 / CAMEO 매핑 {sum(r['cameo'] for r in rows)}종"
          f" (서비스 대상 중 {m}종)")
    for code in ("A", "B1", "C", "X"):
        print(f"  {TIERS[code]:<28} {tier[code]:>3}종")
    thin = [r for r in served if r["s10_thin"]]
    print(f"§10 물질특이 정보 {S10_THIN}자 미만 {len(thin)}종 (표시용, 편입 게이트 아님):"
          f" {', '.join(r['name_ko'] for r in thin[:8])}{' …' if len(thin) > 8 else ''}")
    total_pairs = s * (s - 1) // 2
    judgeable = m * (m - 1) // 2
    pct = judgeable / total_pairs * 100 if total_pairs else 0
    print(f"판정 가능 쌍 {judgeable:,} / {total_pairs:,} = {pct:.1f}%")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    con = sqlite3.connect(DB_PATH)
    rows = audit(con)
    con.close()

    # 물질 수는 하드코딩하지 않는다(2026-08-28) - Registry가 늘면 그대로 따라간다.
    assert rows, "Registry가 비어 있음"
    assert all(r["kosha"] or r["tier_code"] == "X" for r in rows), "X 티어 판정 불일치"

    args.out.parent.mkdir(exist_ok=True)
    with open(args.out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    summarize(rows)
    print(f"\n대조표: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
