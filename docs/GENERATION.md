# GENERATION — 설명을 어떻게 만들고 어떻게 채점하는가?

## 1. LLM의 역할은 판정이 아니라 설명이다

판정(Compatible / Caution / Incompatible)은 CAMEO 반응성 그룹 조회가 결정론적으로
내린다. LLM은 **그 판정을 이미 결정된 값으로 받아** MSDS §2·§10 원문으로 왜 그런지만
설명한다. 근거가 부족하면 Abstain한다.

이 구조를 코드가 강제한다.

- **판정줄은 모델이 쓰지 않는다.** structured output(v8b)에서 `verdict`는 스키마 필드가
  아니고 코드가 `cameo.category`를 주입한다(`render_answer`).
- **결론 문장도 모델이 쓰지 않는다.** `render_conclusion()`이 판정에 맞는 문장을 조립한다.
- 이 설계로 되돌아가는 것을 `tests/test_run_cameo_resume.py`의
  `test_verdict_is_never_model_output()`이 막는다.

> **왜 복사조차 시키지 않는가.** 판정을 스키마 필드로 두고 "그대로 옮기라"고 지시했더니
> 1,922건 중 20건(1.04%)에서 판정이 뒤집혔고 그중 18건이 위험을 낮추는 방향이었다.
> 코드가 이미 아는 값을 모델에 복사시키면 복사를 틀릴 기회를 주는 것이다.
> 근거: [`archive/.../_v8_verdict_regression/FINDING.md`](../archive/2026-08-29_generation_prompt_history/_v8_verdict_regression/FINDING.md)
>
> 따라서 아래 표의 **정답률(판정줄) 100%는 성과가 아니라 아키텍처가 보장하는 값**이다.
> 실제 품질을 재는 건 judge가 본문을 다시 분류한 값이다.

## 2. 프롬프트에 들어가는 것

```
[시스템 규칙]  +  [CAMEO 컨텍스트]  +  [MSDS 근거 n개]  +  [질문]
```

| 블록 | 무엇 | 만드는 곳 |
|---|---|---|
| CAMEO 컨텍스트 | 확정된 판정 + 그룹 쌍의 위험코드·발생가스 **원문** | `cameo_group_lookup.format_context(..., detailed=True)` |
| MSDS 근거 | 두 물질의 §2·§10 청크 전부. `[근거 n]`으로 번호를 매기고 답변이 그 번호를 인용한다 | `msds_context()`(앱) / `pair_chunk_ids()`(평가) — **정렬 규칙이 같다** |

CAMEO 위험코드는 뭉뚱그리지 않고 원문을 그대로 노출한다. 대신 시스템 규칙이 변환을
제한한다 — `Generates heat`는 "열을 발생시킬 수 있음"까지만 허용하고 폭발로 확대하지
않는다. 규칙 구성은 `[1. 판정]` `[2. 위험 이유 설명]` `[3. 화학적 추론 금지]`
`[3-1. 그룹 분류 vs 확인된 반응 구분]` `[4. MSDS 정보 사용]` `[5. 근거 부족 시]`
`[6. 물질 혼동 방지]`이며 원문은
[`scripts/5_generation/run_cameo_context_pilot.py`](../scripts/5_generation/run_cameo_context_pilot.py)에 있다.

**현행 프롬프트는 둘이고 둘 다 유효하다.**

| 버전 | 출력 형식 | 어디서 쓰나 |
|---|---|---|
| `cameo_service_v7` | 자유 텍스트 | **앱의 서비스 경로**(`SYSTEM_PROMPT` / `build_prompt`) · `run_cameo_full.py --format text`(기본값) |
| `cameo_service_v8b_schema` | JSON structured output (`PAIR_SCHEMA` 6필드) | `run_cameo_full.py --format schema` |

v8b는 자유 텍스트에서 정규식으로 긁던 판정줄·인용태그·결론문장을 스키마로 고정한 것이다.
스키마 산출물은 `render_answer()`가 자유 텍스트와 같은 모양으로 조립하므로 **채점 정의가
그대로 유지되고 v7과 직접 비교할 수 있다.**

> **두 결과의 지위가 다르다.** v7은 **현재 서비스 런타임 프롬프트의 결과**이고, v8b는
> **구조화 출력 실험의 평가 결과로 별도 관리한다.** 두 결과를 단일 서비스 성능으로
> 합산하지 않는다.

## 3. 현재 결과

두 실행 모두 조건이 같다 — Upstage `solar-pro3`(`reasoning_effort=high`) /
`corpus_tag='service'` 173종 371청크 / 근거는 `--context pair`(CAS 직접조회) /
쌍 질의 2,240건 전수 / **생성·채점 실패 0건**.

| 지표 | v7 (앱 경로) | v8b (structured) | 정의 |
|---|---:|---:|---|
| 정답률(판정줄) | 99.9% (2,238/2,240) | 100.0% (2,240/2,240) | 답변 판정줄이 CAMEO 판정을 유지 — v8b는 구조상 보장값 |
| **정답률(judge 재분류)** | **94.0%** (2,089/2,223) | **92.9%** (2,056/2,213) | judge가 **본문**을 재분류한 결과가 매트릭스와 일치 |
| Faithful | 97.5% (2,184/2,240) | 92.9% (2,080/2,240) | 근거 밖 주장 없음 |
| 물질 혼동 | 0.0% (0/2,240) | 0.0% (0/2,142) | 쌍의 두 물질 어디에도 없는 근거를 인용 |
| 인용 태그 출력 | 100.0% | 100.0% | 물질혼동 측정의 전제 |
| 판정줄–본문 일치 | 93.4% (2,087/2,235) | 92.0% (2,056/2,235) | |
| evidence precision / recall | 0.4598 / 0.9574 | 0.4397 / 0.8567 | |
| 생성 지연(평균) | 13.3초 | **4.2초** | |

**물질 혼동 0%도 성과가 아니라 구조가 강제한 값이다** — 근거를 CAS로 직접 조회하므로
제3물질 청크가 프롬프트에 들어올 경로 자체가 없다.

집계 스크립트는 [`scripts/6_eval/summarize_cameo_full.py`](../scripts/6_eval/summarize_cameo_full.py)이고
**지표 정의의 단일 출처는 그 docstring**이다. 재현:

```bash
python scripts/6_eval/summarize_cameo_full.py --gen results/generation_cameo_full_pair_v8b.jsonl --eval results/eval_cameo_full_pair_v8b.jsonl
```

## 4. 남은 결함 — Caution 칸

판정줄은 항상 맞다. 문제는 **본문 서술의 강도**이고, 전부 Caution 행에 몰려 있다.

**v7 (앱 경로)** — matrix × judge 재분류

| matrix \ judge | Compatible | Caution | Incompatible |
|---|---:|---:|---:|
| Compatible (745) | 732 | 11 | 0 |
| **Caution (745)** | 25 | 623 | **84** |
| Incompatible (750) | 11 | 1 | 734 |

**v8b (structured)**

| matrix \ judge | Compatible | Caution | Incompatible |
|---|---:|---:|---:|
| Compatible (745) | 718 | 13 | 5 |
| **Caution (745)** | **70** | 605 | 54 |
| Incompatible (750) | 14 | 1 | 733 |

**두 버전의 실패 방향이 반대다.** v7은 Caution을 실제보다 세게 읽고(84건),
v8b는 약하게 읽는 쪽이 더 많다(70건). 안전 관점에서 더 위험한 건 약하게 읽는 쪽이다 —
위험한 조합을 Compatible로 읽은 건수가 v7은 36건(11+25), v8b는 84건(14+70)이다.

이 칸을 겨냥해 프롬프트를 개정한 v9는 사전 등록한 채택 기준 4개 중 2개를 통과하지 못해
폐기했다(600건 짝지은 비교에서 전체 일치 87.2→86.5%, Caution 82.2→80.0%). 경위:
[`archive/.../_v9_regression/FINDING.md`](../archive/2026-08-29_generation_prompt_history/_v9_regression/FINDING.md).

그 밖의 잔여 결함:

- **faithful 잔여 실패** — 그룹 분류를 확인된 반응처럼 단정하는 패턴. CAMEO reason은
  "두 물질이 속한 반응성 그룹끼리의 분류적 특성"인데 답변이 "이 두 물질이 실제로
  반응한다"로 서술하는 경우다. 프롬프트 규칙 `[3-1]`이 이걸 겨냥하지만 완전히 없애지는
  못했다.
- **evidence precision이 낮다**(0.44~0.46) — 두 물질의 §2·§10을 전부 넣고 그중 일부만
  인용하기 때문이며, recall(0.86~0.96)이 높은 것과 짝을 이룬다.

## 5. 채점 구조

`src/eval_generation.py`가 두 갈래로 채점한다.

- **규칙 기반**(LLM 호출 없음): `abstained`(고정 문구 매칭), `cited_chunk_ids`,
  `evidence_precision` / `evidence_recall`, `substance_confused`
- **LLM Judge**(짧은 분류 호출 1회): `predicted_verdict`, `faithful`, `unsupported_claims`

`answer_correct = predicted_verdict == matrix_verdict`(Abstain은 분모에서 제외).

**judge에 넘기는 근거에는 MSDS 청크뿐 아니라 CAMEO 컨텍스트도 합성 청크
(`__cameo_context__`)로 포함된다.** 생성기가 본 컨텍스트와 채점기가 보는 근거가 어긋나면
정당한 CAMEO 인용이 "근거 없는 주장"으로 오탐되기 때문이다.

세대별 프롬프트 산출물과 폐기 사유는
[`archive/2026-08-29_generation_prompt_history/NOTES.md`](../archive/2026-08-29_generation_prompt_history/NOTES.md),
개발 경위는 [`PROJECT_LOG.md`](PROJECT_LOG.md).
