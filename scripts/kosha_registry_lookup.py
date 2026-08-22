# -*- coding: utf-8 -*-
"""substance_registry(CORE 207종) <-> KOSHA MSDS Open API 매핑 점검.

API 클라이언트를 새로 만들지 않는다 - kosha_msds_collector의 call_api /
parse_chem_list / msds_chem_id_cache를 그대로 재사용한다. 이 스크립트가 하는 건
"registry의 CAS 목록을 그 흐름에 입력으로 넣고, 결과를 4개 상태로 분류해
보고"하는 것뿐이다.

캐시 우선(msds_chem_id_cache에 이미 있으면 API를 다시 부르지 않음). 실제 호출은
캐시에 없는 CAS에 대해서만 getChemList 1회씩 발생한다 - 엔드포인트별 일 1,000회
한도(collector 주석 참고) 대비 여유가 크다. 병렬 호출은 하지 않는다.

상태 4종:
  matched     KOSHA 목록에서 동일 CAS 항목을 찾음(chem_id 확보)
  not_found   API는 정상 응답했으나 해당 CAS 없음
  error       API 호출/파싱 오류(재시도 3회 소진)
  invalid_cas CAS 형식 또는 체크디지트가 틀림 - API를 부르지 않고 걸러냄

KOSHA 물질명은 절대 registry에 덮어쓰지 않는다. 이름 차이는 리포트로만 남긴다.

  python scripts/kosha_registry_lookup.py             # 캐시만 사용(네트워크 없음)
  python scripts/kosha_registry_lookup.py --fetch     # 캐시 없는 CAS만 실제 API 조회
  python scripts/kosha_registry_lookup.py --fetch --limit 10
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import kosha_msds_collector as K  # noqa: E402  기존 API 클라이언트 재사용

DB_PATH = ROOT / "data" / "reactivity_reference.db"
REPORT_PATH = ROOT / "results" / "kosha_registry_lookup.csv"

STATUSES = ("matched", "not_found", "error", "invalid_cas")


def valid_cas(cas: str) -> bool:
    """CAS 등록번호 체크디지트 검증. 형식 NNNNNNN-NN-N, 마지막 자리는 앞자리들을
    오른쪽부터 1,2,3... 가중합한 뒤 mod 10 (CAS 공식 규칙)."""
    parts = cas.split("-")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return False
    if not (2 <= len(parts[0]) <= 7 and len(parts[1]) == 2 and len(parts[2]) == 1):
        return False
    digits = parts[0] + parts[1]
    total = sum(int(d) * (i + 1) for i, d in enumerate(reversed(digits)))
    return total % 10 == int(parts[2])


def load_registry(con: sqlite3.Connection) -> list[tuple[str, str, str | None]]:
    return con.execute(
        "select cas_number, name_ko, name_en from substance_registry order by cas_number"
    ).fetchall()


def cached_row(con: sqlite3.Connection, cas: str):
    """msds_chem_id_cache 조회. (있음?, chem_id, chem_name_kor, last_date)."""
    row = con.execute(
        "select chem_id, chem_name_kor, last_date from msds_chem_id_cache where cas_number=?",
        (cas,),
    ).fetchone()
    return (row is not None, *(row or (None, None, None)))


def lookup(con: sqlite3.Connection, cas: str, fetch: bool) -> dict:
    """캐시 -> (허용 시) API 순. 반환: status/chem_id/kosha_name/last_date/detail."""
    if not valid_cas(cas):
        return {"status": "invalid_cas", "detail": "CAS 체크디지트/형식 불일치"}

    hit, chem_id, kosha_name, last_date = cached_row(con, cas)
    if hit:
        return {
            "status": "matched" if chem_id else "not_found",
            "chem_id": chem_id, "kosha_name": kosha_name, "last_date": last_date,
            "detail": "cache",
        }
    if not fetch:
        return {"status": "not_checked", "detail": "캐시 없음 (--fetch로 조회)"}

    try:
        root = K.call_api("getChemList", {"searchWrd": cas, "searchCnd": 1, "numOfRows": 5, "pageNo": 1})
        found = K.parse_chem_list(root, cas)
    except Exception as e:  # 재시도 3회 소진 포함
        return {"status": "error", "detail": f"{type(e).__name__}: {e}"}

    now = datetime.now().isoformat()
    con.execute(
        "INSERT OR REPLACE INTO msds_chem_id_cache "
        "(cas_number, chem_id, chem_name_kor, last_date, open_yn, kosha_confirm, resolved_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (cas, found and found["chem_id"], found and found["chem_name_kor"],
         found and found["last_date"], found and found["open_yn"],
         found and found["kosha_confirm"], now),
    )
    con.commit()
    if not found:
        return {"status": "not_found", "detail": "api"}
    return {
        "status": "matched", "chem_id": found["chem_id"],
        "kosha_name": found["chem_name_kor"], "last_date": found["last_date"], "detail": "api",
    }


def rag_names(con: sqlite3.Connection) -> dict[str, str]:
    return dict(con.execute(
        "select cas_number, chemical_name from rag_chunks group by cas_number"
    ))


def run(fetch: bool, limit: int | None) -> list[dict]:
    con = sqlite3.connect(DB_PATH, timeout=120)
    K.ensure_tables(con)
    reg = load_registry(con)
    rag = rag_names(con)

    out, fetched = [], 0
    for cas, name_ko, name_en in reg:
        need_api = fetch and not cached_row(con, cas)[0] and valid_cas(cas)
        if need_api and limit is not None and fetched >= limit:
            r = {"status": "not_checked", "detail": "--limit 도달"}
        else:
            r = lookup(con, cas, fetch)
            if need_api:
                fetched += 1
        out.append({
            "cas_number": cas,
            "registry_name_ko": name_ko,
            "registry_name_en": name_en or "",
            "rag_chunk_name": rag.get(cas, ""),
            "kosha_name": r.get("kosha_name") or "",
            "chem_id": r.get("chem_id") or "",
            "kosha_last_date": r.get("last_date") or "",
            "status": r["status"],
            "detail": r.get("detail", ""),
            # 이름 차이는 기록만 한다 - registry를 덮어쓰지 않는다.
            "name_differs": bool(r.get("kosha_name")) and r.get("kosha_name") != name_ko,
        })
    con.close()
    return out


def report(rows: list[dict]) -> None:
    counts = {s: sum(1 for r in rows if r["status"] == s) for s in STATUSES}
    not_checked = sum(1 for r in rows if r["status"] == "not_checked")

    print(f"\n전체: {len(rows)}")
    print(f"조회 성공(matched): {counts['matched']}")
    print(f"미조회(not_found): {counts['not_found']}")
    print(f"API 오류(error): {counts['error']}")
    print(f"CAS 오류(invalid_cas): {counts['invalid_cas']}")
    if not_checked:
        print(f"미확인(not_checked): {not_checked}  <- --fetch 필요")

    for status in ("not_found", "error", "invalid_cas"):
        bad = [r for r in rows if r["status"] == status]
        if bad:
            print(f"\n[{status}] {len(bad)}종")
            for r in bad:
                print(f"  {r['cas_number']:12s} {r['registry_name_ko']:14s} {r['detail']}")

    diff = [r for r in rows if r["name_differs"]]
    print(f"\n[이름 불일치] {len(diff)}종 (registry 유지, 참고용 기록만)")
    for r in diff[:15]:
        print(f"  {r['cas_number']:12s} registry={r['registry_name_ko']!r} kosha={r['kosha_name']!r}")
    if len(diff) > 15:
        print(f"  ... 외 {len(diff) - 15}종 (전체는 {REPORT_PATH.name} 참고)")

    REPORT_PATH.parent.mkdir(exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"\n리포트: {REPORT_PATH}")


def self_check() -> None:
    """API 없이 실행 가능한 검사만. 실제 조회 결과 검증은 run()/report()가 담당."""
    assert valid_cas("64-17-5"), "에탄올 CAS가 유효 판정되지 않음"
    assert valid_cas("7440-66-6"), "아연 CAS가 유효 판정되지 않음"
    assert not valid_cas("64-17-6"), "체크디지트 오류를 잡지 못함"
    assert not valid_cas("abc-12-3"), "형식 오류를 잡지 못함"
    assert not valid_cas("7440-666"), "구분자 오류를 잡지 못함"
    print("valid_cas 자가검증 통과")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="캐시에 없는 CAS를 실제 API로 조회")
    ap.add_argument("--limit", type=int, default=None, help="이번 실행의 최대 신규 API 호출 수")
    ap.add_argument("--self-check", action="store_true", help="API 없이 CAS 검증 로직만 점검")
    args = ap.parse_args()

    if args.self_check:
        self_check()
        return
    if args.fetch and not K.SERVICE_KEY:
        print("환경변수 KOSHA_SERVICE_KEY 가 필요합니다(.env 또는 셸에 설정).")
        sys.exit(1)

    self_check()
    report(run(args.fetch, args.limit))


if __name__ == "__main__":
    main()
