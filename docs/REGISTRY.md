# REGISTRY — 어떤 물질을 이 프로젝트가 다루는가?

Substance Registry는 이 프로젝트가 "다룬다"고 선언한 물질의 목록이자, 그 물질의
기준 식별 정보(CAS·한글명·영문명·화학식·별칭)를 보관하는 단일 출처다.
현재 확정 규모는 **CORE 207종**이다.

이 문서는 물질을 넣고 빼는 판단 기준을 정의한다. 데이터 소스와 173종 코퍼스의
수집 이력은 [`DATA.md`](DATA.md), 검색 지표는 [`RETRIEVAL.md`](RETRIEVAL.md).

## 1. Registry의 목적

Registry가 하는 일은 하나다 — **CAS 하나에 그 물질의 모든 이름을 묶는 것**.
"아연 = zinc = Zn = 7440-66-6"이 검색·질의·표시 전 구간에서 같은 물질로 잡히게
하는 식별(identity) 레이어다.

| Registry가 하는 것 | Registry가 하지 않는 것 |
|---|---|
| CAS를 기본키로 물질을 1행씩 등록 | MSDS 원문 보관 (→ `msds_sections`) |
| 한글명/영문명/화학식/별칭 정규화 | 검색 근거 청크 보관 (→ `rag_chunks`) |
| CORE 소속 그룹(`core_category`) 표시 | 반응성 판정 (→ CAMEO 매트릭스) |

`substance_registry` 테이블에는 `msds_available` / `rag_available` /
`cameo_available` 같은 가용성 플래그를 저장하지 않는다. 그 물질에 MSDS가 있는지,
검색 대상인지, CAMEO 그룹이 매핑됐는지는 **필요한 시점에 해당 테이블을 라이브
조회해서 판단**한다. Registry에 캐시하면 두 곳이 어긋나고, 어긋난 순간 "등록돼
있으니 판정 가능하다"는 잘못된 전제가 파이프라인에 들어온다.

`substance_registry` 테이블은 CORE CSV 5종의 **파생 테이블**이다. `--write`는 UPSERT가
아니라 테이블을 drop 후 전량 재적재한다 — CSV에서 뺀 물질이 DB에 남으면 CSV가 기준
목록이 아니게 되기 때문이다. 구축 스크립트는
[`scripts/build_substance_registry.py`](../scripts/build_substance_registry.py).

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
| `fundamental` | 17 | [`core_fundamental_chemicals.csv`](../data/collection/core_fundamental_chemicals.csv) |
| `educational` | 20 | [`core_educational_chemicals.csv`](../data/collection/core_educational_chemicals.csv) |
| `practical` | 30 | [`core_practical_chemicals.csv`](../data/collection/core_practical_chemicals.csv) |
| `representative` | 22 | [`core_representative_chemicals.csv`](../data/collection/core_representative_chemicals.csv) |
| **CORE 합계** | **207** | |

한 CAS는 하나의 `core_category`에만 귀속된다. 여러 그룹의 성격을 동시에 갖는
물질(예: 황산 — 기본성·교육·실무 전부 해당)은 더 기본적인 그룹으로 귀속시키고
중복 등록하지 않는다. 귀속 우선순위는 `periodic_element` > `fundamental` >
`educational` > `practical` > `representative`이며, 이 순서가 그대로
[`build_substance_registry.py`](../scripts/build_substance_registry.py)의
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

## 4. project_173을 폐기하고 CORE 중심으로 전환한 이유

173종은 RAG 코퍼스로 동결된 집합이지 물질 선정 기준이 아니다. 이 둘을 Registry
안에서 나란히 둘 이유가 없다:

- **선정 기준이 아니라 수집 결과였다.** 173종은 KOSHA MSDS §10에서 의미 있는
  반응성 정보가 확보된 물질이 남은 결과다. "MSDS 수집에 성공했는가"는 그 물질을
  다뤄야 하는 이유가 아니라 다룰 수 있는 조건이다. 조건을 기준 자리에 놓으면
  데이터가 있는 쪽으로 목록이 끌려간다.
- **목록의 성격을 설명할 수 없다.** 173종에는 실험실에도 사업장에도 없는 물질이
  다수 포함돼 있는 반면, 물·염산 같은 기본 물질이 빠져 있다. 외부에 "이 프로젝트가
  다루는 물질"로 제시했을 때 선정 논리를 한 문장으로 말할 수 없다.
- **두 축을 한 테이블에 두면 기준이 흐려진다.** Registry에 CORE와 173이 공존하면
  "이 물질은 왜 여기 있는가"의 답이 물질마다 달라진다. 판단 기준으로 재사용할 수
  없는 목록은 기준 문서를 만들 수 없다.

따라서 **Registry의 소속 기준은 CORE 다섯 그룹 하나로 통일**하고, project_173은
Registry의 별도 집합으로 유지하지 않는다. 173종 자체가 사라지는 게 아니라 원래
있어야 할 축(RAG 코퍼스 membership)으로 돌아간다 — 아래 5절.

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
  ([`CLAUDE.md`](../CLAUDE.md), [`GENERATION.md`](GENERATION.md))의 연장이다.
- **Registry에 물질을 추가해도 CAMEO `chemicals` 테이블에 임의로 넣지 않는다.**
  식별은 되게 하되 반응성 축은 정직하게 비워 둔다.
- **앱의 물질 선택 목록은 Registry ∪ 173 코퍼스다.** Registry에 없는 173종 물질도
  선택·검색은 되며, 별칭 기반 매칭이 붙지 않을 뿐이다.
- **RAG 코퍼스 membership은 Registry가 건드리지 않는다.** 173종 코퍼스와 그
  검색 지표는 `rag_corpus_membership`에서 그대로 유지된다. 이번 재편은 Registry
  축만의 변경이며 RAG 코퍼스·평가셋·검색 인덱스는 대상이 아니다.

## 6. 물질 추가·삭제 기준

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

- 그룹 CSV(`data/collection/core_*.csv`) 5종 중 해당 파일에 행을 추가한 뒤
  `python scripts/build_substance_registry.py --write`로 반영한다.
- 반영 후 `python scripts/kosha_registry_lookup.py --fetch`로 KOSHA 조회 캐시를
  갱신한다. 하지 않으면 자가검증(`check_kosha_cache`)이 미조회 CAS를 잡아낸다.
- MSDS나 CAMEO 매핑이 없어도 추가 자체는 가능하다. 없는 축은 비워 두면 된다.

### 삭제

삭제는 추가보다 엄격하다. **다섯 축 어느 것으로도 설명되지 않을 때만** 뺀다.

- **"쓸 일이 없어 보인다"는 삭제 사유가 아니다.** 그룹 귀속 근거가 무효가 됐음을
  보여야 한다(예: 교육과정에서 해당 실험이 사라짐, 대표 범주가 재편됨).
- **MSDS·CAMEO 데이터가 없다는 이유로 삭제하지 않는다.** 데이터 가용성은 식별
  축의 문제가 아니다. 이 이유로 빼기 시작하면 project_173에서 벗어난 의미가 없어진다.
- **173종 RAG 코퍼스에 속한 물질의 질의 이름(`rag_chunks.chemical_name`)은
  변경·삭제하지 않는다.** 한 글자만 바뀌어도 동결된 검색 지표(쌍 질의 2,160건 기준)가
  무효가 된다. 자가검증(`check_frozen_173`)이 이를 강제한다.
- 삭제 시에도 CSV → `--write` → 자가검증 순서를 거친다.

### 식별 정보 유지 규칙

CAS·한글명·영문명·별칭은 물질의 기준 식별 정보로 계속 유지한다. 별칭은 검색에서
같은 물질로 잡히게 하는 유일한 수단이므로, 통용되는 다른 이름(염산/염화수소,
과망간산칼륨/과망가니즈산칼륨, 생석회/산화칼슘)이 확인되면 삭제가 아니라 보강한다.
자가검증이 대표 CAS 몇 종의 별칭 정규화를 실제로 확인한다.
