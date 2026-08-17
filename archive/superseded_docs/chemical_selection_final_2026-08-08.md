# 화학물질 선정 최종 확정 (2026-08-08)

이 문서는 화학물질 corpus 선정 작업의 **최종·동결(FROZEN)** 결과와 그 전체 lifecycle을
기록한다. 과거에 시도했던 접근법은 상세히 재서술하지 않고, 폐기되었다는 사실과 그
산출물이 archive에 보존되어 있다는 사실만 남긴다.

핵심은 세 가지다: **왜 기존 방법을 버렸는가, 어떤 단순한 기준으로 다시 선정했는가,
왜 최종 173개가 나왔는가.**

## Lifecycle

```
426 Existing Corpus
        │
        ▼
PHASE 1
Existing Selection Audit
        │
        ▼
PHASE 2
Criteria Redesign
        │
        ▼
PHASE 3
Full-Corpus Application
        │
        ▼
PHASE 4
Targeted Validation
+ CASE 2 Minimal Fix
        │
        ▼
PHASE 5
Final Selection Freeze
        │
        ├── 30  MANDATORY
        ├── 129 HAZARD-RELEVANT
        ├── 14  REPRESENTATIVE
        └── 253 UNJUSTIFIED
        │
        ▼
173 FINAL KEEP
        │
        ▼
PHASE 6
Archive & Handoff
```

## PHASE 1 — Existing Selection Audit

기존 426개 corpus가 어떤 논리로 구성되었는지 실제 코드·데이터를 추적해 확인한 문제:

- `pool_supplement`/`pool_topup` 자동 보충으로 개별 선정 근거가 없는 물질이 다수 포함됨
- Phase마다 서로 다른 candidate set(`259proposed`, `phase6_D`, `phase7_D`, `phase8_E` 등)이
  동시에 존재해 authoritative selection이 불명확함
- retrieval/eval 결과가 selection 의사결정에 개입함
- eval set이 corpus에서 파생되어 selection과 evaluation 사이에 순환 의존성이 발생함
- target count가 고정·변경되며 물질 수 자체가 선정 논리에 영향을 줌

→ 원칙: **Selection은 Retrieval Evaluation과 독립되어야 한다.**

## PHASE 2 — Selection Criteria Redesign

기존 로직을 폐기하고 근거 기반 단순 우선순위로 재정의했다.

1. **MANDATORY** — 교육과정/커리큘럼상 명확히 필요한 물질
2. **HAZARD-RELEVANT** — KOSHA MSDS §10.5("피해야 할 물질")에서 물질 간 의미 있는
   반응성/incompatibility 정보가 확인되는 물질(일반 안전문구만으로는 불충분)
3. **REPRESENTATIVE** — CAMEO 구조에서 희소한 대표성을 가져 별도 대표물질이 필요한 경우
4. **UNJUSTIFIED** — 위 세 기준에 해당하지 않고 현재 근거로 독립적 선정 이유를 설명할 수 없는 경우

최종 selection 기준에 사용하지 않는 것: retrieval metrics(hit@k/recall/MRR), eval-set
membership, marginal utility, target corpus size/quota.

## PHASE 3 — Full-Corpus Application

재정의한 기준을 426종 corpus 전체에 적용했다(목적은 새 기준 적용이지 특정 물질 수 맞추기가 아님).

```
MANDATORY        30
HAZARD-RELEVANT 247
REPRESENTATIVE    8
UNJUSTIFIED     141
```

## PHASE 4 — Targeted Validation & CASE 2 Fix

전체 methodology를 재설계하지 않고, HAZARD-RELEVANT 판정이 §10.5 데이터를 과도하게
포함하는지 샘플 감사로 제한적으로 검증했다. 발견한 문제:

1. `"가연성 물질, 환원성 물질"` 같은 generic-only 문구가 단독 HAZARD-RELEVANT 근거로 포함됨
2. `"물"` substring 매칭이 `"물질"`의 부분 문자열까지 water로 인식하는 false positive

수정(다른 selection logic은 변경하지 않음):

- generic-only §10.5 문구는 단독 HAZARD-RELEVANT 근거로 인정하지 않음
- `"물"` substring matching 제거
- 실제 substance-specific 물질군(금속/물/산화제)만 HAZARD-RELEVANT 근거로 인정

이 변경은 선정 기준의 재설계가 아니라 **명백한 과잉포함과 매칭 버그에 대한 최소 수정**이다.

## PHASE 5 — Final Selection Freeze

CASE 2 수정 후 426종을 재산출하고 최종 selection을 동결했다.

```
MANDATORY        30
HAZARD-RELEVANT 129
REPRESENTATIVE   14
UNJUSTIFIED     253
───────────────────
TOTAL           426

30 + 129 + 14 = 173  → Final Chemical Selection
```

**최종 KEEP: 173 / 426 (40.6%)**

253개 UNJUSTIFIED는 추가 전수 인간 검수 없이 이번 최종 집합에서 제외한다. 이는 "불필요
하다고 증명됨"이 아니라, **현재 확정된 selection criteria와 확보된 근거만으로는 이번
corpus에 반드시 포함할 충분한 근거가 확인되지 않았다**는 의미로 기록한다.

**Selection Freeze 원칙**: 여기서 기준과 최종 집합을 동결한다. 향후 retrieval 성능이나
eval 결과가 나오더라도 이를 소급하여 selection 기준에 반영하지 않는다. 추가 물질이
필요하다고 판단되면 새로운 근거를 가진 별도 change request로 처리한다.

## PHASE 6 — Archive & Handoff

**Authoritative / Live** (archive 밖에 유지):

- [`docs/chemical_selection_final_2026-08-08.md`](chemical_selection_final_2026-08-08.md) — 본 문서
- [`01_collection/chemical_selection_final_2026-08-08.csv`](../01_collection/chemical_selection_final_2026-08-08.csv) — 최종 173개, CAS 중복 없음
- [`01_collection/chemical_selection_final_audit_2026-08-08.csv`](../01_collection/chemical_selection_final_audit_2026-08-08.csv) — 426종 전체 4분류 감사 기록

**Reproducibility** — 최종 audit 재생성에 필요해 live로 유지되는 파일(임의 이동하지 않음):

- `01_collection/chemical_selection_audit_dataset_2026-08-08.csv`
- `02_classification/provenance_audit.py`
- `01_collection/build_final_selection_audit.py`

**Archive** — 중간 candidate set, 과거 methodology, 샘플 감사, CASE 2 비교 등은
[`archive/chemical_selection_2026-08-08/`](../archive/chemical_selection_2026-08-08/README.md)에
historical/provenance record로 보존한다. Phase 3~8의 과거 candidate set들은 최종
methodology의 정식 Phase가 아니라 당시 탐색·시행착오의 기록이다.

---

**Chemical Selection is frozen at 173 substances as of 2026-08-08.**

The selection process is intentionally separated from retrieval evaluation. Future
retrieval/RAG results must not retroactively redefine the selection criteria.
