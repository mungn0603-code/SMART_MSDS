# -*- coding: utf-8 -*-
"""
Round 3: 자동 필터(GHS H-code + A0401 용도)로도 걸러지지 않은 문제 물질을
사람이 이름을 보고 직접 검토해 고른 대체품으로 교체.

- 1162-65-8 아프라톡신 B1(H361만 걸림, 실제로는 IARC 1군 발암물질) -> 119-53-9 벤조인
  (H-code 자료없음, 벤조인 축합반응은 학부 유기화학 정석 실험)
- 123-88-6 메톡시에틸수은 염화물(H372 미탐지) -> 13007-92-6 크롬 카보닐
  (H301만 있음, 유기수은/유기주석류보다 훨씬 약한 급성독성)
- 111-48-8 티오디글리콜(GHS상 H319뿐이지만 화학무기금지협약 스케줄2 전구물질이라 보수적으로 교체)
  -> 7220-79-3 메틸렌 블루 트리수화물(H361뿐, 학부 실험 정석 산화환원지시약)
- 1271-28-9 니켈로센: round2에서 채택됐으나 재검토 - H351(2등급, 의심수준)뿐이고
  organometallics 그룹 자체가 KOSHA 등록물질 중 마땅한 대안이 없어 유지하기로 결정
  (CSV 변경 없음, 기록용으로만 로그 남김)
"""
import csv
import shutil
import sqlite3
from datetime import datetime

from kosha_msds_collector import (
    DB_PATH, TARGET_CSV, SECTIONS,
    call_api, parse_chem_list, fetch_and_store_section, ensure_tables, log,
)

REPLACEMENTS = {
    "1162-65-8": "119-53-9",   # 아프라톡신 B1 -> 벤조인
    "123-88-6": "13007-92-6",  # 메톡시에틸수은 염화물 -> 크롬 카보닐
    "111-48-8": "7220-79-3",   # 티오디글리콜(CWC 전구물질) -> 메틸렌 블루 트리수화물
}
KEEP_WITH_NOTE = {
    "1271-28-9": "니켈로센 유지 - GHS H351(2등급,의심수준)뿐, organometallics 그룹 내 "
                  "KOSHA 등록 대안 전부 조사했으나 이보다 나은 게 없음(원문 그룹 자체가 고위험군)",
}


def resolve(con, cas):
    root = call_api("getChemList", {"searchWrd": cas, "searchCnd": 1, "numOfRows": 5, "pageNo": 1})
    found = parse_chem_list(root, cas)
    if not found:
        raise RuntimeError(f"{cas}: KOSHA 미등록 - 사전 검증 결과와 다름")
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

    shutil.copy(TARGET_CSV, TARGET_CSV + ".round3.bak")

    for old_cas, new_cas in REPLACEMENTS.items():
        found = resolve(con, new_cas)
        for r in rows:
            if r["cas_number"] == old_cas:
                r["cas_number"] = new_cas
                r["chemical_name"] = found["chem_name_kor"] or new_cas
                r["source"] = "pool_replacement_v3_manual"
        for section in SECTIONS:
            fetch_and_store_section(con, new_cas, found["chem_id"], section)
        con.execute("DELETE FROM msds_sections WHERE cas_number=?", (old_cas,))
        con.execute("DELETE FROM msds_chem_id_cache WHERE cas_number=?", (old_cas,))
        con.commit()
        log(f"[수동 재대체] {old_cas} -> {new_cas} ({found['chem_name_kor']})")

    with open(TARGET_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)

    for cas, note in KEEP_WITH_NOTE.items():
        log(f"[유지 결정] {cas}: {note}")

    log("Round 3 완료")
    con.close()


if __name__ == "__main__":
    main()
