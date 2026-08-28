"""evalset_pairs.py 의 gold_evidence 규칙 자체검증. 실행: python scripts/test_evalset_evidence.py

정답지는 archive/2026-08-17_baseline/evalset/gold_pair.jsonl 이다 — 2026-08-08 일회성
작업의 산출물로, 규칙이 맞으면 현재 DB에서 슬롯 판정이 그대로 재현돼야 한다.
(쌍 표본 자체는 재현 대상이 아니다: chemical_group_membership 이 8/17 이후 바뀌어
 rng.sample 결과가 달라졌다 — 슬롯 판정 = 물질×섹션 단위라 그 영향을 받지 않는다.)
"""

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from evalset_pairs import (  # noqa: E402
    DB_PATH,
    _heading_block,
    boilerplate_values,
    classify_evidence,
    load,
)

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "archive" / "2026-08-17_baseline" / "evalset" / "gold_pair.jsonl"


def test_heading_block():
    text = "# 제목\n## 피해야 할 물질\n- 금속\n- 물\n## 분해시 생성되는 유해물질\n자극성 가스"
    assert _heading_block(text, "## 피해야 할 물질") == "- 금속\n- 물"
    assert _heading_block(text, "## 없는 헤딩") == ""


def test_archive_slots():
    """8/17 평가셋 8,700 슬롯의 chunk_id/evidence_type/본문/note 전건 대조."""
    con = sqlite3.connect(DB_PATH)
    cas_list, _, _, _, _, sec_chunks, _, sec_texts = load(con, "173")
    con.close()
    bl = boilerplate_values(cas_list, sec_chunks, sec_texts)

    n = 0
    for line in ARCHIVE.open(encoding="utf-8"):
        rec = json.loads(line)
        for want in rec["evidence_detail"]:
            cas = rec["cas_a"] if want["label"] == "A" else rec["cas_b"]
            got = classify_evidence(sec_chunks, sec_texts, bl, cas, want["section"])
            for field in ("chunk_id", "evidence_type", "gold_evidence_text"):
                assert got[field] == want[field], (cas, want["section"], field, got[field], want[field])
            assert got.get("note") == want.get("note"), (cas, want["section"], "note")
            n += 1
        assert rec["gold_evidence"] == sorted(
            classify_evidence(sec_chunks, sec_texts, bl, c, s)["chunk_id"]
            for label, c in (("A", rec["cas_a"]), ("B", rec["cas_b"]))
            for s in (2, 10)
            if classify_evidence(sec_chunks, sec_texts, bl, c, s)["evidence_type"]
            == "HAZARD_CLASSIFICATION"
        ), rec["query_id"]
    assert n == 8700, n
    print(f"  8/17 평가셋 슬롯 {n}건 전건 일치")


if __name__ == "__main__":
    test_heading_block()
    test_archive_slots()
    print("OK")
