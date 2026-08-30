# 프로젝트 진행 로그 (일자별)

MSDS 위험성평가 자동화 프로젝트의 시작(2026-07-29)부터 현재까지 일자별 진행 기록.
**출처**: 각 세션에서 생성된 문서(`HANDOFF.md`, `HANDOFF_ARCHIVE.md`, `session_log_2026-08-06.md`,
`stage4_design_changes_2026-08-06.md`, `msds_risk_assessment_readme.md`)와 파일 생성
타임스탬프를 근거로 재구성. 문서에 명시되지 않은 세부 시각은 파일 시스템 타임스탬프로
보완했으며, 그 경우 "(파일 타임스탬프 기준)"으로 표기.

이 로그는 사실 기록이며 판단 근거의 상세 설명은 `decisions.md`를, 폐기/기각 파일의
상세 사유는 `archive/*/NOTES.md`를 참고.

---

## 2026-07-29 — 프로젝트 착수

- 문제 정의: KOSHA MSDS 데이터 기반 화학물질 반응성 위험 자동평가 시스템. 화공 도메인
  지식 + AI/RAG 엔지니어링 역량을 동시에 증명하는 포트폴리오 프로젝트로 설정.
- 5단계 파이프라인 스코프 확정(수집 → 분류 → 매트릭스 → RAG/Agent → 평가).
- 작업 도구 결정: Claude Code 전환을 논의했으나 **미채택** — 당시에는 채팅 + Desktop
  Commander 방식 유지로 결정(이 결정은 이후 08-06에 뒤집힘, `decisions.md` 참고).
- 매트릭스 "단독 최종 판정 근거 사용 금지" 원칙 최초 수립(EPA 원문 경고 계승).

## 2026-07-30 — 계획 문서 확정, 스키마 설계 시작

- `archive/superseded_docs/msds_risk_assessment_readme.md` 작성(10:57) — 이 시점까지의 유일한 기준 문서로
  선언, 기존 산출물 전부 폐기 후 재출발.
- 반응성 그룹 체계를 **CAMEO 68그룹**으로 확정(구 EPA-600/2-80-076 41그룹 폐기 — 41그룹은
  CAMEO가 68그룹으로 확장하기 전 구버전이었기 때문).
- 타겟 물질 스코프 **200~400종**으로 확정(전체 20,568종 대비 API quota 현실성).
- `Cameo_reactivity.csv` 확보(11:34), `02_classification/schema.sql` 작성(12:09) — DB
  스키마 초안.
- **양립성 쌍 수 정정**: 초기 가정 2,346쌍(68×69/2, 자기반응 포함) → CAMEO 원자료가
  자기반응(대각선) 데이터를 제공하지 않는다는 사실 확인 → **2,278쌍**(68×67/2, 오프대각
  전용)으로 정정. `self_reactivity` 테이블을 별도 분리해 관리하기로 결정.

## 2026-07-31 — CAMEO 데이터 수집, 시드 스크립트

- `CRW_Data_Export_reactivity map.xlsx` 확보(11:01, CRW 4.0 원본 매트릭스 후보).
- `01_collection/scrape_cameo_chemical_groups.py` 작성·실행(16:06) — CAMEO 웹 스크레이핑.
- `cameo_chemical_groups.db`(16:18), `cas_reactive_group_mapping.csv`(16:19) 생성.
- `02_classification/seed_reactivity_reference.py`(17:10), `seed_self_reactivity.py`(17:12)
  작성 — 68그룹·2,278쌍 매트릭스와 자기반응 68행을 `reactivity_reference.db`에 시딩.

## 2026-08-01 — 스코프 논쟁 시작

- `02_classification/build_chemical_group_membership.py` 작성(23:19) — CAS↔CAMEO 그룹
  매핑 처리 결과 **3,386종 규모의 별도 풀**이 존재하게 됨.
- 이 풀의 존재로 "200종 유지 vs 3,386종 전체로 스코프 확대" 논쟁이 부상(08-04까지 지속).

## 2026-08-02 — 양립성 판정 엔진

- `03_compatibility/compatibility_engine.py` 작성(00:07).
- KOSHA 신규 서비스키 발급이 08-02 18:00까지 불가하다는 제약 확인(기존 발급 보유자는
  영향 없음).

## 2026-08-03 — 200종 타겟 리스트, CAS 불일치 발견

- `01_collection/build_undergrad_target_list.py` 작성(00:16) — CAMEO 68그룹을 학부
  실험 등장빈도로 HIGH/MED/LOW 3단계 티어링해 대표 200종을 자동 배분하는 로직.
- **커리큘럼 12종 CAS 불일치 발견**(00:34, `fix_missing_common_chemicals.py` 착수):
  에탄올·아세톤·헥산 등 학부 커리큘럼 30종 중 12종이 3,386종 풀에 CAS로 존재하지 않음.
  원인: CAMEO 스크레이핑이 "모체 화합물" 자체를 체계적으로 누락(유도체만 존재).

## 2026-08-04 — 스코프 확정, CAS 불일치 해결, 수집기 완성

- **스코프 논쟁 종결**: 200종(학부 커버리지 리스트) 유지로 최종 확정, 3,386종 전체
  확대안 미채택.
- **API quota 계산 정정**: 초기 계산(200~400종×4섹션=800~1,600콜)이 "CAS로 섹션 직접
  조회 가능"이라는 잘못된 가정에 근거했음을 확인 → 실제로는 `getChemList`로 chemId
  선행 조회가 필요 → **정확한 계산: 200종×(chemId조회 1콜+섹션4콜)=1,000콜**로 정정.
- **12종 CAS 불일치 해결**: `fix_missing_common_chemicals.py`(00:34)로 12종 전부 수동
  그룹배정·DB삽입 완료(`source='manual_classification_verified'`). 최종 구성:
  curated_curriculum 30 / pool_supplement 156 / pool_topup 14 = 200종, 67그룹 커버.
- `01_collection/test_kosha_msds_collector.py`(00:03), `kosha_msds_collector.py`(15:29)
  작성 — KOSHA MSDS 수집기 완성.
- 이 시점 핸드오프 스냅샷의 미해결 이슈로 "KOSHA 서비스키 미발급"이 기록됨 — 그러나
  실제로는 08-04~08-06 사이 키는 발급되어 `.env`에 설정된 상태였고, API 호출이
  계속 `HTTP 403 Forbidden`으로 실패하는 별개 문제였음이 이후 밝혀짐.

## 2026-08-05 — (기록 없음)

- 이 날짜로 명시적으로 남은 문서·파일 타임스탬프 없음. 403 원인 조사가 이 기간에
  이어졌을 가능성이 있으나 세션 기록으로 특정되지 않음.

## 2026-08-06 — Stage 1 완주 + Stage 4(RAG) 전체를 하루에 진행

이 프로젝트에서 가장 밀도가 높은 하루. 오전에 Stage 1(수집)을 마무리하고, 오후~저녁에
Stage 4(RAG) 설계부터 구현·실측까지 한 세션에서 완주했다.

### 오전 — KOSHA 403 해결, 200종 수집
- **403 원인 확정**: 서비스키가 마이페이지에서는 승인완료 상태였음에도 모든 호출이
  `resultCode=30 SERVICE_KEY_IS_NOT_REGISTERED_ERROR`로 실패. 로컬 인코딩 3방식 테스트 +
  data.go.kr 공식 Swagger 재현 테스트로 **로컬 코드 문제가 아니라 포털 측 계정-키 등록
  연동 버그**임을 확정. 사용자가 KOSHA(디지털계획부)에 직접 문의 → 조치 완료 → 동일
  키로 `resultCode=00` 정상 응답 확인.
- **1차 수집 실행**: 200종(섹션 2/3/9/10) 시도 → **168종 성공**(EAV 6,720행), 32종 미발견.
- **32종 분석**: 커리큘럼 30종은 100% 발견. 미발견 32종은 전부 CAMEO 67그룹 커버리지용
  보충물질(`pool_supplement`/`pool_topup`) — 군용폭약·단종농약 등 KOSHA 미등록 희귀물질.
- **대체 3라운드** (`backfill_group_replacements.py` 11:43 / `backfill_round2_safety_filter.py`
  11:49 / `backfill_round3_manual_picks.py` 11:56):
  - Round 1(KOSHA 등록여부만 확인): 30/32 성공했으나 재검증 결과 **석면(1A급 발암물질)·
    블레오미신(항암제)·안트랄린(치료제) 등 10건이 부적절**로 판명.
  - Round 2(GHS H-code + KOSHA 권고용도 자동필터 추가): 재대체했으나 **아프라톡신
    B1(최강 발암물질급)이 필터를 통과하는 사고 발생** — KOSHA 자체 데이터의 H-code가
    약하게(H361만) 등록되어 있었기 때문.
  - Round 3(수동 이름 검토): 최종 교정. 아프라톡신 B1→벤조인, 메톡시에틸수은
    염화물→크롬 카보닐, 티오디글리콜(CWC 전구물질)→메틸렌 블루 트리수화물로 교체.
  - **최종 198/200 KOSHA 데이터 확보**, 2종은 Abstain 유지(Diazonium Salts 그룹, 대체
    후보 3개 전부 KOSHA 미등록).
- **교훈 기록**: 단일 자동 안전판정(GHS H-code 하나)은 못 믿음 — 정부DB 자체 분류가
  부실한 경우 위험물질도 통과 가능. 용도필드+이름 직접 검토 병행 필요.
- `archive/superseded_docs/HANDOFF_ARCHIVE.md`(10:35), `archive/superseded_docs/session_log_2026-08-06.md`(12:07) 작성 —
  Stage 1 완주 및 과거 정정 이력 정리.

### 오후~저녁 — Stage 4(RAG) 설계부터 실측까지
- **설계 v1 → v2 전면 교체(같은 날)**: v1의 최상위 철학("기존 자산(KDIC) 재사용 우선")을
  버리고 v2("검색 성능 우선")로 전환. `archive/superseded_docs/stage4_design_principles_v2.md`(14:21)
  확정본 작성, v1은 `archive/design_docs/`로 보존.
- `04_rag_agent/pipeline.py` / `test_pipeline.py`(14:42) — 본문추출→Normalize→Chunk→
  Metadata 파이프라인. section 청크 805개 / item 청크 7,420개 생성.
- `evalset.py`(15:03) — 단일물질 평가셋(407건) 최초 작성.
- `retrieval.py`(15:12) — bge-m3-ko 임베딩 + FAISS + BM25(kiwipiepy) + RRF + 리랭커.
- **평가셋 전면 교체(설계 오류 정정)**: 제품 과제가 "물질 2종 이상의 조합"이라는
  사실이 뒤늦게 반영되어 `evalset_pairs.py`(15:35) 작성 — 그 최소 단위인 **쌍(2종)**
  으로 우선 검증. `gold_pair.jsonl` 369쌍(Incompatible 135/Caution 114/Compatible 120),
  `gold_pair_abstain.jsonl` 81쌍. 단일물질 평가셋은 부품 점검용(`--task fact`)으로 격하.
  N종(N≥3) 조합은 쌍 판정을 worst-case로 종합하는 설계까지만 되어있고 미구현
  (`archive/superseded_docs/decisions.md` §2.10).
- `run_ab.py`(16:40)로 실측 진행, 주요 발견:
  - **섹션 §2·§10 필터 적용(805→409청크)**: 정확도(Recall@10 +1.59%p, nDCG@10 +3.68%p)와
    속도(3.3배 단축)가 동시에 개선되는 순수 이득 확인.
  - **Hybrid vs Dense 충돌**: 같은 조건에서 hybrid가 7개 목표 중 6개, dense가 4개
    충족(Recall@10 hybrid 0.9005 > dense 0.8829). 그럼에도 **사용자 지시로 dense
    단독 채택** — 레이턴시 차이(6.19ms)가 사용자가 정한 예산(10ms) 안에 들어와 실측과
    결정이 충돌하는 상황이 그대로 기록됨.
  - 리랭커 미실행 결정(Hit@5=Hit@10=1.0000으로 "탐지 실패" 문제가 없다는 근거).
- `archive/superseded_docs/stage4_design_changes_2026-08-06.md`(16:53) — 위 7건(D1~D7)의 변경과 근거를
  전부 아카이빙(380줄, 12절).
- `04_rag_agent/llm.py`(17:15) — NVIDIA NIM Nemotron Nano 클라이언트(API 키 미설정
  상태로 마무리).
- `docs/HANDOFF.md`(17:17) 최종 갱신 — 이 시점 기준 현재 상태.

### 밤 — 저장소 정리
- (이 대화 세션) 최종 채택 파일과 실행 로그·기각 파일을 분리해 `archive/`를 분야별
  (`01_collection/`, `04_rag_agent/`, `02_pubchem_rejected/`, `design_docs/`,
  `adhoc_check_scripts/`)로 재구성, 각 폴더에 사유를 설명하는 `NOTES.md` 작성.
  `.gitignore`에 로그/백업 자동무시 규칙 추가.
- 본 `PROJECT_LOG.md`와 `decisions.md` 작성.
- **검색 방식 재검토**: `decisions.md`를 포트폴리오 관점에서 검토하던 중, §2.4(Dense
  단독 채택)가 "성능이 더 나은 방법을 알면서도 안 쓴 상태"로 남아있다는 지적을
  계기로 재검토 → 섹션 §2·§10 필터 적용 후 실측에서 hybrid가 7개 목표 중 6개(dense
  4개) 충족한다는 이미 기록된 근거에 따라 **dense 단독 결정을 철회하고 hybrid로
  재채택**. `04_rag_agent/run_ab.py`의 dense 우회 코드(`h = d`)를 되돌리고,
  `HANDOFF.md`·`decisions.md`·`stage4_design_changes_2026-08-06.md`(§5-1 신설)에
  반영. 리랭커 단계는 여전히 미실행 상태로 남음(hybrid 후보 기준 재검증 필요).

## 2026-08-07 — N종 물질 조합 구현, 저장소 정리, GitHub push 준비

- **N종(N≥2) 물질 조합 판정 구현** (`03_compatibility/compatibility_engine.py`):
  입력 물질을 전부 쌍 C(N,2)로 쪼개 기존 `judge_pair_by_cas`를 재사용해 판정,
  worst-case 종합(`judge_combination_by_cas`). 처음엔 worst-case 단일값만
  냈으나, 실사용자가 원한 건 "물질별 프로필 + 전체 매트릭스 + 쌍별 유의사항을
  한 번에 보고 싶다"는 것으로 요구사항 재확인 → `SubstanceProfile`, `to_table()`
  (N×N 매트릭스), `pair_reports()`(쌍별 상세), `full_report()`(전부 합친 리포트)
  추가. 자체검증 7건 실물 DB로 통과(중복 CAS 제거, 미등록 CAS Abstain 전파,
  실물 3종 조합 등). 상세 설계는 `archive/superseded_docs/decisions.md` §2.10.
- **robots.txt / "비상업 포트폴리오" 서술 전면 삭제**: GitHub 공개 저장소로
  전환하며 CAMEO 스크레이핑의 robots.txt 위반 사실과 그 정당화 서술("비상업
  목적이므로 무시")을 `HANDOFF.md`, `HANDOFF_ARCHIVE.md`(§5 삭제, 이하 절 재번호),
  `PROJECT_LOG.md`, `msds_risk_assessment_readme.md`에서 제거. 코드 동작 변경
  없음, 문서 서술만 정리.
- **저장소 용량 정리**: `04_rag_agent/chunks/`(8,225개 파일, 21MB)와
  `04_rag_agent/index/`(임베딩·BM25 캐시, 7.3MB)를 `.gitignore`에 추가 — 전부
  `pipeline.py`/`retrieval.py` 재실행으로 재생성 가능한 산출물이라 git에 담지
  않기로 함. `reactivity_reference.db`는 KOSHA API 호출 비용이 든 데이터라 예외로
  유지. `.claude/settings.local.json`도 프로젝트 `.gitignore`에 명시(기존엔 유저
  전역 gitignore에만 의존).
- **N종 관련 문서 상태 동기화**: `README.md`, `docs/HANDOFF.md`, `archive/superseded_docs/decisions.md`
  (§2.5, §2.10, §4-7)에 남아있던 "N종 미구현" 서술을 실제 구현 상태로 갱신.
  RAG 검색 계층의 N종 실측(Recall 등)은 여전히 없다는 점은 구분해서 남김 —
  결정론적 매트릭스 조회(구현됨)와 RAG 검색 성능 실측(안 됨)을 혼동하지 않도록.
- **GitHub push 준비**: 새 저장소(`github.com/mungn0603-code/SMART_MSDS`)로 push
  예정. 기존 git 루트가 `MSDS`가 아니라 상위 `OPEN CODE` 폴더였던 문제 때문에
  `MSDS/` 단독 저장소로 새로 준비. 비밀 유출 점검(dry-run) 후 사용자가 직접
  push하도록 안내(Claude는 push 자체를 실행하지 않음).

---

## 2026-08-09~08-17 — Hazard/Reactivity Assessment STEP1~5 (Generation·Judge·실패분석)

- (출처: `docs/HANDOFF.md` §0-6, 상세는 그쪽이 원본) LLM 연결 완료 후 STEP1(Retrieval
  고정) → STEP2(Generation baseline 확정) → STEP3(2,158건 생성) → STEP4(Judge 전체
  평가) → STEP5(`04_rag_agent/analyze_generation.py`로 Retrieval×Generation 분리분석)
  진행.
- 핵심 결론: Retrieval은 병목 아님(hit 98.84%). Generation 실패의 최대 원인은
  over-abstention(46.1%, 근거 있어도 쌍별 명시 문장 없으면 회피) — wrong(30.9%)은
  대부분 "개별물질 위험문구를 쌍 반응성으로 오인해 과잉위험 판정"하는 방향성 편향
  (false negative는 3.6%뿐).
- 산출물: `04_rag_agent/results/step5_summary.json` 외 3종.
- 2026-08-17 사용자 결정: over-abstention 완화를 위한 prompt v2 설계·소규모 pilot
  검증 착수(전수 재실행 아님). 개선 확인 후 프로젝트 정리→공개 순으로 진행 예정.

---

## 2026-08-17 — prompt v2 폐기 → CAMEO-context 전환 → 전수실행 → 문서·저장소 재편

- prompt v2/v2.1은 정상 케이스 과잉 Abstain 회귀를 유발해 기각. CAMEO 반응성 그룹
  조회가 matrix_verdict와 100% 일치함을 확인하고, LLM은 판정을 직접 하지 않고
  CAMEO 판정을 MSDS 근거로 설명만 하는 구조(v4)로 전환.
- judge가 CAMEO 근거를 못 보고 채점하는 버그 발견·수정(13건 파일럿 6/13→13/13
  faithful). Cascade Judge는 신뢰도 문제로 기각. 전수실행(2,160건) 중 API 429
  685건은 재시도 로직 강화로 해소, 잔여 unfaithful 203건은 v5로 표적 재시도해
  74.3% 회수.
- 최종: 정답률 99.9%, faithful 97.2%, 물질혼동 0/2,142. 상세는
  `docs/HANDOFF.md` §0-7, `docs/GENERATION.md`.
- 저장소를 `01_collection~05_evaluation`에서 `src/scripts/data/results/docs/archive`
  구조로 재편. docs/는 8개 표준 문서(README/PIPELINE/DATA/RETRIEVAL/GENERATION/
  FILE_GUIDE/HANDOFF/PROJECT_LOG)만 유지, 흡수된 원본은 `archive/superseded_docs/`,
  기각된 실험은 `archive/generation_experiments/`로 이동.

## 2026-08-22 — Registry 237종 확정, KOSHA 상세 연동, 물질명 일관성

**KOSHA MSDS 상세정보 연동.** 그때까지 앱은 KOSHA 등재 여부(`getChemList` 결과)만
보여줬다. `getChemDetail02/03/09/10`으로 §2/§3/§9/§10을 수집해 물질별 상세 패널을
붙였다. Registry 대상 중 상세 보유가 130 → 198종.

**미등재 39종을 실조회로 확정.** 처음엔 캐시에 `chem_id IS NULL`로 남아 있던 걸
"미등재 확인"으로 보고했는데, 그건 확인이 아니라 캐시를 읽은 것이었다. 39종 전부를
`getChemList`로 CAS(searchCnd=1)/국문명·영문명(searchCnd=0) 3경로 실호출한 결과
CAS 검색 0건, 오류 0건. 이름 검색에 걸린 7종은 전부 화합물이거나 부분문자열
오매칭(라돈→팔라듐, 어븀→터븀)이었다. 근거:
`results/kosha_missing39_probe_2026-08-22.csv`.

**물질명 기준을 registry canonical name으로 통일.** `display_names`가
`rag_chunks.chemical_name`을 우선하던 탓에 선택 목록은 "염화아연", 결과·보고서는
"염화 아연 흄"으로 갈렸다(overlap 127종 중 85종 불일치). 우선순위를 뒤집어 검색
→ 선택 → 상세 → 판정 → 보고서가 같은 이름을 쓰게 했다. RAG 질의문 생성은 계속
`rag_chunks` 이름을 쓰므로 frozen eval은 무영향.

**"Registry ∪ 173" 규칙 폐기.** 앱 선택 목록이 Registry 207 ∪ 코퍼스 173이라,
Registry 심사를 거치지 않은 코퍼스 전용 96종이 서비스 대상에 있었다. 96종을 CORE
5축으로 재평가하니 `curated_curriculum` 근거를 가진 물질이 **0종**, 전량이 반응빈도·
풀보충 수집 산물이었다. PROMOTE 7 / DROP 86 / UNCERTAIN 3으로 판정하고, 선정 기준을
Registry 단독으로 세웠다.

**CORE 207 공백 탐색 → 신규 23종.** 재평가를 96종 안에서만 하면 "데이터가 있는 것
중에 고르기"가 되어 project_173을 폐기한 이유가 재현된다. 탐색 범위를 96종 밖까지
넓히자 판정이 3건 뒤집혔다 — 금속 인화물 대표는 Mg₃P₂(96종) 대신 인화알루미늄,
클로로실란은 다이메틸다이클로로실란. fundamental에서 인산과 유기용매 계열이 통째로
비어 있던 것도 이때 드러났다. 신규 26종 후보 전량 KOSHA 등재를 실조회로 확인하고
23종 편입, 3종 보류. **Registry 207 → 237 확정**(등재 198 / 미등재 39).

**서비스 계약 4조건 정의.** 등록됐다고 다 서비스되는 게 아니라는 걸 티어로 드러냈다 —
A(4조건 충족) 111 / B1(검색근거 결여) 31 / C(상세만) 56 / X(미등재) 39. `chemicals`
매핑이 없으면 `judge_pair_by_cas`가 무조건 Abstain이라는 사실이 여기서 수치로 나왔다.

**인덱스 23종 편입.** Registry 소속인데 `rag_chunks`가 있고 인덱스 태그에만 없던
23종(테레프탈산·페로센·삼산화크로뮴·질산암모늄 등)을 `corpus_tag='core'`에 추가
(27→50종, 인덱스 200→223종 / §2·§10 471청크). 캐시는 청크 수 불일치로 자동 재생성.
A티어 111 → 134.

**질의 별칭 확장.** 표시명을 표준명으로 통일한 부작용으로, 청크 헤더가 KOSHA
원문명인 물질은 BM25가 어휘 매칭을 못 했다(페로센 vs 디시클로펜타디에닐 철).
`query_term()`이 `rag_chunks.chemical_name` → KOSHA 원문명 → `name_en` → `aliases`
순으로 최대 3개를 덧붙이게 했다. 자기 청크 top-10 진입이 101/134 → 132/134, 회귀 0건
(파트너를 수산화나트륨으로 고정한 자체 프로브 기준이며 frozen 지표와 무관).
남은 2종(`수소`·`나트륨`)은 수산화·과산화수소·나트륨염 등이 같은 형태소를 공유해
IDF가 바닥인 케이스라 별칭으로는 못 푼다.

**남긴 판단.** Registry 단독 전환으로 판정 가능 쌍이 72.6% → 51.3%로 떨어진다.
제외된 코퍼스 96종이 CAMEO 매핑을 100% 보유했기 때문이며, 선정 기준의 정합성과
맞바꾼 값이다. 회복하려면 물질을 더 넣는 게 아니라 CAMEO 매핑을 확충해야 한다.

### 2026-08-22 (이어서) — CAMEO 매핑 확충 142 → 173종

바로 위에서 "회복하려면 CAMEO 매핑을 확충해야 한다"고 남긴 걸 그대로 했다.

**경로 선택.** 미매핑 95종은 CAMEO 스크레이핑 풀(`chemicals` 3,400종)에 아예 없다.
`reactivity_groups` 68그룹을 우리가 구조 기준으로 직접 매핑하는 안을 검토했지만
그건 "CAMEO가 판정하고 LLM은 설명한다"는 원칙에서 판정 주체를 우리로 바꾸는 일이라
택하지 않았다. 대신 [`DATA.md`](DATA.md)가 스크레이핑 대체 경로로 이미 채택해 둔
PubChem Classification Browser `hid=86`(CAMEO Chemical Reactivity Classification)을
미매핑분에 그대로 적용했다 — 출처가 여전히 CAMEO다.

**신뢰도 먼저 쟀다.** 이미 매핑된 registry 30종을 같은 엔드포인트로 재조회해
29종 완전 일치 / 1종 PubChem superset(에틸렌글라이콜에 `Ethers` 추가)을 확인한 뒤
미매핑분에 적용했다.

**결과.** 95종 조회 → 31종 적재(48행), `chemicals` 3,400 → 3,431종.
매핑 142 → **173종**, 판정 가능 쌍 10,011 → **14,878 / 19,503 = 76.3%**.
티어는 A 134(불변) / B1 8 → **39** / C 56 → **25** / X 39.
기존 `CAMEO_scrape` 행은 건드리지 않았고 추가분은 전량
`source='pubchem_cameo_2026-08-22'`라 태그 하나로 되돌릴 수 있다.

**두 건 제외.** 메탄올(CH4O)에 `Amines, Phosphines, and Pyridines`가,
산화철(III)(Fe2O3)에 `Sulfides, Inorganic`이 딸려왔다. 둘 다 해당 원소가 분자에
없다 — PubChem CID 하나에 CAMEO 데이터시트 여럿이 엮이면서 생긴 것으로 보인다.
구조 판단이 아니라 조성 대조이므로 제외했고 사유를 스크립트 상수와 리포트에 남겼다.

**채우지 않은 25종.** 원소 23종 + 탄산나트륨 + 염화나트륨은 PubChem `hid=86`에
CAMEO 분류 자체가 없다. 염화칼륨(47번)·탄산칼슘(21번)·세륨/이트륨(41번) 같은
유사 물질로 유추해 채울 수 있었지만 그건 CAMEO의 판정이 아니라 우리의 판단이라
비워 뒀다. Abstain이 틀린 판정보다 낫다는 원칙이 여기에도 적용된다.

**병목 이동 → 같은 날 해소.** C→B1로 31종이 옮겨간 건 "판정은 되는데 §2/§10 원문
근거를 못 붙인다"는 뜻이었고, 그 39종은 `msds_sections`에 상세 40행씩 갖고 있고
`rag_chunks`만 0건이었다. 아래에서 청킹해 해소했다.

**검증.** `app/streamlit_app.py --check`에 코퍼스 규모(당시 173 frozen + core 50 = 223종),
CAMEO 매핑 173/198, 매핑쌍 non-Abstain / 미매핑쌍 Abstain, 신규 매핑 실판정
(메탄올 × 질산 = Incompatible + 상세 37행)을 추가해 전부 통과. 신규 매핑 10쌍
수기 점검에서도 벤젠×질산·아세틸렌×구리·DCM×나트륨·하이드라진×과산화수소 등이
전부 Incompatible, 메탄×물은 Compatible로 나왔다.


### 2026-08-22 (이어서) — B1 39종 청킹, A티어 134 → 173

**편입 게이트를 세우려다 폐기했다.** "MSDS 행이 있다고 내용이 있는 건 아니다"라는
지적에 따라 39종을 A(청킹)/B(§2·§10 내용 없음)/C(placeholder)로 삼분하려 했다.
기준은 §10에서 정형문구(`타는 동안 열분해…`)와 `자료없음`을 뺀 물질특이 정보량,
경계는 173 코퍼스 하위 5%인 27자. 이 기준이면 자일렌·인산·수은·불소 4종이 제외된다.

그런데 **같은 기준을 이미 편입된 `core` 50종에 대 보니 6종이 걸렸다** — 과산화나트륨·
삼산화크로뮴·중크롬산칼륨·칼륨·나트륨·카드뮴. 알칼리 금속과 크로뮴(VI)은 혼재보관
위험성평가가 가장 다뤄야 할 물질이다. 즉 이 값이 재는 건 근거의 유무가 아니라
**KOSHA가 그 물질의 §10을 채웠는가**이고, 편입을 가를 근거가 못 된다. 제외 예정이던
불소도 같은 경우다(§10 10자, 실제로는 최강 산화제).

게이트를 폐기하고 39종 전부 편입했다. 삼분 자체는 버리지 않고 `s10_specific_chars`
열로 `service_contract_audit.py`에 남겨 **표시만** 한다(서비스 198종 중 20종이 27자 미만).
근거 하나 더 — 검색 실측에서 gold_evidence는 전량 §2이고 §10 청크는 전부 감점
대상이라(`retrieval.boilerplate_penalty_vector`), §10이 얇아도 §2 청크는 정상 작동한다.

**실행.** `pipeline.py --target-csv <39종> --version stage4-v2-chunk-1-core39 --no-markdown`
→ section 164청크 / item 1,446청크. 새 version 태그가 필수다(`persist()`가 version
기준으로 DELETE 먼저 한다). `--no-markdown`도 필수 — `write_markdown()`이
`data/chunks/**`를 전부 지우고 이번 실행분만 쓴다. 이어서 `seed_core_corpus.py --write`로
`corpus_tag='core'` 50 → **89종**, 인덱스 223 → **262종 / §2·§10 557청크**.
frozen 173은 태그가 달라 불변.

**결과.** 티어 **A 134 → 173 / B1 39 → 0** / C 25 / X 39. 서비스 대상 198종 중
CAMEO 매핑이 있는 173종은 전부 상세·검색·판정 3조건을 충족한다. 판정 가능 쌍은
CAMEO 매핑이 안 변했으므로 76.3% 그대로.

**회귀 1종 — 아세트산.** 인덱스 확장 전후로 "자기 청크 top-10 진입"을 실측했다
(파트너를 수산화나트륨으로 고정, 별칭 확장 때와 같은 프로브). 기존 134종 **132 → 131**,
신규 39종 **37/39**. 떨어진 건 아세트산(64-19-7) 하나이고, 원인은 신규 편입된
아세트산에틸(141-78-6)의 KOSHA 원문명이 "초산 에틸"이라 아세트산의 별칭 "초산"과
어휘 매칭된 것이다. 판정은 영향 없고 §2/§10 근거가 상대 물질 것만 붙는다.
별칭을 빼는 건 REGISTRY.md의 식별정보 유지 규칙에 어긋나므로 고치지 않고 기록만
남긴다 — 코퍼스에 물질이 늘면 별칭이 모호해지는 문제이며, 기존 과제 7번(원소·일반명의
검색 열위)과 같은 뿌리다. 신규 미진입 2종(인산·프로페인)도 §10이 얇은 같은 계열이다.

**검증.** `--check` 전항 통과(코퍼스 262종 / core 89 / CAMEO 173-198 / 매핑쌍
non-Abstain / 미매핑쌍 Abstain / 메탄올×질산 Incompatible).


## 2026-08-23 — CAMEO coverage 확정, item 청크 생성 제거

**미매핑 25종은 원천 부재로 확정.** PubChem `hid=86` 무응답이 조회 실패인지 데이터
부재인지를 CAMEO 자체 색인으로 교차 확인했다. `robots.txt`가 막는 건 `/search`·
`/reactivity`·`/help`·`/my`·`/stats`뿐이라 `/browse/{letter}`는 허용 경로다.
처음엔 `/browse/S`·`/browse/G` 두 장만 봤는데, "이름이 달라서 못 찾은 것 아니냐"는
지적을 받고 다시 했다. 타당한 지적이었다 — 페이지 상단에 "This list only includes the
names at the top of the chemical datasheets"라고 적혀 있어 대표명만 보고 있었던 것이다.
**19개 알파벳 페이지 대표명 4,391건을 전수 스캔**하고 별칭 후보(SODA ASH·SALT·HALITE·
BRINE·COLUMBIUM=나이오븀 구명칭)까지 넣어 재검색했다. 결과는 같다 — 25종 전부 부재,
원소는 화합물만. 대조군으로 `PLATINUM`(`/chemical/25055`)이 존재하고 그건 우리 DB에
이미 42번으로 매핑돼 있다.

로컬 CRW 4.0 엑셀(`CRW_Data_Export_reactivity map.xlsx`)도 봤으나 68×68 매트릭스뿐이라
물질 단위 데이터가 없다.

**근거는 CAMEO 자신의 수록 범위다.** About 페이지가 "a database of hazardous chemical
datasheets... thousands of hazardous substances"라고 명시한다. 염화나트륨·탄산나트륨은
DOT/UN 분류가 없는 비위험물이고 란타넘족·귀금속 원소도 마찬가지다. 이름 불일치가 아니라
대상 밖이다. **판정 가능 쌍 76.3%(14,878/19,503)를 현재 coverage로 확정**하고 목표를
CAMEO 100%로 두지 않는다.

**폐기한 근거 하나.** PubChem 출처 목록에 CAMEO가 없다는 걸 증거로 쓰려다, 대조군인
황산·백금도 똑같이 안 잡히는 걸 확인하고 버렸다(`pug_view/categories`가 CAMEO 출처를
노출하지 않음). 대조군을 안 돌렸으면 틀린 근거를 문서에 남길 뻔했다.

**닫지 못한 것.** 대표명이 아닌 별칭으로만 존재하는 데이터시트는 확인 불가다. 별칭
검색은 `/search`(robots 금지)뿐이고 `/react/{id}` 그룹 페이지도 소속 물질을 나열하지
않는다(허용 경로에 열거 수단 없음). 확실히 닫으려면 CAMEO 오프라인 desktop program의
배포 데이터가 필요하다.

**item 청크 생성 제거.** 2026-08-06에 section vs item을 Retrieval 지표로 A/B 하려고
둘 다 만들었고 section이 채택됐다. 그 뒤로 앱·평가·인덱스가 전부 `GRAN='section'`만
쓰는데 `pipeline.py`는 계속 둘 다 만들었다 — 전날 39종 청킹에서도 쓰이지 않을 item
1,446개가 같이 생성됐다. `build_chunks`의 item 블록을 제거했다.

검증: `test_pipeline.py` 통과, `build_chunks`가 section만 반환, DB의 section 1,993행과
인덱스 §2·§10 557청크 무변경.

**기존 item 18,200행도 삭제했다**(2026-08-24, 사용자 지시). DB 20.8MB → 9.6MB(VACUUM).
`granularity` 스키마 제약은 남겨 둔다 — 되살리려면 git 이력에서 `build_chunks`의 item
블록을 복원하고 재청킹하면 된다. 삭제 후 `--check` 전항·`test_pipeline.py` 통과,
section 1,993행 / 인덱스 557청크 / frozen 173 코퍼스 전부 무변경.

**부작용 두 가지(코드는 안 고쳤다).** `run_ab.py`와 `freeze_retrieval.py`는 확정 지표를
낸 재현 경로라 손대지 않는다는 규칙이 있어 그대로 뒀다.

- `run_ab.py --granularity both`(기본값)/`item`은 이제 빈 코퍼스가 된다. README에 적힌
  재현 명령은 `--granularity section`을 명시하므로 문서화된 경로는 영향 없다.
- `archive/2026-08-08_selection_scripts/evalset.py`는 item 청크에서 단일물질 fact 평가셋을 만든다 — 재실행 불가.
  산출물 4종(`gold_pair.jsonl`·`gold_retrieval.jsonl`·`gold_abstain.jsonl`·
  `gold_pair_abstain.jsonl`)은 `data/evalset/`에 이미 있고 쌍 평가셋이 확정 지표의
  근거이므로 재생성할 일이 없다.

같이 고친 것 — `write_markdown`/`report`가 `("section","item")`을 하드코딩하고 있어
item이 비면 깨진다. 실제 생성된 granularity를 보도록 바꿨다. `--target-csv` 도움말에는
"부분 실행 시 `--no-markdown` 필수"를 명시했다(`write_markdown`이 기존 `.md`를 전부
지운다 — 전날 밟을 뻔한 지뢰다).

---

## 아직 착수하지 않은 것 (다음 세션)

2026-08-22 기준 최신 우선순위(`docs/HANDOFF.md` §0-7 참고):
0. **RAG 검색을 앱 UI에 연결** — 서비스 계층에서 남은 가장 큰 구멍. A티어가 173종이 된
   지금 `explain()`/`retrieve()`의 호출 지점은 여전히 `--check`뿐이고, 최종 보고서는
   CAMEO 판정행으로만 프롬프트를 만든다(6번 항목과 같은 건이며 우선순위를 올림)
1. faithful 잔여 실패 2.8%(61건) — 그룹 분류를 확인된 반응처럼 단정하는 패턴,
   프롬프트 지시만으로는 완전 해소 안 됨
2. RAG 지표(RAGAS 계열: Context Precision 등)는 n=7 파일럿 후 중단, 자체 Judge로
   대체된 채 재개 안 함(`archive/generation_experiments/NOTES.md`)
3. 질의 인코더 최적화(임베딩 지연 500ms 목표는 이후 재측정에서 368ms로 충족 상태 전환)
4. 청석면 등 원본 리스트 전체 안전성 재검증(대체 후보군만 재검증됨, 173종 전체는 아직)
5. N종(N≥3) 물질 조합의 **RAG 검색 실측** — 매트릭스 판정 자체는
   `src/compatibility_engine.py`의 `judge_combination_by_cas`/`full_report`로 구현
   완료(쌍 판정을 worst-case로 종합), 다만 RAG 검색 계층의 Recall/MRR 실측은
   여전히 쌍(2종) 질의 기준까지만
6. RAG 검색 결과를 앱 UI에 연결 — `explain()`/`retrieve()`의 유일한 호출 지점이
   아직 `--check`뿐이다. 최종 보고서는 CAMEO 판정 행에서 프롬프트를 만들고 RAG
   컨텍스트를 쓰지 않는다
7. `수소`·`나트륨` 같은 일반 원소명의 검색 열위 — 같은 형태소를 공유한 화합물이
   다수라 IDF가 낮다. 별칭 확장으로는 못 풀고 원소 부스팅이나 CAS 필터가 필요
8. 보류 물질 6종 재판정 — 학부 커리큘럼 실측 3종(`106-51-4`/`100-02-7`/`76-03-9`),
   대안·저우선순위 3종(`75-21-8`/`110-86-1`/`97-93-8`)

---

## 2026-08-29 — Generation을 Upstage 기준으로 재정의하고 service 전수 측정

- **Generation/Judge LLM을 NVIDIA NIM(`nemotron-3-nano-omni-30b-a3b-reasoning`)에서
  Upstage `solar-pro3`로 전환**(`src/llm.py`). 엔드포인트
  `https://api.upstage.ai/v1/chat/completions`, `reasoning_effort=high`(문서 기준
  minimal/low/medium/high, high는 컨텍스트 잔여량의 60%를 추론 예산으로 씀).
  실측 레이트리밋 100 RPM / 250,000 TPM — 생성은 worker 7, 채점은 worker 1이
  TPM 상한에 맞는 값이다. 종전 모델로 낸 173 코퍼스 지표는
  `archive/2026-08-17_baseline/`에 보존한다.
- **`generate_baseline.MAX_TOKENS` 1500 → 8192.** NVIDIA NIM은 `reasoning_budget`이
  `max_tokens`와 별개라 1500이 본문 전용 예산이었으나 solar-pro3는 추론 토큰이
  `max_tokens`를 같이 소비한다. 1500 유지 시 파일럿 20건 중 9건이 상한에 걸리고 3건은
  본문이 빈 문자열로 나왔다.
- **재개 로직 강화**(`run_cameo_full.py`). 종전에는 실패 레코드도 출력 파일에 기록되고
  `already_done`이 query_id만 봐서 재실행해도 영구히 건너뛰었다 — 일시적 429/파싱 실패가
  영구 결손이 된다. 성공 건만 완료로 치도록 바꾸고, 재시도로 생기는 중복은
  `dedupe_records`로 접는다. 빈 응답은 `error`로 승격, judge JSON 파싱 실패는 3회 재시도.
  자가검증 `tests/test_run_cameo_resume.py`. 전수 실행 중 실제로 3건이 실패·누락했고
  같은 명령 재실행으로 전부 복구됐다.
- **"물질 혼동 0/2,142"가 공허한 값이었음을 확인.** 이 지표는 답변의
  `[사용한 근거: n, ...]` 태그를 파싱하는데 v4/v5 프롬프트가 그 태그를 요구하지 않아
  아카이브 2,160건 전건이 측정 불가(None)였다. 사용자 결정에 따라 아카이브는 그대로 두고,
  새 프롬프트 `cameo_service_v6`에서 태그 출력을 요구했다.
- **`VERDICT_LINE_RE` 확장.** solar-pro3는 "판정:" 대신 마크다운 헤더 "**판정**" + 줄바꿈
  형태를 자주 쓴다. 종전 정규식이 150건을 놓쳤다(판정 자체는 정확히 명시됨). 콜론/볼드/
  줄바꿈을 허용하도록 넓혔고, 둘 다 매칭되는 건에서 결과가 달라지는 사례는 0건이라
  해석 변경이 아니라 recall 개선이다(93.3% → 99.8%). 파생 필드는
  `scripts/6_eval/reparse_verdict_line.py`로 API 재호출 없이 재계산했다.
- **service 전수 측정 완료** — 2,240건, 생성·채점 **실패 0건**, 비용 $5.79, 생성 지연
  평균 12.0초. 정답률(판정줄) 99.9%(2,238/2,240, **뒤집힌 판정 0건**) / 정답률(judge
  재분류) 83.9% / faithful 94.6% / 물질혼동 14.7% / 판정줄–본문 일치 82.9%.
- **최대 결함 식별**: judge 불일치 355건 중 323건이 "본문을 더 위험하게 읽음"이고, 그중
  301건이 matrix=Caution인데 본문은 Incompatible로 읽힌 건이다. 그 301건 전부 판정줄은
  Caution으로 정확히 썼다. 판정은 지키되 서술 강도가 올라간다.
- 집계 스크립트 `scripts/6_eval/summarize_cameo_full.py` 추가(지표 정의의 단일 출처). 아카이브로
  검증해 문서의 99.9%/97.2%가 그대로 재현됨을 확인했다. 다만 문서의 "93.6%(judge 재분류
  기준)"는 같은 정의로 계산하면 97.0%(2,041/2,104)로, 어떤 분모를 썼는지 불명이다.
