# -*- coding: utf-8 -*-
import os
p = r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS\.env"
print("exists:", os.path.exists(p))
with open(p, encoding="utf-8-sig") as f:
    raw = f.read()
lines = raw.splitlines()
print(len(lines), "lines total")
for line in lines:
    if not line.strip():
        print("(blank)")
    elif line.strip().startswith("#"):
        print(line)
    elif "=" in line:
        k, v = line.split("=", 1)
        print(f"{k.strip()} = <len={len(v.strip())}, has_percent={'%' in v}>")
    else:
        print(repr(line))
