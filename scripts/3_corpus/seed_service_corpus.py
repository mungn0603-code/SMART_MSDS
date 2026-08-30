# -*- coding: utf-8 -*-
"""서비스 범위 정의: substance_status VIEW 생성 + corpus_tag='service' 시딩.

2026-08-28 결정 — 서비스 검색 대상은 `corpus_tag='service'` 하나다.
`'173'`(평가 재현용 고정 코퍼스)과 `'core'`(그 확장분)는 **보존만** 하고
서비스 경로에서 참조하지 않는다.

## 계층 (사용자 확정 구조)

    Registry 등록
      -> KOSHA MSDS 확보
      -> CAMEO 매핑
      -> service_eligible          (여기까지가 '원천 데이터 자격')
      -> corpus/chunk 생성
      -> chunks_ready              (자격의 결과가 실제 검색 가능한지 검증)

`chunks_ready`를 `service_eligible`의 조건에 넣지 않는 이유: 넣으면 청킹 실패가
"서비스 불가 물질"로 둔갑한다. 분리해 두면 `service_eligible=1 & chunks_ready=0`이
곧 **인덱스 결손(버그)** 신호가 된다 - `index_status`가 그 상태를 이름으로 드러낸다.

## 왜 플래그 컬럼이 아니라 VIEW인가

docs/REGISTRY.md 1절: 가용성 플래그를 substance_registry에 저장하지 않는다.
저장하면 두 곳이 어긋나고, 어긋난 순간 "등록됐으니 판정 가능하다"는 잘못된 전제가
파이프라인에 들어온다. VIEW는 조회 시점에 계산되므로 어긋날 수 없다.
물질 수(173 등)를 코드에 하드코딩하지 않는 것도 같은 이유다.

    python scripts/seed_service_corpus.py            # 점검만(변경 없음)
    python scripts/seed_service_corpus.py --write    # VIEW 생성 + service 태그 반영
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "reactivity_reference.db"

SERVICE_CORPUS_TAG = "service"

# MSDS 상세 확보의 정의: 이 4개 섹션이 전부 있어야 한다(docs/REGISTRY.md 6절).
MSDS_SECTIONS = (2, 3, 9, 10)
# 검색 근거로 쓰는 섹션(gold_evidence는 전량 §2, §10은 boilerplate penalty 대상).
CHUNK_SECTIONS = (2, 10)

VIEW_DDL = """
DROP VIEW IF EXISTS substance_status;
CREATE VIEW substance_status AS
WITH base AS (
    -- Registry 물질 + 현행 태그('173'/'core'/'service')에 속한 물질.
    -- 폐기된 실험 코퍼스 태그(426/259proposed/phase*)는 제외한다 - 그 물질들은
    -- 현재 어느 경로에도 쓰이지 않고, 넣으면 legacy 집계가 실험 이력으로 오염된다.
    SELECT cas_number FROM substance_registry
    UNION
    SELECT cas_number FROM rag_corpus_membership
     WHERE corpus_tag IN ('173', 'core', 'service')
),
kosha AS (
    SELECT cas_number FROM msds_chem_id_cache WHERE IFNULL(chem_id, '') <> ''
),
msds AS (
    SELECT cas_number FROM msds_sections
     WHERE section IN (2, 3, 9, 10)
     GROUP BY cas_number
    HAVING COUNT(DISTINCT section) = 4
),
cameo AS (
    SELECT c.cas_number,
           GROUP_CONCAT(rg.group_name, ' | ') AS group_names,
           COUNT(*)                           AS n_groups
      FROM chemicals c
      JOIN chemical_group_membership m ON m.chemical_id = c.chemical_id
      JOIN reactivity_groups rg        ON rg.group_id   = m.group_id
     GROUP BY c.cas_number
),
chunks AS (
    SELECT cas_number, COUNT(*) AS n_chunks
      FROM rag_chunks
     WHERE section IN (2, 10) AND status = 'active'
     GROUP BY cas_number
),
membership AS (
    SELECT cas_number, GROUP_CONCAT(corpus_tag, ',') AS tags
      FROM rag_corpus_membership
     GROUP BY cas_number
),
chunk_name AS (
    SELECT cas_number, MIN(chemical_name) AS name_fallback
      FROM rag_chunks GROUP BY cas_number
)
SELECT
    b.cas_number,
    COALESCE(r.name_ko, n.name_fallback)                        AS name_ko,
    r.name_en,
    r.formula,
    r.aliases,
    r.core_category,
    CASE WHEN r.cas_number IS NOT NULL THEN 1 ELSE 0 END        AS in_registry,
    CASE WHEN k.cas_number IS NOT NULL THEN 1 ELSE 0 END        AS kosha_listed,
    CASE WHEN s.cas_number IS NOT NULL THEN 1 ELSE 0 END        AS msds_complete,
    CASE WHEN g.cas_number IS NOT NULL THEN 1 ELSE 0 END        AS cameo_matched,
    g.group_names                                               AS cameo_groups,
    CASE
        WHEN r.cas_number IS NOT NULL
         AND k.cas_number IS NOT NULL
         AND s.cas_number IS NOT NULL
         AND g.cas_number IS NOT NULL THEN 1 ELSE 0
    END                                                         AS service_eligible,
    CASE WHEN ch.cas_number IS NOT NULL THEN 1 ELSE 0 END       AS chunks_ready,
    IFNULL(ch.n_chunks, 0)                                      AS n_chunks,
    IFNULL(mb.tags, '')                                         AS corpus_membership,
    CASE WHEN r.cas_number IS NULL AND mb.tags IS NOT NULL
         THEN 1 ELSE 0 END                                      AS legacy_only,
    CASE
        WHEN r.cas_number IS NULL THEN 'Registry 미등록(legacy 코퍼스 전용)'
        WHEN k.cas_number IS NULL THEN 'KOSHA 미등재'
        WHEN s.cas_number IS NULL THEN 'MSDS 섹션 미비'
        WHEN g.cas_number IS NULL THEN 'CAMEO 매핑 없음'
        ELSE NULL
    END                                                         AS exclusion_reason,
    CASE
        WHEN r.cas_number IS NOT NULL AND k.cas_number IS NOT NULL
         AND s.cas_number IS NOT NULL AND g.cas_number IS NOT NULL
         AND ch.cas_number IS NULL   THEN '인덱스 결손'
        WHEN r.cas_number IS NOT NULL AND k.cas_number IS NOT NULL
         AND s.cas_number IS NOT NULL AND g.cas_number IS NOT NULL
                                     THEN '정상'
        WHEN ch.cas_number IS NOT NULL THEN '서비스 외 청크 보유'
        ELSE '해당없음'
    END                                                         AS index_status
FROM base b
LEFT JOIN substance_registry r ON r.cas_number = b.cas_number
LEFT JOIN kosha      k  ON k.cas_number  = b.cas_number
LEFT JOIN msds       s  ON s.cas_number  = b.cas_number
LEFT JOIN cameo      g  ON g.cas_number  = b.cas_number
LEFT JOIN chunks     ch ON ch.cas_number = b.cas_number
LEFT JOIN membership mb ON mb.cas_number = b.cas_number
LEFT JOIN chunk_name n  ON n.cas_number  = b.cas_number;
"""


def ensure_view(con: sqlite3.Connection) -> None:
    con.executescript(VIEW_DDL)


def report(con: sqlite3.Connection) -> dict:
    cur = con.cursor()
    n_registry = cur.execute("select count(*) from substance_status where in_registry=1").fetchone()[0]
    eligible = [r[0] for r in cur.execute(
        "select cas_number from substance_status where service_eligible=1 order by cas_number")]
    ready = [r[0] for r in cur.execute(
        "select cas_number from substance_status"
        " where service_eligible=1 and chunks_ready=1 order by cas_number")]
    gap = [(r[0], r[1]) for r in cur.execute(
        "select cas_number, name_ko from substance_status where index_status='인덱스 결손'")]
    excl = cur.execute(
        "select exclusion_reason, count(*) from substance_status"
        " where in_registry=1 and service_eligible=0 group by 1 order by 2 desc").fetchall()
    legacy = cur.execute("select count(*) from substance_status where legacy_only=1").fetchone()[0]

    print(f"Registry {n_registry}종")
    print(f"  service_eligible : {len(eligible)}종  (Registry + KOSHA MSDS + CAMEO)")
    print(f"  chunks_ready     : {len(ready)}종  (그중 인덱스 생성 완료)")
    for reason, n in excl:
        print(f"  제외 - {reason:<16} {n:>3}종")
    print(f"  legacy 전용(Registry 밖 코퍼스 물질): {legacy}종")
    if gap:
        print(f"\n  [경고] 인덱스 결손 {len(gap)}종 - 서비스 자격이 있는데 청크가 없다:")
        for cas, ko in gap[:20]:
            print(f"    {cas}  {ko}")
        print("  -> pipeline.py 로 해당 물질을 청킹해야 한다(서비스 불가 물질이 아니다).")
    return {"eligible": eligible, "ready": ready, "gap": gap}


def seed(con: sqlite3.Connection, cas_list: list[str]) -> None:
    con.execute("delete from rag_corpus_membership where corpus_tag=?", (SERVICE_CORPUS_TAG,))
    con.executemany(
        "insert or ignore into rag_corpus_membership (corpus_tag, cas_number) values (?, ?)",
        [(SERVICE_CORPUS_TAG, cas) for cas in cas_list],
    )
    con.commit()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true",
                    help="VIEW 생성 + corpus_tag='service' 반영 (미지정 시 점검만)")
    args = ap.parse_args()

    con = sqlite3.connect(DB_PATH)
    ensure_view(con)  # VIEW는 읽기 전용이라 점검 모드에서도 만든다
    con.commit()

    info = report(con)

    if args.write:
        seed(con, info["ready"])
        n = con.execute(
            "select count(*) from rag_corpus_membership where corpus_tag=?",
            (SERVICE_CORPUS_TAG,)).fetchone()[0]
        kept = dict(con.execute(
            "select corpus_tag, count(*) from rag_corpus_membership"
            " where corpus_tag in ('173','core') group by corpus_tag").fetchall())
        print(f"\ncorpus_tag='{SERVICE_CORPUS_TAG}' {n}종 반영")
        print(f"  보존 확인: '173' {kept.get('173', 0)}종 / 'core' {kept.get('core', 0)}종 (불변)")
        if info["gap"]:
            print("  주의: 인덱스 결손 물질은 청크가 없어 service 태그에서 빠졌다(위 경고 참고).")
    else:
        print(f"\n(점검 모드) --write 를 붙이면 corpus_tag='{SERVICE_CORPUS_TAG}'로 {len(info['ready'])}종 반영")

    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
