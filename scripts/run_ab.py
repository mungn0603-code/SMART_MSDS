"""Stage 4 §13 실행순서 1~4단계: baseline -> 임베딩 A/B -> Reranker A/B

  python run_ab.py embedding --models bge-m3-ko --granularity both
  python run_ab.py reranker  --winner bge-m3-ko --winner-granularity section \
                             --rerankers bge-reranker-base

평가 과제 (--task)
  pair (기본, 제품 과제) : 물질 쌍의 반응성·양립성 판정. 질의당 정답청크 다수.
                           평가셋 = evalset/gold_pair.jsonl (evalset_pairs.py 생성)
  fact (부품 점검용)     : 단일물질 사실조회. 질의당 정답청크 1개.
                           평가셋 = evalset/gold_retrieval.jsonl (evalset.py 생성)

  fact 는 "검색기가 물질·항목을 제대로 찾는가"를 보는 하위 테스트이지 제품 지표가
  아니다. §11 목표치와 대조할 대상은 pair 쪽이다.

[2026-08-06 사용자 결정 — 설계문서 §1/§13 1~2단계를 대체함]
  임베딩 = bge-m3-ko, 리랭커 = bge-reranker-base 로 **A/B 없이 지정**.
  사유: 무거운 모델(KURE, bge-reranker-v2-m3) 배제. CPU 전용 환경에서 3파전
  전체 실행에 약 5.7시간이 소요된다는 실측치를 보고 사용자가 결단.
  => 이 두 모델은 "A/B 승자"가 아니라 "사용자 지정"이다. 실측 비교 근거 없음.
  --models / --rerankers 로 범위를 좁혀 실행한다. 플래그 없이 재실행하면 전체
  A/B가 그대로 돌아간다(코드 보존).

Retrieval 지표(§10): Recall@5, Recall@10, MRR, nDCG@10
  다중 정답이므로 Recall@k = (top-k 안에 든 정답 수) / (전체 정답 수).
  Recall@20 은 §10 규정 외 참고치 — §10의 k 값은 정답 1개를 전제로 잡힌 수치라
  정답 4개인 pair 과제에서 Recall@5 는 구조적으로 상한이 빡빡하다. 목표치 재조정
  판단에 필요해서 함께 낸다.

주의(§11): 목표치는 잠정치. 이 스크립트는 실측값만 출력하고 달성/미달성을 판정하지 않는다.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))
import retrieval as R  # noqa: E402

EVAL_DIR = ROOT / "data" / "evalset"
RESULT_DIR = ROOT / "results"
TOPK = 20
CAND_K = 20  # reranker 후보 수
NDCG_K = 10

TASK_FILES = {"pair": "gold_pair.jsonl", "fact": "gold_retrieval.jsonl"}


def load_gold(task: str) -> list[dict]:
    path = EVAL_DIR / TASK_FILES[task]
    if not path.exists():
        raise SystemExit(f"{path} 없음. {'evalset_pairs.py' if task == 'pair' else 'evalset.py'} 먼저 실행.")
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def metrics(ranks: np.ndarray, gold_sets: list[set[int]]) -> dict[str, float]:
    """ranks: (nq, TOPK) 문서 인덱스(-1 = 없음). gold_sets: 질의별 정답 인덱스 집합.

    Recall@k = top-k 안에 든 정답 수 / 전체 정답 수 (질의당 정답 다수)
    Hit@k    = top-k 안에 정답이 하나라도 있으면 1 (질의 단위 이진)
    """
    acc = {
        "Recall@10": 0.0, "Recall@5": 0.0, "Recall@20": 0.0,
        "Hit@5": 0.0, "Hit@10": 0.0, "MRR": 0.0, "nDCG@10": 0.0,
    }
    n = len(gold_sets)
    for i, gold in enumerate(gold_sets):
        hits = [p + 1 for p, d in enumerate(ranks[i]) if d >= 0 and int(d) in gold]
        for k in (5, 10, 20):
            acc[f"Recall@{k}"] += sum(1 for h in hits if h <= k) / len(gold)
        for k in (5, 10):
            acc[f"Hit@{k}"] += 1.0 if any(h <= k for h in hits) else 0.0
        if hits:
            acc["MRR"] += 1.0 / hits[0]
        dcg = sum(1.0 / np.log2(h + 1) for h in hits if h <= NDCG_K)
        idcg = sum(1.0 / np.log2(j + 2) for j in range(min(len(gold), NDCG_K)))
        acc["nDCG@10"] += dcg / idcg
    return {k: v / n for k, v in acc.items()}


def prepare(gran: str, gold: list[dict], task: str, sections: set[int] | None = None, corpus_tag: str | None = None):
    """sections 지정 시 검색공간을 해당 섹션으로 축소(§6 payload 의 section 필터).

    문서 벡터 캐시는 전체 코퍼스 기준이므로, 캐시를 재생성하지 않고 인덱스만 잘라 쓴다.
    corpus_tag: PHASE 5 — 426/259proposed 등 rag_corpus_membership 기준 코퍼스 선택.
    """
    corpus = R.load_corpus(gran, corpus_tag=corpus_tag)
    keep = None
    if sections:
        keep = [i for i, m in enumerate(corpus.meta) if m["section"] in sections]
        corpus = R.Corpus(
            chunk_ids=[corpus.chunk_ids[i] for i in keep],
            texts=[corpus.texts[i] for i in keep],
            meta=[corpus.meta[i] for i in keep],
        )
    pos = {cid: i for i, cid in enumerate(corpus.chunk_ids)}
    key = "gold_item" if gran == "item" else "gold_section"

    # 2026-08-28 안전장치 -> 2026-08-29 실패로 격상: pair 평가셋에 gold_evidence가 없으면
    # 아래 로직이 조용히 gold_section으로 되돌아가 **채점 기준이 느슨해진 것을 모른 채**
    # 숫자만 나온다(§10 boilerplate까지 정답으로 셈). 경고는 파이프 뒤에서 묻히므로
    # 여기서 멈춘다. evalset_pairs.py가 이제 gold_evidence를 생성하므로 정상 경로에서는
    # 발생하지 않는다 - 뜨면 평가셋이 낡은 것이다.
    if task == "pair" and gold and not any("gold_evidence" in g for g in gold):
        raise SystemExit(
            "[중단] 이 pair 평가셋에는 gold_evidence가 없다. gold_section으로 채점하면"
            " §10 boilerplate가 정답에 섞여 evidence 기준 수치와 비교 불가.\n"
            "        python scripts/evalset_pairs.py --corpus-tag <tag> 로 평가셋을 재생성할 것."
        )

    kept, gold_sets = [], []
    for g in gold:
        # Evidence-level 채점: gold_pair.jsonl(173종 재정의, 2026-08-08)에 gold_evidence가
        # 있으면 그걸 정답으로 쓴다. gold_section은 §10 boilerplate/review-required 청크까지
        # 포함해 "같은 문서의 무관한 chunk"도 Hit으로 잘못 셀 수 있음(2026-08-09 검증으로 확인,
        # 샘플 5건 중 2건 재현). gold_evidence가 없는 gold(fact task 등)는 기존 동작 그대로.
        raw = g["gold_evidence"] if key == "gold_section" and "gold_evidence" in g else g[key]
        ids = raw if isinstance(raw, list) else [raw]
        idx = {pos[c] for c in ids if c in pos}
        if idx:
            kept.append(g)
            gold_sets.append(idx)
    return corpus, kept, gold_sets, len(gold) - len(kept), keep


def _per_query_ms(fn, n: int = 50) -> float:
    """질의 1건씩 순차 실행했을 때의 중앙값 지연(ms). 배치 평균은 실사용 지연이 아니다."""
    samples = []
    for i in range(n):
        t0 = time.perf_counter()
        fn(i)
        samples.append((time.perf_counter() - t0) * 1000)
    return round(float(np.median(samples)), 3)


def _search(model_key: str, gran: str, gold: list[dict], task: str, k: int, sections=None, corpus_tag=None):
    corpus, kept, gold_sets, dropped, keep = prepare(gran, gold, task, sections, corpus_tag)
    queries = [g["query"] for g in kept]
    dvecs = R.embed_corpus(model_key, gran, R.load_corpus(gran, corpus_tag=corpus_tag), corpus_tag=corpus_tag or "")
    if keep is not None:
        dvecs = dvecs[keep]
    qvecs = R.embed_queries(model_key, queries, f"{task}_q")
    index = R.build_faiss(dvecs)
    tag = f"{gran}_s{''.join(map(str, sorted(sections)))}" if sections else gran
    if corpus_tag:
        tag = f"{tag}_{corpus_tag}"
    bm25 = R.build_bm25(tag, corpus)

    d_ranks = R.dense_rank(index, qvecs, k)
    b_ranks = R.bm25_rank(bm25, queries, k)
    penalty = R.boilerplate_penalty_vector(corpus)  # STEP 2/3 확정 baseline: §10 boilerplate penalty
    h_ranks = R.rrf_fuse([d_ranks, b_ranks], k, penalty=penalty)

    lat = {
        "dense": _per_query_ms(lambda i: index.search(qvecs[i : i + 1], k)),
        "bm25": _per_query_ms(lambda i: bm25.get_scores(R.tokenize_ko(queries[i]))),
    }
    lat["hybrid"] = round(lat["dense"] + lat["bm25"], 3)
    return corpus, kept, gold_sets, dropped, queries, (d_ranks, b_ranks, h_ranks), lat


def evaluate(model_key: str, gran: str, gold: list[dict], task: str, sections=None, corpus_tag=None) -> list[dict]:
    corpus, kept, gold_sets, dropped, queries, (d, b, h), lat = _search(
        model_key, gran, gold, task, TOPK, sections, corpus_tag
    )
    avg_gold = sum(len(s) for s in gold_sets) / len(gold_sets)
    q_ms = query_encode_ms(model_key, queries)
    rows = []
    for mode, ranks in (("dense", d), ("bm25", b), ("hybrid", h)):
        search_ms = lat[mode]
        rows.append(
            {
                "task": task,
                "embedding": model_key,
                "granularity": gran,
                "sections": ",".join(map(str, sorted(sections))) if sections else "all",
                "retriever": mode,
                "reranker": "-",
                "n_queries": len(kept),
                "n_chunks": len(corpus),
                "avg_gold_per_query": round(avg_gold, 1),
                "dropped_queries": dropped,
                **metrics(ranks, gold_sets),
                "search_ms": search_ms,
                # BM25 는 질의 임베딩이 필요 없다. dense/hybrid 는 필요하다.
                "query_encode_ms": 0.0 if mode == "bm25" else q_ms,
                "total_retrieval_ms": round(search_ms + (0.0 if mode == "bm25" else q_ms), 2),
            }
        )
    return rows


def query_encode_ms(model_key: str, queries: list[str], n: int = 20) -> float:
    """질의 1건 임베딩 지연(ms) 중앙값. 실사용 Retrieval 지연의 지배 요인."""
    R.torch_threads()
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(R.EMBEDDING_MODELS[model_key])
    model.max_seq_length = R.MAX_SEQ_LEN
    model.encode(queries[:2], show_progress_bar=False)  # warmup
    return _per_query_ms(
        lambda i: model.encode([queries[i]], normalize_embeddings=True, show_progress_bar=False),
        min(n, len(queries)),
    )


def evaluate_reranker(model_key: str, gran: str, rr_key: str, gold: list[dict], task: str, sections=None, corpus_tag=None) -> dict:
    corpus, kept, gold_sets, dropped, queries, (_d, _b, h), _t = _search(
        model_key, gran, gold, task, CAND_K, sections, corpus_tag
    )
    # 하이브리드 재채택(2026-08-06 결정 재검토, decisions.md §2.4) -> hybrid 상위 후보를 리랭커 입력으로
    ranks, secs = R.rerank(rr_key, queries, h, corpus, TOPK)
    return {
        "task": task,
        "embedding": model_key,
        "granularity": gran,
        "retriever": f"hybrid(top{CAND_K})",
        "reranker": rr_key,
        "n_queries": len(kept),
        "n_chunks": len(corpus),
        "avg_gold_per_query": round(sum(len(s) for s in gold_sets) / len(gold_sets), 1),
        "dropped_queries": dropped,
        **metrics(ranks, gold_sets),
        "rerank_ms_per_query": round(secs / len(queries) * 1000, 1),
    }


def save(rows: list[dict], name: str) -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    cols = list(rows[0].keys())
    with (RESULT_DIR / f"{name}.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    def fmt(v):
        return f"{v:.4f}" if isinstance(v, float) else str(v)

    md = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    md += ["| " + " | ".join(fmt(r[c]) for c in cols) + " |" for r in rows]
    (RESULT_DIR / f"{name}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md), flush=True)
    print(f"\n저장: {RESULT_DIR / name}.csv / .md", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["embedding", "reranker"])
    ap.add_argument("--task", choices=["pair", "fact"], default="pair")
    ap.add_argument("--granularity", choices=["section", "item", "both"], default="both")
    ap.add_argument("--models", help="평가할 임베딩 모델(쉼표 구분). 미지정 시 전체")
    ap.add_argument("--rerankers", help="평가할 리랭커(쉼표 구분). 미지정 시 전체")
    ap.add_argument("--sections", help="검색공간을 이 섹션들로 축소(쉼표 구분). 예: 2,10")
    ap.add_argument("--winner", help="reranker 단계에서 쓸 임베딩 모델 키")
    ap.add_argument("--winner-granularity", help="reranker 단계에서 쓸 청킹 단위")
    ap.add_argument("--corpus-tag", default=None,
                     help="PHASE 5: rag_corpus_membership의 corpus_tag(예: 426, 259proposed). "
                          "미지정시 기존 동작(rag_chunks 전체, 하위호환)")
    args = ap.parse_args()

    gold = load_gold(args.task)
    sections = {int(x) for x in args.sections.split(",")} if args.sections else None
    grans = ["section", "item"] if args.granularity == "both" else [args.granularity]
    name_suffix = f"_{args.corpus_tag}" if args.corpus_tag else ""

    if args.stage == "embedding":
        rows = []
        for key in (args.models.split(",") if args.models else list(R.EMBEDDING_MODELS)):
            for gran in grans:
                rows += evaluate(key, gran, gold, args.task, sections, args.corpus_tag)
                save(rows, f"02_embedding_{args.task}" + (f"_sec{args.sections.replace(',', '')}" if args.sections else "") + name_suffix)  # 조합마다 중간 저장
    else:
        if not args.winner or not args.winner_granularity:
            raise SystemExit("--winner 와 --winner-granularity 필수")
        rows = []
        for rr in (args.rerankers.split(",") if args.rerankers else list(R.RERANKER_MODELS)):
            rows.append(evaluate_reranker(args.winner, args.winner_granularity, rr, gold, args.task, sections, args.corpus_tag))
            save(rows, f"03_reranker_{args.task}" + name_suffix)


if __name__ == "__main__":
    main()
