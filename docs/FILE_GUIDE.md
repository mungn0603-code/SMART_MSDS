# FILE_GUIDE — 각 파일은 정확히 무엇을 하는가?

디렉터리 역할부터: `src/`는 다른 파일이 import하는 재사용 모듈, `scripts/`는
`python scripts/x.py`로 직접 실행하는 엔트리포인트, `data/`는 입력·중간 산출물,
`results/`는 평가·생성 결과, `archive/`는 폐기·기각된 것(각 하위폴더에 `NOTES.md`).

## src/ — 핵심 모듈

| 파일 | 역할 |
|---|---|
| `llm.py` | DeepSeek 클라이언트. `chat()`이 전 파이프라인의 유일한 LLM 호출 경로 — 429/503 재시도(backoff+jitter) 포함 |
| `retrieval.py` | FAISS(dense) + BM25 하이브리드 검색, RRF 융합, §10 boilerplate penalty |
| `pipeline.py` | MSDS 원문 → Normalize → Chunk(section 단위) → `rag_chunks` 적재 |
| `eval_generation.py` | Judge 채점(rule_based + LLM judge), `substance_confused`/`cas_in_text`(물질 혼동 진단) |
| `cameo_group_lookup.py` | CAS 쌍 → CAMEO 그룹 → 판정+사유 조회(Generation 프롬프트에 주입하는 "정답" 소스) |
| `compatibility_engine.py` | N종(3종 이상) 물질 조합 판정 — 전체 쌍을 계산해 worst-case 종합 |

## scripts/ — 실행 스크립트

### 1단계: 수집
| 파일 | 역할 |
|---|---|
| `kosha_msds_collector.py` | KOSHA MSDS Open API 수집(§2/3/9/10). `--target-csv`로 대상 지정. `chem_id IS NULL`(미등재 확정) 캐시도 적중 처리해 재조회하지 않는다 |
| `build_substance_registry.py` | `core_*.csv` 5종 → `substance_registry` 재생성(drop 후 전량 적재) + 자가검증([`REGISTRY.md`](REGISTRY.md)) |
| `kosha_registry_lookup.py` | registry ↔ KOSHA 등재 상태 점검 리포트(`--fetch`로 미조회분 실조회) |
| `pubchem_verify_groups.py` | PubChem 경로로 CAS→CAMEO 그룹 재검증([`DATA.md`](DATA.md)) |
| `build_undergrad_target_list.py`, `expand_by_reaction_frequency.py` | 타겟 물질 리스트 구성(웨이브1/2) |
| `backfill_group_replacements.py`, `backfill_round2_safety_filter.py`, `backfill_round3_manual_picks.py` | 결측/부적절 물질 대체 |
| `test_kosha_msds_collector.py` | 수집기 자체검증 |

### 2단계: 분류
| 파일 | 역할 |
|---|---|
| `build_chemical_group_membership.py` | CAS→CAMEO 그룹 매핑 테이블 시드 |
| `map_registry_cameo_groups.py` | registry 미매핑 CAS를 PubChem `hid=86`으로 조회해 CAMEO 그룹 적재(`--write`). 분자식 대조로 CID 오식별 차단([`REGISTRY.md`](REGISTRY.md) 7절) |
| `service_contract_audit.py` | 서비스 계약 5조건 재대조 + A/B1/C/X 티어 재계산([`REGISTRY.md`](REGISTRY.md) 6절) |
| `seed_reactivity_reference.py`, `seed_self_reactivity.py` | 68×68 매트릭스/자기반응성 테이블 시드 |
| `group_fallback.py` | 결측 물질의 같은-그룹 대체 후보 추천 |
| `section10_baseline.py`, `provenance_audit.py` | §10 근거 실측·선정 근거 추적 감사 |
| `backfill_candidate_probe.py`, `backfill_coverage_gain.py` | 그룹 커버리지 보강 후보 조사 |
| `fix_missing_common_chemicals.py` | 결측 공통물질 보정 |
| `build_final_selection_audit.py` | 173종 최종 선정 감사([`DATA.md`](DATA.md)) |

### 4단계: RAG(검색+생성) 최종 파이프라인
| 파일 | 역할 |
|---|---|
| `evalset.py`, `evalset_pairs.py` | 평가셋 생성(단일물질 fact / 물질쌍 pair, gold_evidence 포함). `evalset.py`는 item 청크 기반이라 2026-08-24 이후 재실행 불가 — 산출물은 `data/evalset/`에 보존 |
| `run_ab.py` | Retrieval A/B 평가 드라이버(Recall/MRR/nDCG/Hit, [`RETRIEVAL.md`](RETRIEVAL.md)). `--granularity section`으로 쓸 것 — 기본값 `both`의 item 쪽은 청크가 없어 빈 코퍼스가 된다 |
| `freeze_retrieval.py` | STEP1 — Retrieval 결과를 top-10으로 고정(`results/frozen_retrieval_top10.jsonl`) |
| `generate_baseline.py` | STEP2/3 — baseline 프롬프트로 생성(LLM이 직접 판정하던 1차 버전) |
| `run_cameo_context_pilot.py` | CAMEO-context 프롬프트 정의 + 13건 파일럿(v1~v5 프롬프트 반복이 이 파일 하나에 누적) |
| `run_cameo_full.py` | **최종 채택 파이프라인** — 2,160건 전수 생성+채점, 동시실행(ThreadPoolExecutor) |
| `run_cameo_v5_retry.py` | v4 결과 중 unfaithful 203건만 v5 프롬프트로 표적 재시도 |
| `analyze_generation.py` | STEP5 — Retrieval×Generation 분리분석([`GENERATION.md`](GENERATION.md)) |
| `seed_core_corpus.py` | Registry 물질 중 청크·CAMEO 그룹이 둘 다 있는 것을 `rag_corpus_membership`의 `corpus_tag='core'`로 편입([`REGISTRY.md`](REGISTRY.md) §8 4단계) |
| `build_pair_report.py` | 전수실행 산출물(`generation_cameo_full.jsonl` + `eval_cameo_full.jsonl`)을 단일 HTML 보고서로 렌더링. 읽기 전용, 재생성 없음 |
| `test_pipeline.py` | `pipeline.py` 자체검증 |

## data/ — 입력·중간 산출물

| 항목 | 내용 |
|---|---|
| `reactivity_reference.db` | SQLite 진실원본(전 테이블) |
| `schema.sql` | DB 스키마 원본 |
| `collection/` | 수집 단계 CSV/로그(선정 리스트, PubChem 검증 리포트 등) |
| `collection/core_*.csv` (5종) | **Registry 237종의 기준 목록** — CORE 5축별 물질과 편입 근거(`course`/`experiment`/`note`) |
| `collection/registry_additions_2026-08-22.csv` | 207→237 확장분 30종의 편입 근거([`REGISTRY.md`](REGISTRY.md) §7) |
| `collection/registry_core207.csv` | 확장 이전 CORE 207종 목록 — `service_contract_audit.py`가 물질별 origin(CORE207/신규)을 가르는 데 쓴다 |
| `collection/core_gap_kosha_target.csv` | 207→237 확장 후보의 KOSHA 등재 확인용 조회 입력 |
| `collection/core_chunk_target_2026-08-22.csv` | 청킹 대상 39종(B1 티어) — `pipeline.py --target-csv` 입력 |
| `collection/kosha_unlisted_39.csv` | KOSHA MSDS 미등재 39종 — 3경로 실조회로 확정, 앱 선택 목록에서 제외되는 물질 |
| `evalset/` | `gold_pair.jsonl`(물질쌍 평가셋, gold_evidence 포함) 등 4종 |
| `chunks/` | 청킹된 MSDS 본문 `.md`. `section/`만 유효 — `item/`은 2026-08-23 생성 중단, DB의 item 청크 18,200행은 2026-08-24 삭제(A/B 종료, section 채택) |
| `index/` | FAISS/BM25 인덱스·임베딩 캐시(재현용, 재실행 시 자동 재생성 가능) |
| `boilerplate_sec10_values.json` | §10 정형문구 15종 실측 기록(코드는 더 이상 참조 안 함, [`RETRIEVAL.md`](RETRIEVAL.md)) |

## results/ — 평가·생성 산출물

| 파일 | 내용 |
|---|---|
| `frozen_retrieval_top10.jsonl` | STEP1 고정 Retrieval 결과(2,160건) |
| `generation_baseline.jsonl` / `eval_generation.jsonl` | STEP2~4 baseline(LLM 직접판정) 생성/채점 |
| `step5_summary.json` / `step5_failure_sample.jsonl` / `step5_condensed_review.txt` / `step5_clean_correct_sample.jsonl` | STEP5 실패분석 산출물 |
| `cameo_lookup_full_check.json` / `*_mismatches.jsonl` / `*_no_group.jsonl` | CAMEO 조회가 matrix_verdict와 100% 일치함을 검증한 기록 |
| `generation_cameo_pilot_v4.jsonl` / `eval_cameo_pilot_v4.jsonl` | v4 프롬프트 13건 파일럿 |
| `unfaithful_v4_ids.json` | v4 전수실행에서 unfaithful로 나온 203건 query_id 목록(v5 재시도 입력) |
| `generation_cameo_v5_retry.jsonl` / `eval_cameo_v5_retry.jsonl` | v5 표적 재시도(203건) 결과 |
| `generation_cameo_full.jsonl` / `eval_cameo_full.jsonl` | **최종 산출물** — v4 전수 + v5 병합본, 2,160건 |
| `cameo_unfaithful_detail.txt`, `class_vocab_probe.txt` | 진단용 원문 덤프(각각 unfaithful 사례/§2 어휘 확인) |
| `02_embedding_pair_sec210*.csv/.md`, `retrieval_experiments_*`, `step3_final_baseline_comparison.md` | Retrieval 단계 실험 기록([`RETRIEVAL.md`](RETRIEVAL.md)) |
| `kosha_missing39_probe_2026-08-22.csv` | 미등재 39종을 CAS/국문명/영문명 3경로로 실조회한 근거(전부 0건) |
| `corpus96_core_reassessment_2026-08-22.csv` / `registry_expansion_proposal_2026-08-22.csv` | 코퍼스 전용 96종 재평가 + 신규 후보 26종 판정표 |
| `registry237_service_contract_2026-08-22.csv` → `_after_reindex_` → `_after_cameo_` | Registry 237종 서비스 계약 대조표 3판(인덱스 23종 편입 전 / 후 / CAMEO 매핑 확충 후). 생성은 `service_contract_audit.py` |
| `registry_cameo_mapping_2026-08-22.csv` | 미매핑 95종의 PubChem `hid=86` 조회 결과 전량(status·CID·분자식 대조·제외 사유) |
| `kosha_registry_lookup.csv` | `kosha_registry_lookup.py --fetch` 출력 — registry 전체의 KOSHA 등재 상태 스냅샷 |
| `pair_verdict_report.html` | 위 최종 산출물을 사람이 훑어보는 용도로 렌더링한 것(`build_pair_report.py` 출력) |

## docs/ — 표준 문서 9종

`README.md`(루트) + `PIPELINE.md`/`DATA.md`/`REGISTRY.md`/`RETRIEVAL.md`/`GENERATION.md`/
`FILE_GUIDE.md`(이 문서) + `HANDOFF.md`/`PROJECT_LOG.md`. 각 문서가 답하는 질문은 루트
`README.md`의 표 참고. **어떤 물질을 다루는가**는 [`REGISTRY.md`](REGISTRY.md)가 단일 출처다.

## archive/ — 폐기·기각

| 폴더 | 내용 |
|---|---|
| `01_collection/` | 수집 단계 실행 로그·폐기 CSV |
| `02_pubchem_rejected/` | 기각된 PubChem SDF 매핑 경로 |
| `04_rag_agent/` | Retrieval 단계 — 섹션필터 전 폐기 A/B 결과 |
| `generation_experiments/` | Generation 단계 — 기각된 prompt v2/v2.1, Cascade Judge, RAGAS |
| `superseded_docs/` | 8개 표준 문서에 흡수된 원본 상세 문서(decisions.md 등) |
| `design_docs/` | 설계 철학 자체가 교체되며 폐기된 문서 |
| `chemical_selection_2026-08-08/` | 화학물질 선정 재설계 이전 시행착오 |
| `adhoc_check_scripts/` | 특정 이슈 조사용 1회성 스크립트 |

각 폴더의 `NOTES.md`에 무엇을 왜 옮겼는지 상세 기록.
