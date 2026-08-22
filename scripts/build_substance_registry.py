"""substance_registry 구축: 물질 식별(identity) 레이어.

Registry != RAG evidence != CAMEO 매핑. 이 세 축은 이미 DB에서 분리돼 있다
(chemicals/chemical_group_membership = CAMEO 축, msds_sections/rag_chunks = RAG
축). 여기서 만드는 substance_registry는 식별 축만 담당한다 - CAS 하나에
한글명/영문명/기호/별칭을 묶어 "아연=zinc=Zn=7440-66-6"이 검색에서 같은
물질로 잡히게 하는 게 유일한 목적. msds_available/rag_available/cameo_available은
저장하지 않고 필요할 때 chemicals/rag_chunks를 라이브 조회해서 판단한다.

registry의 소속 기준은 CORE 5그룹(periodic_element/fundamental/educational/
practical/representative) 하나뿐이다 - 207종. 173종 RAG 코퍼스는 Registry의
집합이 아니라 rag_corpus_membership이 소유하는 별개 축이므로 여기서 병합하지
않는다(docs/REGISTRY.md).

CAMEO chemicals 테이블에 없는 물질(염소·메탄올 등)을 이 스크립트가 chemicals에
새로 넣는 일은 없다 - registry에는 올려 검색은 되게 하되 CAMEO 축은 정직하게
비워 기존 Abstain 로직이 처리하게 둔다.

  python scripts/build_substance_registry.py            # 점검만(변경 없음)
  python scripts/build_substance_registry.py --write     # substance_registry에 반영
"""

from __future__ import annotations

import argparse
import collections
import csv
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "reactivity_reference.db"
COLLECTION_DIR = ROOT / "data" / "collection"
BASELINE_PATH = COLLECTION_DIR / "_frozen_substances_baseline.json"

CORE_SOURCES = [
    (COLLECTION_DIR / "core_periodic_elements.csv", "periodic_element"),
    (COLLECTION_DIR / "core_fundamental_chemicals.csv", "fundamental"),
    (COLLECTION_DIR / "core_educational_chemicals.csv", "educational"),
    (COLLECTION_DIR / "core_practical_chemicals.csv", "practical"),
    (COLLECTION_DIR / "core_representative_chemicals.csv", "representative"),
]


def load_core_rows() -> dict[str, dict]:
    """3개 CSV -> {cas: {name_ko, name_en, formula, aliases, core_category}}.
    CAS 중복시 먼저 나온(원소 > 기본 > 교육 > 실무 > 대표 순) core_category를 유지한다."""
    rows: dict[str, dict] = {}
    for path, category in CORE_SOURCES:
        with open(path, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                cas = r["cas_number"].strip()
                if cas in rows:
                    continue
                rows[cas] = {
                    "name_ko": r["name_ko"].strip(),
                    "name_en": (r.get("name_en") or "").strip() or None,
                    "formula": (r.get("formula") or r.get("symbol") or "").strip() or None,
                    "aliases": (r.get("aliases") or "").strip(),
                    "core_category": category,
                }
    return rows


def build_registry() -> list[dict]:
    return [
        {
            "cas_number": cas,
            "name_ko": r["name_ko"],
            "name_en": r["name_en"],
            "formula": r["formula"],
            "aliases": r["aliases"],
            "core_category": r["core_category"],
        }
        for cas, r in load_core_rows().items()
    ]


def write_registry(rows: list[dict]) -> None:
    """CSV에서 전량 재생성한다 - registry는 CORE CSV의 파생 테이블이라 CSV에서
    빠진 물질이 DB에 남으면 안 된다(그래서 UPSERT가 아니라 drop 후 재적재)."""
    con = sqlite3.connect(DB_PATH)
    con.executescript("""
    DROP TABLE IF EXISTS substance_registry;
    CREATE TABLE substance_registry (
        cas_number    TEXT PRIMARY KEY,
        name_ko       TEXT NOT NULL,
        name_en       TEXT,
        formula       TEXT,
        aliases       TEXT NOT NULL DEFAULT '',
        core_category TEXT NOT NULL
    );
    """)
    con.executemany(
        "INSERT INTO substance_registry "
        "(cas_number, name_ko, name_en, formula, aliases, core_category) "
        "VALUES (:cas_number, :name_ko, :name_en, :formula, :aliases, :core_category)",
        rows,
    )
    con.commit()
    con.close()


def self_check(rows: list[dict]) -> None:
    """ponytail 자가검증 - 별칭 정규화가 실제로 동작하는지 CAS 단위로 확인."""
    by_cas = {r["cas_number"]: r for r in rows}

    def label(cas: str) -> str:
        r = by_cas[cas]
        return " ".join(x for x in (r["name_ko"], r["name_en"], r["formula"], r["aliases"], r["cas_number"]) if x)

    checks = [
        ("7440-66-6", ["아연", "zinc", "Zn", "7440-66-6"]),
        ("7647-01-0", ["염산", "hydrochloric", "hydrogen chloride", "7647-01-0"]),
        ("7440-23-5", ["나트륨", "sodium", "Na", "7440-23-5"]),
        ("7440-59-7", ["헬륨", "helium", "He", "7440-59-7"]),
        ("1333-74-0", ["수소", "hydrogen", "1333-74-0"]),
    ]
    for cas, terms in checks:
        assert cas in by_cas, f"자가검증 실패: {cas} registry에 없음"
        text = label(cas).lower()
        # zinc 별칭은 name_en에 있고, hydrochloric acid는 core_fundamental의 aliases("염산")+
        # name_en("Hydrogen chloride")로 커버됨. 없는 term은 aliases 컬럼 확장이 필요하다는 뜻.
        missing = [t for t in terms if t.lower() not in text]
        assert not missing, f"자가검증 실패: {cas} 라벨에 {missing} 없음 (label={label(cas)!r})"

    cas_list = [r["cas_number"] for r in rows]
    assert len(cas_list) == len(set(cas_list)), "자가검증 실패: CAS 중복"

    groups = collections.Counter(r["core_category"] for r in rows)
    assert not groups[None], "자가검증 실패: core_category 없는 행 존재"
    assert set(groups) == {c for _, c in CORE_SOURCES}, f"자가검증 실패: 그룹 구성 불일치 {sorted(groups)}"

    check_frozen_173()
    check_kosha_cache()
    print(f"자가검증 통과: CORE {len(cas_list)}종 "
          f"({', '.join(f'{k} {v}' for k, v in groups.most_common())}), CAS 중복 없음")


def check_kosha_cache() -> None:
    """registry ↔ KOSHA 조회 캐시 정합성. **API를 호출하지 않는다** — 이미 적재된
    msds_chem_id_cache만 읽으므로 키/네트워크 없이 CI에서도 돌아간다. 실제 API
    조회와 그 결과 검증은 scripts/kosha_registry_lookup.py --fetch 담당.

    registry에 물질을 추가하고 lookup을 돌리지 않으면 여기서 잡힌다."""
    con = sqlite3.connect(DB_PATH)
    reg = {c for (c,) in con.execute("select cas_number from substance_registry")}
    cache = dict(con.execute("select cas_number, chem_id from msds_chem_id_cache"))
    con.close()

    unchecked = sorted(reg - set(cache))
    assert not unchecked, (
        f"KOSHA 조회 미실행 CAS {len(unchecked)}종: {unchecked[:10]} "
        "-> python scripts/kosha_registry_lookup.py --fetch"
    )
    matched = sum(1 for c in reg if cache.get(c))
    print(f"KOSHA 연동 확인: registry {len(reg)}종 전부 조회 완료 "
          f"(등재 {matched} / 미등재 {len(reg) - matched}, API 호출 없음)")


def check_frozen_173() -> None:
    """173종의 RAG 질의 텍스트(rag_chunks.chemical_name)가 Registry 도입 전과
    완전히 동일한지 확인. 이 이름이 한 글자라도 바뀌면 frozen retrieval 지표
    (Recall@10 0.9336 등)가 무효화된다. baseline은 Registry 적용 전 커밋에서
    뜬 substances() 반환값."""
    import json

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    con = sqlite3.connect(DB_PATH)
    p173 = {c for (c,) in con.execute(
        "select cas_number from rag_corpus_membership where corpus_tag='173'"
    )}
    current = dict(con.execute(
        "select rc.cas_number, rc.chemical_name from rag_chunks rc "
        "join rag_corpus_membership m on m.cas_number = rc.cas_number "
        "where m.corpus_tag in ('173','core') group by rc.cas_number"
    ))
    con.close()

    changed = {c: (baseline.get(c), current.get(c)) for c in p173 if baseline.get(c) != current.get(c)}
    assert not changed, f"frozen 위반: 173종 질의 이름이 바뀜 {changed}"
    dropped = set(baseline) - set(current)
    assert not dropped, f"frozen 위반: baseline에 있던 물질이 사라짐 {dropped}"
    print(f"frozen 보존 확인: 173종 질의 이름 불변, 검색 대상 {len(baseline)}→{len(current)}종")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="실제로 substance_registry에 반영")
    args = ap.parse_args()

    rows = build_registry()
    print(f"registry 후보 {len(rows)}종 (CORE 5그룹)")

    self_check(rows)

    if args.write:
        write_registry(rows)
        print(f"substance_registry에 {len(rows)}행 반영 완료")
    else:
        print("점검만 수행(변경 없음). 반영하려면 --write")


if __name__ == "__main__":
    main()
