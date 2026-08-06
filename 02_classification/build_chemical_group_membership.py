import sqlite3, csv

DB = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\reactivity_reference.db"
CSV = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\01_collection\cas_reactive_group_mapping.csv"

conn = sqlite3.connect(DB)
cur = conn.cursor()

cur.executescript("""
CREATE TABLE IF NOT EXISTS chemicals (
    chemical_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    cas_number    TEXT NOT NULL UNIQUE,
    chemical_name TEXT,
    source        TEXT NOT NULL DEFAULT 'CAMEO_scrape'
);

CREATE TABLE IF NOT EXISTS chemical_group_membership (
    membership_id INTEGER PRIMARY KEY AUTOINCREMENT,
    chemical_id   INTEGER NOT NULL REFERENCES chemicals(chemical_id),
    group_id      INTEGER NOT NULL REFERENCES reactivity_groups(group_id),
    source        TEXT NOT NULL DEFAULT 'CAMEO_scrape',
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(chemical_id, group_id)
);
""")
conn.commit()
print("schema ready")

n_chem, n_mem, skipped = 0, 0, 0
with open(CSV, encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        cas = row["CAS_Number"].strip()
        name = row["Chemical_Name"].strip()
        gids_raw = row["Reactive_Group_IDs"].strip()
        if not cas or not gids_raw:
            skipped += 1
            continue
        cur.execute(
            "INSERT OR IGNORE INTO chemicals (cas_number, chemical_name) VALUES (?, ?)",
            (cas, name),
        )
        cur.execute("SELECT chemical_id FROM chemicals WHERE cas_number = ?", (cas,))
        chem_id = cur.fetchone()[0]
        n_chem += 1
        for gid in gids_raw.split(";"):
            gid = gid.strip()
            if not gid.isdigit():
                continue
            cur.execute(
                "INSERT OR IGNORE INTO chemical_group_membership (chemical_id, group_id) VALUES (?, ?)",
                (chem_id, int(gid)),
            )
            n_mem += 1

conn.commit()
print(f"processed CAS rows: {n_chem}  membership rows inserted: {n_mem}  skipped(no CAS/group): {skipped}")

cur.execute("SELECT COUNT(*) FROM chemicals")
print("total chemicals:", cur.fetchone()[0])
cur.execute("SELECT COUNT(*) FROM chemical_group_membership")
print("total memberships:", cur.fetchone()[0])
cur.execute("SELECT COUNT(DISTINCT group_id) FROM chemical_group_membership")
print("groups covered:", cur.fetchone()[0], "/ 68")
cur.execute("""
    SELECT rg.group_id, rg.group_name, COUNT(*) 
    FROM chemical_group_membership m JOIN reactivity_groups rg ON rg.group_id=m.group_id
    GROUP BY rg.group_id ORDER BY COUNT(*) ASC LIMIT 5
""")
print("적은 그룹(하위5):", cur.fetchall())
conn.close()
