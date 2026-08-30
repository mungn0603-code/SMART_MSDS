"""Stage 4 검색계층: Embedding -> FAISS + BM25 -> Hybrid Search -> Reranker

설계 근거: docs/stage4_design_principles_v2.md §3, §4, §5, §7

미규정 파라미터에 대한 선택(설계문서에 없어 관례 기본값 사용, 리포트에 명시):
  - Hybrid 융합 = RRF(Reciprocal Rank Fusion, k=60). 점수 스케일이 다른
    dense/BM25를 가중치 튜닝 없이 합치는 표준 무파라미터 방식.
  - BM25 토크나이저 = kiwipiepy 형태소 분석 (조사/어미/기호 제거).
  - FAISS = IndexFlatIP + 정규화 벡터(= 코사인). 청크 8천개 규모라 근사색인 불필요.
"""

from __future__ import annotations

import hashlib
import os
import pickle
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "reactivity_reference.db"
CACHE_DIR = ROOT / "data" / "index"

RRF_K = 60
MAX_SEQ_LEN = 2048

# STEP 2/3 실측 확정(2026-08-08): §10 "피해야 할 물질" 중 173종 코퍼스 안에서 2회 이상
# 반복되는 정형문구 15종(evidence_full173_tagged.jsonl 태깅으로 식별, 목록은
# archive/2026-08-30_superseded/data_inputs/boilerplate_sec10_values.json)이 BM25 어휘매칭으로 상위 rank를 차지해 실제 evidence(§2 분류)를 밀어내는 문제를
# 완화하려고 RRF 융합 시 고정 penalty를 도입(Evidence MRR 0.52->0.83).
# 2026-08-09 확장: gold_evidence 재정의상 상대 물질을 직접 지목하는 §10은 0건 확인됨(§0-3
# STEP2) - 즉 boilerplate 여부와 무관하게 **§10 청크는 전부 gold_evidence가 될 수 없다**.
# 정형문구 15종만 감점하던 기존 범위를 §10 전체로 넓힘(실측: 나머지 173종/2,160질의에서
# 추가로 MRR 0.835->0.917, nDCG@10 0.791->0.850, 다른 지표 전부 동반 상승/±0 - 악화 없음).
# lambda 값은 그대로(튜닝 아님, 적용 범위만 확장). §10 자체는 검색 대상에서 제거하지 않는다.
BOILERPLATE_PENALTY_LAMBDA = 0.01

EMBEDDING_MODELS = {
    "bge-m3": "BAAI/bge-m3",
    "bge-m3-ko": "dragonkue/BGE-m3-ko",
    "KURE": "nlpai-lab/KURE-v1",
}

RERANKER_MODELS = {
    "bge-reranker-v2-m3": "BAAI/bge-reranker-v2-m3",
    "bge-reranker-base": "BAAI/bge-reranker-base",
}

_DROP_TAG_PREFIX = ("J", "E")  # 조사, 어미
_DROP_TAGS = {"SF", "SP", "SS", "SSO", "SSC", "SE", "SO", "SW", "SB"}  # 문장부호/괄호
_kiwi = None


def tokenize_ko(text: str) -> list[str]:
    global _kiwi
    if _kiwi is None:
        from kiwipiepy import Kiwi

        _kiwi = Kiwi()
    out = []
    for t in _kiwi.tokenize(text):
        if t.tag in _DROP_TAGS or t.tag.startswith(_DROP_TAG_PREFIX):
            continue
        out.append(t.form.lower())
    return out


@dataclass
class Corpus:
    chunk_ids: list[str]
    texts: list[str]
    meta: list[dict]

    def __len__(self) -> int:
        return len(self.chunk_ids)


def load_corpus(granularity: str, corpus_tag: str | None = None) -> Corpus:
    """corpus_tag=None이면 기존 동작 그대로(모든 활성 청크, 하위호환).

    PHASE 5 교훈(중요): rag_chunks.chunk_id(예: sec::{cas}::{section})는 cas+section
    으로만 정해지고 어느 "코퍼스 정의"에서 왔는지와 무관한 content-addressed 키다.
    426종 대상과 259종(proposed final) 대상을 각각 다른 rag_chunks.version 태그로
    두 번 실행했더니, 두 코퍼스가 공유하는 CAS의 chunk_id가 겹쳐서 INSERT OR REPLACE가
    나중 실행의 version으로 덮어써버렸다(426 전용 202 3종만 남고 나머지는 259 태그로
    바뀜 — 실측 확인). 즉 **rag_chunks.version은 코퍼스 멤버십 필터로 신뢰할 수 없다.**
    대신 별도의 `rag_corpus_membership(corpus_tag, cas_number)` 테이블(코퍼스 정의 CSV의
    cas_number만 담음, 청크 내용과 무관)로 어느 코퍼스에 어떤 CAS가 속하는지를
    관리하고, 여기서 cas_number 기준으로 rag_chunks를 필터링한다 — chunk_id 충돌
    문제와 완전히 무관해지는 방식.
    """
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    if corpus_tag:
        rows = con.execute(
            "select rc.chunk_id, rc.text, rc.cas_number, rc.chemical_name, rc.section, rc.item_codes, "
            "       rc.evidence_grade, rc.evidence_grades, rc.cameo_groups, rc.abstain "
            "from rag_chunks rc "
            "join rag_corpus_membership m on m.cas_number = rc.cas_number and m.corpus_tag = ? "
            "where rc.granularity=? and rc.status='active' order by rc.chunk_id",
            (corpus_tag, granularity),
        ).fetchall()
    else:
        rows = con.execute(
            "select chunk_id, text, cas_number, chemical_name, section, item_codes, "
            "       evidence_grade, evidence_grades, cameo_groups, abstain "
            "from rag_chunks where granularity=? and status='active' order by chunk_id",
            (granularity,),
        ).fetchall()
    con.close()
    if not rows:
        raise SystemExit(f"rag_chunks 에 granularity={granularity} corpus_tag={corpus_tag} 청크가 없음. "
                          f"pipeline.py 먼저 실행하거나 rag_corpus_membership을 확인할 것.")
    return Corpus(
        chunk_ids=[r["chunk_id"] for r in rows],
        texts=[r["text"] for r in rows],
        meta=[dict(r) for r in rows],
    )


def boilerplate_penalty_vector(corpus: Corpus, lam: float = BOILERPLATE_PENALTY_LAMBDA) -> np.ndarray:
    """corpus 청크별 penalty(section=10이면 lam, 아니면 0 - gold_evidence는 전부 §2이므로 §10은 전부 비정답)."""
    return np.array([lam if m.get("section") == 10 else 0.0 for m in corpus.meta], dtype=np.float64)


def _cache(name: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / name


def torch_threads() -> int:
    """CPU 스레드 수 고정. 실측 결과 기본값으로는 8코어 중 ~2코어만 사용됨.
    레이턴시 실측(§12)을 비교 가능하게 하려면 전 실행에서 동일해야 하므로 여기서 통일한다.
    """
    import torch

    n = int(os.environ.get("MSDS_TORCH_THREADS") or os.cpu_count() or 4)
    torch.set_num_threads(n)
    return n


def embed_corpus(model_key: str, gran: str, corpus: Corpus, batch_size: int = 8, corpus_tag: str = "") -> np.ndarray:
    """문서 벡터 생성(+캐시). 200종 규모라 1회성 비용 — §4 판단근거.
    corpus_tag: PHASE 5의 426/259 코퍼스처럼 같은 model/gran 조합에서도 서로 다른
    코퍼스를 동시에 캐시해두고 싶을 때 구분용(예: "426"/"259proposed"). 비우면 기존
    동작과 동일한 파일명(하위호환)."""
    suffix = f"_{corpus_tag}" if corpus_tag else ""
    path = _cache(f"emb_{model_key}_{gran}{suffix}.npy")
    if path.exists():
        vecs = np.load(path)
        if len(vecs) == len(corpus):
            return vecs
    torch_threads()
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(EMBEDDING_MODELS[model_key])
    model.max_seq_length = MAX_SEQ_LEN
    vecs = model.encode(
        corpus.texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=True,
        convert_to_numpy=True,
    ).astype("float32")
    np.save(path, vecs)
    return vecs


def embed_queries(model_key: str, queries: list[str], tag: str, batch_size: int = 16) -> np.ndarray:
    # 질의문이 바뀌면(템플릿 수정) 캐시가 무효화되도록 내용 해시를 키에 포함.
    # 개수만 비교하면 수정된 질의에 옛 벡터를 그대로 쓰는 조용한 오류가 난다.
    digest = hashlib.sha256("\n".join(queries).encode("utf-8")).hexdigest()[:10]
    path = _cache(f"q_{model_key}_{tag}_{digest}.npy")
    if path.exists():
        vecs = np.load(path)
        if len(vecs) == len(queries):
            return vecs
    torch_threads()
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(EMBEDDING_MODELS[model_key])
    model.max_seq_length = MAX_SEQ_LEN
    vecs = model.encode(
        queries,
        batch_size=batch_size,
        normalize_embeddings=True,
        show_progress_bar=True,
        convert_to_numpy=True,
    ).astype("float32")
    np.save(path, vecs)
    return vecs


def build_faiss(vecs: np.ndarray):
    import faiss

    index = faiss.IndexFlatIP(vecs.shape[1])
    index.add(vecs)
    return index


def build_bm25(gran: str, corpus: Corpus, corpus_tag: str = ""):
    """BM25는 임베딩 모델과 무관하므로 granularity 단위로 캐시.

    pickle 사용: 이 스크립트가 같은 머신에서 직접 생성한 캐시만 읽는다(외부 입력 아님).
    BM25Okapi 객체가 JSON 직렬화 대상이 아니라 pickle 을 쓰며, 캐시 파일이 없거나
    청크 수가 다르면 무조건 재생성한다. corpus_tag는 embed_corpus와 동일한 용도.
    """
    suffix = f"_{corpus_tag}" if corpus_tag else ""
    path = _cache(f"bm25_{gran}{suffix}.pkl")
    if path.exists():
        with path.open("rb") as f:
            obj = pickle.load(f)
        if obj["n"] == len(corpus):
            return obj["bm25"]
    from rank_bm25 import BM25Okapi

    bm25 = BM25Okapi([tokenize_ko(t) for t in corpus.texts])
    with path.open("wb") as f:
        pickle.dump({"n": len(corpus), "bm25": bm25}, f)
    return bm25


def dense_rank(index, qvecs: np.ndarray, k: int) -> np.ndarray:
    _, idx = index.search(qvecs, k)
    return idx


def bm25_rank(bm25, queries: list[str], k: int) -> np.ndarray:
    out = np.empty((len(queries), k), dtype=np.int64)
    for i, q in enumerate(queries):
        scores = bm25.get_scores(tokenize_ko(q))
        out[i] = np.argsort(-scores)[:k]
    return out


def rrf_fuse(rank_lists: list[np.ndarray], k: int, rrf_k: int = RRF_K,
             penalty: np.ndarray | None = None) -> np.ndarray:
    """여러 랭킹을 Reciprocal Rank Fusion 으로 합침. rank_lists: [(nq, kk), ...]

    penalty: corpus 청크 수 길이의 배열(예: boilerplate_penalty_vector()). 지정하면
    각 후보의 RRF 점수에서 penalty[doc]를 뺀 뒤 재정렬한다(§10 boilerplate가 상위 rank를
    차지하는 문제 완화 - STEP 2/3 실측 확정, 미지정시 기존 동작과 완전히 동일/하위호환).
    """
    nq = rank_lists[0].shape[0]
    fused = np.empty((nq, k), dtype=np.int64)
    for i in range(nq):
        scores: dict[int, float] = {}
        for ranks in rank_lists:
            for pos, doc in enumerate(ranks[i]):
                scores[int(doc)] = scores.get(int(doc), 0.0) + 1.0 / (rrf_k + pos + 1)
        if penalty is not None:
            for doc in list(scores):
                scores[doc] -= float(penalty[doc])
        top = sorted(scores.items(), key=lambda kv: -kv[1])[:k]
        row = [d for d, _ in top]
        row += [-1] * (k - len(row))
        fused[i] = row
    return fused


def rerank(model_key: str, queries: list[str], cand: np.ndarray, corpus: Corpus, k: int) -> tuple[np.ndarray, float]:
    """CrossEncoder 로 후보 재정렬. 반환: (재정렬 랭킹, 총 소요초)"""
    import time

    torch_threads()
    from sentence_transformers import CrossEncoder

    ce = CrossEncoder(RERANKER_MODELS[model_key], max_length=512)
    out = np.empty((len(queries), k), dtype=np.int64)
    t0 = time.perf_counter()
    for i, q in enumerate(queries):
        docs = [int(d) for d in cand[i] if d >= 0]
        if not docs:
            out[i] = [-1] * k
            continue
        scores = ce.predict([(q, corpus.texts[d]) for d in docs], batch_size=16)
        order = np.argsort(-np.asarray(scores))
        ranked = [docs[j] for j in order][:k]
        ranked += [-1] * (k - len(ranked))
        out[i] = ranked
    return out, time.perf_counter() - t0
