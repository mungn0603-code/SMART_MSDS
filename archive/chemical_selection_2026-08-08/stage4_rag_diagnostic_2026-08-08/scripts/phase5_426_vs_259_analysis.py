# -*- coding: utf-8 -*-
"""
PHASE 5 §6 — 426 vs 259proposed 공정 비교 (사용자 지시, 2026-08-08).

Recall@10 0.896(259, 130건 제외 후) 하나만 보고 "축소해도 성능 유지"라고 결론
내리지 않기 위해 5단계로 나눠 비교한다:
  1) 426 전체(1,915건, dropped=0)
  2) 259 전체(1,785건, dropped=130)
  3) 공통 1,785건으로 426 vs 259 paired evaluation(코퍼스 차이만 격리)
  4) 130건(REMOVE/MERGE로 259에서 빠진 질의)을 426 안에서만 채점 — 제거 비용 실측
  5) strict(1,915건 모수로 259의 130건을 전부 0점 처리해 환산) vs
     selection-aware(1,785건 모수, 즉 기존 §2 수치)

전부 캐시된 임베딩/BM25 재사용 — 재계산 없음, 수 분 내 완료. 읽기 전용.
"""
import json
from pathlib import Path

import numpy as np

import retrieval as R
from run_ab import load_gold, prepare, metrics, TOPK

TASK = "pair"
SECTIONS = {2, 10}
MODEL = "bge-m3-ko"
GRAN = "section"
OUT_MD = Path(__file__).resolve().parent.parent / "docs" / "phase5_426_vs_259_results_2026-08-08.md"


def eval_subset(index, bm25, qvecs, queries, gold_sets, positions, k=TOPK):
    qv = qvecs[positions]
    qs = [queries[i] for i in positions]
    gs = [gold_sets[i] for i in positions]
    d = R.dense_rank(index, qv, k)
    b = R.bm25_rank(bm25, qs, k)
    h = R.rrf_fuse([d, b], k)
    return {"dense": metrics(d, gs), "bm25": metrics(b, gs), "hybrid": metrics(h, gs)}, len(positions)


def build_index_bm25(corpus_tag, corpus, keep):
    dvecs_full = R.embed_corpus(MODEL, GRAN, R.load_corpus(GRAN, corpus_tag=corpus_tag), corpus_tag=corpus_tag)
    dvecs = dvecs_full[keep] if keep is not None else dvecs_full
    index = R.build_faiss(dvecs)
    bm25_tag = f"{GRAN}_s210_{corpus_tag}"
    bm25 = R.build_bm25(bm25_tag, corpus)
    return index, bm25


def fmt(res):
    return {k: {m: round(v, 4) for m, v in d.items()} for k, d in res.items()}


def main():
    gold = load_gold(TASK)

    corpus_426, kept_426, gold_sets_426, dropped_426, keep_426 = prepare(GRAN, gold, TASK, SECTIONS, "426")
    corpus_259, kept_259, gold_sets_259, dropped_259, keep_259 = prepare(GRAN, gold, TASK, SECTIONS, "259proposed")

    qids_426 = [g["query_id"] for g in kept_426]
    qids_259 = [g["query_id"] for g in kept_259]
    set_426, set_259 = set(qids_426), set(qids_259)

    subset_ok = set_259 <= set_426
    print(f"259 유효질의 ⊆ 426 유효질의? {subset_ok}  (426={len(set_426)}, 259={len(set_259)}, "
          f"259만에 있음={len(set_259 - set_426)})")

    common = set_259 & set_426
    only_426 = set_426 - set_259

    pos_all_426 = list(range(len(kept_426)))
    pos_common_426 = [i for i, q in enumerate(qids_426) if q in common]
    pos_only426 = [i for i, q in enumerate(qids_426) if q in only_426]
    pos_all_259 = list(range(len(kept_259)))

    queries_426 = [g["query"] for g in kept_426]
    queries_259 = [g["query"] for g in kept_259]
    qvecs_426 = R.embed_queries(MODEL, queries_426, f"{TASK}_q")
    qvecs_259 = R.embed_queries(MODEL, queries_259, f"{TASK}_q")

    index_426, bm25_426 = build_index_bm25("426", corpus_426, keep_426)
    index_259, bm25_259 = build_index_bm25("259proposed", corpus_259, keep_259)

    r1_full426, n1 = eval_subset(index_426, bm25_426, qvecs_426, queries_426, gold_sets_426, pos_all_426)
    r2_full259, n2 = eval_subset(index_259, bm25_259, qvecs_259, queries_259, gold_sets_259, pos_all_259)
    r3_common426, n3 = eval_subset(index_426, bm25_426, qvecs_426, queries_426, gold_sets_426, pos_common_426)
    r4_only426, n4 = eval_subset(index_426, bm25_426, qvecs_426, queries_426, gold_sets_426, pos_only426)
    # 259 쪽 "공통"은 정의상 이미 kept_259 전체와 동일(위 r2_full259 재사용)
    r3_common259, n3b = r2_full259, n2

    strict_ratio = n2 / n1  # 1785/1915
    r5_strict259 = {mode: {m: round(v * strict_ratio, 4) for m, v in d.items()} for mode, d in r2_full259.items()}

    print("\n=== 1) 426 전체(1,915) ===", n1)
    print(json.dumps(fmt(r1_full426), ensure_ascii=False, indent=1))
    print("\n=== 2) 259 전체(1,785, selection-aware) ===", n2)
    print(json.dumps(fmt(r2_full259), ensure_ascii=False, indent=1))
    print("\n=== 3) 공통 1,785 paired — 426쪽 ===", n3)
    print(json.dumps(fmt(r3_common426), ensure_ascii=False, indent=1))
    print("=== 3) 공통 1,785 paired — 259쪽(=전체와 동일) ===", n3b)
    print("\n=== 4) 130건(REMOVE/MERGE) — 426 안에서만 ===", n4)
    print(json.dumps(fmt(r4_only426), ensure_ascii=False, indent=1))
    print("\n=== 5) 259 strict(1,915 모수 환산, ratio=%.4f) ===" % strict_ratio)
    print(json.dumps(r5_strict259, ensure_ascii=False, indent=1))

    # ---- 마크다운 리포트 ----
    L = ["# PHASE 5 §6 — 426 vs 259proposed 5단계 비교 결과", "",
         "**생성**: `04_rag_agent/phase5_426_vs_259_analysis.py` (캐시 재사용, 읽기 전용)", "",
         f"259의 유효질의 집합이 426의 부분집합인가: **{subset_ok}** "
         f"(426 valid={len(set_426)}, 259 valid={len(set_259)}, 259에만 있는 질의={len(set_259-set_426)})",
         ""]

    def table(title, res, n):
        rows = [f"### {title} (n={n})", "", "| retriever | Recall@10 | Recall@5 | MRR | nDCG@10 | Hit@5 | Hit@10 |",
                "|---|---:|---:|---:|---:|---:|---:|"]
        for mode in ("dense", "bm25", "hybrid"):
            d = res[mode]
            rows.append(f"| {mode} | {d['Recall@10']:.4f} | {d['Recall@5']:.4f} | {d['MRR']:.4f} | "
                        f"{d['nDCG@10']:.4f} | {d['Hit@5']:.4f} | {d['Hit@10']:.4f} |")
        rows.append("")
        return rows

    L += table("1) 426 전체", r1_full426, n1)
    L += table("2) 259 전체 (selection-aware)", r2_full259, n2)
    L += table("3) 공통 1,785 — 426 (paired)", r3_common426, n3)
    L += table("3) 공통 1,785 — 259 (paired, = 2와 동일)", r3_common259, n3b)
    L += table("4) 130건(REMOVE/MERGE) — 426 안에서만", r4_only426, n4)
    L += table(f"5) 259 strict (1,915 모수 환산, ratio={strict_ratio:.4f})", r5_strict259, n1)

    L.append("## 해석")
    L.append("")
    d3a, d3b = r3_common426["hybrid"], r3_common259["hybrid"]
    d4 = r4_only426["hybrid"]
    d5 = r5_strict259["hybrid"]
    d1 = r1_full426["hybrid"]
    L.append(f"- **공정 비교(3, 동일 1,785건)**: 426 hybrid Recall@10={d3a['Recall@10']:.4f} vs "
              f"259 hybrid Recall@10={d3b['Recall@10']:.4f} — "
              f"{'259가 더 높음' if d3b['Recall@10'] > d3a['Recall@10'] else '426이 더 높음' if d3a['Recall@10'] > d3b['Recall@10'] else '동일'}"
              f"(차이 {d3b['Recall@10']-d3a['Recall@10']:+.4f}).")
    L.append(f"- **130건 제거 비용(4)**: 이 130건을 426 안에서만 채점하면 hybrid Recall@10="
              f"{d4['Recall@10']:.4f} — 426 전체 평균({d1['Recall@10']:.4f})과 비교해 "
              f"{'더 어려운/성능이 낮은' if d4['Recall@10'] < d1['Recall@10'] else '오히려 더 쉬운/성능이 높은'} "
              f"질의 집단이었다.")
    L.append(f"- **strict vs selection-aware(5)**: selection-aware hybrid Recall@10="
              f"{r2_full259['hybrid']['Recall@10']:.4f} → strict 환산 시 {d5['Recall@10']:.4f} "
              f"(1,915건 모수로 130건을 0점 처리). **426 전체({d1['Recall@10']:.4f})와 비교할 때는 "
              f"이 strict 값을 써야 공정하다.**")

    OUT_MD.write_text("\n".join(L), encoding="utf-8")
    print("\n리포트 작성:", OUT_MD)


if __name__ == "__main__":
    main()
