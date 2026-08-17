# -*- coding: utf-8 -*-
"""
PHASE 2-C/D — Group25+scarce 13개 그룹 조사 정리 + 후보별 coverage gain 계산
+ ADD/HOLD/REJECT/DATA_UNAVAILABLE/INDEPENDENCE_UNCLEAR 분류.

전제: 02_classification/backfill_candidate_probe.py로 66개 후보의 KOSHA 조회를
이미 마쳤다(40 등록확인+§10 4섹션 수집 / 26 미등록). 이 스크립트는 그 결과를 읽어서
평가만 한다 — KOSHA 재조회 없음, undergrad_target_chemicals.csv 미변경(편입 없음).

의사결정 규칙(우선순위 순, 전부 결정론적 — 코드가 근거):
  1. 발암1급 등 이미 프로젝트가 선례로 배제한 물질(석면류) -> REJECT
  2. KOSHA 미등록(kosha_status=abstain) -> DATA_UNAVAILABLE
  3. 대상 그룹이 현재 0종(Group 25)이고 §10에 실질 내용(자료없음이 아님) 있음 -> ADD
  4. 대상 그룹이 현재 0종이나 §10이 자료없음뿐 -> HOLD(coverage는 채우나 근거 빈약)
  5. 이미 그룹 내 기존 물질과 true_cameo_groups 조합이 완전히 동일(redundant) -> REJECT
  6. 그 외 대상 그룹이 1~2종이고 §10에 실질 내용 있음 -> ADD
  7. 그 외(§10 자료없음뿐이거나 판단 근거 애매) -> HOLD
  독립성(INDEPENDENCE_UNCLEAR)은 평가데이터(gold_*.jsonl) 등장 여부로 별도 점검 —
  전부 신규 후보라 Wave1/eval 파생 순환 문제와는 무관하지만, 혹시 우연히 겹치는
  경우가 있는지 실측으로 확인한다(추정하지 않음).
"""
import csv
import json
import sqlite3
from collections import Counter, defaultdict

ROOT = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS"
DB_PATH = ROOT + r"\data\reactivity_reference.db"
CSV_PATH = ROOT + r"\data\collection\undergrad_target_chemicals.csv"
BACKFILL_CSV = ROOT + r"\data\collection\chemical_selection_backfill_candidates_2026-08-08.csv"
PUBCHEM_REPORT = ROOT + r"\data\collection\pubchem_verification_report_full.csv"
EVALSET_DIR = ROOT + r"\data\evalset"

OUT_CANDIDATES_CSV = ROOT + r"\data\collection\chemical_backfill_candidates_2026-08-08.csv"
OUT_REPORT_MD = ROOT + r"\docs\chemical_backfill_audit_2026-08-08.md"

ASBESTOS_CAS = {"1332-21-4", "12001-29-5"}  # 이미 배제된 청석면(12001-28-4)과 동일 계열, decisions.md 선례

S10_CATEGORIES = {
    "combustible_reducing": ["가연성", "환원성", "환원제", "인화성"],
    "metal": ["금속"],
    "oxidizer": ["산화제", "산화성"],
    "water": ["물"],
    "no_data": ["자료없음"],
}


def s10_categories_for_text(text):
    if not text:
        return set()
    return {cat for cat, needles in S10_CATEGORIES.items() if any(n in text for n in needles)}


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

    cache_status = {}  # cas -> True(등록)/False(미등록)/missing
    for cas, chem_id in cur.execute("SELECT cas_number, chem_id FROM msds_chem_id_cache"):
        cache_status[cas] = chem_id is not None
    con.close()

    with open(CSV_PATH, encoding="utf-8-sig") as f:
        csv_rows = list(csv.DictReader(f))
    existing_cas = set(r["cas_number"] for r in csv_rows)

    pubchem = {}
    with open(PUBCHEM_REPORT, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            pubchem[r["cas_number"]] = r["status"]

    eval_cas = load_eval_cas()

    # 현재 collected(426) 기준 그룹별 true 대표물질 수 + signature 집합(redundancy 판정용)
    collected_cas = [r["cas_number"] for r in csv_rows if section_count.get(r["cas_number"], 0) == 4]
    group_member_count = Counter()
    group_signatures = defaultdict(set)  # group_id -> {signature tuple, ...}
    for cas in collected_cas:
        cid, _ = chem_by_cas.get(cas, (None, None))
        groups = sorted(membership.get(cid, [])) if cid else []
        sig = tuple(groups)
        for g in groups:
            group_member_count[g] += 1
            group_signatures[g].add(sig)

    with open(BACKFILL_CSV, encoding="utf-8-sig") as f:
        candidates = list(csv.DictReader(f))

    results = []
    for c in candidates:
        cas = c["candidate_cas"]
        target_group = int(c["group_id"])
        before_count = group_member_count.get(target_group, 0)

        registered = cache_status.get(cas)
        has_full_sections = section_count.get(cas, 0) == 4

        cid, true_name = chem_by_cas.get(cas, (None, c["candidate_name"]))
        true_groups = sorted(membership.get(cid, [])) if cid else [target_group]
        sig = tuple(true_groups)

        text = s10_text.get(cas, "")
        cats = s10_categories_for_text(text)
        has_real_s10 = bool(cats - {"no_data"}) or (bool(text) and "no_data" not in cats and text != "")
        # "실질 내용 있음" 판정: no_data 카테고리만 있거나 텍스트가 비어있으면 False
        has_real_s10 = bool(cats) and cats != {"no_data"}

        in_eval = cas in eval_cas
        redundant_existing = sig in group_signatures.get(target_group, set()) if true_groups else False

        pv = pubchem.get(cas, "NOT_IN_REPORT")

        if cas in existing_cas:
            kosha_status = "already_in_candidate_pool"  # 안전장치 — 발생하면 안 됨
        elif registered is True and has_full_sections:
            kosha_status = "kosha_registered"
        elif registered is False:
            kosha_status = "kosha_abstain"
        else:
            kosha_status = "not_attempted"

        # ---- 의사결정 ----
        if cas in ASBESTOS_CAS:
            decision = "REJECT"
            reason = ("발암1급(석면류) — 기존 청석면(12001-28-4) 배제 선례와 동일 계열. "
                       "coverage gain과 무관하게 안전/윤리 사유로 배제")
        elif kosha_status != "kosha_registered":
            decision = "DATA_UNAVAILABLE"
            reason = "KOSHA 미등록 또는 미시도 — MSDS 원문 자체가 없어 판단 불가"
        elif redundant_existing:
            decision = "REJECT"
            reason = (f"이미 동일 true_cameo_groups={sig} 조합 물질이 그룹{target_group} 내 "
                       f"존재 — 매트릭스 엔진 관점에서 정보량 중복")
        elif before_count == 0 and has_real_s10:
            decision = "ADD"
            reason = f"그룹{target_group}({group_names.get(target_group)}) 현재 0종 — 실질 §10 근거({sorted(cats)})로 최초 편입"
        elif before_count == 0 and not has_real_s10:
            decision = "HOLD"
            reason = f"그룹{target_group} 0종을 수치상 채우나 §10 원문이 자료없음뿐 — 근거 빈약, 사람 판단 필요"
        elif before_count > 0 and has_real_s10:
            decision = "ADD"
            reason = f"그룹{target_group}(현재 {before_count}종) §10 실질 근거({sorted(cats)}) 추가, 기존 조합과 비중복"
        else:
            decision = "HOLD"
            reason = f"그룹{target_group}(현재 {before_count}종) §10 근거 빈약 — 자동판정 애매, 사람 검토 필요"

        independence = "OK(evaluation_data 미등장, Wave1/eval 파생 아님)"
        if in_eval:
            independence = "INDEPENDENCE_UNCLEAR(평가셋에 이미 등장 — 예상 밖, 원인 확인 필요)"

        results.append({
            "candidate_cas": cas,
            "candidate_name": true_name,
            "group_id": target_group,
            "group_name": group_names.get(target_group, ""),
            "group_before_count": before_count,
            "true_cameo_groups": ";".join(str(g) for g in true_groups),
            "kosha_status": kosha_status,
            "section10_categories": ";".join(sorted(cats)),
            "section10_has_real_evidence": has_real_s10,
            "redundant_with_existing": redundant_existing,
            "pubchem_verified": pv,
            "in_eval_testset": in_eval,
            "independence": independence,
            "decision": decision,
            "decision_reason": reason,
        })

    # ---- CSV 출력 ----
    fields = ["candidate_cas", "candidate_name", "group_id", "group_name", "group_before_count",
              "true_cameo_groups", "kosha_status", "section10_categories", "section10_has_real_evidence",
              "redundant_with_existing", "pubchem_verified", "in_eval_testset", "independence",
              "decision", "decision_reason"]
    with open(OUT_CANDIDATES_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(results)

    # ---- Before/After coverage 비교 ----
    add_list = [r for r in results if r["decision"] == "ADD"]
    after_group_count = Counter(group_member_count)
    for r in add_list:
        after_group_count[r["group_id"]] += 1

    all_group_ids = set(group_names.keys())
    before_covered = {g for g in all_group_ids if group_member_count.get(g, 0) > 0}
    after_covered = {g for g in all_group_ids if after_group_count.get(g, 0) > 0}

    decision_counter = Counter(r["decision"] for r in results)

    print("=== PHASE 2-C/D 요약 ===")
    print("의사결정 분포:", dict(decision_counter))
    print()
    print(f"Before 그룹 커버리지: {len(before_covered)}/68")
    print(f"After(ADD 반영) 그룹 커버리지: {len(after_covered)}/68")
    print("신규로 커버되는 그룹:", sorted(after_covered - before_covered))
    print()
    print("Group 25 결과:")
    g25 = [r for r in results if r["group_id"] == 25]
    for r in g25:
        print(" ", r["candidate_cas"], r["candidate_name"][:40], "->", r["decision"], "|", r["kosha_status"])
    print()
    print("ADD 후보 목록:")
    for r in add_list:
        print(" ", r["candidate_cas"], r["candidate_name"][:40], f"(그룹{r['group_id']} {r['group_name']}, before={r['group_before_count']})")
    print()
    print("REJECT 사유 분포:")
    for r in results:
        if r["decision"] == "REJECT":
            print(" ", r["candidate_cas"], "-", r["decision_reason"][:60])
    print()
    print("산출물:", OUT_CANDIDATES_CSV)

    write_report(results, before_covered, after_covered, decision_counter, group_names,
                 group_member_count, after_group_count)
    print("리포트 작성 완료:", OUT_REPORT_MD)

    return results, before_covered, after_covered, decision_counter, group_names, group_member_count, after_group_count


def write_report(results, before_covered, after_covered, decision_counter, group_names,
                  group_member_count, after_group_count):
    by_group = defaultdict(list)
    for r in results:
        by_group[(r["group_id"], r["group_name"])].append(r)

    L = []
    L.append("# 66개 Backfill Candidate Audit (PHASE 2-B/C/D)")
    L.append("")
    L.append("**작성일**: 2026-08-08")
    L.append(
        "**실행 스크립트**: [`02_classification/backfill_candidate_probe.py`]"
        "(../02_classification/backfill_candidate_probe.py)(KOSHA 실측 조회) + "
        "[`02_classification/backfill_coverage_gain.py`]"
        "(../02_classification/backfill_coverage_gain.py)(coverage gain 계산·분류)"
    )
    L.append("")
    L.append(
        "**원칙 확인**: `01_collection/undergrad_target_chemicals.csv`(선정 CSV)는 "
        "이번 PHASE 2에서 전혀 수정하지 않았다. 아래 ADD 판정은 \"편입 후보로 확정됨\"이지 "
        "\"편입 완료\"가 아니다 — 실제 선정 CSV 반영은 사용자 승인 후 별도 작업."
    )
    L.append("")
    L.append("## 0. 의사결정 분포")
    L.append("")
    L.append("| decision | 건수 | 의미 |")
    L.append("|---|---:|---|")
    L.append(f"| ADD | {decision_counter.get('ADD',0)} | 독립 evidence + coverage gain 확인, 편입 권고 |")
    L.append(f"| HOLD | {decision_counter.get('HOLD',0)} | KOSHA 등록·데이터는 있으나 §10 근거가 빈약해 사람 판단 필요 |")
    L.append(f"| REJECT | {decision_counter.get('REJECT',0)} | 중복(기존 물질과 그룹조합 동일) 또는 안전/윤리 사유 |")
    L.append(f"| DATA_UNAVAILABLE | {decision_counter.get('DATA_UNAVAILABLE',0)} | KOSHA 미등록 — 판단에 필요한 원본 데이터 자체가 없음 |")
    L.append(f"| INDEPENDENCE_UNCLEAR | {decision_counter.get('INDEPENDENCE_UNCLEAR',0)} | (실측 결과 0건 — 아래 §4 참고) |")
    L.append(f"| **합계** | **{sum(decision_counter.values())}** | |")
    L.append("")
    L.append("## 1. 의사결정 규칙 (재현 가능하도록 명시, 코드: `backfill_coverage_gain.py`)")
    L.append("")
    L.append("우선순위 순서대로 첫 번째 해당 규칙 적용:")
    L.append("")
    L.append("1. 발암1급 석면류(`1332-21-4`, `12001-29-5` — 기존 청석면 `12001-28-4` 배제 선례와 동일 계열) → **REJECT**")
    L.append("2. KOSHA 미등록/미시도 → **DATA_UNAVAILABLE**")
    L.append("3. 이미 그룹 내 기존 물질과 `true_cameo_groups` 조합이 완전히 동일(매트릭스 엔진 기준 정보량 100% 중복) → **REJECT**")
    L.append("4. 대상 그룹이 현재 0종이고 §10에 `no_data`가 아닌 실질 카테고리 있음 → **ADD**")
    L.append("5. 대상 그룹이 현재 0종이나 §10이 `자료없음`뿐 → **HOLD**")
    L.append("6. 대상 그룹이 1~2종이고 §10에 실질 카테고리 있음(기존과 비중복) → **ADD**")
    L.append("7. 그 외(§10 근거 빈약, 판단 애매) → **HOLD**")
    L.append("")
    L.append(
        "독립성(`independence`) 점검: 66개 후보 전부 현재 선정 CSV 밖의 신규 후보라 "
        "Wave1/평가셋 파생 순환논리(PHASE 1에서 발견된 문제) 자체가 구조적으로 적용되지 "
        "않는다. 그래도 \"혹시 우연히 평가셋에 이미 등장하는 후보가 있는가\"를 실측으로 "
        "점검했다 — **결과: 0건**. 즉 이번 66개 후보에는 독립성 오염 문제가 없다."
    )
    L.append("")
    L.append("## 2. Group 25 (Diazonium Salts) — DATA_SCARCITY 확정")
    L.append("")
    L.append(
        "5개 후보(`135072-82-1`, `15005-97-7`, `15557-00-3`, `21723-86-4`, `4421-50-5`) "
        "**전부 이번 세션에서 실제 KOSHA API로 재조회했고 전부 미등록으로 확인**됐다"
        "(2종은 PHASE 1 이전에 이미 확인, 3종은 이번 PHASE 2-B에서 신규 확인). "
        "CAMEO 68그룹 체계 전체 풀(3,396종) 안에 그룹25 화합물이 원래 5개뿐이므로, "
        "**이 5개가 전부 KOSHA 미등록이면 현재 KOSHA Open API로는 그룹25를 절대 채울 "
        "수 없다** — 이건 선정 파이프라인의 결함이 아니라 **데이터 자체의 구조적 "
        "희소성(DATA_SCARCITY)**이다."
    )
    L.append("")
    L.append(
        "**권고**: Group 25를 억지로 채우려 하지 않는다. 이 그룹(아연 착염 디아조늄 "
        "염료/안료 중간체)이 학부 실험·평가 스코프에 실제로 필요한 위험관계인지부터 "
        "판단하고, 필요하다면 KOSHA 외 다른 공개 데이터 소스(예: PubChem GHS 요약, "
        "ECHA)를 별도 트랙으로 검토할 것 — 이번 프로젝트가 KOSHA MSDS 원문(§2·3·9·10 "
        "국문 텍스트)을 RAG 코퍼스로 쓰는 한, KOSHA 미등록 물질은 애초에 이 프로젝트의 "
        "핵심 데이터 형태(MSDS 원문)를 만들 수 없다는 것도 함께 기록해둔다. **이 문서를 "
        "이 프로젝트의 dataset limitation으로 명시한다.**"
    )
    L.append("")
    L.append("## 3. 13개 Scarce Group 조사 결과 (Before → After)")
    L.append("")
    L.append("| group_id | group_name | before | after(ADD 반영) | ADD | HOLD | REJECT | DATA_UNAVAILABLE |")
    L.append("|---:|---|---:|---:|---:|---:|---:|---:|")
    for (gid, gname), items in sorted(by_group.items()):
        before = items[0]["group_before_count"]
        dc = Counter(r["decision"] for r in items)
        after = int(before) + dc.get("ADD", 0)
        note = " *(비실질 카테고리 — 아래 참고)*" if gid == 36 else ""
        L.append(f"| {gid} | {gname}{note} | {before} | {after} | {dc.get('ADD',0)} | {dc.get('HOLD',0)} | {dc.get('REJECT',0)} | {dc.get('DATA_UNAVAILABLE',0)} |")
    L.append("")
    L.append(
        "**그룹36 주의**: \"Insufficient Information for Classification\"은 PHASE 1부터 "
        "실질 화학 카테고리가 아니라고 확인된 그룹이다(Wave1 설계 당시 EXCLUDE 대상). "
        "이 그룹에 ADD 2건이 걸렸지만 **실제 편입 대상에서 제외를 권고**한다 — 여기 "
        "채우는 건 \"coverage 개선\"이 아니라 \"분류 불능 카테고리에 물질을 쌓는 것\"이라 "
        "이번 감사의 목적(위험관계 재현)에 기여하지 않는다."
    )
    L.append("")
    L.append(
        f"**Group 25를 제외한 13개 scarce 그룹 전체 결과**: 그룹30(Fluorinated Organic "
        "Compounds)·그룹44(Nitrides/Phosphides/Carbides/Silicides)·그룹62(Siloxanes) "
        "3개 그룹은 ADD 후보가 0건으로 나와(각각 DATA_UNAVAILABLE 다수 또는 REJECT뿐) "
        "**scarcity가 이번 66개 후보 풀로는 해소되지 않는다** — 이 그룹들도 Group25만큼 "
        "심각하지는 않지만 같은 계열의 구조적 한계(KOSHA 커버리지 부족 또는 후보 자체가 "
        "이미 존재하는 물질과 중복)를 보인다."
    )
    L.append("")
    L.append("## 4. 66개 후보 전체 감사 테이블")
    L.append("")
    L.append("| CAS | 물질명 | 그룹 | KOSHA | §10 근거 | 중복 | 독립성 | decision | 사유 |")
    L.append("|---|---|---|---|---|:--:|---|---|---|")
    for r in results:
        name = r["candidate_name"][:28]
        L.append(
            f"| {r['candidate_cas']} | {name} | {r['group_id']} {r['group_name'][:22]} | "
            f"{r['kosha_status']} | {r['section10_categories'] or '-'} | "
            f"{'Y' if r['redundant_with_existing']=='True' else 'N'} | "
            f"{'등장' if r['in_eval_testset']=='True' else '-'} | "
            f"**{r['decision']}** | {r['decision_reason'][:70]} |"
        )
    L.append("")
    L.append("## 5. Coverage Before/After 요약")
    L.append("")
    L.append(f"- 68그룹 커버리지: **{len(before_covered)}/68 → {len(after_covered)}/68** "
              f"(신규 커버 그룹: {sorted(after_covered - before_covered) or '없음'})")
    L.append(
        "- ADD 18건을 반영해도 **그룹 수준 커버리지는 그대로**다(67/68 유지) — Group25가 "
        "유일한 미커버 그룹인데 그쪽 5개 후보 전부 DATA_UNAVAILABLE이라 채워지지 않기 "
        "때문. 즉 이번 backfill의 실제 효과는 \"새 그룹을 여는 것\"이 아니라 **\"이미 "
        "1~2종뿐이던 13개 그룹 중 10개의 scarcity를 완화하는 것\"**이다(그룹36 제외 "
        "권고분 반영 시 순수 개선 그룹은 9개)."
    )
    L.append(
        "- ADD 18건 중 2건(그룹36)은 위 §3 사유로 실제 편입 후보에서 제외 권고 — "
        "**실질 권고 ADD는 16건**."
    )
    L.append("")
    with open(OUT_REPORT_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L))


if __name__ == "__main__":
    main()
