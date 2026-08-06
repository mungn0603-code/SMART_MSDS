import sqlite3

DB_PATH = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\reactivity_reference.db"

targets = ["64-17-5", "67-64-1", "110-54-3", "60-29-7", "108-88-3", "64-19-7",
           "108-24-7", "7647-01-0", "7697-37-2", "7722-84-1", "7772-98-7", "497-19-8"]

con = sqlite3.connect(DB_PATH)
cur = con.cursor()
q = "SELECT cas_number, chemical_name, source FROM chemicals WHERE cas_number IN ({})".format(
    ",".join(["?"] * len(targets))
)
cur.execute(q, targets)
rows = cur.fetchall()

print(f"DB 내 발견: {len(rows)} / {len(targets)}")
for r in rows:
    print(r)

found_cas = {r[0] for r in rows}
missing = [t for t in targets if t not in found_cas]
print("여전히 누락:", missing)

# group_membership 연결 확인
cur.execute("""
    SELECT c.cas_number, c.chemical_name, m.group_id, m.source
    FROM chemicals c
    JOIN chemical_group_membership m ON c.chemical_id = m.chemical_id
    WHERE c.cas_number IN ({})
""".format(",".join(["?"] * len(targets))), targets)
print("\n그룹 매핑 확인:")
for r in cur.fetchall():
    print(r)

con.close()
