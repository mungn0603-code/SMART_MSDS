# v8 (verdict를 스키마에 포함) 폐기 기록 — 2026-08-29

structured output 도입 시 `verdict`를 스키마 필드로 두고 모델에게 CAMEO 판정을
"그대로 옮기라"고 지시했다. 전수 실행 중 판정 뒤집기가 관측되어 1928건에서 중단했다.

- verdict 불일치 **20/1922 = 1.04%**
- 방향: {('Incompatible', 'Caution'): 1, ('Incompatible', 'Compatible'): 3, ('Caution', 'Incompatible'): 2, ('Caution', 'Compatible'): 14}
- 위험을 낮춘 방향(안전 임계): **18건**

v7 자유 텍스트는 같은 항목에서 뒤집힌 판정 0건이었다. 스키마 도입으로 없던 실패가 생겼다.

대표 사례: `pair::62-53-3::7440-32-6::t4` — CAMEO=Incompatible 인데 verdict="Compatible",
`hazard_basis`에 "CAMEO 분류상 호환 가능한 것으로 판정되어 있습니다"라고 서술했다.
CAMEO가 말하지 않은 것을 CAMEO 판정이라고 지어낸 것으로, 프로젝트의 타협 불가 원칙
("CAMEO 판정을 LLM이 다시 판단하지 않는다")을 정면으로 위반한다.

## 결론

`verdict`는 코드가 이미 아는 값(`cameo.category`)이다. 복사 작업을 LLM에 시키면
복사를 틀릴 기회를 준다. v8b 에서 스키마에서 제거하고 코드가 주입한다.
그 결과 `정답률(판정줄)`은 구조적으로 100%가 되며, 성과가 아니라 아키텍처가 보장하는
값으로 기록해야 한다(`substance_confused`가 CAS 필터에서 그렇게 된 것과 같다).
