# REGISTRY — 어떤 물질을 이 프로젝트가 다루는가?

Substance Registry는 이 프로젝트가 "다룬다"고 선언한 물질의 목록이자, 그 물질의
기준 식별 정보(CAS·한글명·영문명·화학식·별칭)를 보관하는 단일 출처다.
**서비스 물질 선정의 기준은 이 Registry 하나다.**

| 집합 | 규모 | 뜻 |
|---|---:|---|
| CORE Registry | **237종** | 다섯 축 기준을 통과해 등록된 물질 |
| 선택 가능 | **198종** | 그중 KOSHA MSDS에 등재된 물질. 앱 목록에 뜨고 상세정보를 준다 |
| 판정 가능 | **173종** | 그중 CAMEO 매핑까지 있는 물질. 이게 `corpus_tag='service'`다 |

셋은 포함 관계이고(173 ⊂ 198 ⊂ 237), 각 단계에서 빠지는 이유는 6절의 계약 표에 있다.
**등록에서 뺀 게 아니라 조건을 못 채운 것이다.**

> **이름 충돌 주의.** 여기서 말하는 `corpus_tag='service'` 173종과, 구 평가 코퍼스인
> `corpus_tag='173'` 173종은 **크기만 같고 84종만 겹치는 다른 집합**이다. 구 코퍼스에는
> Registry 심사를 거치지 않은 물질 89종이 들어 있고, 그 코퍼스는 과거 지표를 재현할
> 때만 쓴다.

이 문서는 물질을 넣고 빼는 판단 기준을 정의한다. 데이터 원천은 [`DATA.md`](DATA.md),
검색 지표는 [`RETRIEVAL.md`](RETRIEVAL.md).

## 1. Registry의 목적

Registry가 하는 일은 하나다 — **CAS 하나에 그 물질의 모든 이름을 묶는 것**.
"아연 = zinc = Zn = 7440-66-6"이 검색·질의·표시 전 구간에서 같은 물질로 잡히게
하는 식별(identity) 레이어다.

| Registry가 하는 것 | Registry가 하지 않는 것 |
|---|---|
| CAS를 기본키로 물질을 1행씩 등록 | MSDS 원문 보관 (→ `msds_sections`) |
| 한글명/영문명/화학식/별칭 정규화 | 검색 근거 청크 보관 (→ `rag_chunks`) |
| CORE 소속 그룹(`core_category`) 표시 | 반응성 판정 (→ CAMEO 매트릭스) |

`substance_registry` 테이블에는 "MSDS가 있음 / 검색 가능 / CAMEO 매핑 있음" 같은
상태 값을 따로 저장하지 않는다. 그건 **물어볼 때마다 해당 테이블을 직접 조회해서**
판단한다. 상태를 Registry에 복사해 두면 원본이 바뀔 때 두 값이 어긋나고, 어긋난
순간 "등록돼 있으니 판정도 된다"는 틀린 전제가 파이프라인 전체로 퍼진다.

`substance_registry` 테이블은 CORE CSV 5종에서 만들어지는 **결과물**이다. `--write`는
기존 행을 하나씩 고치는 게 아니라 테이블을 통째로 지우고 다시 채운다 — CSV에서 뺀
물질이 DB에 남아 있으면 CSV가 더는 기준 목록이 아니게 되기 때문이다. 구축 스크립트는
[`scripts/2_registry/build_substance_registry.py`](../scripts/2_registry/build_substance_registry.py).

## 2. CORE 선정 원칙

CORE는 다음 다섯 축을 함께 만족시키는 집합이다. 하나의 축만으로 편입하지 않고,
어느 축으로도 설명되지 않으면 넣지 않는다.

1. **실제 사용 가능성** — 실험실·사업장에서 실제로 보관·취급되는 물질인가
2. **화학적 기본성** — 화학을 설명할 때 빠질 수 없는 기본 물질인가
3. **교육/실험 활용성** — 학부 교육과정과 실험에서 실제로 등장하는가
4. **대표성** — 특정 화학 범주(산화제·유기용매·무기염 등)를 대표하는가
5. **프로젝트 필요성** — 혼재보관 위험성평가라는 이 프로젝트의 목적에 필요한가

여기에 [`DATA.md`](DATA.md)에서 세운 원칙이 그대로 유지된다:
**Selection은 Retrieval Evaluation과 독립이다.** 검색 지표(Recall·Hit 등)가 좋아
보이는 물질을 넣거나 나빠 보이는 물질을 빼지 않는다. 지표는 선정의 결과를 측정할
뿐, 선정의 입력이 아니다.

## 3. 다섯 개 그룹

| 그룹 | 종수 | 목록 |
|---|---:|---|
| `periodic_element` | 118 | [`core_periodic_elements.csv`](../data/collection/core_periodic_elements.csv) |
| `fundamental` | 25 | [`core_fundamental_chemicals.csv`](../data/collection/core_fundamental_chemicals.csv) |
| `educational` | 26 | [`core_educational_chemicals.csv`](../data/collection/core_educational_chemicals.csv) |
| `practical` | 37 | [`core_practical_chemicals.csv`](../data/collection/core_practical_chemicals.csv) |
| `representative` | 31 | [`core_representative_chemicals.csv`](../data/collection/core_representative_chemicals.csv) |
| **CORE 합계** | **237** | |

물질별 편입 근거는 각 CSV의 근거 컬럼(`course`·`experiment`·`note`)에 행 단위로 남아
있다. 목록이 지금 규모가 된 경위는 [`PROJECT_LOG.md`](PROJECT_LOG.md).

한 CAS는 하나의 `core_category`에만 귀속된다. 여러 그룹의 성격을 동시에 갖는
물질(예: 황산 — 기본성·교육·실무 전부 해당)은 더 기본적인 그룹으로 귀속시키고
중복 등록하지 않는다. 귀속 우선순위는 `periodic_element` > `fundamental` >
`educational` > `practical` > `representative`이며, 이 순서가 그대로
[`build_substance_registry.py`](../scripts/2_registry/build_substance_registry.py)의
`CORE_SOURCES` 순서다.

### periodic_element — 주기율표 원소

**무엇** — 주기율표 원소 118종 전체.
**왜** — 원소는 선정 기준을 따로 논할 대상이 아니다. 화학 물질 체계의 좌표축이고,
"이 원소가 목록에 없다"는 상태 자체가 설명하기 어렵다. 부분 수록은 자의적인
경계선을 만들 뿐이므로 전체를 넣는다. MSDS나 CAMEO 매핑이 없는 원소도 그대로
등록한다 — 식별은 되되 판정은 Abstain으로 처리되는 게 정직하다.
**예시** — 수소(1333-74-0) · 헬륨(7440-59-7) · 리튬(7439-93-2) · 나트륨(7440-23-5) ·
아연(7440-66-6) · 구리(7440-50-8)
**목록** — [`data/collection/core_periodic_elements.csv`](../data/collection/core_periodic_elements.csv)

### fundamental — 기본 화합물

**무엇** — 화학 교육·실무 어디서 시작해도 반드시 만나게 되는 기초 화합물.
**왜** — "화학적 기본성" 축이다. 강산·강염기·기본 용매·기본 기체는 다른 모든
물질을 설명하는 기준점 역할을 한다. 혼재보관 관점에서도 산-염기, 산화제-환원제
같은 가장 흔한 위험 조합이 이 그룹 안에서 발생한다.
**예시** — 물(7732-18-5) · 염화수소/염산(7647-01-0) · 황산(7664-93-9) ·
질산(7697-37-2) · 수산화나트륨(1310-73-2) · 암모니아 · 과산화수소(7722-84-1) ·
메탄올 · 에탄올(64-17-5) · 아세톤(67-64-1) · 벤젠 · 톨루엔(108-88-3) ·
일산화탄소 · 이산화탄소
**목록** — [`data/collection/core_fundamental_chemicals.csv`](../data/collection/core_fundamental_chemicals.csv)

### educational — 교육·실험 물질

**무엇** — 학부 화학 교육과정(일반화학·분석화학·유기화학·무기화학·물리화학)의
실험에서 실제로 사용되는 시약.
**왜** — "교육/실험 활용성" 축이다. 이 프로젝트가 상정한 첫 사용 맥락이 학부
실험실의 시약 보관이다. 교육과정 문헌에 실험명과 함께 근거가 남는 물질만
넣는다 — "화학 시간에 쓸 법한"이 아니라 **어느 과목 어느 실험에서 쓰이는지 지목
가능해야** 편입 근거가 된다.
**예시** — EDTA(60-00-4, 분석화학 킬레이트 적정) · 무수아세트산(108-24-7, 유기화학
아세틸화) · 염화철(III)(7705-08-0, 무기화학 착물합성) · 싸이오황산나트륨(7772-98-7,
분석화학 아이오딘 적정) · 옥살산나트륨(62-76-0, 분석화학 과망가니즈산 적정 표준물질) ·
크로뮴산칼륨(7789-00-6, 분석화학 Mohr법 지시약) · 염화칼륨(7447-40-7, 물리화학
전도도 측정) · 페로센(102-54-5, 무기화학 유기금속 합성)
**목록** — [`data/collection/core_educational_chemicals.csv`](../data/collection/core_educational_chemicals.csv)
(모든 행에 `course`·`experiment` 근거 컬럼이 붙어 있다. 일부는
[`undergrad_target_chemicals.csv`](../data/collection/undergrad_target_chemicals.csv)의
`source=curated_curriculum` 행에서 왔다)

### practical — 실무 취급 물질

**무엇** — 실험실·사업장에서 상시 보관되며, 실제로 서로 가까이 쌓여 혼재보관
위험이 발생하는 물질.
**왜** — "실제 사용 가능성" 축이다. 교육과정에는 안 나오지만 창고와 시약장에는
반드시 있는 것들이 있다. 이 그룹이 없으면 Registry가 교과서에서만 통하는 목록이
되고, 혼재보관이라는 문제 설정 자체와 어긋난다. 편입 근거는 **보관 현장에서의
실재성** — 실제 취급량이 있고 다른 물질과 같은 공간에 놓인다는 점이다.
**예시** — 차아염소산칼슘(7778-54-3, 상수·수영장 소독) · 황산알루미늄(10043-01-3,
정수 응집제) · 질산암모늄(6484-52-2, 비료·화약 원료) · 삼산화크로뮴(1333-82-0,
도금·표면처리) · 과황산암모늄(7727-54-0, 에칭·중합 개시제) · 트라이에탄올아민
(102-71-6, 금속가공유) · 사이안화칼륨(151-50-8, 도금) · MDI(101-68-8, 폴리우레탄 원료)
**목록** — [`data/collection/core_practical_chemicals.csv`](../data/collection/core_practical_chemicals.csv)
(각 행의 `note`에 어느 용도로 어디에 보관되는지를 남긴다)

### representative — 범주 대표 물질

**무엇** — 특정 화학 범주를 한 종으로 대표하게 하려고 명시적으로 고른 물질.
**왜** — "대표성" 축이다. CAMEO 68그룹 구조에서 특정 범주에 실제 수록 물질이
희소하면 그 범주의 반응 거동을 설명할 근거가 통째로 비게 된다. 대표 물질 한 종을
세워 범주 단위의 설명 가능성을 확보한다. 각 행에 어떤 범주의 대표인지(`note`)를
반드시 남긴다 — 근거 없는 대표는 대표가 아니다.
**예시** — 과망가니즈산칼륨(7722-64-7, 강산화제) · 수소화붕소나트륨(16940-66-2,
강환원제) · 염화나트륨(7647-14-5, 무기염) · 과산화벤조일(94-36-0, 유기과산화물) ·
폼알데하이드(50-00-0, 알데하이드류) · 사이안화나트륨(143-33-9, 무기 시안화물) ·
아자이드화나트륨(26628-22-8, 아지도 화합물) · 아세틸렌(74-86-2, 알킨류)
**목록** — [`data/collection/core_representative_chemicals.csv`](../data/collection/core_representative_chemicals.csv)

## 4. 왜 코퍼스가 아니라 CORE가 선정 기준인가

173종 코퍼스는 **수집 결과이지 선정 기준이 아니다.** "KOSHA MSDS §10에서 반응성 정보가
확보됐는가"는 그 물질을 다뤄야 하는 이유가 아니라 다룰 수 있는 조건이다. 조건을 기준
자리에 놓으면 데이터가 있는 쪽으로 목록이 끌려간다 — 실제로 그 목록에는 실험실에도
사업장에도 없는 물질이 다수 들어 있으면서 물·염산 같은 기본 물질이 빠져 있었고, 외부에
"이 프로젝트가 다루는 물질"로 제시했을 때 선정 논리를 한 문장으로 말할 수 없었다.

그래서 Registry의 소속 기준은 **CORE 다섯 그룹 하나로 통일**한다. 앱 선택 목록을
"Registry ∪ 코퍼스"로 잡던 규칙도 폐기했다 — 코퍼스 소속은 선정 근거가 아니다.
코퍼스는 사라지지 않고 원래 있어야 할 축(RAG 코퍼스 membership)으로 돌아간다(5절).

이 판단의 경위와 재평가 전문은 [`PROJECT_LOG.md`](PROJECT_LOG.md) 2026-08-22 항목과
[`results/registry_expansion_proposal_2026-08-22.csv`](../results/registry_expansion_proposal_2026-08-22.csv).

## 5. Registry · RAG corpus · CAMEO의 관계

세 축은 서로 독립이며, 각자 다른 테이블이 소유한다.

| 축 | 질문 | 소유 테이블 |
|---|---|---|
| **Registry** | 이 물질이 무엇인가 (식별) | `substance_registry` |
| **RAG corpus** | 이 물질의 근거 문서를 검색할 수 있는가 | `rag_chunks`, `rag_corpus_membership` |
| **CAMEO** | 이 물질의 반응성 그룹을 알고 있는가 | `chemicals`, `chemical_group_membership` |

교차 규칙:

- **Registry 등록 ≠ 검색 가능.** Registry에 있어도 `rag_chunks`에 청크가 없으면
  검색 대상이 아니다.
- **Registry 등록 ≠ 판정 가능.** CAMEO 그룹 매핑이 없는 물질은 매트릭스가
  판정하지 않는다. 이때 Registry에 있다는 이유로 LLM이 대신 판단하게 두지 않는다 —
  기존 Abstain 로직이 그대로 처리한다. 이건 프로젝트의 타협 불가 원칙
  ([`README.md`](../README.md), [`GENERATION.md`](GENERATION.md))의 연장이다.
- **Registry에 물질을 추가해도 CAMEO `chemicals` 테이블에 임의로 넣지 않는다.**
  식별은 되게 하되 반응성 축은 정직하게 비워 둔다. 채울 수 있는 유일한 경로는
  **출처가 CAMEO 자신인 분류를 그대로 가져오는 것**이다 — PubChem Classification
  Browser의 `hid=86`(CAMEO Chemical Reactivity Classification)이며, 이는
  [`DATA.md`](DATA.md)가 공식 API 경로로 채택한 그 엔드포인트다. 구조를 보고
  "이건 알코올이니 8번"이라고 우리가 정하지 않는다. CAMEO에 분류가 없으면 비워 둔다.
  적재 스크립트는
  [`scripts/2_registry/map_registry_cameo_groups.py`](../scripts/2_registry/map_registry_cameo_groups.py)이고
  `source='pubchem_cameo_2026-08-22'`로 태그해 기존 `CAMEO_scrape` 행과 구분한다.
- **앱의 물질 선택 목록은 Registry − KOSHA 미등재분이다.** 237 − 39 = **198종**.
  미등재 제외는 상세정보를 줄 수 없는 물질을 고르게 하지 않으려는 **표시 단계
  필터**이며 Registry 237종에서 빼는 게 아니다. 미등재 39종은
  전부 원소(초중원소·방사성 원소·란타넘족 일부)이고, getChemList를 CAS(searchCnd=1)/
  국문명·영문명(searchCnd=0) 3경로로 실조회해 전부 0건임을 확인했다
  (`data/collection/kosha_unlisted_39.csv`, `results/kosha_missing39_probe_2026-08-22.csv`).
- **검색 코퍼스 멤버십은 Registry와 별개로 `rag_corpus_membership`이 소유한다.**
  태그가 둘이고 용도가 다르다.
  - `service` — **현재 서비스·평가의 코퍼스.** Registry·KOSHA·MSDS·CAMEO 4조건을 모두
    채운 173종 / §2·§10 371청크. 정의 지점은
    [`seed_service_corpus.py`](../scripts/3_corpus/seed_service_corpus.py)이고, 앱과
    `run_cameo_full.py`가 이 태그만 본다.
  - `173` · `core` — **과거 지표 재현용 인덱스**(합쳐 262종 / §2·§10 557청크). 서비스
    경로에서 쓰지 않는다. `173`에는 Registry 심사를 거치지 않은 89종이 들어 있어,
    검색 후보로 남겨 두면 서비스 불가 물질이 경쟁에 끼어든다.

- **질의문은 registry 표준명에 별칭을 붙여 만든다.** 청크 헤더가 KOSHA 원문명으로
  렌더돼 있어(`페로센` vs `디시클로펜타디에닐 철`) 표준명만으로는 BM25가 어휘
  매칭을 못 한다. `app/streamlit_app.py`의 `query_term()`이 `rag_chunks.chemical_name`
  → KOSHA 원문명 → `name_en` → `aliases` 순으로 최대 3개를 덧붙인다. Registry는
  건드리지 않고 DB에 이미 있는 이름만 모은다.
- **코퍼스 membership을 Registry가 건드리지 않는다.** Registry에 물질을 넣고 빼는
  일과 코퍼스·평가셋·인덱스를 바꾸는 일은 서로 다른 작업이다.

## 6. 서비스 계약 — 등록됐다고 다 서비스되는 게 아니다

Registry 등록은 식별을 보장할 뿐이다. 화면에서 그 물질이 실제로 무엇을 받는지는
네 조건이 각각 결정하며, 조건마다 소유 테이블이 다르다.

| # | 조건 | 판정 소스 | 미충족 시 |
|---|---|---|---|
| ① | 식별 | `substance_registry` | 검색·선택 자체 불가 |
| ② | KOSHA 등재 | `msds_chem_id_cache.chem_id` | 상세정보 불가 → **선택 목록에서 제외** |
| ③ | MSDS 상세 §2/§3/§9/§10 | `msds_sections` | 상세 패널 공란 |
| ④ | 근거 청크 | `rag_chunks` + `corpus_tag='service'` | LLM이 §2/§10 원문 근거를 못 붙임 |
| ⑤ | CAMEO 그룹 매핑 | `chemicals` | **판정 자체가 Abstain** |

⑤가 없으면 `compatibility_engine.judge_pair_by_cas`가 무조건 Abstain을 반환한다.
Registry에 있다는 이유로 LLM이 대신 판단하게 두지 않는다는 원칙(5절)이 여기서
코드로 강제된다.

### 현재 이행률 (237종)

| 티어 | 종수 | 상태 |
|---|---:|---|
| **A** 4조건 전부 충족 | 173 | 상세·검색·판정 전부 가능 |
| **B1** 검색 근거 결여 | 0 | 없음 |
| **C** 상세정보만 | 25 | 선택은 되지만 CAMEO 매핑이 없어 조합은 Abstain |
| **X** KOSHA 미등재 | 39 | 선택 목록에서 제외 |

**판정 가능 쌍은 14,878 / 19,503 = 76.3%**다(선택 가능 198종 중 판정 가능 173종끼리의 쌍).
종별 대조표는
[`results/registry237_service_contract_after_chunking_2026-08-22.csv`](../results/registry237_service_contract_after_chunking_2026-08-22.csv),
재계산은 [`scripts/2_registry/service_contract_audit.py`](../scripts/2_registry/service_contract_audit.py).

### C티어 25종을 채우지 않는 이유

원소 23종 + 탄산나트륨(497-19-8) + 염화나트륨(7647-14-5)이며 **CAMEO에 데이터시트 자체가
없다.** 두 경로로 확인했다.

- PubChem `hid=86`: 25종 전량 무응답(CID는 찾아지지만 CAMEO 분류 항목이 없다)
- CAMEO 자체 색인: 알파벳 목록 페이지 19장의 대표명 4,391건을 전부 훑었다 — 25종 전부
  없었다. 원소는 화합물만 있다(스트론튬 화합물 8종은 있는데 스트론튬 금속은 없다).
  **대조군** `PLATINUM`은 실제로 있고 우리 DB에 이미 42번으로 매핑돼 있다 — CAMEO가
  원소로 수록한 것은 우리가 이미 갖고 있다는 뜻이다

근거는 CAMEO가 밝힌 수록 범위다. About 페이지가 "위험(hazardous) 화학물질 데이터시트
모음"이라고 적고 있고, 염화나트륨·탄산나트륨은 운송 위험물 분류가 없는 비위험물이다.
이름이 안 맞아 못 찾은 게 아니라 애초에 수록 대상이 아니다.

비슷한 물질(염화칼륨 = 47번, 탄산칼슘 = 21번)을 보고 유추해 채울 수도 있지만, 그건
CAMEO의 판정이 아니라 우리의 추측이므로 넣지 않는다 — 5절의 규칙 그대로다.
**따라서 판정 가능 쌍 76.3%를 현재 coverage로 확정한다. 목표는 100%가 아니다.**

**남은 한계**: 알파벳 목록에는 물질마다 대표 이름 하나만 실린다. 대표명이 아닌 다른
이름으로만 존재하는 데이터시트가 있다면 이 방법으로는 **확인할 수 없다.** 완전히 닫으려면
CAMEO 오프라인 프로그램의 배포 데이터가 필요하다.

### §10 근거가 얇다고 코퍼스에서 빼지 않는다

대조표의 `s10_specific_chars` 열(§10에서 정형문구와 `자료없음`을 뺀 물질특이 정보량)은
**표시용이고 편입 게이트가 아니다.**

이 값이 재는 건 물질의 근거 유무가 아니라 **KOSHA가 그 물질의 §10을 채웠는가**다. 실제로
이 값으로 자르면 과산화나트륨·삼산화크로뮴·중크롬산칼륨·칼륨·나트륨·카드뮴이 먼저 걸린다 —
알칼리 금속과 크로뮴(VI)은 혼재보관 위험성평가가 가장 다뤄야 할 물질이다. 게다가 검색에서
정답 근거는 전량 §2이고 §10 청크는 전부 감점 대상이라([`RETRIEVAL.md`](RETRIEVAL.md)),
§10이 얇아도 §2 청크는 정상 작동한다.

---

## 7. 물질 추가·삭제 기준

### 추가

편입하려면 다음을 모두 만족해야 한다.

1. **다섯 그룹 중 하나에 명시적으로 귀속된다.** 어느 그룹인지 말할 수 없으면
   넣지 않는다. "있으면 좋을 것 같아서"는 근거가 아니다.
2. **그룹별 편입 근거를 지목할 수 있다.** educational이면 과목·실험명,
   representative면 어떤 범주의 대표인지, practical이면 어디에 실제로 보관되는지.
3. **CAS가 유일하다.** 이미 등록된 CAS면 새 행을 만들지 않고 기존 행의 별칭·이름을
   보강한다.
4. **검색 지표를 근거로 삼지 않는다.** Recall·Hit이 오를 것 같다는 이유의 추가는
   순환 의존이다.

절차상 유의점:

1. 그룹 CSV(`data/collection/core_*.csv`) 5종 중 해당 파일에 행을 추가한다.
2. **KOSHA 캐시와 MSDS 상세를 먼저 채운다.** 추가분만 담은 CSV(`cas_number` 컬럼)를
   만들어 `python scripts/1_collect/kosha_msds_collector.py --target-csv <경로>`를 돌리면
   `getChemList` 결과 캐시와 `getChemDetail02/03/09/10` 4개 섹션이 한 번에 적재된다.
   이 단계를 건너뛰면 다음 단계의 자가검증(`check_kosha_cache`)이 미조회 CAS를 잡아
   실패한다. 이미 등록된 물질은 캐시·수집분을 보고 알아서 skip한다.
3. `python scripts/2_registry/build_substance_registry.py --write`로 반영한다(점검만 하려면
   `--write` 없이 실행).
4. 근거 청크까지 주려면 `src/pipeline.py`로 청킹한 뒤
   `python scripts/3_corpus/seed_service_corpus.py --write`를 돌린다 —
   `substance_status`를 다시 계산해 4조건을 채운 물질을 `corpus_tag='service'`로
   시딩한다. 인덱스 캐시는 청크 수가 달라지면 자동 재생성된다
   (`retrieval.embed_corpus` / `build_bm25`가 길이 불일치를 검사).
5. 판정까지 되게 하려면 `python scripts/2_registry/map_registry_cameo_groups.py`로 CAMEO 분류를
   조회한다(`--write` 없이 돌리면 리포트만). 미매핑 CAS만 대상으로 잡으므로 몇 번
   돌려도 기존 행을 덮어쓰지 않는다. CAMEO에 분류가 없으면 비워 두는 게 정답이다.
6. `python scripts/2_registry/service_contract_audit.py`로 6절 티어를 다시 계산하고,
   `python app/streamlit_app.py --check`로 앱 경로까지 확인한다.
- MSDS나 CAMEO 매핑이 없어도 추가 자체는 가능하다. 없는 축은 비워 두면 되고,
  그 물질이 무엇을 받는지는 6절의 계약 티어로 드러난다.
- `scripts/1_collect/kosha_registry_lookup.py --fetch`는 registry 전체의 KOSHA 등재 상태를
  점검·리포트할 때 쓴다(신규 추가분 수집은 2번이 담당).

### 삭제

삭제는 추가보다 엄격하다. **다섯 축 어느 것으로도 설명되지 않을 때만** 뺀다.

- **"쓸 일이 없어 보인다"는 삭제 사유가 아니다.** 그룹 귀속 근거가 무효가 됐음을
  보여야 한다(예: 교육과정에서 해당 실험이 사라짐, 대표 범주가 재편됨).
- **MSDS·CAMEO 데이터가 없다는 이유로 삭제하지 않는다.** 데이터 가용성은 식별 축의
  문제가 아니다. 이 이유로 빼기 시작하면 4절이 폐기한 "데이터가 있는 쪽으로 목록이
  끌려가는" 상태로 되돌아간다.
- **구 평가 코퍼스(`corpus_tag='173'`)에 속한 물질의 질의 이름
  (`rag_chunks.chemical_name`)은 변경·삭제하지 않는다.** 한 글자만 바뀌어도 그
  코퍼스로 낸 지표가 무효가 된다. `build_substance_registry.py`의 자가검증
  `check_frozen_173()`이 이를 강제한다.
- 삭제 시에도 CSV → `--write` → 자가검증 순서를 거친다.

### 식별 정보 유지 규칙

CAS·한글명·영문명·별칭은 물질의 기준 식별 정보로 계속 유지한다. 별칭은 검색에서
같은 물질로 잡히게 하는 유일한 수단이므로, 통용되는 다른 이름(염산/염화수소,
과망간산칼륨/과망가니즈산칼륨, 생석회/산화칼슘)이 확인되면 삭제가 아니라 보강한다.
자가검증이 대표 CAS 몇 종의 별칭 정규화를 실제로 확인한다.
