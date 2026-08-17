"""Judge 비용 최적화: Rule Judge -> Small LLM Judge -> Large LLM Judge(fallback).

기존 Large Judge(eval_generation.judge(), nemotron-3-nano-omni-30b, ~9.2s/건)를 모든
건에 호출하던 구조를 대체한다. 평가 기준(JUDGE_PROMPT, predicted_verdict/faithful/
unsupported_claims schema)은 바꾸지 않는다 — eval_generation.judge()를 모델만 바꿔
그대로 재사용(Small Judge = meta/llama-3.1-8b-instruct, 같은 엔드포인트/키, ~1.5s/건).

라우팅 (CAMEO-context 파이프라인 전용 — 답변이 "판정: X / 요약 / 근거" 구조를 강제받고
CAMEO 판정값을 그대로 진술하게 되어 있다는 전제, run_cameo_context_pilot.py 참고):

  1) Rule Judge (LLM 호출 없음) — 기계적으로 확실한 경우만 여기서 종결:
     - format_error   : "판정:" 줄도 없고 Abstain 문구도 없음 -> 명백한 출력 형식 오류
     - abstain        : Abstain 문구만 있고 "판정:" 줄 없음 -> 깨끗한 Abstain
     - category_mismatch : "판정:" 값이 CAMEO 제공값과 다름 -> 규칙4 위반(명백한 불일치)
     그 외(= "판정:" 값이 CAMEO 값과 일치하는 깨끗한 답변)는 faithful 여부가 순수
     의미 판단이라 규칙으로 못 끝냄 -> Small Judge로 넘김.
     "판정:" 값이 있으면서 동시에 Abstain 문구도 있는 경우(태그-본문 모순, 파일럿
     13건 중 1건 관찰)는 규칙으로 억지 판정하지 않고 바로 Small Judge로 넘긴다.

  2) Small Judge — Large와 동일 프롬프트/schema, 작은 모델로 호출.
     아래 중 하나면 신뢰 못 함 -> Large Judge로 escalate:
     - JSON 파싱 실패(API/형식 오류)
     - Small이 낸 predicted_verdict가 "판정:" 태그 값과 다름(자기모순 신호,
       Large Judge에서도 이런 태그-본문 불일치를 잡아낸 전례가 있음)

  3) Large Judge fallback — 위 escalate 대상만 호출.

  python 04_rag_agent/cascade_judge.py --check   # 연결 점검(작은 모델 1건 호출)
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import llm as L  # noqa: E402
import eval_generation as EV  # noqa: E402
from run_cameo_context_pilot import parse_stated_verdict  # noqa: E402

SMALL_MODEL = "meta/llama-3.1-8b-instruct"
SMALL_REASONING_BUDGET = 0  # 추론형 모델이 아님 — reasoning_budget 불필요


def rule_judge(rec: dict) -> dict | None:
    """규칙만으로 확정 가능하면 최종 판정 dict, 애매하면 None(에스컬레이션 필요)."""
    answer = rec.get("generated_answer") or ""
    stated_verdict = parse_stated_verdict(answer)
    abstain_lexical = EV.ABSTAIN_PHRASE in answer
    cameo_category = rec.get("cameo_category")

    if stated_verdict is not None and abstain_lexical:
        return None  # 태그-본문 모순 -> Small Judge

    if stated_verdict is None and not abstain_lexical:
        return {
            "predicted_verdict": None,
            "faithful": False,
            "unsupported_claims": "형식 오류: '판정:' 줄과 Abstain 문구 모두 없음",
            "judge_tier": "rule",
            "judge_reason": "format_error",
        }

    if stated_verdict is None and abstain_lexical:
        return {
            "predicted_verdict": "Abstain",
            "faithful": True,
            "unsupported_claims": "",
            "judge_tier": "rule",
            "judge_reason": "abstain",
        }

    # stated_verdict is not None and not abstain_lexical
    if cameo_category is not None and stated_verdict != cameo_category:
        return {
            "predicted_verdict": stated_verdict,
            "faithful": False,
            "unsupported_claims": f"CAMEO 판정({cameo_category})과 다른 판정을 진술함(규칙4 위반)",
            "judge_tier": "rule",
            "judge_reason": "category_mismatch",
        }

    return None  # 태그가 CAMEO 값과 일치하는 깨끗한 답변 -> faithful 판단은 Small Judge로


def judge_cascade(rec: dict, contexts_by_id: dict[str, str]) -> dict:
    resolved = rule_judge(rec)
    if resolved is not None:
        return resolved

    stated_verdict = parse_stated_verdict(rec.get("generated_answer") or "")
    try:
        small = EV.judge(rec, contexts_by_id, model=SMALL_MODEL, reasoning_budget=SMALL_REASONING_BUDGET)
        small_failed = False
    except Exception:  # noqa: BLE001 - 파싱/API 오류 시 Large로 escalate
        small = None
        small_failed = True

    disagree = (
        not small_failed
        and stated_verdict is not None
        and small["predicted_verdict"] is not None
        and small["predicted_verdict"] != stated_verdict
    )

    if small_failed or disagree:
        large = EV.judge(rec, contexts_by_id)  # 기본값 = 기존 Large Judge, 예외는 상위(run_eval)로 전파
        large["judge_tier"] = "large_fallback"
        large["judge_reason"] = "small_json_error" if small_failed else "small_tag_disagreement"
        return large

    small["judge_tier"] = "small"
    small["judge_reason"] = None
    return small


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check:
        data = L.chat(
            [{"role": "user", "content": "한 단어로만 답하시오: 물의 화학식은?"}],
            model=SMALL_MODEL,
            max_tokens=50,
            reasoning_budget=SMALL_REASONING_BUDGET,
            timeout=30,
        )
        print(f"Small Judge 모델: {SMALL_MODEL}")
        print(f"응답: {data['choices'][0]['message']['content'].strip()}")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
