# PHASE 7 — 독립 평가 기반 최종 Chemical Corpus 검증

**작성일**: 2026-08-08
**결론 먼저**: **301종(C)을 최종 확정하지 않는다.** 이번 PHASE 7에서 구축한, wave
편향과 어휘 누출을 최대한 줄인 신규 독립 평가셋(150건)으로 426/259/301/354(D)를
동일 조건에서 재평가한 결과, PHASE 5~6의 "301이 426과 동등하거나 더 낫다"는
결론은 **뒤집혔다** — strict(150건 공통 모수) 기준으로 **426이 301보다 Recall@10
2.26배(0.455 vs 0.201), MRR 2.47배 높다.** 근거가 확정을 지지하지 않으므로
301은 물론 426·354(D) 어느 것도 이번 단계에서 "최종"으로 확정하지 않고
**전부 REVIEW 상태로 남긴다** — 아래 §9에서 이유를 상세히 설명한다.

**실행 스크립트**: `02_classification/phase7_independent_validation.py`(기존
50건 감사 + 신규 150건 생성), `04_rag_agent/phase7_candidate_comparison.py`
(426/259/301/D 동일조건 비교 + REVIEW-134 분류 + paired bootstrap).

**산출물**: `01_collection/chemical_phase7_eval_audit_2026-08-08.csv`(기존
36쌍 감사), `01_collection/chemical_phase7_independent_evalset_2026-08-08.csv`
+ `04_rag_agent/evalset/independent_eval_v2_2026-08-08.jsonl`(신규 150쌍),
`01_collection/chemical_phase7_review134_status_2026-08-08.csv`(134종 분류),
`01_collection/chemical_phase7_candidate_sets_2026-08-08.csv`(A/B/C/D 요약),
`docs/phase7_candidate_comparison_results_2026-08-08.md`(상세 수치).

**원칙 확인**: `undergrad_target_chemicals.csv` 미변경(세션 내내). DB는
`rag_corpus_membership`에 `phase7_D` 태그 1개 추가만(CAS 목록, 청크 내용
무변경). 자동 삭제·병합·최종 편입 없음. 근거 부족 시 확정하지 않는다는 원칙을
그대로 지켰다.

---

## 1. 왜 실제 코드/DB부터 다시 봤는가

시작 전 `04_rag_agent/evalset/independent_eval_prototype_2026-08-08.jsonl`(기존
50건)을 다시 열어 확인한 결과, PHASE 6에서 인용한 "301=38.9%"가 **retrieval
성능이 아니라 corpus membership 체크**(양쪽 물질이 코퍼스에 존재하는가)였다는
걸 코드 추적으로 확인했다(`phase6_selection_scenarios.py`의 해당 로직은
`rag_corpus_membership` 대조만 하고 실제 랭킹은 계산하지 않았다). 또한 그
파일의 `gold_section` 필드가 **PHASE 4-F 생성 시점(당시 `rag_chunks`는 Wave1
197종만 있던 상태)에 고정된 값**이라 지금 기준으로 stale하다는 것도 확인했다
— 지금 `rag_chunks` 기준으로 다시 계산하면 36쌍 전부 정답 청크가 잡힌다
(§2 표).

---

## 2. 기존 50건(36쌍) 전수 감사 결과

| 항목 | 결과 |
|---|---|
| membership 커버리지 | 426=100%(36/36), 259=33.3%(12/36), 301=38.9%(14/36), D(phase6)=41.7%(15/36) |
| gold_section stale(파일 저장값, >0인 것) | 25/36 |
| gold_section fresh(현재 rag_chunks 재계산, >0인 것) | **36/36** |
| query leakage(질의에 정답 물질명이 그대로 노출) | **36/36(100%)** |
| wave 조합 | wave1×wave2=24, wave2×wave2=11, wave2×wave1=1, **wave1×wave1=0건** |
| 301 membership 미충족(22건) 원인 | **100%가 REMOVE_CONFIRMED 또는 MERGE_REDUNDANT(비대표) 물질** — 즉 Phase4/6이 실제로 근거를 갖고 뺀 물질을 물어보는 질의였다 |

**진단**: 기존 프로토타입은 (1) 어휘 누출이 100%라 lexical/BM25 매칭에 유리하게
설계돼 있었고, (2) wave1×wave1 조합이 0건이라 "제거된 물질들이 얼마나 자주
등장하는 질의인가"를 의도적으로 wave2 편중으로 만들었으며, (3) 이 편중된
질의 집합에 대고 259/301의 낮은 membership을 "성능 문제"처럼 인용한 것이
PHASE 6까지의 오해였다. **301 membership 미충족의 근본 원인은 corpus/selection
결함이 아니라 평가셋이 "이미 제거하기로 결정한 물질"을 집중적으로 캐물었기
때문**이다 — 이 부분만 보면 오히려 Phase4/6 판정이 일관됐다는 증거로도 읽을 수
있다. 문제는 여기서 끝나지 않는다 — §4에서 훨씬 중요한 사실이 나온다.

---

## 3. 신규 독립 평가셋 150건 설계

기존 36쌍을 재사용하지 않고 새로 만들었다(중복 제거 확인). 설계 원칙:

- **wave 편향 제거**: wave1×wave1 **33건**, wave1×wave2 67건, wave2×wave2 43건,
  reactive_basics 조합 7건 — 기존(wave1×wave1 0건)과 달리 실제 pair 공간을
  왜곡 없이 대표하도록 균형을 맞췄다.
- **68 CAMEO 그룹 중 scarce 그룹 13/13 전부 커버**.
- **PHASE6 REVIEW-134 물질을 의도적으로 다수 포함**(150쌍 중 97쌍이 REVIEW-134
  관여) — 이건 특정 후보군에 유불리하게 만들려는 조작이 아니라, REVIEW 134종의
  실제 처분(§6)을 판단하는 데 필요한 데이터를 확보하려는 명시적 목적이다(요청
  사항에도 명시).
- **카테고리 균형**: Incompatible 80 / Caution 39 / Compatible(hard negative) 31.
- **어휘 누출 완화**: 150건 중 75건은 물질명 기반(기존과 동일 방식), 나머지
  75건은 **CAS 번호만 사용**(물질명 노출 없음) — 두 방식을 절반씩 섞어 어휘
  누출 효과를 분리 관찰할 수 있게 했다.
- **gold_section은 현재 `rag_chunks`를 직접 조회**해 생성(캐시된 stale 값
  재사용 안 함) + 실질 내용(공백/자료없음 아님) 확인까지 마친 것만 채택.
- **정직한 provenance 표기**: `verification_method=rule_based_self_check`,
  `human_verified=False`, `provenance_tier=DIAGNOSTIC`로 전부 명시했다 —
  "사람이 검수했다"고 사칭하지 않는다. gold 라벨(매트릭스 판정 + 실제 §2/§10
  원문 청크)은 객관적 원천에서 나오지만, **질의 문구 자체와 표집 대상 선정은
  AI(이 세션)가 수행**했고, wave/그룹 인지 계층표집을 썼으므로 §7 기준으로는
  **DIAGNOSTIC**이지 완전한 INDEPENDENT가 아니다(정직하게 승격하지 않음).

---

## 4. 426/259/301(C)/354(D) 완전 동일조건 비교 — 핵심 결과

동일 임베딩모델(bge-m3-ko)·동일 청킹(section)·동일 섹션필터(§2,§10)·동일
hybrid(RRF k=60)·동일 top-10·동일 채점 코드.

### selection-aware(각 코퍼스 자체 유효질의 기준)

| candidate | n_kept/150 | Recall@10 | MRR | nDCG@10 | Hit@10 |
|---|---:|---:|---:|---:|---:|
| A(426) | **150** | 0.4550 | 0.3849 | 0.3495 | 0.7667 |
| B(259) | 36 | 0.6681 | 0.5483 | 0.5222 | 0.9722 |
| C(301) | 51 | 0.5922 | 0.4591 | 0.4508 | 0.9020 |
| D(354=C+REVIEW_SUPPORTED) | 112 | 0.5549 | 0.4608 | 0.4270 | 0.8750 |

### strict(150건 공통 모수 환산 — **공정 비교 기준, 이번 보고서의 공식 KPI**)

| candidate | Recall@10 | MRR | nDCG@10 | Hit@10 |
|---|---:|---:|---:|---:|
| **A(426)** | **0.4550** | **0.3849** | **0.3495** | **0.7667** |
| B(259) | 0.1603 | 0.1316 | 0.1253 | 0.2333 |
| C(301) | 0.2013 | 0.1561 | 0.1533 | 0.3067 |
| D(354) | 0.4143 | 0.3440 | 0.3188 | 0.6533 |

**426이 모든 strict 지표에서 압도적 1위다.** 301은 259보다는 낫지만 426의
44%(Recall@10 기준) 수준에 그친다. D(354)가 426에 가장 근접(Recall@10
91.1%)하지만 여전히 못 미친다.

### Paired bootstrap(질의 단위 win/loss, 95% CI, n_boot=2,000)

| 비교 | 지표 | n_common | mean diff | 95% CI | win/loss/tie |
|---|---|---:|---:|---|---|
| A vs B | MRR성분(rr) | 36 | −0.179 | (−0.253, −0.120) | 1/23/12 |
| A vs B | nDCG | 36 | −0.158 | (−0.202, −0.120) | 1/31/4 |
| A vs C | rr | 51 | −0.053 | (−0.077, −0.032) | 1/22/28 |
| A vs C | nDCG | 51 | −0.061 | (−0.082, −0.042) | 3/33/15 |
| B vs C | rr | 36 | **+0.119** | (+0.076, +0.172) | 19/1/16 |
| B vs C | nDCG | 36 | **+0.090** | (+0.062, +0.122) | 26/1/9 |

**흥미로운 반전**: **A(426) vs B/C의 공통질의 비교에서는 오히려 259/301이
426보다 개별 순위 품질(rr/nDCG)이 유의하게 높다**(CI가 0을 포함하지 않음,
표본 36~51건으로 작지만 방향은 일관됨). 즉 **"답할 수 있는 질의에 한해서는"
작은 코퍼스가 더 정확하게 답한다** — 그런데 정작 **"답할 수 있는 질의의
범위 자체"가 426(150/150)과 259/301(36~51/150)에서 크게 차이 나서, 전체
모수로 환산(strict)하면 결과가 뒤집힌다.** 이게 이번 PHASE 7의 핵심 발견이다
— PHASE 5/6은 "답할 수 있는 것만 놓고 보면 작은 코퍼스가 낫다"는 것까지는
맞았지만, "그래서 작은 코퍼스가 전반적으로 낫다"로 일반화한 게 이번 재검증으로
기각됐다.

**B vs C 반전**: 259(B)가 301(C)보다 공통질의에서 유의하게 더 좋다(win 19~26 vs
loss 1). 301이 259보다 42종 더 크기 때문에 코퍼스 안에 경쟁 후보(distractor)가
늘어 특정 질의의 랭킹이 오히려 밀리는 현상으로 보인다 — "코퍼스를 키우면
무조건 좋아진다"도 아니라는 뜻.

---

## 5. REVIEW-134 최종 분류 (신규 평가셋 기준)

| status | 종수 | 의미 |
|---|---:|---|
| REVIEW_SUPPORTED | **53** | 신규 평가셋에서 실제로 등장 + 자기 청크가 426에서 top-10에 잡힘(hit_rate≥0.5) |
| REVIEW_UNSUPPORTED | 34 | 등장했지만 hit_rate<0.5 |
| REVIEW_NOT_TESTED | 47 | 이번 150건에도 등장 안 함 — 여전히 근거 없음 |

**원칙 준수**: UNSUPPORTED·NOT_TESTED를 "제거해야 한다"는 의미로 해석하지
않았다(요청사항 그대로) — 둘 다 REVIEW 상태 유지, 자동 REMOVE 전환 없음.

D = C(301) + REVIEW_SUPPORTED(53) = **354종**.

---

## 6. 필수 질문 13개에 대한 답

**1) independent evaluation에서 301이 38.9%로 낮게 나온 정확한 원인은?**
membership 체크였을 뿐 retrieval 성능 지표가 아니었고, 그 membership 결손의
100%가 "Phase4/6이 이미 근거를 갖고 뺀 물질"을 질문한 데서 왔다 — 평가셋
설계(wave2 의도적 편중)가 낳은 구조적 결과이지 무작위 결함이 아니다(§2).

**2) 평가셋의 label/provenance에 문제가 있었는가?**
있었다 — `gold_section`이 stale했고(§1), query leakage가 100%였다(§2). 둘 다
신규 150건에서 수정했다(§3).

**3) corpus membership 또는 MERGE 처리 문제가 있었는가?**
membership 자체는 설계대로 정확했다(REMOVE_CONFIRMED/MERGE_REDUNDANT가
빠진 게 맞다). 문제는 membership이 아니라 **strict 환산 시 그 빠짐 자체가
retrieval 성능에 미치는 실질적 비용**이었다(§4) — 이건 "처리 오류"가 아니라
"실제로 존재하는 트레이드오프"다.

**4) query distribution/difficulty imbalance가 있었는가?**
있었다(기존 50건, §2) — 신규 150건에서 wave/그룹/난이도 균형을 재설계했다(§3).

**5) 실제 selection 품질의 문제였는가?**
부분적으로 그렇다 — strict 비교(§4)가 "301은 426보다 답할 수 있는 질의
범위가 훨씬 좁다"를 실측으로 보여준다. 다만 **답할 수 있는 범위 안에서의
품질은 259/301이 426보다 낫다**(paired 비교, §4) — "품질이 나쁘다"가 아니라
"커버리지가 좁다"는 게 더 정확한 진단이다.

**6) 426/259/301 중 독립 평가에서 가장 안정적인 후보군은?**
strict 기준으로는 **426**이 가장 안정적(전 지표 1위, 모든 질의에 답 가능).
답 가능한 범위로 한정하면 **259**가 가장 품질이 높다. 이 둘은 서로 다른 질문에
대한 답이라 단일 승자를 선언하지 않는다.

**7) 301이 실제로 426보다 작은 corpus로 동일하거나 더 좋은 retrieval 성능을
유지하는가?**
**아니다.** strict 기준 426이 301보다 Recall@10 2.26배, MRR 2.47배 높다 —
PHASE 5/6의 결론은 이번 재검증으로 **기각**된다.

**8) REVIEW 134종 중 independent evidence가 확인되는 물질은 몇 종인가?**
**53종**(REVIEW_SUPPORTED, §5). 47종은 이번에도 근거 없음(NOT_TESTED), 34종은
근거가 있지만 약함(UNSUPPORTED) — 강제 판정하지 않고 REVIEW 유지.

**9) 301보다 작은 후보군으로 성능을 유지할 수 있는가?**
데이터 없음 — 이번 PHASE 7은 301보다 작은 후보군을 별도로 만들어 평가하지
않았다. strict 결과(259가 301보다도 더 낮음)를 보면 "작을수록 유지가 어려워
진다"는 방향성은 있으나 확정적 증거는 아니다.

**10) 301보다 큰 후보군이 성능/coverage/효율 측면에서 더 합리적인가?**
D(354)가 301보다 strict Recall@10을 0.201→0.414로 크게 개선한다(§4) — 그러나
여전히 426(0.455)에는 못 미친다. "더 큰 게 낫다"는 방향은 지지되지만 "얼마나
커야 충분한가"의 임계값은 이번 데이터로 특정할 수 없다.

**11) 최종 Chemical Selection Rule을 다른 사람이 실행해도 동일한 결과가
나오는가?**
§7의 규칙 자체(코드로 구현된 결정론적 규칙)는 재현 가능하다 — 단, 재현
가능한 건 "규칙 적용 결과"이지 "최종 확정된 물질 목록"이 아니다. 이번
PHASE 7 결과로 그 목록 자체는 아직 확정할 수 없다(§9).

**12) 최종 corpus의 각 물질에 대해 "왜 포함/제외됐는가"를 설명할 수 있는가?**
Phase1~7 전체 파이프라인(curriculum, §10 empirical, group coverage, scarcity,
redundancy, retrieval contribution, independent eval)을 거친 물질에 대해서는
**예** — CSV들의 provenance 체인으로 역추적 가능하다. 다만 REVIEW 134종
(특히 NOT_TESTED 47종)에 대해서는 "왜 REVIEW 상태인가"는 설명 가능해도 "왜
최종적으로 포함/제외됐는가"는 **아직 답할 수 없다**(근거 부족, 확정 안 함).

**13) 최종 corpus를 실제 RAG production/evaluation corpus로 사용해도 되는
수준인가?**
**아니다, 아직.** strict Recall@10이 최선의 후보(426)조차 0.455 수준이고
(과거 gold_pair.jsonl 기준 0.88대와 크게 다름 — 이는 어휘 누출이 제거된
더 현실적인 수치로 판단됨), 어느 후보군도 "production-ready"라고 부를 근거가
없다. §9에서 이유를 정리한다.

---

## 7. 재현 가능한 최종 Chemical Selection Rule (초안)

이번 PHASE 7까지의 전 과정을 종합해, 아래 8개 요소를 **개별적으로 계산하고
결정론적 우선순위로 결합**하는 규칙을 제안한다(가중치로 뭉개지 않음 — Phase6
§6에서 가중치 시나리오 70.7%가 불안정했던 교훈 반영):

```
1. curriculum/실험 현실성      : curated_curriculum 소속 여부 (KEEP_MANDATORY)
2. §10 empirical evidence      : 자기 §10 실질근거(has_own_s10_evidence)
3. CAMEO group coverage        : 이 물질 없이 그룹이 커버되는가
4. scarce-group preservation   : 소속 그룹이 현재 대표물질 ≤2종인가(현재 코퍼스 기준 재계산)
5. signature redundancy        : 동일 그룹조합 물질 중 순위(자기 근거 유무·양)
6. independent retrieval       : 신규 독립평가셋에서 자기 청크 hit_rate(있는 경우만, NO_DATA는 미확정)
7. data availability            : KOSHA 4섹션 확보 여부
8. independent evaluation evidence: 위 6번이 진단(diagnostic)이 아니라 진짜 독립 평가에서
                                     나온 것인지 — 이번 PHASE 7 150건도 아직 DIAGNOSTIC
                                     등급(§3)이라 이 요소는 **아직 완전히 충족되지 않음**
```

우선순위(REMOVE 확정 조건, 전부 동시 충족 시에만):
```
독립 evidence 없음(1,2 모두 False)
AND coverage 기여 없음(3,4 모두 False)
AND retrieval contribution 근거 없음(6이 NO_DATA 또는 UNSUPPORTED)
AND 대체 대표물질 존재(5에서 자신이 rank1 아님)
→ REMOVE_CONFIRMED

그 외 전부 → REVIEW 또는 RETAIN_* (근거 있는 쪽으로)
```

이 규칙 자체는 코드(`phase6_retrieval_reassessment.py`+`phase7_*.py`)로
구현돼 있어 **동일 입력에 대해 항상 동일 출력**을 낸다(요청사항 11 충족).
그러나 8번 요소(진짜 independent evaluation evidence)가 이번 세션까지도
DIAGNOSTIC 등급을 벗어나지 못했으므로, **이 규칙을 "완성됐다"고 선언하지
않는다** — §9.

---

## 8. selection quality / retrieval quality / efficiency 종합 비교

`01_collection/chemical_phase7_candidate_sets_2026-08-08.csv` 참고. 요약:

| candidate | 물질 수 | §2,§10 청크 수 | strict Recall@10 | 독립근거비율(A/B만 재계산됨) | 그룹coverage |
|---|---:|---:|---:|---|---|
| A(426) | 426 | 893 | 0.4550 | 12.0% | 67/68 |
| B(259) | 259 | 545 | 0.1603 | 70.3% | 67/68 |
| C(301) | 301 | 629 | 0.2013 | **재계산 안 됨**(NOT_RECOMPUTED) | 67/68 |
| D(354) | 354 | 738 | 0.4143 | **재계산 안 됨**(NOT_RECOMPUTED) | 재계산 안 됨 |

**정직하게 밝히는 gap**: C/D의 selection-quality 지표(독립근거비율·중복비율·
§10 커버리지)는 이번 PHASE 7에서 별도로 재계산하지 않았다 — 시간·범위 제약으로
retrieval 축 검증에 집중했다. **이 표를 selection-quality까지 완전히 채우는
것이 다음 세션의 선결 과제**다(추측치로 채우지 않음 — 완료조건 미충족을
그대로 노출).

---

## 9. 왜 301(또는 다른 후보)을 최종 확정하지 않는가 — Blocker 정리

완료 조건(사용자 지정) 대조:

| 조건 | 상태 |
|---|:--:|
| independent evaluation provenance 정리 | 완료(§3, DIAGNOSTIC 등급으로 정직하게 표기) |
| 최소 100건 이상 독립 평가셋 확보 | 완료(150건) |
| gold label 검수 완료 | **부분 완료** — rule-based self-check만 했고 실제 사람 검수는 안 됨(§3에 명시) |
| 426/259/301 동일조건 비교 완료 | 완료(§4) |
| REVIEW 134종 independent evidence 상태 확인 | 완료(§5) |
| selection/retrieval/coverage/efficiency 종합 비교 | **부분 완료** — retrieval·efficiency는 완료, C/D의 selection quality는 미완료(§8) |
| 재현 가능한 최종 selection rule 작성 | 완료(규칙 자체, §7) — 단 규칙의 8번 요소(진짜 independent evidence)가 미충족 |
| 301종 최종 확정 가능 여부 판단 | **완료 — 판단 결과는 "확정 불가"** |

**핵심 blocker 3가지**:
1. **평가셋이 여전히 DIAGNOSTIC**: 150건이 사람 검수를 거치지 않았고, wave/
   그룹 인지 계층표집이라 완전한 독립 표본이 아니다. 진짜 INDEPENDENT 등급을
   확보하려면 사람이 gold를 검수하거나, 최소한 selection 구조를 전혀 모르는
   상태에서 질의를 만드는 절차가 필요하다.
2. **strict Recall@10이 최선의 후보(426)조차 0.455**: 이게 "이 RAG 시스템의
   진짜 실력"인지 "질의 스타일(CAS 기반 75건 vs 명칭 기반 75건)에 따라
   갈리는 것"인지 이번 보고서에서 분리하지 않았다 — 두 스타일의 지표를
   따로 뽑아보는 게 다음 단계에서 필요하다.
3. **C/D의 selection-quality 축이 비어 있다**(§8) — retrieval만으로 최종
   후보를 정하면 "Coverage ≠ Retrieval"(판정 원칙 3)을 스스로 어기는 것.

이 세 가지가 전부 해소되기 전까지는 **426, 259, 301, 354(D) 중 어느 것도
"최종 Chemical Corpus"로 확정하지 않는다.** 현재 시점에서 실무적으로 가장
방어 가능한 잠정 선택지는 **D(354)** — strict retrieval이 426에 가장
근접하면서(91.1%) selection 축 개선(REMOVE_CONFIRMED/MERGE_REDUNDANT 근거
있는 128종은 여전히 제외)도 일부 유지하기 때문 — 이나, 이것도 "잠정 권고"
이지 확정이 아니다.

---

## 10. Phase 8 제안 (착수하지 않음)

1. 150건 중 최소 30~50건을 사람이 직접 검수해 INDEPENDENT 등급으로 승격.
2. CAS 기반 vs 명칭 기반 질의의 성능 차이를 분리 측정(어휘 누출 정량화).
3. C(301)/D(354)의 selection-quality 지표(독립근거비율·중복비율·§10 커버리지)를
   Phase4/6과 동일한 방법론으로 재계산해 §8 표를 완성.
4. §7의 selection rule을 실제로 426종 전체에 처음부터 다시 적용해, 지금까지
   나온 순차적 후보군(B→C→D)이 아니라 규칙을 한 번에 적용했을 때도 같은
   결과가 나오는지 검증(규칙의 경로 독립성 확인).
5. strict Recall@10 0.455(426, 최선)가 production 기준을 만족하는지 목표치를
   먼저 정하고, 안 되면 리랭커 재도입·질의 인코더 교체 등 검색 품질 개선
   자체를 먼저 검토.

**PHASE 8로 자동 진행하지 않는다.**
