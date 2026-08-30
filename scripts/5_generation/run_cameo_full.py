"""STEP 5 최종: 파일럿(13건, v4 프롬프트)에서 검증된 CAMEO+MSDS 컨텍스트 파이프라인을
2,160건 전체에 적용해 최종 결과를 고정한다.

프롬프트/모델/Retrieval/평가 조건은 전혀 바꾸지 않는다 — run_cameo_context_pilot.py의
build_prompt/SYSTEM_PROMPT(v4, 사용자 작성), eval_generation.py의 rule_based()/judge()를
그대로 재사용한다. 재개 가능(이미 생성/채점된 query_id는 건너뜀, 매 건 flush) —
generate_baseline.py/eval_generation.py와 동일한 재개 패턴.

v4 도입 시 반영한 2가지(파일럿에서 확정, 여기서도 동일 적용):
1. CL.format_context(..., detailed=True) — CAMEO 실제 hazard code/gas product 원문 노출.
2. judge() 호출 시 cameo_context를 합성 청크(__cameo_context__)로 근거에 포함 — 안 하면
   judge가 CAMEO를 정당하게 인용한 답변도 "근거 없음"으로 오탐한다(파일럿에서 실측, 11/13
   ->0/13 unfaithful로 뒤집힘).

동시실행: 순차 실행 시 2,160건 * ~38s(생성+채점) ≈ 20시간+ 추정됨. 이 구간은 STEP1에서
retrieval을 이미 고정해뒀기 때문에(frozen_retrieval_top10.jsonl) 로컬 GPU/임베딩 연산이
전혀 없고 순수 원격 API 호출뿐이라 스레드 병렬화가 안전하다(과거 관측된 세그폴트는
torch/FAISS 로컬 모델 반복 로딩 문제로, 이 경로와 무관 — docs/HANDOFF.md §0-1 참고).
개별 실패는 error 필드에 기록하고 배치를 막지 않는다(기존 동작 유지).

  python 04_rag_agent/run_cameo_full.py --n 20 --workers 8   # 소규모 동시성 검증 먼저
  python 04_rag_agent/run_cameo_full.py --workers 8          # 전체(이어서 실행 가능)
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "src"))

import llm as L  # noqa: E402
import generate_baseline as GB  # noqa: E402
import eval_generation as EV  # noqa: E402
import cameo_group_lookup as CL  # noqa: E402
from run_cameo_context_pilot import (  # noqa: E402
    build_prompt, build_schema_prompt, parse_stated_verdict, render_answer,
    PROMPT_VERSION, RESPONSE_FORMAT, SCHEMA_PROMPT_VERSION,
)
from eval_generation import substance_confused  # noqa: E402

FROZEN_PATH = ROOT / "results" / "frozen_retrieval_top10.jsonl"
GEN_OUT = ROOT / "results" / "generation_cameo_full.jsonl"
EVAL_OUT = ROOT / "results" / "eval_cameo_full.jsonl"

# 컨텍스트 구성 방식. "frozen" = 검색 top-10 그대로(2026-08-29 baseline 재현 경로).
# "pair" = 쌍의 두 CAS 에 속한 청크 전부(검색 우회). service 코퍼스는 물질당 청크가
# 평균 2.14개뿐이라 top-10 의 6.6개가 구조적으로 제3물질이었고, 그게 물질혼동 14.7%의
# 원인이었다. pair 모드는 gold_evidence 를 2,240건 전건 포함하며(실측) 컨텍스트가
# 평균 4.29개로 줄어 프롬프트 토큰도 57% 감소한다.
CONTEXT_MODE = "frozen"

# 출력 계약. "text" = 자유 텍스트(v7 재현 경로). "schema" = structured output.
# schema 모드는 reasoning 을 쓰지 않는다 — 20건 실측에서 품질은 동등하거나 낫고
# (judge 일치 20/20, Caution 과잉서술 0/7) 출력 토큰은 1/5.7, 비용은 1/2.8이었다.
# 이 과제는 추론이 아니라 추출·강도보존 번역이라 추론 예산이 부연으로 새어나갔다.
OUTPUT_FORMAT = "text"

# 처리할 query_id 화이트리스트(None = 전체). 계층 표집한 서브샘플로 두 프롬프트를
# 같은 문항에서 짝지어 비교하려면 필요하다 — --n 은 리스트 앞부분만 잘라 계층이 깨진다.
ONLY_IDS: set[str] | None = None
CITATION_RE = __import__("re").compile(r"\[사용한\s*근거\s*:")


def pair_chunk_ids(cur, cas_a: str, cas_b: str) -> list[str]:
    """쌍의 두 물질이 service 코퍼스에 가진 §2·§10 청크 전부. 순서는 결정적으로.

    인용 번호가 이 순서에 대응하므로(프롬프트의 [근거 n]) 정렬을 고정한다.
    """
    q = (
        "select c.chunk_id, c.cas_number, c.section from rag_chunks c "
        "join rag_corpus_membership m on m.cas_number = c.cas_number "
        "where m.corpus_tag = 'service' and c.granularity = 'section' "
        "and c.section in (2, 10) and c.cas_number in (?, ?)"
    )
    rows = cur.execute(q, (cas_a, cas_b)).fetchall()
    order = {cas_a: 0, cas_b: 1}
    rows.sort(key=lambda r: (order.get(r[1], 9), r[2], r[0]))
    return [r[0] for r in rows]


def load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def already_done(path: Path, err_field: str = "error") -> set[str]:
    """'완료'는 성공한 건만이다. 실패 레코드(err_field 채워짐)는 제외해서
    같은 명령을 다시 돌리면 그 건만 재시도되게 한다 — 종전처럼 query_id만 보면
    일시적 429/파싱 실패가 영구 결손으로 굳는다."""
    if not path.exists():
        return set()
    done = set()
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if rec.get(err_field) is None:
                    done.add(rec["query_id"])
            except (json.JSONDecodeError, KeyError):
                continue
    return done


def dedupe_records(rows: list[dict], err_field: str) -> list[dict]:
    """재시도로 같은 query_id 가 여러 줄일 수 있다. 성공본을 우선해 하나만 남긴다."""
    best: dict[str, dict] = {}
    for r in rows:
        cur = best.get(r["query_id"])
        if cur is None or cur.get(err_field) is not None:
            best[r["query_id"]] = r
    return list(best.values())


def _call_generate(r: dict, cameo_category: str, cameo_ctx: str, prompt: str,
                   context_ids: list[str]) -> dict:
    """네트워크 호출만 담당(스레드에서 실행) — sqlite 접근 없음.

    빈 본문과 인용 태그 누락은 예외가 아니라서 그냥 두면 조용히 채점까지 흘러간다.
    둘 다 확률적이라 1회 재호출로 대부분 붙고(태그 누락 6.6% 관측), 그래도 안 되면
    error 로 승격해 already_done 이 재시도 대상으로 잡게 한다.
    """
    t0 = time.perf_counter()
    answer = usage = finish = structured = None
    error = None
    for attempt in range(2):
        try:
            schema = OUTPUT_FORMAT == "schema"
            data = L.chat(
                [{"role": "user", "content": prompt}],
                max_tokens=GB.MAX_TOKENS,
                reasoning_effort=None if schema else GB.REASONING_EFFORT,
                response_format=RESPONSE_FORMAT if schema else None,
            )
            choice = data["choices"][0]
            raw = choice["message"]["content"]
            usage = data.get("usage", {})
            finish = choice.get("finish_reason")
            if schema:
                # 스키마 모드에서도 answer 는 조립된 텍스트로 남긴다 —
                # judge/rule_based 가 그대로 채점해야 v7 과 지표가 비교 가능하다.
                structured = json.loads(raw)
                # 판정은 CAMEO 값을 그대로 주입한다(모델에게 묻지 않는다).
                answer = render_answer(structured, r["name_a"], r["name_b"], cameo_category)
                error = None
                break
            answer = raw
            if not (answer or "").strip():
                error = f"EmptyAnswer: finish_reason={finish}"
            elif not CITATION_RE.search(answer):
                error = "MissingCitationTag"
            else:
                error = None
                break
        except Exception as e:  # noqa: BLE001 - 배치 중 개별 실패로 전체를 잃지 않음
            answer = None
            structured = None
            usage = {}
            finish = None
            error = f"{type(e).__name__}: {str(e)[:300]}"
            break  # HTTP 오류는 L.chat 이 이미 자체 재시도했다
    usage = usage or {}
    latency = round(time.perf_counter() - t0, 3)
    return {
        "query_id": r["query_id"],
        "query": r["query"],
        "cas_a": r["cas_a"],
        "cas_b": r["cas_b"],
        "name_a": r["name_a"],
        "name_b": r["name_b"],
        "matrix_verdict": r["matrix_verdict"],
        "cameo_category": cameo_category,
        "cameo_context": cameo_ctx,
        "gold_evidence": r["gold_evidence"],
        "retrieval_status": r["retrieval_status"],
        "context_ids": context_ids,
        "generated_answer": answer,
        "structured": structured,
        "model": L.MODEL,
        "finish_reason": finish,
        "prompt_version": SCHEMA_PROMPT_VERSION if OUTPUT_FORMAT == "schema" else PROMPT_VERSION,
        "latency_sec": latency,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "error": error,
    }


def run_generation(limit: int | None, workers: int) -> None:
    rows = load_jsonl(FROZEN_PATH)
    done = already_done(GEN_OUT, "error")
    todo = [r for r in rows if r["query_id"] not in done
            and (ONLY_IDS is None or r["query_id"] in ONLY_IDS)]
    if limit is not None:
        todo = todo[:limit]
    print(f"전체 {len(rows)}건, 완료 {len(done)}건, 이번 생성 {len(todo)}건 (workers={workers})")

    # sqlite 조회(CAMEO lookup + MSDS 청크 텍스트)는 로컬이라 빠름 — 메인 스레드에서 전부
    # 미리 끝내고, 느린 네트워크 호출(L.chat)만 스레드풀로 동시 실행한다.
    con = sqlite3.connect(ROOT / "data" / "reactivity_reference.db")
    cur = con.cursor()
    prepared = []
    for r in todo:
        cameo = CL.lookup(cur, r["cas_a"], r["cas_b"])
        cameo_ctx = CL.format_context(cameo, r["name_a"], r["name_b"], detailed=True)
        if CONTEXT_MODE == "pair":
            chunk_ids = pair_chunk_ids(cur, r["cas_a"], r["cas_b"])
            # retrieval_status 는 frozen 파일 값이라 pair 모드에서는 맞지 않는다.
            # 실제 컨텍스트에 gold 가 들어있는지로 다시 매긴다(abstention_bucket 이 쓴다).
            gold = set(r.get("gold_evidence") or [])
            r = {**r, "retrieval_status": "hit" if gold and gold <= set(chunk_ids) else "miss"}
        else:
            chunk_ids = [c["chunk_id"] for c in r["retrieved"]]
        texts = GB.load_texts(cur, chunk_ids)
        contexts = [{"chunk_id": cid, "text": texts.get(cid, "")} for cid in chunk_ids]
        mk = build_schema_prompt if OUTPUT_FORMAT == "schema" else build_prompt
        prompt = mk(r["query"], cameo_ctx, contexts)
        prepared.append((r, cameo.category, cameo_ctx, prompt, chunk_ids))
    con.close()

    GEN_OUT.parent.mkdir(parents=True, exist_ok=True)
    out_f = GEN_OUT.open("a", encoding="utf-8")
    n_done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_call_generate, r, cat, ctx, p, cids): r
                   for r, cat, ctx, p, cids in prepared}
        for fut in as_completed(futures):
            rec = fut.result()
            n_done += 1
            out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out_f.flush()
            print(f"[gen {n_done}/{len(todo)}] {rec['query_id']} {'실패' if rec['error'] else '완료'} "
                  f"(cameo={rec['cameo_category']}) ({rec['latency_sec']}s)", flush=True)
    out_f.close()


def _call_eval(r: dict, contexts_by_id: dict[str, str]) -> dict:
    """네트워크 호출(judge)만 담당(스레드에서 실행) — sqlite 접근 없음."""
    rb = EV.rule_based(r)
    # judge_rec: cameo_context를 합성 청크(__cameo_context__)로 근거에 포함(v4 파일럿에서
    # 확정 — 안 하면 CAMEO를 정당하게 인용한 답변도 judge가 "근거 없음"으로 오탐한다).
    judge_rec = {**r, "context_ids": r.get("context_ids", []) + ["__cameo_context__"]}
    t0 = time.perf_counter()
    # judge 응답의 JSON 파싱 실패는 확률적이다(파일럿 1/20). 같은 프롬프트로 다시 부르면
    # 대개 붙으므로 3회까지 시도한다. HTTP 오류는 L.chat 이 이미 자체 재시도한다.
    jr = {"predicted_verdict": None, "faithful": None, "unsupported_claims": None}
    error = None
    for attempt in range(3):
        try:
            jr = EV.judge(judge_rec, contexts_by_id)
            error = None
            break
        except Exception as e:  # noqa: BLE001
            error = f"{type(e).__name__}: {str(e)[:300]}"
    latency = round(time.perf_counter() - t0, 3)
    matrix_verdict = r.get("matrix_verdict")
    pv = jr["predicted_verdict"]
    abstained = pv == "Abstain" if pv is not None else rb["abstained_lexical"]
    answer_correct = None if pv in (None, "Abstain") else (pv == matrix_verdict)
    stated_verdict = parse_stated_verdict(r.get("generated_answer"))
    kept_cameo_verdict = None if stated_verdict is None else (stated_verdict == r.get("cameo_category"))
    tag_body_consistent = None if pv is None or stated_verdict is None else (pv == stated_verdict)
    confused = substance_confused(r, {**rb, **jr})
    return {
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


def run_eval(limit: int | None, workers: int) -> None:
    rows = [r for r in dedupe_records(load_jsonl(GEN_OUT), "error") if r.get("error") is None]
    done = already_done(EVAL_OUT, "judge_error")
    todo = [r for r in rows if r["query_id"] not in done
            and (ONLY_IDS is None or r["query_id"] in ONLY_IDS)]
    if limit is not None:
        todo = todo[:limit]
    print(f"채점 대상 {len(rows)}건, 완료 {len(done)}건, 이번 채점 {len(todo)}건 (workers={workers})")

    con = sqlite3.connect(ROOT / "data" / "reactivity_reference.db")
    cur = con.cursor()
    prepared = []
    for r in todo:
        context_ids = r.get("context_ids", [])
        if context_ids:
            q = "select chunk_id, text from rag_chunks where chunk_id in ({})".format(
                ",".join("?" * len(context_ids))
            )
            contexts_by_id = dict(cur.execute(q, context_ids).fetchall())
        else:
            contexts_by_id = {}
        contexts_by_id["__cameo_context__"] = r.get("cameo_context", "")
        prepared.append((r, contexts_by_id))
    con.close()

    EVAL_OUT.parent.mkdir(parents=True, exist_ok=True)
    out_f = EVAL_OUT.open("a", encoding="utf-8")
    n_done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_call_eval, r, ctx): r for r, ctx in prepared}
        for fut in as_completed(futures):
            rec = fut.result()
            n_done += 1
            out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out_f.flush()
            print(f"[eval {n_done}/{len(todo)}] {rec['query_id']} "
                  f"{'실패' if rec['judge_error'] else '완료'} ({rec['judge_latency_sec']}s)", flush=True)
    out_f.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=None, help="처리할 최대 건수(미지정시 전체, 이미 완료된 건 제외)")
    ap.add_argument("--stage", choices=["gen", "eval", "both"], default="both")
    ap.add_argument("--workers", type=int, default=8, help="동시 API 호출 수")
    ap.add_argument("--context", choices=["frozen", "pair"], default="frozen",
                    help="frozen=검색 top-10 그대로(baseline 재현). "
                         "pair=쌍의 두 CAS 청크 전부(검색 우회)")
    ap.add_argument("--format", choices=["text", "schema"], default="text",
                    help="text=자유 텍스트(v7 재현). schema=structured output "
                         "(판정/인용/결론을 스키마로 고정, reasoning 미사용)")
    ap.add_argument("--ids", help="처리할 query_id 목록 파일(줄당 1개). 미지정시 전체")
    ap.add_argument("--tag", default="",
                    help="출력 파일 접미사. 출력은 append+재개라 조건이 다른 실행이 "
                         "같은 파일에 섞이면 되돌릴 수 없다. 예: pair, pair_v7")
    args = ap.parse_args()

    if (args.context != "frozen" or args.format != "text") and not args.tag:
        ap.error("--context/--format 을 바꿀 때는 --tag 로 출력을 분리해야 합니다 "
                 "(기존 결과에 덮어쓰기 방지). 예: --context pair --format schema --tag pair_v8")

    # ponytail: 모듈 전역 재바인딩. 경로를 여러 함수에 인자로 흘리는 것보다 짧다.
    global CONTEXT_MODE, OUTPUT_FORMAT, GEN_OUT, EVAL_OUT, ONLY_IDS
    CONTEXT_MODE = args.context
    OUTPUT_FORMAT = args.format
    if args.ids:
        ONLY_IDS = {l.strip() for l in Path(args.ids).read_text(encoding="utf-8").splitlines() if l.strip()}
        print(f"대상 제한: {args.ids} ({len(ONLY_IDS)}건)")
    if args.tag:
        GEN_OUT = GEN_OUT.with_name(f"{GEN_OUT.stem}_{args.tag}{GEN_OUT.suffix}")
        EVAL_OUT = EVAL_OUT.with_name(f"{EVAL_OUT.stem}_{args.tag}{EVAL_OUT.suffix}")
    print(f"컨텍스트 모드: {CONTEXT_MODE} · 출력 계약: {OUTPUT_FORMAT}")
    print(f"  생성 출력: {GEN_OUT.name}")
    print(f"  채점 출력: {EVAL_OUT.name}")

    if args.stage in ("gen", "both"):
        run_generation(args.n, args.workers)
    if args.stage in ("eval", "both"):
        run_eval(args.n, args.workers)
    for path, field in ((GEN_OUT, "error"), (EVAL_OUT, "judge_error")):
        if not path.exists():
            continue
        recs = dedupe_records(load_jsonl(path), field)
        bad = [r for r in recs if r.get(field) is not None]
        print(f"저장: {path}  성공 {len(recs) - len(bad)} / 실패 {len(bad)}")
        if bad:
            print(f"  -> 같은 명령을 다시 실행하면 실패분만 재시도됩니다. 예: {bad[0][field][:120]}")


if __name__ == "__main__":
    main()
