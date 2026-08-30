# -*- coding: utf-8 -*-
"""Registry 물질 중 CAMEO 그룹 매핑이 없는 CAS를 PubChem으로 채운다.

경로는 기존과 같다 — CAS -> PubChem CID(PUG-REST) -> CAMEO Chemical Reactivity
Classification(hid=86). cameochemicals.noaa.gov 직접 스크레이핑은 robots.txt 위반으로
폐기된 경로이므로 쓰지 않는다(docs/DATA.md).

CID 오식별을 막기 위해 PubChem MolecularFormula를 registry.formula와 대조하고,
불일치는 리포트에 FORMULA_MISMATCH로 남긴 뒤 기본적으로 적재하지 않는다(--force-mismatch).

    python scripts/map_registry_cameo_groups.py            # 조회 + 리포트만
    python scripts/map_registry_cameo_groups.py --write    # DB 반영
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "reactivity_reference.db"
TODAY = date.today().isoformat()
# results/는 덮어쓰지 않는다 — 실행일로 파일을 나눈다.
REPORT = ROOT / "results" / f"registry_cameo_mapping_{TODAY}.csv"
SOURCE_TAG = f"pubchem_cameo_{TODAY}"
UA = {"User-Agent": "Mozilla/5.0 (SMART_MSDS research script)"}
DELAY = 0.25  # PUG-REST 권장 상한(5 req/s) 이내

# PubChem CID가 CAMEO 데이터시트와 다대일로 엮이면서 구조상 불가능한 그룹이 딸려온다.
# 해당 물질에 그 원소 자체가 없는 경우만 제외한다 — 판단이 아니라 조성 대조다.
EXCLUDE = {
    ("67-56-1", "Amines, Phosphines, and Pyridines"):
        "메탄올(CH4O)에 질소·인이 없다. 메틸아민 용액 데이터시트가 같은 CID로 엮인 것",
    ("1309-37-1", "Sulfides, Inorganic"):
        "산화철(III)(Fe2O3)에 황이 없다. CAMEO 'IRON OXIDE, SPENT'(황화철 함유)가 엮인 것",
}

# PubChem에 CID가 없는 혼합 이성질체 CAS. 이성질체 전부가 같은 그룹일 때만 수동 지정한다.
MANUAL_GROUPS = {
    "1330-20-7": (["Hydrocarbons, Aromatic"],
                  "혼합 자일렌은 PubChem CID 없음. o/m/p 이성질체(CID 7237/7929/7809) "
                  "전부 hid=86에서 Hydrocarbons, Aromatic 단독"),
}


def _get(url: str, timeout: int = 30):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return json.load(r)


def cas_to_cid(cas: str):
    """CAS -> (cid, molecular_formula). 미해결이면 (None, None)."""
    url = (
        "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
        f"{cas}/property/MolecularFormula/JSON"
    )
    try:
        props = _get(url, timeout=20)["PropertyTable"]["Properties"][0]
    except Exception:
        return None, None
    return props["CID"], props.get("MolecularFormula")


def cid_to_group_names(cid: int) -> list[str]:
    url = (
        "https://pubchem.ncbi.nlm.nih.gov/classification_2/classification_2.fcgi"
        f"?format=json&hid=86&search_uid={cid}&search_type=list&search_uid_type=cid"
    )
    try:
        data = _get(url)
    except Exception:
        return []
    names = set()
    for hier in data.get("Hierarchies", {}).get("Hierarchy", []):
        for node in hier.get("Node", []):
            info = node["Information"]
            if info.get("Match"):
                names.add(info["Name"]["StringWithMarkup"]["String"])
    return sorted(names)


_TOKEN = re.compile(r"([A-Z][a-z]?)(\d*)|(\()|(\))(\d*)")


def norm_formula(f: str | None) -> dict[str, int] | None:
    """분자식 -> 원소별 개수. CH3OH와 CH4O를 같은 것으로 본다. 파싱 불가면 None."""
    if not f:
        return None
    f = re.sub(r"\s+", "", f)
    if not re.fullmatch(r"[A-Za-z0-9()]+", f):
        return None
    stack: list[dict[str, int]] = [{}]
    pos = 0
    while pos < len(f):
        m = _TOKEN.match(f, pos)
        if not m or m.end() == pos:
            return None
        pos = m.end()
        el, n, opn, close, mult = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
        if el:
            stack[-1][el] = stack[-1].get(el, 0) + int(n or 1)
        elif opn:
            stack.append({})
        elif close:
            if len(stack) == 1:
                return None
            top = stack.pop()
            k = int(mult or 1)
            for e, c in top.items():
                stack[-1][e] = stack[-1].get(e, 0) + c * k
    return stack[0] if len(stack) == 1 else None


def formula_matches(registry_f: str | None, pubchem_f: str | None, axis: str) -> bool:
    """registry 분자식과 PubChem 분자식이 같은 물질을 가리키는가.

    원소는 registry가 기호(Br)로, PubChem이 실제 분자(Br2)로 적으므로 개수는 비교하지
    않고 원소 종류만 본다. 그 외에는 원소별 개수까지 일치해야 한다.
    """
    a, b = norm_formula(registry_f), norm_formula(pubchem_f)
    if a is None or b is None:
        return True  # 한쪽이라도 파싱 불가면 이 검사로 걸러내지 않는다
    return set(a) == set(b) if axis == "periodic_element" else a == b


def _self_check() -> None:
    assert formula_matches("Br", "Br2", "periodic_element")
    assert not formula_matches("Br", "BrCl", "periodic_element")
    assert formula_matches("CH3OH", "CH4O", "fundamental")
    assert not formula_matches("C8H10", "C8H8", "fundamental")
    assert norm_formula("CH3OH") == norm_formula("CH4O") == {"C": 1, "H": 4, "O": 1}
    assert norm_formula("Ca(OH)2") == {"Ca": 1, "O": 2, "H": 2}
    assert norm_formula("H2SO4") != norm_formula("H2SO3")
    assert norm_formula("") is None and norm_formula("Fe2O3·xH2O") is None
    print("norm_formula 자체검증 통과")


def unmapped_rows(cur) -> list[tuple]:
    return cur.execute(
        """select r.cas_number, r.name_ko, r.name_en, r.formula, r.core_category,
                  exists(select 1 from msds_chem_id_cache k
                         where k.cas_number = r.cas_number and ifnull(k.chem_id,'') <> '') as kosha
           from substance_registry r
           where r.cas_number not in (
                 select c.cas_number from chemicals c
                 join chemical_group_membership m on m.chemical_id = c.chemical_id)
           order by kosha desc, r.core_category, r.cas_number"""
    ).fetchall()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="DB에 반영")
    ap.add_argument("--kosha-only", action="store_true",
                    help="KOSHA 등재분만 조회(선택 목록 198종에 실제로 영향 있는 범위)")
    ap.add_argument("--force-mismatch", action="store_true",
                    help="분자식 불일치 건도 적재")
    args = ap.parse_args()
    _self_check()

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    gid_of = {name: gid for gid, name in
              cur.execute("select group_id, group_name from reactivity_groups")}

    targets = unmapped_rows(cur)
    if args.kosha_only:
        targets = [t for t in targets if t[5]]
    print(f"미매핑 대상 {len(targets)}종 조회 시작", flush=True)

    report, to_write, unknown_names = [], [], set()
    for cas, ko, en, formula, axis, kosha in targets:
        note = ""
        if cas in MANUAL_GROUPS:
            cid, pc_formula = None, None
            names, note = MANUAL_GROUPS[cas][0], MANUAL_GROUPS[cas][1]
            status = "MANUAL"
        else:
            cid, pc_formula = cas_to_cid(cas)
            time.sleep(DELAY)
            names = cid_to_group_names(cid) if cid else []
            time.sleep(DELAY)
            dropped = [n for n in names if (cas, n) in EXCLUDE]
            if dropped:
                names = [n for n in names if n not in dropped]
                note = " / ".join(f"제외: {n} — {EXCLUDE[(cas, n)]}" for n in dropped)
            if cid is None:
                status = "NO_CID"
            elif not formula_matches(formula, pc_formula, axis):
                status = "FORMULA_MISMATCH"
            elif not names:
                status = "NO_CAMEO_GROUP"
            else:
                status = "OK"
        gids = []
        for n in names:
            if n in gid_of:
                gids.append(gid_of[n])
            else:
                unknown_names.add(n)
        report.append({
            "cas_number": cas, "name_ko": ko, "name_en": en, "core_axis": axis,
            "kosha": bool(kosha), "cid": cid, "registry_formula": formula,
            "pubchem_formula": pc_formula, "status": status,
            "group_ids": ";".join(str(g) for g in sorted(gids)),
            "group_names": " | ".join(names), "note": note,
        })
        if gids and (status in ("OK", "MANUAL")
                     or (status == "FORMULA_MISMATCH" and args.force_mismatch)):
            to_write.append((cas, en or ko, sorted(set(gids))))
        print(f"  {cas:>12} {axis:<17} {status:<16} {' | '.join(names) or '-'}", flush=True)

    # 이미 이 경로로 적재된 물질도 리포트에 남긴다 — 재실행 시 대상이 미매핑분으로
    # 줄어들어 리포트가 "이 경로가 채운 전체"를 못 보여주는 걸 막는다.
    for cas, ko, axis, kosha, gids_s, names_s in cur.execute(
            "select r.cas_number, r.name_ko, r.core_category,"
            "  exists(select 1 from msds_chem_id_cache k"
            "         where k.cas_number = r.cas_number and ifnull(k.chem_id,'') <> ''),"
            "  group_concat(m.group_id), group_concat(rg.group_name, ' | ')"
            " from substance_registry r"
            " join chemicals c on c.cas_number = r.cas_number"
            " join chemical_group_membership m on m.chemical_id = c.chemical_id"
            " join reactivity_groups rg on rg.group_id = m.group_id"
            " where m.source like 'pubchem_cameo_%'"
            " group by r.cas_number order by r.core_category, r.cas_number"):
        report.append({
            "cas_number": cas, "name_ko": ko, "name_en": None, "core_axis": axis,
            "kosha": bool(kosha), "cid": None, "registry_formula": None,
            "pubchem_formula": None, "status": "ALREADY_WRITTEN",
            "group_ids": ";".join(sorted(gids_s.split(","), key=int)),
            "group_names": names_s, "note": "",
        })

    REPORT.parent.mkdir(exist_ok=True)
    with open(REPORT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(report[0].keys()))
        w.writeheader()
        w.writerows(report)
    print(f"\n리포트: {REPORT}")

    if unknown_names:
        print("\n[중단] reactivity_groups에 없는 그룹명이 반환됨:", sorted(unknown_names))
        return 1

    from collections import Counter
    print("상태 분포:", dict(Counter(r["status"] for r in report)))
    print(f"적재 가능 {len(to_write)}종 / 매핑행 {sum(len(g) for _, _, g in to_write)}")

    if not args.write:
        print("(--write 없음 — DB 미반영)")
        return 0

    n_chem = n_mem = 0
    for cas, name, gids in to_write:
        cur.execute(
            "insert or ignore into chemicals (cas_number, chemical_name, source) values (?,?,?)",
            (cas, name, SOURCE_TAG))
        n_chem += cur.rowcount
        chem_id = cur.execute("select chemical_id from chemicals where cas_number=?",
                              (cas,)).fetchone()[0]
        for gid in gids:
            cur.execute(
                "insert or ignore into chemical_group_membership (chemical_id, group_id, source)"
                " values (?,?,?)", (chem_id, gid, SOURCE_TAG))
            n_mem += cur.rowcount
    con.commit()
    print(f"chemicals +{n_chem}행, chemical_group_membership +{n_mem}행 (source={SOURCE_TAG})")

    mapped = cur.execute(
        """select count(distinct r.cas_number) from substance_registry r
           join chemicals c on c.cas_number = r.cas_number
           join chemical_group_membership m on m.chemical_id = c.chemical_id""").fetchone()[0]
    print(f"registry 237종 중 CAMEO 매핑: {mapped}종")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
