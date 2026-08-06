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
