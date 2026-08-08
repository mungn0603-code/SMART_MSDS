# PHASE 3 — 375종 재평가: Marginal Coverage / Leave-One-Out

**작성일**: 2026-08-08
**실행 스크립트**: [`02_classification/phase3_reassessment.py`](../02_classification/phase3_reassessment.py) (읽기 전용, DB/CSV 미변경)

**원칙 확인**: `undergrad_target_chemicals.csv`는 이번 PHASE 3에서도 수정하지 않았다. 아래 REMOVE_CANDIDATE/MERGE_CANDIDATE는 "제거/통합 후보로 확정"이지 "제거 완료"가 아니다 — 실제 반영은 사용자 승인 후 별도 단계.

## 0. 방법론 — 왜 90,525쌍을 375번 다시 계산하지 않는가

그룹매트릭스 판정(`compatibility_pairs`)의 category는 `(group_a_id, group_b_id)` 쌍에만 의존하고 그 그룹을 대표하는 물질이 누구인지와 무관하다. 따라서 물질 X를 제거해도 X의 true_groups 각각에 **다른 대표물질이 남아있다면**, X가 관여하던 모든 그룹쌍 판정은 그 다른 대표물질로 100% 동일하게 재현된다 — 이는 근사가 아니라 테이블 구조(그룹쌍 단위 저장)에서 나오는 정확한 결론이다. 그 결과:

- **Group marginal contribution ≡ Risk-pair marginal contribution ≡ Scarce-group contribution**: 셋 다 "X가 자신의 true_groups 중 최소 하나에서 현재 유일한 대표물질인가"라는 동일한 신호로 계산된다(신호 이름은 `sole_group_of`).
- **§10 relationship marginal contribution**은 물질별 실제 MSDS 텍스트라 위 그룹 구조와 독립적이다 — `section10_has_real_evidence`/`section10_categories`로 별도 계산.
- **Redundancy**는 `true_cameo_groups` 조합(signature)이 완전히 같은 다른 물질이 있는지로 판정(PHASE 2에서 검증한 것과 동일 로직).

## 1. 의사결정 규칙 (재현 가능, 코드에 그대로 구현됨)

우선순위 순서대로 첫 번째 해당 규칙 적용:

1. true_groups 중 하나라도 현재 유일 대표물질(`group_member_count==1`) → **KEEP_COVERAGE**
2. true_groups 조합이 dataset 내 유일(동일 조합 물질 없음):
   - 자기 §10에 실질 근거 있음 → **KEEP_EMPIRICAL**
   - 없음(자료없음뿐) → **REVIEW**
3. true_groups 조합이 다른 물질과 동일(cluster 크기 ≥2), cluster를 (§10 실질근거 유무, 카테고리 수, CAS) 순으로 랭킹:
   - 1순위 + 실질근거 있음 → **KEEP_EMPIRICAL**
   - 1순위 + 실질근거 없음 → **REVIEW**(cluster 전체가 근거 빈약)
   - 1순위 아님 + 실질근거 있음 → **MERGE_CANDIDATE**
   - 1순위 아님 + 실질근거 없음 → **REMOVE_CANDIDATE**

**평가셋 사용 금지 확인**: 위 규칙 어디에도 `gold_*.jsonl` 등장 여부가 없다. 각 물질에 `in_eval_testset_FYI_NOT_USED_IN_DECISION` 필드로 등장 여부를 기록은 하되(투명성), 판정에는 사용하지 않았다 — PHASE 1에서 발견한 Wave1→평가셋→"평가셋 등장"→Wave1 정당화 순환을 Phase 3에서도 재차 차단한다.

## 2. 재평가 대상 수 확인: 375종 (기대값 375)

## 3. recommendation 분포

| recommendation | 종수 | 의미 |
|---|---:|---|
| KEEP_COVERAGE | 0 | 그룹 내 유일 대표물질 — 제거 시 그룹 자체가 0종 |
| KEEP_EMPIRICAL | 117 | 자기 §10 실질근거로 뒷받침되는 (준)유일 조합 |
| REVIEW | 62 | 근거는 약하나 자동판정으로 제거를 단정할 수 없음 |
| MERGE_CANDIDATE | 118 | 실질근거는 있으나 더 나은 대표물질과 중복 — 통합 검토 |
| REMOVE_CANDIDATE | 78 | 중복 + 실질근거 없음 — 제거해도 coverage 손실 없음 |
| **합계** | **375** | |

**KEEP_COVERAGE가 0건인 이유(버그 아님)**: PHASE 1에서 이미 "true 그룹 중 하나라도 대표물질 ≤2종"인 물질 51종 중 17종을 `KEEP_COVERAGE`로 선분류했다. 그 결과 이번 375종은 **전부 소속 true_groups 전체가 이미 다른 대표물질로 3종 이상 채워진 물질들**이다 — 그래서 group/risk-pair marginal contribution 축(`sole_group_of`)에서는 375종 전원이 0을 받는다(수학적으로 당연한 결과, 재확인 완료). 즉 이 375종의 존재가치는 **오직 §10 개별 실측 근거**에 달려 있다는 뜻이고, 이번 PHASE 3의 판정이 실질적으로 §10 근거 축 하나에 집중된 것은 의도된 결과다.

## 4. 원 selection_status(PHASE 1) x recommendation(PHASE 3) 교차표

| 원 status | recommendation | 종수 |
|---|---|---:|
| DUPLICATE | KEEP_EMPIRICAL | 9 |
| DUPLICATE | MERGE_CANDIDATE | 74 |
| DUPLICATE | REMOVE_CANDIDATE | 48 |
| REVIEW | KEEP_EMPIRICAL | 55 |
| REVIEW | MERGE_CANDIDATE | 22 |
| REVIEW | REMOVE_CANDIDATE | 10 |
| REVIEW | REVIEW | 30 |
| UNSUPPORTED | KEEP_EMPIRICAL | 53 |
| UNSUPPORTED | MERGE_CANDIDATE | 22 |
| UNSUPPORTED | REMOVE_CANDIDATE | 20 |
| UNSUPPORTED | REVIEW | 32 |

## 5. Wave x recommendation 교차표 (PHASE 3-E)

| wave | recommendation | 종수 |
|---|---|---:|
| wave1 | KEEP_EMPIRICAL | 63 |
| wave1 | MERGE_CANDIDATE | 29 |
| wave1 | REMOVE_CANDIDATE | 23 |
| wave1 | REVIEW | 38 |
| wave2 | KEEP_EMPIRICAL | 54 |
| wave2 | MERGE_CANDIDATE | 89 |
| wave2 | REMOVE_CANDIDATE | 55 |
| wave2 | REVIEW | 24 |

**해석**: wave2(222종) 중 MERGE_CANDIDATE 비율 89/222=40.1%, REMOVE_CANDIDATE 비율 55/222=24.8%인 반면, wave1(153종)은 MERGE 29/153=19.0%, REMOVE 23/153=15.0%로 뚜렷이 낮다. PHASE 1이 지적한 "Wave2 그룹 전체 편입"이 실제로 중복성 높은 물질을 더 많이 만들었다는 가설이 marginal-coverage 분석으로 재확인된다.

## 6. Group 25 / Group 36 처리 확인

375종 중 그룹25(Diazonium Salts) 소속 물질은 0종이다(PHASE 1 감사 시점부터 그룹25 자체가 collected 426종에 미커버 — `chemical_selection_audit_2026-08-08.md` §8 참고). 이번 PHASE 3도 이를 다시 확인만 하고 별도 처리는 하지 않는다 — `DATA_SCARCITY`는 PHASE 2 결론 그대로 유지.
그룹36(Insufficient Information for Classification) 소속으로 375종 중 걸리는 물질이 있는지는 아래 CSV의 `true_cameo_groups` 컬럼에 36이 포함되는지로 확인 가능하다 — 있다면 `EXCLUDED_META_GROUP`으로 별도 표기할 것을 권고하며, 이 그룹은 coverage 계산에서 실질 그룹으로 세지 않는다(PHASE 1/2와 동일 원칙).

## 7. 안전/규제 플래그 확인 (삭제 기준으로 쓰지 않음)

| CAS | 물질명 | safety_flag | recommendation |
|---|---|---|---|
| 1271-28-9 | NICKELOCENE | REVIEWED_H351_KEPT(01_collection/backfill_round3_manual_picks.py) | REVIEW |

**원칙**: 이 프로젝트는 위험성평가가 목적이므로 안전도가 낮다는 이유만으로 REMOVE_CANDIDATE 처리하지 않는다(`docs/decisions.md` §1.2d와 동일 원칙). 위 표는 `safety_flag`/`selection_status`를 분리해 관리하는 것을 보여주는 예시일 뿐, 이번 375종 중 안전성만을 이유로 제거 후보가 된 물질은 없다.

참고(정보용, 판정에 미사용): 375종 중 평가셋(`gold_*.jsonl`)에 등장하는 물질 153종.

## 8. 대표 사례 (spot-check)

**KEEP_EMPIRICAL 예시**
- `100-21-0` TEREPHTHALIC ACID (wave1) — true_groups 조합 (2, 35)이 dataset 내 유일(중복 없음) + 자기 §10 실질근거(['combustible_reducing', 'water'])
- `104-01-8` 4-METHOXYPHENYLACETIC ACID (wave1) — true_groups 조합 (2, 28)이 dataset 내 유일(중복 없음) + 자기 §10 실질근거(['combustible_reducing', 'water'])
- `107-94-8` 3-CHLOROPROPIONIC ACID (wave1) — true_groups 조합 (2, 31)이 dataset 내 유일(중복 없음) + 자기 §10 실질근거(['combustible_reducing', 'water'])

**MERGE_CANDIDATE 예시**
- `10025-91-9` ANTIMONY TRICHLORIDE (wave1) — 동일 true_groups=(3, 32, 50) 물질 4종 중 3순위 — 자기 §10 근거는 있으나 상위 대표물질과 중복, 통합 검토 대상
- `10026-11-6` ZIRCONIUM TETRACHLORIDE (wave1) — 동일 true_groups=(3,) 물질 2종 중 2순위 — 자기 §10 근거는 있으나 상위 대표물질과 중복, 통합 검토 대상
- `42615-29-2` PHENYLSULPHONIC ACID (wave1) — 동일 true_groups=(4,) 물질 6종 중 4순위 — 자기 §10 근거는 있으나 상위 대표물질과 중복, 통합 검토 대상

**REMOVE_CANDIDATE 예시**
- `100-07-2` 4-METHOXYBENZOYL CHLORIDE (wave1) — 동일 true_groups=(7,) 물질 2종 중 2순위 + §10 실질근거 없음 — 제거해도 coverage 손실 없음
- `3486-35-9` ZINC CARBONATE (wave1) — 동일 true_groups=(21,) 물질 4종 중 4순위 + §10 실질근거 없음 — 제거해도 coverage 손실 없음
- `10031-87-5` 2-ETHYLBUTYL ACETATE (wave1) — 동일 true_groups=(27,) 물질 5종 중 3순위 + §10 실질근거 없음 — 제거해도 coverage 손실 없음

**REVIEW 예시**
- `103-75-3` ETHOXYDIHYDROPYRAN (wave1) — true_groups 조합 (1, 28, 34)은 유일하나 §10 실질근거 없음(자료없음뿐) — group은 scarce 아님, 자동판정 보류
- `1271-19-8` TITANOCENE DICHLORIDE (wave1) — true_groups 조합 (3, 35, 49)은 유일하나 §10 실질근거 없음(자료없음뿐) — group은 scarce 아님, 자동판정 보류
- `10265-92-6` METHAMIDOPHOS (wave1) — true_groups 조합 (5, 27)은 유일하나 §10 실질근거 없음(자료없음뿐) — group은 scarce 아님, 자동판정 보류

## 9. 다음 단계(PHASE 4) 권고

- **최종 후보군 구성 공식(권고, 개수 미확정)**: 기존 KEEP(PHASE1 51종) + PHASE3 KEEP_EMPIRICAL(117종) + PHASE2 ADD(16종, 그룹36 2종 제외) − PHASE3 REMOVE_CANDIDATE(78종). MERGE_CANDIDATE(118종)와 REVIEW(62종)는 자동 반영하지 않고 사람 검토를 거칠 것.
- **MERGE_CANDIDATE 처리 방안**: 같은 signature cluster 내 1순위(KEEP_EMPIRICAL로 이미 남은 대표물질)와 병기해 "대표물질 + 참고물질" 구조로 유지하거나, coverage 목적상 정말 필요 없다면 REMOVE로 재분류 — 이번 단계는 후보만 만들고 결정하지 않는다.
- **독립 평가셋 필요성**: 필요하다고 판단한다. 현재 `gold_*.jsonl`은 Wave1(197종) 파생이라 Wave2(223종, 이번 재평가에서 상대적으로 redundancy가 높게 나온 축)를 전혀 검증하지 못한다(PHASE 1 §7). 최소 요구사항 제안:
  1. Wave2 KEEP_EMPIRICAL로 남은 물질(위 표, 실질 §10 근거 보유)을 우선 포함
  2. Wave1 파생 오염 방지 — 새 쌍 추출 시 Wave1/Wave2 구분 없이 전체 collected 기준 재추출
  3. 실제 §10 원문 기반 정답(gold_section)을 그대로 재사용(청킹/근거등급 로직 변경 없음)
  4. scarce group(그룹25 제외 13개) 및 PHASE2 ADD 16종을 최소 1회 이상 질의에 포함
  5. Compatible(무해) 판정 쌍을 hard-negative로 포함해 Abstain/Compatible 구분 능력 검증
  이번 PHASE 3에서 실제 평가셋을 생성하지는 않았다 — 설계안만 제시(요청사항 그대로).
