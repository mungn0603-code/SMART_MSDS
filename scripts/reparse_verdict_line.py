# -*- coding: utf-8 -*-
"""판정줄 파생 필드를 갱신된 파서로 재계산한다. LLM 호출 없음.

배경: VERDICT_LINE_RE 가 "판정:" 형태만 인식해서 solar-pro3 의 마크다운 헤더
("**판정**" + 줄바꿈 + 판정어) 출력을 놓쳤다. 채점 실행 중에는 옛 파서가 쓰였으므로
stated_verdict / kept_cameo_verdict / tag_body_consistent 를 저장된 답변에서 다시 계산한다.
이 세 필드는 전부 로컬 파생값이라 API 재호출이 필요 없다.

원본은 덮어쓰지 않는다(results/ 규약) — 새 파일로 남긴다.

    python scripts/reparse_verdict_line.py
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
import sys  # noqa: E402

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))

from run_cameo_context_pilot import parse_stated_verdict  # noqa: E402
from run_cameo_full import dedupe_records, load_jsonl  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", type=Path, default=ROOT / "results" / "generation_cameo_full.jsonl")
    ap.add_argument("--eval", type=Path, default=ROOT / "results" / "eval_cameo_full.jsonl")
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "eval_cameo_full_reparsed.jsonl")
    args = ap.parse_args()

    gen = {r["query_id"]: r for r in dedupe_records(load_jsonl(args.gen), "error")}
    ev = dedupe_records(load_jsonl(args.eval), "judge_error")

    before = Counter(r["kept_cameo_verdict"] for r in ev)
    changed = 0
    out = []
    for r in ev:
        g = gen.get(r["query_id"])
        stated = parse_stated_verdict(g.get("generated_answer") if g else None)
        pv = r.get("predicted_verdict")
        cat = r.get("cameo_category") or (g or {}).get("cameo_category")
        new = {
            **r,
            "stated_verdict": stated,
            "kept_cameo_verdict": None if stated is None else (stated == cat),
            "tag_body_consistent": None if pv is None or stated is None else (pv == stated),
        }
        if new["kept_cameo_verdict"] != r.get("kept_cameo_verdict"):
            changed += 1
        out.append(new)

    with args.out.open("w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    after = Counter(r["kept_cameo_verdict"] for r in out)
    print(f"{len(out)}건 재계산, kept_cameo_verdict 변경 {changed}건")
    print(f"  before: {dict(before)}")
    print(f"  after : {dict(after)}")
    print(f"저장: {args.out}")


if __name__ == "__main__":
    main()
