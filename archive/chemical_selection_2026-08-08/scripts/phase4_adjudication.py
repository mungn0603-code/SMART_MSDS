# -*- coding: utf-8 -*-
"""
PHASE 4-A/B/C/D — 78 REMOVE_CANDIDATE + 118 MERGE_CANDIDATE + 62 REVIEW + 16(Phase2) ADD
최종 adjudication.

읽기 전용 — undergrad_target_chemicals.csv/DB 미변경. 이 스크립트는 Phase 1~3 산출물을
다시 읽어 "제거/병합/보류를 확정해도 되는가"만 한 단계 더 검증한다(단일 조건 자동판정 금지).

핵심 참조 사실(Phase3에서 증명): 그룹매트릭스 category는 (group_a,group_b)에만
의존하므로, 어떤 signature cluster의 rank1(최상위 대표물질)이 "이미 확정 KEEP"
계열(Phase1의 51종 또는 Phase3의 KEEP_EMPIRICAL)이면 그 cluster의 나머지 물질을
제거해도 그룹/매트릭스 coverage는 절대 훼손되지 않는다. REMOVE_CONFIRMED의 핵심
조건은 바로 이것 — "대체 가능"을 추측이 아니라 rank1의 신원으로 직접 검증한다.
"""
import csv
import sqlite3
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\02_classification")  # noqa: E402
from provenance_audit import DB_PATH, CSV_PATH, s10_categories_for_text, SOURCE_MAP  # noqa: E402

AUDIT_CSV = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\01_collection\chemical_selection_audit_dataset_2026-08-08.csv"
PHASE3_CSV = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\01_collection\chemical_phase3_reassessment_2026-08-08.csv"
BACKFILL_DECISIONS_CSV = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\01_collection\chemical_backfill_candidates_2026-08-08.csv"

OUT_CSV = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\01_collection\chemical_phase4_adjudication_2026-08-08.csv"


def main():
    with open(AUDIT_CSV, encoding="utf-8-sig") as f:
        audit_rows = {r["cas_number"]: r for r in csv.DictReader(f)}
    with open(PHASE3_CSV, encoding="utf-8-sig") as f:
        phase3_rows = {r["cas"]: r for r in csv.DictReader(f)}

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
    # 섹션2(GHS 분류) 실질 내용 존재 여부 — REVIEW의 NEEDS_EVIDENCE/UNRESOLVED 판정용
    section2_has_content = defaultdict(bool)
    for cas, detail in cur.execute("SELECT cas_number, item_detail FROM msds_sections WHERE section=2"):
        d = (detail or "").strip()
        if d and d not in ("자료없음", "-", "해당없음"):
            section2_has_content[cas] = True
    group_names = dict(cur.execute("SELECT group_id, group_name FROM reactivity_groups").fetchall())
    con.close()

    with open(CSV_PATH, encoding="utf-8-sig") as f:
        csv_rows = list(csv.DictReader(f))
    collected_cas = [r["cas_number"] for r in csv_rows if section_count.get(r["cas_number"], 0) == 4]

    true_groups_of, own_categories, has_real = {}, {}, {}
    for cas in collected_cas:
        cid, _ = chem_by_cas.get(cas, (None, None))
        groups = tuple(sorted(membership.get(cid, []))) if cid else tuple()
        true_groups_of[cas] = groups
        cats = s10_categories_for_text(s10_text.get(cas, ""))
        own_categories[cas] = cats
        has_real[cas] = bool(cats) and cats != {"no_data"}

    signature_members = defaultdict(list)
    for cas, groups in true_groups_of.items():
        signature_members[groups].append(cas)

    # 물질 상태(51 keep 여부/Phase3 결과) 조회 헬퍼
    def status_of(cas):
        a = audit_rows.get(cas, {})
        st = a.get("selection_status", "")
        if st in ("KEEP_MANDATORY", "KEEP_COVERAGE", "KEEP_EMPIRICAL"):
            return f"PHASE1_{st}"
        p3 = phase3_rows.get(cas, {})
        rec = p3.get("recommendation", "")
        if rec:
            return f"PHASE3_{rec}"
        return "UNKNOWN"

    def cluster_rank1(groups):
        members = signature_members.get(groups, [])
        ranked = sorted(members, key=lambda c: (0 if has_real.get(c) else 1, -len(own_categories.get(c, set()) - {"no_data"}), c))
        return ranked[0] if ranked else None

    results = []

    # ---------------- PHASE 4-A: 78 REMOVE_CANDIDATE ----------------
    n_remove_confirmed = n_keep_exception = n_review_required = 0
    for cas, p3 in phase3_rows.items():
        if p3["recommendation"] != "REMOVE_CANDIDATE":
            continue
        groups = true_groups_of.get(cas, tuple())
        rep = cluster_rank1(groups)
        rep_status = status_of(rep) if rep else "UNKNOWN"
        safety_flag = p3.get("safety_flag", "NOT_CHECKED")

        if safety_flag != "NOT_CHECKED":
            phase4_status = "KEEP_EXCEPTION"
            reason = f"safety_flag={safety_flag} — 위험성평가 목적상 낮은 대표성만으로 제거하지 않음"
            n_keep_exception += 1
        elif rep_status.startswith("PHASE1_") or rep_status == "PHASE3_KEEP_EMPIRICAL":
            phase4_status = "REMOVE_CONFIRMED"
            reason = (f"동일 그룹조합({groups}) 대표물질 {rep}({rep_status})이 이미 확정 KEEP — "
                       f"제거해도 그룹/매트릭스 coverage 불변(수학적 보장), §10 실질근거도 없음")
            n_remove_confirmed += 1
        else:
            phase4_status = "REVIEW_REQUIRED"
            reason = (f"대체물질로 지목된 {rep}({rep_status}) 역시 §10 실질근거가 없는 REVIEW급 "
                       f"— cluster 전체가 근거 빈약해 자동 제거 확정 보류")
            n_review_required += 1

        results.append({
            "cas": cas, "chemical_name": p3["chemical_name"], "wave": p3["wave"],
            "original_status": p3["original_selection_status"], "phase4_status": phase4_status,
            "merge_cluster_id": "", "representative_cas": rep or "",
            "independent_evidence": p3["section10_has_real_evidence"],
            "section10_evidence": p3["section10_categories"],
            "marginal_coverage": "none(non-sole-group-member)",
            "reason": reason, "confidence": "high" if phase4_status != "REVIEW_REQUIRED" else "low",
        })

    # ---------------- PHASE 4-B: 118 MERGE_CANDIDATE -> clusters ----------------
    merge_clusters = defaultdict(list)
    for cas, p3 in phase3_rows.items():
        if p3["recommendation"] == "MERGE_CANDIDATE":
            merge_clusters[true_groups_of.get(cas, tuple())].append(cas)

    cluster_id_seq = 0
    n_merge_rows = 0
    for groups, members in merge_clusters.items():
        cluster_id_seq += 1
        cid_str = f"MC{cluster_id_seq:03d}_g{'-'.join(map(str, groups))}"
        rep = cluster_rank1(groups)
        rep_status = status_of(rep)
        for cas in members:
            p3 = phase3_rows[cas]
            n_merge_rows += 1
            results.append({
                "cas": cas, "chemical_name": p3["chemical_name"], "wave": p3["wave"],
                "original_status": p3["original_selection_status"], "phase4_status": "MERGE_REDUNDANT",
                "merge_cluster_id": cid_str, "representative_cas": rep or "",
                "independent_evidence": p3["section10_has_real_evidence"],
                "section10_evidence": p3["section10_categories"],
                "marginal_coverage": "redundant_with_representative(matrix-level)",
                "reason": (f"대표물질 {rep}({rep_status})과 동일 그룹조합({groups}) — 매트릭스 기반 "
                           f"coverage는 대표물질이 전담 가능. 단, 개별 §2·3·9 실측값(물성 등)은 "
                           f"물질마다 달라 완전한 정보손실은 아님(사람 검토 시 고려)"),
                "confidence": "medium",
            })

    # ---------------- PHASE 4-C: 62 REVIEW ----------------
    n_needs_evidence = n_unresolved = 0
    for cas, p3 in phase3_rows.items():
        if p3["recommendation"] != "REVIEW":
            continue
        rank_info = p3["signature_rank"]
        if rank_info == "unique_signature_no_duplicate":
            reason_codes = ["insufficient_section10", "unclear_empirical_relevance"]
        else:
            reason_codes = ["insufficient_section10", "unclear_redundancy"]
        if section2_has_content.get(cas):
            final = "NEEDS_EVIDENCE"
            reason_codes.append("section2_has_unexamined_content")
            n_needs_evidence += 1
        else:
            final = "UNRESOLVED"
            n_unresolved += 1
        results.append({
            "cas": cas, "chemical_name": p3["chemical_name"], "wave": p3["wave"],
            "original_status": p3["original_selection_status"], "phase4_status": final,
            "merge_cluster_id": "", "representative_cas": "",
            "independent_evidence": p3["section10_has_real_evidence"],
            "section10_evidence": p3["section10_categories"],
            "marginal_coverage": "unclear",
            "reason": f"REVIEW_REASON={'+'.join(reason_codes)}",
            "confidence": "low",
        })

    # ---------------- PHASE 4-D: Phase2 16 ADD 최종검토 ----------------
    with open(BACKFILL_DECISIONS_CSV, encoding="utf-8-sig") as f:
        backfill_rows = list(csv.DictReader(f))
    add_rows = [r for r in backfill_rows if r["decision"] == "ADD" and r["group_id"] != "36"]
    by_cas = defaultdict(list)
    for r in add_rows:
        by_cas[r["candidate_cas"]].append(r["group_id"])

    all_existing_signatures = set(true_groups_of.values())
    seen_add_signatures = {}
    n_add_confirmed = n_add_hold = n_add_reject = 0
    for cas, group_ids in by_cas.items():
        sample = next(r for r in add_rows if r["candidate_cas"] == cas)
        name = sample["candidate_name"]
        cid, _ = chem_by_cas.get(cas, (None, None))
        true_groups = tuple(sorted(membership.get(cid, []))) if cid else tuple(sorted(int(g) for g in group_ids))

        if true_groups in all_existing_signatures:
            status = "ADD_REJECT"
            reason = f"true_groups={true_groups}가 이미 기존 426종 내 존재 — 재검증 결과 중복 확인"
            n_add_reject += 1
        elif true_groups in seen_add_signatures:
            status = "ADD_HOLD"
            other = seen_add_signatures[true_groups]
            reason = f"같은 ADD 후보 {other}와 true_groups={true_groups} 동일 — 둘 중 하나만 필요, 사람 선택 필요"
            n_add_hold += 1
        else:
            seen_add_signatures[true_groups] = cas
            status = "ADD_CONFIRMED"
            reason = (f"true_groups={true_groups} 기존/다른 ADD후보와 비중복, 대상 그룹({','.join(group_ids)}) "
                      f"scarcity 완화 — Phase2 coverage gain 재확인")
            n_add_confirmed += 1

        results.append({
            "cas": cas, "chemical_name": name, "wave": "phase2_add",
            "original_status": "ADD(PHASE2)", "phase4_status": status,
            "merge_cluster_id": "", "representative_cas": "",
            "independent_evidence": "true", "section10_evidence": "",
            "marginal_coverage": f"target_groups={group_ids}",
            "reason": reason, "confidence": "high",
        })

    # ---------------- 출력 ----------------
    fields = ["cas", "chemical_name", "wave", "original_status", "phase4_status", "merge_cluster_id",
              "representative_cas", "independent_evidence", "section10_evidence", "marginal_coverage",
              "reason", "confidence"]
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(results)

    print("=== PHASE 4-A (REMOVE 78) ===")
    print(f"REMOVE_CONFIRMED={n_remove_confirmed} KEEP_EXCEPTION={n_keep_exception} REVIEW_REQUIRED={n_review_required}")
    print()
    print("=== PHASE 4-B (MERGE 118) ===")
    print(f"clusters={len(merge_clusters)} merge_rows={n_merge_rows}")
    print()
    print("=== PHASE 4-C (REVIEW 62) ===")
    print(f"NEEDS_EVIDENCE={n_needs_evidence} UNRESOLVED={n_unresolved}")
    print()
    print("=== PHASE 4-D (ADD 16→unique) ===")
    print(f"unique ADD candidates={len(by_cas)}  ADD_CONFIRMED={n_add_confirmed} ADD_HOLD={n_add_hold} ADD_REJECT={n_add_reject}")
    print()
    print("산출물:", OUT_CSV)

    return results, {
        "remove_confirmed": n_remove_confirmed, "keep_exception": n_keep_exception,
        "review_required": n_review_required, "merge_clusters": len(merge_clusters),
        "merge_rows": n_merge_rows, "needs_evidence": n_needs_evidence, "unresolved": n_unresolved,
        "add_confirmed": n_add_confirmed, "add_hold": n_add_hold, "add_reject": n_add_reject,
        "unique_add": len(by_cas),
    }


if __name__ == "__main__":
    main()
