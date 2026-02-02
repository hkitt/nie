from kivy.config import Config

Config.set("graphics", "fullscreen", "auto")
Config.set("graphics", "borderless", "1")

import os
import sys
import time
import threading
import webbrowser
import sqlite3
import subprocess
from datetime import datetime

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
from kivy.uix.popup import Popup
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.image import AsyncImage
from kivy.metrics import dp
from kivy.graphics import Color, Rectangle

from db import (
    init_db,
    connect,
    list_sources,
    get_setting,
    set_setting,
    add_source,
    update_source,
    update_source_full,
    delete_source,
    list_categories,
    add_category,
    update_category,
    delete_category,
)
from rss import fetch_feed
from ranker import score_article, recency_boost
from settings import EngineConfig
from reader import html_to_simple_markup, fetch_article_content

COLOR_THEME = {
    "background": (0.05, 0.08, 0.12, 1),
    "surface": (0.11, 0.16, 0.24, 1),
    "accent": (0.18, 0.52, 0.85, 1),
    "text_primary": (1, 1, 1, 1),
    "text_secondary": (0.85, 0.9, 0.96, 1),
    "button": (0.2, 0.36, 0.6, 1),
}

MONO_THEME = {
    "background": (0, 0, 0, 1),
    "surface": (0.12, 0.12, 0.12, 1),
    "accent": (1, 1, 1, 1),
    "text_primary": (1, 1, 1, 1),
    "text_secondary": (0.8, 0.8, 0.8, 1),
    "button": (0.2, 0.2, 0.2, 1),
}


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
        app = App.get_running_app()
        if app:
            self.apply_theme(app.theme)

    def build_ui(self):
        layout = BoxLayout(orientation="vertical")
        self._layout = layout

        top_bar = BoxLayout(
            size_hint_y=None,
            height=dp(56),
            spacing=dp(8),
            padding=(dp(12), dp(8)),
        )
        admin_button = Button(text="Admin")
        admin_button.bind(on_release=lambda *_: App.get_running_app().show_admin())
        open_button = Button(text="Åpne")
        open_button.bind(on_release=lambda *_: App.get_running_app().open_current())
        exit_button = Button(text="Lukk")
        exit_button.bind(on_release=lambda *_: App.get_running_app().exit_app())
        self._admin_button = admin_button
        self._open_button = open_button
        self._exit_button = exit_button
        for widget in (admin_button, open_button, exit_button):
            top_bar.add_widget(widget)
        self._top_bar = top_bar

        content_area = BoxLayout(
            orientation="vertical",
            size_hint_y=1,
            padding=dp(20),
            spacing=dp(12),
        )

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
        self._running_label = running_label

        self._headline_label = Label(
            text=self.headline,
            font_size="28sp",
            bold=True,
            halign="left",
            valign="middle",
        )
        self._headline_label.bind(size=self._headline_label.setter("text_size"))
        self._headline_label.bind(on_touch_down=self._on_headline_touch)

        self._subline_label = Label(
            text=self.subline,
            font_size="16sp",
            halign="left",
            valign="top",
        )
        self._subline_label.bind(size=self._subline_label.setter("text_size"))

        content_area.add_widget(running_label)
        content_area.add_widget(self._headline_label)
        content_area.add_widget(self._subline_label)

        layout.add_widget(top_bar)
        layout.add_widget(content_area)
        self.add_widget(layout)
        theme = App.get_running_app().theme if App.get_running_app() else COLOR_THEME
        self._apply_backgrounds(theme)
        self.apply_theme(theme)

    def _apply_backgrounds(self, theme):
        self._layout_bg = self._add_background(self._layout, theme["background"])
        self._top_bar_bg = self._add_background(self._top_bar, theme["surface"])

    def _add_background(self, widget, color):
        with widget.canvas.before:
            color_instruction = Color(*color)
            rect = Rectangle(pos=widget.pos, size=widget.size)

        def update_rect(*_args):
            rect.pos = widget.pos
            rect.size = widget.size

        widget.bind(pos=update_rect, size=update_rect)
        return color_instruction

    def apply_theme(self, theme):
        if hasattr(self, "_layout_bg"):
            self._layout_bg.rgba = theme["background"]
        if hasattr(self, "_top_bar_bg"):
            self._top_bar_bg.rgba = theme["surface"]
        if hasattr(self, "_running_label"):
            self._running_label.color = theme["text_secondary"]
        if hasattr(self, "_headline_label"):
            self._headline_label.color = theme["text_primary"]
        if hasattr(self, "_subline_label"):
            self._subline_label.color = theme["text_secondary"]
        for button in (
            getattr(self, "_admin_button", None),
            getattr(self, "_open_button", None),
            getattr(self, "_exit_button", None),
        ):
            if button:
                button.background_normal = ""
                button.background_down = ""
                button.background_color = theme["button"]
                button.color = theme["text_primary"]

    def _sync_labels(self):
        if hasattr(self, "_headline_label"):
            self._headline_label.text = self.headline
        if hasattr(self, "_subline_label"):
            self._subline_label.text = self.subline

    def on_headline(self, *_args):
        self._sync_labels()

    def on_subline(self, *_args):
        self._sync_labels()

    def _on_headline_touch(self, instance, touch):
        if instance.collide_point(*touch.pos):
            app = App.get_running_app()
            if app:
                app.open_current()
            return True
        return False


class AdminScreen(Screen):
    status = StringProperty("")
    _ui_built = False

    def on_pre_enter(self, *_args):
        if not self._ui_built:
            self.build_ui()
            self._ui_built = True
        self.refresh()
        app = App.get_running_app()
        if app:
            self.apply_theme(app.theme)

    def build_ui(self):
        layout = BoxLayout(orientation="vertical")
        self._layout = layout

        top_bar = BoxLayout(
            size_hint_y=None,
            height=dp(56),
            spacing=dp(8),
            padding=(dp(12), dp(8)),
        )
        back_button = Button(text="Til ticker")
        back_button.bind(on_release=lambda *_: App.get_running_app().show_ticker())
        top_bar.add_widget(back_button)
        self._back_button = back_button

        self._tab_buttons = {}
        for tab_name, label in (
            ("sources", "Sources"),
            ("categories", "Categories"),
            ("settings", "Settings"),
        ):
            button = ToggleButton(text=label, group="admin-tabs")
            button.bind(on_release=lambda btn, name=tab_name: self._switch_tab(name))
            self._tab_buttons[tab_name] = button
            top_bar.add_widget(button)

        refresh_button = Button(text="Refresh", size_hint_x=None, width=dp(100))
        refresh_button.bind(on_release=lambda *_: self.trigger_update())
        top_bar.add_widget(refresh_button)
        self._refresh_button = refresh_button

        exit_button = Button(text="Lukk", size_hint_x=None, width=dp(80))
        exit_button.bind(on_release=lambda *_: App.get_running_app().exit_app())
        top_bar.add_widget(exit_button)
        self._exit_button = exit_button
        self._top_bar = top_bar

        layout.add_widget(top_bar)

        content_area = BoxLayout(
            orientation="vertical",
            size_hint_y=1,
            padding=dp(12),
            spacing=dp(8),
        )
        self._content_area = content_area

        self._status_label = Label(
            text="",
            font_size="14sp",
            size_hint_y=None,
            height=dp(20),
            halign="left",
            valign="middle",
        )
        self._status_label.bind(size=self._status_label.setter("text_size"))
        content_area.add_widget(self._status_label)

        self._tab_scrolls = {}
        self._content_manager = ScreenManager()
        self._content_manager.add_widget(self._build_sources_tab())
        self._content_manager.add_widget(self._build_categories_tab())
        self._content_manager.add_widget(self._build_settings_tab())
        content_area.add_widget(self._content_manager)

        layout.add_widget(content_area)

        self.add_widget(layout)
        self._switch_tab("sources")
        theme = App.get_running_app().theme if App.get_running_app() else COLOR_THEME
        self._apply_backgrounds(theme)
        self.apply_theme(theme)

    def _apply_backgrounds(self, theme):
        self._layout_bg = self._add_background(self._layout, theme["background"])
        self._top_bar_bg = self._add_background(self._top_bar, theme["surface"])

    def _add_background(self, widget, color):
        with widget.canvas.before:
            color_instruction = Color(*color)
            rect = Rectangle(pos=widget.pos, size=widget.size)

        def update_rect(*_args):
            rect.pos = widget.pos
            rect.size = widget.size

        widget.bind(pos=update_rect, size=update_rect)
        return color_instruction

    def apply_theme(self, theme):
        if hasattr(self, "_layout_bg"):
            self._layout_bg.rgba = theme["background"]
        if hasattr(self, "_top_bar_bg"):
            self._top_bar_bg.rgba = theme["surface"]
        if hasattr(self, "_status_label"):
            self._status_label.color = theme["text_secondary"]
        for button in (
            getattr(self, "_back_button", None),
            getattr(self, "_refresh_button", None),
            getattr(self, "_exit_button", None),
        ):
            if button:
                button.background_normal = ""
                button.background_down = ""
                button.background_color = theme["button"]
                button.color = theme["text_primary"]

    def _build_sources_tab(self):
        screen = Screen(name="sources")
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(12), size_hint=(1, 1))
        self._tab_scrolls["sources"] = scroll
        content = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=dp(12),
        )
        content.bind(minimum_height=content.setter("height"))

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
        content.add_widget(add_title)

        add_grid = GridLayout(
            cols=2,
            row_default_height=dp(34),
            row_force_default=True,
            spacing=dp(6),
            size_hint_y=None,
        )
        add_grid.bind(minimum_height=add_grid.setter("height"))

        add_grid.add_widget(self._settings_label("Navn"))
        self._new_name_input = self._settings_input()
        add_grid.add_widget(self._new_name_input)

        add_grid.add_widget(self._settings_label("URL"))
        self._new_url_input = self._settings_input()
        add_grid.add_widget(self._new_url_input)

        add_grid.add_widget(self._settings_label("Weight"))
        self._new_weight_input = self._settings_input()
        add_grid.add_widget(self._new_weight_input)

        add_grid.add_widget(self._settings_label("Enabled"))
        self._new_enabled_switch = Switch(active=True)
        add_grid.add_widget(self._new_enabled_switch)

        content.add_widget(add_grid)

        add_actions = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8))
        add_button = Button(text="Legg til kilde")
        add_button.bind(on_release=lambda *_: self._add_source())
        add_actions.add_widget(add_button)
        content.add_widget(add_actions)

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
        content.add_widget(sources_title)

        self.sources_grid = GridLayout(
            cols=6,
            size_hint_y=None,
            row_default_height=dp(40),
            row_force_default=True,
            spacing=dp(6),
        )
        self.sources_grid.bind(minimum_height=self.sources_grid.setter("height"))
        content.add_widget(self.sources_grid)
        scroll.add_widget(content)
        screen.add_widget(scroll)

        self._sources_header_widgets = []
        header = ("Enabled", "Weight", "Name", "URL", "Edit", "Delete")
        for text in header:
            label = self._add_cell(self.sources_grid, text, bold=True)
            self._sources_header_widgets.append(label)

        return screen

    def _build_categories_tab(self):
        screen = Screen(name="categories")
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(12), size_hint=(1, 1))
        self._tab_scrolls["categories"] = scroll
        content = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=dp(12),
        )
        content.bind(minimum_height=content.setter("height"))

        add_title = Label(
            text="Legg til kategori",
            font_size="18sp",
            bold=True,
            size_hint_y=None,
            height=dp(24),
            halign="left",
            valign="middle",
        )
        add_title.bind(size=add_title.setter("text_size"))
        content.add_widget(add_title)

        add_grid = GridLayout(
            cols=2,
            row_default_height=dp(34),
            row_force_default=False,
            spacing=dp(6),
            size_hint_y=None,
        )
        add_grid.bind(minimum_height=add_grid.setter("height"))

        add_grid.add_widget(self._settings_label("Navn"))
        self._new_category_name = self._settings_input()
        add_grid.add_widget(self._new_category_name)

        keywords_label = self._settings_label("Keywords")
        keywords_label.height = dp(68)
        add_grid.add_widget(keywords_label)
        self._new_category_keywords = TextInput(
            multiline=True,
            font_size="16sp",
            size_hint_y=None,
            height=dp(68),
        )
        add_grid.add_widget(self._new_category_keywords)

        add_grid.add_widget(self._settings_label("Weight"))
        self._new_category_weight = self._settings_input()
        add_grid.add_widget(self._new_category_weight)

        add_grid.add_widget(self._settings_label("Enabled"))
        self._new_category_enabled = Switch(active=True)
        add_grid.add_widget(self._new_category_enabled)

        content.add_widget(add_grid)

        add_actions = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8))
        add_button = Button(text="Legg til kategori")
        add_button.bind(on_release=lambda *_: self._add_category())
        add_actions.add_widget(add_button)
        content.add_widget(add_actions)

        categories_title = Label(
            text="Kategorier",
            font_size="18sp",
            bold=True,
            size_hint_y=None,
            height=dp(24),
            halign="left",
            valign="middle",
        )
        categories_title.bind(size=categories_title.setter("text_size"))
        content.add_widget(categories_title)

        self.categories_grid = GridLayout(
            cols=6,
            size_hint_y=None,
            row_default_height=dp(60),
            row_force_default=True,
            spacing=dp(6),
        )
        self.categories_grid.bind(
            minimum_height=self.categories_grid.setter("height")
        )
        content.add_widget(self.categories_grid)
        scroll.add_widget(content)
        screen.add_widget(scroll)

        self._categories_header_widgets = []
        header = ("Enabled", "Weight", "Name", "Keywords", "Edit", "Delete")
        for text in header:
            label = self._add_cell(self.categories_grid, text, bold=True, height=dp(60))
            self._categories_header_widgets.append(label)

        return screen

    def _build_settings_tab(self):
        screen = Screen(name="settings")
        scroll = ScrollView(do_scroll_x=False, bar_width=dp(12), size_hint=(1, 1))
        self._tab_scrolls["settings"] = scroll
        content = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=dp(12),
        )
        content.bind(minimum_height=content.setter("height"))

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
        content.add_widget(settings_title)

        settings_grid = GridLayout(
            cols=2,
            row_default_height=dp(34),
            row_force_default=True,
            spacing=dp(6),
            size_hint_y=None,
        )
        settings_grid.bind(minimum_height=settings_grid.setter("height"))

        settings_grid.add_widget(self._settings_label("Hentefrekvens (sek)"))
        self._fetch_input = self._settings_input()
        settings_grid.add_widget(self._fetch_input)

        settings_grid.add_widget(self._settings_label("Ticker-intervall (sek)"))
        self._ticker_input = self._settings_input()
        settings_grid.add_widget(self._ticker_input)

        settings_grid.add_widget(self._settings_label("Min score"))
        self._min_score_input = self._settings_input()
        settings_grid.add_widget(self._min_score_input)

        settings_grid.add_widget(self._settings_label("Fargetema"))
        self._theme_switch = Switch(active=True)
        self._theme_switch.bind(
            on_active=lambda instance, value: self._apply_theme_setting(value)
        )
        settings_grid.add_widget(self._theme_switch)

        content.add_widget(settings_grid)

        settings_actions = BoxLayout(
            size_hint_y=None,
            height=dp(36),
            spacing=dp(8),
        )
        settings_save = Button(text="Lagre innstillinger")
        settings_save.bind(on_release=lambda *_: self._save_settings())
        settings_actions.add_widget(settings_save)
        content.add_widget(settings_actions)

        scroll.add_widget(content)
        screen.add_widget(scroll)
        return screen

    def refresh(self):
        self.refresh_sources()
        self.refresh_categories()
        self.refresh_settings()

    def refresh_sources(self):
        grid = self.sources_grid
        header_widgets = getattr(self, "_sources_header_widgets", [])
        for widget in list(grid.children):
            if widget not in header_widgets:
                grid.remove_widget(widget)

        sources = list_sources()
        if not sources:
            self._add_empty_row(grid, "Ingen kilder")
            return

        for source in sources:
            self._add_source_row(source)

    def refresh_categories(self):
        grid = self.categories_grid
        header_widgets = getattr(self, "_categories_header_widgets", [])
        for widget in list(grid.children):
            if widget not in header_widgets:
                grid.remove_widget(widget)

        categories = list_categories()
        if not categories:
            self._add_empty_row(grid, "Ingen kategorier")
            return

        for category in categories:
            self._add_category_row(category)

    def refresh_settings(self):
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
        if hasattr(self, "_theme_switch"):
            theme_value = int(get_setting("color_theme", 1))
            self._theme_switch.active = bool(theme_value)

    def _switch_tab(self, tab_name):
        if hasattr(self, "_content_manager"):
            self._content_manager.current = tab_name
        tab_scroll = getattr(self, "_tab_scrolls", {}).get(tab_name)
        if tab_scroll is not None:
            tab_scroll.scroll_y = 1
        if tab_name in self._tab_buttons:
            self._tab_buttons[tab_name].state = "down"

    def _add_cell(self, grid, text, bold=False, height=dp(36)):
        label = Label(
            text=text,
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=height,
            bold=bold,
        )
        label.bind(size=label.setter("text_size"))
        grid.add_widget(label)
        return label

    def _add_empty_row(self, grid, message):
        label = Label(
            text=message,
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(36),
        )
        label.bind(size=label.setter("text_size"))
        grid.add_widget(label)
        for _ in range(grid.cols - 1):
            grid.add_widget(Label(text=""))

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

    def trigger_update(self):
        app = App.get_running_app()
        if app:
            app.update_and_restart(self._set_status)

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
        if hasattr(self, "_theme_switch"):
            set_setting("color_theme", int(self._theme_switch.active))
        app = App.get_running_app()
        if app:
            app.apply_settings(fetch_interval, ticker_interval, min_score)
            if hasattr(self, "_theme_switch"):
                app.apply_color_theme(self._theme_switch.active)
        self._set_status("Innstillinger lagret.")

    def _apply_theme_setting(self, use_color):
        set_setting("color_theme", int(use_color))
        app = App.get_running_app()
        if app:
            app.apply_color_theme(use_color)

    def _add_source(self):
        name = self._new_name_input.text.strip()
        url = self._new_url_input.text.strip()
        weight_text = self._new_weight_input.text.strip()
        enabled = 1 if self._new_enabled_switch.active else 0
        if not name or not url:
            self._set_status("Navn og URL må fylles ut.")
            return
        try:
            weight = float(weight_text)
        except ValueError:
            self._set_status("Weight må være et tall.")
            return
        try:
            add_source(name, url, weight, enabled)
        except sqlite3.IntegrityError:
            self._set_status("URL finnes allerede.")
            return
        except Exception:
            self._set_status("Kunne ikke legge til kilde (sjekk URL).")
            return
        self._new_name_input.text = ""
        self._new_url_input.text = ""
        self._new_weight_input.text = ""
        self._new_enabled_switch.active = True
        self._set_status("Kilde lagt til.")
        self.refresh_sources()

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
        weight_input.bind(on_text_validate=lambda *_: apply_update())
        weight_input.bind(
            on_focus=lambda instance, focused: not focused and apply_update()
        )

        edit_button = Button(text="✎", size_hint_x=None, width=dp(50))
        edit_button.bind(on_release=lambda *_: self._edit_source_popup(source))
        delete_button = Button(text="🗑", size_hint_x=None, width=dp(50))
        delete_button.bind(
            on_release=lambda *_: self._confirm_delete_source(source)
        )

        self.sources_grid.add_widget(enabled_switch)
        self.sources_grid.add_widget(weight_input)
        self.sources_grid.add_widget(name_label)
        self.sources_grid.add_widget(url_label)
        self.sources_grid.add_widget(edit_button)
        self.sources_grid.add_widget(delete_button)

    def _edit_source_popup(self, source):
        content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(12))
        name_input = self._settings_input()
        name_input.text = source["name"]
        url_input = self._settings_input()
        url_input.text = source["url"]
        weight_input = self._settings_input()
        weight_input.text = str(source["weight"])
        enabled_switch = Switch(active=bool(source["enabled"]))

        form = GridLayout(cols=2, spacing=dp(6), size_hint_y=None)
        form.bind(minimum_height=form.setter("height"))
        form.add_widget(self._settings_label("Navn"))
        form.add_widget(name_input)
        form.add_widget(self._settings_label("URL"))
        form.add_widget(url_input)
        form.add_widget(self._settings_label("Weight"))
        form.add_widget(weight_input)
        form.add_widget(self._settings_label("Enabled"))
        form.add_widget(enabled_switch)

        content.add_widget(form)
        status_label = Label(
            text="",
            font_size="14sp",
            size_hint_y=None,
            height=dp(20),
            halign="left",
            valign="middle",
        )
        status_label.bind(size=status_label.setter("text_size"))
        content.add_widget(status_label)

        actions = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8))
        popup = Popup(title="Rediger kilde", content=content, size_hint=(0.9, 0.7))

        def save_source(*_args):
            name = name_input.text.strip()
            url = url_input.text.strip()
            if not name or not url:
                status_label.text = "Navn og URL må fylles ut."
                return
            try:
                weight = float(weight_input.text.strip())
            except ValueError:
                status_label.text = "Weight må være et tall."
                return
            try:
                update_source_full(
                    source["id"],
                    name,
                    url,
                    weight,
                    int(enabled_switch.active),
                )
            except sqlite3.IntegrityError:
                status_label.text = "URL finnes allerede."
                return
            popup.dismiss()
            self._set_status("Kilde oppdatert.")
            self.refresh_sources()

        save_button = Button(text="Lagre")
        cancel_button = Button(text="Avbryt")
        save_button.bind(on_release=save_source)
        cancel_button.bind(on_release=lambda *_: popup.dismiss())
        actions.add_widget(save_button)
        actions.add_widget(cancel_button)
        content.add_widget(actions)

        popup.open()

    def _confirm_delete_source(self, source):
        content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(12))
        content.add_widget(
            Label(
                text=f"Slette {source['name']}?",
                halign="left",
                valign="middle",
            )
        )
        actions = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8))
        popup = Popup(title="Bekreft sletting", content=content, size_hint=(0.8, 0.4))

        def confirm(*_args):
            delete_source(source["id"])
            popup.dismiss()
            self._set_status("Kilde slettet.")
            self.refresh_sources()

        delete_button = Button(text="Slett")
        cancel_button = Button(text="Avbryt")
        delete_button.bind(on_release=confirm)
        cancel_button.bind(on_release=lambda *_: popup.dismiss())
        actions.add_widget(delete_button)
        actions.add_widget(cancel_button)
        content.add_widget(actions)

        popup.open()

    def _add_category(self):
        name = self._new_category_name.text.strip()
        keywords = self._new_category_keywords.text.strip()
        weight_text = self._new_category_weight.text.strip()
        enabled = 1 if self._new_category_enabled.active else 0
        if not name or not keywords:
            self._set_status("Navn og keywords må fylles ut.")
            return
        try:
            weight = float(weight_text)
        except ValueError:
            self._set_status("Weight må være et tall.")
            return
        try:
            add_category(name, keywords, weight, enabled)
        except sqlite3.IntegrityError:
            self._set_status("Kategori finnes allerede.")
            return
        self._new_category_name.text = ""
        self._new_category_keywords.text = ""
        self._new_category_weight.text = ""
        self._new_category_enabled.active = True
        self._set_status("Kategori lagt til.")
        self.refresh_categories()

    def _add_category_row(self, category):
        enabled_switch = Switch(active=bool(category["enabled"]))
        weight_input = TextInput(
            text=f'{category["weight"]:.1f}',
            multiline=False,
            font_size="16sp",
            size_hint_y=None,
            height=dp(34),
        )
        name_label = Label(
            text=category["name"],
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(60),
        )
        name_label.bind(size=name_label.setter("text_size"))
        keywords_label = Label(
            text=category["keywords"],
            halign="left",
            valign="top",
            size_hint_y=None,
            height=dp(60),
        )
        keywords_label.bind(size=keywords_label.setter("text_size"))

        def apply_update(*_args):
            try:
                weight = float(weight_input.text.strip())
            except ValueError:
                self._set_status("Weight må være et tall.")
                return
            update_category(
                category["id"],
                category["name"],
                category["keywords"],
                weight,
                int(enabled_switch.active),
            )
            self._set_status("Kategori oppdatert.")

        enabled_switch.bind(on_active=lambda *_: apply_update())
        weight_input.bind(on_text_validate=lambda *_: apply_update())
        weight_input.bind(
            on_focus=lambda instance, focused: not focused and apply_update()
        )

        edit_button = Button(text="✎", size_hint_x=None, width=dp(50))
        edit_button.bind(on_release=lambda *_: self._edit_category_popup(category))
        delete_button = Button(text="🗑", size_hint_x=None, width=dp(50))
        delete_button.bind(
            on_release=lambda *_: self._confirm_delete_category(category)
        )

        self.categories_grid.add_widget(enabled_switch)
        self.categories_grid.add_widget(weight_input)
        self.categories_grid.add_widget(name_label)
        self.categories_grid.add_widget(keywords_label)
        self.categories_grid.add_widget(edit_button)
        self.categories_grid.add_widget(delete_button)

    def _edit_category_popup(self, category):
        content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(12))
        name_input = self._settings_input()
        name_input.text = category["name"]
        keywords_input = TextInput(
            text=category["keywords"],
            multiline=True,
            font_size="16sp",
            size_hint_y=None,
            height=dp(80),
        )
        weight_input = self._settings_input()
        weight_input.text = str(category["weight"])
        enabled_switch = Switch(active=bool(category["enabled"]))

        form = GridLayout(cols=2, spacing=dp(6), size_hint_y=None)
        form.bind(minimum_height=form.setter("height"))
        form.add_widget(self._settings_label("Navn"))
        form.add_widget(name_input)
        form.add_widget(self._settings_label("Keywords"))
        form.add_widget(keywords_input)
        form.add_widget(self._settings_label("Weight"))
        form.add_widget(weight_input)
        form.add_widget(self._settings_label("Enabled"))
        form.add_widget(enabled_switch)

        content.add_widget(form)
        status_label = Label(
            text="",
            font_size="14sp",
            size_hint_y=None,
            height=dp(20),
            halign="left",
            valign="middle",
        )
        status_label.bind(size=status_label.setter("text_size"))
        content.add_widget(status_label)

        actions = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8))
        popup = Popup(title="Rediger kategori", content=content, size_hint=(0.9, 0.7))

        def save_category(*_args):
            name = name_input.text.strip()
            keywords = keywords_input.text.strip()
            if not name or not keywords:
                status_label.text = "Navn og keywords må fylles ut."
                return
            try:
                weight = float(weight_input.text.strip())
            except ValueError:
                status_label.text = "Weight må være et tall."
                return
            try:
                update_category(
                    category["id"],
                    name,
                    keywords,
                    weight,
                    int(enabled_switch.active),
                )
            except sqlite3.IntegrityError:
                status_label.text = "Kategori finnes allerede."
                return
            popup.dismiss()
            self._set_status("Kategori oppdatert.")
            self.refresh_categories()

        save_button = Button(text="Lagre")
        cancel_button = Button(text="Avbryt")
        save_button.bind(on_release=save_category)
        cancel_button.bind(on_release=lambda *_: popup.dismiss())
        actions.add_widget(save_button)
        actions.add_widget(cancel_button)
        content.add_widget(actions)

        popup.open()

    def _confirm_delete_category(self, category):
        content = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(12))
        content.add_widget(
            Label(
                text=f"Slette {category['name']}?",
                halign="left",
                valign="middle",
            )
        )
        actions = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8))
        popup = Popup(title="Bekreft sletting", content=content, size_hint=(0.8, 0.4))

        def confirm(*_args):
            delete_category(category["id"])
            popup.dismiss()
            self._set_status("Kategori slettet.")
            self.refresh_categories()

        delete_button = Button(text="Slett")
        cancel_button = Button(text="Avbryt")
        delete_button.bind(on_release=confirm)
        cancel_button.bind(on_release=lambda *_: popup.dismiss())
        actions.add_widget(delete_button)
        actions.add_widget(cancel_button)
        content.add_widget(actions)

        popup.open()


class ReaderScreen(Screen):
    _ui_built = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.current_article = None
        self._fetch_token = 0
        self._pending_theme = None

    def on_pre_enter(self, *_args):
        if not self._ui_built:
            self.build_ui()
        if self.current_article:
            self.render_article(self.current_article)
        app = App.get_running_app()
        if app:
            self.apply_theme(app.theme)

    def build_ui(self):
        layout = BoxLayout(orientation="vertical")
        self._layout = layout

        top_bar = BoxLayout(
            size_hint_y=None,
            height=dp(56),
            spacing=dp(8),
            padding=(dp(12), dp(8)),
        )
        back_button = Button(text="Tilbake")
        back_button.bind(on_release=lambda *_: App.get_running_app().show_ticker())
        open_button = Button(text="Åpne i nettleser")
        open_button.bind(on_release=lambda *_: App.get_running_app().open_in_browser())
        self._back_button = back_button
        self._open_button = open_button
        top_bar.add_widget(back_button)
        top_bar.add_widget(open_button)
        self._top_bar = top_bar

        scroll = ScrollView(do_scroll_x=False)
        content = GridLayout(
            cols=1,
            size_hint_y=None,
            spacing=dp(12),
            padding=(dp(12), dp(12)),
        )
        content.bind(minimum_height=content.setter("height"))
        scroll.add_widget(content)
        self._content = content
        self._scroll = scroll

        self._title_label = Label(
            text="",
            font_size="28sp",
            bold=True,
            halign="left",
            valign="top",
            size_hint_y=None,
        )
        self._title_label.bind(
            size=self._title_label.setter("text_size"),
            texture_size=self._set_height_from_texture,
        )

        self._meta_label = Label(
            text="",
            font_size="14sp",
            halign="left",
            valign="top",
            size_hint_y=None,
        )
        self._meta_label.bind(
            size=self._meta_label.setter("text_size"),
            texture_size=self._set_height_from_texture,
        )

        self._image = AsyncImage(
            source="",
            allow_stretch=True,
            keep_ratio=True,
            size_hint_y=None,
            height=0,
            opacity=0,
        )

        self._body_label = Label(
            text="",
            font_size="16sp",
            markup=True,
            halign="left",
            valign="top",
            size_hint_y=None,
        )
        self._body_label.bind(
            width=self._update_body_width,
            texture_size=self._set_height_from_texture,
        )

        self._note_label = Label(
            text="",
            font_size="12sp",
            halign="left",
            valign="top",
            size_hint_y=None,
            opacity=0,
        )
        self._note_label.bind(
            size=self._note_label.setter("text_size"),
            texture_size=self._set_height_from_texture,
        )

        for widget in (
            self._title_label,
            self._meta_label,
            self._image,
            self._note_label,
            self._body_label,
        ):
            content.add_widget(widget)

        layout.add_widget(top_bar)
        layout.add_widget(scroll)
        self.add_widget(layout)
        theme = (
            self._pending_theme
            or (App.get_running_app().theme if App.get_running_app() else COLOR_THEME)
        )
        self._apply_backgrounds(theme)
        self._ui_built = True
        self.apply_theme(theme)
        self._pending_theme = None

    def _apply_backgrounds(self, theme):
        self._layout_bg = self._add_background(self._layout, theme["background"])
        self._top_bar_bg = self._add_background(self._top_bar, theme["surface"])

    def _add_background(self, widget, color):
        with widget.canvas.before:
            color_instruction = Color(*color)
            rect = Rectangle(pos=widget.pos, size=widget.size)

        def update_rect(*_args):
            rect.pos = widget.pos
            rect.size = widget.size

        widget.bind(pos=update_rect, size=update_rect)
        return color_instruction

    def apply_theme(self, theme):
        if not self._ui_built:
            self._pending_theme = theme
            return
        if hasattr(self, "_layout_bg"):
            self._layout_bg.rgba = theme["background"]
        if hasattr(self, "_top_bar_bg"):
            self._top_bar_bg.rgba = theme["surface"]
        for label, color_key in (
            (getattr(self, "_title_label", None), "text_primary"),
            (getattr(self, "_meta_label", None), "text_secondary"),
            (getattr(self, "_body_label", None), "text_primary"),
            (getattr(self, "_note_label", None), "text_secondary"),
        ):
            if label:
                label.color = theme[color_key]
        for button in (
            getattr(self, "_back_button", None),
            getattr(self, "_open_button", None),
        ):
            if button:
                button.background_normal = ""
                button.background_down = ""
                button.background_color = theme["button"]
                button.color = theme["text_primary"]

    def render_article(self, article):
        self.current_article = article
        self._fetch_token += 1
        fetch_token = self._fetch_token

        title = article.get("title") or ""
        source_name = article.get("source_name") or ""
        published_ts = article.get("published_ts")
        score = article.get("score")
        published_str = self._format_published(published_ts)
        score_str = f"{score:.1f}" if score is not None else "?"
        self._title_label.text = title
        self._meta_label.text = f"{source_name} | {published_str} | score {score_str}"

        image_url = article.get("image_url")
        self._set_image(image_url)

        summary = article.get("summary") or ""
        self._body_label.text = html_to_simple_markup(summary)
        self._note_label.text = ""
        self._note_label.opacity = 0
        self._note_label.height = 0

        def worker():
            result = fetch_article_content(
                article.get("link", ""),
                rss_summary=summary,
                rss_image_url=image_url,
            )
            Clock.schedule_once(
                lambda *_: self._apply_fulltext(result, fetch_token), 0
            )

        threading.Thread(target=worker, daemon=True).start()

    def _apply_fulltext(self, result, fetch_token):
        if fetch_token != self._fetch_token:
            return
        if not result:
            return
        text = result.get("text", "")
        if text:
            self._body_label.text = html_to_simple_markup(text)
        if result.get("image_url") and not self.current_article.get("image_url"):
            self._set_image(result.get("image_url"))
        if result.get("used_fallback"):
            self._note_label.text = "Kunne ikke hente fulltekst, viser forhåndsvisning."
            self._note_label.opacity = 1
            self._note_label.height = self._note_label.texture_size[1]

    def _set_height_from_texture(self, label, *_args):
        label.height = label.texture_size[1]

    def _update_body_width(self, instance, *_args):
        instance.text_size = (instance.width, None)

    def _set_image(self, image_url):
        if image_url:
            self._image.source = image_url
            self._image.opacity = 1
            self._image.height = dp(220)
        else:
            self._image.source = ""
            self._image.opacity = 0
            self._image.height = 0

    def _format_published(self, published_ts):
        if not published_ts:
            return "ukjent tid"
        try:
            return datetime.fromtimestamp(published_ts).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return "ukjent tid"


class NIEApp(App):
    def build(self):
        init_db()
        self.cfg = EngineConfig()
        self._load_settings_from_db()

        self.sm = ScreenManager()
        self.ticker = TickerScreen(name="ticker")
        self.admin = AdminScreen(name="admin")
        self.reader = ReaderScreen(name="reader")
        self.sm.add_widget(self.ticker)
        self.sm.add_widget(self.admin)
        self.sm.add_widget(self.reader)

        Window.fullscreen = True
        Window.borderless = True
        if hasattr(Window, "state"):
            Window.state = "fullscreen"

        self._articles = []
        self._ticker_idx = 0
        self._lock = threading.Lock()
        self._current_article = None

        threading.Thread(target=self.engine_loop, daemon=True).start()

        self._ticker_event = Clock.schedule_interval(
            self.rotate_ticker,
            self.cfg.ticker_interval_sec,
        )

        self._startup_theme_smoke_check()
        self.apply_color_theme(self.use_color_theme)

        return self.sm

    def _startup_theme_smoke_check(self):
        test_reader = ReaderScreen(name="_theme_check")
        test_reader.apply_theme(self.theme)
        assert test_reader._pending_theme == self.theme

    def rotate_ticker(self, *_):
        with self._lock:
            if not self._articles:
                self.ticker.headline = "Ingen saker enda…"
                self.ticker.subline = "Venter på RSS-henting."
                self.ticker.current_link = ""
                self._current_article = None
                return

            a = self._articles[self._ticker_idx % len(self._articles)]
            self._ticker_idx += 1

        self.ticker.headline = a["title"]
        self.ticker.subline = f'{a["source_name"]} | score {a["score"]:.1f}'
        self.ticker.current_link = a["link"]
        self._current_article = a

    def open_current(self):
        article = self._current_article
        if article:
            self.show_reader(article)

    def open_in_browser(self):
        reader = getattr(self, "reader", None)
        article = self._current_article or (reader.current_article if reader else None)
        if article and article.get("link"):
            webbrowser.open(article["link"])

    def exit_app(self):
        self.stop()

    def toggle_admin(self):
        self.sm.current = "admin" if self.sm.current != "admin" else "ticker"

    def show_admin(self):
        self.sm.current = "admin"

    def show_ticker(self):
        self.sm.current = "ticker"

    def show_reader(self, article):
        self._current_article = article
        self.reader.current_article = article
        self.sm.current = "reader"

    def update_and_restart(self, status_callback=None):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

        def set_status(message):
            if status_callback:
                Clock.schedule_once(lambda *_: status_callback(message), 0)

        def worker():
            set_status("Henter siste versjon fra GitHub…")
            try:
                result = subprocess.run(
                    ["git", "pull", "--rebase"],
                    cwd=repo_root,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except Exception as exc:
                print("Update failed:", exc)
                set_status("Oppdatering feilet.")
                return
            if result.returncode != 0:
                print("Update failed:", result.stderr or result.stdout)
                set_status("Oppdatering feilet.")
                return
            set_status("Oppdatering fullført. Starter på nytt…")
            Clock.schedule_once(lambda *_: self._restart_app(), 0)

        threading.Thread(target=worker, daemon=True).start()

    def _restart_app(self):
        python = sys.executable
        os.execv(python, [python] + sys.argv)

    def apply_color_theme(self, use_color):
        self.use_color_theme = bool(use_color)
        self.theme = COLOR_THEME if self.use_color_theme else MONO_THEME
        if self.ticker:
            self.ticker.apply_theme(self.theme)
        if self.admin:
            self.admin.apply_theme(self.theme)
        if self.reader:
            self.reader.apply_theme(self.theme)

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
        self.use_color_theme = bool(int(get_setting("color_theme", 1)))
        self.theme = COLOR_THEME if self.use_color_theme else MONO_THEME
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

                try:
                    con.execute(
                        """INSERT INTO articles(guid,title,link,source_name,published_ts,summary,image_url,score,created_ts)
                           VALUES(?,?,?,?,?,?,?,?,?)""",
                        (
                            it["guid"],
                            it["title"],
                            it["link"],
                            s["name"],
                            it["published_ts"],
                            it["summary"],
                            it.get("image_url"),
                            score,
                            now,
                        )
                    )
                    inserted += 1
                except Exception:
                    pass

        con.commit()

        rows = con.execute(
            """SELECT title, link, source_name, score, summary, published_ts, image_url
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
