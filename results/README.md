# results/ — 어떤 수치가 어느 파일에서 나오는가

이 폴더에는 **최종 결과만** 둔다. 중간 실험 산출물은 전부 `archive/`로 옮겼다.
문서(README·`docs/`)가 인용하는 수치는 아래 표의 근거 파일에서 나온 것이다.

## 확정 지표와 그 근거

### 2026-08-29 — Retrieval: service 173종 · 쌍 질의 2,240건

| Recall@10 | Hit@10 | MRR | nDCG@10 |
|---:|---:|---:|---:|
| 0.9888 | 1.0000 | 0.9581 | 0.9547 |

근거: `02_embedding_pair_sec210_service_decomposed.{csv,md}`
재현: `python scripts/4_retrieval/run_ab.py embedding --models bge-m3-ko --granularity section --task pair --sections 2,10 --corpus-tag service --decompose`

채점은 **evidence 기준**(`gold_evidence` = §2 100%)이다. `gold_section` 기준 수치와 섞어 쓰지 않는다.
분해 전 쌍질의 baseline(0.8987 / 0.9790 / 0.8803 / 0.8065)은
`archive/2026-08-30_superseded/retrieval/`에 있다 — 같은 평가셋·같은 채점 기준이라 직접 비교 가능하다.

### Generation: service 코퍼스 173종 · 쌍 질의 2,240건

현행 프롬프트는 둘이다. 둘 다 근거는 `--context pair`(CAS 직접조회)이고 조건이 같다.

| 프롬프트 | 정답률(판정줄) | 정답률(judge 재분류) | faithful | 물질혼동 | 판정줄–본문 |
|---|---:|---:|---:|---:|---:|
| `cameo_service_v7`(자유텍스트, 앱 경로) | 99.9% | 94.0% | 97.5% | 0.0% | 93.4% |
| `cameo_service_v8b_schema`(structured) | 100.0% | 92.9% | 92.9% | 0.0% | 92.0% |

```bash
# v8b (이 폴더)
python scripts/6_eval/summarize_cameo_full.py --gen results/generation_cameo_full_pair_v8b.jsonl --eval results/eval_cameo_full_pair_v8b.jsonl
# v7 (앱이 쓰는 프롬프트, 산출물은 archive)
python scripts/6_eval/summarize_cameo_full.py --gen archive/2026-08-29_generation_prompt_history/v7/generation_cameo_full_pair_v7.jsonl --eval archive/2026-08-29_generation_prompt_history/v7/eval_cameo_full_pair_v7.jsonl
```

정답률은 **두 정의를 반드시 함께** 적는다. 판정줄 기준 수치는 코드가 판정을 주입해서
나오는 **구조적 보장값**이라 그것만 쓰면 남은 결함(Caution 칸의 본문 서술)이 숨는다.
지표 정의의 단일 출처는 `scripts/6_eval/summarize_cameo_full.py`의 docstring이다.

## 파일 목록

### Retrieval
| 파일 | 내용 |
|---|---|
| `02_embedding_pair_sec210_service_decomposed.{csv,md}` | **확정 지표**(질의 분해) |
| `frozen_retrieval_top10.jsonl` | Generation 입력으로 고정한 top-10(쌍 질의) |
| `frozen_retrieval_top10_decomposed.jsonl` | 분해판. **아직 Generation에 반영되지 않았다** |

### Generation
| 파일 | prompt_version | 생성 명령 |
|---|---|---|
| `generation_cameo_full_pair_v8b.jsonl` / `eval_cameo_full_pair_v8b.jsonl` | `cameo_service_v8b_schema` | `run_cameo_full.py --context pair --format schema --tag v8b` |

v7 산출물은 `archive/2026-08-29_generation_prompt_history/v7/`에 있다. **프롬프트 자체는
현행이다** — `run_cameo_full.py --format text`의 기본 경로이고 앱이 이걸 쓴다. 옮긴 것은
결과 파일뿐이다. v6 이전 세대와 폐기된 v8·v9는 같은 폴더의 다른 하위 폴더에 있다.

### Registry · KOSHA
| 파일 | 내용 |
|---|---|
| `registry237_service_contract_after_chunking_2026-08-22.csv` | 서비스 계약 대조표 **최종판** |
| `registry_service_contract_recheck.csv` | `service_contract_audit.py` 기본 출력(재점검) |
| `registry_cameo_mapping_2026-08-22.csv` | 미매핑 95종의 PubChem `hid=86` 조회 전량 |
| `registry_expansion_proposal_2026-08-22.csv` | 신규 후보 26종 판정표 |
| `kosha_registry_lookup.csv` | registry 전체의 KOSHA 등재 상태 스냅샷 |
| `kosha_missing39_probe_2026-08-22.csv` | 미등재 39종을 CAS/국문명/영문명 3경로로 실조회(전부 0건) |

대조표 1~3판은 `archive/2026-08-30_superseded/registry/`.

## 규약

- **덮어쓰지 않는다.** 재실행 결과는 `--tag`나 날짜를 붙여 새 파일로 남긴다.
- `run_cameo_full.py`를 `--tag` 없이 돌리면 `generation_cameo_full.jsonl` /
  `eval_cameo_full.jsonl`이 여기 **새로** 생긴다. 위 표의 산출물과는 다른 파일이다.
