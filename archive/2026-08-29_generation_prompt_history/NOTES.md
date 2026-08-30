# archive/2026-08-29_generation_prompt_history — 정리 사유

Generation 프롬프트 세대별 산출물. **2026-08-30 저장소 정리에서 `results/`가 현행
산출물만 담도록 분리하면서 옮겼다.** 삭제한 것은 없다.

## 세대 대조

| 세대 | 상태 | 위치 | 코드 경로 |
|---|---|---|---|
| `cameo_service_v6` | **문서의 확정 지표를 낸 산출물** | `v6/` (여기) | 프롬프트가 코드에 더는 없다 |
| `cameo_service_v7` | 현행 · 자유텍스트 | `results/*_v7.jsonl` | `run_cameo_full.py --format text` (기본값) |
| `cameo_service_v8_schema` | **폐기** | `_v8_verdict_regression/` | 없음 |
| `cameo_service_v8b_schema` | 현행 · structured output | `results/*_v8b.jsonl` | `run_cameo_full.py --format schema` |
| `cameo_service_v9_schema` | **폐기** | `_v9_regression/` | 없음 |

## v6/ — 왜 archive인데 문서가 인용하는가

README · [`docs/GENERATION.md`](../../docs/GENERATION.md) · `CLAUDE.md`가 인용하는
**정답률(판정줄) 99.9% / judge 재분류 83.9% / faithful 94.6% / 물질혼동 14.7%**
(쌍 질의 2,240건, `corpus_tag='service'`)는 전부 이 폴더의 산출물에서 나온 값이다.
v7·v8b는 v6 이후에 나왔지만 **아직 문서에 반영되지 않았다** — 지표 재측정은 별개 작업이다.

이번 이동에서 **수치는 한 자리도 바꾸지 않았다.** 경로 표기만 새 위치로 고쳤다.
`summarize_cameo_full.py` / `reparse_verdict_line.py` / `build_pair_report.py`의 기본
입력 경로도 여기를 가리키게 바꿔서, 인자 없이 실행하면 이동 전과 같은 수치가 나온다.

```bash
python scripts/summarize_cameo_full.py \
  --eval archive/2026-08-29_generation_prompt_history/v6/eval_cameo_full_reparsed.jsonl
```

| 파일 | 내용 |
|---|---|
| `generation_cameo_full.jsonl` / `eval_cameo_full.jsonl` | frozen top-10 컨텍스트 전수 생성·채점 |
| `eval_cameo_full_reparsed.jsonl` | 판정줄 재파싱본 — **확정 지표는 이 파일 기준** |
| `generation_cameo_full_pair.jsonl` / `eval_cameo_full_pair.jsonl` / `eval_cameo_full_pair_reparsed.jsonl` | 같은 v6 프롬프트를 `--context pair`(CAS 직접조회)로 돌린 대조군 |

주의: `run_cameo_full.py`의 출력 슬롯(`GEN_OUT`/`EVAL_OUT`)은 그대로 두었다 —
CLAUDE.md가 "확정 지표를 낸 경로는 건드리지 않는다"로 지정한 스크립트다. 따라서 태그 없이
재실행하면 `results/generation_cameo_full.jsonl`이 **새로** 생긴다. 그건 재실행 결과지
여기 보존된 v6 산출물이 아니다.

## _v8_verdict_regression/ · _v9_regression/ — 폐기 기록

각 폴더의 `FINDING.md`가 사전 등록한 채택 기준과 실측 결과, 폐기 사유를 담는다.
요지만:

- **v8**: `verdict`를 스키마 필드로 두고 모델에게 CAMEO 판정을 옮기라고 시켰더니
  1,922건 중 20건(1.04%)에서 판정이 뒤집혔고 18건이 위험을 낮추는 방향이었다.
  타협 불가 원칙 위반이라 1,928건에서 중단. → v8b에서 스키마에서 빼고 코드가 주입.
  이 설계로 되돌아가는 것은 `tests/test_run_cameo_resume.py`의
  `test_verdict_is_never_model_output()`이 막는다.
- **v9**: Caution 칸을 겨냥해 `SCHEMA_PROMPT`를 개정했으나 채택 기준 4개 중 2개 미달,
  McNemar 양측 p=0.789로 v8b와 통계적으로 구분되지 않아 폐기. 지시는 지켜졌는데
  (evidence_gap 보일러플레이트 -30pt 등) judge 일치가 ±0이었다는 게 결론이다.
  폐기된 프롬프트 전문은 `_v9_regression/schema_prompt_v9.txt`에 그대로 있다.
