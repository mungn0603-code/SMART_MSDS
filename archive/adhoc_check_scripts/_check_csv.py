import csv

BASE = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\01_collection"
CURRENT = BASE + r"\undergrad_target_chemicals.csv"
BACKUP = BASE + r"\undergrad_target_chemicals_v1_backup.csv"

targets = ["64-17-5", "67-64-1", "110-54-3", "60-29-7", "108-88-3", "64-19-7",
           "108-24-7", "7647-01-0", "7697-37-2", "7722-84-1", "7772-98-7", "497-19-8"]


def scan(path):
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    fieldnames = reader.fieldnames
    cas_field = None
    for cand in ["cas_number", "cas", "CAS", "CAS_NUMBER", "cas_no"]:
        if cand in fieldnames:
            cas_field = cand
            break
    found = {}
    for r in rows:
        if r.get(cas_field) in targets:
            found[r[cas_field]] = r
    return len(rows), fieldnames, found


for label, path in [("CURRENT", CURRENT), ("BACKUP(v1)", BACKUP)]:
    total, fields, found = scan(path)
    print(f"\n=== {label} ({path}) ===")
    print("총 행수:", total, "| 컬럼:", fields)
    print(f"12종 중 발견: {len(found)}")
    for cas in targets:
        status = "O" if cas in found else "X"
        print(f"  [{status}] {cas}", found.get(cas, {}))
