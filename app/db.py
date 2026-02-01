import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "nie.db"

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

    # Seed defaults if empty
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
