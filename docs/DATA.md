# DATA — 왜 이 물질/데이터를 선택했는가?

## 데이터 소스 2종

| 소스 | 용도 | 접근 경로 |
|---|---|---|
| KOSHA MSDS Open API | 물질별 §2(GHS 분류)·§3(구성성분)·§9(물리화학적 특성)·§10(안정성·반응성) 4개 핵심 섹션 | 공식 API, 서비스키 인증 |
| CAMEO Chemicals 반응성 그룹 68종 | 물질 쌍의 반응성 그룹 양립성 매트릭스(2,278쌍) | PubChem PUG-REST(CAS→CID) + Classification Browser(CID→CAMEO그룹, `hid=86`) — 상세는 아래 |

## CAMEO 데이터 경로: 스크레이핑에서 공식 API로 전환

원래는 `cameochemicals.noaa.gov`의 검색 결과 페이지를 직접 스크레이핑해 3,386종/
6,657행을 확보했는데, 이 경로가 `robots.txt`의 `/search` disallow를 위반한 상태로
식별됐다(비상업 포트폴리오 목적 사용 승인은 받았으나 방어 논리가 필요한 취약점).
대체 경로를 검증·전환했다:

1. CAS → PubChem CID: 공식 PUG-REST(`/rest/pug/compound/name/{CAS}/cids/JSON`)
2. CID → CAMEO 그룹: PubChem Classification Browser의 비공식이지만 `robots.txt`
   disallow 대상이 아닌 JSON 엔드포인트(`hid=86` = "CAMEO Chemical Reactivity
   Classification" — 초안이 가정했던 `hid=80`은 오답, 그건 별개 분류 체계였음)
3. 3,396종 전체 재실행 결과 **94.0%가 깨끗하게 재검증**(MATCH 3,185 + 표기차이뿐인
   사실상 일치 7). 나머지 6.0%는 진짜 결측(혼합물 표기 등, 9종) + CID 조회 실패
   (고분자·천연수지·광물 등 PubChem이 원리적으로 색인 못 하는 범주, 195종)

이 과정에서 UREA(CAS 오기 정정), 그룹42/48 표기 통일 등 부수 오류도 발견·정정했다.
스크레이핑 원본은 `archive/`로 이동, 시드 CSV 2종만 재현성을 위해 남겨뒀다.

2026-08-22에 이 경로를 **신규 매핑 확보**에도 그대로 썼다. Registry 237종 중 스크레이핑
풀에 아예 없던 미매핑 95종을 `hid=86`으로 조회해 31종을 채웠다(매핑 142 → 173종).
스크립트는 [`scripts/2_registry/map_registry_cameo_groups.py`](../scripts/2_registry/map_registry_cameo_groups.py),
적재 태그는 `source='pubchem_cameo_2026-08-22'`, 경위는
[`REGISTRY.md`](REGISTRY.md) 7절. 적용 전에 **이미 매핑된 30종을 같은 엔드포인트로
재조회해 29종 완전 일치 / 1종 superset**임을 확인하고 시작했다.

## 화학물질 선정 — 173종 최종 동결 (평가 코퍼스)

> **현재 서비스 물질 선정의 단일 출처는 [`REGISTRY.md`](REGISTRY.md)다(CORE 237종).**
> 이 절은 그 이전 단계의 기록이다 — 여기서 동결한 173종은 2026-08-17 검색 지표
> (Recall@10 0.9336 등)를 낸 **평가 코퍼스**이고, 2026-08-22부터는 선정 기준이
> 아니다. 현재 baseline은 `corpus_tag='service'` 기준으로 대체됐다
> ([`RETRIEVAL.md`](RETRIEVAL.md)). "Registry ∪ 173" 규칙도 그때 폐기됐다. 아래 "Selection은 Retrieval
> Evaluation과 독립이어야 한다"는 원칙만 그대로 Registry로 승계됐다.

### 왜 재설계했는가

기존 426종 코퍼스를 추적해보니 구조적 문제가 있었다: `pool_supplement`/
`pool_topup` 자동 보충으로 개별 선정 근거가 없는 물질이 섞여 있었고, retrieval
실측(hit rate 등)이 **선정 여부 자체에 개입**하는 순환 의존성이 있었다. 원칙을
다시 세웠다: **Selection은 Retrieval Evaluation과 독립되어야 한다** — retrieval
지표로 "이 물질을 넣을지 뺄지"를 정하지 않는다.

### 재정의한 기준 (근거 기반 우선순위, retrieval 지표 사용 안 함)

1. **MANDATORY** — 교육과정/커리큘럼상 명확히 필요한 물질
2. **HAZARD-RELEVANT** — KOSHA MSDS §10.5("피해야 할 물질")에서 물질 간 의미 있는
   반응성 정보가 확인됨(일반 안전문구만으로는 불충분 — "가연성 물질, 환원성
   물질"처럼 범용 카테고리 문구만 있는 경우는 제외)
3. **REPRESENTATIVE** — CAMEO 68그룹 구조에서 희소(대표물질 ≤2종)해 별도 대표성이
   필요한 경우
4. **UNJUSTIFIED** — 위 기준에 해당 안 함(자동 삭제 아님, "근거부족" 상태로 표시만)

### 최종 결과

| 등급 | 종수 |
|---|---:|
| MANDATORY | 30 |
| HAZARD-RELEVANT | 129 |
| REPRESENTATIVE | 14 |
| **최종 KEEP** | **173** |
| UNJUSTIFIED(제외) | 253 |

전체 lifecycle(6 Phase, 426종 감사→기준 재설계→전체 적용→표적 검증→동결→아카이빙)은
[`archive/superseded_docs/chemical_selection_final_2026-08-08.md`](../archive/superseded_docs/chemical_selection_final_2026-08-08.md).

### 반응성 "기본 물질" 우선순위

§10 "피해야 할 물질" 텍스트 전수조사(197종 대상 실측): **물 55.3%**, **금속(포괄)
22.3%**가 반응 상대로 가장 흔히 등장. 이 실측을 근거로 물·산소·질소·이산화탄소·
수소·암모니아 6종(reactive_basics tier1/2)을 KOSHA MSDS 4섹션 전부 우선 확보했다.
같은 실측(가연성/환원성 47.6%, 금속 34.9%, 물 23.0%)을 근거로 웨이브2에서 8개
CAMEO 그룹(금속/산화제/환원제/물)만 상한 없이 확대 수집했다.

### 안전성 조치

청석면(ASBESTOS [BLUE], CAS 12001-28-4)은 사용자 결단으로 즉시 제외(1A급 발암물질,
2026-08-07). 이후 발견된 유사 계열 물질(백석면 등)도 같은 기준으로 배제. 대체
후보군에는 GHS H-code + KOSHA 권고용도 자동필터 + 수동 이름 검토의 3단계 필터를
거쳤다 — 자동 필터 1단계만으로는 아플라톡신 B1(최강 발암물질급, 당시 KOSHA
H-code가 H361로만 약하게 등록돼 있어 필터를 통과) 같은 사고가 실제로 발생했다.

## 근거등급제 (Mandatory > Recommended > Reference)

MSDS 각 필드를 3단계로 분류해 신뢰도를 구분한다(2026-08-06 확정):

| 등급 | 대상 | 근거 |
|---|---|---|
| Mandatory | §2(GHS 분류·H/P코드) | 고용노동부고시 별표 확정 문구 |
| Recommended | §3·9·10 중 `※출처` 미표기 | KOSHA 자체 작성값 |
| Reference | `※출처` 표기 항목 | HSDB·ECHA·ICSC 등 외부DB 인용 |

## DB 스키마

`data/reactivity_reference.db`(SQLite, 진실원본): `chemicals`, `chemical_group_membership`,
`reactivity_groups`, `compatibility_pairs`, `self_reactivity`, `msds_sections`,
`msds_chem_id_cache`, `rag_chunks`, `rag_corpus_membership`, `hazard_code_legend`,
`gas_product_legend`. 스키마 원본: `data/schema.sql`.
