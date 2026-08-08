# 427종 화학물질 Provenance Audit — PHASE 1 결과

**작성일**: 2026-08-08
**범위**: PHASE 1(Provenance Audit + Group Distribution Audit + Coverage Audit)만 수행.
물질 추가/삭제/CSV 덮어쓰기는 하지 않았다.
**실행 스크립트**: [`02_classification/provenance_audit.py`](../02_classification/provenance_audit.py)
(읽기 전용 — 원본 CSV·DB에 쓰기 연산 없음. 검증은 §10 참고)

**산출물**:
- [`01_collection/chemical_selection_audit_dataset_2026-08-08.csv`](../01_collection/chemical_selection_audit_dataset_2026-08-08.csv) — 후보 475행 전체 provenance
- [`01_collection/chemical_selection_backfill_candidates_2026-08-08.csv`](../01_collection/chemical_selection_backfill_candidates_2026-08-08.csv) — coverage gap 후보 66행(자동 편입 안 됨)

이 문서에 인용된 모든 숫자는 위 스크립트가 직접 계산해 출력한 값을 그대로 옮긴 것이다
(손으로 다시 계산하지 않음 — 재현하려면 스크립트를 그대로 재실행하면 된다).

---

## 0. candidate pool / selected dataset / collected dataset 3분리 (요청사항 정리)

| 개념 | 정의 | 실측값 |
|---|---|---:|
| candidate pool | `undergrad_target_chemicals.csv`의 전체 행 | **475** |
| collected dataset | KOSHA MSDS 4섹션(2/3/9/10) 전부 확보 | **426** (candidate와 연결된 것만) |
| (미수집) | KOSHA 목록에 없어 조회 즉시 실패 | **49**(ABSTAIN_NOT_FOUND) — `msds_chem_id_cache.chem_id IS NULL` |

**"427"이라는 숫자에 대한 정정**: DB(`msds_sections`)에서 4섹션을 전부 가진 CAS를 직접 세면
**427**개가 나온다. 그런데 그중 1개(`497-19-8`)는 현재 candidate CSV(475행) 어디에도 없는
**고아 레코드**다. `docs/decisions.md` §1.2b가 "UREA CAS 오류(497-19-8→57-13-6) 정정,
`chemicals` 테이블에서 chemical_id 3398 삭제"라고 기록했지만, 실제로는 `chemicals` 테이블
에서만 지워졌고 `msds_sections`/`msds_chem_id_cache`의 497-19-8 행은 그대로 남아있다
(`chemicals` 테이블 조회 시 497-19-8은 없음 → 이름 없는 orphan). 즉:

- **DB를 그냥 세면 427** (orphan 1건 포함)
- **현재 candidate CSV와 실제로 연결되는 수집 완료 물질은 426**

이 1건짜리 불일치 자체가 "427이라는 숫자를 셀 때마다 다른 방법으로 세고 있었다"는
사실을 보여주는 작은 증거다. 이 문서의 모든 통계는 **426(candidate CSV와 연결된
collected dataset)**을 기준으로 한다. Phase 2 실행 시 이 orphan 행 정리를 권고한다(삭제
여부는 이번 PHASE 1 범위 밖 — 보고만 함).

---

## 1. Provenance 복원 결과 (요청 보고사항 1·2)

426개 collected 물질 전체에 대해 `selection_status`를 계산했다(분류 규칙은 §4).

| selection_status | 종수 | 의미 |
|---|---:|---|
| KEEP_MANDATORY | **30** | 커리큘럼 실사용 근거 명시(`curated_curriculum`) |
| KEEP_COVERAGE | **17** | 자신이 속한 그룹 중 최소 하나가 대표물질 ≤2종인 그룹(coverage상 대체 어려움) |
| KEEP_EMPIRICAL | **4** | §10 실측(197종 전수조사) 1순위 기본물질 보강(`reactive_basics_tier1/2`) |
| REVIEW | **117** | 그룹 소속(무제한 편입) 또는 강제 대체 후보 — 개별 근거는 있으나 재평가 필요 |
| DUPLICATE | **131** | 다른 물질과 CAMEO 그룹 조합(true_cameo_groups)이 완전히 동일 — 매트릭스 엔진 기준 정보량 100% 중복 |
| UNSUPPORTED | **127** | 그룹 슬롯 자동 보충 — 물질 단위 개별 선정 근거가 코드/문서 어디에도 없음 |
| UNKNOWN | **0** | (모든 CSV `source` 값이 매핑 가능해 발생하지 않음) |
| 합계 | 426 | |

**"근거를 복원할 수 있는 종수"에 대한 두 가지 답**(질문이 요구한 대로 단정하지 않고
분리한다):
- **독립적 근거가 있는 것**(KEEP_MANDATORY+KEEP_COVERAGE+KEEP_EMPIRICAL) = **51종
  (12.0%)** — "왜 넣었는가"에 즉답 가능.
- **기계적 편입 경로는 추적되나 물질 단위 가치판단 근거는 없는 것**(REVIEW+DUPLICATE+
  UNSUPPORTED) = **375종(88.0%)** — 이 중 REVIEW(117)·DUPLICATE(131)는 "그룹에
  속해서 들어왔다"는 경로 자체는 재현 가능하지만, "왜 하필 이 물질을" 수준의 개별
  근거는 없다. UNSUPPORTED(127)는 경로조차 "슬롯을 채웠다"는 것 외에 아무 근거가
  없다(§1-2/1-6, 앞선 재설계 문서 참고).

**중요한 방법론 수정 — 순환논리 발견 및 배제**: 최초 구현에서는 "평가데이터
(`gold_pair.jsonl` 등)에 CAS가 등장하면 KEEP_MANDATORY"로 계산했더니 Wave1
non-curated 167종(pool_supplement 126+pool_topup 11+pool_replacement류 30) **전부**가
KEEP_MANDATORY로 나왔다. 원인을 추적하니 `04_rag_agent/evalset/gold_pair.jsonl` 등
평가셋 자체가 **Wave1(198~203종) 풀에서 기계적으로 파생**된 데이터였다(`HANDOFF.md`
§0-2: "Stage4 RAG 파이프라인은 전부 198~203종 기준으로 빌드"). 즉 "평가데이터 등장"을
Wave1의 독립적 가치 근거로 쓰면 "Wave1이었으니까 평가셋에 있고, 평가셋에 있으니까
Wave1은 정당하다"는 순환논리가 된다. 실측: 평가셋에 등장하는 196개 CAS 전부가
Wave1에서 나왔고, Wave2(223종) 중 평가셋에 등장하는 CAS는 **0개**다. 이 순환을
차단하기 위해 "평가데이터 등장 → KEEP_MANDATORY" 규칙은 **Wave1이 아닌 물질에만**
적용하도록 수정했다(Wave2/reactive_basics는 평가셋 생성에 관여하지 않았으므로 그쪽에서
평가셋에 등장한다면 그건 진짜 독립 증거다 — 다만 실측상 해당 사례는 0건). 이 발견 자체가
PHASE 1의 핵심 성과 중 하나다: **관련 없어 보이는 두 산출물(선정 CSV와 평가셋)이 같은
뿌리에서 나와 서로를 순환적으로 정당화할 위험이 있다는 것을 코드가 아니라 실측으로
잡아낸 사례.**

---

## 2. Wave1 / Wave2 분포 (요청 보고사항 3)

| wave | 종수 | 원본 source 구성 |
|---|---:|---|
| wave1 | **197** | curated_curriculum 30, pool_supplement 126, pool_topup 11, pool_replacement 20, pool_replacement_v2 7, pool_replacement_v3_manual 3 |
| wave2 | **223** | reaction_frequency_high 223 |
| reactive_basics | **6** | reactive_basics_tier1 3, reactive_basics_tier2 3 |
| 합계 | 426 | |

(참고: `decisions.md`/`HANDOFF.md`가 "203종→427종"이라 서술한 것과 달리, wave1은
현재 197종이다 — 청석면 등 이후 제외분과 collected/candidate 재계산 차이로 보임.
6종은 wave1도 wave2도 아닌 **별도 축**(§1.2a-upd)이라는 원 문서의 서술을 그대로
유지했다.)

---

## 3. 68그룹 분포 Audit (요청 보고사항 4)

**중요한 방법론 차이**: 이전 재설계 문서(`chemical_selection_criteria_redesign_2026-08-08.md`)
는 CSV의 `group_id`(물질이 편입될 때 배정받은 **단일** 그룹) 기준으로 66/68 커버리지를
계산했다. 이번 감사는 `chemical_group_membership` 테이블의 **실제(true) 다중 그룹
소속**을 기준으로 다시 계산했다 — 에탄올처럼 한 물질이 여러 그룹에 동시 소속되는 게
정상이기 때문에(`decisions.md` §1.2b), 이 쪽이 더 정확하다.

- **true-membership 기준 커버리지: 67/68** (CSV 단일배정 기준 66/68보다 1개 더
  커버됨 — 다중 그룹 소속 덕에 어딘가에 "곁다리로" 걸쳐 들어온 그룹이 있다는 뜻).
- **미커버**: 그룹25(Diazonium Salts)뿐. 그룹36(Insufficient Information for
  Classification)은 실질 화학 카테고리가 아니므로(Wave1 설계 당시부터 EXCLUDE) 커버
  대상에서 애초에 제외.

### 상위 10그룹 (true-membership, wave 분해)

| 그룹 | 그룹명 | 총 | wave1 | wave2 | reactive_basics |
|---:|---|---:|---:|---:|---:|
| 68 | Water and Aqueous Solutions | 106 | 18 | 86 | 2 |
| 50 | Oxidizing Agents, Strong | 82 | 13 | 68 | 1 |
| 61 | Salts, Basic | 55 | 15 | 40 | 0 |
| 60 | Salts, Acidic | 43 | 12 | 31 | 0 |
| 42 | Metals, Less Reactive agents | 29 | 7 | 22 | 0 |
| 46 | Nitro/Nitroso/Nitrate/Nitrite Compounds, Organic | 24 | 7 | 17 | 0 |
| 51 | Oxidizing Agents, Weak | 24 | 7 | 17 | 0 |
| 41 | Metals, Elemental and Powder, Active | 23 | 7 | 16 | 0 |
| 59 | Reducing Agents, Weak | 19 | 4 | 14 | 1 |
| 14 | Amines, Phosphines, and Pyridines | 18 | 12 | 6 | 0 |

**8개 실측빈도그룹(40/41/42/50/51/58/59/68) 합계: 305/426 = 71.6%** — 재설계 문서가
CSV 단일배정 기준으로 계산했던 70%(301/427)와 비슷하지만, true-membership 기준이라
약간 더 높다.

**새 발견 — Wave2의 "숨은 spillover"**: 그룹61(Salts, Basic, 55종)과 그룹60(Salts,
Acidic, 43종)은 **애초에 Wave2가 목표한 8개 그룹(40/41/42/50/51/58/59/68) 어디에도
속하지 않는다**. 그런데도 각각 40종·31종이 wave2로 편입돼 있다 — 이는 Wave2가 "그룹
50/51/58/59/68 등에 넣은 물질 중 다수가 동시에 Salts, Basic/Acidic 그룹에도 속해서"
생긴 부수효과다(다중 그룹 소속). 즉 Wave2는 "8개 그룹만 확장한다"고 선언했지만 실제
데이터셋에 미친 영향은 8개 그룹보다 넓다 — §1-3(재설계 문서)이 지적한 "실측 빈도 →
그룹 전체 편입"의 비약이 그룹61/60처럼 **의도하지 않은 그룹**까지 부풀리는 2차
효과를 냈다는 뜻이다.

---

## 4. selection_status 분류 규칙 (재현 가능하도록 명시)

우선순위 순서대로 첫 번째로 해당하는 규칙 적용(코드: `provenance_audit.py`
`# 3) selection_status 분류` 섹션):

1. `original_candidate_source == 'curated_curriculum'` → **KEEP_MANDATORY**
2. `wave != 'wave1'` 이고 평가셋(`gold_*.jsonl`)에 CAS 등장 → **KEEP_MANDATORY**
   (Wave1은 순환논리 방지로 제외, §1 참고)
3. 소속 true 그룹 중 하나라도 전체 대표물질 수 ≤2 → **KEEP_COVERAGE**
4. `source in (reactive_basics_tier1, reactive_basics_tier2)` → **KEEP_EMPIRICAL**
5. `source in (pool_replacement, pool_replacement_v2, pool_replacement_v3_manual)` →
   **REVIEW**
6. `source == reaction_frequency_high` → 잠정 **REVIEW**, 이후 signature(=true
   그룹조합)가 동일한 다른 reaction_frequency_high 물질이 있으면 그중 CAS 사전순
   1개만 REVIEW로 남기고 **나머지는 DUPLICATE**로 재분류(그룹매트릭스 엔진 관점에서
   두 물질이 완전히 같은 그룹조합에 속하면 다른 모든 물질과의 판정 결과가 100%
   동일하므로 — 임의의 개수 기준이 아니라 수학적 사실)
7. `source in (pool_supplement, pool_topup)` → **UNSUPPORTED**
8. 그 외(발생 안 함) → **UNKNOWN**

---

## 5. Section 10 Coverage — 서로 다른 3개의 실측치가 존재함 (요청 보고사항 6)

§10 "피해야 할 물질" 원문을 직접 열어보면 대부분 **개별 화합물명이 아니라 GHS 위험군
카테고리 명칭**이다 — 예: `가연성 물질, 환원성 물질`, `금속|물`, `자료없음`. 특정
화합물명이 그대로 적힌 경우는 이번 감사(426종 전수, §7 참고)에서 **0건**이었다. 이
사실이 아래 세 실측치가 왜 서로 다른지를 어느 정도 설명한다 — 키워드 정의(어떤
문자열을 "물"/"금속"으로 셀지)에 따라 결과가 크게 흔들리는 구조다.

| 출처 | 표본 | 키워드 정의 | 물(water) | 금속(metal) | 가연성/환원성 |
|---|---:|---|---:|---:|---:|
| `docs/decisions.md` §1.2a-upd | 197종 | 리터럴 "물"/"금속" 단순 포함 | **55.3%**(109/197) | **22.3%**(44/197) | 측정 안 함 |
| `expand_by_reaction_frequency.py` docstring | 204종(명시) | 미문서화(스크립트 자체엔 계산 코드 없음, 주석에 결과만 인용) | **23.0%** | **34.9%** | **47.6%** |
| **이번 감사(재현 가능)** | 426종(collected 전체) | `가연성/환원성/환원제/인화성`, `금속`, `물`, `산화제/산화성`, `자료없음` — 코드에 명시(§10_CATEGORIES) | **58.9%**(251/426) | **23.2%**(99/426) | **47.4%**(202/426) |

세 수치 중 특히 "물" 항목이 55.3% / 23.0% / 58.9%로 **최대 2.5배 차이**가 난다.
`expand_by_reaction_frequency.py`의 23.0%는 코드 어디에도 계산 로직이 없이 주석에만
인용돼 있어 **재현이 불가능**하다 — 이번 감사가 이 불일치를 처음으로 명시적으로
드러낸 것이다. **이 문서의 47.4%/23.2%/58.9%(가연성·금속·물)를 앞으로의 단일
기준선으로 채택할 것을 제안한다** — 계산 코드가 스크립트에 그대로 남아있어 재실행
때마다 같은 값이 나온다.

추가로 `no_data`("자료없음") 비율이 **36.2%(154/426)**로 상당히 높다 — 즉 collected
426종 중 1/3 이상은 §10 자체에 실질적 위험관계 정보가 없다. 이 비율 자체도 이후
"§10 실측 기반 선정"이 원리적으로 커버할 수 있는 상한을 시사한다(자료없음 물질은
애초에 실측으로 편입 근거를 댈 수 없음).

---

## 6. Risk-pair Coverage (요청 보고사항 3의 risk-pair, 6의 일부)

두 가지를 분리해서 측정했다(하나만 보면 오독 위험이 있어 반드시 함께 본다).

### 6-1. 그룹매트릭스 기반 (`compatibility_pairs`/`self_reactivity` 재사용)

collected 426종 전수 쌍 C(426,2) = **90,525쌍** 전부에 대해 `compatibility_engine.py`와
동일한 worst-case 로직(그룹조합 전수평가)으로 판정:

| 판정 | 건수 | 비율 |
|---|---:|---:|
| Incompatible | 67,678 | 74.76% |
| Caution | 14,509 | 16.03% |
| Compatible | 8,338 | 9.21% |
| Abstain(그룹쌍 매트릭스 값 없음) | 0 | 0.00% |

**해석 주의**: 이 수치를 "위험관계 커버리지가 90% 넘는다"로 읽으면 안 된다. 68×68
CAMEO 매트릭스 자체가 원래 조밀해서(대부분의 그룹조합이 Incompatible/Caution),
아무 물질 426개를 무작위로 뽑아도 이와 비슷하게 높은 Incompatible 비율이 나올
가능성이 크다. 이 지표 단독으로는 "우리가 잘 골랐다"를 증명하지 못한다 — 그래서
아래 6-2를 별도로 계산했다.

### 6-2. §10 텍스트 교차검증 기반(더 보수적·직접적인 근거)

쌍(A,B) 중 **A의 §10 카테고리가 B가 실제로 속한 그룹의 위험관계와 일치**하거나
그 반대인 경우만 "text_evidenced"로 카운트(카테고리→위험관계 매핑:
`combustible_reducing→reducer`, `metal→metal`, `oxidizer→oxidizer`, `water→water`).

- text_evidenced 쌍: **33,513 / 90,525 = 37.02%**
- 그룹매트릭스가 Incompatible로 판정한 67,678쌍 중, §10 텍스트로도 직접 뒷받침되는
  것은 **26,420건(39.04%)뿐**.

**결론**: "그룹매트릭스상 Incompatible"이라는 판정의 약 61%는 CAMEO 그룹 분류
자체에서 나온 것이지, 우리가 실제로 수집한 개별 물질의 §10 텍스트가 그 관계를
직접 증언하고 있는 건 아니다. 이건 데이터셋의 결함이 아니라 **CAMEO 매트릭스와
개별 MSDS §10 텍스트가 서로 다른 정보원**이라는 구조적 사실이지만, "risk-pair
coverage"를 보고할 때 반드시 두 수치를 함께 제시해야 과장되지 않는다.

### 6-3. 물질명 직접 매칭(요청된 "물질A ↔ 특정 물질B" 형태) — 계산 불가로 판명

원 요청은 `substance A ↔ incompatible substance B` 형태의 구체적 물질쌍 커버리지를
요구했다. 426종 전체 §10 텍스트에서 서로의 화학물질명(CSV `chemical_name`, `;`로
분리된 동의어 포함, 2자 이상)이 문자 그대로 등장하는지 전수 대조했으나 **히트 0건**
이었다. §10 원문 자체가 개별 화합물명이 아니라 GHS 카테고리 명칭 위주로 채워져
있기 때문(§5 참고)이며, 이는 우리 코드의 결함이 아니라 KOSHA MSDS 데이터 자체의
기재 관행이다. **따라서 이 형태의 risk-pair coverage는 현재 데이터로는 원천적으로
측정 불가능하고, 6-1/6-2의 그룹·카테고리 레벨 대리 지표로 대체해야 한다** — 이
사실 자체를 Phase 2/3 설계에 반영할 것.

---

## 7. 평가데이터(Testset) Coverage

- `gold_pair.jsonl`+`gold_pair_abstain.jsonl`+`gold_retrieval.jsonl`+`gold_abstain.jsonl`
  전체에 등장하는 고유 CAS: **230개**
- 그중 현재 collected 426종에 포함: **196개(85.2%)**
- 현재 candidate CSV(475행) 어디에도 없는 CAS(=평가셋이 참조하지만 지금은 존재하지
  않는 물질, 예: `100-19-6`, `100-27-6`, `100-38-9` 등): **34개** — Wave1 이후
  `pool_replacement*`로 대체되며 CSV에서 빠진 원 후보들로 추정(교차검증은 Phase 2
  과제로 남김).
- **Wave2(223종) 중 평가셋에 등장하는 CAS: 0개.** 즉 현재 Stage4 RAG 평가 파이프라인은
  Wave2로 추가된 223종(전체의 52%)을 **전혀 평가하지 않고 있다.** `HANDOFF.md`
  "Stage4는 198~203종 기준 빌드, 재구축 필요 여부 판단 보류"가 실측으로 확인된 셈 —
  PHASE 5(Retrieval 재평가) 전에 평가셋 자체를 426(또는 그 이상) 기준으로 재생성하지
  않으면, 재평가는 데이터셋 개선의 52%를 측정하지 못한다.

---

## 8. Group 25 (Diazonium Salts) 원인 분석 (요청 보고사항 5)

- 현재 426종 내 true 대표물질: **0**
- CAMEO 전체 풀(3,396종)에서 그룹25에 속한 화합물 자체가 **5개뿐**:
  `135072-82-1`, `15005-97-7`, `15557-00-3`, `21723-86-4`, `4421-50-5`
  (전부 아연 착염 디아조늄 염료/안료 중간체 — 매우 좁고 산업 특화된 하위군)
- 이 중 `135072-82-1`, `15005-97-7`은 KOSHA 조회를 **실제로 시도했고 미등록으로
  확인**됨(`msds_chem_id_cache.chem_id IS NULL`)
- 나머지 `15557-00-3`, `21723-86-4`, `4421-50-5` 3종은 **한 번도 조회 시도된 적이
  없음**(캐시에 행 자체가 없음)

**결론**: Group 25 미커버는 "선정 과정의 실수"가 아니라 **① CAMEO 68그룹 체계
자체에서 이 그룹의 화합물 다양성이 원래 극히 낮고(전체 풀에 5개뿐), ② KOSHA
등록 여부가 산업용·특수 안료 중간체 특성상 낮을 가능성이 높으며(2/5 이미 확인된
미등록), ③ 나머지 3종은 아직 시도조차 안 된 순수한 미착수 상태**의 조합이다.
"68개 그룹을 반드시 다 채워야 한다"고 단정하지 않는 이번 감사의 원칙에 따라, Group
25를 억지로 채우는 것이 실제 가치가 있는지(이 위험관계 유형이 학부 실험·평가
범위와 관련 있는지)를 Phase 2에서 먼저 판단할 것을 제안한다 — 무조건 3종을 마저
시도하기보다, "Diazonium Salts라는 위험관계가 이 프로젝트 스코프에 실제로
필요한가"를 먼저 묻는 게 순서에 맞다.

---

## 9. Coverage Gap 후보 목록 (요청 보고사항 8, Backfill 후보 — 자동 편입 안 함)

대표물질 ≤2종인 그룹 **14개**를 대상으로, candidate CSV에 없는 후보를 그룹별 최대
5개까지 뽑았다(`chemical_selection_backfill_candidates_2026-08-08.csv`, 총 66행).

| group_id | group_name | 현재 true 대표 수 |
|---:|---|---:|
| 10 | Alkynes, with Acetylenic Hydrogen | 1 |
| 11 | Alkynes, with No Acetylenic Hydrogen | 1 |
| 20 | Carbamates | 2 |
| 22 | Chlorosilanes | 1 |
| 23 | Conjugated Dienes | 1 |
| 25 | Diazonium Salts | 0 |
| 30 | Fluorinated Organic Compounds | 1 |
| 36 | Insufficient Information for Classification | 1(*실질 카테고리 아님 — 백필 대상에서 제외 권고) |
| 37 | Isocyanates and Isothiocyanates | 2 |
| 44 | Nitrides, Phosphides, Carbides, and Silicides | 1 |
| 48 | Not Chemically Reactive agents | 2 |
| 52 | Oximes | 1 |
| 57 | Quaternary Ammonium and Phosphonium Salts | 2 |
| 62 | Siloxanes | 2 |

66개 후보 중 **61개는 KOSHA 조회를 아직 시도조차 안 했고(`not_attempted`)**, 5개는
이미 시도해서 미등록으로 확인됨(`abstain_not_found`). 즉 이 영역은 "후보가 없어서
못 채운 것"이 아니라 **"후보는 있는데 아직 KOSHA 조회를 안 해본 것"**이 대부분이다.

---

## 10. 구현/검증 (요청 보고사항 10)

- 신규 스크립트: `02_classification/provenance_audit.py` (단일 파일, 표준 라이브러리만
  사용 — `sqlite3`/`csv`/`json`/`collections`, 추가 의존성 없음)
- **원본 미변경 검증**: `01_collection/undergrad_target_chemicals.csv`(mtime
  2026-08-08 09:40)·`reactivity_reference.db`(mtime 2026-08-08 09:50)는 이번 세션의
  감사 스크립트 실행 시각(10:46 이후)보다 먼저 수정된 상태 그대로다 — 스크립트는
  `SELECT`만 실행하고 `INSERT`/`UPDATE`/`csv.writer`를 원본 경로에 연 적이 없다(코드
  검토로 확인 가능: `CSV_PATH`/`DB_PATH`는 읽기 전용으로만 참조되고, 쓰기는
  `OUT_AUDIT_CSV`/`OUT_BACKFILL_CSV`라는 별도 신규 파일 경로에만 수행).
- 산출물 2종은 전부 날짜가 들어간 새 파일명으로 생성(`*_2026-08-08.csv`) — 기존
  파일을 덮어쓰지 않음.
- 재현 방법: `python 02_classification/provenance_audit.py` (DB/CSV 경로는 스크립트
  상단 상수, 별도 인자 없음). 재실행해도 같은 입력이면 같은 출력이 나오는 결정론적
  스크립트(임의성 없음, 정렬은 CAS 사전순 고정).

---

## 요약 — 다음 세션(PHASE 2) 판단을 위한 근거

1. **UNSUPPORTED(127) + DUPLICATE(131) = 258종(60.6%)**이 "제거해도 되는지 판단이
   필요한 후보군"이다. 단, 이번 감사는 **제거를 권고하지 않는다** — "근거 없음 ≠
   불필요함" 원칙(HANDOFF 지시)에 따라 PHASE 3에서 leave-one-out coverage 손실
   측정이 먼저다.
2. **Group 25(0종)** + **13개 추가 scarce 그룹(≤2종)**이 PHASE 2 후보 생성의 우선
   대상이다. 후보 66개 중 61개가 KOSHA 조회조차 안 된 상태라 "물질이 없어서"가
   아니라 "아직 안 해봐서" 미충족인 경우가 대부분.
3. **§10 Coverage 실측치 3종 불일치(55.3%/23.0%/58.9%)**를 이번 감사의 47.4%/23.2%/
   58.9%로 통일할 것을 제안 — 계산 코드가 보존돼 재현 가능한 유일한 버전.
4. **평가셋(gold_*)이 Wave2(223종, 전체의 52%)를 전혀 커버하지 않는다** — PHASE 5
   전에 평가셋 재생성이 선행돼야 "물질 선정 개선이 실제로 Retrieval 성능에 기여했는가"
   를 측정할 수 있다.
5. **risk-pair coverage는 "물질↔물질" 단위로 계산 불가**(§10 원문이 카테고리
   명칭 위주) — 그룹매트릭스(74.76% Incompatible, 그러나 원래 조밀해서 해석
   주의) + 텍스트교차검증(37.02% text_evidenced, 개별 근거 있는 부분만 카운트)
   두 지표를 병행 보고하는 방식을 이후 KPI로 고정할 것을 제안.
