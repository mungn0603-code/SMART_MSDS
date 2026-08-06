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

- `docs/msds_risk_assessment_readme.md` 작성(10:57) — 이 시점까지의 유일한 기준 문서로
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
- `docs/HANDOFF_ARCHIVE.md`(10:35), `docs/session_log_2026-08-06.md`(12:07) 작성 —
  Stage 1 완주 및 과거 정정 이력 정리.

### 오후~저녁 — Stage 4(RAG) 설계부터 실측까지
- **설계 v1 → v2 전면 교체(같은 날)**: v1의 최상위 철학("기존 자산(KDIC) 재사용 우선")을
  버리고 v2("검색 성능 우선")로 전환. `docs/stage4_design_principles_v2.md`(14:21)
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
  (`docs/decisions.md` §2.10).
- `run_ab.py`(16:40)로 실측 진행, 주요 발견:
  - **섹션 §2·§10 필터 적용(805→409청크)**: 정확도(Recall@10 +1.59%p, nDCG@10 +3.68%p)와
    속도(3.3배 단축)가 동시에 개선되는 순수 이득 확인.
  - **Hybrid vs Dense 충돌**: 같은 조건에서 hybrid가 7개 목표 중 6개, dense가 4개
    충족(Recall@10 hybrid 0.9005 > dense 0.8829). 그럼에도 **사용자 지시로 dense
    단독 채택** — 레이턴시 차이(6.19ms)가 사용자가 정한 예산(10ms) 안에 들어와 실측과
    결정이 충돌하는 상황이 그대로 기록됨.
  - 리랭커 미실행 결정(Hit@5=Hit@10=1.0000으로 "탐지 실패" 문제가 없다는 근거).
- `docs/stage4_design_changes_2026-08-06.md`(16:53) — 위 7건(D1~D7)의 변경과 근거를
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
  실물 3종 조합 등). 상세 설계는 `docs/decisions.md` §2.10.
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
- **N종 관련 문서 상태 동기화**: `README.md`, `docs/HANDOFF.md`, `docs/decisions.md`
  (§2.5, §2.10, §4-7)에 남아있던 "N종 미구현" 서술을 실제 구현 상태로 갱신.
  RAG 검색 계층의 N종 실측(Recall 등)은 여전히 없다는 점은 구분해서 남김 —
  결정론적 매트릭스 조회(구현됨)와 RAG 검색 성능 실측(안 됨)을 혼동하지 않도록.
- **GitHub push 준비**: 새 저장소(`github.com/mungn0603-code/SMART_MSDS`)로 push
  예정. 기존 git 루트가 `MSDS`가 아니라 상위 `OPEN CODE` 폴더였던 문제 때문에
  `MSDS/` 단독 저장소로 새로 준비. 비밀 유출 점검(dry-run) 후 사용자가 직접
  push하도록 안내(Claude는 push 자체를 실행하지 않음).

---

## 아직 착수하지 않은 것 (다음 세션)

`docs/HANDOFF.md` §4 기준:
1. LLM 연결(NVIDIA_API_KEY 설정 — 사용자만 가능)
2. RAG 지표 측정(Faithfulness / Context Recall / Context Precision / Answer Relevancy) —
   `ragas` 미설치
3. Abstain Precision 측정(평가셋 81쌍은 준비됨, LLM 연결 필요)
4. 질의 인코더 최적화(임베딩 지연 500ms 목표에 1.7ms 초과)
5. 청석면 등 원본 200종 리스트 안전성 재검증(§10, 조치 대기)
6. N종(N≥3) 물질 조합 판정 구현 — 쌍 판정을 worst-case로 종합하는 상위 함수 없음
   (`docs/decisions.md` §2.10)
