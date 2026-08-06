import py_compile

path = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\01_collection\kosha_msds_collector.py"
py_compile.compile(path, doraise=True)
print("컴파일 성공: 문법 오류 없음")

with open(path, encoding="utf-8") as f:
    lines = f.readlines()
print("총 라인수:", len(lines))

# 함수 정의 목록 및 중복 여부 확인
import re
defs = [l.strip() for l in lines if re.match(r"^def ", l.strip())]
print("정의된 함수:", defs)
print("중복 함수명 여부:", len(defs) != len(set(defs)))
