"""Stage 4 §10 생성 계층 파일럿: 검색 -> LLM 답변 생성 -> RAGAS 평가용 레코드 저장.

RAG 지표(Faithfulness/Context Recall/Context Precision/Answer Relevancy) 측정 전
반드시 필요한 (question, answer, contexts, reference) 4종을 만든다.

- question : gold_pair.jsonl 의 template_idx=0(기존 제품형 질문) 사용
- contexts : 확정 구성(hybrid, bge-m3-ko, section, §2·§10 필터, top-10)으로 실제 검색
- answer   : 위 contexts만 근거로 LLM이 생성한 실답변 (Abstain 원칙 프롬프트 포함)
- reference: 같은 쌍의 gold_section 전체(§2·§10 완전근거)로 생성한 오라클 답변
             (사람이 작성한 정답이 없어 대체 — 한계는 HANDOFF/decisions.md에 명시)

표본은 카테고리(Incompatible/Caution/Compatible) 균형표집, 기본 15건(파일럿 규모).
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import llm as L  # noqa: E402
import retrieval as R  # noqa: E402

DB_PATH = ROOT / "reactivity_reference.db"
EVAL_DIR = Path(__file__).resolve().parent / "evalset"
OUT_DIR = Path(__file__).resolve().parent / "results"

SEED = 42
TOPK = 10
SECTIONS = {2, 10}
MODEL = "bge-m3-ko"

SYSTEM_PROMPT = (
    "당신은 KOSHA MSDS 데이터를 근거로 화학물질 혼합/공동취급 위험성을 평가하는 보조자다.\n"
    "아래 [근거]에 제시된 내용만 사용해 답하라. 근거에 없는 내용은 추측하지 말고, 근거가\n"
    "부족하면 반드시 \"제공된 자료만으로는 판단할 근거가 부족합니다\"라고만 답하라(Abstain).\n"
    "근거등급(법령 > 권고 > 참고자료 순으로 신뢰도가 높음)을 알고 있다면 그 우선순위를\n"
    "반영해 답하라. 한국어로, 3~5문장 이내로 간결하게 답하라.\n"
)


def build_prompt(question: str, contexts: list[str], *, allow_abstain: bool = True) -> str:
    ev = "\n\n".join(f"[근거 {i + 1}]\n{c}" for i, c in enumerate(contexts))
    sys_p = SYSTEM_PROMPT
    if not allow_abstain:
        sys_p = sys_p.replace(
            "근거가\n부족하면 반드시 \"제공된 자료만으로는 판단할 근거가 부족합니다\"라고만 답하라(Abstain).",
            "아래 근거는 두 물질의 GHS 분류·피해야 할 물질 정보를 모두 포함한 완전한 근거이니\n"
            "Abstain하지 말고 반드시 판단을 내려라.",
        )
    return f"{sys_p}\n\n{ev}\n\n[질문]\n{question}\n\n[답변]"


def retrieve_one(qvec, question: str, corpus: R.Corpus, index, bm25) -> tuple[list[str], list[str]]:
    """qvec: 미리 배치 계산된 (1, dim) 질의 벡터. 루프 안에서 SentenceTransformer를
    반복 로드하지 않기 위해 임베딩은 호출부에서 한 번에 배치로 계산해 전달받는다
    (반복 모델 로드가 이 환경에서 Segfault를 유발하는 것으로 관측됨, HANDOFF 참고)."""
    d = R.dense_rank(index, qvec, TOPK)
    b = R.bm25_rank(bm25, [question], TOPK)
    h = R.rrf_fuse([d, b], TOPK)
    idx = [int(i) for i in h[0] if i >= 0]
    return [corpus.texts[i] for i in idx], [corpus.chunk_ids[i] for i in idx]


def sample_pairs(n: int) -> list[dict]:
    with (EVAL_DIR / "gold_pair.jsonl").open(encoding="utf-8") as f:
        rows = [json.loads(line) for line in f]
    pairs = [r for r in rows if r.get("template_idx") == 0]
    rng = random.Random(SEED)
    buckets: dict[str, list[dict]] = defaultdict(list)
    for r in pairs:
        buckets[r["matrix_verdict"]].append(r)
    per_cat = max(1, n // len(buckets))
    sample = []
    for cat in sorted(buckets):
        sample += rng.sample(buckets[cat], min(per_cat, len(buckets[cat])))
    return sample[:n]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=15, help="표본 쌍 개수(카테고리 균형표집)")
    args = ap.parse_args()

    sample = sample_pairs(args.n)
    print(f"표본 {len(sample)}건 확정 (카테고리 균형표집, seed={SEED})")

    corpus_full = R.load_corpus("section")
    keep = [i for i, m in enumerate(corpus_full.meta) if m["section"] in SECTIONS]
    corpus = R.Corpus(
        chunk_ids=[corpus_full.chunk_ids[i] for i in keep],
        texts=[corpus_full.texts[i] for i in keep],
        meta=[corpus_full.meta[i] for i in keep],
    )
    dvecs = R.embed_corpus(MODEL, "section", corpus_full)[keep]
    index = R.build_faiss(dvecs)
    tag = f"section_s{''.join(map(str, sorted(SECTIONS)))}"
    bm25 = R.build_bm25(tag, corpus)

    # 질의 임베딩은 여기서 한 번에 배치로 계산(SentenceTransformer 반복 로드 방지).
    questions = [r["query"] for r in sample]
    qvecs = R.embed_queries(MODEL, questions, "generate_q")

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "rag_generation_sample.jsonl"
    out_f = out_path.open("w", encoding="utf-8")  # 매 건 즉시 flush(크래시 대비 부분 저장)

    records = []
    for i, r in enumerate(sample):
        question = r["query"]
        contexts, ctx_ids = retrieve_one(qvecs[i : i + 1], question, corpus, index, bm25)
        answer = L.ask(build_prompt(question, contexts), max_tokens=1500, reasoning_budget=4096)

        gold_texts = []
        for cid in r["gold_section"]:
            cur.execute("select text from rag_chunks where chunk_id=?", (cid,))
            row = cur.fetchone()
            if row:
                gold_texts.append(row[0])
        reference = L.ask(
            build_prompt(question, gold_texts, allow_abstain=False),
            max_tokens=1500,
            reasoning_budget=4096,
        )

        rec = {
            "query_id": r["query_id"],
            "cas_a": r["cas_a"],
            "cas_b": r["cas_b"],
            "name_a": r["name_a"],
            "name_b": r["name_b"],
            "matrix_verdict": r["matrix_verdict"],
            "question": question,
            "answer": answer,
            "contexts": contexts,
            "context_ids": ctx_ids,
            "reference": reference,
        }
        records.append(rec)
        out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        out_f.flush()
        print(f"[{i + 1}/{len(sample)}] {r['name_a']} + {r['name_b']} 완료", flush=True)

    con.close()
    out_f.close()
    print(f"저장: {out_path} ({len(records)}건)")


if __name__ == "__main__":
    main()
