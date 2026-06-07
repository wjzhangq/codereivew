-- ===========================================================================
-- meta.sqlite — OLTP 主库 schema (plan §8)
-- WAL 模式;所有写都进 SQLite 家族。
-- ===========================================================================

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT DEFAULT (datetime('now'))
);

-- 项目 ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS projects (
    id              TEXT PRIMARY KEY,           -- slug,如 memory-lancedb-pro
    name            TEXT NOT NULL,
    org             TEXT,
    git_url         TEXT NOT NULL,
    platform        TEXT,                       -- github | gitlab | null
    default_branch  TEXT,
    lang            TEXT,
    license         TEXT,
    description     TEXT,
    version         TEXT,
    deploy_key_enc  TEXT,                        -- 加密的 deploy key
    status          TEXT DEFAULT 'pending',      -- pending|indexing|active|error
    index_progress  INTEGER DEFAULT 0,
    health          INTEGER,
    files           INTEGER DEFAULT 0,
    loc             INTEGER DEFAULT 0,
    last_indexed_at TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

-- 分支 ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS branches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    whitelisted     INTEGER DEFAULT 0,
    is_default      INTEGER DEFAULT 0,
    last_commit     TEXT,
    last_commit_msg TEXT,
    author          TEXT,
    committed_at    TEXT,
    ahead           INTEGER DEFAULT 0,
    behind          INTEGER DEFAULT 0,
    indexed         INTEGER DEFAULT 0,
    graph_version   INTEGER DEFAULT 0,
    last_indexed_at TEXT,
    UNIQUE(project_id, name)
);

-- 用户 / 授权 ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    name          TEXT,
    password_hash TEXT NOT NULL,
    role          TEXT DEFAULT 'user',          -- admin | user
    disabled      INTEGER DEFAULT 0,
    last_login    TEXT,
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS project_access (
    user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    role       TEXT DEFAULT 'user',
    PRIMARY KEY (user_id, project_id)
);

-- 平台身份映射 --------------------------------------------------------------
CREATE TABLE IF NOT EXISTS identities (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id       TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    platform         TEXT,
    platform_user_id TEXT,
    username         TEXT,
    name             TEXT,
    emails           TEXT,                       -- JSON 数组
    verified         INTEGER DEFAULT 0,
    merged_into      INTEGER,                     -- 手动合并目标 identity id
    UNIQUE(project_id, platform, platform_user_id)
);

-- API Key -------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS api_keys (
    id          TEXT PRIMARY KEY,
    project_id  TEXT REFERENCES projects(id) ON DELETE CASCADE,
    name        TEXT,
    key_hash    TEXT NOT NULL,
    scope       TEXT DEFAULT 'read',
    created_at  TEXT DEFAULT (datetime('now')),
    revoked_at  TEXT
);

-- 任务队列 ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS jobs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  TEXT REFERENCES projects(id) ON DELETE CASCADE,
    branch      TEXT,
    type        TEXT NOT NULL,
    payload     TEXT,                            -- JSON
    priority    INTEGER DEFAULT 0,               -- 高数字 = 高优先级
    status      TEXT DEFAULT 'queued',           -- queued|running|done|failed
    progress    INTEGER DEFAULT 0,
    attempts    INTEGER DEFAULT 0,
    locked_by   TEXT,
    locked_at   TEXT,
    detail      TEXT,
    result_ref  TEXT,
    error       TEXT,
    run_after   TEXT DEFAULT (datetime('now')),  -- 退避调度
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status, priority DESC, created_at);

-- 逐 commit 理解 ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS commit_analysis (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    branch      TEXT,
    commit_sha  TEXT NOT NULL,
    author      TEXT,
    committed_at TEXT,
    summary     TEXT,
    problem     TEXT,
    approach    TEXT,
    modules     TEXT,                            -- JSON 数组
    loc_add     INTEGER DEFAULT 0,
    loc_del     INTEGER DEFAULT 0,
    raw_msg     TEXT,
    msg_drift   INTEGER DEFAULT 0,
    model       TEXT,
    created_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(project_id, commit_sha)
);

-- 安全 findings -------------------------------------------------------------
CREATE TABLE IF NOT EXISTS findings (
    id          TEXT PRIMARY KEY,                -- F-xxxx
    project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    branch      TEXT,
    scan_id     TEXT,
    severity    TEXT,                            -- critical|high|medium|low
    rule        TEXT,
    source      TEXT,                            -- gitleaks|semgrep|osv|llm-review
    file        TEXT,
    line        INTEGER,
    title       TEXT,
    evidence    TEXT,
    suggestion  TEXT,
    module      TEXT,
    blast       INTEGER DEFAULT 0,
    llm_reviewed INTEGER DEFAULT 0,
    status      TEXT DEFAULT 'new',              -- new|resolved|ignored
    created_at  TEXT DEFAULT (datetime('now'))
);

-- 报告 / Wiki ---------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reports (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    type        TEXT,
    range_spec  TEXT,
    payload     TEXT,                            -- JSON
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS wiki_pages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    page_key    TEXT NOT NULL,
    title       TEXT,
    page_group  TEXT,
    sections    TEXT,                            -- JSON
    fresh       INTEGER DEFAULT 0,
    updated_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(project_id, page_key)
);

-- 项目设置(webhook/平台 token 覆盖/分析参数覆盖) --------------------------
CREATE TABLE IF NOT EXISTS project_settings (
    project_id   TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    webhook_secret TEXT,
    webhook_enabled INTEGER DEFAULT 1,
    settings_json  TEXT                          -- 分析参数覆盖
);
