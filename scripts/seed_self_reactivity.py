# -*- coding: utf-8 -*-
"""
self_reactivity 테이블 채우기 (68개 CAMEO 그룹 자기반응성)
근거: NFPA 704, DOT/UN Class 4.1(자기반응성물질), OSHA 과산화물생성물질 목록,
      EPA/CAMEO 반응성그룹 공식 설명 등 공개 문헌 기반 일반 지식.
근거등급: 모든 행에 [Reference] 표기 (법령/권고 등급 아님, 개별 물질 확인 전 참고용).
정보 부족 그룹(#36)은 기각정책에 따라 Unknown 유지.
idempotent: UPDATE만 수행, 행은 이미 68개 존재(schema 초기화 시 생성).
"""
import sqlite3, os

DB_PATH = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\data\reactivity_reference.db"

# (group_id, category, notes)  category in {Compatible, Caution, Incompatible, Unknown}
DATA = [
    (1, "Compatible", "대부분 안정적, 일부 헤미아세탈은 서서히 알데히드/알코올로 가역 분해되나 위험한 자기반응 아님. [Reference]"),
    (2, "Compatible", "카르복실산은 일반적으로 자기반응성 없음, 안정. [Reference]"),
    (3, "Compatible", "강산(비산화성)은 순물질 상태에서 안정, 자기반응 없음. [Reference]"),
    (4, "Caution", "농축 강산화성 산(발연질산, 과염소산 등)은 가열/오염 시 자기가속분해 가능. [Reference]"),
    (5, "Compatible", "약산은 안정. [Reference]"),
    (6, "Incompatible", "아크릴레이트/아크릴산은 억제제 소실·가열 시 격렬한 자기중합(폭주반응) 위험, 대표적 자기반응성 그룹. [Reference]"),
    (7, "Compatible", "아실/설포닐 할라이드는 수분과 반응(외부 요인)하나 자체끼리는 비교적 안정; 수분 민감성 별도 주의. [Reference]"),
    (8, "Compatible", "알코올/폴리올은 안정. [Reference]"),
    (9, "Caution", "일부 알데히드는 공기 중 서서히 산화되어 불안정 과산화물/과산 생성(자동산화), 포름알데히드는 파라포름알데히드로 자기중합 가능. [Reference]"),
    (10, "Caution", "말단 알킨은 장기보관/금속용기 접촉 시 폭발성 금속아세틸라이드 형성 가능(외부 금속 개입), 일부 촉매 조건에서 자기중합 가능성. [Reference]"),
    (11, "Compatible", "비말단 알킨은 비교적 안정. [Reference]"),
    (12, "Compatible", "아마이드/이미드는 안정. [Reference]"),
    (13, "Compatible", "방향족 아민은 공기 중 서서히 변색(자동산화)되나 격렬한 자기반응 아님. [Reference]"),
    (14, "Compatible", "아민/포스핀/피리딘은 안정; 일부 포스핀은 공기(외부 O2)와 자연발화성이나 자기반응 아님. [Reference]"),
    (15, "Compatible", "무수물은 수분에 반응(외부 요인)하나 건조 상태에서 안정. [Reference]"),
    (16, "Compatible", "아릴 할라이드는 안정. [Reference]"),
    (17, "Incompatible", "아조/디아조/아지도/하이드라진/아자이드 화합물은 열적으로 불안정하여 폭발적 자기분해(질소가스 방출) 가능, 대표적 자기반응성 그룹. [Reference]"),
    (18, "Compatible", "강염기는 안정. [Reference]"),
    (19, "Compatible", "약염기는 안정. [Reference]"),
    (20, "Compatible", "카바메이트는 비교적 안정; 고온에서 이소시아네이트/CO2로 분해 가능하나 상온에서 자발적 자기반응 아님. [Reference]"),
    (21, "Compatible", "탄산염은 안정. [Reference]"),
    (22, "Compatible", "클로로실란은 수분과 격렬히 반응(외부 요인, HCl 방출)하나 자체끼리는 반응 없음. [Reference]"),
    (23, "Incompatible", "공액디엔(부타디엔, 이소프렌 등)은 자동산화로 생성된 과산화물이 개시제로 작용해 자기중합 폭주 위험, 억제제 필요. [Reference]"),
    (24, "Compatible", "무기 시아나이드는 산/수분과 반응(외부 요인, HCN 방출)하나 고체 상태에서 자체 안정. [Reference]"),
    (25, "Incompatible", "디아조늄염은 극히 불안정, 특히 건조 상태에서 폭발적으로 자기분해; 대표적 고위험 자기반응성 그룹. [Reference]"),
    (26, "Incompatible", "에폭사이드는 미량 산/염기 촉매나 가열 시 발열성 개환 자기중합 폭주 가능(예: 에틸렌옥사이드). [Reference]"),
    (27, "Compatible", "에스터류(황산/인산/티오인산/붕산 에스터)는 대체로 안정; 일부는 수분에 가수분해되나 자기반응 아님. [Reference]"),
    (28, "Caution", "에터는 공기/빛 노출 시 서서히 자동산화되어 불안정/폭발성 과산화물 축적(대표적 장기보관 위험). [Reference]"),
    (29, "Compatible", "가용성 불화물염은 안정. [Reference]"),
    (30, "Compatible", "불소화 유기화합물은 상온에서 매우 안정; 고온 열분해 시 유독가스(HF) 발생 가능하나 자발적 자기반응 아님. [Reference]"),
    (31, "Caution", "할로겐화 유기화합물 일부는 빛/열/금속 접촉 시 서서히 분해(예: 클로로포름의 광산화) 가능. [Reference]"),
    (32, "Caution", "할로겐화제(차아염소산칼슘 등)는 오염/가열 시 자기가속 발열분해로 화재 이력 다수, 취급 주의. [Reference]"),
    (33, "Compatible", "포화 지방족 탄화수소는 안정. [Reference]"),
    (34, "Caution", "불포화 지방족 탄화수소는 자동산화로 과산화물 생성 가능, 일부는 중합 경향. [Reference]"),
    (35, "Compatible", "방향족 탄화수소는 안정. [Reference]"),
    (36, "Unknown", "분류 정보 부족 그룹(정의상 불확실), 기각정책 적용. 근거등급 부여 대상 아님."),
    (37, "Incompatible", "이소시아네이트류는 촉매/가열/미량 수분에 의해 발열성 자기삼량체화(자기중합) 위험, MDI/TDI 보관 시 대표적 위험. [Reference]"),
    (38, "Compatible", "케톤은 안정; 일부 엔올화 가능 케톤은 염기 촉매 하 알돌 자기축합 가능하나 자발적이지 않음. [Reference]"),
    (39, "Caution", "금속수소화물/금속알킬/금속아릴/실란류는 열적으로 불안정하거나 공기(외부 O2/수분) 노출 시 자연발화성인 경우가 많음. [Reference]"),
    (40, "Compatible", "활성알칼리금속은 순수 상태(공기/수분 차단)에서는 안정; 반응성은 주로 외부 수분/공기와의 접촉에서 발생. [Reference]"),
    (41, "Caution", "활성 금속분말(알루미늄, 아연, 마그네슘 분말 등)은 미세분말 상태에서 공기 중 자연발화/자기발열 위험. [Reference]"),
    (42, "Compatible", "반응성 낮은 금속은 안정. [Reference]"),
    (43, "Caution", "무기 질산염/아질산염은 가열/오염 시 열분해 위험, 특히 질산암모늄은 오염·밀폐 조건에서 자기지속 분해·폭발 사례 다수. [Reference]"),
    (44, "Compatible", "질화물/인화물/탄화물/규화물은 수분과 격렬히 반응(외부 요인, 유독/가연성 가스 방출)하나 건조 상태에서 자체 안정. [Reference]"),
    (45, "Compatible", "니트릴은 비교적 안정. [Reference]"),
    (46, "Incompatible", "유기 니트로/니트로소/니트레이트/니트라이트 화합물은 다수가 폭발물로 분류되며 열/충격에 의한 자기분해 폭발 위험. [Reference]"),
    (47, "Compatible", "비산화환원성 무기화합물은 정의상 반응성 낮음. [Reference]"),
    (48, "Compatible", "화학적으로 비반응성 그룹, 정의상 안정. [Reference]"),
    (49, "Caution", "유기금속화합물은 다수가 공기/수분(외부 요인)에 민감하거나 열적으로 불안정. [Reference]"),
    (50, "Incompatible", "강산화제는 가열/오염 시 자기가속 발열분해 위험(과산화물, 과염소산염, 과망간산염 등), 대표적 고위험군. [Reference]"),
    (51, "Caution", "약산화제는 강산화제보다 낮으나 일부 가열 시 서서히 분해 가능. [Reference]"),
    (52, "Compatible", "옥심은 비교적 안정; 산 촉매 하 베크만 전위 등은 외부 촉매 필요. [Reference]"),
    (53, "Incompatible", "유기 과산화물은 충격/마찰/열에 극히 민감하여 폭발적 자기분해 위험, 자기반응성의 대표 그룹. [Reference]"),
    (54, "Compatible", "페놀염은 안정. [Reference]"),
    (55, "Compatible", "페놀/크레졸은 공기 중 서서히 변색(자동산화)되나 격렬한 자기반응 아님. [Reference]"),
    (56, "Incompatible", "중합성화합물은 정의상 자기중합(자기반응) 위험군, 억제제 없이는 발열 폭주 가능. [Reference]"),
    (57, "Compatible", "4급 암모늄/포스포늄염은 안정; 고온에서 Hofmann 분해 가능하나 상온 자발적 반응 아님. [Reference]"),
    (58, "Caution", "강력 환원제 일부(하이드라진 등)는 열적으로 불안정하여 자기분해 위험 존재. [Reference]"),
    (59, "Compatible", "약한 환원제는 비교적 안정. [Reference]"),
    (60, "Compatible", "산성염은 안정. [Reference]"),
    (61, "Compatible", "염기성염은 안정. [Reference]"),
    (62, "Compatible", "실록산은 매우 안정(예: 실리콘오일). [Reference]"),
    (63, "Compatible", "무기 황화물은 산/수분과 반응(외부 요인, H2S 방출) 가능하나 자체는 비교적 안정. [Reference]"),
    (64, "Compatible", "유기 황화물은 공기 중 서서히 산화(설폭사이드/설폰 생성)되나 격렬하지 않음. [Reference]"),
    (65, "Compatible", "아황산염/티오황산염은 서서히 공기산화되나 비교적 안정. [Reference]"),
    (66, "Compatible", "유기 설포네이트/포스포네이트/티오포스포네이트는 안정. [Reference]"),
    (67, "Compatible", "티오카바메이트/디티오카바메이트 에스터·염은 열/산에 의해 분해(CS2/H2S 방출) 가능하나 상온 자발적 반응 아님. [Reference]"),
    (68, "Compatible", "물 및 수용액은 정의상 자기반응 없음(자기 자신과 반응하지 않음). [Reference]"),
]

def main():
    assert len(DATA) == 68, f"expected 68 rows, got {len(DATA)}"
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.executemany(
        "UPDATE self_reactivity SET category = ?, notes = ? WHERE group_id = ?",
        [(cat, notes, gid) for gid, cat, notes in DATA],
    )
    con.commit()

    cur.execute("SELECT category, COUNT(*) FROM self_reactivity GROUP BY category ORDER BY category")
    breakdown = cur.fetchall()
    cur.execute("SELECT COUNT(*) FROM self_reactivity WHERE category='Unknown'")
    unknown_ct = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM self_reactivity")
    total_ct = cur.fetchone()[0]

    print("category breakdown:", breakdown)
    print("total rows:", total_ct, "| Unknown remaining:", unknown_ct)
    con.close()

if __name__ == "__main__":
    main()
