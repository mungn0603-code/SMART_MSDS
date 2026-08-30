# DATA — 무슨 데이터를 쓰고 왜 그걸 쓰는가?

## 1. 데이터 소스 2종

| 소스 | 무엇을 얻는가 | 왜 이걸 쓰는가 | 접근 경로 |
|---|---|---|---|
| KOSHA MSDS Open API | 물질별 §2(유해성·위험성) · §3(구성성분) · §9(물리화학적 특성) · §10(안정성·반응성) | 판정의 **설명 근거**가 되는 원문. 국내 법령 체계에 맞춰 공표된 값이라 출처를 그대로 인용할 수 있다 | 공식 API, 서비스키 인증 |
| CAMEO Chemicals 반응성 그룹 68종 | 그룹 간 양립성 매트릭스 2,278쌍 + 위험코드 · 발생가스 | 물질 쌍의 **판정** 자체. 이 프로젝트는 판정을 LLM에 맡기지 않으므로 판정의 출처가 외부 권위 데이터여야 한다 | PubChem PUG-REST + Classification Browser (아래 2절) |

두 소스의 역할은 겹치지 않는다. **CAMEO가 판정하고, KOSHA MSDS가 설명한다.**

## 2. CAMEO 반응성 그룹 매핑 경로

현재 신규 매핑을 확보하는 경로는 하나다.

```
CAS  →  PubChem CID  →  CAMEO Chemical Reactivity Classification
      (PUG-REST)        (Classification Browser, hid=86)
```

- **PubChem의 역할은 식별자 매핑뿐이다** — `/rest/pug/compound/name/{CAS}/cids/JSON`으로
  CAS에 해당하는 CID를 찾는다. 반응성 분류를 PubChem이 판단하지 않는다.
- **분류의 출처는 CAMEO다** — Classification Browser의 `hid=86`이
  "CAMEO Chemical Reactivity Classification"이고, 여기서 CID에 붙은 그룹을 그대로 가져온다.
- 이 경로를 "CAS → CAMEO 직접 매핑"으로 줄여 쓰지 않는다. 중간에 CID 식별 단계가 있고,
  CID를 못 찾으면 매핑도 못 한다.

**기존 DB에는 이전 수집분도 존재하며, PubChem 기반 조회로 검증·보완되었다.** 지금 새로
채울 때 쓰는 경로는 위의 PubChem 경로 하나뿐이다. 행 단위 출처(`source` 태그)는
`chemical_group_membership`을 직접 조회하면 나오고, 수집 경위는
[`PROJECT_LOG.md`](PROJECT_LOG.md)에 있다.

**우리가 그룹을 직접 정하지 않는다.** 구조를 보고 "이건 알코올이니 8번"이라고 배정하면
판정 주체가 CAMEO에서 우리로 바뀐다. CAMEO에 분류가 없으면 비워 두고, 그 물질이 낀
조합은 Abstain으로 나간다. 적재 스크립트는
[`scripts/2_registry/map_registry_cameo_groups.py`](../scripts/2_registry/map_registry_cameo_groups.py).

## 3. MSDS 4개 섹션과 근거등급

40개 항목 전체가 아니라 4개 섹션만 쓴다.

| 섹션 | 쓰는 이유 |
|---|---|
| §2 유해성·위험성 | GHS 분류와 H/P코드. 검색·설명에서 실제 근거로 인용되는 것의 대부분이 여기다 |
| §3 구성성분 | 물질 식별 확인용(상세정보 패널) |
| §9 물리화학적 특성 | 인화점·반응 조건 등 취급 주의의 배경 |
| §10 안정성 및 반응성 | "피해야 할 물질"이 여기 있다. 다만 여러 물질에 같은 정형 문구가 반복돼, 검색에서는 감점 대상이다([`RETRIEVAL.md`](RETRIEVAL.md)) |

**근거등급제** — MSDS 필드를 출처 표기 기준으로 3단계로 나눈다. 판정 결과에 어떤 등급의
근거가 붙었는지를 화면과 리포트에 그대로 표시한다.

| 등급 | 대상 | 근거 |
|---|---|---|
| Mandatory | §2 (GHS 분류·H/P코드) | 고용노동부고시 별표의 확정 문구 |
| Recommended | §3·§9·§10 중 `※출처` 표기가 없는 값 | KOSHA가 직접 작성한 값 |
| Reference | `※출처` 표기가 있는 항목 | HSDB·ECHA·ICSC 등 외부 DB 인용 |

## 4. Registry · MSDS · 서비스 코퍼스의 관계

세 숫자가 서로 다른 집합이라 그때그때 무엇을 세는지 밝혀야 한다.

| 집합 | 규모 | 소유 테이블 | 뜻 |
|---|---:|---|---|
| 수집된 MSDS 전체 | **534종** × 4섹션 = 21,360행 | `msds_sections` | 그동안 수집해 둔 원문 전부. 서비스 범위보다 넓다 |
| Registry | **237종** | `substance_registry` | 이 프로젝트가 다룬다고 선언한 물질([`REGISTRY.md`](REGISTRY.md)) |
| 선택 가능 | **198종** | Registry ∩ KOSHA 등재 | 앱에서 고를 수 있는 물질. 상세정보를 줄 수 있다 |
| 서비스 코퍼스 | **173종** / §2·§10 371청크 | `rag_corpus_membership(corpus_tag='service')` | 판정까지 되는 물질. CAMEO 매핑이 있어야 한다 |

Registry에 있어도 MSDS가 없으면 상세정보가 비고, CAMEO 매핑이 없으면 판정이 Abstain이다.
조건별 이행 상태는 [`REGISTRY.md`](REGISTRY.md)의 서비스 계약 표가 정본이다.

> **이름이 같은 다른 집합 주의.** `corpus_tag='service'` 173종과, 구 평가 코퍼스인
> `corpus_tag='173'` 173종은 **크기만 같고 84종만 겹치는 다른 집합**이다. 구 코퍼스에는
> Registry 심사를 거치지 않은 물질 89종이 들어 있다. 구 코퍼스는 과거 지표를 재현할 때만
> 쓴다.

## 5. DB 스키마

`data/reactivity_reference.db`(SQLite)가 진실원본이다. 스키마 원본은 `data/schema.sql`.

| 축 | 테이블 |
|---|---|
| 물질 식별 | `substance_registry` |
| CAMEO 반응성 | `chemicals`, `chemical_group_membership`, `reactivity_groups`(68행), `compatibility_pairs`(2,278행), `self_reactivity`(68행), `compatibility_hazard_codes`, `compatibility_gas_products`, `hazard_code_legend`, `gas_product_legend` |
| KOSHA MSDS | `msds_sections`, `msds_chem_id_cache` |
| RAG 근거 | `rag_chunks`(section 단위 1,993행), `rag_corpus_membership` |
| 파생 | `substance_status` (VIEW) — Registry·KOSHA·MSDS·CAMEO 네 축의 상태를 조합해 서비스 가능 여부를 계산한다. 상태 값을 어디에도 복사해 두지 않는 게 요점이다 |
