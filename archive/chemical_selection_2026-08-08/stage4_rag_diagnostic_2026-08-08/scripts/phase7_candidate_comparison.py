# -*- coding: utf-8 -*-
"""
PHASE 7 — 신규 독립 평가셋(150건, DIAGNOSTIC이지만 wave 편향 없는 계층표집)으로
426/259/301(C)/신규D를 완전히 동일한 조건(같은 임베딩모델·청킹·섹션필터·hybrid
RRF·top-k·채점코드)에서 비교한다.

D(신규, PHASE7 정의) = 301(C) + REVIEW_SUPPORTED(신규 평가셋에서 자기 청크가
실제로 top-10에 검색되는 것이 확인된 REVIEW-134 물질) — Phase6의 D(C+RETAIN_COVERAGE)
와는 다른 후보군이다.

읽기 전용(rag_corpus_membership에 corpus_tag='phase7_D' 1개만 신규 추가 — CAS
목록일 뿐 청크 내용 변경 없음). undergrad_target_chemicals.csv 미변경.
"""
import csv
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\04_rag_agent")

import numpy as np
import retrieval as R

ROOT = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS"
DB_PATH = ROOT + r"\reactivity_reference.db"
NEW_EVAL_JSONL = ROOT + r"\04_rag_agent\evalset\independent_eval_v2_2026-08-08.jsonl"
PHASE6_CSV = ROOT + r"\01_collection\chemical_phase6_retrieval_reassessment_2026-08-08.csv"
OUT_MD = Path(ROOT) / "docs" / "phase7_candidate_comparison_results_2026-08-08.md"
OUT_REVIEW_CSV = ROOT + r"\01_collection\chemical_phase7_review134_status_2026-08-08.csv"
OUT_CANDIDATES_CSV = ROOT + r"\01_collection\chemical_phase7_candidate_sets_2026-08-08.csv"

MODEL, GRAN = "bge-m3-ko", "section"
TOPK = 10
CAS_RE = re.compile(r"^sec::([^:]+)::")


def cas_of_chunk(cid):
    m = CAS_RE.match(cid)
    return m.group(1) if m else None


def load_new_eval():
    with open(NEW_EVAL_JSONL, encoding="utf-8") as f:
        recs = [json.loads(line) for line in f if line.strip()]
    return [r for r in recs if r["kind"] == "pair"]


def metrics_extended(ranks, gold_sets):
    """ranks: (nq, TOPK) 문서 인덱스. gold_sets: 질의별 정답 인덱스 집합. Recall/Hit @1/3/5/10 + MRR + nDCG@10."""
    ks = (1, 3, 5, 10)
    acc = {f"Recall@{k}": 0.0 for k in ks}
    acc.update({f"Hit@{k}": 0.0 for k in ks})
    acc["MRR"] = 0.0
    acc["nDCG@10"] = 0.0
    n = len(gold_sets)
    per_query = []
    for i, gold in enumerate(gold_sets):
        hits = [p + 1 for p, d in enumerate(ranks[i]) if d >= 0 and int(d) in gold]
        for k in ks:
            acc[f"Recall@{k}"] += sum(1 for h in hits if h <= k) / len(gold)
            acc[f"Hit@{k}"] += 1.0 if any(h <= k for h in hits) else 0.0
        rr = 1.0 / hits[0] if hits else 0.0
        acc["MRR"] += rr
        dcg = sum(1.0 / np.log2(h + 1) for h in hits if h <= 10)
        idcg = sum(1.0 / np.log2(j + 2) for j in range(min(len(gold), 10)))
        ndcg = dcg / idcg if idcg else 0.0
        acc["nDCG@10"] += ndcg
        per_query.append({"rr": rr, "ndcg": ndcg, "hit10": 1.0 if any(h <= 10 for h in hits) else 0.0})
    return {k: v / n for k, v in acc.items()}, per_query


def _combined_chunk_vectors():
    vecs = {}
    for tag in ("426", "259proposed"):
        corpus = R.load_corpus(GRAN, corpus_tag=tag)
        dvecs = R.embed_corpus(MODEL, GRAN, corpus, corpus_tag=tag)
        for cid, v in zip(corpus.chunk_ids, dvecs):
            vecs.setdefault(cid, v)
    return vecs


def prepare_for_tag(pairs, corpus_tag, chunk_vecs):
    """corpus_tag 멤버십 기준으로 유효 질의만 남기고 (corpus, kept, gold_sets, dvecs) 구성."""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT cas_number FROM rag_corpus_membership WHERE corpus_tag=?", (corpus_tag,))
    members = {r[0] for r in cur.fetchall()}
    con.close()

    # 코퍼스(§2,§10 청크) 구성 = 멤버십에 속한 물질의 청크만
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT DISTINCT chunk_id, cas_number FROM rag_chunks WHERE granularity='section' AND section IN (2,10)")
    all_chunks = [(cid, cas) for cid, cas in cur.fetchall() if cas in members and cid in chunk_vecs]
    con.close()
    chunk_ids = sorted({cid for cid, _ in all_chunks})
    pos = {cid: i for i, cid in enumerate(chunk_ids)}
    dvecs = np.stack([chunk_vecs[cid] for cid in chunk_ids])

    kept, gold_sets = [], []
    for g in pairs:
        gold_ids = [c for c in g["gold_section"] if c in pos]
        if gold_ids and g["cas_a"] in members and g["cas_b"] in members:
            kept.append(g)
            gold_sets.append({pos[c] for c in gold_ids})
    return chunk_ids, dvecs, kept, gold_sets


def main():
    pairs = load_new_eval()
    print(f"신규 평가셋: {len(pairs)}쌍")
    chunk_vecs = _combined_chunk_vectors()

    tags = {"A_426": "426", "B_259": "259proposed", "C_301": "259_retrieval_aware"}
    results = {}
    per_query_all = {}
    for label, tag in tags.items():
        chunk_ids, dvecs, kept, gold_sets = prepare_for_tag(pairs, tag, chunk_vecs)
        queries = [g["query"] for g in kept]
        qvecs = R.embed_queries(MODEL, queries, "phase7v2_q")
        index = R.build_faiss(dvecs)
        con = sqlite3.connect(DB_PATH)
        text_map = dict(con.execute("SELECT chunk_id, text FROM rag_chunks WHERE granularity='section'"))
        con.close()
        corpus_obj = R.Corpus(chunk_ids=chunk_ids, texts=[text_map.get(cid, "") for cid in chunk_ids], meta=[{}] * len(chunk_ids))
        bm25 = R.build_bm25(f"phase7v2_{tag}_t", corpus_obj)

        d = R.dense_rank(index, qvecs, TOPK)
        b = R.bm25_rank(bm25, queries, TOPK)
        h = R.rrf_fuse([d, b], TOPK)
        m, per_q = metrics_extended(h, gold_sets)
        results[label] = {"metrics": m, "n_kept": len(kept), "n_total": len(pairs), "kept_qids": [g["query_id"] for g in kept], "per_query": per_q}
        print(f"\n=== {label} (tag={tag}, n_kept={len(kept)}/{len(pairs)}) ===")
        for k, v in m.items():
            print(f"  {k}: {v:.4f}")

    # ---- REVIEW-134 SUPPORTED/UNSUPPORTED/NOT_TESTED (426 기준 자기 청크 hit) ----
    with open(PHASE6_CSV, encoding="utf-8-sig") as f:
        review_cas = {r["cas"]: r for r in csv.DictReader(f) if r["phase6_status"] == "REVIEW"}

    chunk_ids_426, dvecs_426, kept_426, gold_sets_426 = prepare_for_tag(pairs, "426", chunk_vecs)
    queries_426 = [g["query"] for g in kept_426]
    qvecs_426 = R.embed_queries(MODEL, queries_426, "phase7v2_q")
    index_426 = R.build_faiss(dvecs_426)
    con = sqlite3.connect(DB_PATH)
    text_map = dict(con.execute("SELECT chunk_id, text FROM rag_chunks WHERE granularity='section'"))
    con.close()
    corpus_426 = R.Corpus(chunk_ids=chunk_ids_426, texts=[text_map.get(c, "") for c in chunk_ids_426], meta=[{}] * len(chunk_ids_426))
    bm25_426 = R.build_bm25("phase7v2_426_full", corpus_426)
    d426 = R.dense_rank(index_426, qvecs_426, TOPK)
    b426 = R.bm25_rank(bm25_426, queries_426, TOPK)
    h426 = R.rrf_fuse([d426, b426], TOPK)

    per_cas_found = defaultdict(list)
    for i, g in enumerate(kept_426):
        ranked = [chunk_ids_426[x] if x >= 0 else None for x in h426[i]]
        found_cas = {cas_of_chunk(c) for c in ranked if c}
        for side in ("cas_a", "cas_b"):
            cas = g[side]
            if cas in review_cas:
                per_cas_found[cas].append(1 if cas in found_cas else 0)

    review_status = []
    tested_cas = set(per_cas_found.keys())
    for cas, row in review_cas.items():
        if cas not in tested_cas:
            status = "REVIEW_NOT_TESTED"
            rate = None
        else:
            hits = per_cas_found[cas]
            rate = sum(hits) / len(hits)
            status = "REVIEW_SUPPORTED" if rate >= 0.5 else "REVIEW_UNSUPPORTED"
        review_status.append({"cas": cas, "chemical_name": row["chemical_name"], "n_tested": len(per_cas_found.get(cas, [])),
                                "hit_rate_10": rate, "status": status})

    with open(OUT_REVIEW_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["cas", "chemical_name", "n_tested", "hit_rate_10", "status"])
        w.writeheader()
        w.writerows(review_status)

    status_counter = Counter(r["status"] for r in review_status)
    print(f"\n=== REVIEW-134 분류(신규 평가셋 기준) ===")
    print(dict(status_counter))

    # ---- D = 301(C) + REVIEW_SUPPORTED ----
    supported_cas = [r["cas"] for r in review_status if r["status"] == "REVIEW_SUPPORTED"]
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT cas_number FROM rag_corpus_membership WHERE corpus_tag='259_retrieval_aware'")
    c301 = {r[0] for r in cur.fetchall()}
    tag_d = c301 | set(supported_cas)
    cur.execute("DELETE FROM rag_corpus_membership WHERE corpus_tag='phase7_D'")
    cur.executemany("INSERT INTO rag_corpus_membership (corpus_tag, cas_number) VALUES (?,?)",
                     [("phase7_D", c) for c in tag_d])
    con.commit()
    con.close()
    print(f"\nD(phase7_D) = C(301) + REVIEW_SUPPORTED({len(supported_cas)}) = {len(tag_d)}종")

    chunk_ids_d, dvecs_d, kept_d, gold_sets_d = prepare_for_tag(pairs, "phase7_D", chunk_vecs)
    queries_d = [g["query"] for g in kept_d]
    qvecs_d = R.embed_queries(MODEL, queries_d, "phase7v2_q")
    index_d = R.build_faiss(dvecs_d)
    con = sqlite3.connect(DB_PATH)
    text_map_d = dict(con.execute("SELECT chunk_id, text FROM rag_chunks WHERE granularity='section'"))
    con.close()
    corpus_d = R.Corpus(chunk_ids=chunk_ids_d, texts=[text_map_d.get(c, "") for c in chunk_ids_d], meta=[{}] * len(chunk_ids_d))
    bm25_d = R.build_bm25("phase7v2_D_full", corpus_d)
    dd = R.dense_rank(index_d, qvecs_d, TOPK)
    bd = R.bm25_rank(bm25_d, queries_d, TOPK)
    hd = R.rrf_fuse([dd, bd], TOPK)
    m_d, per_q_d = metrics_extended(hd, gold_sets_d)
    results["D_301+supported"] = {"metrics": m_d, "n_kept": len(kept_d), "n_total": len(pairs), "kept_qids": [g["query_id"] for g in kept_d], "per_query": per_q_d}
    print(f"\n=== D_301+supported (n_kept={len(kept_d)}/{len(pairs)}) ===")
    for k, v in m_d.items():
        print(f"  {k}: {v:.4f}")

    # ---- strict 환산(150건 공통 모수) + paired bootstrap ----
    n_total = len(pairs)
    strict = {}
    for label, res in results.items():
        ratio = res["n_kept"] / n_total
        strict[label] = {k: v * ratio for k, v in res["metrics"].items()}

    print("\n=== strict(150건 모수 환산) ===")
    for label in results:
        print(f"  {label}: Recall@10={strict[label]['Recall@10']:.4f} MRR={strict[label]['MRR']:.4f} nDCG@10={strict[label]['nDCG@10']:.4f}")

    def bootstrap_ci(per_q_a, qid_a, per_q_b, qid_b, metric_key, n_boot=2000, seed=42):
        """공통 query_id 집합에서만 paired bootstrap."""
        common = sorted(set(qid_a) & set(qid_b))
        idx_a = {q: i for i, q in enumerate(qid_a)}
        idx_b = {q: i for i, q in enumerate(qid_b)}
        diffs = np.array([per_q_a[idx_a[q]][metric_key] - per_q_b[idx_b[q]][metric_key] for q in common])
        if len(diffs) == 0:
            return None
        rng = np.random.default_rng(seed)
        boot_means = [rng.choice(diffs, size=len(diffs), replace=True).mean() for _ in range(n_boot)]
        lo, hi = np.percentile(boot_means, [2.5, 97.5])
        return {"n_common": len(common), "mean_diff": float(diffs.mean()), "ci95": (float(lo), float(hi)),
                "win": int((diffs > 0).sum()), "loss": int((diffs < 0).sum()), "tie": int((diffs == 0).sum())}

    pair_compare = {}
    for (l1, l2) in [("A_426", "B_259"), ("A_426", "C_301"), ("B_259", "C_301")]:
        for metric_key in ("rr", "ndcg", "hit10"):
            res1, res2 = results[l1], results[l2]
            r = bootstrap_ci(res1["per_query"], res1["kept_qids"], res2["per_query"], res2["kept_qids"], metric_key)
            pair_compare[(l1, l2, metric_key)] = r

    print("\n=== Paired bootstrap (query-level win/loss, 95% CI) ===")
    for (l1, l2, mk), r in pair_compare.items():
        if r:
            print(f"  {l1} vs {l2} [{mk}]: n={r['n_common']} mean_diff={r['mean_diff']:+.4f} "
                  f"95%CI=({r['ci95'][0]:+.4f},{r['ci95'][1]:+.4f}) win/loss/tie={r['win']}/{r['loss']}/{r['tie']}")

    write_report(results, strict, review_status, status_counter, pair_compare, tag_d, c301)
    print("\n리포트:", OUT_MD)


def write_report(results, strict, review_status, status_counter, pair_compare, tag_d, c301):
    L = ["# PHASE 7 — 신규 독립 평가셋(150건) 기반 후보군 비교 결과", "",
         "**생성**: `04_rag_agent/phase7_candidate_comparison.py`", "",
         "426/259/301(C)/D(301+REVIEW_SUPPORTED) 전부 동일 임베딩모델(bge-m3-ko)·"
         "동일 청킹(section)·동일 섹션필터(§2,§10)·동일 hybrid(RRF k=60)·동일 top-10·"
         "동일 채점코드로 평가했다.", ""]

    L.append("## selection-aware 결과 (각 코퍼스 자체 유효질의 기준)")
    L.append("")
    L.append("| candidate | n_kept/150 | Recall@1 | Recall@3 | Recall@5 | Recall@10 | MRR | nDCG@10 | Hit@1 | Hit@10 |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for label, res in results.items():
        m = res["metrics"]
        L.append(f"| {label} | {res['n_kept']} | {m['Recall@1']:.4f} | {m['Recall@3']:.4f} | {m['Recall@5']:.4f} | "
                  f"{m['Recall@10']:.4f} | {m['MRR']:.4f} | {m['nDCG@10']:.4f} | {m['Hit@1']:.4f} | {m['Hit@10']:.4f} |")
    L.append("")

    L.append("## strict(150건 공통 모수 환산)")
    L.append("")
    L.append("| candidate | Recall@10 | MRR | nDCG@10 | Hit@10 |")
    L.append("|---|---:|---:|---:|---:|")
    for label in results:
        s = strict[label]
        L.append(f"| {label} | {s['Recall@10']:.4f} | {s['MRR']:.4f} | {s['nDCG@10']:.4f} | {s['Hit@10']:.4f} |")
    L.append("")

    L.append("## Paired 비교 (query-level, 95% bootstrap CI, n_boot=2000)")
    L.append("")
    L.append("| 비교 | 지표 | n_common | mean diff | 95% CI | win/loss/tie |")
    L.append("|---|---|---:|---:|---|---|")
    for (l1, l2, mk), r in pair_compare.items():
        if r:
            L.append(f"| {l1} vs {l2} | {mk} | {r['n_common']} | {r['mean_diff']:+.4f} | "
                      f"({r['ci95'][0]:+.4f}, {r['ci95'][1]:+.4f}) | {r['win']}/{r['loss']}/{r['tie']} |")
    L.append("")
    L.append("CI가 0을 포함하면 그 차이는 이 표본 크기에서 통계적으로 유의하다고 "
              "주장하지 않는다(표본이 작을 때 과장 금지 원칙).")
    L.append("")

    L.append("## REVIEW-134 분류 (신규 평가셋 기준)")
    L.append("")
    L.append("| status | 종수 |")
    L.append("|---|---:|")
    for k in ("REVIEW_SUPPORTED", "REVIEW_UNSUPPORTED", "REVIEW_NOT_TESTED"):
        L.append(f"| {k} | {status_counter.get(k,0)} |")
    L.append("")
    L.append(f"D = C(301) + REVIEW_SUPPORTED = **{len(tag_d)}종** (C={len(c301)}종 대비 +{len(tag_d)-len(c301)}종)")
    L.append("")
    L.append("`NO_DATA`/`REVIEW_UNSUPPORTED`/`REVIEW_NOT_TESTED`는 \"retrieval 성능이 "
              "낮다\"가 아니라 각각 \"근거 없음\"/\"이 표본에서는 낮게 나옴\"/\"이번에도 "
              "평가 안 됨\"을 뜻할 뿐이다 — REMOVE 근거로 쓰지 않는다.")

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


if __name__ == "__main__":
    main()
