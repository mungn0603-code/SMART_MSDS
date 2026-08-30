<div align="center">

# 🧪 MSDS 위험성평가 자동화

**화학물질들을 함께 두면 안전한가?** — KOSHA 공공데이터와 RAG로 답한다.

*포트폴리오 프로젝트 · 2026-07-29 ~ 진행중*

</div>

---

## 이 프로젝트가 푸는 문제

실험실·창고에서 화학물질 혼재보관 사고는 물질 하나의 위험성이 아니라
**"여러 물질을 같이 뒀을 때"** 일어난다. 그런데 이 상호작용 정보는 흩어져 있다 —
반응성 그룹 매트릭스(CAMEO)는 "위험/주의/안전" 딱지만 붙일 뿐 이유를 설명하지
않고, 정작 이유는 물질별 MSDS(물질안전보건자료) 원문 안에 텍스트로 묻혀 있다.

이 프로젝트는 KOSHA(한국산업안전보건공단) 공개 MSDS 데이터와 CAMEO 68개
반응성 그룹 체계를 결합해, **물질을 2종 이상 입력하면 왜 위험한지 원문 근거와
함께 답하는 시스템**을 만든다. 근거가 부족하면 억지로 답하지 않고 **기각
(Abstain)** 한다 — 안전 도메인에서는 "모르겠다"고 말하는 것도 기능이다.

### 서비스 범위 (2026-08-28 확정)

물질을 임의로 줄인 게 아니라, **근거를 제공할 수 있는 범위를 데이터로 결정**했다.

```
Registry 237종            CORE 5축 선정 기준을 통과한 후보
  ├─ Service 173종        KOSHA MSDS + CAMEO 매핑 모두 확보 -> 실제 검색·판정 대상
  └─ Unsupported 64종     KOSHA 미등재 39 / CAMEO 데이터 부재 25

Legacy corpus 89종        과거 평가 코퍼스에만 있던 물질. DB 보존, 서비스 제외
```

`service_eligible`은 사람이 켜는 플래그가 아니라 **Registry·KOSHA·CAMEO 상태에서
파생**된다(`substance_status` VIEW). 인덱스 생성 여부(`chunks_ready`)는 자격의
조건이 아니라 결과 검증이라 따로 둔다 — 청킹이 실패해도 "서비스 불가 물질"로
둔갑하지 않고 `index_status='인덱스 결손'`으로 드러난다.
상세: [`docs/REGISTRY.md`](docs/REGISTRY.md)

> **타협 불가 원칙**: 매트릭스(CAMEO) 판정을 단독 최종 답변 근거로 쓰지 않는다.
> 매트릭스는 "이미 결정된 판정값"으로 LLM에 주어지지만, LLM은 그 판정을 재판단하지
> 않고 실제 MSDS §2/§10 근거로 **설명**만 한다 — 판정과 설명의 근거를 분리해서,
> 설명이 근거를 벗어나면(hallucination) 그 자체로 실패로 잡는다. 착수일부터 한 번도
> 흔들리지 않은 규칙. 상세: [`archive/superseded_docs/decisions.md`](archive/superseded_docs/decisions.md) §0.3

---

## 아키텍처 — 5단계 파이프라인

```mermaid
flowchart LR
    A["1. 수집\nKOSHA MSDS API\n173종"] --> B["2. 분류\nCAMEO 68그룹\n반응성 그룹 매핑"]
    B --> C["3. 매트릭스\n양립성 판정\n2,278쌍"]
    C --> D["4. RAG · Generation\n검색 + CAMEO-context 생성"]
    D --> E["5. 평가\nJudge · Faithful · Abstain"]

    style A fill:#2b6cb0,color:#fff
    style B fill:#2b6cb0,color:#fff
    style C fill:#2b6cb0,color:#fff
    style D fill:#2f855a,color:#fff
    style E fill:#2f855a,color:#fff
```

5단계 전부 최소 1회 이상 전수 실행·측정 완료. 상세 흐름은 [`docs/PIPELINE.md`](docs/PIPELINE.md).

### 핵심 발견 — Retrieval이 아니라 Generation이 병목이었다

1차 라운드(baseline 프롬프트, LLM이 CAMEO 판정을 직접 재추론)에서 측정한 결과:
Retrieval hit rate **98.84%**(병목 아님)인데도 Generation 실패율이 압도적으로
높았다 — 근거가 있어도 회피(**over-abstention 46.1%**)하거나, 개별 물질의
위험문구를 쌍 반응성으로 오인해 과잉위험 판정(**30.9%**)하는 두 가지 실패
패턴이었다.

해법은 프롬프트를 다듬는 게 아니라 **역할을 바꾸는 것**이었다 — LLM에게 판정을
맡기지 않고, CAMEO 반응성 그룹 조회(이미 2,160건 전수에서 실제 정답과 **100%
일치** 검증됨)로 판정을 확정해 컨텍스트에 박아 넣은 뒤, LLM은 그 판정을 MSDS
근거로 **설명만** 하게 했다. 결과:

| 지표 | 1차(LLM이 직접 판정) | 최종(CAMEO-context, service) |
|---|---:|---:|
| 정답률(판정줄) | 19.8% | **99.9%** |
| 정답률(judge 재분류) | — | 83.9% |
| Over-abstention | 46.1% | 1.1% |
| Faithful(근거 밖 주장 없음) | 측정 안 됨 | **94.6%** |
| 물질 혼동 | 관측됨 | 14.7% |

> **service 기준, 2026-08-29 측정** — Upstage `solar-pro3` / 프롬프트
> `cameo_service_v6` / `corpus_tag='service'` 173종 / 2,240건 전수, 실패 0건.
> 정답률은 두 정의가 다르다: 답변 **판정줄**이 CAMEO 판정을 유지했는가(99.9%,
> 뒤집힌 판정 0건)와, judge가 **본문**을 재분류한 결과가 일치하는가(83.9%).
> 둘의 격차가 이 시스템의 남은 결함이다 — 판정은 지키되 본문 서술이 판정보다 세다
> (Caution 745건 중 301건이 본문상 Incompatible로 읽힘). 물질 혼동 14.7%는 하락이
> 아니라 **최초 측정치**다: 구 프롬프트는 인용 태그를 요구하지 않아 이 지표가
> 측정된 적이 없었다. 상세는 [`docs/GENERATION.md`](docs/GENERATION.md).
>
> 단, **왼쪽 "1차" 열은 173 코퍼스 기준(2026-08-17)이다.** 두 열은 코퍼스·모델이
> 달라 엄밀한 대조가 아니며, 구조 전환의 방향성을 보이는 용도로만 나란히 둔다.

전체 경위(prompt v2 시도 → 실패 → CAMEO-context 전환 → judge 채점버그 발견·수정 →
전수실행 429 재시도 강화 → 잔여 실패 표적 재시도)는 [`docs/GENERATION.md`](docs/GENERATION.md).

---

## 검색 계층 실측 결과

서비스 코퍼스(`corpus_tag='service'`, 173종 / 371청크) 기준. 물질 쌍 450쌍 × 5개 질의
템플릿 = 2,250질의 중 gold_evidence가 없는 10건을 제외한 2,240질의.

| 지표 | 쌍 질의 | **질의 분해** |
|---|---:|---:|
| Recall@10 | 0.8987 | **0.9888** |
| Hit@10 | 0.9790 | **1.0000** |
| MRR | 0.8803 | **0.9581** |
| nDCG@10 | 0.8065 | **0.9547** |
| 질의 임베딩 지연 | 444ms | 461ms(목표 500ms 충족) |
| 검색 지연 | 4.9ms | 11.2ms |

채점은 **evidence 기준**이다 — 정답은 §2 GHS 분류 청크뿐이고, §10은 boilerplate라
"같은 문서의 무관한 청크가 검색돼도 Hit"으로 세지 않는다. 문서/섹션 단위(gold_section)
기준 수치와는 정의가 달라 직접 비교할 수 없다.

> 현재 서비스는 CAS가 이미 확정된 closed-world 질의이므로 결정론적 MSDS 조회를 사용하며, retrieval pipeline은 자유 질의 및 supplementary evidence 확장을 위해 유지한다.
>
> 위 수치는 **검색 계층**의 실측이다. **서비스 경로**는 두 CAS의 §2·§10을 SQL로 직접
> 조회한다 — 정답 확보 100%, 제3물질 0%, 프롬프트 8,570자 → 3,170자, 질의 임베딩
> 461ms → 0ms. 나눈 이유는 아래 "검색을 안 쓰기로 한 이유".

```
검색 계층 (평가·확장)                    서비스 경로 (production)
  src/retrieval.py                         app/streamlit_app.py
  scripts/run_ab.py                          explain(CAS_A, CAS_B)
  scripts/freeze_retrieval.py                  └─ pair_context()   CAS 직접조회 §2+§10
  app: retrieve(query)
```

### 실패를 먼저 세어보고 고쳤다

베이스라인이 Hit@10 0.979인데도 **양쪽 물질의 근거를 다 확보한 비율은 67.9%**였다.
Hit은 "둘 중 하나만 찾아도" 세기 때문에 높게 보였던 것이다. 실패 2,240건을 top-50까지
뜯어보니 지배 유형이 **"한쪽 물질의 §2만 검출"(22.4%)**이었고, 놓친 근거의 81%는
rank 11–20에 있었다 — 검색력이 아니라 순위 문제였다.

원인은 쌍 질의였다. 벡터 하나로 두 물질을 동시에 겨냥하니 한쪽이 밀린다. 물질명 단독으로
물으면 171종 중 162종이 자기 §2를 1위로 가져온다. 그래서 쌍 질의를 **물질별 질의 2개로
분해해 각 top-5씩 교차 병합**했다 — 검색 예산은 그대로다. 리랭커는 붙이지 않았다:
분해만으로 Hit@10이 1.000이 돼 얹을 여지가 없어졌다.

### 검색을 안 쓰기로 한 이유

분해로 순위는 잡혔는데 **한 가지가 안 풀렸다** — 컨텍스트의 60%가 그 쌍과 무관한
제3물질 청크였고(분해 전 65.8%), 이게 답변에서 남의 물질을 근거로 인용하는 문제의
공급원이다. 코퍼스가 173종 371청크라 **물질당 청크가 2.1개**뿐이라서, 한 물질에 대해
top-2 이상을 요구하면 나머지는 남의 물질일 수밖에 없는 구조였다.

그래서 물질당 top-N을 줄여가며 재봤더니, **검색을 아예 안 하는 쪽이 모든 축에서
이겼다.**

| 방식 | 청크 | 정답확보 | 제3물질 | 프롬프트 | 질의 임베딩 |
|---|---:|---:|---:|---:|---:|
| 분해 top-5/측 | 9.62 | 0.9888 | 60.1% | 8,570자 | 461ms |
| 분해 top-3/측 | 5.93 | 0.9821 | 44.5% | 5,326자 | 461ms |
| **CAS 직접조회 §2+§10** | **4.29** | **1.0000** | **0.0%** | **3,170자** | **0ms** |

이길 수밖에 없다. 정답 근거는 정의상 두 물질의 §2이고, 앱은 두 CAS를 **이미 알고 있다** —
사용자가 드롭다운에서 고른 값이다. 검색기는 결정론적으로 아는 것을 다시 찾고 있었고,
그 과정에서 남의 물질을 섞어 넣고 있었다. 여기서 검색은 정보를 더하지 않고 잃기만 한다.

**검색 계층을 지우지는 않았다.** 지표는 그대로 유효하고, 자유 텍스트 질의나 물질당
청크가 늘어나는 경우엔 다시 필요해진다. 다만 **지금 앱이 그 경로를 안 탄다는 사실을
숫자와 함께 적는다** — 이걸 안 적으면 검색 성능이 곧 제품 성능인 것처럼 읽힌다.

3종 이상 조합의 판정(매트릭스 조회)은 지원되지만, RAG 검색 자체의 실측 지표는
쌍(2종) 질의 기준까지만이다. 상세·실험 이력은 [`docs/RETRIEVAL.md`](docs/RETRIEVAL.md).

---

## N종(3종 이상) 물질 조합 지원

`src/compatibility_engine.py`의 `judge_combination_by_cas`가 입력 물질 전부를
쌍(pair)으로 쪼개 매트릭스 판정 후, worst-case 종합 + 전체 반응 매트릭스 표 +
쌍별 상세 리포트를 함께 낸다. 매트릭스 조회는 결정론적 DB 조회라 N종에 바로
적용되지만, 위 검색 계층 실측은 여전히 쌍 단위라는 점은 구분해서 표시한다.

---

## 이 프로젝트에서 보여주고 싶은 것

숫자보다 **판단 과정**을 더 신경 썼다 — 결정이 틀렸을 때 감추지 않고 왜
틀렸는지, 어떻게 다시 바꿨는지를 그대로 남겼다. 두 가지 사례:

> 검색 방식을 처음엔 "속도가 빠르다"는 이유로 dense 단독으로 정했다. 그런데
> 검색 범위를 좁히는 최적화를 하나 더 적용하고 나니 실측값이 **하이브리드가 7개
> 목표 중 6개, dense는 4개 충족**으로 뒤집혀, 결정 자체를 재전환했다.

> Generation 채점에서 "faithful 9.5% 실패"가 나왔을 때, 곧바로 프롬프트를 더
> 다듬는 대신 먼저 원인을 팠다 — 채점기(judge)가 CAMEO 컨텍스트를 못 보고
> MSDS 근거만 보고 채점하는 구조적 버그였다. 버그를 고치니 같은 13건 파일럿이
> 6/13 → 13/13 faithful로 뒤집혔다. **숫자가 나쁘게 나왔을 때 프롬프트부터
> 의심하지 않고 채점 로직부터 의심한 것**이 이 프로젝트 전체에서 반복되는 태도다.

이런 판단이 20건 넘게 쌓여 있고, 각각 "실측인지 사용자 결단인지", "출처가
있는지 없는지"를 구분해 기록했다.

| 문서 | 답하는 질문 |
|---|---|
| [`docs/PIPELINE.md`](docs/PIPELINE.md) | 전체 시스템은 어떻게 흘러가는가? |
| [`docs/REGISTRY.md`](docs/REGISTRY.md) | 어떤 물질을 다루는가? 넣고 빼는 기준은? |
| [`docs/DATA.md`](docs/DATA.md) | 데이터 원천은 무엇이고 어떻게 검증했는가? |
| [`docs/RETRIEVAL.md`](docs/RETRIEVAL.md) | 검색은 어떻게 설계했고 결과는 어땠는가? |
| [`docs/GENERATION.md`](docs/GENERATION.md) | 답변 생성과 평가를 어떻게 했는가? |
| [`docs/FILE_GUIDE.md`](docs/FILE_GUIDE.md) | 각 파일은 정확히 무엇을 하는가? |
| [`docs/HANDOFF.md`](docs/HANDOFF.md) | 현재 어디까지 왔는가? |
| [`docs/PROJECT_LOG.md`](docs/PROJECT_LOG.md) | 어떻게 발전했는가? |
| [`archive/`](archive/) | 폐기·기각 파일과 그 사유(분야별 정리, 원본 상세 문서 포함) |

---

## 기술 스택

| 영역 | 선택 | 비고 |
|---|---|---|
| 데이터 | KOSHA MSDS Open API, CAMEO 68그룹(PubChem 경로로 재검증) | 화학 도메인 원천 |
| 저장 | SQLite (`data/reactivity_reference.db`) | 관계형 진실원본 |
| 임베딩 | `dragonkue/BGE-m3-ko` | 한국어 특화, 사용자 지정 |
| 검색 | FAISS(dense) + BM25(kiwipiepy) + RRF 융합 + §10 boilerplate penalty | 하이브리드 |
| LLM | Upstage `solar-pro3`(reasoning_effort=high) | Generation + Judge 공용, OpenAI 호환 API |
| 평가 | 자체 rule+LLM Judge(faithful/predicted_verdict/substance_confused) | RAGAS는 파일럿 후 자체 채점기로 대체 |

---

## 디렉터리 구조

```
MSDS/
├─ README.md              # 이 문서
├─ docs/                  # 표준 문서 9종(위 표)
├─ src/                   # 재사용 핵심 모듈 (llm/retrieval/pipeline/eval_generation/
│                          # cameo_group_lookup/compatibility_engine)
├─ scripts/               # 현행 실행 스크립트 24종 (수집/분류/RAG 평가·생성)
├─ tests/                 # 자가검증 4종 (pipeline/collector/evalset/run_cameo 재개)
├─ app/                   # Streamlit 조회·판정 UI
├─ data/                  # DB·평가셋·청크·임베딩 캐시·원본 CSV
├─ results/               # 현행 산출물만 — Generation v7·v8b, Retrieval 지표, Registry 감사
└─ archive/               # 폐기·대체된 파일과 사유(폴더마다 NOTES.md)
```

전체 파일 목록과 역할은 [`docs/FILE_GUIDE.md`](docs/FILE_GUIDE.md).

---

## 실행

```bash
# 1) .env에 UPSTAGE_API_KEY 설정 후 연결 확인
python src/llm.py --check

# 2) Retrieval 재현(캐시된 임베딩/인덱스 사용)
python scripts/run_ab.py embedding --models bge-m3-ko --granularity section --task pair --sections 2,10 --corpus-tag service

# 3) Generation 입력 고정 -> 생성 -> 채점 (각 단계는 이어서 실행 가능, 실패분만 재시도됨)
#    worker 수는 Upstage 레이트리밋(100 RPM / 250,000 TPM)에 맞춘 값이다.
#    채점은 호출당 5.3k 토큰 x 1.3초라 worker 1개가 이미 TPM 상한이다.
python scripts/freeze_retrieval.py --corpus-tag service
python scripts/run_cameo_full.py --stage gen  --workers 7
python scripts/run_cameo_full.py --stage eval --workers 1
python scripts/reparse_verdict_line.py --gen results/generation_cameo_full.jsonl --eval results/eval_cameo_full.jsonl --out results/eval_cameo_full_reparsed.jsonl
python scripts/summarize_cameo_full.py --gen results/generation_cameo_full.jsonl --eval results/eval_cameo_full_reparsed.jsonl

# 3-b) 재실행 없이 아래 확정 지표만 확인하려면 인자 없이 (기본값이 아카이브된 v6 산출물이다)
python scripts/summarize_cameo_full.py --eval archive/2026-08-29_generation_prompt_history/v6/eval_cameo_full_reparsed.jsonl

# 4) Demo UI (물질 선택 -> CAMEO 판정 -> MSDS 근거 검색 -> LLM 설명)
streamlit run app/streamlit_app.py
```

---

## 지금까지 완성된 것 / 아직인 것

**완성**
- [x] Substance Registry **CORE 237종 확정** — 5축 선정 기준, 서비스 대상 198종
      ([`docs/REGISTRY.md`](docs/REGISTRY.md))
- [x] **서비스 계약 A티어 173종** — CAMEO 매핑이 있는 서비스 대상 전량이 상세·검색·판정
      3조건을 모두 충족(2026-08-22, B1 티어 해소)
- [x] KOSHA MSDS §2/§3/§9/§10 상세 연동 — Registry 198종 전량 수집, 앱에서 물질별 조회
- [x] KOSHA MSDS 173종 평가 코퍼스(수집 자체는 더 넓은 풀에서 진행, 평가셋은 173종 확정)
- [x] CAMEO 68그룹 · 양립성 매트릭스 2,278쌍, PubChem 경로로 94% 재검증
- [x] RAG 검색 계층 — hybrid, service 코퍼스 기준 Recall@10 0.8987 / Hit@10 0.9790
- [x] Generation 계층 — CAMEO-context 파이프라인, **service 기준** 정답률(판정줄)
      99.9% / 정답률(judge) 83.9% / faithful 94.6% (2026-08-29, 2,240건 전수)
- [x] N종(3종 이상) 물질 조합 판정(`judge_combination_by_cas`/`full_report`)
- [x] 자체 Judge 채점 파이프라인(rule + LLM, faithful/predicted_verdict/substance_confused)

**미완성 (감추지 않고 그대로 남김)**
- [ ] **본문 서술이 판정보다 강한 문제 (최대 결함)** — 판정줄 기준 오답은 0건이지만,
      matrix=Caution 745건 중 **301건이 본문상 Incompatible로 읽힌다**(judge 재분류).
      판정줄은 그 301건 모두 Caution으로 정확히 썼다. 판정줄–본문 일치 82.9%
- [ ] **물질 혼동 14.7%** (307/2,093) — 검색 top-10에 섞인 제3물질 청크를 이 쌍의
      근거로 인용한다. 2026-08-29에 프롬프트가 인용 태그를 요구하게 되면서 **처음
      측정된 값**이다(그전에는 0%가 아니라 측정 불가였다). 태그 미출력 6.2%는 여전히 측정 불가
- [ ] Reranker 미실행 — 저비용 대안(boilerplate penalty)으로 이미 목표 충족해 보류 중
- [ ] 잔여 faithful 실패 5.4%(120건, service 기준) — 패턴은 파악됐으나(그룹 분류를
      확인된 반응처럼 단정) 완전히 해소되진 않음. 173/Nemotron 때는 2.8%였다
- [ ] Registry 237종 중 **CAMEO 매핑 173종(73.0%)** — 2026-08-22에 PubChem `hid=86`으로
      142 → 173종으로 늘려 판정 가능 쌍은 51.3% → **76.3%**(14,878/19,503). 남은 25종은
      CAMEO에 데이터시트 자체가 없어(원소 23종 + 탄산나트륨 + 염화나트륨) **76.3%를 현재
      coverage로 확정**했다 — PubChem `hid=86`과 CAMEO 자체 색인 두 경로로 원천 부재 확인
- [ ] 원본 리스트 전체(173종 이전 풀) 안전성 재검증 미완
- [ ] RAGAS 기반 지표(Faithfulness/Context Precision 등)는 n=7 파일럿 이후 중단,
      자체 Judge로 대체된 채 재개 안 함(사유: [`archive/generation_experiments/NOTES.md`](archive/generation_experiments/NOTES.md))

솔직한 진행률이 실제로는 더 신뢰가 간다고 생각해서 완성된 척 하지 않는다.
상세 목록은 [`docs/HANDOFF.md`](docs/HANDOFF.md).

---

<div align="center">

*이 문서는 열람자를 위한 요약본이다.
실행 방법·환경변수·상세 설계 근거는 위 링크된 문서들을 참고.*

</div>
