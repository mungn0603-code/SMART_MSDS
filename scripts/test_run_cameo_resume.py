# -*- coding: utf-8 -*-
"""run_cameo_full 재개 로직 자가검증. API 호출 없음.

지키려는 성질(2026-08-29 Upstage 전환 시 도입):
  - 실패 레코드는 '완료'로 치지 않는다 -> 같은 명령 재실행 시 그 건만 재시도된다.
  - 재시도로 같은 query_id 가 여러 줄이 되어도 소비 시 성공본 하나만 남는다.

    python scripts/test_run_cameo_resume.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "src"))

import run_cameo_full as RC  # noqa: E402


def write(rows: list[dict]) -> Path:
    f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8")
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
    f.close()
    return Path(f.name)


def test_already_done_skips_failures():
    p = write([
        {"query_id": "ok1", "error": None},
        {"query_id": "boom", "error": "HTTPError: 429"},
        {"query_id": "empty", "error": "EmptyAnswer: finish_reason=length"},
        {"query_id": "ok2", "error": None},
    ])
    assert RC.already_done(p, "error") == {"ok1", "ok2"}, "실패 건이 완료로 잡혔다"
    p.unlink()


def test_already_done_judge_field():
    p = write([
        {"query_id": "j1", "judge_error": None},
        {"query_id": "j2", "judge_error": "JSONDecodeError: ..."},
    ])
    assert RC.already_done(p, "judge_error") == {"j1"}
    p.unlink()


def test_already_done_missing_file():
    assert RC.already_done(Path("__no_such_file__.jsonl"), "error") == set()


def test_dedupe_prefers_success():
    rows = [
        {"query_id": "a", "error": "HTTPError: 429", "v": 1},   # 1차 실패
        {"query_id": "a", "error": None, "v": 2},               # 재시도 성공
        {"query_id": "b", "error": None, "v": 3},
        {"query_id": "c", "error": "boom", "v": 4},             # 끝내 실패
    ]
    out = {r["query_id"]: r for r in RC.dedupe_records(rows, "error")}
    assert len(out) == 3, f"중복이 안 접혔다: {len(out)}"
    assert out["a"]["v"] == 2, "성공본이 아니라 실패본이 남았다"
    assert out["b"]["v"] == 3
    assert out["c"]["error"] == "boom", "끝내 실패한 건은 실패본이 남아야 한다"


def test_dedupe_keeps_first_success():
    """성공이 두 줄이면 앞엣것을 유지한다(뒤엣것으로 덮어쓰지 않는다)."""
    rows = [{"query_id": "a", "error": None, "v": 1}, {"query_id": "a", "error": None, "v": 2}]
    assert RC.dedupe_records(rows, "error")[0]["v"] == 1


def test_pair_chunk_ids():
    """pair 모드 컨텍스트: gold_evidence 를 전건 포함하고 순서가 결정적이어야 한다.

    인용 번호([근거 n])가 이 순서에 대응하므로 순서가 흔들리면 물질혼동 지표가 깨진다.
    """
    import sqlite3

    db = HERE.parent / "data" / "reactivity_reference.db"
    frozen = HERE.parent / "results" / "frozen_retrieval_top10.jsonl"
    if not (db.exists() and frozen.exists()):
        print("  skip test_pair_chunk_ids (DB 또는 frozen 파일 없음)")
        return
    con = sqlite3.connect(db)
    cur = con.cursor()
    rows = RC.load_jsonl(frozen)
    miss = []
    for r in rows:
        cids = RC.pair_chunk_ids(cur, r["cas_a"], r["cas_b"])
        assert cids == RC.pair_chunk_ids(cur, r["cas_a"], r["cas_b"]), "순서가 비결정적"
        gold = set(r["gold_evidence"])
        if gold and not gold <= set(cids):
            miss.append(r["query_id"])
    con.close()
    assert not miss, f"gold 누락 {len(miss)}건: {miss[:3]}"


def main() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
