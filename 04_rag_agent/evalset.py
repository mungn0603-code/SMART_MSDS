"""Stage 4 평가셋 생성: Retrieval gold set + Abstain 평가셋

설계 근거: docs/stage4_design_principles_v2.md §10 (2계층 평가), §13 (실행순서)
세션 확정사항(2026-08-06, 사용자 승인): "템플릿 + 사용자 검수 혼합"
  - DB에서 결정론적으로 전량 생성 -> 사용자가 샘플 검수 -> 템플릿 수정 후 재생성

정답(gold) 정의
  - item    : gold chunk = 해당 (CAS, EAV 항목코드) 청크
  - section : gold chunk = 해당 (CAS, 섹션) 청크. 분할된 섹션은 그 항목 제목이 실제로
              들어있는 part 만 정답으로 인정 (느슨한 '섹션 전체 정답' 금지)

제외 규칙 (평가 왜곡 방지)
  - 값이 없는 구조상 상위노드(B04/B0408/I02) : 청크 자체가 없음
  - C02 물질명 / C04 이명 : 질의문에 정답이 그대로 들어가는 퇴화(degenerate) 질의
  - abstain=1 항목 : Retrieval gold set에서 제외하고 Abstain 평가셋으로 분리
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "reactivity_reference.db"
OUT_DIR = Path(__file__).resolve().parent / "evalset"

SEED = 42
PER_ITEM_DEFAULT = 12  # 항목코드당 표본 물질 수

# EAV 항목코드 -> 질의 템플릿. {n} = 물질 한글명
TEMPLATES: dict[str, str] = {
    # 2. 유해성·위험성
    "B02": "{n}의 GHS 유해성·위험성 분류는 무엇인가?",
    "B0402": "{n}의 경고표지 그림문자는 무엇인가?",
    "B0404": "{n}의 신호어는 무엇인가?",
    "B0406": "{n}의 유해·위험문구(H코드)는 무엇인가?",
    "B040802": "{n}의 취급 시 예방에 관한 조치문구는 무엇인가?",
    "B040804": "{n}에 노출되었을 때 대응 조치문구는 무엇인가?",
    "B040806": "{n}의 저장에 관한 예방조치문구는 무엇인가?",
    "B040808": "{n}의 폐기에 관한 예방조치문구는 무엇인가?",
    "B06": "{n}의 분류기준에 포함되지 않는 기타 유해성·위험성은 무엇인가?",
    # 3. 구성성분
    "C06": "{n}의 CAS 번호는 무엇인가?",
    "C08": "{n}의 함유량은 몇 퍼센트인가?",
    # 9. 물리화학적 특성
    "I0202": "{n}의 성상은 무엇인가?",
    "I0204": "{n}의 색상은 무엇인가?",
    "I04": "{n}의 냄새는 어떠한가?",
    "I06": "{n}의 냄새역치는 얼마인가?",
    "I08": "{n}의 pH는 얼마인가?",
    "I10": "{n}의 녹는점은 몇 도인가?",
    "I12": "{n}의 끓는점은 몇 도인가?",
    "I14": "{n}의 인화점은 몇 도인가?",
    "I16": "{n}의 증발속도는 얼마인가?",
    "I18": "{n}의 인화성(고체, 기체)은 어떠한가?",
    "I20": "{n}의 폭발 범위 상한과 하한은 얼마인가?",
    "I22": "{n}의 증기압은 얼마인가?",
    "I24": "{n}의 물에 대한 용해도는 얼마인가?",
    "I26": "{n}의 증기밀도는 얼마인가?",
    "I28": "{n}의 비중은 얼마인가?",
    "I30": "{n}의 n-옥탄올/물 분배계수(Kow)는 얼마인가?",
    "I32": "{n}의 자연발화온도는 몇 도인가?",
    "I34": "{n}의 분해온도는 몇 도인가?",
    "I36": "{n}의 점도는 얼마인가?",
    "I38": "{n}의 분자량은 얼마인가?",
    # 10. 안정성 및 반응성
    "J02": "{n}의 화학적 안정성과 유해 반응의 가능성은 어떠한가?",
    "J06": "{n}의 취급·저장 시 피해야 할 조건은 무엇인가?",
    "J08": "{n}의 취급 시 접촉을 피해야 할 물질은 무엇인가?",
    "J10": "{n}의 분해 시 생성되는 유해물질은 무엇인가?",
}

EXCLUDED_DEGENERATE = {"C02", "C04"}  # 질의에 정답이 그대로 노출됨


def item_heading(con: sqlite3.Connection, cas: str, code: str) -> str | None:
    row = con.execute(
        "select item_name_kor from msds_sections where cas_number=? and msds_item_code=?",
        (cas, code),
    ).fetchone()
    return row[0].strip() if row and row[0] else None


def section_gold(
    con: sqlite3.Connection, cas: str, section: int, heading: str
) -> str | None:
    """분할된 섹션 청크 중 해당 항목 제목이 실제로 들어있는 part 만 정답."""
    rows = con.execute(
        "select chunk_id, text from rag_chunks "
        "where granularity='section' and cas_number=? and section=? order by chunk_id",
        (cas, section),
    ).fetchall()
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0][0]
    for chunk_id, text in rows:
        for line in text.splitlines():
            if line.startswith("#") and line.lstrip("# ").strip() == heading:
                return chunk_id
    return None


def build(con: sqlite3.Connection, per_item: int) -> tuple[list[dict], list[dict]]:
    rng = random.Random(SEED)
    rows = con.execute(
        "select chunk_id, cas_number, chemical_name, section, item_codes, abstain, "
        "       evidence_grade, cameo_groups "
        "from rag_chunks where granularity='item' order by chunk_id"
    ).fetchall()

    by_code: dict[str, list[tuple]] = {}
    for r in rows:
        by_code.setdefault(r[4], []).append(r)

    gold: list[dict] = []
    abstain: list[dict] = []
    for code, entries in sorted(by_code.items()):
        if code in EXCLUDED_DEGENERATE or code not in TEMPLATES:
            continue
        answerable = [e for e in entries if e[5] == 0]
        no_data = [e for e in entries if e[5] == 1]

        for pool, sink, kind in ((answerable, gold, "answerable"), (no_data, abstain, "no_data")):
            if not pool:
                continue
            picked = rng.sample(pool, min(per_item, len(pool)))
            for chunk_id, cas, name, section, item_code, _ab, grade, cameo in picked:
                heading = item_heading(con, cas, item_code)
                sec_gold = section_gold(con, cas, section, heading) if heading else None
                rec = {
                    "query_id": f"{kind[:3]}::{item_code}::{cas}",
                    "query": TEMPLATES[code].format(n=name),
                    "kind": kind,
                    "cas_number": cas,
                    "chemical_name": name,
                    "section": section,
                    "item_code": item_code,
                    "item_name": heading,
                    "evidence_grade": grade,
                    "cameo_groups": cameo,
                    "gold_item": chunk_id,
                    "gold_section": sec_gold,
                }
                sink.append(rec)

    # KOSHA MSDS 자체가 없는 물질 -> 물질 특정 근거 없음 -> 무조건 Abstain
    missing = con.execute(
        "select cas_number from msds_chem_id_cache where chem_id is null order by cas_number"
    ).fetchall()
    names = dict(
        con.execute("select cas_number, chemical_name from chemicals").fetchall()
    )
    for (cas,) in missing:
        abstain.append(
            {
                "query_id": f"nomsds::{cas}",
                "query": f"{names.get(cas, cas)}(CAS {cas})의 피해야 할 물질은 무엇인가?",
                "kind": "no_msds",
                "cas_number": cas,
                "chemical_name": names.get(cas),
                "section": None,
                "item_code": None,
                "item_name": None,
                "evidence_grade": None,
                "cameo_groups": None,
                "gold_item": None,
                "gold_section": None,
            }
        )
    return gold, abstain


def write_review(gold: list[dict], abstain: list[dict], n: int, path: Path) -> None:
    rng = random.Random(SEED + 1)
    sample = rng.sample(gold, min(n, len(gold)))
    lines = [
        "# 평가셋 검수용 샘플",
        "",
        f"- Retrieval gold set: {len(gold)}건 (항목코드 {len({g['item_code'] for g in gold})}종)",
        f"- Abstain 평가셋: {len(abstain)}건 "
        f"(자료없음 {sum(1 for a in abstain if a['kind'] == 'no_data')}건 / "
        f"MSDS없음 {sum(1 for a in abstain if a['kind'] == 'no_msds')}건)",
        "",
        "## 검수 방법",
        "아래 질의문이 (1) 한국어로 자연스러운지 (2) 정답 항목을 정확히 겨냥하는지 확인.",
        "고칠 문구가 있으면 `evalset.py`의 `TEMPLATES` 항목코드별 문장을 알려주세요.",
        "",
        "| # | 항목코드 | 항목명 | 질의문 | 정답청크(item) |",
        "|---|---|---|---|---|",
    ]
    for i, g in enumerate(sample, 1):
        lines.append(
            f"| {i} | {g['item_code']} | {g['item_name']} | {g['query']} | `{g['gold_item']}` |"
        )
    lines += [
        "",
        "## 제외된 항목 (평가 왜곡 방지)",
        "- `B04`, `B0408`, `I02`: 값이 없는 구조상 상위노드 (청크 자체가 없음)",
        "- `C02`(물질명), `C04`(이명): 질의문에 정답이 그대로 들어가는 퇴화 질의",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-item", type=int, default=PER_ITEM_DEFAULT)
    ap.add_argument("--review-n", type=int, default=20)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    gold, abstain = build(con, args.per_item)
    con.close()

    for name, data in (("gold_retrieval", gold), ("gold_abstain", abstain)):
        with (OUT_DIR / f"{name}.jsonl").open("w", encoding="utf-8") as f:
            for rec in data:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    write_review(gold, abstain, args.review_n, OUT_DIR / "review_sample.md")

    missing_sec = sum(1 for g in gold if not g["gold_section"])
    print(f"Retrieval gold set : {len(gold)}건")
    print(f"Abstain 평가셋      : {len(abstain)}건")
    print(f"섹션 정답 미해결    : {missing_sec}건 (0이어야 정상)")
    print(f"출력: {OUT_DIR}")


if __name__ == "__main__":
    main()
