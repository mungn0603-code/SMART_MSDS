# 2026-08-17 baseline (평가 코퍼스 173종)

`corpus_tag='173'` 코퍼스에서 측정한 확정 지표와 그 산출물이다.
**2026-08-28에 서비스 기준을 `corpus_tag='service'`로 전환하면서 여기로 격리했다.**

## 왜 옮겼는가

`evalset_pairs.py` / `freeze_retrieval.py` / `run_cameo_full.py`는 출력 파일명이
고정이라 service 기준으로 재실행하면 이 파일들을 그대로 덮어쓴다.
재평가 전에 옮겨야 보존이 성립한다.

## 이 지표의 유효 범위

Recall@10 0.9336 / Hit@10 0.9884 / MRR 0.9169 / nDCG@10 0.8500
정답률 99.9% / faithful 97.2% / 물질혼동 0 (쌍 질의 2,160건)

**측정 대상은 `corpus_tag='173'` 코퍼스 173종이다.** 그중 89종은 Registry 237에
없는 물질이라 현재 서비스 대상이 아니다. 서비스 코퍼스(173종)와는 84종만 겹친다.
따라서 이 숫자는 service 기준 지표와 직접 비교하지 않는다.

## 현재 실행 경로와의 관계

현재 파이프라인은 이 디렉터리를 참조하지 않는다.
재현이 필요하면 파일을 원위치로 되돌린 뒤 `--corpus-tag 173`으로 실행한다.
`corpus_tag='173'` / `'core'` 태그 자체는 DB에 그대로 남아 있다.

## 내용

- `evalset/` — 2026-08-08 생성 평가셋 (gold_pair / gold_pair_abstain / gold_retrieval / gold_abstain / review_sample)
- `results/` — frozen retrieval, generation·eval 산출물(v4 전수/pilot/v5 retry, baseline), 검색 A/B 결과, step3·step5 분석, CAMEO 조회 점검
