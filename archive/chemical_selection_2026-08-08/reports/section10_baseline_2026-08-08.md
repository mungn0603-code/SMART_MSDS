# §10 "피해야 할 물질" Baseline — 공식 고정 (PHASE 2-A)

**작성일**: 2026-08-08
**실행 스크립트**: [`02_classification/section10_baseline.py`](../02_classification/section10_baseline.py) (읽기 전용, DB/CSV 미변경)

이 문서가 앞으로 §10 위험관계 빈도를 인용할 때 쓰는 **유일한 공식 baseline**이다. 기존에 인용됐던 두 수치(`docs/decisions.md` §1.2a-upd의 55.3%/22.3%, `01_collection/expand_by_reaction_frequency.py` 주석의 47.6%/34.9%/23.0%)는 계산 코드가 보존되지 않아 재현이 불가능하므로 더 이상 인용하지 않는다.

## 1. 방법론 (재현에 필요한 전부)

| 항목 | 값 |
|---|---|
| 원본 문서 | `msds_sections` 테이블, `section=10` AND `item_name_kor='피해야 할 물질'` 행의 `item_detail` 컬럼 |
| 분모(모집단) | candidate CSV(`undergrad_target_chemicals.csv`, 475행)와 연결되며 4섹션(2/3/9/10)을 전부 확보한 CAS = **426종** (DB를 그냥 세면 orphan 1건이 섞여 427이 나옴 — `chemical_selection_audit_2026-08-08.md` §0 참고, 이 문서는 그 orphan을 제외한 426종을 분모로 쓴다) |
| 청크/단위 | 물질(CAS) 단위 — 한 물질의 §10 "피해야 할 물질" 원문 전체를 하나의 텍스트로 보고, 카테고리별로 그 문자열이 포함되어 있는지만 판정(문장/청크 분할 없음) |
| 분류 규칙 | 아래 표의 문자열이 원문에 **부분 문자열로 포함**되면 해당 카테고리 히트(대소문자 구분 없음 — 한국어라 해당 없음, 정규식 아닌 단순 `in` 연산자) |
| 중복 처리 | 한 물질의 §10 원문이 여러 카테고리에 동시 히트할 수 있음(예: "가연성 물질(나무, 종이, 기름, 의류 등)\|금속\|물"은 3개 카테고리 전부 히트) — 카테고리별 % 합이 100%를 넘는 것이 정상. 물질 자신을 두 번 세는 중복은 없음(카테고리 내부는 물질 CAS 집합, 즉 set 아님을 주의 — 카테고리당 물질 1개는 1회만 카운트됨) |
| 재현 방법 | `python 02_classification/section10_baseline.py` (인자 없음, DB/CSV 경로는 `provenance_audit.py`의 상수를 그대로 import) |

### 카테고리별 키워드 정의 (코드: `provenance_audit.S10_CATEGORIES`)

| 카테고리 | 매칭 문자열(하나라도 포함되면 히트) |
|---|---|
| combustible_reducing | 가연성, 환원성, 환원제, 인화성 |
| metal | 금속 |
| oxidizer | 산화제, 산화성 |
| water | 물 |
| no_data | 자료없음 |

## 2. 공식 Baseline 수치

**분모: 426종** (COLLECTED, candidate CSV와 연결됨)

| 카테고리 | 분자(물질 수) | 비율 | wave 분해 |
|---|---:|---:|---|
| combustible_reducing | 202 | 47.4% | {'wave1': 88, 'wave2': 113, 'reactive_basics': 1} |
| metal | 99 | 23.2% | {'wave1': 44, 'wave2': 55} |
| oxidizer | 0 | 0.0% | {} |
| water | 251 | 58.9% | {'wave1': 109, 'wave2': 139, 'reactive_basics': 3} |
| no_data | 154 | 36.2% | {'wave1': 75, 'wave2': 76, 'reactive_basics': 3} |

## 3. 기존 두 수치와의 차이 — 왜 다른가

| 출처 | 표본 | water | metal | combustible/reducing | 재현 가능? |
|---|---:|---:|---:|---:|:--:|
| `docs/decisions.md` §1.2a-upd | 197종 | 55.3% | 22.3% | (측정 안 함) | 아니오 — SQL 쿼리 문자열만 텍스트로 기록, 스크립트 파일로 보존 안 됨 |
| `expand_by_reaction_frequency.py` 주석 | 204종(명시) | 23.0% | 34.9% | 47.6% | 아니오 — 스크립트 자체엔 §10 텍스트 분석 코드가 없고 docstring에 결과만 인용 |
| **이 문서(공식 채택)** | 426종(현재 전수) | 58.9% | 23.2% | 47.4% | **예 — 이 스크립트 재실행으로 동일 결과 재현** |

표본 크기(197→204→426)와 키워드 정의 자체가 다른 세 측정을 직접 비교하는 것은 원래 무의미하다. 이 문서는 어느 것이 '맞는' 수치인지 판정하지 않고, **앞으로 유일하게 재현 가능한 버전**을 공식으로 채택한다는 것만 결정한다.

참고: `no_data`(§10 원문이 "자료없음") 비율은 154/426 = 36.2% — 이 비율만큼은 §10 실측으로 선정 근거를 댈 수 있는 상한을 넘어선다(정보 자체가 없으므로).
