# SMART_MSDS — 화학물질 혼재보관 위험성평가 RAG

단독 포트폴리오 프로젝트. 2026-08-07 시작, RAG 파이프라인은 **2026-08-17 완주**. 원격 저장소 `mungn0603-code/SMART_MSDS`.
평가 파이프라인(검색·생성·채점)은 재현 모드다 — 확정 지표를 낸 경로(`run_ab.py`/`freeze_retrieval.py`/`run_cameo_full.py`)는 건드리지 않는다.
**서비스 계층(Registry·KOSHA 연동·앱)은 2026-08-22에 확장했다.** 어느 쪽 작업인지 먼저 구분한다.

## 물질 선정 (2026-08-22 확정)

**서비스 물질 선정의 기준은 `substance_registry` 하나다.** CORE 5축(periodic_element 118 / practical 37 / representative 31 / educational 26 / fundamental 25) = **237종**, 그중 KOSHA 등재 **198종**이 앱 선택 대상이다.

과거의 "Registry ∪ 173" 규칙은 폐기됐다. 173종 코퍼스는 **검색 인덱스와 평가 재현용 자산**이지 선정 근거가 아니다. 물질을 넣고 빼는 판단은 전부 `docs/REGISTRY.md`를 따른다 — 특히 데이터가 있다는 이유로 편입하지 않는다(그게 project_173을 폐기한 이유다).

등록 ≠ 서비스다. 상세정보(`msds_sections`)·검색 근거(`rag_chunks`+인덱스 태그)·판정(`chemicals` 매핑)은 각각 별개 조건이고, `chemicals` 매핑이 없으면 `judge_pair_by_cas`가 무조건 Abstain한다. 현재 이행률 A 173 / B1 0 / C 25 / X 39.

## 타협 불가 원칙

**CAMEO 매트릭스의 판정을 LLM이 다시 판단하지 않는다.** LLM 역할은 판정이 아니라 설명이다 — 매트릭스 판정을 그대로 받아 MSDS §2/§10 원문으로 근거를 붙인다. 근거가 부족하면 Abstain.

이게 이 프로젝트의 핵심 성과다. LLM이 직접 판정하던 baseline은 정답률 19.8%(과잉기각 46.1%, 과잉위험판정 30.9%)였고, 역할을 설명으로 바꾼 v4가 99.9%다. 되돌리지 않는다.

## 구조 (2026-08-17 재편 후)

- `src/` — 핵심 모듈. `pipeline.py` `retrieval.py` `compatibility_engine.py` `cameo_group_lookup.py` `llm.py` `eval_generation.py`
- `scripts/` — 1회성 수집·구축·실험 스크립트
- `data/` — SQLite(`reactivity_reference.db`), chunks, index, evalset
- `results/` — 실행 결과 jsonl/csv. 덮어쓰지 말고 새 파일로 남긴다.
- `docs/` — 표준 문서 9종(README/PIPELINE/DATA/**REGISTRY**/RETRIEVAL/GENERATION/FILE_GUIDE/HANDOFF/PROJECT_LOG). 사실 확인은 여기부터. "어떤 물질을 다루는가"는 REGISTRY.md가 단일 출처.
- `app/streamlit_app.py` — 조회·판정 UI. `--check`로 LLM 없이 자가검증 가능.
- `archive/` — 폐기된 접근(PubChem 기각, rag_agent 등). 참고용이며 되살리지 않는다.

## 스택

SQLite · 임베딩 `dragonkue/BGE-m3-ko` · FAISS(dense) + BM25(kiwipiepy) 하이브리드 + RRF + §10 boilerplate penalty · LLM은 Upstage `solar-pro3`(reasoning_effort=high, Generation과 Judge 겸용 — 실제 값은 `src/llm.py`의 `MODEL`) · 평가는 자체 rule + LLM Judge (RAGAS는 n=7 파일럿 후 폐기, 재개하지 않음)

## 확정 지표

**Retrieval — service 기준 (쌍 질의 2,240건, 2026-08-29)**

Recall@10 0.8987 · Hit@10 0.9790 · MRR 0.8803 · nDCG@10 0.8065

조건: `corpus_tag='service'` 173종 / 371청크(§2·§10) / 450쌍 × 템플릿 5 = 2,250질의 중 gold_evidence 없는 10건 제외. 채점은 evidence 기준(gold_evidence = §2 100%)이고, gold_section 기준 수치와 섞어 쓰지 않는다. 숫자를 인용할 때는 이 조건을 반드시 함께 적는다.

**Generation — service 기준 (쌍 질의 2,240건, 2026-08-29)**

정답률(판정줄) 99.9% (2,238/2,240) · 정답률(judge 재분류) 83.9% (1,852/2,207) · faithful 94.6% (2,120/2,240) · 물질혼동 14.7% (307/2,093) · 판정줄–본문 일치 82.9%

조건: Upstage `solar-pro3` / 프롬프트 `cameo_service_v6` / `corpus_tag='service'` 173종 371청크 / frozen top-10 / 생성·채점 실패 0건. **정답률은 두 정의를 반드시 함께 적는다** — 판정줄 기준만 쓰면 아래 과잉위험 서술 문제가 숨는다. 지표 정의는 `scripts/summarize_cameo_full.py` docstring이 단일 출처다.

**판정줄 기준 오답은 0건이다**(뒤집힌 판정 없음, None 2건은 판정어 미기재). 그러나 judge 불일치 355건 중 323건이 "본문을 더 위험하게 읽음"이고, 그중 301건이 matrix=Caution인데 본문은 Incompatible로 읽힌 건이다 — 그 301건 전부 판정줄은 Caution으로 정확히 썼다. **판정은 지키되 본문 서술이 판정보다 세다**는 뜻이고, 이게 남은 최대 결함이다.

물질혼동 14.7%는 하락이 아니라 **처음 측정된 값**이다. 종전 "0/2,142"는 공허했다 — 이 지표는 답변의 `[사용한 근거: n, ...]` 태그를 파싱하는데 구 프롬프트가 그 태그를 요구하지 않아 아카이브 2,160건 전건이 측정 불가(None)였다. `cameo_service_v6`에서 태그 출력을 요구해 93.8%가 측정 가능해졌다.

173/Nemotron 값(정답률 99.9%, faithful 97.2%)은 `archive/2026-08-17_baseline/`에 보존한다. 코퍼스·모델·프롬프트가 모두 달라 **직접 비교 대상이 아니다.**

N종 조합 판정은 `compatibility_engine.py`의 `judge_combination_by_cas`로 구현돼 있지만 **검색 실측 지표는 쌍 단위까지만** 있다.

## 미완성 (README에 명시된 것)

- **본문 서술이 판정보다 강한 문제(최대 결함)**: matrix=Caution 745건 중 301건이 본문상 Incompatible로 읽힌다. 판정줄은 전부 Caution으로 정확하다. 판정줄–본문 일치 82.9%
- 물질 혼동 14.7%(307/2,093): 검색 top-10에 섞인 제3물질 청크를 이 쌍의 근거로 인용. 인용 태그 미출력 6.2%는 측정 불가로 남는다
- faithful 잔여 실패 5.4%(120건, service 기준): 그룹 분류를 확인된 반응처럼 단정하는 패턴
- Reranker 미실행 (boilerplate penalty로 목표를 충족해 보류)
- 원본 173종 이전 풀 전체의 안전성 재검증 미완
- CAMEO 매핑 173/237(73.0%) — **판정 가능 쌍 76.3%로 확정**(2026-08-23). 남은 25종은 CAMEO에 데이터시트 자체가 없다(PubChem hid=86 + CAMEO `/browse` 두 경로 확인). 목표는 100%가 아니다
- RAG 검색이 앱 UI에 미연결 — `explain()`/`retrieve()`의 호출 지점이 아직 `--check`뿐

## 주의

- 루트 `.env`에 자격증명이 있다. 읽지 않는다.
- 하위에 `SMART_MSDS/` 디렉터리가 통째로 중복 존재한다(자체 `.git` 포함, 재편 과정의 잔재). 작업은 루트에서 하고 중복본은 수정하지 않는다.
