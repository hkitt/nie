import time
import threading
import webbrowser

from kivy.app import App
from kivy.clock import Clock
from kivy.properties import StringProperty, NumericProperty, BooleanProperty
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.core.window import Window
from kivy.uix.label import Label
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.metrics import dp

from db import init_db, connect, list_sources, get_setting
from rss import fetch_feed
from ranker import score_article, recency_boost
from settings import EngineConfig


class TickerScreen(Screen):
    headline = StringProperty("Starter NIE…")
    subline = StringProperty("")
    current_link = StringProperty("")
    running = BooleanProperty(True)
    _ui_built = False

    def on_pre_enter(self, *_args):
        if not self._ui_built:
            self.build_ui()
            self._ui_built = True
        self._sync_labels()

    def build_ui(self):
        layout = BoxLayout(
            orientation="vertical",
            padding=dp(20),
            spacing=dp(12),
        )

        top_bar = BoxLayout(size_hint_y=None, height=dp(48))
        admin_button = Button(text="Admin")
        admin_button.bind(on_release=lambda *_: App.get_running_app().toggle_admin())
        open_button = Button(text="Åpne")
        open_button.bind(on_release=lambda *_: App.get_running_app().open_current())
        exit_button = Button(text="X")
        exit_button.bind(
            on_release=lambda *_: setattr(Window, "fullscreen", False)
        )
        for btn in (admin_button, open_button, exit_button):
            top_bar.add_widget(btn)

        running_label = Label(
            text="NIE running",
            font_size="18sp",
            bold=True,
            size_hint_y=None,
            height=dp(24),
            halign="left",
            valign="middle",
        )
        running_label.bind(size=running_label.setter("text_size"))

        self._headline_label = Label(
            text=self.headline,
            font_size="28sp",
            bold=True,
            halign="left",
            valign="middle",
        )
        self._headline_label.bind(size=self._headline_label.setter("text_size"))

        self._subline_label = Label(
            text=self.subline,
            font_size="16sp",
            halign="left",
            valign="top",
        )
        self._subline_label.bind(size=self._subline_label.setter("text_size"))

        layout.add_widget(top_bar)
        layout.add_widget(running_label)
        layout.add_widget(self._headline_label)
        layout.add_widget(self._subline_label)
        self.add_widget(layout)

    def _sync_labels(self):
        if hasattr(self, "_headline_label"):
            self._headline_label.text = self.headline
        if hasattr(self, "_subline_label"):
            self._subline_label.text = self.subline

    def on_headline(self, *_args):
        self._sync_labels()

    def on_subline(self, *_args):
        self._sync_labels()


class AdminScreen(Screen):
    status = StringProperty("")
    fetch_interval_display = StringProperty("")
    ticker_interval_display = StringProperty("")
    min_score_display = StringProperty("")
    _ui_built = False

    def on_pre_enter(self, *_args):
        if not self._ui_built:
            self.build_ui()
            self._ui_built = True
        self.refresh()

    def build_ui(self):
        layout = BoxLayout(
            orientation="vertical",
            padding=dp(20),
            spacing=dp(12),
        )

        top_bar = BoxLayout(size_hint_y=None, height=dp(48))
        back_button = Button(text="Til ticker")
        back_button.bind(on_release=lambda *_: App.get_running_app().toggle_admin())
        top_bar.add_widget(back_button)
        layout.add_widget(top_bar)

        settings_box = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(90),
        )
        settings_title = Label(
            text="Innstillinger",
            font_size="18sp",
            bold=True,
            size_hint_y=None,
            height=dp(24),
            text_size=(0, None),
            halign="left",
            valign="middle",
        )
        settings_title.bind(size=settings_title.setter("text_size"))

        self._fetch_label = Label(
            text="Hentefrekvens (sek): ",
            font_size="16sp",
            size_hint_y=None,
            height=dp(22),
            halign="left",
            valign="middle",
        )
        self._fetch_label.bind(size=self._fetch_label.setter("text_size"))

        self._ticker_label = Label(
            text="Ticker-intervall (sek): ",
            font_size="16sp",
            size_hint_y=None,
            height=dp(22),
            halign="left",
            valign="middle",
        )
        self._ticker_label.bind(size=self._ticker_label.setter("text_size"))

        self._min_score_label = Label(
            text="Min score: ",
            font_size="16sp",
            size_hint_y=None,
            height=dp(22),
            halign="left",
            valign="middle",
        )
        self._min_score_label.bind(size=self._min_score_label.setter("text_size"))

        settings_box.add_widget(settings_title)
        settings_box.add_widget(self._fetch_label)
        settings_box.add_widget(self._ticker_label)
        settings_box.add_widget(self._min_score_label)
        layout.add_widget(settings_box)

        sources_title = Label(
            text="Kilder",
            font_size="18sp",
            bold=True,
            size_hint_y=None,
            height=dp(24),
            halign="left",
            valign="middle",
        )
        sources_title.bind(size=sources_title.setter("text_size"))
        layout.add_widget(sources_title)

        scroll = ScrollView(do_scroll_x=False)
        self.sources_grid = GridLayout(
            cols=4,
            size_hint_y=None,
            row_default_height=dp(32),
            row_force_default=True,
            spacing=dp(6),
        )
        self.sources_grid.bind(
            minimum_height=self.sources_grid.setter("height")
        )
        scroll.add_widget(self.sources_grid)
        layout.add_widget(scroll)
        self.add_widget(layout)

        self._header_widgets = []
        header = ("Enabled", "Weight", "Name", "URL")
        for text in header:
            label = self._add_cell(self.sources_grid, text, bold=True)
            self._header_widgets.append(label)

    def refresh(self):
        defaults = EngineConfig()
        self.fetch_interval_display = str(
            get_setting("fetch_interval_sec", defaults.fetch_interval_sec)
        )
        self.ticker_interval_display = str(
            get_setting("ticker_interval_sec", defaults.ticker_interval_sec)
        )
        self.min_score_display = str(
            get_setting("min_score", defaults.min_score)
        )

        if hasattr(self, "_fetch_label"):
            self._fetch_label.text = (
                "Hentefrekvens (sek): " + self.fetch_interval_display
            )
        if hasattr(self, "_ticker_label"):
            self._ticker_label.text = (
                "Ticker-intervall (sek): " + self.ticker_interval_display
            )
        if hasattr(self, "_min_score_label"):
            self._min_score_label.text = (
                "Min score: " + self.min_score_display
            )

        grid = self.sources_grid
        header_widgets = getattr(self, "_header_widgets", [])
        for widget in list(grid.children):
            if widget not in header_widgets:
                grid.remove_widget(widget)

        for source in list_sources():
            enabled = "Ja" if source["enabled"] else "Nei"
            weight = f'{source["weight"]:.1f}'
            name = source["name"]
            url = self._truncate_url(source["url"])
            for value in (enabled, weight, name, url):
                self._add_cell(grid, value)

    def _add_cell(self, grid, text, bold=False):
        label = Label(
            text=text,
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(32),
            bold=bold,
        )
        label.bind(size=label.setter("text_size"))
        grid.add_widget(label)
        return label

    def _truncate_url(self, url, max_len=48):
        if len(url) <= max_len:
            return url
        return f"{url[:max_len - 1]}…"


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
