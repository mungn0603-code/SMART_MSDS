# HAZARD-RELEVANT 판정 2차 검증 (샘플 감사) — 2026-08-08

대상: [chemical_selection_criteria_final_redesign_2026-08-08.md](chemical_selection_criteria_final_redesign_2026-08-08.md)의
HAZARD-RELEVANT 247건. `undergrad_target_chemicals.csv`/corpus는 이번에도 수정하지 않았다.

## 1. 실제 구현에서 HAZARD-RELEVANT 판정 로직

`build_final_selection_audit.py`의 `has_s10_evidence()`는
`chemical_selection_audit_dataset_2026-08-08.csv`의 `section10_categories` 필드가
`""`/`"no_data"`가 아니면 HAZARD-RELEVANT로 판정한다. 이 필드는 실제로
`02_classification/provenance_audit.py`가 생성하며, 원문 소스를 추적한 결과는 다음과 같다.

- **필드 소스**: `msds_sections` 테이블에서 `section=10 AND item_name_kor='피해야 할 물질'`
  (KOSHA MSDS 16항목 중 §10.5 "피해야 할 물질" — 정확히 "materials to avoid/incompatibility"
  항목이다. §10에는 이 외에 `화학적 안정성 및 유해 반응의 가능성`, `피해야 할 조건`(열/광 등 일반
  보관조건), `분해시 생성되는 유해물질` 3개 하위항목이 더 있으나 **이 파이프라인은 이들을 전혀 읽지
  않는다** — 즉 "일반 안전문구가 섞여 들어올 위험이 있는 항목"(피해야 할 조건 등)은 애초에 입력에
  포함되지 않는다.
- **분류 로직**: 이 텍스트 안에서 5개 키워드 카테고리(`가연성/환원성/환원제/인화성`→combustible_reducing,
  `금속`→metal, `산화제/산화성`→oxidizer, `물`→water, `자료없음`→no_data)를 단순 substring
  매칭한다(`provenance_audit.py:112-119`).
- **질문별 답**
  1. §10 청크 존재 여부만으로 분류하는가? → **아니다.** 텍스트가 있어도 위 5개 키워드 중 하나도
     안 걸리면(예: 다른 문구) `section10_categories`는 빈 문자열이 되어 HAZARD-RELEVANT가 되지 않는다.
  2. 실제 물질 간 반응성/incompatibility 관계를 판단하는가? → **부분적으로.** §10.5 필드 자체가
     "피해야 할 물질"(회피 대상 물질군)이므로 개념적으로는 맞으나, 실제 판단은 5개 키워드의
     "존재 여부"뿐이며 그 카테고리가 **이 물질 고유의 반응성과 실제로 연결되는지는 검증하지 않는다**
     (§4 참조).
  3. 일반 안전문구가 잘못 포함될 가능성? → 전수조사 결과(§10.5 필드, 466행 중 466행) **0건.**
     `보호구/환기/직사광선/밀폐/서늘/고온다습/화기엄금/점화원` 등 일반 문구 마커는 단 한 건도
     이 필드에서 발견되지 않았다 — 그런 문구는 애초에 "피해야 할 조건" 필드로 분리되어 있고
     파이프라인이 읽지 않기 때문.
  4. 동일 물질의 여러 §10 청크가 중복 집계되는가? → **아니다.** `(cas_number, section=10,
     item_name_kor='피해야 할 물질')` 조합은 DB에서 CAS당 정확히 1행이다(중복 0건, 직접 쿼리 확인).
  5. MSDS 데이터가 없거나 불완전하면? → §10.5 텍스트가 없으면 `""`(빈 문자열)로 처리되어
     `has_s10_evidence`가 `False` — 안전하게 HAZARD-RELEVANT 밖으로 빠진다. `자료없음`(명시적
     "no data")도 별도 카테고리로 잡혀 마찬가지로 제외된다(전체 466건 중 170건, 36.5%).

**발견된 코드 버그(결정 자체는 안 바꿈):** `water` 키워드가 `"물"` 한 글자 substring 매칭이라
`"물질"`(=substance, 거의 모든 문장에 등장하는 단어)의 부분 문자열로도 걸린다. §10.5 텍스트가 있는
466건 중 274건이 `물` substring을 포함하지만, 그중 **204건(74%)은 `물질`의 부분일 뿐 실제
"물"(water) 단독 언급이 아니다.** 다만 이 204건은 전부 `가연성`/`환원성` 같은 진짜 키워드도 같이
갖고 있어 HAZARD-RELEVANT 여부(케이스 통과/탈락) 자체를 바꾸지는 않는다 — `water` 서브태그와
그것을 인용한 `selection_reason` 문구, 그리고 `provenance_audit.py`의 텍스트-교차검증 통계
(`n_text_evidenced`)만 오염시킨다.

## 2. 샘플링 방법

247건 중 45건(18.2%)을 층화 추출했다(스크립트: 세션 내 1회성, 저장 안 함 — 방법은 재현 가능하도록
아래 기술). 무작위 1개 방식이 아니라 6개 층을 겹쳐서 뽑았다.

1. **그룹 다양성**: 247건이 걸쳐 있는 서로 다른 CAMEO 그룹 50개 중 25개 그룹에서 1건씩(그룹당
   CAS 오름차순 1번째, 결정적)
2. **§10 텍스트 길이 극단**: 최단 6건(길이 1~4자), 최장 6건(길이 79~107자)
3. **카테고리 조합별 최소 3건**: `section10_categories`의 5개 조합값(`water`/`metal`/
   `metal;water`/`combustible_reducing;water`/`combustible_reducing;metal;water`)마다 최소 3건 보장
4. **동일 그룹 클러스터**: 가장 큰 그룹(Group 50, Oxidizing Agents Strong)에서 4건 연속 추출 —
   동일/유사 그룹 내 판정 일관성 확인용
5. **랜덤 채움**: `seed=42`로 45건에 도달할 때까지 나머지에서 무작위 보충

결과 45건은 서로 다른 CAMEO 그룹 39개, 카테고리 조합 5종 전부, 텍스트 길이 1~107자 전 구간을
포함한다.

## 3~4. 샘플별 판정 결과 및 TRUE/FALSE/BORDERLINE 통계

전체 45건, 각 CAS의 §10.5 원문·CAMEO 그룹·판정 근거는 CSV 참고:
[chemical_hazard_relevant_sample_audit_2026-08-08.csv](../01_collection/chemical_hazard_relevant_sample_audit_2026-08-08.csv)

```
TRUE       23  (51.1%)
BORDERLINE 22  (48.9%)
FALSE       0  (0.0%)
```

정의:
```
confirmed_precision  = TRUE / (TRUE + FALSE) = 23 / 23        = 100.0%
false_positive_rate  = FALSE / n              = 0 / 45         = 0.0%
borderline_rate       = BORDERLINE / n         = 22 / 45        = 48.9%
```

**중요한 재확인**: "일반 안전문구"(§10.5가 아닌 다른 문구, 열/환기/보호구 등)로 인한 FALSE는
45건 중 0건, 그리고 앞서 전수조사(466건)에서도 0건이었다. 사용자가 정의한 FALSE 기준
(생활안전수칙류)에 해당하는 사례는 이 데이터셋에 사실상 존재하지 않는다.

## 5. False positive 분석 — 대신 발견한 것은 "BORDERLINE 과반"

FALSE는 0건이지만, BORDERLINE 22건(48.9%)은 전부 **동일한 하나의 패턴**이다: §10.5 텍스트에
"물"이나 "금속" 같은 구체적 물질군 언급 없이 `"가연성 물질, 환원성 물질"`(또는 `"가연성 물질"`
단독)만 있는 경우. `물` substring 버그를 보정해서(§1) 다시 집계하면:

- **표본 45건 중 21건(46.7%)**, **모집단 247건 중 118건(47.8%)** 이 이 패턴에 해당한다
  (표본 비율과 모집단 비율이 거의 일치 — 층화추출이 대표성을 잘 확보했다는 뜻).
- 이 118건 중 대다수는 **자기 자신의 true_cameo_groups에 가연성/환원제/산화제/물 관련 그룹이
  전혀 없다** (예: `4-CHLOROBENZALDEHYDE`는 Aldehydes/Aryl Halides/Aromatic Hydrocarbons
  그룹인데 §10 문구는 다른 무관 물질들과 토씨 하나 안 틀리고 동일한 `"가연성 물질, 환원성 물질"`).
  전체 KOSHA MSDS §10.5 필드에서 가장 흔한 텍스트 1~2위가 바로 이 문구(각각 63건, 66건)라는
  점도 이 문구가 "이 물질에 대한 개별 판단"이 아니라 **KOSHA MSDS 작성 시스템의 정형 기본값**일
  가능성을 시사한다.
- 물/금속처럼 구체적 물질을 지목하거나(예: `"금속|물"`), 실제 화학적으로 잘 알려진 위험군
  (예: Group 50 강산화제류의 `"가연성 물질과 혼합되지 않도록"` 계열 서술, 유기과산화물의
  가연물 격리 경고)과 맞물린 23건은 TRUE로 판정했다.
- FALSE로 판정할 만한, 즉 §10.5인데도 물질 정보가 전혀 없는 사례는 찾지 못했다(이런 사례는
  이미 `no_data`/빈 문자열로 걸러져 HAZARD-RELEVANT 후보에도 안 들어간다 — 파이프라인이
  구조적으로 방어하고 있다).

## 6. 발견된 대표적인 오분류 패턴

1. **범용 카테고리 문구 단독**(BORDERLINE 다수, 47.8%): `"가연성 물질, 환원성 물질"` 단독 —
   실질은 있으나(문구 자체는 프로젝트가 이미 쓰는 CAMEO risk_relation 개념인 "reducer"와 대응)
   그 문구가 이 물질에 특이적인지, KOSHA 서식의 기본값인지 원문만으로 구분 불가.
2. **`물` substring 버그**(코드 버그, 결정에는 영향 없음): `"물질"`의 부분 문자열로 `water`가
   전체 466건 중 204건에서 잘못 붙는다.
3. **화학적으로 의심스러운 개별 사례 1건**: `PLATINUM(7440-06-4)`의 §10.5가 `"물"` 단독인데,
   백금은 표준상태에서 물과 반응하지 않는 것으로 알려진 비활성 금속이다 — KOSHA 데이터 자체의
   품질 이슈로 보이며, 우리 코드 문제는 아니다.

## 7. 판정: CASE 2 — 기준의 문구만 수정

오분류(FALSE)율이 0%이므로 "기준 자체가 잘못됨"(CASE 3)은 아니다. 그러나 BORDERLINE이 거의
절반(48.9%)이라는 것은 "§10이 존재하면 HAZARD-RELEVANT"라는 현재 정의가 **너무 관대**하다는
뜻이다. 최소 수정만 제안한다.

**수정 전**: §10.5(피해야 할 물질) 텍스트가 5개 키워드 중 하나라도 걸리면 HAZARD-RELEVANT.

**수정 후 제안**:
- §10.5에 **구체적 물질군**(금속 / 물 / 산화제)이 명시되면 HAZARD-RELEVANT 그대로 유지.
- §10.5의 유일한 근거가 `"가연성 물질, 환원성 물질"`(범용 문구) 하나뿐이면, HAZARD-RELEVANT
  단독 근거로 인정하지 않고 **`HAZARD-RELEVANT-GENERIC`**으로 서브태그만 남긴 뒤, 원래
  분류 우선순위(§4 문서)의 다음 단계(REPRESENTATIVE → 없으면 UNJUSTIFIED)로 재평가한다.
- `물` substring 매칭은 `물질`을 제외하도록 최소 수정한다(예: `text.replace("물질","")`
  후 `물` 존재 확인) — 새 scoring 모델이 아니라 정규식/substring 한 줄 수정.

**이번 검증에서는 위 규칙을 코드에 적용하지 않았다.** 사용자 승인 후 `build_final_selection_audit.py`에
반영하면 된다(간단한 조건 추가 — 새 인프라 불필요).

## 8. 다음 단계 권고

1. (승인 시) 위 수정 규칙을 `build_final_selection_audit.py`에 반영 → HAZARD-RELEVANT
   247건 중 118건이 `HAZARD-RELEVANT-GENERIC`으로 재표시되고, 그중 REPRESENTATIVE 조건
   (그룹 회소)에 해당하지 않는 것들은 UNJUSTIFIED(근거 부족)로 넘어간다. **자동 삭제 없음** —
   기존 원칙 그대로 유지.
2. retrieval/marginal utility/평가셋 어떤 것도 이번 재평가에 개입시키지 않는다(요청 원칙 그대로).
3. 이 검증 결과를 반영한 뒤에만 141개 UNJUSTIFIED 인간 검수 단계로 넘어간다 — 118건이 추가로
   REVIEW 후보군에 합류할 수 있으므로, 순서상 이 검증이 먼저 반영되는 것이 맞다.
