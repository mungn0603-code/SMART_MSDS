# Archive: Chemical Selection 2026-08-08

**STATUS: HISTORICAL / NOT AUTHORITATIVE**

이 디렉터리는 2026-08-08 Chemical Selection 기준 재설계 과정의 중간 산출물, 과거 후보
집합, 검증 결과 및 methodology 기록을 보존한다.

**최종 authoritative 결과는 archive 밖에 존재한다.**

- 최종 기준: [`docs/chemical_selection_final_2026-08-08.md`](../../docs/chemical_selection_final_2026-08-08.md)
- 최종 chemical selection: [`01_collection/chemical_selection_final_2026-08-08.csv`](../../01_collection/chemical_selection_final_2026-08-08.csv) (173행)
- 426종 전체 4분류 감사(추적용, 이것도 authoritative): [`01_collection/chemical_selection_final_audit_2026-08-08.csv`](../../01_collection/chemical_selection_final_audit_2026-08-08.csv)
- 최종 판정 스크립트: [`01_collection/build_final_selection_audit.py`](../../01_collection/build_final_selection_audit.py)

```
최종 corpus 기준: 173 substances

426개 전체 중:
  30  MANDATORY
  129 HAZARD-RELEVANT
  14  REPRESENTATIVE
  253 UNJUSTIFIED (최종 집합에서 제외 — "쓸모없음 증명"이 아니라 "현재 근거 부족")
```

## audits/ — 과거 후보 세트 / provenance 감사 CSV

Phase 3~8에서 반복적으로 만들어졌던 "최종" 후보 세트들. 어느 것도 최종 기준이 아니며,
retrieval 성능·marginal utility·eval-set 등 이번에 배제하기로 한 진단자료에 의존해
KEEP/DROP을 재판정했던 산출물이다.

| 파일 | 내용 |
|---|---|
| `chemical_phase3_reassessment_2026-08-08.csv` | signature 중복/§10 실질근거 기준 1차 재평가 |
| `chemical_phase4_adjudication_2026-08-08.csv` | Phase3 결과에 대한 조정(merge cluster) 판정 |
| `chemical_phase6_query_level_2026-08-08.csv` | retrieval 질의 단위 성능 상세 |
| `chemical_phase6_retrieval_reassessment_2026-08-08.csv` | retrieval hit_rate/MRR 기반 재평가(시나리오 가중치 포함) |
| `chemical_phase7_candidate_sets_2026-08-08.csv` | Phase7 후보 세트 비교 요약 |
| `chemical_phase7_eval_audit_2026-08-08.csv` | Phase7 독립 평가셋 감사 |
| `chemical_phase7_independent_evalset_2026-08-08.csv` | Phase7 독립 평가셋 본체 |
| `chemical_phase7_review134_status_2026-08-08.csv` | 134종 REVIEW 대상 상태 추적 |
| `chemical_phase8_eval_expansion_2026-08-08.csv` | Phase8 평가셋 확장 |
| `chemical_phase8_final_candidates_2026-08-08.csv` | Phase8 "최종" 후보(당시 426/259 등 라벨) |
| `chemical_phase8_gold_audit_2026-08-08.csv` | Phase8 gold 쌍 감사 |
| `chemical_phase8_marginal_utility_2026-08-08.csv` | Phase8 marginal utility(dependency_class) 모델 결과 — 이번 재설계에서 금지한 방식 |
| `chemical_backfill_candidates_2026-08-08.csv` | 회소 그룹 backfill 후보(자동 편입 안 됨) |
| `chemical_selection_backfill_candidates_2026-08-08.csv` | 위와 동일 계열의 초기 버전 |
| `undergrad_target_chemicals_proposed_final_2026-08-08.csv` | 과거 "제안 최종" 목록(현재 authoritative 파일로 대체됨) |
| `chemical_hazard_relevant_sample_audit_2026-08-08.csv` | HAZARD-RELEVANT 247건 중 45건 샘플 감사(TRUE/BORDERLINE/FALSE 수기 판정) — CASE 2 수정의 근거 자료 |

## comparisons/ — 기준 변경 전후 비교

| 파일 | 내용 |
|---|---|
| `chemical_hazard_relevant_case2_changes_2026-08-08.csv` | CASE 2 수정 적용 전/후 category·decision이 바뀐 118개 물질 diff |

## reports/ — 과거 methodology 문서 / 리포트

| 파일 | 내용 |
|---|---|
| `chemical_selection_criteria_redesign_2026-08-08.md` | 1차(Phase1) 재설계 문서 |
| `chemical_selection_audit_2026-08-08.md` | Phase1 provenance/coverage 감사 리포트 |
| `chemical_backfill_audit_2026-08-08.md` | backfill 후보 감사 리포트 |
| `chemical_selection_phase3_reassessment_2026-08-08.md` | Phase3 리포트 |
| `chemical_selection_phase4_adjudication_2026-08-08.md` | Phase4 리포트 |
| `chemical_selection_phase6_retrieval_reassessment_2026-08-08.md` | Phase6 리포트(retrieval 기반 재평가) |
| `chemical_selection_phase7_independent_validation_2026-08-08.md` | Phase7 리포트 |
| `chemical_selection_phase8_final_validation_2026-08-08.md` | Phase8 리포트 |
| `independent_evaluation_set_design_2026-08-08.md` | Phase7 독립 평가셋 설계 문서 |
| `phase5_426_vs_259_results_2026-08-08.md` | 426 vs 259 코퍼스 retrieval 비교 |
| `phase5_rag_sync_plan_2026-08-08.md` | corpus_tag 기반 RAG 동기화 설계(259proposed/259_retrieval_aware/phase6_D/phase7_D/phase8_E 등 복수 코퍼스 태그 도입 경위) |
| `phase6_candidate_sets_results_2026-08-08.md` | Phase6 후보 세트 결과 |
| `phase7_candidate_comparison_results_2026-08-08.md` | Phase7 후보 비교 결과 |
| `phase8_final_comparison_results_2026-08-08.md` | Phase8 최종 비교 결과 |
| `section10_baseline_2026-08-08.md` | §10 카테고리 baseline 분석 |
| `chemical_selection_criteria_final_redesign_2026-08-08.md` | 이번 재설계 1단계 문서(4분류 프레임워크 최초 도입, CASE 2 수정 반영 전) |
| `hazard_relevant_sample_audit_2026-08-08.md` | HAZARD-RELEVANT 샘플 감사 리포트(CASE 2 수정의 직접 근거) |

## 왜 archive로 옮겼는가

이 파일들은 모두 retrieval 성능·marginal utility·eval-set 멤버십·목표 물질 수 등
diagnostic evidence에 의존했거나, 이번에 동결한 4분류(MANDATORY/HAZARD-RELEVANT/
REPRESENTATIVE/UNJUSTIFIED) 기준 이전 단계의 산출물이다. 삭제하지 않고 보존한 이유는
"왜 이런 시행착오를 거쳤는지"를 나중에 다시 추적할 수 있게 하기 위함이며, 이 디렉터리의
어떤 파일도 현재 corpus 구성이나 selection 기준에 더 이상 사용되지 않는다.

## scripts/ — Phase 3~8 방법론 소스 (2026-08-08 이동)

`02_classification/phase3~8_*.py`를 여기로 이동했다(`reports/`, `audits/`의
산출물을 만들어낸 실제 소스). 최소 변경 원칙상 보류했던 초기 버전과 달리,
`from provenance_audit import ...`를 쓰는 phase3/phase4_adjudication/
phase4_coverage_and_proposal 세 파일은 이동 전 `sys.path.insert(0, ...02_classification)`를
추가해 provenance_audit.py(archive 밖, `02_classification/`에 authoritative로 유지)를
계속 import할 수 있게 했다. phase6/phase7은 이미 절대경로 sys.path.insert를 쓰고
있어 그대로 옮겨도 안전했고, phase8은 로컬 모듈 의존이 없었다.

`04_rag_agent/phase5~8_*.py`는 Stage4 RAG 트랙 소재라 이번 archive 대상에서
제외했다(Chemical Selection과 Stage4 RAG 커밋을 섞지 않는다는 원칙).

**정정(2026-08-08 후속 세션)**: 위 판단을 재검토한 결과, 이 스크립트들이 만들어내는
후보 세트(426/259proposed/259_retrieval_aware 등) 자체가 "retrieval 진단으로 selection을
재판정"하는 동일한 문제의 산출물이라 판단해 결국 archive로 옮겼다 —
[`stage4_rag_diagnostic_2026-08-08/`](stage4_rag_diagnostic_2026-08-08/README.md) 참고.

## Archive 대상에서 제외한 것 (의도적으로 남겨둔 것)

- `01_collection/chemical_selection_audit_dataset_2026-08-08.csv`(475행 provenance 감사)와
  `02_classification/provenance_audit.py`: `build_final_selection_audit.py`(최종 판정
  스크립트, archive 밖)가 지금도 직접 읽는 입력 파일/생성 스크립트라서 archive로 옮기면
  최종 감사 CSV를 재현할 수 없게 된다. 그대로 원위치에 남겨두었다.
- `02_classification/section10_baseline.py`: provenance_audit.py와 마찬가지로
  현재 §10 baseline 수치의 유일한 재현 가능 소스라 원위치에 남겨두었다.
