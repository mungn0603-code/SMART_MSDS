# -*- coding: utf-8 -*-
"""
PHASE 6 — REMOVE_CONFIRMED(63)/MERGE_REDUNDANT(118) = 181종에 실제 retrieval
contribution(R)을 추가해 재평가한다.

방법론 요약
-----------
- R(retrieval contribution): 426 코퍼스(캐시된 임베딩/BM25 재사용, 재임베딩 없음)에서
  gold_pair.jsonl 전체(1,915건) hybrid 랭킹을 뽑고, 각 질의의 gold_section 청크가
  "누구 소유"인지 chunk_id(sec::{cas}::{section})에서 CAS를 파싱해 물질 단위로
  귀속시킨다. 물질 X의 R = X 자신의 청크가 X가 등장하는 질의들에서 top-10에 얼마나
  자주/얼마나 높은 순위로 검색되는가(hit_rate@10, mean reciprocal rank).
  이렇게 하면 "쌍 전체가 dropped됐는가"가 아니라 "이 물질 자신의 정보가 실제로
  검색되고 있었는가"를 물질 단위로 분리해서 볼 수 있다.
- E(independent evidence): Phase3의 section10_has_real_evidence(자기 §10 실질근거)
  + 신규로 §2(GHS분류) 실질 내용 존재 여부(Phase4의 NEEDS_EVIDENCE 판정과 동일 로직
  재사용) — 두 신호를 합쳐 0/1/2로 강도화.
- C(coverage contribution): PHASE4 판정 당시(426 기준) "sole/scarce group member
  아님"이었던 게 REMOVE_CONFIRMED/MERGE_REDUNDANT 편입 조건이었다. 이번엔 **259
  기준으로 다시** 그룹 대표물질 수를 계산해서, 181종을 동시에 뺀 누적효과로 그룹이
  새로 scarce해지지 않았는지 재확인한다(개별 판단이 누적효과를 놓쳤을 가능성 점검).
- D(redundancy): 같은 signature cluster 크기(대표 포함) — 클수록 중복성 높음.
- S(data availability): 전부 이미 KOSHA 4섹션 확보됨 — True 고정(재확인만).

읽기 전용 — DB의 rag_chunks/rag_corpus_membership 외 어떤 것도 쓰지 않는다.
undergrad_target_chemicals.csv 미변경.
"""
import csv
import re
import sqlite3
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\04_rag_agent")
sys.path.insert(0, r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\02_classification")

from provenance_audit import DB_PATH, CSV_PATH, s10_categories_for_text  # noqa: E402
import retrieval as R  # noqa: E402
from run_ab import load_gold, prepare, TOPK  # noqa: E402

ROOT = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS"
PHASE4_CSV = ROOT + r"\01_collection\chemical_phase4_adjudication_2026-08-08.csv"
PHASE3_CSV = ROOT + r"\01_collection\chemical_phase3_reassessment_2026-08-08.csv"
AUDIT_CSV = ROOT + r"\01_collection\chemical_selection_audit_dataset_2026-08-08.csv"

OUT_CSV = ROOT + r"\01_collection\chemical_phase6_retrieval_reassessment_2026-08-08.csv"
OUT_QUERY_CSV = ROOT + r"\01_collection\chemical_phase6_query_level_2026-08-08.csv"

TASK, SECTIONS, MODEL, GRAN = "pair", {2, 10}, "bge-m3-ko", "section"
CAS_RE = re.compile(r"^sec::([^:]+)::")


def cas_of_chunk(chunk_id):
    m = CAS_RE.match(chunk_id)
    return m.group(1) if m else None


def main():
    # ---- 1) 426 코퍼스 hybrid 랭킹 전량 추출(캐시 재사용) ----
    gold = load_gold(TASK)
    corpus_426, kept_426, gold_sets_426, dropped_426, keep_426 = prepare(GRAN, gold, TASK, SECTIONS, "426")
    corpus_259, kept_259, gold_sets_259, dropped_259, keep_259 = prepare(GRAN, gold, TASK, SECTIONS, "259proposed")

    dvecs_full = R.embed_corpus(MODEL, GRAN, R.load_corpus(GRAN, corpus_tag="426"), corpus_tag="426")
    dvecs_426 = dvecs_full[keep_426] if keep_426 is not None else dvecs_full
    queries_426 = [g["query"] for g in kept_426]
    qvecs_426 = R.embed_queries(MODEL, queries_426, f"{TASK}_q")
    index_426 = R.build_faiss(dvecs_426)
    bm25_426 = R.build_bm25(f"{GRAN}_s210_426", corpus_426)

    d_ranks = R.dense_rank(index_426, qvecs_426, TOPK)
    b_ranks = R.bm25_rank(bm25_426, queries_426, TOPK)
    h_ranks = R.rrf_fuse([d_ranks, b_ranks], TOPK)

    qids_259 = {g["query_id"] for g in kept_259}
    chunk_ids_426 = corpus_426.chunk_ids

    # ---- 2) 질의별/청크별 rank 기록 ----
    query_rows = []
    per_cas_hits = defaultdict(list)  # cas -> [ (rank_or_None, query_id, in_259) ]
    for i, g in enumerate(kept_426):
        gold_ids = g["gold_section"] if isinstance(g["gold_section"], list) else [g["gold_section"]]
        ranked = [chunk_ids_426[d] if d >= 0 else None for d in h_ranks[i]]
        pos_of = {cid: p + 1 for p, cid in enumerate(ranked) if cid}
        in_259 = g["query_id"] in qids_259
        for gid in gold_ids:
            cas = cas_of_chunk(gid)
            if not cas:
                continue
            rank = pos_of.get(gid)
            per_cas_hits[cas].append((rank, g["query_id"], in_259))
            query_rows.append({
                "query_id": g["query_id"], "cas_a": g["cas_a"], "cas_b": g["cas_b"],
                "gold_chunk": gid, "gold_chunk_cas": cas, "rank_426": rank if rank else "",
                "in_259_valid": in_259,
            })

    with open(OUT_QUERY_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["query_id", "cas_a", "cas_b", "gold_chunk", "gold_chunk_cas",
                                           "rank_426", "in_259_valid"])
        w.writeheader()
        w.writerows(query_rows)
    print(f"질의-청크 레벨 기록: {len(query_rows)}행 -> {OUT_QUERY_CSV}")

    def retrieval_contribution(cas):
        hits = per_cas_hits.get(cas, [])
        n = len(hits)
        if n == 0:
            return {"n_gold_queries": 0, "hit_rate_10": None, "mean_rank": None, "mrr": None,
                     "n_queries_dropped_from_259": 0}
        found = [r for r, _, _ in hits if r is not None]
        hit10 = sum(1 for r in found if r <= 10)
        mrr = sum((1.0 / r) if r else 0.0 for r, _, _ in hits) / n
        dropped_259 = sum(1 for _, _, in259 in hits if not in259)
        return {
            "n_gold_queries": n,
            "hit_rate_10": round(hit10 / n, 4),
            "mean_rank": round(sum(found) / len(found), 2) if found else None,
            "mrr": round(mrr, 4),
            "n_queries_dropped_from_259": dropped_259,
        }

    # ---- 3) Phase1/3/4 산출물 로드 ----
    with open(PHASE4_CSV, encoding="utf-8-sig") as f:
        phase4_rows = {r["cas"]: r for r in csv.DictReader(f)}
    with open(PHASE3_CSV, encoding="utf-8-sig") as f:
        phase3_rows = {r["cas"]: r for r in csv.DictReader(f)}
    with open(AUDIT_CSV, encoding="utf-8-sig") as f:
        audit_rows = {r["cas_number"]: r for r in csv.DictReader(f)}

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    chem_by_cas = {}
    for cid, cas, name in cur.execute("SELECT chemical_id, cas_number, chemical_name FROM chemicals"):
        chem_by_cas[cas] = (cid, name)
    membership = defaultdict(list)
    for cid, gid in cur.execute("SELECT chemical_id, group_id FROM chemical_group_membership"):
        membership[cid].append(gid)
    group_names = dict(cur.execute("SELECT group_id, group_name FROM reactivity_groups").fetchall())
    section2_has_content = defaultdict(bool)
    for cas, detail in cur.execute("SELECT cas_number, item_detail FROM msds_sections WHERE section=2"):
        d = (detail or "").strip()
        if d and d not in ("자료없음", "-", "해당없음"):
            section2_has_content[cas] = True
    cur.execute("SELECT cas_number FROM rag_corpus_membership WHERE corpus_tag='259proposed'")
    cas_in_259 = {r[0] for r in cur.fetchall()}
    cur.execute("SELECT cas_number FROM rag_corpus_membership WHERE corpus_tag='426'")
    cas_in_426 = {r[0] for r in cur.fetchall()}
    con.close()

    # 259 기준 fresh 그룹 멤버 수(181종 동시 제거 누적효과 확인용)
    group_member_count_259 = Counter()
    for cas in cas_in_259:
        cid, _ = chem_by_cas.get(cas, (None, None))
        for g in membership.get(cid, []):
            group_member_count_259[g] += 1

    targets = [cas for cas, r in phase4_rows.items() if r["phase4_status"] in ("REMOVE_CONFIRMED", "MERGE_REDUNDANT")]
    print(f"재평가 대상(REMOVE_CONFIRMED+MERGE_REDUNDANT): {len(targets)}종")

    # cluster 크기(대표 포함) 계산용
    cluster_size = Counter()
    for cas, r in phase4_rows.items():
        if r["phase4_status"] == "MERGE_REDUNDANT" and r["merge_cluster_id"]:
            cluster_size[r["merge_cluster_id"]] += 1

    results = []
    for cas in targets:
        p4 = phase4_rows[cas]
        p3 = phase3_rows.get(cas, {})
        arow = audit_rows.get(cas, {})
        name = p4["chemical_name"]
        cid, _ = chem_by_cas.get(cas, (None, None))
        true_groups = sorted(membership.get(cid, [])) if cid else []

        rc = retrieval_contribution(cas)

        # E: 자기 §10 실질근거 + §2 실질내용
        has_s10 = str(p3.get("section10_has_real_evidence", "")).strip() == "True"
        has_s2 = section2_has_content.get(cas, False)
        E_score = int(has_s10) + int(has_s2)

        # C: 259 기준(누적효과 반영) 소속 그룹 중 하나라도 <=2종인가
        scarce_groups_259 = [g for g in true_groups if group_member_count_259.get(g, 0) <= 2]
        C_flag = bool(scarce_groups_259)

        # D: 같은 cluster 크기(대표 포함) — MERGE_REDUNDANT만 cluster_id 있음
        cluster_id = p4.get("merge_cluster_id", "")
        cluster_total = cluster_size.get(cluster_id, 0) + 1 if cluster_id else (2 if p4["phase4_status"] == "REMOVE_CONFIRMED" else 1)

        # R: retrieval 등급화(임계치는 데이터 분포 보고 절 이후 §2에서 함께 문서화)
        if rc["n_gold_queries"] == 0:
            R_tier = "NO_DATA"
        elif rc["hit_rate_10"] is not None and rc["hit_rate_10"] >= 0.8 and rc["n_gold_queries"] >= 3:
            R_tier = "HIGH"
        elif rc["hit_rate_10"] is not None and rc["hit_rate_10"] >= 0.5:
            R_tier = "MEDIUM"
        else:
            R_tier = "LOW"

        results.append({
            "cas": cas, "chemical_name": name,
            "phase4_status": p4["phase4_status"],
            "phase4_reason": p4["reason"],
            "merge_cluster_id": cluster_id,
            "representative_cas": p4.get("representative_cas", ""),
            "true_cameo_groups": ";".join(str(g) for g in true_groups),
            "group_names": ";".join(group_names.get(g, "") for g in true_groups),
            "in_426": cas in cas_in_426,
            "in_259": cas in cas_in_259,
            "n_gold_queries": rc["n_gold_queries"],
            "n_queries_dropped_from_259": rc["n_queries_dropped_from_259"],
            "hit_rate_10_426": rc["hit_rate_10"],
            "mean_rank_426": rc["mean_rank"],
            "mrr_426": rc["mrr"],
            "R_tier": R_tier,
            "E_score": E_score,
            "has_own_s10_evidence": has_s10,
            "has_own_s2_content": has_s2,
            "C_scarce_in_259": C_flag,
            "scarce_groups_259": ";".join(str(g) for g in scarce_groups_259),
            "D_cluster_total_size": cluster_total,
            "S_data_available": True,
            "safety_flag": arow.get("safety_flag", "NOT_CHECKED"),
        })

    # ---- 4) 5-분류 재분류 (결정론적 규칙, 가중치 미사용 — §6 가중치는 별도 안정성 점검용) ----
    # 우선순위: ① 259 기준 신규 scarce(누적효과) -> RETAIN_COVERAGE
    #          ② R=HIGH -> RETAIN_RETRIEVAL
    #          ③ R=MEDIUM 또는 NO_DATA(gold_pair 미평가 = 불확실, 강제판정 금지) -> REVIEW
    #          ④ 그 외(R=LOW, 실제 근거상 성능이 나쁨) -> 원 phase4_status 유지(REMOVE_CONFIRMED)
    for r in results:
        if r["C_scarce_in_259"]:
            r["phase6_status"] = "RETAIN_COVERAGE"
            r["phase6_reason"] = f"259 기준 재계산 시 소속 그룹({r['scarce_groups_259']})이 신규로 대표물질 <=2종(누적 제거 효과) — 개별판단이 놓친 부분"
        elif r["R_tier"] == "HIGH":
            r["phase6_status"] = "RETAIN_RETRIEVAL"
            r["phase6_reason"] = f"426에서 자기 청크 hit_rate@10={r['hit_rate_10_426']}(n={r['n_gold_queries']}) — 실제 검색 기여 확인됨"
        elif r["R_tier"] in ("MEDIUM", "NO_DATA"):
            r["phase6_status"] = "REVIEW"
            r["phase6_reason"] = ("retrieval 근거 애매(MEDIUM)" if r["R_tier"] == "MEDIUM"
                                    else "gold_pair.jsonl에 이 물질 관련 질의가 전혀 없어 retrieval 근거 자체가 없음(불확실 — 강제판정 안 함)")
        else:
            r["phase6_status"] = "REMOVE_CONFIRMED"
            r["phase6_reason"] = f"426에서도 자기 청크 검색 성능이 낮음(hit_rate@10={r['hit_rate_10_426']}) — 제거 유지"

    # ---- 5) 가중치 시나리오 안정성 점검(결정에는 미사용, 로버스트니스 검증 전용) ----
    R_NORM = {"HIGH": 1.0, "MEDIUM": 0.6, "LOW": 0.2, "NO_DATA": 0.3}
    SCENARIOS = {
        "selection_only":        {"E": 0.4, "C": 0.4, "R": 0.0, "D": 0.1, "S": 0.1},
        "selection_plus_retrieval": {"E": 0.2, "C": 0.2, "R": 0.3, "D": 0.15, "S": 0.15},
        "retrieval_heavy":       {"E": 0.1, "C": 0.1, "R": 0.6, "D": 0.1, "S": 0.1},
        "coverage_heavy":        {"E": 0.1, "C": 0.6, "R": 0.1, "D": 0.1, "S": 0.1},
    }
    for r in results:
        e_norm = r["E_score"] / 2
        c_norm = 1.0 if r["C_scarce_in_259"] else 0.0
        r_norm = R_NORM[r["R_tier"]]
        d_norm = 1 - min(r["D_cluster_total_size"] / 10, 1.0)  # 클러스터 작을수록(=덜 중복) 유지쪽 가점
        s_norm = 1.0
        decisions = {}
        for name, w in SCENARIOS.items():
            score = w["E"] * e_norm + w["C"] * c_norm + w["R"] * r_norm + w["D"] * d_norm + w["S"] * s_norm
            decisions[name] = "RETAIN" if score >= 0.5 else "REMOVE"
            r[f"scenario_{name}"] = round(score, 3)
        n_retain = sum(1 for v in decisions.values() if v == "RETAIN")
        r["scenario_stable"] = n_retain in (0, len(SCENARIOS))
        r["scenario_retain_count"] = n_retain

    fields = list(results[0].keys())
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(results)

    print(f"\nR_tier 분포: {dict(Counter(r['R_tier'] for r in results))}")
    print(f"E_score 분포: {dict(Counter(r['E_score'] for r in results))}")
    print(f"C_scarce_in_259=True 종수: {sum(1 for r in results if r['C_scarce_in_259'])}")
    print(f"n_gold_queries=0(gold_pair에 아예 안 나오는 물질) 종수: {sum(1 for r in results if r['n_gold_queries']==0)}")
    print(f"\nphase6_status 분포: {dict(Counter(r['phase6_status'] for r in results))}")
    print(f"scenario_stable(4개 시나리오 전부 동일 결정) 종수: {sum(1 for r in results if r['scenario_stable'])}/{len(results)}")
    unstable = [r for r in results if not r["scenario_stable"]]
    print(f"scenario 불안정(가중치에 따라 결정 바뀜) 종수: {len(unstable)}")
    print(f"\n산출물: {OUT_CSV}")

    return results


if __name__ == "__main__":
    main()
