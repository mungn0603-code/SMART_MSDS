# PHASE 5 — RAG Corpus Synchronization & Retrieval Validation: 실행계획 + 진행상황

**작성일**: 2026-08-08
**목적**: ①~⑨ 전 과정을 재현 가능한 방식으로 명세하고, 그중 빠르고 안전한 단계(①~③)는
이번 세션에서 실제로 실행·검증했다. 나머지(④ 임베딩/색인 재구축부터)는 소요시간이
크고(추정 2시간 안팎) 이 프로젝트 자체 문서(`HANDOFF.md` §5)가 이미 반복 세그폴트를
경고한 리소스 집약 단계라, **실행 커맨드까지 전부 준비해두고 실행 여부만 확인받는다.**

**원칙 재확인**: `undergrad_target_chemicals.csv`(원본 선정 CSV)는 이번 PHASE 5에서도
수정하지 않았다. `reactivity_reference.db`는 **수정했다** — 단 `rag_chunks`(청크
캐시, 언제든 `pipeline.py` 재실행으로 재생성 가능)와 신규 테이블
`rag_corpus_membership`(코퍼스 정의 매핑, 마찬가지로 CSV에서 재생성 가능)뿐이다.
`chemicals`/`chemical_group_membership`/`msds_sections` 등 원본 수집 데이터는
건드리지 않았다.

---

## 0. 왜 "지금 바로 pipeline.py 재실행"이 아니라 먼저 명세인가 — 실제로 발견한 4개 blocker

착수 전 조사에서 코드를 직접 읽고 실측한 결과, 사용자가 우려한 그대로 **naive하게
바로 실행했으면 전부 걸렸을 4개의 실제 문제**를 찾았다(순서대로 발견·해결):

| # | 문제 | 실측 근거 | 해결 |
|---|---|---|---|
| 1 | `pipeline.py`는 애초에 CSV를 읽지 않는다 — `msds_sections` 테이블 전체를 그대로 청킹한다 | 코드 직독(`build_chunks`가 `select ... from msds_sections`만 함, CSV 무관) | `--target-csv` 옵션 신설(§2) |
| 2 | `msds_sections`에 `chemicals` 테이블과 매핑 안 되는 고아 CAS(`497-19-8`, UREA CAS 오류 잔재)가 있어 `ref[cas]` 조회가 `KeyError`로 즉시 죽는다 | `chemicals` 테이블에 `497-19-8` 없음을 재확인(Phase1에서 이미 발견했던 것과 동일 건) | `ref`에 없는 CAS는 건너뛰고 경고만 출력하도록 방어 처리 |
| 3 | `msds_sections`에는 선정 CSV(475행) 밖의 물질도 40종 섞여 있다 — PHASE 2에서 backfill 후보 KOSHA 조회할 때 `msds_chem_id_cache`/`msds_sections`에 결과가 쌓였기 때문(선정과는 무관한 "조사 기록") | `msds_sections` full-4-section distinct CAS = 466, 그중 선정 CSV(475행) 밖 40종 실측 확인 | `--target-csv`로 걸러짐(문제 1의 해결책이 이것도 해결) |
| 4 | **가장 중요**: `rag_chunks.chunk_id`(`sec::{cas}::{section}`)는 CAS+섹션으로만 정해지는 content-addressed 키라 "코퍼스 정의"와 무관하다. 426 대상과 259(proposed final) 대상을 각각 다른 `version` 태그로 두 번 실행했더니, 두 코퍼스가 공유하는 CAS의 청크가 같은 `chunk_id`라서 `INSERT OR REPLACE`가 나중 실행의 `version`으로 덮어써버렸다 — **`rag_chunks.version`은 코퍼스 멤버십 필터로 못 쓴다** | 직접 재현·확인: `version='...-426'`로 조회하면 259와 안 겹치는 181종만 남고(63 REMOVE_CONFIRMED+118 MERGE_REDUNDANT), 나머지는 전부 `259proposed`로 덮어써짐 | 별도 테이블 `rag_corpus_membership(corpus_tag, cas_number)` 신설 — 청크 내용과 무관하게 "이 코퍼스엔 이 CAS들이 속한다"만 관리하고, `retrieval.py load_corpus(corpus_tag=...)`가 이걸로 필터링(§3) |

4번은 이번 조사에서 실제로 실행해보지 않았으면 몰랐을 문제였다 — "명세부터"라는
사용자 지시가 정확히 옳았다.

---

## 1. proposed_final 259 확정본 (①)

이미 PHASE 4 산출물로 존재한다:
`01_collection/undergrad_target_chemicals_proposed_final_2026-08-08.csv`(259행).
이번 PHASE 5에서는 이걸 **그대로** RAG 재구축 입력으로 쓴다 — 재생성하지 않았다.
(주의: 이건 여전히 "제안"이다. REVIEW_REQUIRED 15 + REVIEW 62 = 77종이 보수적으로
포함된 상태 — §8에서 이 77종의 영향을 실측으로 분석하는 게 이번 Phase 5의 목적 중
하나.)

---

## 2. pipeline.py 수정 + 실행 (②) — 완료

**코드 변경**(`04_rag_agent/pipeline.py`):
- `--target-csv PATH`: 지정한 CSV의 `cas_number`만 청킹 대상으로 제한(생략 시 기존
  동작 그대로 — 하위호환)
- `--version TAG`: `rag_chunks.version`에 기록할 태그(코퍼스별로 다르게 지정 —
  단, §0-4에서 밝혔듯 이것만으로 코퍼스를 완전히 분리 관리할 수는 없다는 것도 함께
  발견)
- `chemicals` 테이블에 없는 CAS는 청킹에서 제외하고 경고 출력(크래시 대신)

**실행 결과** (둘 다 `--no-markdown`으로 실행 — 마크다운 파일은 최종 확정 코퍼스에
대해서만 나중에 별도 생성):

```bash
python pipeline.py --no-markdown --target-csv ..\01_collection\undergrad_target_chemicals.csv \
    --version stage4-v2-chunk-1-426
python pipeline.py --no-markdown --target-csv ..\01_collection\undergrad_target_chemicals_proposed_final_2026-08-08.csv \
    --version stage4-v2-chunk-1-259proposed
```

| 코퍼스 | 물질 수 | section 청크 | item 청크 |
|---|---:|---:|---:|
| 426(baseline) | 426 | 1,745 | 15,966 |
| 259(proposed final) | 259 | 1,063 | 9,710 |

두 실행 모두 크래시 없음, 대상 밖 CAS(40종/207종) 정상 제외 로그 출력 확인.

---

## 3. rag_chunks / rag_corpus_membership 검증 (③) — 완료

§0-4 문제 때문에 `rag_chunks.version`으로는 코퍼스를 못 나눈다는 걸 확인한 뒤,
아래 테이블을 신설해 CAS 멤버십으로 관리하도록 전환했다:

```sql
CREATE TABLE rag_corpus_membership (
    corpus_tag  TEXT NOT NULL,
    cas_number  TEXT NOT NULL,
    PRIMARY KEY (corpus_tag, cas_number)
);
```

`corpus_tag='426'`에 426종, `corpus_tag='259proposed'`에 259종 적재 완료. **검증**:
`rag_chunks`에 두 코퍼스 전 CAS의 청크가 실제로 존재하는지 대조 — 누락 0건(둘 다).

`retrieval.py`도 함께 수정: `load_corpus(granularity, corpus_tag=...)`가 이제
`rag_corpus_membership`으로 조인해서 필터링한다(기존 `version` 파라미터는 제거하고
`corpus_tag`로 교체 — 더 신뢰할 수 있는 메커니즘으로). **실측 재확인**:

```
426          section chunks=1745  distinct_cas=426
426          item    chunks=15966 distinct_cas=426
259proposed  section chunks=1063  distinct_cas=259
259proposed  item    chunks=9710  distinct_cas=259
```

`pipeline.py` 실행 직후 리포트와 정확히 일치 — `chunk_id` 충돌 문제를 완전히 우회해
정확한 코퍼스 재구성이 가능함을 확인했다.

`embed_corpus`/`build_bm25`도 `corpus_tag` 파라미터를 받아 캐시 파일명을
`emb_{model}_{gran}_{corpus_tag}.npy` / `bm25_{gran}_{corpus_tag}.pkl`로 분리하도록
수정 완료(생략 시 기존 파일명 — 하위호환). 이러면 두 코퍼스의 임베딩을 서로 지우지
않고 동시에 캐시해둘 수 있다.

**ponytail 메모**: 426/259 코퍼스가 공유하는 245종(청크 기준 약 1,000개 section
청크)은 두 코퍼스 각각의 `corpus_tag` 캐시에 중복 임베딩된다(내용이 같아도 배열
위치·캐시 키가 코퍼스 단위라서). chunk_id 키로 임베딩을 공유 캐시하는 최적화는
하지 않았다 — add when: 임베딩 재실행 비용이 반복적으로 문제가 될 때.

---

## 4. 남은 단계 — 실행 커맨드는 준비됐으나 미실행 (④~⑨)

### ④ 임베딩/색인 재구축 — 실행 결과 및 known operational limitation

**중요 발견 — Segfault + 캐시 기반 복구 절차(재현 확인됨)**: 259proposed 코퍼스
첫 실행이 정확히 `HANDOFF.md` §0-1이 경고한 패턴대로 **종료 코드 139(SIGSEGV)로
죽었다.** 로그를 그대로 대조한 결과:

1. 문서 임베딩(1,063개 section 청크, `SentenceTransformer` 1차 로드) 완료 —
   `emb_bge-m3-ko_section_259proposed.npy` **디스크에 저장됨**(25분 45초 소요)
2. 질의 임베딩(1,785개, `SentenceTransformer` 2차 로드) 완료 —
   `q_bge-m3-ko_pair_q_5d1469a1aa.npy` **디스크에 저장됨**(5분 1초 소요)
3. `build_bm25` 완료 — `bm25_section_s210_259proposed.pkl` **디스크에 저장됨**
4. 이후(FAISS 인덱스 빌드 / dense·bm25·hybrid 랭킹 / 레이턴시 측정을 위한
   `query_encode_ms`의 3차 `SentenceTransformer` 로드 / `metrics()` / `save()`
   구간 어딘가)에서 세그폴트 — 표준출력 로그가 그 지점에서 끊김, 후속 라인 없음

**세 단계 캐시가 크래시 이전에 전부 디스크로 flush됐다는 게 핵심**이다 — `.npy`/
`.pkl` 저장은 각 단계 완료 직후 즉시 일어나므로, 크래시가 그 이후(랭킹·채점·저장
단계)에서 나도 비싼 연산 결과는 안전하다. **동일 커맨드를 그대로 재실행**하니
`embed_corpus`/`embed_queries`/`build_bm25`가 전부 캐시 히트로 즉시 반환되고,
남은 랭킹·채점·저장만 수행해 **수 초 안에 정상 종료**했다(exit code 0).

**결론 — `run_ab.py`의 known operational limitation으로 기록**:
> `run_ab.py embedding` 실행 중 하나의 프로세스 안에서 `SentenceTransformer`를
> 여러 번(문서 임베딩·질의 임베딩·`query_encode_ms` 레이턴시 측정용) 로드하면,
> Windows 환경에서 torch/FAISS/kiwipiepy 네이티브 라이브러리 자원이 완전히
> 해제되지 않아 세그폴트가 발생할 수 있다(원인은 `HANDOFF.md` §0-1이 이미 추정한
> 것과 동일 계열 — 근본 원인은 여전히 미확정). **표준 복구 절차**: 크래시 나면
> ① `04_rag_agent/index/` 안에 해당 코퍼스/모델 조합의 `emb_*.npy`,
> `q_*_<hash>.npy`, `bm25_*.pkl`가 저장됐는지 확인 → ② 저장돼 있으면 동일 커맨드를
> **그대로 재실행**(캐시 히트로 수 초~수 분 내 완료) → ③ 저장 안 됐으면(문서
> 임베딩 도중 크래시 등 더 이른 단계) 처음부터 재시도, 필요시 프로세스 간 텀을 두거나
> 재부팅 후 1회 실행(`HANDOFF.md` §0-1 권고와 동일). **캐시가 있는 한 재시도 비용은
> 거의 0에 가깝다** — 이번 실측으로 "세그폴트 = 처음부터 다시"가 아님을 확인.

**실행 결과(259proposed, 재시도로 완료)**:

| retriever | n_queries | dropped | Recall@10 | Recall@5 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| dense | 1,785 | 130 | 0.8586 | 0.7724 | 0.9362 | 0.8370 |
| bm25 | 1,785 | 130 | 0.7372 | 0.6528 | 0.8436 | 0.7173 |
| hybrid | 1,785 | 130 | **0.8960** | 0.7919 | 0.9309 | 0.8572 |

426 코퍼스는 캐시가 없어(처음 청킹되는 코퍼스라 임베딩도 처음부터) 같은 방식으로
백그라운드 실행 중 — 완료 즉시 §6 비교로 넘어간다. **주의(사용자 지시 반영)**:
`Recall@10 0.896`(259) 하나만 보고 "426종을 259종으로 줄여도 성능이 유지된다"고
결론 내리지 않는다 — 259쪽은 애초에 130개 어려운/불리한 질의가 빠진 상태의 점수라
426의 전체(1,915건, dropped=0) 결과와 **모수 자체가 다르다**. 아래 §6(공통
1,785건 paired evaluation + strict 환산)을 거쳐야 공정한 비교가 된다.

### ④ 원래 실행 전 프리플라이트 메모(실행 전 작성, 그대로 보존)

**환경 프리플라이트(실측 완료, 문제 없음)**:
- `torch`/`sentence_transformers`/`faiss`/`kiwipiepy` 전부 import 성공
- 임베딩 모델 `dragonkue/BGE-m3-ko`가 이미 로컬 캐시에 있음(`~/.cache/huggingface/hub/models--dragonkue--BGE-m3-ko`)
  → `HF_HUB_OFFLINE=1`로 네트워크·SSL 이슈 자체를 회피 가능(`HANDOFF.md` §5의 SSL
  인증서 문제는 "신규 다운로드" 시나리오라 캐시 히트면 발생 안 함)
- `MSDS_TORCH_THREADS` 미설정 상태 — 설정 안 하면 8코어 중 2코어만 써서 1.45배
  느려짐(`HANDOFF.md` §5 실측)

**비용 추정(과거 실측 기반, `HANDOFF.md` §5: section 청크 2.61초/청크)**:

| 코퍼스 | section 청크 | 추정 소요(2.61s/청크) |
|---|---:|---:|
| 426 | 1,745 | 약 76분 |
| 259proposed | 1,063 | 약 46분 |
| **둘 다** | 2,808(중복 임베딩 포함) | **약 122분(2시간 안팎)** |

item 청크(더 짧아 0.637초/청크, `HANDOFF.md` §5)까지 하면 추가로
(15,966+9,710)×0.637s ≈ 273분이 더 필요하나, **§2.2(기존 결정) 원칙대로 item
granularity는 이미 폐기됐으므로(§2.2 "item 단위 청킹 폐기") item 임베딩은
이번 재구축에서 하지 않는다** — section만 대상.

**실행 커맨드(준비 완료, 미실행)**:
```bash
# 8스레드 고정 + 캐시 모델만 사용(네트워크 회피)
export MSDS_TORCH_THREADS=8
export HF_HUB_OFFLINE=1

python run_ab.py embedding --models bge-m3-ko --granularity section --task pair \
    --sections 2,10 --corpus-tag 426
python run_ab.py embedding --models bge-m3-ko --granularity section --task pair \
    --sections 2,10 --corpus-tag 259proposed
```
(`run_ab.py`에 `--corpus-tag`를 넘기면 `load_corpus`/`embed_corpus`/`build_bm25`에
그대로 전달되도록 하는 소규모 배선 작업이 필요 — 현재 `run_ab.py`는 아직 이 인자를
모른다. §0-4에서 만든 `corpus_tag` 파라미터를 `retrieval.py`까지는 배선했지만
`run_ab.py` CLI까지는 이번 세션에서 안 했다. **다음 실행 전 마지막 남은 배선**.)

**권고**: 이 단계는 확실히 실행은 필요하지만, 2시간 안팎 CPU 연산이고 이 프로젝트
문서 스스로 반복 세그폴트를 기록해뒀다(`HANDOFF.md` §0-1 "같은 세션에서 run_ab.py를
반복 실행하면 재현되는 Segmentation Fault... 재실행이 필요하면 매 실행 사이 텀을
두거나 재부팅 후 1회씩 실행 권장"). **한 번에 몰아서 돌리기보다 코퍼스 하나씩,
실행 사이 텀을 두고 진행할 것을 권고**한다. 사용자 확인 후 착수.

### ⑤ independent eval 50건 실행
`04_rag_agent/evalset/independent_eval_prototype_2026-08-08.jsonl` 이미 존재(PHASE
4-F). ④가 끝나면 `retrieval_indexed=True`(현재 시점 49건 중 2건뿐 — 259proposed
색인 완료 후 재계산하면 크게 늘어날 것으로 예상되나 실측 전엔 단정하지 않는다)
쿼리부터 Hit@1/Hit@3/MRR/Recall@K 채점.

### ⑥ 426 vs 259 retrieval 비교 — 5단계로 세분화(사용자 지시, 2026-08-08 추가)

`Recall@10 0.896`(259, 130건 제외 후 점수) 하나만 보고 "426종을 259종으로 줄여도
성능이 유지된다"고 결론 내리지 않는다 — 모수가 다른 두 숫자를 비교하는 것이기
때문이다. 아래 5단계로 나눠 공정하게 비교한다(스크립트:
`04_rag_agent/phase5_426_vs_259_analysis.py`, 캐시된 임베딩/BM25 재사용 — 재계산
없음, 수 분 내 완료):

1. **426 전체 평가**: 1,915건 전체(dropped=0) — 이미 완료(백그라운드 작업, §4 표).
2. **259 전체 평가**: 1,785건(dropped=130) — 완료(§4 표).
3. **공통 1,785건으로 426 vs 259 paired evaluation**: 259에서 유효했던 정확히 같은
   1,785개 질의만 골라 426 코퍼스에서도 다시 채점 — 코퍼스 차이만 격리한 apples-to-apples
   비교. (426의 자연 valid-query 집합이 259의 그것을 완전히 포함하는지도 검증 —
   259가 424에 없는 신규 ADD_CONFIRMED 14종을 포함하지만 `gold_pair.jsonl`
   자체가 Wave1 파생이라 그 14종을 참조하는 질의가 원천적으로 없으므로 포함
   관계가 성립할 것으로 예상 — 실측으로 확인.)
4. **130건(REMOVE_CONFIRMED/MERGE_REDUNDANT 관련) 영향 분석**: 259에서 빠진
   130건을 426 코퍼스 안에서만 따로 채점 — "제거된 물질들이 실제로는 검색을 잘
   해내고 있던 질의였는가, 원래도 성능이 나빴는가"를 실측으로 확인. 전자면 제거의
   실질 비용이 있는 것이고, 후자면 제거가 손해가 아니라는 근거가 된다.
5. **strict vs selection-aware 평가**: `selection-aware`는 §2의 259 결과 그대로
   (1,785건 모수). `strict`는 259가 아예 답할 수 없는 130건을 "완전 실패(모든
   지표 0점)"로 접어 넣어 426과 같은 1,915건 모수로 환산한 값 —
   `strict_metric = selection_aware_metric × (1785/1915)`. 이게 "259종 코퍼스로
   축소했을 때 사용자가 원래 하던 질문 전체에 대해 실제로 얼마나 잘 답하는가"에
   더 가까운 현실적 지표다. **이번 Phase5 결론은 selection-aware가 아니라 strict
   수치를 주 지표로 인용한다.**

426 백그라운드 작업이 끝나는 대로 실행하며, 결과는 이 문서 §6-결과에 추가한다.

### ⑦ coverage + retrieval 동시 평가
PHASE 4-E의 coverage 지표(§10/그룹/risk-pair)와 ⑥의 retrieval 지표를 한 표에
나란히 놓고 "선정 개선이 실제 검색 성능과 함께 갔는가"를 처음으로 직접 확인.

### ⑧ unresolved 77종 영향 분석
REVIEW_REQUIRED(15)+REVIEW(59+3)=77종을 **뺀** 세 번째 코퍼스(182종)를 하나 더
만들어(`corpus_tag=182confirmed`, 같은 방식으로 CAS 목록만 새로 만들면 됨 — 이미
있는 `chemical_phase4_adjudication_2026-08-08.csv`에서 걸러내면 즉시 가능) ④~⑥을
한 번 더 돌리면, 77종이 retrieval 지표에 실제로 기여하는지(있으나 마나 한지)를
추측이 아니라 실측으로 답할 수 있다. 이게 77종 중 어느 게 진짜 필요한지 판단하는
가장 직접적인 근거가 될 것.

### ⑨ Final Chemical Dataset 결정
④~⑧ 결과를 사람이 검토한 뒤에만 `undergrad_target_chemicals.csv`에 실제 반영—
이번 세션 범위 밖(반복 확인).

---

## 5. 지금 상태 요약

| 단계 | 상태 |
|---|---|
| ① proposed_final 259 확정본 | 완료(PHASE 4 산출물 재사용) |
| ② pipeline.py 재구축 | **완료** — 426/259 두 코퍼스 청킹 성공 |
| ③ rag_chunks 검증 | **완료** — corpus_membership 기반으로 정확성 검증 |
| ④ 임베딩/색인 재구축 | **완료** — 426/259proposed 둘 다 완료(각각 세그폴트 1회 → 캐시 재시도로 성공, §4 표) |
| ⑤ independent eval 50건 | 미실행(다음 세션 과제) |
| ⑥ 426 vs 259 5단계 비교 | **완료** — [`docs/phase5_426_vs_259_results_2026-08-08.md`](phase5_426_vs_259_results_2026-08-08.md). **핵심 결론: strict 환산 시 259가 426보다 모든 지표(Recall@10/MRR/nDCG@10/Hit@10)에서 낮음 — "축소해도 성능 유지" 주장은 기각** |
| ⑦~⑨ | 미실행(다음 세션 과제 — §6 결과를 Phase 4 adjudication 규칙에 되먹임할지부터 검토) |

**결론**: "지금 바로 pipeline.py를 재실행"했다면 §0의 4개 문제 중 최소 2개(고아
CAS 크래시, 코퍼스 뒤섞임)에 그대로 부딪혔을 것이다. 명세를 먼저 한 덕에 이 세션
안에서 그 문제들을 실제로 재현·해결하고 ①~③까지 검증된 상태로 끝냈다 — ④부터는
비용이 다른 종류(수 시간 CPU 연산 + 이 프로젝트 자체가 기록한 세그폴트 이력)라
별도 확인 후 진행이 합리적이다.
