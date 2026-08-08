# -*- coding: utf-8 -*-
"""
PHASE 2-B — 66개 backfill 후보(chemical_selection_backfill_candidates_2026-08-08.csv)
KOSHA 실측 조회.

중요: 이 스크립트는 `01_collection/undergrad_target_chemicals.csv`(선정 CSV)를
절대 건드리지 않는다. KOSHA 조회 결과는 기존 관행대로 `msds_chem_id_cache`/
`msds_sections`에만 기록한다(원래 이 두 테이블의 용도가 "조회 시도 기록"이라 —
group_fallback.py, backfill_group_replacements.py 등 기존 스크립트도 동일하게
"조회/캐시"와 "선정 CSV 편입"을 분리해서 다뤄왔다). "조회했다"는 "편입했다"가 아니다.

이미 abstain_not_found로 확인된 5종은 재조회하지 않는다(쿼터 절약, 결과가 바뀔
이유가 없음). not_attempted 61종만 신규 조회한다.
"""
import csv
import sys
import time

sys.path.insert(0, r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\01_collection")
from kosha_msds_collector import (  # noqa: E402
    DB_PATH, SECTIONS, ensure_tables, resolve_chem_id, fetch_and_store_section, log, SERVICE_KEY,
)
import sqlite3  # noqa: E402

BACKFILL_CSV = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\01_collection\chemical_selection_backfill_candidates_2026-08-08.csv"


def main():
    if not SERVICE_KEY:
        print("KOSHA_SERVICE_KEY 미설정 — 중단")
        return

    with open(BACKFILL_CSV, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))

    to_probe = [r for r in rows if r["kosha_status"] == "not_attempted"]
    print(f"신규 조회 대상: {len(to_probe)}종 (이미 abstain 확인된 {len(rows)-len(to_probe)}종은 건너뜀)")

    con = sqlite3.connect(DB_PATH, timeout=60)
    ensure_tables(con)

    found, not_found = 0, 0
    for i, r in enumerate(to_probe, 1):
        cas = r["candidate_cas"]
        chem_id = resolve_chem_id(con, cas)
        if chem_id:
            found += 1
            for section in SECTIONS:
                fetch_and_store_section(con, cas, chem_id, section)
            log(f"[P2-B 조회] {cas}({r['candidate_name'][:30]}) -> KOSHA 등록 확인, 4섹션 수집")
        else:
            not_found += 1
            log(f"[P2-B 조회] {cas}({r['candidate_name'][:30]}) -> KOSHA 미등록")
        if i % 10 == 0:
            print(f"  진행 {i}/{len(to_probe)}")

    con.close()
    print(f"완료: KOSHA 등록확인 {found} / 미등록 {not_found}")


if __name__ == "__main__":
    main()
