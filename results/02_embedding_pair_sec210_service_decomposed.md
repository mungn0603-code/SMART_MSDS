| task | embedding | granularity | sections | retriever | reranker | query | n_queries | n_chunks | avg_gold_per_query | dropped_queries | Recall@10 | Recall@5 | Recall@20 | Hit@5 | Hit@10 | MRR | nDCG@10 | search_ms | query_encode_ms | total_retrieval_ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pair | bge-m3-ko | section | 2,10 | dense | - | decomposed | 2240 | 371 | 1.9000 | 10 | 0.9866 | 0.9676 | 0.9866 | 0.9955 | 1.0000 | 0.7763 | 0.8182 | 0.4900 | 460.8480 | 461.3400 |
| pair | bge-m3-ko | section | 2,10 | bm25 | - | decomposed | 2240 | 371 | 1.9000 | 10 | 0.9152 | 0.8516 | 0.9353 | 0.9665 | 0.9866 | 0.3533 | 0.5251 | 10.7360 | 0.0000 | 10.7400 |
| pair | bge-m3-ko | section | 2,10 | hybrid | - | decomposed | 2240 | 371 | 1.9000 | 10 | 0.9888 | 0.9688 | 0.9933 | 0.9978 | 1.0000 | 0.9581 | 0.9547 | 11.2260 | 460.8480 | 472.0700 |
