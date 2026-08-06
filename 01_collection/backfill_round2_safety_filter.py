# -*- coding: utf-8 -*-
"""
1차 대체(backfill_group_replacements.py) 결과 30종 중, "학부실험용으로 부적절"한
후보를 걸러내고 같은 그룹 내 다음 후보로 재교체.

부적절 판정 기준(자동):
- GHS 유해·위험 문구(H-code)에 H300/H310/H330(급성독성 1등급, 치사 가능) 또는
  H340/H350/H360(발암성·생식세포변이원성·생식독성 1A/1B) 포함
- getChemDetail01의 "제품의 권고 용도"(A0401)에 의약품/치료 용도로 명시된 경우
수동 제외(자동 기준으로 못 거른 것):
- 10453-86-8 (레스메트린, 피레스로이드계 살충제 - 용도필드 공란이라 자동필터로 못 거름)
"""
import csv
import shutil
import sqlite3
import xml.etree.ElementTree as ET

from kosha_msds_collector import (
    DB_PATH, TARGET_CSV, SECTIONS,
    call_api, parse_chem_list, parse_chem_detail, ensure_tables, fetch_and_store_section, log,
)

SEVERE_HCODES = ("H300", "H310", "H330", "H340", "H350", "H360")
DRUG_USE_KEYWORDS = ("의약품", "치료", "제약")
MANUAL_REJECT_CAS = {"10453-86-8"}  # 레스메트린: 자동필터 미탐지, 알려진 살충제라 수동 제외

BAD_CAS = {
    "10453-86-8": 27, "1143-38-0": 38, "116-71-2": 38,
    "1067-33-0": 49, "107-27-7": 49, "1332-21-4": 62,
    "11056-06-7": 64, "102-81-8": 8, "104-94-9": 28, "107-20-0": 31,
}


def candidate_pool(con, group_id, exclude_cas):
    cur = con.execute("""
        SELECT c.cas_number, c.chemical_name
        FROM chemical_group_membership m
        JOIN chemicals c ON c.chemical_id = m.chemical_id
        WHERE m.group_id = ?
        ORDER BY c.chemical_id
    """, (group_id,))
    return [(cas, name) for cas, name in cur.fetchall() if cas not in exclude_cas]


def vet_candidate(cas, chem_id):
    """급성치사/CMR 1급 또는 의약품 용도면 부적격(False)."""
    root01 = call_api("getChemDetail01", {"chemId": chem_id})
    for item in root01.findall("./body/items/item"):
        if item.findtext("msdsItemCode") == "A0401":
            use = (item.findtext("itemDetail") or "").strip()
            if any(k in use for k in DRUG_USE_KEYWORDS):
                log(f"  [거부] {cas}: 의약품/치료 용도 명시 ({use[:40]})")
                return False

    root02 = call_api("getChemDetail02", {"chemId": chem_id})
    text = " ".join(r["item_detail"] or "" for r in parse_chem_detail(root02))
    hit = [h for h in SEVERE_HCODES if h in text]
    if hit:
        log(f"  [거부] {cas}: 고위험 GHS 문구 {hit}")
        return False
    return True


def resolve_and_vet(con, cas):
    root = call_api("getChemList", {"searchWrd": cas, "searchCnd": 1, "numOfRows": 5, "pageNo": 1})
    try:
        found = parse_chem_list(root, cas)
    except RuntimeError as e:
        log(f"  [조회 에러] {cas}: {e}")
        return None
    if not found:
        return None
    if not vet_candidate(cas, found["chem_id"]):
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

    with open(TARGET_CSV, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    used_cas = {r["cas_number"] for r in rows} | MANUAL_REJECT_CAS

    replacements = {}
    unresolved = []

    for bad_cas, group_id in BAD_CAS.items():
        pool = candidate_pool(con, group_id, used_cas)
        chosen = None
        for cas, name in pool:
            found = resolve_and_vet(con, cas)
            used_cas.add(cas)
            if found:
                chosen = (cas, found["chem_name_kor"] or name)
                log(f"[재대체 성공] group={group_id} {bad_cas} -> {cas} ({chosen[1]})")
                break
        if chosen:
            replacements[bad_cas] = chosen
        else:
            unresolved.append((bad_cas, group_id))
            log(f"[재대체 실패] group={group_id} {bad_cas} - 적격 후보 소진, 기존 유지")

    # CSV 갱신 (기존 값을 새 값으로)
    shutil.copy(TARGET_CSV, TARGET_CSV + ".round2.bak")
    old_cas_to_drop = []
    for r in rows:
        if r["cas_number"] in replacements:
            new_cas, new_name = replacements[r["cas_number"]]
            old_cas_to_drop.append(r["cas_number"])
            r["cas_number"] = new_cas
            r["chemical_name"] = new_name
            r["source"] = "pool_replacement_v2"
    with open(TARGET_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)

    # 신규 채택 물질 섹션(2,3,9,10) 수집
    for old_cas, (new_cas, new_name) in replacements.items():
        chem_id = con.execute(
            "SELECT chem_id FROM msds_chem_id_cache WHERE cas_number=?", (new_cas,)
        ).fetchone()[0]
        for section in SECTIONS:
            fetch_and_store_section(con, new_cas, chem_id, section)

    # 폐기된(부적격 판정) 기존 데이터 정리
    for old_cas in old_cas_to_drop:
        con.execute("DELETE FROM msds_sections WHERE cas_number=?", (old_cas,))
        con.execute("DELETE FROM msds_chem_id_cache WHERE cas_number=?", (old_cas,))
    con.commit()

    log(f"완료: 재대체성공 {len(replacements)} / 재대체실패 {len(unresolved)}")
    if unresolved:
        log(f"  기존 유지 목록: {unresolved}")

    con.close()


if __name__ == "__main__":
    main()
