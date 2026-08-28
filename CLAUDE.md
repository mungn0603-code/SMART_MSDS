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

SQLite · 임베딩 `dragonkue/BGE-m3-ko` · FAISS(dense) + BM25(kiwipiepy) 하이브리드 + RRF + §10 boilerplate penalty · LLM은 DeepSeek `deepseek-v4-flash`(thinking mode, Generation과 Judge 겸용 — 실제 값은 `src/llm.py`의 `MODEL`) · 평가는 자체 rule + LLM Judge (RAGAS는 n=7 파일럿 후 폐기, 재개하지 않음)

## 확정 지표

**Retrieval — service 기준 (쌍 질의 2,240건, 2026-08-29)**

Recall@10 0.8987 · Hit@10 0.9790 · MRR 0.8803 · nDCG@10 0.8065

조건: `corpus_tag='service'` 173종 / 371청크(§2·§10) / 450쌍 × 템플릿 5 = 2,250질의 중 gold_evidence 없는 10건 제외. 채점은 evidence 기준(gold_evidence = §2 100%)이고, gold_section 기준 수치와 섞어 쓰지 않는다. 숫자를 인용할 때는 이 조건을 반드시 함께 적는다.

**Generation — service 기준 미측정.**

정답률 99.9% / faithful 97.2% / 물질혼동 0/2,142는 `corpus_tag='173'` 코퍼스에서 낸 값이다. 그 코퍼스는 2026-08-28에 서비스 범위에서 내려왔으므로 **service의 지표가 아니다.** 인용하려면 "173 평가 코퍼스 기준"을 반드시 붙인다. service 기준 값을 얻으려면 `run_cameo_full.py`를 새 평가셋으로 재실행해야 한다(미실행).

N종 조합 판정은 `compatibility_engine.py`의 `judge_combination_by_cas`로 구현돼 있지만 **검색 실측 지표는 쌍 단위까지만** 있다.

## 미완성 (README에 명시된 것)

- faithful 잔여 실패 2.8%(61건): 그룹 분류를 확인된 반응처럼 단정하는 패턴
- Reranker 미실행 (boilerplate penalty로 목표를 충족해 보류)
- 원본 173종 이전 풀 전체의 안전성 재검증 미완
- CAMEO 매핑 173/237(73.0%) — **판정 가능 쌍 76.3%로 확정**(2026-08-23). 남은 25종은 CAMEO에 데이터시트 자체가 없다(PubChem hid=86 + CAMEO `/browse` 두 경로 확인). 목표는 100%가 아니다
- RAG 검색이 앱 UI에 미연결 — `explain()`/`retrieve()`의 호출 지점이 아직 `--check`뿐

## 주의

- 루트 `.env`에 자격증명이 있다. 읽지 않는다.
- 하위에 `SMART_MSDS/` 디렉터리가 통째로 중복 존재한다(자체 `.git` 포함, 재편 과정의 잔재). 작업은 루트에서 하고 중복본은 수정하지 않는다.
