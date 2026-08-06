#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stage 3: 화학물질 쌍 양립성 판정 엔진 (CAMEO 68그룹 매트릭스 기반)

설계 원칙(비협상):
  1. 매트릭스 판정 결과는 단독 최종 판단 근거로 사용 불가 -> 모든 결과에
     disclaimer(면책 고지) 필드를 무조건 부착한다.
  2. 근거 등급: 이 엔진의 모든 판정은 evidence_grade='Reference' (CAMEO 그룹
     매트릭스는 참고자료 등급, 법령/권고 등급 아님).
  3. 다음 경우 category='Abstain'으로 강제 반환한다(억지 답변 금지):
       - CAS 번호가 chemicals 테이블에 없음(매핑 미등록)
       - 그룹쌍 조합에 대한 compatibility_pairs 레코드가 없음
       - 자기반응(self_reactivity) 값이 'Unknown'인 경우
  4. 화학물질이 다중 그룹에 속할 경우, 모든 그룹조합 쌍을 평가하여
     보수적(worst-case) 원칙으로 종합한다: Incompatible > Caution > Compatible.
     단, 하나라도 Abstain 사유가 있으면 그 사실을 함께 표기한다(침묵하지 않음).
"""

import itertools
import sqlite3
from dataclasses import dataclass, field
from typing import Optional

DISCLAIMER = (
    "본 판정은 CAMEO 68그룹 반응성 매트릭스 대조 결과이며 [참고자료] 등급입니다. "
    "단독 최종 위험성평가 근거로 사용할 수 없으며, KOSHA MSDS 및 관련 법령(산업안전보건법 "
    "제110조·111조 등)과 전문가 검토를 병행해야 합니다."
)

_CATEGORY_RANK = {"Compatible": 0, "Caution": 1, "Incompatible": 2, "Unknown": -1}

# 쌍 판정 결과(category)를 N종 종합에서 비교할 때 쓰는 순위. Compatible보다 Abstain을
# 위로 두는 이유: "모름"이 "안전 확인됨"보다 위험도가 낮다고 말할 근거가 없다.
_VERDICT_RANK = {"Compatible": 0, "Abstain": 1, "Caution": 2, "Incompatible": 3}


@dataclass
class SubstanceProfile:
    """물질 1종의 기본 프로필 - CAS/이름/소속 CAMEO 반응성 그룹. 조합 판정 위에
    붙는 '이 물질이 뭔지' 요약. 상세 유해성 텍스트(GHS 문구 등)는 04_rag_agent
    쪽 MSDS 청크가 다루는 영역이라 여기서는 안 끌어옴(스테이지 경계 유지)."""
    cas: str
    name: Optional[str]
    groups: list = field(default_factory=list)  # CAMEO 그룹명 리스트
    mapped: bool = True  # False면 chemicals 테이블에 없어 그룹 미상

    def pretty(self) -> str:
        if not self.mapped:
            return f"- {self.cas}: 매핑 없음 (chemicals 테이블에 없음, 그룹 미상)"
        group_str = ", ".join(self.groups) if self.groups else "(소속 그룹 없음)"
        return f"- {self.cas} ({self.name}): {group_str}"


@dataclass
class GroupPairResult:
    group_a_id: int
    group_b_id: int
    group_a_name: str
    group_b_name: str
    category: str
    description: Optional[str]
    hazard_codes: Optional[str]
    gas_products: Optional[str]


@dataclass
class CompatibilityVerdict:
    query_a: str
    query_b: str
    category: str  # Compatible / Caution / Incompatible / Abstain
    evidence_grade: str
    disclaimer: str
    reasons: list = field(default_factory=list)
    group_pair_details: list = field(default_factory=list)
    abstain_notes: list = field(default_factory=list)


@dataclass
class CombinationVerdict:
    """N종(N>=2) 물질 조합 판정. 쌍 판정 C(N,2)개의 worst-case 종합.

    ponytail: 3체 이상에서만 나타나는 반응(각 쌍은 안전하나 셋이 같이 있을 때만
    위험한 경우)은 이 방식으로 못 잡는다. CAMEO 자체가 쌍 단위 데이터라 구조적
    한계 - N종 전용 실측 매트릭스가 생기면 그때 그 데이터로 교체.
    """
    inputs: list
    category: str  # 전체 쌍 중 worst-case
    evidence_grade: str
    disclaimer: str
    worst_pair: tuple  # (query_a, query_b) - category를 결정한 쌍
    reasons: list = field(default_factory=list)
    pair_verdicts: list = field(default_factory=list)  # 모든 C(N,2) 쌍의 CompatibilityVerdict
    abstain_notes: list = field(default_factory=list)  # 어느 쌍에서 나왔든 전부 취합(침묵 금지)
    profiles: list = field(default_factory=list)  # 입력 물질 각각의 SubstanceProfile

    def pretty(self) -> str:
        """빠른 요약 한 줄짜리 - '이 조합 전체가 위험한가?'용. 쌍별 상세는 to_table()/pair_reports() 참고."""
        lines = [
            f"[{self.category}] 입력 {len(self.inputs)}종: {', '.join(self.inputs)}",
            f"근거등급: {self.evidence_grade}",
            f"최악 판정 쌍: {self.worst_pair[0]} <-> {self.worst_pair[1]}",
        ]
        if self.abstain_notes:
            lines.append(f"Abstain/미상 경고 {len(self.abstain_notes)}건 (침묵하지 않음, 상세는 pair_reports() 참고)")
        lines.append(self.disclaimer)
        return "\n".join(lines)

    def _cas_name_map(self) -> dict:
        """query 문자열("{cas} ({name})" 또는 미매핑시 "{cas}")에서 cas->표시이름 추출."""
        names = {}
        for v in self.pair_verdicts:
            for q in (v.query_a, v.query_b):
                cas = q.split(" ", 1)[0]
                names.setdefault(cas, q)
        return names

    def to_table(self) -> str:
        """N x N 마크다운 표 - 전체 쌍을 한 화면에. 히트맵/표로 그대로 렌더링 가능한 형태.
        칸 값은 category 문자열 그대로(Compatible/Caution/Incompatible/Abstain) -
        프론트에서 색만 입히면 히트맵 완성(Incompatible=빨강, Caution=노랑, Compatible=초록, Abstain=회색 추천).
        """
        lookup = {}
        for (a, b), v in zip(itertools.combinations(self.inputs, 2), self.pair_verdicts):
            lookup[(a, b)] = lookup[(b, a)] = v.category
        header = "| | " + " | ".join(self.inputs) + " |"
        sep = "|---" * (len(self.inputs) + 1) + "|"
        rows = [header, sep]
        for a in self.inputs:
            cells = ["-" if a == b else lookup[(a, b)] for b in self.inputs]
            rows.append(f"| {a} | " + " | ".join(cells) + " |")
        names = self._cas_name_map()
        legend = [f"- {cas}: {label}" for cas, label in names.items() if "(" in label]
        if legend:
            rows.append("")
            rows.append("범례:")
            rows += legend
        return "\n".join(rows)

    def pair_reports(self) -> list:
        """쌍마다 따로 - 사유·유의사항·경고를 합치지 않고 쌍 단위로 분리한 리포트.
        각 원소가 그 쌍만의 완결된 요약이라 UI에서 카드/아코디언 하나씩으로 그대로 쓸 수 있다.
        """
        reports = []
        for v in self.pair_verdicts:
            lines = [f"[{v.category}] {v.query_a} <-> {v.query_b} (근거등급: {v.evidence_grade})"]
            lines += [f"  - {r}" for r in v.reasons]
            for d in v.group_pair_details:
                extra = ", ".join(
                    x for x in (
                        d.description,
                        f"hazard={d.hazard_codes}" if d.hazard_codes else None,
                        f"gas={d.gas_products}" if d.gas_products else None,
                    ) if x
                )
                if extra:
                    lines.append(f"  · {d.group_a_name} x {d.group_b_name}: {extra}")
            lines += [f"  ! {n}" for n in v.abstain_notes]
            reports.append("\n".join(lines))
        return reports

    def full_report(self) -> str:
        """물질별 프로필 -> 전체 매트릭스 표 -> 쌍별 상세(유의사항) -> 면책고지,
        한 번에 이어붙인 최종 사용자용 리포트. 세 조각(profiles/to_table/pair_reports)이
        각자 독립적으로도 쓸 수 있게 분리돼 있고, 이건 그걸 그대로 이어붙이기만 한다."""
        lines = [f"=== 조합 판정: {len(self.inputs)}종 입력 ==="]
        lines.append("\n[물질별 프로필]")
        lines += [p.pretty() for p in self.profiles]
        lines.append("\n[전체 매트릭스]")
        lines.append(self.to_table())
        lines.append("\n[쌍별 상세 - 유의사항]")
        lines.append("\n---\n".join(self.pair_reports()))
        lines.append(f"\n{self.disclaimer}")
        return "\n".join(lines)


class CompatibilityEngine:
    def __init__(self, db_path: str):
        self.con = sqlite3.connect(db_path)
        self.con.row_factory = sqlite3.Row

    def close(self):
        self.con.close()


    # ---------- 저수준 조회 ----------

    def _group_name(self, group_id: int) -> str:
        row = self.con.execute(
            "SELECT group_name FROM reactivity_groups WHERE group_id = ?", (group_id,)
        ).fetchone()
        return row["group_name"] if row else f"(unknown group #{group_id})"

    def resolve_cas_to_groups(self, cas_number: str):
        """CAS 번호 -> chemical_id, 소속 group_id 리스트. 매핑 없으면 (None, None, [])."""
        row = self.con.execute(
            "SELECT chemical_id, chemical_name FROM chemicals WHERE cas_number = ?",
            (cas_number,),
        ).fetchone()
        if row is None:
            return None, None, []
        chem_id, chem_name = row["chemical_id"], row["chemical_name"]
        groups = self.con.execute(
            "SELECT group_id FROM chemical_group_membership WHERE chemical_id = ?",
            (chem_id,),
        ).fetchall()
        return chem_id, chem_name, [g["group_id"] for g in groups]

    def profile_for_cas(self, cas_number: str) -> SubstanceProfile:
        """CAS 하나의 기본 프로필(이름 + 소속 CAMEO 그룹). resolve_cas_to_groups 재사용."""
        chem_id, name, group_ids = self.resolve_cas_to_groups(cas_number)
        if chem_id is None:
            return SubstanceProfile(cas=cas_number, name=None, groups=[], mapped=False)
        return SubstanceProfile(
            cas=cas_number, name=name,
            groups=[self._group_name(g) for g in group_ids], mapped=True,
        )


    def judge_group_pair(self, group_a_id: int, group_b_id: int) -> GroupPairResult:
        """그룹쌍 판정. compatibility_pairs는 group_a_id < group_b_id로 정규화 저장됨."""
        a, b = sorted((group_a_id, group_b_id))
        if a == b:
            row = self.con.execute(
                "SELECT category, notes FROM self_reactivity WHERE group_id = ?", (a,)
            ).fetchone()
            category = row["category"] if row else "Unknown"
            desc = row["notes"] if row else None
            return GroupPairResult(
                group_a_id=a, group_b_id=b,
                group_a_name=self._group_name(a), group_b_name=self._group_name(b),
                category=category, description=desc,
                hazard_codes=None, gas_products=None,
            )
        row = self.con.execute(
            """SELECT category, description, hazard_codes_raw, gas_products_raw
               FROM compatibility_pairs WHERE group_a_id = ? AND group_b_id = ?""",
            (a, b),
        ).fetchone()
        if row is None:
            category, desc, hz, gas = "Unknown", None, None, None
        else:
            category, desc = row["category"], row["description"]
            hz, gas = row["hazard_codes_raw"], row["gas_products_raw"]
        return GroupPairResult(
            group_a_id=a, group_b_id=b,
            group_a_name=self._group_name(a), group_b_name=self._group_name(b),
            category=category, description=desc,
            hazard_codes=hz, gas_products=gas,
        )


    # ---------- 상위 판정 API ----------

    def judge_pair_by_cas(self, cas_a: str, cas_b: str) -> CompatibilityVerdict:
        chem_a_id, name_a, groups_a = self.resolve_cas_to_groups(cas_a)
        chem_b_id, name_b, groups_b = self.resolve_cas_to_groups(cas_b)

        abstain_notes = []
        if chem_a_id is None:
            abstain_notes.append(f"CAS {cas_a}: chemicals 테이블에 매핑 없음(그룹 미상)")
        if chem_b_id is None:
            abstain_notes.append(f"CAS {cas_b}: chemicals 테이블에 매핑 없음(그룹 미상)")

        if chem_a_id is None or chem_b_id is None:
            return CompatibilityVerdict(
                query_a=cas_a, query_b=cas_b,
                category="Abstain", evidence_grade="Reference",
                disclaimer=DISCLAIMER,
                reasons=["그룹 매핑이 없는 화학물질이 포함되어 매트릭스 대조 불가"],
                abstain_notes=abstain_notes,
            )

        details = []
        worst = "Compatible"
        for ga in groups_a:
            for gb in groups_b:
                r = self.judge_group_pair(ga, gb)
                details.append(r)
                if r.category == "Unknown":
                    abstain_notes.append(
                        f"그룹#{r.group_a_id}({r.group_a_name}) x 그룹#{r.group_b_id}"
                        f"({r.group_b_name}): 매트릭스 값 없음/Unknown"
                    )
                elif _CATEGORY_RANK[r.category] > _CATEGORY_RANK[worst]:
                    worst = r.category

        final_category = "Abstain" if (abstain_notes and worst == "Compatible") else worst
        reasons = [
            f"{name_a}(그룹 {groups_a}) vs {name_b}(그룹 {groups_b}) 그룹쌍 조합 중 "
            f"최고 위험도: {worst}"
        ]
        return CompatibilityVerdict(
            query_a=f"{cas_a} ({name_a})", query_b=f"{cas_b} ({name_b})",
            category=final_category, evidence_grade="Reference",
            disclaimer=DISCLAIMER, reasons=reasons,
            group_pair_details=details, abstain_notes=abstain_notes,
        )

    def judge_combination_by_cas(self, cas_list: list) -> CombinationVerdict:
        """N종(N>=2) 물질 조합 판정. 모든 쌍 C(N,2)을 judge_pair_by_cas로 판정한 뒤
        worst-case로 종합한다 (Incompatible > Caution > Abstain > Compatible).
        중복 CAS는 무시한다(같은 물질 2번 입력 = 1번 입력과 동일 취급).
        """
        unique = sorted(set(cas_list))
        if len(unique) < 2:
            raise ValueError("judge_combination_by_cas: 서로 다른 CAS가 최소 2개 필요")

        pairs = list(itertools.combinations(unique, 2))
        pair_verdicts = [self.judge_pair_by_cas(a, b) for a, b in pairs]
        profiles = [self.profile_for_cas(c) for c in unique]

        worst = max(pair_verdicts, key=lambda v: _VERDICT_RANK[v.category])
        all_abstain_notes = [n for v in pair_verdicts for n in v.abstain_notes]

        return CombinationVerdict(
            inputs=unique,
            category=worst.category,
            evidence_grade=worst.evidence_grade,
            disclaimer=DISCLAIMER,
            worst_pair=(worst.query_a, worst.query_b),
            reasons=[r for v in pair_verdicts for r in v.reasons],
            pair_verdicts=pair_verdicts,
            abstain_notes=all_abstain_notes,
            profiles=profiles,
        )


if __name__ == "__main__":
    import sys
    db_path = sys.argv[1] if len(sys.argv) > 1 else "reactivity_reference.db"
    eng = CompatibilityEngine(db_path)

    print("=== 테스트 1: 그룹 레벨 직접 판정 (데이터 완비 영역) ===")
    r = eng.judge_group_pair(50, 57)
    print(f"{r.group_a_name} x {r.group_b_name} -> {r.category} | {r.description} "
          f"| hazard={r.hazard_codes} | gas={r.gas_products}")

    print("\n=== 테스트 2: CAS 기반 판정 - 매핑 있는 케이스 (황산 x 황산) ===")
    v = eng.judge_pair_by_cas("7664-93-9", "7664-93-9")
    print(f"{v.query_a} vs {v.query_b} -> {v.category} (grade={v.evidence_grade})")
    print("reasons:", v.reasons)
    print("abstain_notes:", v.abstain_notes)

    print("\n=== 테스트 3: CAS 기반 판정 - 매핑 없는 케이스 (아세톤, 미등록 CAS) ===")
    v = eng.judge_pair_by_cas("67-64-1", "7664-93-9")
    print(f"{v.query_a} vs {v.query_b} -> {v.category}")
    print("abstain_notes:", v.abstain_notes)
    print("disclaimer:", v.disclaimer)

    print("\n=== 테스트 4: N종 조합 - 중복 CAS는 1개로 축약, 미만2종이면 에러 ===")
    try:
        eng.judge_combination_by_cas(["7664-93-9", "7664-93-9"])
        raise AssertionError("중복 제거 후 1종만 남으면 ValueError 나야 함")
    except ValueError:
        print("OK: 중복 제거 후 1종 -> ValueError")

    print("\n=== 테스트 5: N종 조합 (3개 입력, 아세톤 중복 1개 섞임 -> 중복 제거) ===")
    cv = eng.judge_combination_by_cas(["7664-93-9", "67-64-1", "67-64-1"])
    assert cv.inputs == ["67-64-1", "7664-93-9"], "중복 제거 후 2종이어야 함"
    assert len(cv.pair_verdicts) == 1, "2종이면 쌍은 C(2,2)=1개"
    assert cv.category == "Incompatible", "황산 x 아세톤은 Incompatible (테스트3과 동일 쌍)"
    print(cv.pretty())

    print("\n=== 테스트 6: N종 조합 (3개 입력, 미등록 CAS 하나 섞임 -> Abstain 전파) ===")
    cv2 = eng.judge_combination_by_cas(["7664-93-9", "67-64-1", "0000-00-0"])
    assert len(cv2.pair_verdicts) == 3, "3종이면 쌍은 C(3,2)=3개"
    assert cv2.category == "Incompatible", "다른 쌍이 Incompatible이면 Abstain보다 우선"
    assert cv2.abstain_notes, "미등록 CAS로 인한 abstain_notes는 결과에 살아있어야 함(침묵 금지)"
    print(cv2.pretty())

    print("\n=== 테스트 7: N종 조합 실물 3종 (황산/아세톤/과산화수소) - 전체 리포트 ===")
    cv3 = eng.judge_combination_by_cas(["7664-93-9", "67-64-1", "7722-84-1"])
    assert len(cv3.pair_verdicts) == 3, "3종이면 쌍은 3개"
    assert len(cv3.profiles) == 3, "입력 3종이면 프로필도 3개"
    assert all(p.mapped for p in cv3.profiles), "이 3종은 전부 DB 매핑 있음"
    print(cv3.full_report())

    eng.close()
