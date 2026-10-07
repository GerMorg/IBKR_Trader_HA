PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS cycles (
  cycle_id TEXT PRIMARY KEY,
  started_at REAL NOT NULL,
  finished_at REAL,
  status TEXT NOT NULL,
  config_hash TEXT NOT NULL,
  blocker TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS instruments (
  con_id INTEGER PRIMARY KEY,
  symbol TEXT NOT NULL,
  local_symbol TEXT NOT NULL,
  asset_class TEXT NOT NULL,
  contract_json TEXT NOT NULL,
  capability_json TEXT NOT NULL,
  sector TEXT DEFAULT '',
  industry TEXT DEFAULT '',
  updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS market_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  con_id INTEGER NOT NULL,
  captured_at REAL NOT NULL,
  payload_json TEXT NOT NULL,
  UNIQUE(con_id, captured_at)
);

CREATE TABLE IF NOT EXISTS news_items (
  news_id TEXT PRIMARY KEY,
  published_at REAL NOT NULL,
  payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decisions (
  decision_id TEXT PRIMARY KEY,
  cycle_id TEXT NOT NULL,
  con_id INTEGER NOT NULL,
  action TEXT NOT NULL,
  target_position TEXT NOT NULL,
  confidence TEXT NOT NULL,
  net_edge_bps TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS order_intents (
  intent_id TEXT PRIMARY KEY,
  idempotency_key TEXT NOT NULL UNIQUE,
  decision_id TEXT NOT NULL,
  con_id INTEGER NOT NULL,
  state TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
  broker_order_id INTEGER PRIMARY KEY,
  intent_id TEXT NOT NULL,
  con_id INTEGER NOT NULL,
  state TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  submitted_at REAL,
  updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS executions (
  execution_id TEXT PRIMARY KEY,
  broker_order_id INTEGER NOT NULL,
  con_id INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  captured_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS positions (
  con_id INTEGER PRIMARY KEY,
  quantity TEXT NOT NULL,
  market_value TEXT NOT NULL,
  average_cost TEXT NOT NULL,
  currency TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  captured_at REAL NOT NULL,
  payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS risk_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cycle_id TEXT NOT NULL,
  con_id INTEGER,
  reason TEXT NOT NULL,
  checks_json TEXT NOT NULL,
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS learning_samples (
  sample_id TEXT PRIMARY KEY,
  decision_id TEXT NOT NULL,
  outcome_status TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at REAL NOT NULL,
  settled_at REAL
);

CREATE TABLE IF NOT EXISTS model_versions (
  version TEXT PRIMARY KEY,
  parent_version TEXT,
  status TEXT NOT NULL,
  parameters_json TEXT NOT NULL,
  metrics_json TEXT NOT NULL,
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS app_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL,
  code TEXT NOT NULL,
  level TEXT NOT NULL,
  payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recovery_markers (
  key TEXT PRIMARY KEY,
  state TEXT NOT NULL,
  detail TEXT NOT NULL,
  updated_at REAL NOT NULL
);
