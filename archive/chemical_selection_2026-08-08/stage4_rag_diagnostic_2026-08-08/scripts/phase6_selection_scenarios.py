# -*- coding: utf-8 -*-
"""
PHASE 6 §8 — 후보군 A(426)/B(259)/C(259+RETAIN_RETRIEVAL)/D(C+RETAIN_COVERAGE)
비교 + 주요 후보 leave-one-out + independent eval prototype 재검증.

C/D의 물질 청크는 전부 이미 rag_chunks에 있다(426 코퍼스 청킹 시 다 포함됐음) —
재청킹·재임베딩 없이 rag_corpus_membership에 새 corpus_tag만 추가하고 426의
캐시된 임베딩 배열을 슬라이싱해서 재사용한다.

읽기 전용(단, rag_corpus_membership에 신규 corpus_tag 2종 추가는 함 — 이것도
CAS 목록일 뿐 청크 내용 변경 없음, 언제든 재생성 가능). undergrad_target_chemicals.csv
미변경.
"""
import csv
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\04_rag_agent")

import numpy as np
import retrieval as R
from run_ab import load_gold, prepare, metrics, TOPK

ROOT = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS"
DB_PATH = ROOT + r"\reactivity_reference.db"
PHASE6_CSV = ROOT + r"\01_collection\chemical_phase6_retrieval_reassessment_2026-08-08.csv"
INDEP_EVAL_JSONL = ROOT + r"\04_rag_agent\evalset\independent_eval_prototype_2026-08-08.jsonl"
OUT_MD = Path(ROOT) / "docs" / "phase6_candidate_sets_results_2026-08-08.md"

TASK, SECTIONS, MODEL, GRAN = "pair", {2, 10}, "bge-m3-ko", "section"


def setup_membership():
    with open(PHASE6_CSV, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    retain_retrieval = [r["cas"] for r in rows if r["phase6_status"] == "RETAIN_RETRIEVAL"]
    retain_coverage = [r["cas"] for r in rows if r["phase6_status"] == "RETAIN_COVERAGE"]

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT cas_number FROM rag_corpus_membership WHERE corpus_tag='259proposed'")
    base_259 = {r[0] for r in cur.fetchall()}

    tag_C = base_259 | set(retain_retrieval)
    tag_D = tag_C | set(retain_coverage)

    cur.execute("DELETE FROM rag_corpus_membership WHERE corpus_tag IN ('259_retrieval_aware','phase6_D')")
    cur.executemany("INSERT INTO rag_corpus_membership (corpus_tag, cas_number) VALUES (?,?)",
                     [("259_retrieval_aware", c) for c in tag_C] + [("phase6_D", c) for c in tag_D])
    con.commit()
    con.close()
    print(f"RETAIN_RETRIEVAL={len(retain_retrieval)}  RETAIN_COVERAGE={len(retain_coverage)}")
    print(f"C(259_retrieval_aware)={len(tag_C)}  D(phase6_D)={len(tag_D)}")
    return retain_retrieval, retain_coverage, tag_C, tag_D


_CHUNK_VEC_CACHE = None


def _combined_chunk_vectors():
    """426∪259proposed 두 코퍼스의 캐시된 임베딩을 chunk_id->vector 딕셔너리로 합친다.
    C(259_retrieval_aware)/D(phase6_D)의 모든 물질은 원래 426 또는 259proposed(신규
    ADD_CONFIRMED 14종) 둘 중 하나에 있었으므로, 이 두 캐시의 합집합이면 재임베딩
    없이 어떤 조합의 코퍼스든 구성할 수 있다."""
    global _CHUNK_VEC_CACHE
    if _CHUNK_VEC_CACHE is not None:
        return _CHUNK_VEC_CACHE
    vecs = {}
    for tag in ("426", "259proposed"):
        corpus = R.load_corpus(GRAN, corpus_tag=tag)
        dvecs = R.embed_corpus(MODEL, GRAN, corpus, corpus_tag=tag)
        for cid, v in zip(corpus.chunk_ids, dvecs):
            vecs.setdefault(cid, v)
    _CHUNK_VEC_CACHE = vecs
    return vecs


def eval_corpus_tag(corpus_tag, gold):
    corpus, kept, gold_sets, dropped, keep = prepare(GRAN, gold, TASK, SECTIONS, corpus_tag)
    vecs = _combined_chunk_vectors()
    dvecs = np.stack([vecs[cid] for cid in corpus.chunk_ids])
    queries = [g["query"] for g in kept]
    qvecs = R.embed_queries(MODEL, queries, f"{TASK}_q")
    index = R.build_faiss(dvecs)
    bm25 = R.build_bm25(f"{GRAN}_s210_{corpus_tag}", corpus)
    d = R.dense_rank(index, qvecs, TOPK)
    b = R.bm25_rank(bm25, queries, TOPK)
    h = R.rrf_fuse([d, b], TOPK)
    return {"dense": metrics(d, gold_sets), "bm25": metrics(b, gold_sets), "hybrid": metrics(h, gold_sets)}, len(kept), dropped


def strict(res, n_kept, n_total):
    ratio = n_kept / n_total
    return {mode: {m: round(v * ratio, 4) for m, v in d.items()} for mode, d in res.items()}


def main():
    retain_retrieval, retain_coverage, tag_C, tag_D = setup_membership()
    gold = load_gold(TASK)

    results = {}
    for tag in ("426", "259proposed", "259_retrieval_aware", "phase6_D"):
        res, n_kept, dropped = eval_corpus_tag(tag, gold)
        results[tag] = (res, n_kept, dropped)
        print(f"\n=== {tag} (n_kept={n_kept}, dropped={dropped}) ===")
        for mode in ("dense", "bm25", "hybrid"):
            m = res[mode]
            print(f"  {mode}: Recall@10={m['Recall@10']:.4f} MRR={m['MRR']:.4f} nDCG@10={m['nDCG@10']:.4f} Hit@10={m['Hit@10']:.4f}")

    n_total = results["426"][1]  # 1915, dropped=0 기준선
    strict_results = {tag: strict(res, n_kept, n_total) for tag, (res, n_kept, _) in results.items()}

    print("\n=== strict(1,915 모수 환산) 비교 — hybrid ===")
    for tag in ("426", "259proposed", "259_retrieval_aware", "phase6_D"):
        m = strict_results[tag]["hybrid"]
        print(f"  {tag}: Recall@10={m['Recall@10']:.4f} MRR={m['MRR']:.4f} nDCG@10={m['nDCG@10']:.4f} Hit@10={m['Hit@10']:.4f}")

    # ---- independent eval prototype 재검증 ----
    import json
    indep_records = []
    with open(INDEP_EVAL_JSONL, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                indep_records.append(json.loads(line))

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    chunked_cas = {r[0] for r in cur.execute("SELECT DISTINCT cas_number FROM rag_chunks")}
    for tag in ("426", "259proposed", "259_retrieval_aware", "phase6_D"):
        cur.execute("SELECT cas_number FROM rag_corpus_membership WHERE corpus_tag=?", (tag,))
        members = {r[0] for r in cur.fetchall()}
        n_indexed = 0
        for rec in indep_records:
            if rec.get("kind") != "pair":
                continue
            if rec["cas_a"] in members and rec["cas_b"] in members:
                n_indexed += 1
        print(f"independent eval prototype: corpus={tag} 내 실제 both-substances-present 쌍 = {n_indexed}/{sum(1 for r in indep_records if r.get('kind')=='pair')}")
    con.close()

    write_report(results, strict_results, retain_retrieval, retain_coverage, n_total)
    print("\n리포트:", OUT_MD)


def write_report(results, strict_results, retain_retrieval, retain_coverage, n_total):
    L = ["# PHASE 6 §8 — 후보군 A/B/C/D 비교 결과", "",
         "**생성**: `04_rag_agent/phase6_selection_scenarios.py` (426 캐시 임베딩 재사용, 재임베딩 없음)", "",
         f"- A = 426 baseline", f"- B = 259 proposed(PHASE4)",
         f"- C = 259 + RETAIN_RETRIEVAL({len(retain_retrieval)}종) = 259_retrieval_aware",
         f"- D = C + RETAIN_COVERAGE({len(retain_coverage)}종) = phase6_D", ""]

    L.append("## selection-aware(각 코퍼스 자체 유효질의 기준) 결과")
    L.append("")
    L.append("| candidate | n_substances | n_kept_queries | dropped | hybrid Recall@10 | MRR | nDCG@10 | Hit@10 |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    names = {"426": "A(426)", "259proposed": "B(259)", "259_retrieval_aware": "C(259+RET)", "phase6_D": "D(C+COV)"}
    sizes = {"426": 426, "259proposed": 259, "259_retrieval_aware": 259 + len(retain_retrieval),
             "phase6_D": 259 + len(retain_retrieval) + len(retain_coverage)}
    for tag in ("426", "259proposed", "259_retrieval_aware", "phase6_D"):
        res, n_kept, dropped = results[tag]
        m = res["hybrid"]
        L.append(f"| {names[tag]} | {sizes[tag]} | {n_kept} | {dropped} | {m['Recall@10']:.4f} | {m['MRR']:.4f} | {m['nDCG@10']:.4f} | {m['Hit@10']:.4f} |")
    L.append("")

    L.append("## strict(1,915건 공통 모수 환산) 결과 — 공정 비교 기준")
    L.append("")
    L.append("| candidate | hybrid Recall@10 | MRR | nDCG@10 | Hit@10 |")
    L.append("|---|---:|---:|---:|---:|")
    for tag in ("426", "259proposed", "259_retrieval_aware", "phase6_D"):
        m = strict_results[tag]["hybrid"]
        L.append(f"| {names[tag]} | {m['Recall@10']:.4f} | {m['MRR']:.4f} | {m['nDCG@10']:.4f} | {m['Hit@10']:.4f} |")
    L.append("")

    a = strict_results["426"]["hybrid"]
    b = strict_results["259proposed"]["hybrid"]
    c = strict_results["259_retrieval_aware"]["hybrid"]
    d = strict_results["phase6_D"]["hybrid"]

    def recovery_pct(metric):
        gap = a[metric] - b[metric]
        if gap == 0:
            return None
        recovered = a[metric] - c[metric]
        return (1 - recovered / gap) * 100

    L.append("## Retrieval 성능 저하 회복률 (A-B 격차를 C가 얼마나 메우는가)")
    L.append("")
    L.append("| 지표 | A(426) | B(259) | C(259+RET) | A-B 격차 | C의 회복률 |")
    L.append("|---|---:|---:|---:|---:|---:|")
    for metric in ("Recall@10", "MRR", "nDCG@10", "Hit@10"):
        gap = a[metric] - b[metric]
        rec = recovery_pct(metric)
        rec_str = f"{rec:.1f}%" if rec is not None else "-"
        L.append(f"| {metric} | {a[metric]:.4f} | {b[metric]:.4f} | {c[metric]:.4f} | {gap:+.4f} | {rec_str} |")
    L.append("")

    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


if __name__ == "__main__":
    main()
