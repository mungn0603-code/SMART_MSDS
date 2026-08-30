# -*- coding: utf-8 -*-
"""
12종 누락 화학물질 수동 분류 보강 스크립트
- 원인: CAMEO 그룹 스크레이핑에서 극단적으로 흔한 '순수/모체' 화합물
  (에탄올, 아세톤, 헥산, 다이에틸에터, 톨루엔, 아세트산, 무수아세트산,
   염산, 질산, 과산화수소, 티오황산나트륨, 요소)이 체계적으로 누락됨을 확인.
  (파생/치환 화합물은 다수 존재하나 모체 화합물 자체가 없음 - 스크레이핑 갭)
- 조치: 학부 화학 수준에서 명확한 CAMEO 68그룹 분류를 수동 배정,
  source='manual_classification_verified'로 플래그하여 스크레이핑 데이터와 구분
"""
import sqlite3

DB_PATH = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\data\reactivity_reference.db"

MANUAL = [
    ("64-17-5", "ETHANOL", 8),
    ("67-64-1", "ACETONE", 38),
    ("110-54-3", "HEXANE", 33),
    ("60-29-7", "ETHYL ETHER", 28),
    ("108-88-3", "TOLUENE", 35),
    ("64-19-7", "ACETIC ACID", 2),
    ("108-24-7", "ACETIC ANHYDRIDE", 15),
    ("7647-01-0", "HYDROCHLORIC ACID", 3),
    ("7697-37-2", "NITRIC ACID", 4),
    ("7722-84-1", "HYDROGEN PEROXIDE", 50),
    ("7772-98-7", "SODIUM THIOSULFATE", 65),
    ("497-19-8", "UREA", 12),
]


def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    inserted = []
    for cas, name, gid in MANUAL:
        cur.execute("SELECT chemical_id FROM chemicals WHERE cas_number=?", (cas,))
        if cur.fetchone():
            print(f"[스킵] {cas} {name} 이미 존재")
            continue
        cur.execute(
            "INSERT INTO chemicals (cas_number, chemical_name, source) VALUES (?,?,?)",
            (cas, name, "manual_classification_verified"),
        )
        cid = cur.lastrowid
        cur.execute(
            "INSERT INTO chemical_group_membership (chemical_id, group_id, source) VALUES (?,?,?)",
            (cid, gid, "manual_classification_verified"),
        )
        inserted.append((cid, cas, name, gid))
    con.commit()

    print(f"\n[결과] {len(inserted)}건 삽입 완료")
    for row in inserted:
        print(row)

    cur.execute("SELECT COUNT(*) FROM chemicals")
    print("chemicals 총 종수:", cur.fetchone()[0])
    con.close()


if __name__ == "__main__":
    main()
