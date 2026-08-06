| task | embedding | granularity | sections | retriever | reranker | n_queries | n_chunks | avg_gold_per_query | dropped_queries | Recall@10 | Recall@5 | Recall@20 | Hit@5 | Hit@10 | MRR | nDCG@10 | search_ms | query_encode_ms | total_retrieval_ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pair | bge-m3-ko | section | all | dense | - | 369 | 805 | 4.1000 | 0 | 0.8691 | 0.7376 | 0.9252 | 1.0000 | 1.0000 | 0.9661 | 0.8461 | 0.2930 | 513.0610 | 513.3500 |
| pair | bge-m3-ko | section | all | bm25 | - | 369 | 805 | 4.1000 | 0 | 0.7393 | 0.5742 | 0.8308 | 0.9973 | 0.9973 | 0.7306 | 0.6412 | 8.4910 | 0.0000 | 8.4900 |
| pair | bge-m3-ko | section | all | hybrid | - | 369 | 805 | 4.1000 | 0 | 0.8767 | 0.7254 | 0.9344 | 1.0000 | 1.0000 | 0.9630 | 0.8347 | 8.7840 | 513.0610 | 521.8500 |
