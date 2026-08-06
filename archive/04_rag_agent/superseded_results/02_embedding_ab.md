| embedding | granularity | retriever | reranker | n_queries | n_chunks | dropped_queries | Recall@5 | Recall@10 | MRR | nDCG@10 | retrieval_ms_per_query |
|---|---|---|---|---|---|---|---|---|---|---|---|
| bge-m3-ko | section | dense | - | 407 | 805 | 0 | 0.9926 | 0.9951 | 0.9317 | 0.9478 | 0.0300 |
| bge-m3-ko | section | bm25 | - | 407 | 805 | 0 | 0.8796 | 0.9214 | 0.4694 | 0.5834 | 3.2600 |
| bge-m3-ko | section | hybrid | - | 407 | 805 | 0 | 0.9902 | 0.9926 | 0.8592 | 0.8934 | 3.3000 |
