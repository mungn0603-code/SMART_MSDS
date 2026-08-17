# archive/superseded_docs — 정리 사유

2026-08-17 문서 재편에서 `docs/`를 8개 표준 문서(README/PIPELINE/DATA/RETRIEVAL/
GENERATION/FILE_GUIDE/HANDOFF/PROJECT_LOG)로만 유지하기로 하면서, 그 표준 문서들이
내용을 흡수·요약한 원본 상세 문서를 여기로 옮겼다. **삭제가 아니라 이관** — 각 문서의
결론은 아래 표의 흡수처 문서에 반영돼 있고, 판단 과정의 세부 근거(원본 수치, 시행착오
경위)는 이 폴더에 그대로 보존된다.

| 파일 | 흡수처(현재 문서) | 비고 |
|---|---|---|
| `msds_risk_assessment_readme.md` | `README.md` | 2026-07-30 최초 기획 문서(프로젝트 기원) — 당시 "유일한 기준점"이었으나 이후 전부 구현·갱신됨 |
| `stage4_design_principles_v2.md` | `docs/PIPELINE.md` | Stage 4(RAG) 설계 원칙 확정판 |
| `stage4_design_changes_2026-08-06.md` | `docs/PIPELINE.md` | 설계 변경 이력 12건(2026-08-06 세션) |
| `session_log_2026-08-06.md` | `docs/PROJECT_LOG.md` | 2026-08-06 세션 요약(KOSHA API 이슈·1차 수집) |
| `decisions.md` | `docs/DATA.md` / `docs/RETRIEVAL.md` / `docs/GENERATION.md` | 프로젝트 전체 의사결정 로그(545줄) — 주제별로 분산 흡수 |
| `chemical_selection_final_2026-08-08.md` | `docs/DATA.md` | 173종 최종 선정 기준(MANDATORY/HAZARD-RELEVANT/REPRESENTATIVE) |
| `retrieval_query_diversity_review_2026-08-07.md` | `docs/RETRIEVAL.md` | 질의 템플릿 다양화 검증(단일→5개) |
| `HANDOFF_ARCHIVE.md` | `docs/HANDOFF.md` | HANDOFF.md에 없는 과거 정정 이력(이전에도 archive 성격 문서였음, 위치만 이동) |

## 원칙
이 폴더의 문서를 새로 읽어야 하는 경우: 표준 문서(`docs/PIPELINE.md` 등)의 서술이
"왜 이렇게 결정했는가"의 근거·시행착오·실측 원본 수치까지 필요할 때. 표준 문서는
결론과 최종 수치만 담고, 그 결론에 이른 과정(가설→검증→기각/채택)은 여기 원본에 있다.
