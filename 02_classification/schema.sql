-- MSDS 위험성평가 자동화 : CAMEO 68그룹 반응성 참조 스키마
-- source: Cameo_reactivity.csv (CAMEO Chemicals Reactivity Group Compatibility Chart)
-- engine: SQLite

PRAGMA foreign_keys = ON;

CREATE TABLE reactivity_groups (
    group_id    INTEGER PRIMARY KEY,      -- CAMEO 1~68
    group_name  TEXT NOT NULL UNIQUE,
    source      TEXT NOT NULL DEFAULT 'CAMEO_68'
);

CREATE TABLE hazard_code_legend (
    code        TEXT PRIMARY KEY,         -- C,E,F,G,NR,R1,R2,R3,R4,T,UR
    description TEXT NOT NULL
);

CREATE TABLE gas_product_legend (
    code        TEXT PRIMARY KEY,         -- CO, CO2, HX, N2 ...
    full_name   TEXT NOT NULL
);

-- 그룹쌍 매트릭스 (off-diagonal, group_a_id < group_b_id 로 정규화하여 중복 저장 방지)
CREATE TABLE compatibility_pairs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    group_a_id        INTEGER NOT NULL REFERENCES reactivity_groups(group_id),
    group_b_id        INTEGER NOT NULL REFERENCES reactivity_groups(group_id),
    category          TEXT NOT NULL CHECK(category IN ('Compatible','Caution','Incompatible','Unknown')),
    description       TEXT,               -- Summary 차트 원문 (예: "Generates heat,Flammable")
    hazard_codes_raw  TEXT,               -- Hazard Codes 차트 원문 (예: "F,G,R1,R3,T")
    gas_products_raw  TEXT,               -- Gas Products 차트 원문 (예: "CO,CO2")
    source            TEXT NOT NULL DEFAULT 'CAMEO_68',
    UNIQUE(group_a_id, group_b_id),
    CHECK(group_a_id < group_b_id)
);

-- 정규화 조인 테이블: 위험코드/기체생성물 다중값을 필터링 가능하게 분리
CREATE TABLE compatibility_hazard_codes (
    pair_id     INTEGER NOT NULL REFERENCES compatibility_pairs(id) ON DELETE CASCADE,
    hazard_code TEXT NOT NULL REFERENCES hazard_code_legend(code),
    PRIMARY KEY (pair_id, hazard_code)
);

CREATE TABLE compatibility_gas_products (
    pair_id     INTEGER NOT NULL REFERENCES compatibility_pairs(id) ON DELETE CASCADE,
    gas_code    TEXT NOT NULL REFERENCES gas_product_legend(code),
    PRIMARY KEY (pair_id, gas_code)
);

-- 자기반응(대각선, group_id = group_id) 전용 테이블
-- CAMEO 원자료(Cameo_reactivity.csv)에는 자기 자신과의 반응 데이터가 없음(오프대각 2,278쌍만 제공).
-- 기본값 'Unknown' -> 프로젝트 기각(Abstain) 정책 적용 대상. 값 채우기 전까지 단독 판정 금지.
CREATE TABLE self_reactivity (
    group_id    INTEGER PRIMARY KEY REFERENCES reactivity_groups(group_id),
    category    TEXT NOT NULL DEFAULT 'Unknown' CHECK(category IN ('Compatible','Caution','Incompatible','Unknown')),
    notes       TEXT
);

CREATE INDEX idx_pairs_group_a ON compatibility_pairs(group_a_id);
CREATE INDEX idx_pairs_group_b ON compatibility_pairs(group_b_id);
CREATE INDEX idx_pairs_category ON compatibility_pairs(category);
