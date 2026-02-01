import time
import threading
import webbrowser

from kivy.app import App
from kivy.clock import Clock
from kivy.properties import StringProperty, NumericProperty, BooleanProperty
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.core.window import Window

from db import init_db, connect
from rss import fetch_feed
from ranker import score_article, recency_boost
from settings import EngineConfig


class TickerScreen(Screen):
    headline = StringProperty("Starter NIE…")
    subline = StringProperty("")
    current_link = StringProperty("")
    running = BooleanProperty(True)


class AdminScreen(Screen):
    status = StringProperty("")


class NIEApp(App):
    def build(self):
        init_db()
        self.cfg = EngineConfig()

        self.sm = ScreenManager()
        self.ticker = TickerScreen(name="ticker")
        self.admin = AdminScreen(name="admin")
        self.sm.add_widget(self.ticker)
        self.sm.add_widget(self.admin)

        # Fullskjerm
        Window.fullscreen = True

        # Engine state
        self._articles = []
        self._ticker_idx = 0
        self._lock = threading.Lock()

        # Start background engine loop
        threading.Thread(target=self.engine_loop, daemon=True).start()

        # Start ticker rotation on UI thread
        Clock.schedule_interval(self.rotate_ticker, self.cfg.ticker_interval_sec)

        return self.sm

    def rotate_ticker(self, *_):
        with self._lock:
            if not self._articles:
                self.ticker.headline = "Ingen saker enda…"
                self.ticker.subline = "Venter på RSS-henting."
                self.ticker.current_link = ""
                return

            a = self._articles[self._ticker_idx % len(self._articles)]
            self._ticker_idx += 1

        self.ticker.headline = a["title"]
        self.ticker.subline = f'{a["source_name"]} | score {a["score"]:.1f}'
        self.ticker.current_link = a["link"]

    def open_current(self):
        link = self.ticker.current_link
        if link:
            webbrowser.open(link)

    def toggle_admin(self):
        self.sm.current = "admin" if self.sm.current == "ticker" else "ticker"

    def engine_loop(self):
        while True:
            try:
                self.fetch_and_rank()
            except Exception as e:
                print("Engine error:", e)
            time.sleep(self.cfg.fetch_interval_sec)

    def fetch_and_rank(self):
        con = connect()

        sources = con.execute("SELECT * FROM sources WHERE enabled=1").fetchall()
        cats = con.execute("SELECT * FROM categories WHERE enabled=1").fetchall()
        categories = [{
            "name": c["name"],
            "keywords": c["keywords"],
            "weight": c["weight"],
            "enabled": bool(c["enabled"]),
        } for c in cats]

        now = int(time.time())

        inserted = 0
        for s in sources:
            items = fetch_feed(s["url"])
            for it in items:
                base_score = score_article(it["title"], it["summary"], s["weight"], categories)
                score = base_score + recency_boost(it["published_ts"])

                # Upsert (ignore duplicates)
                try:
                    con.execute(
                        """INSERT INTO articles(guid,title,link,source_name,published_ts,summary,score,created_ts)
                           VALUES(?,?,?,?,?,?,?,?)""",
                        (it["guid"], it["title"], it["link"], s["name"], it["published_ts"], it["summary"], score, now)
                    )
                    inserted += 1
                except Exception:
                    pass

        con.commit()

        # Select top articles for ticker
        rows = con.execute(
            """SELECT title, link, source_name, score
               FROM articles
               WHERE score >= ?
               ORDER BY score DESC, created_ts DESC
               LIMIT ?""",
            (self.cfg.min_score, self.cfg.max_items)
        ).fetchall()
        con.close()

        with self._lock:
            self._articles = [dict(r) for r in rows]
            self._ticker_idx = 0

        print(f"Fetched/inserted: {inserted}, ticker items: {len(rows)}")


if __name__ == "__main__":
    NIEApp().run()
