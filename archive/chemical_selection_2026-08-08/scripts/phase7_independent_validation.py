# -*- coding: utf-8 -*-
"""
PHASE 7-1/2/3/4/5/6/7 — 기존 independent_eval_prototype(50건) 전수 감사.

핵심 질문: "independent evaluation에서 301(C)이 38.9%로 낮게 나온 정확한 원인은?"
Phase6에서 낸 38.9%는 corpus_membership(양쪽 물질이 그 코퍼스에 존재하는가) 체크였지
실제 retrieval 성능(Recall/MRR)이 아니었다 — 이 스크립트가 그 둘을 분리해서 재확인한다.

또한 프로토타입 파일의 `gold_section` 필드는 PHASE 4-F 생성 시점(그때 `rag_chunks`는
Wave1 197종만 있던 구버전 상태)에 계산된 것이라 **지금 기준으로 stale** —
PHASE 5에서 rag_chunks를 426/259proposed 기준으로 재구축했으므로, 이 스크립트가
현재 rag_chunks 기준으로 gold_section을 다시 계산해 얼마나 달라지는지 직접 비교한다.

읽기 전용 — DB/CSV에 쓰기 없음.
"""
import csv
import json
import re
import sqlite3
from collections import Counter, defaultdict

ROOT = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS"
DB_PATH = ROOT + r"\reactivity_reference.db"
PROTOTYPE_JSONL = ROOT + r"\04_rag_agent\evalset\independent_eval_prototype_2026-08-08.jsonl"
PHASE6_CSV = ROOT + r"\01_collection\chemical_phase6_retrieval_reassessment_2026-08-08.csv"
PHASE4_CSV = ROOT + r"\01_collection\chemical_phase4_adjudication_2026-08-08.csv"

OUT_AUDIT_CSV = ROOT + r"\01_collection\chemical_phase7_eval_audit_2026-08-08.csv"

CAS_RE = re.compile(r"^sec::([^:]+)::(\d+)")


def main():
    with open(PROTOTYPE_JSONL, encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]
    pairs = [r for r in records if r["kind"] == "pair"]
    print(f"prototype 전체 {len(records)}건, pair {len(pairs)}건")

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # 현재(최신) rag_chunks 기준 섹션 청크 목록 재계산(§2,§10만)
    cur_sec_chunks = defaultdict(list)
    chunk_text = {}
    for chunk_id, cas, section, text in cur.execute(
        "SELECT chunk_id, cas_number, section, text FROM rag_chunks "
        "WHERE granularity='section' AND section IN (2,10)"
    ):
        cur_sec_chunks[(cas, section)].append(chunk_id)
        chunk_text[chunk_id] = text

    def membership(tag):
        cur.execute("SELECT cas_number FROM rag_corpus_membership WHERE corpus_tag=?", (tag,))
        return {r[0] for r in cur.fetchall()}

    mem = {tag: membership(tag) for tag in ("426", "259proposed", "259_retrieval_aware", "phase6_D")}
    con.close()

    with open(PHASE6_CSV, encoding="utf-8-sig") as f:
        phase6 = {r["cas"]: r for r in csv.DictReader(f)}
    with open(PHASE4_CSV, encoding="utf-8-sig") as f:
        phase4 = {r["cas"]: r for r in csv.DictReader(f)}

    def status_of(cas):
        if cas in phase4:
            return phase4[cas]["phase4_status"], phase4[cas].get("representative_cas", "")
        return "KEEP(PHASE1)", ""

    rows = []
    for rec in pairs:
        fresh_gold = []
        for cas in (rec["cas_a"], rec["cas_b"]):
            for sec in (2, 10):
                fresh_gold += cur_sec_chunks.get((cas, sec), [])
        stale_gold = rec.get("gold_section", [])

        both_in = {}
        for tag in mem:
            both_in[tag] = (rec["cas_a"] in mem[tag]) and (rec["cas_b"] in mem[tag])

        st_a, rep_a = status_of(rec["cas_a"])
        st_b, rep_b = status_of(rec["cas_b"])

        # gold label 검증: 청크가 실존하고 텍스트가 실질적인가(자료없음 단독이 아님)
        valid_chunks = [c for c in fresh_gold if chunk_text.get(c, "").strip() not in ("", "자료없음")]

        # query leakage: 질의 문자열에 CAS 그대로 또는 물질명이 그대로 들어있는가
        q = rec["query"]
        leak_name_a = rec["name_a"] in q
        leak_name_b = rec["name_b"] in q
        leak_cas_a = rec["cas_a"] in q
        leak_cas_b = rec["cas_b"] in q

        rows.append({
            "query_id": rec["query_id"],
            "query": q,
            "cas_a": rec["cas_a"], "name_a": rec["name_a"],
            "cas_b": rec["cas_b"], "name_b": rec["name_b"],
            "cameo_groups_a": ";".join(map(str, rec["cameo_groups_a"])),
            "cameo_groups_b": ";".join(map(str, rec["cameo_groups_b"])),
            "gold_risk_pair": rec["gold_risk_pair"],
            "stale_gold_section_count": len(stale_gold),
            "fresh_gold_section_count": len(fresh_gold),
            "fresh_gold_valid_content_count": len(valid_chunks),
            "in_426": both_in["426"], "in_259proposed": both_in["259proposed"],
            "in_301_C": both_in["259_retrieval_aware"], "in_D": both_in["phase6_D"],
            "cas_a_phase4_status": st_a, "cas_a_representative": rep_a,
            "cas_b_phase4_status": st_b, "cas_b_representative": rep_b,
            "wave_a": rec["wave_a"], "wave_b": rec["wave_b"],
            "difficulty": rec["difficulty"],
            "independence_wave_flag": rec["independence"],
            "leak_name_a": leak_name_a, "leak_name_b": leak_name_b,
            "leak_cas_a": leak_cas_a, "leak_cas_b": leak_cas_b,
            "provenance_tier": "DIAGNOSTIC",  # 전부 wave/group 인지 표집이라 강한 의미의 독립 아님(§ 보고서 참고)
        })

    fields = list(rows[0].keys())
    with open(OUT_AUDIT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    # ---- 요약 ----
    n = len(rows)
    print(f"\n=== membership 커버리지(양쪽 물질 다 코퍼스에 존재) ===")
    for tag, key in [("426", "in_426"), ("259proposed", "in_259proposed"), ("301(C)", "in_301_C"), ("D", "in_D")]:
        cnt = sum(1 for r in rows if r[key])
        print(f"  {tag}: {cnt}/{n} ({cnt/n:.1%})")

    print(f"\n=== gold_section: stale(파일 저장값) vs fresh(현재 rag_chunks 재계산) ===")
    stale_nonzero = sum(1 for r in rows if r["stale_gold_section_count"] > 0)
    fresh_nonzero = sum(1 for r in rows if r["fresh_gold_section_count"] > 0)
    fresh_both_sides = sum(1 for r in rows if r["fresh_gold_valid_content_count"] >= 2)
    print(f"  stale gold_section>0: {stale_nonzero}/{n}")
    print(f"  fresh gold_section>0: {fresh_nonzero}/{n}")
    print(f"  fresh gold 실질내용>=2건(양쪽 다 뭔가 있음): {fresh_both_sides}/{n}")

    print(f"\n=== 301(C)에서 membership 미충족 원인 분해 ===")
    miss = [r for r in rows if not r["in_301_C"]]
    print(f"  미충족 쌍: {len(miss)}/{n}")
    reason_counter = Counter()
    for r in miss:
        missing_sides = []
        if r["cas_a_phase4_status"] not in ("KEEP(PHASE1)",):
            missing_sides.append(f"a={r['cas_a_phase4_status']}")
        if r["cas_b_phase4_status"] not in ("KEEP(PHASE1)",):
            missing_sides.append(f"b={r['cas_b_phase4_status']}")
        reason_counter[",".join(missing_sides) if missing_sides else "unknown"] += 1
    for k, v in reason_counter.most_common():
        print(f"    {k}: {v}건")

    print(f"\n=== query leakage(질의에 물질명/CAS 그대로 노출) ===")
    leak_any_name = sum(1 for r in rows if r["leak_name_a"] or r["leak_name_b"])
    print(f"  질의에 정답 물질명이 그대로 포함: {leak_any_name}/{n} ({leak_any_name/n:.1%})")

    print(f"\n=== §2/§10, wave 분포 ===")
    print(f"  wave 조합: {dict(Counter((r['wave_a'], r['wave_b']) for r in rows))}")
    print(f"  difficulty: {dict(Counter(r['difficulty'] for r in rows))}")

    print(f"\n산출물: {OUT_AUDIT_CSV}")
    return rows


# =====================================================================
# PHASE 7-8/9 — 신규 독립 평가셋 생성 (100~200건, wave 편향 없는 계층표집)
# =====================================================================
import random  # noqa: E402
import sys  # noqa: E402

sys.path.insert(0, r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\04_rag_agent")
from evalset_pairs import pair_verdict  # noqa: E402  (판정 로직 재사용, 새로 안 만듦)

OUT_NEW_JSONL = ROOT + r"\04_rag_agent\evalset\independent_eval_v2_2026-08-08.jsonl"
OUT_NEW_CSV = ROOT + r"\01_collection\chemical_phase7_independent_evalset_2026-08-08.csv"

SEED = 20260808
TARGET_N = 150

NAME_TEMPLATES = [
    "{a}와 {b}를 함께 취급해도 되는가? 혼합 시 위험성과 유의사항은?",
    "{a}랑 {b} 같이 보관해도 괜찮을까요?",
    "실험실에 {a}와 {b}가 둘 다 있는데 옆에 놔둬도 되나요?",
]
CAS_TEMPLATES = [
    "CAS {ca}와 CAS {cb} 두 물질의 반응 위험성을 알려줘.",
    "CAS번호 {ca}, {cb} 조합의 안전성을 검토해줘.",
]

OLD_PAIR_KEYS = None  # 기존 36쌍과 중복 방지용, generate_new_evalset()에서 채움


def generate_new_evalset():
    global OLD_PAIR_KEYS
    with open(PROTOTYPE_JSONL, encoding="utf-8") as f:
        old_records = [json.loads(line) for line in f if line.strip()]
    OLD_PAIR_KEYS = {tuple(sorted((r["cas_a"], r["cas_b"]))) for r in old_records if r["kind"] == "pair"}

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    names = {}
    for cid, cas, name in cur.execute("SELECT chemical_id, cas_number, chemical_name FROM chemicals"):
        names[cas] = name
    groups = defaultdict(set)
    for cas, gid in cur.execute(
        "SELECT ch.cas_number, m.group_id FROM chemicals ch "
        "JOIN chemical_group_membership m ON m.chemical_id = ch.chemical_id"
    ):
        groups[cas].add(gid)
    matrix = {(a, b): cat for a, b, cat in cur.execute("SELECT group_a_id, group_b_id, category FROM compatibility_pairs")}
    self_react = dict(cur.execute("SELECT group_id, category FROM self_reactivity").fetchall())
    group_names = dict(cur.execute("SELECT group_id, group_name FROM reactivity_groups").fetchall())
    sec_chunks = defaultdict(list)
    chunk_text = {}
    for chunk_id, cas, section, text in cur.execute(
        "SELECT chunk_id, cas_number, section, text FROM rag_chunks WHERE granularity='section' AND section IN (2,10)"
    ):
        sec_chunks[(cas, section)].append(chunk_id)
        chunk_text[chunk_id] = text
    cur.execute("SELECT cas_number FROM rag_corpus_membership WHERE corpus_tag='426'")
    collected_426 = [r[0] for r in cur.fetchall()]
    con.close()

    with open(PHASE6_CSV, encoding="utf-8-sig") as f:
        phase6_rows = list(csv.DictReader(f))
    review_cas = [r["cas"] for r in phase6_rows if r["phase6_status"] == "REVIEW"]

    wave_of = {}
    with open(ROOT + r"\01_collection\chemical_selection_audit_dataset_2026-08-08.csv", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            wave_of[r["cas_number"]] = r["wave"]

    collected_426 = [c for c in collected_426 if c in names]

    group_member_count = defaultdict(int)
    for cas in collected_426:
        for g in groups.get(cas, ()):
            group_member_count[g] += 1
    scarce_groups = sorted({g for g, c in group_member_count.items() if 0 < c <= 2 and g != 25})

    rng = random.Random(SEED)

    def has_real_content(cas):
        for sec in (2, 10):
            for cid in sec_chunks.get((cas, sec), []):
                t = chunk_text.get(cid, "").strip()
                if t and t != "자료없음":
                    return True
        return False

    usable = [c for c in collected_426 if has_real_content(c)]
    review_usable = [c for c in review_cas if c in usable]
    print(f"426 중 §2/§10 실질내용 있는 물질(usable): {len(usable)}, 그중 REVIEW-134: {len(review_usable)}")

    def make_pair_record(a, b, idx, category_hint=None):
        key = tuple(sorted((a, b)))
        if key in OLD_PAIR_KEYS or a == b:
            return None
        worst, cats = pair_verdict(groups.get(a, set()), groups.get(b, set()), matrix, self_react)
        if category_hint and worst != category_hint:
            return None
        gold = []
        for cas in (a, b):
            for sec in (2, 10):
                gold += sec_chunks.get((cas, sec), [])
        gold_valid = [c for c in gold if chunk_text.get(c, "").strip() not in ("", "자료없음")]
        if not gold_valid:
            return None
        use_cas_template = idx % 2 == 1
        if use_cas_template:
            tpl = rng.choice(CAS_TEMPLATES)
            query = tpl.format(ca=a, cb=b)
        else:
            tpl = rng.choice(NAME_TEMPLATES)
            query = tpl.format(a=names[a], b=names[b])
        return {
            "query_id": f"indepv2::{a}::{b}",
            "query": query,
            "kind": "pair",
            "cas_a": a, "cas_b": b, "name_a": names[a], "name_b": names[b],
            "wave_a": wave_of.get(a, "unknown"), "wave_b": wave_of.get(b, "unknown"),
            "cameo_groups_a": sorted(groups.get(a, ())), "cameo_groups_b": sorted(groups.get(b, ())),
            "gold_risk_pair": worst, "gold_risk_pair_all": cats,
            "gold_section": sorted(gold_valid),
            "query_style": "cas_based" if use_cas_template else "name_based",
            "contains_exact_name": (not use_cas_template),
            "contains_exact_cas": use_cas_template,
            "involves_review134": a in review_cas or b in review_cas,
            "source": "phase7_independent_v2_2026-08-08",
            "verification_method": "rule_based_self_check",
            "human_verified": False,
            "provenance_tier": "DIAGNOSTIC",  # §보고서: wave/그룹 인지 계층표집이라 완전한 INDEPENDENT는 아님, 근거는 객관적(매트릭스+원문)
        }

    records = []
    idx = 0

    # 1) scarce group 커버리지 — 각 그룹에서 1쌍
    for g in scarce_groups:
        members = [c for c in usable if g in groups.get(c, ())]
        if not members:
            continue
        a = members[0]
        partner_pool = [c for c in usable if c != a]
        rng.shuffle(partner_pool)
        for b in partner_pool:
            rec = make_pair_record(a, b, idx)
            if rec:
                rec["note"] = f"희소그룹 {g}({group_names.get(g)}) 커버리지"
                records.append(rec)
                idx += 1
                break

    # 2) REVIEW-134 의도적 포함(REVIEW 처분 판단 근거 확보 목적 — 명시적 stratification, 특정 후보군 유불리 목적 아님)
    rng.shuffle(review_usable)
    partners = [c for c in usable]
    for a in review_usable:
        rng.shuffle(partners)
        added = 0
        for b in partners:
            if added >= 1:
                break
            rec = make_pair_record(a, b, idx)
            if rec:
                rec["note"] = "PHASE6 REVIEW 물질 판단 근거 확보용"
                records.append(rec)
                idx += 1
                added += 1
        if len(records) >= TARGET_N * 0.5:
            break

    # 3) 카테고리 균형(Incompatible/Caution/Compatible=hard negative) — wave 편향 없는 무작위쌍
    remaining = TARGET_N - len(records)
    per_cat = max(remaining // 3, 10)
    for cat in ("Incompatible", "Caution", "Compatible"):
        added = 0
        attempts = 0
        while added < per_cat and attempts < per_cat * 30:
            a, b = rng.sample(usable, 2)
            rec = make_pair_record(a, b, idx, category_hint=cat)
            attempts += 1
            if rec:
                rec["note"] = "카테고리 균형표집" + ("(hard negative)" if cat == "Compatible" else "")
                if cat == "Compatible":
                    rec["difficulty"] = "hard_negative"
                else:
                    rec["difficulty"] = "normal"
                records.append(rec)
                idx += 1
                added += 1

    # 4) Group25 — 여전히 DATA_SCARCITY
    records.append({
        "query_id": "indepv2::group25::UNAVAILABLE", "query": None, "kind": "unavailable_group",
        "group_id": 25, "group_name": "Diazonium Salts", "status": "DATA_SCARCITY",
        "note": "PHASE2에서 5종 전부 KOSHA 미등록 확인 — 독립평가에서도 재현 불가",
        "source": "phase7_independent_v2_2026-08-08", "human_verified": False,
        "provenance_tier": "DIAGNOSTIC",
    })

    with open(OUT_NEW_JSONL, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    pair_recs = [r for r in records if r["kind"] == "pair"]
    csv_fields = ["query_id", "query", "cas_a", "name_a", "cas_b", "name_b", "wave_a", "wave_b",
                  "cameo_groups_a", "cameo_groups_b", "gold_risk_pair", "gold_section",
                  "query_style", "contains_exact_name", "contains_exact_cas", "involves_review134",
                  "difficulty", "note", "verification_method", "human_verified", "provenance_tier"]
    with open(OUT_NEW_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=csv_fields, extrasaction="ignore")
        w.writeheader()
        for r in pair_recs:
            row = dict(r)
            row["cameo_groups_a"] = ";".join(map(str, r["cameo_groups_a"]))
            row["cameo_groups_b"] = ";".join(map(str, r["cameo_groups_b"]))
            row["gold_section"] = ";".join(r["gold_section"])
            w.writerow(row)

    print(f"\n=== 신규 독립 평가셋 생성 결과 ===")
    print(f"총 레코드: {len(records)} (pair {len(pair_recs)}건 + group25 stub 1건)")
    print(f"REVIEW-134 관여 쌍: {sum(1 for r in pair_recs if r['involves_review134'])}")
    print(f"category 분포: {dict(Counter(r['gold_risk_pair'] for r in pair_recs))}")
    print(f"query_style 분포: {dict(Counter(r['query_style'] for r in pair_recs))}")
    print(f"wave 조합 분포: {dict(Counter(tuple(sorted((r['wave_a'], r['wave_b']))) for r in pair_recs))}")
    print(f"difficulty 분포: {dict(Counter(r.get('difficulty','normal') for r in pair_recs))}")
    scarce_covered = {g for r in pair_recs for g in r["cameo_groups_a"] + r["cameo_groups_b"] if g in scarce_groups}
    print(f"scarce group 커버: {len(scarce_covered)}/{len(scarce_groups)}")
    print(f"\n산출물: {OUT_NEW_JSONL}\n산출물: {OUT_NEW_CSV}")
    return records


if __name__ == "__main__":
    main()
    generate_new_evalset()
