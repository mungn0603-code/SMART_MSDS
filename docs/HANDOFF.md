# MSDS 위험성평가 자동화 — 핸드오프

**최종 갱신**: 2026-08-22 (§0-8: Registry 237종 확정 · KOSHA 상세 연동 · 물질명 일관성 ·
인덱스 23종 편입 · 질의 별칭 확장 · **CAMEO 매핑 142→173종 · B1 39종 청킹으로 A티어 173종**)

> **평가 파이프라인과 서비스 계층을 구분해서 읽는다.** §0-1~§0-7은 검색·생성·채점
> 파이프라인의 기록이고 여기 실린 지표는 그대로 유효하다(재측정하지 않았고, 평가
> 경로는 `corpus_tag='173'`을 계속 쓴다). 2026-08-22 작업은 **서비스 계층**
> (물질 선정·KOSHA 연동·앱)에 한정되며, 물질 선정의 현재 단일 출처는
> [`REGISTRY.md`](REGISTRY.md)다 — CORE 237종, 서비스 대상 198종.
> 경위는 [`PROJECT_LOG.md`](PROJECT_LOG.md)의 2026-08-22 항목.
**현재 단계**: Chemical Selection 173종 동결(§0-3), Retrieval baseline hybrid
Recall@10 0.9336 / MRR 0.9169 / Hit@10 0.9884(§0-5)에 이어, Generation 단계도
CAMEO-context 파이프라인으로 **정답률 99.9% / faithful 97.2%**까지 완료(§0-7,
상세는 [`GENERATION.md`](GENERATION.md)). 저장소 구조도 numbered stage 폴더에서
`src/scripts/data/results/docs/archive`로 재편했다(§0-7, [`FILE_GUIDE.md`](FILE_GUIDE.md)).
**남은 것**: faithful 잔여 실패 2.8%(61건), N종 조합의 RAG 검색 실측(현재는 쌍
단위까지만), 리랭커 미실행(보류 상태).

## 0-7. 2026-08-17 갱신: prompt v2 폐기 → CAMEO-context 전환 → 전수실행 → 문서·저장소 재편

§0-6이 지목한 over-abstention(46.1%)·과잉위험 판정(30.9%)을 prompt v2/v2.1로
고쳐보려 했으나 정상 케이스 회귀만 유발해 기각. 대신 CAMEO 반응성 그룹 조회가
matrix_verdict와 2,160건 전수 100% 일치함을 확인하고, **LLM이 판정을 직접 하지
않고 CAMEO 판정을 그대로 받아 MSDS 근거로 설명만 하는 구조**로 전환(v4, 사용자
작성 프롬프트). 이 과정에서 judge가 CAMEO 근거를 못 보고 채점하는 버그를 발견·
수정했고(같은 13건 파일럿이 6/13→13/13 faithful로 뒤집힘), 전수실행에서 나온
잔여 unfaithful 203건을 v5로 표적 재시도해 74.3% 회수했다. Cascade Judge(비용
절감 시도)는 신뢰도 문제로 기각, 전수실행 중 API 429 오류 685건은 재시도 로직
강화(backoff+jitter, workers 조정)로 전부 해소.

최종: 2,160건 중 2,142건 유효 채점, 정답률 99.9%(판정줄 기준)/93.6%(judge
재분류 기준), faithful 97.2%, 물질혼동 0건. 상세 경위·프롬프트 반복·실패 패턴
분석은 전부 [`GENERATION.md`](GENERATION.md)로 옮겼다(이 문서는 앞으로 "지금
어디까지 왔는가"만 간결하게 유지).

이어서 저장소를 `01_collection~05_evaluation` numbered 폴더에서
`src/`(재사용 모듈)·`scripts/`(실행 스크립트)·`data/`(DB·평가셋·캐시)·
`results/`(산출물)·`docs/`(당시 표준 문서 8종, 현재는 REGISTRY.md 포함 9종)·`archive/`(폐기·기각, 원위치 유지)로
재편했다. 기각된 실험(cascade judge, prompt v2, RAGAS 파이프라인)은
`archive/generation_experiments/`로, 흡수된 원본 상세 문서는
`archive/superseded_docs/`로 이동. 전체 경위·파일 매핑은
[`PIPELINE.md`](PIPELINE.md)/[`FILE_GUIDE.md`](FILE_GUIDE.md).

---

## 0-6. 2026-08-09~17 — STEP1~5: Generation·Judge·Retrieval×Generation 분리분석 (§0-7로 대체된 초기 결론)

**배경**: §0-5까지 확정된 Retrieval baseline 위에서, 실제 생성(Generation) 단계
성능을 측정하기 위해 STEP1~5를 진행했다. STEP1(Retrieval 결과 고정, 2,160질의
Hit@10=0.9884 재확인) → STEP2(Generation baseline prompt/model 확정, pilot 검증) →
STEP3(Generation 전체 실행, 2,160건 중 2,158건 정상/오류 2건) → STEP4(Judge 평가,
2,158건 전체를 Large Judge로 평가 — `meta/llama-3.1-8b-instruct` 대체실험 15건은
별도 진행했으나 최종 Judge로 미채택, 재실행 없음) → STEP5(`04_rag_agent/analyze_generation.py`
신규 작성, STEP3+STEP4 결과를 join해 Retrieval×Generation 분리분석). self-check
3건 3/3 통과, `bucket4()` 재계산과 저장된 라벨 100% 일치 확인.

**STEP5 핵심 수치** (`04_rag_agent/results/step5_summary.json`, n=2,158):

| bucket | 건수 | 비율 |
|---|---:|---:|
| evidence_retrieved__correct | 427 | 19.8% |
| evidence_retrieved__over_abstain | 995 | 46.1% |
| evidence_retrieved__wrong | 666 | 30.9% |
| evidence_retrieved__unclassified(judge 판정추출 실패) | 45 | 2.1% |
| no_evidence_retrieved__answer_or_abstain(retrieval miss) | 25 | 1.2% |

**해석 (원본 `generation_baseline.jsonl`/`eval_generation.jsonl` 재집계로 검증,
STEP5 로직·Judge 재실행 없음)**:
1. Retrieval은 병목이 아님 — hit rate 98.84%(2,133/2,158), miss 25건뿐.
2. 실패의 77.9%(1,661/2,133, `retrieval_success_generation_failure_ratio`)가
   retrieval 성공 상태에서도 Generation 단계에서 발생.
3. **over_abstain(46.1%, 최대 버킷)**: matrix_verdict 등급(Compatible/Caution/
   Incompatible)별로 44~49%로 고르게 분포 — 특정 위험등급 문제가 아니라 "쌍별
   반응 명시 문장이 없으면 근거가 있어도 회피"하는 일반화된 정책성 실패. 원인은
   KOSHA MSDS가 물질별(per-substance) 문서라 "두 물질이 함께일 때"를 직접 명시한
   문장이 소스 데이터에 구조적으로 드물다는 점(§0-3 STEP2에서 이미 "상대 물질을
   직접 지목하는 §10은 0건"으로 확인된 것과 같은 계열의 문제).
4. **wrong(30.9%)**: 방향성이 뚜렷함 — 정답 Compatible인데 오답 처리된 306건 중
   238건(78%)이 Incompatible로 과잉판정, 정답 Caution 오답 282건 중 233건(83%)도
   Incompatible로 과잉판정. 반대로 진짜 위험한 조합(Incompatible)을 안전하다고
   오판(false negative, 더 위험한 오류 방향)한 경우는 78건(전체의 3.6%)뿐. "개별
   물질의 위험문구(가연성·부식성 등)"를 "두 물질 간 실제 반응성"으로 오인해
   과잉위험 쪽으로 치우치는 편향으로 판단.
5. correct 버킷(427건) 중 65건(15.2%)은 최종 판정은 matrix_verdict와 일치했지만
   근거 청크에 없는 부연설명을 덧붙임(faithful=False) — 판정 로직보다 답변 생성
   과정의 근거 외 일반화 경향.
6. no_evidence(25건, 1.2%)는 표본이 작아 별도 결론 도출 안 함 — retrieval hit
   rate가 이미 98.84%라 전체 성능에 미치는 영향도 무시할 수준.

**정정**: 이전 세션 구두 보고에서 over_abstain/wrong 수치가 서로 바뀌어 전달된
적 있음(오기: wrong=995/over_abstain=666) — 본 절 수치가 `step5_summary.json`
원본 기준 정정판. "unclassified"(45건)도 "unfaithful-but-correct"가 아니라 judge가
`predicted_verdict`를 추출하지 못한 별개의 케이스(파싱/추출 실패)임을 확인.

**사용자 결정(2026-08-17)**: over-abstention을 prompt 수정(v2)으로 개선 시도.
진행 순서 — (1) 본 절로 결과표 아카이빙 완료 → (2) prompt v2 설계 → (3) 전수
재실행 없이 소규모 pilot으로 개선 확인(기존 `generation_v2_pilot.jsonl`,
`generation_v2_1_pilot.jsonl` 계열 인프라 재사용) → (4) 개선 확인되면 프로젝트
정리(README 등) → (5) 공개/발표자료.

**타협 불가 원칙 재확인**: v2는 "매트릭스 단독 최종판정 금지"·"근거 부족시
Abstain" 원칙(§2) 자체를 없애는 방향이 아니라, "개별 위험군 조합 규칙으로 판단
가능한 경우까지 과도하게 회피하지 않도록" 범위만 조정하는 것. wrong 방향(과잉위험
판정) 악화를 막는 가드레일을 v2 설계에 반드시 포함.

**산출물**: `04_rag_agent/results/step5_summary.json`,
`step5_failure_sample.jsonl`(35건 대표사례, 근거 원문 포함),
`step5_condensed_review.txt`(사람이 읽기 쉬운 버전),
`step5_clean_correct_sample.jsonl`(정답+faithful 15건 query_id).

---

## 0-5. 2026-08-09 갱신: 실패 사례 분석 → §10 penalty 범위 확장 (baseline 개선)

**목적**: §0-4로 Evidence 기준 채점이 정확해진 뒤, "실제로 개선할 문제가 있는가"를
판단하기 위해 baseline(hybrid, 2,160질의)에서 실패 사례(MRR 계산상 첫 정답 rank가
5 초과이거나 top20 안에도 없는 질의, 총 93건/2,160=4.3%)를 추려 상위 15건을 직접
확인했다.

**패턴 발견**: 대다수가 "정답 §2 청크는 코퍼스에 존재하지만, 같은 물질 또는 다른
물질의 §10 청크가 더 상위 rank를 차지해 밀려남"이었다(예:
`sec::7487-94-7::2::p1`이 gold인 질의에서 같은 물질의 `sec::7487-94-7::10`이 4위,
정작 gold는 top20 밖). §0-3 STEP2에서 이미 "상대 물질을 직접 지목하는 §10은 0건"이
확인돼 있었으므로 — 즉 **boilerplate 여부와 무관하게 §10 청크는 전부 gold_evidence가
될 수 없다** — 기존 penalty(정형문구 15종만 감점, §10 173개 중 144개만 해당)가
범위상 좁았다는 게 명확한 단일 원인이었다.

**검증(코드 수정 전 가설 테스트)**: `boilerplate_penalty_vector()`를 "§10이면 무조건
λ=0.01"로 넓혀 캐시된 벡터로 2,160질의 재채점 → 전 지표 동시 개선(악화 없음):

| Metric | 기존(정형문구 15종만) | 확장(§10 전체) |
|---|---:|---:|
| Recall@5 | 0.8118 | 0.8303 |
| Recall@10 | 0.9204 | 0.9336 |
| Recall@20 | 0.9676 | 0.9681 |
| Hit@5 | 0.9569 | 0.9644 |
| Hit@10 | 0.9866 | 0.9884 |
| MRR | 0.8352 | **0.9169** |
| nDCG@10 | 0.7912 | **0.8500** |

λ 값은 그대로 두고 적용 조건만 확장했다(파라미터 튜닝 아님). dense/bm25 단독 지표
(penalty 미적용)는 그대로였고 hybrid만 개선됐다.

**회귀(악화) 검증 — 범위를 명시**: "이 확장이 §2 검색을 망가뜨린 사례가 없는가"를
2,160질의 전체에서 1건씩 직접 대조했다(기존 penalty 결과 vs 확장 penalty 결과, 정답
첫 등장 rank 비교) — **개선 418건 / 동일 1,742건 / 회귀 0건**. 회귀가 0건인 것은
일반 법칙이 아니라 **현재 173종 코퍼스 + 현재 Gold Evidence 정의(§2 100%, §10 0%)라는
조건에서만** 성립하는 결과다: 이 조건에서는 penalty가 §10 청크 점수만 낮추고 §2
청크 점수는 전혀 건드리지 않으므로 §2끼리의 상대 순위가 바뀌지 않는다 — 그래서 이
실험 조건 안에서는 회귀가 나올 수가 없다. **Gold Evidence 정의가 바뀌어 §10이
정답에 포함되는 경우가 생기면 이 논리는 더 이상 성립하지 않으므로, 그때는 이
penalty를 다시 검증해야 한다.**

**코드 반영**: `retrieval.py`의 `boilerplate_penalty_vector()`를 "section==10이면
lam, 아니면 0"으로 단순화(정형문구 값 매칭 로직·`_load_boilerplate_values()`·미사용
`re` import 제거). `boilerplate_sec10_values.json`은 삭제하지 않고 보존 — 코드가
더는 읽지 않지만 "173종 중 정형문구 15종이 무엇이었는지"의 실측 기록으로 남긴다.
production 코드(`run_ab.py embedding --models bge-m3-ko --granularity section
--task pair --sections 2,10 --corpus-tag 173`)로 재현한 결과가 가설 테스트 수치와
정확히 일치함을 확인.

**현재 baseline(최신)**: hybrid Recall@5=0.8303 / Recall@10=0.9336 / Recall@20=0.9681
/ Hit@5=0.9644 / Hit@10=0.9884 / MRR=0.9169 / nDCG@10=0.8500 (2,160질의, 15건
no-gold-evidence 제외). 남은 실패(약 3.6%)는 §10 penalty로 해소되지 않는 다른
유형(예: 짧은 §2 텍스트 대비 무관 물질의 §10 텍스트가 여전히 우세, 희귀 금속류
질의에서 정답 물질 자체가 top20 밖) — 리랭커 없이 저비용으로 잡을 수 있는 범위는
이번 수정으로 소진됐다고 판단, 추가 개선은 후속 세션 판단 필요.

---

## 0-4. 2026-08-09 갱신: Evidence-level Hit 판정 버그 발견·수정 (검증 세션, 재설계 아님)

**배경**: §0-3이 "production 코드 경로로 재현한 최종 수치"라고 적어둔 Evidence 기준
표(Recall@10 0.9204 등)를 신뢰하기 전에, Hit 판정이 실제로 `gold_evidence`(§2 GHS
분류 등 진짜 근거) 기준인지 아니면 `gold_section`(§10 boilerplate/review-required
청크까지 포함) 기준인지 코드로 직접 확인하는 것이 이번 세션의 목적이었다.

**발견**: `run_ab.py:104` `prepare()`가 `key = "gold_item" if gran=="item" else
"gold_section"`으로 하드코딩돼 있어, `gold_pair.jsonl`에 이미 존재하는 `gold_evidence`
필드를 전혀 참조하지 않았다. 즉 **§0-3이 "코드로 재현했다"고 적은 수치는 실제로는 그
커밋된 코드로 재현되지 않는 상태**였다 — 채점은 여전히 `gold_section` 기준으로
동작했고, 이 필드에는 §10의 무근거 청크(예: `REVIEW_REQUIRED`, `NO_DIRECT_MSDS_EVIDENCE`)가
정답으로 섞여 있어 "같은 물질의 무관한 §10 청크가 검색돼도 Hit"으로 잘못 셀 수 있는
구조였다.

**샘플 검증(5건)**: hybrid top-1을 직접 뽑아 대조한 결과 5건 중 2건에서 실제로 재현됨
(`sec::7697-37-2::10`=REVIEW_REQUIRED, `sec::60-00-4::10`=NO_DIRECT_MSDS_EVIDENCE인
청크가 기존 코드 기준으론 Hit, evidence 기준으론 MISS).

**수정**: `prepare()`에 4줄만 추가 — `gold_evidence` 필드가 있으면 그걸 정답으로 쓰고,
없는 gold(예: `gold_retrieval.jsonl`의 fact task)는 기존 동작 그대로 유지(하위호환).
구조 변경·파라미터 튜닝·재설계 없음.

**재계산 결과 — 수치는 바뀌지 않았다**: 수정된 코드로 173종/2,175질의(2,160질의 유효,
15건은 gold_evidence 없음)를 캐시된 임베딩·BM25로 재채점한 결과, hybrid
Recall@5=0.8118/Recall@10=0.9204/Hit@5=0.9569/MRR=0.8352/nDCG@10=0.7912로 §0-3이 이미
문서화해둔 Evidence 기준 수치와 **소수점 4자리까지 정확히 일치**했다. 즉 §0-3의
결론(baseline 수치) 자체는 옳았다 — 다만 그 수치를 실제로 재현하는 코드가 커밋되지
않은 채 문서에만 남아있던 것이 문제였다. 저장 산출물
`results/02_embedding_pair_sec210_173.{csv,md}`는 재실행 전까지 실제로는
`gold_section` 기준 옛 수치(n=2175, dropped=0, Recall@10=0.8688, MRR=0.9806 — 이건
Section 기준 표 값과 일치)를 담고 있었고, 이번 세션에서 Evidence 기준 값으로
재생성해 문서와 저장 파일을 일치시켰다.

**결론**: baseline 수치는 유지, 코드만 수정. §0-3의 "production 코드 경로로 재현한
최종 수치"라는 서술은 이제 실제로 참이다.

---

## 0-3. 2026-08-08 갱신: Stage 4 RAG — 173종 Dataset Freeze + Gold Evidence 재정의 + Retrieval 최종 baseline (전체 완료)

**배경**: 이 세션은 "①Chemical Selection 완료 → Gold Evidence 확정 → Evaluation Logic
→ Baseline Retrieval" 순으로 진행하라는 continuation 프롬프트로 시작했다. 그런데 실제
저장소 상태를 먼저 확인해보니 전제가 어긋나 있었다 — §0-2(CAMEO 트랙)와 **같은 날, 그
이후에** 화학물질 선정 기준 자체가 재설계되어 **173종으로 재동결**된 상태였고
(`archive/superseded_docs/chemical_selection_final_2026-08-08.md`, MANDATORY 30/HAZARD-RELEVANT 129/
REPRESENTATIVE 14), 그 근거가 바로 "Selection은 Retrieval Evaluation과 독립되어야
한다"는 원칙이었다(과거 `259proposed`/`phase6_D`/`phase7_D`/`phase8_E` 등 retrieval
성능·marginal utility로 물질 수를 정당화하던 방식을 전부 폐기하고
`archive/chemical_selection_2026-08-08/`로 이동). **왜 먼저 확인이 필요했는가**: 이
사실을 놓치고 곧바로 Gold Evidence 작업을 시작했다면, 이미 폐기된 기준(426종/259종
등)으로 만들어진 산출물 위에서 작업하게 될 뻔했다.

### 1) 정리 — 폐기된 diagnostic 트랙 archive 이동
`04_rag_agent/phase5~8_*.py`, `independent_evalset_prototype.py`,
`independent_eval_*.jsonl`, `02_embedding_pair_sec210_{259proposed,426}.*` 등은 미커밋
상태로 남아있던 "426 vs 259 corpus retrieval 비교" 작업 흔적이었다. 위와 같은 이유
(retrieval 진단으로 selection을 재판정하는 방식 자체가 폐기됨)로
`archive/chemical_selection_2026-08-08/stage4_rag_diagnostic_2026-08-08/`로 이동.
**왜**: 상위 archive README가 이미 "왜 이런 시행착오를 거쳤는지 추적 가능하게 보존"
원칙을 세워뒀고, 같은 원칙을 Stage4 쪽 잔재에도 그대로 적용했다.

### 2) STEP 1 — Dataset Freeze (173종 corpus_tag 등록 + 재동기화)
`rag_corpus_membership`에 `corpus_tag='173'`을 등록(173종 전부 `rag_chunks` 커버리지
확인, 누락 0). `evalset_pairs.py`/`evalset.py`에 `--corpus-tag`(기본값 `173`) 옵션을
추가해 평가셋을 173종 기준으로 재생성: `gold_pair.jsonl` 435쌍×5템플릿=2,175질의,
`gold_pair_abstain.jsonl` 15쌍×5=75, `gold_retrieval.jsonl` 402건, `gold_abstain.jsonl`
357건.

**baseline 실측 결과가 기존(198종, Recall@10 0.9234)보다 낮게 나옴(0.8627)** — 원인을
파고들어 보니 retrieval 품질 저하가 아니라 **n_gold(정답청크 수)에 따른 구조적
아티팩트**였다: n_gold=4(분할 없음) 쌍만 보면 0.9278로 오히려 더 높고, §10이 여러
청크로 쪼개져 n_gold=5~6인 쌍만 낮다(0.69/0.55). 173종은 "§10에 구체적 근거가 있는
물질"을 선정 기준으로 삼았기 때문에(HAZARD-RELEVANT 정의) §10 텍스트가 길어서 분할되는
비율이 기존보다 높아진 것 — **선정 기준의 부수효과이지 검색기 결함이 아니다**. 이
진단을 근거로 baseline을 **그대로 동결**하기로 함(지표 정의를 바꿔서 숫자를 올리지
않음).

### 3) STEP 2 — Gold Evidence 재정의 (근본 원인 재발견)
26쌍 파일럿에서 §10 "피해야 할 물질" 텍스트를 실제로 읽어보니, **52개 물질 청크 중
90%가 5종 이하의 정형 문구 반복**이었다(예: `가연성 물질, 환원성 물질 / 금속`이 서로
무관한 물질들에 글자 하나 안 틀리고 반복). 173종 전체로 확대 확인한 결과도 동일 —
15종의 정형 문구가 173종 §10의 대다수를 차지하고, **상대 물질을 직접 지목하는 §10은
0건**이었다. **왜 문제였는가**: 기존 `gold_section`(문서/섹션 단위)을 그대로
"정답 근거"로 썼다면, 실제로는 아무 관계도 증명 못 하는 boilerplate를 evidence로
잘못 인정하는 셈이었다 — Document Hit과 Evidence Hit을 구분하자는 이 프로젝트의
핵심 원칙(§7 본문 도입부)이 바로 이 문제를 겨냥한 것이었는데, 기존 gold 정의는 그
구분을 못 하고 있었다.

최소 규칙(복잡한 ontology 안 만듦)으로 재정의: §2 GHS 분류는 항상 gold
(`HAZARD_CLASSIFICATION`), §10은 173종 안에서 2회 이상 반복 확인된 정형문구만
`BOILERPLATE`로 제외, 나머지는 `NO_DIRECT_MSDS_EVIDENCE`(자료없음) 또는
`REVIEW_REQUIRED`(1회만 등장해 정형 여부 자동판정 불가 — 억지 해석하지 않음, 173종 중
9개 물질/45쌍에서 발생). 435쌍/2,175질의 전체 적용 결과: `gold_evidence`가 기존
`gold_section` 평균 4.28개 → 1.88개로 축소, **그 중 100%가 §2 기반**. `gold_pair.jsonl`에
`gold_evidence`/`evidence_count`/`evidence_detail` 필드로 병합(원본은
`gold_pair.jsonl.bak_20260808_230337`로 백업 보존). 부수 발견: 티타늄·텅스텐·
사이클로헥사논옥심 3종의 §10 "분리 그룹(segregation group)" 필드값이 파싱 결함으로
비어있음 — evidence 정의 문제와 별개로 `04_rag_agent/pipeline.py`의 §10 서브필드
파서 확인이 필요한 채로 남겨둠(이번 세션엔 수정 안 함).

### 4) Evidence 기준 재평가 — Section 지표가 가려온 진짜 병목 발견
Evidence 정의로 처음 채점해보니 **Recall은 Section 대비 큰 차이가 없는데(@10
0.863→0.857) MRR·nDCG@10은 거의 반토막**(0.983→0.516, 0.866→0.567)이었다. **왜
이렇게 갈렸는가**: top-10 안에 정답이 있긴 있지만(Recall 유지), 1순위로 뜨는 건
대개 boilerplate 청크였고 진짜 evidence(§2)는 순위가 밀려 있었다 — Section 기준
평가는 "그 섹션 청크가 top-k에 있는가"만 보기 때문에 이 문제를 완전히 가리고
있었다. Hit@5도 0.9995→0.9264로 떨어져, **질의의 7%가량은 top-5 안에 진짜 evidence가
전혀 없었다**는 게 처음으로 드러났다.

### 5) STEP 3 — Retrieval 개선 실험 (reranker 없이 해결)
바로 리랭커를 붙이지 않고, 저비용 대안부터 검증:
- **실험1 Dense/BM25 weight sweep**: dense 비중을 올려도 Evidence MRR 개선폭이
  작고(0.516→0.538) Section Recall@10은 오히려 하락(0.863→0.842) — **폐기**.
- **실험2 Boilerplate penalty**(`adjusted_score = rrf_score - λ×boilerplate_flag`,
  STEP2에서 이미 확정한 정형문구 판정을 그대로 재사용, 새 classifier 없음): λ=0.01에서
  **Evidence MRR 0.516→0.835(+62%), nDCG@10 0.567→0.791(+39%)**, Section 지표는 오히려
  소폭 개선(Recall@10 0.863→0.869)되어 부작용이 없었다. λ=0.02는 더 좋아 보였지만
  Section Recall@10이 0.66까지 급락(boilerplate 청크가 아예 밀려남)해 채택하지 않음.

**왜 리랭커 대신 이걸 택했나**: 진단(§4)이 지목한 원인이 "BM25 어휘매칭이 정형문구를
과대평가한다"는 매우 구체적인 것이었고, penalty는 그 원인에 정확히 대응하는 최소
개입이었다. 근본 원인에 딱 맞는 저비용 수정이 이미 문제를 해소했는데 굳이 무거운
모델(리랭커)을 도입할 이유가 없었다.

**최종 baseline으로 코드에 반영**: `retrieval.py`에
`boilerplate_penalty_vector()`(정형문구 15종은 `boilerplate_sec10_values.json`에 고정
저장) + `rrf_fuse(..., penalty=...)` 파라미터 추가(미지정시 기존 동작과 완전 동일 —
하위호환), `run_ab.py`의 `_search()`가 hybrid 융합 시 기본으로 이 penalty를 적용하도록
연결. production 코드 경로로 재현한 최종 수치(173종/2,175질의):

| Metric | 기존 Hybrid | 최종 baseline(+penalty λ=0.01) |
|---|---:|---:|
| Evidence Recall@5 | 0.7292 | 0.8118 |
| Evidence Recall@10 | 0.8567 | 0.9204 |
| Evidence Hit@5 | 0.9264 | 0.9569 |
| Evidence MRR | 0.5157 | 0.8352 |
| Evidence nDCG@10 | 0.5671 | 0.7912 |
| Section Recall@10 | 0.8627 | 0.8688 |
| Section MRR | 0.9834 | 0.9806 |

실험 전체 기록은 `04_rag_agent/results/retrieval_experiments_{full.json,report.txt}`,
최종 비교표는 `04_rag_agent/results/step3_final_baseline_comparison.md`에 보존.

### 다음 세션 확인 필요
- **REVIEW_REQUIRED 46건(9개 물질)**: 의도적으로 미해결 상태로 남김(억지 해석
  금지 원칙) — 필요시에만 개별 검토.
- **§10 "분리 그룹(segregation group)" 파싱 결함**(티타늄/텅스텐/사이클로헥사논옥심):
  `pipeline.py` 서브필드 파서 확인 필요, evidence 결론에는 영향 없어 이번엔 보류.
- **`gold_pair_abstain.jsonl`(15쌍)은 173종 기준으로 재생성만 됐고 evidence 태깅은
  안 함** — abstain 정의(양쪽 J08 자료없음) 특성상 우선순위 낮다고 판단, 필요시 STEP2
  방식 그대로 적용 가능.
- **리랭커는 "불필요"가 아니라 "이번 단계 기준으론 보류"** — 향후 물질 수가 늘거나
  코퍼스가 바뀌면 재검토 여지 있음.
- 다음 단계는 ⑧ Hazard/Reactivity Assessment(Verified Evidence → 위험성 판정 로직).

---

## 0-2. 2026-08-08 갱신: CAMEO 데이터 소스 robots.txt 준수 전환 (전체 완료)

기존 `chemicals`/`chemical_group_membership`(3,386종/6,657행)은
`cameochemicals.noaa.gov` 검색 결과 페이지를 직접 스크레이핑해 확보한 것으로,
`robots.txt`의 `/search` 계열 disallow를 위반한 상태로 식별돼 있었다(비상업
포트폴리오 목적으로 사용 승인은 받았으나 방어 논리가 필요한 취약점으로 트래킹
중이었음). 이번 세션에서 대체 경로를 검증·전환·확대 실행까지 전부 완료했다.
상세 근거는 `archive/superseded_docs/decisions.md` §1.2b/§1.2c/§1.2a-upd, 실행 스크립트는
`01_collection/pubchem_verify_groups.py` + `02_classification/group_fallback.py`.

1. **경로 검증 (12종 파일럿 → 199종 → 3,396종 전체)**:
   - CAS→CID: 공식 PUG-REST(`/rest/pug/compound/name/{CAS}/cids/JSON`).
   - CID→CAMEO그룹: PubChem Classification Browser의 JSON 엔드포인트
     (`/classification_2/classification_2.fcgi?hid=86&...`) — PUG-REST 공식
     문서엔 없는 비공식 엔드포인트지만 robots.txt disallow 대상 아님(hid=86 =
     "CAMEO Chemical Reactivity Classification", 핸드오프 초안이 가정했던
     hid=80은 오답이었음 — 그건 현재 "PubChem BioAssay Classification").
   - **3,396종 전체 실행 결과**: MATCH 3,185 + 표기차이뿐인 사실상 일치 7 =
     **94.0%가 깨끗하게 재검증됨**. 나머지 6.0%(204종)는 진짜 결측(9, 전부
     "MIXTURE" 혼합물 표기 + 티오황산나트륨) + CID 조회 실패(195, 고분자·천연수지·
     광물·상표명·N.O.S. 총칭명 — PubChem의 "단일 이산 구조" 전제상 원리적으로
     색인 안 되는 범주, 우리 조회 로직 결함 아님).
   - robots.txt 재확인: `/classification_2/`는 전면 허용, `/rest/pug/`는
     `User-agent:*`에 명시적 disallow가 있으나 NCBI가 이를 PUG-REST라는
     이름으로 공식 문서화·요청제한정책까지 공개해 API 클라이언트 사용을 전제로
     운영한다는 점에서 "검색엔진 크롤링 차단"과는 통상 구분되는 사안 — 다만
     100% 무결한 주장은 아니라는 뉘앙스를 그대로 남겨둠(§1.2b).
2. **부수 발견·정정**:
   - UREA CAS 오류: DB·CSV 양쪽에 `497-19-8`(실제 탄산나트륨 CAS)로 잘못
     등록된 것을 발견 → 올바른 `57-13-6`으로 확인. 이미 스크레이핑 데이터에
     정확한 UREA(CAS 57-13-6)가 존재해 **완전 중복**이었음이 드러나 중복
     레코드(chemical_id 3398) 삭제.
   - 그룹명 표기 통일: PubChem 대조 중 그룹42("Metals, Less Reactive"),
     그룹48("Not Chemically Reactive")이 실제로는 각각 "...agents" 접미사가
     붙은 이름임을 발견해 정정(5종+7종 false mismatch 해소).
3. **그룹 대표물질 폴백 로직 구현**: `02_classification/group_fallback.py`
   `get_fallback_candidates()`. 특정 CAS의 데이터가 결측/조회실패일 때, 같은
   CAMEO 그룹 내 이미 KOSHA MSDS를 확보한 다른 물질을 대체 후보로 추천(최대
   3건). 199종 파일럿의 문제 10종 전부 즉시 대체 가능함을 확인 — 급한
   블로커 없음. 최종 반응성 판정 단계(`compatibility_engine.py`)의 Abstain
   원칙과는 별개 계층(수집 단계 전용).
4. **반응성 기본물질 풀 확장**: §1.2a("물·산소 등은 반응 상대로 자주 등장")의
   "실측 아님" 추정을 197종 §10 "피해야 할 물질" 텍스트 전수조사로 실제 측정 —
   **물 55.3%, 금속(포괄) 22.3%**, 나머지 키워드는 0%. 물이 실측 1순위임을
   확인하고 우선순위 6종(물·산소·질소·이산화탄소·수소·암모니아)의 KOSHA MSDS를
   전부 수집 완료(4개 섹션 전부). Tier2(CO2·수소·암모니아)는 PubChem 경로로
   CAMEO 그룹 매핑도 신규 확보(`chemicals` chemical_id 3399~3401).
   `01_collection/undergrad_target_chemicals.csv`에 `source=reactive_basics_tier1/2`로
   6행 추가, 기존 `kosha_msds_collector.py`를 코드 변경 없이 재사용해 수집.
5. **CAMEO 스크레이핑 원본 아카이브 이동**: robots.txt 위반 스크레이퍼
   (`scrape_cameo_chemical_groups.py`+테스트), 원시 출력(`cameo_chemical_groups.db`,
   9,231행), 시드 CSV 2종(`cas_reactive_group_mapping.csv`,
   `Cameo_reactivity.csv`)을 `archive/01_collection/`로 이동. 단, 이 두 CSV는
   `reactivity_reference.db`를 0부터 재빌드할 때 여전히 필요한 시드 입력이라
   완전 폐기하지 않고, `build_chemical_group_membership.py`·
   `seed_reactivity_reference.py`의 경로 상수만 아카이브 경로로 갱신(재현성
   유지). 상세는 `archive/01_collection/NOTES.md`.
6. **환경 이슈 기록**: 3,396종 전체 재수집(백그라운드, 40분)과 KOSHA 수집이
   동시에 DB에 쓰기를 시도하며 `database is locked` 충돌 반복 발생 →
   `kosha_msds_collector.py`의 `sqlite3.connect`에 `timeout=120`(busy_timeout)
   추가로 해결. **두 수집 스크립트를 동시 실행할 때는 이 타임아웃이 필요**하다는
   점을 기록해둠(향후 병렬 실행 시 재확인).

**PubChem 기반 CAS→CAMEO 재수집/교차검증 트랙은 이걸로 종료.** 이번 세션에서
검증→199종 실행→3,396종 전체 확대→폴백 로직→기본물질 풀 확장→구 스크레이핑
아카이브까지 전부 완결.

**추가: 타겟리스트 2차 확장 — 웨이브1 누락분 보강 (같은 날 후속)** — 웨이브1
(203종, tier 슬롯 기반)은 "68그룹 골고루 커버 + 교육 현실성" 기준이라 실제
반응 상대로 자주 등장하는 물질(금속·환원제·물 등)이 얼마나 실제로 자주
검색/등장하는지는 반영 못 했다. 이 빈틈을 메우려고 "그룹당 슬롯 채워 총원수
목표 달성"(200→380종, tier 기반) 방식 대신 "실측 반응 빈도 높은 그룹만 무제한
수집"으로 웨이브2를 추가(웨이브1을 대체한 게 아니라 웨이브1엔 없던 축을
더한 것). 근거: §1.2a-upd 실측(§10 "피해야 할 물질" 전수조사) — 가연성/환원성
47.6%, 금속 34.9%, 물 23.0%. 이 실측이
직접 가리키는 8개 그룹(금속 40/41/42, 산화제 50/51, 환원제 58/59, 물 68)만
PubChem 확정 풀 전체를 상한 없이 수집(`01_collection/expand_by_reaction_frequency.py`).
KOSHA 수집 결과: 시도 272종 중 426종 성공(4섹션 전부, 기존분 포함 누적)/49종
Abstain(KOSHA 미등록). **전체 수집 종수 203→427종**.
- **round2 안전필터 적용 안 함**: 신규 배치에 급성치사·CMR1급 물질이 섞여도
  거르지 않기로 결정 — 이 배치의 선정 이유 자체가 "위험 상대로 자주 지목됨"이라
  걸러내면 이 프로젝트 목적(반응성 위험 고지)과 충돌. round2 필터는 §1.2
  커리큘럼 대표성 축에만 유효(교육 현실성 문제였지 위험도 문제가 아니었음).
  상세는 `archive/superseded_docs/decisions.md` §1.2d.
- **미반영 — 다음 세션 확인 필요**: Stage 4(RAG) 파이프라인(청킹 805개 섹션,
  임베딩 인덱스, 평가셋 gold_pair 등)은 전부 **198~203종 기준으로 빌드된 상태**.
  종수가 203→427로 2배 넘게 늘었으니 재구축 필요 여부를 다음 세션에서 판단할
  것 — 이번 세션엔 실행 안 함(범위 밖 판단, 큰 작업이라 별도 확인 필요).

---

## 0-1. 2026-08-07 갱신: 청석면 제외 + 질의 템플릿 다양화 재측정

1. **청석면(12001-28-4) 제외**: 사용자 결단. CSV(200→199 유효 대상, 이하 198종 활성)·DB
   3테이블(40행)·평가셋 3종에서 제거. 근거 `decisions.md` §1.2a 인접 항목.
2. **질의 템플릿 단일→5개 다양화**: `archive/superseded_docs/retrieval_query_diversity_review_2026-08-07.md`
   에서 정답 청크 원문에 템플릿 단어("위험성" 51.6%, "취급" 42.7%)가 리터럴 중복됨을
   실측 확인, 어휘 편향 리스크 제기. `evalset_pairs.py`의 `QUERY_TEMPLATES`를 5개로
   확장(383쌍 × 5템플릿 = 1,915질의, 그중 4개는 "위험성"/"취급" 의도적 배제)해 재생성.
3. **재측정 결과** (hybrid, §2·§10 필터, 리랭커 미실행, 2026-08-07):

   | 지표 | 기존(단일템플릿 369쌍) | 신규(5템플릿 1,915질의) |
   |---|---:|---:|
   | Recall@10 | 0.9005 | **0.9234** |
   | Recall@5 | 0.7811 | 0.8166 |
   | MRR | 0.9986 | 0.9915 |
   | nDCG@10 | 0.8932 | 0.9104 |
   | Hit@5 | 1.0000 | 0.9995 |
   | 질의 임베딩 지연 | 501.724ms (목표 500ms 미달) | **368.009ms (목표 충족)** |

   **질의를 다양화해도 Recall@10·nDCG@10이 오히려 상승**했다 — 단일 템플릿 결과가
   어휘 중복으로 부풀려졌다는 가설과 반대 방향.
   질의 임베딩 지연 개선(501.7→368.0ms, 재현시행마다 368~395ms 범위)은 템플릿 문장이
   짧아진 평균 효과로 추정 — §4-4 목표는 이번 재측정으로 **충족 상태로 전환**됨(단,
   재측정 전제 조건이 바뀌어서 생긴 부수 효과이니 인코더 자체를 최적화한 결과는 아님).

   **템플릿별 개별 breakdown (383쌍 기준, hybrid, 383개 전용 재실행)** — 5개 중 2개만
   측정 완료, 나머지 3개는 환경 문제로 미완료(아래 참고):

   | 템플릿 | "위험성"/"취급" 포함 | Recall@10 | MRR | nDCG@10 |
   |---|---|---:|---:|---:|
   | t0(기존, 취급·혼합·위험성 포함) | 포함 | 0.9149 | 0.9974 | 0.8990 |
   | t1("같이 보관해도 안전한가요?") | 미포함 | **0.9503** | 0.9926 | **0.9347** |
   | t2~t4 | — | 측정 안 됨 | — | — |

   **어휘 편향 가설과 반대 결과**: 리터럴 중복 단어가 없는 t1이 기존 템플릿(t0)보다
   Recall@10·nDCG@10 모두 더 높게 나왔다. 표본 2개뿐이라 결론으로 단정할 수는 없지만,
   적어도 "단일 템플릿이 어휘 중복 덕에 부풀려진 숫자"라는 우려는 이 두 표본에서는
   기각되는 방향. t2~t4까지 마쳐야 확정 가능.

   **환경 문제 진단**: 같은 세션에서 `run_ab.py`를 반복 실행하면 재현되는
   Segmentation Fault(exit 139)를 총 5회 관측. 패턴은 "세션당 첫 실행은 항상 성공,
   바로 이어지는 재실행은 실패"— 프로세스 분리(subprocess)·25초 대기를 넣어도 실패가
   재현되어, 단순 OneDrive 파일 잠금 가설은 기각. `torch`/`FAISS`/`kiwipiepy`를 함께
   로드하는 상태에서 반복 프로세스 기동 시 Windows 쪽 자원(스레드 풀·DLL 핸들 등)이
   완전히 해제되지 않는 문제로 추정되나 근본 원인 미확인 — **후속 세션 과제**. 재실행이
   필요하면 매 실행 사이 텀(수 분 이상)을 두거나 재부팅 후 1회씩 실행 권장.
   시행 중 `gold_pair.jsonl`이 일시적으로 서브셋 상태로 남는 사고가 있었으나 즉시
   복구했고, 최종 확인 결과 1,915건(템플릿당 383건) 전체 정상 복원됨.
4. **원본 CSV(evalset_pairs.py) 재실행 결과 쌍 구성도 바뀜**: 198종 기준 재추출이라
   기존 369쌍(청석면 포함, per_category 150 상한)과 다른 383쌍이 됨(카테고리 분포
   Incompatible 135/Caution 128/Compatible 120). `gold_pair_abstain.jsonl`도 67쌍
   ×5템플릿=335질의로 갱신.

---

## 0. 이번 세션(2026-08-06 Stage 4) 결과 요약

Stage 4 §13 실행순서 1~4단계 중 **Retrieval 계층까지 완주**. 진행 중 설계 변경이 7건
발생했고, 전부 근거와 함께 **`archive/superseded_docs/stage4_design_changes_2026-08-06.md`** 에 아카이빙했다.
설계 원칙 문서(`stage4_design_principles_v2.md`)와 실제 구현이 다른 부분은 그 문서가 기준이다.

### 확정 구성

| 항목 | 확정값 | 근거 유형 |
|---|---|---|
| 임베딩 | `dragonkue/BGE-m3-ko` | **사용자 지정** (A/B 승자 아님) |
| 리랭커 | `BAAI/bge-reranker-base` | **사용자 지정**, 이번 세션 미실행 |
| 청킹 | section 단위 단독 (item 폐기) | 실측 + 구조적 논증 |
| 검색공간 | §2·§10 필터 (805 → 409청크) | **실측** — 정확도·속도 동시 개선 |
| 검색 | **hybrid** (dense+BM25 RRF, FAISS IndexFlatIP) | **실측** — 아래 재검토 이력 참고 |
| 평가 과제 | 물질 **쌍** 369건 | 설계 오류 정정 |
| LLM | NVIDIA NIM `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` | 사용자 지정 |

### 최종 실측 (bge-m3-ko / section / §2·§10 필터 / hybrid / 쌍 369건)

| 구간 | 지표 | 확정 목표 | 실측 | 판정 |
|---|---|---:|---:|:--:|
| 정확도 | **Recall@10** (핵심 KPI) | ≥ 0.89 | **0.9005** | 충족 |
| | MRR | ≥ 0.98 | 0.9986 | 충족 |
| | nDCG@10 | ≥ 0.88 | 0.8932 | 충족 |
| | Hit@5 | 1.00 유지 | 1.0000 | 충족 |
| 지연 | Embedding(질의) | ≤ 500ms | 501.724ms | 미달 |
| | Retrieval(검색) | ≤ 10ms | 6.281ms | 충족 |
| | Total (TTFT 전) | ≤ 600ms | 508.00ms | 충족 |

**7개 목표 중 6개 충족** (dense 채택 시 4/7이었던 것 대비 개선). 유일한 미달은
질의 임베딩 지연(501.724ms, 목표 500ms 대비 1.724ms 초과) — 검색 방식과 무관한
질의 인코더 자체의 문제(§4-4 참고).

참고: Recall@5 0.7811 / Recall@20 0.9409 (Recall@5는 참고치로 강등 — 쌍당 정답이 평균
4.1개라 5칸에 4개를 담아야 하는 구조)

> **검색 방식 재검토 이력 (2026-08-06, 같은 세션 내 정정)**
> 최초 결정은 dense 단독(레이턴시 사유). §2·§10 필터 적용 **후** 재실측하니
> hybrid가 7개 목표 중 6개 충족(dense는 4개), 레이턴시 차이 6.19ms는 사용자가 정한
> `Retrieval ≤ 10ms` 예산 안에 들어옴을 확인 → **dense 단독 결정을 철회하고 hybrid로
> 재채택**. `04_rag_agent/run_ab.py`의 `evaluate_reranker()`에 남아있던 dense 우회
> 코드(`h = d`)도 되돌려 실제 hybrid 후보가 리랭커 입력으로 들어가도록 수정.
> 상세 근거·이력은 `archive/superseded_docs/decisions.md` §2.4, `archive/superseded_docs/stage4_design_changes_2026-08-06.md` §5·§5-1.
> **리랭커 단계는 아직 미실행** — hybrid 후보 기준으로 리랭커까지 재검증하는 것은
> 다음 세션 과제.

---

## 1. 프로젝트 개요 (변경 없음)

- 목적: KOSHA MSDS Open API 데이터 기반, **화학물질 2종 이상 조합의 반응성·양립성**을
  RAG+Agent로 자동 평가하는 **포트폴리오 MVP**
- 작업 경로: `C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS`
- 제품 형태: 사용자가 **물질 2종 이상을 입력** → 상호 반응성·혼합 시 위험성·유의사항 제공.
  (단일물질 사실조회가 아니다 — 이번 세션에서 평가셋을 이 기준으로 전면 교체했다)
- **N종 조합 판정 구현됨** (`03_compatibility/compatibility_engine.py`
  `judge_combination_by_cas`): 모든 쌍 C(N,2)을 기존 쌍 판정으로 계산 후 worst-case
  종합 + 전체 쌍 매트릭스(`to_table()`) + 쌍별 상세 리포트(`pair_reports()`) 제공.
  상세 설계는 `decisions.md` §2.10.

## 2. 타협 불가 원칙 (변경 없음)

1. 양립성 매트릭스 조회 결과를 단독 최종 판정 근거로 사용 금지
2. CAMEO 최신 68그룹 체계 엄격 적용(구 EPA 41그룹 폐기)
3. 근거 부족 시 Abstain — 억지로 답변하지 않음
4. 근거 등급제: 법령(Mandatory) > 권고(Recommended) > 참고자료(Reference)
5. 서비스키·API키 원문은 코드/로그/응답 어디에도 노출 금지 — `.env` + 환경변수로만

**근거등급 판정 규칙 (2026-08-06 확정, 출처표기 기반 3분할)**
- 섹션2 (GHS분류·H/P코드 = 고용노동부고시 별표 확정문구) → **Mandatory**
- 섹션3·9·10 중 `※출처` 미표기 (KOSHA 작성값) → **Recommended**
- `※출처` 표기 항목 (HSDB·ECHA·ICSC 등 외부DB 인용) → **Reference**

## 3. 완료된 작업

### Stage 1~3 (이전 세션)
1. `reactivity_reference.db`: CAMEO 68그룹, 2,278쌍(오프대각), self_reactivity 68행
2. CAS↔CAMEO 매핑: `chemicals`(3,398종), `chemical_group_membership`(6,669행, 68/68그룹)
3. 200종 타겟 리스트: `01_collection/undergrad_target_chemicals.csv`
4. KOSHA 수집 완료: **198종 확보**(`msds_sections` 7,920행 = 198종 × 40항목, 결측 EAV 없음),
   2종 Abstain 유지(135072-82-1, 15005-97-7 — Diazonium Salts 그룹, 대체 후보 소진)

### Stage 4 (이번 세션)
5. **청킹 파이프라인** `04_rag_agent/pipeline.py` — 본문추출 → Normalize → Chunk → Metadata
   - section 청크 **805개** (길이 p50 390 / max 1,792자, 13개 섹션이 2분할)
   - item 청크 **7,420개** (폐기했으나 DB 보존)
   - Normalize: NFKC 단위 정규화(`℃`→`°C`, `㎩`→`Pa`), `|` 다중값→불릿,
     `※출처` 메타데이터 승격, `GHS06.gif`→`GHS06(급성독성)`, 무자료 10종 변종 통일
   - 근거등급 분포(item): Mandatory 1,782 / Recommended 4,226 / Reference 1,412
   - 자체검증 `test_pipeline.py` 통과
6. **§6 메타데이터 테이블** `rag_chunks` — SQLite 진실원본 + vector payload 필드 전부
7. **평가셋**
   - `evalset_pairs.py` → `gold_pair.jsonl` **369쌍** (Incompatible 135 / Caution 114 /
     Compatible 120, 전체 19,503쌍에서 카테고리 균형표집), `gold_pair_abstain.jsonl` **81쌍**
   - `evalset.py` → `gold_retrieval.jsonl` 407건 (단일물질 사실조회, `--task fact` 부품점검용)
8. **검색계층** `retrieval.py` — bge-m3-ko 임베딩 + FAISS IndexFlatIP + BM25(kiwipiepy)
   + RRF(k=60) + CrossEncoder 리랭커. 인덱스·벡터는 `04_rag_agent/index/` 캐시
9. **평가 드라이버** `run_ab.py` — Recall@5/10/20, Hit@5/10, MRR, nDCG@10,
   구간별 레이턴시(질의임베딩 / 검색 / 합계). 다중정답 채점 자체검증 통과
10. **LLM 클라이언트** `llm.py` — NVIDIA NIM Nemotron Nano (키 미설정 상태, 아래 4-1)
11. **설계변경 아카이브** `archive/superseded_docs/stage4_design_changes_2026-08-06.md` (12절, 380줄)

---

## 4. 다음 세션이 할 일 (우선순위 순)

### 4-1. LLM 연결 — **선행 조건**
`.env` 에 아래 한 줄 추가가 필요하다. **사용자만 할 수 있다.**
```
NVIDIA_API_KEY=<발급받은 키>
```
그다음 점검:
```bash
python 04_rag_agent/llm.py --check
```
- 모델: `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning`
- 엔드포인트: `https://integrate.api.nvidia.com/v1/chat/completions` (OpenAI 호환)
- `.env` 는 이미 `.gitignore` 등록됨. 키 원문은 출력·로그·커밋 어디에도 남기지 말 것
  (`llm.py` 의 `key_fingerprint()` 가 길이+해시만 보여준다)

### 4-1a. ~~평가셋 질의 다양화~~ **(완료, 2026-08-07)**
템플릿 5개로 확장, 383쌍×5템플릿=1,915질의로 재측정 완료. 결과는 §0-1 참고. 남은 것은
템플릿별 개별 breakdown(환경 세그폴트로 미완료, §0-1 참고)뿐.

### 4-2. RAG 지표 측정 (§10, §13 5단계) — **파일럿 완료(n=7), 확대는 후속 과제**

`ragas 0.4.3` 설치·연결 완료. NVIDIA NIM(judge LLM) + bge-m3-ko(embeddings, AnswerRelevancy용)
조합으로 4개 지표 파일럿 측정.

**패키징 버그 우회**: ragas 0.4.3이 `langchain_community.chat_models.vertexai`를
무조건 import하는데, `langchain-community` 0.4.x 리스트럭처링으로 그 서브모듈이
사라져 있음(업스트림 미수정 버그, Vertex AI는 이 프로젝트와 무관). google-cloud
전체를 설치하는 대신 `sys.modules`에 빈 스텁을 미리 넣어 import만 통과시키는 방식으로
우회(`rag_metrics.py` 상단 참고, 대형 의존성 설치 안 함).

**신규 스크립트**:
- `04_rag_agent/generate.py` — gold_pair.jsonl(template_idx=0)에서 카테고리 균형표집한
  쌍에 대해 (확정 구성으로) 실제 검색 → LLM 답변 생성. reference(오라클 정답)는 같은
  쌍의 gold_section 전체(§2·§10 완전근거)로 별도 생성 — **사람이 쓴 정답이 없어 LLM
  생성으로 대체**, 완전 독립적인 참조는 아님(한계로 명시).
- `04_rag_agent/rag_metrics.py` — 4개 지표 채점, 결과 `results/rag_metrics.csv`.

**파일럿 결과 (n=7, 카테고리 균형표집 15쌍 중 7건 성공, 2026-08-07)**:

| 지표 | 실측 평균 |
|---|---:|
| Faithfulness | 0.5104 |
| Context Precision | 0.4003 |
| Context Recall | 0.7429 |
| Answer Relevancy | 0.4672 |

Context Precision 목표치는 설계 §11이 "baseline 실측 후 설정"으로 비워둔 상태 — 이
값을 사용자에게 보고하고 확정은 승인 후. **표본 7개는 파일럿 규모라 확정 수치가
아님** — Faithfulness·Context Precision·Answer Relevancy가 모두 0.5 안팎으로 낮게
나온 건 표본 노이즈일 수도, 실제 생성 프롬프트/검색 개선 여지일 수도 있어 n을 늘려
재확인이 필요하다.

**환경 문제로 미완료**: 15쌍 전체 채점 목표였으나 8건은 API "Connection error"(5건,
재시도 로직 추가로 완화) 또는 프로세스 Segmentation Fault(반복 재현, 이 세션 내내
관측된 것과 동일 계열)로 손실. 병렬화(asyncio.gather) 시도는 3회 연속 시작 직후
즉시 크래시 — 임베딩 호출만 락으로 직렬화해도 동일해서 되돌림. 크래시 직후 시스템을
확인하니 python 프로세스가 하나도 없는데 **CPU 81%, 여유메모리 22%**로 부하가 높았음
— 이번 세션에서 문서·CSV·JSONL·인덱스 캐시를 계속 고쳐써서 OneDrive 동기화가 그
변경분을 백그라운드에서 처리 중이었을 가능성. **후속 세션 과제**: 시스템이 유휴
상태일 때(또는 OneDrive 동기화 일시정지 후) 15쌍 전체, 이후 필요시 383쌍 전체로 확대
재측정.

### 4-3. Abstain Precision 측정 (§13 6단계)
평가셋 `gold_pair_abstain.jsonl` **81쌍** 생성 완료.
정의: 양쪽 물질 모두 §10 "피해야 할 물질"이 자료없음 → 물질 특정 근거 없이 그룹 근거만
남음 → **원칙 1(매트릭스 단독판정 금지)에 의해 Abstain 대상**.
목표: False Answer 0건, Abstain Precision ≥ 95%.

### 4-4. 질의 인코더 최적화
`Embedding ≤ 500ms` 목표에 501.724ms로 **1.724ms 초과**. 전체 Retrieval 지연의 99.98%가
이 구간이다(검색은 0.089ms). 검색 방식과 무관한 문제.
후보: ONNX Runtime, 동적 양자화(int8), 질의 전용 경량 인코더.

### 4-5. 조치 대기 (사용자 판단 필요)
- ~~청석면(ASBESTOS [BLUE], 12001-28-4)이 200종 리스트에 잔존~~ **(해결, 2026-08-07)**:
  사용자 결단으로 즉시 제외. CSV 200종, DB 3테이블(40행), 평가셋 3종 반영 완료,
  인덱스 캐시 재빌드 대기 상태로 삭제함. 근거 `archive/superseded_docs/decisions.md` §4-5.
  **나머지 199종 전수 재검증은 여전히 미착수** — 대체 후보 32종에만 적용됐던 안전필터가
  원본 리스트 전체에는 아직 미적용.
- **설계문서 §5 사실오류**: `bge-reranker-v2-m3`를 "경량/빠름", `bge-reranker-base`를
  "대형/고성능"이라 적었으나 반대. 실제 v2-m3=2.2GB(568M), base=1.2GB(278M). 수정 대기.
- **평가셋 검수 미완**: 샘플 20건 사용자 검수를 못 받은 채 현 템플릿으로 실측 진행됨.
  템플릿 수정 시 질의 벡터만 재생성하면 되므로 반영은 수 분.
- **Hybrid 재검토 여부**: 위 0절 주의 참조.

### 4-6. CAMEO 그룹 매핑 데이터 소스 전환 (robots.txt 준수) — **완료(199종 + 3,396종 전체)**
2026-08-07 파일럿(12종) → 199종 전체 실행까지 완료. 상세 근거·엔드포인트·robots.txt
뉘앙스·199종 실행 결과 표는 `archive/superseded_docs/decisions.md` §1.2b 참고. 스크립트:
`01_collection/pubchem_verify_groups.py`(재실행 가능, idempotent — `INSERT OR IGNORE`).
결과: MATCH 183 / 표기차이뿐인 사실상 일치 5(그룹명 정정으로 해소) / 진짜 결측 1
(티오황산나트륨) / CID 조회 실패 9(혼합물·희귀 화합물, PubChem 자체 커버리지 한계).
UREA CAS 오류(`497-19-8`→`57-13-6`)는 DB(`chemical_id 3398` 삭제)와
`01_collection/undergrad_target_chemicals.csv` 양쪽 정정 완료.
**그룹 대표물질 폴백 로직 — 구현 완료(2026-08-08)**: `02_classification/group_fallback.py`.
결측/CID실패 10종 전부 같은 그룹 내 KOSHA MSDS 확보 완료 물질로 즉시 대체 가능함을
확인(급한 블로커 아님). 상세는 `archive/superseded_docs/decisions.md` §1.2c.

**3,396종 전체 풀 실행 완료(2026-08-08)**: MATCH 3,185 / 표기차이(정정완료) 7 /
진짜결측 9(전부 혼합물+티오황산나트륨) / CID조회실패 195(고분자·광물·총칭명 —
PubChem 구조적 커버리지 한계). **실질 문제는 3,396종 중 204종(6.0%)뿐**이고
전부 그룹 대표물질 폴백(§1.2c) 적용 대상. 상세는 `archive/superseded_docs/decisions.md` §1.2b.
남은 것 없음 — 이 항목은 종료.
### 4-7. 반응성 기본물질 풀 확장 — **실행 완료(2026-08-08)**
§1.2a의 "섹션10 등장빈도 추정"을 197종 §10 "피해야 할 물질" 전수조사로 실측
(`archive/superseded_docs/decisions.md` §1.2a-upd): **물 55.3%, 금속(포괄) 22.3%**, 나머지 키워드는
0%. 물은 실측 1순위, 금속은 이미 68그룹 체계·현재 풀에 대표종 다수 있어 신규
추가 불요.
- **Tier 1(그룹매핑 이미 있음, KOSHA MSDS만 필요)**: 물(7732-18-5, "Water and
  Aqueous Solutions"), 산소(7782-44-7, "Oxidizing Agents, Strong"), 질소
  (7727-37-9, "Not Chemically Reactive").
- **Tier 2(그룹매핑도 신규 필요)**: 이산화탄소(124-38-9), 수소(1333-74-0),
  암모니아(7664-41-7) — §1.2b PubChem 경로로 그룹매핑은 즉시 가능, KOSHA MSDS는
  별도.
- **실행 결과**: 사용자 승인 후 6종 전부 수집 완료.
  - Tier 2(CO2 124-38-9, 수소 1333-74-0, 암모니아 7664-41-7)는 먼저 PubChem
    경로(§1.2b)로 CAMEO 그룹 매핑 신규 확보(`chemicals` chemical_id 3399~3401,
    `source='pubchem_verified'`).
  - `01_collection/undergrad_target_chemicals.csv`에 6행 추가
    (`source='reactive_basics_tier1'`/`'reactive_basics_tier2'`) — 기존
    `01_collection/kosha_msds_collector.py`를 코드 변경 없이 재실행해 그대로 수집
    (idempotent라 기존 199종은 스킵, 신규 6종만 API 호출).
  - 6종 전부 4개 섹션(2/3/9/10) 완전 수집 확인.
  - **부수 이슈**: 이번 실행 중 `01_collection/pubchem_verify_groups.py --full`
    (3,386종 전체 재수집, 아래 참고)이 동시에 DB에 쓰기 중이라 `database is
    locked` 충돌이 반복 발생 — `kosha_msds_collector.py`의 `sqlite3.connect`에
    `timeout=120` 추가로 해결(재시도 로직 아님, SQLite busy_timeout 활용). 두
    스크립트를 **동시 실행할 때는 이 타임아웃이 필요**하다는 점을 기록.
  - **그룹명 표기 통일**: PubChem 대조 중 그룹 42("Metals, Less Reactive" →
    "...agents") 이어서 그룹 48("Not Chemically Reactive" → "...agents")도
    동일 패턴으로 발견·수정. 3,386종 전체 재수집 결과에서 같은 패턴의 다른
    그룹명도 추가로 나올 수 있음 — 완료되면 일괄 재확인 필요.

---

## 5. 환경 / 실행 방법

### 필수 환경변수
```bash
export SSL_CERT_FILE="$HOME/.cache/win_ca_bundle.pem"   # 아래 SSL 항목 참조
export MSDS_TORCH_THREADS=8                              # 미설정 시 실효 2코어만 사용
export HF_HUB_OFFLINE=1                                  # 캐시된 모델만 쓸 때
```

### 실행 순서
```bash
python 04_rag_agent/test_pipeline.py                     # 자체검증
python 04_rag_agent/pipeline.py                          # 청크 + rag_chunks + 마크다운
python 04_rag_agent/evalset_pairs.py                     # 쌍 평가셋
python 04_rag_agent/run_ab.py embedding --models bge-m3-ko \
    --granularity section --task pair --sections 2,10    # 확정 구성 재현
```

### 알려진 환경 함정 (재발 방지)
| 문제 | 해결 |
|---|---|
| HF 모델 다운로드 SSL 실패 | `huggingface_hub`의 httpx가 certifi만 참조해 로컬 루트 CA 미발견. Windows 인증서 저장소(ROOT/CA) 105개를 certifi와 합친 번들 생성 → `SSL_CERT_FILE` 지정. **검증 비활성화 금지**. `llm.py`는 이 번들이 있으면 자동 사용 |
| torch가 8코어 중 2코어만 사용 | `MSDS_TORCH_THREADS=8` (1.45배 단축) |
| 임베딩 배치를 키우면 더 느림 | 배치 32가 배치 8보다 2배 느림(메모리 대역폭). **배치 8 유지** |

### CPU 처리량 실측 (참고 — 8스레드)
| 대상 | 속도 | 환산 |
|---|---|---|
| section 청크(평균 487자) | 2.61초/청크 | 805청크 = 35분 |
| item 청크(평균 88자) | 0.637초/청크 | 7,420청크 = 79분 |
| 리랭커 base | 1.09초/쌍 | 369질의×20후보 = 최대 134분 |
| 질의 1건 임베딩 | 501.7ms | — |

---

## 6. 파일 위치

```
MSDS\
├── .env                  (KOSHA_SERVICE_KEY, NVIDIA_API_KEY — gitignore, 원문 노출 금지)
├── .env.example          (키 이름만)
├── reactivity_reference.db   (+ rag_chunks 테이블 추가됨)
├── 01_collection\        (수집 완료)
├── 02_classification\ · 03_compatibility\
├── 04_rag_agent\
│   ├── pipeline.py           본문추출→Normalize→Chunk→Metadata
│   ├── test_pipeline.py      자체검증
│   ├── evalset_pairs.py      쌍 평가셋 (제품 과제)
│   ├── evalset.py            단일물질 평가셋 (부품 점검용)
│   ├── retrieval.py          임베딩/FAISS/BM25/RRF(+§10 전체 penalty, 2026-08-09 확장)/리랭커
│   ├── run_ab.py             평가 드라이버 (hybrid에 penalty 기본 적용)
│   ├── boilerplate_sec10_values.json  §10 정형문구 15종 목록(2026-08-08) — 코드 미참조,
│   │                         2026-08-09 penalty가 §10 전체로 확장돼 기록용으로만 보존
│   ├── llm.py                NVIDIA NIM Nemotron Nano
│   ├── chunks\               section 805 + item 7,420 마크다운
│   ├── evalset\              gold_pair(173종 기준 435쌍×5=2,175, gold_evidence 포함) /
│   │                         gold_pair_abstain 75 / gold_retrieval 402 / gold_abstain 357
│   │                         (*.bak_2026-08-08 = evidence 병합 전 백업)
│   ├── index\                벡터·BM25 캐시 (corpus_tag=173 포함)
│   └── results\              실측 CSV/md + retrieval_experiments_*/step3_final_baseline_comparison.md
├── 05_evaluation\        (미착수)
├── archive\
│   └── chemical_selection_2026-08-08\    173종 재설계 이전 폐기 산출물(선정+RAG 진단 양쪽)
└── docs\
    ├── HANDOFF.md                            ← 이 문서
    ├── chemical_selection_final_2026-08-08.md  ★ 화학물질 선정 최종 확정(173종)
    ├── stage4_design_principles_v2.md        설계 확정본
    ├── stage4_design_changes_2026-08-06.md   설계 변경 아카이브
    ├── HANDOFF_ARCHIVE.md                    과거 이력
    └── msds_risk_assessment_readme.md
```

## 7. 컨텍스트 복원 방법

다음 세션 시작 시 **이 문서 → `stage4_design_changes_2026-08-06.md` → 설계원칙 v2** 순으로 읽을 것.
설계원칙 v2와 실제 구현이 어긋나는 부분은 변경 아카이브가 기준이다.
DB 구조는 문서 설명만 믿지 말고 `rag_chunks`, `msds_sections` 실제 데이터를 직접 조회해
확인한 뒤 작업할 것.
