# FILE_GUIDE — 각 파일은 정확히 무엇을 하는가?

디렉터리 역할부터: `src/`는 다른 파일이 import하는 재사용 모듈, `scripts/`는
`python scripts/x.py`로 직접 실행하는 엔트리포인트, `tests/`는 자가검증,
`app/`은 Streamlit UI, `data/`는 입력·중간 산출물, `results/`는 **현행** 평가·생성 결과,
`archive/`는 폐기·대체된 것(각 하위폴더에 `NOTES.md`).

> **최종 갱신 2026-08-30 — 저장소 정리.** `scripts/` 1회성 14종과 Generation v6·v8·v9
> 산출물을 `archive/`로 옮기고, 테스트 4종을 `tests/`로 분리했다. 삭제한 파일은 없다.

## app/ — 서비스

| 파일 | 역할 |
|---|---|
| `streamlit_app.py` | 조회·판정 UI. `python app/streamlit_app.py --check`로 LLM 없이 자가검증. **근거 수집은 `pair_context()`(CAS 직접조회 §2+§10)** — 검색을 타지 않는다. 읽는 데이터 파일은 `data/reactivity_reference.db` 하나다 |

앱이 import하는 모듈: `src/` 6종(`pipeline.py` 제외) + `scripts/generate_baseline.py`
+ `scripts/run_cameo_context_pilot.py`. **이 둘은 실행 스크립트인 동시에 앱의 런타임
의존이다** — 옮기거나 이름을 바꾸면 앱이 죽는다.

## src/ — 핵심 모듈

| 파일 | 역할 |
|---|---|
| `llm.py` | Upstage Solar 클라이언트(`solar-pro3`). `chat()`이 전 파이프라인의 유일한 LLM 호출 경로 — 429/503 재시도(backoff+jitter) 포함 |
| `retrieval.py` | FAISS(dense) + BM25 하이브리드 검색, RRF 융합, §10 boilerplate penalty. **현재 서비스 경로 아님** — 자유 질의용으로 보존 |
| `pipeline.py` | MSDS 원문 → Normalize → Chunk(section 단위) → `rag_chunks` 적재 |
| `eval_generation.py` | Judge 채점(rule_based + LLM judge), `substance_confused`/`cas_in_text`(물질 혼동 진단) |
| `cameo_group_lookup.py` | CAS 쌍 → CAMEO 그룹 → 판정+사유 조회(Generation 프롬프트에 주입하는 "정답" 소스) |
| `compatibility_engine.py` | N종(3종 이상) 물질 조합 판정 — 전체 쌍을 계산해 worst-case 종합 |
| `kr_glossary.py` | CAMEO 68그룹·위험코드 11종·발생가스 48종의 영문→한글 고정 사전. 정적 dict 3개, 번역 API 없음 |

## scripts/ — 실행 스크립트 24종

### 수집·Registry
| 파일 | 역할 |
|---|---|
| `kosha_msds_collector.py` | KOSHA MSDS Open API 수집(§2/3/9/10). `--target-csv`로 대상 지정. `chem_id IS NULL`(미등재 확정) 캐시도 적중 처리해 재조회하지 않는다 |
| `build_substance_registry.py` | `core_*.csv` 5종 → `substance_registry` 재생성(drop 후 전량 적재) + 자가검증([`REGISTRY.md`](REGISTRY.md)) |
| `kosha_registry_lookup.py` | registry ↔ KOSHA 등재 상태 점검 리포트(`--fetch`로 미조회분 실조회) |
| `service_contract_audit.py` | 서비스 계약 5조건 재대조 + A/B1/C/X 티어 재계산([`REGISTRY.md`](REGISTRY.md) 6절) |

### 분류·시딩
| 파일 | 역할 |
|---|---|
| `map_registry_cameo_groups.py` | registry 미매핑 CAS를 PubChem `hid=86`으로 조회해 CAMEO 그룹 적재(`--write`). 분자식 대조로 CID 오식별 차단([`REGISTRY.md`](REGISTRY.md) 7절) |
| `pubchem_verify_groups.py` | PubChem 경로로 CAS→CAMEO 그룹 재검증([`DATA.md`](DATA.md)) |
| `build_chemical_group_membership.py` | CAS→CAMEO 그룹 매핑 테이블 시드. 입력 CSV는 `archive/01_collection/`에 있다 |
| `seed_reactivity_reference.py` / `seed_self_reactivity.py` | 68×68 매트릭스 / 자기반응성 테이블 시드 |
| `seed_service_corpus.py` | `substance_status` VIEW 생성 + `corpus_tag='service'` 시딩. **서비스 범위의 정의 지점** |
| `seed_core_corpus.py` | 청크·CAMEO 그룹이 둘 다 있는 Registry 물질을 `corpus_tag='core'`로 편입([`REGISTRY.md`](REGISTRY.md) §8) |

### Retrieval
| 파일 | 역할 |
|---|---|
| `evalset_pairs.py` | 물질쌍 평가셋 생성(`gold_evidence` 포함). gold_evidence 규칙이 여기 코드로 고정돼 있다 |
| `run_ab.py` | Retrieval A/B 평가 드라이버(Recall/MRR/nDCG/Hit, [`RETRIEVAL.md`](RETRIEVAL.md)). `--granularity section` · `--decompose`(질의 분해) |
| `build_service_embedding_cache.py` | service 태그 문서 임베딩 캐시를 기존 캐시에서 조립(전량 재인코딩 100분 회피) |
| `freeze_retrieval.py` | Retrieval 결과를 top-10으로 고정 → `results/frozen_retrieval_top10.jsonl` |

### Generation·평가
| 파일 | 역할 |
|---|---|
| `run_cameo_context_pilot.py` | **프롬프트 정의 파일.** `SYSTEM_PROMPT`(자유텍스트 v7) · `SCHEMA_PROMPT`(structured v8b) · `PAIR_SCHEMA` · `render_answer()` · `render_conclusion()`. 앱도 여기서 프롬프트를 가져간다 |
| `run_cameo_full.py` | **최종 채택 파이프라인** — 전수 생성+채점, 동시실행. `--context frozen/pair` · `--format text/schema` · `--tag`. 실패분만 재시도되는 재개 로직 포함 |
| `generate_baseline.py` | baseline 프롬프트 생성(LLM 직접판정 1차 버전). 앱이 컨텍스트 조립 함수를 재사용한다 |
| `reparse_verdict_line.py` | 판정줄 재파싱 — **확정 지표는 이 출력 기준**([`GENERATION.md`](GENERATION.md)) |
| `summarize_cameo_full.py` | 전수 결과 요약. **지표 정의의 단일 출처는 이 파일 docstring** |
| `score_answer_metrics.py` | 본문 기준 지표를 기존 결과에 사후 계산(LLM 호출 없음). `substance_confused` 0%가 측정 결과가 아니라 구조가 강제한 값임을 드러내려고 만든 것 |
| `analyze_generation.py` | Retrieval×Generation 분리분석(4-bucket, [`GENERATION.md`](GENERATION.md)) |
| `build_pair_report.py` | 전수 산출물을 단일 HTML 보고서로 렌더링. 읽기 전용, 재생성 없음 |
| `generate_final_report.py` | N종 조합의 §1~§5 최종 보고서 PDF CLI. 앱의 인앱 리포트와 별개 경로 |

## tests/ — 자가검증 4종

전부 `python tests/<파일>.py`로 단독 실행한다. 프레임워크·픽스처 없음.

| 파일 | 지키는 것 |
|---|---|
| `test_pipeline.py` | `src/pipeline.py` 청킹·Normalize |
| `test_kosha_msds_collector.py` | 수집기 XML 파서(API 키·쿼터 불필요) |
| `test_evalset_evidence.py` | `evalset_pairs.py`의 gold_evidence 규칙 — 8/17 아카이브 8,700슬롯 재현 |
| `test_run_cameo_resume.py` | 재개 로직 + **`verdict`가 스키마에 없다는 불변식**. v8 판정뒤집기 회귀를 막는 가드다(`archive/2026-08-29_generation_prompt_history/_v8_verdict_regression/FINDING.md`) |

## data/ — 입력·중간 산출물

| 항목 | 내용 |
|---|---|
| `reactivity_reference.db` | SQLite 진실원본(전 테이블). 앱이 읽는 유일한 데이터 파일 |
| `schema.sql` | DB 스키마 원본 |
| `collection/core_*.csv` (5종) | **Registry 237종의 기준 목록** — CORE 5축별 물질과 편입 근거 |
| `collection/registry_additions_2026-08-22.csv` | 207→237 확장분 30종의 편입 근거([`REGISTRY.md`](REGISTRY.md) §7) |
| `collection/registry_core207.csv` | 확장 이전 CORE 207종 — `service_contract_audit.py`가 물질별 origin을 가르는 데 쓴다 |
| `collection/core_gap_kosha_target.csv` | 확장 후보의 KOSHA 등재 확인용 조회 입력 |
| `collection/core_chunk_target_2026-08-22.csv` | 청킹 대상 39종(B1 티어) — `pipeline.py --target-csv` 입력 |
| `collection/kosha_unlisted_39.csv` | KOSHA MSDS 미등재 39종 — 앱 선택 목록에서 제외되는 물질 |
| `collection/undergrad_target_chemicals.csv` | `kosha_msds_collector.py`의 기본 수집 대상 목록 |
| `collection/pubchem_verification_report{,_full}.csv` | `pubchem_verify_groups.py` 입출력 |
| `collection/_frozen_substances_baseline.json` | `build_substance_registry.py` 자가검증 기준선 |
| `collection/CRW_Data_Export_reactivity map.xlsx` | CAMEO 반응성 매트릭스 원본 export |
| `evalset/gold_pair.jsonl` | 물질쌍 평가셋(gold_evidence 포함) |
| `chunks/` `index/` | **git 미추적**(`.gitignore`) — 재실행하면 재생성된다. 청크 md / FAISS·BM25 캐시 |
| `boilerplate_sec10_values.json` | §10 정형문구 15종 실측 기록(코드는 더 이상 참조 안 함) |

## results/ — 현행 산출물만

> 세대가 갈린 Generation 산출물(v6·v8·v9)은
> [`archive/2026-08-29_generation_prompt_history/`](../archive/2026-08-29_generation_prompt_history/NOTES.md)에 있다.

### Generation — 현행 2세대
| 파일 | prompt_version | 생성 명령 |
|---|---|---|
| `generation_cameo_full_pair_v7.jsonl` / `eval_cameo_full_pair_v7.jsonl` | `cameo_service_v7`(자유텍스트) | `run_cameo_full.py --context pair --format text --tag v7` |
| `generation_cameo_full_pair_v8b.jsonl` / `eval_cameo_full_pair_v8b.jsonl` | `cameo_service_v8b_schema`(structured output) | `run_cameo_full.py --context pair --format schema --tag v8b` |

**문서의 확정 지표는 v7·v8b가 아니라 v6 기준이다.** v6 산출물은 archive에 있고,
`summarize_cameo_full.py`를 인자 없이 실행하면 그 파일을 읽어 문서와 같은 수치를 낸다.

주의: `run_cameo_full.py`의 출력 슬롯은 `--tag` 미지정 시
`results/generation_cameo_full.jsonl` / `eval_cameo_full.jsonl`로 고정이다. 태그 없이
재실행하면 그 이름의 파일이 `results/`에 **새로** 생긴다 — archive의 v6 산출물과 다른 파일이다.

### Retrieval 지표
| 파일 | 내용 |
|---|---|
| `frozen_retrieval_top10.jsonl` | 고정 Retrieval 결과(쌍 질의) — Generation 입력 |
| `frozen_retrieval_top10_decomposed.jsonl` | 질의 분해판. **아직 Generation에 반영되지 않았다** |
| `02_embedding_pair_sec210_service.{csv,md}` | service 173종 쌍질의 baseline |
| `02_embedding_pair_sec210_service_decomposed.{csv,md}` | 질의 분해 결과([`RETRIEVAL.md`](RETRIEVAL.md) 확정 지표) |

### Registry·KOSHA 감사
| 파일 | 내용 |
|---|---|
| `registry237_service_contract_2026-08-22.csv` → `_after_reindex_` → `_after_cameo_` → `_after_chunking_` | 서비스 계약 대조표 4판(인덱스 편입 전/후, CAMEO 매핑 확충 후, 청킹 후). 생성은 `service_contract_audit.py` |
| `registry_service_contract_recheck.csv` | 위 스크립트의 재점검 출력 |
| `registry_cameo_mapping_2026-08-22.csv` | 미매핑 95종의 PubChem `hid=86` 조회 결과 전량(status·CID·분자식 대조·제외 사유) |
| `registry_expansion_proposal_2026-08-22.csv` / `corpus96_core_reassessment_2026-08-22.csv` | 신규 후보 26종 판정표 + 코퍼스 전용 96종 재평가 |
| `kosha_registry_lookup.csv` | registry 전체의 KOSHA 등재 상태 스냅샷 |
| `kosha_missing39_probe_2026-08-22.csv` | 미등재 39종을 CAS/국문명/영문명 3경로로 실조회한 근거(전부 0건) |

## docs/ — 표준 문서 9종

`README.md`(루트) + `PIPELINE.md`/`DATA.md`/`REGISTRY.md`/`RETRIEVAL.md`/`GENERATION.md`/
`FILE_GUIDE.md`(이 문서) + `HANDOFF.md`/`PROJECT_LOG.md`. 각 문서가 답하는 질문은 루트
`README.md`의 표 참고. **어떤 물질을 다루는가**는 [`REGISTRY.md`](REGISTRY.md)가 단일 출처다.

## archive/ — 폐기·대체

| 폴더 | 내용 |
|---|---|
| `01_collection/` | 수집 단계 실행 로그·폐기 CSV(일부는 DB 재빌드 시드로 여전히 참조됨) |
| `02_pubchem_rejected/` | 기각된 PubChem SDF 매핑 경로 |
| `04_rag_agent/` | Retrieval 단계 — 섹션필터 전 폐기 A/B 결과 |
| `generation_experiments/` | 기각된 prompt v2/v2.1, Cascade Judge, RAGAS |
| `chemical_selection_2026-08-08/` | 화학물질 선정 재설계 이전 시행착오 |
| **`2026-08-08_selection_scripts/`** | **(2026-08-30 신규)** 물질선정 시절 1회성 스크립트 14종 + 전용 입력 CSV 3종. archive 위치에서는 실행되지 않는다 |
| `2026-08-17_baseline/` | `corpus_tag='173'` 코퍼스 확정 지표와 산출물 |
| **`2026-08-29_generation_prompt_history/`** | **(2026-08-30 신규)** Generation 세대별 산출물 — `v6/`(문서 확정 지표) · `_v8_verdict_regression/` · `_v9_regression/` |
| `superseded_docs/` | 표준 문서에 흡수된 원본 상세 문서(decisions.md 등) |
| `design_docs/` | 설계 철학 자체가 교체되며 폐기된 문서 |
| `adhoc_check_scripts/` | 특정 이슈 조사용 1회성 스크립트 |

각 폴더의 `NOTES.md`(또는 `README.md`)에 무엇을 왜 옮겼는지 상세 기록.

## 루트 설정 파일 — 지우면 안 되는 것

| 파일 | 왜 필요한가 |
|---|---|
| `.gitignore` | `.env`(자격증명) · `data/index/`·`data/chunks/`(재생성 가능한 캐시) · 중복본 `SMART_MSDS/` · `.claude/`를 막는다 |
| `.env.example` | 필요한 환경변수 이름을 값 없이 문서화 |
| `.streamlit/config.toml` | 앱 테마. 배포 시 필요 |

`.claude/`는 2026-08-30에 git 추적에서 뺐다(로컬 파일은 그대로 있다).
