| task | embedding | granularity | sections | retriever | reranker | n_queries | n_chunks | avg_gold_per_query | dropped_queries | Recall@10 | Recall@5 | Recall@20 | Hit@5 | Hit@10 | MRR | nDCG@10 | search_ms | query_encode_ms | total_retrieval_ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| pair | bge-m3-ko | section | 2,10 | dense | - | 2175 | 366 | 4.3000 | 0 | 0.8069 | 0.7111 | 0.8617 | 0.9968 | 1.0000 | 0.9781 | 0.8197 | 0.0620 | 194.5640 | 194.6300 |
| pair | bge-m3-ko | section | 2,10 | bm25 | - | 2175 | 366 | 4.3000 | 0 | 0.7764 | 0.6659 | 0.8432 | 0.9890 | 0.9940 | 0.9680 | 0.7934 | 1.1670 | 0.0000 | 1.1700 |
| pair | bge-m3-ko | section | 2,10 | hybrid | - | 2175 | 366 | 4.3000 | 0 | 0.8688 | 0.7334 | 0.9107 | 0.9991 | 1.0000 | 0.9806 | 0.8485 | 1.2290 | 194.5640 | 195.7900 |
