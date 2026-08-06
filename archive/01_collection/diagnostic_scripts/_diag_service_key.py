# -*- coding: utf-8 -*-
"""
KOSHA_SERVICE_KEY 403(SERVICE_KEY_IS_NOT_REGISTERED_ERROR) 원인 진단.

절대 원칙: 서비스키 원문은 어떤 경우에도 print/log 하지 않는다.
길이, 앞뒤 공백/따옴표 여부, '%' 포함 여부, sha256 해시(비교용, 역산 불가) 만 출력.

사용법:
  python _diag_service_key.py
  (선택) Decoding 버전 키도 같이 테스트하려면 .env에 KOSHA_SERVICE_KEY_DECODING=... 추가
"""
import hashlib
import os
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
BASE_URL = "https://apis.data.go.kr/B552468/msdschem"
TEST_CAS = "64-17-5"


def read_raw_env_value(path, key):
    """.env에서 key의 '가공 전' 원문 값을 반환 (strip 없이, 있는 그대로)."""
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line_nolf = line.rstrip("\n").rstrip("\r")
            if line_nolf.strip().startswith("#") or "=" not in line_nolf:
                continue
            k, v = line_nolf.split("=", 1)
            if k.strip() == key:
                return v  # strip 하지 않은 원문 그대로 반환
    return None


def describe(label, raw_value):
    """값 자체는 절대 출력하지 않고 메타데이터만 출력."""
    if raw_value is None:
        print(f"[{label}] .env에 없음")
        return None
    h = hashlib.sha256(raw_value.encode("utf-8")).hexdigest()[:12]
    print(f"[{label}] len={len(raw_value)} "
          f"leading_ws={raw_value != raw_value.lstrip()} "
          f"trailing_ws={raw_value != raw_value.rstrip()} "
          f"has_quote={'\"' in raw_value or chr(39) in raw_value} "
          f"has_percent={'%' in raw_value} "
          f"has_plus={'+' in raw_value} "
          f"sha256_12={h}")
    return raw_value.strip().strip('"').strip("'")


def call_get_chem_list(service_key, pre_encoded):
    """
    pre_encoded=False: urllib.parse.urlencode()로 정상 인코딩 (Decoding 버전 키에 맞음)
    pre_encoded=True : serviceKey를 인코딩 없이 URL에 그대로 삽입 (Encoding 버전 키를 이중인코딩하지 않기 위함)
    """
    params = {"searchWrd": TEST_CAS, "searchCnd": 1, "numOfRows": 5, "pageNo": 1}
    if pre_encoded:
        query = urllib.parse.urlencode(params) + f"&serviceKey={service_key}"
    else:
        params["serviceKey"] = service_key
        query = urllib.parse.urlencode(params)
    url = f"{BASE_URL}/getChemList?{query}"

    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            status = resp.status
            body = resp.read()
    except urllib.error.HTTPError as e:
        status = e.code
        body = e.read()
    except Exception as e:
        return f"요청 실패: {type(e).__name__}: {e}"

    try:
        root = ET.fromstring(body)
        result_code = root.findtext("./header/resultCode") or root.findtext("./cmmMsgHeader/returnReasonCode")
        result_msg = (root.findtext("./header/resultMsg")
                      or root.findtext("./cmmMsgHeader/returnAuthMsg")
                      or root.findtext("./cmmMsgHeader/errMsg"))
        n_items = len(root.findall("./body/items/item"))
        return f"HTTP {status} resultCode={result_code} msg={result_msg} items={n_items}"
    except ET.ParseError:
        snippet = body[:200].decode("utf-8", errors="replace")
        return f"HTTP {status} XML 파싱 실패, 응답 앞부분: {snippet!r}"


def main():
    print("=== 1) .env 원문 메타데이터 ===")
    raw_enc = read_raw_env_value(ENV_PATH, "KOSHA_SERVICE_KEY")
    clean_enc = describe("KOSHA_SERVICE_KEY (encoding 버전으로 추정)", raw_enc)

    raw_dec = read_raw_env_value(ENV_PATH, "KOSHA_SERVICE_KEY_DECODING")
    clean_dec = describe("KOSHA_SERVICE_KEY_DECODING (선택, decoding 버전)", raw_dec)

    if clean_enc is None:
        print("\nKOSHA_SERVICE_KEY가 .env에 없습니다. 중단합니다.")
        return

    print("\n=== 2) API 호출 테스트 (getChemList, CAS 64-17-5) ===")

    print("\n[테스트 A] 현재 collector 로직: '%' 있으면 unquote() 후 urlencode()")
    key_a = urllib.parse.unquote(clean_enc) if "%" in clean_enc else clean_enc
    print("  결과:", call_get_chem_list(key_a, pre_encoded=False))

    print("\n[테스트 B] .env 원문을 가공 없이 그대로 urlencode() (이중인코딩 가능성 있음)")
    print("  결과:", call_get_chem_list(clean_enc, pre_encoded=False))

    print("\n[테스트 C] .env 원문(Encoding 버전 가정)을 인코딩 없이 URL에 그대로 삽입")
    print("  결과:", call_get_chem_list(clean_enc, pre_encoded=True))

    if clean_dec:
        print("\n[테스트 D] KOSHA_SERVICE_KEY_DECODING 값을 urlencode()로 정상 인코딩")
        print("  결과:", call_get_chem_list(clean_dec, pre_encoded=False))
    else:
        print("\n[테스트 D] 건너뜀 - .env에 KOSHA_SERVICE_KEY_DECODING 없음")
        print("  (data.go.kr 마이페이지에서 Decoding 버전 키를 복사해 .env에 추가하면 테스트 가능)")

    print("\n=== 진단 끝 ===")
    print("resultCode=00 또는 items>0 이 나온 테스트가 정답 키/인코딩 방식입니다.")


if __name__ == "__main__":
    main()
