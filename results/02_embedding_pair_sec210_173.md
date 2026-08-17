| task | embedding | granularity | sections | retriever | reranker | n_queries | n_chunks | avg_gold_per_query | dropped_queries | Recall@10 | Recall@5 | Recall@20 | Hit@5 | Hit@10 | MRR | nDCG@10 | search_ms | query_encode_ms | total_retrieval_ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pair | bge-m3-ko | section | 2,10 | dense | - | 2160 | 366 | 1.9000 | 15 | 0.8025 | 0.6815 | 0.8704 | 0.8866 | 0.9380 | 0.5489 | 0.5682 | 0.1550 | 436.4450 | 436.6000 |
| pair | bge-m3-ko | section | 2,10 | bm25 | - | 2160 | 366 | 1.9000 | 15 | 0.7299 | 0.5509 | 0.8532 | 0.8130 | 0.9014 | 0.4084 | 0.4487 | 5.2240 | 0.0000 | 5.2200 |
| pair | bge-m3-ko | section | 2,10 | hybrid | - | 2160 | 366 | 1.9000 | 15 | 0.9336 | 0.8303 | 0.9681 | 0.9644 | 0.9884 | 0.9169 | 0.8500 | 5.3790 | 436.4450 | 441.8200 |
