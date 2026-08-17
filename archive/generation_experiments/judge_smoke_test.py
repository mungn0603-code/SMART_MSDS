"""STEP4 새 Judge 후보(meta/llama-3.1-8b-instruct) smoke test(10~20건).

llm.py/eval_generation.py는 건드리지 않는다 — eval_generation.judge()가 이미 지원하는
model/reasoning_budget override만 써서 기존 Judge interface(JUDGE_PROMPT, 파싱, 출력
schema) 그대로 재사용한다. 기존 Large Judge 결과(results/eval_generation.jsonl,
2,158건 전수 채점 완료)가 이미 있으므로 같은 query_id로 직접 비교한다(별도 ground
truth 생성 불필요).

확인 항목: API 호출 성공 / JSON 파싱 성공(judge_error) / 출력 schema 정상 /
판정이 명백히 이상하지 않은지 / 기존 large judge 결과와의 category·faithful 일치.

  python 04_rag_agent/judge_smoke_test.py --n 15
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

CANDIDATE_MODEL = "meta/llama-3.1-8b-instruct"

GEN_PATH = HERE / "results" / "generation_baseline.jsonl"
LARGE_EVAL_PATH = HERE / "results" / "eval_generation.jsonl"
OUT_PATH = HERE / "results" / "judge_smoke_test_llama31_8b.jsonl"


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=15)
    args = ap.parse_args()

    gen_rows = {r["query_id"]: r for r in load_jsonl(GEN_PATH) if r.get("error") is None}
    large_rows = {r["query_id"]: r for r in load_jsonl(LARGE_EVAL_PATH)}
    # 기존 Large Judge 결과가 있는 건 중에서만 표본 추출 -> 바로 비교 가능.
    ids = [qid for qid in gen_rows if qid in large_rows][: args.n]
    print(f"smoke test 대상 {len(ids)}건 (모델={CANDIDATE_MODEL})")

    con = sqlite3.connect(ROOT / "reactivity_reference.db")
    cur = con.cursor()

    results = []
    with OUT_PATH.open("w", encoding="utf-8") as out_f:
        for i, qid in enumerate(ids):
            r = gen_rows[qid]
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
                jr = EV.judge(r, contexts_by_id, model=CANDIDATE_MODEL, reasoning_budget=None)
                error = None
            except Exception as e:  # noqa: BLE001
                jr = {"predicted_verdict": None, "faithful": None, "unsupported_claims": None}
                error = f"{type(e).__name__}: {str(e)[:300]}"
            latency = round(time.perf_counter() - t0, 3)

            large = large_rows[qid]
            rec = {
                "query_id": qid,
                "matrix_verdict": r.get("matrix_verdict"),
                "candidate_predicted_verdict": jr.get("predicted_verdict"),
                "candidate_faithful": jr.get("faithful"),
                "candidate_unsupported_claims": jr.get("unsupported_claims"),
                "candidate_judge_error": error,
                "candidate_latency_sec": latency,
                "large_predicted_verdict": large.get("predicted_verdict"),
                "large_faithful": large.get("faithful"),
                "category_agree": (
                    None if error else jr.get("predicted_verdict") == large.get("predicted_verdict")
                ),
                "faithful_agree": (
                    None if error else jr.get("faithful") == large.get("faithful")
                ),
            }
            results.append(rec)
            out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out_f.flush()
            print(f"[{i + 1}/{len(ids)}] {qid} error={error!r} "
                  f"cand={rec['candidate_predicted_verdict']}/{rec['candidate_faithful']} "
                  f"large={rec['large_predicted_verdict']}/{rec['large_faithful']} "
                  f"({latency}s)", flush=True)
    con.close()

    n = len(results)
    n_error = sum(1 for r in results if r["candidate_judge_error"] is not None)
    n_ok = n - n_error
    n_cat_agree = sum(1 for r in results if r["category_agree"] is True)
    n_faith_agree = sum(1 for r in results if r["faithful_agree"] is True)
    n_faith_miss = sum(
        1 for r in results if r["large_faithful"] is False and r["candidate_faithful"] is True
    )
    lat = [r["candidate_latency_sec"] for r in results if r["candidate_judge_error"] is None]

    print("\n=== 요약 ===")
    print(f"전체 {n}건, API/JSON 실패(judge_error) {n_error}건, 성공 {n_ok}건")
    if n_ok:
        print(f"category(predicted_verdict) 일치: {n_cat_agree}/{n_ok}")
        print(f"faithful 일치: {n_faith_agree}/{n_ok}")
        print(f"large=unfaithful인데 candidate=faithful(놓침): {n_faith_miss}/{n_ok}")
        print(f"평균 latency: {sum(lat) / len(lat):.2f}s (min={min(lat):.2f}s max={max(lat):.2f}s)")
    print(f"저장: {OUT_PATH}")


if __name__ == "__main__":
    main()
