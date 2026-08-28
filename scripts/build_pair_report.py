# -*- coding: utf-8 -*-
"""전체 물질쌍 판정+MSDS(§2·§10) 근거 설명을 단일 HTML 보고서로 만든다.

입력(이미 완료된 전수실행 산출물, 재생성 없음):
  results/generation_cameo_full.jsonl (435쌍×5템플릿=2160건, LLM 설명)
  results/eval_cameo_full.jsonl        (Judge 채점: 정답/faithful/abstain)
출력:
  results/pair_verdict_report.html
"""
import json
from pathlib import Path
from collections import defaultdict, Counter

ROOT = Path(r"C:\Users\mungn\OneDrive\문서\OPEN CODE\MSDS")
gen_path = ROOT / "results" / "generation_cameo_full.jsonl"
eval_path = ROOT / "results" / "eval_cameo_full.jsonl"
out_path = ROOT / "results" / "pair_verdict_report.html"

gen = {}
with open(gen_path, encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        gen[r["query_id"]] = r

ev = {}
with open(eval_path, encoding="utf-8") as f:
    for line in f:
        r = json.loads(line)
        ev[r["query_id"]] = r

pairs = defaultdict(list)
for qid, g in gen.items():
    pairs[(g["cas_a"], g["cas_b"])].append(qid)

rows = []
for (cas_a, cas_b), qids in pairs.items():
    rep_qid = sorted(qids)[0]  # t0 템플릿을 대표 설명으로 사용
    g0 = gen[rep_qid]
    n_total = len(qids)
    n_correct = sum(1 for q in qids if ev.get(q, {}).get("answer_correct"))
    n_faithful = sum(1 for q in qids if ev.get(q, {}).get("faithful"))
    n_abstain = sum(1 for q in qids if ev.get(q, {}).get("abstained"))
    rows.append({
        "cas_a": cas_a, "cas_b": cas_b,
        "name_a": g0["name_a"], "name_b": g0["name_b"],
        "verdict": g0["matrix_verdict"],
        "explanation": g0["generated_answer"],
        "n_total": n_total, "n_correct": n_correct,
        "n_faithful": n_faithful, "n_abstain": n_abstain,
    })

sev = {"Incompatible": 0, "Caution": 1, "Compatible": 2}
rows.sort(key=lambda r: (sev.get(r["verdict"], 9), r["name_a"], r["name_b"]))

print("total pairs:", len(rows))
print(Counter(r["verdict"] for r in rows))
print(rows[0]["name_a"], rows[0]["name_b"], rows[0]["verdict"], rows[0]["n_correct"], "/", rows[0]["n_total"])

import html as _html

VERDICT_LABEL = {"Incompatible": "부적합", "Caution": "주의", "Compatible": "적합"}
VERDICT_CLASS = {"Incompatible": "bad", "Caution": "warn", "Compatible": "ok"}

data_rows = []
for r in rows:
    data_rows.append({
        "a": r["name_a"], "b": r["name_b"],
        "casA": r["cas_a"], "casB": r["cas_b"],
        "verdict": r["verdict"],
        "label": VERDICT_LABEL.get(r["verdict"], r["verdict"]),
        "cls": VERDICT_CLASS.get(r["verdict"], ""),
        "correct": r["n_correct"], "total": r["n_total"],
        "faithful": r["n_faithful"], "abstain": r["n_abstain"],
        "explain": r["explanation"],
    })

n_total = len(rows)
n_correct_all = sum(r["n_correct"] for r in rows)
n_q_all = sum(r["n_total"] for r in rows)
n_faithful_all = sum(r["n_faithful"] for r in rows)
counts = Counter(r["verdict"] for r in rows)
data_json = json.dumps(data_rows, ensure_ascii=False)

HTML_HEAD = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8"/>
<title>SMART-MSDS 물질쌍 판정 보고서</title>
<style>
:root{--bg:#F8FAFC;--surf:#FFFFFF;--bd:#E2E8F0;--tx:#0F172A;--mut:#64748B;
--acc:#2563EB;--bad-bg:#FEF2F2;--bad-tx:#B91C1C;--warn-bg:#FFFBEB;--warn-tx:#92400E;
--ok-bg:#F0FDF4;--ok-tx:#15803D;}
*{box-sizing:border-box;}
body{margin:0;background:var(--bg);color:var(--tx);
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Malgun Gothic",sans-serif;}
.wrap{max-width:1080px;margin:0 auto;padding:28px 20px 60px;}
h1{font-size:1.35rem;margin:0 0 4px;}
.sub{color:var(--mut);font-size:.85rem;margin:0 0 18px;}
.stats{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px;}
.stat{background:var(--surf);border:1px solid var(--bd);border-radius:10px;
padding:10px 16px;min-width:110px;}
.stat b{display:block;font-size:1.15rem;}
.stat span{font-size:.74rem;color:var(--mut);}
.controls{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap;}
input[type=text]{flex:1;min-width:200px;padding:9px 12px;border:1px solid var(--bd);
border-radius:8px;font-size:.9rem;}
select{padding:9px 10px;border:1px solid var(--bd);border-radius:8px;font-size:.9rem;background:#fff;}
"""

HTML_HEAD2 = """
table{width:100%;border-collapse:collapse;background:var(--surf);
border:1px solid var(--bd);border-radius:10px;overflow:hidden;}
th{text-align:left;font-size:.72rem;color:var(--mut);text-transform:uppercase;
letter-spacing:.03em;padding:10px 12px;border-bottom:1px solid var(--bd);}
td{padding:10px 12px;border-bottom:1px solid var(--bd);font-size:.86rem;vertical-align:top;}
tr:last-child td{border-bottom:none;}
tr.pair-row{cursor:pointer;}
tr.pair-row:hover{background:#F8FAFC;}
.badge{display:inline-flex;align-items:center;gap:5px;padding:3px 10px;
border-radius:6px;font-size:.78rem;font-weight:600;}
.badge.bad{background:var(--bad-bg);color:var(--bad-tx);}
.badge.warn{background:var(--warn-bg);color:var(--warn-tx);}
.badge.ok{background:var(--ok-bg);color:var(--ok-tx);}
.score{font-family:ui-monospace,Consolas,monospace;font-size:.8rem;color:var(--mut);}
.score.full{color:var(--ok-tx);}
.score.partial{color:var(--warn-tx);}
.explain{display:none;padding:14px 16px;background:#FBFDFF;border-bottom:1px solid var(--bd);
white-space:pre-wrap;font-size:.84rem;line-height:1.6;}
.explain.open{display:table-cell;}
.pill{font-size:.72rem;color:var(--mut);}
.disc{margin-top:22px;padding:12px 16px;background:#F1F5F9;border-radius:8px;
font-size:.78rem;color:var(--mut);line-height:1.6;}
</style>
</head>
<body>
<div class="wrap">
"""

BODY_TOP = """
<h1>SMART-MSDS 물질쌍 판정 보고서</h1>
<p class="sub">CAMEO 68그룹 판정 + KOSHA MSDS §2·§10 근거 기반 LLM 설명 · 전수실행 결과
(재생성 없음, 2026-08-17 완료본 그대로) · 판정 자체는 CAMEO 매트릭스가 근거이며
LLM은 §2·§10 원문으로 설명만 함</p>
<div class="stats">
<div class="stat"><b>@@TOTAL@@</b><span>전체 물질쌍</span></div>
<div class="stat"><b>@@BAD@@</b><span>부적합(Incompatible)</span></div>
<div class="stat"><b>@@WARN@@</b><span>주의(Caution)</span></div>
<div class="stat"><b>@@OK@@</b><span>적합(Compatible)</span></div>
<div class="stat"><b>@@ACC@@%</b><span>Judge 정답률(질의 @@NQ@@건)</span></div>
<div class="stat"><b>@@FAI@@%</b><span>Faithful 비율</span></div>
</div>
<div class="controls">
<input id="q" type="text" placeholder="물질명 또는 CAS로 검색…"/>
<select id="f">
<option value="">전체 판정</option>
<option value="Incompatible">부적합만</option>
<option value="Caution">주의만</option>
<option value="Compatible">적합만</option>
</select>
</div>
<table>
<thead><tr><th>물질 A</th><th>물질 B</th><th>판정</th><th>정답률</th><th>Faithful</th></tr></thead>
<tbody id="tb"></tbody>
</table>
"""

BODY_BOTTOM = """
<div class="disc">본 보고서의 CAMEO 매트릭스 판정은 [참고자료] 등급이며 단독 최종 판정
근거로 사용하지 않습니다. LLM 설명은 KOSHA MSDS §2(유해성·위험성 분류)·§10(안정성 및
반응성) 원문을 근거로 서술만 하도록 제한했으며, 근거가 불충분하면 Abstain(판단 보류)
처리됩니다. 실험실 배치 전 원문 MSDS와 담당자 확인을 병행하십시오.</div>
</div>
<script id="rowdata" type="application/json">@@DATA_JSON@@</script>
<script>
const rows = JSON.parse(document.getElementById('rowdata').textContent);
const tb = document.getElementById('tb');
function scoreCls(n, total){ return n === total ? 'full' : (n === 0 ? '' : 'partial'); }
function render(list){
  tb.innerHTML = '';
  list.forEach((r, i) => {
    const tr = document.createElement('tr');
    tr.className = 'pair-row';
    tr.innerHTML =
      '<td>' + r.a + ' <span class="pill">(' + r.casA + ')</span></td>' +
      '<td>' + r.b + ' <span class="pill">(' + r.casB + ')</span></td>' +
      '<td><span class="badge ' + r.cls + '">' + r.label + '</span></td>' +
      '<td class="score ' + scoreCls(r.correct, r.total) + '">' + r.correct + '/' + r.total + '</td>' +
      '<td class="score ' + scoreCls(r.faithful, r.total) + '">' + r.faithful + '/' + r.total + '</td>';
    const tr2 = document.createElement('tr');
    const td2 = document.createElement('td');
    td2.colSpan = 5; td2.className = 'explain';
    td2.textContent = r.explain;
    tr2.appendChild(td2);
    tr.addEventListener('click', () => {
      const open = td2.classList.toggle('open');
      td2.style.display = open ? 'table-cell' : 'none';
    });
    tb.appendChild(tr); tb.appendChild(tr2);
  });
}

function applyFilter(){
  const q = document.getElementById('q').value.trim().toLowerCase();
  const f = document.getElementById('f').value;
  const list = rows.filter(r => {
    const matchQ = !q || r.a.toLowerCase().includes(q) || r.b.toLowerCase().includes(q)
      || r.casA.includes(q) || r.casB.includes(q);
    const matchF = !f || r.verdict === f;
    return matchQ && matchF;
  });
  render(list);
}
document.getElementById('q').addEventListener('input', applyFilter);
document.getElementById('f').addEventListener('change', applyFilter);
render(rows);
</script>
</body>
</html>
"""

html_out = (
    HTML_HEAD + HTML_HEAD2 + BODY_TOP
    .replace("@@TOTAL@@", str(n_total))
    .replace("@@BAD@@", str(counts.get("Incompatible", 0)))
    .replace("@@WARN@@", str(counts.get("Caution", 0)))
    .replace("@@OK@@", str(counts.get("Compatible", 0)))
    .replace("@@ACC@@", f"{100*n_correct_all/n_q_all:.1f}")
    .replace("@@NQ@@", str(n_q_all))
    .replace("@@FAI@@", f"{100*n_faithful_all/n_q_all:.1f}")
    + BODY_BOTTOM.replace("@@DATA_JSON@@", data_json.replace("</", "<\\/"))
)

out_path.write_text(html_out, encoding="utf-8")
print("written:", out_path, len(html_out), "chars")
