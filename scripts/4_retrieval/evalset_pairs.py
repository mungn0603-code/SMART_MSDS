"""Stage 4 평가셋 (제품 과제): 물질 '쌍'의 반응성·양립성 판정용 Retrieval gold set

왜 이 파일이 생겼는가 (2026-08-06)
  최초 `evalset.py`는 "아세톤의 인화점은?" 같은 **단일물질 사실조회** 질의를 만들었다.
  그건 이 시스템의 과제가 아니다. 목표 스코프는 사용자가 물질 **2종 이상**을
  입력하고 그것들을 함께 취급할 때의 위험성과 유의사항을 받는 것이다(N종 판정은
  가능한 모든 쌍을 판정해 worst-case로 종합하는 방식으로 확장 예정 — 이미
  `compatibility_engine.py`가 다중 그룹 물질에 이 패턴을 쓰고 있다). 이 평가셋은
  그 최소 단위인 **쌍(2종)** 을 먼저 검증하는 것이며, N종 확장판 자체는 아니다.
  `evalset.py`는 폐기하지 않고 '검색기 부품 점검용'으로 남긴다(물질·항목을 제대로
  찾아내는지 확인하는 하위 테스트).

정답(gold) 정의 — 판단이 아니라 고정 스키마
  쌍 (A,B)에 대해 반드시 참조해야 하는 MSDS 근거:
    A의 §10, B의 §10  (안정성 및 반응성 — 피해야 할 물질/조건, 유해반응 가능성)
    A의 §2,  B의 §2   (유해성·위험성 분류 — 산화성/인화성/자기반응성 등 반응유형 근거)
  섹션이 분할된 경우 그 섹션의 모든 part를 정답으로 인정한다(근거가 나뉘어 들어감).
  §9(물리화학적 특성)는 화재·폭발 위험의 정량화에는 쓰이나 '두 물질이 반응하는가'의
  1차 근거가 아니므로 gold에서 제외. §3(구성성분)도 제외.

비협상 원칙과의 관계
  CAMEO 양립성 매트릭스 판정은 이 검색 경로에 넣지 않는다. 매트릭스는 SQLite에서
  결정론적으로 조회되는 **별도 신호**이고, 위 MSDS 근거로 교차검증되어야 한다.
  (원칙 1: 매트릭스 조회 결과 단독 최종판정 금지 — 그래서 RAG가 필요한 것)
  매트릭스 판정값은 참고용으로 레코드에 함께 저장하되 정답 근거가 아니다.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "reactivity_reference.db"
OUT_DIR = ROOT / "data" / "evalset"

PER_CATEGORY_DEFAULT = 150
GOLD_SECTIONS = (2, 10)
CORPUS_TAG_DEFAULT = "173"  # docs/chemical_selection_final_2026-08-08.md 확정 코퍼스

CATEGORY_RANK = {"Incompatible": 3, "Caution": 2, "Compatible": 1, "Unknown": 0}

# Gold Evidence 재정의(docs/HANDOFF.md §0-3 STEP 2, 2026-08-08) 코드화 — 2026-08-29
#   §2  GHS 분류 블록  -> 항상 gold (HAZARD_CLASSIFICATION)
#   §10 "피해야 할 물질" 블록 -> 코퍼스 안에서 2회 이상 반복되면 BOILERPLATE(제외),
#       1회만 등장하면 REVIEW_REQUIRED(제외 — 억지 해석하지 않는다)
#   블록이 비었거나 "자료없음" -> NO_DIRECT_MSDS_EVIDENCE(제외)
# 결과적으로 gold_evidence는 100% §2다. 이 규칙은 --corpus-tag 173 재생성으로
# archive/2026-08-17_baseline/evalset/gold_pair.jsonl 8,700슬롯 전건 재현을 확인했다.
EVIDENCE_HEADINGS = {2: "## 유해성·위험성 분류", 10: "## 피해야 할 물질"}
NODATA = "자료없음"
# §10 "분리 그룹(segregation group)" 값이 빈 채로 파싱된 청크(pipeline.py 서브필드
# 파서 결함, 2026-08-08 발견). evidence 판정에는 영향 없고 기록만 남긴다.
PARSING_DEFECT_SUFFIX = "분리 그룹(segregation group) :"
BOILERPLATE_MIN_REPEAT = 2


def _heading_block(text: str, heading: str) -> str:
    """청크 본문에서 heading 바로 아래 블록만 잘라낸다(다음 '#' 헤딩 전까지)."""
    lines = text.split("\n")
    try:
        i = lines.index(heading)
    except ValueError:
        return ""
    out = []
    for ln in lines[i + 1:]:
        if ln.startswith("#"):
            break
        out.append(ln)
    return "\n".join(out).strip()

QUERY_TEMPLATES = [
    "{a}, {b} 두 물질을 함께 취급해도 되는가? 혼합 시 위험성과 유의사항은?",
    "{a}와 {b}를 같이 보관해도 안전한가요?",
    "{a}와 {b}가 접촉하면 위험한가요?",
    "{a}와 {b}는 반응할 가능성이 있나요?",
    "{a}와 {b}를 분리해서 보관해야 하나요?",
]
# 5개 중 4개("취급"/"혼합"/"위험성" 미포함, 3번만 "위험" 일부 중복)는 어휘 편향 검증용.
# 근거: docs/retrieval_query_diversity_review_2026-08-07.md §4·§7


def load(con: sqlite3.Connection, corpus_tag: str = CORPUS_TAG_DEFAULT):
    cur = con.cursor()
    if corpus_tag:
        cas_list = [r[0] for r in cur.execute(
            "select distinct rc.cas_number from rag_chunks rc "
            "join rag_corpus_membership m on m.cas_number = rc.cas_number and m.corpus_tag = ? "
            "order by rc.cas_number", (corpus_tag,)
        )]
    else:
        cas_list = [r[0] for r in cur.execute("select distinct cas_number from rag_chunks order by cas_number")]
    names = dict(
        cur.execute(
            "select cas_number, chemical_name from rag_chunks group by cas_number"
        ).fetchall()
    )
    groups: dict[str, set[int]] = defaultdict(set)
    for cas, gid in cur.execute(
        "select ch.cas_number, m.group_id from chemicals ch "
        "join chemical_group_membership m on m.chemical_id = ch.chemical_id"
    ):
        groups[cas].add(gid)
    matrix = {
        (a, b): cat
        for a, b, cat in cur.execute(
            "select group_a_id, group_b_id, category from compatibility_pairs"
        )
    }
    self_react = dict(cur.execute("select group_id, category from self_reactivity").fetchall())

    # 섹션 -> 그 섹션의 모든 청크 id (분할 part 포함)
    sec_chunks: dict[tuple[str, int], list[str]] = defaultdict(list)
    item_chunks: dict[tuple[str, int], list[str]] = defaultdict(list)
    sec_texts: dict[str, str] = {}
    for chunk_id, cas, section, gran, text in cur.execute(
        "select chunk_id, cas_number, section, granularity, text from rag_chunks"
    ):
        (sec_chunks if gran == "section" else item_chunks)[(cas, section)].append(chunk_id)
        if gran == "section":
            sec_texts[chunk_id] = text

    return cas_list, names, groups, matrix, self_react, sec_chunks, item_chunks, sec_texts


def pick_evidence_chunk(sec_chunks, sec_texts, cas: str, section: int) -> tuple[str | None, str]:
    """(chunk_id, 근거 블록). 섹션이 분할된 경우 블록 내용이 실제로 들어있는 첫 part."""
    cands = sorted(sec_chunks.get((cas, section), []))
    head = EVIDENCE_HEADINGS[section]
    for cid in cands:
        block = _heading_block(sec_texts.get(cid, ""), head)
        if block:
            return cid, block
    return (cands[0] if cands else None), ""


def boilerplate_values(cas_list, sec_chunks, sec_texts) -> set[str]:
    """코퍼스 안에서 2회 이상 그대로 반복되는 §10 '피해야 할 물질' 문구."""
    freq = Counter()
    for cas in cas_list:
        _, block = pick_evidence_chunk(sec_chunks, sec_texts, cas, 10)
        if block and block != NODATA:
            freq[block] += 1
    return {v for v, n in freq.items() if n >= BOILERPLATE_MIN_REPEAT}


def classify_evidence(sec_chunks, sec_texts, boilerplate: set[str], cas: str, section: int) -> dict:
    """슬롯 1개(물질×섹션)의 evidence 판정. gold 여부는 HAZARD_CLASSIFICATION만."""
    cid, block = pick_evidence_chunk(sec_chunks, sec_texts, cas, section)
    if not block or block == NODATA:
        etype, block = "NO_DIRECT_MSDS_EVIDENCE", None
    elif section == 2:
        etype = "HAZARD_CLASSIFICATION"
    else:
        etype = "BOILERPLATE" if block in boilerplate else "REVIEW_REQUIRED"
    rec = {"chunk_id": cid, "section": section, "evidence_type": etype, "gold_evidence_text": block}
    if section == 10:
        rec["note"] = "PARSING_DEFECT" if block and any(
            ln.rstrip().endswith(PARSING_DEFECT_SUFFIX) for ln in block.split("\n")
        ) else None
    return rec


def pair_verdict(ga: set[int], gb: set[int], matrix: dict, self_react: dict) -> tuple[str, list[str]]:
    """그룹 조합별 판정을 모아 최악값을 대표로. 참고용이며 정답 근거가 아니다."""
    cats = set()
    for x in ga:
        for y in gb:
            if x == y:
                cats.add(self_react.get(x, "Unknown"))
            else:
                cats.add(matrix.get((min(x, y), max(x, y)), "Unknown"))
    if not cats:
        return "Unknown", []
    worst = max(cats, key=lambda c: CATEGORY_RANK[c])
    return worst, sorted(cats)


def build(con: sqlite3.Connection, per_cat: int, corpus_tag: str = CORPUS_TAG_DEFAULT):
    cas_list, names, groups, matrix, self_react, sec_chunks, item_chunks, sec_texts = load(con, corpus_tag)
    boilerplate = boilerplate_values(cas_list, sec_chunks, sec_texts)
    slots = {(cas, sec): classify_evidence(sec_chunks, sec_texts, boilerplate, cas, sec)
             for cas in cas_list for sec in GOLD_SECTIONS}

    buckets: dict[str, list] = defaultdict(list)
    for a, b in itertools.combinations(cas_list, 2):
        worst, cats = pair_verdict(groups.get(a, set()), groups.get(b, set()), matrix, self_react)
        buckets[worst].append((a, b, worst, cats))

    gold = []
    for cat in sorted(buckets, key=lambda c: -CATEGORY_RANK[c]):
        # 2026-08-29: rng.sample -> 쌍 자체의 해시 정렬. rng.sample은 pool 구성 전체에
        # 의존해서, chemical_group_membership 2행이 바뀌자 450쌍 중 33쌍만 살아남았다
        # (유지율 7.3%). 해시 정렬은 실제로 버킷이 바뀐 쌍만 교체한다(실측 95.8%).
        pool = sorted(buckets[cat], key=lambda t: hashlib.blake2b(
            f"{t[0]}::{t[1]}".encode(), digest_size=8).digest())
        for a, b, worst, cats in pool[:per_cat]:
            gs, gi, detail = [], [], []
            for label, cas in (("A", a), ("B", b)):
                for sec in GOLD_SECTIONS:
                    gs += sec_chunks.get((cas, sec), [])
                    gi += item_chunks.get((cas, sec), [])
                    d = slots[(cas, sec)]
                    detail.append({"chunk_id": d["chunk_id"], "label": label, **{
                        k: d[k] for k in ("section", "evidence_type", "gold_evidence_text")},
                        **({"note": d["note"]} if sec == 10 else {})})
            evidence = sorted(d["chunk_id"] for d in detail
                              if d["evidence_type"] == "HAZARD_CLASSIFICATION")
            for ti, tpl in enumerate(QUERY_TEMPLATES):
                rec = {
                    "query_id": f"pair::{a}::{b}::t{ti}",
                    "query": tpl.format(a=names[a], b=names[b]),
                    "template_idx": ti,
                    "kind": "pair",
                    "cas_a": a,
                    "cas_b": b,
                    "name_a": names[a],
                    "name_b": names[b],
                    "matrix_verdict": worst,
                    "matrix_verdicts_all": ",".join(cats),
                    "cameo_groups_a": ",".join(map(str, sorted(groups.get(a, ())))),
                    "cameo_groups_b": ",".join(map(str, sorted(groups.get(b, ())))),
                    "gold_section": sorted(gs),
                    "gold_item": sorted(gi),
                    "gold_evidence": evidence,
                    "evidence_count": len(evidence),
                    "evidence_detail": detail,
                }
                gold.append(rec)
    return gold, buckets, slots


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-category", type=int, default=PER_CATEGORY_DEFAULT)
    ap.add_argument("--corpus-tag", default=CORPUS_TAG_DEFAULT,
                     help="rag_corpus_membership 태그(기본: 173 = 확정 코퍼스). 빈 문자열이면 rag_chunks 전체(하위호환)")
    ap.add_argument("--db", type=Path, default=DB_PATH,
                     help="SQLite 경로(기본: data/reactivity_reference.db). 과거 DB로 재현 대조할 때만 바꾼다")
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR,
                     help="출력 디렉터리(기본: data/evalset). 재현 대조용으로만 바꾼다")
    args = ap.parse_args()

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(args.db)
    gold, buckets, slots = build(con, args.per_category, args.corpus_tag)
    con.close()

    with (out_dir / "gold_pair.jsonl").open("w", encoding="utf-8") as f:
        for rec in gold:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    n_tpl = len(QUERY_TEMPLATES)
    print("전체 쌍 분포:", {k: len(v) for k, v in buckets.items()})
    print(f"표본 추출: 카테고리당 최대 {args.per_category}쌍 x 템플릿 {n_tpl}개")
    print(f"  Retrieval gold: 쌍 {len(gold)//n_tpl}개 x 질의 {len(gold)}건  "
          f"{dict(Counter(g['matrix_verdict'] for g in gold[::n_tpl]))}")
    if gold:
        n = [len(g["gold_section"]) for g in gold]
        m = [len(g["gold_item"]) for g in gold]
        print(f"  쌍당 정답청크 section: min {min(n)} / 최빈 {Counter(n).most_common(1)[0]}")
        print(f"  쌍당 정답청크 item   : min {min(m)} / 최빈 {Counter(m).most_common(1)[0]}")
    audit(gold, slots)
    print(f"출력: {out_dir}")


def audit(records: list[dict], slots: dict) -> None:
    """gold_evidence 생성 결과 감사 — 규칙과 어긋난 사례가 있으면 그대로 드러낸다."""
    det = [d for r in records for d in r["evidence_detail"]]
    print("\n[audit] evidence_type 분포(슬롯 %d건):" % len(det),
          dict(Counter(d["evidence_type"] for d in det)))
    print("[audit] 물질×섹션 슬롯 판정:", dict(Counter(
        (s, d["evidence_type"]) for (_, s), d in slots.items())))
    print("[audit] 질의당 evidence 개수:", dict(sorted(
        Counter(r["evidence_count"] for r in records).items())))
    sec = Counter(d["section"] for d in det if d["evidence_type"] == "HAZARD_CLASSIFICATION")
    print(f"[audit] gold_evidence 섹션 분포: {dict(sec)}"
          f"  (§2 비율 {sec[2] / max(sum(sec.values()), 1):.4f})")
    print("[audit] PARSING_DEFECT 슬롯:", sum(1 for d in det if d.get("note") == "PARSING_DEFECT"),
          "/ 물질:", sorted({d["chunk_id"] for d in det if d.get("note") == "PARSING_DEFECT"}))
    bad = [(d["chunk_id"], d["evidence_type"]) for d in det
           if (d["evidence_type"] == "HAZARD_CLASSIFICATION") != (
               d["section"] == 2 and d["gold_evidence_text"] is not None)
           or (d["gold_evidence_text"] is None) != (d["evidence_type"] == "NO_DIRECT_MSDS_EVIDENCE")]
    print("[audit] 규칙 불일치:", len(bad), sorted(set(bad))[:10])
    n_no = sum(1 for r in records if not r["gold_evidence"])
    print(f"[audit] gold_evidence 없는 질의: {n_no}/{len(records)}"
          f"  (§2가 양쪽 다 자료없음 -> 채점 대상에서 빠짐)")


if __name__ == "__main__":
    main()
