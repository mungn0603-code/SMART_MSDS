# -*- coding: utf-8 -*-
"""
PHASE 8 — 평가셋 확장(150→~220) + 물질별 marginal utility 분석 +
A(426)/B(259)/C(301)/D(354)/E(268, evidence-first) 동일조건 최종 비교.

E = phase8_final_selection_rule.py가 426종 전체에 최종 규칙을 적용한 결과 중
final_decision != REVIEW인 물질 전체(KEEP+KEEP_COVERAGE+KEEP_EMPIRICAL+
KEEP_RETRIEVAL_DIAGNOSTIC) — "현재 어떤 근거로든 적극적 keep 판정을 받은
최대 집합"이라는 명확한 규칙으로 정의됨(숫자를 먼저 정하지 않음).

읽기 전용(rag_corpus_membership에 'phase8_E' 1개만 신규 추가). undergrad_target_chemicals.csv
미변경.
"""
import csv
import json
import random
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\04_rag_agent")
sys.path.insert(0, r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\02_classification")

import numpy as np
import retrieval as R
from evalset_pairs import pair_verdict

ROOT = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS"
DB_PATH = ROOT + r"\reactivity_reference.db"
OLD_EVAL_JSONL = ROOT + r"\04_rag_agent\evalset\independent_eval_v2_2026-08-08.jsonl"
FINAL_CANDIDATES_CSV = ROOT + r"\01_collection\chemical_phase8_final_candidates_2026-08-08.csv"
OUT_EXPANDED_JSONL = ROOT + r"\04_rag_agent\evalset\independent_eval_v3_2026-08-08.jsonl"
OUT_EVAL_EXPANSION_CSV = ROOT + r"\01_collection\chemical_phase8_eval_expansion_2026-08-08.csv"
OUT_MARGINAL_CSV = ROOT + r"\01_collection\chemical_phase8_marginal_utility_2026-08-08.csv"
OUT_MD = Path(ROOT) / "docs" / "phase8_final_comparison_results_2026-08-08.md"

MODEL, GRAN, TOPK = "bge-m3-ko", "section", 10
SEED = 20260808
CAS_RE = re.compile(r"^sec::([^:]+)::")


def cas_of_chunk(cid):
    m = CAS_RE.match(cid)
    return m.group(1) if m else None


# =====================================================================
# ① 후보 E 등록
# =====================================================================
def register_candidate_e():
    with open(FINAL_CANDIDATES_CSV, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    e_members = [r["cas"] for r in rows if r["final_decision"] != "REVIEW"]
    con = sqlite3.connect(DB_PATH)
    con.execute("DELETE FROM rag_corpus_membership WHERE corpus_tag='phase8_E'")
    con.executemany("INSERT INTO rag_corpus_membership (corpus_tag, cas_number) VALUES (?,?)",
                     [("phase8_E", c) for c in e_members])
    con.commit()
    con.close()
    print(f"후보 E(final_decision != REVIEW) = {len(e_members)}종 등록")
    return set(e_members)


# =====================================================================
# ② 평가셋 확장(+70 목표): E 경계물질, 동일그룹 구별질의, NOT_TESTED REVIEW 보강
# =====================================================================
def expand_evalset(e_members):
    with open(OLD_EVAL_JSONL, encoding="utf-8") as f:
        old = [json.loads(l) for l in f if l.strip()]
    old_pairs = [r for r in old if r["kind"] == "pair"]
    used_keys = {tuple(sorted((r["cas_a"], r["cas_b"]))) for r in old_pairs}

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    names = dict(cur.execute("SELECT cas_number, chemical_name FROM chemicals"))
    groups = defaultdict(set)
    for cas, gid in cur.execute(
        "SELECT ch.cas_number, m.group_id FROM chemicals ch JOIN chemical_group_membership m ON m.chemical_id=ch.chemical_id"
    ):
        groups[cas].add(gid)
    matrix = {(a, b): cat for a, b, cat in cur.execute("SELECT group_a_id, group_b_id, category FROM compatibility_pairs")}
    self_react = dict(cur.execute("SELECT group_id, category FROM self_reactivity").fetchall())
    sec_chunks = defaultdict(list)
    chunk_text = {}
    for cid, cas, sec, text in cur.execute("SELECT chunk_id, cas_number, section, text FROM rag_chunks WHERE granularity='section' AND section IN (2,10)"):
        sec_chunks[(cas, sec)].append(cid)
        chunk_text[cid] = text
    cur.execute("SELECT cas_number FROM rag_corpus_membership WHERE corpus_tag='426'")
    collected_426 = [c for c in {r[0] for r in cur.fetchall()} if c in names]
    con.close()

    with open(ROOT + r"\01_collection\chemical_phase7_review134_status_2026-08-08.csv", encoding="utf-8-sig") as f:
        not_tested = [r["cas"] for r in csv.DictReader(f) if r["status"] == "REVIEW_NOT_TESTED"]

    def has_content(cas):
        return any(chunk_text.get(c, "").strip() not in ("", "자료없음")
                   for sec in (2, 10) for c in sec_chunks.get((cas, sec), []))

    usable = [c for c in collected_426 if has_content(c)]
    rng = random.Random(SEED + 1)

    def make(a, b, style_idx, note):
        key = tuple(sorted((a, b)))
        if key in used_keys or a == b:
            return None
        used_keys.add(key)
        worst, cats = pair_verdict(groups.get(a, set()), groups.get(b, set()), matrix, self_react)
        gold = []
        for cas in (a, b):
            for sec in (2, 10):
                gold += sec_chunks.get((cas, sec), [])
        gold_valid = [c for c in gold if chunk_text.get(c, "").strip() not in ("", "자료없음")]
        if not gold_valid:
            return None
        if style_idx % 2 == 0:
            query = f"{names[a]}와 {names[b]}를 함께 두어도 안전한가요?"
            style = "name_based"
        else:
            query = f"CAS {a}, {b} 물질을 혼합 보관해도 되는지 검토해줘."
            style = "cas_based"
        return {
            "query_id": f"indepv3::{a}::{b}", "query": query, "kind": "pair",
            "cas_a": a, "cas_b": b, "name_a": names[a], "name_b": names[b],
            "cameo_groups_a": sorted(groups.get(a, ())), "cameo_groups_b": sorted(groups.get(b, ())),
            "gold_risk_pair": worst, "gold_risk_pair_all": cats, "gold_section": sorted(gold_valid),
            "query_style": style, "note": note, "source": "phase8_eval_expansion_2026-08-08",
            "verification_method": "rule_based_self_check", "human_verified": False,
            "provenance_tier": "DIAGNOSTIC",
        }

    new_records = []
    idx = 0

    # (a) E 경계물질: E에는 없고 426엔 있는 물질(=REVIEW 158) 중 아직 미검증인 것 위주로 보강
    review_pool = [c for c in usable if c not in e_members]
    rng.shuffle(review_pool)
    for a in review_pool:
        partner_pool = [c for c in usable if c != a]
        rng.shuffle(partner_pool)
        for b in partner_pool[:5]:
            rec = make(a, b, idx, "E 경계물질(REVIEW) 검증 보강")
            if rec:
                new_records.append(rec)
                idx += 1
                break
        if len(new_records) >= 40:
            break

    # (b) 동일 CAMEO 그룹 내 구별 질의(hard negative: 같은 그룹이라 헷갈리기 쉬움)
    group_members = defaultdict(list)
    for cas in usable:
        for g in groups.get(cas, ()):
            group_members[g].append(cas)
    big_groups = [g for g, members in group_members.items() if len(members) >= 5]
    rng.shuffle(big_groups)
    for g in big_groups[:20]:
        members = group_members[g]
        rng.shuffle(members)
        a, b = members[0], members[1]
        rec = make(a, b, idx, f"동일그룹{g} 내 구별질의(hard)")
        if rec:
            new_records.append(rec)
            idx += 1

    # (c) NOT_TESTED REVIEW 물질 추가 보강
    rng.shuffle(not_tested)
    for a in not_tested:
        if a not in usable:
            continue
        partner_pool = [c for c in usable if c != a]
        rng.shuffle(partner_pool)
        for b in partner_pool[:5]:
            rec = make(a, b, idx, "REVIEW_NOT_TESTED 보강")
            if rec:
                new_records.append(rec)
                idx += 1
                break
        if len(new_records) >= 70:
            break

    combined = old_pairs + new_records
    with open(OUT_EXPANDED_JSONL, "w", encoding="utf-8") as f:
        for r in old_pairs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        for r in new_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        f.write(json.dumps({"query_id": "indepv3::group25::UNAVAILABLE", "query": None, "kind": "unavailable_group",
                             "group_id": 25, "status": "DATA_SCARCITY", "human_verified": False}, ensure_ascii=False) + "\n")

    with open(OUT_EVAL_EXPANSION_CSV, "w", newline="", encoding="utf-8-sig") as f:
        fields = ["query_id", "cas_a", "name_a", "cas_b", "name_b", "gold_risk_pair", "query_style", "note"]
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(new_records)

    print(f"기존 {len(old_pairs)}건 + 신규 {len(new_records)}건 = 총 {len(combined)}건")
    print("산출물:", OUT_EXPANDED_JSONL, "/", OUT_EVAL_EXPANSION_CSV)
    return combined


# =====================================================================
# ③ A/B/C/D/E 동일조건 비교(150+70건 확장 평가셋)
# =====================================================================
def _combined_chunk_vectors():
    vecs = {}
    for tag in ("426", "259proposed"):
        corpus = R.load_corpus(GRAN, corpus_tag=tag)
        dvecs = R.embed_corpus(MODEL, GRAN, corpus, corpus_tag=tag)
        for cid, v in zip(corpus.chunk_ids, dvecs):
            vecs.setdefault(cid, v)
    return vecs


def metrics_extended(ranks, gold_sets):
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
        acc["nDCG@10"] += dcg / idcg if idcg else 0.0
        per_query.append({"query_id": None, "rr": rr})
    return {k: v / n for k, v in acc.items()}, per_query


def prepare_for_tag(pairs, corpus_tag, chunk_vecs):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT cas_number FROM rag_corpus_membership WHERE corpus_tag=?", (corpus_tag,))
    members = {r[0] for r in cur.fetchall()}
    cur.execute("SELECT DISTINCT chunk_id, cas_number FROM rag_chunks WHERE granularity='section' AND section IN (2,10)")
    all_chunks = [(cid, cas) for cid, cas in cur.fetchall() if cas in members and cid in chunk_vecs]
    text_map = dict(cur.execute("SELECT chunk_id, text FROM rag_chunks WHERE granularity='section'"))
    con.close()
    chunk_ids = sorted({cid for cid, _ in all_chunks})
    pos = {cid: i for i, cid in enumerate(chunk_ids)}
    dvecs = np.stack([chunk_vecs[cid] for cid in chunk_ids]) if chunk_ids else np.zeros((0, 1024), dtype="float32")

    kept, gold_sets = [], []
    for g in pairs:
        gold_ids = [c for c in g["gold_section"] if c in pos]
        if gold_ids and g["cas_a"] in members and g["cas_b"] in members:
            kept.append(g)
            gold_sets.append({pos[c] for c in gold_ids})
    texts = [text_map.get(c, "") for c in chunk_ids]
    return chunk_ids, dvecs, kept, gold_sets, texts


def run_comparison(pairs):
    chunk_vecs = _combined_chunk_vectors()
    tags = {"A_426": "426", "B_259": "259proposed", "C_301": "259_retrieval_aware",
            "D_354": "phase7_D", "E_268": "phase8_E"}
    results = {}
    n_total = len(pairs)
    for label, tag in tags.items():
        chunk_ids, dvecs, kept, gold_sets, texts = prepare_for_tag(pairs, tag, chunk_vecs)
        if not kept:
            print(f"{label}: kept=0, 스킵")
            continue
        queries = [g["query"] for g in kept]
        qvecs = R.embed_queries(MODEL, queries, "phase8v3_q")
        index = R.build_faiss(dvecs)
        corpus_obj = R.Corpus(chunk_ids=chunk_ids, texts=texts, meta=[{}] * len(chunk_ids))
        bm25 = R.build_bm25(f"phase8v3_{tag}", corpus_obj)
        d = R.dense_rank(index, qvecs, TOPK)
        b = R.bm25_rank(bm25, queries, TOPK)
        h = R.rrf_fuse([d, b], TOPK)
        m, per_q = metrics_extended(h, gold_sets)
        results[label] = {"metrics": m, "n_kept": len(kept), "n_total": n_total}
        print(f"\n=== {label} (n_kept={len(kept)}/{n_total}) ===")
        for k, v in m.items():
            print(f"  {k}: {v:.4f}")

    print("\n=== strict(전체 모수 환산) ===")
    strict = {}
    for label, res in results.items():
        ratio = res["n_kept"] / n_total
        strict[label] = {k: v * ratio for k, v in res["metrics"].items()}
        print(f"  {label}: Recall@10={strict[label]['Recall@10']:.4f} MRR={strict[label]['MRR']:.4f} nDCG@10={strict[label]['nDCG@10']:.4f}")

    return results, strict, n_total


def main():
    e_members = register_candidate_e()
    combined = expand_evalset(e_members)
    results, strict, n_total = run_comparison(combined)

    L = ["# PHASE 8 — 확장 평가셋 기반 A/B/C/D/E 최종 비교", "",
         f"**평가셋 규모**: {n_total}건(기존 150 + 신규 확장분)", "",
         "## strict(공통 모수 환산)", "",
         "| candidate | n_substances | n_kept | Recall@1 | Recall@5 | Recall@10 | MRR | nDCG@10 | Hit@10 |",
         "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    sizes = {"A_426": 426, "B_259": 259, "C_301": 301, "D_354": "?", "E_268": len(e_members)}
    for label in results:
        s = strict[label]
        L.append(f"| {label} | {sizes.get(label,'?')} | {results[label]['n_kept']} | {s['Recall@1']:.4f} | "
                  f"{s['Recall@5']:.4f} | {s['Recall@10']:.4f} | {s['MRR']:.4f} | {s['nDCG@10']:.4f} | {s['Hit@10']:.4f} |")
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("\n리포트:", OUT_MD)


if __name__ == "__main__":
    main()
