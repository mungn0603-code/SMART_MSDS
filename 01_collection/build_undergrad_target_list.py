# -*- coding: utf-8 -*-
"""
학부 실험실 커버리지 기반 KOSHA 수집 대상 화학물질 리스트 생성
=================================================================
전략
----
1. CAMEO 68개 반응성 그룹을 학부 실험 등장빈도 기준 3단계로 티어링
   (HIGH=전과목에서 자주 등장 / MED=특정 과목·실험에서 등장 / LOW=거의 안 씀·특수산업용)
   -> 그룹 36 "Insufficient Information for Classification"은 실질 화학물질
      범주가 아니므로 제외(EXCLUDE)
2. 티어별 목표 대표 종 수(HIGH>MED>LOW)를 배분
3. 그룹별 슬롯을 채울 때, 학부 커리큘럼에서 실제로 등장이 확인된
   CURATED_LIST(30종, CAS 직접 검증됨)를 우선 배정하고, 남는 슬롯은
   기확보 3,386종 풀(chemical_group_membership)에서 자동 보충
4. 최종 200종을 목표로 하되 미달 시 HIGH 그룹부터 추가 보충, 250종 상한
5. 결과를 CSV로 저장 + 콘솔에 요약 리포트 출력

주의
----
자동보충분(pool_supplement/pool_topup)은 "그룹 소속"만 검증된 것이며,
개별 물질이 실제 학부 실험에서 쓰이는지는 검증되지 않음.
KOSHA 수집 전 스팟체크 권장.
"""

import sqlite3
import csv
from collections import Counter

DB_PATH = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\reactivity_reference.db"
OUT_CSV = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\01_collection\undergrad_target_chemicals.csv"
PUBCHEM_REPORT = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\01_collection\pubchem_verification_report_full.csv"

TARGET_MIN = 380
TARGET_MAX = 420

# 2026-08-08: 판정 기준을 "CAMEO 스크레이핑 일치"에서 "PubChem 재검증 통과"로 전환
# (docs/decisions.md 1.2b). 풀은 PubChem이 CAMEO 그룹을 확인해준 물질(MATCH/MISMATCH
# — MISMATCH는 표기차이뿐, 실질 불일치 아님, 상세는 decisions.md 참고)로 제한한다.
def load_pubchem_confirmed_cas(path=PUBCHEM_REPORT):
    import csv as _csv
    confirmed = set()
    with open(path, encoding="utf-8-sig") as f:
        for row in _csv.DictReader(f):
            if row["status"] in ("MATCH", "MISMATCH"):
                confirmed.add(row["cas_number"])
    return confirmed

# ---------------------------------------------------------------
# 1) 그룹 티어 분류 (group_id: tier) - 화공/학부실험 도메인 판단, 필요시 재조정
# ---------------------------------------------------------------
GROUP_TIER = {
    1: "LOW", 2: "HIGH", 3: "HIGH", 4: "HIGH", 5: "MED", 6: "LOW", 7: "MED",
    8: "HIGH", 9: "MED", 10: "LOW", 11: "LOW", 12: "MED", 13: "MED", 14: "MED",
    15: "MED", 16: "MED", 17: "LOW", 18: "HIGH", 19: "HIGH", 20: "LOW",
    21: "HIGH", 22: "LOW", 23: "LOW", 24: "LOW", 25: "MED", 26: "LOW",
    27: "HIGH", 28: "HIGH", 29: "MED", 30: "LOW", 31: "HIGH", 32: "MED",
    33: "HIGH", 34: "MED", 35: "HIGH", 36: "EXCLUDE", 37: "LOW", 38: "HIGH",
    39: "MED", 40: "MED", 41: "HIGH", 42: "HIGH", 43: "MED", 44: "LOW",
    45: "MED", 46: "LOW", 47: "HIGH", 48: "LOW", 49: "MED", 50: "HIGH",
    51: "HIGH", 52: "LOW", 53: "MED", 54: "LOW", 55: "MED", 56: "MED",
    57: "LOW", 58: "MED", 59: "MED", 60: "MED", 61: "MED", 62: "LOW",
    63: "MED", 64: "LOW", 65: "HIGH", 66: "LOW", 67: "LOW", 68: "HIGH",
}

TIER_SLOTS = {"HIGH": 12, "MED": 4, "LOW": 2}

# ---------------------------------------------------------------
# 2) 커리큘럼 근거 확인된 큐레이션 리스트 (CAS 직접 검증, 30종)
# ---------------------------------------------------------------
CURATED_LIST = [
    ("일반화학", "산-염기 적정", "7647-01-0"),
    ("일반화학", "산-염기/탈수", "7664-93-9"),
    ("일반화학", "산화반응", "7697-37-2"),
    ("일반화학", "적정/비누화", "1310-73-2"),
    ("일반화학", "적정/전해질", "1310-58-3"),
    ("일반화학", "착물형성/완충", "1336-21-6"),
    ("일반화학", "산화환원반응(자기반응성 주의)", "7722-84-1"),
    ("일반화학", "산화환원 적정", "7722-64-7"),
    ("분석화학", "침전적정(할로겐 정량)", "7761-88-8"),
    ("분석화학", "요오드 적정", "7553-56-2"),
    ("분석화학", "요오드 적정 환원제", "7772-98-7"),
    ("분석화학", "킬레이트 적정(EDTA)", "60-00-4"),
    ("분석화학", "황산염 침전정량", "10361-37-2"),
    ("분석화학", "침전실험", "10099-74-8"),
    ("분석화학", "착물형성/전기화학", "7758-98-7"),
    ("유기화학", "재결정 용매", "64-17-5"),
    ("유기화학", "세척/추출 용매", "67-64-1"),
    ("유기화학", "추출 용매", "110-54-3"),
    ("유기화학", "추출 용매(과산화물 형성주의)", "60-29-7"),
    ("유기화학", "재결정/추출", "108-88-3"),
    ("유기화학", "에스테르화 반응", "64-19-7"),
    ("유기화학", "아세틸화 반응(발열주의)", "108-24-7"),
    ("유기화학", "환원반응", "16940-66-2"),
    ("무기화학", "착물합성/페놀검출", "7705-08-0"),
    ("무기화학", "착물합성", "7786-81-4"),
    ("무기화학", "착물 색반응", "1762-95-4"),
    ("무기화학", "완충/염기반응", "57-13-6"),
    ("물리화학", "전도도/전기화학 셀", "7447-40-7"),
    ("물리화학", "갈바니 전지(아연)", "7440-66-6"),
    ("물리화학", "갈바니 전지(구리)", "7440-50-8"),
]


def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    group_names = dict(cur.execute("SELECT group_id, group_name FROM reactivity_groups").fetchall())

    # PubChem 재검증 통과 + 이미 KOSHA 수집 완료한 것(교차검증 배치 이후 추가된
    # 반응성 기본물질 등, 리포트 CSV 스냅샷보다 최신)은 허용 풀에 포함
    pubchem_ok = load_pubchem_confirmed_cas()
    try:
        with open(OUT_CSV, encoding="utf-8-sig") as f:
            import csv as _csv
            already_rows = list(_csv.DictReader(f))
    except FileNotFoundError:
        already_rows = []
    already_collected = set(r["cas_number"] for r in already_rows)
    allowed_cas = pubchem_ok | already_collected
    print(f"[허용 풀] PubChem 재검증 {len(pubchem_ok)}종 + 기존 수집분 {len(already_collected)}종 = {len(allowed_cas)}종")

    # --- CURATED_LIST 존재 확인 + 소속 그룹 조회 ---
    curated_rows = []
    curated_missing = []
    for course, exp, cas in CURATED_LIST:
        cur.execute("SELECT chemical_id, chemical_name FROM chemicals WHERE cas_number=?", (cas,))
        r = cur.fetchone()
        if not r:
            curated_missing.append((cas, course, exp))
            continue
        chem_id, name = r
        cur.execute("SELECT group_id FROM chemical_group_membership WHERE chemical_id=?", (chem_id,))
        for (gid,) in cur.fetchall():
            curated_rows.append({
                "cas": cas, "name": name, "group_id": gid,
                "source": "curated_curriculum", "course": course, "experiment": exp,
            })

    final = {}
    filled_per_group = {}

    # 이미 KOSHA로 실제 수집을 마친 물질은 무조건 보존한다(재생성 때마다
    # 잘리면 이미 쓴 KOSHA 쿼터·수집 데이터가 목표 리스트에서 유실됨).
    for row in already_rows:
        cas, gid = row["cas_number"], int(row["group_id"])
        final.setdefault(cas, {
            "cas": cas, "name": row["chemical_name"], "group_id": gid,
            "source": row["source"], "course": row["course"], "experiment": row["experiment"],
        })
        filled_per_group.setdefault(gid, set()).add(cas)

    for row in curated_rows:
        final.setdefault(row["cas"], row)
        filled_per_group.setdefault(row["group_id"], set()).add(row["cas"])

    # --- 그룹별 슬롯 채우기 (커리큘럼 우선, 부족분은 풀에서 자동 보충) ---
    for gid, tier in GROUP_TIER.items():
        if tier == "EXCLUDE":
            continue
        slots = TIER_SLOTS[tier]
        have = filled_per_group.get(gid, set())
        need = slots - len(have)
        if need <= 0:
            continue
        cur.execute("""
            SELECT c.cas_number, c.chemical_name
            FROM chemical_group_membership m
            JOIN chemicals c ON c.chemical_id = m.chemical_id
            WHERE m.group_id = ?
            ORDER BY c.chemical_id
        """, (gid,))
        pool = [row for row in cur.fetchall()
                if row[0] not in have and row[0] not in final and row[0] in allowed_cas]
        for cas, name in pool[:need]:
            final[cas] = {
                "cas": cas, "name": name, "group_id": gid,
                "source": "pool_supplement", "course": "", "experiment": "",
            }
            have.add(cas)

    # --- 200종 미달 시 HIGH 그룹부터 추가 보충 (250 상한) ---
    if len(final) < TARGET_MIN:
        high_groups = [g for g, t in GROUP_TIER.items() if t == "HIGH"]
        progressed = True
        while len(final) < TARGET_MIN and progressed:
            progressed = False
            for gid in high_groups:
                if len(final) >= TARGET_MAX:
                    break
                cur.execute("""
                    SELECT c.cas_number, c.chemical_name
                    FROM chemical_group_membership m
                    JOIN chemicals c ON c.chemical_id = m.chemical_id
                    WHERE m.group_id = ?
                    ORDER BY c.chemical_id
                """, (gid,))
                for cas, name in cur.fetchall():
                    if cas in final or cas not in allowed_cas:
                        continue
                    final[cas] = {
                        "cas": cas, "name": name, "group_id": gid,
                        "source": "pool_topup", "course": "", "experiment": "",
                    }
                    progressed = True
                    break
                if len(final) >= TARGET_MIN:
                    break

    # --- 상한 강제 (초과분은 topup/supplement 순으로 정리, 기존 수집분은 보존) ---
    if len(final) > TARGET_MAX:
        removable = [k for k, v in final.items()
                     if v["source"] in ("pool_topup", "pool_supplement") and k not in already_collected]
        excess = len(final) - TARGET_MAX
        for k in removable[:excess]:
            del final[k]

    # --- CSV 출력 ---
    rows = list(final.values())
    rows.sort(key=lambda r: (r["group_id"], r["source"], r["cas"]))
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["cas_number", "chemical_name", "group_id", "group_name", "source", "course", "experiment"])
        for r in rows:
            w.writerow([r["cas"], r["name"], r["group_id"], group_names.get(r["group_id"], ""),
                        r["source"], r["course"], r["experiment"]])

    # --- 콘솔 리포트 ---
    print(f"[리포트] 최종 목표 물질 수: {len(rows)}")
    src_counter = Counter(r["source"] for r in rows)
    print("  - 커리큘럼 근거(curated_curriculum):", src_counter.get("curated_curriculum", 0))
    print("  - 그룹배분 자동보충(pool_supplement):", src_counter.get("pool_supplement", 0))
    print("  - 200종 미달분 추가top-up(pool_topup):", src_counter.get("pool_topup", 0))

    covered_groups = set(r["group_id"] for r in rows)
    valid_groups = [g for g in GROUP_TIER if GROUP_TIER[g] != "EXCLUDE"]
    missing_groups = [g for g in valid_groups if g not in covered_groups]
    print(f"  - 커버된 그룹 수: {len(covered_groups)} / {len(valid_groups)}")
    if missing_groups:
        print("  - [주의] 미커버 그룹:", [(g, group_names.get(g)) for g in missing_groups])
    if curated_missing:
        print("  - [주의] CURATED_LIST 중 DB 미존재(수동확인 필요):", curated_missing)

    con.close()


if __name__ == "__main__":
    main()
