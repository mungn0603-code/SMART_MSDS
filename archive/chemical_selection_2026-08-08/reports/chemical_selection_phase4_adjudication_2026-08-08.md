# PHASE 4 — Final Adjudication + Independent Evaluation 설계

**작성일**: 2026-08-08
**전제**: PHASE 1~3 완료 (`chemical_selection_audit_2026-08-08.md`,
`chemical_backfill_audit_2026-08-08.md`, `chemical_selection_phase3_reassessment_2026-08-08.md`)

**실행 스크립트**:
- [`02_classification/phase4_adjudication.py`](../02_classification/phase4_adjudication.py) — A/B/C/D
- [`02_classification/phase4_coverage_and_proposal.py`](../02_classification/phase4_coverage_and_proposal.py) — E/G
- [`04_rag_agent/independent_evalset_prototype.py`](../04_rag_agent/independent_evalset_prototype.py) — F

**산출물**:
- [`01_collection/chemical_phase4_adjudication_2026-08-08.csv`](../01_collection/chemical_phase4_adjudication_2026-08-08.csv)(300행: REMOVE 78 + MERGE 118 + REVIEW 62 + ADD 15 + 정확히는 아래 §0 참고)
- [`01_collection/undergrad_target_chemicals_proposed_final_2026-08-08.csv`](../01_collection/undergrad_target_chemicals_proposed_final_2026-08-08.csv)(259행, **PROPOSED, 미승인**)
- [`docs/independent_evaluation_set_design_2026-08-08.md`](independent_evaluation_set_design_2026-08-08.md)
- [`04_rag_agent/evalset/independent_eval_prototype_2026-08-08.jsonl`](../04_rag_agent/evalset/independent_eval_prototype_2026-08-08.jsonl)(50행)

**원칙 재확인**: `01_collection/undergrad_target_chemicals.csv`는 이번 PHASE 4에서도
전혀 수정하지 않았다(mtime 2026-08-08 09:40:22, 세션 내내 불변). 78개 자동삭제,
118개 자동병합, 16개 ADD 자동편입 전부 수행하지 않았다 — 아래 REMOVE_CONFIRMED /
MERGE_REDUNDANT / ADD_CONFIRMED는 전부 **"확정 근거가 마련된 제안"**이지 "실행 완료"가
아니다.

---

## 0. 데이터 정합성 확인

Phase4 adjudication CSV 총 행수 = REMOVE 78 + MERGE 118 + REVIEW 62 + ADD(중복 CAS
제거 후) 15 = **273행**(요청서의 "16종"은 Phase2 원본 표기, 실제로는 SULFAN BLUE
(129-17-9)가 그룹23/57 두 그룹의 후보로 중복 집계돼 있었음을 이번 단계에서 발견·정정
— 고유 CAS 기준 15종이 맞다, §4 참고).

---

## PHASE 4-A. 78 REMOVE_CANDIDATE Adjudication

**규칙**: 각 물질의 signature cluster에서 rank1(대체 대표물질) 신원을 확인한다.
대체물질이 이미 확정 KEEP(Phase1 51종 또는 Phase3 KEEP_EMPIRICAL)이면 REMOVE_CONFIRMED,
safety_flag가 있으면 KEEP_EXCEPTION, 대체물질조차 근거가 약하면(REVIEW급) REVIEW_REQUIRED.

| 분류 | 종수 |
|---|---:|
| REMOVE_CONFIRMED | **63** |
| KEEP_EXCEPTION | **0**(78종 중 safety_flag 있는 물질 없음 — 니켈로센 등은 REVIEW 62종 쪽에 있어 이 78종과 무관) |
| REVIEW_REQUIRED | **15** |

REVIEW_REQUIRED 15종의 의미: 이들은 신호상 REMOVE_CANDIDATE(중복+무근거)였지만,
"대체 가능"의 실제 근거인 rank1 대표물질 자체도 Phase3에서 REVIEW(근거 빈약)로
남아있다 — 즉 **cluster 전체가 근거 빈약**이라 이 15종만 골라 제거하는 게 정당화되지
않는다(대표물질도 못 미더운데 나머지를 지울 근거는 더 없다). 사람이 cluster 단위로
같이 봐야 한다.

---

## PHASE 4-B. 118 MERGE_CANDIDATE Adjudication → 41개 Cluster

signature(true_cameo_groups 조합)별로 묶으면 **41개 cluster**, 118개 물질 전부 배정.
각 cluster의 representative_cas는 Phase1의 51종 또는 Phase3 KEEP_EMPIRICAL 중
하나(수학적으로 항상 real §10 evidence 보유 — 그렇지 않으면애초에 MERGE_CANDIDATE로
분류되지 않았을 것).

**coverage_preserved**: 그룹/매트릭스 기반 coverage는 대표물질이 남아있는 한
**항상 보존됨**(Phase3에서 증명한 스키마 사실 — `(group_a,group_b)`에만 의존).
다만 이건 "매트릭스 판정 능력"에 한정된 보장이다 — **병합 대상 물질들의 개별
§2·3·9 실측값(분자량·비중·인화점 등 물리화학적 데이터, RAG 코퍼스의 원문 다양성)은
소실된다.** 이건 이번 단계에서 자동으로 결정할 수 없는 트레이드오프이므로
"MERGE_REDUNDANT"라는 이름 자체를 "물질 자체가 무가치"로 오독하지 않도록
`01_collection/chemical_phase4_adjudication_2026-08-08.csv`의 `reason` 컬럼에
매 행마다 이 caveat를 명시했다.

**cluster 크기 분포** (41개 cluster 중 큰 것 6개, CSV `merge_cluster_id` 기준 실측):

| cluster | 그룹조합 | 대표물질(representative_cas) | cluster 총 크기(대표+MERGE) | MERGE 대상 |
|---|---|---|---:|---:|
| MC015 | 50(Oxidizing Agents, Strong) | 20816-12-0 | 20 | **19** |
| MC014 | 41(Metals, Elemental and Powder, Active) | 7440-47-3 | 15 | **14** |
| MC023 | 50+61(Oxidizing Agents, Strong; Salts, Basic) | 14018-95-2 | 11 | 10 |
| MC021 | 42(Metals, Less Reactive agents) | 7439-92-1 | 8 | 7 |
| MC032 | 59+61(Reducing Agents, Weak; Salts, Basic) | 10026-17-2 | 6 | 5 |
| MC003 | 4(Acids, Strong Oxidizing) | 7664-93-9 | 5 | 4 |
| (나머지 35개 cluster) | — | — | 평균 2.5종 | 나머지 59 |

상위 2개 cluster(MC015 산화제, MC014 금속)만으로 118개 MERGE 대상 중 **33개
(28.0%)**를 차지한다 — Wave2가 그룹50/41에 집중 편입한 결과가 그대로 가장 큰
중복 cluster로 나타난 것으로, PHASE 1/3에서 지적한 "그룹 전체 무제한 편입" 문제의
직접적 증거다. 41개 cluster 전체 목록은 CSV의 `merge_cluster_id` 컬럼으로
재구성 가능하다.

---

## PHASE 4-C. 62 REVIEW Adjudication

| 최종 상태 | 종수 | 판정 기준 |
|---|---:|---|
| NEEDS_EVIDENCE | **59** | §10엔 실질 근거 없지만 §2(GHS 분류) 원문에 검토 안 된 실질 내용이 있음 — 추가 조사(사람이 §2/3/9 직접 확인)로 해소 가능성 있음 |
| UNRESOLVED | **3** | §2도 실질 내용 없음(자료없음/공란) — 현재 KOSHA 데이터 전체에서 근거를 찾을 수 없음, 현재 데이터로는 판단 불가 |

REVIEW_REASON 코드(코드에 그대로 기록): `insufficient_section10`(공통) +
`unclear_empirical_relevance`(고유 조합인데 근거 없음) 또는 `unclear_redundancy`
(cluster 전체가 근거 없음). 62종 전부 강제로 KEEP/REMOVE 나누지 않았다 — 요청사항
그대로 "보류" 상태를 유지한다.

---

## PHASE 4-D. Phase2 16(→고유 15) ADD 최종 검토

Phase2의 18개 ADD 행에서 그룹36 2건을 제외하면 16행이었는데, **CAS 기준으로
중복 제거하면 실제로는 15개 고유 후보**였다(SULFAN BLUE 129-17-9가 그룹23/57 두
자리에 중복 집계). 이번 단계에서 이 중복 제거와 함께, ADD 후보끼리도 서로
signature가 겹치는지 재검증했다(Phase2는 기존 426과만 대조했고 ADD 후보끼리는
대조하지 않았었다 — 이번에 발견한 gap).

| 최종 상태 | 종수 | 사례 |
|---|---:|---|
| ADD_CONFIRMED | **14** | — |
| ADD_HOLD | **1** | `102-36-3`(ISOCYANIC ACID, 3,4-DICHLOROPHENYL ESTER)와 `104-12-1`(P-CHLOROPHENYL ISOCYANATE)이 true_groups=(16,37)로 완전히 동일 — Phase2가 놓친 ADD-후보간 중복을 이번에 발견. 어느 쪽을 넣을지는 사람이 선택(둘 다 넣을 필요 없음) |
| ADD_REJECT | **0** | 기존 426과 재중복된 후보 없음(Phase2 검증이 정확했음을 재확인) |

---

## PHASE 4-E. Global Optimization — Before/After

| 지표 | Baseline(426) | Proposed(259) | 비고 |
|---|---:|---:|---|
| 물질 수 | 426 | **259** | −167(−39.2%), 아래 §G 산출식 참고 |
| Chemical group coverage | 67/68 | **67/68** | **불변** — REMOVE/MERGE 대상은 전부 "sole group member 아님"으로 사전 필터링됐으므로 수학적으로 당연 |
| Scarce group(≤2종) 수 | 13 | **9** | ADD_CONFIRMED 14종이 4개 그룹의 scarcity를 해소(Phase2 예측과 정확히 일치) |
| 매트릭스 Incompatible 비율 | 74.76% | **64.97%** | 아래 해석 참고 |
| 매트릭스 Caution 비율 | 16.03% | **21.06%** | 〃 |
| 매트릭스 Compatible 비율 | 9.21% | **13.97%** | 〃 |
| 매트릭스 Abstain 비율 | 0.00% | **0.00%**(재확인) | 그룹 커버리지 불변과 일관 |
| 동일-signature 중복 물질 비율 | 66.9% | **23.6%** | REMOVE/MERGE의 직접 효과 — 43.3%p 감소 |
| §10 water | 58.9%(251/426) | 57.9%(150/259) | |
| §10 combustible/reducing | 47.4%(202/426) | **50.6%**(131/259) | |
| §10 metal | 23.2%(99/426) | **27.8%**(72/259) | |
| §10 no_data(자료없음) | 36.2%(154/426) | 35.9%(93/259) | 근소 개선 |

**매트릭스 Incompatible%가 왜 떨어졌는가(그룹 coverage 불변인데 왜?)**: 그룹
coverage 불변은 "이 그룹조합 관계가 dataset에 여전히 존재하는가"에 대한 보장이지,
"물질 쌍을 무작위로 뽑았을 때 Incompatible이 나올 확률"이 고정된다는 뜻이 아니다.
REMOVE/MERGE로 빠진 181종은 Wave2가 집중 편입한 산화제(그룹50)·물(그룹68) 등
**원래 Incompatible 비율이 극단적으로 높은 대형 그룹**에 몰려 있었다(PHASE1 §3).
그 대형 그룹의 "복제본"들을 정리하니 남은 물질들의 그룹 구성이 더 다양해졌고,
그 결과 쌍의 판정 분포도 Incompatible 편중에서 Caution/Compatible 쪽으로
자연스럽게 분산됐다 — **결함이 아니라 중복 제거의 직접적 부작용(오히려 더
대표성 있는 분포로 재조정된 것)**.

---

## PHASE 4-F. 독립 평가셋

상세 설계는 [`docs/independent_evaluation_set_design_2026-08-08.md`](independent_evaluation_set_design_2026-08-08.md)
참고. 핵심 요약:

- prototype 50행(쌍 49 + Group25 UNAVAILABLE 스텁 1) 생성 완료
- Wave2/reactive_basics 관여 쌍 **47/49(95.9%)** — 기존 gold_pair.jsonl의 Wave2
  커버리지 0%를 직접 해소
- 희소그룹 13/13 전부 최소 1쌍 포함
- hard negative(Compatible 판정) 포함
- **새로 발견한 blocker**: `retrieval_indexed=True`(실제 검색평가 가능) 비율이
  **2/49뿐**. 원인은 `rag_chunks`가 여전히 197종(Wave1)만 담고 있어서다 —
  Wave2는 RAG 파이프라인(`pipeline.py`)이 확장 이후 재실행된 적이 없다. **Phase 5
  착수 전 이 재실행이 반드시 선행돼야** 이번 prototype이 실제 Hit@K/MRR 측정에
  쓰일 수 있다.

---

## PHASE 4-G. Final Candidate Set (Proposed)

```
Baseline 426
  - REMOVE_CONFIRMED   63
  - MERGE_REDUNDANT   118  (대표물질 41종은 이미 KEEP 쪽에 포함되어 있으므로 여기선 비대표 118종만 뺌)
  + ADD_CONFIRMED       14
  --------------------------------
  = Proposed final     259
```

REVIEW_REQUIRED(15) + REVIEW(62, NEEDS_EVIDENCE 59 + UNRESOLVED 3) = 77종은 "제거
확정도, 유지 확정도 아님" 상태라 **보수적으로 유지**해 proposed final에 포함했다
(합계 검산: 51 + 194 + 14 = 259, 194 = 117 KEEP_EMPIRICAL + 15 REVIEW_REQUIRED + 59
NEEDS_EVIDENCE + 3 UNRESOLVED). ADD_HOLD(1)는 미포함(둘 중 하나를 고를 때까지 보류).

산출물: `01_collection/undergrad_target_chemicals_proposed_final_2026-08-08.csv`
(259행, 원본과 동일 스키마 + ADD_CONFIRMED 14종은 `source=phase4_add_confirmed`로
표기).

---

## 최종 보고 (요청된 10개 항목)

**1. REMOVE**
```
REMOVE_CONFIRMED: 63
KEEP_EXCEPTION:    0
REVIEW_REQUIRED:  15
```
주요 사례(CSV 실측): 나트륨(SODIUM, 7440-23-5, wave2) — 그룹(40,) signature의
대표물질 7439-93-2(리튬, PHASE3_KEEP_EMPIRICAL)가 이미 확정 KEEP 상태라
REMOVE_CONFIRMED. 대다수 REMOVE_CONFIRMED 63종이 이런 패턴 — Wave2가 그룹40/41/42/
50/51/58/59/68에 집중 편입한 같은 signature의 금속·산화제 단체들.

**2. MERGE**
```
merge clusters:      41
representatives:      41 (전부 기존 KEEP 51종 또는 Phase3 KEEP_EMPIRICAL 소속)
merged substances:   118
coverage preserved:  그룹/매트릭스 기준 100%(수학적 보장), 개별 물성 데이터는 비보존(사람 검토 필요)
```

**3. REVIEW**
```
resolved:        0 (강제 KEEP/REMOVE 전환 없음 — 요청사항 그대로 보류 유지)
needs_evidence: 59
unresolved:      3
```

**4. ADD**
```
ADD_CONFIRMED: 14
ADD_HOLD:       1  (102-36-3 vs 104-12-1, 상호 중복 발견)
ADD_REJECT:     0
```

**5. 최종 후보군**
```
baseline count:       426
proposed final count: 259
delta:                -167 (-39.2%)
```

**6. Coverage (Before → After)**
```
group coverage:        67/68 -> 67/68 (불변)
§10 coverage:          water 58.9%->57.9%, combustible/reducing 47.4%->50.6%,
                        metal 23.2%->27.8%, no_data 36.2%->35.9%
risk-pair coverage:    Incompatible 74.76%->64.97%, Caution 16.03%->21.06%,
                        Compatible 9.21%->13.97%, Abstain 0%->0%(불변)
scarce-group coverage: <=2종 그룹 13개 -> 9개
```

**7. Quality**
```
independent evidence ratio: (KEEP_MANDATORY+KEEP_COVERAGE+KEEP_EMPIRICAL) / n
  before: 51/426 = 12.0%
  after:  (51+117+14)/259 = 182/259 = 70.3%   ← REVIEW_REQUIRED/REVIEW는 "독립근거
  확인됨"으로 세지 않았으므로 보수적 하한치
unsupported ratio: 127/426(29.8%) -> 0/259(0%, UNSUPPORTED 127종은 전부 REMOVE_CONFIRMED/
  MERGE_REDUNDANT/KEEP_EMPIRICAL/REVIEW 중 하나로 이미 재분류돼 이 라벨 자체가 소멸)
duplicate ratio(동일 signature 공유): 66.9% -> 23.6%
data availability: 변화 없음(전부 이미 KOSHA 4섹션 확보된 물질 + ADD_CONFIRMED 14종도
  Phase2에서 이미 4섹션 확보)
```

**8. Independent Evaluation Set**
- 독립성 검증 방법: Wave2/reactive_basics 관여 여부를 레코드마다 `independence`
  필드로 직접 기록(추정 아님, 소스 wave 라벨 기반 사실 판정)
- query 수: 50(쌍 49 + stub 1)
- Wave2 coverage: 47/49(95.9%)
- risk-pair coverage: Incompatible/Caution/Compatible(hard negative) 3계층
- hard-negative 구성: Compatible 판정 쌍 최대 12개, `difficulty=hard_negative`
- 현재 평가셋과의 차이: 기존 gold_pair.jsonl은 Wave2 CAS를 원리적으로 포함할 수
  없음(rag_chunks 자체에 없음) — 이번 prototype은 그 CAS들을 명시적으로 포함하되,
  실제 검색평가 가능 여부(`retrieval_indexed`)는 2/49뿐이라는 한계도 함께 기록

**9. Unresolved issues (사람 판단 필요)**
- REVIEW_REQUIRED 15종 + REVIEW 62종(NEEDS_EVIDENCE 59 + UNRESOLVED 3) = 77종의
  개별 최종 처분
- MERGE cluster 41개 각각에서 "정말 대표 1종만 남길지, 교육적 다양성을 위해
  일부는 유지할지"(coverage_preserved는 매트릭스 기준일 뿐, RAG 코퍼스 다양성은
  별개 가치판단)
- ADD_HOLD 1건(102-36-3 vs 104-12-1) 중 선택
- `rag_chunks` 재구축(Wave2 포함) 시점과 방법(전량 재실행 vs 증분)
- Group25(Diazonium Salts) 자체를 이 프로젝트 스코프에서 완전히 포기할지, 아니면
  KOSHA 외 별도 소스(PubChem GHS 요약 등)를 트랙으로 열지

**10. Phase 5 권고**
1. **선행조건**: `04_rag_agent/pipeline.py`를 proposed final(259종, 또는 사람
   검토 후 확정된 최종 리스트) 기준으로 재실행 → `rag_chunks` 갱신 → FAISS/BM25
   인덱스 재빌드. 이게 없으면 Wave2/독립 평가셋 어느 것도 실제 Retrieval 지표를
   낼 수 없다(이번 조사로 확인된 진짜 blocker).
2. 재구축 후 `independent_evalset_prototype.py`를 규모 확장(카테고리당 12→50~150,
   `evalset_pairs.py`의 5개 템플릿 적용)해 재실행.
3. 기존 `run_ab.py` 평가 파이프라인으로 **구 dataset(426) vs proposed final(259)**
   양쪽에 대해 같은 독립 평가셋으로 Hit@1/Hit@3/Recall@K/MRR을 비교 — "선정 개선이
   실제 검색 성능에 기여했는가"를 처음으로 직접 측정.
4. §9의 unresolved 77종 + 41 merge cluster + ADD_HOLD 1건에 대한 사람 검토를
   거쳐 `undergrad_target_chemicals.csv`에 실제 반영할지 결정(이번 세션 범위 밖).
