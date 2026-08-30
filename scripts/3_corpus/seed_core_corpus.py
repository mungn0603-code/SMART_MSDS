"""corpus_tag='core' 시딩: substance_registry의 Core 후보 중 RAG+CAMEO가 둘 다
갖춰진 것만 rag_corpus_membership에 편입한다.

왜 별도 태그인가(2026-08-17 사용자 결정): corpus_tag='173'은 Retrieval/Generation
평가가 측정된 **고정 코퍼스**라 건드리지 않는다. 기본 물질은 별도 'core' 태그로
추가하고, 서비스/데모 검색만 '173 + core'를 함께 로드한다.

주의: substance_registry에 있다고 전부 여기 편입되는 게 아니다(Registry = RAG
후보라는 뜻이 아님). Registry는 식별 축, corpus 편입은 RAG 축 - 아래 4개
범주로 나눠 무엇이 왜 빠졌는지 전부 보고한다(침묵 금지).

  python scripts/seed_core_corpus.py            # 점검만(변경 없음)
  python scripts/seed_core_corpus.py --write    # rag_corpus_membership에 반영
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "reactivity_reference.db"
CORPUS_TAG = "core"


def audit(con: sqlite3.Connection) -> list[dict]:
    cas_rows = con.execute(
        "select cas_number, name_ko from substance_registry where core_category is not null"
    ).fetchall()

    rows = []
    for cas, label in cas_rows:
        n_chunk = con.execute(
            "select count(*) from rag_chunks where cas_number=? and section in (2,10) and status='active'",
            (cas,),
        ).fetchone()[0]
        n_group = con.execute(
            "select count(*) from chemical_group_membership m "
            "join chemicals c on c.chemical_id = m.chemical_id where c.cas_number=?",
            (cas,),
        ).fetchone()[0]
        in_173 = con.execute(
            "select 1 from rag_corpus_membership where corpus_tag='173' and cas_number=?", (cas,)
        ).fetchone() is not None
        rows.append({"cas": cas, "label": label, "chunks": n_chunk, "groups": n_group, "in_173": in_173})
    return rows


def categorize(rows: list[dict]) -> dict[str, list[dict]]:
    cats: dict[str, list[dict]] = {"편입 성공": [], "RAG 없음": [], "CAMEO 없음": [], "둘 다 없음": [], "173 중복": []}
    for r in rows:
        if r["in_173"]:
            cats["173 중복"].append(r)
        elif r["chunks"] > 0 and r["groups"] > 0:
            cats["편입 성공"].append(r)
        elif r["chunks"] == 0 and r["groups"] == 0:
            cats["둘 다 없음"].append(r)
        elif r["chunks"] == 0:
            cats["RAG 없음"].append(r)
        else:
            cats["CAMEO 없음"].append(r)
    return cats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="실제로 rag_corpus_membership에 반영")
    args = ap.parse_args()

    con = sqlite3.connect(DB_PATH)
    rows = audit(con)
    cats = categorize(rows)

    for name, items in cats.items():
        print(f"\n[{name}] {len(items)}종")
        for r in items:
            print(f"  {r['label']:12s} {r['cas']:12s} §2/10청크={r['chunks']:2d} CAMEO그룹={r['groups']:2d}")

    to_add = cats["편입 성공"]
    if args.write:
        con.executemany(
            "insert or ignore into rag_corpus_membership (corpus_tag, cas_number) values (?, ?)",
            [(CORPUS_TAG, r["cas"]) for r in to_add],
        )
        con.commit()
        count = "select count(*) from rag_corpus_membership where corpus_tag=?"
        n_core = con.execute(count, (CORPUS_TAG,)).fetchone()[0]
        n_173 = con.execute(count, ("173",)).fetchone()[0]
        print(f"\ncorpus_tag='{CORPUS_TAG}' 총 {n_core}종 / '173'은 {n_173}종(불변)")
    else:
        print(f"\n점검만 수행(변경 없음). 반영하려면 --write")
    con.close()


if __name__ == "__main__":
    main()
