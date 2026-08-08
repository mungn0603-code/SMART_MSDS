# 독립 평가셋(Independent Evaluation Set) 설계 — PHASE 4-F

**작성일**: 2026-08-08
**prototype 생성 스크립트**: [`04_rag_agent/independent_evalset_prototype.py`](../04_rag_agent/independent_evalset_prototype.py)
**prototype 산출물**: [`04_rag_agent/evalset/independent_eval_prototype_2026-08-08.jsonl`](../04_rag_agent/evalset/independent_eval_prototype_2026-08-08.jsonl)(50행)

기존 `04_rag_agent/evalset/gold_pair.jsonl`을 대체하지 않는다 — 그대로 유지하고, 이 문서는
그것과 별개의 **신규·독립** 평가 트랙 설계안이다.

---

## 1. 왜 필요한가 — 실측으로 확인된 문제

`evalset_pairs.py`(기존 gold_pair.jsonl 생성기)를 열어보면 후보 물질 목록을
`undergrad_target_chemicals.csv`가 아니라 **`rag_chunks` 테이블**에서 가져온다
(`select distinct cas_number from rag_chunks`). `rag_chunks`를 직접 세어보면:

```
rag_chunks distinct cas: 197
Wave2(reaction_frequency_high, 272종 시도분) 중 rag_chunks에 있는 것: 0
```

즉 Wave2는 `undergrad_target_chemicals.csv`(선정 CSV)에는 있지만 RAG 청킹
파이프라인(`04_rag_agent/pipeline.py`)이 Wave2 확장 이후 **한 번도 재실행되지
않아** `rag_chunks`에는 전혀 존재하지 않는다. 그 결과 `gold_pair.jsonl`은
구조적으로 Wave2를 평가할 수 없다 — PHASE 1~3에서 반복 확인된 "평가셋이 Wave1
파생"이라는 문제의 근본 원인이 바로 이것이다.

**이 발견의 실질적 함의**: 독립 평가셋을 만드는 것만으로는 부족하다. RAG
파이프라인 자체를 Wave2 포함 기준으로 재실행하지 않으면, 새 평가셋의 질의도
검색 결과를 얻을 수 없다(청크가 없으므로). 이 문서 §5에서 이를 Phase 5
선행조건으로 명시한다.

---

## 2. 독립성 원칙

**금지**: `selected chemical → gold pair 생성 → "gold pair에 등장하므로
selected chemical이 중요"`라는 역방향 정당화.

**허용**: 최종 dataset(선정은 이미 Phase 1~4에서 별도 근거로 완료됨) → 그 dataset을
대상으로 실제 검색 품질을 재는 evaluation item 생성 → **evaluation 결과를 selection
근거로 다시 끌어오지 않는다**(단방향 사용).

이번 prototype이 구조적으로 독립성을 확보하는 방법: 기존 gold_pair.jsonl이
Wave1 전용 소스(`rag_chunks`, 당시 197종)에서 파생된 것과 달리, 이 prototype은
**Wave2/reactive_basics가 최소 한쪽에 포함된 쌍만** 표집한다. Wave1이 갖고
있던 "선정 → 파생 → 재정당화" 경로 자체가 성립할 수 없는 물질들로만 구성했다.
각 레코드의 `independence` 필드로 명시적으로 추적된다(양쪽 다 wave1인 경우
`independence=false`로 표기해 혼동 방지 — 이런 레코드는 이번 prototype에
포함하지 않았다. 47/49쌍이 `independence=true`).

---

## 3. 최소 요건 5가지 충족 현황 (prototype 기준)

| 요건 | 충족 방법 | 실측 결과 |
|---|---|---|
| ① Wave independence | Wave2/reactive_basics 최소 한쪽 포함 쌍만 표집 | 49쌍 중 47쌍(95.9%) |
| ② Wave2 coverage | 위와 동일 — 기존 0%였던 Wave2 커버리지를 직접 해소 | 47쌍 |
| ③ Risk-pair diversity | Incompatible/Caution/Compatible(=hard negative) 3계층 각 최대 12쌍 표집(`pair_verdict` 재사용, 새 판정 로직 없음) | 카테고리별 최대 12쌍 |
| ④ Scarce-group coverage | Phase1/2가 확정한 13개 희소그룹(그룹25 제외) 각각에서 최소 1쌍 | **13/13 전부 포함** |
| ⑤ Negative/hard-negative | 매트릭스 판정이 Compatible(무해)인 쌍을 그대로 hard negative로 사용 — "위험 관련 어휘가 있어도 실제로는 무해하다고 정확히 판단하는가"를 테스트 | 최대 12쌍, `difficulty=hard_negative` 태그 |

Group25(Diazonium Salts)는 "가능한 범위에서 포함"이 원천적으로 불가능함을
확인했다(Phase2에서 5종 전부 KOSHA 미등록 재확인). 조용히 빠뜨리는 대신
`kind=unavailable_group`, `status=DATA_SCARCITY`인 명시적 스텁 레코드 1건을
포함시켰다.

---

## 4. 레코드 스키마

```json
{
  "query_id": "indep::{cas_a}::{cas_b}",
  "query": "...",
  "kind": "pair | scarce_group_pair | unavailable_group",
  "cas_a": "...", "cas_b": "...", "name_a": "...", "name_b": "...",
  "wave_a": "wave1|wave2|reactive_basics", "wave_b": "...",
  "cameo_groups_a": [...], "cameo_groups_b": [...],
  "gold_risk_pair": "Incompatible|Caution|Compatible",
  "gold_risk_pair_all": [...],
  "gold_section": ["sec::{cas}::{2|10}", ...],
  "retrieval_indexed": true/false,
  "difficulty": "normal|hard_negative",
  "source": "independent_eval_prototype_2026-08-08",
  "independence": true/false,
  "independence_reason": "...",
  "note": "..."
}
```

`gold_risk_pair`(매트릭스 판정)는 기존 `evalset_pairs.py`의 `pair_verdict()`를
**그대로 import**해서 계산했다(청킹/근거등급 로직 변경 없음 — 요청사항 그대로).
`gold_section`은 `rag_chunks`에서 조회하되, 없으면 빈 리스트를 두고
`retrieval_indexed=false`로 명시한다(아래 §5).

---

## 5. Retrieval 준비 상태 — Phase 5 선행조건

prototype 실행 결과:

```
총 레코드: 50 (Group25 stub 1건 포함)
Wave2 관여 쌍: 47
retrieval_indexed=True(즉시 검색평가 가능): 2 / 49
희소그룹 커버: 13/13
```

**retrieval_indexed=True인 쌍이 49개 중 2개뿐**이다 — 나머지 47개는 스키마·정답
라벨(매트릭스 기반 `gold_risk_pair`)까지는 완성됐지만, 실제 Hit@K/MRR을 측정하려면
그 물질의 §2·§10 텍스트가 `rag_chunks`에 청킹·임베딩돼 있어야 하는데 Wave2가
빠져 있어 지금 당장은 안 된다. **이건 이 평가셋의 결함이 아니라 RAG 파이프라인이
아직 Wave2를 반영하지 않았다는, 이번 조사로 명확해진 실제 blocker다.**

Phase 5 착수 전 필요한 선행 작업(이번 PHASE 4에서는 실행하지 않음, 범위 밖):
1. `04_rag_agent/pipeline.py`를 proposed final(또는 426 전체) 기준으로 재실행 →
   `rag_chunks` 갱신(현재 197종 → 259~426종)
2. FAISS 인덱스(`04_rag_agent/index/`) 재빌드
3. 재빌드 후 이 prototype을 재실행하면 `retrieval_indexed=True` 비율이 크게
   올라갈 것으로 예상(검증은 재실행 후 실측 필요 — 지금 추정치를 미리 주장하지 않음)

---

## 6. Retrieval Evaluation 준비 구조

Phase 5에서 그대로 쓸 수 있도록 다음 지표를 계산할 수 있는 형태로 스키마를
맞췄다(이번 PHASE 4에서는 실행하지 않음 — 구조만 준비):

- **Hit@1 / Hit@3 / Recall@K**: `gold_section`(정답 청크 ID 목록) vs 검색기 top-K 결과 비교
- **MRR**: 첫 정답 청크의 순위 역수 평균
- 기존 `run_ab.py`의 채점 로직(다중정답 채점)을 그대로 재사용 가능 — `gold_section`
  필드 이름과 형식을 기존 `gold_pair.jsonl`과 동일하게 맞춰뒀다(재사용을 위한
  의도적 설계).

**Selection vs Evaluation 분리 확인**: 이 문서와 prototype 어디에도 "이 쌍이
평가셋에 있으니 이 물질을 선정에 반영해야 한다"는 문장이 없다. 반대로 선정
CSV(`undergrad_target_chemicals.csv`, `*_proposed_final_2026-08-08.csv`)도 이
평가셋 파일을 참조하지 않는다 — 두 산출물은 서로를 모른다(단방향: 확정된 선정
결과 → 그 결과를 재는 평가셋).

---

## 7. 규모 확장 시 권고

이번 prototype은 스키마·독립성 검증 목적의 소규모(카테고리당 최대 12쌍)다.
전면 확장 시:
- `N_PER_BUCKET`을 늘리고 `QUERY_TEMPLATES`(기존 `evalset_pairs.py`의 5개 템플릿)를
  그대로 적용해 템플릿 다양성 확보(`docs/retrieval_query_diversity_review_2026-08-07.md`
  교훈 재사용)
- Wave1 관여 쌍(`independence=false`)도 일정 비율 포함해 "기존 gold_pair.jsonl 대비
  성능이 실제로 달라지는지"를 같은 조건에서 비교할 대조군으로 남길 것
- §5의 RAG 파이프라인 재실행을 먼저 완료할 것(선행조건)
