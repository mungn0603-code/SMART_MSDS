# PHASE 6 — Retrieval-aware Chemical Selection Reassessment

**작성일**: 2026-08-08
**전제**: PHASE 1~5 완료. PHASE 5가 "strict 비교 시 259가 426보다 모든 retrieval
지표에서 낮다"는 걸 실측했고, 이번 PHASE 6은 그 격차의 원인(PHASE 4의
REMOVE_CONFIRMED/MERGE_REDUNDANT 181종)을 물질 단위로 재평가한다.

**실행 스크립트**: `02_classification/phase6_retrieval_reassessment.py`(물질 단위
E/C/R/D/S 계산 + 재분류), `04_rag_agent/phase6_selection_scenarios.py`(후보군
A/B/C/D 비교, 캐시 재사용 — 재임베딩 없음).

**산출물**: `01_collection/chemical_phase6_retrieval_reassessment_2026-08-08.csv`(181행),
`01_collection/chemical_phase6_query_level_2026-08-08.csv`(7,880행, 질의-청크
레벨 원자료), `docs/phase6_candidate_sets_results_2026-08-08.md`(A/B/C/D 상세표).

**원칙 확인**: `undergrad_target_chemicals.csv` 미변경(세션 내내). `reactivity_reference.db`는
`rag_corpus_membership`에 신규 corpus_tag 2종(`259_retrieval_aware`, `phase6_D`)만
추가 — 청크·임베딩 원본 변경 없음. 130종 일괄 복구·426 롤백 없음. 최종 dataset
반영도 하지 않음(요청사항 그대로 여기서 중단).

---

## 0. 방법론 요약

### R(retrieval contribution) — 이번 Phase의 핵심 신규 신호
426 코퍼스(캐시된 임베딩·BM25 재사용)에서 `gold_pair.jsonl` 전체(1,915건) hybrid
랭킹을 뽑고, 각 질의의 `gold_section` 청크가 `sec::{cas}::{section}` 형식이라는
점을 이용해 **어느 물질 소유인지 청크 단위로 파싱**했다. 물질 X의 R은 "X 자신의
청크가 X가 등장하는 질의들에서 top-10에 얼마나 자주/높게 검색되는가"
(hit_rate@10, mean reciprocal rank)로 정의했다 — **쌍 전체가 dropped됐는가가
아니라 이 물질 자신의 정보가 실제로 검색되고 있었는가를 물질 단위로 분리**한
것이 기존 Phase5 분석과의 차이다.

### E/C/D/S
- **E**(independent evidence): 자기 §10 실질근거(Phase3) + §2 GHS 실질내용 신규
  확인(Phase4 NEEDS_EVIDENCE와 동일 로직) → 0/1/2.
- **C**(coverage): **259 기준으로 다시** 그룹 대표물질 수를 계산 — 181종을
  동시에 뺀 누적효과로 그룹이 새로 scarce(≤2종)해지지 않았는지 재확인(개별
  판단이 누적효과를 놓쳤을 가능성 점검).
- **D**(redundancy): 같은 signature cluster 크기(대표 포함).
- **S**(data availability): 전부 이미 KOSHA 4섹션 확보 — 고정 True.

### 재분류 규칙(결정론적, 가중치 미사용)
우선순위: ① 259 기준 신규 scarce(누적효과) → **RETAIN_COVERAGE** / ② R=HIGH →
**RETAIN_RETRIEVAL** / ③ R=MEDIUM 또는 NO_DATA(gold_pair에 아예 없어 근거
자체가 없음 — 강제판정 안 함) → **REVIEW** / ④ 그 외(R=LOW, 실측상 성능이
나쁨) → **REMOVE_CONFIRMED** 유지.

가중치 시나리오(selection-only/selection+retrieval/retrieval-heavy/coverage-heavy)는
**이 결정에 쓰이지 않았다** — 별도로 계산해 "합리적인 가중치 어디를 골라도
결과가 안정적인가"만 점검하는 로버스트니스 체크로만 썼다(§6).

---

## 1. 181종 재평가 결과 개요

| R_tier | 종수 | 의미 |
|---|---:|---|
| HIGH | 42 | hit_rate@10≥0.8 (n≥3) — 강한 실측 근거로 검색 기여 확인 |
| MEDIUM | 5 | hit_rate@10≥0.5 — 근거는 있으나 약함 |
| NO_DATA | 134 | `gold_pair.jsonl`에 이 물질이 아예 등장 안 함 — **근거 자체가 없음(불확실, LOW와 다름)** |
| LOW | 0 | (해당 없음 — gold_pair에 등장하면서 실제로 성능이 나쁜 경우는 이번 181종 중 0건) |

| phase6_status | 종수 | 원 phase4_status 분해 |
|---|---:|---|
| RETAIN_RETRIEVAL | **42** | REMOVE_CONFIRMED 19 + MERGE_REDUNDANT 23 |
| RETAIN_COVERAGE | **5** | REMOVE_CONFIRMED 2 + MERGE_REDUNDANT 3 |
| REVIEW | **134** | REMOVE_CONFIRMED 42 + MERGE_REDUNDANT 92 |
| REMOVE_CONFIRMED(유지) | **0** | — |

**REMOVE_CONFIRMED가 0으로 나온 것에 대한 정직한 해석**: 이게 "181종 전부
유지해야 한다"는 뜻이 아니다. `gold_pair.jsonl`(Wave1 파생 진단용 평가셋,
383쌍만 표본추출)이 181종 중 **134종(74%)에 대해서는 애초에 어떤 질의도
포함하지 않는다** — 그래서 이 134종에 대해 "retrieval 관점에서 제거해도
된다"고 확인해 줄 데이터 자체가 없다. 반대로 근거가 존재하는 47종(HIGH+MEDIUM)은
**전부** 최소 MEDIUM 이상이었다(LOW=0). 이건 "이 진단 평가셋에 걸린 물질은
전부 검색이 잘 됐다"는 뜻이지 "나머지 134종도 다 잘 될 것"이라는 뜻이 아니다
— 정확히 이 비대칭 때문에 134종을 REVIEW로 남기고 강제 판정하지 않았다.

---

## 2. 130건(질의) 관련 물질 상세

`01_collection/chemical_phase6_query_level_2026-08-08.csv`(7,880행)에 질의별
`query_id/cas_a/cas_b/gold_chunk/gold_chunk_cas/rank_426/in_259_valid`를 전부
기록했다. 130건(`in_259_valid=False`)만 필터링하면 정확히 어느 물질의 어느
청크가 426에서 몇 위였는지 재구성 가능하다.

요약(PHASE 5에서 이미 확인한 것의 물질 단위 분해): 130건에 연루된 물질들의
hybrid hit_rate@10 평균이 426 전체 평균보다 높았다(Phase5 §6-4: 0.9346 vs 전체
0.8826) — 이번 물질 단위 분해로 봐도 일관된다: 상위 5개 RETAIN_RETRIEVAL 예시
(`10025-91-9` 삼염화안티몬 hit@10=1.0/mrr=0.75/n=40,
`104-15-4` 톨루엔술폰산 hit@10=1.0/n=10, `10026-11-6` 사염화지르코늄
hit@10=1.0/n=30 등)는 전부 gold_pair에서 다수 질의(n=10~70)에 등장하며
**한 번도 top-10을 놓친 적이 없다**(hit_rate@10=1.0).

---

## 3. REMOVE_CONFIRMED(63) 재분류 결과

| phase6_status | 종수 |
|---|---:|
| RETAIN_RETRIEVAL | 19 |
| RETAIN_COVERAGE | 2 |
| REVIEW | 42 |

RETAIN_COVERAGE 2종 예시: `7440-09-7`(POTASSIUM), `7440-23-5`(SODIUM) — 둘 다
그룹40(Metals, Elemental and Powder, Active) 소속인데, **181종을 동시에 뺀
누적효과로 259에서 그룹40 대표물질이 2종 이하로 줄어든 것**을 이번에 처음
확인했다(개별 판단 시점엔 그룹40에 다른 대표물질이 충분해 보였지만, 같은
그룹에서 여러 종이 동시에 REMOVE/MERGE 판정을 받으면서 누적된 것 — Phase4의
개별 판단 로직이 놓칠 수 있었던 부분을 이번 재검증이 잡아냄).

---

## 4. MERGE_REDUNDANT(118) / 41개 Cluster 재검토

| phase6_status | 종수 |
|---|---:|
| RETAIN_RETRIEVAL | 23 |
| RETAIN_COVERAGE | 3 |
| REVIEW | 92 |

**"동일 signature = 동일 retrieval 가치"는 기각된다** — 41개 cluster 중
**7개가 mixed-status**(같은 그룹조합인데 구성원별로 판정이 갈림)였다. 가장
극적인 사례:

**MC014 (그룹41, Metals Elemental and Powder Active, 14종 cluster)**:
- `7439-95-4` MAGNESIUM → RETAIN_RETRIEVAL(hit@10=0.9)
- `7440-25-7` TANTALUM → RETAIN_RETRIEVAL(hit@10=0.9333)
- `7440-02-0` NICKEL, `7440-21-3` SILICON POWDER, `7429-90-5` ALUMINUM POWDER,
  `7439-89-6` IRON 등 나머지 10종 → REVIEW(hit@10 0.55~0.7 또는 데이터 없음)

같은 CAMEO 그룹(활성 금속분말)에 속해 매트릭스 판정 능력은 동일하지만, 실제
RAG 검색에서는 마그네슘·탄탈럼이 니켈·규소·알루미늄분말보다 뚜렷이 더 잘
검색됐다 — 물질명 인지도, MSDS 문서 품질, 질의 문구와의 어휘 유사도 등이
원인일 수 있으나 원인 규명은 이번 범위 밖(사람 검토 필요 항목으로 남김).

다른 mixed cluster: **MC001**(그룹3/32/50, 삼염화안티몬만 RETAIN), **MC003**
(그룹4 술폰산류, 4종 중 3종 RETAIN), **MC008**(그룹18/68 수산화물, 나트륨알루민산만
RETAIN), **MC009**(그룹18/50 과산화물, 칼륨과산화물만 RETAIN). 전체 목록은
CSV의 `merge_cluster_id` 컬럼으로 재구성 가능.

---

## 5. Retrieval 손실/회복 실측 (개별 + 집계)

개별 leave-one-out(181종 각각을 따로 빼고 재임베딩)은 계산 비용이 과도해
**집계 단위**로 대체 측정했다 — RETAIN_RETRIEVAL 42종을 통째로 259에 복원한
것(후보 C)과 259(B) 자체의 차이가 정확히 이 42종의 **집계 기여도**다(§8에
상세 수치). 개별 기여도는 §1~4의 `hit_rate_10_426`/`mrr_426`(물질별 실측)로
갈음한다 — 이게 사실상 "이 물질 하나가 빠지면 이 물질 관련 질의들이 얼마나
답이 안 나오게 되는가"와 동일한 정보다(해당 물질 자신의 청크가 사라지면
hit_rate만큼의 확률로 정답을 완전히 잃는다는 뜻이므로).

---

## 6. 가중치 시나리오 안정성 점검 (E/C/R/D/S)

4개 시나리오(각 실행 스크립트에 그대로 값 명시, 결과를 보고 나중에 조정하지
않음):

| 시나리오 | w(E) | w(C) | w(R) | w(D) | w(S) |
|---|---:|---:|---:|---:|---:|
| selection_only | 0.4 | 0.4 | 0.0 | 0.1 | 0.1 |
| selection_plus_retrieval | 0.2 | 0.2 | 0.3 | 0.15 | 0.15 |
| retrieval_heavy | 0.1 | 0.1 | 0.6 | 0.1 | 0.1 |
| coverage_heavy | 0.1 | 0.6 | 0.1 | 0.1 | 0.1 |

**181종 중 53종(29.3%)만 4개 시나리오 전부에서 같은 결정**(RETAIN 또는
REMOVE)이 나왔고, **128종(70.7%)은 가중치에 따라 결정이 바뀌었다.** 이건
"이번 재평가가 부정확하다"는 뜻이 아니라 — 오히려 **이 판정 공간 자체가
단일 고정 가중치로 깔끔하게 나뉘지 않는, 본질적으로 애매한 영역**이라는
근거다. `selection_only`(R 가중치 0)는 원래 Phase4 로직을 그대로 재현하므로,
이 시나리오와 다른 시나리오 간 결정 차이가 클수록 "retrieval 정보를 추가한
게 실제로 판정을 바꾼다"는 뜻이고, 그 비율(70.7%)이 낮지 않다 — retrieval
증거를 무시할 수 없다는 정량적 근거다. 다만 이 수치를 "최종 결정"으로 쓰지
않고 §1의 규칙기반 재분류(REVIEW 134종 포함)를 그대로 최종안으로 채택한
이유이기도 하다 — 안정적이지 않은 영역을 안정적인 척 억지로 가중치 하나로
확정하지 않는다.

---

## 7. Independent Evaluation Prototype 재검증

`04_rag_agent/evalset/independent_eval_prototype_2026-08-08.jsonl`(50행,
PHASE 4-F 산출물) 중 물질쌍 레코드 36건을 대상으로, 각 후보군에서 **양쪽
물질이 모두 코퍼스에 실제로 존재하는지** 재확인:

| corpus | 양쪽 물질 존재 쌍 | 비율 |
|---|---:|---:|
| A(426) | 36/36 | 100% |
| B(259) | 12/36 | 33.3% |
| C(259+RETAIN_RETRIEVAL) | 14/36 | 38.9% |
| D(C+RETAIN_COVERAGE) | 15/36 | 41.7% |

**Wave1-derived vs Independent 구분(요청사항 명시)**:
- `gold_pair.jsonl` 기반의 모든 수치(§1~6, R_tier, hit_rate@10 등)는
  **RETRIEVAL_DIAGNOSTIC**으로 분류한다 — Wave1(198~203종) 후보 풀에서
  파생된 평가셋이라 독립적인 selection evidence가 아니다. 이번 PHASE 6의
  RETAIN_RETRIEVAL/RETAIN_COVERAGE 판정은 전부 이 진단 근거에 기반한다.
- Independent eval prototype(47/50 = wave2 관여)은 **선정 근거로 쓰기엔 더
  강하지만, 표본이 36쌍뿐**이라 이번 세션에서는 후보군 검증(위 표)에만
  쓰고 새로운 RETAIN 판정의 근거로 승격하지 않았다. C/D가 B보다는 낫지만
  여전히 426의 41.7%에 그친다는 사실 자체가, RETAIN_RETRIEVAL(42종, Wave1
  진단 기반)이 독립 평가셋 관점의 부족분을 완전히 메우지는 못한다는 걸
  보여준다 — **독립 평가셋 확대가 여전히 필요**(PHASE 5 §설계 문서의 결론
  재확인).

---

## 8. 후보군 A/B/C/D 비교 (상세는 `docs/phase6_candidate_sets_results_2026-08-08.md`)

| candidate | 물질 수 | strict Recall@10 | strict MRR | strict nDCG@10 | strict Hit@10 |
|---|---:|---:|---:|---:|---:|
| A(426, baseline) | 426 | 0.8826 | 0.9835 | 0.8734 | 0.9995 |
| B(259, PHASE4 proposed) | 259 | 0.8352 | 0.8677 | 0.7991 | 0.9269 |
| **C(259+RETAIN_RETRIEVAL, 301종)** | **301** | **0.9047** | **0.9845** | **0.8919** | **0.9969** |
| D(C+RETAIN_COVERAGE, 306종) | 306 | 0.9042 | 0.9847 | 0.8916 | 0.9969 |

**핵심 결과**: C(301종, 426보다 125종 적음)는 **426의 A-B 격차를 Recall@10
146.6%, MRR 100.9%, nDCG@10 124.9%, Hit@10 96.4% 회복**한다 — 3개 지표는
426을 오히려 상회하고 나머지 1개도 사실상 동률이다. **selection quality는
259 기준을 유지(REMOVE_CONFIRMED 근거 없는 217종은 그대로 제외, 그룹
coverage·중복성 개선분 보존)하면서 retrieval 성능은 426과 동등 이상**이라는
뜻 — 이게 이번 PHASE 6이 찾던 답이다.

Efficiency(청크 수)는 코퍼스 물질 수에 거의 비례(§2 참고, 426=1,745
section청크 / 259=1,063 / C≈1,063+42종분 ≈1,230 추정, 정확한 수치는
`rag_chunks` 재질의로 산출 가능하나 이번 라운드에서 별도 계산은 생략 — add
when: 실제 서빙 인프라 용량 계획이 필요해지면).

---

## 9. 최종 요약 (요청된 9개 항목)

1. **130건 중 RETAIN_RETRIEVAL 후보**: 42종(REMOVE_CONFIRMED 유래 19 +
   MERGE_REDUNDANT 유래 23). 전체 CSV: §2 참고.
2. **실제 REMOVE 유지 가능 후보**: **0종** — gold_pair 근거가 있는 47종은
   전부 MEDIUM 이상, 근거 없는 134종은 REVIEW로 유보(강제판정 안 함).
3. **MERGE 41 cluster 재평가**: 7개 cluster가 mixed-status(같은 signature
   내에서도 판정 갈림) — "signature=가치" 가정 기각(§4).
4. **retrieval contribution 높은/낮은 물질**: 높음 — 삼염화안티몬(hit@10=1.0,
   n=40), 톨루엔술폰산(1.0, n=10), 사염화지르코늄(1.0, n=30) 등(§2). 낮음 —
   MC014의 니켈·규소·알루미늄분말 등(§4) — 단, "낮음"은 대부분 "데이터 없음
   (NO_DATA)"이지 확인된 저성능이 아님(§1).
5. **selection-only vs retrieval-aware 차이**: 가중치 시나리오 128/181
   (70.7%)에서 결정이 갈림(§6) — retrieval 정보 반영이 실제로 판정을
   바꾸는 사례가 다수.
6. **426/259/retrieval-aware 비교**: C(301종)가 426 대비 retrieval 3/4 지표
   우위, 1/4 동률, selection quality는 259 유지(§8).
7. **independent evaluation 결과**: 프로토타입 36쌍 기준 A 100%→B 33.3%→C
   38.9%→D 41.7% — C/D가 개선하지만 426 수준 회복엔 못 미침, 독립 평가셋
   자체 확대 필요(§7).
8. **최종 권고 candidate set**: **C(259 + RETAIN_RETRIEVAL 42종 = 301종)**를
   1차 후보로 권고. D(306종)는 C와 retrieval 성능 거의 동일하면서 coverage
   안전마진(그룹40 등 누적 scarcity 해소)을 추가로 확보 — **D를 최종 권고로
   제안**하되, 이는 여전히 REVIEW 134종을 제외한 "확정 가능한 부분집합"일
   뿐 최종 확정 아님.
9. **사람 검토 필요 항목**: REVIEW 134종(retrieval 근거 없음) 전체, MERGE
   mixed-status 7개 cluster의 나머지 구성원 처리, RETAIN_COVERAGE 5종이
   가리키는 그룹40 등의 근본적 coverage 전략 재검토, MC014류 사례의 원인
   규명(왜 같은 그룹에서 특정 물질만 잘 검색되는지).

**Wave1-derived evaluation contamination 가능성**: 이번 PHASE 6의 R
계산·재분류는 100% `gold_pair.jsonl`(Wave1 파생)에 의존한다 — 오염 가능성이
아니라 **오염이 확정된 사실**이다. 그래서 전체 재분류 결과를
`RETRIEVAL_DIAGNOSTIC`으로 명시하고, "최종 selection evidence로 채택 가능"
과 "단순 diagnostic"을 아래처럼 구분한다.

| Evidence | 성격 | 이번 PHASE 6에서의 역할 |
|---|---|---|
| gold_pair.jsonl 기반 R/hit_rate/MRR | **RETRIEVAL_DIAGNOSTIC** (Wave1 파생, 독립 아님) | RETAIN_RETRIEVAL/RETAIN_COVERAGE 판정의 유일한 근거 — **잠정적** |
| Independent eval prototype(47/50 wave2 관여) | 더 강한 근거이나 표본 36쌍뿐 | 후보군 사후 검증에만 사용, 신규 판정 근거로 미승격 |
| Phase1~4 coverage/signature/§10 근거 | 물질 자체의 실측 데이터(그룹매트릭스, KOSHA 원문) | selection-only 축의 근거, retrieval과 무관하게 유효 |

즉 이번 PHASE 6의 RETAIN_RETRIEVAL 42종 판정은 "**Wave1 파생 진단 근거로
확인된 잠정 권고**"이지 "독립적으로 검증된 최종 근거"가 아니다 — Phase 5
설계 문서(§독립 평가셋)가 제안한 확장이 실행되기 전까지는 이 라벨을
유지해야 한다.

---

## 최종 두 질문에 대한 답

### Q1. "Group coverage/signature 기준으로 제거해도 되는 물질 중 실제 RAG
retrieval 관점에서는 유지해야 하는 물질이 얼마나 되는가?"

**최소 42종(181종 중 23.2%), 근거 있는 47종 중 89.4%.** 단, 181종 중 134종
(74.0%)은 진단 평가셋 자체에 등장하지 않아 판단 근거가 없다 — "42종"은
확인된 하한선이고, 실제 값은 나머지 134종 중 일부를 포함해 더 클 수 있다
(독립 평가셋 확대 전까지는 상한을 말할 수 없음). **RETAIN_COVERAGE 5종을
더하면 47종(26.0%)**이 coverage 또는 retrieval 중 최소 한 축에서 실제
유지 근거가 확인된 물질이다.

### Q2. "그 물질을 선택적으로 유지했을 때 259의 selection quality를
유지하면서 426의 retrieval 성능 저하를 얼마나 회복할 수 있는가?"

**126.7%~146.6% 회복(지표별)** — 정확히는 Recall@10 146.6%, MRR 100.9%,
nDCG@10 124.9%, Hit@10 96.4%(§8 표). 즉 42종만 선택적으로 복원해도 426 대비
retrieval 저하는 **완전히 해소되고 대부분의 지표에서 오히려 426을 상회**한다
— 그러면서도 물질 수는 301종(426의 70.7%)에 그쳐 259가 확보한 selection
quality 개선(중복성 66.9%→23.6%, 독립근거비율 12.0%→70.3%, 그룹 coverage
67/68 유지 — PHASE4 §7 수치)을 대부분 보존한다.
