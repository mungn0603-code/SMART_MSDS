"""Stage 4 LLM 클라이언트 — DeepSeek (deepseek-v4-flash, thinking mode)

설계 §3 파이프라인의 LLM 단계, 그리고 §10 RAG 지표(Faithfulness / Context Recall /
Context Precision / Answer Relevancy) · Abstain Precision 측정에 쓰인다.

  모델      : deepseek-v4-flash (thinking: enabled, reasoning_effort: high)
  엔드포인트 : https://api.deepseek.com/chat/completions (OpenAI 호환)
  인증      : .env 의 DEEPSEEK_API_KEY (gitignore 대상. 원문은 코드/로그/출력 어디에도 남기지 않음)

연결 점검:
    python 04_rag_agent/llm.py --check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

INVOKE_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-v4-flash"
MAX_TOKENS = 65536
REASONING_EFFORT = "high"


def _load_dotenv(path: Path = ROOT / ".env") -> None:
    """이미 설정된 환경변수는 덮어쓰지 않음 (01_collection 수집기와 동일 규약)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = (x.strip() for x in line.split("=", 1))
        if k and v and k not in os.environ:
            os.environ[k] = v


def _ensure_ca_bundle() -> None:
    """huggingface_hub 때와 동일한 SSL 문제 예방.

    certifi 번들에 로컬 루트 CA가 없어 인증서 검증이 실패하는 환경이다.
    Windows 인증서 저장소에서 만들어 둔 번들이 있으면 그것을 쓴다.
    검증을 끄지는 않는다. (생성: docs/stage4_design_changes_2026-08-06.md §9)
    """
    if "SSL_CERT_FILE" in os.environ:
        return
    bundle = Path.home() / ".cache" / "win_ca_bundle.pem"
    if bundle.exists():
        os.environ["SSL_CERT_FILE"] = str(bundle)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", str(bundle))


def api_key() -> str:
    _load_dotenv()
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise SystemExit(
            "DEEPSEEK_API_KEY 가 없음. 프로젝트 루트 .env 에 아래 한 줄을 추가하세요.\n"
            "  DEEPSEEK_API_KEY=<발급받은 키>\n"
            ".env 는 이미 .gitignore 에 등록되어 있습니다."
        )
    return key


def key_fingerprint() -> str:
    """키 원문 대신 로그·보고에 쓸 지문. 길이 + sha256 앞 10자리."""
    k = api_key()
    return f"len={len(k)} sha256={hashlib.sha256(k.encode()).hexdigest()[:10]}"


def chat(
    messages: list[dict],
    *,
    model: str = MODEL,
    max_tokens: int = MAX_TOKENS,
    reasoning_effort: str | None = REASONING_EFFORT,
    timeout: int = 180,
) -> dict:
    """단발 호출. 스트리밍은 쓰지 않는다(평가 배치 용도라 불필요).

    urllib 사용: requests 미설치 환경에서도 돌게 하고, 의존성을 늘리지 않는다.
    model: 기본값은 이 파일의 MODEL(현재 Generation/Large Judge용). Small Judge처럼
    다른 모델을 같은 엔드포인트/키로 호출할 때만 override.
    reasoning_effort: DeepSeek thinking 모델 전용 필드("low"/"high"/"max").
    temperature/top_p는 thinking 모드에서 무시되므로(DeepSeek 문서) 아예 보내지 않는다.
    None이면 payload에서 thinking을 아예 빼고 보낸다.
    """
    _ensure_ca_bundle()
    payload = {
        "messages": messages,
        "model": model,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if reasoning_effort is not None:
        payload["thinking"] = {"type": "enabled"}
        payload["reasoning_effort"] = reasoning_effort
    req = urllib.request.Request(
        INVOKE_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    # 일시적 서버 과부하(503)/rate limit(429) 재시도. 그 외 오류(4xx 등)는 즉시 올린다.
    # 2026-08-17 전수실행(workers=16, 2,054건)에서 685건이 429로 재시도 소진 후 실패한 걸
    # 보고 강화함: 기존 4회/최대 21초는 동시 스레드 다수가 거의 같은 타이밍에 몰려 재충돌하는
    # thundering herd를 못 버텼다. 시도 6회로 늘리고, 서버가 Retry-After를 주면 그걸 우선
    # 쓰고, 스레드 간 재시도 타이밍을 어긋나게 하는 jitter를 추가했다.
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == 5:
                raise
            retry_after = e.headers.get("Retry-After") if e.headers else None
            try:
                wait = float(retry_after) if retry_after else 2**attempt * 3
            except ValueError:
                wait = 2**attempt * 3
            wait += random.uniform(0, wait * 0.5)
            time.sleep(wait)


def ask(prompt: str, **kw) -> str:
    """본문 텍스트만 반환. reasoning 계열 모델이라 추론부는 분리해 버린다."""
    data = chat([{"role": "user", "content": prompt}], **kw)
    return data["choices"][0]["message"]["content"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="연결 점검(키 원문 미출력)")
    ap.add_argument("--prompt", help="단발 질의")
    args = ap.parse_args()

    if args.check:
        print(f"모델      : {MODEL}")
        print(f"엔드포인트 : {INVOKE_URL}")
        print(f"API 키    : {key_fingerprint()}")  # 원문 아님
        try:
            out = ask("한 단어로만 답하시오: 물의 화학식은?", max_tokens=2048, reasoning_effort="low")
            print(f"응답      : {out.strip()[:200]}")
            print("연결 정상")
        except Exception as e:  # noqa: BLE001
            print(f"연결 실패 : {type(e).__name__}: {str(e)[:300]}")
            raise SystemExit(1) from e
    elif args.prompt:
        print(ask(args.prompt))
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
