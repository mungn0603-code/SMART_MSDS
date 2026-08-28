| task | embedding | granularity | sections | retriever | reranker | n_queries | n_chunks | avg_gold_per_query | dropped_queries | Recall@10 | Recall@5 | Recall@20 | Hit@5 | Hit@10 | MRR | nDCG@10 | search_ms | query_encode_ms | total_retrieval_ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pair | bge-m3-ko | section | 2,10 | dense | - | 2250 | 371 | 4.3000 | 0 | 0.7686 | 0.6741 | 0.8313 | 0.9947 | 0.9973 | 0.9669 | 0.7866 | 0.0920 | 395.7380 | 395.8300 |
| pair | bge-m3-ko | section | 2,10 | bm25 | - | 2250 | 371 | 4.3000 | 0 | 0.6820 | 0.5841 | 0.7705 | 0.9689 | 0.9782 | 0.9468 | 0.7175 | 2.1170 | 0.0000 | 2.1200 |
| pair | bge-m3-ko | section | 2,10 | hybrid | - | 2250 | 371 | 4.3000 | 0 | 0.8164 | 0.6938 | 0.8505 | 0.9956 | 0.9996 | 0.9733 | 0.8108 | 2.2090 | 395.7380 | 397.9500 |
