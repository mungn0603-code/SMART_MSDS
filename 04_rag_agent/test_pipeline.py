"""pipeline.py 자체검증. 실행: python 04_rag_agent/test_pipeline.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline import (  # noqa: E402
    MAX_CHARS,
    dominant_grade,
    evidence_grade,
    normalize_detail,
    recursive_split,
)


def test_normalize():
    # 단위 호환문자 NFKC 정규화 + ※출처 분리
    body, src, nd = normalize_detail("82~84 ℃  |   ※출처 : IPCS")
    assert body == "82~84 °C", body
    assert src == ["IPCS"], src
    assert nd is False

    # ㎩/㎖/㎎ 도 NFKC 로 풀려야 함
    body, _, _ = normalize_detail("20 ㎩ (30℃) ")
    assert body == "20 Pa (30°C)", body
    body, _, _ = normalize_detail("225 g/100㎖ (20℃) |   ※출처 : CHemIDplus")
    assert body == "225 g/100ml (20°C)", body  # NFKC(㎖) == 'ml'

    # '|' 다중값 -> 불릿 리스트
    body, _, _ = normalize_detail("열|충격|마찰")
    assert body == "- 열\n- 충격\n- 마찰", body

    # 그림문자 파일명 -> 코드+한글명
    body, _, _ = normalize_detail("GHS06.gif|GHS08.gif")
    assert body == "- GHS06(급성독성)\n- GHS08(건강유해성)", body

    # 무자료 변종 전부 동일 처리
    for raw in ("자료없음", "(자료 없음.)", "(없음)", "(해당 안됨)", "(해당 없음)", "- / -"):
        body, _, nd = normalize_detail(raw)
        assert nd is True, raw
        assert body == "자료없음", (raw, body)

    # NULL 은 무자료가 아니라 '값 없는 구조상 상위노드'
    body, _, nd = normalize_detail(None)
    assert body == "" and nd is False

    # 값과 무자료가 섞이면 무자료 항목만 탈락
    body, _, nd = normalize_detail("고체|자료없음|노란색")
    assert nd is False and body == "- 고체\n- 노란색", body

    # CAS 표기 정규화
    body, _, _ = normalize_detail("67 - 64 - 1")
    assert body == "67-64-1", body


def test_evidence_grade():
    assert evidence_grade(2, []) == "Mandatory"
    assert evidence_grade(9, []) == "Recommended"
    assert evidence_grade(9, ["HSDB"]) == "Reference"
    assert evidence_grade(10, ["ECHA"]) == "Reference"
    assert dominant_grade(["Reference", "Recommended"]) == "Recommended"
    assert dominant_grade(["Reference", "Mandatory", "Recommended"]) == "Mandatory"


def test_recursive_split():
    short = "가" * 100
    assert recursive_split(short) == [short]

    text = "\n".join(f"## 항목{i}\n" + "가" * 300 for i in range(10))
    parts = recursive_split(text)
    assert len(parts) > 1
    assert all(len(p) <= MAX_CHARS for p in parts), [len(p) for p in parts]
    # 무손실 분할: 이어붙이면 원문과 완전히 같아야 함 (구분자 유실 금지)
    assert "".join(parts) == text

    # 구분자가 전혀 없는 초장문도 상한을 넘기지 않음
    parts = recursive_split("가" * (MAX_CHARS * 2 + 7))
    assert all(len(p) <= MAX_CHARS for p in parts)
    assert sum(len(p) for p in parts) == MAX_CHARS * 2 + 7


if __name__ == "__main__":
    test_normalize()
    test_evidence_grade()
    test_recursive_split()
    print("OK: pipeline self-check passed")
