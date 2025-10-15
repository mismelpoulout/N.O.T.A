# -*- coding: utf-8 -*-
from __future__ import annotations
import sqlite3, time, json
from typing import List, Dict, Optional

class MemoryStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.con = sqlite3.connect(db_path)
        self.con.execute("PRAGMA journal_mode=WAL;")
        self.con.executescript("""
        CREATE TABLE IF NOT EXISTS threads(
          id TEXT PRIMARY KEY, title TEXT, created_at REAL
        );
        CREATE TABLE IF NOT EXISTS messages(
          id TEXT PRIMARY KEY, thread_id TEXT, role TEXT, text TEXT, created_at REAL
        );
        CREATE TABLE IF NOT EXISTS turn_summaries(
          msg_id TEXT PRIMARY KEY, summary TEXT, entities_json TEXT
        );
        CREATE TABLE IF NOT EXISTS thread_memory(
          thread_id TEXT PRIMARY KEY, rolling_summary TEXT, last_updated REAL
        );
        CREATE TABLE IF NOT EXISTS clinical_facts(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          thread_id TEXT, fact TEXT, source_msg_id TEXT, created_at REAL
        );
        CREATE TABLE IF NOT EXISTS citations(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          thread_id TEXT, msg_id TEXT, url TEXT, title TEXT, rank INTEGER
        );
        """)
        self.con.commit()

    # -------- messages / threads --------
    def add_message(self, thread_id: str, role: str, text: str, msg_id: str):
        now = time.time()
        self.con.execute("INSERT OR IGNORE INTO threads(id, title, created_at) VALUES(?,?,?)",
                         (thread_id, thread_id, now))
        self.con.execute("REPLACE INTO messages(id, thread_id, role, text, created_at) VALUES(?,?,?,?,?)",
                         (msg_id, thread_id, role, text, now))
        self.con.commit()

    def last_messages(self, thread_id: str, limit: int = 10) -> List[Dict]:
        cur = self.con.execute(
            "SELECT role, text FROM messages WHERE thread_id=? ORDER BY created_at DESC LIMIT ?",
            (thread_id, limit)
        )
        return [{"role": r, "text": t} for r,t in cur.fetchall()][::-1]

    # -------- summaries / memory --------
    def save_turn_summary(self, msg_id: str, summary: str, entities: Dict):
        self.con.execute("REPLACE INTO turn_summaries(msg_id, summary, entities_json) VALUES(?,?,?)",
                         (msg_id, summary, json.dumps(entities or {})))
        self.con.commit()

    def update_thread_memory(self, thread_id: str, rolling_summary: str):
        now = time.time()
        self.con.execute("REPLACE INTO thread_memory(thread_id, rolling_summary, last_updated) VALUES(?,?,?)",
                         (thread_id, rolling_summary, now))
        self.con.commit()

    # -------- clinical facts --------
    def save_facts(self, thread_id: str, msg_id: str, facts: List[str]):
        now = time.time()
        for f in facts or []:
            self.con.execute(
                "INSERT INTO clinical_facts(thread_id, fact, source_msg_id, created_at) VALUES(?,?,?,?)",
                (thread_id, f, msg_id, now)
            )
        self.con.commit()

    # -------- citations --------
    def save_citations(self, thread_id: str, msg_id: str, cites: List[Dict]):
        for i, c in enumerate(cites):
            self.con.execute(
                "INSERT INTO citations(thread_id, msg_id, url, title, rank) VALUES(?,?,?,?,?)",
                (thread_id, msg_id, c.get("url",""), c.get("title",""), i+1)
            )
        self.con.commit()