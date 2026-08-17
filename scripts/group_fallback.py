# -*- coding: utf-8 -*-
"""
CAMEO 그룹 대표물질 폴백 (docs/decisions.md 1.2c)

수집/매핑 단계에서 특정 CAS의 데이터에 결측·오류가 있을 때(PubChem 무매칭,
CID 조회 실패 등), 같은 CAMEO 그룹의 다른 물질을 대체 후보로 제시한다.
최종 반응성 판정 단계(03_compatibility/compatibility_engine.py)의 Abstain
원칙과는 다른 계층 — 여기는 "이 물질 대신 뭘 쓸까"를 고르는 수집 단계 보조 도구다.

이미 KOSHA MSDS 4개 섹션을 확보한 물질을 우선 추천한다 — 그래야 대체 즉시
쓸 수 있다(추가 수집 없이).
"""
import sqlite3
import sys

DB_PATH = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\data\reactivity_reference.db"


def get_fallback_candidates(cas_number, db_path=DB_PATH, limit=3):
    """cas_number가 속한 그룹에서 자기 자신을 제외한 대체 후보를 반환.
    반환: [{cas, name, group_id, group_name, has_msds}, ...] (그룹별 최대 limit개)
    cas_number 자체가 매핑이 없으면 빈 리스트."""
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    cur.execute("SELECT chemical_id FROM chemicals WHERE cas_number=?", (cas_number,))
    row = cur.fetchone()
    if row is None:
        con.close()
        return []
    chemical_id = row[0]

    cur.execute(
        "SELECT group_id FROM chemical_group_membership WHERE chemical_id=?",
        (chemical_id,),
    )
    group_ids = [r[0] for r in cur.fetchall()]

    candidates = []
    for gid in group_ids:
        cur.execute(
            """
            SELECT c.cas_number, c.chemical_name, g.group_id, g.group_name,
                   EXISTS(
                       SELECT 1 FROM msds_sections s WHERE s.cas_number = c.cas_number
                   ) AS has_msds
            FROM chemical_group_membership m
            JOIN chemicals c ON c.chemical_id = m.chemical_id
            JOIN reactivity_groups g ON g.group_id = m.group_id
            WHERE m.group_id = ? AND c.chemical_id != ?
            ORDER BY has_msds DESC, c.cas_number
            LIMIT ?
            """,
            (gid, chemical_id, limit),
        )
        for cas, name, group_id, group_name, has_msds in cur.fetchall():
            candidates.append(
                {
                    "cas": cas,
                    "name": name,
                    "group_id": group_id,
                    "group_name": group_name,
                    "has_msds": bool(has_msds),
                }
            )
    con.close()
    return candidates


def _print_candidates(cas_number):
    candidates = get_fallback_candidates(cas_number)
    print(f"\n=== {cas_number} 대체 후보 ===")
    if not candidates:
        print("  (그룹 매핑 자체가 없음 — 폴백 불가, 이 CAS는 Abstain 대상)")
        return
    for c in candidates:
        flag = "MSDS 확보" if c["has_msds"] else "MSDS 미확보"
        print(f"  [{c['group_name']}] {c['cas']} {c['name']} ({flag})")


def _self_check():
    """CID 조회 실패했던 실제 문제 CAS 하나로 자체검증."""
    candidates = get_fallback_candidates("7440-50-8")  # COPPER, Metals Less Reactive
    assert candidates, "구리(7440-50-8)는 그룹 매핑이 있으므로 후보가 있어야 함"
    assert all(c["cas"] != "7440-50-8" for c in candidates), "자기 자신은 후보에서 제외돼야 함"
    assert get_fallback_candidates("0-00-0") == [], "미매핑 CAS는 빈 리스트여야 함"
    print("자체검증 통과")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args:
        for cas in args:
            _print_candidates(cas)
    else:
        _self_check()
        # 2026-08-07 파일럿에서 확인된 PubChem 결측/CID조회실패 10종
        problem_cas = [
            "10026-11-6",  # ZIRCONIUM TETRACHLORIDE
            "27176-87-0",  # DODECYLBENZENESULFONIC ACID
            "1317-65-3",   # LIMESTONE
            "135072-82-1", # Diazonium Salts (기존 대체후보 소진으로 기록된 물질)
            "15005-97-7",  # Diazonium Salts (상동)
            "12002-43-6",  # GILSONITE
            "1338-02-9",   # COPPER NAPHTHENATE
            "1304-82-1",   # BISMUTH TELLURIDE
            "10101-63-0",  # LEAD IODIDE
            "7772-98-7",   # SODIUM THIOSULFATE
        ]
        for cas in problem_cas:
            _print_candidates(cas)
