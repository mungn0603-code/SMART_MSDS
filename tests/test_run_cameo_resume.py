# -*- coding: utf-8 -*-
"""run_cameo_full 재개 로직 자가검증. API 호출 없음.

지키려는 성질(2026-08-29 Upstage 전환 시 도입):
  - 실패 레코드는 '완료'로 치지 않는다 -> 같은 명령 재실행 시 그 건만 재시도된다.
  - 재시도로 같은 query_id 가 여러 줄이 되어도 소비 시 성공본 하나만 남는다.

    python tests/test_run_cameo_resume.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts" / "5_generation"))
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


def test_verdict_is_never_model_output():
    """불변식: LLM 은 설명하고, 코드가 판정한다.

    v8 에서 verdict 를 스키마 필드로 두고 "CAMEO 판정을 그대로 옮기라"고 시켰더니
    1,922건 중 20건(1.04%)에서 판정이 뒤집혔고 18건이 위험을 낮추는 방향이었다
    (archive/2026-08-29_generation_prompt_history/_v8_verdict_regression/FINDING.md). 이 테스트는 그 설계로 되돌아가는 것을 막는다.
    """
    import run_cameo_context_pilot as P

    assert "verdict" not in P.PAIR_SCHEMA["properties"], \
        "verdict 가 스키마에 있다 - 판정을 모델에게 묻고 있다"
    assert "verdict" not in P.PAIR_SCHEMA["required"]

    # 모델 출력에 verdict 가 섞여 들어와도 코드가 넘긴 값이 이긴다.
    obj = {"hazard_basis": "H", "substance_a_note": "A", "substance_b_note": "B",
           "precaution": "", "evidence_gap": "", "cited": [1],
           "verdict": "Compatible"}  # 오염된 모델 출력을 가정
    out = P.render_answer(obj, "A물질", "B물질", "Incompatible")
    assert out.startswith("판정: Incompatible"), out[:60]
    assert "함께 취급·보관해서는 안 되는 조합입니다." in out
    assert "가능한 조합입니다" not in out


def test_conclusion_matches_verdict():
    """결론 문장은 판정에서 결정된다 - 누락도 오용도 구조적으로 불가능하다."""
    import run_cameo_context_pilot as P

    assert P.render_conclusion("Caution", "산과 접촉할 때") == \
        "분리보관이 필수인 조합은 아니나, 산과 접촉할 때 주의가 필요합니다."
    assert P.render_conclusion("Caution", "") == \
        "분리보관이 필수인 조합은 아니나 취급 시 주의가 필요합니다."
    assert "안 되는 조합" in P.render_conclusion("Incompatible", "무시됨")
    assert "가능한 조합" in P.render_conclusion("Compatible", "무시됨")
    # 판정별 문장이 서로 섞이지 않는다
    for v in ("Compatible", "Caution", "Incompatible", "Abstain"):
        c = P.render_conclusion(v, "가열될 때")
        others = [P.render_conclusion(o, "") for o in
                  ("Compatible", "Caution", "Incompatible", "Abstain") if o != v]
        assert all(not c.startswith(x[:15]) for x in others), (v, c)


def test_schema_prompt_contract():
    """스키마 프롬프트가 6개 필드를 전부 지시하는가 + 앱의 자유텍스트 경로가 살아 있는가.

    v9 에서 SCHEMA_PROMPT 를 SYSTEM_PROMPT 슬라이스에서 독립시켰다. 필드명을 하나라도
    빠뜨리면 모델이 그 필드를 빈 값으로 채우고, 그건 실행 전에는 안 보인다.
    SYSTEM_PROMPT 쪽은 app/streamlit_app.py 가 import 해 쓰는 라이브 경로라 같이 지킨다.
    프롬프트 문구 자체는 assert 하지 않는다 - 개정할 때마다 깨져서 쓸모가 없다.
    """
    import run_cameo_context_pilot as P

    missing = [f for f in P.PAIR_SCHEMA["properties"] if f not in P.SCHEMA_PROMPT]
    assert not missing, f"스키마 필드가 프롬프트에 없다: {missing}"
    assert "[출력 형식]" in P.SYSTEM_PROMPT, "자유텍스트 출력 형식 지시가 사라졌다(앱 경로)"
    assert P.SCHEMA_PROMPT_VERSION != P.PROMPT_VERSION


def main() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"  ok  {t.__name__}")
    print(f"{len(tests)} passed")


if __name__ == "__main__":
    main()
