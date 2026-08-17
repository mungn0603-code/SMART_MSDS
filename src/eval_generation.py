"""STEP 4 (Generation 평가 파이프라인): generate_baseline.py 산출물을 채점한다.

두 갈래로 나눠 계산한다(불필요한 LLM 호출을 줄이기 위해 규칙 기반으로 되는 것은
규칙으로 끝낸다 — RAGAS 전체 재도입/멀티스텝 CoT 없음):

규칙 기반(LLM 호출 없음):
  - abstained            : 고정 Abstain 문구 포함 여부(생성 프롬프트가 정확한 문구를 강제함)
  - cited_chunk_ids       : 답변 끝의 "[사용한 근거: N, M]" 표시를 context_ids로 역매핑
  - evidence_precision/recall : cited_chunk_ids vs gold_evidence
  - abstention_bucket     : retrieval_status(성공/실패) x abstained(했는가) 4분면
                            (STEP5 Retrieval x Generation matrix의 재료)

LLM 판정(1건당 1회, 같은 모델, 짧은 분류 호출 — 답변 생성보다 훨씬 저비용):
  - predicted_verdict     : 답변이 실제로 내린 판정(Compatible/Caution/Incompatible/Abstain)
  - faithful              : 답변의 모든 주장이 제공된 근거로 뒷받침되는가
  - unsupported_claims    : 근거 밖 주장 요약(hallucination 탐지)

Answer Correctness = predicted_verdict == matrix_verdict (Abstain 답변은 별도 집계,
정오 판정 대상이 아니라 Abstention 적절성 쪽으로 감).

  python src/eval_generation.py            # 전체(이어서 실행 가능)
  python src/eval_generation.py --n 20      # 파일럿
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import llm as L  # noqa: E402

GEN_PATH = ROOT / "results" / "generation_baseline.jsonl"
OUT_PATH = ROOT / "results" / "eval_generation.jsonl"

ABSTAIN_PHRASE = "제공된 자료만으로는 판단할 근거가 부족합니다"
CITED_RE = re.compile(r"\[사용한\s*근거\s*:\s*([^\]]*)\]")

JUDGE_MAX_TOKENS = 400
JUDGE_REASONING_BUDGET = 1024  # 분류 전용 — 생성 호출(4096)보다 낮춰 지연 단축

JUDGE_PROMPT = """당신은 화학물질 위험성 평가 답변을 채점하는 심사자다. 아래 [근거]만이
사실 판단의 근거이며, 그 외 너의 지식으로 사실 여부를 판단하지 마라(근거에 없으면
"근거 밖"으로 간주).

[근거]
{evidence}

[질문]
{question}

[답변]
{answer}

다음을 판정해 오직 JSON 한 줄로만 답하라(다른 텍스트 금지):
{{"predicted_verdict": "Compatible|Caution|Incompatible|Abstain",
  "faithful": true|false,
  "unsupported_claims": "근거로 뒷받침되지 않는 주장을 요약, 없으면 빈 문자열"}}

predicted_verdict 기준: 답변이 "함께 취급/보관 가능·안전"이라 결론지으면 Compatible,
"주의/조건부 가능"이면 Caution, "위험/분리·금지"면 Incompatible, 답변이 판단을
보류(근거 부족 등)하면 Abstain."""


def parse_cited(answer: str, context_ids: list[str]) -> list[str]:
    m = CITED_RE.search(answer or "")
    if not m:
        return []
    body = m.group(1).strip()
    if not body or "없음" in body:
        return []
    out = []
    for tok in re.findall(r"\d+", body):
        i = int(tok) - 1
        if 0 <= i < len(context_ids):
            out.append(context_ids[i])
    return out


def rule_based(rec: dict) -> dict:
    answer = rec.get("generated_answer") or ""
    context_ids = rec.get("context_ids", [])
    gold = set(rec.get("gold_evidence", []))
    cited = parse_cited(answer, context_ids)
    cited_set = set(cited)
    # 진단용 참고치일 뿐 — LLM이 고정 문구를 그대로 안 쓰고 풀어 쓰는 경우가 있어(예:
    # "...같이 보관해도 안전한지 판단할 근거가 부족합니다") 정확 문자열 매칭으론 놓친다.
    # 실제 abstain 판정은 judge()의 predicted_verdict=="Abstain"을 권위 있는 신호로 쓴다.
    abstained_lexical = ABSTAIN_PHRASE in answer

    precision = len(cited_set & gold) / len(cited_set) if cited_set else None
    recall = len(cited_set & gold) / len(gold) if gold else None

    return {
        "abstained_lexical": abstained_lexical,
        "cited_chunk_ids": cited,
        "evidence_precision": precision,
        "evidence_recall": recall,
    }


def abstention_bucket(abstained: bool, retrieval_status: str) -> str:
    if abstained and retrieval_status == "miss":
        return "appropriate_abstain"
    if abstained and retrieval_status == "hit":
        return "over_abstain"
    if not abstained and retrieval_status == "miss":
        return "answered_without_evidence"
    return "answered_with_evidence"


def judge(rec: dict, contexts_by_id: dict[str, str], *, model: str = L.MODEL, reasoning_budget: int = JUDGE_REASONING_BUDGET) -> dict:
    """model/reasoning_budget override는 Cascade Judge의 Small Judge 호출용(cascade_judge.py).
    기본값은 기존 Large Judge와 동일 — 프롬프트·파싱·출력 schema는 절대 바꾸지 않는다.
    """
    evidence = "\n\n".join(
        f"[근거 {i + 1}] {contexts_by_id.get(cid, '')}" for i, cid in enumerate(rec.get("context_ids", []))
    )
    prompt = JUDGE_PROMPT.format(evidence=evidence, question=rec["query"], answer=rec.get("generated_answer") or "")
    data = L.chat(
        [{"role": "user", "content": prompt}],
        model=model,
        max_tokens=JUDGE_MAX_TOKENS,
        reasoning_budget=reasoning_budget,
        temperature=0.0,
    )
    text = data["choices"][0]["message"]["content"]
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError(f"judge 응답에서 JSON을 찾지 못함: {text[:200]}")
    parsed = json.loads(m.group(0))
    return {
        "predicted_verdict": parsed.get("predicted_verdict"),
        "faithful": parsed.get("faithful"),
        "unsupported_claims": parsed.get("unsupported_claims", ""),
    }


def cas_in_text(cas: str, text: str) -> bool:
    return bool(cas) and cas in (text or "")


def substance_confused(gen_rec: dict, eval_rec: dict) -> bool | None:
    """cited_chunk_ids 중 cas_a/cas_b 어느 쪽에도 속하지 않는 근거를 인용했는가(물질 혼동 진단).

    chunk_id 형식이 sec::{CAS}::{section} 이므로 문자열 매칭만으로 판정 가능(추가 LLM 호출 없음).
    Abstain(cited 없음)이면 해당 없음 -> None.

    원래 run_v2_pilot.py(prompt v2/v2.1 실험, archive됨)에 있었으나 CAMEO-context 파이프라인
    (run_cameo_context_pilot.py/run_cameo_full.py)이 지금도 이 함수를 쓰고 있어 여기로 옮김.
    """
    cited = eval_rec.get("cited_chunk_ids") or []
    if not cited:
        return None
    cas_a, cas_b = gen_rec.get("cas_a"), gen_rec.get("cas_b")
    return any(not (cas_in_text(cas_a, cid) or cas_in_text(cas_b, cid)) for cid in cited)


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
    ap.add_argument("--n", type=int, default=None)
    args = ap.parse_args()

    if not GEN_PATH.exists():
        raise SystemExit(f"{GEN_PATH} 없음. generate_baseline.py 먼저 실행할 것.")
    with GEN_PATH.open(encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    rows = [r for r in rows if r.get("error") is None]  # 생성 실패 건은 채점 대상 아님

    done = already_done(OUT_PATH)
    todo = [r for r in rows if r["query_id"] not in done]
    if args.n is not None:
        todo = todo[: args.n]
    print(f"채점 대상 {len(rows)}건, 완료 {len(done)}건, 이번 실행 {len(todo)}건")

    import sqlite3

    con = sqlite3.connect(ROOT / "data" / "reactivity_reference.db")
    cur = con.cursor()

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out_f = OUT_PATH.open("a", encoding="utf-8")

    for i, r in enumerate(todo):
        rb = rule_based(r)

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
            jr = judge(r, contexts_by_id)
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
            "abstention_bucket": abstention_bucket(abstained, r.get("retrieval_status")),
            "answer_correct": answer_correct,
            "judge_latency_sec": latency,
            "judge_error": error,
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
