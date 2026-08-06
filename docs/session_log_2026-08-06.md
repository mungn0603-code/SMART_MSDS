2026-08-06 세션 요약 (Claude Code)

**KOSHA API 403 해결**: 서비스키가 마이페이지에서 승인완료(자동승인, 2026-08-04~2028-08-04) 상태였음에도 모든 호출이 `resultCode=30 SERVICE_KEY_IS_NOT_REGISTERED_ERROR`로 실패. 로컬 인코딩 3방식 테스트 + data.go.kr 공식 Swagger "Try it out" 도구로 동일 키 재현 테스트를 통해 로컬 코드/인코딩 문제가 아니라 포털 측 계정-키 등록 연동 버그임을 확정. 사용자가 KOSHA(디지털계획부)에 문의 접수 → 조치 완료 → 동일 키로 `resultCode=00` 정상 응답 확인.

**1차 수집**: `kosha_msds_collector.py`로 200종(섹션 2/3/9/10) 수집 실행 → 168종 성공(EAV 6,720행), 32종 미발견.

**32종 분석**: `undergrad_target_chemicals.csv`의 `source`별로 보면 실제 커리큘럼 화학물질(`curated_curriculum`, 30종)은 100% 발견됨. 미발견 32종은 전부 CAMEO 67그룹 커버리지를 채우려 넣은 보충물질(`pool_supplement`/`pool_topup`)로, 군용폭약·단종농약 등 KOSHA에 없을 법한 희귀물질이었음.

**그룹 내 대체 (사용자 요청)**: "학부실험에 가까운" 대체품을 찾기 위해 같은 CAMEO 그룹의 KOSHA 등록 후보를 순차 시도. 1차(KOSHA 등록여부만 확인) 30/32 성공했으나 재검증 결과 석면(1A급 발암물질)·블레오미신(항암제)·안트랄린(치료제) 등 10건이 부적절로 판명. 2차(GHS H-code+KOSHA 권고용도 자동필터 추가)로 재대체했으나 **아프라톡신 B1**(최강 발암물질급)이 필터를 통과하는 사고 발생 — KOSHA 자체 데이터의 H-code가 약하게(H361만)만 등록되어 있었기 때문. 3차(수동 이름 검토)로 최종 교정. **최종 198/200 KOSHA 데이터 확보**, 2종만 Abstain 유지(Diazonium Salts 그룹, 후보 3개 전부 KOSHA 미등록).

**그룹 커버리지 검증**: 67/67 유효 CAMEO 그룹 전부 대표물질 보유 확인(그룹36 "분류정보부족"은 설계상 제외).

**교훈**: 단일 자동 안전판정(GHS H-code 하나)은 못 믿음 — 정부DB 자체 분류가 부실한 경우 위험물질도 통과 가능. 용도필드+이름 직접 검토 병행 필요.

**다음 단계**: Stage 4(RAG: 분류→본문추출→청킹→임베딩→적재검증)는 별도 세션에서 착수 예정.

**이번 세션에서 생성/변경된 파일** (참고용):
- `01_collection/backfill_group_replacements.py`, `backfill_round2_safety_filter.py`, `backfill_round3_manual_picks.py` (신규)
- `01_collection/undergrad_target_chemicals.csv` (갱신, `.bak`/`.round2.bak`/`.round3.bak`으로 각 라운드 이전 상태 보존)
- `reactivity_reference.db` (msds_sections, msds_chem_id_cache 갱신)
- `docs/HANDOFF.md` (현재 상태 반영)
- NotebookLM "MSDS 종합" 노트북에도 동일 요약 저장됨
