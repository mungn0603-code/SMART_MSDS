# archive/04_rag_agent — 정리 사유

`04_rag_agent/`에서 최종 확정 구성만 남기고 옮긴 항목들. 최종 확정 구성(임베딩/청킹/검색/
필터)은 [`docs/HANDOFF.md`](../../docs/HANDOFF.md) §0 표 참고.

**현재 최종 baseline**(2026-08-08, 173종 corpus + Hybrid + Boilerplate Penalty λ=0.01)은
`04_rag_agent/results/02_embedding_pair_sec210_173.{csv,md}`. 아래
`02_embedding_pair_sec210.{csv,md}`(접미사 없음, 198종 기준)는 그 이전 확정 baseline으로,
`docs/HANDOFF.md` §0/§0-1 서술이 이 파일을 직접 참조하고 있어 경로를 유지한 채 원위치에
남겨뒀다 — "폐기"가 아니라 "이전 단계 기록"이다.

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

| `02_embedding_pair_sec210_t0.csv` / `_t1.csv` | 2026-08-07 질의 템플릿(t0/t1)별 개별 breakdown, 198종 383쌍 기준 | 173종 재동결(2026-08-08) 이후 코퍼스 자체가 바뀌어 더 이상 재현 가능한 현재 상태가 아님. 수치는 `docs/HANDOFF.md` §0-1에 이미 표로 옮겨져 있어 원본 CSV만 보존 |
| `gold_pair_pre_evidence_merge_2026-08-08.jsonl.bak` | 173종 재동결 직후, `gold_evidence`/`evidence_count`/`evidence_detail` 필드 병합 **이전** `gold_pair.jsonl` 스냅샷 | 병합 후 원본 파일에 evidence 필드가 추가되며 덮어써짐 — 병합 전 상태를 되짚어볼 수 있게 보존(`docs/HANDOFF.md` §0-3 STEP2 참고) |
