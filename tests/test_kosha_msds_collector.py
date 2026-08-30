# -*- coding: utf-8 -*-
"""
kosha_msds_collector.py의 XML 파서 로직 검증 (실제 API 키 없이 실행 가능)
- KOSHA 공식 Swagger 스키마를 그대로 반영한 가상 응답으로 테스트
- 쿼터를 쓰지 않고 파싱 버그를 사전에 잡기 위한 용도
"""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "1_collect"))
from kosha_msds_collector import parse_chem_list, parse_chem_detail

FAKE_CHEM_LIST_XML = """<response>
<header><resultCode>00</resultCode><resultMsg>NORMAL SERVICE.</resultMsg></header>
<body>
<items>
<item>
<lastDate>2021-03-15</lastDate>
<casNo>64-17-5</casNo>
<chemId>12345</chemId>
<chemNameKor>에탄올</chemNameKor>
<enNo></enNo><keNo></keNo><unNo>1170</unNo>
<openYn>Y</openYn><koshaConfirm>Y</koshaConfirm>
</item>
</items>
<numOfRows>5</numOfRows><pageNo>1</pageNo>
</body>
</response>"""


FAKE_CHEM_DETAIL_XML = """<response>
<header><resultCode>00</resultCode><resultMsg>NORMAL SERVICE.</resultMsg></header>
<body>
<items>
<item>
<msdsItemNameKor>그림문자</msdsItemNameKor>
<msdsItemNo>나</msdsItemNo>
<itemDetail>인화성</itemDetail>
<lev>2</lev>
<msdsItemCode>201</msdsItemCode>
<upMsdsItemCode>200</upMsdsItemCode>
<ordrIdx>3</ordrIdx>
</item>
<item>
<msdsItemNameKor>보건(NFPA)</msdsItemNameKor>
<msdsItemNo>다</msdsItemNo>
<itemDetail>2</itemDetail>
<lev>1</lev>
<msdsItemCode>210</msdsItemCode>
<upMsdsItemCode></upMsdsItemCode>
<ordrIdx>7</ordrIdx>
</item>
</items>
</body>
</response>"""


def test_parse_chem_list_match():
    root = ET.fromstring(FAKE_CHEM_LIST_XML)
    found = parse_chem_list(root, "64-17-5")
    assert found is not None, "일치하는 CAS를 찾지 못함"
    assert found["chem_id"] == "12345"
    assert found["chem_name_kor"] == "에탄올"
    print("[PASS] parse_chem_list 일치 케이스")


def test_parse_chem_list_no_match():
    root = ET.fromstring(FAKE_CHEM_LIST_XML)
    found = parse_chem_list(root, "999-99-9")
    assert found is None, "존재하지 않는 CAS인데 값이 반환됨"
    print("[PASS] parse_chem_list 불일치(Abstain) 케이스")


def test_parse_chem_detail():
    root = ET.fromstring(FAKE_CHEM_DETAIL_XML)
    rows = parse_chem_detail(root)
    assert len(rows) == 2, f"행 개수 불일치: {len(rows)}"
    assert rows[0]["item_name_kor"] == "그림문자"
    assert rows[0]["ordr_idx"] == "3"
    assert rows[1]["item_no"] == "다"
    assert rows[1]["up_msds_item_code"] is None or rows[1]["up_msds_item_code"] == ""
    print("[PASS] parse_chem_detail EAV 파싱 (2행)")


if __name__ == "__main__":
    test_parse_chem_list_match()
    test_parse_chem_list_no_match()
    test_parse_chem_detail()
    print("\n전체 통과: API 키 없이도 파서 로직 정상 확인됨")
