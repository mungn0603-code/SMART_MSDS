"""Stage 4 파이프라인 1단계: 본문추출 -> Normalize -> Chunk -> Metadata Attach

설계 근거: docs/stage4_design_principles_v2.md
  §3  파이프라인 대순서 (임의 변경 금지)
  §6  Metadata Hybrid (SQLite 진실원본 + Vector payload 캐시)
  §8  Chunking (1차 경계 = EAV 항목, 상한 초과 시만 Recursive Split)
  §9  Normalize (공백/줄바꿈/특수문자/단위/CAS표기/한영혼용)

세션 확정사항(2026-08-06, 사용자 승인):
  - 근거등급: 출처표기 기반 3분할
      섹션2(GHS분류·H/P코드 = 고용노동부고시 별표 확정문구) -> Mandatory
      섹션3·9·10 중 ※출처 미표기 (KOSHA 작성값)          -> Recommended
      ※출처 표기 항목 (HSDB/ECHA/ICSC 등 외부DB 인용)     -> Reference
  - 청킹 단위는 2종 모두 생성하여 Retrieval 지표로 A/B (section / item)

입력 : reactivity_reference.db (msds_sections, chemicals, chemical_group_membership,
                                reactivity_groups, msds_chem_id_cache)
출력 : reactivity_reference.db 의 rag_chunks 테이블 + data/chunks/**.md
"""

from __future__ import annotations

import argparse
import csv
import re
import sqlite3
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

PIPELINE_VERSION = "stage4-v2-chunk-1"
SOURCE = "KOSHA_MSDS"

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "reactivity_reference.db"
CHUNK_DIR = ROOT / "data" / "chunks"


def load_target_cas(target_csv: str | None) -> set[str] | None:
    """PHASE 5 대응: --target-csv로 넘긴 CSV의 cas_number만 청킹 대상으로 제한.
    None이면 기존 동작(msds_sections 전체) 그대로 — 하위호환 유지."""
    if not target_csv:
        return None
    with open(target_csv, encoding="utf-8-sig") as f:
        return {row["cas_number"] for row in csv.DictReader(f)}

# §8 상한. 실측 (물질,섹션) 합본 최대 2,095자 -> 대부분 무분할, 초과분만 Recursive Split.
MAX_CHARS = 1800

SECTION_TITLES = {
    2: "유해성·위험성",
    3: "구성성분의 명칭 및 함유량",
    9: "물리화학적 특성",
    10: "안정성 및 반응성",
}

# 고용노동부고시 「화학물질의 분류·표시 및 물질안전보건자료에 관한 기준」 별표 그림문자
PICTOGRAMS = {
    "GHS01": "폭발성",
    "GHS02": "인화성",
    "GHS03": "산화성",
    "GHS04": "고압가스",
    "GHS05": "부식성",
    "GHS06": "급성독성",
    "GHS07": "경고(자극성)",
    "GHS08": "건강유해성",
    "GHS09": "수생환경유해성",
}

# 실측된 무자료 표기 변종 전부 (2026-08-06 msds_sections 전수조사)
# 두번째 대안: 값이 구두점/대시/슬래시뿐인 자리표시자('- / -' 72건 등)
NO_DATA_RE = re.compile(
    r"^\(?\s*(자료\s*없음|해당\s*없음|해당\s*안됨|없음|미상|불명)\s*\.?\s*\)?$"
    r"|^[-–—/\s.·]+$"
)
SOURCE_RE = re.compile(r"※\s*출처\s*[:：]\s*(.+)$")
CAS_RE = re.compile(r"\b(\d{2,7})\s*-\s*(\d{2})\s*-\s*(\d)\b")
PICTO_RE = re.compile(r"\b(GHS\d{2})\.gif\b", re.IGNORECASE)


def normalize_detail(raw: str | None) -> tuple[str, list[str], bool]:
    """§9 Normalize. 반환: (정규화 본문, ※출처 목록, 무자료 여부)

    - NFKC 로 단위 호환문자 정규화 (℃->°C, ㎩->Pa, ㎖->mL, ㎎->mg, 전각->반각)
    - '|' 다중값 구분자를 줄 단위로 분리
    - '※출처 : X' 는 본문에서 분리해 메타데이터로 승격 (근거등급 판정 신호)
    - GHS 그림문자 파일명(GHS06.gif)을 판독 가능한 코드+한글명으로 치환
    - CAS 표기 정규화 (공백 제거, NNNNNNN-NN-N)
    - 무자료 표기 변종을 단일 마커로 통일
    """
    if raw is None:
        return "", [], False

    text = unicodedata.normalize("NFKC", raw)
    parts = [p.strip() for p in text.split("|")]

    values: list[str] = []
    sources: list[str] = []
    for part in parts:
        if not part:
            continue
        m = SOURCE_RE.match(part)
        if m:
            src = m.group(1).strip().rstrip(".")
            if src:
                sources.append(src)
            continue
        part = PICTO_RE.sub(
            lambda mm: f"{mm.group(1).upper()}({PICTOGRAMS.get(mm.group(1).upper(), '기타')})",
            part,
        )
        part = CAS_RE.sub(lambda mm: f"{mm.group(1)}-{mm.group(2)}-{mm.group(3)}", part)
        part = re.sub(r"[ \t ]+", " ", part).strip()
        if part:
            values.append(part)

    values = [v for v in values if not NO_DATA_RE.match(v)]
    if not values:
        return ("자료없음" if raw.strip() else ""), sources, True

    body = values[0] if len(values) == 1 else "\n".join(f"- {v}" for v in values)
    return body, sources, False


def evidence_grade(section: int, sources: list[str]) -> str:
    """세션 확정 근거등급 규칙 (출처표기 기반 3분할)."""
    if section == 2:
        return "Mandatory"
    return "Reference" if sources else "Recommended"


GRADE_RANK = {"Mandatory": 0, "Recommended": 1, "Reference": 2}


def dominant_grade(grades: list[str]) -> str:
    """혼재 시 가장 권위 있는 등급을 대표값으로. 전체 목록은 별도 컬럼에 보존."""
    return min(grades, key=lambda g: GRADE_RANK[g])


def recursive_split(text: str, cap: int = MAX_CHARS) -> list[str]:
    """§8 2차 분할. EAV 항목 경계(헤딩)를 최우선으로, 그 다음 문단/줄/공백."""
    if len(text) <= cap:
        return [text]
    for sep in ("\n### ", "\n## ", "\n\n", "\n", " "):
        if sep not in text:
            continue
        segs = text.split(sep)
        segs = [segs[0]] + [sep + s for s in segs[1:]]  # 구분자를 보존(무손실 분할)
        pieces, buf = [], ""
        for seg in segs:
            if buf and len(buf) + len(seg) > cap:
                pieces.append(buf)
                buf = seg
            else:
                buf += seg
        if buf:
            pieces.append(buf)
        if len(pieces) > 1:
            out: list[str] = []
            for p in pieces:
                out.extend(recursive_split(p, cap) if len(p) > cap else [p])
            return out
    return [text[i : i + cap] for i in range(0, len(text), cap)]


def load_reference(con: sqlite3.Connection) -> dict[str, dict]:
    """CAS -> {한글명, 영문명, chemical_id, CAMEO 그룹, 개정일}"""
    cur = con.cursor()
    ref: dict[str, dict] = {}
    for cas, cid, name_en in cur.execute(
        "select cas_number, chemical_id, chemical_name from chemicals"
    ):
        ref[cas] = {
            "chemical_id": cid,
            "name_en": name_en,
            "name_kor": None,
            "groups": [],
            "group_names": [],
            "revision": None,
        }
    for cas, name_kor, last_date in cur.execute(
        "select cas_number, chem_name_kor, last_date from msds_chem_id_cache"
    ):
        if cas in ref:
            ref[cas]["name_kor"] = name_kor
            ref[cas]["revision"] = last_date
    for cas, gid, gname in cur.execute(
        "select c.cas_number, g.group_id, g.group_name from chemicals c "
        "join chemical_group_membership m on m.chemical_id = c.chemical_id "
        "join reactivity_groups g on g.group_id = m.group_id order by g.group_id"
    ):
        if cas in ref:
            ref[cas]["groups"].append(gid)
            ref[cas]["group_names"].append(gname)
    return ref


def heading(lev: int) -> str:
    return "#" * (lev + 1)


def build_chunks(
    con: sqlite3.Connection, ref: dict[str, dict], target_cas: set[str] | None = None,
    version: str = PIPELINE_VERSION,
) -> list[dict]:
    cur = con.cursor()
    rows = cur.execute(
        "select cas_number, section, item_name_kor, item_detail, lev, msds_item_code, ordr_idx "
        "from msds_sections order by cas_number, section, ordr_idx"
    ).fetchall()

    skipped_no_ref, skipped_not_target = set(), set()

    # (cas, section) -> 정규화된 항목 리스트
    grouped: dict[tuple[str, int], list[dict]] = {}
    for cas, section, name, detail, lev, code, ordr in rows:
        if target_cas is not None and cas not in target_cas:
            skipped_not_target.add(cas)
            continue
        if cas not in ref:
            # chemicals 테이블에 없는 고아 레코드(예: 497-19-8, docs/decisions.md §1.2b
            # UREA CAS 오류 정정 후 msds_sections에만 남은 잔재) — 청킹 대상에서 제외.
            skipped_no_ref.add(cas)
            continue
        body, sources, no_data = normalize_detail(detail)
        grouped.setdefault((cas, section), []).append(
            {
                "cas": cas,
                "section": section,
                "name": (name or "").strip(),
                "body": body,
                "sources": sources,
                "no_data": no_data,
                "lev": lev,
                "code": code,
                "ordr": ordr,
                "grade": evidence_grade(section, sources),
            }
        )

    if skipped_no_ref:
        print(f"[경고] chemicals 테이블에 없어 청킹 제외된 고아 CAS {len(skipped_no_ref)}건: "
              f"{sorted(skipped_no_ref)}")
    if target_cas is not None and skipped_not_target:
        print(f"[정보] --target-csv 대상 아니라 제외된 CAS {len(skipped_not_target)}건 "
              f"(msds_sections엔 있으나 이번 rebuild 범위 밖)")

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    chunks: list[dict] = []

    def meta(cas: str, section: int) -> dict:
        r = ref[cas]
        return {
            "chemical_id": r["chemical_id"],
            "cas_number": cas,
            "chemical_name": r["name_kor"],
            "chemical_name_en": r["name_en"],
            "section": section,
            "cameo_groups": ",".join(str(g) for g in r["groups"]),
            "cameo_group_names": " | ".join(r["group_names"]),
            "revision": r["revision"],
            "source": SOURCE,
            "version": version,
            "status": "active",
            "created_at": now,
        }

    for (cas, section), items in grouped.items():
        r = ref[cas]
        title = f"{r['name_kor']} ({cas}) — {section}. {SECTION_TITLES[section]}"

        # --- granularity: section (§3 "Section Chunk, EAV 경계 유지") ---
        lines = [f"# {title}"]
        for it in items:
            lines.append(f"{heading(it['lev'])} {it['name']}")
            if it["body"]:
                lines.append(it["body"])
        text = "\n".join(lines).strip()
        grades = [it["grade"] for it in items]
        srcs = sorted({s for it in items for s in it["sources"]})
        all_no_data = all(it["no_data"] or not it["body"] for it in items)
        parts = recursive_split(text)
        for idx, part in enumerate(parts, start=1):
            suffix = "" if len(parts) == 1 else f"::p{idx}"
            chunks.append(
                {
                    **meta(cas, section),
                    "chunk_id": f"sec::{cas}::{section}{suffix}",
                    "granularity": "section",
                    "item_codes": ",".join(it["code"] for it in items),
                    "item_names": " | ".join(it["name"] for it in items),
                    "evidence_grade": dominant_grade(grades),
                    "evidence_grades": ",".join(sorted(set(grades), key=GRADE_RANK.get)),
                    "evidence_sources": ",".join(srcs),
                    "abstain": int(all_no_data),
                    "text": part,
                    "n_chars": len(part),
                }
            )

        # --- granularity: item (§8 "1차 경계: EAV 항목") ---
        for it in items:
            if not it["body"]:
                continue  # 값 없는 구조상 상위노드(B04/B0408/I02 등)는 단독 청크 대상 아님
            body = it["body"]
            item_text = f"# {title}\n{heading(it['lev'])} {it['name']}\n{body}"
            item_parts = recursive_split(item_text)
            for idx, part in enumerate(item_parts, start=1):
                suffix = "" if len(item_parts) == 1 else f"::p{idx}"
                chunks.append(
                    {
                        **meta(cas, section),
                        "chunk_id": f"item::{cas}::{it['code']}{suffix}",
                        "granularity": "item",
                        "item_codes": it["code"],
                        "item_names": it["name"],
                        "evidence_grade": it["grade"],
                        "evidence_grades": it["grade"],
                        "evidence_sources": ",".join(sorted(set(it["sources"]))),
                        "abstain": int(it["no_data"]),
                        "text": part,
                        "n_chars": len(part),
                    }
                )
    return chunks


COLUMNS = [
    "chunk_id", "granularity", "chemical_id", "cas_number", "chemical_name",
    "chemical_name_en", "section", "item_codes", "item_names", "cameo_groups",
    "cameo_group_names", "evidence_grade", "evidence_grades", "evidence_sources",
    "abstain", "text", "n_chars", "revision", "source", "version", "status",
    "created_at",
]

DDL = """
CREATE TABLE IF NOT EXISTS rag_chunks (
    chunk_id          TEXT PRIMARY KEY,
    granularity       TEXT NOT NULL CHECK(granularity IN ('section','item')),
    chemical_id       INTEGER REFERENCES chemicals(chemical_id),
    cas_number        TEXT NOT NULL,
    chemical_name     TEXT,
    chemical_name_en  TEXT,
    section           INTEGER NOT NULL,
    item_codes        TEXT,
    item_names        TEXT,
    cameo_groups      TEXT,
    cameo_group_names TEXT,
    evidence_grade    TEXT NOT NULL CHECK(evidence_grade IN ('Mandatory','Recommended','Reference')),
    evidence_grades   TEXT NOT NULL,
    evidence_sources  TEXT,
    abstain           INTEGER NOT NULL,
    text              TEXT NOT NULL,
    n_chars           INTEGER NOT NULL,
    revision          TEXT,
    source            TEXT NOT NULL,
    version           TEXT NOT NULL,
    status            TEXT NOT NULL,
    created_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_gran ON rag_chunks(granularity);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_cas ON rag_chunks(cas_number);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_grade ON rag_chunks(evidence_grade);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_abstain ON rag_chunks(abstain);
"""


def persist(con: sqlite3.Connection, chunks: list[dict], version: str = PIPELINE_VERSION) -> None:
    con.executescript(DDL)
    con.execute("DELETE FROM rag_chunks WHERE version = ?", (version,))
    con.executemany(
        f"INSERT OR REPLACE INTO rag_chunks ({','.join(COLUMNS)}) "
        f"VALUES ({','.join('?' * len(COLUMNS))})",
        [tuple(c[k] for k in COLUMNS) for c in chunks],
    )
    con.commit()


def write_markdown(chunks: list[dict]) -> None:
    for gran in ("section", "item"):
        d = CHUNK_DIR / gran
        d.mkdir(parents=True, exist_ok=True)
        for f in d.glob("*.md"):
            f.unlink()
    for c in chunks:
        fm = [
            "---",
            f"chunk_id: {c['chunk_id']}",
            f"granularity: {c['granularity']}",
            f"cas_number: {c['cas_number']}",
            f"chemical_name: {c['chemical_name']}",
            f"section: {c['section']}",
            f"item_codes: {c['item_codes']}",
            f"cameo_groups: {c['cameo_groups']}",
            f"evidence_grade: {c['evidence_grade']}",
            f"evidence_grades: {c['evidence_grades']}",
            f"evidence_sources: {c['evidence_sources']}",
            f"abstain: {c['abstain']}",
            f"revision: {c['revision']}",
            f"source: {c['source']}",
            f"version: {c['version']}",
            "---",
            "",
        ]
        safe = c["chunk_id"].replace("::", "__").replace("/", "_")
        (CHUNK_DIR / c["granularity"] / f"{safe}.md").write_text(
            "\n".join(fm) + c["text"] + "\n", encoding="utf-8"
        )


def report(chunks: list[dict]) -> None:
    import collections

    print(f"총 청크: {len(chunks)}")
    for gran in ("section", "item"):
        sub = [c for c in chunks if c["granularity"] == gran]
        lens = sorted(c["n_chars"] for c in sub)
        print(f"\n[{gran}] n={len(sub)}  물질={len({c['cas_number'] for c in sub})}")
        print(f"  길이 min={lens[0]} p50={lens[len(lens)//2]} p90={lens[int(len(lens)*.9)]} max={lens[-1]}")
        print(f"  분할발생(::p) = {sum(1 for c in sub if '::p' in c['chunk_id'])}")
        print(f"  근거등급 {dict(collections.Counter(c['evidence_grade'] for c in sub))}")
        print(f"  abstain=1 {sum(c['abstain'] for c in sub)}")
        print(f"  섹션분포 {dict(sorted(collections.Counter(c['section'] for c in sub).items()))}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-markdown", action="store_true", help="마크다운 파일 생성 생략")
    ap.add_argument("--target-csv", default=None,
                     help="이 CSV(cas_number 컬럼)에 있는 물질만 청킹. 생략 시 기존 동작"
                          "(msds_sections 전체) 그대로 — PHASE 5: 426/259 두 코퍼스 분리 rebuild용")
    ap.add_argument("--version", default=PIPELINE_VERSION,
                     help="rag_chunks.version 태그. 코퍼스별로 다르게 줘야 서로 안 겹침")
    args = ap.parse_args()

    target_cas = load_target_cas(args.target_csv)

    con = sqlite3.connect(DB_PATH)
    ref = load_reference(con)
    chunks = build_chunks(con, ref, target_cas=target_cas, version=args.version)
    persist(con, chunks, version=args.version)
    if not args.no_markdown:
        write_markdown(chunks)
    con.close()
    report(chunks)
    print(f"\nversion: {args.version}")
    print(f"DB: {DB_PATH} (rag_chunks)")
    print(f"MD: {CHUNK_DIR}")


if __name__ == "__main__":
    main()
