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
import itertools
import json
import random
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "reactivity_reference.db"
OUT_DIR = Path(__file__).resolve().parent / "evalset"

SEED = 42
PER_CATEGORY_DEFAULT = 150
GOLD_SECTIONS = (2, 10)
CORPUS_TAG_DEFAULT = "173"  # docs/chemical_selection_final_2026-08-08.md 확정 코퍼스

CATEGORY_RANK = {"Incompatible": 3, "Caution": 2, "Compatible": 1, "Unknown": 0}

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
    for chunk_id, cas, section, gran in cur.execute(
        "select chunk_id, cas_number, section, granularity from rag_chunks"
    ):
        (sec_chunks if gran == "section" else item_chunks)[(cas, section)].append(chunk_id)

    # J08(피해야 할 물질) 자료없음 여부 — Abstain 판단 신호
    j08_nodata = {
        cas
        for (cas,) in cur.execute(
            "select cas_number from rag_chunks "
            "where granularity='item' and item_codes='J08' and abstain=1"
        )
    }
    return cas_list, names, groups, matrix, self_react, sec_chunks, item_chunks, j08_nodata


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
    cas_list, names, groups, matrix, self_react, sec_chunks, item_chunks, j08_nodata = load(con, corpus_tag)
    rng = random.Random(SEED)

    buckets: dict[str, list] = defaultdict(list)
    for a, b in itertools.combinations(cas_list, 2):
        worst, cats = pair_verdict(groups.get(a, set()), groups.get(b, set()), matrix, self_react)
        buckets[worst].append((a, b, worst, cats))

    gold, abstain = [], []
    for cat in sorted(buckets, key=lambda c: -CATEGORY_RANK[c]):
        pool = buckets[cat]
        for a, b, worst, cats in rng.sample(pool, min(per_cat, len(pool))):
            gs, gi = [], []
            for cas in (a, b):
                for sec in GOLD_SECTIONS:
                    gs += sec_chunks.get((cas, sec), [])
                    gi += item_chunks.get((cas, sec), [])
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
                    # 양쪽 다 '피해야 할 물질' 자료없음 -> 물질 특정 근거 없이 그룹 근거만 남음
                    # -> 원칙 1(매트릭스 단독판정 금지)에 의해 Abstain 대상
                    "both_j08_nodata": int(a in j08_nodata and b in j08_nodata),
                }
                (abstain if rec["both_j08_nodata"] else gold).append(rec)
    return gold, abstain, buckets


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-category", type=int, default=PER_CATEGORY_DEFAULT)
    ap.add_argument("--corpus-tag", default=CORPUS_TAG_DEFAULT,
                     help="rag_corpus_membership 태그(기본: 173 = 확정 코퍼스). 빈 문자열이면 rag_chunks 전체(하위호환)")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    gold, abstain, buckets = build(con, args.per_category, args.corpus_tag)
    con.close()

    for name, data in (("gold_pair", gold), ("gold_pair_abstain", abstain)):
        with (OUT_DIR / f"{name}.jsonl").open("w", encoding="utf-8") as f:
            for rec in data:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    n_tpl = len(QUERY_TEMPLATES)
    print("전체 쌍 분포:", {k: len(v) for k, v in buckets.items()})
    print(f"표본 추출: 카테고리당 최대 {args.per_category}쌍 x 템플릿 {n_tpl}개")
    print(f"  Retrieval gold: 쌍 {len(gold)//n_tpl}개 x 질의 {len(gold)}건  "
          f"{dict(Counter(g['matrix_verdict'] for g in gold[::n_tpl]))}")
    print(f"  Abstain       : 쌍 {len(abstain)//n_tpl if abstain else 0}개 x 질의 {len(abstain)}건 (양쪽 J08 자료없음)")
    if gold:
        n = [len(g["gold_section"]) for g in gold]
        m = [len(g["gold_item"]) for g in gold]
        print(f"  쌍당 정답청크 section: min {min(n)} / 최빈 {Counter(n).most_common(1)[0]}")
        print(f"  쌍당 정답청크 item   : min {min(m)} / 최빈 {Counter(m).most_common(1)[0]}")
    print(f"출력: {OUT_DIR}")


if __name__ == "__main__":
    main()
