# archive/2026-08-08_selection_scripts — 정리 사유

2026-08-08 물질선정 시절에 쓰인 1회성 스크립트 14종과 그 전용 입력 CSV 3종.
**2026-08-30 저장소 정리에서 `scripts/`가 실행 스크립트만 담도록 분리하면서 옮겼다.**

## 왜 옮겼는가

물질 선정의 단일 출처가 `substance_registry`로 바뀌면서
([`docs/REGISTRY.md`](../../docs/REGISTRY.md)) 이 스크립트들이 만들던 선정 결과 자체가
근거로서 폐기됐다. 코드가 틀려서가 아니라 **판단 기준이 교체돼 존재 목적이 소멸**했다.
현재 저장소에서 이 14개 파일을 import하거나 호출하는 코드는 0건이다.

## 실행 가능 상태가 아니다

`backfill_*` 계열은 `sys.path` 상대경로로 `scripts/kosha_msds_collector.py`를 import하고,
`section10_baseline.py`는 같은 폴더의 `provenance_audit.py`를 import한다.
**archive 위치에서는 그대로 돌지 않는다.** 재실행이 필요하면 `scripts/`로 되돌린 뒤 돌린다.
이 폴더의 목적은 기록 보존이지 실행 가능 상태 유지가 아니다.

## 파일

| 파일 | 용도 | 대체된 경로 |
|---|---|---|
| `backfill_candidate_probe.py` `backfill_coverage_gain.py` | 그룹 커버리지 보강 후보 조사 | Registry CORE 5축 선정 |
| `backfill_group_replacements.py` `backfill_round2_safety_filter.py` `backfill_round3_manual_picks.py` | 결측·부적절 물질 대체(3라운드) | 동일 |
| `build_undergrad_target_list.py` `expand_by_reaction_frequency.py` | 타겟 물질 리스트 웨이브1/2 구성 | `scripts/build_substance_registry.py` |
| `fix_missing_common_chemicals.py` | 결측 공통물질 보정 | 동일 |
| `build_final_selection_audit.py` `provenance_audit.py` | 173종 선정 감사·근거 추적 | `scripts/service_contract_audit.py` |
| `section10_baseline.py` | §10 근거 실측 | 목적 달성 후 재실행 없음 |
| `group_fallback.py` | 같은-그룹 대체 후보 추천(수집 단계 전용) | 수집 종료로 소멸 |
| `evalset.py` | 단일물질 fact 평가셋 생성 | **재실행 불가** — item 청크 기반인데 DB의 item 청크 18,200행이 2026-08-24 삭제됐다. 산출물은 `data/evalset/`에 보존 |
| `run_cameo_v5_retry.py` | v4 unfaithful 203건 v5 표적 재시도 | Nemotron·프롬프트 v5 시절. 현재 모델(solar-pro3)·프롬프트(v7/v8b)와 무관 |

## inputs/

`scripts/` 쪽 살아있는 코드가 더 이상 읽지 않아 함께 옮긴 CSV.

| 파일 | 읽던 스크립트 |
|---|---|
| `chemical_selection_final_2026-08-08.csv` | 없음(참조 0건) |
| `chemical_selection_audit_dataset_2026-08-08.csv` | `build_final_selection_audit.py`, `provenance_audit.py` |
| `chemical_selection_final_audit_2026-08-08.csv` | `build_final_selection_audit.py` |

함께 옮기지 **않은** 것: `data/collection/undergrad_target_chemicals.csv`(살아있는
`scripts/kosha_msds_collector.py`가 읽는다), `pubchem_verification_report{,_full}.csv`
(`scripts/pubchem_verify_groups.py`가 읽는다).
