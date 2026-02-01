import time
import threading
import webbrowser

from kivy.app import App
from kivy.clock import Clock
from kivy.properties import StringProperty, BooleanProperty
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.core.window import Window
from kivy.uix.label import Label
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.switch import Switch
from kivy.metrics import dp

from db import (
    init_db,
    connect,
    list_sources,
    get_setting,
    set_setting,
    add_source,
    update_source,
    delete_source,
)
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
            height=dp(160),
            spacing=dp(8),
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

        settings_grid = GridLayout(
            cols=2,
            row_default_height=dp(34),
            row_force_default=True,
            spacing=dp(6),
            size_hint_y=None,
            height=dp(110),
        )

        settings_grid.add_widget(self._settings_label("Hentefrekvens (sek)"))
        self._fetch_input = self._settings_input()
        settings_grid.add_widget(self._fetch_input)

        settings_grid.add_widget(self._settings_label("Ticker-intervall (sek)"))
        self._ticker_input = self._settings_input()
        settings_grid.add_widget(self._ticker_input)

        settings_grid.add_widget(self._settings_label("Min score"))
        self._min_score_input = self._settings_input()
        settings_grid.add_widget(self._min_score_input)

        settings_actions = BoxLayout(
            size_hint_y=None,
            height=dp(36),
            spacing=dp(8),
        )
        settings_save = Button(text="Lagre innstillinger")
        settings_save.bind(on_release=lambda *_: self._save_settings())
        settings_actions.add_widget(settings_save)

        settings_box.add_widget(settings_title)
        settings_box.add_widget(settings_grid)
        settings_box.add_widget(settings_actions)
        layout.add_widget(settings_box)

        self._status_label = Label(
            text="",
            font_size="14sp",
            size_hint_y=None,
            height=dp(20),
            halign="left",
            valign="middle",
        )
        self._status_label.bind(size=self._status_label.setter("text_size"))
        layout.add_widget(self._status_label)

        add_box = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(150),
            spacing=dp(8),
        )
        add_title = Label(
            text="Legg til kilde",
            font_size="18sp",
            bold=True,
            size_hint_y=None,
            height=dp(24),
            halign="left",
            valign="middle",
        )
        add_title.bind(size=add_title.setter("text_size"))

        add_grid = GridLayout(
            cols=2,
            row_default_height=dp(34),
            row_force_default=True,
            spacing=dp(6),
            size_hint_y=None,
            height=dp(110),
        )
        add_grid.add_widget(self._settings_label("Navn"))
        self._new_name_input = self._settings_input()
        add_grid.add_widget(self._new_name_input)
        add_grid.add_widget(self._settings_label("URL"))
        self._new_url_input = self._settings_input()
        add_grid.add_widget(self._new_url_input)
        add_grid.add_widget(self._settings_label("Weight"))
        self._new_weight_input = self._settings_input()
        add_grid.add_widget(self._new_weight_input)

        add_actions = BoxLayout(
            size_hint_y=None,
            height=dp(36),
            spacing=dp(8),
        )
        add_button = Button(text="Legg til kilde")
        add_button.bind(on_release=lambda *_: self._add_source())
        add_actions.add_widget(add_button)

        add_box.add_widget(add_title)
        add_box.add_widget(add_grid)
        add_box.add_widget(add_actions)
        layout.add_widget(add_box)

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
            cols=5,
            size_hint_y=None,
            row_default_height=dp(36),
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
        header = ("Enabled", "Weight", "Name", "URL", "Handling")
        for text in header:
            label = self._add_cell(self.sources_grid, text, bold=True)
            self._header_widgets.append(label)

    def refresh(self):
        defaults = EngineConfig()
        if hasattr(self, "_fetch_input"):
            self._fetch_input.text = str(
                get_setting("fetch_interval_sec", defaults.fetch_interval_sec)
            )
        if hasattr(self, "_ticker_input"):
            self._ticker_input.text = str(
                get_setting("ticker_interval_sec", defaults.ticker_interval_sec)
            )
        if hasattr(self, "_min_score_input"):
            self._min_score_input.text = str(
                get_setting("min_score", defaults.min_score)
            )

        grid = self.sources_grid
        header_widgets = getattr(self, "_header_widgets", [])
        for widget in list(grid.children):
            if widget not in header_widgets:
                grid.remove_widget(widget)

        for source in list_sources():
            self._add_source_row(source)

    def _add_cell(self, grid, text, bold=False):
        label = Label(
            text=text,
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(36),
            bold=bold,
        )
        label.bind(size=label.setter("text_size"))
        grid.add_widget(label)
        return label

    def _truncate_url(self, url, max_len=48):
        if len(url) <= max_len:
            return url
        return f"{url[:max_len - 1]}…"

    def _settings_label(self, text):
        label = Label(
            text=text,
            font_size="16sp",
            size_hint_y=None,
            height=dp(34),
            halign="left",
            valign="middle",
        )
        label.bind(size=label.setter("text_size"))
        return label

    def _settings_input(self):
        return TextInput(
            multiline=False,
            font_size="16sp",
            size_hint_y=None,
            height=dp(34),
        )

    def _set_status(self, message):
        self.status = message
        if hasattr(self, "_status_label"):
            self._status_label.text = message

    def _save_settings(self):
        try:
            fetch_interval = int(self._fetch_input.text.strip())
            ticker_interval = int(self._ticker_input.text.strip())
            min_score = float(self._min_score_input.text.strip())
        except ValueError:
            self._set_status("Ugyldig format i innstillinger.")
            return

        if fetch_interval <= 0 or ticker_interval <= 0:
            self._set_status("Intervaller må være større enn 0.")
            return

        set_setting("fetch_interval_sec", fetch_interval)
        set_setting("ticker_interval_sec", ticker_interval)
        set_setting("min_score", min_score)
        app = App.get_running_app()
        if app:
            app.apply_settings(fetch_interval, ticker_interval, min_score)
        self._set_status("Innstillinger lagret.")

    def _add_source(self):
        name = self._new_name_input.text.strip()
        url = self._new_url_input.text.strip()
        weight_text = self._new_weight_input.text.strip()
        if not name or not url:
            self._set_status("Navn og URL må fylles ut.")
            return
        try:
            weight = float(weight_text)
        except ValueError:
            self._set_status("Weight må være et tall.")
            return
        try:
            add_source(name, url, weight)
        except Exception:
            self._set_status("Kunne ikke legge til kilde (sjekk URL).")
            return
        self._new_name_input.text = ""
        self._new_url_input.text = ""
        self._new_weight_input.text = ""
        self._set_status("Kilde lagt til.")
        self.refresh()

    def _add_source_row(self, source):
        enabled_switch = Switch(active=bool(source["enabled"]))
        weight_input = TextInput(
            text=f'{source["weight"]:.1f}',
            multiline=False,
            font_size="16sp",
            size_hint_y=None,
            height=dp(34),
        )
        name_label = Label(
            text=source["name"],
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(36),
        )
        name_label.bind(size=name_label.setter("text_size"))
        url_label = Label(
            text=self._truncate_url(source["url"]),
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(36),
        )
        url_label.bind(size=url_label.setter("text_size"))

        def apply_update(*_args):
            try:
                weight = float(weight_input.text.strip())
            except ValueError:
                self._set_status("Weight må være et tall.")
                return
            update_source(source["id"], int(enabled_switch.active), weight)
            self._set_status("Kilde oppdatert.")

        enabled_switch.bind(on_active=lambda *_: apply_update())

        actions = BoxLayout(spacing=dp(6))
        save_button = Button(text="Lagre", size_hint_x=None, width=dp(70))
        save_button.bind(on_release=lambda *_: apply_update())
        delete_button = Button(text="Slett", size_hint_x=None, width=dp(70))
        delete_button.bind(
            on_release=lambda *_: self._delete_source(source["id"])
        )
        actions.add_widget(save_button)
        actions.add_widget(delete_button)

        self.sources_grid.add_widget(enabled_switch)
        self.sources_grid.add_widget(weight_input)
        self.sources_grid.add_widget(name_label)
        self.sources_grid.add_widget(url_label)
        self.sources_grid.add_widget(actions)

    def _delete_source(self, source_id):
        delete_source(source_id)
        self._set_status("Kilde slettet.")
        self.refresh()


class NIEApp(App):
    def build(self):
        init_db()
        self.cfg = EngineConfig()
        self._load_settings_from_db()

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
        self._ticker_event = Clock.schedule_interval(
            self.rotate_ticker,
            self.cfg.ticker_interval_sec,
        )

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

    def apply_settings(self, fetch_interval, ticker_interval, min_score):
        self.cfg.fetch_interval_sec = fetch_interval
        self.cfg.ticker_interval_sec = ticker_interval
        self.cfg.min_score = min_score
        if getattr(self, "_ticker_event", None) is not None:
            self._ticker_event.cancel()
        self._ticker_event = Clock.schedule_interval(
            self.rotate_ticker,
            self.cfg.ticker_interval_sec,
        )

    def _load_settings_from_db(self):
        defaults = EngineConfig()
        fetch_interval = int(
            get_setting("fetch_interval_sec", defaults.fetch_interval_sec)
        )
        ticker_interval = int(
            get_setting("ticker_interval_sec", defaults.ticker_interval_sec)
        )
        min_score = float(get_setting("min_score", defaults.min_score))
        self.cfg.fetch_interval_sec = fetch_interval
        self.cfg.ticker_interval_sec = ticker_interval
        self.cfg.min_score = min_score

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
