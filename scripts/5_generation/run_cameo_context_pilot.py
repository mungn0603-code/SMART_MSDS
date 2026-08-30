"""CAMEO metadata + MSDS evidence를 Generation context에 함께 넣었을 때 LLM 행동 확인용 파일럿.

cameo_group_lookup.lookup()로 CAS 쌍의 CAMEO 판정(이미 2,160건 전수에서 matrix_verdict와
100% 일치 검증됨)을 조회해 프롬프트에 "이미 결정된 판정"으로 박아 넣고, LLM에게는 그
판정을 재판정하지 말고 MSDS §2/§10 근거로 설명만 하게 한다. 새 evaluator는 안 만들고
eval_generation.py의 rule_based()/judge()를 그대로 재사용, substance_confused 체크는
run_v2_pilot.py 것을 재사용한다.

13건 혼합 샘플(물질 혼동 4 / 개별위험→상호반응 비약 4 / 정상 Compatible 3 / 정상
Caution·Incompatible 2)에 대해서만 실행한다.

  python 04_rag_agent/run_cameo_context_pilot.py
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
import time
from pathlib import Path

# 2026-08-29: solar-pro3 는 "판정:" 대신 마크다운 볼드 헤더 다음 줄에 판정어를 쓰는 일이
# 많다. 종전 정규식은 콜론을 요구해 2,240건 중 150건을 놓쳤다(판정 자체는 정확히 명시됨).
# 콜론/볼드/줄바꿈을 모두 허용하도록 넓혔다 — 둘 다 매칭되는 건에서 결과가 달라지는
# 사례는 0건이라 해석 변경이 아니라 순수 recall 개선이다(93.3% -> 99.8%).
VERDICT_LINE_RE = re.compile(r"판정\**\s*[:：]?\s*\**\s*(Compatible|Caution|Incompatible)", re.IGNORECASE)


def parse_stated_verdict(answer: str) -> str | None:
    m = VERDICT_LINE_RE.search(answer or "")
    return m.group(1) if m else None

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))

import llm as L  # noqa: E402
import generate_baseline as GB  # noqa: E402
import eval_generation as EV  # noqa: E402
import cameo_group_lookup as CL  # noqa: E402
from eval_generation import substance_confused  # noqa: E402

FROZEN_PATH = ROOT / "results" / "frozen_retrieval_top10.jsonl"
GEN_OUT = ROOT / "results" / "generation_cameo_pilot_v4.jsonl"
EVAL_OUT = ROOT / "results" / "eval_cameo_pilot_v4.jsonl"

PROMPT_VERSION = "cameo_service_v7"  # v6 + 판정별 결론 문장 · 위험 표현 강도 보존

# v3(과장 금지 위주, CATEGORY_REASON 뭉뚱그린 정보만 제공)까지는 파일럿 실행 전.
# v4는 사용자가 직접 작성한 프롬프트로 전략이 다르다 — 정보를 숨기는 대신
# cameo_group_lookup.format_context(..., detailed=True)로 CAMEO의 실제 hazard
# code/gas product/reason 원문을 그대로 노출하되, "번역만 허용, 의미 강화 금지"라는
# 명시적 변환 규칙(예: "Generates heat" -> "열을 발생시킬 수 있음", 폭발로 확대 금지)으로
# 과장을 막는다. 길이는 사용자가 "너무 오래 걸리면 요약 가능"이라고 명시해 핵심 규칙만
# 남기고 8항목 최종검증 체크리스트는 짧게 축약했다.
# v5 변경: v4 전수실행(2,142건) 결과 faithful 90.5%(203건 unfaithful)까지 확인됨.
# 잔여 203건을 표본 확인한 결과 전부 같은 패턴 — CAMEO reason은 두 물질이 속한
# "반응성 그룹" 간의 분류적 위험 특성인데, 답변이 이를 "두 물질이 실제로/확인된 반응을
# 일으킨다"처럼 이 특정 쌍에서 관찰된 사실인 양 확언함(예: "두 물질이 실제로 반응하여
# 수소 불화수소 가스를 발생시킨다는 구체적 근거가 없음"). 규칙3에 이 구분을 명시한다.
SYSTEM_PROMPT = (
    "당신은 화학물질 안전정보를 설명하는 시스템이다.\n"
    "입력으로 제공되는 CAMEO 판정·위험정보와 각 물질의 MSDS 정보를 바탕으로 두 물질\n"
    "조합이 왜 해당 판정을 받았는지 한국어로 설명하라. 핵심은 화학적으로 그럴듯한 설명을\n"
    "새로 만드는 것이 아니라, 제공된 근거를 정확하게 해석해 전달하는 것이다.\n"
    "\n"
    "[1. 판정] 입력된 CAMEO 판정(Compatible/Caution/Incompatible)을 그대로 사용한다.\n"
    "재계산·변경하지 않는다. 두 물질의 개별 MSDS 위험정보만으로 판정을 재추론하지 않는다.\n"
    "\n"
    "[2. 위험 이유 설명 — 가장 중요] CAMEO의 reason/hazard code/gas products를 적극\n"
    "활용해 설명한다. 자연스러운 한국어로 옮기는 것은 허용하되 원본보다 강한 의미로\n"
    "확대하지 않는다.\n"
    "예: \"Generates heat\" -> 허용: \"열을 발생시킬 수 있어 주의가 필요합니다.\"\n"
    "    금지: \"격렬한 발열로 화재나 폭발이 발생할 수 있습니다.\"(입력에 없는 화재·폭발을 추가)\n"
    "\n"
    "[3. 화학적 추론 금지] 입력 context에 명시되지 않은 반응 메커니즘·반응식·생성물·\n"
    "생성 가스·반응 속도·발열량·온도 조건·화재/폭발 가능성·독성 생성물·산화환원 등 구체적\n"
    "반응 유형을 새로 추론하지 않는다. 특히 \"A는 산화성, B는 가연성이니 산화환원 반응으로\n"
    "화재가 난다\"처럼 두 물질의 개별 위험정보를 쌍별 반응성의 증거로 쓰지 않는다.\n"
    "\n"
    "[3-1. 그룹 분류 vs 확인된 반응 — 반드시 구분] CAMEO reason은 두 물질이 속한\n"
    "반응성 그룹끼리의 분류적 위험 특성이지, 이 두 특정 물질 사이에서 실제로 관찰·확인된\n"
    "반응이 아니다. \"두 물질이 실제로 반응하여 ~가 발생한다\", \"접촉 시 ~반응이 확인된다\"처럼\n"
    "단정적으로 서술하지 말고, CAMEO 분류에 근거한 것임을 표현에 남긴다.\n"
    "나쁜 예: \"두 물질이 실제로 반응하여 수소 불화수소 가스를 발생시킵니다.\"\n"
    "좋은 예: \"두 물질이 속한 반응성 그룹 조합은 CAMEO 분류상 가스 발생 위험이 있는 것으로\n"
    "분류되어 있습니다.\"\n"
    "\n"
    "[4. MSDS 정보 사용] §2/§10 정보로 각 물질의 위험성·취급/보관 주의사항을 설명한다.\n"
    "물질별 정보를 정확히 구분하고, MSDS에 없는 정보를 일반 화학지식으로 보완하지 않는다.\n"
    "\n"
    "[5. 근거 부족 시] CAMEO·MSDS에 구체적 반응 정보가 없으면 \"제공된 자료에는 두 물질\n"
    "사이의 구체적인 반응 메커니즘이나 생성물에 대한 정보가 명시되어 있지 않습니다.\"라고\n"
    "밝힌다. 단 CAMEO에 위험 이유가 명시돼 있다면 이 문구로 대체하지 말고 그 정보를 먼저\n"
    "설명한다.\n"
    "\n"
    "[6. 물질 혼동 방지] CAS 번호와 물질명을 정확히 대응시키고, 두 물질의 MSDS 정보를\n"
    "서로 바꾸거나 임의로 합쳐 새 사실을 만들지 않는다.\n"
    "\n"
    "[출력 형식]\n"
    "판정:\n{입력된 CAMEO 판정을 그대로 출력}\n\n"
    "위험 이유:\nCAMEO의 구체적 reason/hazard 정보를 근거로 1~3문장으로 설명.\n\n"
    "물질별 근거:\n- {물질A}: 관련 MSDS 정보를 간결하게 설명\n- {물질B}: 관련 MSDS 정보를 간결하게 설명\n\n"
    "취급 주의:\n제공된 정보 범위 안에서만 설명.\n\n"
    "근거 한계:\n추가 반응 메커니즘·생성물 정보가 없다면 \"제공된 자료에는 해당 세부 정보가\n"
    "명시되어 있지 않습니다.\"라고 명시.\n"
    "\n"
    "[판정별 결론 문장] 마지막 문단은 판정에 맞는 결론으로 맺는다.\n"
    "- Compatible: \"제공된 자료 범위에서 함께 취급·보관 가능한 조합입니다.\"\n"
    "- Caution: \"분리보관이 필수인 조합은 아니나, ...에서는 주의가 필요합니다.\" 형태로\n"
    "  맺는다. 주의가 필요한 구체적 조건은 제공된 CAMEO/MSDS 근거에서 확인되는 경우에만\n"
    "  적는다. 근거에 조건이 없으면 조건을 지어내지 말고 \"분리보관이 필수인 조합은 아니나\n"
    "  취급 시 주의가 필요합니다.\"로 맺는다. 이 지시문의 문구를 답변에 그대로 옮기지 않는다.\n"
    "- Incompatible: \"함께 취급·보관해서는 안 되는 조합입니다.\"\n"
    "\n"
    "[위험 표현의 강도 보존] CAMEO 위험코드의 may/can 등 가능성을 나타내는 표현은\n"
    "\"~일 수 있다\" 등 동일한 수준의 가능성 표현으로 옮긴다. 가능성을 확정적 사실로\n"
    "강화하거나, 원문에 없는 위험을 추가하지 않는다.\n"
    "\n"
    "사용한 근거:\n답변 맨 마지막 줄에, 위 설명에서 실제로 인용한 [MSDS 근거]의 번호만\n"
    "대괄호 안에 나열한다. 형식은 정확히 다음과 같다.\n"
    "[사용한 근거: 1, 4, 7]\n"
    "번호 외의 문자(chunk_id·CAS 번호·물질명·섹션명)를 이 줄에 넣지 않는다.\n"
    "MSDS 근거를 하나도 인용하지 않았다면 [사용한 근거: 없음] 이라고 적는다.\n"
    "\n"
    "최종 확인(출력 전 스스로 점검): 판정을 바꾸지 않았는가 / CAMEO 근거를 충분히 활용했는가\n"
    "/ 원본보다 강한 표현을 추가하지 않았는가 / MSDS에 없는 사실을 추론하지 않았는가 /\n"
    "두 물질 정보를 혼동하지 않았는가 / 개별 위험정보를 쌍별 반응성 근거로 쓰지 않았는가 /\n"
    "그룹 분류를 이 특정 물질쌍에서 확인된 반응처럼 단정하지 않았는가.\n"
    "\n"
    "가장 중요한 원칙: 근거가 있으면 구체적으로 설명하고, 근거가 없으면 추론하지 않는다.\n"
)

# 물질 혼동 4 + 개별위험->상호반응 비약 4 + 정상 Compatible 3 + 정상 Caution/Incompatible 2
TEST_IDS = [
    "pair::21351-79-1::7220-79-3::t0",
    "pair::108-88-3::7790-99-0::t4",
    "pair::100-02-7::16940-66-2::t4",
    "pair::10112-91-1::7220-79-3::t1",
    "pair::10361-37-2::12030-88-5::t1",
    "pair::115-19-5::7440-70-2::t0",
    "pair::103-80-0::7553-56-2::t0",
    "pair::112-02-7::7758-94-3::t0",
    "pair::7447-40-7::7784-30-7::t4",
    "pair::7447-40-7::7803-55-6::t4",
    "pair::108-88-3::7439-98-7::t4",
    "pair::101-27-9::7440-33-7::t3",
    "pair::7440-16-6::7722-64-7::t1",
]


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


ABSTAIN_SENTENCE = EV.ABSTAIN_PHRASE + "."


# ── structured output 계약 (2026-08-29) ──────────────────────────────────────
# 자유 텍스트에서 판정줄·인용태그·결론문장을 정규식으로 긁던 것을 스키마로 고정한다.
# 실측 근거: 결론 문장 준수율이 51~61%에 그쳤고(자유 텍스트), 누락 시 Caution 정답률이
# 94.2% -> 75.4%로 떨어졌다. 결론 문장은 모델이 쓰지 않고 코드가 verdict 로 조립한다.
#
# Upstage 제약: strict=true / additionalProperties=false / 모든 필드 required /
# 중첩 3단 / $ref 불가. (console.upstage.ai/docs/capabilities/structured-outputs)
SCHEMA_PROMPT_VERSION = "cameo_service_v8b_schema"

PAIR_SCHEMA = {
    "type": "object",
    "properties": {
        # verdict 는 필드가 아니다. CAMEO 판정은 코드가 주입한다 —
        # 모델에게 복사를 시키면 복사를 틀릴 기회를 준다(v8 에서 1.04% 뒤집힘,
        # 그중 18/20 이 위험을 낮추는 방향. archive/2026-08-29_generation_prompt_history/_v8_verdict_regression/ 참고).
        "hazard_basis": {"type": "string"},
        "substance_a_note": {"type": "string"},
        "substance_b_note": {"type": "string"},
        "precaution": {"type": "string"},
        "evidence_gap": {"type": "string"},
        "cited": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["hazard_basis", "substance_a_note", "substance_b_note",
                 "precaution", "evidence_gap", "cited"],
    "additionalProperties": False,
}
RESPONSE_FORMAT = {"type": "json_schema",
                   "json_schema": {"name": "pair_assessment", "strict": True,
                                   "schema": PAIR_SCHEMA}}

# v9(2026-08-29) 폐기 — archive/2026-08-29_generation_prompt_history/_v9_regression/FINDING.md.
# 프롬프트를 독립시키고 강도 보존을 양방향으로 바꿨으나 사전 등록한 채택 기준을 통과하지
# 못했다(600건 짝지은 비교: 전체 일치 87.2->86.5%, Caution 82.2->80.0%). 폐기된 v9 전문은
# archive/2026-08-29_generation_prompt_history/_v9_regression/schema_prompt_v9.txt 에 있다.
# 출력 형식 지시는 스키마가 대신하므로 프롬프트에서 잘라낸다.
SCHEMA_PROMPT = SYSTEM_PROMPT[:SYSTEM_PROMPT.index("[출력 형식]")] + """[출력] 아래 JSON 스키마로만 답한다.
판정과 결론 문장은 쓰지 않는다 — 둘 다 시스템이 CAMEO 판정으로 직접 채운다.
설명 안에서 판정을 다시 말하거나 바꾸지 않는다.
- hazard_basis: CAMEO reason/hazard 원문 근거로 1~3문장. may/can 은 "~일 수 있다"로
  옮기고 확정적 사실로 강화하지 않는다. 판정어(Compatible/Caution/Incompatible)를
  이 문장에 쓰지 않는다.
- substance_a_note / substance_b_note: 각 물질의 MSDS 2/10절 근거. 두 물질을 섞지 않는다.
- precaution: 주의가 필요한 조건을 한 구절로만 쓴다(30자 내외, 문장이 아니라 구).
  "~할 때" 또는 "~시" 형태로 끝낸다. 예: "산과 접촉하거나 가열될 때".
  제공된 근거에서 확인되는 경우에만 쓰고, 근거에 없으면 빈 문자열로 둔다.
  조건을 지어내지 않는다. 취급 지침을 나열하지 않는다.
- evidence_gap: 근거에 없는 내용. 없으면 빈 문자열.
- cited: 실제로 인용한 [MSDS 근거] 번호 배열. 없으면 빈 배열.
"""


_CONCLUSION = {
    "Compatible": "제공된 자료 범위에서 함께 취급·보관 가능한 조합입니다.",
    "Incompatible": "함께 취급·보관해서는 안 되는 조합입니다.",
    "Abstain": ABSTAIN_SENTENCE,
}


def build_schema_prompt(question: str, cameo_ctx: str, contexts: list[dict]) -> str:
    """build_prompt 와 근거 블록은 동일하고 지시부만 스키마용으로 바꾼다."""
    ev = "\n\n".join(f"[근거 {i + 1}] (chunk_id={c['chunk_id']})\n{c['text']}"
                      for i, c in enumerate(contexts))
    return f"{SCHEMA_PROMPT}\n\n{cameo_ctx}\n\n[MSDS 근거]\n{ev}\n\n[질문]\n{question}\n\n[답변]"


def render_conclusion(verdict: str, precaution: str) -> str:
    """결론 문장은 모델이 아니라 여기서 만든다 — 누락·오용이 구조적으로 불가능해진다."""
    if verdict == "Caution":
        p = (precaution or "").strip().rstrip(".")
        return (f"분리보관이 필수인 조합은 아니나, {p} 주의가 필요합니다." if p
                else "분리보관이 필수인 조합은 아니나 취급 시 주의가 필요합니다.")
    return _CONCLUSION.get(verdict, _CONCLUSION["Abstain"])


def render_answer(obj: dict, name_a: str, name_b: str, verdict: str) -> str:
    """스키마 산출물을 기존 자유 텍스트와 같은 모양으로 조립한다.

    judge·rule_based 는 이 텍스트를 그대로 채점하므로 지표 정의가 유지되고
    v7 자유 텍스트 결과와 직접 비교할 수 있다.
    """
    cited = ", ".join(str(i) for i in obj.get("cited") or [])
    parts = [
        f"판정: {verdict}",
        f"위험 이유: {obj['hazard_basis']}",
        f"물질별 근거:\n- {name_a}: {obj['substance_a_note']}\n- {name_b}: {obj['substance_b_note']}",
    ]
    if (obj.get("precaution") or "").strip():
        parts.append(f"취급 주의: {obj['precaution']}")
    if (obj.get("evidence_gap") or "").strip():
        parts.append(f"근거 한계: {obj['evidence_gap']}")
    parts.append(f"결론: {render_conclusion(verdict, obj.get('precaution', ''))}")
    parts.append(f"[사용한 근거: {cited or '없음'}]")
    return "\n\n".join(parts)


def build_prompt(question: str, cameo_ctx: str, contexts: list[dict]) -> str:
    ev = "\n\n".join(f"[근거 {i + 1}] (chunk_id={c['chunk_id']})\n{c['text']}" for i, c in enumerate(contexts))
    return f"{SYSTEM_PROMPT}\n\n{cameo_ctx}\n\n[MSDS 근거]\n{ev}\n\n[질문]\n{question}\n\n[답변]"


def run_generation() -> None:
    rows = {r["query_id"]: r for r in load_jsonl(FROZEN_PATH)}
    todo = [rows[qid] for qid in TEST_IDS]
    print(f"생성 대상 {len(todo)}건")

    con = sqlite3.connect(ROOT / "data" / "reactivity_reference.db")
    cur = con.cursor()
    with GEN_OUT.open("w", encoding="utf-8") as out_f:
        for i, r in enumerate(todo):
            cameo = CL.lookup(cur, r["cas_a"], r["cas_b"])
            cameo_ctx = CL.format_context(cameo, r["name_a"], r["name_b"], detailed=True)

            chunk_ids = [c["chunk_id"] for c in r["retrieved"]]
            texts = GB.load_texts(cur, chunk_ids)
            contexts = [{"chunk_id": cid, "text": texts.get(cid, "")} for cid in chunk_ids]

            prompt = build_prompt(r["query"], cameo_ctx, contexts)
            t0 = time.perf_counter()
            try:
                data = L.chat(
                    [{"role": "user", "content": prompt}],
                    max_tokens=GB.MAX_TOKENS,
                    reasoning_effort=GB.REASONING_EFFORT,
                )
                answer = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                error = None
            except Exception as e:  # noqa: BLE001
                answer = None
                usage = {}
                error = f"{type(e).__name__}: {str(e)[:300]}"
            latency = round(time.perf_counter() - t0, 3)

            rec = {
                "query_id": r["query_id"],
                "query": r["query"],
                "cas_a": r["cas_a"],
                "cas_b": r["cas_b"],
                "name_a": r["name_a"],
                "name_b": r["name_b"],
                "matrix_verdict": r["matrix_verdict"],
                "cameo_category": cameo.category,
                "cameo_context": cameo_ctx,
                "gold_evidence": r["gold_evidence"],
                "retrieval_status": r["retrieval_status"],
                "context_ids": chunk_ids,
                "generated_answer": answer,
                "model": L.MODEL,
                "prompt_version": PROMPT_VERSION,
                "latency_sec": latency,
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "error": error,
            }
            out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out_f.flush()
            print(f"[gen {i + 1}/{len(todo)}] {r['query_id']} {'실패' if error else '완료'} "
                  f"(cameo={cameo.category}) ({latency}s)", flush=True)
    con.close()


def run_eval() -> None:
    rows = [r for r in load_jsonl(GEN_OUT) if r.get("error") is None]
    print(f"채점 대상 {len(rows)}건")
    con = sqlite3.connect(ROOT / "data" / "reactivity_reference.db")
    cur = con.cursor()
    with EVAL_OUT.open("w", encoding="utf-8") as out_f:
        for i, r in enumerate(rows):
            rb = EV.rule_based(r)
            context_ids = r.get("context_ids", [])
            if context_ids:
                q = "select chunk_id, text from rag_chunks where chunk_id in ({})".format(
                    ",".join("?" * len(context_ids))
                )
                contexts_by_id = dict(cur.execute(q, context_ids).fetchall())
            else:
                contexts_by_id = {}
            # judge()는 MSDS 청크만 근거로 보고 채점한다(eval_generation.py 원래 설계).
            # 이 파이프라인은 CAMEO context도 생성기에 실제로 준 입력이므로, 생성기가 본 것과
            # 다른(더 좁은) 근거로 채점하면 CAMEO를 정당하게 인용한 답변도 "근거 없음"으로
            # 오탐한다 — judge에 넘기는 근거에도 cameo_context를 합성 청크로 추가해 맞춘다.
            judge_rec = {**r, "context_ids": context_ids + ["__cameo_context__"]}
            contexts_by_id["__cameo_context__"] = r.get("cameo_context", "")
            t0 = time.perf_counter()
            try:
                jr = EV.judge(judge_rec, contexts_by_id)
                error = None
            except Exception as e:  # noqa: BLE001
                jr = {"predicted_verdict": None, "faithful": None, "unsupported_claims": None}
                error = f"{type(e).__name__}: {str(e)[:300]}"
            latency = round(time.perf_counter() - t0, 3)
            matrix_verdict = r.get("matrix_verdict")
            pv = jr["predicted_verdict"]
            abstained = pv == "Abstain" if pv is not None else rb["abstained_lexical"]
            answer_correct = None if pv in (None, "Abstain") else (pv == matrix_verdict)
            stated_verdict = parse_stated_verdict(r.get("generated_answer"))
            # 규칙5("판정은 코드가 준 값 그대로") 직접 검증: 답변의 "판정:" 줄 vs 코드가 넣어준 값.
            kept_cameo_verdict = None if stated_verdict is None else (stated_verdict == r.get("cameo_category"))
            # v1 파일럿에서 나온 "본문은 A인데 태그는 B" 자기모순 재발 여부 확인.
            tag_body_consistent = None if pv is None or stated_verdict is None else (pv == stated_verdict)
            confused = substance_confused(r, {**rb, **jr})  # 이번 출력엔 인용번호 태그가 없어 대부분 None -> 수동 확인 필요
            rec = {
                "query_id": r["query_id"],
                "matrix_verdict": matrix_verdict,
                "cameo_category": r.get("cameo_category"),
                "retrieval_status": r.get("retrieval_status"),
                **rb,
                **jr,
                "abstained": abstained,
                "abstention_bucket": EV.abstention_bucket(abstained, r.get("retrieval_status")),
                "answer_correct": answer_correct,
                "stated_verdict": stated_verdict,
                "kept_cameo_verdict": kept_cameo_verdict,
                "tag_body_consistent": tag_body_consistent,
                "substance_confused": confused,
                "judge_latency_sec": latency,
                "judge_error": error,
            }
            out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out_f.flush()
            print(f"[eval {i + 1}/{len(rows)}] {r['query_id']} {'실패' if error else '완료'} ({latency}s)", flush=True)
    con.close()


def report() -> None:
    gen = {r["query_id"]: r for r in load_jsonl(GEN_OUT) if r.get("error") is None}
    ev = {r["query_id"]: r for r in load_jsonl(EVAL_OUT)}
    ids = [qid for qid in TEST_IDS if qid in gen and qid in ev]

    n = len(ids)
    n_kept = sum(1 for qid in ids if ev[qid]["kept_cameo_verdict"] is True)
    n_tag_mismatch = sum(1 for qid in ids if ev[qid]["tag_body_consistent"] is False)
    n_confused = sum(1 for qid in ids if ev[qid]["substance_confused"] is True)
    n_unfaithful = sum(1 for qid in ids if ev[qid].get("faithful") is False)
    print(f"\n=== 요약 (n={n}) ===")
    print(f"1) '판정:' 줄이 CAMEO 값과 일치      : {n_kept}/{n}")
    print(f"1b) '판정:' 줄 vs judge 재분류 불일치 : {n_tag_mismatch}/{n} (자기모순 재발 여부)")
    print(f"2) cited_chunk_ids로 혼동 감지(참고, 인용 태그 없어 대부분 None) : {n_confused}/{n}")
    print(f"3) judge unfaithful(주의: CAMEO context 못 보는 판정기라 과대추정됨) : {n_unfaithful}/{n}")
    print()
    print("=== 건별 상세 ===")
    for qid in ids:
        g, e = gen[qid], ev[qid]
        print(f"- {qid}")
        print(f"    matrix={g['matrix_verdict']} cameo={g['cameo_category']} stated={e['stated_verdict']} "
              f"judge_predicted={e['predicted_verdict']} kept_cameo={e['kept_cameo_verdict']} "
              f"tag_body_consistent={e['tag_body_consistent']} faithful={e['faithful']}")
        print(f"    답변: {g['generated_answer']!r}")


def main() -> None:
    if not GEN_OUT.exists():
        run_generation()
    else:
        print(f"{GEN_OUT} 이미 존재 — 생성 건너뜀(다시 하려면 파일 삭제)")
    if not EVAL_OUT.exists():
        run_eval()
    else:
        print(f"{EVAL_OUT} 이미 존재 — 채점 건너뜀(다시 하려면 파일 삭제)")
    report()


if __name__ == "__main__":
    main()
