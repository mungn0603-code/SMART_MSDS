# 화학물질 선정 기준 최종 재설계 (2026-08-08)

## 0. 배경

Phase 1~8을 거치며 3,386종 후보 → 426종(현재 `rag_corpus_membership` corpus_tag=`426`,
실제 운영 코퍼스)까지 좁혀 왔다. 그 과정에서 CAMEO 그룹 슬롯 배분, HIGH/MED/LOW 티어링,
§10 빈도 기반 무제한 편입, retrieval 성능 기반 삭제, marginal utility 모델,
259/301/354/268 등 여러 개의 "최종" 후보 세트가 DB(`rag_corpus_membership`)에
동시에 남아 있는 상태가 되었다. 이 문서는 그 판단들을 계승하지 않고, 원점에서
**"왜 이 물질을 코퍼스에 넣었는가"에 한 문장으로 답할 수 있는가**만을 기준으로
426종을 재분류한다.

## 1. 프로젝트 최종 목적

> 학부 화학실험 및 위험성평가 RAG에서 실제로 필요한 화학물질을 충분히 포함하면서,
> 선정 이유를 설명할 수 있고, 불필요한 중복 물질을 과도하게 포함하지 않는
> 실용적인 물질 코퍼스를 구축한다.

최적화 대상은 물질 개수가 아니다. 목표는 셋 중 하나로 답할 수 있는 집합이다:
① 학부 실험/교육에 필요한가, ② 위험성평가에 의미가 있는가, ③ 비슷한 역할의
물질을 과도하게 중복 포함하고 있지 않은가.

## 2. 기존 방식의 핵심 문제

실제 코드(`01_collection/build_undergrad_target_list.py`)와 Phase 3~8 산출물을
대조한 결과, 다음이 확인되었다.

1. **그룹 슬롯 배분이 물질 단위 근거를 대체함.** `GROUP_TIER`(68개 그룹을
   HIGH=12슬롯/MED=4슬롯/LOW=2슬롯)로 자동 채운 `pool_supplement`/`pool_topup`이
   426종 중 **141종(33%)**을 차지하는데, 이 물질들의 실제 `selection_reason`은
   `"UNKNOWN(그룹 슬롯 자동 보충 — 물질 단위 개별 선정 근거 없음)"`이다. 그룹에는
   속하지만 그 물질이어야 할 이유는 애초에 기록된 적이 없다.
2. **평가/재평가가 선정을 다시 흔드는 순환 구조.** Phase 6~8은 retrieval
   hit_rate·MRR·`R_tier`·`E_score`·시나리오 가중치(`scenario_selection_only` 등)로
   물질을 다시 KEEP/DROP 판정했고(`chemical_phase6_retrieval_reassessment...csv`),
   Phase 8은 여기에 `dependency_class`(marginal utility) 모델까지 얹었다. 그
   결과 `rag_corpus_membership`에는 `259proposed`, `259_retrieval_aware`,
   `phase6_D`, `phase7_D`, `phase8_E`, `426` 6개의 서로 다른 "최종" 후보 세트가
   동시에 남아, 어느 것도 유효한 기준선이 되지 못했다.
3. **진단자료가 선정근거로 승격됨.** Wave1 파생 gold_pair/평가셋 등장 여부가
   `in_eval_testset`으로 기록되고 이것이 다시 KEEP 판정에 관여했다. 평가셋은
   코퍼스에서 파생된 것이므로 그것으로 코퍼스 자체를 정당화하는 것은 순환 논리다.
4. **목표 물질 수를 먼저 정하고 맞춤.** `TARGET_MIN=380 / TARGET_MAX=420`이
   코드에 상수로 박혀 있었고, 이후 200→259→301→354→426으로 목표가 계속
   바뀌었다. 물질 수가 결과가 아니라 입력이 되어 있었다.

## 3. 최종 선정 원칙

- **선정 판단은 물질 단위로 하고, 근거는 한 문장으로 기술 가능해야 한다.**
- **독립 근거(independent evidence)와 진단자료(diagnostic evidence)를 구분한다.**
  독립 근거만 선정 사유가 될 수 있다.
  - 독립 근거: 커리큘럼 실사용 기록(과목/실험명), KOSHA MSDS §10에서 실제
    파싱된 반응성 데이터, CAMEO 그룹 소속(구조적 사실).
  - 진단자료(선정 근거로 쓰지 않음): retrieval 성능 지표, 평가셋 등장 여부,
    marginal utility/dependency 점수, 가중치 시나리오 결과.
- **CAMEO 그룹 커버리지는 보조 신호다.** 68개 그룹을 강제로 채우지 않으며,
  그룹 자체가 희소한 경우(예: Group 25) 커버 실패로 취급하지 않는다.
- **중복 제거는 보수적으로만 한다.** 자동 삭제는 하지 않으며, "동일 CAMEO
  그룹조합 + 자체 근거 없음 + 대체 가능한 대표물질 존재"가 모두 성립할 때만
  검토 대상으로 표시한다.
- **물질 수는 결과값이다.** 사전에 정한 목표 개수는 없다.

## 4. 선정 분류 (4개 범주)

| 분류 | 정의 | 판정 규칙(이 재설계에서 적용) |
|---|---|---|
| **MANDATORY** | 실제 학부 실험/커리큘럼에서 명확히 필요 | `selection_source == curriculum` (과목·실험명이 직접 기록된 30종) |
| **HAZARD-RELEVANT** | 위험성평가 관점에서 의미가 명확 | KOSHA MSDS §10에서 실제로 파싱된 반응성 카테고리 존재(`section10_categories not in {"", "no_data"}`) |
| **REPRESENTATIVE** | 특정 화학적 역할/반응군의 대표물질 | 소속 CAMEO 그룹이 426종 내에서 회소(그룹 내 확보물질 ≤2종)하고 위 두 근거가 없는 경우 |
| **UNJUSTIFIED** | 현재 근거로는 포함 이유를 설명하기 어려움 | 위 세 조건에 모두 해당하지 않음. **자동 삭제 아님** — "근거 부족" 상태 표시 |

우선순위는 MANDATORY → HAZARD-RELEVANT → REPRESENTATIVE → UNJUSTIFIED 순으로
적용하고(위 순서로 첫 매치), 물질마다 하나의 결정적 사유만 남긴다.

## 5. 중복 제거 원칙 (보수적)

UNJUSTIFIED로 분류된 물질 중, 다음이 모두 성립할 때만 "중복 검토
(REMOVE/MERGE 후보)"로 표시한다.

- 자체 §10 근거·커리큘럼 근거 없음 (UNJUSTIFIED 조건)
- 동일한 CAMEO 그룹조합(signature)을 가진 다른 물질이 426종 내에 존재함
- 그 그룹조합이 회소 그룹이 아님(다른 대표물질로 이미 대체 가능)

이 조건을 만족하지 않는 UNJUSTIFIED 물질(그룹조합 자체는 유일하지만 근거가
아직 확인 안 된 경우)은 "근거 부족/검토"로만 표시하고 삭제 후보로 올리지
않는다.

## 6. CAMEO 그룹 커버리지의 역할

68개 그룹 중 실질 화학물질 범주가 아닌 Group 36(Insufficient Information)을
제외한 67개를 기준으로, 426종은 **66/67 그룹을 커버**한다. 미커버는
**Group 25 (Diazonium Salts)** 1개뿐이며, 이는 원천 데이터(CAMEO/KOSHA MSDS)
자체의 희소성 때문으로 확인된다 — 선정 실패가 아니라 데이터셋의 구조적 한계로
기록하고 종료한다. 회소 그룹(그룹 내 확보물질 ≤2종)은 13개이며, 이 그룹들의
대표물질은 REPRESENTATIVE 근거로 유지를 권고한다.

## 7. Retrieval의 역할

Retrieval(검색 성능) 평가는 선정 기준이 아니라 **선정 이후의 검증 단계**로
분리한다.

```
물질 선정(본 문서 기준) → 코퍼스 구축 → Retrieval 평가
  → 검색 성능 확인 → (부족 영역 발견 시) 후보 보완 검토
```

Wave1 파생 gold_pair 및 기존 retrieval 평가 결과(Phase 6~7 산출물)는 진단
자료로만 사용하며, 이번 재분류의 어떤 결정에도 입력으로 쓰지 않았다.

## 8. 산출물

1. 본 문서.
2. [`01_collection/chemical_selection_final_audit_2026-08-08.csv`](../01_collection/chemical_selection_final_audit_2026-08-08.csv)
   — 426종 전체에 대해 `cas, chemical_name, cameo_groups, wave, category,
   selection_reason, evidence_source, evidence_strength, decision, review_note`.
   `category`가 4분류, `decision`이 최종 후보군 제안(반드시 유지 / 유지 권고 /
   중복 검토(REMOVE/MERGE 후보) / 근거 부족·검토)이다. 자동 삭제/자동 병합은
   하지 않았다 — 최종 변경은 사용자 승인 후에만 수행한다.

## 9. 참고: 코퍼스 밖 49종

`undergrad_target_chemicals.csv`(현재 475행)에는 위 426종 외에 49종이 더
있으나, KOSHA MSDS 검색에서 확인되지 않아(`collection_status=ABSTAIN_NOT_FOUND`)
`rag_corpus_membership`에 들어간 적이 없다. 이번 재분류의 대상이 아니며,
별도 조치가 필요하면(KOSHA 재검색 등) 후속 작업으로 분리한다.
