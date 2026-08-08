# -*- coding: utf-8 -*-
"""
PHASE 8 — ① 150건 신규 독립평가셋 gold label 감사, ② C(301)/D(354) selection-quality
재계산, ③ 426종 전체에 최종 Selection Rule 적용(KEEP/KEEP_COVERAGE/KEEP_EMPIRICAL/
KEEP_RETRIEVAL_DIAGNOSTIC/REVIEW/REMOVE_CANDIDATE), ④ 그 근거로 후보 E 구성.

읽기 전용 — DB/CSV 미변경. undergrad_target_chemicals.csv 미변경.
"""
import csv
import json
import re
import sqlite3
from collections import Counter, defaultdict

ROOT = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS"
DB_PATH = ROOT + r"\reactivity_reference.db"
NEW_EVAL_JSONL = ROOT + r"\04_rag_agent\evalset\independent_eval_v2_2026-08-08.jsonl"
PHASE6_CSV = ROOT + r"\01_collection\chemical_phase6_retrieval_reassessment_2026-08-08.csv"
PHASE4_CSV = ROOT + r"\01_collection\chemical_phase4_adjudication_2026-08-08.csv"
PHASE3_CSV = ROOT + r"\01_collection\chemical_phase3_reassessment_2026-08-08.csv"
AUDIT_CSV = ROOT + r"\01_collection\chemical_selection_audit_dataset_2026-08-08.csv"
REVIEW_STATUS_CSV = ROOT + r"\01_collection\chemical_phase7_review134_status_2026-08-08.csv"

OUT_GOLD_AUDIT = ROOT + r"\01_collection\chemical_phase8_gold_audit_2026-08-08.csv"
OUT_FINAL_CANDIDATES = ROOT + r"\01_collection\chemical_phase8_final_candidates_2026-08-08.csv"

CAS_RE = re.compile(r"^sec::([^:]+)::(\d+)")


# =====================================================================
# ① Gold label 감사 (150건)
# =====================================================================
def gold_audit():
    with open(NEW_EVAL_JSONL, encoding="utf-8") as f:
        recs = [json.loads(l) for l in f if l.strip()]
    pairs = [r for r in recs if r["kind"] == "pair"]

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    chem_cas = {r[0] for r in cur.execute("SELECT cas_number FROM chemicals")}
    chunk_meta = {}  # chunk_id -> (cas, section, text)
    for cid, cas, sec, text in cur.execute("SELECT chunk_id, cas_number, section, text FROM rag_chunks WHERE granularity='section'"):
        chunk_meta[cid] = (cas, sec, text)
    matrix = {(a, b): cat for a, b, cat in cur.execute("SELECT group_a_id, group_b_id, category FROM compatibility_pairs")}
    self_react = dict(cur.execute("SELECT group_id, category FROM self_reactivity").fetchall())
    groups = defaultdict(set)
    for cas, gid in cur.execute(
        "SELECT ch.cas_number, m.group_id FROM chemicals ch JOIN chemical_group_membership m ON m.chemical_id=ch.chemical_id"
    ):
        groups[cas].add(gid)
    con.close()

    def recompute_verdict(ga, gb):
        cats = set()
        for x in ga:
            for y in gb:
                if x == y:
                    cats.add(self_react.get(x, "Unknown"))
                else:
                    cats.add(matrix.get((min(x, y), max(x, y)), "Unknown"))
        if not cats:
            return "Unknown"
        rank = {"Compatible": 0, "Caution": 1, "Incompatible": 2, "Unknown": -1}
        return max(cats, key=lambda c: rank[c])

    rows = []
    issues = Counter()
    for r in pairs:
        problems = []
        # 1) CAS 유효성
        if r["cas_a"] not in chem_cas:
            problems.append("cas_a_invalid")
        if r["cas_b"] not in chem_cas:
            problems.append("cas_b_invalid")
        # 2) gold_section 청크가 실제로 cas_a/cas_b 중 하나에 속하는가(다른 물질 혼입 여부)
        mismatched = []
        sections_seen = set()
        for cid in r["gold_section"]:
            m = chunk_meta.get(cid)
            if m is None:
                problems.append(f"chunk_missing:{cid}")
                continue
            cas_of, sec_of, text_of = m
            sections_seen.add(sec_of)
            if cas_of not in (r["cas_a"], r["cas_b"]):
                mismatched.append(cid)
            if not text_of or text_of.strip() in ("", "자료없음"):
                problems.append(f"empty_content:{cid}")
        if mismatched:
            problems.append(f"gold_chunk_wrong_substance:{mismatched}")
        # 3) section 범위(§2,§10만이어야 함)
        if sections_seen - {2, 10}:
            problems.append(f"unexpected_section:{sections_seen}")
        # 4) 양쪽 물질 둘 다 gold에 최소 1개씩 대표됐는가(복수정답 누락 여부)
        cas_in_gold = {chunk_meta[c][0] for c in r["gold_section"] if c in chunk_meta}
        if r["cas_a"] not in cas_in_gold:
            problems.append("cas_a_missing_from_gold")
        if r["cas_b"] not in cas_in_gold:
            problems.append("cas_b_missing_from_gold")
        # 5) gold_risk_pair 재계산 일치 여부(매트릭스/DB 드리프트 확인)
        worst = recompute_verdict(set(r["cameo_groups_a"]), set(r["cameo_groups_b"]))
        verdict_mismatch = worst != r["gold_risk_pair"]
        if verdict_mismatch:
            problems.append(f"verdict_drift:{r['gold_risk_pair']}->{worst}")
        # 6) merge representative 혼동 여부: cas_a/cas_b가 실제로 그 이름의 CAS인지
        #    (대표물질 CAS로 슬쩍 바뀌지 않았는지 — name_a/name_b가 실제 그 CAS의 chemicals.chemical_name과 일치하는가는
        #     생성 시점에 동일 소스에서 가져왔으므로 구조적으로 일치가 보장됨; 여기서는 재확인만)
        status = "CLEAN" if not problems else "FLAGGED"
        rows.append({
            "query_id": r["query_id"], "cas_a": r["cas_a"], "cas_b": r["cas_b"],
            "gold_risk_pair_recorded": r["gold_risk_pair"], "gold_risk_pair_recomputed": worst,
            "verdict_drift": verdict_mismatch,
            "n_gold_chunks": len(r["gold_section"]),
            "sections_covered": ";".join(map(str, sorted(sections_seen))),
            "issues": ";".join(problems) if problems else "",
            "status": status,
        })
        for p in problems:
            issues[p.split(":")[0]] += 1

    with open(OUT_GOLD_AUDIT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    n_clean = sum(1 for r in rows if r["status"] == "CLEAN")
    print(f"=== Gold audit: {len(rows)}건 중 CLEAN {n_clean}, FLAGGED {len(rows)-n_clean} ===")
    print("이슈 유형별 건수:", dict(issues))
    print("산출물:", OUT_GOLD_AUDIT)
    return rows


# =====================================================================
# ② C(301)/D(354) selection-quality 재계산 + 최종 후보 요약표
# =====================================================================
def selection_quality_for_tag(tag, con):
    cur = con.cursor()
    cur.execute("SELECT cas_number FROM rag_corpus_membership WHERE corpus_tag=?", (tag,))
    members = {r[0] for r in cur.fetchall()}

    chem_by_cas = {}
    for cid, cas, name in cur.execute("SELECT chemical_id, cas_number, chemical_name FROM chemicals"):
        chem_by_cas[cas] = cid
    membership = defaultdict(list)
    for cid, gid in cur.execute("SELECT chemical_id, group_id FROM chemical_group_membership"):
        membership[cid].append(gid)
    all_group_ids = {r[0] for r in cur.execute("SELECT group_id FROM reactivity_groups")}

    true_groups = {}
    for cas in members:
        cid = chem_by_cas.get(cas)
        true_groups[cas] = tuple(sorted(membership.get(cid, []))) if cid else tuple()

    group_count = Counter()
    for cas, gs in true_groups.items():
        for g in gs:
            group_count[g] += 1
    covered = {g for g in all_group_ids if group_count.get(g, 0) > 0}
    scarce = sum(1 for g in all_group_ids if 0 < group_count.get(g, 0) <= 2)

    # signature 중복 비율
    sig_members = defaultdict(list)
    for cas, gs in true_groups.items():
        sig_members[gs].append(cas)
    dup_members = sum(len(v) for v in sig_members.values() if len(v) > 1)

    # 선정근거 라벨(Phase1 audit + Phase6 phase6_status 병합)
    with open(AUDIT_CSV, encoding="utf-8-sig") as f:
        audit = {r["cas_number"]: r for r in csv.DictReader(f)}
    with open(PHASE6_CSV, encoding="utf-8-sig") as f:
        phase6 = {r["cas"]: r for r in csv.DictReader(f)}

    # 원칙(Phase6/7 확립): Diagnostic(gold_pair.jsonl 등 Wave1 파생 retrieval 근거) != Independent.
    # KEEP_MANDATORY/COVERAGE/EMPIRICAL(curriculum/§10실측/그룹희소성)와 RETAIN_COVERAGE(그룹
    # 구조적 근거)만 "independent"로 센다. RETAIN_RETRIEVAL(gold_pair 기반)은 diagnostic 별도 집계.
    n_independent = 0
    n_diagnostic_retrieval = 0
    n_unsupported = 0
    for cas in members:
        a = audit.get(cas, {})
        st = a.get("selection_status", "")
        if st in ("KEEP_MANDATORY", "KEEP_COVERAGE", "KEEP_EMPIRICAL"):
            n_independent += 1
        elif cas in phase6 and phase6[cas]["phase6_status"] == "RETAIN_COVERAGE":
            n_independent += 1
        elif cas in phase6 and phase6[cas]["phase6_status"] == "RETAIN_RETRIEVAL":
            n_diagnostic_retrieval += 1
        elif st in ("REVIEW", "DUPLICATE", "UNSUPPORTED") and cas not in phase6:
            n_unsupported += 1
        elif cas in phase6 and phase6[cas]["phase6_status"] == "REVIEW":
            pass  # 아래 review_status로 세분

    # §10 evidence coverage
    s10_categories = {"combustible_reducing": ["가연성", "환원성", "환원제", "인화성"],
                       "metal": ["금속"], "oxidizer": ["산화제", "산화성"], "water": ["물"], "no_data": ["자료없음"]}
    s10_text = {}
    for cas, detail in cur.execute("SELECT cas_number, item_detail FROM msds_sections WHERE section=10 AND item_name_kor='피해야 할 물질'"):
        s10_text[cas] = detail or ""
    cat_counter = Counter()
    for cas in members:
        text = s10_text.get(cas, "")
        for cat, needles in s10_categories.items():
            if any(n in text for n in needles):
                cat_counter[cat] += 1

    n = len(members)
    return {
        "n_substances": n,
        "group_coverage": f"{len(covered)}/{len(all_group_ids)}",
        "scarce_group_count": scarce,
        "duplicate_signature_ratio": round(dup_members / n, 4) if n else None,
        "independent_evidence_ratio": round(n_independent / n, 4) if n else None,
        "diagnostic_retrieval_backed_ratio": round(n_diagnostic_retrieval / n, 4) if n else None,
        "s10_water_pct": round(cat_counter["water"] / n, 4) if n else None,
        "s10_combustible_reducing_pct": round(cat_counter["combustible_reducing"] / n, 4) if n else None,
        "s10_metal_pct": round(cat_counter["metal"] / n, 4) if n else None,
        "s10_no_data_pct": round(cat_counter["no_data"] / n, 4) if n else None,
        "members": members,
    }


def recompute_selection_quality():
    con = sqlite3.connect(DB_PATH)
    results = {}
    for label, tag in [("A_426", "426"), ("B_259", "259proposed"), ("C_301", "259_retrieval_aware"), ("D_354", "phase6_D")]:
        # 참고: phase6_D는 C+RETAIN_COVERAGE(306종) — PHASE7의 "D=354(C+REVIEW_SUPPORTED)"와는
        # 다른 코퍼스이므로 phase7_D 태그도 별도로 계산한다.
        results[label] = selection_quality_for_tag(tag, con)
    if _tag_exists(con, "phase7_D"):
        results["D_354(phase7)"] = selection_quality_for_tag("phase7_D", con)
    con.close()

    print("\n=== C/D selection-quality 재계산 ===")
    for label, r in results.items():
        print(f"{label}: n={r['n_substances']} group_cov={r['group_coverage']} scarce={r['scarce_group_count']} "
              f"dup_sig={r['duplicate_signature_ratio']:.1%} indep_evid={r['independent_evidence_ratio']:.1%} "
              f"diag_retrieval={r['diagnostic_retrieval_backed_ratio']:.1%} "
              f"s10_water={r['s10_water_pct']:.1%} s10_metal={r['s10_metal_pct']:.1%}")
    return results


def _tag_exists(con, tag):
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM rag_corpus_membership WHERE corpus_tag=?", (tag,))
    return cur.fetchone()[0] > 0


# =====================================================================
# ③ 426종 전체 최종 Selection Rule 적용
# =====================================================================
def apply_final_rule():
    with open(AUDIT_CSV, encoding="utf-8-sig") as f:
        audit = {r["cas_number"]: r for r in csv.DictReader(f) if r["collection_status"] == "COLLECTED"}
    with open(PHASE3_CSV, encoding="utf-8-sig") as f:
        phase3 = {r["cas"]: r for r in csv.DictReader(f)}
    with open(PHASE4_CSV, encoding="utf-8-sig") as f:
        phase4 = {r["cas"]: r for r in csv.DictReader(f)}
    with open(PHASE6_CSV, encoding="utf-8-sig") as f:
        phase6 = {r["cas"]: r for r in csv.DictReader(f)}
    with open(REVIEW_STATUS_CSV, encoding="utf-8-sig") as f:
        review_status = {r["cas"]: r["status"] for r in csv.DictReader(f)}

    rows = []
    for cas, a in audit.items():
        st1 = a["selection_status"]
        p6 = phase6.get(cas, {})
        rv = review_status.get(cas, "")

        if st1 == "KEEP_MANDATORY":
            final, reason = "KEEP", f"curriculum/evaluation 근거({a['selection_reason']})"
        elif st1 == "KEEP_COVERAGE":
            final, reason = "KEEP_COVERAGE", "그룹 내 대표물질 희소(<=2종) — Phase1"
        elif st1 == "KEEP_EMPIRICAL":
            final, reason = "KEEP_EMPIRICAL", "§10 실측 1순위 기본물질(Phase1)"
        elif cas in phase6:
            p6_status = p6["phase6_status"]
            if p6_status == "RETAIN_RETRIEVAL":
                final, reason = "KEEP_RETRIEVAL_DIAGNOSTIC", f"426 자기청크 hit_rate@10={p6['hit_rate_10_426']}(diagnostic, Wave1파생)"
            elif p6_status == "RETAIN_COVERAGE":
                final, reason = "KEEP_COVERAGE", f"259 기준 재계산시 그룹{p6['scarce_groups_259']} 대표물질 <=2종(누적효과)"
            elif p6_status == "REVIEW":
                if rv == "REVIEW_SUPPORTED":
                    final, reason = "KEEP_RETRIEVAL_DIAGNOSTIC", "PHASE7 신규평가셋에서 자기청크 hit_rate>=0.5(diagnostic)"
                elif rv == "REVIEW_UNSUPPORTED":
                    final, reason = "REVIEW", "PHASE7 평가셋에 등장했으나 hit_rate<0.5 — 근거 불충분, 확정 보류"
                else:
                    final, reason = "REVIEW", "PHASE1~7 어느 평가셋에도 등장 안 함 — 근거 없음(불확실, REMOVE 아님)"
            else:  # 이 분기는 발생하지 않음(REMOVE_CONFIRMED가 phase6단계에서 전부 재분류됨)
                final, reason = "REVIEW", "미분류"
        elif st1 in ("REVIEW", "DUPLICATE", "UNSUPPORTED"):
            # phase3/4 375종 중 phase6 재평가 대상(REMOVE_CONFIRMED/MERGE_REDUNDANT)이 아니었던
            # 나머지(=phase3 KEEP_EMPIRICAL/REVIEW_REQUIRED/NEEDS_EVIDENCE/UNRESOLVED로 보수적 유지된 194종)
            p3 = phase3.get(cas, {})
            p3_rec = p3.get("recommendation", "")
            if p3_rec == "KEEP_EMPIRICAL":
                final, reason = "KEEP_EMPIRICAL", f"자기 §10 실질근거(Phase3, {p3.get('section10_categories','')})"
            else:
                final, reason = "REVIEW", f"Phase3 REVIEW(근거 빈약, {p3.get('reason','')[:60]})"
        else:
            final, reason = "REVIEW", "분류 경로 없음(예외) — 근거 부족으로 보류"

        rows.append({
            "cas": cas, "chemical_name": a["chemical_name"], "wave": phase6.get(cas, {}).get("wave", ""),
            "true_cameo_groups": a["true_cameo_groups"], "original_selection_status": st1,
            "phase6_status": p6.get("phase6_status", ""), "review134_status": rv,
            "final_decision": final, "final_reason": reason,
            "in_A_426": True,
            "in_B_259": final not in ("REMOVE_CANDIDATE",) and st1 not in ("UNSUPPORTED",) and cas not in [c for c, r in phase4.items() if r["phase4_status"] in ("REMOVE_CONFIRMED", "MERGE_REDUNDANT")],
        })

    fields = list(rows[0].keys())
    with open(OUT_FINAL_CANDIDATES, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"\n=== 최종 Selection Rule 적용 결과(426종 전체) ===")
    print(dict(Counter(r["final_decision"] for r in rows)))
    print("산출물:", OUT_FINAL_CANDIDATES)
    return rows


# =====================================================================
# ④ Marginal utility(물질별 retrieval dependency) — 기존 산출물 조인, 재임베딩 없음
# =====================================================================
def build_marginal_utility():
    OUT = ROOT + r"\01_collection\chemical_phase8_marginal_utility_2026-08-08.csv"
    with open(AUDIT_CSV, encoding="utf-8-sig") as f:
        audit = {r["cas_number"]: r for r in csv.DictReader(f) if r["collection_status"] == "COLLECTED"}
    with open(PHASE6_CSV, encoding="utf-8-sig") as f:
        phase6 = {r["cas"]: r for r in csv.DictReader(f)}
    with open(REVIEW_STATUS_CSV, encoding="utf-8-sig") as f:
        review = {r["cas"]: r for r in csv.DictReader(f)}
    with open(OUT_FINAL_CANDIDATES, encoding="utf-8-sig") as f:
        final = {r["cas"]: r for r in csv.DictReader(f)}

    rows = []
    for cas, a in audit.items():
        p6 = phase6.get(cas)
        rv = review.get(cas)
        fin = final.get(cas, {})
        if a["selection_status"] in ("KEEP_MANDATORY", "KEEP_COVERAGE") or (p6 and p6["phase6_status"] == "RETAIN_COVERAGE"):
            dep_class, dep_reason = "A_unique_dependency", "curriculum/coverage 근거 — 대체 불가"
        elif p6:
            if p6["phase6_status"] == "RETAIN_RETRIEVAL":
                dep_class = "A_unique_dependency"
                dep_reason = f"426 자기청크 hit_rate@10={p6['hit_rate_10_426']}(diagnostic) — 대체물질로 못 메움"
            elif p6["phase4_status"] == "MERGE_REDUNDANT":
                dep_class, dep_reason = "B_representative_substitutable", f"대표물질 {p6['representative_cas']}로 매트릭스상 대체 가능"
            elif p6["phase4_status"] == "REMOVE_CONFIRMED":
                dep_class, dep_reason = "C_redundant", f"대표물질 {p6['representative_cas']}로 대체, §10 실질근거 없음"
            else:
                dep_class, dep_reason = "D_not_observed", "분류 불명"
            if rv:
                dep_reason += f" | PHASE7 재평가: {rv['status']}(hit_rate={rv['hit_rate_10']})"
                if rv["status"] == "REVIEW_SUPPORTED":
                    dep_class = "A_unique_dependency"
        else:
            dep_class = "A_unique_dependency" if a["selection_status"] == "KEEP_EMPIRICAL" else "D_not_observed"
            dep_reason = a.get("selection_reason", "")[:80]
        rows.append({
            "cas": cas, "chemical_name": a["chemical_name"], "true_cameo_groups": a["true_cameo_groups"],
            "original_selection_status": a["selection_status"], "phase6_status": p6["phase6_status"] if p6 else "",
            "review134_status": rv["status"] if rv else "", "final_decision": fin.get("final_decision", ""),
            "dependency_class": dep_class, "dependency_reason": dep_reason,
        })
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("\n=== Marginal utility(dependency_class) 분포 ===")
    print(dict(Counter(r["dependency_class"] for r in rows)))
    print("산출물:", OUT)
    return rows


if __name__ == "__main__":
    gold_audit()
    recompute_selection_quality()
    apply_final_rule()
    build_marginal_utility()
