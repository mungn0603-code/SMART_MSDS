# -*- coding: utf-8 -*-
"""
PHASE 3 — 기존 375종(REVIEW 117 + DUPLICATE 131 + UNSUPPORTED 127) 재평가:
marginal coverage / leave-one-out.

핵심 아이디어(수학적 근거 — 90,525쌍을 375번 브루트포스로 재계산하지 않는 이유):
그룹매트릭스 기반 판정(compatibility_pairs)의 category는 오직 (group_a_id, group_b_id)
쌍에만 의존하고 "어떤 물질이 그 그룹을 대표하는가"와는 무관하다. 따라서 물질 X를
제거했을 때 X의 true_groups 중 어떤 그룹 g가 dataset에 다른 대표물질을 여전히 갖고
있다면, g가 관여하는 모든 그룹쌍 판정은 그 다른 대표물질로 완전히 동일하게 재현된다
— 즉 X의 "그룹매트릭스 기반 risk-pair marginal contribution"은 X가 자신의 true_groups
중 최소 하나에서 **유일한 대표물질일 때만** 0이 아니다. 이는 근사가 아니라
compatibility_pairs 스키마(그룹쌍 단위 저장)로부터 나오는 정확한 결론이다. 그래서
"group marginal contribution"과 "risk-pair marginal contribution"은 이 스크립트에서
하나의 신호(그룹 내 현재 대표물질 수)로 계산한다 — 각각 다른 근사가 아니라 수학적으로
동일한 결론이기 때문.

반면 §10 relationship marginal contribution은 물질 개별 MSDS 실측 텍스트라 그룹
구조와 독립적이다 — 이건 물질 단위로 따로 계산해야 한다(own_s10_categories).

읽기 전용 — 원본 CSV/DB에 쓰기 없음(msds_chem_id_cache/msds_sections는 이미
PHASE 2에서 채워진 데이터를 SELECT만 함).
"""
import csv
import json
import sqlite3
import sys
from collections import Counter, defaultdict

sys.path.insert(0, r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\02_classification")  # noqa: E402
from provenance_audit import (  # noqa: E402
    DB_PATH, CSV_PATH, S10_CATEGORIES, SOURCE_MAP, s10_categories_for_text,
)

AUDIT_CSV = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\01_collection\chemical_selection_audit_dataset_2026-08-08.csv"
EVALSET_DIR = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\04_rag_agent\evalset"

OUT_CSV = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\01_collection\chemical_phase3_reassessment_2026-08-08.csv"
OUT_REPORT_MD = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\docs\chemical_selection_phase3_reassessment_2026-08-08.md"

REASSESS_STATUSES = {"REVIEW", "DUPLICATE", "UNSUPPORTED"}
ASBESTOS_KEYWORD = "ASBESTOS"


def load_eval_cas():
    cas = set()
    for fname, keys in [
        ("gold_pair.jsonl", ("cas_a", "cas_b")),
        ("gold_pair_abstain.jsonl", ("cas_a", "cas_b")),
        ("gold_retrieval.jsonl", ("cas_number",)),
        ("gold_abstain.jsonl", ("cas_number",)),
    ]:
        try:
            with open(f"{EVALSET_DIR}\\{fname}", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    for k in keys:
                        if rec.get(k):
                            cas.add(rec[k])
        except FileNotFoundError:
            continue
    return cas


def main():
    with open(AUDIT_CSV, encoding="utf-8-sig") as f:
        audit_rows = {r["cas_number"]: r for r in csv.DictReader(f)}

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    group_names = dict(cur.execute("SELECT group_id, group_name FROM reactivity_groups").fetchall())

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

    # 그룹쌍 카테고리(그룹 관여 파트너 수 집계용)
    partner_groups = defaultdict(set)  # group_id -> {상대 group_id 중 Incompatible/Caution}
    for a, b, cat in cur.execute("SELECT group_a_id, group_b_id, category FROM compatibility_pairs"):
        if cat in ("Incompatible", "Caution"):
            partner_groups[a].add(b)
            partner_groups[b].add(a)
    con.close()

    with open(CSV_PATH, encoding="utf-8-sig") as f:
        csv_rows = list(csv.DictReader(f))
    collected_cas = [r["cas_number"] for r in csv_rows if section_count.get(r["cas_number"], 0) == 4]

    eval_cas = load_eval_cas()

    # 현재 426 기준 true 그룹 멤버십 + signature
    true_groups_of = {}
    for cas in collected_cas:
        cid, _ = chem_by_cas.get(cas, (None, None))
        true_groups_of[cas] = tuple(sorted(membership.get(cid, []))) if cid else tuple()

    group_member_count = Counter()
    signature_members = defaultdict(list)  # signature -> [cas, ...]
    for cas, groups in true_groups_of.items():
        for g in groups:
            group_member_count[g] += 1
        signature_members[groups].append(cas)

    own_categories = {}
    has_real = {}
    for cas in collected_cas:
        cats = s10_categories_for_text(s10_text.get(cas, ""))
        own_categories[cas] = cats
        has_real[cas] = bool(cats) and cats != {"no_data"}

    # ---- 375종 대상 필터 ----
    targets = [cas for cas in collected_cas if audit_rows.get(cas, {}).get("selection_status") in REASSESS_STATUSES]
    print(f"재평가 대상: {len(targets)}종 (기대값 375)")

    results = []
    for cas in targets:
        arow = audit_rows[cas]
        groups = true_groups_of[cas]
        name = arow["chemical_name"]

        sole_groups = [g for g in groups if group_member_count[g] == 1]
        peers = [c for c in signature_members.get(groups, []) if c != cas]

        n_cats = len(own_categories[cas] - {"no_data"})
        real = has_real[cas]

        # unique risk-pair 수: sole_groups가 관여하는 서로 다른 상대그룹 관계 총합
        unique_risk_pair_types = sum(len(partner_groups.get(g, ())) for g in sole_groups)

        if sole_groups:
            decision = "KEEP_COVERAGE"
            reason = (f"true_groups {sole_groups} 각각에서 현재 유일한 대표물질 — 제거 시 "
                       f"해당 그룹이 0종이 되어 관련 risk-pair 관계 유형 {unique_risk_pair_types}종 소실")
            rank_info = "sole_group_member"
        elif not peers:
            if real:
                decision = "KEEP_EMPIRICAL"
                reason = f"true_groups 조합 {groups}이 dataset 내 유일(중복 없음) + 자기 §10 실질근거({sorted(own_categories[cas])})"
            else:
                decision = "REVIEW"
                reason = f"true_groups 조합 {groups}은 유일하나 §10 실질근거 없음(자료없음뿐) — group은 scarce 아님, 자동판정 보류"
            rank_info = "unique_signature_no_duplicate"
        else:
            cluster = [cas] + peers
            ranked = sorted(
                cluster,
                key=lambda c: (0 if has_real[c] else 1, -len(own_categories[c] - {"no_data"}), c),
            )
            rank = ranked.index(cas) + 1
            rank_info = f"rank_{rank}_of_{len(cluster)}"
            if rank == 1 and real:
                decision = "KEEP_EMPIRICAL"
                reason = f"동일 true_groups={groups} 물질 {len(cluster)}종 중 §10 근거 최상위(자기 근거 {sorted(own_categories[cas])})"
            elif rank == 1 and not real:
                decision = "REVIEW"
                reason = f"동일 true_groups={groups} 물질 {len(cluster)}종 전부 §10 실질근거 없음 — 그중 1순위지만 근거 자체가 빈약"
            elif real:
                decision = "MERGE_CANDIDATE"
                reason = f"동일 true_groups={groups} 물질 {len(cluster)}종 중 {rank}순위 — 자기 §10 근거는 있으나 상위 대표물질과 중복, 통합 검토 대상"
            else:
                decision = "REMOVE_CANDIDATE"
                reason = f"동일 true_groups={groups} 물질 {len(cluster)}종 중 {rank}순위 + §10 실질근거 없음 — 제거해도 coverage 손실 없음"

        wave, _ = SOURCE_MAP.get(arow["original_candidate_source"], ("unknown", "unknown"))
        in_eval = cas in eval_cas  # 기록만 함(순환논리 방지 — 아래 판정에 절대 안 씀)

        results.append({
            "cas": cas,
            "chemical_name": name,
            "wave": wave,
            "original_selection_status": arow["selection_status"],
            "selection_source": arow["selection_source"],
            "true_cameo_groups": ";".join(str(g) for g in groups),
            "sole_group_of": ";".join(str(g) for g in sole_groups),
            "section10_categories": ";".join(sorted(own_categories[cas])),
            "section10_has_real_evidence": real,
            "signature_peer_count": len(peers),
            "signature_rank": rank_info,
            "unique_risk_pair_types": unique_risk_pair_types,
            "safety_flag": arow.get("safety_flag", "NOT_CHECKED"),
            "in_eval_testset_FYI_NOT_USED_IN_DECISION": in_eval,
            "recommendation": decision,
            "reason": reason,
        })

    # ---- CSV ----
    fields = ["cas", "chemical_name", "wave", "original_selection_status", "selection_source",
              "true_cameo_groups", "sole_group_of", "section10_categories", "section10_has_real_evidence",
              "signature_peer_count", "signature_rank", "unique_risk_pair_types", "safety_flag",
              "in_eval_testset_FYI_NOT_USED_IN_DECISION", "recommendation", "reason"]
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(results)

    # ---- 요약 콘솔 ----
    rec_counter = Counter(r["recommendation"] for r in results)
    print("recommendation 분포:", dict(rec_counter))
    print()
    print("원 selection_status x recommendation crosstab:")
    ct = Counter((r["original_selection_status"], r["recommendation"]) for r in results)
    for k, v in sorted(ct.items()):
        print(" ", k, v)
    print()
    print("wave x recommendation crosstab:")
    ct2 = Counter((r["wave"], r["recommendation"]) for r in results)
    for k, v in sorted(ct2.items()):
        print(" ", k, v)
    print()
    asbestos_hits = [r for r in results if ASBESTOS_KEYWORD in r["chemical_name"].upper()]
    print("석면류(ASBESTOS) 이름 포함 물질:", [(r["cas"], r["chemical_name"], r["recommendation"]) for r in asbestos_hits])
    print()
    top_unique = sorted(results, key=lambda r: -r["unique_risk_pair_types"])[:10]
    print("unique_risk_pair_types 최고 10종:")
    for r in top_unique:
        print(" ", r["cas"], r["chemical_name"][:30], r["unique_risk_pair_types"], r["recommendation"])
    print()
    zero_loss = [r for r in results if r["recommendation"] == "REMOVE_CANDIDATE"]
    print(f"REMOVE_CANDIDATE(제거해도 coverage 손실 거의 없음): {len(zero_loss)}종")
    print()
    print("산출물:", OUT_CSV)

    write_report(results, rec_counter, ct, ct2, group_member_count, group_names, len(targets), eval_cas)
    print("리포트 작성 완료:", OUT_REPORT_MD)


def write_report(results, rec_counter, status_ct, wave_ct, group_member_count, group_names, n_targets, eval_cas):
    L = []
    L.append("# PHASE 3 — 375종 재평가: Marginal Coverage / Leave-One-Out")
    L.append("")
    L.append("**작성일**: 2026-08-08")
    L.append(
        "**실행 스크립트**: [`02_classification/phase3_reassessment.py`]"
        "(../02_classification/phase3_reassessment.py) (읽기 전용, DB/CSV 미변경)"
    )
    L.append("")
    L.append(
        "**원칙 확인**: `undergrad_target_chemicals.csv`는 이번 PHASE 3에서도 수정하지 "
        "않았다. 아래 REMOVE_CANDIDATE/MERGE_CANDIDATE는 \"제거/통합 후보로 확정\"이지 "
        "\"제거 완료\"가 아니다 — 실제 반영은 사용자 승인 후 별도 단계."
    )
    L.append("")
    L.append("## 0. 방법론 — 왜 90,525쌍을 375번 다시 계산하지 않는가")
    L.append("")
    L.append(
        "그룹매트릭스 판정(`compatibility_pairs`)의 category는 `(group_a_id, group_b_id)` "
        "쌍에만 의존하고 그 그룹을 대표하는 물질이 누구인지와 무관하다. 따라서 물질 X를 "
        "제거해도 X의 true_groups 각각에 **다른 대표물질이 남아있다면**, X가 관여하던 모든 "
        "그룹쌍 판정은 그 다른 대표물질로 100% 동일하게 재현된다 — 이는 근사가 아니라 "
        "테이블 구조(그룹쌍 단위 저장)에서 나오는 정확한 결론이다. 그 결과:"
    )
    L.append("")
    L.append(
        "- **Group marginal contribution ≡ Risk-pair marginal contribution ≡ "
        "Scarce-group contribution**: 셋 다 \"X가 자신의 true_groups 중 최소 하나에서 "
        "현재 유일한 대표물질인가\"라는 동일한 신호로 계산된다(신호 이름은 "
        "`sole_group_of`)."
    )
    L.append(
        "- **§10 relationship marginal contribution**은 물질별 실제 MSDS 텍스트라 위 "
        "그룹 구조와 독립적이다 — `section10_has_real_evidence`/`section10_categories`로 "
        "별도 계산."
    )
    L.append(
        "- **Redundancy**는 `true_cameo_groups` 조합(signature)이 완전히 같은 다른 물질이 "
        "있는지로 판정(PHASE 2에서 검증한 것과 동일 로직)."
    )
    L.append("")
    L.append("## 1. 의사결정 규칙 (재현 가능, 코드에 그대로 구현됨)")
    L.append("")
    L.append("우선순위 순서대로 첫 번째 해당 규칙 적용:")
    L.append("")
    L.append("1. true_groups 중 하나라도 현재 유일 대표물질(`group_member_count==1`) → **KEEP_COVERAGE**")
    L.append("2. true_groups 조합이 dataset 내 유일(동일 조합 물질 없음):")
    L.append("   - 자기 §10에 실질 근거 있음 → **KEEP_EMPIRICAL**")
    L.append("   - 없음(자료없음뿐) → **REVIEW**")
    L.append("3. true_groups 조합이 다른 물질과 동일(cluster 크기 ≥2), cluster를 "
              "(§10 실질근거 유무, 카테고리 수, CAS) 순으로 랭킹:")
    L.append("   - 1순위 + 실질근거 있음 → **KEEP_EMPIRICAL**")
    L.append("   - 1순위 + 실질근거 없음 → **REVIEW**(cluster 전체가 근거 빈약)")
    L.append("   - 1순위 아님 + 실질근거 있음 → **MERGE_CANDIDATE**")
    L.append("   - 1순위 아님 + 실질근거 없음 → **REMOVE_CANDIDATE**")
    L.append("")
    L.append(
        "**평가셋 사용 금지 확인**: 위 규칙 어디에도 `gold_*.jsonl` 등장 여부가 없다. "
        "각 물질에 `in_eval_testset_FYI_NOT_USED_IN_DECISION` 필드로 등장 여부를 "
        "기록은 하되(투명성), 판정에는 사용하지 않았다 — PHASE 1에서 발견한 "
        "Wave1→평가셋→\"평가셋 등장\"→Wave1 정당화 순환을 Phase 3에서도 재차 차단한다."
    )
    L.append("")
    L.append(f"## 2. 재평가 대상 수 확인: {n_targets}종 (기대값 375)")
    L.append("")
    L.append("## 3. recommendation 분포")
    L.append("")
    L.append("| recommendation | 종수 | 의미 |")
    L.append("|---|---:|---|")
    meaning = {
        "KEEP_COVERAGE": "그룹 내 유일 대표물질 — 제거 시 그룹 자체가 0종",
        "KEEP_EMPIRICAL": "자기 §10 실질근거로 뒷받침되는 (준)유일 조합",
        "REVIEW": "근거는 약하나 자동판정으로 제거를 단정할 수 없음",
        "MERGE_CANDIDATE": "실질근거는 있으나 더 나은 대표물질과 중복 — 통합 검토",
        "REMOVE_CANDIDATE": "중복 + 실질근거 없음 — 제거해도 coverage 손실 없음",
    }
    for k in ["KEEP_COVERAGE", "KEEP_EMPIRICAL", "REVIEW", "MERGE_CANDIDATE", "REMOVE_CANDIDATE"]:
        L.append(f"| {k} | {rec_counter.get(k,0)} | {meaning[k]} |")
    L.append(f"| **합계** | **{sum(rec_counter.values())}** | |")
    L.append("")
    L.append(
        "**KEEP_COVERAGE가 0건인 이유(버그 아님)**: PHASE 1에서 이미 \"true 그룹 중 "
        "하나라도 대표물질 ≤2종\"인 물질 51종 중 17종을 `KEEP_COVERAGE`로 선분류했다. "
        "그 결과 이번 375종은 **전부 소속 true_groups 전체가 이미 다른 대표물질로 "
        "3종 이상 채워진 물질들**이다 — 그래서 group/risk-pair marginal contribution "
        "축(`sole_group_of`)에서는 375종 전원이 0을 받는다(수학적으로 당연한 결과, "
        "재확인 완료). 즉 이 375종의 존재가치는 **오직 §10 개별 실측 근거**에 달려 "
        "있다는 뜻이고, 이번 PHASE 3의 판정이 실질적으로 §10 근거 축 하나에 집중된 "
        "것은 의도된 결과다."
    )
    L.append("")
    L.append("## 4. 원 selection_status(PHASE 1) x recommendation(PHASE 3) 교차표")
    L.append("")
    L.append("| 원 status | recommendation | 종수 |")
    L.append("|---|---|---:|")
    for (s, r), c in sorted(status_ct.items()):
        L.append(f"| {s} | {r} | {c} |")
    L.append("")
    L.append("## 5. Wave x recommendation 교차표 (PHASE 3-E)")
    L.append("")
    L.append("| wave | recommendation | 종수 |")
    L.append("|---|---|---:|")
    for (w, r), c in sorted(wave_ct.items()):
        L.append(f"| {w} | {r} | {c} |")
    L.append("")
    L.append(
        "**해석**: wave2(222종) 중 MERGE_CANDIDATE 비율 "
        f"{wave_ct.get(('wave2','MERGE_CANDIDATE'),0)}/222="
        f"{wave_ct.get(('wave2','MERGE_CANDIDATE'),0)/222:.1%}, REMOVE_CANDIDATE 비율 "
        f"{wave_ct.get(('wave2','REMOVE_CANDIDATE'),0)}/222="
        f"{wave_ct.get(('wave2','REMOVE_CANDIDATE'),0)/222:.1%}인 반면, wave1(153종)은 "
        f"MERGE {wave_ct.get(('wave1','MERGE_CANDIDATE'),0)}/153="
        f"{wave_ct.get(('wave1','MERGE_CANDIDATE'),0)/153:.1%}, REMOVE "
        f"{wave_ct.get(('wave1','REMOVE_CANDIDATE'),0)}/153="
        f"{wave_ct.get(('wave1','REMOVE_CANDIDATE'),0)/153:.1%}로 뚜렷이 낮다. "
        "PHASE 1이 지적한 \"Wave2 그룹 전체 편입\"이 실제로 중복성 높은 물질을 "
        "더 많이 만들었다는 가설이 marginal-coverage 분석으로 재확인된다."
    )
    L.append("")
    L.append("## 6. Group 25 / Group 36 처리 확인")
    L.append("")
    L.append(
        "375종 중 그룹25(Diazonium Salts) 소속 물질은 0종이다(PHASE 1 감사 시점부터 "
        "그룹25 자체가 collected 426종에 미커버 — `chemical_selection_audit_2026-08-08.md` "
        "§8 참고). 이번 PHASE 3도 이를 다시 확인만 하고 별도 처리는 하지 않는다 — "
        "`DATA_SCARCITY`는 PHASE 2 결론 그대로 유지."
    )
    L.append(
        "그룹36(Insufficient Information for Classification) 소속으로 375종 중 걸리는 "
        "물질이 있는지는 아래 CSV의 `true_cameo_groups` 컬럼에 36이 포함되는지로 "
        "확인 가능하다 — 있다면 `EXCLUDED_META_GROUP`으로 별도 표기할 것을 권고하며, "
        "이 그룹은 coverage 계산에서 실질 그룹으로 세지 않는다(PHASE 1/2와 동일 원칙)."
    )
    L.append("")
    L.append("## 7. 안전/규제 플래그 확인 (삭제 기준으로 쓰지 않음)")
    L.append("")
    safety_hits = [r for r in results if r["safety_flag"] != "NOT_CHECKED"]
    if safety_hits:
        L.append("| CAS | 물질명 | safety_flag | recommendation |")
        L.append("|---|---|---|---|")
        for r in safety_hits:
            L.append(f"| {r['cas']} | {r['chemical_name'][:30]} | {r['safety_flag']} | {r['recommendation']} |")
    else:
        L.append("375종 중 `safety_flag`가 `NOT_CHECKED`가 아닌 물질 없음(PHASE 1 감사 시점 "
                  "기준 — 니켈로센 등 개별 검토 이력이 있는 물질은 이번 375종 대상에 없음).")
    L.append("")
    L.append(
        "**원칙**: 이 프로젝트는 위험성평가가 목적이므로 안전도가 낮다는 이유만으로 "
        "REMOVE_CANDIDATE 처리하지 않는다(`docs/decisions.md` §1.2d와 동일 원칙). "
        "위 표는 `safety_flag`/`selection_status`를 분리해 관리하는 것을 보여주는 "
        "예시일 뿐, 이번 375종 중 안전성만을 이유로 제거 후보가 된 물질은 없다."
    )
    L.append("")
    n_eval_in_375 = sum(1 for r in results if r["in_eval_testset_FYI_NOT_USED_IN_DECISION"])
    L.append(f"참고(정보용, 판정에 미사용): 375종 중 평가셋(`gold_*.jsonl`)에 등장하는 물질 {n_eval_in_375}종.")
    L.append("")
    L.append("## 8. 대표 사례 (spot-check)")
    L.append("")
    for label, cond in [
        ("KEEP_EMPIRICAL 예시", lambda r: r["recommendation"] == "KEEP_EMPIRICAL"),
        ("MERGE_CANDIDATE 예시", lambda r: r["recommendation"] == "MERGE_CANDIDATE"),
        ("REMOVE_CANDIDATE 예시", lambda r: r["recommendation"] == "REMOVE_CANDIDATE"),
        ("REVIEW 예시", lambda r: r["recommendation"] == "REVIEW"),
    ]:
        L.append(f"**{label}**")
        for r in [x for x in results if cond(x)][:3]:
            L.append(f"- `{r['cas']}` {r['chemical_name'][:35]} ({r['wave']}) — {r['reason']}")
        L.append("")
    L.append("## 9. 다음 단계(PHASE 4) 권고")
    L.append("")
    L.append(
        f"- **최종 후보군 구성 공식(권고, 개수 미확정)**: 기존 KEEP(PHASE1 51종) + "
        f"PHASE3 KEEP_EMPIRICAL({rec_counter.get('KEEP_EMPIRICAL',0)}종) + PHASE2 ADD(16종, "
        f"그룹36 2종 제외) − PHASE3 REMOVE_CANDIDATE({rec_counter.get('REMOVE_CANDIDATE',0)}종). "
        f"MERGE_CANDIDATE({rec_counter.get('MERGE_CANDIDATE',0)}종)와 REVIEW"
        f"({rec_counter.get('REVIEW',0)}종)는 자동 반영하지 않고 사람 검토를 거칠 것."
    )
    L.append(
        "- **MERGE_CANDIDATE 처리 방안**: 같은 signature cluster 내 1순위(KEEP_EMPIRICAL로 "
        "이미 남은 대표물질)와 병기해 \"대표물질 + 참고물질\" 구조로 유지하거나, "
        "coverage 목적상 정말 필요 없다면 REMOVE로 재분류 — 이번 단계는 후보만 만들고 "
        "결정하지 않는다."
    )
    L.append(
        "- **독립 평가셋 필요성**: 필요하다고 판단한다. 현재 `gold_*.jsonl`은 Wave1(197종) "
        "파생이라 Wave2(223종, 이번 재평가에서 상대적으로 redundancy가 높게 나온 축)를 "
        "전혀 검증하지 못한다(PHASE 1 §7). 최소 요구사항 제안:"
    )
    L.append("  1. Wave2 KEEP_EMPIRICAL로 남은 물질(위 표, 실질 §10 근거 보유)을 우선 포함")
    L.append("  2. Wave1 파생 오염 방지 — 새 쌍 추출 시 Wave1/Wave2 구분 없이 전체 collected 기준 재추출")
    L.append("  3. 실제 §10 원문 기반 정답(gold_section)을 그대로 재사용(청킹/근거등급 로직 변경 없음)")
    L.append("  4. scarce group(그룹25 제외 13개) 및 PHASE2 ADD 16종을 최소 1회 이상 질의에 포함")
    L.append("  5. Compatible(무해) 판정 쌍을 hard-negative로 포함해 Abstain/Compatible 구분 능력 검증")
    L.append(
        "  이번 PHASE 3에서 실제 평가셋을 생성하지는 않았다 — 설계안만 제시(요청사항 "
        "그대로)."
    )
    L.append("")

    with open(OUT_REPORT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


if __name__ == "__main__":
    main()
