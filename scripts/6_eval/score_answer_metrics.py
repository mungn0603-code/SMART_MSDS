"""본문 기준 지표를 이미 나온 결과 파일에 사후 계산해 비교한다 (LLM 호출 없음).

왜 필요한가 (2026-08-29)
  근거를 검색 top-10에서 CAS 직접조회로 바꾸자 `substance_confused`가 0%가 됐다.
  그런데 이 지표는 **인용된 chunk_id의 소속**만 검사하므로, 컨텍스트에 그 쌍 청크만
  넣으면 남의 물질을 인용할 방법 자체가 없어진다 — 0%는 측정 결과가 아니라 구조가
  강제한 값이다. 성과지표로 쓸 수 없다.

  그래서 답변 **본문**을 직접 보는 지표를 따로 잰다:
    answer_offpair_substance : 근거에도 없는 쌍 밖 물질명이 본문에 나왔는가
    cited_both_substances    : A와 B 양쪽 근거를 인용했는가
  둘 다 규칙 기반이라 LLM 호출이 없고, 기존 산출물만으로 계산된다(재생성 불필요).

  `substance_confused`는 지우지 않는다 — **retrieval 오염 지표**로는 여전히 유효하다.

  python scripts/score_answer_metrics.py
  python scripts/score_answer_metrics.py --runs frozen=eval_cameo_full.jsonl,...
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "src"))

import eval_generation as EG  # noqa: E402

DB_PATH = ROOT / "data" / "reactivity_reference.db"
RESULTS = ROOT / "results"
# (라벨, 생성 결과, 채점 결과) — 기본은 frozen(검색 top-10) vs pair(CAS 직접조회)
DEFAULT_RUNS = [
    ("frozen(검색 top-10)", "generation_cameo_full.jsonl", "eval_cameo_full.jsonl"),
    ("pair(CAS 직접조회)", "generation_cameo_full_pair.jsonl", "eval_cameo_full_pair.jsonl"),
]


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def score(gen_path: Path, eval_path: Path, table: dict[str, str],
          names_by_cas: dict[str, set[str]], chunk_text: dict[str, str],
          only_ids: set[str] | None = None) -> dict:
    gens = {r["query_id"]: r for r in load_jsonl(gen_path) if not r.get("error")}
    evals = {r["query_id"]: r for r in load_jsonl(eval_path)}
    out = Counter()
    leaked_by_cas = Counter()
    samples = []
    match: dict[str, bool] = {}   # qid -> judge 재분류가 matrix 와 일치했는가(짝지은 비교용)
    for qid, g in gens.items():
        e = evals.get(qid)
        if e is None or (only_ids is not None and qid not in only_ids):
            continue
        out["n"] += 1
        mv, pv = e.get("matrix_verdict"), e.get("predicted_verdict")
        match[qid] = pv == mv
        out["n_" + str(mv)] += 1
        out["match_" + str(mv)] += pv == mv
        # 안전 임계 방향: 위험한 조합을 안전하다고 읽은 건
        out["under_safe"] += mv != "Compatible" and pv == "Compatible"
        # 근거 = MSDS 청크 + CAMEO 컨텍스트(영문 원문에 생성 가스가 들어있다)
        texts = [chunk_text.get(c, "") for c in (g.get("context_ids") or [])]
        texts.append(g.get("cameo_context") or "")
        offpair, leaked = EG.answer_offpair_substance(g, texts, table, names_by_cas)
        if offpair is None:
            out["offpair_none"] += 1
        else:
            out["offpair"] += offpair
            leaked_by_cas.update(leaked)
            if offpair and len(samples) < 5:
                samples.append((qid, g["name_a"], g["name_b"], sorted(leaked)))
        cov = EG.citation_coverage(g, e)
        if cov is None:
            out["cited_none"] += 1
        else:
            out["sec2_" + cov["sec2"]] += 1
            out["sec10_" + cov["sec10"]] += 1
            out["sec2_one"] += cov["sec2"] in ("a_only", "b_only")
        out["faithful"] += e.get("faithful") in (True, "true")
        out["judge_match"] += e.get("predicted_verdict") == e.get("matrix_verdict")
        sc = e.get("substance_confused")
        out["substance_confused"] += sc is True
        out["substance_confused_none"] += sc is None
    return {"counts": out, "leaked": leaked_by_cas, "samples": samples, "match": match}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", help="라벨=생성파일:채점파일 을 쉼표로 (미지정시 frozen vs pair)")
    ap.add_argument("--corpus-tag", default="service")
    ap.add_argument("--ids", help="이 query_id 목록(줄당 1개)만 채점 — 두 실행을 같은 문항에서 비교")
    args = ap.parse_args()

    runs = DEFAULT_RUNS
    if args.runs:
        runs = []
        for item in args.runs.split(","):
            label, files = item.split("=", 1)
            gen, ev = files.split(":", 1)
            runs.append((label, gen, ev))

    con = sqlite3.connect(DB_PATH)
    table, names_by_cas = EG.substance_name_table(con, args.corpus_tag)
    chunk_text = dict(con.execute(
        "select chunk_id, text from rag_chunks where granularity='section'"))
    covered = len(set(table.values()))
    con.close()
    print(f"물질명 표기 {len(table)}개 / 커버 {covered}종 "
          f"(1~2자 이름은 조사·일반명사와 구분 불가라 제외 — 이 지표는 하한값)")

    only_ids = None
    if args.ids:
        only_ids = {x.strip() for x in Path(args.ids).read_text(encoding="utf-8").splitlines() if x.strip()}
        print(f"대상 제한: {args.ids} ({len(only_ids)}건)")

    results = []
    for label, gen, ev in runs:
        gp, ep = RESULTS / gen, RESULTS / ev
        if not (gp.exists() and ep.exists()):
            print(f"[건너뜀] {label}: {gp.name} 또는 {ep.name} 없음")
            continue
        results.append((label, score(gp, ep, table, names_by_cas, chunk_text, only_ids)))

    hdr = f"{'지표':30s}" + "".join(f"{lab:>24s}" for lab, _ in results)
    print("\n" + hdr)
    print("-" * len(hdr))
    rows = [
        ("answer_offpair_substance", "offpair", "n"),
        ("§2 양쪽 인용", "sec2_both", "n"),
        ("  §2 한쪽만", "sec2_one", "n"),
        ("  §2 아예 없음", "sec2_none", "n"),
        ("§10 양쪽 인용", "sec10_both", "n"),
        ("faithful", "faithful", "n"),
        ("judge 재분류 일치", "judge_match", "n"),
        ("  Compatible 칸", "match_Compatible", "n_Compatible"),
        ("  Caution 칸", "match_Caution", "n_Caution"),
        ("  Incompatible 칸", "match_Incompatible", "n_Incompatible"),
        ("위험->안전 오독(안전임계)", "under_safe", "n"),
        ("substance_confused(오염지표)", "substance_confused", "n"),
    ]
    for name, key, denom in rows:
        line = f"{name:30s}"
        for _, r in results:
            c = r["counts"]
            line += f"{c[key]:>10d} ({c[key] / c[denom]:>6.1%})"
        print(line)
    line = f"{'  측정불가(인용 없음)':30s}"
    for _, r in results:
        line += f"{r['counts']['cited_none']:>19d}    "
    print(line)

    if len(results) == 2:
        (la, ra), (lb, rb) = results
        common = sorted(set(ra["match"]) & set(rb["match"]))
        cell = Counter((ra["match"][q], rb["match"][q]) for q in common)
        fixed, broke = cell[(False, True)], cell[(True, False)]
        print()
        print(f"짝지은 비교 (공통 {len(common)}건)  행={la} 열={lb}")
        print(f"{'':>14s}{'맞음':>10s}{'틀림':>10s}")
        for a in (True, False):
            print(f"{'맞음' if a else '틀림':>14s}{cell[(a, True)]:>10d}{cell[(a, False)]:>10d}")
        print(f"  {lb} 가 고친 건 {fixed} / 새로 틀린 건 {broke} (순증 {fixed - broke:+d})")

    for label, r in results:
        print(f"\n[{label}] 본문에 새어나온 물질 상위:",
              [f"{c}×{k}" for c, k in r["leaked"].most_common(5)])
        for s in r["samples"][:3]:
            print("   샘플:", s)


if __name__ == "__main__":
    main()
