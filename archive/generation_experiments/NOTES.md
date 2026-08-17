# archive/generation_experiments — 정리 사유

Hazard/Reactivity Assessment(Generation) 단계에서 시도했다가 기각·대체된 접근법들.
채택된 최종 파이프라인(CAMEO 판정을 컨텍스트로 주입 + MSDS 근거로 설명, v5 프롬프트)은
[`docs/GENERATION.md`](../../docs/GENERATION.md) 참고. 코드와 그 코드가 만든 결과
파일을 세트로 옮겼다 — 코드만 있고 결과가 없으면(또는 반대) 왜 기각됐는지 재현할 수
없기 때문.

## 1. prompt v2 / v2.1 — 기각(rejected)
**사유**: 프롬프트만 수정해 over-abstention·물질혼동을 잡으려 한 접근. v2는 물질혼동은
잡았지만 정상 케이스의 과잉 Abstain 회귀(35건 파일럿에서 11/15)를 유발, v2.1로 완화해도
"개별 위험군 조합 규칙 근거로 판단 가능한 경우까지 회피"하는 근본 문제는 못 풂 — CAMEO
판정을 정답으로 미리 주는 구조 전환(v4)으로 대체.
- `run_v2_pilot.py` — v2/v2.1 프롬프트 생성·비교 스크립트
- `generation_v2_pilot.jsonl` / `eval_v2_pilot.jsonl`(v2), `generation_v2_1_pilot.jsonl` /
  `eval_v2_1_pilot.jsonl`(v2.1), `*_clean_spotcheck.jsonl`(정상 케이스 회귀 확인용)

## 2. CAMEO-context 파일럿 v1/v2/v2_soft — 폐기(superseded)
**사유**: v4(사용자 작성 프롬프트, CAMEO hazard code/gas product 원문 노출 + 번역만
허용)로 대체되기 전 단계의 프롬프트 반복. v1은 faithful 3/13, v2도 3/13, v2_soft(reason
뭉뚱그림)는 6/13 — v4는 judge 채점버그(CAMEO 근거 누락) 수정 후 13/13.
- `generation_cameo_pilot.jsonl`/`eval_cameo_pilot.jsonl`(v1),
  `generation_cameo_pilot_v2.jsonl`/`eval_cameo_pilot_v2.jsonl`(v2),
  `generation_cameo_pilot_v2_soft.jsonl`/`eval_cameo_pilot_v2_soft.jsonl`(v2_soft)

## 3. Cascade Judge(Rule→Small→Large fallback) — 기각(rejected)
**사유**: Large Judge(~9~14초/건) 비용을 줄이려 Small Judge(`meta/llama-3.1-8b-instruct`)로
1차 채점하는 구조를 검증했으나, Small Judge가 판정(category)은 Large와 잘 맞아도
faithful 판정에서 자주 어긋남(150~300건 검증, `judge_smoke_test_llama31_8b.jsonl`에서
`faithful_agree=false` 다수 관측) — 신뢰도 문제로 기각, 전수실행은 Large Judge 단독으로
진행.
- `cascade_judge.py` — Rule/Small/Large 라우팅 구현
- `validate_cascade.py` — 검증 스크립트
- `judge_smoke_test.py` — Small Judge 단독 스모크 테스트
- `judge_smoke_test_llama31_8b.jsonl`, `validate_cascade_llama31_8b_REJECTED_reference.jsonl`
  (파일명의 REJECTED는 이 검증 세션에서 그대로 붙인 것 — 결과 자체가 기각 판정의 증거)

## (부록) 정리 중 함께 옮긴 관련 파일
- `clean15_detail.txt` — prompt v2.1 baseline vs v2.1 답변 비교 상세(§1과 세트)
- `generation_cameo_pilot_v3.jsonl` — 채점(eval) 없이 생성만 된 미완성/미사용 파일럿
  산출물(v4로 바로 넘어가며 폐기)

## 4. RAGAS 지표 파이프라인 — 폐기(superseded)
**사유**: `ragas` 라이브러리로 Faithfulness/Context Recall/Context Precision/Answer
Relevancy를 측정하려 했으나(n=7 파일럿) 반복 세그폴트·연결오류로 15쌍 전체 확대를 못
마쳤고, 이후 `eval_generation.py`의 자체 Judge(rule_based + LLM judge, faithful/
predicted_verdict/substance_confused)로 대체되어 재개하지 않음.
- `generate.py` — RAGAS용 (question, answer, contexts, reference) 생성
- `rag_metrics.py` — RAGAS 4개 지표 채점(langchain_community 스텁 우회 포함)
- `rag_generation_sample.jsonl`, `rag_metrics.csv` — 위 파일럿 결과(n=7)
