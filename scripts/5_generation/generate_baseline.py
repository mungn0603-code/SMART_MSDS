"""STEP 2/3 (Generation 평가 파이프라인): 고정 Retrieval(freeze_retrieval.py 산출물) 위에서
단일 LLM·단일 최소 프롬프트로 baseline 답변을 생성한다.

  Fixed Retrieval Top-k(STEP1 산출물) -> LLM(temperature=0) -> Final Answer

재검색 없음 — 각 질의의 retrieved chunk_id는 STEP1에서 이미 확정됐고, 여기서는 그
chunk_id로 본문을 조회해 프롬프트에 넣기만 한다. 재개 가능: 이미 생성된 query_id는
건너뛴다(장시간 배치 중 크래시/중단 대비, 매 건 즉시 flush).

  python scripts/generate_baseline.py            # 전체 2,160건(이어서 실행 가능)
  python scripts/generate_baseline.py --n 20      # 파일럿
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))
import llm as L  # noqa: E402

DB_PATH = ROOT / "data" / "reactivity_reference.db"
FROZEN_PATH = ROOT / "results" / "frozen_retrieval_top10.jsonl"
OUT_PATH = ROOT / "results" / "generation_baseline.jsonl"

PROMPT_VERSION = "baseline_v1"
MAX_TOKENS = 8192
# 2026-08-29 Upstage 전환: 1500 -> 8192. NVIDIA NIM 은 reasoning_budget(16384) 이
# max_tokens 와 별개라 1500 이 본문 전용 예산이었으나, solar-pro3 는 추론 토큰이
# max_tokens 를 같이 소비한다. 1500 유지 시 20건 중 9건이 상한에 걸리고 3건은 본문이
# 빈 문자열로 나왔다(측정). 8192 에서는 12/12 finish_reason=stop, compl p90=2371 max=6852.
REASONING_EFFORT = "high"  # Upstage solar-pro3: 추론 예산 60%. temperature 는 보내지 않음

SYSTEM_PROMPT = (
    "당신은 KOSHA MSDS 데이터를 근거로 화학물질 혼합/공동취급 위험성을 평가하는 보조자다.\n"
    "아래 [근거]에 제시된 내용만 사용해 답하라. 근거에 없는 내용은 추측하지 말고, 근거가\n"
    "부족하면 반드시 \"제공된 자료만으로는 판단할 근거가 부족합니다\"라고만 답하라(Abstain).\n"
    "답변 마지막 줄에 실제로 사용한 근거 번호를 \"[사용한 근거: 1, 3]\" 형식으로 밝혀라\n"
    "(Abstain한 경우 \"[사용한 근거: 없음]\"). 한국어로, 3~5문장 이내로 간결하게 답하라.\n"
)


def build_prompt(question: str, contexts: list[dict]) -> str:
    ev = "\n\n".join(f"[근거 {i + 1}] (chunk_id={c['chunk_id']})\n{c['text']}" for i, c in enumerate(contexts))
    return f"{SYSTEM_PROMPT}\n\n{ev}\n\n[질문]\n{question}\n\n[답변]"


def load_texts(cur: sqlite3.Cursor, chunk_ids: list[str]) -> dict[str, str]:
    q = "select chunk_id, text from rag_chunks where chunk_id in ({})".format(
        ",".join("?" * len(chunk_ids))
    )
    return dict(cur.execute(q, chunk_ids).fetchall())


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
    ap.add_argument("--n", type=int, default=None, help="처리할 최대 건수(미지정시 전체, 이미 완료된 건 제외)")
    args = ap.parse_args()

    if not FROZEN_PATH.exists():
        raise SystemExit(f"{FROZEN_PATH} 없음. freeze_retrieval.py 먼저 실행할 것.")
    with FROZEN_PATH.open(encoding="utf-8") as f:
        rows = [json.loads(line) for line in f]

    done = already_done(OUT_PATH)
    todo = [r for r in rows if r["query_id"] not in done]
    if args.n is not None:
        todo = todo[: args.n]
    print(f"전체 {len(rows)}건, 완료 {len(done)}건, 이번 실행 {len(todo)}건")

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out_f = OUT_PATH.open("a", encoding="utf-8")

    for i, r in enumerate(todo):
        chunk_ids = [c["chunk_id"] for c in r["retrieved"]]
        texts = load_texts(cur, chunk_ids)
        contexts = [{"chunk_id": cid, "text": texts.get(cid, "")} for cid in chunk_ids]

        prompt = build_prompt(r["query"], contexts)
        t0 = time.perf_counter()
        try:
            data = L.chat(
                [{"role": "user", "content": prompt}],
                max_tokens=MAX_TOKENS,
                reasoning_effort=REASONING_EFFORT,
            )
            answer = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            error = None
        except Exception as e:  # noqa: BLE001 - 배치 중 개별 실패로 전체를 잃지 않음
            answer = None
            usage = {}
            error = f"{type(e).__name__}: {str(e)[:300]}"
        latency = round(time.perf_counter() - t0, 3)

        rec = {
            "query_id": r["query_id"],
            "query": r["query"],
            "cas_a": r["cas_a"],
            "cas_b": r["cas_b"],
            "name_a": r["name_a"],
            "name_b": r["name_b"],
            "matrix_verdict": r["matrix_verdict"],
            "gold_evidence": r["gold_evidence"],
            "retrieval_status": r["retrieval_status"],
            "context_ids": chunk_ids,
            "generated_answer": answer,
            "model": L.MODEL,
            "prompt_version": PROMPT_VERSION,
            "latency_sec": latency,
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "error": error,
        }
        out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        out_f.flush()
        status = "실패" if error else "완료"
        print(f"[{i + 1}/{len(todo)}] {r['query_id']} {status} ({latency}s)", flush=True)

    out_f.close()
    con.close()
    print(f"저장: {OUT_PATH}")


if __name__ == "__main__":
    main()
