| task | embedding | granularity | sections | retriever | reranker | n_queries | n_chunks | avg_gold_per_query | dropped_queries | Recall@10 | Recall@5 | Recall@20 | Hit@5 | Hit@10 | MRR | nDCG@10 | search_ms | query_encode_ms | total_retrieval_ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pair | bge-m3-ko | section | 2,10 | dense | - | 1915 | 407 | 4.1000 | 0 | 0.8800 | 0.7804 | 0.9284 | 0.9995 | 1.0000 | 0.9832 | 0.8763 | 0.0790 | 395.0950 | 395.1700 |
| pair | bge-m3-ko | section | 2,10 | bm25 | - | 1915 | 407 | 4.1000 | 0 | 0.7885 | 0.7002 | 0.8598 | 0.9901 | 0.9948 | 0.9683 | 0.8078 | 1.7140 | 0.0000 | 1.7100 |
| pair | bge-m3-ko | section | 2,10 | hybrid | - | 1915 | 407 | 4.1000 | 0 | 0.9234 | 0.8166 | 0.9562 | 0.9995 | 1.0000 | 0.9915 | 0.9104 | 1.7930 | 395.0950 | 396.8900 |
