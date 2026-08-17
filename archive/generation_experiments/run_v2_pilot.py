"""Prompt v2 파일럿: STEP5 실패 샘플/정상 샘플에 v2 프롬프트로 재생성 -> 채점 -> baseline과 비교.

STEP5 핵심 발견 2가지(물질 혼동, 개별 위험->상호반응 비약)를 겨냥해 baseline 프롬프트를
최소 수정한 v2로 재실행하고, 같은 judge로 채점한 뒤 baseline 채점 결과와 나란히 비교한다.
평가 기준(judge, correctness 정의)은 바꾸지 않는다 — generate_baseline.py / eval_generation.py의
함수를 그대로 재사용.

v2.1 변경(35건 파일럿에서 물질 혼동은 해결됐으나, 정상 15건 스팟체크에서 11/15가 과잉
Abstain으로 회귀함을 확인 — "직접적인 근거 없으면 무조건 Abstain"이 §10 "피해야 할 물질"
위험군 매칭 같은 합당한 교차추론까지 차단했기 때문. v2.1은 이 교차추론은 허용하되, 근거에
없는 구체적 반응/생성물을 지어내는 것만 금지):

  python 04_rag_agent/run_v2_pilot.py --sample results/step5_failure_sample.jsonl --tag v2_1_pilot
  python 04_rag_agent/run_v2_pilot.py --sample results/step5_clean_correct_sample.jsonl --tag v2_1_clean_spotcheck
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

import llm as L  # noqa: E402
import generate_baseline as GB  # noqa: E402
import eval_generation as EV  # noqa: E402

FROZEN_PATH = HERE / "results" / "frozen_retrieval_top10.jsonl"
BASELINE_GEN = HERE / "results" / "generation_baseline.jsonl"
BASELINE_EVAL = HERE / "results" / "eval_generation.jsonl"

PROMPT_VERSION = "v2_1_pilot"

# baseline 대비 최소 추가: 물질 동일성 확인 + 상호작용 교차근거 원칙(제한적 허용) + 반응 날조 금지.
SYSTEM_PROMPT_V2 = (
    "당신은 KOSHA MSDS 데이터를 근거로 화학물질 혼합/공동취급 위험성을 평가하는 보조자다.\n"
    "아래 [근거]에 제시된 내용만 사용해 답하라. 근거에 없는 내용은 추측하지 말고, 근거가\n"
    "부족하면 반드시 \"제공된 자료만으로는 판단할 근거가 부족합니다\"라고만 답하라(Abstain).\n"
    "다음 규칙을 반드시 지켜라:\n"
    "1) 각 근거가 실제로 어느 물질(CAS/물질명)에 대한 것인지 확인하라. 근거의 CAS/물질명이\n"
    "   질문의 대상 물질과 다르면 그 근거를 해당 물질의 근거로 쓰지 마라.\n"
    "2) 두 물질 사이의 반응·혼합 위험성 판단은 다음 중 하나에 해당할 때만 허용한다:\n"
    "   (a) 한 물질의 근거에 상대 물질의 이름/CAS가 직접 언급된 경우, 또는\n"
    "   (b) 한 물질의 근거(예: 피해야 할 물질/조건)에 명시된 위험군(가연성 물질, 환원성 물질,\n"
    "       산화제, 물, 산, 금속 등)에 상대 물질이 자신의 근거상 실제로 해당하는 경우.\n"
    "   이 두 경우가 아니라 \"각자 위험하니 둘도 위험할 것\"이라는 막연한 추론은 금지한다.\n"
    "   (a)(b)에 해당해 위험성 자체는 판단하더라도, 근거에 없는 구체적 반응 생성물이나\n"
    "   반응 메커니즘(예: 특정 가스 발생, 폭발 반응 등)을 지어내지 마라 — 근거가 뒷받침하는\n"
    "   수준(예: \"~할 수 있어 위험함\")까지만 말하라. (a)(b) 어느 것도 해당하지 않으면 Abstain하라.\n"
    "답변 마지막 줄에 실제로 사용한 근거 번호를 \"[사용한 근거: 1, 3]\" 형식으로 밝혀라\n"
    "(Abstain한 경우 \"[사용한 근거: 없음]\"). 한국어로, 3~5문장 이내로 간결하게 답하라.\n"
)


def build_prompt_v2(question: str, contexts: list[dict]) -> str:
    ev = "\n\n".join(f"[근거 {i + 1}] (chunk_id={c['chunk_id']})\n{c['text']}" for i, c in enumerate(contexts))
    return f"{SYSTEM_PROMPT_V2}\n\n{ev}\n\n[질문]\n{question}\n\n[답변]"


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def cas_in_text(cas: str, text: str) -> bool:
    return bool(cas) and cas in (text or "")


def run_generation(pilot_ids: set[str], gen_out: Path) -> None:
    rows = [r for r in load_jsonl(FROZEN_PATH) if r["query_id"] in pilot_ids]
    print(f"v2 생성 대상 {len(rows)}건")

    con = sqlite3.connect(ROOT / "reactivity_reference.db")
    cur = con.cursor()
    with gen_out.open("w", encoding="utf-8") as out_f:
        for i, r in enumerate(rows):
            chunk_ids = [c["chunk_id"] for c in r["retrieved"]]
            texts = GB.load_texts(cur, chunk_ids)
            contexts = [{"chunk_id": cid, "text": texts.get(cid, "")} for cid in chunk_ids]
            prompt = build_prompt_v2(r["query"], contexts)
            t0 = time.perf_counter()
            try:
                data = L.chat(
                    [{"role": "user", "content": prompt}],
                    max_tokens=GB.MAX_TOKENS,
                    reasoning_budget=GB.REASONING_BUDGET,
                    temperature=GB.TEMPERATURE,
                )
                answer = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                error = None
            except Exception as e:  # noqa: BLE001
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
            print(f"[gen {i + 1}/{len(rows)}] {r['query_id']} {'실패' if error else '완료'} ({latency}s)", flush=True)
    con.close()


def run_eval(gen_out: Path, eval_out: Path) -> None:
    rows = [r for r in load_jsonl(gen_out) if r.get("error") is None]
    print(f"v2 채점 대상 {len(rows)}건")
    con = sqlite3.connect(ROOT / "reactivity_reference.db")
    cur = con.cursor()
    with eval_out.open("w", encoding="utf-8") as out_f:
        for i, r in enumerate(rows):
            rb = EV.rule_based(r)
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
                jr = EV.judge(r, contexts_by_id)
                error = None
            except Exception as e:  # noqa: BLE001
                jr = {"predicted_verdict": None, "faithful": None, "unsupported_claims": None}
                error = f"{type(e).__name__}: {str(e)[:300]}"
            latency = round(time.perf_counter() - t0, 3)
            matrix_verdict = r.get("matrix_verdict")
            pv = jr["predicted_verdict"]
            abstained = pv == "Abstain" if pv is not None else rb["abstained_lexical"]
            answer_correct = None if pv in (None, "Abstain") else (pv == matrix_verdict)
            rec = {
                "query_id": r["query_id"],
                "matrix_verdict": matrix_verdict,
                "retrieval_status": r.get("retrieval_status"),
                **rb,
                **jr,
                "abstained": abstained,
                "abstention_bucket": EV.abstention_bucket(abstained, r.get("retrieval_status")),
                "answer_correct": answer_correct,
                "judge_latency_sec": latency,
                "judge_error": error,
            }
            out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out_f.flush()
            print(f"[eval {i + 1}/{len(rows)}] {r['query_id']} {'실패' if error else '완료'} ({latency}s)", flush=True)
    con.close()


def substance_confused(gen_rec: dict, eval_rec: dict) -> bool | None:
    """cited_chunk_ids 중 cas_a/cas_b 어느 쪽에도 속하지 않는 근거를 인용했는가(물질 혼동 진단).

    chunk_id 형식이 sec::{CAS}::{section} 이므로 문자열 매칭만으로 판정 가능(추가 LLM 호출 없음).
    Abstain(cited 없음)이면 해당 없음 -> None.
    """
    cited = eval_rec.get("cited_chunk_ids") or []
    if not cited:
        return None
    cas_a, cas_b = gen_rec.get("cas_a"), gen_rec.get("cas_b")
    return any(not (cas_in_text(cas_a, cid) or cas_in_text(cas_b, cid)) for cid in cited)


def compare(gen_out: Path, eval_out: Path) -> None:
    base_gen = {r["query_id"]: r for r in load_jsonl(BASELINE_GEN) if r.get("error") is None}
    base_eval = {r["query_id"]: r for r in load_jsonl(BASELINE_EVAL)}
    v2_gen = {r["query_id"]: r for r in load_jsonl(gen_out) if r.get("error") is None}
    v2_eval = {r["query_id"]: r for r in load_jsonl(eval_out)}

    ids = [qid for qid in v2_gen if qid in v2_eval and qid in base_gen and qid in base_eval]
    print(f"\n비교 대상 {len(ids)}건\n")

    def summarize(tag: str, gen: dict, ev: dict) -> dict:
        n = len(ids)
        n_abstain = sum(1 for qid in ids if ev[qid]["abstained"])
        n_unfaithful = sum(1 for qid in ids if ev[qid].get("faithful") is False)
        confused = [substance_confused(gen[qid], ev[qid]) for qid in ids]
        n_confused = sum(1 for c in confused if c is True)
        n_correct = sum(1 for qid in ids if ev[qid]["answer_correct"] is True)
        n_wrong = sum(1 for qid in ids if ev[qid]["answer_correct"] is False)
        print(f"[{tag}] n={n} abstain={n_abstain} unfaithful={n_unfaithful} "
              f"substance_confused={n_confused} correct_vs_matrix={n_correct} wrong_vs_matrix={n_wrong}")
        return {"abstain": {qid: ev[qid]["abstained"] for qid in ids},
                "faithful": {qid: ev[qid].get("faithful") for qid in ids},
                "confused": {qid: c for qid, c in zip(ids, confused)}}

    base_s = summarize("baseline", base_gen, base_eval)
    v2_s = summarize("v2", v2_gen, v2_eval)

    print("\n개별 변화(다른 건만):")
    for qid in ids:
        b_ab, v_ab = base_s["abstain"][qid], v2_s["abstain"][qid]
        b_fa, v_fa = base_s["faithful"][qid], v2_s["faithful"][qid]
        b_cf, v_cf = base_s["confused"][qid], v2_s["confused"][qid]
        if (b_ab, b_fa, b_cf) != (v_ab, v_fa, v_cf):
            print(f"  {qid}: abstain {b_ab}->{v_ab} | faithful {b_fa}->{v_fa} | confused {b_cf}->{v_cf}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", default=str(HERE / "results" / "step5_failure_sample.jsonl"),
                     help="query_id 목록이 담긴 jsonl(각 줄에 최소 query_id 필드)")
    ap.add_argument("--tag", default="v2_pilot", help="출력 파일명에 쓸 태그")
    args = ap.parse_args()

    sample_path = Path(args.sample)
    gen_out = HERE / "results" / f"generation_{args.tag}.jsonl"
    eval_out = HERE / "results" / f"eval_{args.tag}.jsonl"

    ids = {r["query_id"] for r in load_jsonl(sample_path)}
    if not gen_out.exists():
        run_generation(ids, gen_out)
    else:
        print(f"{gen_out} 이미 존재 — 생성 건너뜀(다시 하려면 파일 삭제)")
    if not eval_out.exists():
        run_eval(gen_out, eval_out)
    else:
        print(f"{eval_out} 이미 존재 — 채점 건너뜀(다시 하려면 파일 삭제)")
    compare(gen_out, eval_out)


if __name__ == "__main__":
    main()
