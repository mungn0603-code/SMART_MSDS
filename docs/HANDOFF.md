# HANDOFF — 지금 상태 그대로 이어받기

이 문서는 **현재 시점의 상태**만 적는다. 어떻게 여기까지 왔는지는
[`PROJECT_LOG.md`](PROJECT_LOG.md), 폐기된 것의 사유는 `archive/*/NOTES.md`에 있다.

## 1. 이 시스템이 하는 일

사용자가 화학물질을 2종 이상 고르면 **함께 보관해도 되는지 판정하고, 왜 그런지 MSDS
원문 근거로 설명한다.** 판정은 CAMEO 반응성 그룹 매트릭스가 결정론적으로 내리고, LLM은
그 판정을 재판단하지 않는다. 근거가 없으면 Abstain한다.

전체 흐름은 [`PIPELINE.md`](PIPELINE.md)가 정본이다.

## 2. 지금 되는 것 / 안 되는 것

| | 상태 |
|---|---|
| 물질 선택 | Registry 237종 중 KOSHA 등재 **198종** |
| 쌍·N종 판정 | 됨. 198종 중 CAMEO 매핑이 있는 **173종** 사이에서 판정이 나오고, 나머지 25종이 끼면 Abstain |
| MSDS 상세정보 | 198종 전부 §2/§3/§9/§10 |
| 설명 생성 | 됨(Upstage `solar-pro3`). 근거는 CAS 직접조회 §2·§10 |
| 검색 계층 | 구현·측정 완료. **서비스 경로에서는 쓰지 않는다**(의도된 선택, [`RETRIEVAL.md`](RETRIEVAL.md) 5절) |
| 리랭커 | 미실행(질의 분해로 Hit@10 1.0000 달성) |

## 3. 핵심 파일

| 파일 | 왜 중요한가 |
|---|---|
| `app/streamlit_app.py` | 서비스 진입점. `explain()` → `pair_context()`가 근거 수집 경로다 |
| `src/compatibility_engine.py` | **판정.** `judge_pair_by_cas` / `judge_combination_by_cas` |
| `src/cameo_group_lookup.py` | CAS 쌍 → CAMEO 그룹 → 판정+사유. 프롬프트에 넣는 "정답" 소스 |
| `scripts/5_generation/run_cameo_context_pilot.py` | **프롬프트 정의 파일.** 앱도 여기서 가져간다 |
| `src/llm.py` | 전 파이프라인의 유일한 LLM 호출 경로(재시도 포함) |
| `data/reactivity_reference.db` | 진실원본. 앱이 읽는 데이터 파일은 이것 하나다 |

파일 전체 목록은 [`FILE_GUIDE.md`](FILE_GUIDE.md).

## 4. 데이터 현황

| 항목 | 값 | 소유 |
|---|---:|---|
| Registry | 237종 | `substance_registry` |
| KOSHA 등재 | 198종 | `msds_chem_id_cache` |
| 판정까지 가능 | 173종 | `substance_status.service_eligible` |
| 수집된 MSDS | 534종 × 4섹션 | `msds_sections` |
| 서비스 코퍼스 | 173종 / §2·§10 371청크 | `rag_corpus_membership(corpus_tag='service')` |
| CAMEO | 68그룹 / 2,278쌍 | `reactivity_groups`, `compatibility_pairs` |

> **함정: "173종"이 두 개다.** `corpus_tag='service'` 173종과 구 평가 코퍼스
> `corpus_tag='173'` 173종은 크기만 같고 **84종만 겹치는 다른 집합**이다. 구 코퍼스는
> 과거 지표 재현용으로만 남아 있다.

## 5. 현재 지표

| 계층 | 값 | 조건 |
|---|---|---|
| Retrieval | Recall@10 0.9888 · Hit@10 1.0000 · MRR 0.9581 · nDCG@10 0.9547 | service 173종, 2,240질의, evidence 기준, 질의 분해 |
| Generation (v7, 앱 경로) | 정답률(judge) 94.0% · faithful 97.5% · 물질혼동 0.0% | 2,240건 전수, `--context pair` |
| Generation (v8b, structured) | 정답률(judge) 92.9% · faithful 92.9% · 물질혼동 0.0% · 생성 4.2초 | 같음 |

정의와 주의사항은 [`RETRIEVAL.md`](RETRIEVAL.md) · [`GENERATION.md`](GENERATION.md).
**Retrieval 지표는 검색 계층의 값이지 앱 성능이 아니다.**

## 6. 환경과 키

`.env`에 아래를 넣는다(파일은 `.gitignore` 대상, 키 원문은 로그·출력 어디에도 남기지 않는다).

```
UPSTAGE_API_KEY=...     # Generation + Judge
KOSHA_SERVICE_KEY=...   # MSDS 수집 시에만 필요
```

이름 목록은 `.env.example`에 값 없이 있다.

권장 환경변수:

```bash
export SSL_CERT_FILE="$HOME/.cache/win_ca_bundle.pem"   # 아래 함정 표 참조
export MSDS_TORCH_THREADS=8                              # 미설정 시 실효 2코어만 쓴다
export HF_HUB_OFFLINE=1                                  # 캐시된 모델만 쓸 때
```

연결 확인: `python src/llm.py --check`
앱 자가검증(LLM 없이): `python app/streamlit_app.py --check`

## 7. 알려진 함정

| 문제 | 대응 |
|---|---|
| **`--help`를 붙여도 본문이 실행되는 스크립트가 6개 있다** | argparse나 `__main__` 가드가 없다. 특히 `scripts/3_corpus/seed_reactivity_reference.py`는 **실행하면 DB를 재생성한다.** 경로 확인은 실행이 아니라 `python -m compileall`과 `grep`으로 한다. 목록은 [`FILE_GUIDE.md`](FILE_GUIDE.md) |
| HF 모델 다운로드 SSL 실패 | 다운로드 라이브러리가 certifi만 보고 Windows 루트 인증서를 못 찾는다. Windows 인증서 저장소를 certifi와 합친 번들을 만들어 `SSL_CERT_FILE`로 지정한다. **검증을 끄지 않는다** |
| torch가 8코어 중 2코어만 씀 | `MSDS_TORCH_THREADS=8` |
| 임베딩 배치를 키우면 더 느림 | 배치 32가 배치 8보다 2배 느리다. **배치 8 유지** |
| 수집 스크립트 2개 동시 실행 시 `database is locked` | 수집기의 DB 연결에 대기시간 120초를 준다 |
| `run_cameo_full.py`를 `--tag` 없이 재실행 | `results/generation_cameo_full.jsonl` / `eval_cameo_full.jsonl`이 **새로** 생긴다. 기존 산출물과 다른 파일이다 |
| 리랭커 모델 크기 표기 | `bge-reranker-v2-m3`가 2.2GB(568M), `bge-reranker-base`가 1.2GB(278M)다. 이름과 크기의 직관이 반대이므로 도입 시 주의 |

## 8. 남은 작업

- **Caution 칸의 본문 서술** — 판정줄은 항상 맞지만 본문 강도가 어긋난다. v7은 세게,
  v8b는 약하게 읽는 쪽이 많다. 안전 관점에서 문제가 되는 건 약하게 읽는 방향이다
  ([`GENERATION.md`](GENERATION.md) 4절). v9 개정안은 채택 기준 미달로 폐기했다
- **faithful 잔여 실패** — 그룹 분류를 확인된 반응처럼 단정하는 패턴
- **CAMEO 매핑 25종 공백** — 원천에 데이터시트가 없음을 두 경로로 확인해 **판정 가능
  쌍 76.3%를 현재 coverage로 확정**했다. 목표는 100%가 아니다([`REGISTRY.md`](REGISTRY.md) 6절)
- **3종 이상 조합의 검색 실측 없음** — 판정은 되지만 검색 지표는 쌍 단위까지다
- **평가셋 `REVIEW_REQUIRED` 350건(69쌍)** — §10 청크가 정형문구인지 자동 판정이 안 되는
  경우다. 억지로 해석하지 않기로 하고 미해결로 둔다(gold_evidence에는 포함되지 않으므로
  지표에는 영향이 없다)
- **§10 "분리 그룹" 파싱 결함 4종** — `sec::100-64-1::10` · `sec::7440-32-6::10` ·
  `sec::7440-33-7::10` · `sec::7723-14-0::10`. 평가셋에 `PARSING_DEFECT`로 표시돼 있다
- **원본 리스트 전체의 안전성 재검증 미완** — 안전필터가 대체 후보군에만 적용됐다
- **리랭커 미실행** — 코퍼스나 정답 정의가 바뀌면 재검토

## 9. 손대면 안 되는 것

1. **판정은 CAMEO가 내리고 LLM은 재판단하지 않는다.** 판정줄·결론 문장을 모델이 쓰게
   되돌리지 않는다. `tests/test_run_cameo_resume.py`가 이걸 막는다
2. **판정만 단독으로 제시하지 않는다.** MSDS 근거를 함께 붙이고, 못 붙이면 Abstain
3. **확정 지표를 낸 재현 경로**(`run_ab.py` / `freeze_retrieval.py` / `run_cameo_full.py`)의
   동작을 바꾸지 않는다
4. **구 평가 코퍼스(`corpus_tag='173'`)의 질의 이름을 바꾸지 않는다.** 한 글자만 바뀌어도
   그 코퍼스로 낸 지표가 무효가 된다
5. **결과 파일을 덮어쓰지 않는다.** 재실행분은 `--tag`나 날짜를 붙여 새 파일로 남긴다
6. **서비스키·API키 원문을 코드·로그·응답에 노출하지 않는다**

## 10. 컨텍스트를 잃었을 때

| 알고 싶은 것 | 볼 곳 |
|---|---|
| 전체가 어떻게 흘러가나 | [`PIPELINE.md`](PIPELINE.md) |
| 어떤 물질을 다루나 | [`REGISTRY.md`](REGISTRY.md) |
| 데이터 원천은 무엇인가 | [`DATA.md`](DATA.md) |
| 검색·생성 지표 | [`RETRIEVAL.md`](RETRIEVAL.md) · [`GENERATION.md`](GENERATION.md) |
| 어느 파일이 무슨 일을 하나 | [`FILE_GUIDE.md`](FILE_GUIDE.md) |
| 어떤 수치가 어느 파일에서 나오나 | [`results/README.md`](../results/README.md) |
| 어떻게 여기까지 왔나 | [`PROJECT_LOG.md`](PROJECT_LOG.md) |

DB 구조는 문서 설명만 믿지 말고 `rag_chunks`·`msds_sections`·`substance_status`를 직접
조회해 확인한 뒤 작업한다.
