| task | embedding | granularity | sections | retriever | reranker | n_queries | n_chunks | avg_gold_per_query | dropped_queries | Recall@10 | Recall@5 | Recall@20 | Hit@5 | Hit@10 | MRR | nDCG@10 | search_ms | query_encode_ms | total_retrieval_ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pair | bge-m3-ko | section | 2,10 | dense | - | 2160 | 366 | 1.9000 | 15 | 0.8025 | 0.6815 | 0.8704 | 0.8866 | 0.9380 | 0.5489 | 0.5682 | 0.1270 | 430.8810 | 431.0100 |
| pair | bge-m3-ko | section | 2,10 | bm25 | - | 2160 | 366 | 1.9000 | 15 | 0.7299 | 0.5509 | 0.8532 | 0.8130 | 0.9014 | 0.4084 | 0.4487 | 2.6820 | 0.0000 | 2.6800 |
| pair | bge-m3-ko | section | 2,10 | hybrid | - | 2160 | 366 | 1.9000 | 15 | 0.9204 | 0.8118 | 0.9676 | 0.9569 | 0.9866 | 0.8352 | 0.7912 | 2.8090 | 430.8810 | 433.6900 |
