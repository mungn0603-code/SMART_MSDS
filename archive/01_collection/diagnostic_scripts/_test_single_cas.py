# -*- coding: utf-8 -*-
"""
이중인코딩 수정 검증용 단건 테스트 - 에탄올(CAS 64-17-5) 1종만 실행.
kosha_msds_collector.py의 실제 함수를 그대로 재사용(로직 중복 없음).
성공/실패만 확인하고 끝냄 - 200종 전체 수집(main())은 호출하지 않음.
"""
import sqlite3
import kosha_msds_collector as kc

TEST_CAS = "64-17-5"  # 에탄올

def main():
    print(f"SERVICE_KEY 로드 여부: {'OK' if kc.SERVICE_KEY else 'MISSING'}")
    print(f"SERVICE_KEY에 '%' 잔존 여부(이중인코딩 재발 체크): {'%' in (kc.SERVICE_KEY or '')}")

    con = sqlite3.connect(kc.DB_PATH)
    kc.ensure_tables(con)

    try:
        chem_id = kc.resolve_chem_id(con, TEST_CAS)
        print(f"chem_id 조회 결과: {chem_id}")
        if not chem_id:
            print("실패: getChemList에서 CAS를 찾지 못함(Abstain 처리됨)")
            return

        for section in kc.SECTIONS:
            status = kc.fetch_and_store_section(con, TEST_CAS, chem_id, section)
            print(f"섹션 {section}: {status}")

        cur = con.execute(
            "SELECT section, COUNT(*) FROM msds_sections WHERE cas_number=? GROUP BY section",
            (TEST_CAS,)
        )
        print("DB 적재 확인:", cur.fetchall())
        print("=== 테스트 성공 ===")
    except Exception as e:
        print(f"=== 테스트 실패: {type(e).__name__}: {e} ===")
    finally:
        con.close()

if __name__ == "__main__":
    main()
