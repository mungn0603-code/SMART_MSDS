| task | embedding | granularity | sections | retriever | reranker | query | n_queries | n_chunks | avg_gold_per_query | dropped_queries | Recall@10 | Recall@5 | Recall@20 | Hit@5 | Hit@10 | MRR | nDCG@10 | search_ms | query_encode_ms | total_retrieval_ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pair | bge-m3-ko | section | 2,10 | dense | - | pair | 2240 | 371 | 1.9000 | 10 | 0.7491 | 0.6288 | 0.8279 | 0.8496 | 0.9094 | 0.5446 | 0.5398 | 0.2190 | 331.3660 | 331.5800 |
| pair | bge-m3-ko | section | 2,10 | bm25 | - | pair | 2240 | 371 | 1.9000 | 10 | 0.6022 | 0.4379 | 0.7804 | 0.6790 | 0.8156 | 0.3538 | 0.3686 | 5.0500 | 0.0000 | 5.0500 |
| pair | bge-m3-ko | section | 2,10 | hybrid | - | pair | 2240 | 371 | 1.9000 | 10 | 0.8987 | 0.7734 | 0.9431 | 0.9335 | 0.9790 | 0.8803 | 0.8065 | 5.2690 | 331.3660 | 336.6300 |
