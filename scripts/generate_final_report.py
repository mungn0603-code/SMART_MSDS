#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""사용자가 입력한 N종 물질(CAS)에 대해 §1~§5 최종 보고서 PDF를 생성한다.

설계 원칙(docs/superpowers 없이 대화로 합의):
  - KPI(§1)와 조합 표(§2)는 Python이 CombinationVerdict에서 확정한 값만 쓴다.
    LLM은 재계산하지 않는다 (§1/§2 불일치, 언어 혼용 버그의 근본 원인 제거).
  - 판정 라벨은 LABELS 딕셔너리 하나로 고정 -> 부적합/不適格 같은 혼용 불가능.
  - §2는 물질A x 물질B = 1행. 같은 쌍에 그룹조합 근거가 여럿이면 최악 1개만
    표시하고 나머지는 "외 N쌍"으로만 알림.
  - §3(분석 요약)만 LLM 호출. Caution/Incompatible 쌍만 압축해서 넘기고,
    판정 재계산 금지·정해진 용어만 사용·§2 반복 금지를 프롬프트로 강제한다.
  - PDF 표 셀은 전부 Paragraph로 감싼다(문자열 그대로 셀에 넣으면 긴 텍스트가
    거대한 단일 셀로 파싱되어 LayoutError 발생 - 실제 겪은 버그).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from compatibility_engine import DISCLAIMER, CompatibilityEngine, _CATEGORY_RANK  # noqa: E402

LABELS = {
    "Compatible": "적합",
    "Caution": "주의",
    "Incompatible": "부적합",
    "Abstain": "판단보류",
}

HAZARD_TEXT_CAP = 80


def truncate(text: str | None, n: int = HAZARD_TEXT_CAP) -> str:
    if not text:
        return "-"
    text = text.strip()
    return text if len(text) <= n else text[: n - 1] + "…"


def worst_group_detail(pair_verdict):
    """쌍의 group_pair_details 중 카테고리 위험도가 가장 높은 것 1개. 없으면 None."""
    if not pair_verdict.group_pair_details:
        return None
    return max(
        pair_verdict.group_pair_details,
        key=lambda d: _CATEGORY_RANK.get(d.category, -1),
    )


def build_kpi(cv) -> dict:
    """§1 KPI. CombinationVerdict에서만 집계 - LLM 미개입."""
    counts = {k: 0 for k in LABELS}
    for v in cv.pair_verdicts:
        counts[v.category] = counts.get(v.category, 0) + 1
    unmapped = [p for p in cv.profiles if not p.mapped]
    return {
        "total_substances": len(cv.inputs),
        "total_combinations": len(cv.pair_verdicts),
        "counts": counts,
        "unmapped_count": len(unmapped),
        "unmapped_profiles": unmapped,
        "overall_category": cv.category,
    }


def build_section2_rows(cv) -> list[dict]:
    """§2 표 행. 쌍 1개 = 행 1개(엔진이 이미 그렇게 만듦, 여기서는 최악 그룹쌍만 추림)."""
    rows = []
    for v in cv.pair_verdicts:
        detail = worst_group_detail(v)
        extra_count = len(v.group_pair_details) - 1 if v.group_pair_details else 0
        rows.append({
            "substance_a": v.query_a,
            "substance_b": v.query_b,
            "category": v.category,
            "label": LABELS[v.category],
            "group_pair": f"{detail.group_a_name} x {detail.group_b_name}" if detail else "-",
            "hazard": truncate(detail.hazard_codes) if detail else (
                "그룹 매핑 없음" if v.category == "Abstain" and not v.group_pair_details else "-"
            ),
            "extra_note": f"외 {extra_count}쌍" if extra_count > 0 else "",
        })
    return rows


def build_section3_prompt(rows: list[dict]) -> str | None:
    """Caution/Incompatible 쌍만 압축해 LLM에 넘긴다. 위험 쌍이 없으면 프롬프트 자체를 만들지 않는다."""
    risky = [r for r in rows if r["category"] in ("Caution", "Incompatible")]
    if not risky:
        return None
    lines = [
        f"- {r['substance_a']} x {r['substance_b']}: [{r['label']}] "
        f"{r['group_pair']} (근거: {r['hazard']})"
        for r in risky
    ]
    data_block = "\n".join(lines)
    return (
        "아래는 화학물질 조합의 CAMEO 반응성 매트릭스 판정 결과다(이미 확정된 값, "
        "재판단하지 말 것). 이 데이터만 근거로 산업안전 보고서용 분석 요약을 작성하라.\n\n"
        "출력 형식 - 반드시 아래 3개 영역으로 구조화하고, 각 영역 제목은 대괄호를 그대로 써라:\n"
        "[주요 결과 요약]\n"
        "- 부적합/주의로 집중되는 조합·그룹쌍 패턴을 불렛(-)으로 정리\n"
        "[위험 원인 분석]\n"
        "- 어떤 CAMEO 반응성 그룹 교차에서 어떤 위험(폭발/화염/가스 발생 등)이 나타나는지 불렛(-)으로 정리\n"
        "[결론 및 한계점]\n"
        "- 실제 위험성은 온도·농도·상태·불순물 등 조건에 따라 달라질 수 있어 추가 검토가 "
        "필요하다는 점을 명시\n\n"
        "문장 규칙:\n"
        "- 보고서 어조로 통일: 서술은 '~함/~임'체, 필요시 '~입니다'체 중 하나로 문서 전체 일관되게 "
        "(혼용 금지)\n"
        "- 같은 단어를 붙여 반복하는 오류 금지(예: '산소와 산소와 같은' 금지)\n"
        "- '~를 가능하다' 식 비문 금지, '~이 가능함'/'~할 수 있음'처럼 올바른 문법만 사용\n"
        "- 불렛 항목은 개조식(명사형 종결 또는 '~함')으로 짧게\n\n"
        "가독성 규칙(반드시 지킬 것):\n"
        "- 각 영역([...] 아래)은 절대 하나의 긴 문단으로 쓰지 말 것. 최소 3개, 최대 6개의 불렛(-)으로 "
        "나눠 쓸 것\n"
        "- 불렛 1개당 문장 1개, 1문장은 60자 내외로 짧게 끊을 것(접속사로 여러 문장을 이어붙이지 말 것)\n"
        "- 각 불렛은 줄바꿈(\\n)으로 구분하고, 영역과 영역 사이는 빈 줄(\\n\\n)로 구분할 것\n\n"
        "금지사항:\n"
        "- 판정 재계산/변경 금지\n"
        "- 아래 데이터에 없는 화학적 메커니즘 추론 금지\n"
        "- 위험 코드 단순 나열, 빈도표 금지\n"
        "- '위험성이 존재한다' 수준의 일반론 금지\n"
        "- 판정 용어는 반드시 '적합/주의/부적합/판단보류'만 사용(한자·일본어 표기 금지)\n"
        "- 여러 문장을 접속사로 이어 붙인 긴 문단 금지(가독성 규칙 위반)\n"
        "- 전체 출력은 한글(및 필요시 영문 화학용어·CAMEO 코드)만 사용. 중국어 간체/번체 한자, "
        "일본어 가나 등 다른 언어 혼입 절대 금지(예: '剧烈' 금지, '격렬' 사용)\n\n"
        f"[데이터: 주의/부적합 쌍 {len(risky)}건]\n{data_block}\n"
    )


def normalize_section3_text(text: str) -> str:
    """LLM이 프롬프트의 줄바꿈 지시를 무시하고 문단으로 뭉쳐 낼 때가 있다.
    헤더([...])는 항상 새 줄로, 문장은 마침표 뒤에서 강제로 끊어 불렛화한다."""
    import re

    text = text.strip()
    # [헤더] 앞뒤에 강제 개행
    text = re.sub(r"\s*(\[[^\[\]]+\])\s*", r"\n\n\1\n", text)
    out_blocks = []
    for block in text.split("\n\n"):
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        new_lines = []
        for ln in lines:
            if ln.startswith("[") and ln.endswith("]"):
                new_lines.append(ln)
                continue
            ln = ln.lstrip("-").strip()
            # 마침표(다./음./임./함.) 뒤 공백을 문장 경계로 보고 불렛 분리
            sentences = re.split(r"(?<=[다음임함]\.)\s+", ln)
            new_lines.extend(f"- {s.strip()}" for s in sentences if s.strip())
        if new_lines:
            out_blocks.append("\n".join(new_lines))
    return "\n\n".join(out_blocks)


def run_section3(rows: list[dict]) -> str:
    prompt = build_section3_prompt(rows)
    if prompt is None:
        return (
            "[주요 결과 요약]\n- 주의/부적합으로 판정된 조합이 없음\n"
            "[위험 원인 분석]\n- 해당 없음\n"
            "[결론 및 한계점]\n- 전 조합이 적합/판단보류로만 분류되어 추가 위험 분석이 불필요함"
        )
    from llm import ask  # noqa: E402 (지연 임포트: --check 등에서 API 키 없이도 동작하게)
    raw = ask(prompt, max_tokens=2048, reasoning_budget=2048).strip()
    return normalize_section3_text(raw)


def build_section4(cv, kpi: dict) -> list[str]:
    """데이터 한계 - 전부 고정 템플릿, LLM 없음."""
    lines = []
    if kpi["unmapped_count"]:
        names = ", ".join(p.cas for p in kpi["unmapped_profiles"])
        lines.append(f"- 그룹 매핑 실패 {kpi['unmapped_count']}종: {names} (CAMEO 68그룹 매트릭스에 미등록)")
    if cv.abstain_notes:
        lines.append(f"- 판단보류(Abstain) 사유 {len(cv.abstain_notes)}건:")
        lines += [f"  · {n}" for n in cv.abstain_notes]
    if not lines:
        lines.append("- 데이터 매핑/판단보류 관련 한계 없음(전 조합 매트릭스 대조 완료).")
    return lines


def build_section5() -> str:
    return (
        "본 보고서의 모든 조합 판정은 CAMEO 68그룹 반응성 매트릭스 대조 결과이며 "
        "[참고자료] 등급입니다.\n\n" + DISCLAIMER + "\n\n"
        "사용 지침: §2 표의 '부적합/주의' 판정은 격리 보관·혼재 금지 검토의 출발점으로 "
        "쓰되, 최종 보관 계획 수립 시에는 반드시 KOSHA MSDS 원문, 산업안전보건법 "
        "제110조·111조 등 관련 법령, 그리고 자체 전문가 검토를 병행해야 합니다."
    )


# ---------------------------------------------------------------- PDF 렌더링

def render_pdf(out_path: str, cv, kpi: dict, rows: list[dict], section3_text: str, section4_lines: list[str]):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import (
        Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    FONT = "HYSMyeongJo-Medium"
    pdfmetrics.registerFont(UnicodeCIDFont(FONT))

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontName=FONT, fontSize=16, spaceAfter=8)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontName=FONT, fontSize=13, spaceBefore=14, spaceAfter=6)
    body = ParagraphStyle("body", parent=styles["Normal"], fontName=FONT, fontSize=9.5, leading=13)
    h3 = ParagraphStyle("h3", parent=body, fontName=FONT, fontSize=10.5, spaceBefore=8, spaceAfter=3, leading=14)
    cell = ParagraphStyle("cell", parent=styles["Normal"], fontName=FONT, fontSize=8, leading=11)
    cell_hdr = ParagraphStyle("cell_hdr", parent=cell, fontName=FONT, textColor=colors.white)

    story = [Paragraph("SMART-MSDS 화학물질 조합 판정 보고서", h1)]

    # §1
    story.append(Paragraph("§1 Executive Summary", h2))
    c = kpi["counts"]
    kpi_lines = (
        f"입력 물질 {kpi['total_substances']}종 · 전체 조합 {kpi['total_combinations']}쌍 "
        f"· 종합 판정: {LABELS[kpi['overall_category']]}<br/>"
        f"적합 {c['Compatible']} · 주의 {c['Caution']} · 부적합 {c['Incompatible']} · "
        f"판단보류 {c['Abstain']}<br/>"
        f"그룹 매핑 실패 물질: {kpi['unmapped_count']}종"
    )
    story.append(Paragraph(kpi_lines, body))

    # §2
    story.append(Paragraph("§2 부적합 판정 조합", h2))
    header = ["물질 A", "물질 B", "판정", "CAMEO 그룹쌍", "근거", "비고"]
    table_data = [[Paragraph(h, cell_hdr) for h in header]]
    for r in rows:
        table_data.append([
            Paragraph(r["substance_a"], cell),
            Paragraph(r["substance_b"], cell),
            Paragraph(r["label"], cell),
            Paragraph(r["group_pair"], cell),
            Paragraph(r["hazard"], cell),
            Paragraph(r["extra_note"], cell),
        ])
    col_widths = [32 * mm, 32 * mm, 14 * mm, 34 * mm, 40 * mm, 16 * mm]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
    ]))
    story.append(t)

    # §3 - "[제목]" 단독 줄은 소제목으로, 나머지는 본문(줄바꿈은 <br/>)으로 렌더링
    story.append(Paragraph("§3 상세 분석 및 근거", h2))
    for block in section3_text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        for line in block.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("[") and line.endswith("]"):
                story.append(Paragraph(f"<b>{line}</b>", h3))
            else:
                story.append(Paragraph(line, body))
        story.append(Spacer(1, 4))

    # §4
    story.append(Paragraph("§4 데이터상 한계", h2))
    for line in build_section4(cv, kpi):
        story.append(Paragraph(line, body))

    # §5
    story.append(Paragraph("§5 판단 기준 및 사용 지침", h2))
    for para in build_section5().split("\n\n"):
        story.append(Paragraph(para.replace("\n", "<br/>"), body))
        story.append(Spacer(1, 4))

    doc = SimpleDocTemplate(
        out_path, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
    )
    doc.build(story)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cas", nargs="+", required=True, help="CAS 번호 목록(2개 이상)")
    ap.add_argument("--out", default="report.pdf", help="출력 PDF 경로")
    ap.add_argument("--db", default=str(ROOT / "data" / "reactivity_reference.db"))
    ap.add_argument("--no-llm", action="store_true", help="§3을 LLM 없이 고정 문구로 채움(연결 점검용)")
    args = ap.parse_args()

    eng = CompatibilityEngine(args.db)
    try:
        cv = eng.judge_combination_by_cas(args.cas)
    finally:
        eng.close()

    kpi = build_kpi(cv)
    rows = build_section2_rows(cv)
    section3_text = "(LLM 미실행 - --no-llm)" if args.no_llm else run_section3(rows)

    render_pdf(args.out, cv, kpi, rows, section3_text, build_section4(cv, kpi))
    print(f"작성 완료: {args.out}")


if __name__ == "__main__":
    main()
