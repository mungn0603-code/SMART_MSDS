"""v4 전수실행(2,142건)에서 faithful=False였던 203건만 v5 프롬프트로 재생성·재채점.

전체 재실행이 아니라 틀렸던 건만 표적 재시도한다(사용자 지시). run_cameo_full.py의
_call_generate/_call_eval(스레드풀 동시실행, judge에 cameo_context 포함)을 그대로
재사용하고, run_cameo_context_pilot의 build_prompt/SYSTEM_PROMPT(v5)만 새로 반영된다.
결과는 별도 파일(generation_cameo_v5_retry.jsonl/eval_cameo_v5_retry.jsonl)에 쓴다 —
개선 확인 전까지 기존 v4 전수 결과(generation_cameo_full.jsonl/eval_cameo_full.jsonl)는
건드리지 않는다. 개선되면 merge_v5_retry.py(별도)로 반영.

  python 04_rag_agent/run_cameo_v5_retry.py --workers 8
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))

import cameo_group_lookup as CL  # noqa: E402
import generate_baseline as GB  # noqa: E402
from run_cameo_context_pilot import build_prompt, PROMPT_VERSION  # noqa: E402
from run_cameo_full import (  # noqa: E402
    _call_generate,
    _call_eval,
    already_done,
    load_jsonl,
)
from concurrent.futures import ThreadPoolExecutor, as_completed  # noqa: E402

FROZEN_PATH = ROOT / "results" / "frozen_retrieval_top10.jsonl"
TARGET_IDS_PATH = ROOT / "results" / "unfaithful_v4_ids.json"
GEN_OUT = ROOT / "results" / "generation_cameo_v5_retry.jsonl"
EVAL_OUT = ROOT / "results" / "eval_cameo_v5_retry.jsonl"


def run(workers: int) -> None:
    target_ids = set(json.loads(TARGET_IDS_PATH.read_text(encoding="utf-8")))
    rows = {r["query_id"]: r for r in load_jsonl(FROZEN_PATH)}
    done = already_done(GEN_OUT)
    todo = [rows[qid] for qid in target_ids if qid not in done]
    print(f"대상 {len(target_ids)}건, 완료 {len(done)}건, 이번 생성 {len(todo)}건 (workers={workers}, prompt={PROMPT_VERSION})")

    con = sqlite3.connect(ROOT / "data" / "reactivity_reference.db")
    cur = con.cursor()
    prepared = []
    for r in todo:
        cameo = CL.lookup(cur, r["cas_a"], r["cas_b"])
        cameo_ctx = CL.format_context(cameo, r["name_a"], r["name_b"], detailed=True)
        chunk_ids = [c["chunk_id"] for c in r["retrieved"]]
        texts = GB.load_texts(cur, chunk_ids)
        contexts = [{"chunk_id": cid, "text": texts.get(cid, "")} for cid in chunk_ids]
        prompt = build_prompt(r["query"], cameo_ctx, contexts)
        prepared.append((r, cameo.category, cameo_ctx, prompt))
    con.close()

    GEN_OUT.parent.mkdir(parents=True, exist_ok=True)
    out_f = GEN_OUT.open("a", encoding="utf-8")
    n_done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_call_generate, r, cat, ctx, p): r for r, cat, ctx, p in prepared}
        for fut in as_completed(futures):
            rec = fut.result()
            n_done += 1
            out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out_f.flush()
            print(f"[gen {n_done}/{len(todo)}] {rec['query_id']} {'실패' if rec['error'] else '완료'} "
                  f"({rec['latency_sec']}s)", flush=True)
    out_f.close()

    # 채점
    gen_rows = [r for r in load_jsonl(GEN_OUT) if r.get("error") is None]
    eval_done = already_done(EVAL_OUT)
    eval_todo = [r for r in gen_rows if r["query_id"] not in eval_done]
    print(f"채점 대상 {len(gen_rows)}건, 완료 {len(eval_done)}건, 이번 채점 {len(eval_todo)}건")

    con = sqlite3.connect(ROOT / "data" / "reactivity_reference.db")
    cur = con.cursor()
    eval_prepared = []
    for r in eval_todo:
        context_ids = r.get("context_ids", [])
        if context_ids:
            q = "select chunk_id, text from rag_chunks where chunk_id in ({})".format(
                ",".join("?" * len(context_ids))
            )
            contexts_by_id = dict(cur.execute(q, context_ids).fetchall())
        else:
            contexts_by_id = {}
        contexts_by_id["__cameo_context__"] = r.get("cameo_context", "")
        eval_prepared.append((r, contexts_by_id))
    con.close()

    EVAL_OUT.parent.mkdir(parents=True, exist_ok=True)
    out_f = EVAL_OUT.open("a", encoding="utf-8")
    n_done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_call_eval, r, ctx): r for r, ctx in eval_prepared}
        for fut in as_completed(futures):
            rec = fut.result()
            n_done += 1
            out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out_f.flush()
            print(f"[eval {n_done}/{len(eval_todo)}] {rec['query_id']} "
                  f"{'실패' if rec['judge_error'] else '완료'} ({rec['judge_latency_sec']}s)", flush=True)
    out_f.close()
    print(f"저장: {GEN_OUT}")
    print(f"저장: {EVAL_OUT}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    run(args.workers)


if __name__ == "__main__":
    main()
