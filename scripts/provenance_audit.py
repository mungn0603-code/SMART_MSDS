# -*- coding: utf-8 -*-
"""
PHASE 1 — 427종 화학물질 Provenance Audit + Group/Coverage Audit
(docs/chemical_selection_criteria_redesign_2026-08-08.md 후속 HANDOFF)

읽기 전용 실행: 원본 CSV(undergrad_target_chemicals.csv)와 DB는 절대 수정하지 않는다.
산출물은 전부 별도 파일로만 쓴다.

산출물
------
1. 01_collection/chemical_selection_audit_dataset_2026-08-08.csv
   - CSV 475행(후보 전체) 1행=1물질, provenance 필드 부여
2. 01_collection/chemical_selection_backfill_candidates_2026-08-08.csv
   - coverage gap(그룹 내 대표물질 <=2종)에 대한 미편입 후보 목록. 자동 편입 안 함.
3. docs/chemical_selection_audit_2026-08-08.md
   - 이 스크립트가 계산한 숫자를 그대로 채워넣는 서술형 리포트(재현성 확보 —
     수치를 손으로 옮겨적지 않고 스크립트가 직접 렌더링)

근거 없이 채우지 않는다 — 못 채우면 그대로 "UNKNOWN".
"""
import csv
import json
import re
import sqlite3
from collections import Counter, defaultdict

ROOT = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS"
DB_PATH = ROOT + r"\data\reactivity_reference.db"
CSV_PATH = ROOT + r"\data\collection\undergrad_target_chemicals.csv"
PUBCHEM_REPORT = ROOT + r"\data\collection\pubchem_verification_report_full.csv"
EVALSET_DIR = ROOT + r"\data\evalset"

OUT_AUDIT_CSV = ROOT + r"\data\collection\chemical_selection_audit_dataset_2026-08-08.csv"
OUT_BACKFILL_CSV = ROOT + r"\data\collection\chemical_selection_backfill_candidates_2026-08-08.csv"
OUT_REPORT_MD = ROOT + r"\docs\chemical_selection_audit_2026-08-08.md"

FREQ_GROUPS = {40, 41, 42, 50, 51, 58, 59, 68}
RISK_RELATION_BY_GROUP = {
    40: "metal", 41: "metal", 42: "metal",
    50: "oxidizer", 51: "oxidizer",
    58: "reducer", 59: "reducer",
    68: "water",
}
SCARCE_GROUP_THRESHOLD = 2  # 그룹 내 true 대표물질 수가 이 이하이면 "coverage 필수"로 간주

# source(원본 CSV 값) -> (wave, selection_source 정규화값)
SOURCE_MAP = {
    "curated_curriculum": ("wave1", "curriculum"),
    "pool_supplement": ("wave1", "wave1_topup"),
    "pool_topup": ("wave1", "wave1_topup"),
    "pool_replacement": ("wave1", "wave1_topup"),
    "pool_replacement_v2": ("wave1", "wave1_topup"),
    "pool_replacement_v3_manual": ("wave1", "manual_addition"),
    "reaction_frequency_high": ("wave2", "wave2_expansion"),
    "reactive_basics_tier1": ("reactive_basics", "section10_empirical"),
    "reactive_basics_tier2": ("reactive_basics", "section10_empirical"),
}

# §10 "피해야 할 물질" 텍스트 카테고리 키워드 — decisions.md/expand_by_reaction_frequency.py가
# 서로 다른 키워드셋으로 서로 다른 백분율을 냈던 문제(감사 대상)를 재현 가능하게 만들기 위해
# 카테고리를 넓게(포함) 정의하고 각 카테고리의 실제 문자열 변형을 전부 명시한다.
S10_CATEGORIES = {
    "combustible_reducing": ["가연성", "환원성", "환원제", "인화성"],
    "metal": ["금속"],
    "oxidizer": ["산화제", "산화성"],
    "water": ["물"],
    "no_data": ["자료없음"],
}


def load_csv_rows():
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_pubchem():
    out = {}
    with open(PUBCHEM_REPORT, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            out[r["cas_number"]] = r["status"]
    return out


def load_eval_cas():
    """평가셋(gold_pair/gold_pair_abstain/gold_retrieval/gold_abstain)에 등장하는
    CAS 집합 + CAS별 등장 query_id 목록(evidence 용)."""
    hits = defaultdict(list)
    files = [
        ("gold_pair.jsonl", ("cas_a", "cas_b")),
        ("gold_pair_abstain.jsonl", ("cas_a", "cas_b")),
        ("gold_retrieval.jsonl", ("cas_number",)),
        ("gold_abstain.jsonl", ("cas_number",)),
    ]
    for fname, keys in files:
        path = f"{EVALSET_DIR}\\{fname}"
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    for k in keys:
                        cas = rec.get(k)
                        if cas:
                            hits[cas].append(f"{fname}:{rec.get('query_id', '')}")
        except FileNotFoundError:
            continue
    return hits


def s10_categories_for_text(text):
    if not text:
        return set()
    cats = set()
    for cat, needles in S10_CATEGORIES.items():
        if any(n in text for n in needles):
            cats.add(cat)
    return cats


def main():
    csv_rows = load_csv_rows()
    pubchem = load_pubchem()
    eval_hits = load_eval_cas()

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    group_names = dict(cur.execute("SELECT group_id, group_name FROM reactivity_groups").fetchall())
    all_group_ids = set(group_names.keys())

    # chemicals: cas -> chemical_id / name
    chem_by_cas = {}
    for r in cur.execute("SELECT chemical_id, cas_number, chemical_name FROM chemicals"):
        chem_by_cas[r["cas_number"]] = (r["chemical_id"], r["chemical_name"])

    # chemical_id -> [group_id...]  (true membership, 다중 그룹 포함)
    membership = defaultdict(list)
    for r in cur.execute("SELECT chemical_id, group_id FROM chemical_group_membership"):
        membership[r["chemical_id"]].append(r["group_id"])

    # msds_chem_id_cache: cas -> chem_id(str) or None(=Abstain, KOSHA 미등록)
    cache = {}
    for r in cur.execute("SELECT cas_number, chem_id FROM msds_chem_id_cache"):
        cache[r["cas_number"]] = r["chem_id"]

    # msds_sections: cas -> 확보 섹션 수
    section_count = Counter()
    for r in cur.execute("SELECT cas_number, COUNT(DISTINCT section) c FROM msds_sections GROUP BY cas_number"):
        section_count[r["cas_number"]] = r["c"]

    # section10 "피해야 할 물질" 원문 (cas -> text)
    s10_text = {}
    for r in cur.execute(
        "SELECT cas_number, item_detail FROM msds_sections "
        "WHERE section=10 AND item_name_kor='피해야 할 물질'"
    ):
        s10_text[r["cas_number"]] = r["item_detail"] or ""

    # group-pair 판정표 (compatibility_engine.py의 judge_pair_by_cas와 동일 로직을
    # 소규모 인메모리 lookup으로 재현 — 90,525쌍을 빠르게 처리하기 위함)
    pair_category = {}
    for r in cur.execute("SELECT group_a_id, group_b_id, category FROM compatibility_pairs"):
        pair_category[(r["group_a_id"], r["group_b_id"])] = r["category"]
    self_category = {}
    for r in cur.execute("SELECT group_id, category FROM self_reactivity"):
        self_category[r["group_id"]] = r["category"]

    # chemical_group_membership 전체 풀(3,396종) — backfill 후보 생성용
    pool_by_group = defaultdict(list)
    for r in cur.execute(
        "SELECT m.group_id, c.cas_number, c.chemical_name "
        "FROM chemical_group_membership m JOIN chemicals c ON c.chemical_id = m.chemical_id"
    ):
        pool_by_group[r["group_id"]].append((r["cas_number"], r["chemical_name"]))

    con.close()

    # ------------------------------------------------------------------
    # 1) CSV 후보 475행 각각의 provenance 레코드 구성
    # ------------------------------------------------------------------
    orphan_cas = set(section_count) - set(r["cas_number"] for r in csv_rows)  # ex) 497-19-8

    records = []
    for row in csv_rows:
        cas = row["cas_number"]
        raw_source = row["source"]
        wave, sel_source = SOURCE_MAP.get(raw_source, ("unknown", "unknown"))

        chem_id, chem_name = chem_by_cas.get(cas, (None, row["chemical_name"]))
        true_groups = sorted(membership.get(chem_id, [])) if chem_id else []
        csv_group_id = int(row["group_id"])
        if not true_groups:
            true_groups = [csv_group_id]  # DB 조회 실패시 CSV 배정값으로 폴백(그대로 명시)

        risk_relations = sorted({RISK_RELATION_BY_GROUP[g] for g in true_groups if g in RISK_RELATION_BY_GROUP})

        n_sections = section_count.get(cas, 0)
        if n_sections == 4:
            collection_status = "COLLECTED"
        elif n_sections > 0:
            collection_status = "PARTIAL"
        elif cas in cache and cache[cas] is None:
            collection_status = "ABSTAIN_NOT_FOUND"
        elif cas in cache:
            collection_status = "PARTIAL"
        else:
            collection_status = "NOT_ATTEMPTED"

        text = s10_text.get(cas, "")
        cats = s10_categories_for_text(text)

        in_eval = cas in eval_hits
        evidence_bits = []

        if raw_source == "curated_curriculum":
            reason = f"커리큘럼 실사용 근거: {row['course']} / {row['experiment']}"
            evidence = "01_collection/build_undergrad_target_list.py CURATED_LIST"
        elif raw_source == "reaction_frequency_high":
            rel = ",".join(risk_relations) if risk_relations else "(그룹 매핑 없음)"
            reason = f"실측 §10 위험관계 고빈도 그룹(위험관계={rel}) 소속으로 무제한 편입"
            evidence = "01_collection/expand_by_reaction_frequency.py FREQ_GROUPS + docs/decisions.md §1.2a-upd"
        elif raw_source in ("reactive_basics_tier1", "reactive_basics_tier2"):
            reason = "§10 전수조사(197종) 실측 1순위 반응 상대(물 등) 기본물질 보강"
            evidence = "docs/decisions.md §1.2a-upd"
        elif raw_source in ("pool_replacement", "pool_replacement_v2"):
            reason = "원 후보가 KOSHA 미등록이라 같은 그룹 내 다음 후보로 자동 대체"
            evidence = "01_collection/backfill_group_replacements.py"
        elif raw_source == "pool_replacement_v3_manual":
            reason = "자동 안전필터로 못 거른 물질을 사람이 검토해 대체"
            evidence = "01_collection/backfill_round3_manual_picks.py"
        elif raw_source in ("pool_supplement", "pool_topup"):
            reason = "UNKNOWN(그룹 슬롯 자동 보충 — 물질 단위 개별 선정 근거 없음)"
            evidence = "01_collection/build_undergrad_target_list.py GROUP_TIER/TIER_SLOTS(근거 미기록)"
        else:
            reason = "UNKNOWN"
            evidence = "UNKNOWN"

        if in_eval:
            evidence_bits.append("evaluation_data:" + ";".join(eval_hits[cas][:3]))

        pv_status = pubchem.get(cas, "NOT_IN_REPORT")

        safety_flag = "NOT_CHECKED"
        if cas == "1271-28-9":
            safety_flag = "REVIEWED_H351_KEPT(01_collection/backfill_round3_manual_picks.py)"

        records.append({
            "cas_number": cas,
            "chemical_name": chem_name,
            "wave": wave,
            "original_candidate_source": raw_source,
            "selection_source": sel_source,
            "selection_reason": reason,
            "selection_evidence": evidence + ((" | " + "; ".join(evidence_bits)) if evidence_bits else ""),
            "csv_assigned_group_id": csv_group_id,
            "true_cameo_groups": ";".join(str(g) for g in true_groups),
            "risk_relation": ";".join(risk_relations),
            "section10_categories": ";".join(sorted(cats)),
            "section10_text": text,
            "coverage_role": "",  # 아래 그룹 통계 계산 후 채움
            "pubchem_verified": pv_status,
            "safety_flag": safety_flag,
            "in_eval_testset": in_eval,
            "collection_status": collection_status,
            "true_groups_list": true_groups,
        })

    # ------------------------------------------------------------------
    # 2) 그룹별 true-membership 통계(수집 완료분 COLLECTED만 대상)
    # ------------------------------------------------------------------
    collected = [r for r in records if r["collection_status"] == "COLLECTED"]
    group_member_count = Counter()
    group_wave_count = defaultdict(lambda: Counter())
    for r in collected:
        for g in r["true_groups_list"]:
            group_member_count[g] += 1
            group_wave_count[g][r["wave"]] += 1

    covered_groups = set(group_member_count.keys())
    missing_groups = sorted(all_group_ids - covered_groups)

    for r in records:
        if r["collection_status"] != "COLLECTED":
            continue
        scarce = [g for g in r["true_groups_list"] if group_member_count[g] <= SCARCE_GROUP_THRESHOLD]
        if scarce:
            r["coverage_role"] = "scarce_group:" + ";".join(str(g) for g in scarce)

    # ------------------------------------------------------------------
    # 3) selection_status 분류 (COLLECTED만 해당, 나머지는 NOT_COLLECTED)
    # ------------------------------------------------------------------
    # 주의(순환논리 방지): 04_rag_agent/evalset/gold_*.jsonl은 198~203종(=Wave1) 풀에서
    # "기계적으로 파생"된 데이터다(HANDOFF.md §0-2). 따라서 "평가데이터에 등장한다"를
    # Wave1 물질의 KEEP_MANDATORY 근거로 쓰면 "Wave1이었으니까 평가셋에 있고, 평가셋에
    # 있으니까 Wave1은 정당하다"는 순환논리가 된다(실측: eval 등장 196종 전부 Wave1
    # 파생, Wave2 223종 중 0종). 그래서 평가데이터 근거는 Wave1 외부(Wave2/기본물질처럼
    # eval 풀 생성에 관여하지 않은 물질)에만 독립 증거로 인정한다.
    for r in records:
        if r["collection_status"] != "COLLECTED":
            r["selection_status"] = "NOT_COLLECTED"
            continue
        if r["original_candidate_source"] == "curated_curriculum":
            r["selection_status"] = "KEEP_MANDATORY"
        elif r["wave"] != "wave1" and r["in_eval_testset"]:
            r["selection_status"] = "KEEP_MANDATORY"
        elif r["coverage_role"].startswith("scarce_group"):
            r["selection_status"] = "KEEP_COVERAGE"
        elif r["original_candidate_source"] in ("reactive_basics_tier1", "reactive_basics_tier2"):
            r["selection_status"] = "KEEP_EMPIRICAL"
        elif r["original_candidate_source"] == "pool_replacement_v3_manual":
            r["selection_status"] = "REVIEW"
        elif r["original_candidate_source"] in ("pool_replacement", "pool_replacement_v2"):
            r["selection_status"] = "REVIEW"
        elif r["original_candidate_source"] == "reaction_frequency_high":
            r["selection_status"] = "REVIEW"  # 아래 signature 기반 재분류로 DUPLICATE 승격
        elif r["original_candidate_source"] in ("pool_supplement", "pool_topup"):
            r["selection_status"] = "UNSUPPORTED"
        else:
            r["selection_status"] = "UNKNOWN"

    # signature(=true_groups 조합) 기반 중복 판정: 매트릭스 엔진 관점에서 그룹조합이
    # 완전히 같은 물질은 다른 모든 물질과의 판정 결과가 100% 동일하다(정보량 동일).
    # "그룹 내 물질 수가 많다"는 크기 기준(임의 숫자) 대신 이 수학적 사실을 근거로 쓴다.
    sig_groups = defaultdict(list)
    for r in records:
        if r["selection_status"] == "REVIEW" and r["original_candidate_source"] == "reaction_frequency_high":
            sig = tuple(r["true_groups_list"])
            sig_groups[sig].append(r)
    for sig, members in sig_groups.items():
        if len(members) < 2:
            continue
        members.sort(key=lambda x: x["cas_number"])
        for dup in members[1:]:
            dup["selection_status"] = "DUPLICATE"
            dup["selection_evidence"] += (
                f" | signature_duplicate_of={members[0]['cas_number']}"
                f"(동일 true_cameo_groups={sig} 조합 물질 {len(members)}종 중 대표 1종 제외 나머지)"
            )

    # ------------------------------------------------------------------
    # 4) risk-pair coverage: 그룹쌍 매트릭스로 COLLECTED 426종 전수 쌍 판정
    # ------------------------------------------------------------------
    def group_pair_category(ga, gb):
        a, b = sorted((ga, gb))
        if a == b:
            return self_category.get(a, "Unknown")
        return pair_category.get((a, b), "Unknown")

    _RANK = {"Compatible": 0, "Caution": 1, "Incompatible": 2}
    # §10 텍스트 카테고리 -> risk_relation 매핑(교차검증용): 이 물질의 §10 "피해야 할
    # 물질"에 적힌 카테고리가, 상대 물질의 실제 소속 그룹이 대표하는 위험관계와 일치하는가.
    TEXT_TO_RELATION = {
        "water": "water", "metal": "metal", "oxidizer": "oxidizer",
        "combustible_reducing": "reducer",
    }
    for r in collected:
        r["text_relations"] = {TEXT_TO_RELATION[c] for c in s10_categories_for_text(r["section10_text"]) if c in TEXT_TO_RELATION}
        r["group_relations"] = set(RISK_RELATION_BY_GROUP.get(g) for g in r["true_groups_list"]) - {None}

    n_pairs = 0
    n_incompatible = 0
    n_caution = 0
    n_compatible = 0
    n_abstain = 0
    n_text_evidenced = 0
    n_incompatible_text_evidenced = 0
    wave_pair_counter = Counter()
    for i in range(len(collected)):
        for j in range(i + 1, len(collected)):
            a, b = collected[i], collected[j]
            worst = "Compatible"
            any_known = False
            for ga in a["true_groups_list"]:
                for gb in b["true_groups_list"]:
                    cat = group_pair_category(ga, gb)
                    if cat == "Unknown":
                        continue
                    any_known = True
                    if _RANK[cat] > _RANK[worst]:
                        worst = cat
            n_pairs += 1
            final = worst if any_known else "Abstain"
            if final == "Incompatible":
                n_incompatible += 1
            elif final == "Caution":
                n_caution += 1
            elif final == "Compatible":
                n_compatible += 1
            else:
                n_abstain += 1
            if final in ("Incompatible", "Caution"):
                wave_pair_counter[(a["wave"], b["wave"])] += 1

            text_evidenced = bool(a["text_relations"] & b["group_relations"]) or bool(b["text_relations"] & a["group_relations"])
            if text_evidenced:
                n_text_evidenced += 1
                if final == "Incompatible":
                    n_incompatible_text_evidenced += 1

    # ------------------------------------------------------------------
    # 5) §10 카테고리 corpus 통계 (COLLECTED 426종 기준)
    # ------------------------------------------------------------------
    n_collected = len(collected)
    cat_counter = Counter()
    for r in collected:
        for c in s10_categories_for_text(r["section10_text"]):
            cat_counter[c] += 1

    # 이름 substring 매칭 (exploratory) — 참고용으로만 계산, 결과는 리포트에서 해석
    names = []
    for r in collected:
        for seg in r["chemical_name"].split(";"):
            seg = seg.strip()
            if len(seg) >= 2:
                names.append((seg, r["cas_number"]))
    name_match_count = Counter()
    total_name_hits = 0
    for r in collected:
        text = r["section10_text"]
        if not text or text == "자료없음":
            continue
        for seg, other_cas in names:
            if other_cas == r["cas_number"]:
                continue
            if seg in text:
                name_match_count[r["cas_number"]] += 1
                total_name_hits += 1

    # ------------------------------------------------------------------
    # 6) backfill 후보(coverage gap) 목록 — 자동 편입 안 함
    # ------------------------------------------------------------------
    existing_cas_all = set(r["cas_number"] for r in csv_rows)
    backfill_rows = []
    scarce_groups = sorted(g for g in all_group_ids if group_member_count.get(g, 0) <= SCARCE_GROUP_THRESHOLD)
    for g in scarce_groups:
        candidates = [(cas, name) for cas, name in pool_by_group.get(g, []) if cas not in existing_cas_all]
        for cas, name in candidates[:5]:
            kosha_status = "not_attempted"
            if cas in cache:
                kosha_status = "abstain_not_found" if cache[cas] is None else "kosha_registered"
            backfill_rows.append({
                "group_id": g,
                "group_name": group_names.get(g, ""),
                "current_true_member_count": group_member_count.get(g, 0),
                "candidate_cas": cas,
                "candidate_name": name,
                "kosha_status": kosha_status,
                "note": "coverage gap: 그룹 내 대표물질 2종 이하",
            })

    # ------------------------------------------------------------------
    # 7) 출력 1: audit CSV (475행)
    # ------------------------------------------------------------------
    audit_fields = [
        "cas_number", "chemical_name", "wave", "original_candidate_source",
        "selection_source", "selection_reason", "selection_evidence",
        "csv_assigned_group_id", "true_cameo_groups", "risk_relation",
        "section10_categories", "coverage_role", "pubchem_verified",
        "safety_flag", "in_eval_testset", "collection_status", "selection_status",
    ]
    with open(OUT_AUDIT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=audit_fields, extrasaction="ignore")
        w.writeheader()
        for r in records:
            w.writerow(r)

    # ------------------------------------------------------------------
    # 8) 출력 2: backfill candidate CSV
    # ------------------------------------------------------------------
    with open(OUT_BACKFILL_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=[
            "group_id", "group_name", "current_true_member_count",
            "candidate_cas", "candidate_name", "kosha_status", "note",
        ])
        w.writeheader()
        w.writerows(backfill_rows)

    # ------------------------------------------------------------------
    # 9) 콘솔 요약 (리포트 md는 별도로 사람이 작성 — 아래 수치를 그대로 인용)
    # ------------------------------------------------------------------
    print("=== PHASE 1 감사 요약 ===")
    print(f"CSV 후보 총수: {len(csv_rows)}")
    print(f"COLLECTED(4섹션 완비): {n_collected}")
    print(f"ABSTAIN_NOT_FOUND: {sum(1 for r in records if r['collection_status']=='ABSTAIN_NOT_FOUND')}")
    print(f"PARTIAL: {sum(1 for r in records if r['collection_status']=='PARTIAL')}")
    print(f"NOT_ATTEMPTED: {sum(1 for r in records if r['collection_status']=='NOT_ATTEMPTED')}")
    print(f"DB상 orphan(cas not in current CSV, 4섹션 존재): {sorted(orphan_cas)}")
    print()
    print("selection_status 분포(COLLECTED만):")
    print(Counter(r["selection_status"] for r in records if r["collection_status"] == "COLLECTED"))
    print()
    print("wave 분포(COLLECTED만):", Counter(r["wave"] for r in collected))
    print()
    print(f"68그룹 중 covered: {len(covered_groups)} / missing: {missing_groups}")
    top_groups = group_member_count.most_common(10)
    print("상위 10그룹:", [(g, group_names.get(g), c) for g, c in top_groups])
    top8_sum = sum(group_member_count.get(g, 0) for g in FREQ_GROUPS)
    print(f"8개 실측빈도그룹(40/41/42/50/51/58/59/68) 합계: {top8_sum} / {n_collected} = {top8_sum/n_collected:.1%}")
    print()
    print("§10 카테고리 분포(COLLECTED 426 기준, 카테고리 중복집계 가능):")
    for cat, cnt in cat_counter.most_common():
        print(f"  {cat}: {cnt}/{n_collected} = {cnt/n_collected:.1%}")
    print()
    print("이름 substring 매칭(exploratory) 총 히트수:", total_name_hits,
          "/ 히트 있는 물질 수:", len(name_match_count))
    print()
    print("Risk-pair coverage (그룹매트릭스 기반, COLLECTED 426종 전수 C(426,2)):")
    print(f"  전체 쌍수: {n_pairs}")
    print(f"  Incompatible: {n_incompatible} ({n_incompatible/n_pairs:.2%})")
    print(f"  Caution: {n_caution} ({n_caution/n_pairs:.2%})")
    print(f"  Compatible: {n_compatible} ({n_compatible/n_pairs:.2%})")
    print(f"  Abstain(그룹쌍 매트릭스 값 없음): {n_abstain} ({n_abstain/n_pairs:.2%})")
    print("  Wave간 위험쌍(Incompatible/Caution) 분포:", dict(wave_pair_counter))
    print()
    print("§10 텍스트-교차검증 risk-pair (한쪽의 §10 카테고리가 상대 물질의 실제 그룹 "
          "위험관계와 일치하는 쌍 — 그룹매트릭스보다 보수적/직접적인 근거):")
    print(f"  text_evidenced 쌍: {n_text_evidenced} / {n_pairs} = {n_text_evidenced/n_pairs:.2%}")
    print(f"  그중 매트릭스도 Incompatible: {n_incompatible_text_evidenced} "
          f"(matrix-only Incompatible {n_incompatible}건 중 "
          f"{n_incompatible_text_evidenced/n_incompatible:.2%}가 텍스트로도 뒷받침됨)")
    print()
    print("그룹별 wave 분해(상위 10, true-membership 기준):")
    for g, cnt in top_groups:
        print(f"  그룹{g} {group_names.get(g)}: 총{cnt} = {dict(group_wave_count[g])}")
    print()
    print("평가셋(gold_*) 등장 CAS 수:", len(eval_hits))
    print("  그중 현재 427(COLLECTED) 내 포함:", sum(1 for cas in eval_hits if cas in set(r['cas_number'] for r in collected)))
    print("  그중 CSV 475 후보에도 없음(=평가셋에만 있는 CAS):",
          sorted(set(eval_hits) - existing_cas_all)[:10], "...")
    print()
    print("Group 25 (Diazonium Salts) 진단:")
    print("  true member in COLLECTED:", group_member_count.get(25, 0))
    print("  전체 풀(pool_by_group) 내 후보:", pool_by_group.get(25, []))
    print()
    print(f"backfill candidate rows(자동편입 아님): {len(backfill_rows)}, groups covered: {len(scarce_groups)}")
    print()
    print("산출물:")
    print(" ", OUT_AUDIT_CSV)
    print(" ", OUT_BACKFILL_CSV)


if __name__ == "__main__":
    main()
