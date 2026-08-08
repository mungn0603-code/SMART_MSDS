# -*- coding: utf-8 -*-
"""
426종(rag_corpus_membership corpus_tag='426' == undergrad_target_chemicals.csv 중
collection_status=='COLLECTED') 실제 코퍼스를 대상으로, HANDOFF 원칙(4분류/보수적
중복제거/coverage는 보조/retrieval은 검증단계)에 따라 단순 규칙 기반으로 재분류한다.

사용 필드(독립 근거로 인정):
  - selection_source=='curriculum' + course/experiment  -> MANDATORY
  - §10.5(피해야 할 물질) 원문에 구체적 물질군(금속/물/산화제)이 명시됨 -> HAZARD-RELEVANT
    (2026-08-08 CASE 2 수정, docs/hazard_relevant_sample_audit_2026-08-08.md: 유일한 근거가
    "가연성 물질, 환원성 물질" 같은 범용 카테고리 문구뿐이면 불충분 — KOSHA MSDS 전체 466건
    §10.5 텍스트 중 가장 흔한 값이라 이 물질에 특이적인 근거인지 서식 기본값인지 원문만으로
    구분 불가. 또한 "물" substring이 "물질"의 부분 문자열로도 걸리는 버그를 원문 재파싱으로
    제거함 — 466건 중 204건이 이 버그의 영향을 받았었음.)
  - 그 물질이 속한 CAMEO 그룹이 426종 내에서 회소(<=2종)함 -> REPRESENTATIVE
  - 그 외 -> UNJUSTIFIED (자동삭제 아님, 근거부족 상태로 표시)

사용하지 않는 필드(진단자료로만 존재, 선정근거로 승격 금지):
  phase6/7/8의 retrieval hit_rate/MRR/R_tier/E_score/scenario_*, in_eval_testset,
  phase8 marginal utility dependency_class, phase3/4/6/8의 recommendation/status.
"""
import sqlite3
import pandas as pd

DB = "reactivity_reference.db"
AUDIT_CSV = "01_collection/chemical_selection_audit_dataset_2026-08-08.csv"
OUT_CSV = "01_collection/chemical_selection_final_audit_2026-08-08.csv"

con = sqlite3.connect(DB)
group_names = dict(con.execute("SELECT group_id, group_name FROM reactivity_groups").fetchall())

# §10.5(피해야 할 물질) 원문 — section10_categories 컬럼이 아니라 원문에서 직접 재파싱한다
# (그 컬럼은 "물" substring 버그를 그대로 갖고 있어 genuine/spurious를 구분할 수 없음).
s10_text_by_cas = dict(con.execute(
    "SELECT cas_number, item_detail FROM msds_sections "
    "WHERE section=10 AND item_name_kor='피해야 할 물질'"
).fetchall())

GENERIC_ONLY_KEYWORDS = ["가연성", "환원성", "환원제", "인화성"]
SPECIFIC_KEYWORDS = {"metal": ["금속"], "oxidizer": ["산화제", "산화성"]}

def genuine_s10_categories(text):
    """원문에서 직접 카테고리를 재계산한다. water는 '물질'의 부분문자열이 아닌
    독립된 '물' 언급만 인정한다(CASE 2 버그 수정)."""
    if not isinstance(text, str) or not text:
        return set()
    cats = set()
    if any(k in text for k in GENERIC_ONLY_KEYWORDS):
        cats.add("combustible_reducing")
    for cat, needles in SPECIFIC_KEYWORDS.items():
        if any(n in text for n in needles):
            cats.add(cat)
    if "물" in text.replace("물질", ""):
        cats.add("water")
    return cats

audit = pd.read_csv(AUDIT_CSV, dtype=str)
base = audit[audit.collection_status == "COLLECTED"].copy()
assert len(base) == 426, f"expected 426 collected rows, got {len(base)}"
base["s10_text"] = base.cas_number.map(s10_text_by_cas)
base["genuine_s10_cats"] = base.s10_text.apply(genuine_s10_categories)

def parse_groups(s):
    if pd.isna(s) or not str(s).strip():
        return []
    return [int(x) for x in str(s).split(";") if x.strip()]

base["group_list"] = base.true_cameo_groups.apply(parse_groups)

# group membership counts within the 426-set (structural, recomputed fresh - not inherited)
from collections import Counter
group_counts = Counter()
for gl in base.group_list:
    for g in gl:
        group_counts[g] += 1

# duplicate-signature peer groups (identical CAMEO group combination)
base["signature"] = base.group_list.apply(lambda gl: tuple(sorted(gl)))
sig_counts = Counter(base.signature)

def has_s10_evidence(row):
    """구체적 물질군(금속/물/산화제)이 있어야 충분. '가연성 물질, 환원성 물질' 같은
    범용 카테고리 문구 하나뿐이면(combustible_reducing만 있고 나머지가 비어있으면)
    불충분 근거로 취급한다(CASE 2 수정)."""
    cats = row.genuine_s10_cats
    return len(cats - {"combustible_reducing"}) > 0

def classify(row):
    scarce_groups = [g for g in row.group_list if group_counts[g] <= 2]
    is_dup = sig_counts[row.signature] > 1 and len(row.group_list) > 0
    generic_only_s10 = row.genuine_s10_cats == {"combustible_reducing"}
    generic_tag = (
        " | §10.5에 범용 카테고리 문구('가연성 물질, 환원성 물질')만 있어 CASE 2 기준상 "
        "HAZARD-RELEVANT 단독 근거로 불충분(docs/hazard_relevant_sample_audit_2026-08-08.md)"
        if generic_only_s10 else ""
    )

    if row.selection_source == "curriculum":
        category = "MANDATORY"
        reason = row.orig_selection_reason if isinstance(row.orig_selection_reason, str) else "커리큘럼 실사용 근거 확인됨"
        evidence_source = "curated_curriculum (build_undergrad_target_list.py CURATED_LIST)"
        strength = "INDEPENDENT"
        decision = "반드시 유지"
        note = ""
    elif has_s10_evidence(row):
        category = "HAZARD-RELEVANT"
        cats_str = ";".join(sorted(row.genuine_s10_cats))
        rr = f", 위험상호작용: {row.risk_relation}" if isinstance(row.risk_relation, str) and row.risk_relation.strip() else ""
        reason = f"KOSHA MSDS §10.5(피해야 할 물질) 실측 구체적 물질군 근거 존재({cats_str}){rr}"
        evidence_source = "msds_sections §10.5 원문 재파싱 (금속/물/산화제 등 구체적 물질군)"
        strength = "INDEPENDENT"
        decision = "유지 권고"
        note = ""
    elif scarce_groups:
        category = "REPRESENTATIVE"
        g = scarce_groups[0]
        reason = f"CAMEO 그룹 {g}({group_names.get(g,'?')}) 대표물질 — 426종 내 이 그룹 확보물질 {group_counts[g]}종뿐"
        evidence_source = "chemical_group_membership (CAMEO 그룹 회소성, 426종 내 재계산)"
        strength = "INDEPENDENT"
        decision = "유지 권고"
        note = f"희소 그룹: {','.join(str(g)+'('+group_names.get(g,'?')+')' for g in scarce_groups)}" + generic_tag
    else:
        category = "UNJUSTIFIED"
        reason = "자동 그룹슬롯 보충 물질 — 자체 §10 근거 없음, 커리큘럼 근거 없음, 소속 그룹도 이미 회소하지 않음(다른 물질로 충분히 대표됨)"
        evidence_source = "없음 (그룹 소속만 확인됨, 물질 단위 개별 근거 없음)"
        strength = "NONE"
        if is_dup:
            decision = "중복 검토(REMOVE/MERGE 후보)"
            peers = base[(base.signature == row.signature) & (base.cas_number != row.cas_number)]
            peer_desc = "; ".join(f"{r.chemical_name}({r.cas_number})" for r in peers.itertuples())
            note = f"동일 CAMEO 그룹조합 보유 물질 {len(peers)}종과 역할 중복 가능: {peer_desc}" + generic_tag
        else:
            decision = "근거 부족/검토"
            note = ("그룹조합 자체는 426종 내 유일하나, 그룹이 회소하지 않거나(그룹 내 다른 대표물질 이미 존재) "
                     "개별 위험성 근거가 아직 확인되지 않음") + generic_tag

    return pd.Series({
        "category": category, "selection_reason": reason,
        "evidence_source": evidence_source, "evidence_strength": strength,
        "decision": decision, "review_note": note,
    })

base = base.rename(columns={"selection_reason": "orig_selection_reason"})
result = base.join(base.apply(classify, axis=1))

out = result[[
    "cas_number", "chemical_name", "true_cameo_groups", "wave",
    "category", "selection_reason", "evidence_source", "evidence_strength",
    "decision", "review_note",
]].rename(columns={"cas_number": "cas", "true_cameo_groups": "cameo_groups"})

out.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

print("=== 분류 요약 (426종) ===")
print(result.category.value_counts())
print()
print("=== 최종 decision 요약 ===")
print(result.decision.value_counts())
print()
print(f"저장: {OUT_CSV}  ({len(out)}행)")

# coverage check: 68 groups status among the 426
valid_groups = set(g for g in group_names if group_names[g] != "Insufficient Information for Classification")
covered = set(group_counts.keys())
missing = sorted(valid_groups - covered)
thin = sorted(g for g in covered if group_counts[g] <= 2)
print(f"\n=== CAMEO 그룹 커버리지 (68개 중) ===")
print(f"커버됨: {len(covered & valid_groups)} / {len(valid_groups)}")
print(f"미커버 그룹: {[(g, group_names.get(g)) for g in missing]}")
print(f"회소 그룹(<=2종, 대표성 얇음): {len(thin)}개 -> {thin}")
