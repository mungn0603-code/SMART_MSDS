# STEP 3 최종 baseline 확정 - Hybrid Retrieval + Boilerplate Penalty (lambda=0.01)

173종 / 435 pairs / 2175 queries (dropped=0), corpus=366 chunks (section 2,10)
Evidence 지표 모수: 2160 queries (no_gold_evidence 15건 제외)

## Section 기준
| Metric | 기존 Hybrid | 최종 baseline(+penalty) |
|---|---:|---:|
| Recall@5 | 0.7696 | 0.7334 |
| Recall@10 | 0.8627 | 0.8688 |
| Recall@20 | 0.9106 | 0.9107 |
| Hit@5 | 0.9995 | 0.9991 |
| Hit@10 | 1.0000 | 1.0000 |
| MRR | 0.9834 | 0.9806 |
| nDCG@10 | 0.8660 | 0.8485 |

## Evidence 기준
| Metric | 기존 Hybrid | 최종 baseline(+penalty) |
|---|---:|---:|
| Recall@5 | 0.7292 | 0.8118 |
| Recall@10 | 0.8567 | 0.9204 |
| Recall@20 | 0.9315 | 0.9676 |
| Hit@5 | 0.9264 | 0.9569 |
| Hit@10 | 0.9690 | 0.9866 |
| MRR | 0.5157 | 0.8352 |
| nDCG@10 | 0.5671 | 0.7912 |