# -*- coding: utf-8 -*-
"""
타겟리스트 확장 기준 전면 교체: "그룹당 슬롯 채우기(총원수 목표)" 폐기,
"실측 반응 상대 빈도 높은 그룹만 무제한 수집"으로 교체 (2026-08-08, 사용자 지시:
"숫자는 안중요하다. 이 물질을 찾는 빈도수가 높으면 수집한다").

실측 근거: 이미 수집된 204종의 KOSHA §10 "피해야 할 물질" 텍스트 전수조사
(docs/decisions.md 1.2a-upd 실측 갱신):
  가연성/환원성 물질 47.6%, 금속 34.9%, 물 23.0%(단일물질 최고 빈도)
-> 이 실측이 직접 가리키는 CAMEO 그룹만 대상, 개수 목표 없음(전량 수집).

FREQ_GROUPS: 40/41/42(금속류), 50/51(산화제), 58/59(환원제), 68(물/수용액)
"""
import csv
import sqlite3

DB_PATH = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\data\reactivity_reference.db"
OUT_CSV = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\data\collection\undergrad_target_chemicals.csv"
PUBCHEM_REPORT = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\data\collection\pubchem_verification_report_full.csv"

FREQ_GROUPS = (40, 41, 42, 50, 51, 58, 59, 68)


def main():
    con = sqlite3.connect(DB_PATH, timeout=30)
    cur = con.cursor()
    group_names = dict(cur.execute("SELECT group_id, group_name FROM reactivity_groups").fetchall())

    with open(PUBCHEM_REPORT, encoding="utf-8-sig") as f:
        pubchem_ok = set(r["cas_number"] for r in csv.DictReader(f) if r["status"] in ("MATCH", "MISMATCH"))

    with open(OUT_CSV, encoding="utf-8-sig") as f:
        existing_rows = list(csv.DictReader(f))
    already = set(r["cas_number"] for r in existing_rows)

    new_rows = []
    for gid in FREQ_GROUPS:
        cur.execute(
            """
            SELECT c.cas_number, c.chemical_name
            FROM chemical_group_membership m
            JOIN chemicals c ON c.chemical_id = m.chemical_id
            WHERE m.group_id = ?
            ORDER BY c.cas_number
            """,
            (gid,),
        )
        added_for_group = 0
        for cas, name in cur.fetchall():
            if cas in already or cas not in pubchem_ok:
                continue
            new_rows.append(
                {
                    "cas_number": cas, "chemical_name": name, "group_id": gid,
                    "group_name": group_names[gid], "source": "reaction_frequency_high",
                    "course": "", "experiment": "",
                }
            )
            already.add(cas)
            added_for_group += 1
        print(f"그룹{gid} {group_names[gid]}: 신규 {added_for_group}종")

    con.close()

    all_rows = existing_rows + new_rows
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["cas_number", "chemical_name", "group_id", "group_name", "source", "course", "experiment"])
        w.writeheader()
        w.writerows(all_rows)

    print(f"\n총 {len(all_rows)}종 (기존 {len(existing_rows)} + 신규 {len(new_rows)})")


if __name__ == "__main__":
    main()
