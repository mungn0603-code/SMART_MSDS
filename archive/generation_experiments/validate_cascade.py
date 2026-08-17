"""Cascade Judge(Rule -> Small -> Large fallback) 소규모 검증(100~300건).

같은 CAMEO+MSDS 생성 답변에 대해 기존 Large Judge(ground truth)와 Cascade Judge를
각각 돌려 비교한다. Retrieval/Generation prompt·model/format_context()/CAMEO 판정
로직은 전혀 건드리지 않는다 — run_cameo_full.py의 생성 로직을 그대로 재사용해 표본만
생성하고(이미 생성된 건은 재사용), 채점만 두 갈래로 비교한다.

  python 04_rag_agent/validate_cascade.py --n 150
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import eval_generation as EV  # noqa: E402
import cascade_judge as CJ  # noqa: E402
from run_cameo_full import run_generation, load_jsonl, GEN_OUT  # noqa: E402

VAL_OUT = HERE / "results" / "validate_cascade.jsonl"


def already_done(path: Path) -> set[str]:
    if not path.exists():
        return set()
    done = set()
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                done.add(json.loads(line)["query_id"])
            except (json.JSONDecodeError, KeyError):
                continue
    return done


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=150)
    args = ap.parse_args()

    # 표본만큼 생성 확보(이미 생성된 건은 run_generation의 resume 로직이 건너뜀).
    run_generation(args.n)

    rows = [r for r in load_jsonl(GEN_OUT) if r.get("error") is None][: args.n]
    done = already_done(VAL_OUT)
    todo = [r for r in rows if r["query_id"] not in done]
    print(f"검증 대상 {len(rows)}건, 완료 {len(done)}건, 이번 채점 {len(todo)}건")

    con = sqlite3.connect(ROOT / "reactivity_reference.db")
    cur = con.cursor()
    VAL_OUT.parent.mkdir(parents=True, exist_ok=True)
    out_f = VAL_OUT.open("a", encoding="utf-8")

    for i, r in enumerate(todo):
        context_ids = r.get("context_ids", [])
        if context_ids:
            q = "select chunk_id, text from rag_chunks where chunk_id in ({})".format(
                ",".join("?" * len(context_ids))
            )
            contexts_by_id = dict(cur.execute(q, context_ids).fetchall())
        else:
            contexts_by_id = {}

        t0 = time.perf_counter()
        try:
            large = EV.judge(r, contexts_by_id)
            large_error = None
        except Exception as e:  # noqa: BLE001
            large = {"predicted_verdict": None, "faithful": None, "unsupported_claims": None}
            large_error = f"{type(e).__name__}: {str(e)[:300]}"
        large_latency = round(time.perf_counter() - t0, 3)

        t0 = time.perf_counter()
        try:
            cascade = CJ.judge_cascade(r, contexts_by_id)
            cascade_error = None
        except Exception as e:  # noqa: BLE001
            cascade = {"predicted_verdict": None, "faithful": None, "unsupported_claims": None,
                       "judge_tier": "error", "judge_reason": str(e)[:200]}
            cascade_error = f"{type(e).__name__}: {str(e)[:300]}"
        cascade_latency = round(time.perf_counter() - t0, 3)

        rec = {
            "query_id": r["query_id"],
            "matrix_verdict": r.get("matrix_verdict"),
            "cameo_category": r.get("cameo_category"),
            "large_predicted_verdict": large.get("predicted_verdict"),
            "large_faithful": large.get("faithful"),
            "large_error": large_error,
            "large_latency_sec": large_latency,
            "cascade_predicted_verdict": cascade.get("predicted_verdict"),
            "cascade_faithful": cascade.get("faithful"),
            "cascade_tier": cascade.get("judge_tier"),
            "cascade_reason": cascade.get("judge_reason"),
            "cascade_error": cascade_error,
            "cascade_latency_sec": cascade_latency,
        }
        out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        out_f.flush()
        print(f"[{i + 1}/{len(todo)}] {r['query_id']} tier={rec['cascade_tier']} "
              f"large_v={rec['large_predicted_verdict']} cascade_v={rec['cascade_predicted_verdict']} "
              f"large_f={rec['large_faithful']} cascade_f={rec['cascade_faithful']}", flush=True)

    out_f.close()
    con.close()
    print(f"저장: {VAL_OUT}")


if __name__ == "__main__":
    main()
