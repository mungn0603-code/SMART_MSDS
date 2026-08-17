# archive/ — 폐기·기각 파일 보관소

프로젝트 루트(`01_collection/` ~ `05_evaluation/`, `docs/`)에는 **현재 채택된 최종
파일만** 남긴다. 과거 실행 로그, 폐기된 중간 산출물, 기각된 접근법은 여기에 분야별로
보관하며, 각 하위 폴더에는 무엇을 왜 옮겼는지 설명하는 `NOTES.md`가 있다.

현재 채택 상태의 기준 문서는 [`docs/HANDOFF.md`](../docs/HANDOFF.md)이며, 이 문서에
없는 과거 정정 이력은 [`superseded_docs/HANDOFF_ARCHIVE.md`](superseded_docs/HANDOFF_ARCHIVE.md)를 본다.
`docs/`는 2026-08-17부터 8개 표준 문서(README/PIPELINE/DATA/RETRIEVAL/GENERATION/
FILE_GUIDE/HANDOFF/PROJECT_LOG)만 유지한다 — 그 문서들이 흡수한 원본 상세 문서는
[`superseded_docs/`](superseded_docs/)에 있다.

## 폴더 구성

| 폴더 | 내용 | 상세 |
|---|---|---|
| `01_collection/` | KOSHA/CAMEO 수집 단계 — 실행 로그, 폐기된 CSV 스냅샷, 해결된 이슈의 진단 스크립트 | [NOTES.md](01_collection/NOTES.md) |
| `02_pubchem_rejected/` | CAS↔물질 매핑에 시도했다 기각한 PubChem SDF 경로(CAMEO 경로로 최종 대체) | [NOTES.md](02_pubchem_rejected/NOTES.md) |
| `04_rag_agent/` | RAG 검색 단계 — 실행 로그, 섹션필터 적용 전 폐기된 A/B 실험 결과 | [NOTES.md](04_rag_agent/NOTES.md) |
| `generation_experiments/` | Generation 단계 — 기각된 prompt v2/v2.1, Cascade Judge, RAGAS 파이프라인 | [NOTES.md](generation_experiments/NOTES.md) |
| `design_docs/` | 설계 철학 자체가 교체되며 폐기된 문서(Stage 4 기술스택 도입근거 v1) | [NOTES.md](design_docs/NOTES.md) |
| `superseded_docs/` | 2026-08-17 문서 재편으로 8개 표준 문서에 흡수된 원본 상세 문서(decisions.md 등) | [NOTES.md](superseded_docs/NOTES.md) |
| `adhoc_check_scripts/` | 특정 시점 이슈 조사용 1회성 스크립트(이슈 해결 후 존재 목적 소멸) | [NOTES.md](adhoc_check_scripts/NOTES.md) |

## 원칙
- **기각(rejected)**: 접근법 자체가 대체됨(예: PubChem 매핑 → CAMEO 매핑). 코드 오류
  때문이 아님.
- **폐기(superseded)**: 더 나은 실측/설계로 교체됨(예: 섹션필터 전 실험 결과).
- **1회성(one-off)**: 특정 버그/이슈 조사용으로 만들어졌고 그 이슈가 해결되어 재사용
  가치가 없음.
- 각 폴더의 `NOTES.md`는 이 세 분류 중 어디에 해당하는지, 관련 로그·후속 문서가
  무엇인지 명시한다.
- 데이터 계보 재현에 여전히 필요한 스크립트(예: `01_collection/backfill_round*.py`)는
  기각이 아니므로 아카이브하지 않고 원래 위치에 유지한다.
