-- ===== Conversación =====
CREATE TABLE IF NOT EXISTS threads(
  id TEXT PRIMARY KEY,
  title TEXT,
  created_at REAL
);
CREATE TABLE IF NOT EXISTS messages(
  id TEXT PRIMARY KEY,
  thread_id TEXT,
  role TEXT,            -- 'user' | 'assistant' | 'system'
  text TEXT,
  created_at REAL,
  FOREIGN KEY(thread_id) REFERENCES threads(id)
);

-- Resúmenes/entidades por turno e hilo
CREATE TABLE IF NOT EXISTS turn_summaries(
  msg_id TEXT PRIMARY KEY,
  summary TEXT,
  entities_json TEXT
);
CREATE TABLE IF NOT EXISTS thread_memory(
  thread_id TEXT PRIMARY KEY,
  rolling_summary TEXT,
  last_updated REAL
);

-- Hechos clínicos extraídos del hilo
CREATE TABLE IF NOT EXISTS clinical_facts(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  thread_id TEXT,
  fact TEXT,
  source_msg_id TEXT,
  created_at REAL
);

-- Citas usadas por respuesta
CREATE TABLE IF NOT EXISTS citations(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  thread_id TEXT,
  msg_id TEXT,
  url TEXT,
  title TEXT,
  rank INTEGER
);

-- ===== RAG: documentos y chunks =====
CREATE TABLE IF NOT EXISTS documents(
  id TEXT PRIMARY KEY,
  url TEXT,
  title TEXT,
  published_at REAL,
  evidence_score REAL
);
CREATE TABLE IF NOT EXISTS doc_chunks(
  id TEXT PRIMARY KEY,
  doc_id TEXT,
  url TEXT,
  title TEXT,
  section TEXT,         -- definicion | sintomas | diagnostico | tratamiento | conducta | otros
  chunk TEXT,
  published_at REAL,
  evidence_score REAL,
  FOREIGN KEY(doc_id) REFERENCES documents(id)
);

-- Índice léxico simple (opcional; puedes usar tantivy o similar si quieres)
CREATE TABLE IF NOT EXISTS bm25_index(
  chunk_id TEXT PRIMARY KEY,
  tokens TEXT            -- espacio-separado (pretokenizado)
);

-- ===== Caché de limpieza (ya lo usas) =====
CREATE TABLE IF NOT EXISTS pages(
  url TEXT PRIMARY KEY,
  fetched_at REAL NOT NULL,
  content TEXT
);