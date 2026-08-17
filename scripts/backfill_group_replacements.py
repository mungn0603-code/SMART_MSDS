# -*- coding: utf-8 -*-
"""
32종 미발견(KOSHA 미등록) 보충물질을 같은 CAMEO 그룹 내 다른 후보로 교체.
- 대상: undergrad_target_chemicals.csv 중 source in (pool_supplement, pool_topup)이고
  KOSHA에서 못 찾은 32종
- 방법: 같은 group_id의 후보 풀(chemical_group_membership, 이미 쓰인 CAS 제외)을
  chemical_id 순으로 하나씩 getChemList에 조회 -> 발견되면 채택
- 채택된 대체물질은 chem_id_cache에 즉시 기록하고 섹션(2,3,9,10)까지 수집
- CSV는 원본을 .csv.bak으로 백업한 뒤 교체 행만 갱신(source=pool_replacement)
"""
import csv
import shutil
import sqlite3

from kosha_msds_collector import (
    DB_PATH, TARGET_CSV, SECTIONS,
    call_api, parse_chem_list, ensure_tables, fetch_and_store_section, log,
)

NOT_FOUND_CAS = {
    "100-19-6", "100-27-6", "100-38-9", "100-65-2", "101-55-3", "101-73-5",
    "101200-48-0", "10137-69-6", "10143-23-4", "102-96-5", "10213-75-9",
    "10318-26-0", "1034-41-9", "10353-73-8", "104-28-9", "1066-45-1",
    "1067-14-7", "11106-54-0", "111512-56-2", "1122-54-9", "1124-33-0",
    "1174-72-7", "12003-41-7", "12034-12-7", "135072-82-1", "15005-97-7",
    "2508-19-2", "308068-21-5", "54413-15-9", "67713-16-0", "68848-64-6",
    "70399-13-2",
}


def load_csv_rows():
    with open(TARGET_CSV, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def candidate_pool(con, group_id, exclude_cas):
    cur = con.execute("""
        SELECT c.cas_number, c.chemical_name
        FROM chemical_group_membership m
        JOIN chemicals c ON c.chemical_id = m.chemical_id
        WHERE m.group_id = ?
        ORDER BY c.chemical_id
    """, (group_id,))
    return [(cas, name) for cas, name in cur.fetchall() if cas not in exclude_cas]


def try_resolve(con, cas):
    """getChemList로 cas 조회. 성공하면 chem_id_cache에 기록 후 dict 반환, 실패하면 None."""
    root = call_api("getChemList", {"searchWrd": cas, "searchCnd": 1, "numOfRows": 5, "pageNo": 1})
    try:
        found = parse_chem_list(root, cas)
    except RuntimeError as e:
        log(f"[조회 에러] {cas}: {e}")
        return None
    if not found:
        return None
    from datetime import datetime
    now = datetime.now().isoformat()
    con.execute("""INSERT OR REPLACE INTO msds_chem_id_cache
        (cas_number, chem_id, chem_name_kor, last_date, open_yn, kosha_confirm, resolved_at)
        VALUES (?,?,?,?,?,?,?)""",
        (cas, found["chem_id"], found["chem_name_kor"], found["last_date"],
         found["open_yn"], found["kosha_confirm"], now))
    con.commit()
    return found


def main():
    con = sqlite3.connect(DB_PATH)
    ensure_tables(con)

    rows = load_csv_rows()
    used_cas = {r["cas_number"] for r in rows}
    targets = [r for r in rows if r["cas_number"] in NOT_FOUND_CAS]

    replacements = {}   # old_cas -> (new_cas, new_name)
    unresolved = []      # (old_cas, group_id) 대체 후보 소진

    for row in targets:
        old_cas, group_id = row["cas_number"], int(row["group_id"])
        pool = candidate_pool(con, group_id, used_cas)
        chosen = None
        for cas, name in pool:
            found = try_resolve(con, cas)
            if found:
                chosen = (cas, found["chem_name_kor"] or name)
                used_cas.add(cas)
                log(f"[대체 성공] group={group_id} {old_cas} -> {cas} ({chosen[1]})")
                break
            else:
                used_cas.add(cas)  # 이번 실행 내 중복 시도 방지
        if chosen:
            replacements[old_cas] = chosen
        else:
            unresolved.append((old_cas, group_id))
            log(f"[대체 실패] group={group_id} {old_cas} - 풀 소진, 원안 유지(Abstain)")

    # CSV 갱신
    shutil.copy(TARGET_CSV, TARGET_CSV + ".bak")
    for r in rows:
        if r["cas_number"] in replacements:
            new_cas, new_name = replacements[r["cas_number"]]
            r["cas_number"] = new_cas
            r["chemical_name"] = new_name
            r["source"] = "pool_replacement"
    with open(TARGET_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)

    # 대체된 신규 CAS 섹션 수집
    for old_cas, (new_cas, new_name) in replacements.items():
        chem_id = con.execute(
            "SELECT chem_id FROM msds_chem_id_cache WHERE cas_number=?", (new_cas,)
        ).fetchone()[0]
        for section in SECTIONS:
            fetch_and_store_section(con, new_cas, chem_id, section)

    log(f"완료: 대체성공 {len(replacements)} / 대체실패(Abstain 유지) {len(unresolved)}")
    if unresolved:
        log(f"  Abstain 유지 목록: {unresolved}")

    con.close()


if __name__ == "__main__":
    main()
