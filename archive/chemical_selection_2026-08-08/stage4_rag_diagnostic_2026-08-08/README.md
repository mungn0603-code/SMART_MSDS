# Archive: Stage4 RAG Diagnostic Exploration (2026-08-08)

**STATUS: HISTORICAL / NOT AUTHORITATIVE**

`04_rag_agent/` 안에서 진행됐던 "426 vs 259(proposed/retrieval_aware) corpus 비교"
작업 흔적이다. 상위 `archive/chemical_selection_2026-08-08/README.md`가 명시한 원칙
(**Selection은 Retrieval Evaluation과 독립되어야 한다**)에 따라, retrieval
hit-rate/marginal-utility로 화학물질 선정을 재판정하려던 이 트랙 전체가 폐기됐다.
최종 authoritative selection은 `docs/chemical_selection_final_2026-08-08.md`
(173종, MANDATORY/HAZARD-RELEVANT/REPRESENTATIVE 3분류)이며 여기 있는 어떤 파일도
현재 corpus 구성에 쓰이지 않는다.

원래 상위 archive README(2026-08-08 작성 당시)는 "`04_rag_agent/phase5~8_*.py`는
Stage4 RAG 트랙 소재라 archive 대상에서 제외한다"고 명시했었으나, 후속 세션에서
재검토한 결과 이 파일들이 만들어내는 candidate set(426/259proposed/259_retrieval_aware
등) 자체가 동일한 "diagnostic evidence로 selection 재판정" 문제의 산출물이라
판단해 여기로 옮겼다.

## scripts/
- `phase5_426_vs_259_analysis.py` — 426 vs 259 corpus 5단계 공정 비교
- `phase6_selection_scenarios.py` — 후보군 A(426)/B(259)/C(259+RETAIN_RETRIEVAL)/D(C+RETAIN_COVERAGE)
- `phase7_candidate_comparison.py` — 독립 평가셋(150건) 기반 후보 비교
- `phase8_final_candidate_comparison.py` — 평가셋 확장 + marginal utility + A~E 최종 비교
- `independent_evalset_prototype.py` — 위 phase7/8이 쓰는 독립 평가셋 prototype 생성기

## evalset/
- `independent_eval_prototype_2026-08-08.jsonl`, `_v2_`, `_v3_` — 위 스크립트들의 평가셋 산출물

## results/
- `02_embedding_pair_sec210_259proposed.{csv,md}`, `_426.{csv,md}` — 426/259 corpus 각각의 retrieval 실측

## 남겨둔 것
`04_rag_agent/retrieval.py`/`pipeline.py`/`run_ab.py`의 `corpus_tag` 파라미터는
이 트랙에서 추가됐지만 범용 인프라(기본값 None = 기존 동작과 동일)라 코드에는 그대로
남겨뒀다 — 173종 확정 corpus를 위한 `corpus_tag` 태깅에도 그대로 재사용 가능하다.
