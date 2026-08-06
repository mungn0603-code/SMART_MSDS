"""
CAMEO 68그룹 반응성 참조 DB 시드 스크립트
source: Cameo_reactivity.csv (Summary / Gas Products / Hazard Codes 3개 차트 + 2개 범례)
output: reactivity_reference.db (SQLite)
"""
import csv
import re
import sqlite3
from pathlib import Path

BASE = Path(r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS")
CSV_PATH = BASE / "01_collection" / "Cameo_reactivity.csv"
SCHEMA_PATH = BASE / "02_classification" / "schema.sql"
DB_PATH = BASE / "02_classification" / "reactivity_reference.db"

CATEGORY_RE = re.compile(r'^(Compatible|Caution|Incompatible)\s*:\s*(.*)$')


def load_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.reader(f))


def is_blank(row):
    return len(row) == 0 or all(c.strip() == "" for c in row)


def split_category(cell):
    cell = (cell or "").strip()
    if not cell:
        return ("Unknown", "")
    m = CATEGORY_RE.match(cell)
    if m:
        return (m.group(1), m.group(2).strip())
    return ("Unknown", cell)


def parse(rows):
    groups = {}      # group_id -> name (Hazard Codes 헤더에서 확보, 정본)
    summary = {}     # (i,j) i>j -> (category, description)
    gas = {}         # (i,j) -> raw gas string
    hazcode = {}     # (i,j) -> raw hazard code string
    haz_legend = {}  # code -> description
    gas_legend = {}  # code -> full_name

    section = None
    row_counter = 0
    hz_stage = 0  # 0=대기, 1=인덱스행 대기, 2=이름행 대기, 3=데이터

    for row in rows:
        if is_blank(row):
            continue
        head = row[0].strip()

        if head == "Compatibility Chart: Summary":
            section, row_counter = "summary", 0
            continue
        if head == "Compatibility Chart: Gas Products":
            section, row_counter = "gas", 0
            continue
        if head == "Compatibility Chart: Hazard Codes":
            section, hz_stage = "hazcode", 1
            continue
        if head == "Key to Hazard Codes":
            section = "haz_legend"
            continue
        if head == "Key to Gas Products":
            section = "gas_legend"
            continue

        if section == "summary":
            row_counter += 1
            i = row_counter
            values = row[1:-1]
            assert len(values) == i - 1, f"summary row {i} 길이 불일치: {row}"
            for j, cell in enumerate(values, start=1):
                summary[(i, j)] = split_category(cell)

        elif section == "gas":
            row_counter += 1
            i = row_counter
            values = row[1:-1]
            assert len(values) == i - 1, f"gas row {i} 길이 불일치: {row}"
            for j, cell in enumerate(values, start=1):
                gas[(i, j)] = cell.strip()

        elif section == "hazcode":
            if hz_stage == 1:
                hz_stage = 2  # "-,-,1,2,...,68" 인덱스행: 사용 안 함
                continue
            if hz_stage == 2:
                names = row[2:]  # "-,-,name1,...,name68"
                for idx, name in enumerate(names, start=1):
                    groups[idx] = name.strip()
                hz_stage, row_counter = 3, 0
                continue
            row_counter += 1
            i = row_counter
            values = row[2:]
            assert len(values) == i - 1, f"hazcode row {i} 길이 불일치: {row}"
            for j, cell in enumerate(values, start=1):
                hazcode[(i, j)] = cell.strip()

        elif section == "haz_legend":
            if len(row) >= 2 and row[0].strip() != "-":
                haz_legend[row[0].strip()] = row[1].strip()

        elif section == "gas_legend":
            if len(row) >= 2:
                gas_legend[row[0].strip()] = row[1].strip()

    return groups, summary, gas, hazcode, haz_legend, gas_legend


def build_db():
    rows = load_rows(CSV_PATH)
    groups, summary, gas, hazcode, haz_legend, gas_legend = parse(rows)

    assert len(groups) == 68, f"그룹 수 {len(groups)} != 68"
    expected_pairs = 68 * 67 // 2  # 2,278 (오프대각만, 자기반응 미포함)
    assert len(summary) == expected_pairs, f"summary 쌍 수 {len(summary)} != {expected_pairs}"
    assert len(hazcode) == expected_pairs, f"hazcode 쌍 수 {len(hazcode)} != {expected_pairs}"
    assert len(gas) == expected_pairs, f"gas 쌍 수 {len(gas)} != {expected_pairs}"

    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    cur = conn.cursor()

    cur.executemany(
        "INSERT INTO reactivity_groups(group_id, group_name) VALUES (?,?)",
        list(groups.items()),
    )
    cur.executemany(
        "INSERT INTO hazard_code_legend(code, description) VALUES (?,?)",
        list(haz_legend.items()),
    )
    cur.executemany(
        "INSERT OR IGNORE INTO gas_product_legend(code, full_name) VALUES (?,?)",
        list(gas_legend.items()),
    )

    pair_id_map = {}
    for (i, j), (cat, desc) in summary.items():
        group_a, group_b = j, i  # i(행)>j(열) 이므로 항상 group_a<group_b
        cur.execute(
            """INSERT INTO compatibility_pairs
               (group_a_id, group_b_id, category, description,
                hazard_codes_raw, gas_products_raw)
               VALUES (?,?,?,?,?,?)""",
            (group_a, group_b, cat, desc, hazcode.get((i, j), ""), gas.get((i, j), "")),
        )
        pair_id_map[(group_a, group_b)] = cur.lastrowid

    for (i, j), hz_raw in hazcode.items():
        pid = pair_id_map[(j, i)]
        for code in [c.strip() for c in hz_raw.split(",") if c.strip()]:
            cur.execute(
                "INSERT OR IGNORE INTO compatibility_hazard_codes(pair_id, hazard_code) VALUES (?,?)",
                (pid, code),
            )

    for (i, j), gas_raw in gas.items():
        pid = pair_id_map[(j, i)]
        for code in [c.strip() for c in gas_raw.split(",") if c.strip()]:
            cur.execute(
                "INSERT OR IGNORE INTO compatibility_gas_products(pair_id, gas_code) VALUES (?,?)",
                (pid, code),
            )

    cur.executemany(
        "INSERT INTO self_reactivity(group_id, category, notes) VALUES (?,?,?)",
        [(gid, "Unknown", "CAMEO 원자료에 자기반응 데이터 없음 - 별도 확인 필요") for gid in groups],
    )

    conn.commit()
    return conn

def report(conn):
    cur = conn.cursor()
    checks = [
        ("groups", "SELECT COUNT(*) FROM reactivity_groups"),
        ("pairs", "SELECT COUNT(*) FROM compatibility_pairs"),
        ("hazard_code_legend", "SELECT COUNT(*) FROM hazard_code_legend"),
        ("gas_product_legend", "SELECT COUNT(*) FROM gas_product_legend"),
        ("hazard_code_links", "SELECT COUNT(*) FROM compatibility_hazard_codes"),
        ("gas_product_links", "SELECT COUNT(*) FROM compatibility_gas_products"),
        ("self_reactivity_rows", "SELECT COUNT(*) FROM self_reactivity"),
    ]
    print("=== 시드 결과 검증 ===")
    for label, q in checks:
        cur.execute(q)
        print(f"{label}: {cur.fetchone()[0]}")

    cur.execute(
        "SELECT category, COUNT(*) FROM compatibility_pairs GROUP BY category ORDER BY 2 DESC"
    )
    print("category breakdown:", cur.fetchall())


if __name__ == "__main__":
    connection = build_db()
    report(connection)
    connection.close()
    print(f"\nDB 생성 완료: {DB_PATH}")
