import sqlite3
import json
import os
from pathlib import Path

DB_PATH = Path(os.getenv("LIFEPILOT_DB_PATH", "data/lifepilot.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    telegram_id INTEGER UNIQUE NOT NULL,
    username TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_profiles (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    agent_id TEXT NOT NULL,
    data JSON NOT NULL DEFAULT '{}',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, agent_id)
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    agent_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS summaries (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    agent_id TEXT NOT NULL,
    summary TEXT NOT NULL,
    msg_start_id INTEGER,
    msg_end_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS memory_facts (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    agent_id TEXT NOT NULL,
    fact_type TEXT NOT NULL,
    fact_key TEXT NOT NULL,
    fact_value TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    valid_until TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, agent_id, fact_type, fact_key)
);

CREATE INDEX IF NOT EXISTS idx_messages_user_agent ON messages(user_id, agent_id, created_at);
CREATE INDEX IF NOT EXISTS idx_summaries_user_agent ON summaries(user_id, agent_id, created_at);
CREATE INDEX IF NOT EXISTS idx_facts_user_agent ON memory_facts(user_id, agent_id);
"""


class Database:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(DB_PATH)
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def get_or_create_user(self, telegram_id: int, username: str = None) -> int:
        row = self.conn.execute(
            "SELECT id FROM users WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        if row:
            return row["id"]
        cur = self.conn.execute(
            "INSERT INTO users (telegram_id, username) VALUES (?, ?)",
            (telegram_id, username),
        )
        self.conn.commit()
        return cur.lastrowid

    # -- Messages --

    def add_message(self, user_id: int, agent_id: str, role: str, content: str) -> int:
        cur = self.conn.execute(
            "INSERT INTO messages (user_id, agent_id, role, content) VALUES (?, ?, ?, ?)",
            (user_id, agent_id, role, content),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_recent_messages(self, user_id: int, agent_id: str, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, role, content, created_at FROM messages "
            "WHERE user_id = ? AND agent_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, agent_id, limit),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def count_unsummarized_messages(self, user_id: int, agent_id: str) -> tuple[int, int | None]:
        """Returns (count, last_summarized_msg_id)."""
        last = self.conn.execute(
            "SELECT msg_end_id FROM summaries WHERE user_id = ? AND agent_id = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (user_id, agent_id),
        ).fetchone()
        last_id = last["msg_end_id"] if last else 0
        count = self.conn.execute(
            "SELECT COUNT(*) as c FROM messages WHERE user_id = ? AND agent_id = ? AND id > ?",
            (user_id, agent_id, last_id),
        ).fetchone()["c"]
        return count, last_id

    def get_messages_since(self, user_id: int, agent_id: str, since_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id, role, content FROM messages "
            "WHERE user_id = ? AND agent_id = ? AND id > ? ORDER BY created_at ASC",
            (user_id, agent_id, since_id),
        ).fetchall()
        return [dict(r) for r in rows]

    # -- Summaries --

    def add_summary(self, user_id: int, agent_id: str, summary: str,
                    msg_start_id: int, msg_end_id: int) -> int:
        cur = self.conn.execute(
            "INSERT INTO summaries (user_id, agent_id, summary, msg_start_id, msg_end_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, agent_id, summary, msg_start_id, msg_end_id),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_recent_summaries(self, user_id: int, agent_id: str, limit: int = 3) -> list[dict]:
        rows = self.conn.execute(
            "SELECT summary, created_at FROM summaries "
            "WHERE user_id = ? AND agent_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, agent_id, limit),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def get_all_agent_summaries(self, user_id: int, limit_per_agent: int = 3) -> dict[str, list[dict]]:
        """For the manager: get recent summaries across all agents."""
        rows = self.conn.execute(
            "SELECT agent_id, summary, created_at FROM summaries "
            "WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        result: dict[str, list[dict]] = {}
        for r in rows:
            agent = r["agent_id"]
            if agent == "manager":
                continue
            result.setdefault(agent, [])
            if len(result[agent]) < limit_per_agent:
                result[agent].append(dict(r))
        return result

    # -- Memory Facts --

    def upsert_fact(self, user_id: int, agent_id: str, fact_type: str,
                    fact_key: str, fact_value: str, confidence: float = 1.0):
        self.conn.execute(
            "INSERT INTO memory_facts (user_id, agent_id, fact_type, fact_key, fact_value, confidence) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id, agent_id, fact_type, fact_key) DO UPDATE SET "
            "fact_value=excluded.fact_value, confidence=excluded.confidence, "
            "updated_at=CURRENT_TIMESTAMP",
            (user_id, agent_id, fact_type, fact_key, fact_value, confidence),
        )
        self.conn.commit()

    def get_facts(self, user_id: int, agent_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT fact_type, fact_key, fact_value FROM memory_facts "
            "WHERE user_id = ? AND agent_id = ?",
            (user_id, agent_id),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_all_facts(self, user_id: int) -> dict[str, list[dict]]:
        rows = self.conn.execute(
            "SELECT agent_id, fact_type, fact_key, fact_value FROM memory_facts "
            "WHERE user_id = ? AND agent_id != 'manager'",
            (user_id,),
        ).fetchall()
        result: dict[str, list[dict]] = {}
        for r in rows:
            result.setdefault(r["agent_id"], []).append(dict(r))
        return result

    # -- User Profiles --

    def get_profile(self, user_id: int, agent_id: str) -> dict:
        row = self.conn.execute(
            "SELECT data FROM user_profiles WHERE user_id = ? AND agent_id = ?",
            (user_id, agent_id),
        ).fetchone()
        return json.loads(row["data"]) if row else {}

    def set_profile(self, user_id: int, agent_id: str, data: dict):
        self.conn.execute(
            "INSERT INTO user_profiles (user_id, agent_id, data) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, agent_id) DO UPDATE SET data=excluded.data, "
            "updated_at=CURRENT_TIMESTAMP",
            (user_id, agent_id, json.dumps(data)),
        )
        self.conn.commit()

    # -- Data Export / Delete --

    def export_agent_data(self, user_id: int, agent_id: str) -> dict:
        return {
            "messages": self.get_messages_since(user_id, agent_id, 0),
            "summaries": [dict(r) for r in self.conn.execute(
                "SELECT * FROM summaries WHERE user_id = ? AND agent_id = ?",
                (user_id, agent_id),
            ).fetchall()],
            "facts": self.get_facts(user_id, agent_id),
            "profile": self.get_profile(user_id, agent_id),
        }

    def delete_agent_data(self, user_id: int, agent_id: str):
        for table in ("messages", "summaries", "memory_facts", "user_profiles"):
            self.conn.execute(
                f"DELETE FROM {table} WHERE user_id = ? AND agent_id = ?",
                (user_id, agent_id),
            )
        self.conn.commit()

    def close(self):
        self.conn.close()
