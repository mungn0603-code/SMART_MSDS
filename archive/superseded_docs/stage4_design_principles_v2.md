# Stage 4 (RAG 파이프라인) 설계 원칙 v2 — 최종 확정본

**작성일**: 2026-08-06
**상태**: 확정, 현재 유효 버전
**대체 대상**: `archive/stage4_design_v1_superseded_2026-08-06.md` ("기존 자산 재사용 우선" 철학 — 폐기)

---

## 0. 변경 이력
- v1 (2026-08-06 오전, 폐기): 최상위 판단기준 = "기존 자산(KDIC) 재사용 우선"
- v2 (본 문서, 2026-08-06): 최상위 판단기준 = "검색 성능 우선"으로 전면 교체

## 1. 최상위 철학 (교체됨)
우선순위: **검색 성능 > 유지보수성 > 확장성 > 기존 자산 재사용**
- 재사용은 "성능이 동률일 때만" 고려 대상이 된다.
- "기존에 사용했다"는 사실 자체는 채택 근거가 될 수 없다.
- 모든 핵심 기술(Embedding/Chunking/Hybrid Search/Reranker)은 A/B 테스트 실측으로 결정한다.

## 2. 비협상 원칙 (불변 — 이번 철학 교체와 무관)
- CAMEO 68그룹 체계 엄격 적용
- 양립성 매트릭스 조회 결과 단독 최종판정 금지
- 근거등급제: 법령(Mandatory) > 권고(Recommended) > 참고(Reference)
- Abstain 정책: 근거 불충분 시 억지 답변 금지

## 3. 파이프라인 (확정)

```
분류(Stage2 재사용)
→ 본문추출 (EAV lev/ordrIdx → 마크다운)
→ Normalize (공백/줄바꿈/특수문자/단위/CAS표기/한영혼용)
→ Section Chunk (EAV 경계 유지)
   └ 초과 시 → Recursive Split → (RAGAS로 경계문제 확인되면) Semantic Chunking 재검토
→ Metadata Attach
→ Embedding A/B (bge-m3 / bge-m3-ko / KURE — 3파전)
→ Vector Index(FAISS) + BM25
→ Hybrid Search
→ Reranker A/B (bge-reranker-v2-m3 / bge-reranker-base)
→ LLM
→ 평가 (Retrieval 지표 → RAG 지표 → Abstain 지표)
```

## 4. Embedding
- **방식**: bge-m3 vs bge-m3-ko vs KURE **3파전 A/B** (동시 진행)
- **순서**: bge-m3 단독 baseline 먼저 측정 → 3파전 비교의 기준선으로 사용
- **판단 근거**: 200종 규모라 임베딩(문서벡터 생성)은 1회성 비용이라 A/B 비용이 낮음. 반면 임베딩은 RAG 성능에 가장 큰 영향을 주는 요소 중 하나 — 지금 안 하면 나중에 재임베딩/재평가/재튜닝을 반복해야 함.
- **평가 지표**: Recall@5, Recall@10, MRR, nDCG, Context Recall, Answer Relevancy

## 5. Reranker
- **방식**: bge-reranker-v2-m3(대형/고성능, 568M/2.2GB) vs bge-reranker-base(경량/빠름, 278M/1.2GB) **A/B**
- **순서**: 임베딩 3파전 승자 확정 후 그 위에서 순차 진행(임베딩×reranker 6조합 전수비교는 200종 MVP 규모 대비 과잉으로 판단 — 필요 시 병렬 전수비교로 전환 가능)
- **판단 근거**: MSDS는 문서 수가 많지 않아 둘 다 테스트하는 비용이 낮음. 속도-성능 트레이드오프가 꽤 크다.
- **평가 지표**: Recall, Precision, nDCG, Latency, First Token Time

## 6. Metadata (Hybrid — SQLite + Vector Payload)

SQLite를 완전히 없애면 개정이력/물질관리/업데이트가 불편해지고, 모든 걸 SQLite에만 넣으면 검색이 복잡해진다. 역할을 분리한다.

| 계층 | 필드 | 용도 |
|---|---|---|
| SQLite (`reactivity_reference.db`, 관계형·진실원본) | chemical_id, cas, revision, source, version, status | 개정 이력 추적, 물질 관리, 업데이트 |
| Vector payload (검색용 캐시) | chunk, section, cameo, evidence, abstain, chemical, cas | 검색 시 즉시 필터링(그룹/근거등급/Abstain) |

CAS/chemical이 양쪽에 중복되는 것은 의도된 비정규화다.

## 7. Vector Store
- MVP: FAISS 유지
- 장기 확장 후보: Qdrant (판단 기준: 메타데이터 필터 성능, 운영 편의성, 확장성) — 현시점 재검토 트리거는 없음, 필요성이 드러나면 별도 논의

## 8. Chunking 세부
- 1차 경계: EAV 항목(Section 구조 유지)
- 2차(상한 초과 시만): Recursive Split
- 3차(조건부): RAGAS 평가에서 청크 경계 관련 실패가 확인될 때만 Semantic Chunking 재검토
- Adaptive Chunking(ekimetrics)은 MVP 제외 유지 — Stage6 이후 성능 미달 시 재검토 후보 (v1과 동일 결론, 변경 없음)

## 9. Normalize (신설 단계)
본문추출과 Chunk 사이에 정규화 단계 추가. 대상: 공백, 줄바꿈, 특수문자, 단위 표기, CAS 표기, Chemical Name, 영문/한글 혼용.

## 10. 평가 체계 (2계층 분리)

성능 저하 시 원인이 검색 단계인지 생성 단계인지 빠르게 구분하기 위해 분리한다. 임베딩/리랭커 A/B는 Retrieval 지표로, 최종 사용자 품질은 RAG 지표로 판단한다.

**Retrieval 평가**: Recall@5, Recall@10, MRR, nDCG@10
**RAG 평가**: Faithfulness, Context Recall, Context Precision, Answer Relevancy, Abstain Precision/Recall

## 11. 성능 목표 (MVP, 잠정치 — baseline 실측 후 재조정 가능)

| 계층 | 지표 | 목표 |
|---|---|---|
| Retrieval | Recall@5 | ≥ 0.90 |
| | Recall@10 | ≥ 0.95 |
| | MRR | ≥ 0.85 |
| | nDCG@10 | ≥ 0.90 |
| RAG | Faithfulness | ≥ 0.90 |
| | Context Recall | ≥ 0.90 |
| | Context Precision | (baseline 실측 후 설정 — 임의 수치 미기재) |
| | Answer Relevancy | ≥ 0.90 |
| Abstain | False Answer | 0건 |
| | Hallucination | 최소화 |
| | Abstain Precision | ≥ 95% |

> 주의: 200종 규모 MVP에서 baseline 없이 정한 목표치다. 특히 Recall@10 0.95, Faithfulness 0.90은 튜닝 전 첫 시도 기준으로는 높은 편 — 1차 실측 후 비현실적이면 재조정한다.

## 12. 레이턴시 목표

| 구간 | 목표 |
|---|---|
| Retrieval | < 500ms |
| Reranking | < 700ms |
| Prompt Assembly | < 300ms |
| TTFT(첫 토큰) | 3~7초 |
| Total Response | 8~15초 |

TTFT가 10초를 넘으면 reranker 또는 LLM 단계를 우선 의심한다.

## 13. 실행 순서

1. bge-m3 단독 baseline 측정 (Retrieval + RAG 지표)
2. 임베딩 3파전 A/B (bge-m3 / bge-m3-ko / KURE) → 승자 확정
3. Reranker A/B (bge-reranker-v2-m3 / bge-reranker-base) — 임베딩 승자 위에서 진행
4. Retrieval 지표로 1차 컷 → RAG 지표로 최종 컷 → Abstain Precision으로 안전성 확인
5. Context Precision 목표치는 1차 baseline 실측값을 보고 역산해 확정

## 14. Claude Code 인수인계 체크리스트

- [ ] 입력 소스: `reactivity_reference.db` (msds_sections, chemical_group_membership, chemicals)
- [ ] 출력물: 마크다운 청크 파일 + FAISS 인덱스 + BM25 인덱스 + SQLite 메타데이터 테이블(§6)
- [ ] 메타데이터 필수 필드: §6 SQLite/Payload 필드 전부
- [ ] 비협상 원칙 4종 파이프라인 반영 확인: 매트릭스 단독판정 금지 / CAMEO 68그룹 엄격적용 / 근거등급제 / Abstain 정책
- [ ] Embedding/Reranker는 반드시 A/B 결과로 확정할 것 — 임의로 하나를 먼저 고정하지 말 것
- [ ] §11/§12 목표치는 잠정치임을 인지하고, baseline 실측 후 재조정 여지를 열어둘 것

## 15. 참고 — v1과의 관계

이 문서는 `archive/stage4_design_v1_superseded_2026-08-06.md`를 완전히 대체한다.
v1에 인용된 외부 출처(hoft.tistory, kt cloud, s-core, dl-pkw, storycompiler)는 세부 수치가
미검증 상태였음이 v1 문서에 이미 명시돼 있음 — v2에서 재인용할 경우도 동일하게
원문 재확인 없이는 신뢰하지 말 것.
