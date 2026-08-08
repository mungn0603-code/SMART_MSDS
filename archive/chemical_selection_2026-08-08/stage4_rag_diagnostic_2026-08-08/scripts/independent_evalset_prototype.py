# -*- coding: utf-8 -*-
"""
PHASE 4-F — 독립 평가셋 prototype.

기존 gold_pair.jsonl(evalset_pairs.py)은 rag_chunks(197종, Wave1만 청킹됨)에서
파생된다 — Wave2(223종)는 rag_chunks 자체에 존재하지 않아 원천적으로 이 평가셋에
등장할 수 없었다(실측 확인: rag_chunks distinct cas = 197, Wave2 CAS 중 rag_chunks에
있는 것 0개). 이 스크립트는 그 독립성 문제를 깨는 최소 prototype이다 — Wave2/
reactive_basics가 한쪽에 반드시 포함된 쌍만 뽑고, 그 사실 자체로 "Wave1에서 파생됐다"는
낡은 순환을 구조적으로 차단한다.

중요한 발견(이 스크립트 실행 중 확인): Wave2 CAS는 `rag_chunks`에 없으므로
`gold_section`/`gold_item`(청크 ID)을 만들 수 없다 — retrieval_indexed=false로
명시하고 빈 리스트로 둔다. **이건 이 스크립트의 버그가 아니라 RAG 파이프라인
(04_rag_agent/pipeline.py)이 Wave2 확장 이후 재실행된 적이 없다는 실제 blocker**다.
Phase 5 착수 전 pipeline.py를 426(또는 proposed final)종 기준으로 재실행해야
이 prototype이 실제 Hit@K/MRR 평가에 쓰일 수 있다.

원본 CSV/DB 미변경 — 읽기 전용.
"""
import csv
import json
import random
import sqlite3
from collections import defaultdict

from evalset_pairs import pair_verdict  # 매트릭스 판정 로직 재사용(새로 안 만듦)

ROOT = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS"
DB_PATH = ROOT + r"\reactivity_reference.db"
CSV_PATH = ROOT + r"\01_collection\undergrad_target_chemicals.csv"
SOURCE_MAP_WAVE = {
    "curated_curriculum": "wave1", "pool_supplement": "wave1", "pool_topup": "wave1",
    "pool_replacement": "wave1", "pool_replacement_v2": "wave1", "pool_replacement_v3_manual": "wave1",
    "reaction_frequency_high": "wave2",
    "reactive_basics_tier1": "reactive_basics", "reactive_basics_tier2": "reactive_basics",
}

OUT_JSONL = ROOT + r"\04_rag_agent\evalset\independent_eval_prototype_2026-08-08.jsonl"

SEED = 20260808
N_PER_BUCKET = 12  # prototype 규모 — 소규모, 스키마/독립성 검증 목적(전면 확장은 별도 과제)

# Group25(Diazonium Salts) — Phase2에서 KOSHA API로 5종 전부 미등록 재확인
GROUP25_UNAVAILABLE_NOTE = (
    "CAMEO 전체 풀(3,396종) 내 그룹25 화합물은 5종뿐이며, 2026-08-08 Phase2에서 "
    "5종 전부 KOSHA Open API 재조회 결과 미등록으로 확인됨(DATA_SCARCITY). "
    "이 평가셋은 그룹25에 대해 실행 가능한 질의를 만들 수 없다는 사실 자체를 "
    "레코드로 남긴다(조용히 빠뜨리지 않음)."
)


def main():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    with open(CSV_PATH, encoding="utf-8-sig") as f:
        csv_rows = list(csv.DictReader(f))
    source_of = {r["cas_number"]: r["source"] for r in csv_rows}

    section_count = defaultdict(int)
    for cas, cnt in cur.execute("SELECT cas_number, COUNT(DISTINCT section) FROM msds_sections GROUP BY cas_number"):
        section_count[cas] = cnt
    collected = [r["cas_number"] for r in csv_rows if section_count.get(r["cas_number"], 0) == 4]

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

    # rag_chunks 색인 여부(있으면 gold_section 부여, 없으면 retrieval_indexed=false)
    sec_chunks = defaultdict(list)
    indexed_cas = set()
    for chunk_id, cas, section, gran in cur.execute(
        "SELECT chunk_id, cas_number, section, granularity FROM rag_chunks WHERE granularity='section'"
    ):
        sec_chunks[(cas, section)].append(chunk_id)
        indexed_cas.add(cas)
    con.close()

    wave_of = {cas: SOURCE_MAP_WAVE.get(source_of.get(cas, ""), "unknown") for cas in collected}
    collected = [c for c in collected if c in names]

    # 희소그룹(Phase1/2 기준 <=2종, 그룹25 제외) 소속 CAS
    group_member_count = defaultdict(int)
    for cas in collected:
        for g in groups.get(cas, ()):
            group_member_count[g] += 1
    scarce_groups = {g for g, c in group_member_count.items() if 0 < c <= 2 and g != 25}

    rng = random.Random(SEED)

    def make_record(a, b, kind, difficulty, note):
        worst, cats = pair_verdict(groups.get(a, set()), groups.get(b, set()), matrix, self_react)
        gs = []
        for cas in (a, b):
            gs += sec_chunks.get((cas, 2), []) + sec_chunks.get((cas, 10), [])
        retrieval_indexed = (a in indexed_cas) and (b in indexed_cas)
        independence = wave_of[a] != "wave1" or wave_of[b] != "wave1"
        return {
            "query_id": f"indep::{a}::{b}",
            "query": f"{names[a]}와 {names[b]}를 함께 취급해도 되는가? 혼합 시 위험성과 유의사항은?",
            "kind": kind,
            "cas_a": a, "cas_b": b, "name_a": names[a], "name_b": names[b],
            "wave_a": wave_of[a], "wave_b": wave_of[b],
            "cameo_groups_a": sorted(groups.get(a, ())), "cameo_groups_b": sorted(groups.get(b, ())),
            "gold_risk_pair": worst, "gold_risk_pair_all": cats,
            "gold_section": sorted(gs),
            "retrieval_indexed": retrieval_indexed,
            "difficulty": difficulty,
            "source": "independent_eval_prototype_2026-08-08",
            "independence": independence,
            "independence_reason": (
                "wave2/reactive_basics 물질이 최소 한쪽에 포함 — 기존 gold_pair.jsonl(Wave1 파생)과 "
                "무관하게 신규 구성" if independence else
                "양쪽 모두 wave1 — 참고/연속성 비교용(독립 evidence 아님, 별도 표기)"
            ),
            "note": note,
        }

    records = []

    # 1) Wave2/reactive_basics 관여 쌍 — Incompatible/Caution/Compatible(hard negative) 계층 표집
    non_wave1 = [c for c in collected if wave_of[c] != "wave1"]
    buckets = defaultdict(list)
    rng.shuffle(non_wave1)
    other = collected
    for a in non_wave1:
        sample_partners = rng.sample(other, min(40, len(other)))
        for b in sample_partners:
            if a == b:
                continue
            worst, _ = pair_verdict(groups.get(a, set()), groups.get(b, set()), matrix, self_react)
            key = tuple(sorted((a, b)))
            buckets[worst].append(key)
        if sum(len(v) for v in buckets.values()) > 4000:
            break

    for cat, target_n, difficulty in [
        ("Incompatible", N_PER_BUCKET, "normal"),
        ("Caution", N_PER_BUCKET, "normal"),
        ("Compatible", N_PER_BUCKET, "hard_negative"),
    ]:
        pool = list(set(buckets.get(cat, [])))
        rng.shuffle(pool)
        for a, b in pool[:target_n]:
            note = "Wave2 coverage 확보용" if difficulty == "normal" else "hard negative: 정답은 무해(Compatible) — 과잉 위험판정 여부 테스트"
            records.append(make_record(a, b, "pair", difficulty, note))

    # 2) scarce-group 커버리지 — 각 희소그룹에서 최소 1쌍
    covered_scarce = set()
    for g in sorted(scarce_groups):
        members = [c for c in collected if g in groups.get(c, ())]
        if not members:
            continue
        a = members[0]
        partner_pool = [c for c in collected if c != a]
        rng.shuffle(partner_pool)
        b = partner_pool[0]
        records.append(make_record(a, b, "scarce_group_pair", "normal", f"희소그룹 {g}({group_names.get(g)}) 커버리지"))
        covered_scarce.add(g)

    # 3) Group25 — UNAVAILABLE stub(실행 가능한 질의가 아님을 명시)
    records.append({
        "query_id": "indep::group25::UNAVAILABLE",
        "query": None,
        "kind": "unavailable_group",
        "group_id": 25,
        "group_name": "Diazonium Salts",
        "status": "DATA_SCARCITY",
        "note": GROUP25_UNAVAILABLE_NOTE,
        "source": "independent_eval_prototype_2026-08-08",
    })

    with open(OUT_JSONL, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    n_indexed = sum(1 for r in records if r.get("retrieval_indexed"))
    n_wave2_involved = sum(1 for r in records if r.get("wave_a") == "wave2" or r.get("wave_b") == "wave2")
    print(f"총 레코드: {len(records)} (Group25 stub 1건 포함)")
    print(f"Wave2 관여 쌍: {n_wave2_involved}")
    print(f"retrieval_indexed=True(즉시 검색평가 가능): {n_indexed} / {len(records)-1}")
    print(f"희소그룹 커버: {sorted(covered_scarce)} ({len(covered_scarce)}/{len(scarce_groups)})")
    print("출력:", OUT_JSONL)


if __name__ == "__main__":
    main()
