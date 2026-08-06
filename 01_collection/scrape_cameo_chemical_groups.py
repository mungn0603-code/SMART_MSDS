"""
CAMEO Chemicals 전체 화학물질(약 6,000여 종)의 CAS 번호 -> 68 반응성 그룹 매핑 수집.
source: https://cameochemicals.noaa.gov (정적 HTML, 세션 쿠키 기반 페이지네이션)
output: cameo_chemical_groups.db (SQLite, 단일 테이블)

reactivity_reference.db 는 seed_reactivity_reference.py 재실행 시 통째로 지워지고
재생성되므로, 스크래핑 결과는 별도 DB에 저장해 안전하게 분리한다.

Usage:
    python scrape_cameo_chemical_groups.py
"""

import re
import sqlite3
import time
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

BASE = Path(__file__).parent
REACTIVITY_DB = BASE / "reactivity_reference.db"
OUT_DB = BASE / "cameo_chemical_groups.db"

SITE = "https://cameochemicals.noaa.gov"
UA = "Mozilla/5.0 (msds-risk-assessment research script)"
REQUEST_DELAY = 0.4  # ponytail: fixed courtesy delay, bump if NOAA throttles us

CAS_RE = re.compile(r'^\d{2,7}-\d{2}-\d$')
GROUP_LINK_RE = re.compile(r'href="/react/(\d+)">([^<]+)</a>')
RESULT_BLOCK_RE = re.compile(
    r'class="match_name" href="/chemical/(\d+)">([^<]+)</a>.*?'
    r'CAS Number:</span>\s*([^<\n]*)',
    re.S,
)
PAGE_MARKER_RE = re.compile(r'Page <b>(\d+)</b> of <b>(\d+)</b>')


def make_opener():
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    opener.addheaders = [("User-Agent", UA)]
    opener.open(SITE + "/", timeout=20).read()  # warm up session cookie
    return opener


def fetch_group_links(opener):
    """Return [(react_id, group_name), ...] for all reactive group datasheets."""
    html = opener.open(SITE + "/browse/react", timeout=20).read().decode("utf-8", "ignore")
    return [(int(rid), name.strip()) for rid, name in GROUP_LINK_RE.findall(html)]


def parse_result_page(html):
    """Yield (chemical_id, name, cas_or_None) and return total page count."""
    entries = []
    for chem_id, name, cas_raw in RESULT_BLOCK_RE.findall(html):
        cas_raw = cas_raw.strip()
        cas = cas_raw if CAS_RE.match(cas_raw) else None
        entries.append((int(chem_id), name.strip(), cas))
    m = PAGE_MARKER_RE.search(html)
    total_pages = int(m.group(2)) if m else 1
    return entries, total_pages


def iter_group_chemicals(opener, react_id):
    """Stream (chemical_id, name, cas) for every chemical in one reactive group."""
    html = opener.open(f"{SITE}/search/chemicals_for_react/{react_id}", timeout=20).read().decode("utf-8", "ignore")
    entries, total_pages = parse_result_page(html)
    yield from entries
    for page in range(2, total_pages + 1):
        time.sleep(REQUEST_DELAY)
        html = opener.open(f"{SITE}/search/results?page={page}", timeout=20).read().decode("utf-8", "ignore")
        entries, _ = parse_result_page(html)
        yield from entries


def load_group_name_to_id():
    conn = sqlite3.connect(REACTIVITY_DB)
    rows = conn.execute("SELECT group_id, group_name FROM reactivity_groups").fetchall()
    conn.close()
    return {name: gid for gid, name in rows}


def init_out_db():
    conn = sqlite3.connect(OUT_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cameo_chemical_groups (
            chemical_id   INTEGER NOT NULL,   -- CAMEO's /chemical/{id}
            cas_number    TEXT,               -- NULL if CAMEO lists no CAS
            chemical_name TEXT NOT NULL,
            group_id      INTEGER NOT NULL,   -- matches reactivity_reference.db reactivity_groups.group_id
            group_name    TEXT NOT NULL,
            PRIMARY KEY (chemical_id, group_id)
        )
    """)
    conn.commit()
    return conn


def scrape_all(conn, opener, group_name_to_id):
    groups = fetch_group_links(opener)
    for react_id, group_name in groups:
        group_id = group_name_to_id.get(group_name)
        if group_id is None:
            print(f"SKIP (no matching group_id): {group_name!r}")
            continue
        rows = [
            (chem_id, cas, name, group_id, group_name)
            for chem_id, name, cas in iter_group_chemicals(opener, react_id)
        ]
        conn.executemany(
            "INSERT OR REPLACE INTO cameo_chemical_groups "
            "(chemical_id, cas_number, chemical_name, group_id, group_name) VALUES (?,?,?,?,?)",
            rows,
        )
        conn.commit()
        print(f"{group_name}: {len(rows)} chemicals")
        time.sleep(REQUEST_DELAY)


def report(conn):
    total = conn.execute("SELECT COUNT(*) FROM cameo_chemical_groups").fetchone()[0]
    distinct_chem = conn.execute("SELECT COUNT(DISTINCT chemical_id) FROM cameo_chemical_groups").fetchone()[0]
    with_cas = conn.execute("SELECT COUNT(*) FROM cameo_chemical_groups WHERE cas_number IS NOT NULL").fetchone()[0]
    print(f"\nrows(chemical,group): {total}  distinct chemicals: {distinct_chem}  rows with CAS: {with_cas}")


if __name__ == "__main__":
    opener = make_opener()
    group_name_to_id = load_group_name_to_id()
    conn = init_out_db()
    scrape_all(conn, opener, group_name_to_id)
    report(conn)
    conn.close()
    print(f"\n완료: {OUT_DB}")
