# -*- coding: utf-8 -*-
"""
CAS -> CAMEO 68그룹 매핑을 PubChem 공식 엔드포인트로 재수집/교차검증한다.
CAMEO 웹 스크레이핑(robots.txt 위반) 대체 경로. 근거: docs/decisions.md 1.2b

기본: 200종(199종) 타겟리스트만 처리. --full: chemicals 테이블 3,386종 전체 처리
(2026-08-08, 사용자 지시로 확대).

엔드포인트:
  CAS->CID   : /rest/pug/compound/name/{CAS}/cids/JSON (공식 PUG-REST)
  CID->그룹  : /classification_2/classification_2.fcgi?hid=86&search_uid={cid}
               &search_type=list&search_uid_type=cid (hid=86 = CAMEO Chemical
               Reactivity Classification, PubChem Classification Browser가 쓰는
               비공식 JSON 엔드포인트, robots.txt disallow 없음)

DB 반영 정책: 기존 CAMEO_scrape 행은 건드리지 않는다(삭제 없음). PubChem이
새로 확인한 (chemical_id, group_id) 조합만 source='pubchem_verified'로 추가
INSERT(하나의 물질이 여러 그룹에 속하는 CAMEO 실제 구조를 반영). 기존 스크레이핑
값과 불일치하는 건은 report CSV에만 남기고 자동 정정하지 않는다 — 사용자 지시대로
"약간의 데이터 오류는 허용"하고, 물질 단위 확정 판정이 아니라 그룹 단위 폴백
(같은 그룹의 다른 대표물질 사용)으로 대응하는 게 설계 원칙(decisions.md 1.2c,
실제 폴백 함수는 02_classification/group_fallback.py).
"""
import csv
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request

DB_PATH = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\data\reactivity_reference.db"
CSV_PATH = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\data\collection\undergrad_target_chemicals.csv"
REPORT_PATH = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\data\collection\pubchem_verification_report.csv"
REPORT_PATH_FULL = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\data\collection\pubchem_verification_report_full.csv"
UA = {"User-Agent": "Mozilla/5.0"}
RATE_DELAY = 0.25  # PUG-REST 권장 상한(5req/s) 이내


def cas_to_cid(cas):
    url = f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{cas}/cids/JSON"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    return data["IdentifierList"]["CID"][0]


def cid_to_cameo_groups(cid):
    url = (
        "https://pubchem.ncbi.nlm.nih.gov/classification_2/classification_2.fcgi"
        f"?format=json&hid=86&search_uid={cid}&search_type=list&search_uid_type=cid"
    )
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    hierarchies = data.get("Hierarchies", {}).get("Hierarchy")
    if not hierarchies:
        return []
    return [
        n["Information"]["Name"]["StringWithMarkup"]["String"]
        for hh in hierarchies
        for n in hh.get("Node", [])
    ]


def load_targets_from_csv():
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    return [
        {"cas_number": r["cas_number"], "chemical_name": r["chemical_name"], "expected_groups": [r["group_name"]]}
        for r in rows
    ]


def load_targets_from_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute(
        """
        SELECT c.cas_number, c.chemical_name, g.group_name
        FROM chemicals c
        LEFT JOIN chemical_group_membership m ON m.chemical_id = c.chemical_id
        LEFT JOIN reactivity_groups g ON g.group_id = m.group_id
        ORDER BY c.cas_number
        """
    )
    by_cas = {}
    for cas, name, group_name in cur.fetchall():
        entry = by_cas.setdefault(cas, {"cas_number": cas, "chemical_name": name, "expected_groups": []})
        if group_name:
            entry["expected_groups"].append(group_name)
    con.close()
    return list(by_cas.values())


def main():
    full = "--full" in sys.argv
    targets = load_targets_from_db() if full else load_targets_from_csv()
    report_path = REPORT_PATH_FULL if full else REPORT_PATH

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT group_id, group_name FROM reactivity_groups")
    name_to_gid = dict((name, gid) for gid, name in cur.fetchall())

    counts = {"MATCH": 0, "MISMATCH": 0, "NO_PUBCHEM_DATA": 0, "ERROR": 0}
    new_membership_rows = 0
    report_rows = []

    for i, t in enumerate(targets, 1):
        cas = t["cas_number"]
        name = t["chemical_name"]
        expected_groups = t["expected_groups"]

        cid = None
        groups = []
        try:
            cid = cas_to_cid(cas)
            time.sleep(RATE_DELAY)
            groups = cid_to_cameo_groups(cid)
            time.sleep(RATE_DELAY)
            if not groups:
                status = "NO_PUBCHEM_DATA"
            elif set(expected_groups) & set(groups):
                status = "MATCH"
            else:
                status = "MISMATCH"
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError, TimeoutError) as e:
            status = "ERROR"
            groups = []
            print(f"[{i}/{len(targets)}] {cas} {name} -> ERROR: {e}")

        counts[status if status in counts else "ERROR"] = counts.get(status, 0) + 1
        if i % 25 == 0 or not full:
            print(f"[{i}/{len(targets)}] {cas} {name} -> {status} (PubChem: {groups or '-'})")

        report_rows.append(
            {
                "cas_number": cas,
                "chemical_name": name,
                "expected_group": ";".join(expected_groups),
                "pubchem_cid": cid or "",
                "pubchem_groups": ";".join(groups),
                "status": status,
            }
        )

        if groups and status == "MATCH":
            cur.execute("SELECT chemical_id FROM chemicals WHERE cas_number=?", (cas,))
            row = cur.fetchone()
            if row is None:
                continue
            chemical_id = row[0]
            for g in groups:
                # MATCH만으로도 groups 안에 expected에 없는 추가 그룹이 섞여
                # 있을 수 있다(예: 질소가 Not Chemically Reactive와 함께
                # Epoxides도 반환된 경우). expected와 교집합인 그룹만 반영-
                # PubChem이 검증하지 못한 그룹까지 같이 밀어넣지 않는다.
                if g not in expected_groups:
                    continue
                gid = name_to_gid.get(g)
                if gid is None:
                    continue
                cur.execute(
                    "INSERT OR IGNORE INTO chemical_group_membership "
                    "(chemical_id, group_id, source) VALUES (?,?,'pubchem_verified')",
                    (chemical_id, gid),
                )
                if cur.rowcount:
                    new_membership_rows += 1

        if i % 50 == 0:
            con.commit()

    con.commit()
    con.close()

    with open(report_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "cas_number",
                "chemical_name",
                "expected_group",
                "pubchem_cid",
                "pubchem_groups",
                "status",
            ],
        )
        w.writeheader()
        w.writerows(report_rows)

    print("\n=== 요약 ===")
    print(f"대상: {len(targets)}종")
    for k, v in counts.items():
        print(f"  {k}: {v}")
    print(f"신규 chemical_group_membership 행(source=pubchem_verified): {new_membership_rows}")
    print(f"리포트: {report_path}")


if __name__ == "__main__":
    main()
