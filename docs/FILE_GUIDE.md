# FILE_GUIDE — 각 파일은 정확히 무엇을 하는가?

디렉터리 역할: `src/`는 다른 파일이 import하는 재사용 모듈, `scripts/`는 직접 실행하는
엔트리포인트(**파이프라인 단계별 폴더**), `tests/`는 자가검증, `app/`은 Streamlit UI,
`data/`는 입력, `results/`는 **최종 결과만**, `archive/`는 대체·폐기된 것(폴더마다 `NOTES.md`).

> **최종 갱신 2026-08-30 — 저장소 재구성.** `scripts/`를 파이프라인 6단계 폴더로 나누고,
> 중간 실험 산출물과 더 이상 쓰이지 않는 입력 데이터를 `archive/`로 옮겼다. 삭제한 파일은 없다.

```
MSDS/
├─ app/           Streamlit UI (진입점)
├─ src/           재사용 모듈 7종
├─ scripts/       실행 스크립트 24종 — 1_collect ~ 6_eval 파이프라인 순서
├─ tests/         자가검증 4종
├─ data/          DB · 선정 기준 CSV · 평가셋 (+ 미추적 캐시 chunks/ index/)
├─ results/       최종 결과 12개
├─ docs/          표준 문서 9종
└─ archive/       대체·폐기된 것 (폴더마다 NOTES.md)
```

## app/ — 서비스

| 파일 | 역할 |
|---|---|
| `streamlit_app.py` | 조회·판정 UI. `python app/streamlit_app.py --check`로 LLM 없이 자가검증. **근거 수집은 `pair_context()`(CAS 직접조회 §2+§10)** — 검색을 타지 않는다. 읽는 데이터 파일은 `data/reactivity_reference.db` 하나다 |

앱이 import하는 모듈: `src/` 6종(`pipeline.py` 제외) +
`scripts/5_generation/`의 `generate_baseline.py`·`run_cameo_context_pilot.py`.
**이 둘은 실행 스크립트인 동시에 앱의 런타임 의존이다** — 옮기거나 이름을 바꾸면 앱이 죽는다.

## src/ — 핵심 모듈 7종

| 파일 | 역할 |
|---|---|
| `llm.py` | Upstage Solar 클라이언트(`solar-pro3`). `chat()`이 전 파이프라인의 유일한 LLM 호출 경로 — 429/503 재시도(backoff+jitter) 포함 |
| `retrieval.py` | FAISS(dense) + BM25 하이브리드 검색, RRF 융합, §10 boilerplate penalty. **현재 서비스 경로 아님** — 자유 질의용으로 보존 |
| `pipeline.py` | MSDS 원문 → Normalize → Chunk(section 단위) → `rag_chunks` 적재 |
| `eval_generation.py` | Judge 채점(rule_based + LLM judge), `substance_confused`/`cas_in_text`(물질 혼동 진단) |
| `cameo_group_lookup.py` | CAS 쌍 → CAMEO 그룹 → 판정+사유 조회(Generation 프롬프트에 주입하는 "정답" 소스) |
| `compatibility_engine.py` | N종(3종 이상) 물질 조합 판정 — 전체 쌍을 계산해 worst-case 종합 |
| `kr_glossary.py` | CAMEO 68그룹·위험코드 11종·발생가스 48종의 영문→한글 고정 사전. 정적 dict 3개, 번역 API 없음 |

## scripts/ — 파이프라인 단계별 24종

폴더 번호가 곧 실행 순서다. **처음 보는 사람은 `1_collect`부터 순서대로 읽으면 된다.**

### `1_collect/` — KOSHA MSDS 수집
| 파일 | 역할 |
|---|---|
| `kosha_msds_collector.py` | KOSHA MSDS Open API 수집(§2/3/9/10). `--target-csv`로 대상 지정. `chem_id IS NULL`(미등재 확정) 캐시도 적중 처리해 재조회하지 않는다 |
| `kosha_registry_lookup.py` | registry ↔ KOSHA 등재 상태 점검 리포트(`--fetch`로 미조회분 실조회) |

### `2_registry/` — 물질 선정·CAMEO 매핑·서비스 계약
| 파일 | 역할 |
|---|---|
| `build_substance_registry.py` | `core_*.csv` 5종 → `substance_registry` 재생성(drop 후 전량 적재) + 자가검증([`REGISTRY.md`](REGISTRY.md)) |
| `map_registry_cameo_groups.py` | 미매핑 CAS를 PubChem `hid=86`으로 조회해 CAMEO 그룹 적재(`--write`). 분자식 대조로 CID 오식별 차단([`REGISTRY.md`](REGISTRY.md) 7절) |
| `pubchem_verify_groups.py` | PubChem 경로로 CAS→CAMEO 그룹 재검증([`DATA.md`](DATA.md)). ⚠ argparse 없음 |
| `build_chemical_group_membership.py` | CAS→CAMEO 그룹 매핑 테이블 시드. 입력 CSV는 `archive/01_collection/`. ⚠ `__main__` 가드 없음 — 실행하면 즉시 DB에 쓴다 |
| `service_contract_audit.py` | 서비스 계약 5조건 재대조 + A/B1/C/X 티어 재계산([`REGISTRY.md`](REGISTRY.md) 6절) |

### `3_corpus/` — DB 시드·코퍼스 정의·인덱스
| 파일 | 역할 |
|---|---|
| `seed_reactivity_reference.py` | `schema.sql`로 DB를 만들고 68×68 매트릭스를 적재. ⚠ argparse 없음 — **실행하면 DB를 재생성한다** |
| `seed_self_reactivity.py` | 자기반응성 68행 UPDATE. ⚠ argparse 없음 |
| `seed_service_corpus.py` | `substance_status` VIEW 생성 + `corpus_tag='service'` 시딩. **서비스 범위의 정의 지점** |
| `seed_core_corpus.py` | 청크·CAMEO 그룹이 둘 다 있는 Registry 물질을 `corpus_tag='core'`로 편입([`REGISTRY.md`](REGISTRY.md) §8) |
| `build_service_embedding_cache.py` | service 태그 문서 임베딩 캐시를 기존 캐시에서 조립(전량 재인코딩 100분 회피) |

### `4_retrieval/` — 평가셋·검색 평가·입력 고정
| 파일 | 역할 |
|---|---|
| `evalset_pairs.py` | 물질쌍 평가셋 생성(`gold_evidence` 포함). gold_evidence 규칙이 여기 코드로 고정돼 있다 |
| `run_ab.py` | Retrieval 평가 드라이버(Recall/MRR/nDCG/Hit, [`RETRIEVAL.md`](RETRIEVAL.md)). `--granularity section` · `--decompose`(질의 분해) |
| `freeze_retrieval.py` | Retrieval 결과를 top-10으로 고정 → `results/frozen_retrieval_top10.jsonl` |

### `5_generation/` — 프롬프트·전수 생성
| 파일 | 역할 |
|---|---|
| `run_cameo_context_pilot.py` | **프롬프트 정의 파일.** `SYSTEM_PROMPT`(자유텍스트 v7) · `SCHEMA_PROMPT`(structured v8b) · `PAIR_SCHEMA` · `render_answer()` · `render_conclusion()`. 앱도 여기서 프롬프트를 가져간다. ⚠ argparse 없음 |
| `run_cameo_full.py` | **최종 채택 파이프라인** — 전수 생성+채점, 동시실행. `--context frozen/pair` · `--format text/schema` · `--tag`. 실패분만 재시도되는 재개 로직 포함 |
| `generate_baseline.py` | baseline 프롬프트 생성(LLM 직접판정 1차 버전). 앱이 컨텍스트 조립 함수를 재사용한다 |

### `6_eval/` — 채점·요약·리포트
| 파일 | 역할 |
|---|---|
| `reparse_verdict_line.py` | 판정줄 재파싱 — **확정 지표는 이 출력 기준**([`GENERATION.md`](GENERATION.md)) |
| `summarize_cameo_full.py` | 전수 결과 요약. **지표 정의의 단일 출처는 이 파일 docstring** |
| `score_answer_metrics.py` | 본문 기준 지표를 기존 결과에 사후 계산(LLM 호출 없음). `substance_confused` 0%가 측정 결과가 아니라 구조가 강제한 값임을 드러내려고 만든 것. ⚠ argparse 없음 |
| `analyze_generation.py` | Retrieval×Generation 분리분석(4-bucket, [`GENERATION.md`](GENERATION.md)). ⚠ argparse 없음 |
| `build_pair_report.py` | 전수 산출물을 단일 HTML 보고서로 렌더링. ⚠ `__main__` 가드 없음 |
| `generate_final_report.py` | N종 조합의 §1~§5 최종 보고서 PDF CLI. 앱의 인앱 리포트와 별개 경로 |

> ⚠ 표시된 6개는 **`--help`를 붙여도 본문이 그대로 실행된다**(argparse가 없거나 가드가 없다).
> `seed_reactivity_reference.py`는 실제로 이걸로 DB가 재생성된 적이 있다(2026-08-30, git에서 복구).
> 경로·import 확인은 실행이 아니라 `python -m compileall`과 `grep`으로 한다.

## tests/ — 자가검증 4종

전부 `python tests/<파일>.py`로 단독 실행한다. 프레임워크·픽스처 없음. **부작용 없음.**

| 파일 | 지키는 것 |
|---|---|
| `test_pipeline.py` | `src/pipeline.py` 청킹·Normalize |
| `test_kosha_msds_collector.py` | 수집기 XML 파서(API 키·쿼터 불필요) |
| `test_evalset_evidence.py` | `evalset_pairs.py`의 gold_evidence 규칙 — 8/17 아카이브 8,700슬롯 재현 |
| `test_run_cameo_resume.py` | 재개 로직 + **`verdict`가 스키마에 없다는 불변식**. v8 판정뒤집기 회귀를 막는 가드다 |

## data/ — 입력

지금 코드가 실제로 읽는 것만 남겼다. 대체된 입력은
[`archive/2026-08-30_superseded/data_inputs/`](../archive/2026-08-30_superseded/NOTES.md).

| 항목 | 내용 | 읽는 코드 |
|---|---|---|
| `reactivity_reference.db` | SQLite 진실원본(15테이블 + `substance_status` VIEW) | 앱·전 스크립트 |
| `schema.sql` | DB 스키마 원본 | `seed_reactivity_reference.py` |
| `collection/core_*.csv` (5종) | **Registry 237종의 기준 목록** — CORE 5축별 물질과 편입 근거 | `build_substance_registry.py` |
| `collection/_frozen_substances_baseline.json` | Registry 자가검증 기준선 | `build_substance_registry.py` |
| `collection/registry_core207.csv` | 확장 이전 CORE 207종 — 물질별 origin 판별 | `service_contract_audit.py`, 앱 |
| `collection/registry_additions_2026-08-22.csv` | 207→237 확장분 30종의 편입 근거 | [`REGISTRY.md`](REGISTRY.md) §7 |
| `collection/kosha_unlisted_39.csv` | KOSHA MSDS 미등재 39종 — 앱 선택 목록에서 제외 | 앱 |
| `collection/undergrad_target_chemicals.csv` | 수집 대상 기본 목록 | `kosha_msds_collector.py`, `pubchem_verify_groups.py` |
| `collection/pubchem_verification_report{,_full}.csv` | PubChem 재검증 입출력 | `pubchem_verify_groups.py` |
| `evalset/gold_pair.jsonl` | 물질쌍 평가셋(gold_evidence 포함) | `run_ab.py`, `freeze_retrieval.py` |
| `chunks/` `index/` | **git 미추적**(`.gitignore`) — 재실행하면 재생성된다. 청크 md / FAISS·BM25 캐시 | `pipeline.py`, `retrieval.py` |

## results/ — 최종 결과 12개

**중간 실험 결과는 전부 archive로 갔다.** 어떤 수치가 어느 파일에서 나오는지는
[`results/README.md`](../results/README.md)가 단일 출처다.

| 축 | 파일 | 내용 |
|---|---|---|
| Retrieval 확정 지표 | `02_embedding_pair_sec210_service_decomposed.{csv,md}` | 질의 분해 결과([`RETRIEVAL.md`](RETRIEVAL.md)) |
| Retrieval 입력 고정 | `frozen_retrieval_top10.jsonl` | Generation 입력(쌍 질의) |
| | `frozen_retrieval_top10_decomposed.jsonl` | 분해판. **아직 Generation에 반영되지 않았다** |
| Generation 현행 | `generation_cameo_full_pair_v8b.jsonl` / `eval_cameo_full_pair_v8b.jsonl` | `cameo_service_v8b_schema`(structured output) |
| Registry 최종 대조 | `registry237_service_contract_after_chunking_2026-08-22.csv` | 계약 대조표 최종판 |
| | `registry_service_contract_recheck.csv` | `service_contract_audit.py` 기본 출력 |
| Registry 근거 | `registry_cameo_mapping_2026-08-22.csv` | 미매핑 95종의 PubChem `hid=86` 조회 전량 |
| | `registry_expansion_proposal_2026-08-22.csv` | 신규 후보 26종 판정표 |
| KOSHA 상태 | `kosha_registry_lookup.csv` | registry 전체 등재 상태 스냅샷 |
| | `kosha_missing39_probe_2026-08-22.csv` | 미등재 39종 3경로 실조회 근거(전부 0건) |

**문서의 Generation 확정 지표는 v6 기준이고 그 산출물은 archive에 있다.**
`summarize_cameo_full.py`를 인자 없이 실행하면 거기를 읽어 문서와 같은 수치를 낸다.

주의: `run_cameo_full.py`의 출력 슬롯은 `--tag` 미지정 시
`results/generation_cameo_full.jsonl` / `eval_cameo_full.jsonl`로 고정이다. 태그 없이
재실행하면 그 이름의 파일이 `results/`에 **새로** 생긴다 — archive의 v6 산출물과 다른 파일이다.

## docs/ — 표준 문서 9종

`README.md`(루트) + `PIPELINE.md`/`DATA.md`/`REGISTRY.md`/`RETRIEVAL.md`/`GENERATION.md`/
`FILE_GUIDE.md`(이 문서) + `HANDOFF.md`/`PROJECT_LOG.md`. **어떤 물질을 다루는가**는
[`REGISTRY.md`](REGISTRY.md)가 단일 출처다.

## archive/ — 대체·폐기

| 폴더 | 내용 |
|---|---|
| `01_collection/` | 수집 단계 실행 로그·폐기 CSV(일부는 DB 재빌드 시드로 여전히 참조됨) |
| `02_pubchem_rejected/` | 기각된 PubChem SDF 매핑 경로 |
| `04_rag_agent/` | Retrieval 단계 — 섹션필터 전 폐기 A/B 결과 |
| `generation_experiments/` | 기각된 prompt v2/v2.1, Cascade Judge, RAGAS |
| `chemical_selection_2026-08-08/` | 화학물질 선정 재설계 이전 시행착오 |
| `2026-08-08_selection_scripts/` | 물질선정 시절 1회성 스크립트 14종 + 전용 입력 CSV 3종 |
| `2026-08-17_baseline/` | `corpus_tag='173'` 코퍼스 확정 지표와 산출물 |
| `2026-08-29_generation_prompt_history/` | Generation 세대별 산출물 — `v6/`(문서 확정 지표) · `v7/` · `_v8_verdict_regression/` · `_v9_regression/` |
| `2026-08-30_superseded/` | 중간 Retrieval baseline · Registry 대조 1~3판 · 코드가 더는 읽지 않는 입력 데이터 |
| `superseded_docs/` | 표준 문서에 흡수된 원본 상세 문서(decisions.md 등) |
| `design_docs/` | 설계 철학 자체가 교체되며 폐기된 문서 |
| `adhoc_check_scripts/` | 특정 이슈 조사용 1회성 스크립트 |

각 폴더의 `NOTES.md`(또는 `README.md`)에 무엇을 왜 옮겼는지 기록.

## 루트 설정 파일 — 지우면 안 되는 것

| 파일 | 왜 필요한가 |
|---|---|
| `.gitignore` | `.env`(자격증명) · `data/index/`·`data/chunks/`(재생성 가능한 캐시) · 중복본 `SMART_MSDS/` · `.claude/`를 막는다 |
| `.env.example` | 필요한 환경변수 이름을 값 없이 문서화 |
| `.streamlit/config.toml` | 앱 테마. 배포 시 필요 |

`.claude/`는 2026-08-30에 git 추적에서 뺐다(로컬 파일은 그대로 있다).
