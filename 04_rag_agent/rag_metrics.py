"""Stage 4 §10 RAG 지표: Faithfulness / Context Recall / Context Precision / Answer Relevancy.

generate.py가 만든 results/rag_generation_sample.jsonl(question, answer, contexts,
reference)을 RAGAS로 채점한다.

ragas 0.4.3 packaging 문제 우회:
  ragas.llms.base가 langchain_community.chat_models.vertexai를 무조건 import하는데,
  langchain-community 0.4.x에서 그 서브모듈이 사라짐(업스트림 호환성 버그, Vertex AI는
  이 프로젝트에서 안 씀). 대형 google-cloud 의존성을 깔지 않고, 빈 스텁 모듈을
  sys.modules에 미리 넣어 import만 통과시킨다.

LLM/임베딩은 프로젝트가 이미 쓰는 것을 그대로 재사용한다(llm.py의 NVIDIA NIM,
retrieval.py의 bge-m3-ko) — RAGAS 전용 모델을 새로 고르지 않는다.
"""

from __future__ import annotations

import asyncio
import json
import sys
import types
from pathlib import Path

# --- packaging 우회: 반드시 ragas import 전에 실행 ---
_stub = types.ModuleType("langchain_community.chat_models.vertexai")


class _ChatVertexAIStub:  # pragma: no cover - 실제로 쓰이지 않음
    pass


_stub.ChatVertexAI = _ChatVertexAIStub
sys.modules["langchain_community.chat_models.vertexai"] = _stub

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import llm as L  # noqa: E402

RESULT_DIR = Path(__file__).resolve().parent / "results"
GEN_PATH = RESULT_DIR / "rag_generation_sample.jsonl"


async def run() -> list[dict]:
    from openai import AsyncOpenAI
    from ragas.embeddings.base import embedding_factory
    from ragas.llms import llm_factory
    from ragas.metrics.collections import AnswerRelevancy, ContextPrecision, ContextRecall, Faithfulness

    client = AsyncOpenAI(api_key=L.api_key(), base_url="https://integrate.api.nvidia.com/v1")
    rllm = llm_factory(L.MODEL, client=client, max_tokens=4096)
    emb = embedding_factory("huggingface", "dragonkue/BGE-m3-ko")

    faithfulness = Faithfulness(llm=rllm)
    ctx_precision = ContextPrecision(llm=rllm)
    ctx_recall = ContextRecall(llm=rllm)
    answer_relevancy = AnswerRelevancy(llm=rllm, embeddings=emb)

    with GEN_PATH.open(encoding="utf-8") as f:
        records = [json.loads(line) for line in f]

    async def score_with_retry(coro_fn, tries: int = 3):
        for attempt in range(tries):
            try:
                return (await coro_fn()).value
            except Exception:
                if attempt == tries - 1:
                    raise
                await asyncio.sleep(2**attempt * 3)

    # 병렬화(asyncio.gather) 3회 연속 시도 — 임베딩 락 유무와 무관하게 항상 시작 직후
    # Segmentation Fault. 이 환경(torch+faiss+kiwipiepy가 이미 로드된 프로세스에서
    # asyncio 동시성)은 병렬 실행 자체를 못 버티는 것으로 판단, 순차 실행으로 되돌림.
    # 느리지만(샘플당 4개 지표 순차 호출) 이 방식만 재현 가능하게 성공했음(n=7 두 번 확인).
    rows = []
    for i, r in enumerate(records):
        q, ans, ctxs, ref = r["question"], r["answer"], r["contexts"], r["reference"]
        try:
            f_score = await score_with_retry(
                lambda: faithfulness.ascore(user_input=q, response=ans, retrieved_contexts=ctxs)
            )
            cp_score = await score_with_retry(
                lambda: ctx_precision.ascore(user_input=q, reference=ref, retrieved_contexts=ctxs)
            )
            cr_score = await score_with_retry(
                lambda: ctx_recall.ascore(user_input=q, retrieved_contexts=ctxs, reference=ref)
            )
            ar_score = await score_with_retry(lambda: answer_relevancy.ascore(user_input=q, response=ans))
        except Exception as e:  # noqa: BLE001
            print(f"[{i + 1}/{len(records)}] {r['name_a']}+{r['name_b']} 실패: {type(e).__name__}: {e}", flush=True)
            continue
        rows.append(
            {
                "query_id": r["query_id"],
                "name_a": r["name_a"],
                "name_b": r["name_b"],
                "faithfulness": f_score,
                "context_precision": cp_score,
                "context_recall": cr_score,
                "answer_relevancy": ar_score,
            }
        )
        print(
            f"[{i + 1}/{len(records)}] {r['name_a']}+{r['name_b']} "
            f"faith={f_score:.3f} ctx_prec={cp_score:.3f} ctx_rec={cr_score:.3f} ans_rel={ar_score:.3f}",
            flush=True,
        )
    return rows


def main() -> None:
    rows = asyncio.run(run())
    if not rows:
        raise SystemExit("채점된 레코드 없음")

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULT_DIR / "rag_metrics.csv"
    cols = ["query_id", "name_a", "name_b", "faithfulness", "context_precision", "context_recall", "answer_relevancy"]
    import csv

    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    metric_keys = ["faithfulness", "context_precision", "context_recall", "answer_relevancy"]
    avg = {k: sum(r[k] for r in rows) / len(rows) for k in metric_keys}
    print(f"\n=== 평균 (n={len(rows)}) ===")
    for k, v in avg.items():
        print(f"{k}: {v:.4f}")
    print(f"\n저장: {out_path}")


if __name__ == "__main__":
    main()
