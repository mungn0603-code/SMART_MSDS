# archive/02_pubchem_rejected — 정리 사유

**기각된 접근법**: PubChem Compound Full SDF 덤프를 스트리밍 파싱해 CAS↔PubChem CID
매핑 CSV를 만드는 스크립트. 현재 파이프라인 어디에서도 import/실행되지 않음(전체
코드베이스 grep으로 참조 없음 확인, 2026-08-06).

## 기각 사유
CAS↔물질 매핑은 최종적으로 CAMEO 68그룹 스크레이핑 경로
(`01_collection/scrape_cameo_chemical_groups.py` → `cas_reactive_group_mapping.csv`)로
확정 채택됐다. PubChem SDF 경로는:
- CAMEO의 반응성 그룹 분류 체계(이 프로젝트의 핵심 비타협 원칙 — CAMEO 68그룹 엄격
  적용)와 무관한 별도 식별자 체계라 그룹 매핑에 직접 쓸 수 없음
- 전체 Compound SDF(수백만 화합물)를 스트리밍 처리해야 하는 무거운 접근으로, 200종
  규모의 학부 타겟 리스트에는 과잉 스펙

## 로그
별도 실행 로그 없음(로컬 실행 결과가 파일로 저장되지 않는 스크립트). `test_pubchem_cas_cid_extract.py`는
파싱 로직 자체의 단위 테스트로 스크립트와 함께 보존.

## 남은 파일
| 파일 | 내용 |
|---|---|
| `pubchem_cas_cid_extract.py` | PubChem SDF 스트리밍 파서 (미사용) |
| `test_pubchem_cas_cid_extract.py` | 위 스크립트 단위 테스트 |
