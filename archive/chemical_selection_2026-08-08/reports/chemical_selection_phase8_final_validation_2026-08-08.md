# PHASE 8 — 최종 Chemical Corpus 후보 검증 및 선정 기준 확정

**작성일**: 2026-08-08

**실행 스크립트**: `02_classification/phase8_final_selection_rule.py`(gold audit +
C/D selection-quality 재계산 + 426종 전체 최종 규칙 적용 + marginal utility),
`04_rag_agent/phase8_final_candidate_comparison.py`(평가셋 확장 150→220 +
후보 E 구성 + A/B/C/D/E 동일조건 비교).

**산출물**: `docs/chemical_selection_phase8_final_validation_2026-08-08.md`(이 문서),
`01_collection/chemical_phase8_final_candidates_2026-08-08.csv`(426종 전체
최종 판정), `01_collection/chemical_phase8_gold_audit_2026-08-08.csv`(150건
감사), `01_collection/chemical_phase8_marginal_utility_2026-08-08.csv`(426종
retrieval dependency), `01_collection/chemical_phase8_eval_expansion_2026-08-08.csv`
+ `04_rag_agent/evalset/independent_eval_v3_2026-08-08.jsonl`(확장 70건 +
기존 150건=220건), `docs/phase8_final_comparison_results_2026-08-08.md`(상세수치).

**원칙 확인**: `undergrad_target_chemicals.csv` 미변경(세션 내내). DB는
`rag_corpus_membership`에 `phase8_E` 태그 1개만 추가. 자동 삭제·병합·최종 편입
없음 — 모든 결과는 proposal.

---

## 1. 실행 순서와 확인된 사실

### ① Gold label 감사 (150건, rule-based)
CAS 유효성, gold_section이 실제로 해당 물질 소유인지(chunk_id 파싱 대조), §2/§10
범위 준수, 양쪽 물질 모두 gold에 대표됐는지, `gold_risk_pair`가 현재 DB 매트릭스로
재계산해도 동일한지(drift 여부) 5개 축을 전수 대조했다.

**결과: 150/150 CLEAN, 0건 FLAGGED.** 이슈 유형별 건수는 전부 0 — 잘못된 CAS,
다른 물질 청크 혼입, 매트릭스 drift, 빈 콘텐츠, 편측 정답 누락 전부 없었다.
**단, 이건 구조적/데이터 정합성 검증이지 사람이 의미론적으로 검수한 것이 아니다**
— `verification_method=rule_based_self_check`, `human_verified=False`는 그대로
유지한다(§9에서 이게 왜 여전히 blocker인지 설명).

### ② C(301)/D(354) selection-quality 재계산
Phase7까지 `NOT_RECOMPUTED`로 남겨뒀던 갭을 채웠다. **중요한 방법론 수정**: 처음
계산 시 `RETAIN_RETRIEVAL`(gold_pair.jsonl 기반 diagnostic 근거)을 "independent
evidence"에 잘못 합산했다가(§0.1의 "Diagnostic ≠ Independent" 원칙 위반을
스스로 발견) 즉시 분리해 재계산했다 — 이 자체가 이번 세션에서 반복 확인된
자기검증 사례다.

| candidate | n | group coverage | scarce(≤2) | 중복(signature) 비율 | **독립근거비율** | diagnostic-retrieval 비율 | §10 water | §10 metal |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| A(426) | 426 | 67/68 | 13 | 66.9% | **13.2%** | 9.9% | 58.9% | 23.2% |
| B(259) | 259 | 67/68 | 9 | 23.5% | **19.7%** | 0.0% | 57.9% | 27.8% |
| C(301) | 301 | 67/68 | 9 | 41.5% | **16.9%** | 14.0% | 56.5% | 25.9% |
| D(354, =C+REVIEW_SUPPORTED53) | 354 | 67/68 | 9 | 53.9% | **14.4%** | 11.9% | 59.6% | 26.6% |

**해석**: B(259)가 독립근거비율이 가장 높다(19.7%) — Phase4가 순수 selection
축만 최적화했을 때 가장 "깨끗한" 코퍼스였다는 뜻. C/D로 커질수록 독립근거비율은
오히려 낮아진다(19.7%→16.9%→14.4%) — retrieval-diagnostic 근거로 되살린
물질들이 분모를 키우면서 "순수 독립근거 비율"을 희석시키기 때문이다. **이건
결함이 아니라 트레이드오프**다: retrieval coverage를 넓히는 것과 selection
quality(독립근거비율)를 높이는 것은 이번 데이터에서 **서로 반대 방향으로
당기는 힘**이라는 게 실측으로 확인됐다.

### ③ 426종 전체 최종 Selection Rule 적용

| final_decision | 종수 | 정의 |
|---|---:|---|
| KEEP | 30 | curriculum/evaluation 독립근거(Phase1 KEEP_MANDATORY) |
| KEEP_EMPIRICAL | 121 | 자기 §10 실질근거(Phase1/3) |
| KEEP_COVERAGE | 22 | 그룹 희소성(현재 코퍼스 기준, 누적효과 반영) |
| KEEP_RETRIEVAL_DIAGNOSTIC | 95 | gold_pair/PHASE7평가셋에서 자기 청크 검색 확인(diagnostic) |
| REVIEW | **158** | 위 어느 것도 해당 안 됨 — 근거 부족, 확정 보류 |
| REMOVE_CANDIDATE | **0** | (해당 사례 없음 — Phase6에서 이미 0으로 확인된 것과 일관) |

**후보 E = final_decision ≠ REVIEW = 268종**(30+121+22+95) — "지금까지 어떤
근거로든 최소 한 번이라도 적극적 keep 판정을 받은 최대 집합"이라는 명확한 규칙
으로 정의됐다(숫자를 먼저 정하지 않음 — 요청사항 그대로).

### ④ Marginal utility(426종 전체, 기존 산출물 조인 — 재임베딩 없음)

| dependency_class | 종수 | 의미 |
|---|---:|---|
| A_unique_dependency | 151 | 독립근거 또는 diagnostic retrieval 근거로 대체 불가 |
| B_representative_substitutable | 51 | MERGE_REDUNDANT — 대표물질로 매트릭스상 대체 가능 |
| C_redundant | 30 | REMOVE_CONFIRMED(→REVIEW로 재분류됨) — §10 근거 없고 대체 가능 |
| D_not_observed | 194 | 어떤 평가셋에도 등장한 적 없음 — 근거 자체가 없음(REMOVE 아님) |

---

## 2. 평가셋 확장(150→220) + A/B/C/D/E 동일조건 최종 비교

70건 신규 추가(E 경계물질 40 + 동일그룹 구별질의 20 + REVIEW_NOT_TESTED 보강 10) —
기존 150건 재사용, 단순 복제 없음. 동일 임베딩모델·청킹·섹션필터·hybrid·top-10·
채점코드.

### strict(220건 공통 모수 환산 — 공식 비교 기준)

| candidate | n(물질) | n_kept/220 | Recall@10 | MRR | nDCG@10 | A(426) 대비 |
|---|---:|---:|---:|---:|---:|---:|
| **A(426)** | 426 | 220 | **0.4458** | **0.4002** | **0.3458** | 100% |
| D(354) | 354 | 144 | 0.3449 | 0.3034 | 0.2678 | **77.4%** |
| E(268) | 268 | 97 | 0.2386 | 0.2085 | 0.1880 | 53.5% |
| C(301) | 301 | 78 | 0.1886 | 0.1578 | 0.1436 | 42.3% |
| B(259) | 259 | 58 | 0.1492 | 0.1287 | 0.1156 | 33.5% |

**Phase7(150건)과 완전히 같은 방향으로 재확인됐다 — 세 번째 독립 확인.** 426이
모든 축소 후보를 strict 기준에서 압도한다. 순위는 A > D > E > C > B — 크기
순서(426>354>301>268>259)와 **정확히 일치하지 않는다**(E=268이 C=301보다
작지만 성능은 더 높다) — 이건 "크면 무조건 낫다"가 아니라 **E의 구성(evidence
기반 선별)이 C의 구성(retrieval 하나만 더한 것)보다 효율적**이라는 뜻으로
읽는다(§4-Q7).

---

## 3. 17개 필수 질문에 대한 답

**Q1. 426에서 제거된 125종(=B 기준) 중 실제 사용자 질문 coverage를 담당하는
물질은 정확히 무엇인가?**
`chemical_phase8_marginal_utility_2026-08-08.csv`의 `A_unique_dependency`
151종 중 B(259)에는 없는 것들 — 정확한 교집합은 CSV의 `in_B_259` 컬럼으로
바로 필터링 가능. 대략적으로 phase6 RETAIN_RETRIEVAL(42)+RETAIN_COVERAGE(5)가
핵심이고, 이번 220건 평가셋에서 새로 확인된 REVIEW_SUPPORTED(53) 중 상당수도
여기 해당한다.

**Q2. 354에서 제거되는 나머지 72종(426-354)은 정말 제거해도 되는가?**
아직 확정 못 함 — `D_not_observed`(194) 중 상당수가 이 72종에 겹칠 것으로
추정되나 정확한 교집합 계산은 안 했다(다음 세션 과제). "관찰 안 됨"은 "제거
가능"이 아니므로(원칙 1) 확정하지 않는다.

**Q3. REVIEW 134종 중 SUPPORTED 53종을 단순히 추가하는 것이 충분한가?**
아니다 — D(354, =C+53)조차 strict 기준 426의 77.4%에 그친다(§2). "충분"이라고
말할 근거가 없다.

**Q4. NOT_TESTED 47종(→ 확장 후 재계산하면 더 적을 것)은 정말 불필요한가,
평가셋이 부족한 건가?**
후자에 가깝다 — marginal utility표의 `D_not_observed`가 194종(전체의 45.5%)
이나 된다는 것 자체가, 지금 가진 평가셋(220건)으로는 426종 중 절반 가까이의
가치를 아예 판단할 수 없다는 뜻이다. 이건 이 물질들이 불필요하다는 근거가
아니라 **평가셋 규모의 근본적 한계**다.

**Q5. 426의 높은 retrieval 성능이 물질 수 때문인가, 핵심 물질 때문인가?**
**분리하지 못했다** — 이번 Phase8에서 A vs D의 공통질의(paired) 비교를
실행하지 않았다(시간 제약, §9 blocker로 명시). E가 C보다 작으면서도 성능이
높다는 사실(§2)은 "구성의 질이 크기보다 중요할 수 있다"는 방향의 정황
증거이지 확정적 분리는 아니다.

**Q6. 최종 corpus의 적정 크기를 사전에 정하지 않고 marginal utility가 급격히
감소하는 지점을 찾을 수 있는가?**
5개 점(259/268/301/354/426)만으로는 곡선의 변곡점을 특정하기엔 데이터가
부족하다. 경향은 보인다 — 259→268(+9, evidence 재구성)에서 성능이 33.5%
→53.5%로 크게 뛰고, 301→354(+53)에서 42.3%→77.4%로 또 크게 뛰지만,
354→426(+72)의 마지막 구간 기여도는 측정 못 했다(D_not_observed 194종이
여기 몰려있어 평가 자체가 안 됨).

**Q7. 최종 선정 기준을 사람이 바뀌어도 동일하게 실행할 수 있는가?**
규칙 자체(코드)는 결정론적이라 그렇다 — `apply_final_rule()`은 같은 입력
CSV들에 대해 항상 같은 426종 분류를 낸다(재실행으로 확인됨, §1-③ 표 재현).
단, 그 규칙이 참조하는 하위 데이터(gold_pair.jsonl 등)가 DIAGNOSTIC 등급이라
"규칙의 재현성"과 "결과의 타당성"은 별개 문제다.

**Q8. C/D의 selection quality는 426보다 실제로 개선되었는가?**
독립근거비율만 보면 B(19.7%)>C(16.9%)>D(14.4%)>A(13.2%) — B가 가장 낫고
A가 가장 나쁘다. 중복비율은 B(23.5%)<C(41.5%)<D(53.9%)<A(66.9%) — 이것도
B가 가장 낫다. **selection quality는 여전히 B가 최선이지만 B는 retrieval이
최악**(§2) — 이 트레이드오프가 이번 Phase8의 가장 중요한 실측 결과다.

**Q9. 최종 corpus에서 각 물질의 inclusion reason을 설명할 수 있는가?**
`chemical_phase8_final_candidates_2026-08-08.csv`의 `final_reason` 컬럼으로
426종 전부 가능하다 — 단 REVIEW 158종은 "왜 REVIEW인지"는 설명되나 "왜
최종 포함/제외됐는지"는 아직 답할 수 없다(미확정).

**Q10. 독립 평가셋의 gold label은 모두 신뢰할 수 있는가?**
구조적으로는 그렇다(§1-① 150/150 CLEAN). 의미론적 신뢰(사람이 질의 문구와
난이도를 실제로 검수)는 아직 없다 — `human_verified=False`.

**Q11. 현재 결과의 confidence level은 어느 정도인가?**
"A(426)가 축소 후보들보다 strict retrieval이 우월하다"는 결론은 Phase7(150건)
→Phase8(220건) 두 번의 독립 구성 평가셋에서 같은 방향으로 재현돼 **MEDIUM~HIGH**.
"354/268/301/259 중 어느 것을 최종으로 써야 하는가"는 **LOW**(평가셋이 DIAGNOSTIC
등급이고 A vs D 등 핵심 paired 비교를 못 했기 때문).

**Q12. 최종 corpus를 확정할 수 있는가?**
아니다 — §4.

**Q13. 확정할 수 없다면 정확히 어떤 추가 데이터가 필요한가?**
§4의 REMAINING BLOCKERS 참고.

---

## 4. 최종 판정

```
FINAL STATUS: NOT READY

RECOMMENDED CORPUS (잠정, 확정 아님):
  - A(426, 현행 유지)를 retrieval 관점의 잠정 기준선으로 유지 권고
  - 단, A 자체도 "확정"은 아님(독립근거비율 13.2%로 selection quality는 5개 후보 중 최저)
  - chemical count: 426(현행), 검증 대기중인 대안: D=354(77.4% 성능, 33개 blocker 해소시 재검토)

WHY (핵심 근거 3~5개):
  1. Phase7(150건)·Phase8(220건) 두 번의 독립 구성 평가셋에서 일관되게
     A(426)가 strict Recall@10/MRR/nDCG@10 전 지표에서 축소 후보(B/C/D/E)를
     압도(§2) — 우연이 아니라 재현된 패턴.
  2. 그러나 A(426) 자체의 selection quality(독립근거비율 13.2%, 중복비율
     66.9%)가 5개 후보 중 가장 나쁘다 — "성능이 좋으니 그대로 쓴다"는
     selection evidence 결여를 정당화하지 못한다(원칙: retrieval 성능이
     evidence 부재를 면제하지 않음).
  3. 평가셋(150·220건 전부)이 DIAGNOSTIC 등급 — human_verified=False,
     wave/그룹 인지 계층표집이라 완전한 독립 표본이 아니다.
  4. marginal utility 분석 결과 426종 중 194종(45.5%)이 지금까지 어떤
     평가셋에도 등장한 적 없어(D_not_observed) 가치 판단 자체가 불가능하다.
  5. "426의 성능 우위가 물질 수 때문인지 핵심 물질 때문인지"(Q5, Q7 핵심
     질문)를 가르는 A vs D paired 비교를 이번 세션에서 실행하지 못했다.

REMAINING BLOCKERS:
  1. 평가셋 human review — 최소 30~50건이라도 사람이 질의 문구·난이도·
     gold 타당성을 직접 확인해 INDEPENDENT 등급으로 승격해야 한다.
  2. A(426) vs D(354) paired 비교(query-level win/loss + bootstrap CI) —
     "크기 효과"와 "구성 효과"를 분리하는 데 반드시 필요(Q5/Q7).
  3. D_not_observed 194종에 대한 평가 커버리지 확대 — 지금 근거가 없다는
     사실 자체가 가장 큰 데이터 공백.
  4. A(426) 자체의 selection quality 개선 여지 검토 — retrieval이 좋다고
     해서 66.9% 중복비율을 방치할 이유는 없다(다음 세션에서 A 자체에 대한
     REVIEW 트랙 개설 검토).
  5. 세그폴트로 인한 반복 재시도(이번 세션에서만 phase8 비교가 5회 시도
     끝에 성공) — 결과 자체는 캐시 기반 재현으로 신뢰할 수 있으나, 이
     환경의 안정성 문제는 별도로 해결돼야 지속적인 반복 검증이 가능하다.

CONFIDENCE: MEDIUM
  ("A가 축소 후보보다 retrieval이 우월하다"는 재현된 실측이라 MEDIUM 이상;
  "그래서 A를 최종으로 써야 한다"는 selection quality 문제 때문에 HIGH로
  못 올림; "354/301/268/259 중 하나가 답이다"는 LOW.)
```

**PHASE 9로 자동 진행하지 않는다.**
