# archive/04_rag_agent — 정리 사유

`04_rag_agent/`에서 최종 확정 구성만 남기고 옮긴 항목들. 최종 확정 구성(임베딩/청킹/검색/
필터)은 [`docs/HANDOFF.md`](../../docs/HANDOFF.md) §0 표 참고. 최종 실측 결과는
`04_rag_agent/results/02_embedding_pair_sec210.{csv,md}` (섹션 §2·§10 필터 적용, 이 파일만
현재 위치에 유지됨).

## logs/ — 실행 로그
| 파일 | 내용 |
|---|---|
| `run_baseline.log` | `run_ab.py` 초기 베이스라인 실행 로그 |
| `run_embedding_ko.log` | bge-m3-ko 임베딩 A/B 실행 로그 |

재실행 시 다시 생성되므로 코드 동작에 필요하지 않음. 과거 실행 확인용으로만 보존.

## superseded_results/ — 폐기된 실험 결과
**기각 사유: 이후 실험(섹션 §2·§10 필터 적용)으로 대체됨(superseded). 실험 자체의 오류는 아님.**

| 파일 | 조건 | 대체 이유 |
|---|---|---|
| `02_embedding_ab.md` / `.csv` | task=fact(단일물질 407건), 섹션 필터 없음 | 제품 과제가 "물질 쌍"으로 확정되며(설계 오류 정정) 단일물질 fact 과제는 부품 점검용으로 격하. `evalset.py`/`gold_retrieval.jsonl`은 유지되나 이 결과표는 더 이상 대표 지표가 아님 |
| `02_embedding_pair.md` / `.csv` | task=pair(369쌍), 섹션 필터 없음(전체 805청크) | §2·§10 필터 적용판(`_sec210`)이 정확도·속도 동시 개선(Recall@10 0.8691→0.8829, nDCG@10 0.8461→0.8772, latency 513→502ms)하여 최종 채택됨. 근거: [`docs/HANDOFF.md`](../../docs/HANDOFF.md) §0 |

참고: 세 표 모두에 dense/bm25/hybrid 3가지 retriever 실측이 포함되어 있다. **dense가
7개 목표 중 4개, hybrid가 6개 충족**했음에도 최종 결정은 dense 유지(사용자 지시) —
이는 결과값의 우열이 아니라 사용자 결단이므로 hybrid 행 자체는 기각이 아니다. 상세
근거는 [`docs/stage4_design_changes_2026-08-06.md`](../../docs/stage4_design_changes_2026-08-06.md) §5·§7.
