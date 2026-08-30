"""STEP 5: Retrieval x Generation 분리 분석.

generate_baseline.py(STEP3) + eval_generation.py(STEP4) 산출물을 join해서:
  1) 4-bucket 표(count/ratio) — Gold evidence retrieved x {Correct, Over-abstain, Wrong},
     Gold evidence not retrieved x {Answer/Abstain}
  2) 전체 요약 지표 7종
  3) "Retrieval Hit + Generation Failure"(over-abstain/wrong/unsupported) 대표 사례를
     사람이 직접 읽고 오류유형을 분류할 수 있도록 근거 원문까지 포함해 샘플링·저장

주의(사용자 지시, 2026-08-09): matrix_verdict는 CAMEO matrix 기반 참고/diagnostic 값이다.
이 스크립트가 계산하는 "Wrong/Correct"는 matrix_verdict 대비 일치 여부일 뿐 —
단독 최종 정답으로 취급하지 않는다. 최종 correctness는 대표 사례를 gold_evidence
원문과 대조해 사람이 직접 검증한다(이 스크립트는 그 검증에 필요한 자료만 준비).
이 단계에서 Retrieval을 다시 튜닝하지 않는다(joined 재계산 없음, STEP1 산출물 그대로 사용).
"""

from __future__ import annotations

import json
import random
import sqlite3
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

GEN_PATH = ROOT / "results" / "generation_baseline.jsonl"
EVAL_PATH = ROOT / "results" / "eval_generation.jsonl"
OUT_SUMMARY = ROOT / "results" / "step5_summary.json"
OUT_SAMPLE = ROOT / "results" / "step5_failure_sample.jsonl"

SEED = 42
N_SAMPLE = 30  # >=20 요구, 버킷별 배분 후 여유 있게


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def bucket4(gen: dict, ev: dict) -> str:
    """사용자 지정 4-bucket. retrieval_status는 STEP1 고정값을 그대로 신뢰(재계산 안 함)."""
    if gen["retrieval_status"] != "hit":
        return "no_evidence_retrieved__answer_or_abstain"
    if ev["abstained"]:
        return "evidence_retrieved__over_abstain"
    if ev["answer_correct"] is True:
        return "evidence_retrieved__correct"
    if ev["answer_correct"] is False:
        return "evidence_retrieved__wrong"
    return "evidence_retrieved__unclassified"  # predicted_verdict/judge 실패 등 예외


def main() -> None:
    if not GEN_PATH.exists() or not EVAL_PATH.exists():
        raise SystemExit("generate_baseline.py / eval_generation.py 결과가 모두 있어야 함")

    gen_rows = {r["query_id"]: r for r in load_jsonl(GEN_PATH) if r.get("error") is None}
    eval_rows = {r["query_id"]: r for r in load_jsonl(EVAL_PATH)}
    ids = [qid for qid in gen_rows if qid in eval_rows]
    missing_eval = len(gen_rows) - len(ids)
    print(f"generation {len(gen_rows)}건, eval {len(eval_rows)}건, join {len(ids)}건(eval 누락 {missing_eval})")

    buckets: dict[str, list[str]] = {}
    for qid in ids:
        b = bucket4(gen_rows[qid], eval_rows[qid])
        buckets.setdefault(b, []).append(qid)

    n = len(ids)
    bucket_table = {k: {"count": len(v), "ratio": round(len(v) / n, 4)} for k, v in buckets.items()}

    n_hit = sum(1 for qid in ids if gen_rows[qid]["retrieval_status"] == "hit")
    n_abstained = sum(1 for qid in ids if eval_rows[qid]["abstained"])
    n_over_abstain = len(buckets.get("evidence_retrieved__over_abstain", []))
    n_wrong = len(buckets.get("evidence_retrieved__wrong", []))
    n_unfaithful = sum(1 for qid in ids if eval_rows[qid].get("faithful") is False)
    cited_prec = [eval_rows[qid]["evidence_precision"] for qid in ids if eval_rows[qid]["evidence_precision"] is not None]
    cited_rec = [eval_rows[qid]["evidence_recall"] for qid in ids if eval_rows[qid]["evidence_recall"] is not None]
    n_answered = sum(1 for qid in ids if not eval_rows[qid]["abstained"])
    n_correct = sum(1 for qid in ids if eval_rows[qid]["answer_correct"] is True)

    summary = {
        "n_joined": n,
        "retrieval_hit_rate": round(n_hit / n, 4),
        "generation_correctness_vs_matrix_diagnostic": round(n_correct / n_answered, 4) if n_answered else None,
        "over_abstention_rate": round(n_abstained / n, 4),
        "wrong_answer_rate_vs_matrix_diagnostic": round(n_wrong / n_answered, 4) if n_answered else None,
        "unsupported_answer_rate": round(n_unfaithful / n, 4),
        "citation_evidence_precision_mean": round(sum(cited_prec) / len(cited_prec), 4) if cited_prec else None,
        "citation_evidence_recall_mean": round(sum(cited_rec) / len(cited_rec), 4) if cited_rec else None,
        "retrieval_success_generation_failure_ratio": round((n_over_abstain + n_wrong) / n_hit, 4) if n_hit else None,
        "bucket4": bucket_table,
    }
    OUT_SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    # 대표 실패 사례 샘플링: Retrieval Hit + Generation Failure(over-abstain/wrong)를 우선,
    # 참고로 unsupported(faithful=False)인데 verdict는 correct로 잡힌 애매 사례도 소수 포함.
    rng = random.Random(SEED)
    failure_ids = buckets.get("evidence_retrieved__over_abstain", []) + buckets.get("evidence_retrieved__wrong", [])
    unclassified_ids = buckets.get("evidence_retrieved__unclassified", [])
    unfaithful_but_correct = [
        qid for qid in buckets.get("evidence_retrieved__correct", [])
        if eval_rows[qid].get("faithful") is False
    ]

    def take(pool: list[str], k: int) -> list[str]:
        rng.shuffle(pool)
        return pool[:k]

    n_oa = len(buckets.get("evidence_retrieved__over_abstain", []))
    n_wr = len(buckets.get("evidence_retrieved__wrong", []))
    half = N_SAMPLE // 2
    sample_ids = (
        take(buckets.get("evidence_retrieved__over_abstain", [])[:], min(half, n_oa))
        + take(buckets.get("evidence_retrieved__wrong", [])[:], min(N_SAMPLE - half, n_wr))
    )
    remaining = N_SAMPLE - len(sample_ids)
    if remaining > 0:
        pool = [qid for qid in failure_ids if qid not in sample_ids]
        sample_ids += take(pool, min(remaining, len(pool)))
    remaining = N_SAMPLE - len(sample_ids)
    if remaining > 0 and unclassified_ids:
        sample_ids += take(unclassified_ids[:], min(remaining, len(unclassified_ids)))
    sample_ids += take(unfaithful_but_correct[:], min(5, len(unfaithful_but_correct)))

    con = sqlite3.connect(ROOT / "data" / "reactivity_reference.db")
    cur = con.cursor()

    with OUT_SAMPLE.open("w", encoding="utf-8") as f:
        for qid in sample_ids:
            g, e = gen_rows[qid], eval_rows[qid]
            gold_ids = g.get("gold_evidence", [])
            if gold_ids:
                q = "select chunk_id, text from rag_chunks where chunk_id in ({})".format(",".join("?" * len(gold_ids)))
                gold_texts = dict(cur.execute(q, gold_ids).fetchall())
            else:
                gold_texts = {}
            ctx_ids = g.get("context_ids", [])
            if ctx_ids:
                q = "select chunk_id, text from rag_chunks where chunk_id in ({})".format(",".join("?" * len(ctx_ids)))
                ctx_texts = dict(cur.execute(q, ctx_ids).fetchall())
            else:
                ctx_texts = {}

            rec = {
                "query_id": qid,
                "bucket": bucket4(g, e),
                "query": g["query"],
                "name_a": g["name_a"],
                "name_b": g["name_b"],
                "matrix_verdict_diagnostic": g["matrix_verdict"],
                "retrieval_status": g["retrieval_status"],
                "gold_evidence": [{"chunk_id": cid, "text": gold_texts.get(cid, "")} for cid in gold_ids],
                "retrieved_context": [{"chunk_id": cid, "text": ctx_texts.get(cid, "")} for cid in ctx_ids],
                "generated_answer": g["generated_answer"],
                "cited_chunk_ids": e["cited_chunk_ids"],
                "predicted_verdict": e["predicted_verdict"],
                "faithful": e["faithful"],
                "unsupported_claims": e["unsupported_claims"],
                "evidence_precision": e["evidence_precision"],
                "evidence_recall": e["evidence_recall"],
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    con.close()
    print(f"\n샘플 {len(sample_ids)}건(over_abstain {n_oa}건 중 일부 + wrong {n_wr}건 중 일부 + 기타) 저장: {OUT_SAMPLE}")
    print(f"요약 저장: {OUT_SUMMARY}")


if __name__ == "__main__":
    main()
