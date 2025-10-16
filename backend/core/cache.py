import os, time, json, aiosqlite

TTL = int(os.getenv("CACHE_TTL_SECONDS", "86400"))

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS query_cache(
  query TEXT PRIMARY KEY,
  answer TEXT,
  notes_json TEXT,
  ts INTEGER
);
"""

class QueryCache:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def init(self):
        async with aiosqlite.connect(self.db_path) as con:
            await con.execute(CREATE_SQL)
            await con.commit()

    async def get(self, query: str):
        async with aiosqlite.connect(self.db_path) as con:
            cur = await con.execute("SELECT answer, notes_json, ts FROM query_cache WHERE query=?", (query,))
            row = await cur.fetchone()
        if not row: return None
        answer, notes_json, ts = row
        if time.time() - ts > TTL: return None
        return {"answer": answer, "notes": json.loads(notes_json)}

    async def put(self, query: str, answer: str, notes: dict):
        async with aiosqlite.connect(self.db_path) as con:
            await con.execute(
                "INSERT OR REPLACE INTO query_cache(query, answer, notes_json, ts) VALUES(?,?,?,?)",
                (query, answer, json.dumps(notes, ensure_ascii=False), int(time.time()))
            )
            await con.commit()