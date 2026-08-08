# -*- coding: utf-8 -*-
"""
KOSHA MSDS Open API 수집 스크립트
- 대상: 01_collection/undergrad_target_chemicals.csv 200종
- 섹션: 2(유해성위험성) 3(구성성분) 9(물리화학) 10(안정성반응성)
- 절차: CAS -> getChemList(searchCnd=1)로 chemId 조회 -> getChemDetail0X 4회
- 쿼터: 엔드포인트별 개별 일 1,000회 한도. 실사용(엔드포인트당 최대 200회)이 한도 대비
  여유가 커서 호출 수 제한/카운팅 로직 없이 진행(2026-08-04 확정)
- 서비스키: 환경변수 KOSHA_SERVICE_KEY 에서만 읽음(코드에 절대 하드코딩 금지)
  PowerShell 설정 예: $env:KOSHA_SERVICE_KEY = "발급받은키"
"""

import os
import sys
import csv
import time
import sqlite3
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime

BASE_URL = "https://apis.data.go.kr/B552468/msdschem"
DB_PATH = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\reactivity_reference.db"
TARGET_CSV = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\01_collection\undergrad_target_chemicals.csv"
LOG_PATH = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\01_collection\kosha_collect.log"

SECTIONS = [2, 3, 9, 10]
SLEEP_SEC = 0.3

def _load_dotenv(path):
    """.env 파일이 있으면 읽어서 os.environ에 채워넣음(이미 설정된 환경변수는 덮어쓰지 않음)."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip()
            if k and v and k not in os.environ:
                os.environ[k] = v


_load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))
SERVICE_KEY = os.environ.get("KOSHA_SERVICE_KEY")
if SERVICE_KEY and "%" in SERVICE_KEY:
    # data.go.kr이 발급하는 "URL Encoding" 버전 키 대응: 이미 %XX 인코딩된 상태이므로
    # 한 번 디코딩해서 원문으로 되돌린 뒤, 아래 urlencode()에서 정상적으로 다시 인코딩되게 함.
    # (그대로 두면 urlencode()가 이중 인코딩하여 인증 실패 -> HTTP 403)
    SERVICE_KEY = urllib.parse.unquote(SERVICE_KEY)


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def call_api(operation, params):
    """KOSHA API 공통 호출. 실패시 최대 3회 재시도(지수백오프), XML Element 반환."""
    if not SERVICE_KEY:
        raise RuntimeError("환경변수 KOSHA_SERVICE_KEY 가 설정되어 있지 않습니다.")
    q = dict(params)
    q["serviceKey"] = SERVICE_KEY
    url = f"{BASE_URL}/{operation}?{urllib.parse.urlencode(q)}"

    last_err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                data = resp.read()
            time.sleep(SLEEP_SEC)
            return ET.fromstring(data)
        except Exception as e:
            last_err = e
            log(f"[재시도 {attempt + 1}/3] {operation} 실패: {e}")
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"{operation} 3회 재시도 후 실패: {last_err}")


def _text(el, tag, default=None):
    node = el.find(tag)
    return node.text if node is not None and node.text is not None else default


def parse_chem_list(root, target_cas):
    """getChemList 응답 중 target_cas와 정확히 일치하는 item만 골라 반환. 없으면 None(기각 대상)."""
    result_code = _text(root, "./header/resultCode")
    if result_code not in (None, "00"):
        msg = _text(root, "./header/resultMsg", "알수없음")
        raise RuntimeError(f"resultCode={result_code} msg={msg}")

    for item in root.findall("./body/items/item"):
        if _text(item, "casNo") == target_cas:
            return {
                "chem_id": _text(item, "chemId"),
                "chem_name_kor": _text(item, "chemNameKor"),
                "last_date": _text(item, "lastDate"),
                "open_yn": _text(item, "openYn"),
                "kosha_confirm": _text(item, "koshaConfirm"),
            }
    return None


def parse_chem_detail(root):
    """getChemDetail0X 응답 -> EAV 행 리스트로 변환 (msdsItemNameKor/itemDetail/lev/ordrIdx 등)."""
    rows = []
    for item in root.findall("./body/items/item"):
        rows.append({
            "item_name_kor": _text(item, "msdsItemNameKor"),
            "item_no": _text(item, "msdsItemNo"),
            "item_detail": _text(item, "itemDetail"),
            "lev": _text(item, "lev"),
            "msds_item_code": _text(item, "msdsItemCode"),
            "up_msds_item_code": _text(item, "upMsdsItemCode"),
            "ordr_idx": _text(item, "ordrIdx"),
        })
    return rows


def ensure_tables(con):
    con.executescript("""
    CREATE TABLE IF NOT EXISTS msds_chem_id_cache (
        cas_number TEXT PRIMARY KEY,
        chem_id TEXT,
        chem_name_kor TEXT,
        last_date TEXT,
        open_yn TEXT,
        kosha_confirm TEXT,
        resolved_at TEXT
    );

    CREATE TABLE IF NOT EXISTS msds_sections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cas_number TEXT,
        chem_id TEXT,
        section INTEGER,
        item_name_kor TEXT,
        item_no TEXT,
        item_detail TEXT,
        lev INTEGER,
        msds_item_code INTEGER,
        up_msds_item_code TEXT,
        ordr_idx INTEGER,
        collected_at TEXT,
        UNIQUE(cas_number, section, msds_item_code, ordr_idx)
    );
    """)
    con.commit()


def load_targets(path):
    with open(path, encoding="utf-8-sig") as f:
        return [row["cas_number"] for row in csv.DictReader(f)]


def get_cached_chem_id(con, cas):
    cur = con.execute("SELECT chem_id FROM msds_chem_id_cache WHERE cas_number=?", (cas,))
    row = cur.fetchone()
    return row[0] if row else None


def section_already_collected(con, cas, section):
    cur = con.execute(
        "SELECT COUNT(*) FROM msds_sections WHERE cas_number=? AND section=?", (cas, section)
    )
    return cur.fetchone()[0] > 0


def resolve_chem_id(con, cas):
    """캐시에 있으면 API 호출 없이 반환. 없으면 getChemList 조회 후 캐시에 저장."""
    cached = get_cached_chem_id(con, cas)
    if cached:
        return cached

    root = call_api("getChemList", {
        "searchWrd": cas, "searchCnd": 1, "numOfRows": 5, "pageNo": 1
    })
    found = parse_chem_list(root, cas)
    now = datetime.now().isoformat()

    if not found:
        log(f"[미발견] CAS {cas} - KOSHA 목록에 없음(Abstain 대상, 캐시에 None으로 기록)")
        con.execute("""INSERT OR REPLACE INTO msds_chem_id_cache
            (cas_number, chem_id, chem_name_kor, last_date, open_yn, kosha_confirm, resolved_at)
            VALUES (?,?,?,?,?,?,?)""", (cas, None, None, None, None, None, now))
        con.commit()
        return None

    con.execute("""INSERT OR REPLACE INTO msds_chem_id_cache
        (cas_number, chem_id, chem_name_kor, last_date, open_yn, kosha_confirm, resolved_at)
        VALUES (?,?,?,?,?,?,?)""",
        (cas, found["chem_id"], found["chem_name_kor"], found["last_date"],
         found["open_yn"], found["kosha_confirm"], now))
    con.commit()
    return found["chem_id"]


def fetch_and_store_section(con, cas, chem_id, section):
    """이미 수집된 (cas, section)은 API 호출 없이 skip. 아니면 조회 후 EAV 행 적재."""
    if section_already_collected(con, cas, section):
        return "skip"

    root = call_api(f"getChemDetail{section:02d}", {"chemId": chem_id})
    rows = parse_chem_detail(root)
    now = datetime.now().isoformat()

    for r in rows:
        con.execute("""INSERT OR IGNORE INTO msds_sections
            (cas_number, chem_id, section, item_name_kor, item_no, item_detail,
             lev, msds_item_code, up_msds_item_code, ordr_idx, collected_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (cas, chem_id, section, r["item_name_kor"], r["item_no"], r["item_detail"],
             r["lev"], r["msds_item_code"], r["up_msds_item_code"], r["ordr_idx"], now))
    con.commit()
    return "ok"


def main():
    if not SERVICE_KEY:
        print("환경변수 KOSHA_SERVICE_KEY 를 먼저 설정하세요.")
        print('PowerShell 예: $env:KOSHA_SERVICE_KEY = "발급받은키"')
        sys.exit(1)

    con = sqlite3.connect(DB_PATH, timeout=120)  # 병렬 실행 중인 다른 수집 스크립트와의 잠금 대기
    ensure_tables(con)

    targets = load_targets(TARGET_CSV)
    log(f"수집 대상 {len(targets)}종 로드 (섹션 {SECTIONS})")

    done, not_found, section_calls = 0, 0, 0
    try:
        for cas in targets:
            chem_id = resolve_chem_id(con, cas)
            if not chem_id:
                not_found += 1
                continue
            for section in SECTIONS:
                status = fetch_and_store_section(con, cas, chem_id, section)
                if status == "ok":
                    section_calls += 1
            done += 1
            if done % 10 == 0:
                log(f"진행 {done}/{len(targets)}")
    finally:
        log(f"완료 {done} / 미발견(Abstain) {not_found} / 신규섹션수집 {section_calls}")
        con.close()


if __name__ == "__main__":
    main()
