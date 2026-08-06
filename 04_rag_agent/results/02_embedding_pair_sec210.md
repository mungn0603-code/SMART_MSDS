| task | embedding | granularity | sections | retriever | reranker | n_queries | n_chunks | avg_gold_per_query | dropped_queries | Recall@10 | Recall@5 | Recall@20 | Hit@5 | Hit@10 | MRR | nDCG@10 | search_ms | query_encode_ms | total_retrieval_ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pair | bge-m3-ko | section | 2,10 | dense | - | 369 | 409 | 4.1000 | 0 | 0.8829 | 0.7804 | 0.9304 | 1.0000 | 1.0000 | 0.9837 | 0.8772 | 0.0890 | 501.7240 | 501.8100 |
| pair | bge-m3-ko | section | 2,10 | bm25 | - | 369 | 409 | 4.1000 | 0 | 0.7366 | 0.6757 | 0.8611 | 0.9973 | 1.0000 | 0.9796 | 0.7823 | 6.1920 | 0.0000 | 6.1900 |
| pair | bge-m3-ko | section | 2,10 | hybrid | - | 369 | 409 | 4.1000 | 0 | 0.9005 | 0.7811 | 0.9409 | 1.0000 | 1.0000 | 0.9986 | 0.8932 | 6.2810 | 501.7240 | 508.0000 |
