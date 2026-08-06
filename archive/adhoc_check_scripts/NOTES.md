# archive/adhoc_check_scripts — 정리 사유

특정 시점의 일회성 조사/검증에 쓰인 스크립트 모음(기존 `archive/_delete_candidates/`를
이 폴더로 통합, 하위 카테고리보다 "해결된 이슈의 부산물"이라는 성격이 더 두드러져
분야별 대신 용도별로 묶음). 모두 해당 이슈가 해결된 뒤로는 재실행할 일이 없어 삭제
후보였던 것을 보존 차원에서 아카이브.

| 파일 | 용도 | 관련 이슈 / 로그 |
|---|---|---|
| `_check_12.py` | `reactivity_reference.db`에서 커리큘럼 12종의 CAS/그룹매핑 존재 여부 직접 조회 | 커리큘럼 12종 CAS 불일치 조사. 해결 경위: [`docs/HANDOFF_ARCHIVE.md`](../../docs/HANDOFF_ARCHIVE.md) §4 (`fix_missing_common_chemicals.py`로 최종 해결) |
| `_check_csv.py` | CURRENT vs v1_backup CSV에서 동일 12종의 존재 여부 비교 | 위와 동일 이슈의 CSV 레벨 확인 |
| `_check_env.ps1` | PowerShell로 `.env` 라인 구조 점검(키 원문 미노출) | KOSHA 서비스키 403 진단 과정의 보조 스크립트. [`archive/01_collection/NOTES.md`](../01_collection/NOTES.md) 참고 |
| `_verify_collector.py` | `kosha_msds_collector.py`의 `py_compile` 구문 검증만 수행 | 1회성 문법 점검, 이후 `test_kosha_msds_collector.py`(정식 테스트)로 대체됨 |

기각 사유는 전부 동일: **해당 조사/버그가 이미 해결되어 스크립트의 존재 목적이
소멸**했기 때문(코드 오류로 인한 기각이 아님). 별도 실행 로그 파일은 없음(콘솔 출력만
있었고 저장되지 않음).
