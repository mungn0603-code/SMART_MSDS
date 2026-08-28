# GENERATION — 답변 생성과 평가를 어떻게 했는가?

> **이 문서의 수치는 전부 `corpus_tag='173'` 평가 코퍼스 기준이다(2026-08-17).**
> 그 코퍼스는 2026-08-28에 서비스 범위에서 내려왔고, Retrieval은 2026-08-29에
> `corpus_tag='service'`로 재측정됐다([`RETRIEVAL.md`](RETRIEVAL.md)). Generation은
> **아직 service 기준으로 재실행하지 않았다** — 아래 정답률·faithful은 service의
> 지표가 아니다. 구조 전환(LLM 판정 → CAMEO-context 설명)의 효과를 보여주는 근거로는
> 유효하며, 인용할 때는 "173 평가 코퍼스 기준"을 반드시 함께 적는다.
> service 값을 얻으려면 새 평가셋(`data/evalset/gold_pair.jsonl`, 450쌍/2,250질의)으로
> `run_cameo_full.py`를 재실행해야 한다.

## 최종 결과 — 173 평가 코퍼스 (2,160건 전수, 2,142건 유효 채점)

| 지표 | STEP1~5 baseline(LLM이 직접 판정) | 최종(CAMEO-context, v4+v5) |
|---|---:|---:|
| 정답률 | 19.8% | **99.9%**(답변 판정줄 기준) / 93.6%(judge 재분류 기준) |
| Over-abstention | 46.1% | 1.9% |
| 과잉위험 오판(wrong) | 30.9% | — (구조상 해당 실패모드 소멸) |
| Faithful(근거 밖 주장 없음) | 측정 안 됨 | **97.2%** |
| 물질 혼동 | 관측됨 | **0/2,142** |

---

## STEP1~5 — 문제 발견

Retrieval baseline([`RETRIEVAL.md`](RETRIEVAL.md)) 위에서 실제 Generation 성능을
측정: STEP1(retrieval 결과 고정, `results/frozen_retrieval_top10.jsonl`) → STEP2
(baseline 프롬프트 확정) → STEP3(2,160건 생성) → STEP4(Judge 전체 채점) → STEP5
(Retrieval×Generation 분리분석, `scripts/analyze_generation.py`).

**핵심 발견**: Retrieval hit rate 98.84% — 병목이 아니었다. 실패의 77.9%가
retrieval 성공 상태에서도 Generation 단계에서 발생했다.

| 실패 유형 | 비율 | 원인 |
|---|---:|---|
| Over-abstain | 46.1% | 근거는 있지만 "쌍별 반응 명시 문장"이 없으면 회피. KOSHA MSDS가 물질별 문서라 "두 물질이 함께"를 직접 명시한 문장이 구조적으로 드묾(상대 물질을 직접 지목하는 §10은 0건) |
| Wrong(과잉위험) | 30.9% | 정답 Compatible/Caution인데 오답 306+282건 중 78~83%가 Incompatible로 과잉판정 — "개별 물질 위험문구"를 "쌍별 반응성"으로 오인 |
| Unfaithful(correct 중) | 15.2% | 판정은 맞지만 근거 밖 부연설명 추가 |

## 시도 1 — prompt v2/v2.1(기각)

프롬프트만 수정해 over-abstention·과잉위험을 잡으려 했다. v2는 물질혼동은
잡았지만 정상 케이스 회귀(15건 중 11건이 과잉 Abstain으로 됨)를 유발. v2.1로
"§10 위험군 매칭 같은 합당한 교차추론은 허용, 근거 없는 구체적 반응/생성물만
금지"로 완화해도 근본 문제(개별 위험군 조합 규칙으로 판단 가능한 경우까지 과도
회피)는 안 풀렸다. → 프롬프트 미세조정의 한계로 판단, 방향 전환.

## 핵심 전환 — CAMEO-context 주입

프롬프트가 아니라 **역할**을 바꿨다. CAMEO 반응성 그룹 조회(`src/cameo_group_lookup.py`)로
CAS 쌍의 판정을 조회하면 **2,160건 전수에서 실제 정답(matrix_verdict)과 100% 일치**한다
(`results/cameo_lookup_full_check.json`). 이미 신뢰할 수 있는 정답이 있다는 뜻이므로:

- LLM에게 판정을 맡기지 않는다 — CAMEO 판정을 프롬프트에 "이미 결정된 값"으로 박아 넣는다.
- LLM은 그 판정을 재판단하지 않고, MSDS §2/§10 근거로 **설명만** 한다.
- 채점(faithful)이 "설명이 근거를 벗어나지 않았는가"를 잡아낸다 — 판정이 맞다고 끝이 아니다.

파일럿(13건, 물질혼동 4/개별위험→상호반응 비약 4/정상 5)으로 프롬프트를
v1→v2→v2_soft로 반복: 물질혼동은 v2에서 0건으로 해소됐지만 faithful은 3/13→3/13→6/13에
머물렀다.

## 채점 버그 — judge가 CAMEO 근거를 못 봄

v2_soft까지의 faithful 실패를 들여다보니, 대부분이 진짜 환각이 아니라 **채점기의
맹점**이었다. `eval_generation.judge()`는 MSDS 청크만 "근거"로 보고 채점하는데,
CAMEO-context 파이프라인의 답변은 CAMEO의 실제 hazard code를 정당하게 인용한다 —
judge 입장에선 그 정보를 못 봐서 "근거 없는 주장"으로 오탐했다(`unsupported_claims`에
"CAMEO에 대한 언급이 근거에 없음"이라고 명시적으로 나옴). **생성기가 실제로 본
컨텍스트와 채점기가 보는 근거가 어긋난 채점 버그** — Retrieval 단계의 Evidence-level
버그([`RETRIEVAL.md`](RETRIEVAL.md))와 같은 계열.

수정: judge에 넘기는 근거에 `cameo_context`를 합성 청크(`__cameo_context__`)로
추가. 같은 13건을 재채점하니 **faithful 6/13 → 13/13**으로 뒤집혔다.

## v4(사용자 작성 프롬프트) — 정보를 숨기지 않고 번역 규칙으로 통제

이전까지는 CAMEO reason을 뭉뚱그린 문구(`CATEGORY_REASON`)만 노출했다(과거 파일럿에서
구체적 hazard code를 그대로 노출하면 어조가 과장되는 문제가 관측됐었기 때문). v4는
반대로 접근한다 — `cameo_group_lookup.format_context(..., detailed=True)`로 CAMEO의
실제 hazard code/gas product 원문을 노출하되, "번역만 허용, 의미 강화 금지"라는
명시적 변환 규칙(예: `"Generates heat"` → "열을 발생시킬 수 있음", 폭발로 확대 금지)을
프롬프트에 못박았다. 전수실행(2,142건 유효): 정답률 99.9%, **faithful 90.5%**(203건
unfaithful).

## v5 — 잔여 실패 표적 재시도

v4 전수실행에서 나온 203건 unfaithful을 표본 확인하니 공통 패턴: CAMEO reason은
"이 두 물질이 속한 **반응성 그룹**끼리의 분류적 위험 특성"인데, 답변이 이를 "이
두 특정 물질이 **실제로/확인된** 반응을 일으킨다"처럼 단정적으로 서술하고
있었다(예: "두 물질이 실제로 반응하여 수소 불화수소 가스를 발생시킨다는 구체적
근거가 없음"). 그룹 분류를 확인된 관찰로 오인하는 과확언. 프롬프트에 규칙
[3-1]을 추가해(나쁜 예/좋은 예 명시) 이 203건만 표적 재시도:

- 재시도 191건 성공, **74.3%가 faithful로 전환**(142/191)
- 성공한 191건만 원본 v4 전수결과에 병합(실패 12건은 기존 v4 답변 유지)
- 최종 corpus: 정답률 99.9%, **faithful 97.2%**(61건/2,142 unfaithful)

남은 61건도 같은 계열(그룹 분류를 확인된 반응처럼 단정)이지만 완전히 해소되진
않았다 — 프롬프트 지시만으로 100%를 만드는 데는 한계가 있다는 뜻으로 판단, 이
이상은 후속 세션 과제로 남김.

## 시도했다 기각한 것 — Cascade Judge

Large Judge(9~14초/건)가 느려서 Rule→Small(`meta/llama-3.1-8b-instruct`)→Large
fallback 구조를 검증했으나, Small Judge가 판정(category)은 잘 맞혀도 faithful
판정에서 Large와 자주 어긋남(150~300건 검증, `judge_smoke_test_llama31_8b.jsonl`)
— 신뢰도 문제로 **기각**, 전수실행은 Large Judge 단독으로 진행. 상세:
[`archive/generation_experiments/NOTES.md`](../archive/generation_experiments/NOTES.md).

## 인프라 — 동시실행 + 429 재시도

2,160건을 순차 실행하면 20시간+ 걸린다(생성+채점 평균 38초/건). Retrieval이 이미
고정돼 있어 이 구간은 순수 원격 API 호출뿐이라 스레드풀(`ThreadPoolExecutor`) 동시
실행이 안전했다 — workers=16에서 3.6초/건까지 단축(약 10배). 다만 **2시간 지속
부하에서 실제로 API 요청한도(HTTP 429)에 걸려 738건이 실패**했다 — 짧은 테스트(2~3분)에서는
안 나타난 문제. 기존 4회/최대 21초 재시도로는 스레드 다수가 비슷한 타이밍에 재충돌하는
thundering herd를 못 버텼다. 재시도 6회로 늘리고, `Retry-After` 헤더 우선 사용 + jitter를
추가해(`src/llm.py`) 재시도, workers=8로 낮춰 재실행 — 738건 전부 해소.

## 판정/채점 스키마

`src/eval_generation.py`가 두 갈래로 채점한다:

- **규칙 기반**(LLM 호출 없음): abstained(고정 문구 매칭), cited_chunk_ids, evidence_precision/recall
- **LLM Judge**(1회, 짧은 분류 호출): predicted_verdict, faithful, unsupported_claims

`answer_correct = predicted_verdict == matrix_verdict`(Abstain은 별도 집계).
`substance_confused`(cited_chunk_ids가 물질 A/B 어느 쪽에도 안 속하는 근거를
인용했는가)는 물질 혼동 진단용.
