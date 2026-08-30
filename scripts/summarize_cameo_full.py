# -*- coding: utf-8 -*-
"""run_cameo_full.py 산출물을 지표로 집계한다. LLM 호출 없음.

    python scripts/summarize_cameo_full.py
    python scripts/summarize_cameo_full.py --gen <경로> --eval <경로>   # 아카이브 비교용

지표 정의(문서 인용 시 이 정의를 함께 적는다):
  정답률(판정줄)   = kept_cameo_verdict True / 전체
                     답변 판정줄이 CAMEO 매트릭스 판정을 그대로 유지했는가.
                     이 프로젝트의 '타협 불가 원칙'을 직접 재는 값.
  정답률(judge)    = answer_correct True / (True+False)
                     judge 가 답변 본문을 재분류한 결과가 matrix_verdict 와 일치하는가.
                     Abstain·judge 실패는 분모에서 제외된다.
  faithful         = faithful True / judge 성공 건
  물질 혼동        = substance_confused True / not-None 건
                     인용한 근거 중 쌍의 두 물질 어디에도 속하지 않는 게 있는가.
                     답변에 [사용한 근거: n, ...] 태그가 없으면 None(측정 불가)이다.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V6 = ROOT / "archive" / "2026-08-29_generation_prompt_history" / "v6"  # 문서 확정 지표(cameo_service_v6) 산출물


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def dedupe(rows: list[dict], err_field: str) -> list[dict]:
    best: dict[str, dict] = {}
    for r in rows:
        cur = best.get(r["query_id"])
        if cur is None or cur.get(err_field) is not None:
            best[r["query_id"]] = r
    return list(best.values())


def pct(num: int, den: int) -> str:
    return f"{num}/{den} = {num / den * 100:.1f}%" if den else f"{num}/0 = n/a"


def mean(xs: list) -> float | None:
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", type=Path, default=V6 / "generation_cameo_full.jsonl")
    ap.add_argument("--eval", type=Path, default=V6 / "eval_cameo_full.jsonl")
    args = ap.parse_args()

    gen = dedupe(load(args.gen), "error")
    ev = dedupe(load(args.eval), "judge_error")
    by_id = {r["query_id"]: r for r in gen}
    n_gen, n_ev = len(gen), len(ev)
    gen_fail = sum(1 for r in gen if r.get("error"))
    ev_fail = sum(1 for r in ev if r.get("judge_error"))

    print(f"파일: {args.gen.name} / {args.eval.name}")
    print(f"모델: {sorted({r.get('model') for r in gen})}  프롬프트: {sorted({r.get('prompt_version') for r in gen})}")
    print(f"생성 {n_gen}건(실패 {gen_fail}) · 채점 {n_ev}건(실패 {ev_fail})")
    print()

    kept = [r["kept_cameo_verdict"] for r in ev]
    print(f"정답률(판정줄)  {pct(sum(k is True for k in kept), len(kept))}"
          f"   [None {sum(k is None for k in kept)}건 = 판정줄 파싱 실패]")

    ac = Counter(r["answer_correct"] for r in ev)
    print(f"정답률(judge)   {pct(ac[True], ac[True] + ac[False])}"
          f"   [제외 {ac[None]}건 = Abstain·judge 실패]")

    ok = [r for r in ev if r["faithful"] is not None]
    print(f"faithful        {pct(sum(r['faithful'] is True for r in ok), len(ok))}")

    sc = Counter(r["substance_confused"] for r in ev)
    measured = sc[True] + sc[False]
    if measured:
        print(f"물질 혼동       {pct(sc[True], measured)}"
              f"   [측정 불가 {sc[None]}건 = 인용 태그 없음]")
    else:
        print(f"물질 혼동       측정 불가 (전 {sc[None]}건에 인용 태그 없음 -> 지표가 작동한 적 없음)")

    tagged = sum(1 for r in gen if "[사용한 근거" in (r.get("generated_answer") or ""))
    print(f"인용 태그 출력  {pct(tagged, n_gen)}")

    p, rc = mean([r["evidence_precision"] for r in ev]), mean([r["evidence_recall"] for r in ev])
    print(f"evidence precision {p if p is None else round(p, 4)} / recall {rc if rc is None else round(rc, 4)}")
    print()
    print("abstention_bucket:", dict(Counter(r["abstention_bucket"] for r in ev)))
    print("retrieval_status :", dict(Counter(r["retrieval_status"] for r in ev)))
    print("matrix_verdict   :", dict(Counter(r["matrix_verdict"] for r in ev)))
    tb = Counter(r["tag_body_consistent"] for r in ev)
    print(f"판정줄-본문 일치 : {pct(tb[True], tb[True] + tb[False])} [None {tb[None]}]")

    lat = [by_id[r["query_id"]]["latency_sec"] for r in ev if r["query_id"] in by_id]
    tok = [by_id[r["query_id"]].get("total_tokens") or 0 for r in ev if r["query_id"] in by_id]
    if lat:
        print(f"생성 지연 평균 {mean(lat):.1f}s · 생성 토큰 합 {sum(tok):,}")


if __name__ == "__main__":
    main()
