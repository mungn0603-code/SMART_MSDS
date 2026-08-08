# -*- coding: utf-8 -*-
"""
PHASE 4-E/G — Before/After coverage 비교 + Proposed Final Dataset 생성.

원본 undergrad_target_chemicals.csv는 절대 덮어쓰지 않는다. 이 스크립트는 그 CSV를
읽기만 하고, 별도 파일(*_proposed_final_2026-08-08.csv)에 "제안"을 쓴다.

Proposed final = Phase1 KEEP(51) + Phase3에서 REMOVE_CONFIRMED/MERGE_REDUNDANT로
확정되지 않은 나머지(194, REVIEW_REQUIRED+NEEDS_EVIDENCE+UNRESOLVED+KEEP_EMPIRICAL) +
Phase4 ADD_CONFIRMED(14). REMOVE_CONFIRMED(63)·MERGE_REDUNDANT(118)만 제외, ADD_HOLD(1)는
보류라 미포함.
"""
import csv
import sqlite3
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\02_classification")  # noqa: E402
from provenance_audit import DB_PATH, CSV_PATH, s10_categories_for_text  # noqa: E402

AUDIT_CSV = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\01_collection\chemical_selection_audit_dataset_2026-08-08.csv"
PHASE4_CSV = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\01_collection\chemical_phase4_adjudication_2026-08-08.csv"
BACKFILL_DECISIONS_CSV = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\01_collection\chemical_backfill_candidates_2026-08-08.csv"

OUT_PROPOSED_CSV = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\01_collection\undergrad_target_chemicals_proposed_final_2026-08-08.csv"


def build_dataset_view(cas_set, chem_by_cas, membership, s10_text):
    """cas_set에 대해 그룹커버리지/§10비율/매트릭스 risk-pair 비율/scarce-group 커버리지 계산."""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    pair_category = {}
    for a, b, cat in cur.execute("SELECT group_a_id, group_b_id, category FROM compatibility_pairs"):
        pair_category[(a, b)] = cat
    self_category = dict(cur.execute("SELECT group_id, category FROM self_reactivity").fetchall())
    all_group_ids = set(dict(cur.execute("SELECT group_id, group_name FROM reactivity_groups")).keys())
    con.close()

    true_groups_of = {}
    for cas in cas_set:
        cid, _ = chem_by_cas.get(cas, (None, None))
        true_groups_of[cas] = tuple(sorted(membership.get(cid, []))) if cid else tuple()

    group_member_count = Counter()
    for cas, groups in true_groups_of.items():
        for g in groups:
            group_member_count[g] += 1
    covered_groups = {g for g in all_group_ids if group_member_count.get(g, 0) > 0}

    cat_counter = Counter()
    for cas in cas_set:
        for c in s10_categories_for_text(s10_text.get(cas, "")):
            cat_counter[c] += 1

    def group_pair_category(ga, gb):
        a, b = sorted((ga, gb))
        if a == b:
            return self_category.get(a, "Unknown")
        return pair_category.get((a, b), "Unknown")

    _RANK = {"Compatible": 0, "Caution": 1, "Incompatible": 2}
    cas_list = list(cas_set)
    n_pairs = n_incompatible = n_caution = n_compatible = 0
    for i in range(len(cas_list)):
        for j in range(i + 1, len(cas_list)):
            ga_list = true_groups_of[cas_list[i]]
            gb_list = true_groups_of[cas_list[j]]
            worst, any_known = "Compatible", False
            for ga in ga_list:
                for gb in gb_list:
                    cat = group_pair_category(ga, gb)
                    if cat == "Unknown":
                        continue
                    any_known = True
                    if _RANK[cat] > _RANK[worst]:
                        worst = cat
            n_pairs += 1
            if not any_known:
                continue
            if worst == "Incompatible":
                n_incompatible += 1
            elif worst == "Caution":
                n_caution += 1
            else:
                n_compatible += 1

    signature_members = defaultdict(list)
    for cas, groups in true_groups_of.items():
        signature_members[groups].append(cas)
    duplicate_members = sum(len(v) for v in signature_members.values() if len(v) > 1)

    n = len(cas_set)
    return {
        "n": n,
        "group_coverage": f"{len(covered_groups)}/{len(all_group_ids)}",
        "scarce_group_count(<=2)": sum(1 for g in all_group_ids if 0 < group_member_count.get(g, 0) <= 2),
        "s10_pct": {c: (cnt, cnt / n) for c, cnt in cat_counter.items()},
        "matrix_incompatible_pct": n_incompatible / n_pairs if n_pairs else 0,
        "matrix_caution_pct": n_caution / n_pairs if n_pairs else 0,
        "matrix_compatible_pct": n_compatible / n_pairs if n_pairs else 0,
        "duplicate_member_ratio": duplicate_members / n if n else 0,
        "n_pairs": n_pairs,
    }


def main():
    with open(AUDIT_CSV, encoding="utf-8-sig") as f:
        audit_rows = {r["cas_number"]: r for r in csv.DictReader(f)}
    with open(PHASE4_CSV, encoding="utf-8-sig") as f:
        phase4_rows = list(csv.DictReader(f))

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    chem_by_cas = {}
    for cid, cas, name in cur.execute("SELECT chemical_id, cas_number, chemical_name FROM chemicals"):
        chem_by_cas[cas] = (cid, name)
    membership = defaultdict(list)
    for cid, gid in cur.execute("SELECT chemical_id, group_id FROM chemical_group_membership"):
        membership[cid].append(gid)
    section_count = Counter()
    for cas, cnt in cur.execute("SELECT cas_number, COUNT(DISTINCT section) FROM msds_sections GROUP BY cas_number"):
        section_count[cas] = cnt
    s10_text = {}
    for cas, detail in cur.execute(
        "SELECT cas_number, item_detail FROM msds_sections "
        "WHERE section=10 AND item_name_kor='피해야 할 물질'"
    ):
        s10_text[cas] = detail or ""
    con.close()

    with open(CSV_PATH, encoding="utf-8-sig") as f:
        csv_rows = list(csv.DictReader(f))
    baseline_cas = set(r["cas_number"] for r in csv_rows if section_count.get(r["cas_number"], 0) == 4)

    remove_confirmed = {r["cas"] for r in phase4_rows if r["phase4_status"] == "REMOVE_CONFIRMED"}
    merge_redundant = {r["cas"] for r in phase4_rows if r["phase4_status"] == "MERGE_REDUNDANT"}
    add_confirmed_rows = [r for r in phase4_rows if r["phase4_status"] == "ADD_CONFIRMED"]
    add_confirmed_cas = {r["cas"] for r in add_confirmed_rows}

    proposed_cas = (baseline_cas - remove_confirmed - merge_redundant) | add_confirmed_cas

    print(f"baseline={len(baseline_cas)}  -REMOVE_CONFIRMED={len(remove_confirmed)}  "
          f"-MERGE_REDUNDANT={len(merge_redundant)}  +ADD_CONFIRMED={len(add_confirmed_cas)}  "
          f"=> proposed={len(proposed_cas)}")

    before = build_dataset_view(baseline_cas, chem_by_cas, membership, s10_text)
    after = build_dataset_view(proposed_cas, chem_by_cas, membership, s10_text)

    print()
    print("=== Coverage Before/After ===")
    print(f"n: {before['n']} -> {after['n']}")
    print(f"group_coverage: {before['group_coverage']} -> {after['group_coverage']}")
    print(f"scarce_group_count(<=2): {before['scarce_group_count(<=2)']} -> {after['scarce_group_count(<=2)']}")
    print(f"matrix Incompatible%: {before['matrix_incompatible_pct']:.2%} -> {after['matrix_incompatible_pct']:.2%}")
    print(f"matrix Caution%: {before['matrix_caution_pct']:.2%} -> {after['matrix_caution_pct']:.2%}")
    print(f"matrix Compatible%: {before['matrix_compatible_pct']:.2%} -> {after['matrix_compatible_pct']:.2%}")
    print(f"duplicate_member_ratio(같은 그룹조합 공유): {before['duplicate_member_ratio']:.1%} -> {after['duplicate_member_ratio']:.1%}")
    print("§10 카테고리:")
    for c in before["s10_pct"]:
        b_cnt, b_pct = before["s10_pct"][c]
        a_cnt, a_pct = after["s10_pct"].get(c, (0, 0))
        print(f"  {c}: {b_cnt}({b_pct:.1%}) -> {a_cnt}({a_pct:.1%})")

    # ---- Proposed final CSV 생성 ----
    orig_by_cas = {r["cas_number"]: r for r in csv_rows}
    fieldnames = ["cas_number", "chemical_name", "group_id", "group_name", "source", "course", "experiment"]
    out_rows = []
    for cas in sorted(proposed_cas):
        if cas in orig_by_cas:
            r = orig_by_cas[cas]
            out_rows.append({k: r.get(k, "") for k in fieldnames})
        else:
            add_row = next(r for r in add_confirmed_rows if r["cas"] == cas)
            out_rows.append({
                "cas_number": cas, "chemical_name": add_row["chemical_name"],
                "group_id": "", "group_name": "", "source": "phase4_add_confirmed",
                "course": "", "experiment": "",
            })
    with open(OUT_PROPOSED_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)
    print()
    print(f"PROPOSED FINAL(참고용, 미승인) 작성 완료: {OUT_PROPOSED_CSV} ({len(out_rows)}행)")

    return before, after, proposed_cas, remove_confirmed, merge_redundant, add_confirmed_cas


if __name__ == "__main__":
    main()
