| task | embedding | granularity | sections | retriever | reranker | n_queries | n_chunks | avg_gold_per_query | dropped_queries | Recall@10 | Recall@5 | Recall@20 | Hit@5 | Hit@10 | MRR | nDCG@10 | search_ms | query_encode_ms | total_retrieval_ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pair | bge-m3-ko | section | 2,10 | dense | - | 1915 | 893 | 4.1000 | 0 | 0.8203 | 0.7180 | 0.8834 | 0.9958 | 0.9995 | 0.9719 | 0.8241 | 0.1340 | 432.2420 | 432.3800 |
| pair | bge-m3-ko | section | 2,10 | bm25 | - | 1915 | 893 | 4.1000 | 0 | 0.7424 | 0.6649 | 0.8056 | 0.9875 | 0.9916 | 0.9423 | 0.7635 | 2.8000 | 0.0000 | 2.8000 |
| pair | bge-m3-ko | section | 2,10 | hybrid | - | 1915 | 893 | 4.1000 | 0 | 0.8826 | 0.7668 | 0.9272 | 0.9984 | 0.9995 | 0.9835 | 0.8734 | 2.9340 | 432.2420 | 435.1800 |
