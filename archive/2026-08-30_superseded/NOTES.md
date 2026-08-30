# archive/2026-08-30_superseded — 정리 사유

2026-08-30 저장소 재구성에서 **`results/`는 최종 결과만, `data/`는 코드가 실제로 읽는
입력만** 남기기로 하면서 옮긴 것들. 삭제한 파일은 없다.

## retrieval/ — 분해 이전 Retrieval baseline

| 파일 | 내용 |
|---|---|
| `02_embedding_pair_sec210_service.{csv,md}` | service 173종 **쌍 질의** baseline |

Recall@10 0.8987 / Hit@10 0.9790 / MRR 0.8803 / nDCG@10 0.8065 (2,240질의).

**폐기가 아니라 대체다.** 질의 분해(물질명 단독 질의 2개를 던져 top-5씩 교차 병합)로
전 지표가 개선되고 악화가 0건이라 확정 지표를 분해판으로 갈아끼웠다
(0.9888 / 1.0000 / 0.9581 / 0.9547). **같은 평가셋·같은 채점 기준(evidence)이라
직접 비교 가능하다** — [`docs/RETRIEVAL.md`](../../docs/RETRIEVAL.md)의 비교표가 이 파일 기준이다.

## registry/ — 서비스 계약 대조표 1~3판

| 파일 | 시점 |
|---|---|
| `registry237_service_contract_2026-08-22.csv` | 인덱스 23종 편입 **전** |
| `registry237_service_contract_after_reindex_2026-08-22.csv` | 편입 **후** |
| `registry237_service_contract_after_cameo_2026-08-22.csv` | CAMEO 매핑 확충 후 |
| `corpus96_core_reassessment_2026-08-22.csv` | 코퍼스 전용 96종 재평가(확장 검토 중간 판정표) |

최종판 `_after_chunking_2026-08-22.csv`는 `results/`에 남아 있다. 전부
`scripts/2_registry/service_contract_audit.py`가 같은 조건으로 만든 것이라
1~3판은 최종판이 어떻게 나왔는지 추적하는 용도로만 의미가 있다.

## data_inputs/ — 코드가 더 이상 읽지 않는 입력

| 파일 | 왜 옮겼나 |
|---|---|
| `boilerplate_sec10_values.json` | §10 정형문구 15종 실측 기록. 2026-08-09에 `retrieval.py`의 `boilerplate_penalty_vector()`가 "§10이면 무조건 λ" 로 단순화되면서 **코드가 이 파일을 읽지 않게 됐다**. 당시 정형문구가 무엇이었는지의 실측 기록으로 보존 |
| `CRW_Data_Export_reactivity map.xlsx` | CRW 4.0 원본 매트릭스 **후보**였으나 68×68 매트릭스뿐이라 채택되지 않았다([`docs/PROJECT_LOG.md`](../../docs/PROJECT_LOG.md)). 실제 시드 입력은 `archive/01_collection/Cameo_reactivity.csv` |
| `core_gap_kosha_target.csv` | 207→237 확장 후보의 KOSHA 등재 확인용 **1회성 조회 입력**. 확장이 끝나 재사용 없음 |
| `core_chunk_target_2026-08-22.csv` | B1 티어 39종 **1회성 청킹 입력**(`pipeline.py --target-csv`). 청킹 완료 후 재사용 없음 |

넷 다 어떤 코드도 경로로 참조하지 않는다(2026-08-30 기준 `grep` 확인).

## 함께 옮기지 않은 것

- `data/collection/undergrad_target_chemicals.csv` — 옛 200종 목록이지만
  `kosha_msds_collector.py`의 `TARGET_CSV` 기본값이고 `pubchem_verify_groups.py`도 읽는다.
  코드가 살아 있으므로 `data/`에 남긴다.
- `data/collection/pubchem_verification_report{,_full}.csv` — `pubchem_verify_groups.py`의
  입출력 파일이라 남긴다.
