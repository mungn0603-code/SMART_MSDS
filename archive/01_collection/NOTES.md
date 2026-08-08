# archive/01_collection — 정리 사유

`01_collection/`에서 최종 채택 파일만 남기고 옮긴 항목들. 최종 채택 파일 목록과
현재 파이프라인 실행 순서는 [`docs/HANDOFF.md`](../../docs/HANDOFF.md) §6 참고.

## logs/ — 실행 로그
| 파일 | 내용 | 결과 |
|---|---|---|
| `kosha_collect.log` | `kosha_msds_collector.py` 실행 로그 (200종 수집 시도) | 최종 198/200 확보. 상세 경위는 [`docs/session_log_2026-08-06.md`](../../docs/session_log_2026-08-06.md) |
| `scrape_cameo.log` | `scrape_cameo_chemical_groups.py` 실행 로그 (CAMEO 68그룹 스크레이핑) | 성공, DB(`cameo_chemical_groups.db`)에 반영됨 |

로그 자체는 재실행 시 스크립트가 다시 생성하므로 코드 동작에 필요하지 않음. 과거 실행
결과 확인용으로만 보존.

## superseded_snapshots/ — 폐기된 중간 스냅샷
`undergrad_target_chemicals.csv`의 라운드별 백업. **기각 사유: 최종본으로 대체됨(superseded),
자료 자체의 오류는 아님.**

| 파일 | 시점 | 대체 이유 |
|---|---|---|
| `undergrad_target_chemicals_v1_backup.csv` | 2026-08-03 | 커리큘럼 12종 CAS 불일치 수정 전 원본. [`HANDOFF_ARCHIVE.md`](../../docs/HANDOFF_ARCHIVE.md) §4 |
| `undergrad_target_chemicals.csv.bak` | round1 직전 | `backfill_group_replacements.py` 실행 전 상태 |
| `undergrad_target_chemicals.csv.round2.bak` | round2 직전 | `backfill_round2_safety_filter.py` 실행 전 상태 — round1 대체품 30/32 중 석면·블레오미신 등 10건이 재검증에서 부적절 판정 |
| `undergrad_target_chemicals.csv.round3.bak` | round3 직전 | `backfill_round3_manual_picks.py` 실행 전 상태 — round2 자동필터를 아프라톡신 B1이 통과한 사고 이후 수동 검토本 |

세 차례 라운드 스크립트(`backfill_round*.py`)는 데이터 계보를 재현하는 데 필요하므로
`01_collection/`에 그대로 남겨둠(기각 아님, 최종 파이프라인의 일부).

## CAMEO 웹 스크레이핑 원본 (robots.txt 위반으로 경로 전환, 2026-08-08)
`cameochemicals.noaa.gov`를 직접 스크레이핑해 CAS↔CAMEO 68그룹 매핑
(3,386종/6,657행)을 확보했던 원본 경로. `robots.txt`의 `/search` 계열 disallow를
위반해 확보된 데이터로 확인돼 포트폴리오 취약점으로 식별됐고, PubChem 공식
엔드포인트(`01_collection/pubchem_verify_groups.py`) 기반으로 전환·재검증
완료(3,396종 중 94% MATCH). 상세 근거는
[`docs/decisions.md`](../../docs/decisions.md) §1.2b 참고.

| 파일 | 내용 |
|---|---|
| `scrape_cameo_chemical_groups.py` | 스크레이핑 본체(세션 쿠키 기반 페이지네이션) |
| `test_scrape_cameo_chemical_groups.py` | 위 스크립트 테스트 |
| `cameo_chemical_groups.db` | 스크레이핑 원시 출력(9,231행, `reactivity_reference.db`와 분리 보관하던 원본) |
| `cas_reactive_group_mapping.csv` | 위 원시 출력을 정리한 CAS→그룹 매핑 CSV.
  **여전히 `02_classification/build_chemical_group_membership.py`가 이 경로를
  참조**(재현용, DB 재빌드 시 필요) — 파일만 이동, 코드의 경로 상수도 함께 갱신함 |
| `Cameo_reactivity.csv` | CAMEO 68×68 그룹 양립성 매트릭스(Export Compatibility
  Chart) — 그룹 간 반응성 매트릭스 자체는 CAS 단위 스크레이핑과 무관하게 얻은
  자료라 robots.txt 위반 대상은 아니었으나, 같은 출처 계보라 함께 정리. **여전히
  `02_classification/seed_reactivity_reference.py`가 이 경로를 참조**(재현용) —
  마찬가지로 경로 상수 갱신함 |

**주의**: 위 두 CSV는 폐기물이 아니라 `reactivity_reference.db`를 처음부터
재생성할 때 필요한 시드 입력이다(재현성 유지 목적으로 이동만 하고 삭제하지
않음, backfill_round*.py와 같은 논리). 실제 CAS↔그룹 매핑의 **신규/교차검증
경로는 이제 PubChem**이지만, DB를 0부터 재구축하는 경로 자체는 여전히 이
스크레이핑 원본을 시드로 쓴다 — 완전히 PubChem 기반으로 재시딩하는 스크립트는
아직 없음(다음 세션 후보).

## diagnostic_scripts/ — 해결된 문제의 일회성 진단 스크립트
KOSHA API가 유효한 서비스키에도 `403 SERVICE_KEY_IS_NOT_REGISTERED_ERROR`를 반환하던
문제를 진단하기 위해 작성. **원인은 코드가 아니라 포털 측 계정-키 등록 연동 버그로
판명, 사용자가 KOSHA에 문의해 해결 완료** ([`docs/session_log_2026-08-06.md`](../../docs/session_log_2026-08-06.md)).
문제가 재발하지 않는 한 다음 세션에서 쓸 일이 없어 아카이브.

| 파일 | 용도 |
|---|---|
| `_check_env.py` | `.env` 파일 파싱 상태(키 길이, `%` 잔존 여부) 점검 |
| `_diag_service_key.py` | 서비스키 원문 노출 없이 403 원인 진단(길이/해시만 출력) |
| `_test_single_cas.py` | 이중인코딩 수정 검증용 단건(에탄올) 수집 테스트 |
