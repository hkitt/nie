import sqlite3
from pathlib import Path

DB_PATH = Path.home() / ".local" / "share" / "nie" / "nie.db"

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  url TEXT NOT NULL UNIQUE,
  weight REAL NOT NULL DEFAULT 1.0,
  enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS categories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  keywords TEXT NOT NULL,            -- comma-separated
  weight REAL NOT NULL DEFAULT 1.0,
  enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS articles (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  guid TEXT UNIQUE,
  title TEXT NOT NULL,
  link TEXT NOT NULL,
  source_name TEXT,
  published_ts INTEGER,              -- unix seconds
  summary TEXT,
  score REAL NOT NULL DEFAULT 0,
  created_ts INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_articles_score ON articles(score DESC);
CREATE INDEX IF NOT EXISTS idx_articles_created ON articles(created_ts DESC);
"""

DEFAULTS = {
  "sources": [
    ("Google News - AI", "https://news.google.com/rss/search?q=kunstig%20intelligens%20when:7d&hl=no&gl=NO&ceid=NO:no", 1.2, 1),
    ("E24", "https://e24.no/rss2/", 1.1, 1),
    ("VG Forsiden", "https://www.vg.no/rss/feed/forsiden/", 1.0, 1),
  ],
  "categories": [
    ("AI", "ai,kunstig intelligens,openai,chatgpt,llm,maskinlæring", 1.4, 1),
    ("Krypto", "bitcoin,btc,ethereum,eth,solana,sol,krypto,stablecoin", 1.2, 1),
    ("Norsk økonomi", "norge,norsk økonomi,rente,norges bank,inflasjon,krone", 1.1, 1),
  ]
}


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = connect()
    con.executescript(SCHEMA)

    cur = con.execute("SELECT COUNT(*) AS c FROM sources")
    if cur.fetchone()["c"] == 0:
        con.executemany(
            "INSERT INTO sources(name,url,weight,enabled) VALUES(?,?,?,?)",
            DEFAULTS["sources"]
        )

    cur = con.execute("SELECT COUNT(*) AS c FROM categories")
    if cur.fetchone()["c"] == 0:
        con.executemany(
            "INSERT INTO categories(name,keywords,weight,enabled) VALUES(?,?,?,?)",
            DEFAULTS["categories"]
        )

    con.commit()
    con.close()


def list_sources():
    con = connect()
    cur = con.execute(
        "SELECT id,name,url,weight,enabled FROM sources ORDER BY name ASC"
    )
    rows = cur.fetchall()
    con.close()
    return rows


def add_source(name, url, weight, enabled=1):
    con = connect()
    cur = con.execute(
        "INSERT INTO sources(name,url,weight,enabled) VALUES(?,?,?,?)",
        (name, url, weight, enabled)
    )
    con.commit()
    source_id = cur.lastrowid
    con.close()
    return source_id


def update_source(id, enabled, weight):
    con = connect()
    con.execute(
        "UPDATE sources SET enabled=?, weight=? WHERE id=?",
        (enabled, weight, id)
    )
    con.commit()
    con.close()


def update_source_full(id, name, url, weight, enabled):
    con = connect()
    con.execute(
        "UPDATE sources SET name=?, url=?, weight=?, enabled=? WHERE id=?",
        (name, url, weight, enabled, id)
    )
    con.commit()
    con.close()


def delete_source(id):
    con = connect()
    con.execute("DELETE FROM sources WHERE id=?", (id,))
    con.commit()
    con.close()


def list_categories():
    con = connect()
    cur = con.execute(
        "SELECT id,name,keywords,weight,enabled FROM categories ORDER BY name ASC"
    )
    rows = cur.fetchall()
    con.close()
    return rows


def add_category(name, keywords, weight, enabled=1):
    con = connect()
    cur = con.execute(
        "INSERT INTO categories(name,keywords,weight,enabled) VALUES(?,?,?,?)",
        (name, keywords, weight, enabled)
    )
    con.commit()
    category_id = cur.lastrowid
    con.close()
    return category_id


def update_category(category_id, name, keywords, weight, enabled):
    con = connect()
    con.execute(
        "UPDATE categories SET name=?, keywords=?, weight=?, enabled=? WHERE id=?",
        (name, keywords, weight, enabled, category_id)
    )
    con.commit()
    con.close()


def delete_category(category_id):
    con = connect()
    con.execute("DELETE FROM categories WHERE id=?", (category_id,))
    con.commit()
    con.close()


def get_setting(key, default=None):
    con = connect()
    cur = con.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cur.fetchone()
    con.close()
    if row is None:
        return default
    return row["value"]


def set_setting(key, value):
    con = connect()
    con.execute(
        "INSERT INTO settings(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value)
    )
    con.commit()
    con.close()
