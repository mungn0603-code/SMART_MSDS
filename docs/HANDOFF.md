# MSDS 위험성평가 자동화 — 핸드오프

**최종 갱신**: 2026-08-06 (Stage 4 세션)
**현재 단계**: Stage 4 (RAG) — Retrieval 계층 완료, RAG 지표·Abstain 미착수

---

## 0. 이번 세션(2026-08-06 Stage 4) 결과 요약

Stage 4 §13 실행순서 1~4단계 중 **Retrieval 계층까지 완주**. 진행 중 설계 변경이 7건
발생했고, 전부 근거와 함께 **`docs/stage4_design_changes_2026-08-06.md`** 에 아카이빙했다.
설계 원칙 문서(`stage4_design_principles_v2.md`)와 실제 구현이 다른 부분은 그 문서가 기준이다.

### 확정 구성

| 항목 | 확정값 | 근거 유형 |
|---|---|---|
| 임베딩 | `dragonkue/BGE-m3-ko` | **사용자 지정** (A/B 승자 아님) |
| 리랭커 | `BAAI/bge-reranker-base` | **사용자 지정**, 이번 세션 미실행 |
| 청킹 | section 단위 단독 (item 폐기) | 실측 + 구조적 논증 |
| 검색공간 | §2·§10 필터 (805 → 409청크) | **실측** — 정확도·속도 동시 개선 |
| 검색 | **hybrid** (dense+BM25 RRF, FAISS IndexFlatIP) | **실측** — 아래 재검토 이력 참고 |
| 평가 과제 | 물질 **쌍** 369건 | 설계 오류 정정 |
| LLM | NVIDIA NIM `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` | 사용자 지정 |

### 최종 실측 (bge-m3-ko / section / §2·§10 필터 / hybrid / 쌍 369건)

| 구간 | 지표 | 확정 목표 | 실측 | 판정 |
|---|---|---:|---:|:--:|
| 정확도 | **Recall@10** (핵심 KPI) | ≥ 0.89 | **0.9005** | 충족 |
| | MRR | ≥ 0.98 | 0.9986 | 충족 |
| | nDCG@10 | ≥ 0.88 | 0.8932 | 충족 |
| | Hit@5 | 1.00 유지 | 1.0000 | 충족 |
| 지연 | Embedding(질의) | ≤ 500ms | 501.724ms | 미달 |
| | Retrieval(검색) | ≤ 10ms | 6.281ms | 충족 |
| | Total (TTFT 전) | ≤ 600ms | 508.00ms | 충족 |

**7개 목표 중 6개 충족** (dense 채택 시 4/7이었던 것 대비 개선). 유일한 미달은
질의 임베딩 지연(501.724ms, 목표 500ms 대비 1.724ms 초과) — 검색 방식과 무관한
질의 인코더 자체의 문제(§4-4 참고).

참고: Recall@5 0.7811 / Recall@20 0.9409 (Recall@5는 참고치로 강등 — 쌍당 정답이 평균
4.1개라 5칸에 4개를 담아야 하는 구조)

> **검색 방식 재검토 이력 (2026-08-06, 같은 세션 내 정정)**
> 최초 결정은 dense 단독(레이턴시 사유). §2·§10 필터 적용 **후** 재실측하니
> hybrid가 7개 목표 중 6개 충족(dense는 4개), 레이턴시 차이 6.19ms는 사용자가 정한
> `Retrieval ≤ 10ms` 예산 안에 들어옴을 확인 → **dense 단독 결정을 철회하고 hybrid로
> 재채택**. `04_rag_agent/run_ab.py`의 `evaluate_reranker()`에 남아있던 dense 우회
> 코드(`h = d`)도 되돌려 실제 hybrid 후보가 리랭커 입력으로 들어가도록 수정.
> 상세 근거·이력은 `docs/decisions.md` §2.4, `docs/stage4_design_changes_2026-08-06.md` §5·§5-1.
> **리랭커 단계는 아직 미실행** — hybrid 후보 기준으로 리랭커까지 재검증하는 것은
> 다음 세션 과제.

---

## 1. 프로젝트 개요 (변경 없음)

- 목적: KOSHA MSDS Open API 데이터 기반, **화학물질 2종 이상 조합의 반응성·양립성**을
  RAG+Agent로 자동 평가하는 **포트폴리오 MVP**
- 작업 경로: `C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS`
- 제품 형태: 사용자가 **물질 2종 이상을 입력** → 상호 반응성·혼합 시 위험성·유의사항 제공.
  (단일물질 사실조회가 아니다 — 이번 세션에서 평가셋을 이 기준으로 전면 교체했다)
- **N종 조합 판정 구현됨** (`03_compatibility/compatibility_engine.py`
  `judge_combination_by_cas`): 모든 쌍 C(N,2)을 기존 쌍 판정으로 계산 후 worst-case
  종합 + 전체 쌍 매트릭스(`to_table()`) + 쌍별 상세 리포트(`pair_reports()`) 제공.
  상세 설계는 `decisions.md` §2.10.

## 2. 타협 불가 원칙 (변경 없음)

1. 양립성 매트릭스 조회 결과를 단독 최종 판정 근거로 사용 금지
2. CAMEO 최신 68그룹 체계 엄격 적용(구 EPA 41그룹 폐기)
3. 근거 부족 시 Abstain — 억지로 답변하지 않음
4. 근거 등급제: 법령(Mandatory) > 권고(Recommended) > 참고자료(Reference)
5. 서비스키·API키 원문은 코드/로그/응답 어디에도 노출 금지 — `.env` + 환경변수로만

**근거등급 판정 규칙 (2026-08-06 확정, 출처표기 기반 3분할)**
- 섹션2 (GHS분류·H/P코드 = 고용노동부고시 별표 확정문구) → **Mandatory**
- 섹션3·9·10 중 `※출처` 미표기 (KOSHA 작성값) → **Recommended**
- `※출처` 표기 항목 (HSDB·ECHA·ICSC 등 외부DB 인용) → **Reference**

## 3. 완료된 작업

### Stage 1~3 (이전 세션)
1. `reactivity_reference.db`: CAMEO 68그룹, 2,278쌍(오프대각), self_reactivity 68행
2. CAS↔CAMEO 매핑: `chemicals`(3,398종), `chemical_group_membership`(6,669행, 68/68그룹)
3. 200종 타겟 리스트: `01_collection/undergrad_target_chemicals.csv`
4. KOSHA 수집 완료: **198종 확보**(`msds_sections` 7,920행 = 198종 × 40항목, 결측 EAV 없음),
   2종 Abstain 유지(135072-82-1, 15005-97-7 — Diazonium Salts 그룹, 대체 후보 소진)

### Stage 4 (이번 세션)
5. **청킹 파이프라인** `04_rag_agent/pipeline.py` — 본문추출 → Normalize → Chunk → Metadata
   - section 청크 **805개** (길이 p50 390 / max 1,792자, 13개 섹션이 2분할)
   - item 청크 **7,420개** (폐기했으나 DB 보존)
   - Normalize: NFKC 단위 정규화(`℃`→`°C`, `㎩`→`Pa`), `|` 다중값→불릿,
     `※출처` 메타데이터 승격, `GHS06.gif`→`GHS06(급성독성)`, 무자료 10종 변종 통일
   - 근거등급 분포(item): Mandatory 1,782 / Recommended 4,226 / Reference 1,412
   - 자체검증 `test_pipeline.py` 통과
6. **§6 메타데이터 테이블** `rag_chunks` — SQLite 진실원본 + vector payload 필드 전부
7. **평가셋**
   - `evalset_pairs.py` → `gold_pair.jsonl` **369쌍** (Incompatible 135 / Caution 114 /
     Compatible 120, 전체 19,503쌍에서 카테고리 균형표집), `gold_pair_abstain.jsonl` **81쌍**
   - `evalset.py` → `gold_retrieval.jsonl` 407건 (단일물질 사실조회, `--task fact` 부품점검용)
8. **검색계층** `retrieval.py` — bge-m3-ko 임베딩 + FAISS IndexFlatIP + BM25(kiwipiepy)
   + RRF(k=60) + CrossEncoder 리랭커. 인덱스·벡터는 `04_rag_agent/index/` 캐시
9. **평가 드라이버** `run_ab.py` — Recall@5/10/20, Hit@5/10, MRR, nDCG@10,
   구간별 레이턴시(질의임베딩 / 검색 / 합계). 다중정답 채점 자체검증 통과
10. **LLM 클라이언트** `llm.py` — NVIDIA NIM Nemotron Nano (키 미설정 상태, 아래 4-1)
11. **설계변경 아카이브** `docs/stage4_design_changes_2026-08-06.md` (12절, 380줄)

---

## 4. 다음 세션이 할 일 (우선순위 순)

### 4-1. LLM 연결 — **선행 조건**
`.env` 에 아래 한 줄 추가가 필요하다. **사용자만 할 수 있다.**
```
NVIDIA_API_KEY=<발급받은 키>
```
그다음 점검:
```bash
python 04_rag_agent/llm.py --check
```
- 모델: `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning`
- 엔드포인트: `https://integrate.api.nvidia.com/v1/chat/completions` (OpenAI 호환)
- `.env` 는 이미 `.gitignore` 등록됨. 키 원문은 출력·로그·커밋 어디에도 남기지 말 것
  (`llm.py` 의 `key_fingerprint()` 가 길이+해시만 보여준다)

### 4-2. RAG 지표 측정 (§10, §13 5단계)
Faithfulness / Context Recall / Context Precision / Answer Relevancy.
`ragas` **미설치**. 설치 시 NVIDIA NIM은 OpenAI 호환이므로 base_url 지정으로 연결 가능.
Context Precision 목표치는 설계 §11이 "baseline 실측 후 설정"으로 비워둔 상태 — 실측값을
먼저 보고하고 확정은 사용자 승인 후.

### 4-3. Abstain Precision 측정 (§13 6단계)
평가셋 `gold_pair_abstain.jsonl` **81쌍** 생성 완료.
정의: 양쪽 물질 모두 §10 "피해야 할 물질"이 자료없음 → 물질 특정 근거 없이 그룹 근거만
남음 → **원칙 1(매트릭스 단독판정 금지)에 의해 Abstain 대상**.
목표: False Answer 0건, Abstain Precision ≥ 95%.

### 4-4. 질의 인코더 최적화
`Embedding ≤ 500ms` 목표에 501.724ms로 **1.724ms 초과**. 전체 Retrieval 지연의 99.98%가
이 구간이다(검색은 0.089ms). 검색 방식과 무관한 문제.
후보: ONNX Runtime, 동적 양자화(int8), 질의 전용 경량 인코더.

### 4-5. 조치 대기 (사용자 판단 필요)
- **청석면(ASBESTOS [BLUE], 12001-28-4)이 200종 리스트에 잔존**.
  백업 5개 전수추적 결과 **원본 `pool_supplement` 항목**이며 대체 후보가 아니다.
  기존 안전필터는 **대체 후보 32종에만** 적용됐고 원본 200종은 재검증된 적이 없다.
  Stage 4 동작에는 영향 없음. 변경 아카이브 §10.
- **설계문서 §5 사실오류**: `bge-reranker-v2-m3`를 "경량/빠름", `bge-reranker-base`를
  "대형/고성능"이라 적었으나 반대. 실제 v2-m3=2.2GB(568M), base=1.2GB(278M). 수정 대기.
- **평가셋 검수 미완**: 샘플 20건 사용자 검수를 못 받은 채 현 템플릿으로 실측 진행됨.
  템플릿 수정 시 질의 벡터만 재생성하면 되므로 반영은 수 분.
- **Hybrid 재검토 여부**: 위 0절 주의 참조.

---

## 5. 환경 / 실행 방법

### 필수 환경변수
```bash
export SSL_CERT_FILE="$HOME/.cache/win_ca_bundle.pem"   # 아래 SSL 항목 참조
export MSDS_TORCH_THREADS=8                              # 미설정 시 실효 2코어만 사용
export HF_HUB_OFFLINE=1                                  # 캐시된 모델만 쓸 때
```

### 실행 순서
```bash
python 04_rag_agent/test_pipeline.py                     # 자체검증
python 04_rag_agent/pipeline.py                          # 청크 + rag_chunks + 마크다운
python 04_rag_agent/evalset_pairs.py                     # 쌍 평가셋
python 04_rag_agent/run_ab.py embedding --models bge-m3-ko \
    --granularity section --task pair --sections 2,10    # 확정 구성 재현
```

### 알려진 환경 함정 (재발 방지)
| 문제 | 해결 |
|---|---|
| HF 모델 다운로드 SSL 실패 | `huggingface_hub`의 httpx가 certifi만 참조해 로컬 루트 CA 미발견. Windows 인증서 저장소(ROOT/CA) 105개를 certifi와 합친 번들 생성 → `SSL_CERT_FILE` 지정. **검증 비활성화 금지**. `llm.py`는 이 번들이 있으면 자동 사용 |
| torch가 8코어 중 2코어만 사용 | `MSDS_TORCH_THREADS=8` (1.45배 단축) |
| 임베딩 배치를 키우면 더 느림 | 배치 32가 배치 8보다 2배 느림(메모리 대역폭). **배치 8 유지** |

### CPU 처리량 실측 (참고 — 8스레드)
| 대상 | 속도 | 환산 |
|---|---|---|
| section 청크(평균 487자) | 2.61초/청크 | 805청크 = 35분 |
| item 청크(평균 88자) | 0.637초/청크 | 7,420청크 = 79분 |
| 리랭커 base | 1.09초/쌍 | 369질의×20후보 = 최대 134분 |
| 질의 1건 임베딩 | 501.7ms | — |

---

## 6. 파일 위치

```
MSDS\
├── .env                  (KOSHA_SERVICE_KEY, NVIDIA_API_KEY — gitignore, 원문 노출 금지)
├── .env.example          (키 이름만)
├── reactivity_reference.db   (+ rag_chunks 테이블 추가됨)
├── 01_collection\        (수집 완료)
├── 02_classification\ · 03_compatibility\
├── 04_rag_agent\
│   ├── pipeline.py           본문추출→Normalize→Chunk→Metadata
│   ├── test_pipeline.py      자체검증
│   ├── evalset_pairs.py      쌍 평가셋 (제품 과제)
│   ├── evalset.py            단일물질 평가셋 (부품 점검용)
│   ├── retrieval.py          임베딩/FAISS/BM25/RRF/리랭커
│   ├── run_ab.py             평가 드라이버
│   ├── llm.py                NVIDIA NIM Nemotron Nano
│   ├── chunks\               section 805 + item 7,420 마크다운
│   ├── evalset\              gold_pair 369 / gold_pair_abstain 81 / gold_retrieval 407
│   ├── index\                벡터·BM25 캐시
│   └── results\              실측 CSV/md
├── 05_evaluation\        (미착수)
└── docs\
    ├── HANDOFF.md                            ← 이 문서
    ├── stage4_design_principles_v2.md        설계 확정본
    ├── stage4_design_changes_2026-08-06.md   ★ 설계 변경 아카이브 (구현과 다른 부분의 기준)
    ├── HANDOFF_ARCHIVE.md                    과거 이력
    └── msds_risk_assessment_readme.md
```

## 7. 컨텍스트 복원 방법

다음 세션 시작 시 **이 문서 → `stage4_design_changes_2026-08-06.md` → 설계원칙 v2** 순으로 읽을 것.
설계원칙 v2와 실제 구현이 어긋나는 부분은 변경 아카이브가 기준이다.
DB 구조는 문서 설명만 믿지 말고 `rag_chunks`, `msds_sections` 실제 데이터를 직접 조회해
확인한 뒤 작업할 것.
