"""STEP 1 (Generation 평가 파이프라인): Retrieval baseline을 2,160개 질의 전체에 대해
top-10으로 고정 저장. Generation 실험마다 재검색하지 않고 이 결과를 그대로 재사용한다.

고정 구성(HANDOFF §0-3/§0-5 baseline 그대로, 변경 없음):
  bge-m3-ko / section 청킹 / §2·§10 필터 / hybrid(dense+BM25 RRF, §10 전체 penalty) / top-10

2026-08-28: `--corpus-tag`와 `--out`을 인자로 뺐다. 기본값은 종전 그대로
'173' / results/frozen_retrieval_top10.jsonl 이라 인자 없이 실행하면 동작이 바뀌지
않는다(재현 경로 보존). 서비스 기준 실행은 `--corpus-tag service`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))
import retrieval as R  # noqa: E402
import run_ab as A  # noqa: E402

MODEL = "bge-m3-ko"
GRAN = "section"
SECTIONS = {2, 10}
CORPUS_TAG_DEFAULT = "173"  # 기본값 유지 = 인자 없이 돌리면 종전 재현 경로 그대로
CAND_K = 20  # run_ab._search와 동일한 후보 풀 크기(baseline 수치를 그대로 재현하기 위함)
TOPK = 10
OUT_PATH_DEFAULT = ROOT / "results" / "frozen_retrieval_top10.jsonl"


def rrf_fuse_scored(rank_lists, k, rrf_k=R.RRF_K, penalty=None):
    """retrieval.rrf_fuse와 동일한 알고리즘이되, 산출물에 점수도 남기려고 점수 포함 반환.

    retrieval.py는 건드리지 않는다(freeze 대상) — 이 스크립트에서만 쓰는 소비용 변형."""
    nq = rank_lists[0].shape[0]
    out = []
    for i in range(nq):
        scores: dict[int, float] = {}
        for ranks in rank_lists:
            for pos, doc in enumerate(ranks[i]):
                if doc < 0:
                    continue
                scores[int(doc)] = scores.get(int(doc), 0.0) + 1.0 / (rrf_k + pos + 1)
        if penalty is not None:
            for doc in list(scores):
                scores[doc] -= float(penalty[doc])
        top = sorted(scores.items(), key=lambda kv: -kv[1])[:k]
        out.append(top)
    return out


def _decomposed_scored(corpus, kept, penalty, corpus_tag):
    """물질별 단일 질의로 검색해 각 top-(TOPK//2)씩 교차 병합. run_ab._decomposed_ranks와
    같은 전략이되 frozen 산출물에 남길 점수를 함께 반환한다."""
    dvecs = R.embed_corpus(MODEL, GRAN, R.load_corpus(GRAN, corpus_tag=corpus_tag),
                           corpus_tag=corpus_tag or "")
    pos = {cid: i for i, cid in enumerate(R.load_corpus(GRAN, corpus_tag=corpus_tag).chunk_ids)}
    dvecs = dvecs[[pos[c] for c in corpus.chunk_ids]]
    index = R.build_faiss(dvecs)
    tag = f"{GRAN}_s{''.join(map(str, sorted(SECTIONS)))}" + (f"_{corpus_tag}" if corpus_tag else "")
    bm25 = R.build_bm25(tag, corpus)

    subs = {}
    for g in kept:
        subs[g["cas_a"]] = g["name_a"]
        subs[g["cas_b"]] = g["name_b"]
    cas_order = sorted(subs)
    sub_q = [subs[c] for c in cas_order]
    qv = R.embed_queries(MODEL, sub_q, "pair_sub")
    per_sub = rrf_fuse_scored(
        [R.dense_rank(index, qv, CAND_K), R.bm25_rank(bm25, sub_q, CAND_K)], CAND_K, penalty=penalty
    )
    table = {c: per_sub[i] for i, c in enumerate(cas_order)}

    half = TOPK // 2
    out = []
    for g in kept:
        a, b = table[g["cas_a"]], table[g["cas_b"]]
        merged, seen = [], set()
        for i in range(half):
            for lst in (a, b):
                if i < len(lst) and lst[i][0] not in seen:
                    seen.add(lst[i][0])
                    merged.append(lst[i])
        out.append(merged[:TOPK])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus-tag", default=CORPUS_TAG_DEFAULT,
                    help="rag_corpus_membership 태그(기본: 173 = 재현용 고정 코퍼스). "
                         "서비스 기준은 service")
    ap.add_argument("--out", type=Path, default=OUT_PATH_DEFAULT)
    ap.add_argument("--decompose", action="store_true",
                    help="쌍 질의를 물질별 단일 질의 2개로 분해해 교차 병합(run_ab.py --decompose와 동일 경로). "
                         "미지정시 종전 단일 쌍질의 그대로 - 재현 경로 보존")
    args = ap.parse_args()
    OUT_PATH = args.out
    if args.decompose and OUT_PATH == OUT_PATH_DEFAULT:
        # 기존 frozen(쌍질의)을 덮어쓰면 그걸 입력으로 쓰는 Generation 실행분과 섞인다.
        OUT_PATH = OUT_PATH.with_name(f"{OUT_PATH.stem}_decomposed{OUT_PATH.suffix}")

    gold = A.load_gold("pair")
    corpus, kept, gold_sets, dropped, queries, (d_ranks, b_ranks, _h), lat = A._search(
        MODEL, GRAN, gold, "pair", CAND_K, SECTIONS, args.corpus_tag
    )
    penalty = R.boilerplate_penalty_vector(corpus)
    if args.decompose:
        fused = _decomposed_scored(corpus, kept, penalty, args.corpus_tag)
    else:
        fused = rrf_fuse_scored([d_ranks, b_ranks], TOPK, penalty=penalty)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    n_hit = 0
    with OUT_PATH.open("w", encoding="utf-8") as f:
        for g, gset, top in zip(kept, gold_sets, fused):
            retrieved = []
            for rank, (doc_idx, score) in enumerate(top, start=1):
                m = corpus.meta[doc_idx]
                retrieved.append(
                    {
                        "chunk_id": corpus.chunk_ids[doc_idx],
                        "rank": rank,
                        "score": round(float(score), 6),
                        "section": m["section"],
                        "cas_number": m["cas_number"],
                        "chemical_name": m["chemical_name"],
                    }
                )
            hit = any(doc_idx in gset for doc_idx, _ in top)
            n_hit += hit
            rec = {
                "query_id": g["query_id"],
                "query": g["query"],
                "cas_a": g["cas_a"],
                "cas_b": g["cas_b"],
                "name_a": g["name_a"],
                "name_b": g["name_b"],
                "matrix_verdict": g["matrix_verdict"],
                "gold_evidence": g["gold_evidence"],
                "retrieved": retrieved,
                "retrieval_status": "hit" if hit else "miss",
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"질의 {len(kept)}건(dropped={dropped}) 저장: {OUT_PATH}")
    print(f"retrieval_status hit(top-10 안에 gold_evidence 존재): {n_hit}/{len(kept)} ({n_hit / len(kept):.4f})")


if __name__ == "__main__":
    main()
