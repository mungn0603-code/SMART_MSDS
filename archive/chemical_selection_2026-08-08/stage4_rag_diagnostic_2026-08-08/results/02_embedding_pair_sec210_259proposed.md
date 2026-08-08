| task | embedding | granularity | sections | retriever | reranker | n_queries | n_chunks | avg_gold_per_query | dropped_queries | Recall@10 | Recall@5 | Recall@20 | Hit@5 | Hit@10 | MRR | nDCG@10 | search_ms | query_encode_ms | total_retrieval_ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pair | bge-m3-ko | section | 2,10 | dense | - | 1785 | 545 | 3.4000 | 130 | 0.8586 | 0.7724 | 0.9085 | 0.9720 | 0.9843 | 0.9362 | 0.8370 | 0.0820 | 204.0480 | 204.1300 |
| pair | bge-m3-ko | section | 2,10 | bm25 | - | 1785 | 545 | 3.4000 | 130 | 0.7372 | 0.6528 | 0.8042 | 0.9176 | 0.9423 | 0.8436 | 0.7173 | 1.7470 | 0.0000 | 1.7500 |
| pair | bge-m3-ko | section | 2,10 | hybrid | - | 1785 | 545 | 3.4000 | 130 | 0.8960 | 0.7919 | 0.9344 | 0.9759 | 0.9944 | 0.9309 | 0.8572 | 1.8290 | 204.0480 | 205.8800 |
