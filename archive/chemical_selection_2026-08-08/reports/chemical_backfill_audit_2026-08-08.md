# 66개 Backfill Candidate Audit (PHASE 2-B/C/D)

**작성일**: 2026-08-08
**실행 스크립트**: [`02_classification/backfill_candidate_probe.py`](../02_classification/backfill_candidate_probe.py)(KOSHA 실측 조회) + [`02_classification/backfill_coverage_gain.py`](../02_classification/backfill_coverage_gain.py)(coverage gain 계산·분류)

**원칙 확인**: `01_collection/undergrad_target_chemicals.csv`(선정 CSV)는 이번 PHASE 2에서 전혀 수정하지 않았다. 아래 ADD 판정은 "편입 후보로 확정됨"이지 "편입 완료"가 아니다 — 실제 선정 CSV 반영은 사용자 승인 후 별도 작업.

## 0. 의사결정 분포

| decision | 건수 | 의미 |
|---|---:|---|
| ADD | 18 | 독립 evidence + coverage gain 확인, 편입 권고 |
| HOLD | 12 | KOSHA 등록·데이터는 있으나 §10 근거가 빈약해 사람 판단 필요 |
| REJECT | 10 | 중복(기존 물질과 그룹조합 동일) 또는 안전/윤리 사유 |
| DATA_UNAVAILABLE | 26 | KOSHA 미등록 — 판단에 필요한 원본 데이터 자체가 없음 |
| INDEPENDENCE_UNCLEAR | 0 | (실측 결과 0건 — 아래 §4 참고) |
| **합계** | **66** | |

## 1. 의사결정 규칙 (재현 가능하도록 명시, 코드: `backfill_coverage_gain.py`)

우선순위 순서대로 첫 번째 해당 규칙 적용:

1. 발암1급 석면류(`1332-21-4`, `12001-29-5` — 기존 청석면 `12001-28-4` 배제 선례와 동일 계열) → **REJECT**
2. KOSHA 미등록/미시도 → **DATA_UNAVAILABLE**
3. 이미 그룹 내 기존 물질과 `true_cameo_groups` 조합이 완전히 동일(매트릭스 엔진 기준 정보량 100% 중복) → **REJECT**
4. 대상 그룹이 현재 0종이고 §10에 `no_data`가 아닌 실질 카테고리 있음 → **ADD**
5. 대상 그룹이 현재 0종이나 §10이 `자료없음`뿐 → **HOLD**
6. 대상 그룹이 1~2종이고 §10에 실질 카테고리 있음(기존과 비중복) → **ADD**
7. 그 외(§10 근거 빈약, 판단 애매) → **HOLD**

독립성(`independence`) 점검: 66개 후보 전부 현재 선정 CSV 밖의 신규 후보라 Wave1/평가셋 파생 순환논리(PHASE 1에서 발견된 문제) 자체가 구조적으로 적용되지 않는다. 그래도 "혹시 우연히 평가셋에 이미 등장하는 후보가 있는가"를 실측으로 점검했다 — **결과: 0건**. 즉 이번 66개 후보에는 독립성 오염 문제가 없다.

## 2. Group 25 (Diazonium Salts) — DATA_SCARCITY 확정

5개 후보(`135072-82-1`, `15005-97-7`, `15557-00-3`, `21723-86-4`, `4421-50-5`) **전부 이번 세션에서 실제 KOSHA API로 재조회했고 전부 미등록으로 확인**됐다(2종은 PHASE 1 이전에 이미 확인, 3종은 이번 PHASE 2-B에서 신규 확인). CAMEO 68그룹 체계 전체 풀(3,396종) 안에 그룹25 화합물이 원래 5개뿐이므로, **이 5개가 전부 KOSHA 미등록이면 현재 KOSHA Open API로는 그룹25를 절대 채울 수 없다** — 이건 선정 파이프라인의 결함이 아니라 **데이터 자체의 구조적 희소성(DATA_SCARCITY)**이다.

**권고**: Group 25를 억지로 채우려 하지 않는다. 이 그룹(아연 착염 디아조늄 염료/안료 중간체)이 학부 실험·평가 스코프에 실제로 필요한 위험관계인지부터 판단하고, 필요하다면 KOSHA 외 다른 공개 데이터 소스(예: PubChem GHS 요약, ECHA)를 별도 트랙으로 검토할 것 — 이번 프로젝트가 KOSHA MSDS 원문(§2·3·9·10 국문 텍스트)을 RAG 코퍼스로 쓰는 한, KOSHA 미등록 물질은 애초에 이 프로젝트의 핵심 데이터 형태(MSDS 원문)를 만들 수 없다는 것도 함께 기록해둔다. **이 문서를 이 프로젝트의 dataset limitation으로 명시한다.**

## 3. 13개 Scarce Group 조사 결과 (Before → After)

| group_id | group_name | before | after(ADD 반영) | ADD | HOLD | REJECT | DATA_UNAVAILABLE |
|---:|---|---:|---:|---:|---:|---:|---:|
| 10 | Alkynes, with Acetylenic Hydrogen | 1 | 3 | 2 | 2 | 0 | 0 |
| 11 | Alkynes, with No Acetylenic Hydrogen | 1 | 2 | 1 | 1 | 0 | 2 |
| 20 | Carbamates | 2 | 4 | 2 | 2 | 0 | 1 |
| 22 | Chlorosilanes | 1 | 3 | 2 | 0 | 0 | 3 |
| 23 | Conjugated Dienes | 1 | 2 | 1 | 1 | 1 | 2 |
| 25 | Diazonium Salts | 0 | 0 | 0 | 0 | 0 | 5 |
| 30 | Fluorinated Organic Compounds | 1 | 1 | 0 | 0 | 0 | 5 |
| 36 | Insufficient Information for Classification *(비실질 카테고리 — 아래 참고)* | 1 | 3 | 2 | 1 | 0 | 0 |
| 37 | Isocyanates and Isothiocyanates | 2 | 4 | 2 | 0 | 1 | 2 |
| 44 | Nitrides, Phosphides, Carbides, and Silicides | 1 | 1 | 0 | 0 | 3 | 2 |
| 48 | Not Chemically Reactive agents | 2 | 4 | 2 | 2 | 1 | 0 |
| 52 | Oximes | 1 | 2 | 1 | 1 | 2 | 1 |
| 57 | Quaternary Ammonium and Phosphonium Salts | 2 | 5 | 3 | 1 | 1 | 0 |
| 62 | Siloxanes | 2 | 2 | 0 | 1 | 1 | 3 |

**그룹36 주의**: "Insufficient Information for Classification"은 PHASE 1부터 실질 화학 카테고리가 아니라고 확인된 그룹이다(Wave1 설계 당시 EXCLUDE 대상). 이 그룹에 ADD 2건이 걸렸지만 **실제 편입 대상에서 제외를 권고**한다 — 여기 채우는 건 "coverage 개선"이 아니라 "분류 불능 카테고리에 물질을 쌓는 것"이라 이번 감사의 목적(위험관계 재현)에 기여하지 않는다.

**Group 25를 제외한 13개 scarce 그룹 전체 결과**: 그룹30(Fluorinated Organic Compounds)·그룹44(Nitrides/Phosphides/Carbides/Silicides)·그룹62(Siloxanes) 3개 그룹은 ADD 후보가 0건으로 나와(각각 DATA_UNAVAILABLE 다수 또는 REJECT뿐) **scarcity가 이번 66개 후보 풀로는 해소되지 않는다** — 이 그룹들도 Group25만큼 심각하지는 않지만 같은 계열의 구조적 한계(KOSHA 커버리지 부족 또는 후보 자체가 이미 존재하는 물질과 중복)를 보인다.

## 4. 66개 후보 전체 감사 테이블

| CAS | 물질명 | 그룹 | KOSHA | §10 근거 | 중복 | 독립성 | decision | 사유 |
|---|---|---|---|---|:--:|---|---|---|
| 2312-35-8 | PROPARGITE | 10 Alkynes, with Acetylen | kosha_registered | no_data | N | - | **HOLD** | 그룹10(현재 1종) §10 근거 빈약 — 자동판정 애매, 사람 검토 필요 |
| 23950-58-5 | 3,5-DICHLORO-N-(1,1-DIMETHYL | 10 Alkynes, with Acetylen | kosha_registered | combustible_reducing;water | N | - | **ADD** | 그룹10(현재 1종) §10 실질 근거(['combustible_reducing', 'water']) 추가, 기존 조합과 비중 |
| 57-63-6 | ETHINYLESTRADIOL | 10 Alkynes, with Acetylen | kosha_registered | combustible_reducing;water | N | - | **ADD** | 그룹10(현재 1종) §10 실질 근거(['combustible_reducing', 'water']) 추가, 기존 조합과 비중 |
| 59355-75-8 | METHYLACETYLENE AND PROPADIE | 10 Alkynes, with Acetylen | kosha_registered | no_data | N | - | **HOLD** | 그룹10(현재 1종) §10 근거 빈약 — 자동판정 애매, 사람 검토 필요 |
| 1068-27-5 | 2,5-DIMETHYL-2,5-BIS(TERT-BU | 11 Alkynes, with No Acety | kosha_registered | combustible_reducing;water | N | - | **ADD** | 그룹11(현재 1종) §10 실질 근거(['combustible_reducing', 'water']) 추가, 기존 조합과 비중 |
| 2216-94-6 | ETHYL PHENYLPROPIOLATE | 11 Alkynes, with No Acety | kosha_abstain | - | N | - | **DATA_UNAVAILABLE** | KOSHA 미등록 또는 미시도 — MSDS 원문 자체가 없어 판단 불가 |
| 309-36-4 | SODIUM METHOHEXITAL | 11 Alkynes, with No Acety | kosha_abstain | - | N | - | **DATA_UNAVAILABLE** | KOSHA 미등록 또는 미시도 — MSDS 원문 자체가 없어 판단 불가 |
| 55406-53-6 | 3-IODO-2-PROPYNYL BUTYLCARBA | 11 Alkynes, with No Acety | kosha_registered | no_data | N | - | **HOLD** | 그룹11(현재 1종) §10 근거 빈약 — 자동판정 애매, 사람 검토 필요 |
| 105-40-8 | N-METHYLCARBAMIC ACID, ETHYL | 20 Carbamates | kosha_abstain | - | N | - | **DATA_UNAVAILABLE** | KOSHA 미등록 또는 미시도 — MSDS 원문 자체가 없어 판단 불가 |
| 10605-21-7 | CARBENDAZIM | 20 Carbamates | kosha_registered | no_data | N | - | **HOLD** | 그룹20(현재 2종) §10 근거 빈약 — 자동판정 애매, 사람 검토 필요 |
| 1111-78-0 | AMMONIUM CARBAMATE | 20 Carbamates | kosha_registered | combustible_reducing;water | N | - | **ADD** | 그룹20(현재 2종) §10 실질 근거(['combustible_reducing', 'water']) 추가, 기존 조합과 비중 |
| 1129-41-5 | METOLCARB | 20 Carbamates | kosha_registered | combustible_reducing;metal;water | N | - | **ADD** | 그룹20(현재 2종) §10 실질 근거(['combustible_reducing', 'metal', 'water']) 추가,  |
| 114-26-1 | PROPOXUR | 20 Carbamates | kosha_registered | no_data | N | - | **HOLD** | 그룹20(현재 2종) §10 근거 빈약 — 자동판정 애매, 사람 검토 필요 |
| 10137-69-6 | CYCLOHEXENYLTRICHLOROSILANE | 22 Chlorosilanes | kosha_abstain | - | N | - | **DATA_UNAVAILABLE** | KOSHA 미등록 또는 미시도 — MSDS 원문 자체가 없어 판단 불가 |
| 1125-27-5 | ETHYLPHENYLDICHLOROSILANE | 22 Chlorosilanes | kosha_abstain | - | N | - | **DATA_UNAVAILABLE** | KOSHA 미등록 또는 미시도 — MSDS 원문 자체가 없어 판단 불가 |
| 26571-79-9 | CHLOROPHENYLTRICHLOROSILANE | 22 Chlorosilanes | kosha_abstain | - | N | - | **DATA_UNAVAILABLE** | KOSHA 미등록 또는 미시도 — MSDS 원문 자체가 없어 판단 불가 |
| 27137-85-5 | DICHLOROPHENYLTRICHLOROSILAN | 22 Chlorosilanes | kosha_registered | metal;water | N | - | **ADD** | 그룹22(현재 1종) §10 실질 근거(['metal', 'water']) 추가, 기존 조합과 비중복 |
| 5894-60-0 | HEXADECYLTRICHLOROSILANE | 22 Chlorosilanes | kosha_registered | combustible_reducing;metal;water | N | - | **ADD** | 그룹22(현재 1종) §10 실질 근거(['combustible_reducing', 'metal', 'water']) 추가,  |
| 110-44-1 | SORBIC ACID | 23 Conjugated Dienes | kosha_registered | combustible_reducing;water | N | - | **REJECT** | 이미 동일 true_cameo_groups=(2, 23, 34) 조합 물질이 그룹23 내 존재 — 매트릭스 엔진 관점에서 정보 |
| 11103-57-4 | VITAMIN A | 23 Conjugated Dienes | kosha_abstain | - | N | - | **DATA_UNAVAILABLE** | KOSHA 미등록 또는 미시도 — MSDS 원문 자체가 없어 판단 불가 |
| 123-35-3 | MYRCENE, [LIQUID] | 23 Conjugated Dienes | kosha_registered | no_data | N | - | **HOLD** | 그룹23(현재 1종) §10 근거 빈약 — 자동판정 애매, 사람 검토 필요 |
| 129-17-9 | SULFAN BLUE | 23 Conjugated Dienes | kosha_registered | combustible_reducing;water | N | - | **ADD** | 그룹23(현재 1종) §10 실질 근거(['combustible_reducing', 'water']) 추가, 기존 조합과 비중 |
| 1406-16-2 | VITAMIN D3 EMULSIFIABLE | 23 Conjugated Dienes | kosha_abstain | - | N | - | **DATA_UNAVAILABLE** | KOSHA 미등록 또는 미시도 — MSDS 원문 자체가 없어 판단 불가 |
| 135072-82-1 | 4-DIMETHYLAMINO-6-(2-DIMETHY | 25 Diazonium Salts | kosha_abstain | - | N | - | **DATA_UNAVAILABLE** | KOSHA 미등록 또는 미시도 — MSDS 원문 자체가 없어 판단 불가 |
| 15005-97-7 | 3-(2-HYDROXYETHOXY)-4-PYRROL | 25 Diazonium Salts | kosha_abstain | - | N | - | **DATA_UNAVAILABLE** | KOSHA 미등록 또는 미시도 — MSDS 원문 자체가 없어 판단 불가 |
| 15557-00-3 | 3-CHLORO-4-DIETHYLAMINOBENZE | 25 Diazonium Salts | kosha_abstain | - | N | - | **DATA_UNAVAILABLE** | KOSHA 미등록 또는 미시도 — MSDS 원문 자체가 없어 판단 불가 |
| 21723-86-4 | 4-[BENZYL(ETHYL)AMINO]-3-ETH | 25 Diazonium Salts | kosha_abstain | - | N | - | **DATA_UNAVAILABLE** | KOSHA 미등록 또는 미시도 — MSDS 원문 자체가 없어 판단 불가 |
| 4421-50-5 | 4-[BENZYL(METHYL)AMINO]-3-ET | 25 Diazonium Salts | kosha_abstain | - | N | - | **DATA_UNAVAILABLE** | KOSHA 미등록 또는 미시도 — MSDS 원문 자체가 없어 판단 불가 |
| 111512-56-2 | 1,1-DICHLORO-1,2,3,3,3-PENTA | 30 Fluorinated Organic Co | kosha_abstain | - | N | - | **DATA_UNAVAILABLE** | KOSHA 미등록 또는 미시도 — MSDS 원문 자체가 없어 판단 불가 |
| 1172-18-5 | FLURAZEPAM DIHYDROCHLORIDE | 30 Fluorinated Organic Co | kosha_abstain | - | N | - | **DATA_UNAVAILABLE** | KOSHA 미등록 또는 미시도 — MSDS 원문 자체가 없어 판단 불가 |
| 127564-92-5 | DICHLOROPENTAFLUOROPROPANE | 30 Fluorinated Organic Co | kosha_abstain | - | N | - | **DATA_UNAVAILABLE** | KOSHA 미등록 또는 미시도 — MSDS 원문 자체가 없어 판단 불가 |
| 128903-21-9 | 2,2-DICHLORO-1,1,1,3,3-PENTA | 30 Fluorinated Organic Co | kosha_abstain | - | N | - | **DATA_UNAVAILABLE** | KOSHA 미등록 또는 미시도 — MSDS 원문 자체가 없어 판단 불가 |
| 13098-39-0 | HEXAFLUOROACETONE SESQUIHYDR | 30 Fluorinated Organic Co | kosha_abstain | - | N | - | **DATA_UNAVAILABLE** | KOSHA 미등록 또는 미시도 — MSDS 원문 자체가 없어 판단 불가 |
| 11099-03-9 | C.I. SOLVENT BLACK 5 | 36 Insufficient Informati | kosha_registered | combustible_reducing;water | N | - | **ADD** | 그룹36(현재 1종) §10 실질 근거(['combustible_reducing', 'water']) 추가, 기존 조합과 비중 |
| 8005-02-5 | C.I. SOLVENT BLACK 7 | 36 Insufficient Informati | kosha_registered | combustible_reducing;water | N | - | **ADD** | 그룹36(현재 1종) §10 실질 근거(['combustible_reducing', 'water']) 추가, 기존 조합과 비중 |
| 8016-38-4 | ORANGE FLOWER WATER | 36 Insufficient Informati | kosha_registered | no_data | N | - | **HOLD** | 그룹36(현재 1종) §10 근거 빈약 — 자동판정 애매, 사람 검토 필요 |
| 102-36-3 | ISOCYANIC ACID, 3,4-DICHLORO | 37 Isocyanates and Isothi | kosha_registered | combustible_reducing;metal;water | N | - | **ADD** | 그룹37(현재 2종) §10 실질 근거(['combustible_reducing', 'metal', 'water']) 추가,  |
| 10347-54-3 | 1,4-BIS(METHYLISOCYANATE)CYC | 37 Isocyanates and Isothi | kosha_abstain | - | N | - | **DATA_UNAVAILABLE** | KOSHA 미등록 또는 미시도 — MSDS 원문 자체가 없어 판단 불가 |
| 104-12-1 | P-CHLOROPHENYL ISOCYANATE | 37 Isocyanates and Isothi | kosha_registered | combustible_reducing;metal;water | N | - | **ADD** | 그룹37(현재 2종) §10 실질 근거(['combustible_reducing', 'metal', 'water']) 추가,  |
| 104-49-4 | 1,4-PHENYLENE DIISOCYANATE | 37 Isocyanates and Isothi | kosha_abstain | - | N | - | **DATA_UNAVAILABLE** | KOSHA 미등록 또는 미시도 — MSDS 원문 자체가 없어 판단 불가 |
| 110-78-1 | N-PROPYL ISOCYANATE | 37 Isocyanates and Isothi | kosha_registered | metal;water | N | - | **REJECT** | 이미 동일 true_cameo_groups=(37,) 조합 물질이 그룹37 내 존재 — 매트릭스 엔진 관점에서 정보량 중복 |
| 12058-85-4 | SODIUM PHOSPHIDE | 44 Nitrides, Phosphides,  | kosha_registered | water | N | - | **REJECT** | 이미 동일 true_cameo_groups=(44,) 조합 물질이 그룹44 내 존재 — 매트릭스 엔진 관점에서 정보량 중복 |
| 12737-18-7 | CALCIUM SILICIDE | 44 Nitrides, Phosphides,  | kosha_abstain | - | N | - | **DATA_UNAVAILABLE** | KOSHA 미등록 또는 미시도 — MSDS 원문 자체가 없어 판단 불가 |
| 1299-86-1 | ALUMINUM CARBIDE | 44 Nitrides, Phosphides,  | kosha_abstain | - | N | - | **DATA_UNAVAILABLE** | KOSHA 미등록 또는 미시도 — MSDS 원문 자체가 없어 판단 불가 |
| 1303-00-0 | GALLIUM ARSENIDE | 44 Nitrides, Phosphides,  | kosha_registered | no_data | N | - | **REJECT** | 이미 동일 true_cameo_groups=(44,) 조합 물질이 그룹44 내 존재 — 매트릭스 엔진 관점에서 정보량 중복 |
| 1305-99-3 | CALCIUM PHOSPHIDE | 44 Nitrides, Phosphides,  | kosha_registered | water | N | - | **REJECT** | 이미 동일 true_cameo_groups=(44,) 조합 물질이 그룹44 내 존재 — 매트릭스 엔진 관점에서 정보량 중복 |
| 12001-29-5 | ASBESTOS, WHITE | 48 Not Chemically Reactiv | kosha_registered | no_data | N | - | **REJECT** | 발암1급(석면류) — 기존 청석면(12001-28-4) 배제 선례와 동일 계열. coverage gain과 무관하게 안전/윤리 |
| 39300-88-4 | TARA GUM | 48 Not Chemically Reactiv | kosha_registered | combustible_reducing;water | N | - | **ADD** | 그룹48(현재 2종) §10 실질 근거(['combustible_reducing', 'water']) 추가, 기존 조합과 비중 |
| 67774-32-7 | POLYBROMINATED BIPHENYL | 48 Not Chemically Reactiv | kosha_registered | combustible_reducing;water | N | - | **ADD** | 그룹48(현재 2종) §10 실질 근거(['combustible_reducing', 'water']) 추가, 기존 조합과 비중 |
| 7439-90-9 | KRYPTON | 48 Not Chemically Reactiv | kosha_registered | no_data | N | - | **HOLD** | 그룹48(현재 2종) §10 근거 빈약 — 자동판정 애매, 사람 검토 필요 |
| 7440-01-9 | NEON | 48 Not Chemically Reactiv | kosha_registered | no_data | N | - | **HOLD** | 그룹48(현재 2종) §10 근거 빈약 — 자동판정 애매, 사람 검토 필요 |
| 107-29-9 | ACETALDEHYDE OXIME | 52 Oximes | kosha_registered | no_data | N | - | **REJECT** | 이미 동일 true_cameo_groups=(52,) 조합 물질이 그룹52 내 존재 — 매트릭스 엔진 관점에서 정보량 중복 |
| 110-69-0 | BUTYRALDOXIME | 52 Oximes | kosha_registered | - | N | - | **REJECT** | 이미 동일 true_cameo_groups=(52,) 조합 물질이 그룹52 내 존재 — 매트릭스 엔진 관점에서 정보량 중복 |
| 116-06-3 | ALDICARB | 52 Oximes | kosha_registered | no_data | N | - | **HOLD** | 그룹52(현재 1종) §10 근거 빈약 — 자동판정 애매, 사람 검토 필요 |
| 127-69-5 | SULFISOXAZOLE | 52 Oximes | kosha_registered | combustible_reducing;water | N | - | **ADD** | 그룹52(현재 1종) §10 실질 근거(['combustible_reducing', 'water']) 추가, 기존 조합과 비중 |
| 15271-41-7 | BICYCLO[2.2.1]HEPTANE-2-CARB | 52 Oximes | kosha_abstain | - | N | - | **DATA_UNAVAILABLE** | KOSHA 미등록 또는 미시도 — MSDS 원문 자체가 없어 판단 불가 |
| 121-54-0 | BENZETHONIUM CHLORIDE | 57 Quaternary Ammonium an | kosha_registered | combustible_reducing;metal;water | N | - | **ADD** | 그룹57(현재 2종) §10 실질 근거(['combustible_reducing', 'metal', 'water']) 추가,  |
| 122-19-0 | BENZYLDIMETHYLOCTADECYLAMMON | 57 Quaternary Ammonium an | kosha_registered | combustible_reducing;metal;water | N | - | **REJECT** | 이미 동일 true_cameo_groups=(47, 57) 조합 물질이 그룹57 내 존재 — 매트릭스 엔진 관점에서 정보량 중 |
| 124-64-1 | TETRAKIS(HYDROXYMETHYL)PHOSP | 57 Quaternary Ammonium an | kosha_registered | combustible_reducing;water | N | - | **ADD** | 그룹57(현재 2종) §10 실질 근거(['combustible_reducing', 'water']) 추가, 기존 조합과 비중 |
| 129-17-9 | SULFAN BLUE | 57 Quaternary Ammonium an | kosha_registered | combustible_reducing;water | N | - | **ADD** | 그룹57(현재 2종) §10 실질 근거(['combustible_reducing', 'water']) 추가, 기존 조합과 비중 |
| 1326-03-0 | C.I. PIGMENT VIOLET 1 | 57 Quaternary Ammonium an | kosha_registered | no_data | N | - | **HOLD** | 그룹57(현재 2종) §10 근거 빈약 — 자동판정 애매, 사람 검토 필요 |
| 1174-72-7 | TETRAPHENOXYSILANE | 62 Siloxanes | kosha_abstain | - | N | - | **DATA_UNAVAILABLE** | KOSHA 미등록 또는 미시도 — MSDS 원문 자체가 없어 판단 불가 |
| 1332-21-4 | ASBESTOS | 62 Siloxanes | kosha_registered | no_data | N | - | **REJECT** | 발암1급(석면류) — 기존 청석면(12001-28-4) 배제 선례와 동일 계열. coverage gain과 무관하게 안전/윤리 |
| 17928-28-8 | METHYLTRIS(TRIMETHYLSILOXY)S | 62 Siloxanes | kosha_registered | no_data | N | - | **HOLD** | 그룹62(현재 2종) §10 근거 빈약 — 자동판정 애매, 사람 검토 필요 |
| 2097-19-0 | PHENYLSILATRANE | 62 Siloxanes | kosha_abstain | - | N | - | **DATA_UNAVAILABLE** | KOSHA 미등록 또는 미시도 — MSDS 원문 자체가 없어 판단 불가 |
| 2288-13-3 | METHYLSILATRANE | 62 Siloxanes | kosha_abstain | - | N | - | **DATA_UNAVAILABLE** | KOSHA 미등록 또는 미시도 — MSDS 원문 자체가 없어 판단 불가 |

## 5. Coverage Before/After 요약

- 68그룹 커버리지: **67/68 → 67/68** (신규 커버 그룹: 없음)
- ADD 18건을 반영해도 **그룹 수준 커버리지는 그대로**다(67/68 유지) — Group25가 유일한 미커버 그룹인데 그쪽 5개 후보 전부 DATA_UNAVAILABLE이라 채워지지 않기 때문. 즉 이번 backfill의 실제 효과는 "새 그룹을 여는 것"이 아니라 **"이미 1~2종뿐이던 13개 그룹 중 10개의 scarcity를 완화하는 것"**이다(그룹36 제외 권고분 반영 시 순수 개선 그룹은 9개).
- ADD 18건 중 2건(그룹36)은 위 §3 사유로 실제 편입 후보에서 제외 권고 — **실질 권고 ADD는 16건**.
