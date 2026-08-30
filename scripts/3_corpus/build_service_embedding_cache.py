# -*- coding: utf-8 -*-
"""service 코퍼스 문서 임베딩 캐시를 기존 캐시에서 조립한다(재인코딩 없이).

왜 필요한가 (2026-08-28)
  retrieval.embed_corpus()는 corpus_tag별로 캐시를 따로 두고, 캐시가 없으면 코퍼스
  전체를 다시 인코딩한다. service 태그는 새 태그라 캐시가 없어 전량 재인코딩이
  걸리는데, CPU에서 배치 90개 x 약 70초 = 100분이 넘는다.

  그런데 service 코퍼스의 청크는 전부 '173' 또는 'core' 캐시에 이미 들어 있다
  (service 173종 = '173'∩Registry 84종 + 'core' 89종). 같은 모델, 같은 텍스트이므로
  chunk_id로 골라 담으면 재인코딩 결과와 완전히 동일하다.

  청크 텍스트가 바뀌면(재청킹) 이 스크립트를 쓰면 안 된다 - 그때는 캐시를 지우고
  embed_corpus()가 정상 인코딩하게 둔다. 아래에서 chunk_id뿐 아니라 텍스트 해시까지
  대조해 그런 경우를 막는다.

    python scripts/build_service_embedding_cache.py
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import retrieval as R  # noqa: E402

MODEL, GRAN = "bge-m3-ko", "section"
SOURCE_TAGS = ("173", "core")
TARGET_TAG = "service"


def _digest(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def main() -> int:
    pool: dict[str, np.ndarray] = {}
    pool_hash: dict[str, str] = {}
    for tag in SOURCE_TAGS:
        corpus = R.load_corpus(GRAN, corpus_tag=tag)
        path = R.CACHE_DIR / f"emb_{MODEL}_{GRAN}_{tag}.npy"
        if not path.exists():
            raise SystemExit(f"원본 캐시 없음: {path}")
        vecs = np.load(path)
        if len(vecs) != len(corpus):
            raise SystemExit(f"{tag}: 캐시 {len(vecs)}행 vs 코퍼스 {len(corpus)}청크 불일치")
        for cid, text, v in zip(corpus.chunk_ids, corpus.texts, vecs):
            pool[cid] = v
            pool_hash[cid] = _digest(text)
        print(f"  {tag}: {len(corpus)}청크 적재")

    target = R.load_corpus(GRAN, corpus_tag=TARGET_TAG)
    missing = [c for c in target.chunk_ids if c not in pool]
    if missing:
        raise SystemExit(
            f"기존 캐시에 없는 청크 {len(missing)}개 - 재인코딩이 필요하다: {missing[:5]}")
    changed = [c for c, t in zip(target.chunk_ids, target.texts)
               if pool_hash[c] != _digest(t)]
    if changed:
        raise SystemExit(
            f"텍스트가 바뀐 청크 {len(changed)}개 - 캐시 재사용 불가(재청킹된 것): {changed[:5]}")

    out = np.stack([pool[c] for c in target.chunk_ids])
    dest = R.CACHE_DIR / f"emb_{MODEL}_{GRAN}_{TARGET_TAG}.npy"
    np.save(dest, out)
    print(f"\n{TARGET_TAG}: {len(target)}청크 / {out.shape} -> {dest.name}")
    print("  (재인코딩 없이 조립. 텍스트 해시 전건 일치 확인)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
