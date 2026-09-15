from __future__ import annotations

import asyncio
import json
import os
import queue
import random
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import uuid
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from .claude import ClaudeLimitError, chrome_path, open_login_window
from .covers import FastGenPool
from .config import (ChromeSession, FastGenKey, OpenAIKey, SecretVoicerKey, delete_session_profile, load_settings,
                     save_settings, storyflow_documents_root)
from .openai_client import HybridTextPool, OpenAITextClient
from .core import PromptRange, build_requests, parse_titles, read_text_file, safe_filename, write_exports
from .runner import Job, ParallelRunner, RunState
from .session import load_session, remove_scenarios, rename_scenario, save_session
from .ui_helpers import clipboard_action
from .footage import (download_best_youtube_segment, download_footage, download_youtube_segment, search_wikimedia_videos,
                      search_youtube_videos, search_all_available_videos)
from .config import app_data_root
from .ai_index import ClipIndex
from .player import VideoPlayer
from .timeline import (TimelineClip, TimelineProject, agent_plan_prompt, fallback_scene_plan,
                       parse_agent_scene_plan, probe_media_duration, render_project, remotion_payload)
from .voicer import ChromeSecretVoicer, SecretVoicerClient, VoiceProfile, open_voice_login
from .cutter import cut_sources
from .mixer import make_mix_plans, render_mixes

try:
    from tkinterdnd2 import COPY, DND_FILES, TkinterDnD
    RootWindow = TkinterDnD.Tk
except ImportError:
    COPY = "copy"
    DND_FILES = None
    RootWindow = tk.Tk


# Shared visual system, aligned with Voicer: calmer navy surfaces, clearer
# hierarchy and one blue/green status language across all production modules.
# Visual language: one calm studio surface, close to the Voicer reference.
# The contrast is intentionally kept modest so tables and long production
# forms remain readable for several hours at a time.
BG = "#071526"
SIDEBAR = "#081526"
CARD = "#0D1D31"
CARD_2 = "#0A192B"
BORDER = "#1A3551"
ACTIVE = "#163354"
BLUE = "#2E7FF0"
BLUE_HOVER = "#438FF6"
GREEN = "#087B54"
RED = "#432532"
TEXT = "#F1F6FF"
MUTED = "#83A0BF"
MUTED_2 = "#5E7894"

COVER_MODELS = {
    "Flower • Flower Image — 1 кредит": "flower_image_generate",
    "Grok • Grok Image — 1/3 кредита": "grok_image_generate",
    "OpenAI • Image — 4 кредита": "openai_image_generate",
    "Flow • Nano Banana 2 — 4 кредита": "nano_banana_2_image_generate",
    "Flow • Nano Banana 2 Lite — 4 кредита": "nano_banana_2_lite_image_generate",
    "Flow • Nano Banana Pro — 4 кредита": "nano_banana_pro_image_generate",
}

VIDEO_MODELS = {
    "Flower • Video 3.1 — 1 кредит": "flower_video_from_text",
    "Grok • Video — 1/3 кредита": "grok_video_from_text",
    "Flow • Veo Fast — 1 кредит": "flow_video_from_text",
    "Flow • Veo Lite — 1 кредит": "flow_video_lite_from_text",
    "Flow • Veo Quality — 10 кредитов": "flow_video_quality_from_text",
    "Flow • Omni Flash 4s — 1 кредит": "flow_video_omni_flash_from_text_4s",
}


class ModelSelector(tk.Frame):
    """Dark model picker with real Tk foreground colors instead of monochrome emoji."""

    COLORS = {"available": "#35D99A", "unavailable": "#FF5D73", "unknown": "#F5C451"}

    def __init__(self, parent, models, statuses, selected_operation=None, width=34):
        super().__init__(parent, bg=CARD_2, highlightbackground=BORDER, highlightthickness=1)
        self.models = models
        self.statuses = statuses
        self.selected_label = next((label for label, operation in models.items()
                                    if operation == selected_operation), next(iter(models)))
        self.dot = tk.Label(self, text="●", bg=CARD_2, font=("Segoe UI", 11))
        self.dot.pack(side="left", padx=(8, 3))
        self.variable = tk.StringVar(value=self.selected_label)
        self.button = tk.Menubutton(
            self, textvariable=self.variable, bg=CARD_2, fg=TEXT, activebackground=ACTIVE,
            activeforeground=TEXT, relief="flat", bd=0, width=width, anchor="w",
            font=("Segoe UI", 9), cursor="hand2",
        )
        self.menu = tk.Menu(self.button, tearoff=False, bg=CARD_2, fg=TEXT,
                            activebackground=ACTIVE, activeforeground=TEXT,
                            relief="flat", bd=1, font=("Segoe UI", 9))
        self.button.config(menu=self.menu)
        self.button.pack(side="left", fill="x", expand=True, ipady=6)
        tk.Label(self, text="▾", bg=CARD_2, fg=TEXT, font=("Segoe UI", 9)).pack(side="right", padx=7)
        self.update_status(statuses)

    def get(self):
        return self.selected_label

    def set(self, value):
        label = next((label for label, operation in self.models.items()
                      if value == operation or value == label or value.endswith(label)), None)
        if label:
            self._select(label)

    def _select(self, label):
        self.selected_label = label
        self.variable.set(label)
        operation = self.models[label]
        self.dot.config(fg=self.COLORS[self.statuses.get(operation, "unknown")])

    def update_status(self, statuses):
        self.statuses = statuses
        self.menu.delete(0, "end")
        for label, operation in self.models.items():
            color = self.COLORS[statuses.get(operation, "unknown")]
            self.menu.add_command(label=f"●  {label}", foreground=color,
                                  activeforeground=color, command=lambda value=label: self._select(value))
        self._select(self.selected_label)


class StudioButton(tk.Canvas):
    """Canvas button with the same rounded, compact character as Voicer.

    Tk buttons cannot draw rounded controls.  Making this a drop-in replacement
    lets every existing NewsFlow action use one modern component without
    changing the workflow code behind it.
    """

    PALETTE = {
        "primary": ("#1765CA", "#2C80EC", "#FFFFFF"),
        "success": ("#126544", "#16805A", "#EAFFF6"),
        "danger": ("#39202D", "#563047", "#FFCBD4"),
        "secondary": ("#102238", "#183454", "#D5E3F3"),
    }

    def __init__(self, parent, text, command, kind="secondary"):
        self._text = text
        self._command = command
        self._kind = kind
        self._state = "normal"
        self._hover = False
        self._font = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        self._base, self._hover_bg, self._fg = self.PALETTE[kind]
        width = max(84, self._font.measure(text) + 32)
        super().__init__(parent, width=width, height=38, bg=parent.cget("bg"), bd=0,
                         highlightthickness=0, cursor="hand2", takefocus=0)
        self.bind("<Configure>", lambda _event: self._redraw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self._redraw()

    def _rounded_rect(self, x1, y1, x2, y2, radius, **kwargs):
        points = [x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
                  x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
                  x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1]
        return self.create_polygon(points, smooth=True, **kwargs)

    def _redraw(self):
        self.delete("all")
        if self._state == "disabled":
            fill, fg = "#122238", "#58708B"
        else:
            fill, fg = (self._hover_bg if self._hover else self._base), self._fg
        width, height = max(1, self.winfo_width()), max(1, self.winfo_height())
        self._rounded_rect(1, 1, width - 1, height - 1, 9, fill=fill, outline=fill)
        self.create_text(width / 2, height / 2, text=self._text, fill=fg, font=self._font)

    def _on_enter(self, _event=None):
        if self._state != "disabled":
            self._hover = True; self._redraw()

    def _on_leave(self, _event=None):
        self._hover = False; self._redraw()

    def _on_click(self, _event=None):
        if self._state != "disabled" and self._command:
            self._command()

    def configure(self, cnf=None, **kwargs):
        options = dict(cnf or {})
        options.update(kwargs)
        if "text" in options:
            self._text = str(options.pop("text"))
            self.configure(width=max(84, self._font.measure(self._text) + 32))
        if "state" in options:
            self._state = str(options.pop("state"))
            super().configure(cursor="arrow" if self._state == "disabled" else "hand2")
        if "command" in options:
            self._command = options.pop("command")
        result = super().configure(**options) if options else None
        self._redraw()
        return result

    config = configure


class StudioNavItem(tk.Canvas):
    """Rounded sidebar item with a thin blue active marker."""

    def __init__(self, parent, text, command, indent=0):
        self._text = text
        self._command = command
        self._indent = indent
        self._selected = False
        self._hover = False
        super().__init__(parent, height=42, bg=SIDEBAR, bd=0, highlightthickness=0,
                         cursor="hand2", takefocus=0)
        self._font = tkfont.Font(family="Segoe UI", size=10)
        self.bind("<Configure>", lambda _event: self._redraw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", lambda _event: self._command())
        self._redraw()

    def set_selected(self, selected: bool):
        self._selected = selected
        self._font.configure(weight="bold" if selected else "normal")
        self._redraw()

    def _on_enter(self, _event=None):
        self._hover = True; self._redraw()

    def _on_leave(self, _event=None):
        self._hover = False; self._redraw()

    def _redraw(self):
        self.delete("all")
        width, height = max(1, self.winfo_width()), max(1, self.winfo_height())
        if self._selected or self._hover:
            fill = "#153556" if self._selected else "#102842"
            self.create_polygon([9, 1, width - 1, 1, width - 1, height - 1, 9, height - 1,
                                 1, height - 1, 1, 9], smooth=True, fill=fill, outline=fill)
        if self._selected:
            self.create_rectangle(1, 10, 3, height - 10, fill="#3C8CFF", outline="")
        self.create_text(15 + self._indent, height / 2, text=self._text,
                         fill=TEXT if self._selected else MUTED, anchor="w", font=self._font)


class ScriptorApp:
    def __init__(self):
        self.root = RootWindow()
        self.root.title("NewsFlow Studio")
        self.root.geometry("1380x830")
        self.root.minsize(1080, 680)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        try:
            asset_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])) / "assets"
            self.root.iconbitmap(asset_root / "scriptor.ico")
        except Exception:
            pass

        self.settings = load_settings()
        # Persist generated profile ids and migrations immediately, so an
        # interrupted first launch cannot lose browser/voice session bindings.
        try:
            save_settings(self.settings)
        except Exception:
            pass
        self.titles, self.jobs = load_session()
        self.events: queue.Queue = queue.Queue()
        self.running = False
        self.active_runner: ParallelRunner | None = None
        self.current_page = "dashboard"
        self.nav_buttons: dict[str, tk.Button] = {}
        self.nav_group_buttons: dict[str, tk.Button] = {}
        self.nav_group_children: dict[str, tk.Frame] = {}
        self.nav_group_icons: dict[str, str] = {}
        self.nav_group_expanded = {
            "preparation": True, "visuals": False, "voice": False, "footage": False,
            "editing": False, "publication": False, "settings": False,
        }
        self.nav_group_labels = {
            "preparation": "Подготовка", "visuals": "Обложки и генерации", "voice": "Озвучка",
            "footage": "Футажи", "editing": "Монтаж", "publication": "Публикация", "settings": "Настройки",
        }
        self.range_rows = []
        self.table = None
        self.generated_ideas: list[str] = []
        self.ideas_running = False
        self.ideas_listbox = None
        self.selected_idea_topics: set[str] = set()
        self.auto_pipeline_active = False
        self.cover_items: list[dict] = list(self.settings.cover_queue)
        self.covers_running = False
        self.cover_references: list[str] = []
        self.media_references: list[str] = []
        self.media_results: list[str] = []
        self.media_prompts: list[dict] = []
        self.media_source_text = ""
        self.media_source_path = ""
        self.media_auto_style = False
        self.media_use_interval = False
        self.media_interval_chars = "1000"
        self.media_mode = "image"
        self.media_running = False
        self.fastgen_model_status: dict[str, str] = {
            operation: "unknown" for operation in (*COVER_MODELS.values(), *VIDEO_MODELS.values())
        }
        self.fastgen_capabilities: dict[str, list[dict]] = {"image": [], "video": []}
        self.fastgen_usage: list[dict] = []
        self.fastgen_refresh_running = False
        self.seo_items: list[dict] = []
        self.seo_running = False
        self.last_saved_paths: dict[str, str] = {}
        self.clip_index = ClipIndex(app_data_root() / "footage-index.sqlite3")
        self.footage_items = self.clip_index.all_items()
        self.web_footage_results: list[dict] = []
        self.index_running = False
        self.index_cancel = threading.Event()
        self.cutter_sources: list[str] = []
        self.cutter_running = False
        self.timeline_project = TimelineProject("Новый проект", self.settings.montage_aspect_ratio)
        self.video_player = None
        self.montage_running = False
        self.voicer_running = False
        self.voice_batch_running = False
        self.voicer_catalog: list[dict] = []

        self._style()
        self._shell()
        self._show_page("dashboard")
        self.root.after(100, self._process_events)
        self.root.after(700, self._auto_refresh_fastgen)

    def _style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(
            "Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT,
            rowheight=39, borderwidth=0, relief="flat", font=("Segoe UI", 10),
        )
        style.configure(
            "Treeview.Heading", background=CARD_2, foreground=MUTED,
            borderwidth=0, relief="flat", font=("Segoe UI Semibold", 9),
        )
        style.map("Treeview", background=[("selected", ACTIVE)], foreground=[("selected", TEXT)])
        style.configure("TProgressbar", troughcolor=CARD, background=BLUE, borderwidth=0)
        style.configure(
            "Dark.TCombobox", fieldbackground=CARD_2, background=CARD_2, foreground=TEXT,
            arrowcolor=TEXT, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
            insertcolor=TEXT, padding=5,
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", CARD_2), ("focus", CARD_2)],
            foreground=[("readonly", TEXT), ("focus", TEXT)],
            selectbackground=[("readonly", ACTIVE)], selectforeground=[("readonly", TEXT)],
        )
        self.root.option_add("*TCombobox*Listbox.background", CARD_2)
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACTIVE)
        self.root.option_add("*TCombobox*Listbox.selectForeground", TEXT)

    def _shell(self):
        self.sidebar = tk.Frame(self.root, bg=SIDEBAR, width=242,
                                highlightbackground=BORDER, highlightthickness=1)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        self.content = tk.Frame(self.root, bg=BG)
        self.content.pack(side="left", fill="both", expand=True)

        brand = tk.Frame(self.sidebar, bg=SIDEBAR, padx=18, pady=28)
        brand.pack(fill="x")
        logo = tk.Label(brand, text="N", bg="#3F68FF", fg="white", width=3, height=1,
                        font=("Segoe UI Black", 16), relief="flat", padx=2, pady=4)
        logo.pack(side="left")
        brand_text = tk.Frame(brand, bg=SIDEBAR)
        brand_text.pack(side="left", padx=12)
        tk.Label(brand_text, text="NEWSFLOW", bg=SIDEBAR, fg=TEXT,
                 font=("Segoe UI Semibold", 13)).pack(anchor="w")
        tk.Label(brand_text, text="НОВОСТНЫЕ РОЛИКИ", bg=SIDEBAR, fg=MUTED,
                 font=("Segoe UI", 7)).pack(anchor="w", pady=(3, 0))

        nav = tk.Frame(self.sidebar, bg=SIDEBAR, pady=6)
        nav.pack(fill="x")
        dashboard = StudioNavItem(nav, "◉  Центр управления", lambda: self._show_page("dashboard"))
        dashboard.pack(fill="x", padx=8, pady=(0, 9))
        self.nav_buttons["dashboard"] = dashboard
        self._add_nav_group(nav, "preparation", "✦", [
            ("ideas", "Генерация идей"), ("scenarios", "Новости"), ("templates", "Шаблоны и промпты"),
        ])
        self._add_nav_group(nav, "visuals", "◈", [
            ("covers", "Обложки YouTube"), ("media", "Картинки и видео"),
        ])
        self._add_nav_group(nav, "voice", "◉", [
            ("voice_profiles", "Голоса и API"), ("voice_create", "Создать озвучку"),
            ("voice_outputs", "Готовые MP3"),
        ])
        self._add_nav_group(nav, "footage", "▰", [
            ("footage", "Поиск и библиотека"), ("footage_cutter", "Нарезка исходников"),
        ])
        self._add_nav_group(nav, "editing", "◆", [
            ("editor", "Таймлайн и экспорт"),
        ])
        self._add_nav_group(nav, "publication", "⌁", [
            ("seo", "SEO-пакеты"), ("analytics", "Аналитика и каналы"), ("outputs", "Результаты"),
        ])
        self._add_nav_group(nav, "settings", "⚙", [
            ("keys", "Сессии Chrome"), ("api_keys", "API-ключи"),
        ])

        self.key_badge = tk.Label(self.sidebar, text="", bg=ACTIVE, fg=TEXT,
                                  font=("Segoe UI Semibold", 8), padx=7, pady=2)
        # Счётчик сессий остаётся для обновления статуса, но не перекрывает
        # пункты навигации. Сами сессии доступны в разделе «Настройки».

        status = tk.Frame(self.sidebar, bg=CARD_2, padx=14, pady=11)
        status.pack(side="bottom", fill="x", padx=8, pady=8)
        tk.Label(status, text="●", bg=CARD_2, fg="#37E6A1", font=("Segoe UI", 10)).pack(side="left")
        self.system_status = tk.Label(status, text="Система готова", bg=CARD_2, fg=TEXT,
                                      font=("Segoe UI", 9))
        self.system_status.pack(side="left", padx=7)

        fastgen_status = tk.Frame(self.sidebar, bg=CARD_2, padx=12, pady=9)
        fastgen_status.pack(side="bottom", fill="x", padx=8, pady=(0, 2))
        self.fastgen_sidebar_dot = tk.Label(fastgen_status, text="●", bg=CARD_2, fg="#F5C451",
                                            font=("Segoe UI", 10))
        self.fastgen_sidebar_dot.pack(side="left", anchor="n")
        self.fastgen_sidebar_status = tk.Label(fastgen_status, text="FastGen: проверка…", bg=CARD_2, fg=MUTED,
                                               justify="left", wraplength=170, font=("Segoe UI", 8))
        self.fastgen_sidebar_status.pack(side="left", padx=7)

        top = tk.Frame(self.content, bg=BG, padx=38, pady=32)
        top.pack(fill="x", pady=(0, 0))
        title_area = tk.Frame(top, bg=BG)
        title_area.pack(side="left")
        self.page_eyebrow = tk.Label(title_area, text="РАБОЧЕЕ ПРОСТРАНСТВО", bg=BG, fg=BLUE,
                                     font=("Segoe UI Semibold", 8))
        self.page_eyebrow.pack(anchor="w", pady=(0, 4))
        self.page_title = tk.Label(title_area, text="", bg=BG, fg=TEXT,
                                   font=("Segoe UI Semibold", 25))
        self.page_title.pack(anchor="w")
        self.page_subtitle = tk.Label(title_area, text="", bg=BG, fg=MUTED,
                                      font=("Segoe UI", 10))
        self.page_subtitle.pack(anchor="w", pady=(4, 0))

        counters = tk.Frame(top, bg=BG)
        counters.pack(side="right")
        self.counter_labels = {}
        for key, label, color in (("waiting", "Ожидают", TEXT), ("running", "В работе", TEXT), ("done", "Готово", "#2BDB9B")):
            card = tk.Frame(counters, bg=CARD, highlightbackground=BORDER, highlightthickness=1,
                            width=78, height=58)
            card.pack(side="left", padx=5)
            card.pack_propagate(False)
            value = tk.Label(card, text="0", bg=CARD, fg=color, font=("Segoe UI Semibold", 14))
            value.pack(anchor="w", padx=13, pady=(8, 0))
            tk.Label(card, text=label, bg=CARD, fg=MUTED, font=("Segoe UI", 7)).pack(anchor="w", padx=13)
            self.counter_labels[key] = value

        page_host = tk.Frame(self.content, bg=BG)
        page_host.pack(fill="both", expand=True)
        self.page_canvas = tk.Canvas(page_host, bg=BG, highlightthickness=0, bd=0)
        page_scroll = ttk.Scrollbar(page_host, orient="vertical", command=self.page_canvas.yview)
        self.page_canvas.configure(yscrollcommand=page_scroll.set)
        page_scroll.pack(side="right", fill="y")
        self.page_canvas.pack(side="left", fill="both", expand=True)
        self.page = tk.Frame(self.page_canvas, bg=BG, padx=38, pady=0)
        self.page_window = self.page_canvas.create_window((0, 0), window=self.page, anchor="nw")
        self.page.bind("<Configure>", lambda _: self.page_canvas.configure(scrollregion=self.page_canvas.bbox("all")))
        self.page_canvas.bind("<Configure>", lambda event: self.page_canvas.itemconfigure(self.page_window, width=event.width))
        self.page_canvas.bind_all("<MouseWheel>", lambda event: self.page_canvas.yview_scroll(int(-event.delta / 120), "units"))

    def _show_page(self, page):
        if self.video_player is not None:
            self.video_player.close()
            self.video_player = None
        if self.current_page == "templates" and self.range_rows:
            self._sync_template_settings()
        self.current_page = page
        self.page_canvas.yview_moveto(0)
        for key, button in self.nav_buttons.items():
            selected = key == page
            if isinstance(button, StudioNavItem):
                button.set_selected(selected)
            else:
                button.configure(
                    bg=ACTIVE if selected else SIDEBAR, fg=TEXT if selected else MUTED,
                    font=("Segoe UI Semibold", 9) if selected else ("Segoe UI", 9),
                    highlightbackground=BLUE if selected else SIDEBAR,
                    highlightthickness=1 if selected else 0,
                )
        group_for_page = {
            "dashboard": None,
            "ideas": "preparation", "scenarios": "preparation", "templates": "preparation",
            "covers": "visuals", "media": "visuals", "footage": "footage", "footage_cutter": "footage",
            "voice_create": "voice", "voice_profiles": "voice", "voice_outputs": "voice", "editor": "editing",
            "seo": "publication", "analytics": "publication", "outputs": "publication",
            "keys": "settings", "api_keys": "settings",
        }.get(page)
        if group_for_page and not self.nav_group_expanded[group_for_page]:
            self.nav_group_expanded[group_for_page] = True
            self._refresh_nav_group(group_for_page)
        for child in self.page.winfo_children():
            child.destroy()
        self.range_rows = []
        self.table = None
        titles = {
            "dashboard": ("Центр управления", "Весь путь ролика — от идеи до готового пакета для публикации"),
            "scenarios": ("Новости", "Импортируйте темы, настройте шаблоны и запустите подготовку новостей"),
            "footage": ("Футажи", "Подключите свои папки; агент сначала ищет кадры в них, затем — в интернете"),
            "editor": ("Монтаж", "Подбор кадров по теме и подготовка монтажного плана"),
            "seo": ("SEO-пакеты", "Заголовки, описания и теги для каждого новостного ролика"),
            "ideas": ("Генерация идей", "Выберите одно из 17 новостных направлений и подготовьте углы подачи"),
            "templates": ("Шаблоны и диапазоны", "Общий промпт и требования для групп новостей"),
            "keys": ("Сессии Chrome", "Отдельные профили Chrome для входа в Claude без API"),
            "api_keys": ("API-ключи", "Резервная генерация через OpenAI API, когда Chrome-сессии заняты"),
            "outputs": ("Результаты", "Автоматическое сохранение материалов по названиям новостей"),
            "voice_create": ("Озвучка", "Создайте MP3 из сценария и сразу передайте его в монтаж"),
            "voice_profiles": ("Голоса и API", "Профили дикторов, Voice ID и зашифрованный ключ Secret Voicer"),
            "voice_outputs": ("Готовые MP3", "Все сгенерированные озвучки проекта"),
            "footage_cutter": ("Нарезка футажей", "Исходники → тихие клипы одинаковой длины и 30 FPS → ИИ-индексация"),
            "covers": ("Обложки YouTube", "Промпты из сценариев и создание обложек через FastGen API"),
            "media": ("Картинки и видео", "Генерация дополнительных кадров и видеовставок через FastGen API"),
            "analytics": ("Аналитика и каналы", "Каналы YouTube, последние ролики, просмотры, доход и статус монетизации"),
        }
        self.page_title.config(text=titles[page][0])
        self.page_subtitle.config(text=titles[page][1])
        if hasattr(self, "page_eyebrow"):
            self.page_eyebrow.config(text=(self.nav_group_labels.get(group_for_page, "РАБОЧЕЕ ПРОСТРАНСТВО")).upper())
        getattr(self, f"_page_{page}")()
        self._update_counters()

    def _toggle_nav_group(self, group: str):
        self.nav_group_expanded[group] = not self.nav_group_expanded.get(group, True)
        self._refresh_nav_group(group)

    def _refresh_nav_group(self, group: str):
        expanded = self.nav_group_expanded.get(group, True)
        button = self.nav_group_buttons[group]
        icon = self.nav_group_icons.get(group, "•")
        button.config(text=f"  {icon}  {self.nav_group_labels[group]}    {'⌄' if expanded else '›'}")
        children = self.nav_group_children[group]
        if expanded:
            children.pack(fill="x", padx=0, pady=(0, 3), after=button)
        else:
            children.pack_forget()

    def _add_nav_group(self, parent, group: str, icon: str, items: list[tuple[str, str]]):
        button = tk.Button(parent, anchor="w", command=lambda key=group: self._toggle_nav_group(key),
                           bg=SIDEBAR, fg=MUTED, activebackground=ACTIVE, activeforeground=TEXT,
                           relief="flat", bd=0, padx=13, pady=9, cursor="hand2", font=("Segoe UI Semibold", 10))
        button.pack(fill="x", padx=8, pady=1)
        self.nav_group_buttons[group] = button
        self.nav_group_icons[group] = icon
        children = tk.Frame(parent, bg=SIDEBAR)
        self.nav_group_children[group] = children
        for key, label in items:
            child = StudioNavItem(children, label, lambda page=key: self._show_page(page), indent=16)
            child.pack(fill="x", padx=8, pady=1)
            self.nav_buttons[key] = child
        self._refresh_nav_group(group)

    def _button(self, parent, text, command, kind="secondary"):
        return StudioButton(parent, text, command, kind)

    def _entry(self, parent, **kwargs):
        widget = tk.Entry(
            parent, bg=CARD_2, fg=TEXT, insertbackground=TEXT, relief="flat",
            highlightthickness=1, highlightbackground=BORDER, highlightcolor=BLUE,
            readonlybackground=CARD_2, disabledbackground=CARD_2, disabledforeground=MUTED,
            font=("Segoe UI", 10), **kwargs,
        )
        self._install_edit_bindings(widget, multiline=False)
        return widget

    def _text_pool(self, sessions, chat_url="https://claude.ai/new"):
        return HybridTextPool(sessions, self.settings.openai_api_keys, chat_url, self.settings.openai_model)

    def _sessions_for(self, workflow: str):
        return [item for item in self.settings.chrome_sessions
                if item.active and item.usage.get(workflow, True)]

    def _install_edit_bindings(self, widget, multiline: bool):
        widget.bind("<Control-KeyPress>", lambda event, target=widget, multi=multiline: self._clipboard_key(event, target, multi), add="+")
        widget.bind("<Button-3>", lambda event, target=widget, multi=multiline: self._show_edit_menu(event, target, multi), add="+")

    def _clipboard_key(self, event, widget, multiline: bool):
        action = clipboard_action(event.keysym, event.keycode)
        if not action:
            return None
        self._edit_action(widget, multiline, action)
        return "break"

    def _edit_action(self, widget, multiline: bool, action: str):
        if action == "select_all":
            if multiline:
                widget.tag_add("sel", "1.0", "end-1c")
                widget.mark_set("insert", "end-1c")
            else:
                widget.selection_range(0, "end")
                widget.icursor("end")
            return
        if action in ("copy", "cut"):
            try:
                selected = widget.selection_get()
            except tk.TclError:
                return
            self.root.clipboard_clear()
            self.root.clipboard_append(selected)
            if action == "copy":
                return
            try:
                if multiline:
                    widget.delete("sel.first", "sel.last")
                else:
                    widget.delete("sel.first", "sel.last")
            except tk.TclError:
                pass
            return
        if action == "paste":
            try:
                value = self.root.clipboard_get()
            except tk.TclError:
                return
            try:
                widget.delete("sel.first", "sel.last")
            except tk.TclError:
                pass
            widget.insert("insert", value)

    def _show_edit_menu(self, event, widget, multiline: bool):
        menu = tk.Menu(self.root, tearoff=False, bg=CARD_2, fg=TEXT, activebackground=ACTIVE,
                       activeforeground=TEXT, relief="flat")
        menu.add_command(label="Вырезать", command=lambda: self._edit_action(widget, multiline, "cut"))
        menu.add_command(label="Копировать", command=lambda: self._edit_action(widget, multiline, "copy"))
        menu.add_command(label="Вставить", command=lambda: self._edit_action(widget, multiline, "paste"))
        menu.add_separator()
        menu.add_command(label="Выделить всё", command=lambda: self._edit_action(widget, multiline, "select_all"))
        menu.tk_popup(event.x_root, event.y_root)

    def _card(self, parent, **pack):
        frame = tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        frame.pack(**pack)
        return frame

    def _section_header(self, parent, title: str, subtitle: str = ""):
        """Small, consistent heading for settings and queue cards."""
        header = tk.Frame(parent, bg=CARD)
        header.pack(fill="x", padx=20, pady=(18, 10))
        copy = tk.Frame(header, bg=CARD)
        copy.pack(side="left", fill="x", expand=True)
        tk.Label(copy, text=title, bg=CARD, fg=TEXT, font=("Segoe UI Semibold", 13)).pack(anchor="w")
        if subtitle:
            tk.Label(copy, text=subtitle, bg=CARD, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", pady=(3, 0))
        return header

    def _page_dashboard(self):
        completed = sum(job.state == RunState.DONE for job in self.jobs)
        voices = sum(1 for path in self.settings.voice_scenario_outputs.values() if Path(path).is_file())
        videos = sum(1 for path in self.settings.pipeline_montage_outputs if Path(path).is_file())

        pipeline = self._card(self.page, fill="x", pady=(4, 14))
        pipeline_inner = tk.Frame(pipeline, bg=CARD, padx=18, pady=10)
        pipeline_inner.pack(fill="x")
        tk.Label(pipeline_inner, text="КОНВЕЙЕР", bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 8)).pack(side="left")
        tk.Label(pipeline_inner, text="Цель", bg=CARD, fg=MUTED, font=("Segoe UI", 9)).pack(side="left", padx=(18, 5))
        self.pipeline_target_entry = self._entry(pipeline_inner, width=6)
        self.pipeline_target_entry.insert(0, str(self.settings.pipeline_target_count))
        self.pipeline_target_entry.pack(side="left", ipady=3)
        self.pipeline_target_entry.bind("<Return>", lambda _: self._save_pipeline_target())
        self._button(pipeline_inner, "Сохранить", self._save_pipeline_target).pack(side="left", padx=6)
        self.pipeline_labels = {}
        for key, label in (("ideas", "Идеи"), ("scripts", "Сценарии"), ("voice", "Озвучка"), ("montage", "MP4")):
            chip = tk.Frame(pipeline_inner, bg=CARD_2, padx=9, pady=4)
            chip.pack(side="right", padx=(7, 0))
            tk.Label(chip, text=f"{label}: ", bg=CARD_2, fg=MUTED, font=("Segoe UI", 8)).pack(side="left")
            value = tk.Label(chip, text="0 / 0", bg=CARD_2, fg=TEXT, font=("Segoe UI Semibold", 8))
            value.pack(side="left")
            self.pipeline_labels[key] = value
        self._refresh_pipeline_calculator()

        hero = tk.Frame(self.page, bg="#0E223B", padx=25, pady=22, highlightbackground="#24517E", highlightthickness=1)
        hero.pack(fill="x", pady=(4, 16))
        copy = tk.Frame(hero, bg="#0E223B")
        copy.pack(side="left", fill="x", expand=True)
        tk.Label(copy, text="Новый выпуск начинается здесь", bg="#0E223B", fg=TEXT,
                 font=("Segoe UI Semibold", 19)).pack(anchor="w")
        tk.Label(copy, text="Выберите направление, подготовьте сценарий, создайте озвучку — монтаж сам подстроится под MP3.",
                 bg="#0E223B", fg="#9EB6D2", font=("Segoe UI", 10), wraplength=650, justify="left").pack(anchor="w", pady=(6, 0))
        hero_actions = tk.Frame(hero, bg="#0E223B")
        hero_actions.pack(side="right", padx=(18, 0))
        self._button(hero_actions, "Создать выпуск", lambda: self._show_page("ideas"), "primary").pack(pady=(2, 7))
        self._button(hero_actions, "Запустить автоэтапы", self._start_auto_pipeline, "success").pack(pady=(0, 7))
        self._button(hero_actions, "Открыть результаты", lambda: self._show_page("outputs")).pack()

        summary = tk.Frame(self.page, bg=BG)
        summary.pack(fill="x", pady=(0, 16))
        for column in range(4):
            summary.grid_columnconfigure(column, weight=1, uniform="summary")
        for column, (value, label, hint, color) in enumerate((
            (len(self.generated_ideas), "Идей", "ожидают отбора", BLUE),
            (completed, "Сценариев", "готовы к озвучке", "#7B78FF"),
            (voices, "Озвучек", "MP3 созданы", "#37D99A"),
            (videos, "Роликов", "MP4 готовы", "#F5C451"),
        )):
            card = tk.Frame(summary, bg=CARD, padx=17, pady=14, highlightbackground=BORDER, highlightthickness=1)
            card.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 5, 5 if column < 3 else 0))
            tk.Label(card, text=str(value), bg=CARD, fg=color, font=("Segoe UI Semibold", 22)).pack(anchor="w")
            tk.Label(card, text=label, bg=CARD, fg=TEXT, font=("Segoe UI Semibold", 10)).pack(anchor="w", pady=(2, 0))
            tk.Label(card, text=hint, bg=CARD, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", pady=(3, 0))

        flow = self._card(self.page, fill="x", pady=(0, 16))
        flow_head = tk.Frame(flow, bg=CARD, padx=20, pady=8)
        flow_head.pack(fill="x", pady=(9, 0))
        tk.Label(flow_head, text="Рабочий маршрут", bg=CARD, fg=TEXT, font=("Segoe UI Semibold", 13)).pack(side="left")
        tk.Label(flow_head, text="Можно открывать любой этап вручную. Автомонтаж идёт по этой последовательности.",
                 bg=CARD, fg=MUTED, font=("Segoe UI", 8)).pack(side="left", padx=10)
        stages = tk.Frame(flow, bg=CARD, padx=15, pady=10)
        stages.pack(fill="x", pady=(0, 8))
        for column in range(5):
            stages.grid_columnconfigure(column, weight=1, uniform="stage")
        steps = [
            ("01", "Идеи", "Темы и углы", "ideas", BLUE),
            ("02", "Сценарии", "Факты и текст", "scenarios", "#7B78FF"),
            ("03", "Озвучка", "Голос и MP3", "voice_create", "#37D99A"),
            ("04", "Футажи", "Поиск и выбор", "footage", "#4CB7E9"),
            ("05", "Монтаж", "Таймлайн и MP4", "editor", "#F5C451"),
        ]
        for column, (number, title, hint, page, color) in enumerate(steps):
            stage = tk.Frame(stages, bg=CARD_2, padx=14, pady=13, highlightbackground=BORDER, highlightthickness=1)
            stage.grid(row=0, column=column, sticky="nsew", padx=4)
            tk.Label(stage, text=number, bg=CARD_2, fg=color, font=("Segoe UI Semibold", 8)).pack(anchor="w")
            tk.Label(stage, text=title, bg=CARD_2, fg=TEXT, font=("Segoe UI Semibold", 11)).pack(anchor="w", pady=(7, 2))
            tk.Label(stage, text=hint, bg=CARD_2, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w")
            link = tk.Button(stage, text="Открыть →", command=lambda target=page: self._show_page(target),
                             bg=CARD_2, fg=color, activebackground=ACTIVE, activeforeground=TEXT,
                             relief="flat", bd=0, cursor="hand2", font=("Segoe UI Semibold", 8), padx=0, pady=0)
            link.pack(anchor="w", pady=(12, 0))

        next_card = self._card(self.page, fill="x")
        next_inner = tk.Frame(next_card, bg=CARD, padx=20, pady=16)
        next_inner.pack(fill="x")
        tk.Label(next_inner, text="Следующий логичный шаг", bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 8)).pack(anchor="w")
        if completed and not voices:
            text, action, target = "Создать MP3 для готовых сценариев", "Перейти к озвучке", "voice_create"
        elif voices and not videos:
            text, action, target = "Собрать таймлайн по длине готовой озвучки", "Открыть монтаж", "editor"
        elif not self.generated_ideas:
            text, action, target = "Выбрать направление и сгенерировать идеи", "Открыть генерацию идей", "ideas"
        else:
            text, action, target = "Посмотреть готовые пакеты роликов", "Открыть результаты", "outputs"
        tk.Label(next_inner, text=text, bg=CARD, fg=TEXT, font=("Segoe UI Semibold", 13)).pack(anchor="w", pady=(5, 0))
        self._button(next_inner, action, lambda: self._show_page(target), "primary").pack(anchor="e", pady=(8, 0))

    def _start_auto_pipeline(self):
        if self.running or self.ideas_running or self.voice_batch_running:
            messagebox.showinfo("Автоконвейер", "Текущий этап ещё выполняется.", parent=self.root)
            return
        if not self.titles and self.generated_ideas:
            self.titles.extend(idea for idea in self.generated_ideas if idea not in self.titles)
            save_session(self.titles, self.jobs)
        if not self.titles:
            messagebox.showinfo("Автоконвейер", "Сначала вручную сгенерируйте идеи и передайте нужные в «Новости».", parent=self.root)
            return
        self.auto_pipeline_active = True
        self.settings.auto_montage_enabled = True
        save_settings(self.settings)
        self._show_page("scenarios")
        self.system_status.config(text="Автоконвейер: создаём сценарии…")
        self.root.after(80, self._start)

    def _transfer_completed_to_next_steps(self):
        completed = [job for job in self.jobs if job.state == RunState.DONE]
        cover_titles = {item.get("title") for item in self.cover_items}
        seo_titles = {item.get("source_title") for item in self.seo_items}
        for job in completed:
            if job.request.title not in cover_titles:
                self.cover_items.append({"title": job.request.title, "script": job.result,
                                         "status": "Ожидает", "path": "", "error": ""})
            if job.request.title not in seo_titles:
                self.seo_items.append({"source_title": job.request.title, "script": job.result,
                                       "status": "Ожидает", "title": "", "description": "", "tags": [], "error": ""})
        self._save_cover_queue()

    def _page_scenarios(self):
        toolbar = tk.Frame(self.page, bg=BG)
        toolbar.pack(fill="x", pady=(4, 14))
        self._button(toolbar, "⇧  Добавить TXT", self._choose_txt, "primary").pack(side="left")
        self.start_button = self._button(toolbar, "▷  Запустить всё", self._start, "success")
        self.start_button.pack(side="left", padx=9)
        self.pause_button = self._button(toolbar, "Ⅱ  Пауза", self._toggle_pause)
        self.pause_button.pack(side="left")
        self.stop_button = self._button(toolbar, "□  Стоп всё", self._stop_all, "danger")
        self.stop_button.pack(side="left", padx=9)
        self._button(toolbar, "↻  Повторить ошибки", self._retry_errors).pack(side="left")
        self._button(toolbar, "Перезапустить выбранные", self._rerun_selected).pack(side="left", padx=9)

        managebar = tk.Frame(self.page, bg=BG)
        managebar.pack(fill="x", pady=(0, 10))
        self._button(managebar, "⌫  Удалить выбранные", self._delete_selected).pack(side="left")
        self._button(managebar, "✎  Изменить тему", self._edit_selected_title).pack(side="left", padx=(9, 0))
        self._button(managebar, "🗑  Очистить всё", self._clear_all, "danger").pack(side="left", padx=9)
        tk.Label(managebar, text="Ctrl — выбрать несколько   •   Ctrl+A — выбрать все   •   Delete — удалить",
                 bg=BG, fg=MUTED, font=("Segoe UI", 8)).pack(side="left", padx=10)

        transferbar = tk.Frame(self.page, bg=BG)
        transferbar.pack(fill="x", pady=(0, 10))
        tk.Label(transferbar, text="ПЕРЕДАТЬ ГОТОВЫЕ:", bg=BG, fg=MUTED,
                 font=("Segoe UI Semibold", 8)).pack(side="left", padx=(0, 8))
        tk.Label(transferbar, text="Готовые новости передаются вручную в следующий модуль; исходные данные остаются доступны для проверки.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(side="left")
        self._button(transferbar, "В обложки", self._transfer_to_covers).pack(side="left", padx=8)
        self._button(transferbar, "В SEO-пакеты", self._transfer_to_seo).pack(side="left", padx=8)
        self._button(transferbar, "В озвучку", lambda: self._show_page("voice_create"), "primary").pack(side="left", padx=8)

        summary = self._card(self.page, fill="x", pady=(0, 14))
        tk.Label(summary, text="Параметры запуска", bg=CARD, fg=TEXT,
                 font=("Segoe UI Semibold", 11)).pack(side="left", padx=18, pady=14)
        active_count = len(self.settings.active_sessions)
        self.active_key_label = tk.Label(summary, text=f"Активных сессий: {active_count}", bg=CARD, fg=MUTED,
                                         font=("Segoe UI", 9))
        self.active_key_label.pack(side="right", padx=18)
        tk.Label(summary, text=f"Параллельно: {active_count}", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="right", padx=18)

        table_card = self._card(self.page, fill="both", expand=True)
        columns = ("num", "title", "status", "detail")
        self.table = ttk.Treeview(table_card, columns=columns, show="headings", selectmode="extended")
        for key, label in (("num", "#"), ("title", "СЦЕНАРИЙ"), ("status", "СТАТУС"), ("detail", "РЕЗУЛЬТАТ")):
            self.table.heading(key, text=label)
        self.table.column("num", width=48, anchor="center", stretch=False)
        self.table.column("title", width=390)
        self.table.column("status", width=135, anchor="center", stretch=False)
        self.table.column("detail", width=310)
        self.table.pack(fill="both", expand=True, padx=1, pady=1)
        self.table.tag_configure("done", foreground="#35D99A")
        self.table.tag_configure("error", foreground="#FF7184")
        self.table.tag_configure("paused", foreground="#FFD166")
        self.table.bind("<Double-1>", self._show_result)
        self.table.bind("<Delete>", lambda _: self._delete_selected())
        self.table.bind("<Control-a>", self._select_all)
        if DND_FILES:
            self.table.drop_target_register(DND_FILES)
            self.table.dnd_bind("<<Drop>>", self._drop_file)
        self._populate_titles()
        if not self.titles:
            self.table.insert("", "end", iid="empty", values=("", "Перетащите TXT-файл сюда или нажмите «Добавить TXT»", "", ""))

        footer = tk.Frame(self.page, bg=BG)
        footer.pack(fill="x", pady=10)
        self.progress = ttk.Progressbar(footer, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True)
        self.run_status = tk.Label(footer, text="Готово к запуску", bg=BG, fg=MUTED,
                                   font=("Segoe UI", 9))
        self.run_status.pack(side="right", padx=(16, 0))

    def _page_templates(self):
        library = self._card(self.page, fill="x", pady=(4, 10))
        library_row = tk.Frame(library, bg=CARD, padx=18, pady=12)
        library_row.pack(fill="x")
        tk.Label(library_row, text="НИША ДЛЯ ШАБЛОНОВ", bg=CARD, fg=MUTED,
                 font=("Segoe UI Semibold", 8)).pack(side="left", padx=(0, 10))
        self.template_topic_combo = ttk.Combobox(library_row, state="readonly", style="Dark.TCombobox",
                                                 values=self.settings.idea_topics, width=45)
        self.template_topic_combo.pack(side="left", fill="x", expand=True, ipady=6)
        if self.settings.idea_topics:
            self.template_topic_combo.current(0)
        self.template_topic_combo.bind("<<ComboboxSelected>>", self._on_template_topic_changed)
        self._button(library_row, "Управление нишами…", self._manage_idea_topics).pack(side="left", padx=(10, 0))

        general = self._card(self.page, fill="x", pady=(4, 14))
        head = tk.Frame(general, bg=CARD)
        head.pack(fill="x", padx=20, pady=(17, 8))
        tk.Label(head, text="Общий шаблон", bg=CARD, fg=TEXT,
                 font=("Segoe UI Semibold", 12)).pack(side="left")
        tk.Label(head, text="Используйте {title} для названия сценария", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="right")
        self._button(head, "⇧ TXT", lambda: self._choose_text_for_widget(self.template_widget, True)).pack(side="right", padx=(0, 12))
        template_library = tk.Frame(general, bg=CARD_2, highlightbackground=BORDER, highlightthickness=1)
        template_library.pack(fill="x", padx=20, pady=(0, 8))
        tk.Label(template_library, text="ШАБЛОНЫ ОСНОВНОГО ПРОМПТА", bg=CARD_2, fg=MUTED,
                 font=("Segoe UI Semibold", 8)).pack(side="left", padx=(12, 8), pady=9)
        self.scenario_template_combo = ttk.Combobox(template_library, state="readonly", style="Dark.TCombobox", width=28)
        self.scenario_template_combo.pack(side="left", fill="x", expand=True, ipady=5, pady=6)
        self._button(template_library, "Применить", self._apply_scenario_template).pack(side="left", padx=7, pady=5)
        self._button(template_library, "Сохранить текущий", self._save_scenario_template, "primary").pack(side="left", pady=5)
        self._button(template_library, "Удалить", self._delete_scenario_template, "danger").pack(side="left", padx=7, pady=5)
        self.template_widget = tk.Text(
            general, height=5, bg=CARD_2, fg=TEXT, insertbackground=TEXT, relief="flat",
            padx=13, pady=12, wrap="word", font=("Segoe UI", 10),
            highlightbackground=BORDER, highlightthickness=1,
        )
        self.template_widget.pack(fill="x", padx=20, pady=(0, 20))
        self.template_widget.insert("1.0", self.settings.template)
        self._install_edit_bindings(self.template_widget, multiline=True)
        self._enable_drop_group(general, self.template_widget, multiline=True)

        ranges_card = self._card(self.page, fill="both", expand=True)
        range_head = tk.Frame(ranges_card, bg=CARD)
        range_head.pack(fill="x", padx=20, pady=16)
        tk.Label(range_head, text="Дополнительные промпты по диапазонам", bg=CARD, fg=TEXT,
                 font=("Segoe UI Semibold", 12)).pack(side="left")
        self._button(range_head, "+ Добавить диапазон", self._add_range, "primary").pack(side="right")
        range_library = tk.Frame(ranges_card, bg=CARD_2, highlightbackground=BORDER, highlightthickness=1)
        range_library.pack(fill="x", padx=20, pady=(0, 10))
        tk.Label(range_library, text="ШАБЛОНЫ ДИАПАЗОНОВ", bg=CARD_2, fg=MUTED,
                 font=("Segoe UI Semibold", 8)).pack(side="left", padx=(12, 8), pady=9)
        self.range_template_combo = ttk.Combobox(range_library, state="readonly", style="Dark.TCombobox", width=28)
        self.range_template_combo.pack(side="left", fill="x", expand=True, ipady=5, pady=6)
        self._button(range_library, "Применить", self._apply_range_template).pack(side="left", padx=7, pady=5)
        self._button(range_library, "Сохранить набор", self._save_range_template, "primary").pack(side="left", pady=5)
        self._button(range_library, "Удалить", self._delete_range_template, "danger").pack(side="left", padx=7, pady=5)
        self.ranges_frame = tk.Frame(ranges_card, bg=CARD)
        self.ranges_frame.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        for item in self.settings.prompt_ranges:
            self._add_range(item.get("start", 1), item.get("end", 5), item.get("prompt", ""))
        savebar = tk.Frame(ranges_card, bg=CARD)
        savebar.pack(fill="x", padx=20, pady=(0, 18))
        self._button(savebar, "✓  Сохранить шаблоны", self._save_templates, "primary").pack(side="right")
        self._refresh_template_libraries()
        if self.scenario_templates_view:
            self._apply_scenario_template()
        if self.range_templates_view:
            self._apply_range_template()

    def _template_topic(self):
        return self.template_topic_combo.get().strip() if hasattr(self, "template_topic_combo") else ""

    def _refresh_template_libraries(self):
        topic = self._template_topic()
        self.scenario_templates_view = [item for item in self.settings.scenario_templates if item.get("topic") == topic]
        self.range_templates_view = [item for item in self.settings.range_templates if item.get("topic") == topic]
        if hasattr(self, "scenario_template_combo") and self.scenario_template_combo.winfo_exists():
            self.scenario_template_combo.configure(values=[item.get("name", "Шаблон") for item in self.scenario_templates_view])
            self.scenario_template_combo.current(0) if self.scenario_templates_view else self.scenario_template_combo.set("")
        if hasattr(self, "range_template_combo") and self.range_template_combo.winfo_exists():
            self.range_template_combo.configure(values=[item.get("name", "Набор") for item in self.range_templates_view])
            self.range_template_combo.current(0) if self.range_templates_view else self.range_template_combo.set("")

    def _on_template_topic_changed(self, _=None):
        self._refresh_template_libraries()
        self.template_widget.delete("1.0", "end")
        if self.scenario_templates_view:
            self.template_widget.insert("1.0", self.scenario_templates_view[0].get("template", ""))
        if self.range_templates_view:
            self._load_range_items(self.range_templates_view[0].get("ranges", []))
        else:
            self._load_range_items([])

    def _save_scenario_template(self):
        topic = self._template_topic()
        template = self.template_widget.get("1.0", "end-1c").strip()
        if not topic or not template:
            messagebox.showerror("Шаблоны", "Выберите нишу и заполните основной промпт", parent=self.root)
            return
        name = self._ask_text("Сохранить шаблон", "Название шаблона основного промпта:")
        if not name or not name.strip():
            return
        name = name.strip()
        existing = next((item for item in self.settings.scenario_templates
                         if item.get("topic") == topic and item.get("name", "").casefold() == name.casefold()), None)
        if existing:
            existing["template"] = template
        else:
            self.settings.scenario_templates.append({"name": name, "topic": topic, "template": template})
        save_settings(self.settings)
        self._refresh_template_libraries()
        self.scenario_template_combo.current([item.get("name") for item in self.scenario_templates_view].index(name))

    def _apply_scenario_template(self):
        index = self.scenario_template_combo.current()
        if 0 <= index < len(self.scenario_templates_view):
            self.template_widget.delete("1.0", "end")
            self.template_widget.insert("1.0", self.scenario_templates_view[index].get("template", ""))

    def _delete_scenario_template(self):
        index = self.scenario_template_combo.current()
        if not 0 <= index < len(self.scenario_templates_view):
            return
        item = self.scenario_templates_view[index]
        if messagebox.askyesno("Удаление", f"Удалить шаблон «{item.get('name', 'Шаблон')}»?", parent=self.root):
            self.settings.scenario_templates.remove(item)
            save_settings(self.settings)
            self._refresh_template_libraries()

    def _current_range_items(self):
        return [{"start": int(start.get()), "end": int(end.get()), "prompt": prompt.get().strip()}
                for _, start, end, prompt in self.range_rows]

    def _load_range_items(self, items):
        for row, *_ in self.range_rows:
            row.destroy()
        self.range_rows = []
        for item in items:
            self._add_range(item.get("start", 1), item.get("end", 5), item.get("prompt", ""))

    def _save_range_template(self):
        topic = self._template_topic()
        try:
            ranges = self._current_range_items()
        except ValueError:
            messagebox.showerror("Шаблоны диапазонов", "Начало и конец диапазона должны быть числами", parent=self.root)
            return
        if not topic or not ranges:
            messagebox.showerror("Шаблоны диапазонов", "Выберите нишу и добавьте хотя бы один диапазон", parent=self.root)
            return
        name = self._ask_text("Сохранить набор диапазонов", "Название набора дополнительных промптов:")
        if not name or not name.strip():
            return
        name = name.strip()
        existing = next((item for item in self.settings.range_templates
                         if item.get("topic") == topic and item.get("name", "").casefold() == name.casefold()), None)
        if existing:
            existing["ranges"] = ranges
        else:
            self.settings.range_templates.append({"name": name, "topic": topic, "ranges": ranges})
        save_settings(self.settings)
        self._refresh_template_libraries()
        self.range_template_combo.current([item.get("name") for item in self.range_templates_view].index(name))

    def _apply_range_template(self):
        index = self.range_template_combo.current()
        if 0 <= index < len(self.range_templates_view):
            self._load_range_items(self.range_templates_view[index].get("ranges", []))

    def _delete_range_template(self):
        index = self.range_template_combo.current()
        if not 0 <= index < len(self.range_templates_view):
            return
        item = self.range_templates_view[index]
        if messagebox.askyesno("Удаление", f"Удалить набор «{item.get('name', 'Набор')}»?", parent=self.root):
            self.settings.range_templates.remove(item)
            save_settings(self.settings)
            self._refresh_template_libraries()

    def _add_range(self, start=1, end=5, prompt=""):
        row = tk.Frame(self.ranges_frame, bg=CARD_2, highlightbackground=BORDER, highlightthickness=1)
        row.pack(fill="x", pady=5)
        tk.Label(row, text="Сценарии", bg=CARD_2, fg=MUTED, font=("Segoe UI", 9)).pack(side="left", padx=(14, 8), pady=12)
        start_entry = self._entry(row, width=5); start_entry.insert(0, str(start)); start_entry.pack(side="left", ipady=6)
        tk.Label(row, text="—", bg=CARD_2, fg=MUTED).pack(side="left", padx=7)
        end_entry = self._entry(row, width=5); end_entry.insert(0, str(end)); end_entry.pack(side="left", ipady=6)
        prompt_entry = self._entry(row); prompt_entry.insert(0, prompt)
        prompt_entry.pack(side="left", fill="x", expand=True, padx=12, ipady=6)
        self._button(row, "×", lambda: self._remove_range(row), "danger").pack(side="right", padx=(0, 10), pady=6)
        self._button(row, "TXT", lambda: self._choose_text_for_widget(prompt_entry, False)).pack(side="right", pady=6)
        self._enable_drop_group(row, prompt_entry, multiline=False)
        self.range_rows.append((row, start_entry, end_entry, prompt_entry))

    def _remove_range(self, row):
        self.range_rows = [item for item in self.range_rows if item[0] is not row]
        row.destroy()

    def _sync_template_settings(self):
        if not hasattr(self, "template_widget") or not self.template_widget.winfo_exists():
            return
        try:
            ranges = []
            for _, start, end, prompt in self.range_rows:
                ranges.append({"start": int(start.get()), "end": int(end.get()), "prompt": prompt.get()})
            self.settings.template = self.template_widget.get("1.0", "end").strip()
            self.settings.prompt_ranges = ranges
        except (ValueError, tk.TclError):
            pass

    def _save_templates(self):
        try:
            ranges = self._get_ranges_from_widgets()
            self.settings.template = self.template_widget.get("1.0", "end").strip()
            self.settings.prompt_ranges = [
                {"start": item.start, "end": item.end, "prompt": item.prompt} for item in ranges
            ]
            save_settings(self.settings)
            messagebox.showinfo("Шаблоны", "Настройки шаблонов сохранены", parent=self.root)
        except Exception as exc:
            messagebox.showerror("Шаблоны", str(exc), parent=self.root)

    def _get_ranges_from_widgets(self):
        return [PromptRange(int(start.get()), int(end.get()), prompt.get()) for _, start, end, prompt in self.range_rows]

    def _page_ideas(self):
        controls = self._card(self.page, fill="x", pady=(4, 14))
        top = tk.Frame(controls, bg=CARD, padx=20, pady=17)
        top.pack(fill="x")
        tk.Label(top, text="Новостные направления", bg=CARD, fg=TEXT,
                 font=("Segoe UI Semibold", 12)).pack(anchor="w")
        tk.Label(top, text="Выберите направление — Claude предложит проверяемые углы подачи для новостных роликов",
                 bg=CARD, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", pady=(3, 12))

        # The ideas screen used to be one long form.  It is now divided into
        # short working tabs so the operator sees only the settings needed at
        # the current step.
        style = ttk.Style(self.root)
        style.configure("Studio.TNotebook", background=CARD, borderwidth=0)
        style.configure("Studio.TNotebook.Tab", background=CARD_2, foreground=MUTED,
                        padding=(17, 9), font=("Segoe UI Semibold", 9))
        style.map("Studio.TNotebook.Tab", background=[("selected", ACTIVE)],
                  foreground=[("selected", TEXT)])
        self.idea_tabs = ttk.Notebook(controls, style="Studio.TNotebook")
        self.idea_tab_directions = tk.Frame(self.idea_tabs, bg=CARD, padx=2, pady=4)
        self.idea_tab_ai = tk.Frame(self.idea_tabs, bg=CARD, padx=2, pady=4)
        self.idea_tabs.add(self.idea_tab_directions, text="  1. Направления  ")
        self.idea_tabs.add(self.idea_tab_ai, text="  2. Настройки ИИ и промпты  ")
        self.idea_tabs.pack(fill="x", padx=20, pady=(0, 12))
        directions = self.idea_tab_directions
        ai_settings = self.idea_tab_ai

        plan_head = tk.Frame(directions, bg=CARD_2, padx=12, pady=10, highlightbackground=BORDER, highlightthickness=1)
        plan_head.pack(fill="x", pady=(0, 12))
        tk.Label(plan_head, text="ПЛАН ВЫПУСКА", bg=CARD_2, fg=TEXT,
                 font=("Segoe UI Semibold", 10)).pack(side="left")
        tk.Label(plan_head, text="Всего роликов", bg=CARD_2, fg=MUTED, font=("Segoe UI", 9)).pack(side="left", padx=(18, 5))
        self.idea_target_entry = self._entry(plan_head, width=7)
        self.idea_target_entry.insert(0, str(self.settings.idea_target_count))
        self.idea_target_entry.pack(side="left", ipady=5)
        self.idea_target_entry.bind("<Return>", lambda _: self._save_idea_target())
        self.idea_target_entry.bind("<FocusOut>", lambda _: self._save_idea_target())
        self.idea_target_link_var = tk.BooleanVar(value=self.settings.idea_target_follows_pipeline)
        self.idea_target_link = tk.Checkbutton(
            plan_head, text="Связать с целью конвейера", variable=self.idea_target_link_var,
            command=self._toggle_idea_target_link, bg=CARD_2, fg=MUTED,
            activebackground=CARD_2, activeforeground=TEXT, selectcolor=CARD,
            font=("Segoe UI", 9), relief="flat", bd=0, cursor="hand2",
        )
        self.idea_target_link.pack(side="left", padx=(12, 0))
        self.idea_plan_summary = tk.Label(plan_head, text="", bg=CARD_2, fg=MUTED, font=("Segoe UI", 9))
        self.idea_plan_summary.pack(side="left", padx=12)
        self._update_idea_target_link_ui()

        # Keep the combobox as the single source of the selected value for the
        # existing planning code, but do not display it.  Selection happens in
        # the much clearer grid below.
        self.idea_topic_entry = ttk.Combobox(directions, values=self.settings.idea_topics, style="Dark.TCombobox")
        if self.settings.idea_topics:
            self.idea_topic_entry.set(self.settings.idea_topics[0])

        topics_card = tk.Frame(directions, bg=CARD_2, padx=12, pady=11, highlightbackground=BORDER, highlightthickness=1)
        topics_card.pack(fill="x", pady=(0, 12))
        topics_head = tk.Frame(topics_card, bg=CARD_2)
        topics_head.pack(fill="x", pady=(0, 8))
        tk.Label(topics_head, text="ВЫБЕРИТЕ НАПРАВЛЕНИЕ", bg=CARD_2, fg=TEXT,
                 font=("Segoe UI Semibold", 10)).pack(side="left")
        self.idea_topics_selection_label = tk.Label(topics_head, text="Клик — одна тема · Ctrl + клик — несколько", bg=CARD_2, fg=MUTED,
                                                     font=("Segoe UI", 8))
        self.idea_topics_selection_label.pack(side="left", padx=10)
        self._button(topics_head, "Управление", self._manage_idea_topics).pack(side="right")
        self.idea_suggest_button = self._button(topics_head, "✦ ИИ предложит", self._suggest_idea_directions, "success")
        self.idea_suggest_button.pack(side="right", padx=6)
        self._button(topics_head, "+ Свое направление", self._add_custom_idea_direction, "primary").pack(side="right", padx=6)
        self.idea_topic_grid = tk.Frame(topics_card, bg=CARD_2)
        self.idea_topic_grid.pack(fill="x")
        self._render_idea_topic_grid()

        fields = tk.Frame(directions, bg=CARD)
        fields.pack(fill="x")
        topic_box = tk.Frame(fields, bg=CARD)
        topic_box.pack(side="left", fill="x", expand=True)
        tk.Label(topic_box, text="ВЫБРАННОЕ НАПРАВЛЕНИЕ", bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 8)).pack(anchor="w")
        self.idea_selected_topic = tk.Label(topic_box, text=self.idea_topic_entry.get(), bg=CARD_2, fg=TEXT,
                                             anchor="w", padx=12, pady=9, font=("Segoe UI Semibold", 10),
                                             highlightbackground=BORDER, highlightthickness=1)
        self.idea_selected_topic.pack(fill="x", pady=(5, 0))
        topic_actions = tk.Frame(topic_box, bg=CARD)
        topic_actions.pack(fill="x", pady=(7, 0))
        self._button(topic_actions, "+ В план", self._add_current_idea_to_plan, "primary").pack(side="left")
        self.idea_add_selected_topics_button = self._button(topic_actions, "Добавить все выбранные", self._add_selected_idea_topics_to_plan, "success")
        self.idea_add_selected_topics_button.pack(side="left", padx=7)

        language_box = tk.Frame(fields, bg=CARD)
        language_box.pack(side="left", padx=(12, 0))
        tk.Label(language_box, text="ЯЗЫК", bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 8)).pack(anchor="w")
        self.idea_language = ttk.Combobox(language_box, state="readonly", width=15, style="Dark.TCombobox",
                                           values=("Русский", "Немецкий", "Английский", "Испанский"))
        self.idea_language.set("Русский")
        self.idea_language.pack(ipady=7, pady=(5, 0))

        count_box = tk.Frame(fields, bg=CARD)
        count_box.pack(side="left", padx=(12, 0))
        tk.Label(count_box, text="КОЛИЧЕСТВО", bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 8)).pack(anchor="w")
        self.idea_count_entry = self._entry(count_box, width=8)
        self.idea_count_entry.insert(0, "5")
        self.idea_count_entry.pack(ipady=8, pady=(5, 0))

        plan = tk.Frame(directions, bg=CARD_2, highlightbackground=BORDER, highlightthickness=1)
        plan.pack(fill="x", pady=(12, 0))
        tk.Label(plan, text="НАПРАВЛЕНИЯ В ВЫПУСКЕ", bg=CARD_2, fg=MUTED,
                 font=("Segoe UI Semibold", 8)).pack(anchor="w", padx=12, pady=(9, 4))
        self.idea_plan_tree = ttk.Treeview(plan, columns=("topic", "count", "provider", "route"), show="headings", height=5)
        for key, label, width in (("topic", "НАПРАВЛЕНИЕ", 430), ("count", "ИДЕЙ", 65),
                                  ("provider", "ПРОВАЙДЕР", 135), ("route", "ПРОФИЛЬ / ЧАТ", 280)):
            self.idea_plan_tree.heading(key, text=label)
            self.idea_plan_tree.column(key, width=width, anchor="w")
        self.idea_plan_tree.pack(fill="x", padx=12, pady=(0, 7))
        self.idea_plan_tree.bind("<Double-1>", self._edit_idea_plan_item)
        plan_actions = tk.Frame(plan, bg=CARD_2)
        plan_actions.pack(fill="x", padx=12, pady=(0, 9))
        self._button(plan_actions, "Изменить количество", self._edit_idea_plan_item).pack(side="left")
        self._button(plan_actions, "Убрать из плана", self._remove_idea_plan_item, "danger").pack(side="left", padx=7)
        self._render_idea_plan()

        route = tk.Frame(ai_settings, bg=CARD_2, highlightbackground=BORDER, highlightthickness=1)
        route.pack(fill="x", pady=(12, 0))
        preset_row = tk.Frame(route, bg=CARD_2)
        preset_row.pack(fill="x", padx=12, pady=(10, 5))
        tk.Label(preset_row, text="СОХРАНЁННЫЙ ПРЕСЕТ", bg=CARD_2, fg=MUTED,
                 font=("Segoe UI Semibold", 8)).pack(side="left", padx=(0, 8))
        self.idea_route_preset_combo = ttk.Combobox(preset_row, state="readonly", style="Dark.TCombobox", width=34)
        self.idea_route_preset_combo.pack(side="left", ipady=5)
        self._button(preset_row, "Применить", self._apply_idea_route_preset).pack(side="left", padx=7)
        self._button(preset_row, "Сохранить как…", self._save_idea_route_preset, "primary").pack(side="left")
        self._button(preset_row, "Удалить", self._delete_idea_route_preset, "danger").pack(side="left", padx=7)

        route_main = tk.Frame(route, bg=CARD_2)
        route_main.pack(fill="x", padx=12, pady=(2, 10))
        tk.Label(route_main, text="ПРОВАЙДЕР, ПРОФИЛЬ И ЧАТ ДЛЯ ВЫБРАННОГО НАПРАВЛЕНИЯ", bg=CARD_2, fg=MUTED,
                 font=("Segoe UI Semibold", 8)).pack(side="left", padx=(0, 8), pady=4)
        self.idea_provider_combo = ttk.Combobox(route_main, state="readonly", style="Dark.TCombobox", width=21,
            values=("Claude — Chrome-чат", "OpenAI — API"))
        self.idea_provider_combo.current(0)
        self.idea_provider_combo.pack(side="left", ipady=6, pady=4)
        self.idea_provider_combo.bind("<<ComboboxSelected>>", self._on_idea_provider_changed)
        self.idea_session_entries = self._sessions_for("ideas")
        self.idea_session_combo = ttk.Combobox(route_main, state="readonly", style="Dark.TCombobox", width=24,
            values=[f"{index + 1}. {item.label}" for index, item in enumerate(self.idea_session_entries)])
        self.idea_session_combo.pack(side="left", ipady=6, pady=4)
        if self.idea_session_entries:
            self.idea_session_combo.current(0)
        self.idea_chat_entry = self._entry(route_main)
        self.idea_chat_entry.pack(side="left", fill="x", expand=True, padx=8, ipady=7, pady=4)
        self.idea_chat_entry.insert(0, "https://claude.ai/new")
        self._button(route_main, "Открыть чат", self._open_idea_chat).pack(side="left", pady=4)
        self._button(route_main, "Сохранить для направления", self._save_idea_chat_binding, "primary").pack(side="left", padx=7, pady=4)
        self._refresh_idea_route_presets()

        detail_row = tk.Frame(ai_settings, bg=CARD)
        detail_row.pack(fill="x", pady=(14, 0))
        tk.Label(detail_row, text="ДОПОЛНИТЕЛЬНЫЕ ТРЕБОВАНИЯ", bg=CARD, fg=MUTED,
                 font=("Segoe UI Semibold", 8)).pack(anchor="w")
        self.idea_requirements = tk.Text(detail_row, height=3, bg=CARD_2, fg=TEXT, insertbackground=TEXT,
                                         relief="flat", padx=12, pady=10, wrap="word", font=("Segoe UI", 9),
                                         highlightbackground=BORDER, highlightthickness=1)
        self.idea_requirements.pack(fill="x", pady=(5, 0))
        self.idea_requirements.insert(
            "1.0",
            "Предложи разные актуальные углы подачи. Не выдумывай факты, даты, цифры и цитаты; "
            "каждая идея должна быть пригодна для проверки по источникам.",
        )
        self._install_edit_bindings(self.idea_requirements, multiline=True)

        custom = tk.Frame(ai_settings, bg=CARD_2, highlightbackground=BORDER, highlightthickness=1)
        custom.pack(fill="x", pady=(12, 0))
        self.idea_include_custom_var = tk.BooleanVar(value=self.settings.idea_include_custom)
        tk.Checkbutton(custom, text="Добавить мои идеи в общий результат", variable=self.idea_include_custom_var,
                       bg=CARD_2, fg=TEXT, activebackground=CARD_2, activeforeground=TEXT,
                       selectcolor=ACTIVE, font=("Segoe UI Semibold", 9)).pack(anchor="w", padx=12, pady=(9, 2))
        self.idea_custom_text = tk.Text(custom, height=3, bg=CARD_2, fg=TEXT, insertbackground=TEXT,
                                        relief="flat", wrap="word", font=("Segoe UI", 9), padx=10, pady=7)
        self.idea_custom_text.pack(fill="x", padx=8, pady=(0, 8))
        self.idea_custom_text.insert("1.0", self.settings.idea_custom_text)
        self._install_edit_bindings(self.idea_custom_text, multiline=True)

        prompts = tk.Frame(ai_settings, bg=CARD_2, highlightbackground=BORDER, highlightthickness=1)
        prompts.pack(fill="x", pady=(12, 0))
        tk.Label(prompts, text="СОХРАНЁННЫЕ ПРОМПТЫ", bg=CARD_2, fg=MUTED,
                 font=("Segoe UI Semibold", 8)).pack(side="left", padx=(12, 8), pady=10)
        current_topic = self.idea_topic_entry.get().strip()
        migrated = False
        for item in self.settings.idea_prompts:
            if not item.get("topic"):
                item["topic"] = current_topic
                migrated = True
        if migrated:
            save_settings(self.settings)
        self.idea_prompts_view = [item for item in self.settings.idea_prompts if item.get("topic") == current_topic]
        self.idea_prompt_combo = ttk.Combobox(prompts, state="readonly", width=30, style="Dark.TCombobox",
                                              values=[item.get("name", "Промпт") for item in self.idea_prompts_view])
        self.idea_prompt_combo.pack(side="left", fill="x", expand=True, ipady=6, pady=7)
        if self.idea_prompts_view:
            self.idea_prompt_combo.current(0)
            self.idea_requirements.delete("1.0", "end")
            self.idea_requirements.insert("1.0", self.idea_prompts_view[0].get("prompt", ""))
        self._button(prompts, "Применить", self._apply_saved_idea_prompt).pack(side="left", padx=7, pady=6)
        self._button(prompts, "Загрузить TXT", self._load_idea_prompt_txt).pack(side="left", pady=6)
        self._button(prompts, "Сохранить текущий", self._save_current_idea_prompt, "primary").pack(side="left", pady=6)
        self._button(prompts, "Удалить", self._delete_saved_idea_prompt, "danger").pack(side="left", padx=7, pady=6)

        actionbar = tk.Frame(controls, bg=CARD, padx=20, pady=0)
        actionbar.pack(fill="x", pady=(0, 16))
        self.idea_generate_button = self._button(actionbar, "✦  Сгенерировать план", self._generate_ideas, "primary")
        self.idea_generate_button.pack(side="left")
        self.auto_montage_var = tk.BooleanVar(value=self.settings.auto_montage_enabled)
        tk.Checkbutton(actionbar, text="Автомонтаж: переходить по цепочке", variable=self.auto_montage_var,
                       bg=CARD, fg=TEXT, activebackground=CARD, activeforeground=TEXT, selectcolor=ACTIVE,
                       font=("Segoe UI", 9)).pack(side="left", padx=12)
        tk.Label(actionbar, text="Claude перебирает активные сессии при лимите, затем использует OpenAI API",
                 bg=CARD, fg=MUTED, font=("Segoe UI", 8)).pack(side="left")

        results = self._card(self.page, fill="both", expand=True)
        head = tk.Frame(results, bg=CARD)
        head.pack(fill="x", padx=20, pady=(12, 8))
        self.idea_result_title = tk.Label(head, text=f"Найдено идей: {len(self.generated_ideas)}", bg=CARD, fg=TEXT,
                                          font=("Segoe UI Semibold", 11))
        self.idea_result_title.pack(anchor="w")
        idea_actions = tk.Frame(results, bg=CARD)
        idea_actions.pack(fill="x", padx=20, pady=(0, 10))
        self._button(idea_actions, "Редактировать выбранную", self._edit_selected_idea, "primary").pack(side="left")
        self._button(idea_actions, "Добавить выбранные", self._add_selected_ideas).pack(side="left", padx=8)
        self._button(idea_actions, "Добавить все в новости", self._add_all_ideas, "success").pack(side="left")
        self._button(idea_actions, "Сохранить TXT", self._save_ideas_txt).pack(side="right")
        self._button(idea_actions, "Очистить", self._clear_ideas, "danger").pack(side="right", padx=8)

        self.ideas_listbox = tk.Listbox(results, bg=CARD_2, fg=TEXT, selectbackground=ACTIVE,
                                        selectforeground=TEXT, relief="flat", bd=0, selectmode="extended",
                                        highlightthickness=1, highlightbackground=BORDER, font=("Segoe UI", 10))
        self.ideas_listbox.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        self.ideas_listbox.bind("<Double-1>", self._edit_selected_idea)
        self._render_ideas()
        self._load_idea_chat_binding()

    def _ask_text(self, title: str, prompt: str, initial: str = "", secret: bool = False):
        dialog = tk.Toplevel(self.root, bg=BG)
        dialog.title(title)
        dialog.geometry("540x220")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        result = {"value": None}
        panel = tk.Frame(dialog, bg=CARD, padx=22, pady=20, highlightbackground=BORDER, highlightthickness=1)
        panel.pack(fill="both", expand=True, padx=16, pady=16)
        tk.Label(panel, text=title, bg=CARD, fg=TEXT, font=("Segoe UI Semibold", 14)).pack(anchor="w")
        tk.Label(panel, text=prompt, bg=CARD, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(8, 6))
        entry = self._entry(panel, show="•" if secret else "")
        entry.insert(0, initial)
        entry.pack(fill="x", ipady=8)
        entry.focus_set()
        entry.selection_range(0, "end")

        def accept():
            result["value"] = entry.get()
            dialog.destroy()

        buttons = tk.Frame(panel, bg=CARD)
        buttons.pack(fill="x", pady=(14, 0))
        self._button(buttons, "Отмена", dialog.destroy).pack(side="right")
        self._button(buttons, "Сохранить", accept, "primary").pack(side="right", padx=8)
        entry.bind("<Return>", lambda _: accept())
        entry.bind("<Escape>", lambda _: dialog.destroy())
        self.root.wait_window(dialog)
        return result["value"]

    def _on_idea_topic_changed(self, _=None):
        topic = self.idea_topic_entry.get().strip()
        if hasattr(self, "idea_selected_topic") and self.idea_selected_topic.winfo_exists():
            self.idea_selected_topic.config(text=topic)
        self._render_idea_topic_grid()
        self.idea_requirements.delete("1.0", "end")
        self._refresh_idea_prompt_combo()
        if self.idea_prompts_view:
            self.idea_prompt_combo.current(0)
            self.idea_requirements.insert("1.0", self.idea_prompts_view[0].get("prompt", ""))
        self._load_idea_chat_binding()

    def _render_idea_topic_grid(self):
        if not hasattr(self, "idea_topic_grid") or not self.idea_topic_grid.winfo_exists():
            return
        for child in self.idea_topic_grid.winfo_children():
            child.destroy()
        selected = self.idea_topic_entry.get().strip() if hasattr(self, "idea_topic_entry") else ""
        selected_many = getattr(self, "selected_idea_topics", set())
        if hasattr(self, "idea_topics_selection_label") and self.idea_topics_selection_label.winfo_exists():
            self.idea_topics_selection_label.config(
                text=(f"Выбрано для плана: {len(selected_many)} · Ctrl + клик — добавить/убрать"
                      if selected_many else "Клик — одна тема · Ctrl + клик — несколько"))
        if hasattr(self, "idea_add_selected_topics_button") and self.idea_add_selected_topics_button.winfo_exists():
            self.idea_add_selected_topics_button.config(text=f"Добавить выбранные ({len(selected_many)})")
        columns = 3
        for column in range(columns):
            self.idea_topic_grid.grid_columnconfigure(column, weight=1, uniform="topics")
        for index, topic in enumerate(self.settings.idea_topics):
            active = topic == selected
            batch_selected = topic in selected_many
            button = tk.Button(
                self.idea_topic_grid, text=topic, command=lambda value=topic: self._select_idea_topic(value),
                bg=BLUE if active else ("#16456B" if batch_selected else CARD), fg=TEXT, activebackground=BLUE_HOVER,
                activeforeground=TEXT, relief="flat", bd=0, padx=12, pady=9,
                wraplength=220, justify="left", anchor="w", cursor="hand2",
                font=("Segoe UI Semibold" if active or batch_selected else "Segoe UI", 9),
                highlightbackground=BLUE if active else ("#2E7FB7" if batch_selected else BORDER), highlightthickness=1,
            )
            button.grid(row=index // columns, column=index % columns, sticky="nsew", padx=3, pady=3)
            button.bind("<Control-Button-1>", lambda event, value=topic: self._toggle_idea_topic_selection(value))

    def _select_idea_topic(self, topic: str):
        if topic not in self.settings.idea_topics:
            return
        self.selected_idea_topics = {topic}
        self.idea_topic_entry.set(topic)
        self._on_idea_topic_changed()

    def _toggle_idea_topic_selection(self, topic: str):
        if topic not in self.settings.idea_topics:
            return "break"
        if topic in self.selected_idea_topics:
            self.selected_idea_topics.remove(topic)
        else:
            self.selected_idea_topics.add(topic)
            self.idea_topic_entry.set(topic)
        self._on_idea_topic_changed()
        return "break"

    def _suggest_idea_directions(self):
        if getattr(self, "idea_topics_suggesting", False):
            return
        brief = self._ask_text(
            "ИИ предложит направления",
            "Что учитывать? Можно оставить общий запрос для актуальных новостных направлений.",
            "Актуальные международные новости, экономика и технологии",
        )
        if brief is None:
            return
        self.idea_topics_suggesting = True
        if hasattr(self, "idea_suggest_button") and self.idea_suggest_button.winfo_exists():
            self.idea_suggest_button.config(state="disabled", text="ИИ подбирает…")
        self.system_status.config(text="ИИ подбирает направления…")
        prompt = (
            "Предложи 12 коротких направлений для новостных роликов. "
            f"Учитывай: {brief.strip() or 'актуальные мировые новости'}. "
            "Не придумывай факты и конкретные события. Верни только список: одно направление в строке, без нумерации."
        )

        def work():
            try:
                result = asyncio.run(self._text_pool(self._sessions_for("ideas")).generate(prompt))
                topics = []
                for value in self._parse_ideas(result):
                    value = value.strip(" -•\t")
                    if value and value not in topics and len(value) <= 120:
                        topics.append(value)
                self.events.put(("idea_topics_suggested", topics))
            except Exception as exc:
                self.events.put(("idea_topics_suggest_error", str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def _set_idea_target_entry(self, value: int):
        if not hasattr(self, "idea_target_entry") or not self.idea_target_entry.winfo_exists():
            return
        self.idea_target_entry.configure(state="normal")
        self.idea_target_entry.delete(0, "end")
        self.idea_target_entry.insert(0, str(max(1, int(value))))
        if getattr(self, "idea_target_link_var", None) and self.idea_target_link_var.get():
            self.idea_target_entry.configure(state="readonly")

    def _update_idea_target_link_ui(self):
        if not hasattr(self, "idea_target_link_var"):
            return
        linked = bool(self.idea_target_link_var.get())
        if linked:
            self.settings.idea_target_count = self.settings.pipeline_target_count
            self._set_idea_target_entry(self.settings.pipeline_target_count)
        elif hasattr(self, "idea_target_entry") and self.idea_target_entry.winfo_exists():
            self.idea_target_entry.configure(state="normal")
        self.settings.idea_target_follows_pipeline = linked
        if hasattr(self, "idea_plan_summary"):
            self._render_idea_plan()

    def _toggle_idea_target_link(self):
        self._update_idea_target_link_ui()
        save_settings(self.settings)

    def _save_idea_target(self):
        if not hasattr(self, "idea_target_entry") or not self.idea_target_entry.winfo_exists():
            return
        if getattr(self, "idea_target_link_var", None) and self.idea_target_link_var.get():
            self._set_idea_target_entry(self.settings.pipeline_target_count)
            return
        try:
            self.settings.idea_target_count = max(1, int(self.idea_target_entry.get().strip()))
        except ValueError:
            self._set_idea_target_entry(self.settings.idea_target_count)
            return
        self.settings.idea_target_follows_pipeline = False
        save_settings(self.settings)
        self._render_idea_plan()

    def _render_idea_plan(self):
        if not hasattr(self, "idea_plan_tree") or not self.idea_plan_tree.winfo_exists():
            return
        for item in self.idea_plan_tree.get_children():
            self.idea_plan_tree.delete(item)
        total = 0
        for index, item in enumerate(self.settings.idea_plan):
            count = max(1, int(item.get("count", 1)))
            total += count
            provider = "OpenAI API" if item.get("provider") == "openai" else "Claude"
            route = item.get("key_label") if item.get("provider") == "openai" else item.get("chat_url", "https://claude.ai/new")
            self.idea_plan_tree.insert("", "end", iid=str(index), values=(item.get("topic", ""), count, provider, route))
        try:
            target = max(1, int(self.idea_target_entry.get()))
        except Exception:
            target = max(1, int(self.settings.idea_target_count or 100))
        self.idea_plan_summary.config(text=f"В плане: {total} / {target}", fg="#35D99A" if total == target else "#F5C451")

    def _on_idea_provider_changed(self, _=None):
        provider = self.idea_provider_combo.get()
        if provider.startswith("OpenAI"):
            self.idea_openai_entries = [item for item in self.settings.openai_api_keys if item.active and item.secret.strip()]
            self.idea_session_combo.configure(values=[f"{index + 1}. {item.label}" for index, item in enumerate(self.idea_openai_entries)])
            if self.idea_openai_entries:
                self.idea_session_combo.current(0)
            else:
                self.idea_session_combo.set("")
            self.idea_chat_entry.config(state="normal")
            self.idea_chat_entry.delete(0, "end")
            self.idea_chat_entry.insert(0, "OpenAI API: чат-ссылка не нужна; контекст задаёт сохранённый промпт")
            self.idea_chat_entry.config(state="disabled")
        else:
            self.idea_session_entries = self._sessions_for("ideas")
            self.idea_session_combo.configure(values=[f"{index + 1}. {item.label}" for index, item in enumerate(self.idea_session_entries)])
            if self.idea_session_entries:
                self.idea_session_combo.current(0)
            self.idea_chat_entry.config(state="normal")
            if not self.idea_chat_entry.get().startswith("https://claude.ai/"):
                self.idea_chat_entry.delete(0, "end")
                self.idea_chat_entry.insert(0, "https://claude.ai/new")

    def _idea_chat_binding(self):
        topic = self.idea_topic_entry.get().strip()
        return next((item for item in self.settings.idea_chat_bindings if item.get("topic") == topic), None)

    def _refresh_idea_route_presets(self, selected_name: str = ""):
        if not hasattr(self, "idea_route_preset_combo") or not self.idea_route_preset_combo.winfo_exists():
            return
        names = [item.get("name", "Без названия") for item in self.settings.idea_route_presets]
        self.idea_route_preset_combo.configure(values=names)
        if selected_name in names:
            self.idea_route_preset_combo.set(selected_name)
        elif names:
            self.idea_route_preset_combo.current(0)
        else:
            self.idea_route_preset_combo.set("")

    def _save_idea_route_preset(self):
        try:
            route = self._selected_idea_route()
            name = self._ask_text("Сохранить пресет", "Название пресета для профиля и чата:")
            if not name or not name.strip():
                return
            name = name.strip()
            preset = {"name": name, **route}
            existing = next((item for item in self.settings.idea_route_presets if item.get("name") == name), None)
            if existing:
                existing.update(preset)
            else:
                self.settings.idea_route_presets.append(preset)
            save_settings(self.settings)
            self._refresh_idea_route_presets(name)
            self.system_status.config(text=f"Пресет сохранён: {name}")
        except Exception as exc:
            messagebox.showerror("Пресет", str(exc), parent=self.root)

    def _apply_idea_route_preset(self):
        name = self.idea_route_preset_combo.get().strip()
        preset = next((item for item in self.settings.idea_route_presets if item.get("name") == name), None)
        if not preset:
            messagebox.showinfo("Пресет", "Выберите сохранённый пресет", parent=self.root)
            return
        provider = preset.get("provider", "claude")
        self.idea_provider_combo.set("OpenAI — API" if provider == "openai" else "Claude — Chrome-чат")
        self._on_idea_provider_changed()
        key = "key_label" if provider == "openai" else "profile_id"
        wanted = preset.get(key, "")
        for index, entry in enumerate(self.idea_session_entries):
            entry_value = entry.label if provider == "openai" else entry.profile_id
            if entry_value == wanted:
                self.idea_session_combo.current(index)
                break
        if provider == "claude":
            self.idea_chat_entry.delete(0, "end")
            self.idea_chat_entry.insert(0, preset.get("chat_url") or "https://claude.ai/new")
        self.system_status.config(text=f"Применён пресет: {name}")

    def _delete_idea_route_preset(self):
        name = self.idea_route_preset_combo.get().strip()
        if not name:
            return
        if not messagebox.askyesno("Пресет", f"Удалить пресет «{name}»?", parent=self.root):
            return
        self.settings.idea_route_presets = [item for item in self.settings.idea_route_presets if item.get("name") != name]
        save_settings(self.settings)
        self._refresh_idea_route_presets()

    def _load_idea_chat_binding(self):
        if not hasattr(self, "idea_chat_entry") or not self.idea_chat_entry.winfo_exists():
            return
        binding = self._idea_chat_binding()
        provider = binding.get("provider", "claude") if binding else "claude"
        self.idea_provider_combo.set("OpenAI — API" if provider == "openai" else "Claude — Chrome-чат")
        self._on_idea_provider_changed()
        if provider == "openai":
            key_label = binding.get("key_label", "") if binding else ""
            for index, key in enumerate(getattr(self, "idea_openai_entries", [])):
                if key.label == key_label:
                    self.idea_session_combo.current(index)
                    break
            return
        self.idea_chat_entry.delete(0, "end")
        self.idea_chat_entry.insert(0, binding.get("chat_url", "https://claude.ai/new") if binding else "https://claude.ai/new")
        if binding:
            profile_id = binding.get("profile_id")
            for index, session in enumerate(self.idea_session_entries):
                if session.profile_id == profile_id:
                    self.idea_session_combo.current(index)
                    break

    def _selected_idea_session(self):
        index = self.idea_session_combo.current()
        if not 0 <= index < len(self.idea_session_entries):
            raise ValueError("Выберите Chrome-сессию для этой ниши")
        return self.idea_session_entries[index]

    def _selected_idea_route(self):
        if self.idea_provider_combo.get().startswith("OpenAI"):
            index = self.idea_session_combo.current()
            entries = getattr(self, "idea_openai_entries", [])
            if not 0 <= index < len(entries):
                raise ValueError("Добавьте активный OpenAI API-ключ в разделе «API-ключи»")
            return {"provider": "openai", "key_label": entries[index].label, "profile_id": "", "chat_url": ""}
        session = self._selected_idea_session()
        url = self.idea_chat_entry.get().strip() or "https://claude.ai/new"
        if not url.startswith("https://claude.ai/"):
            raise ValueError("Вставьте ссылку на чат с сайта claude.ai")
        return {"provider": "claude", "profile_id": session.profile_id, "chat_url": url, "key_label": ""}

    def _save_idea_chat_binding(self):
        try:
            topic = self.idea_topic_entry.get().strip()
            route = self._selected_idea_route()
            binding = self._idea_chat_binding()
            data = {"topic": topic, **route}
            if binding:
                binding.update(data)
            else:
                self.settings.idea_chat_bindings.append(data)
            save_settings(self.settings)
            messagebox.showinfo("Сессия и чат", "Связь с нишей сохранена", parent=self.root)
        except Exception as exc:
            messagebox.showerror("Сессия и чат", str(exc), parent=self.root)

    def _open_idea_chat(self):
        try:
            if self.idea_provider_combo.get().startswith("OpenAI"):
                raise ValueError("OpenAI API не использует ссылку на обычный чат ChatGPT. Контекст хранится в промпте.")
            session = self._selected_idea_session()
            url = self.idea_chat_entry.get().strip() or "https://claude.ai/new"
            open_login_window(session, url)
        except Exception as exc:
            messagebox.showerror("Сессия и чат", str(exc), parent=self.root)

    def _add_custom_idea_direction(self):
        value = self._ask_text("Новое направление", "Введите новостное направление:")
        if not value or not value.strip():
            return
        value = value.strip()
        if value not in self.settings.idea_topics:
            self.settings.idea_topics.append(value)
        self.idea_topic_entry.configure(values=self.settings.idea_topics)
        self.idea_topic_entry.set(value)
        save_settings(self.settings)
        self._on_idea_topic_changed()

    def _add_current_idea_to_plan(self):
        topic = self.idea_topic_entry.get().strip()
        self._add_idea_topics_to_plan([topic] if topic else [])

    def _add_selected_idea_topics_to_plan(self):
        topics = list(self.selected_idea_topics)
        if not topics:
            topic = self.idea_topic_entry.get().strip()
            topics = [topic] if topic else []
        self._add_idea_topics_to_plan(topics)

    def _add_idea_topics_to_plan(self, topics: list[str]):
        try:
            topics = [topic for topic in topics if topic in self.settings.idea_topics]
            if not topics:
                raise ValueError("Выберите направление")
            count = int(self.idea_count_entry.get().strip())
            if not 1 <= count <= 200:
                raise ValueError("Для одного направления укажите от 1 до 200 идей")
            route = self._selected_idea_route()
            requirements = self.idea_requirements.get("1.0", "end-1c").strip()
            for topic in topics:
                item = {"topic": topic, "count": count, "requirements": requirements, **route}
                existing = next((value for value in self.settings.idea_plan if value.get("topic") == topic), None)
                if existing:
                    existing.update(item)
                else:
                    self.settings.idea_plan.append(item)
            self.settings.idea_target_count = int(self.idea_target_entry.get() or 100)
            self.settings.idea_target_follows_pipeline = bool(
                getattr(self, "idea_target_link_var", tk.BooleanVar(value=False)).get())
            save_settings(self.settings)
            self._render_idea_plan()
            self.system_status.config(text=f"Добавлено направлений в план: {len(topics)}")
        except Exception as exc:
            messagebox.showerror("План выпуска", str(exc), parent=self.root)

    def _edit_idea_plan_item(self, _=None):
        selected = self.idea_plan_tree.selection()
        if not selected:
            return
        index = int(selected[0])
        item = self.settings.idea_plan[index]
        value = self._ask_text("Количество идей", f"Сколько идей для «{item.get('topic', '')}»?", str(item.get("count", 5)))
        if value is None:
            return
        try:
            count = int(value)
            if not 1 <= count <= 200:
                raise ValueError
        except Exception:
            messagebox.showerror("План выпуска", "Укажите число от 1 до 200", parent=self.root)
            return
        item["count"] = count
        save_settings(self.settings)
        self._render_idea_plan()

    def _remove_idea_plan_item(self):
        selected = self.idea_plan_tree.selection()
        if not selected:
            return
        del self.settings.idea_plan[int(selected[0])]
        save_settings(self.settings)
        self._render_idea_plan()

    def _load_idea_prompt_txt(self):
        path = filedialog.askopenfilename(parent=self.root, title="Загрузить промпт", filetypes=[("Текст", "*.txt"), ("Все файлы", "*.*")])
        if not path:
            return
        try:
            self.idea_requirements.delete("1.0", "end")
            self.idea_requirements.insert("1.0", read_text_file(Path(path)))
        except Exception as exc:
            messagebox.showerror("Загрузить промпт", str(exc), parent=self.root)

    def _manage_idea_topics(self):
        dialog = tk.Toplevel(self.root, bg=BG)
        dialog.title("Новостные направления")
        dialog.geometry("680x480")
        dialog.transient(self.root)
        panel = tk.Frame(dialog, bg=CARD, padx=20, pady=18)
        panel.pack(fill="both", expand=True, padx=16, pady=16)
        tk.Label(panel, text="Новостные направления для генерации", bg=CARD, fg=TEXT,
                 font=("Segoe UI Semibold", 14)).pack(anchor="w")
        tk.Label(panel, text="Добавляйте собственные направления и выбирайте нужное двойным щелчком",
                 bg=CARD, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(3, 12))
        topics = tk.Listbox(panel, bg=CARD_2, fg=TEXT, selectbackground=ACTIVE, selectforeground=TEXT,
                            relief="flat", highlightthickness=1, highlightbackground=BORDER,
                            font=("Segoe UI", 10))
        topics.pack(fill="both", expand=True)

        def refresh():
            topics.delete(0, "end")
            for index, value in enumerate(self.settings.idea_topics, 1):
                topics.insert("end", f"{index}.  {value}")

        def add():
            source = self.idea_topic_entry if hasattr(self, "idea_topic_entry") and self.idea_topic_entry.winfo_exists() else self.template_topic_combo
            initial = source.get().strip()
            value = self._ask_text("Новая тема или ниша", "Введите название:", initial)
            if value and value.strip():
                value = value.strip()
                if value not in self.settings.idea_topics:
                    self.settings.idea_topics.append(value)
                    save_settings(self.settings)
                if hasattr(self, "idea_topic_entry") and self.idea_topic_entry.winfo_exists():
                    self.idea_topic_entry.configure(values=self.settings.idea_topics)
                    self.idea_topic_entry.set(value)
                    self._on_idea_topic_changed()
                    self._render_idea_topic_grid()
                if hasattr(self, "template_topic_combo") and self.template_topic_combo.winfo_exists():
                    self.template_topic_combo.configure(values=self.settings.idea_topics)
                    self.template_topic_combo.set(value)
                    self._on_template_topic_changed()
                refresh()

        def remove():
            selected = topics.curselection()
            if not selected:
                return
            value = self.settings.idea_topics[selected[0]]
            if messagebox.askyesno("Удаление", f"Удалить «{value}»?", parent=dialog):
                del self.settings.idea_topics[selected[0]]
                save_settings(self.settings)
                if hasattr(self, "idea_topic_entry") and self.idea_topic_entry.winfo_exists():
                    self.idea_topic_entry.configure(values=self.settings.idea_topics)
                    if self.idea_topic_entry.get() == value:
                        self.idea_topic_entry.set(self.settings.idea_topics[0] if self.settings.idea_topics else "")
                        self._on_idea_topic_changed()
                    self._render_idea_topic_grid()
                if hasattr(self, "template_topic_combo") and self.template_topic_combo.winfo_exists():
                    self.template_topic_combo.configure(values=self.settings.idea_topics)
                refresh()

        def choose(_=None):
            selected = topics.curselection()
            if selected:
                value = self.settings.idea_topics[selected[0]]
                if hasattr(self, "idea_topic_entry") and self.idea_topic_entry.winfo_exists():
                    self.idea_topic_entry.set(value)
                    self._on_idea_topic_changed()
                if hasattr(self, "template_topic_combo") and self.template_topic_combo.winfo_exists():
                    self.template_topic_combo.set(value)
                    self._on_template_topic_changed()
                dialog.destroy()

        refresh()
        topics.bind("<Double-1>", choose)
        actions = tk.Frame(panel, bg=CARD)
        actions.pack(fill="x", pady=(12, 0))
        self._button(actions, "+ Добавить", add, "primary").pack(side="left")
        self._button(actions, "Удалить", remove, "danger").pack(side="left", padx=8)
        self._button(actions, "Выбрать", choose, "success").pack(side="right")

    def _refresh_idea_prompt_combo(self):
        if not hasattr(self, "idea_prompt_combo") or not self.idea_prompt_combo.winfo_exists():
            return
        topic = self.idea_topic_entry.get().strip()
        self.idea_prompts_view = [item for item in self.settings.idea_prompts if item.get("topic") == topic]
        names = [item.get("name", "Промпт") for item in self.idea_prompts_view]
        self.idea_prompt_combo.configure(values=names)
        if names:
            self.idea_prompt_combo.current(0)
        else:
            self.idea_prompt_combo.set("")

    def _apply_saved_idea_prompt(self):
        index = self.idea_prompt_combo.current()
        if index < 0 or index >= len(self.idea_prompts_view):
            messagebox.showinfo("Сохранённые промпты", "Выберите промпт", parent=self.root)
            return
        prompt = self.idea_prompts_view[index].get("prompt", "")
        self.idea_requirements.delete("1.0", "end")
        self.idea_requirements.insert("1.0", prompt)

    def _save_current_idea_prompt(self):
        prompt = self.idea_requirements.get("1.0", "end-1c").strip()
        if not prompt:
            messagebox.showerror("Сохранённые промпты", "Введите требования для генерации", parent=self.root)
            return
        name = self._ask_text("Сохранить промпт", "Название промпта:")
        if not name or not name.strip():
            return
        name = name.strip()
        topic = self.idea_topic_entry.get().strip()
        if not topic:
            messagebox.showerror("Сохранённые промпты", "Сначала выберите тему или нишу", parent=self.root)
            return
        existing = next((item for item in self.settings.idea_prompts
                         if item.get("topic") == topic and item.get("name", "").casefold() == name.casefold()), None)
        if existing:
            if not messagebox.askyesno("Сохранить промпт", f"Заменить сохранённый промпт «{name}»?", parent=self.root):
                return
            existing["prompt"] = prompt
        else:
            self.settings.idea_prompts.append({"name": name, "topic": topic, "prompt": prompt})
        save_settings(self.settings)
        self._refresh_idea_prompt_combo()
        names = [item.get("name", "") for item in self.idea_prompts_view]
        self.idea_prompt_combo.current(names.index(name))

    def _delete_saved_idea_prompt(self):
        index = self.idea_prompt_combo.current()
        if index < 0 or index >= len(self.idea_prompts_view):
            return
        item = self.idea_prompts_view[index]
        name = item.get("name", "Промпт")
        if messagebox.askyesno("Удаление", f"Удалить промпт «{name}»?", parent=self.root):
            self.settings.idea_prompts.remove(item)
            save_settings(self.settings)
            self._refresh_idea_prompt_combo()

    def _ideas_prompt(self, item: dict | None = None) -> str:
        item = item or {
            "topic": self.idea_topic_entry.get().strip(), "count": self.idea_count_entry.get(),
            "requirements": self.idea_requirements.get("1.0", "end-1c").strip(),
        }
        topic = str(item.get("topic", "")).strip()
        if not topic:
            raise ValueError("Укажите тему или нишу")
        try:
            count = int(item.get("count", 0))
        except (ValueError, TypeError) as exc:
            raise ValueError("Количество идей должно быть числом") from exc
        if not 1 <= count <= 200:
            raise ValueError("Количество идей должно быть от 1 до 200")
        requirements = str(item.get("requirements", "")).strip()
        return (
            f"Предложи ровно {count} разных углов подачи для новостного ролика.\n"
            f"Новостное направление: {topic}.\nЯзык названий: {self.idea_language.get()}.\n"
            f"Дополнительные требования: {requirements or 'нет'}.\n"
            "Не выдумывай факты, даты, цифры и цитаты. Верни только список рабочих заголовков: "
            "один вариант на отдельной строке, без пояснений, вступления и подзаголовков."
        )

    def _generate_ideas(self):
        if self.ideas_running:
            return
        try:
            if self.running:
                raise ValueError("Сначала дождитесь завершения генерации сценариев")
            if not self.settings.idea_plan:
                self._add_current_idea_to_plan()
            plan = [dict(item) for item in self.settings.idea_plan]
            if not plan:
                raise ValueError("Добавьте хотя бы одно направление в план")
            self.settings.idea_target_count = max(1, int(self.idea_target_entry.get()))
            self.settings.idea_include_custom = bool(self.idea_include_custom_var.get())
            self.settings.idea_custom_text = self.idea_custom_text.get("1.0", "end-1c").strip()
            self.settings.auto_montage_enabled = bool(self.auto_montage_var.get())
            save_settings(self.settings)
            self.ideas_running = True
            self.idea_generate_button.config(state="disabled", text="ИИ придумывает…")
            self.system_status.config(text="Генерация идей…")

            def work():
                try:
                    all_ideas = self._parse_ideas(self.settings.idea_custom_text) if self.settings.idea_include_custom else []
                    for position, item in enumerate(plan, 1):
                        prompt = self._ideas_prompt(item)
                        if item.get("provider") == "openai":
                            key = next((value for value in self.settings.openai_api_keys
                                        if value.active and value.secret.strip() and value.label == item.get("key_label")), None)
                            if key is None:
                                raise ValueError(f"OpenAI-ключ для «{item.get('topic', '')}» не найден")
                            result = asyncio.run(HybridTextPool([], [key], "", self.settings.openai_model).generate(prompt))
                        else:
                            allowed = self._sessions_for("ideas")
                            preferred = next((value for value in allowed
                                              if value.profile_id == item.get("profile_id")), None)
                            fallbacks = [value for value in allowed if value is not preferred]
                            sessions = ([preferred] if preferred else []) + fallbacks
                            if not sessions and not self.settings.openai_api_keys:
                                raise ValueError("Нет активных Claude-сессий или OpenAI API-ключа")
                            result = asyncio.run(self._text_pool(
                                sessions, item.get("chat_url") or "https://claude.ai/new").generate(prompt))
                        all_ideas.extend(self._parse_ideas(result))
                        self.events.put(("ideas_progress", (position, len(plan), item.get("topic", ""))))
                    self.events.put(("ideas_complete", {"ideas": all_ideas, "plan": len(plan)}))
                except Exception as exc:
                    self.events.put(("ideas_error", str(exc)))
            threading.Thread(target=work, daemon=True).start()
        except Exception as exc:
            messagebox.showerror("Генерация идей", str(exc), parent=self.root)

    @staticmethod
    def _parse_ideas(text: str) -> list[str]:
        ideas = []
        for raw in text.splitlines():
            value = re.sub(r"^\s*(?:[-•*]|\d+[.)]|идея\s*\d+[:.)-]?)\s*", "", raw, flags=re.IGNORECASE).strip()
            value = value.strip('"“”«»')
            if value and value not in ideas:
                ideas.append(value)
        return ideas

    def _render_ideas(self):
        if not self.ideas_listbox or not self.ideas_listbox.winfo_exists():
            return
        self.ideas_listbox.delete(0, "end")
        for index, idea in enumerate(self.generated_ideas, 1):
            self.ideas_listbox.insert("end", f"{index}.  {idea}")
        if hasattr(self, "idea_result_title") and self.idea_result_title.winfo_exists():
            self.idea_result_title.config(text=f"Найдено идей: {len(self.generated_ideas)}")

    def _add_ideas_to_scenarios(self, ideas):
        new_items = [idea for idea in ideas if idea and idea not in self.titles]
        if not new_items:
            messagebox.showinfo("Генерация идей", "Новых идей для добавления нет", parent=self.root)
            return
        self.titles.extend(new_items)
        save_session(self.titles, self.jobs)
        self._update_counters()
        messagebox.showinfo("Генерация идей", f"Добавлено в новости: {len(new_items)}", parent=self.root)

    def _add_selected_ideas(self):
        if not self.ideas_listbox:
            return
        self._add_ideas_to_scenarios([self.generated_ideas[i] for i in self.ideas_listbox.curselection()])

    def _edit_selected_idea(self, _=None):
        if not self.ideas_listbox:
            return
        selected = self.ideas_listbox.curselection()
        if len(selected) != 1:
            messagebox.showinfo("Редактирование идеи", "Выберите одну идею", parent=self.root)
            return
        index = selected[0]
        value = self._ask_text("Редактирование идеи", "Измените название идеи:", self.generated_ideas[index])
        if value and value.strip():
            self.generated_ideas[index] = value.strip()
            self._render_ideas()
            self.ideas_listbox.selection_set(index)
            self.ideas_listbox.see(index)

    def _add_all_ideas(self):
        self._add_ideas_to_scenarios(self.generated_ideas)

    def _save_ideas_txt(self):
        if not self.generated_ideas:
            messagebox.showinfo("Генерация идей", "Сначала сгенерируйте идеи", parent=self.root)
            return
        idea_folder = Path(self.settings.idea_output_folder)
        idea_folder.mkdir(parents=True, exist_ok=True)
        path = filedialog.asksaveasfilename(initialdir=idea_folder, defaultextension=".txt", filetypes=[("Текстовые файлы", "*.txt")],
                                            initialfile="Идеи для новостей.txt")
        if path:
            Path(path).write_text("\n".join(self.generated_ideas), encoding="utf-8")
            self.last_saved_paths["ideas"] = path
            return Path(path)
        return None

    def _clear_ideas(self):
        self.generated_ideas = []
        self._render_ideas()

    def _page_footage(self):
        folders = self._card(self.page, fill="x", pady=(4, 12))
        tk.Label(folders, text="ПАПКИ ТВОИХ НАРЕЗОК", bg=CARD, fg=MUTED,
                 font=("Segoe UI Semibold", 8)).pack(anchor="w", padx=18, pady=(15, 5))
        self.footage_folder_list = tk.Listbox(folders, height=4, bg=CARD_2, fg=TEXT,
                                              selectbackground=ACTIVE, relief="flat")
        self.footage_folder_list.pack(fill="x", padx=18)
        for folder in self.settings.footage_folders:
            self.footage_folder_list.insert("end", folder)
        actions = tk.Frame(folders, bg=CARD)
        actions.pack(fill="x", padx=18, pady=12)
        self._button(actions, "+ Добавить папку", self._add_footage_folder, "primary").pack(side="left")
        self._button(actions, "Убрать", self._remove_footage_folder, "danger").pack(side="left", padx=7)
        self.footage_index_button = self._button(actions, "ИИ-индексация", self._scan_footage, "success")
        self.footage_index_button.pack(side="right")
        self._button(actions, "Отмена", self._cancel_footage_index).pack(side="right", padx=7)
        self.footage_count_label = tk.Label(actions, text=f"ИИ-индекс: {self.clip_index.count(True)} / {self.clip_index.count()} видео",
                                             bg=CARD, fg=MUTED, font=("Segoe UI", 9))
        self.footage_count_label.pack(side="right", padx=12)
        self.footage_progress = ttk.Progressbar(folders, mode="determinate")
        self.footage_progress.pack(fill="x", padx=18, pady=(0, 7))
        self.footage_progress_label = tk.Label(
            folders, text="При первом запуске модель CLIP загрузится один раз; затем анализ работает локально",
            bg=CARD, fg=MUTED, font=("Segoe UI", 8), anchor="w")
        self.footage_progress_label.pack(fill="x", padx=18, pady=(0, 12))

        web = self._card(self.page, fill="both", expand=True)
        row = tk.Frame(web, bg=CARD)
        row.pack(fill="x", padx=18, pady=14)
        self.footage_search_entry = self._entry(row)
        self.footage_search_entry.pack(side="left", fill="x", expand=True, ipady=8)
        self.footage_search_entry.insert(0, self.titles[0] if self.titles else "Иран Ормузский пролив танкеры")
        self.footage_source_combo = ttk.Combobox(row, state="readonly", width=29, style="Dark.TCombobox",
                                                 values=("Разрешённые источники", "YouTube", "Все доступные источники"))
        self.footage_source_combo.set("Разрешённые источники")
        self.footage_source_combo.pack(side="left", padx=(8, 0), ipady=6)
        self._button(row, "Агент: найти видео", self._search_web_footage, "primary").pack(side="left", padx=8)
        self._button(row, "Скачать выбранное", self._download_selected_footage, "success").pack(side="left")
        segment_row = tk.Frame(web, bg=CARD)
        segment_row.pack(fill="x", padx=18)
        tk.Label(segment_row, text="Для YouTube скачать короткий отрезок с секунды", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="left")
        self.youtube_start_entry = self._entry(segment_row, width=8)
        self.youtube_start_entry.insert(0, "0")
        self.youtube_start_entry.pack(side="left", padx=6, ipady=4)
        tk.Label(segment_row, text="длительностью 6 секунд", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="left")
        tk.Label(web, text="Источник и лицензия хранятся внутри проекта; автоматические подписи на видео не добавляются",
                 bg=CARD, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", padx=18)
        self.web_footage_list = tk.Listbox(web, bg=CARD_2, fg=TEXT, selectbackground=ACTIVE,
                                           relief="flat", font=("Segoe UI", 10))
        self.web_footage_list.pack(fill="both", expand=True, padx=18, pady=(8, 18))
        for item in self.web_footage_results:
            source = "YouTube" if item.get("source") == "youtube" else "Wikimedia"
            self.web_footage_list.insert("end", f"[{source}] {item['title']}  •  {item['license']}")

    def _add_footage_folder(self):
        folder = filedialog.askdirectory(parent=self.root, title="Папка с твоими футажами")
        if folder and folder not in self.settings.footage_folders:
            self.settings.footage_folders.append(folder)
            save_settings(self.settings)
            self._show_page("footage")

    def _remove_footage_folder(self):
        selected = self.footage_folder_list.curselection()
        if selected:
            del self.settings.footage_folders[selected[0]]
            save_settings(self.settings)
            self._show_page("footage")

    def _scan_footage(self):
        if self.index_running:
            return
        if not self.settings.footage_folders:
            messagebox.showinfo("ИИ-индексация", "Сначала добавьте папку с нарезками", parent=self.root)
            return
        self.index_running = True
        self.index_cancel.clear()
        self.footage_index_button.config(state="disabled", text="ИИ анализирует…")
        self.system_status.config(text="ИИ-индексация футажей…")

        def report(state):
            self.events.put(("footage_index_progress", state))

        def work():
            try:
                state = self.clip_index.index_folders(
                    self.settings.footage_folders, progress=report, cancel=self.index_cancel)
                self.events.put(("footage_index_complete", state))
            except Exception as exc:
                self.events.put(("footage_index_error", str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def _cancel_footage_index(self):
        if self.index_running:
            self.index_cancel.set()
            self.system_status.config(text="Останавливаю индексацию после текущего пакета…")

    def _search_web_footage(self):
        query = self.footage_search_entry.get().strip()
        if not query:
            return
        self.system_status.config(text="Агент ищет футажи…")
        def work():
            try:
                source_mode = self.footage_source_combo.get()
                if source_mode == "YouTube":
                    results = search_youtube_videos(query)
                elif source_mode == "Все доступные источники":
                    results = search_all_available_videos(query)
                else:
                    results = search_wikimedia_videos(query)
                self.events.put(("web_footage", results))
            except Exception as exc:
                self.events.put(("web_footage_error", str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def _download_selected_footage(self):
        selected = self.web_footage_list.curselection()
        if not selected:
            return
        result = self.web_footage_results[selected[0]]
        folder = Path(self.settings.footage_download_folder)
        try:
            start = max(0.0, float(self.youtube_start_entry.get().strip() or 0))
        except ValueError:
            start = 0.0
        def work():
            try:
                if result.get("source") == "youtube":
                    item = download_youtube_segment(result, folder, start=start, duration=6.0)
                else:
                    item = download_footage(result, folder)
                self.events.put(("footage_downloaded", item))
            except Exception as exc:
                self.events.put(("web_footage_error", str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def _page_footage_cutter(self):
        card = self._card(self.page, fill="x", pady=(4, 12))
        tk.Label(card, text="ИСХОДНИКИ ДЛЯ НАРЕЗКИ", bg=CARD, fg=MUTED,
                 font=("Segoe UI Semibold", 8)).pack(anchor="w", padx=18, pady=(15, 5))
        self.cutter_sources_list = tk.Listbox(card, height=6, bg=CARD_2, fg=TEXT,
                                              selectbackground=ACTIVE, relief="flat")
        self.cutter_sources_list.pack(fill="x", padx=18)
        for path in self.cutter_sources:
            self.cutter_sources_list.insert("end", path)
        source_actions = tk.Frame(card, bg=CARD)
        source_actions.pack(fill="x", padx=18, pady=10)
        self._button(source_actions, "+ Добавить видео", self._add_cutter_sources, "primary").pack(side="left")
        self._button(source_actions, "Убрать выбранное", self._remove_cutter_source, "danger").pack(side="left", padx=7)
        self._button(source_actions, "Взять скачанные", self._use_downloaded_for_cutter).pack(side="left")

        settings = self._card(self.page, fill="x", pady=(0, 12))
        row = tk.Frame(settings, bg=CARD)
        row.pack(fill="x", padx=18, pady=(14, 8))
        tk.Label(row, text="ПАПКА НАРЕЗОК", bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 8)).pack(side="left")
        self.cutter_output_entry = self._entry(row)
        self.cutter_output_entry.insert(0, self.settings.cutter_output_folder)
        self.cutter_output_entry.pack(side="left", fill="x", expand=True, padx=8, ipady=7)
        self._button(row, "Выбрать", self._choose_cutter_output).pack(side="left")
        row2 = tk.Frame(settings, bg=CARD)
        row2.pack(fill="x", padx=18, pady=(0, 14))
        for label, attr, value, width in (("ДЛИНА", "cutter_length_entry", "6", 6), ("FPS", "cutter_fps_entry", "30", 6),
                                          ("БИТРЕЙТ", "cutter_bitrate_entry", "4M", 8)):
            tk.Label(row2, text=label, bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 8)).pack(side="left", padx=(0, 5))
            entry = self._entry(row2, width=width)
            entry.insert(0, value)
            entry.pack(side="left", padx=(0, 14), ipady=6)
            setattr(self, attr, entry)
        tk.Label(row2, text="звук убирается; H.264, 30 FPS и одинаковый поток подходят для ИИ-индекса и микса",
                 bg=CARD, fg=MUTED, font=("Segoe UI", 8)).pack(side="left")
        self.cutter_start_button = self._button(row2, "Нарезать и добавить в футажи", self._run_cutter, "success")
        self.cutter_start_button.pack(side="right")

        mixer = self._card(self.page, fill="x")
        mix_top = tk.Frame(mixer, bg=CARD)
        mix_top.pack(fill="x", padx=18, pady=(14, 6))
        tk.Label(mix_top, text="ВАРИАЦИИ ИЗ ГОТОВЫХ НАРЕЗОК", bg=CARD, fg=TEXT,
                 font=("Segoe UI Semibold", 11)).pack(side="left")
        tk.Label(mixer, text="Не меняет клипы. Делает отдельные MP4 из случайных сочетаний одинаковых коротких футажей.",
                 bg=CARD, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", padx=18)
        mix_row = tk.Frame(mixer, bg=CARD)
        mix_row.pack(fill="x", padx=18, pady=12)
        self.mixer_folder_entry = self._entry(mix_row)
        self.mixer_folder_entry.insert(0, self.settings.cutter_output_folder)
        self.mixer_folder_entry.pack(side="left", fill="x", expand=True, ipady=7)
        self._button(mix_row, "Папка клипов", self._choose_mixer_folder).pack(side="left", padx=7)
        for label, attr, value in (("КЛИПОВ В ВИДЕО", "mixer_clips_entry", "12"), ("ВАРИАЦИЙ", "mixer_count_entry", "10")):
            tk.Label(mix_row, text=label, bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 8)).pack(side="left", padx=(10, 5))
            entry = self._entry(mix_row, width=5)
            entry.insert(0, value)
            entry.pack(side="left", ipady=6)
            setattr(self, attr, entry)
        self.mixer_start_button = self._button(mix_row, "Собрать вариации", self._run_mixer, "primary")
        self.mixer_start_button.pack(side="right", padx=(8, 0))
        self.mixer_progress_label = tk.Label(mixer, text="", bg=CARD, fg=MUTED, font=("Segoe UI", 8))
        self.mixer_progress_label.pack(anchor="w", padx=18, pady=(0, 14))

    def _add_cutter_sources(self):
        paths = filedialog.askopenfilenames(parent=self.root, title="Исходники для нарезки",
                                             filetypes=[("Видео", "*.mp4 *.mov *.mkv *.webm *.avi *.m4v")])
        for path in paths:
            if path not in self.cutter_sources:
                self.cutter_sources.append(path)
        self._show_page("footage_cutter")

    def _remove_cutter_source(self):
        selected = self.cutter_sources_list.curselection()
        if selected:
            del self.cutter_sources[selected[0]]
            self._show_page("footage_cutter")

    def _use_downloaded_for_cutter(self):
        folder = Path(self.settings.footage_download_folder)
        for path in folder.rglob("*") if folder.exists() else []:
            if path.is_file() and path.suffix.casefold() in {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}:
                if str(path) not in self.cutter_sources:
                    self.cutter_sources.append(str(path))
        self._show_page("footage_cutter")

    def _choose_cutter_output(self):
        folder = filedialog.askdirectory(parent=self.root, title="Папка готовых нарезок")
        if folder:
            self.cutter_output_entry.delete(0, "end")
            self.cutter_output_entry.insert(0, folder)

    def _choose_mixer_folder(self):
        folder = filedialog.askdirectory(parent=self.root, title="Папка готовых коротких клипов")
        if folder:
            self.mixer_folder_entry.delete(0, "end")
            self.mixer_folder_entry.insert(0, folder)

    def _run_cutter(self):
        if self.cutter_running:
            return
        try:
            output = Path(self.cutter_output_entry.get().strip())
            duration = float(self.cutter_length_entry.get().strip())
            fps = int(self.cutter_fps_entry.get().strip())
            bitrate = self.cutter_bitrate_entry.get().strip() or "4M"
            self.settings.cutter_output_folder = str(output)
            save_settings(self.settings)
            self.cutter_running = True
            self.cutter_start_button.config(state="disabled", text="Нарезаю…")
            self.system_status.config(text="Нарезка футажей…")
            def progress(state):
                self.events.put(("cutter_progress", state))
            def work():
                try:
                    clips = cut_sources(list(self.cutter_sources), output, duration, fps, bitrate, progress)
                    self.events.put(("cutter_complete", {"folder": str(output), "count": len(clips)}))
                except Exception as exc:
                    self.events.put(("cutter_error", str(exc)))
            threading.Thread(target=work, daemon=True).start()
        except Exception as exc:
            messagebox.showerror("Нарезка футажей", str(exc), parent=self.root)

    def _run_mixer(self):
        if self.cutter_running:
            return
        try:
            folder = Path(self.mixer_folder_entry.get().strip())
            clips = [str(path) for path in folder.rglob("*") if path.is_file() and path.suffix.casefold() == ".mp4"]
            plans = make_mix_plans(clips, int(self.mixer_clips_entry.get()), int(self.mixer_count_entry.get()))
            output = Path(self.settings.mixer_output_folder)
            self.cutter_running = True
            self.mixer_start_button.config(state="disabled", text="Собираю…")
            def progress(state):
                self.events.put(("mixer_progress", state))
            def work():
                try:
                    paths = render_mixes(plans, output, progress)
                    self.events.put(("mixer_complete", {"folder": str(output), "count": len(paths)}))
                except Exception as exc:
                    self.events.put(("mixer_error", str(exc)))
            threading.Thread(target=work, daemon=True).start()
        except Exception as exc:
            messagebox.showerror("Вариации футажей", str(exc), parent=self.root)

    def _page_editor(self):
        controls = self._card(self.page, fill="x", pady=(4, 12))
        row = tk.Frame(controls, bg=CARD)
        row.pack(fill="x", padx=18, pady=(14, 8))
        self.editor_query = ttk.Combobox(row, values=self.titles or self.settings.idea_topics,
                                         style="Dark.TCombobox")
        self.editor_query.pack(side="left", fill="x", expand=True, ipady=7)
        if self.titles or self.settings.idea_topics:
            self.editor_query.set((self.titles or self.settings.idea_topics)[0])
        self.montage_build_button = self._button(row, "Агент: собрать черновик", self._build_rough_cut, "primary")
        self.montage_build_button.pack(side="left", padx=8)
        self._button(row, "Сохранить проект", self._save_montage_project).pack(side="left")
        self._button(row, "Открыть проект", self._load_montage_project).pack(side="left", padx=(7, 0))

        narration_row = tk.Frame(controls, bg=CARD)
        narration_row.pack(fill="x", padx=18, pady=(0, 10))
        tk.Label(narration_row, text="ДИКТОРСКИЙ ТЕКСТ", bg=CARD, fg=MUTED,
                 font=("Segoe UI Semibold", 8)).pack(anchor="w")
        self.montage_narration = tk.Text(narration_row, height=5, bg=CARD_2, fg=TEXT,
                                         insertbackground=TEXT, relief="flat", padx=10, pady=8, wrap="word")
        self.montage_narration.pack(fill="x", pady=(5, 0))
        self._install_edit_bindings(self.montage_narration, multiline=True)
        existing_text = self._selected_news_text() or self.editor_query.get()
        self.montage_narration.insert("1.0", existing_text)

        options = tk.Frame(controls, bg=CARD)
        options.pack(fill="x", padx=18, pady=(0, 14))
        tk.Label(options, text="ФОРМАТ", bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 8)).pack(side="left")
        self.montage_ratio = ttk.Combobox(options, state="readonly", width=8, style="Dark.TCombobox",
                                           values=("16:9", "9:16"))
        self.montage_ratio.set(self.timeline_project.aspect_ratio)
        self.montage_ratio.pack(side="left", padx=7, ipady=5)
        self.montage_auto_web_var = tk.BooleanVar(value=self.settings.montage_auto_web)
        tk.Checkbutton(options, text="Автодобор из интернета", variable=self.montage_auto_web_var,
                       bg=CARD, fg=TEXT, selectcolor=CARD_2, activebackground=CARD,
                       activeforeground=TEXT).pack(side="left", padx=7)
        self.montage_auto_youtube_var = tk.BooleanVar(value=self.settings.montage_auto_youtube)
        tk.Checkbutton(options, text="включая YouTube", variable=self.montage_auto_youtube_var,
                       bg=CARD, fg=TEXT, selectcolor=CARD_2, activebackground=CARD,
                       activeforeground=TEXT).pack(side="left")
        self.montage_intro_var = tk.BooleanVar(value=self.settings.montage_intro_enabled)
        tk.Checkbutton(options, text="Случайная заставка", variable=self.montage_intro_var,
                       bg=CARD, fg=TEXT, selectcolor=CARD_2, activebackground=CARD,
                       activeforeground=TEXT).pack(side="left", padx=(10, 2))
        self.montage_intro_label = tk.Label(options, text=(Path(self.settings.montage_intro_folder).name
                                                           if self.settings.montage_intro_folder else "папка не выбрана"),
                                          bg=CARD, fg=MUTED, font=("Segoe UI", 8))
        self.montage_intro_label.pack(side="left", padx=4)
        self._button(options, "Папка заставок", self._choose_intro_folder).pack(side="left", padx=3)
        self.montage_overlay_var = tk.BooleanVar(value=self.settings.montage_overlay_enabled)
        tk.Checkbutton(options, text="Бегущая строка (хромакей)", variable=self.montage_overlay_var,
                       bg=CARD, fg=TEXT, selectcolor=CARD_2, activebackground=CARD,
                       activeforeground=TEXT).pack(side="left", padx=(10, 2))
        self.montage_overlay_label = tk.Label(options, text=(Path(self.settings.montage_overlay_folder).name
                                                             if self.settings.montage_overlay_folder else "папка не выбрана"),
                                            bg=CARD, fg=MUTED, font=("Segoe UI", 8))
        self.montage_overlay_label.pack(side="left", padx=4)
        self._button(options, "Папка строк", self._choose_overlay_folder).pack(side="left", padx=3)
        self.montage_voice_label = tk.Label(options, text=(Path(self.timeline_project.voiceover_path).name
                                                           if self.timeline_project.voiceover_path else "Озвучка не выбрана"),
                                             bg=CARD, fg=MUTED, font=("Segoe UI", 8))
        self.montage_voice_label.pack(side="left", padx=10)
        self._button(options, "Добавить озвучку", self._choose_voiceover).pack(side="left")
        self.montage_render_button = self._button(options, "Экспорт MP4", self._render_timeline, "success")
        self.montage_render_button.pack(side="right")

        workspace = tk.Frame(self.page, bg=BG)
        workspace.pack(fill="both", expand=True)
        preview_card = self._card(workspace, fill="both", expand=True, side="left", padx=(0, 6))
        tk.Label(preview_card, text="ПРЕДПРОСМОТР", bg=CARD, fg=MUTED,
                 font=("Segoe UI Semibold", 8)).pack(anchor="w", padx=14, pady=(12, 8))
        self.video_player = VideoPlayer(preview_card, {"card": CARD, "border": BORDER, "active": ACTIVE,
                                                        "text": TEXT, "muted": MUTED, "blue": BLUE})
        self.video_player.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        timeline = self._card(workspace, fill="both", expand=True, side="left", padx=(6, 0))
        timeline_head = tk.Frame(timeline, bg=CARD)
        timeline_head.pack(fill="x", padx=14, pady=10)
        self.montage_duration_label = tk.Label(timeline_head, text="ТАЙМЛАЙН • 00:00",
                                               bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 8))
        self.montage_duration_label.pack(side="left")
        self._button(timeline_head, "↑", lambda: self._move_timeline_clip(-1)).pack(side="right")
        self._button(timeline_head, "↓", lambda: self._move_timeline_clip(1)).pack(side="right", padx=4)
        self._button(timeline_head, "Заменить", self._replace_timeline_clip).pack(side="right", padx=4)
        self._button(timeline_head, "👍", lambda: self._rate_timeline_clip(1)).pack(side="right", padx=4)
        self._button(timeline_head, "👎", lambda: self._rate_timeline_clip(-10)).pack(side="right", padx=4)
        self._button(timeline_head, "Удалить", self._remove_timeline_clip, "danger").pack(side="right", padx=4)
        self.editor_clips = ttk.Treeview(timeline, columns=("num", "phrase", "clip", "time", "score"),
                                         show="headings", selectmode="browse")
        for key, title, width in (("num", "№", 36), ("phrase", "Реплика", 210),
                                  ("clip", "Футаж", 190), ("time", "Сек", 48), ("score", "ИИ", 48)):
            self.editor_clips.heading(key, text=title)
            self.editor_clips.column(key, width=width, anchor="w", stretch=key in ("phrase", "clip"))
        self.editor_clips.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self.editor_clips.bind("<<TreeviewSelect>>", self._preview_timeline_clip)
        self._render_timeline_rows()

    def _build_rough_cut(self):
        if self.montage_running:
            return
        narration = self.montage_narration.get("1.0", "end-1c").strip()
        title = self.editor_query.get().strip()
        if not narration:
            messagebox.showinfo("Монтаж", "Добавьте дикторский текст", parent=self.root)
            return
        if not self.clip_index.count(True):
            messagebox.showinfo("Монтаж", "Сначала выполните ИИ-индексацию в разделе «Футажи»", parent=self.root)
            return
        self.montage_running = True
        self.settings.montage_auto_web = self.montage_auto_web_var.get()
        self.settings.montage_auto_youtube = self.montage_auto_youtube_var.get()
        self.settings.montage_intro_enabled = self.montage_intro_var.get()
        save_settings(self.settings)
        self.montage_build_button.config(state="disabled", text="Агент планирует…")
        self.system_status.config(text="Агент подбирает видеоряд…")

        def work():
            try:
                plan = None
                try:
                    pool = self._text_pool(self._sessions_for("scenarios"), "https://claude.ai/new")
                    response = asyncio.run(pool.generate(agent_plan_prompt(title, narration)))
                    plan = parse_agent_scene_plan(response)
                except Exception:
                    plan = fallback_scene_plan(narration)
                used = set()
                clips = []
                for scene in plan:
                    hits = self.clip_index.search(scene["visual_query_en"], limit=12, exclude=used)
                    best_score = hits[0].score if hits else -1.0
                    if self.settings.montage_auto_web and best_score < self.settings.montage_match_threshold:
                        try:
                            web_results = search_wikimedia_videos(scene["visual_query_en"], limit=5)
                            if web_results:
                                downloaded = download_footage(web_results[0], Path(self.settings.footage_download_folder))
                                self.clip_index.add_item(downloaded)
                                self.clip_index.index_folders([self.settings.footage_download_folder])
                                hits = self.clip_index.search(scene["visual_query_en"], limit=12, exclude=used)
                                best_score = hits[0].score if hits else best_score
                        except Exception:
                            pass
                    if (self.settings.montage_auto_youtube
                            and best_score < self.settings.montage_match_threshold):
                        try:
                            youtube_results = search_youtube_videos(scene["visual_query_en"], limit=5)
                            if youtube_results:
                                downloaded = download_best_youtube_segment(
                                    youtube_results[0], Path(self.settings.footage_download_folder),
                                    scene["visual_query_en"], self.clip_index.score_file, duration=6.0)
                                self.clip_index.add_item(downloaded)
                                self.clip_index.index_folders([self.settings.footage_download_folder])
                                hits = self.clip_index.search(scene["visual_query_en"], limit=12, exclude=used)
                        except Exception:
                            pass
                    if not hits:
                        continue
                    hit = hits[0]
                    used.add(hit.item.path)
                    clips.append(TimelineClip(
                        path=hit.item.path, narration=scene["narration"],
                        visual_query_en=scene["visual_query_en"], duration=scene["duration"],
                        score=hit.score, source=hit.item.source,
                    ))
                if not clips:
                    raise ValueError("ИИ не нашёл подходящих проиндексированных футажей")
                self.events.put(("montage_plan_complete", {"title": title, "clips": clips}))
            except Exception as exc:
                self.events.put(("montage_error", str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def _selected_news_text(self):
        title = self.editor_query.get().strip() if hasattr(self, "editor_query") else ""
        for job in self.jobs:
            if job.request.title == title and job.state == RunState.DONE:
                return job.result
        return ""

    def _render_timeline_rows(self):
        if not hasattr(self, "editor_clips") or not self.editor_clips.winfo_exists():
            return
        for row in self.editor_clips.get_children():
            self.editor_clips.delete(row)
        for index, clip in enumerate(self.timeline_project.clips):
            self.editor_clips.insert("", "end", iid=str(index), values=(
                index + 1, clip.narration, Path(clip.path).name, f"{clip.duration:.1f}", f"{clip.score:.2f}"))
        seconds = int(self.timeline_project.duration)
        self.montage_duration_label.config(text=f"ТАЙМЛАЙН • {seconds // 60:02d}:{seconds % 60:02d}")

    def _selected_timeline_index(self):
        selected = self.editor_clips.selection() if hasattr(self, "editor_clips") else ()
        return int(selected[0]) if selected else None

    def _preview_timeline_clip(self, _=None):
        index = self._selected_timeline_index()
        if index is not None and index < len(self.timeline_project.clips):
            try:
                self.video_player.load(self.timeline_project.clips[index].path)
            except Exception as exc:
                self.system_status.config(text=str(exc))

    def _move_timeline_clip(self, direction):
        index = self._selected_timeline_index()
        target = index + direction if index is not None else -1
        if index is None or not 0 <= target < len(self.timeline_project.clips):
            return
        clips = self.timeline_project.clips
        clips[index], clips[target] = clips[target], clips[index]
        self._render_timeline_rows()
        self.editor_clips.selection_set(str(target))

    def _remove_timeline_clip(self):
        index = self._selected_timeline_index()
        if index is not None:
            del self.timeline_project.clips[index]
            self._render_timeline_rows()

    def _replace_timeline_clip(self):
        index = self._selected_timeline_index()
        if index is None:
            return
        clip = self.timeline_project.clips[index]
        excluded = {item.path for item in self.timeline_project.clips}
        try:
            hits = self.clip_index.search(clip.visual_query_en, limit=10, exclude=excluded)
            if not hits:
                messagebox.showinfo("Замена", "Других подходящих футажей не найдено", parent=self.root)
                return
            hit = hits[0]
            clip.path, clip.score, clip.source = hit.item.path, hit.score, hit.item.source
            self._render_timeline_rows()
            self.editor_clips.selection_set(str(index))
            self._preview_timeline_clip()
        except Exception as exc:
            messagebox.showerror("Замена", str(exc), parent=self.root)

    def _rate_timeline_clip(self, value):
        index = self._selected_timeline_index()
        if index is None:
            return
        clip = self.timeline_project.clips[index]
        self.clip_index.rate(clip.path, value)
        if value <= -10:
            self._replace_timeline_clip()
        else:
            self.system_status.config(text="Предпочтение сохранено — этот футаж получит больший приоритет")

    def _choose_voiceover(self):
        path = filedialog.askopenfilename(parent=self.root, title="Выберите готовую озвучку",
                                          filetypes=[("Аудио", "*.mp3 *.wav *.m4a *.aac"), ("Все файлы", "*.*")])
        if path:
            self.timeline_project.voiceover_path = path
            self.montage_voice_label.config(text=Path(path).name)
            if self.timeline_project.clips:
                try:
                    self._fit_timeline_to_voiceover(probe_media_duration(Path(path)))
                except Exception as exc:
                    messagebox.showerror("Озвучка", str(exc), parent=self.root)

    def _choose_intro_folder(self):
        folder = filedialog.askdirectory(parent=self.root, title="Папка коротких заставок")
        if folder:
            self.settings.montage_intro_folder = folder
            save_settings(self.settings)
            if hasattr(self, "montage_intro_label") and self.montage_intro_label.winfo_exists():
                self.montage_intro_label.config(text=Path(folder).name)

    def _choose_random_intro(self):
        folder = Path(self.settings.montage_intro_folder)
        candidates = [path for path in folder.rglob("*") if path.is_file()
                      and path.suffix.casefold() in {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}] if folder.is_dir() else []
        if not candidates:
            return ""
        return str(random.choice(candidates))

    def _choose_overlay_folder(self):
        folder = filedialog.askdirectory(parent=self.root, title="Папка хромакеев бегущей строки")
        if folder:
            self.settings.montage_overlay_folder = folder
            save_settings(self.settings)
            if hasattr(self, "montage_overlay_label") and self.montage_overlay_label.winfo_exists():
                self.montage_overlay_label.config(text=Path(folder).name)

    def _choose_random_overlay(self):
        folder = Path(self.settings.montage_overlay_folder)
        candidates = [path for path in folder.rglob("*") if path.is_file()
                      and path.suffix.casefold() in {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}] if folder.is_dir() else []
        return str(random.choice(candidates)) if candidates else ""

    def _fit_timeline_to_voiceover(self, target_duration):
        if not self.timeline_project.clips or target_duration <= 0:
            return
        current = max(0.1, sum(item.duration for item in self.timeline_project.clips))
        factor = target_duration / current
        original = list(self.timeline_project.clips)
        fitted = []
        excluded = {item.path for item in original}
        for clip in original:
            remaining = clip.duration * factor
            first = True
            while remaining > 0.02:
                duration = min(5.8, remaining)
                selected = clip
                if not first:
                    hits = self.clip_index.search(clip.visual_query_en, limit=5, exclude=excluded)
                    if hits:
                        hit = hits[0]
                        excluded.add(hit.item.path)
                        selected = TimelineClip(hit.item.path, clip.narration, clip.visual_query_en,
                                                duration, 0.0, hit.score, hit.item.source)
                    else:
                        selected = TimelineClip(clip.path, clip.narration, clip.visual_query_en,
                                                duration, 0.0, clip.score, clip.source)
                else:
                    selected = TimelineClip(clip.path, clip.narration, clip.visual_query_en,
                                            duration, clip.source_start, clip.score, clip.source)
                fitted.append(selected)
                remaining -= duration
                first = False
        difference = target_duration - sum(item.duration for item in fitted)
        if fitted and abs(difference) > 0.001:
            fitted[-1].duration = max(0.1, fitted[-1].duration + difference)
        self.timeline_project.clips = fitted
        self._render_timeline_rows()

    def _save_montage_project(self):
        folder = Path(self.settings.montage_project_folder)
        folder.mkdir(parents=True, exist_ok=True)
        path = filedialog.asksaveasfilename(parent=self.root, initialdir=folder, defaultextension=".newsflow",
                                            filetypes=[("Проект NewsFlow", "*.newsflow")])
        if path:
            self.timeline_project.aspect_ratio = self.montage_ratio.get()
            self.timeline_project.save(Path(path))

    def _load_montage_project(self):
        folder = Path(self.settings.montage_project_folder)
        path = filedialog.askopenfilename(parent=self.root, initialdir=folder,
                                          filetypes=[("Проект NewsFlow", "*.newsflow")])
        if path:
            self.timeline_project = TimelineProject.load(Path(path))
            self._show_page("editor")

    def _render_timeline(self):
        if self.montage_running:
            return
        if not self.timeline_project.clips:
            messagebox.showinfo("Экспорт", "Таймлайн пуст", parent=self.root)
            return
        folder = Path(self.settings.montage_output_folder)
        folder.mkdir(parents=True, exist_ok=True)
        path = filedialog.asksaveasfilename(parent=self.root, initialdir=folder, defaultextension=".mp4",
                                            filetypes=[("Видео MP4", "*.mp4")])
        if not path:
            return
        self.timeline_project.aspect_ratio = self.montage_ratio.get()
        self.settings.montage_aspect_ratio = self.timeline_project.aspect_ratio
        self.settings.montage_intro_enabled = bool(self.montage_intro_var.get())
        self.settings.montage_overlay_enabled = bool(self.montage_overlay_var.get())
        if self.settings.montage_intro_enabled:
            intro = self._choose_random_intro()
            if not intro:
                messagebox.showerror("Заставка", "Выберите папку, где есть видео для случайной заставки.", parent=self.root)
                return
            self.timeline_project.intro_path = intro
            # Заставка — самостоятельный первый клип. Не режем её старым
            # параметром «6 секунд»: озвучка начинается только после полного
            # исходника, а его звук остаётся в итоговом MP4.
            self.timeline_project.intro_duration = probe_media_duration(Path(intro))
        else:
            self.timeline_project.intro_path = ""
            self.timeline_project.intro_duration = 0.0
        if self.settings.montage_overlay_enabled:
            overlay = self._choose_random_overlay()
            if not overlay:
                messagebox.showerror("Бегущая строка", "Выберите папку, где есть видео с зелёным хромакеем.", parent=self.root)
                return
            self.timeline_project.overlay_path = overlay
        else:
            self.timeline_project.overlay_path = ""
        save_settings(self.settings)
        Path(path).with_suffix(".remotion.json").write_text(
            json.dumps(remotion_payload(self.timeline_project), ensure_ascii=False, indent=2), encoding="utf-8")
        self.montage_running = True
        self.montage_render_button.config(state="disabled", text="Рендер…")
        def progress(done, total, label):
            self.events.put(("montage_render_progress", {"done": done, "total": total, "label": label}))
        def work():
            try:
                output = render_project(self.timeline_project, Path(path), progress)
                self.clip_index.mark_used(item.path for item in self.timeline_project.clips)
                self.events.put(("montage_render_complete", str(output)))
            except Exception as exc:
                self.events.put(("montage_error", str(exc)))
        threading.Thread(target=work, daemon=True).start()

    # ---- Voiceover (ported from Voicer: Chrome queue + API provider) ------------

    def _voice_profiles(self) -> list[dict]:
        profiles = self.settings.voice_profiles or []
        clean = []
        for item in profiles:
            clean.append({
                "name": str(item.get("name") or "Новости"),
                "voice_id": str(item.get("voice_id") or ""),
                "voice_name": str(item.get("voice_name") or ""),
                "stability": max(0.0, min(1.0, float(item.get("stability", 0.30)))),
                "style": max(0.0, min(1.0, float(item.get("style", 0.50)))),
                "favorite": bool(item.get("favorite", False)),
            })
        return clean or [{"name": "Новости", "voice_id": "", "voice_name": "", "stability": .30, "style": .50, "favorite": False}]

    def _active_voicer_key(self) -> str:
        key = next((item.secret for item in self.settings.secret_voicer_keys
                    if item.active and item.secret.strip()), "")
        if not key:
            raise ValueError("Добавьте активный API-ключ Secret Voicer в разделе «Голоса и API»")
        return key

    def _profile_from_index(self, index: int) -> VoiceProfile:
        profiles = self._voice_profiles()
        item = profiles[max(0, min(index, len(profiles) - 1))]
        return VoiceProfile(item["name"], item["voice_id"], item["stability"], item["style"], item["voice_name"])

    def _voice_browser_profile_dir(self) -> Path:
        return app_data_root() / "VoiceChromeProfiles" / self.settings.voice_browser_profile_id

    def _voice_provider(self) -> str:
        value = self.voice_provider_var.get() if hasattr(self, "voice_provider_var") else self.settings.voice_provider
        return "api" if str(value).startswith("API") or value == "api" else "chrome"

    def _open_voice_browser_login(self):
        try:
            open_voice_login(self._voice_browser_profile_dir())
            self.system_status.config(text="Открыт отдельный Chrome-профиль Secret Voicer — войдите через Telegram")
            messagebox.showinfo("Chrome-озвучка", "Войдите в Secret Voicer через Telegram в открытом окне. Затем закройте это окно Chrome: NewsFlow будет использовать этот же профиль для фоновой очереди.", parent=self.root)
        except Exception as exc:
            messagebox.showerror("Chrome-озвучка", str(exc), parent=self.root)

    def _synthesize_voice(self, text: str, profile: VoiceProfile, progress):
        provider = self._voice_provider()
        if provider == "api":
            return SecretVoicerClient(self._active_voicer_key()).synthesize(text, profile, progress)
        try:
            return ChromeSecretVoicer(self._voice_browser_profile_dir()).synthesize(text, profile, progress)
        except Exception:
            if not self.settings.voice_api_fallback:
                raise
            key = next((item.secret for item in self.settings.secret_voicer_keys if item.active and item.secret.strip()), "")
            if not key:
                raise
            progress("Chrome недоступен — используем Secret Voicer API", 10)
            return SecretVoicerClient(key).synthesize(text, profile, progress)

    def _page_voice_create(self):
        card = self._card(self.page, fill="both", expand=True, pady=(4, 18))
        head = tk.Frame(card, bg=CARD)
        head.pack(fill="x", padx=20, pady=(18, 8))
        tk.Label(head, text="Новая озвучка", bg=CARD, fg=TEXT,
                 font=("Segoe UI Semibold", 13)).pack(side="left")
        self.voice_status_label = tk.Label(head, text="Готово к генерации", bg=CARD, fg=MUTED,
                                            font=("Segoe UI", 9))
        self.voice_status_label.pack(side="right")

        source_row = tk.Frame(card, bg=CARD)
        source_row.pack(fill="x", padx=20, pady=8)
        self._button(source_row, "Взять выбранную новость", self._voice_use_selected_news).pack(side="left")
        self._button(source_row, "Взять текст монтажа", self._voice_use_montage_text).pack(side="left", padx=7)
        tk.Label(source_row, text="Текст можно править перед генерацией", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 9)).pack(side="left", padx=10)

        self.voice_text = tk.Text(card, height=14, bg=CARD_2, fg=TEXT, insertbackground=TEXT,
                                  relief="flat", wrap="word", font=("Segoe UI", 10), padx=12, pady=10)
        self.voice_text.pack(fill="both", expand=True, padx=20, pady=(4, 12))
        self._install_edit_bindings(self.voice_text, multiline=True)
        initial = self._selected_news_text() or (self.montage_narration.get("1.0", "end-1c").strip()
                                                  if hasattr(self, "montage_narration") else "")
        if initial:
            self.voice_text.insert("1.0", initial)

        controls = tk.Frame(card, bg=CARD_2, padx=12, pady=12)
        controls.pack(fill="x", padx=20, pady=(0, 20))
        tk.Label(controls, text="Провайдер", bg=CARD_2, fg=MUTED, font=("Segoe UI", 9)).pack(side="left")
        self.voice_provider_var = tk.StringVar(value="Chrome — Telegram (фон)" if self.settings.voice_provider != "api" else "API — Secret Voicer")
        provider_picker = ttk.Combobox(controls, state="readonly", width=25, style="Dark.TCombobox",
                                       textvariable=self.voice_provider_var,
                                       values=("Chrome — Telegram (фон)", "API — Secret Voicer"))
        provider_picker.pack(side="left", padx=7, ipady=4)
        provider_picker.bind("<<ComboboxSelected>>", lambda _: self._save_voice_provider())
        self._button(controls, "Открыть Chrome / вход Telegram", self._open_voice_browser_login).pack(side="left", padx=(0, 9))
        tk.Label(controls, text="Профиль", bg=CARD_2, fg=MUTED, font=("Segoe UI", 9)).pack(side="left")
        profiles = self._voice_profiles()
        self.voice_profile_var = tk.StringVar(value="1")
        profile_picker = ttk.Combobox(controls, state="readonly", width=31, style="Dark.TCombobox",
                                      textvariable=self.voice_profile_var,
                                      values=[f"{index + 1}. {item['name']}" for index, item in enumerate(profiles)])
        profile_picker.current(0)
        profile_picker.pack(side="left", padx=7, ipady=4)
        tk.Label(controls, text="Имя MP3", bg=CARD_2, fg=MUTED, font=("Segoe UI", 9)).pack(side="left", padx=(8, 0))
        self.voice_name_entry = self._entry(controls, width=28)
        self.voice_name_entry.insert(0, self.editor_query.get().strip() if hasattr(self, "editor_query") else "Озвучка")
        self.voice_name_entry.pack(side="left", padx=7, ipady=4)
        self.voicer_generate_button = self._button(controls, "Создать MP3", self._generate_voiceover, "success")
        self.voicer_generate_button.pack(side="right")
        batch = tk.Frame(card, bg=CARD, padx=20, pady=16)
        batch.pack(fill="x")
        self.voice_batch_button = self._button(batch, "Озвучить готовые сценарии по диапазонам", self._generate_voice_ranges, "primary")
        self.voice_batch_button.pack(side="left")
        tk.Label(batch, text="Работает строго по очереди в одном фоновом Chrome; диапазоны назначаются в «Голоса и API».",
                 bg=CARD, fg=MUTED, font=("Segoe UI", 9)).pack(side="left", padx=10)

    def _voice_use_selected_news(self):
        text = self._selected_news_text()
        if not text:
            messagebox.showinfo("Озвучка", "Выберите готовую новость в разделе «Новости»", parent=self.root)
            return
        self.voice_text.delete("1.0", "end")
        self.voice_text.insert("1.0", text)

    def _voice_use_montage_text(self):
        if not hasattr(self, "montage_narration"):
            messagebox.showinfo("Озвучка", "Добавьте текст в разделе «Монтаж» или вставьте его сюда", parent=self.root)
            return
        text = self.montage_narration.get("1.0", "end-1c").strip()
        if text:
            self.voice_text.delete("1.0", "end")
            self.voice_text.insert("1.0", text)

    def _generate_voiceover(self):
        if self.voicer_running:
            return
        text = self.voice_text.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showinfo("Озвучка", "Добавьте текст", parent=self.root)
            return
        if self._voice_provider() == "api":
            try:
                self._active_voicer_key()
            except Exception as exc:
                messagebox.showerror("Озвучка", str(exc), parent=self.root)
                return
        try:
            index = max(0, int(self.voice_profile_var.get().split(".", 1)[0]) - 1)
        except Exception:
            index = 0
        profile = self._profile_from_index(index)
        name = self.voice_name_entry.get().strip() or profile.name
        self.voicer_running = True
        self.voicer_generate_button.config(state="disabled", text="Генерация…")
        active = "Secret Voicer API" if self._voice_provider() == "api" else "Chrome / Telegram"
        self.voice_status_label.config(text=f"{active}: отправляем текст")
        self.system_status.config(text="Создание озвучки…")

        def work():
            try:
                content = self._synthesize_voice(text, profile,
                                                lambda label, percent: self.events.put(("voicer_progress", (label, percent))))
                path = SecretVoicerClient("browser-session").save_audio(Path(self.settings.voicer_output_folder), name, content)
                self.events.put(("voicer_done", str(path)))
            except Exception as exc:
                self.events.put(("voicer_error", str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def _save_voice_provider(self):
        self.settings.voice_provider = self._voice_provider()
        save_settings(self.settings)

    def _voice_profile_for_scenario(self, one_based_index: int) -> VoiceProfile:
        profiles = self._voice_profiles()
        profile_index = 0
        for item in self.settings.voice_ranges:
            try:
                if int(item.get("start", 0)) <= one_based_index <= int(item.get("end", 0)):
                    profile_index = int(item.get("profile", 0))
            except (TypeError, ValueError):
                continue
        return self._profile_from_index(max(0, min(profile_index, len(profiles) - 1)))

    def _generate_voice_ranges(self):
        if self.voicer_running or self.voice_batch_running:
            return
        ready = [job for job in self.jobs if job.state == RunState.DONE and job.result.strip()]
        pending = [job for job in ready if not Path(self.settings.voice_scenario_outputs.get(str(job.request.index + 1), "")).is_file()]
        if not pending:
            messagebox.showinfo("Озвучка по диапазонам", "Нет готовых сценариев без MP3. Готовые MP3 уже учтены в конвейере.", parent=self.root)
            return
        if self._voice_provider() == "api":
            try:
                self._active_voicer_key()
            except Exception as exc:
                messagebox.showerror("Озвучка", str(exc), parent=self.root)
                return
        self.voicer_running = True
        self.voice_batch_running = True
        if hasattr(self, "voice_batch_button") and self.voice_batch_button.winfo_exists():
            self.voice_batch_button.config(state="disabled", text="Очередь озвучки…")
        self.system_status.config(text=f"Очередь озвучки: 0 / {len(pending)}")

        def work():
            errors = []
            for number, job in enumerate(pending, 1):
                profile = self._voice_profile_for_scenario(job.request.index + 1)
                try:
                    content = self._synthesize_voice(job.result, profile,
                        lambda label, percent, n=number, total=len(pending): self.events.put(("voicer_batch_progress", (n, total, label, percent))))
                    path = SecretVoicerClient("browser-session").save_audio(
                        Path(self.settings.voicer_output_folder), f"{job.request.index + 1:03d} — {job.request.title}", content)
                    self.events.put(("voicer_batch_item", (job.request.index + 1, str(path), number, len(pending))))
                except Exception as exc:
                    errors.append(f"{job.request.index + 1}. {job.request.title}: {exc}")
            self.events.put(("voicer_batch_done", (len(pending), errors)))
        threading.Thread(target=work, daemon=True).start()

    def _page_voice_profiles(self):
        card = self._card(self.page, fill="both", expand=True, pady=(4, 18))
        browser_panel = tk.Frame(card, bg=CARD_2, padx=16, pady=14)
        browser_panel.pack(fill="x", padx=20, pady=(18, 0))
        tk.Label(browser_panel, text="Chrome / Telegram — основной провайдер", bg=CARD_2, fg=TEXT,
                 font=("Segoe UI Semibold", 11)).pack(anchor="w")
        tk.Label(browser_panel, text="Рабочая схема Войсер: отдельный локальный профиль → ваш вход через Telegram → одна фоновая очередь MP3. Обычный Chrome, cookies и пароли не копируются.",
                 bg=CARD_2, fg=MUTED, wraplength=980, justify="left", font=("Segoe UI", 9)).pack(anchor="w", pady=(3, 9))
        browser_actions = tk.Frame(browser_panel, bg=CARD_2)
        browser_actions.pack(fill="x")
        self._button(browser_actions, "Открыть Chrome / войти через Telegram", self._open_voice_browser_login, "primary").pack(side="left")
        self.voice_api_fallback_var = tk.BooleanVar(value=self.settings.voice_api_fallback)
        tk.Checkbutton(browser_actions, text="При ошибке Chrome перейти на API, если ключ добавлен", variable=self.voice_api_fallback_var,
                       command=self._save_voice_api_fallback, bg=CARD_2, fg=TEXT, selectcolor=ACTIVE,
                       activebackground=CARD_2, activeforeground=TEXT, font=("Segoe UI", 9)).pack(side="left", padx=15)
        key_panel = tk.Frame(card, bg=CARD_2, padx=16, pady=14)
        key_panel.pack(fill="x", padx=20, pady=(10, 10))
        tk.Label(key_panel, text="Secret Voicer API", bg=CARD_2, fg=TEXT,
                 font=("Segoe UI Semibold", 11)).pack(anchor="w")
        tk.Label(key_panel, text="Ключ шифруется Windows и не отображается после сохранения", bg=CARD_2, fg=MUTED,
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(3, 9))
        key_row = tk.Frame(key_panel, bg=CARD_2)
        key_row.pack(fill="x")
        self.voice_api_entry = self._entry(key_row, show="•")
        self.voice_api_entry.pack(side="left", fill="x", expand=True, ipady=6)
        self._button(key_row, "Сохранить ключ", self._save_voice_api_key, "primary").pack(side="left", padx=(8, 0))
        count = len([item for item in self.settings.secret_voicer_keys if item.active and item.secret])
        tk.Label(key_panel, text=f"Активных ключей: {count}", bg=CARD_2, fg="#35D99A" if count else "#F5C451",
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(8, 0))

        ranges_panel = tk.Frame(card, bg=CARD_2, padx=16, pady=12)
        ranges_panel.pack(fill="x", padx=20, pady=(0, 10))
        tk.Label(ranges_panel, text="Голоса по диапазонам сценариев", bg=CARD_2, fg=TEXT,
                 font=("Segoe UI Semibold", 11)).pack(anchor="w")
        tk.Label(ranges_panel, text="Например: 1–100 — первый голос, 101–300 — второй. При пересечении используется последнее правило.",
                 bg=CARD_2, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(3, 8))
        range_row = tk.Frame(ranges_panel, bg=CARD_2)
        range_row.pack(fill="x")
        tk.Label(range_row, text="С", bg=CARD_2, fg=MUTED).pack(side="left")
        self.voice_range_start_entry = self._entry(range_row, width=7); self.voice_range_start_entry.insert(0, "1")
        self.voice_range_start_entry.pack(side="left", padx=(5, 10), ipady=4)
        tk.Label(range_row, text="по", bg=CARD_2, fg=MUTED).pack(side="left")
        self.voice_range_end_entry = self._entry(range_row, width=7); self.voice_range_end_entry.insert(0, str(self.settings.pipeline_target_count))
        self.voice_range_end_entry.pack(side="left", padx=(5, 12), ipady=4)
        tk.Label(range_row, text="Голос", bg=CARD_2, fg=MUTED).pack(side="left")
        self.voice_range_profile_combo = ttk.Combobox(range_row, state="readonly", width=28, style="Dark.TCombobox",
                                                       values=[f"{i + 1}. {item['name']}" for i, item in enumerate(self._voice_profiles())])
        self.voice_range_profile_combo.current(0)
        self.voice_range_profile_combo.pack(side="left", padx=7, ipady=4)
        self._button(range_row, "+ Добавить диапазон", self._add_voice_range, "primary").pack(side="left", padx=6)
        self.voice_range_list = tk.Listbox(ranges_panel, bg=CARD, fg=TEXT, selectbackground=ACTIVE, relief="flat", highlightthickness=0,
                                           font=("Segoe UI", 9), height=4)
        self.voice_range_list.pack(fill="x", pady=(9, 0))
        for item in self.settings.voice_ranges:
            try:
                name = self._voice_profiles()[int(item.get("profile", 0))]["name"]
                self.voice_range_list.insert("end", f"{item.get('start')}–{item.get('end')}  →  {name}")
            except (IndexError, TypeError, ValueError):
                continue
        self._button(ranges_panel, "Удалить выбранный диапазон", self._delete_voice_range, "danger").pack(anchor="e", pady=(7, 0))

        body = tk.Frame(card, bg=CARD)
        body.pack(fill="both", expand=True, padx=20, pady=(4, 20))
        left = tk.Frame(body, bg=CARD_2, width=330, padx=12, pady=12)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        tk.Label(left, text="Профили диктора", bg=CARD_2, fg=TEXT,
                 font=("Segoe UI Semibold", 11)).pack(anchor="w")
        profiles = self._voice_profiles()
        current = min(getattr(self, "voice_profile_edit_index", 0), len(profiles) - 1)
        self.voice_profile_edit_index = current
        self.voice_profile_list = tk.Listbox(left, bg=CARD_2, fg=TEXT, selectbackground=ACTIVE,
                                             relief="flat", highlightthickness=0, font=("Segoe UI", 10), height=13)
        self.voice_profile_list.pack(fill="both", expand=True, pady=10)
        for index, item in enumerate(profiles):
            self.voice_profile_list.insert("end", f"{'★ ' if item.get('favorite') else ''}{index + 1}. {item['name']}")
        self.voice_profile_list.selection_set(current)
        self.voice_profile_list.bind("<<ListboxSelect>>", self._select_voice_profile)
        buttons = tk.Frame(left, bg=CARD_2)
        buttons.pack(fill="x")
        self._button(buttons, "+ Профиль", self._add_voice_profile).pack(side="left")
        self._button(buttons, "Удалить", self._delete_voice_profile, "danger").pack(side="right")

        editor = tk.Frame(body, bg=CARD, padx=18, pady=8)
        editor.pack(side="left", fill="both", expand=True)
        item = profiles[current]
        tk.Label(editor, text="Настройки выбранного профиля", bg=CARD, fg=TEXT,
                 font=("Segoe UI Semibold", 12)).pack(anchor="w", pady=(4, 12))
        favorites = [voice["name"] for voice in profiles if voice.get("favorite")]
        tk.Label(editor, text="Избранные: " + (", ".join(favorites) if favorites else "нет"), bg=CARD, fg="#F5C451",
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 6))
        for label, key, width in (("Название профиля", "name", 42), ("Имя голоса в Secret Voicer", "voice_name", 42), ("Voice ID", "voice_id", 42)):
            tk.Label(editor, text=label, bg=CARD, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(5, 3))
            entry = self._entry(editor, width=width)
            entry.insert(0, item[key])
            entry.pack(anchor="w", ipady=6)
            setattr(self, f"voice_profile_{key}_entry", entry)
        self.voice_stability_var = tk.DoubleVar(value=item["stability"])
        self.voice_style_var = tk.DoubleVar(value=item["style"])
        self.voice_favorite_var = tk.BooleanVar(value=item.get("favorite", False))
        tk.Checkbutton(editor, text="Избранный голос", variable=self.voice_favorite_var, bg=CARD, fg=TEXT,
                       selectcolor=ACTIVE, activebackground=CARD, activeforeground=TEXT, font=("Segoe UI", 9)).pack(anchor="w", pady=(12, 0))
        for label, variable, hint in (("Стабильность", self.voice_stability_var, "ниже — эмоциональнее"),
                                      ("Сила эмоций", self.voice_style_var, "выше — выразительнее")):
            line = tk.Frame(editor, bg=CARD)
            line.pack(fill="x", pady=(17, 0))
            tk.Label(line, text=f"{label}  ·  {hint}", bg=CARD, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w")
            tk.Scale(line, from_=0, to=1, resolution=.01, variable=variable, orient="horizontal",
                     bg=CARD, fg=TEXT, troughcolor=CARD_2, activebackground=BLUE, highlightthickness=0,
                     length=420).pack(anchor="w")
        action = tk.Frame(editor, bg=CARD)
        action.pack(fill="x", pady=20)
        self._button(action, "Сохранить профиль", self._save_voice_profile, "primary").pack(side="left")
        self._button(action, "Получить голоса", self._load_voice_catalog).pack(side="left", padx=8)

        catalog = tk.Frame(editor, bg=CARD_2, padx=10, pady=10)
        catalog.pack(fill="both", expand=True)
        tk.Label(catalog, text="Каталог голосов — двойной клик назначает Voice ID", bg=CARD_2, fg=MUTED,
                 font=("Segoe UI", 9)).pack(anchor="w")
        self.voice_catalog_tree = ttk.Treeview(catalog, columns=("name", "id", "gender"), show="headings", height=7)
        for name, text, width in (("name", "ГОЛОС", 220), ("id", "VOICE ID", 230), ("gender", "ТИП", 100)):
            self.voice_catalog_tree.heading(name, text=text)
            self.voice_catalog_tree.column(name, width=width, anchor="w")
        self.voice_catalog_tree.pack(fill="both", expand=True, pady=(7, 0))
        for index, voice in enumerate(self.voicer_catalog):
            self.voice_catalog_tree.insert("", "end", iid=str(index), values=(voice.get("name", "Голос"),
                                                  voice.get("voice_id", ""), voice.get("gender", "")))
        self.voice_catalog_tree.bind("<Double-1>", self._assign_catalog_voice)

    def _save_voice_api_key(self):
        key = self.voice_api_entry.get().strip()
        if not key:
            messagebox.showinfo("Голоса и API", "Вставьте API-ключ", parent=self.root)
            return
        if self.settings.secret_voicer_keys:
            self.settings.secret_voicer_keys[0].secret = key
            self.settings.secret_voicer_keys[0].active = True
        else:
            self.settings.secret_voicer_keys.append(SecretVoicerKey("Основной Secret Voicer", key, True))
        save_settings(self.settings)
        self.voice_api_entry.delete(0, "end")
        self.system_status.config(text="Ключ Secret Voicer сохранён")
        self._show_page("voice_profiles")

    def _save_voice_api_fallback(self):
        self.settings.voice_api_fallback = bool(self.voice_api_fallback_var.get())
        save_settings(self.settings)

    def _add_voice_range(self):
        try:
            start = max(1, int(self.voice_range_start_entry.get().strip()))
            end = max(start, int(self.voice_range_end_entry.get().strip()))
            profile = max(0, self.voice_range_profile_combo.current())
        except ValueError:
            messagebox.showerror("Диапазон голосов", "Укажите целые номера начала и конца диапазона.", parent=self.root)
            return
        self.settings.voice_ranges.append({"start": start, "end": end, "profile": profile})
        save_settings(self.settings)
        self._show_page("voice_profiles")

    def _delete_voice_range(self):
        selected = self.voice_range_list.curselection()
        if not selected:
            return
        index = int(selected[0])
        if 0 <= index < len(self.settings.voice_ranges):
            del self.settings.voice_ranges[index]
            save_settings(self.settings)
            self._show_page("voice_profiles")

    def _select_voice_profile(self, _=None):
        selected = self.voice_profile_list.curselection()
        if selected:
            self.voice_profile_edit_index = int(selected[0])
            self._show_page("voice_profiles")

    def _add_voice_profile(self):
        self.settings.voice_profiles = self._voice_profiles() + [{
            "name": f"Диктор {len(self._voice_profiles()) + 1}", "voice_id": "", "voice_name": "", "stability": .30, "style": .50, "favorite": False,
        }]
        self.voice_profile_edit_index = len(self.settings.voice_profiles) - 1
        save_settings(self.settings)
        self._show_page("voice_profiles")

    def _delete_voice_profile(self):
        profiles = self._voice_profiles()
        if len(profiles) == 1:
            messagebox.showinfo("Профили", "Оставьте хотя бы один профиль", parent=self.root)
            return
        del profiles[self.voice_profile_edit_index]
        self.settings.voice_profiles = profiles
        self.voice_profile_edit_index = max(0, self.voice_profile_edit_index - 1)
        save_settings(self.settings)
        self._show_page("voice_profiles")

    def _save_voice_profile(self):
        profiles = self._voice_profiles()
        profiles[self.voice_profile_edit_index] = {
            "name": self.voice_profile_name_entry.get().strip() or "Новости",
            "voice_id": self.voice_profile_voice_id_entry.get().strip(),
            "voice_name": self.voice_profile_voice_name_entry.get().strip(),
            "stability": float(self.voice_stability_var.get()), "style": float(self.voice_style_var.get()),
            "favorite": bool(self.voice_favorite_var.get()),
        }
        self.settings.voice_profiles = profiles
        save_settings(self.settings)
        self.system_status.config(text="Профиль диктора сохранён")
        self._show_page("voice_profiles")

    def _load_voice_catalog(self):
        try:
            key = self._active_voicer_key()
        except Exception as exc:
            messagebox.showerror("Каталог голосов", str(exc), parent=self.root)
            return
        self.system_status.config(text="Загружаем каталог голосов…")
        def work():
            try:
                self.events.put(("voicer_catalog", SecretVoicerClient(key).voices()))
            except Exception as exc:
                self.events.put(("voicer_error", str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def _assign_catalog_voice(self, _=None):
        selected = self.voice_catalog_tree.selection()
        if not selected:
            return
        values = self.voice_catalog_tree.item(selected[0], "values")
        self.voice_profile_voice_name_entry.delete(0, "end")
        self.voice_profile_voice_name_entry.insert(0, values[0])
        self.voice_profile_voice_id_entry.delete(0, "end")
        self.voice_profile_voice_id_entry.insert(0, values[1])

    def _apply_voiceover(self, path: str):
        self.timeline_project.voiceover_path = path
        if hasattr(self, "montage_voice_label") and self.montage_voice_label.winfo_exists():
            self.montage_voice_label.config(text=Path(path).name)
        if self.timeline_project.clips:
            self._fit_timeline_to_voiceover(probe_media_duration(Path(path)))

    def _page_voice_outputs(self):
        card = self._card(self.page, fill="both", expand=True, pady=(4, 18))
        top = tk.Frame(card, bg=CARD, padx=20, pady=18)
        top.pack(fill="x")
        tk.Label(top, text="Папка с озвучками", bg=CARD, fg=TEXT,
                 font=("Segoe UI Semibold", 13)).pack(side="left")
        self._button(top, "Открыть папку", lambda: os.startfile(self.settings.voicer_output_folder)).pack(side="right")
        folder = Path(self.settings.voicer_output_folder)
        folder.mkdir(parents=True, exist_ok=True)
        files = sorted((item for item in folder.iterdir() if item.is_file() and item.suffix.lower() in {".mp3", ".wav", ".m4a", ".aac"}),
                       key=lambda item: item.stat().st_mtime, reverse=True)
        self.voice_outputs_tree = ttk.Treeview(card, columns=("name", "size", "modified"), show="headings", height=17)
        for key, label, width in (("name", "ФАЙЛ", 560), ("size", "РАЗМЕР", 120), ("modified", "ИЗМЕНЁН", 180)):
            self.voice_outputs_tree.heading(key, text=label)
            self.voice_outputs_tree.column(key, width=width, anchor="w")
        self.voice_outputs_tree.pack(fill="both", expand=True, padx=20, pady=8)
        self.voice_output_paths = []
        for index, item in enumerate(files):
            self.voice_output_paths.append(str(item))
            self.voice_outputs_tree.insert("", "end", iid=str(index), values=(item.name, f"{item.stat().st_size / 1024:.0f} КБ",
                                               time.strftime("%d.%m.%Y %H:%M", time.localtime(item.stat().st_mtime))))
        actions = tk.Frame(card, bg=CARD, padx=20, pady=10)
        actions.pack(fill="x", pady=(5, 10))
        self._button(actions, "Прослушать", self._open_selected_voice).pack(side="left")
        self._button(actions, "Использовать в монтаже", self._use_selected_voice_in_montage, "success").pack(side="left", padx=8)

    def _selected_voice_file(self) -> str | None:
        selected = self.voice_outputs_tree.selection()
        return self.voice_output_paths[int(selected[0])] if selected else None

    def _open_selected_voice(self):
        path = self._selected_voice_file()
        if path:
            os.startfile(path)

    def _use_selected_voice_in_montage(self):
        path = self._selected_voice_file()
        if not path:
            messagebox.showinfo("Озвучка", "Выберите MP3", parent=self.root)
            return
        try:
            self._apply_voiceover(path)
            self.system_status.config(text="Озвучка передана в монтаж")
        except Exception as exc:
            messagebox.showerror("Озвучка", str(exc), parent=self.root)

    def _page_keys(self):
        card = self._card(self.page, fill="both", expand=True, pady=(4, 18))
        head = tk.Frame(card, bg=CARD)
        head.pack(fill="x", padx=20, pady=18)
        copy = tk.Frame(head, bg=CARD)
        copy.pack(side="left")
        tk.Label(copy, text="Профили Chrome для Claude", bg=CARD, fg=TEXT,
                 font=("Segoe UI Semibold", 12)).pack(anchor="w")
        tk.Label(copy, text="Войдите в Claude вручную один раз — авторизация сохранится в отдельном профиле",
                 bg=CARD, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", pady=(4, 0))
        self._button(head, "+  Добавить сессию", self._add_key_dialog, "primary").pack(side="right")
        tk.Frame(card, bg=BORDER, height=1).pack(fill="x", padx=16)

        self.keys_list = tk.Frame(card, bg=CARD)
        self.keys_list.pack(fill="both", expand=True, padx=20, pady=18)
        self._render_keys()

        note = tk.Frame(card, bg=CARD_2, highlightbackground=BORDER, highlightthickness=1)
        note.pack(fill="x", padx=20, pady=(0, 20))
        tk.Label(note, text="Перед запуском сценариев закройте окна Chrome, открытые кнопкой «Войти / проверить». Одна включённая сессия обрабатывает один сценарий одновременно.",
                 bg=CARD_2, fg=MUTED, wraplength=950, justify="left").pack(anchor="w", padx=15, pady=12)

    def _render_keys(self):
        for child in self.keys_list.winfo_children():
            child.destroy()
        if not self.settings.chrome_sessions:
            empty = tk.Frame(self.keys_list, bg=CARD)
            empty.pack(expand=True)
            tk.Label(empty, text="⚿", bg=CARD, fg=MUTED_2, font=("Segoe UI", 29)).pack()
            tk.Label(empty, text="Добавьте Chrome-сессию", bg=CARD, fg=TEXT,
                     font=("Segoe UI Semibold", 12)).pack(pady=(10, 5))
            tk.Label(empty, text="Для каждой учётной записи создаётся отдельный локальный профиль Chrome",
                     bg=CARD, fg=MUTED, font=("Segoe UI", 9)).pack()
            return
        for index, entry in enumerate(self.settings.chrome_sessions):
            session_color = "#FF5D73" if entry.limit_status == "exhausted" else ("#35D99A" if entry.active else MUTED)
            row = tk.Frame(self.keys_list, bg=CARD_2, highlightbackground=BLUE if entry.active else BORDER,
                           highlightthickness=1)
            row.pack(fill="x", pady=5)
            radio = tk.Button(row, text="●" if entry.active else "○", command=lambda i=index: self._activate_key(i),
                              bg=CARD_2, fg=session_color, relief="flat", bd=0,
                              activebackground=CARD_2, activeforeground=BLUE, cursor="hand2", font=("Segoe UI", 14))
            radio.pack(side="left", padx=(13, 9), pady=9)
            labels = tk.Frame(row, bg=CARD_2); labels.pack(side="left", fill="x", expand=True)
            tk.Label(labels, text=f"{index + 1}.  {entry.label}", bg=CARD_2, fg=TEXT,
                     font=("Segoe UI Semibold", 10)).pack(anchor="w")
            tk.Label(labels, text=f"Профиль: {entry.profile_id[:12]}", bg=CARD_2, fg=MUTED, font=("Consolas", 8)).pack(anchor="w")
            limit_text = "ЛИМИТ ЗАКОНЧИЛСЯ" if entry.limit_status == "exhausted" else "ЛИМИТ АКТИВЕН"
            tk.Label(labels, text=limit_text, bg=CARD_2, fg=session_color,
                     font=("Segoe UI Semibold", 7)).pack(anchor="w")
            usage_row = tk.Frame(labels, bg=CARD_2)
            usage_row.pack(anchor="w", pady=(4, 0))
            for workflow, label in (("ideas", "Идеи"), ("scenarios", "Ролики"), ("covers", "Обложки"), ("seo", "SEO")):
                variable = tk.BooleanVar(value=entry.usage.get(workflow, True))
                tk.Checkbutton(usage_row, text=label, variable=variable, bg=CARD_2, fg=TEXT, selectcolor=ACTIVE,
                               activebackground=CARD_2, activeforeground=TEXT, font=("Segoe UI", 8), padx=3,
                               command=lambda key=workflow, value=variable, i=index: self._set_session_usage(i, key, value.get())).pack(side="left")
            if entry.active:
                tk.Label(row, text="ВКЛЮЧЕНА", bg="#103D36", fg="#35D99A", padx=9, pady=4,
                         font=("Segoe UI Semibold", 7)).pack(side="right", padx=8)
            self._button(row, "Войти / проверить", lambda i=index: self._open_session(i), "primary").pack(side="right", padx=8, pady=8)
            self._button(row, "Удалить", lambda i=index: self._delete_key(i), "danger").pack(side="right", padx=(8, 12), pady=8)

    def _add_key_dialog(self):
        dialog = tk.Toplevel(self.root, bg=BG)
        dialog.title("Добавить Chrome-сессию")
        dialog.geometry("520x250")
        dialog.resizable(False, False)
        dialog.transient(self.root); dialog.grab_set()
        panel = tk.Frame(dialog, bg=CARD, padx=24, pady=22, highlightbackground=BORDER, highlightthickness=1)
        panel.pack(fill="both", expand=True, padx=18, pady=18)
        tk.Label(panel, text="Новая Chrome-сессия", bg=CARD, fg=TEXT,
                 font=("Segoe UI Semibold", 15)).pack(anchor="w")
        tk.Label(panel, text="Название", bg=CARD, fg=MUTED).pack(anchor="w", pady=(18, 5))
        label = self._entry(panel); label.pack(fill="x", ipady=7); label.insert(0, f"Сессия {len(self.settings.chrome_sessions) + 1}")
        def add():
            session = ChromeSession(label.get().strip() or "Chrome-сессия")
            session.profile_dir.mkdir(parents=True, exist_ok=True)
            self.settings.chrome_sessions.append(session)
            save_settings(self.settings)
            self._update_key_badge(); self._render_keys(); dialog.destroy()
        self._button(panel, "Создать сессию", add, "primary").pack(anchor="e", pady=(20, 0))

    def _open_session(self, index):
        try:
            open_login_window(self.settings.chrome_sessions[index])
        except Exception as exc:
            messagebox.showerror("Chrome-сессия", str(exc), parent=self.root)

    def _activate_key(self, index):
        entry = self.settings.chrome_sessions[index]
        entry.active = not entry.active
        save_settings(self.settings)
        self._render_keys()

    def _set_session_usage(self, index, workflow, enabled):
        self.settings.chrome_sessions[index].usage[workflow] = bool(enabled)
        save_settings(self.settings)

    def _delete_key(self, index):
        entry = self.settings.chrome_sessions[index]
        if not messagebox.askyesno("Удаление", f"Удалить сессию «{entry.label}» и её локальный профиль Chrome?", parent=self.root):
            return
        delete_session_profile(entry)
        del self.settings.chrome_sessions[index]
        save_settings(self.settings)
        self._update_key_badge(); self._render_keys()

    def _page_api_keys(self):
        card = self._card(self.page, fill="both", expand=True, pady=(4, 12))
        head = tk.Frame(card, bg=CARD, padx=20, pady=16)
        head.pack(fill="x")
        copy = tk.Frame(head, bg=CARD)
        copy.pack(side="left")
        tk.Label(copy, text="OpenAI API — резерв для Chrome-сессий", bg=CARD, fg=TEXT,
                 font=("Segoe UI Semibold", 13)).pack(anchor="w")
        tk.Label(copy, text="Ключи зашифрованы Windows DPAPI и используются только для Responses API",
                 bg=CARD, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", pady=(4, 0))
        self._button(head, "+ Добавить ключ", self._add_openai_key, "primary").pack(side="right")

        model_row = tk.Frame(card, bg=CARD_2, padx=16, pady=12)
        model_row.pack(fill="x", padx=20, pady=(0, 12))
        tk.Label(model_row, text="МОДЕЛЬ", bg=CARD_2, fg=MUTED,
                 font=("Segoe UI Semibold", 8)).pack(side="left")
        self.openai_model_entry = self._entry(model_row, width=24)
        self.openai_model_entry.insert(0, self.settings.openai_model)
        self.openai_model_entry.pack(side="left", padx=8, ipady=6)
        self._button(model_row, "Сохранить модель", self._save_openai_model).pack(side="left")
        tk.Label(model_row, text="Chrome используется первым; API берёт свободные задачи и подменяет сессию при лимите.",
                 bg=CARD_2, fg=MUTED, font=("Segoe UI", 8)).pack(side="left", padx=14)

        self.openai_keys_frame = tk.Frame(card, bg=CARD)
        self.openai_keys_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        self._render_openai_keys()

    def _render_openai_keys(self):
        for child in self.openai_keys_frame.winfo_children():
            child.destroy()
        if not self.settings.openai_api_keys:
            tk.Label(self.openai_keys_frame, text="Добавьте OpenAI API-ключ для резервной генерации",
                     bg=CARD, fg=MUTED, font=("Segoe UI", 11)).pack(expand=True)
            return
        for index, entry in enumerate(self.settings.openai_api_keys):
            row = tk.Frame(self.openai_keys_frame, bg=CARD_2, highlightbackground=BLUE if entry.active else BORDER,
                           highlightthickness=1)
            row.pack(fill="x", pady=5)
            tk.Button(row, text="●" if entry.active else "○", command=lambda i=index: self._toggle_openai_key(i),
                      bg=CARD_2, fg="#35D99A" if entry.active else MUTED, relief="flat", bd=0,
                      activebackground=CARD_2, cursor="hand2", font=("Segoe UI", 14)).pack(side="left", padx=12, pady=8)
            labels = tk.Frame(row, bg=CARD_2)
            labels.pack(side="left", fill="x", expand=True)
            tk.Label(labels, text=f"{index + 1}. {entry.label}", bg=CARD_2, fg=TEXT,
                     font=("Segoe UI Semibold", 10)).pack(anchor="w")
            masked = entry.secret[:7] + "••••••••" + entry.secret[-4:] if len(entry.secret) > 12 else "••••••••"
            tk.Label(labels, text=masked, bg=CARD_2, fg=MUTED, font=("Consolas", 8)).pack(anchor="w")
            self._button(row, "Проверить", lambda i=index: self._validate_openai_key(i)).pack(side="right", padx=5, pady=8)
            self._button(row, "Удалить", lambda i=index: self._delete_openai_key(i), "danger").pack(side="right", padx=8, pady=8)

    def _add_openai_key(self):
        label = self._ask_text("OpenAI API", "Название ключа:", f"OpenAI {len(self.settings.openai_api_keys) + 1}")
        if not label:
            return
        secret = self._ask_text("OpenAI API", "Вставьте API-ключ:", secret=True)
        if not secret:
            return
        self.settings.openai_api_keys.append(OpenAIKey(label.strip(), secret.strip(), True))
        save_settings(self.settings)
        self._render_openai_keys()

    def _toggle_openai_key(self, index):
        self.settings.openai_api_keys[index].active = not self.settings.openai_api_keys[index].active
        save_settings(self.settings)
        self._render_openai_keys()

    def _delete_openai_key(self, index):
        entry = self.settings.openai_api_keys[index]
        if messagebox.askyesno("OpenAI API", f"Удалить ключ «{entry.label}»?", parent=self.root):
            del self.settings.openai_api_keys[index]
            save_settings(self.settings)
            self._render_openai_keys()

    def _save_openai_model(self):
        self.settings.openai_model = self.openai_model_entry.get().strip() or "gpt-5.6"
        save_settings(self.settings)
        messagebox.showinfo("OpenAI API", "Модель сохранена", parent=self.root)

    def _validate_openai_key(self, index):
        entry = self.settings.openai_api_keys[index]
        self.system_status.config(text="Проверка OpenAI API…")
        def work():
            try:
                OpenAITextClient(entry.secret, self.settings.openai_model, entry.label).validate()
                self.events.put(("openai_key_valid", entry.label))
            except Exception as exc:
                self.events.put(("openai_key_error", str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def _transfer_to_seo(self):
        completed = [job for job in self.jobs if job.state == RunState.DONE]
        if not completed:
            messagebox.showinfo("SEO-пакеты", "Нет готовых сценариев для переноса", parent=self.root)
            return
        existing = {item["source_title"] for item in self.seo_items}
        for job in completed:
            if job.request.title not in existing:
                self.seo_items.append({"source_title": job.request.title, "script": job.result, "status": "Ожидает",
                                       "title": "", "description": "", "tags": "", "error": ""})
        self._show_page("seo")

    def _page_analytics(self):
        top = self._card(self.page, fill="x", pady=(4, 12))
        row = tk.Frame(top, bg=CARD, padx=18, pady=15)
        row.pack(fill="x")
        tk.Label(row, text="Подключённые каналы", bg=CARD, fg=TEXT,
                 font=("Segoe UI Semibold", 13)).pack(side="left")
        self._button(row, "+ Добавить канал", self._add_analytics_channel, "primary").pack(side="right")
        self._button(row, "Обновить аналитику", self._refresh_analytics, "success").pack(side="right", padx=8)
        oauth = self.settings.google_oauth_client_file
        tk.Label(top, text=(f"Google OAuth: {Path(oauth).name}" if oauth else "Google OAuth не подключён — добавьте client_secret.json для закрытой аналитики и дохода"),
                 bg=CARD, fg="#35D99A" if oauth else "#F5C451", font=("Segoe UI", 8), anchor="w").pack(fill="x", padx=18, pady=(0, 12))

        metrics = tk.Frame(self.page, bg=BG)
        metrics.pack(fill="x", pady=(0, 12))
        for value, label in ((str(len(self.settings.analytics_channels)), "КАНАЛОВ"), ("—", "ПРОСМОТРЫ ЗА 48 Ч."),
                             ("—", "ДОХОД"), ("—", "МОНЕТИЗАЦИЯ")):
            card = tk.Frame(metrics, bg=CARD, highlightbackground=BORDER, highlightthickness=1, width=220, height=82)
            card.pack(side="left", fill="x", expand=True, padx=4)
            card.pack_propagate(False)
            tk.Label(card, text=value, bg=CARD, fg=TEXT, font=("Segoe UI Semibold", 17)).pack(anchor="w", padx=14, pady=(14, 0))
            tk.Label(card, text=label, bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 8)).pack(anchor="w", padx=14)

        table_card = self._card(self.page, fill="both", expand=True)
        self.analytics_table = ttk.Treeview(table_card, columns=("name", "channel", "subs", "hour", "hours48", "income", "status"), show="headings")
        for key, label, width in (("name", "КАНАЛ", 190), ("channel", "ID / ССЫЛКА", 220), ("subs", "ПОДПИСЧИКИ", 110),
                                  ("hour", "1 ЧАС", 80), ("hours48", "48 ЧАСОВ", 100), ("income", "ДОХОД", 100), ("status", "СТАТУС", 140)):
            self.analytics_table.heading(key, text=label); self.analytics_table.column(key, width=width, anchor="w")
        self.analytics_table.pack(fill="both", expand=True, padx=18, pady=18)
        for index, item in enumerate(self.settings.analytics_channels):
            self.analytics_table.insert("", "end", iid=str(index), values=(item.get("name", "Канал"), item.get("channel", ""),
                item.get("subscribers", "—"), item.get("views_hour", "—"), item.get("views_48h", "—"),
                item.get("revenue", "—"), item.get("status", "Ожидает обновления")))
        actions = tk.Frame(table_card, bg=CARD)
        actions.pack(fill="x", padx=18, pady=(0, 16))
        self._button(actions, "Войти в выбранный канал", self._open_selected_analytics_channel, "primary").pack(side="left")
        self._button(actions, "Удалить канал", self._delete_selected_analytics_channel, "danger").pack(side="left", padx=8)
        tk.Label(actions, text="Вход открывается в отдельном постоянном профиле Chrome и не очищается при перезапуске.",
                 bg=CARD, fg=MUTED, font=("Segoe UI", 8)).pack(side="left", padx=10)

    def _add_analytics_channel(self):
        dialog = tk.Toplevel(self.root, bg=BG); dialog.title("Добавить канал YouTube"); dialog.geometry("580x290")
        panel = tk.Frame(dialog, bg=CARD, padx=22, pady=20); panel.pack(fill="both", expand=True, padx=16, pady=16)
        tk.Label(panel, text="Название канала", bg=CARD, fg=MUTED).pack(anchor="w")
        name = self._entry(panel); name.pack(fill="x", pady=(4, 12), ipady=7)
        tk.Label(panel, text="ID канала или ссылка", bg=CARD, fg=MUTED).pack(anchor="w")
        channel = self._entry(panel); channel.pack(fill="x", pady=(4, 12), ipady=7)
        def add():
            if not name.get().strip() or not channel.get().strip():
                return
            self.settings.analytics_channels.append({
                "name": name.get().strip(), "channel": channel.get().strip(),
                "profile_id": uuid.uuid4().hex, "status": "Ожидает обновления",
            })
            save_settings(self.settings); dialog.destroy(); self._show_page("analytics")
        self._button(panel, "Добавить", add, "primary").pack(anchor="e")

    def _analytics_profile_dir(self, channel: dict) -> Path:
        profile_id = channel.get("profile_id") or uuid.uuid4().hex
        if not channel.get("profile_id"):
            channel["profile_id"] = profile_id
            save_settings(self.settings)
        return app_data_root() / "YouTubeChannelProfiles" / profile_id

    def _open_selected_analytics_channel(self):
        selected = self.analytics_table.selection() if hasattr(self, "analytics_table") else ()
        if not selected:
            messagebox.showinfo("Каналы", "Выберите канал в таблице", parent=self.root)
            return
        channel = self.settings.analytics_channels[int(selected[0])]
        profile = self._analytics_profile_dir(channel)
        profile.mkdir(parents=True, exist_ok=True)
        target = channel.get("channel", "").strip()
        url = target if target.startswith("https://") else "https://studio.youtube.com/"
        try:
            subprocess.Popen([str(chrome_path()), f"--user-data-dir={profile}",
                              "--no-first-run", "--no-default-browser-check", url])
        except Exception as exc:
            messagebox.showerror("Каналы", str(exc), parent=self.root)

    def _delete_selected_analytics_channel(self):
        selected = self.analytics_table.selection() if hasattr(self, "analytics_table") else ()
        if not selected:
            return
        index = int(selected[0])
        channel = self.settings.analytics_channels[index]
        if not messagebox.askyesno("Каналы", f"Удалить канал «{channel.get('name', '')}» из NewsFlow?", parent=self.root):
            return
        # The saved browser profile is deliberately kept: user credentials are
        # removed only by an explicit request outside this routine.
        del self.settings.analytics_channels[index]
        save_settings(self.settings)
        self._show_page("analytics")

    def _refresh_analytics(self):
        if not self.settings.google_oauth_client_file:
            path = filedialog.askopenfilename(parent=self.root, title="Выберите Google OAuth client_secret.json",
                                              filetypes=[("Google OAuth JSON", "*.json")])
            if not path:
                return
            self.settings.google_oauth_client_file = path
            save_settings(self.settings)
        messagebox.showinfo("Аналитика", "OAuth-файл сохранён. Следующим шагом подключим вход Google и загрузку реальных показателей по кнопке «Обновить».", parent=self.root)
        self._show_page("analytics")

    def _page_seo(self):
        settings_card = self._card(self.page, fill="x", pady=(4, 12))
        top = tk.Frame(settings_card, bg=CARD, padx=18, pady=14)
        top.pack(fill="x")
        route = tk.Frame(top, bg=CARD)
        route.pack(fill="x")
        tk.Label(route, text="ГЕНЕРАЦИЯ ЧЕРЕЗ", bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 8)).pack(side="left")
        self.seo_provider_combo = ttk.Combobox(route, state="readonly", style="Dark.TCombobox", width=22,
                                                values=("Claude — Chrome-сессия", "OpenAI — API"))
        self.seo_provider_combo.set("Claude — Chrome-сессия")
        self.seo_provider_combo.pack(side="left", padx=(8, 4), ipady=6)
        self.seo_provider_combo.bind("<<ComboboxSelected>>", lambda _: self._on_seo_provider_changed())
        tk.Label(route, text="ПРОФИЛЬ / КЛЮЧ", bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 8)).pack(side="left")
        self.seo_session_entries = self._sessions_for("seo")
        self.seo_session_combo = ttk.Combobox(route, state="readonly", style="Dark.TCombobox", width=25,
            values=[f"{i + 1}. {item.label}" for i, item in enumerate(self.seo_session_entries)])
        if self.seo_session_entries:
            self.seo_session_combo.current(0)
        self.seo_session_combo.pack(side="left", padx=8, ipady=6)
        self.seo_session_combo.bind("<<ComboboxSelected>>", lambda _: self._load_seo_chat_binding())
        tk.Label(route, text="ЧАТ", bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 8)).pack(side="left", padx=(10, 5))
        self.seo_chat_entry = self._entry(route)
        self.seo_chat_entry.pack(side="left", fill="x", expand=True, ipady=7)
        self._button(route, "Открыть", self._open_seo_chat).pack(side="left", padx=(8, 4))
        self._button(route, "Сохранить чат", self._save_seo_chat_binding, "primary").pack(side="left", padx=4)
        self._load_seo_chat_binding()

        tk.Label(top, text="ШАБЛОН SEO-ПРОМПТА", bg=CARD, fg=MUTED,
                 font=("Segoe UI Semibold", 8)).pack(anchor="w", pady=(12, 5))
        self.seo_prompt_widget = tk.Text(top, height=4, bg=CARD_2, fg=TEXT, insertbackground=TEXT, relief="flat",
                                         padx=12, pady=10, wrap="word", font=("Segoe UI", 9),
                                         highlightbackground=BORDER, highlightthickness=1)
        self.seo_prompt_widget.insert("1.0", self.settings.seo_prompt_template)
        self.seo_prompt_widget.pack(fill="x")
        self._install_edit_bindings(self.seo_prompt_widget, multiline=True)

        results = self._card(self.page, fill="both", expand=True)
        actions = tk.Frame(results, bg=CARD)
        actions.pack(fill="x", padx=18, pady=12)
        tk.Label(actions, text=f"Тем для SEO: {len(self.seo_items)}", bg=CARD, fg=TEXT,
                 font=("Segoe UI Semibold", 11)).pack(side="left")
        self.seo_generate_button = self._button(actions, "Создать SEO-пакеты", self._generate_seo, "success")
        self.seo_generate_button.pack(side="right")
        self._button(actions, "Сохранить всё", self._export_seo_all, "primary").pack(side="right", padx=8)
        self._button(actions, "Всё в одном TXT", self._export_seo_combined).pack(side="right", padx=4)
        self._button(actions, "По отдельности", self._export_seo_separate).pack(side="right", padx=4)
        self._button(actions, "Удалить выбранные", self._delete_seo_items, "danger").pack(side="right")
        self.seo_table = ttk.Treeview(results, columns=("num", "source", "status", "title", "tags"), show="headings",
                                      selectmode="extended")
        for key, label in (("num", "#"), ("source", "ИСХОДНАЯ ТЕМА"), ("status", "СТАТУС"),
                           ("title", "SEO-ЗАГОЛОВОК"), ("tags", "ТЕГИ")):
            self.seo_table.heading(key, text=label)
        self.seo_table.column("num", width=45, anchor="center", stretch=False)
        self.seo_table.column("source", width=280)
        self.seo_table.column("status", width=100, anchor="center", stretch=False)
        self.seo_table.column("title", width=360)
        self.seo_table.column("tags", width=280)
        self.seo_table.pack(fill="both", expand=True, padx=18, pady=(0, 18))
        self.seo_table.bind("<Double-1>", lambda _: self._show_seo_item())
        self._render_seo_items()

    def _seo_provider(self):
        return "openai" if self.seo_provider_combo.get().startswith("OpenAI") else "claude"

    def _on_seo_provider_changed(self):
        use_openai = self._seo_provider() == "openai"
        self.seo_session_entries = ([item for item in self.settings.openai_api_keys if item.active and item.secret]
                                    if use_openai else self._sessions_for("seo"))
        self.seo_session_combo.config(values=[f"{index + 1}. {item.label}" for index, item in enumerate(self.seo_session_entries)])
        if self.seo_session_entries:
            self.seo_session_combo.current(0)
        if use_openai:
            self.seo_chat_entry.delete(0, "end")
            self.seo_chat_entry.insert(0, "OpenAI API — ссылка на чат не нужна")
            self.seo_chat_entry.config(state="disabled")
        else:
            self.seo_chat_entry.config(state="normal")
            self._load_seo_chat_binding()

    def _selected_seo_route(self):
        index = self.seo_session_combo.current()
        if not 0 <= index < len(self.seo_session_entries):
            raise ValueError("Добавьте подходящую сессию Claude или OpenAI API-ключ")
        return self._seo_provider(), self.seo_session_entries[index]

    def _generate_seo(self):
        if self.seo_running:
            return
        try:
            provider, route = self._selected_seo_route()
            if provider == "claude" and not route.active:
                raise ValueError("Выбранная Chrome-сессия выключена")
            chat_url = self.seo_chat_entry.get().strip() or "https://claude.ai/new"
            if provider == "claude":
                self._store_seo_chat_binding(route, chat_url)
            template = self.seo_prompt_widget.get("1.0", "end-1c").strip()
            self.settings.seo_prompt_template = template
            save_settings(self.settings)
            pending = [item for item in self.seo_items if item["status"] != "Готово"]
            if not pending:
                raise ValueError("Нет тем, ожидающих SEO-генерацию")
            self.seo_running = True
            self.seo_generate_button.config(state="disabled")
            def work():
                for item in pending:
                    item["status"] = "Генерация"
                    self.events.put(("seo_job", item))
                    excerpt = " ".join(item["script"].split())[:1800]
                    prompt = template.replace("{title}", item["source_title"]).replace("{excerpt}", excerpt)
                    try:
                        if provider == "openai":
                            pool = HybridTextPool([], [route], "", self.settings.openai_model)
                        else:
                            sessions = [route] + [item for item in self._sessions_for("seo") if item.profile_id != route.profile_id]
                            pool = self._text_pool(sessions, chat_url)
                        raw = asyncio.run(pool.generate(prompt))
                        parsed = self._parse_seo_json(raw)
                        item.update(status="Готово", title=parsed["title"], description=parsed["description"],
                                    tags=", ".join(parsed["tags"]), error="")
                    except Exception as exc:
                        item.update(status="Ошибка", error=str(exc))
                    self.events.put(("seo_job", item))
                self.events.put(("seo_complete", None))
            threading.Thread(target=work, daemon=True).start()
        except Exception as exc:
            messagebox.showerror("SEO-пакеты", str(exc), parent=self.root)

    def _selected_seo_session(self):
        index = self.seo_session_combo.current()
        if not 0 <= index < len(self.seo_session_entries):
            raise ValueError("Выберите Chrome-сессию")
        return self.seo_session_entries[index]

    def _seo_chat_binding(self, session):
        return next((item for item in self.settings.seo_chat_bindings
                     if item.get("profile_id") == session.profile_id), None)

    def _load_seo_chat_binding(self):
        if not hasattr(self, "seo_chat_entry") or not self.seo_chat_entry.winfo_exists():
            return
        if hasattr(self, "seo_provider_combo") and self._seo_provider() == "openai":
            return
        try:
            session = self._selected_seo_session()
            binding = self._seo_chat_binding(session)
            url = binding.get("chat_url", "https://claude.ai/new") if binding else "https://claude.ai/new"
        except ValueError:
            url = "https://claude.ai/new"
        self.seo_chat_entry.delete(0, "end")
        self.seo_chat_entry.insert(0, url)

    def _store_seo_chat_binding(self, session, url):
        if not url.startswith("https://claude.ai/"):
            raise ValueError("Вставьте ссылку на чат с сайта claude.ai")
        binding = self._seo_chat_binding(session)
        data = {"profile_id": session.profile_id, "chat_url": url}
        if binding:
            binding.update(data)
        else:
            self.settings.seo_chat_bindings.append(data)
        save_settings(self.settings)

    def _save_seo_chat_binding(self):
        try:
            if self._seo_provider() == "openai":
                messagebox.showinfo("SEO-пакеты", "OpenAI использует API-ключ; ссылка на обычный чат не нужна.", parent=self.root)
                return
            session = self._selected_seo_session()
            url = self.seo_chat_entry.get().strip() or "https://claude.ai/new"
            self._store_seo_chat_binding(session, url)
            messagebox.showinfo("SEO-пакеты", f"Чат сохранён для сессии «{session.label}»", parent=self.root)
        except Exception as exc:
            messagebox.showerror("SEO-пакеты", str(exc), parent=self.root)

    def _open_seo_chat(self):
        try:
            if self._seo_provider() == "openai":
                messagebox.showinfo("SEO-пакеты", "OpenAI работает через API-ключ, не через ссылку обычного ChatGPT-чата.", parent=self.root)
                return
            session = self._selected_seo_session()
            url = self.seo_chat_entry.get().strip() or "https://claude.ai/new"
            open_login_window(session, url)
        except Exception as exc:
            messagebox.showerror("SEO-пакеты", str(exc), parent=self.root)

    @staticmethod
    def _parse_seo_json(raw):
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not match:
            raise ValueError("Claude не вернул SEO-данные в формате JSON")
        data = json.loads(match.group(0))
        tags = data.get("tags", [])
        if isinstance(tags, str):
            tags = [value.strip() for value in tags.split(",") if value.strip()]
        return {"title": str(data.get("title", "")).strip(),
                "description": str(data.get("description", "")).strip(), "tags": tags}

    def _render_seo_items(self):
        if not hasattr(self, "seo_table") or not self.seo_table.winfo_exists():
            return
        self.seo_table.delete(*self.seo_table.get_children())
        for index, item in enumerate(self.seo_items):
            tags = item.get("tags") or item.get("error", "")
            self.seo_table.insert("", "end", iid=str(index), values=(index + 1, item["source_title"], item["status"],
                                                                      item.get("title", ""), tags))

    def _delete_seo_items(self):
        if self.seo_running:
            return
        selected = {int(value) for value in self.seo_table.selection()}
        self.seo_items = [item for index, item in enumerate(self.seo_items) if index not in selected]
        self._render_seo_items()

    def _show_seo_item(self):
        selected = self.seo_table.selection()
        if not selected:
            return
        item = self.seo_items[int(selected[0])]
        window = tk.Toplevel(self.root, bg=BG)
        window.title(item["source_title"])
        window.geometry("850x650")
        text = tk.Text(window, bg=CARD, fg=TEXT, insertbackground=TEXT, wrap="word", padx=20, pady=20,
                       relief="flat", font=("Segoe UI", 10))
        text.pack(fill="both", expand=True, padx=16, pady=16)
        text.insert("1.0", f"SEO-ЗАГОЛОВОК\n{item.get('title', '')}\n\nОПИСАНИЕ\n{item.get('description', '')}\n\nТЕГИ\n{item.get('tags', '')}")

    def _ready_seo_items(self):
        ready = [item for item in self.seo_items if item["status"] == "Готово"]
        if not ready:
            messagebox.showinfo("SEO-пакеты", "Нет готовых SEO-пакетов", parent=self.root)
            return []
        return ready

    @staticmethod
    def _seo_item_text(item, number=None):
        prefix = f"{number}. " if number is not None else ""
        return (
            f"{prefix}ТЕМА\n{item['source_title']}\n\n"
            f"SEO-ЗАГОЛОВОК\n{item['title']}\n\n"
            f"SEO-ОПИСАНИЕ\n{item['description']}\n\n"
            f"ТЕГИ\n{item['tags']}\n"
        )

    def _export_seo_separate(self, open_folder=True):
        ready = self._ready_seo_items()
        if not ready:
            return 0
        folder = Path(self.settings.seo_output_folder)
        folder.mkdir(parents=True, exist_ok=True)
        for number, item in enumerate(ready, 1):
            path = folder / f"{number:03d} — {safe_filename(item['source_title'])} — SEO.txt"
            path.write_text(self._seo_item_text(item, number), encoding="utf-8-sig")
        if open_folder:
            os.startfile(folder)
        return len(ready)

    def _export_seo_combined(self, open_folder=True):
        ready = self._ready_seo_items()
        if not ready:
            return 0
        folder = Path(self.settings.seo_output_folder)
        folder.mkdir(parents=True, exist_ok=True)
        divider = "\n\n" + ("=" * 72) + "\n\n"
        content = divider.join(self._seo_item_text(item, number) for number, item in enumerate(ready, 1))
        (folder / "Все SEO-пакеты.txt").write_text(content + "\n", encoding="utf-8-sig")
        if open_folder:
            os.startfile(folder)
        return len(ready)

    def _export_seo_all(self):
        count = self._export_seo_separate(open_folder=False)
        if not count:
            return
        self._export_seo_combined(open_folder=False)
        folder = Path(self.settings.seo_output_folder)
        os.startfile(folder)
        messagebox.showinfo(
            "SEO-пакеты",
            f"Сохранено тем: {count}\n\nСозданы отдельные TXT и общий файл «Все SEO-пакеты.txt».",
            parent=self.root,
        )

    def _transfer_to_covers(self):
        completed = [job for job in self.jobs if job.state == RunState.DONE]
        if not completed:
            messagebox.showinfo("Обложки", "Нет готовых сценариев для переноса", parent=self.root)
            return
        existing = {item["title"] for item in self.cover_items}
        for job in completed:
            if job.request.title not in existing:
                self.cover_items.append({"title": job.request.title, "script": job.result,
                                         "status": "Ожидает", "path": "", "error": ""})
        self._save_cover_queue()
        self._show_page("covers")

    def _save_cover_queue(self):
        self.settings.cover_queue = self.cover_items
        save_settings(self.settings)

    def _page_covers(self):
        settings_card = self._card(self.page, fill="x", pady=(4, 12))
        top = tk.Frame(settings_card, bg=CARD, padx=18, pady=15)
        top.pack(fill="x")
        presets = tk.Frame(top, bg=CARD_2, padx=10, pady=8, highlightbackground=BORDER, highlightthickness=1)
        presets.pack(fill="x", pady=(0, 9))
        tk.Label(presets, text="СОХРАНЁННЫЙ ПРЕСЕТ ПРОМПТОВ", bg=CARD_2, fg=MUTED,
                 font=("Segoe UI Semibold", 8)).pack(side="left", padx=(0, 8))
        self.cover_route_preset_combo = ttk.Combobox(presets, state="readonly", style="Dark.TCombobox", width=34)
        self.cover_route_preset_combo.pack(side="left", ipady=5)
        self._button(presets, "Применить", self._apply_cover_route_preset).pack(side="left", padx=7)
        self._button(presets, "Сохранить как…", self._save_cover_route_preset, "primary").pack(side="left")
        self._button(presets, "Удалить", self._delete_cover_route_preset, "danger").pack(side="left", padx=7)
        route = tk.Frame(top, bg=CARD)
        route.pack(fill="x", pady=(0, 12))
        tk.Label(route, text="ПРОМПТЫ ЧЕРЕЗ", bg=CARD, fg=MUTED,
                 font=("Segoe UI Semibold", 8)).pack(side="left")
        self.cover_provider_combo = ttk.Combobox(route, state="readonly", style="Dark.TCombobox", width=22,
                                                  values=("Claude — Chrome-сессия", "OpenAI — API"))
        self.cover_provider_combo.set("Claude — Chrome-сессия")
        self.cover_provider_combo.pack(side="left", padx=(8, 4), ipady=6)
        self.cover_provider_combo.bind("<<ComboboxSelected>>", lambda _: self._on_cover_provider_changed())
        tk.Label(route, text="ПРОФИЛЬ / КЛЮЧ", bg=CARD, fg=MUTED,
                 font=("Segoe UI Semibold", 8)).pack(side="left", padx=(4, 0))
        self.cover_session_entries = self._sessions_for("covers")
        self.cover_session_combo = ttk.Combobox(
            route, state="readonly", style="Dark.TCombobox", width=24,
            values=[f"{i + 1}. {item.label}" for i, item in enumerate(self.cover_session_entries)])
        if self.cover_session_entries:
            self.cover_session_combo.current(0)
        self.cover_session_combo.pack(side="left", padx=8, ipady=6)
        self.cover_session_combo.bind("<<ComboboxSelected>>", lambda _: self._load_cover_chat_binding())
        self.cover_limit_label = tk.Label(route, text="●", bg=CARD, fg=MUTED, font=("Segoe UI", 14))
        self.cover_limit_label.pack(side="left", padx=(0, 7))
        tk.Label(route, text="ЧАТ", bg=CARD, fg=MUTED,
                 font=("Segoe UI Semibold", 8)).pack(side="left")
        self.cover_chat_entry = self._entry(route)
        self.cover_chat_entry.pack(side="left", fill="x", expand=True, padx=7, ipady=7)
        self._button(route, "Открыть", self._open_cover_chat).pack(side="left", padx=4)
        self._button(route, "Сохранить чат", self._save_cover_chat_binding, "primary").pack(side="left", padx=4)
        self._load_cover_chat_binding()
        self._refresh_cover_route_presets()

        tk.Label(top, text="FastGen API", bg=CARD, fg=TEXT, font=("Segoe UI Semibold", 12)).pack(anchor="w")
        api_row = tk.Frame(top, bg=CARD)
        api_row.pack(fill="x", pady=(10, 0))
        active_keys = sum(item.active for item in self.settings.cover_api_keys)
        self.cover_keys_label = tk.Label(api_row, text=f"КЛЮЧИ FASTGEN: {active_keys} ВКЛЮЧЕНО / {len(self.settings.cover_api_keys)} ВСЕГО",
                                         bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 8))
        self.cover_keys_label.pack(side="left")
        self._button(api_row, "⚿  Управление ключами", self._manage_cover_keys, "primary").pack(side="right")
        self._button(api_row, "Проверить ключ", self._validate_cover_key).pack(side="left")
        self._button(api_row, "Обновить лимиты", self._check_fastgen_usage).pack(side="left", padx=(8, 0))
        self._button(api_row, "Сохранить настройки", self._save_cover_settings).pack(side="left", padx=(8, 0))
        self.cover_usage_label = tk.Label(top, text=self._fastgen_usage_summary(), bg=CARD, fg="#35D99A",
                                          font=("Segoe UI Semibold", 8), anchor="w")
        self.cover_usage_label.pack(fill="x", pady=(8, 0))

        options = tk.Frame(top, bg=CARD)
        options.pack(fill="x", pady=(12, 0))
        tk.Label(options, text="МОДЕЛЬ", bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 8)).pack(side="left")
        self.cover_operation_combo = ModelSelector(options, self._fastgen_models("image", COVER_MODELS), self.fastgen_model_status,
                                                    self.settings.cover_operation, width=34)
        self.cover_operation_combo.pack(side="left", padx=(8, 18), ipady=6)
        tk.Label(options, text="ФОРМАТ", bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 8)).pack(side="left")
        self.cover_ratio_combo = ttk.Combobox(options, state="readonly", style="Dark.TCombobox", width=9,
                                              values=("16:9", "9:16", "1:1"))
        self.cover_ratio_combo.set(self.settings.cover_aspect_ratio)
        self.cover_ratio_combo.pack(side="left", padx=8, ipady=6)
        tk.Label(options, text="ВАРИАНТОВ", bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 8)).pack(side="left", padx=(10, 5))
        self.cover_variants_combo = ttk.Combobox(options, state="readonly", style="Dark.TCombobox", width=4,
                                                 values=("1", "2", "3", "4", "5", "6"))
        self.cover_variants_combo.set(str(self.settings.cover_variant_count))
        self.cover_variants_combo.pack(side="left", padx=4, ipady=6)
        tk.Label(options, text="SEED", bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 8)).pack(side="left", padx=(10, 5))
        self.cover_seed_entry = self._entry(options, width=10)
        self.cover_seed_entry.pack(side="left", ipady=7)
        self.cover_upscale_var = tk.BooleanVar(value=False)
        tk.Checkbutton(options, text="Апскейл 2×", variable=self.cover_upscale_var, bg=CARD, fg=TEXT,
                       selectcolor=CARD_2, activebackground=CARD, activeforeground=TEXT).pack(side="left", padx=10)
        self._button(options, "Открыть папку", self._open_cover_folder).pack(side="right")

        refs = tk.Frame(top, bg=CARD_2, highlightbackground=BORDER, highlightthickness=1)
        refs.pack(fill="x", pady=(10, 0))
        self.cover_refs_label = tk.Label(refs, text=f"РЕФЕРЕНСЫ: {len(self.cover_references)}/10", bg=CARD_2, fg=MUTED,
                                         font=("Segoe UI Semibold", 8))
        self.cover_refs_label.pack(side="left", padx=12, pady=9)
        self._button(refs, "+ Добавить изображения", lambda: self._add_references("cover"), "primary").pack(side="left", pady=5)
        self._button(refs, "Очистить", lambda: self._clear_references("cover"), "danger").pack(side="left", padx=7, pady=5)
        self.cover_refs_names = tk.Label(refs, text=self._reference_names(self.cover_references), bg=CARD_2, fg=TEXT,
                                         anchor="w", font=("Segoe UI", 8))
        self.cover_refs_names.pack(side="left", fill="x", expand=True, padx=8)

        prompt_card = self._card(self.page, fill="x", pady=(0, 12))
        prompt_head = tk.Frame(prompt_card, bg=CARD)
        prompt_head.pack(fill="x", padx=18, pady=(13, 7))
        tk.Label(prompt_head, text="Ваш шаблон и пример промпта для обложки", bg=CARD, fg=TEXT,
                 font=("Segoe UI Semibold", 11)).pack(side="left")
        tk.Label(prompt_head, text="Переменные: {title}, {excerpt}", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="right")
        self.cover_prompt_widget = tk.Text(prompt_card, height=4, bg=CARD_2, fg=TEXT, insertbackground=TEXT,
                                           relief="flat", padx=12, pady=10, wrap="word", font=("Segoe UI", 9),
                                           highlightbackground=BORDER, highlightthickness=1)
        self.cover_prompt_widget.insert("1.0", self.settings.cover_prompt_template)
        self.cover_prompt_widget.pack(fill="x", padx=18, pady=(0, 14))
        self._install_edit_bindings(self.cover_prompt_widget, multiline=True)
        tk.Label(prompt_card, text="Пример: «Крупный план нефтяного танкера в Ормузском проливе, тревожное небо, сильный контраст, свободная зона слева под заголовок, без текста на изображении». Ваш шаблон выше добавляется к теме и сценарию.",
                 bg=CARD, fg=MUTED, wraplength=980, justify="left", font=("Segoe UI", 8)).pack(anchor="w", padx=18, pady=(0, 12))

        queue_card = self._card(self.page, fill="both", expand=True)
        actions = tk.Frame(queue_card, bg=CARD)
        actions.pack(fill="x", padx=18, pady=12)
        tk.Label(actions, text=f"Сценариев для обложек: {len(self.cover_items)}", bg=CARD, fg=TEXT,
                 font=("Segoe UI Semibold", 11)).pack(side="left")
        self._button(actions, "+ Взять готовые сценарии", self._transfer_to_covers).pack(side="left", padx=10)
        self.cover_generate_button = self._button(actions, "Создать обложки", self._generate_covers, "success")
        self.cover_generate_button.pack(side="right")
        self.cover_prompt_button = self._button(actions, "Создать промпты в Claude", self._generate_cover_prompts, "primary")
        self.cover_prompt_button.pack(side="right", padx=8)
        self._button(actions, "Удалить диапазон", self._delete_cover_range).pack(side="right", padx=4)
        self._button(actions, "Удалить выбранные", self._delete_cover_items, "danger").pack(side="right", padx=8)

        self.cover_table = ttk.Treeview(queue_card, columns=("num", "title", "prompt", "status", "result"), show="headings",
                                        selectmode="extended")
        for key, label in (("num", "#"), ("title", "СЦЕНАРИЙ"), ("prompt", "ПРОМПТ CLAUDE"),
                           ("status", "СТАТУС"), ("result", "ФАЙЛ / ОШИБКА")):
            self.cover_table.heading(key, text=label)
        self.cover_table.column("num", width=45, anchor="center", stretch=False)
        self.cover_table.column("title", width=260)
        self.cover_table.column("prompt", width=350)
        self.cover_table.column("status", width=120, anchor="center", stretch=False)
        self.cover_table.column("result", width=330)
        self.cover_table.pack(fill="both", expand=True, padx=18, pady=(0, 12))
        self.cover_table.bind("<Double-1>", lambda _: self._open_selected_cover())

        self.cover_gallery = tk.Frame(queue_card, bg=CARD_2, padx=12, pady=12,
                                      highlightbackground=BORDER, highlightthickness=1)
        self.cover_gallery.pack(fill="x", padx=18, pady=(0, 18))
        gallery_head = tk.Frame(self.cover_gallery, bg=CARD_2)
        gallery_head.pack(fill="x")
        tk.Label(gallery_head, text="Варианты обложек — выберите лучший для каждого сценария", bg=CARD_2, fg=TEXT,
                 font=("Segoe UI Semibold", 10)).pack(side="left")
        tk.Label(gallery_head, text="Клик по варианту назначает его основным", bg=CARD_2, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="right")
        self.cover_gallery_body = tk.Frame(self.cover_gallery, bg=CARD_2)
        self.cover_gallery_body.pack(fill="x", pady=(10, 0))
        self._render_cover_items()

    def _manage_cover_keys(self):
        dialog = tk.Toplevel(self.root, bg=BG)
        dialog.title("Ключи FastGen")
        dialog.geometry("760x520")
        dialog.transient(self.root)
        panel = tk.Frame(dialog, bg=CARD, padx=20, pady=18)
        panel.pack(fill="both", expand=True, padx=16, pady=16)
        head = tk.Frame(panel, bg=CARD)
        head.pack(fill="x")
        tk.Label(head, text="Ключи FastGen API", bg=CARD, fg=TEXT,
                 font=("Segoe UI Semibold", 14)).pack(side="left")
        keys_frame = tk.Frame(panel, bg=CARD)
        keys_frame.pack(fill="both", expand=True, pady=(14, 0))

        def refresh():
            for child in keys_frame.winfo_children():
                child.destroy()
            if not self.settings.cover_api_keys:
                tk.Label(keys_frame, text="Добавьте первый ключ FastGen", bg=CARD, fg=MUTED,
                         font=("Segoe UI", 11)).pack(expand=True)
            for index, entry in enumerate(self.settings.cover_api_keys):
                row = tk.Frame(keys_frame, bg=CARD_2, highlightbackground=BLUE if entry.active else BORDER,
                               highlightthickness=1)
                row.pack(fill="x", pady=5)
                tk.Button(row, text="●" if entry.active else "○", command=lambda i=index: toggle(i),
                          bg=CARD_2, fg="#35D99A" if entry.active else MUTED, relief="flat", bd=0,
                          activebackground=CARD_2, cursor="hand2", font=("Segoe UI", 14)).pack(side="left", padx=12, pady=8)
                labels = tk.Frame(row, bg=CARD_2)
                labels.pack(side="left", fill="x", expand=True)
                tk.Label(labels, text=f"{index + 1}.  {entry.label}", bg=CARD_2, fg=TEXT,
                         font=("Segoe UI Semibold", 10)).pack(anchor="w")
                masked = entry.secret[:5] + "••••••••" + entry.secret[-4:] if len(entry.secret) > 10 else "••••••••"
                tk.Label(labels, text=masked, bg=CARD_2, fg=MUTED, font=("Consolas", 8)).pack(anchor="w")
                cached = next((item.get("usage") for item in self.fastgen_usage
                               if item.get("label") == entry.label and item.get("usage")), None)
                if cached:
                    image_left = self._usage_remaining(cached, "image_generation", "img_gen_per_hour_limit")[2]
                    video_left = self._usage_remaining(cached, "video_generation", "video_gen_per_hour_limit")[2]
                    prompt_left = self._usage_remaining(cached, "prompt_generation", "prompt_tokens_per_hour_limit")[2]
                    tk.Label(labels, text=f"Осталось/час: фото {image_left} • видео {video_left} • токены {prompt_left}",
                             bg=CARD_2, fg="#35D99A", font=("Segoe UI", 8)).pack(anchor="w")
                self._button(row, "Удалить", lambda i=index: remove(i), "danger").pack(side="right", padx=10, pady=8)

        def toggle(index):
            self.settings.cover_api_keys[index].active = not self.settings.cover_api_keys[index].active
            save_settings(self.settings)
            refresh()
            self.root.after(100, self._auto_refresh_fastgen)

        def remove(index):
            entry = self.settings.cover_api_keys[index]
            if messagebox.askyesno("Удаление", f"Удалить ключ «{entry.label}»?", parent=dialog):
                del self.settings.cover_api_keys[index]
                save_settings(self.settings)
                refresh()
                self.root.after(100, self._auto_refresh_fastgen)

        def add():
            label = self._ask_text("Новый ключ FastGen", "Название ключа:",
                                   f"Ключ {len(self.settings.cover_api_keys) + 1}")
            if not label:
                return
            secret = self._ask_text("Новый ключ FastGen", "Вставьте API-ключ:", secret=True)
            if not secret or not secret.strip():
                return
            self.settings.cover_api_keys.append(FastGenKey(label.strip(), secret.strip(), True))
            save_settings(self.settings)
            refresh()
            self.root.after(100, self._auto_refresh_fastgen)

        self._button(head, "+ Добавить ключ", add, "primary").pack(side="right")
        refresh()
        self.root.wait_window(dialog)
        if hasattr(self, "cover_keys_label") and self.cover_keys_label.winfo_exists():
            active = sum(item.active for item in self.settings.cover_api_keys)
            self.cover_keys_label.config(text=f"КЛЮЧИ FASTGEN: {active} ВКЛЮЧЕНО / {len(self.settings.cover_api_keys)} ВСЕГО")

    def _save_cover_settings(self, notify=True):
        self.settings.cover_operation = self._selected_model_operation(self.cover_operation_combo)
        self.settings.cover_aspect_ratio = self.cover_ratio_combo.get().strip()
        self.settings.cover_variant_count = max(1, min(6, int(self.cover_variants_combo.get() or 1)))
        self.settings.cover_prompt_template = self.cover_prompt_widget.get("1.0", "end-1c").strip()
        save_settings(self.settings)
        if notify:
            messagebox.showinfo("Обложки", "Настройки FastGen сохранены", parent=self.root)

    def _validate_cover_key(self):
        self.system_status.config(text="Проверка FastGen…")
        def work():
            try:
                pool = FastGenPool(self.settings.cover_api_keys)
                self.events.put(("cover_key_valid", {"models": pool.validate_all(), "capabilities": pool.capabilities_all()}))
            except Exception as exc:
                self.events.put(("cover_key_error", str(exc)))
        threading.Thread(target=work, daemon=True).start()

    @staticmethod
    def _usage_remaining(usage, usage_name, limit_name):
        limits = usage.get("account_limits", {})
        hourly = usage.get("current_usage", {}).get("hourly_usage", {})
        current = (hourly.get(usage_name) or {}).get("current_usage", 0)
        limit = limits.get(limit_name, 0)
        return current, limit, max(0, limit - current)

    def _fastgen_usage_summary(self):
        valid = [item for item in self.fastgen_usage if item.get("usage")]
        if not valid:
            return "ЛИМИТЫ FASTGEN: нажмите «Обновить лимиты»"
        image_left = video_left = prompt_left = 0
        for item in valid:
            usage = item["usage"]
            image_left += self._usage_remaining(usage, "image_generation", "img_gen_per_hour_limit")[2]
            video_left += self._usage_remaining(usage, "video_generation", "video_gen_per_hour_limit")[2]
            prompt_left += self._usage_remaining(usage, "prompt_generation", "prompt_tokens_per_hour_limit")[2]
        return (f"ОСТАЛОСЬ НА ЧАС: изображения {image_left}  •  видео {video_left}  •  "
                f"токены промптов {prompt_left}  •  ключей {len(valid)}")

    def _check_fastgen_usage(self):
        self.system_status.config(text="Проверка лимитов FastGen…")
        def work():
            try:
                self.events.put(("fastgen_usage", FastGenPool(self.settings.cover_api_keys).usage_all()))
            except Exception as exc:
                self.events.put(("fastgen_usage_error", str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def _auto_refresh_fastgen(self):
        if self.fastgen_refresh_running:
            return
        if not any(item.active and item.secret for item in self.settings.cover_api_keys):
            self.fastgen_sidebar_dot.config(fg="#FF5D73")
            self.fastgen_sidebar_status.config(text="FastGen: нет активных ключей")
            self.root.after(300_000, self._auto_refresh_fastgen)
            return
        self.fastgen_refresh_running = True

        def work():
            try:
                pool = FastGenPool(self.settings.cover_api_keys)
                self.events.put(("fastgen_auto_status", {
                    "models": pool.validate_all(),
                    "capabilities": pool.capabilities_all(),
                    "usage": pool.usage_all(),
                }))
            except Exception as exc:
                self.events.put(("fastgen_auto_error", str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def _schedule_next_fastgen_refresh(self):
        self.fastgen_refresh_running = False
        self.root.after(300_000, self._auto_refresh_fastgen)

    def _update_fastgen_visible_status(self):
        summary = self._fastgen_usage_summary()
        if hasattr(self, "cover_usage_label") and self.cover_usage_label.winfo_exists():
            self.cover_usage_label.config(text=summary)
        if hasattr(self, "media_usage_label") and self.media_usage_label.winfo_exists():
            self.media_usage_label.config(text=summary)
        available_images = sum(self.fastgen_model_status.get(value) == "available" for value in COVER_MODELS.values())
        available_videos = sum(self.fastgen_model_status.get(value) == "available" for value in VIDEO_MODELS.values())
        color = "#35D99A" if available_images or available_videos else "#FF5D73"
        image_left = video_left = 0
        for item in self.fastgen_usage:
            if item.get("usage"):
                image_left += self._usage_remaining(item["usage"], "image_generation", "img_gen_per_hour_limit")[2]
                video_left += self._usage_remaining(item["usage"], "video_generation", "video_gen_per_hour_limit")[2]
        self.fastgen_sidebar_dot.config(fg=color)
        self.fastgen_sidebar_status.config(
            text=(f"Модели: фото {available_images}/{len(COVER_MODELS)}, видео {available_videos}/{len(VIDEO_MODELS)}\n"
                  f"Лимит/час: фото {image_left}, видео {video_left}"))

    def _model_display(self, label, operation):
        status = self.fastgen_model_status.get(operation, "unknown")
        icon = "🟢" if status == "available" else "🔴" if status == "unavailable" else "🟡"
        return f"{icon}  {label}"

    def _model_choices(self, models):
        return tuple(self._model_display(label, operation) for label, operation in models.items())

    @staticmethod
    def _selected_model_operation(combo, models=None):
        models = models or combo.models
        selected = combo.get()
        for label, operation in models.items():
            if selected == label or selected.endswith(label):
                return operation
        return next(iter(models.values()))

    @staticmethod
    def _parse_number_ranges(value, maximum):
        indexes = set()
        try:
            for part in value.replace(" ", "").split(","):
                if not part:
                    continue
                if "-" in part:
                    start, end = (int(number) for number in part.split("-", 1))
                else:
                    start = end = int(part)
                if start < 1 or end < start:
                    raise ValueError
                indexes.update(range(start, min(end, maximum) + 1))
        except (TypeError, ValueError):
            raise ValueError("Введите номера в формате 8-60 или 2, 5-9")
        if not indexes:
            raise ValueError("Диапазон пуст")
        return indexes

    def _apply_fastgen_model_status(self, payload):
        known = set(COVER_MODELS.values()) | set(VIDEO_MODELS.values())
        for items in payload.values():
            for model in items or []:
                known.update(model.get("operations") or [])
        for operation in known:
            self.fastgen_model_status[operation] = "unavailable"
        for items in payload.values():
            for model in items or []:
                status = "unavailable" if model.get("deprecated") else "available"
                for operation in model.get("operations") or []:
                    self.fastgen_model_status[operation] = status

    def _apply_fastgen_capabilities(self, payload):
        self.fastgen_capabilities = {kind: list(payload.get(kind) or []) for kind in ("image", "video")}
        for items in self.fastgen_capabilities.values():
            for item in items:
                if item.get("id"):
                    self.fastgen_model_status[item["id"]] = "unavailable" if item.get("deprecated") else "available"

    def _fastgen_models(self, media_type: str, fallback: dict[str, str]):
        capabilities = self.fastgen_capabilities.get(media_type) or []
        if not capabilities:
            return fallback
        result = {}
        for item in capabilities:
            operation = item.get("id")
            if not operation or item.get("deprecated"):
                continue
            provider = str(item.get("provider", "FastGen")).upper()
            name = item.get("display_name") or item.get("model") or operation
            billing = item.get("billing") or {}
            cost = billing.get("credits") or billing.get("base_credits") or ""
            result[f"{provider} · {name}" + (f" — {cost} кр." if cost != "" else "")] = operation
        return result or fallback

    def _refresh_model_combos(self):
        if hasattr(self, "cover_operation_combo") and self.cover_operation_combo.winfo_exists():
            models = self._fastgen_models("image", COVER_MODELS)
            operation = self._selected_model_operation(self.cover_operation_combo)
            self.cover_operation_combo.models = models
            label = next((label for label, value in models.items() if value == operation), next(iter(models)))
            self.cover_operation_combo.update_status(self.fastgen_model_status)
            self.cover_operation_combo.set(label)
        if hasattr(self, "media_model_combo") and self.media_model_combo.winfo_exists():
            fallback = COVER_MODELS if self.media_mode == "image" else VIDEO_MODELS
            models = self._fastgen_models(self.media_mode, fallback)
            operation = self._selected_model_operation(self.media_model_combo)
            self.media_model_combo.models = models
            label = next((label for label, value in models.items() if value == operation), next(iter(models)))
            self.media_model_combo.update_status(self.fastgen_model_status)
            self.media_model_combo.set(label)

    def _cover_prompt(self, item):
        excerpt = " ".join(item.get("script", "").split())[:1800]
        return self.settings.cover_prompt_template.replace("{title}", item["title"]).replace("{excerpt}", excerpt)

    def _refresh_cover_route_presets(self, selected_name: str = ""):
        if not hasattr(self, "cover_route_preset_combo") or not self.cover_route_preset_combo.winfo_exists():
            return
        names = [item.get("name", "Без названия") for item in self.settings.cover_route_presets]
        self.cover_route_preset_combo.configure(values=names)
        if selected_name in names:
            self.cover_route_preset_combo.set(selected_name)
        elif names:
            self.cover_route_preset_combo.current(0)
        else:
            self.cover_route_preset_combo.set("")

    def _cover_route_preset_data(self):
        provider, session = self._selected_cover_text_route()
        return {
            "provider": provider,
            "profile_id": session.profile_id if provider == "claude" else "",
            "key_label": session.label if provider == "openai" else "",
            "chat_url": (self.cover_chat_entry.get().strip() if provider == "claude" else ""),
        }

    def _save_cover_route_preset(self):
        try:
            name = self._ask_text("Сохранить пресет", "Название пресета для профиля и чата:")
            if not name or not name.strip():
                return
            name = name.strip()
            preset = {"name": name, **self._cover_route_preset_data()}
            existing = next((item for item in self.settings.cover_route_presets if item.get("name") == name), None)
            if existing:
                existing.update(preset)
            else:
                self.settings.cover_route_presets.append(preset)
            save_settings(self.settings)
            self._refresh_cover_route_presets(name)
            self.system_status.config(text=f"Пресет обложек сохранён: {name}")
        except Exception as exc:
            messagebox.showerror("Пресет обложек", str(exc), parent=self.root)

    def _apply_cover_route_preset(self):
        name = self.cover_route_preset_combo.get().strip()
        preset = next((item for item in self.settings.cover_route_presets if item.get("name") == name), None)
        if not preset:
            messagebox.showinfo("Пресет обложек", "Выберите сохранённый пресет", parent=self.root)
            return
        provider = preset.get("provider", "claude")
        self.cover_provider_combo.set("OpenAI — API" if provider == "openai" else "Claude — Chrome-сессия")
        self._on_cover_provider_changed()
        wanted = preset.get("key_label" if provider == "openai" else "profile_id", "")
        for index, entry in enumerate(self.cover_session_entries):
            entry_value = entry.label if provider == "openai" else entry.profile_id
            if entry_value == wanted:
                self.cover_session_combo.current(index)
                break
        if provider == "claude":
            self.cover_chat_entry.config(state="normal")
            self.cover_chat_entry.delete(0, "end")
            self.cover_chat_entry.insert(0, preset.get("chat_url") or "https://claude.ai/new")
        self.system_status.config(text=f"Применён пресет обложек: {name}")

    def _delete_cover_route_preset(self):
        name = self.cover_route_preset_combo.get().strip()
        if not name:
            return
        if not messagebox.askyesno("Пресет обложек", f"Удалить пресет «{name}»?", parent=self.root):
            return
        self.settings.cover_route_presets = [item for item in self.settings.cover_route_presets if item.get("name") != name]
        save_settings(self.settings)
        self._refresh_cover_route_presets()

    def _selected_cover_session(self):
        index = self.cover_session_combo.current()
        if not 0 <= index < len(self.cover_session_entries):
            raise ValueError("Выберите Chrome-сессию для создания промптов")
        return self.cover_session_entries[index]

    def _cover_provider(self):
        return "openai" if hasattr(self, "cover_provider_combo") and self.cover_provider_combo.get().startswith("OpenAI") else "claude"

    def _on_cover_provider_changed(self):
        use_openai = self._cover_provider() == "openai"
        if use_openai:
            self.cover_session_entries = [key for key in self.settings.openai_api_keys if key.active and key.secret]
            self.cover_session_combo.config(values=[f"{index + 1}. {key.label}" for index, key in enumerate(self.cover_session_entries)])
            self.cover_chat_entry.delete(0, "end")
            self.cover_chat_entry.insert(0, "OpenAI API — используется ключ из списка")
            self.cover_chat_entry.config(state="disabled")
            self.cover_limit_label.config(fg="#35D99A" if self.cover_session_entries else "#FF5D73")
        else:
            self.cover_chat_entry.config(state="normal")
            self.cover_session_entries = self._sessions_for("covers")
            self.cover_session_combo.config(values=[f"{index + 1}. {item.label}" for index, item in enumerate(self.cover_session_entries)])
            self._load_cover_chat_binding()
        if self.cover_session_entries:
            self.cover_session_combo.current(0)
        self._load_cover_chat_binding()

    def _selected_cover_text_route(self):
        index = self.cover_session_combo.current()
        if not 0 <= index < len(self.cover_session_entries):
            title = "OpenAI API-ключ" if self._cover_provider() == "openai" else "Chrome-сессию Claude"
            raise ValueError(f"Выберите {title}")
        return self._cover_provider(), self.cover_session_entries[index]

    def _cover_chat_binding(self, session):
        return next((item for item in self.settings.cover_chat_bindings
                     if item.get("profile_id") == session.profile_id), None)

    def _load_cover_chat_binding(self):
        if not hasattr(self, "cover_chat_entry") or not self.cover_chat_entry.winfo_exists():
            return
        if self._cover_provider() == "openai":
            return
        try:
            session = self._selected_cover_session()
            binding = self._cover_chat_binding(session)
            url = binding.get("chat_url", "https://claude.ai/new") if binding else "https://claude.ai/new"
            color = "#FF5D73" if session.limit_status == "exhausted" else "#35D99A"
        except ValueError:
            url, color = "https://claude.ai/new", MUTED
        self.cover_chat_entry.delete(0, "end")
        self.cover_chat_entry.insert(0, url)
        self.cover_limit_label.config(fg=color)

    def _store_cover_chat_binding(self, session, url):
        if not url.startswith("https://claude.ai/"):
            raise ValueError("Вставьте ссылку на чат с сайта claude.ai")
        binding = self._cover_chat_binding(session)
        data = {"profile_id": session.profile_id, "chat_url": url}
        if binding:
            binding.update(data)
        else:
            self.settings.cover_chat_bindings.append(data)
        save_settings(self.settings)

    def _save_cover_chat_binding(self):
        try:
            if self._cover_provider() == "openai":
                messagebox.showinfo("Обложки", "Для OpenAI ссылка на чат не нужна: промпты создаются через API-ключ.", parent=self.root)
                return
            session = self._selected_cover_session()
            url = self.cover_chat_entry.get().strip() or "https://claude.ai/new"
            self._store_cover_chat_binding(session, url)
            messagebox.showinfo("Обложки", f"Чат сохранён для сессии «{session.label}»", parent=self.root)
        except Exception as exc:
            messagebox.showerror("Обложки", str(exc), parent=self.root)

    def _open_cover_chat(self):
        try:
            if self._cover_provider() == "openai":
                messagebox.showinfo("Обложки", "OpenAI работает через API-ключ; открыть обычный чат по ссылке нельзя.", parent=self.root)
                return
            session = self._selected_cover_session()
            open_login_window(session, self.cover_chat_entry.get().strip() or "https://claude.ai/new")
        except Exception as exc:
            messagebox.showerror("Обложки", str(exc), parent=self.root)

    def _operation_with_references(self, operation, references):
        if not references:
            return operation
        mapping = {
            "grok_image_generate": "grok_image_edit",
            "flower_video_from_text": "flower_video_from_image",
            "grok_video_from_text": "grok_video_from_image",
            "flow_video_from_text": "flow_video_from_ingredients",
            "flow_video_lite_from_text": "flow_video_lite_from_ingredients",
            "flow_video_omni_flash_from_text_4s": "flow_video_omni_flash_from_ingredients_4s",
        }
        candidate = mapping.get(operation, operation)
        available = {item.get("id") for items in self.fastgen_capabilities.values() for item in items}
        return candidate if candidate == operation or candidate in available else operation

    def _fastgen_operation(self, operation):
        return next((item for items in self.fastgen_capabilities.values() for item in items
                     if item.get("id") == operation), {})

    def _operation_max_inputs(self, operation):
        return int((self._fastgen_operation(operation).get("inputs") or {}).get("max", 10) or 10)

    def _operation_max_count(self, operation):
        outputs = self._fastgen_operation(operation).get("outputs") or {}
        return max(1, min(6, int(outputs.get("max_items", 1) or 1)))

    @staticmethod
    def _reference_names(paths):
        if not paths:
            return "Референсы не выбраны"
        names = [Path(path).name for path in paths]
        text = ", ".join(names[:4])
        return text + (f" и ещё {len(names) - 4}" if len(names) > 4 else "")

    def _add_references(self, target):
        paths = list(filedialog.askopenfilenames(filetypes=[("Изображения", "*.png *.jpg *.jpeg *.webp *.gif")]))
        current = self.cover_references if target == "cover" else self.media_references
        for path in paths:
            if path not in current and len(current) < 10:
                if Path(path).stat().st_size > 5 * 1024 * 1024:
                    messagebox.showwarning("Референсы", f"Файл {Path(path).name} больше 5 МБ и пропущен", parent=self.root)
                    continue
                current.append(path)
        self._update_reference_ui(target)

    def _clear_references(self, target):
        if target == "cover":
            self.cover_references = []
        else:
            self.media_references = []
        self._update_reference_ui(target)

    def _update_reference_ui(self, target):
        paths = self.cover_references if target == "cover" else self.media_references
        label = getattr(self, f"{target}_refs_label", None)
        names = getattr(self, f"{target}_refs_names", None)
        if label and label.winfo_exists():
            label.config(text=f"РЕФЕРЕНСЫ: {len(paths)}/10")
        if names and names.winfo_exists():
            names.config(text=self._reference_names(paths))

    def _generate_covers(self):
        if self.covers_running:
            return
        try:
            self._save_cover_settings(False)
            if not any(item.active and item.secret for item in self.settings.cover_api_keys):
                raise ValueError("Добавьте и включите хотя бы один ключ FastGen")
            pending = [item for item in self.cover_items if item.get("image_prompt") and item.get("status") != "Готово"]
            if not pending:
                raise ValueError("Сначала создайте промпты в Claude")
            self.covers_running = True
            self.cover_generate_button.config(state="disabled")
            client = FastGenPool(self.settings.cover_api_keys)
            output = Path(self.settings.cover_output_folder)
            seed_text = self.cover_seed_entry.get().strip()
            seed = int(seed_text) if seed_text else None
            references = list(self.cover_references)
            upscale = self.cover_upscale_var.get()
            requested_count = self.settings.cover_variant_count
            def work():
                for item in pending:
                    item["status"] = "FastGen: картинка"
                    self.events.put(("cover_job", item))
                    try:
                        operation = self._operation_with_references(self.settings.cover_operation, references)
                        inputs = references[:self._operation_max_inputs(operation)]
                        count = min(requested_count, self._operation_max_count(operation))
                        paths = client.generate_media(item["image_prompt"], output, item["title"], operation,
                                                      self.settings.cover_aspect_ratio, inputs, count, seed, upscale=upscale)
                        values = [str(path) for path in paths]
                        selected = item.get("selected_path") if item.get("selected_path") in values else values[0]
                        item.update(status="Готово", paths=values, path=selected, selected_path=selected, error="")
                    except Exception as exc:
                        item.update(status="Ошибка", error=str(exc))
                    self.events.put(("cover_job", item))
                self.events.put(("covers_complete", None))
            threading.Thread(target=work, daemon=True).start()
        except Exception as exc:
            messagebox.showerror("Обложки", str(exc), parent=self.root)

    def _generate_cover_prompts(self):
        if self.covers_running:
            return
        try:
            self._save_cover_settings(False)
            provider, route = self._selected_cover_text_route()
            if provider == "claude" and not route.active:
                raise ValueError("Выбранная Chrome-сессия выключена")
            chat_url = self.cover_chat_entry.get().strip() or "https://claude.ai/new"
            if provider == "claude":
                self._store_cover_chat_binding(route, chat_url)
            pending = [item for item in self.cover_items if not item.get("image_prompt")]
            if not pending:
                raise ValueError("Для всех оставшихся сценариев промпты уже созданы")
            self.covers_running = True
            self.cover_prompt_button.config(state="disabled")

            def work():
                for item in pending:
                    item["status"] = "Claude: промпт"
                    self.events.put(("cover_job", item))
                    task = (
                        "Создай один финальный промпт для генератора изображения по сценарию ниже. "
                        "Учти все требования пользователя. Верни только сам готовый промпт без пояснений, "
                        "кавычек и Markdown.\n\n"
                        f"ТЕМА:\n{item['title']}\n\n"
                        f"СЦЕНАРИЙ:\n{item.get('script', '')[:12000]}\n\n"
                        f"ТРЕБОВАНИЯ К ОБЛОЖКЕ:\n{self._cover_prompt(item)}"
                    )
                    try:
                        if provider == "openai":
                            pool = HybridTextPool([], [route], "", self.settings.openai_model)
                        else:
                            sessions = [route] + [item for item in self._sessions_for("covers") if item.profile_id != route.profile_id]
                            pool = self._text_pool(sessions, chat_url)
                        prompt = asyncio.run(pool.generate(task)).strip()
                        if not prompt:
                            raise ValueError("Claude вернул пустой промпт")
                        if provider == "claude" and route.limit_status != "exhausted":
                            route.limit_status = "available"
                        item.update(status="Промпт готов", image_prompt=prompt, error="")
                    except ClaudeLimitError as exc:
                        route.limit_status = "exhausted"
                        item.update(status="Лимит Claude", error=str(exc))
                    except Exception as exc:
                        item.update(status="Ошибка", error=str(exc))
                    save_settings(self.settings)
                    if provider == "claude":
                        self.events.put(("cover_session_status", route))
                    self.events.put(("cover_job", item))
                self.events.put(("cover_prompts_complete", None))

            threading.Thread(target=work, daemon=True).start()
        except Exception as exc:
            messagebox.showerror("Обложки", str(exc), parent=self.root)

    def _render_cover_items(self):
        if not hasattr(self, "cover_table") or not self.cover_table.winfo_exists():
            return
        self.cover_table.delete(*self.cover_table.get_children())
        for index, item in enumerate(self.cover_items):
            variants = list(item.get("paths") or ([item["path"]] if item.get("path") else []))
            detail = item.get("path") or item.get("error", "")
            if variants and item.get("selected_path"):
                detail = f"Выбрано: {Path(item['selected_path']).name} · вариантов: {len(variants)}"
            prompt = " ".join(item.get("image_prompt", "").split())[:120]
            self.cover_table.insert("", "end", iid=str(index),
                                    values=(index + 1, item["title"], prompt, item["status"], detail))
        self._render_cover_gallery()

    def _cover_result_paths(self, item):
        values = item.get("paths") or ([item["path"]] if item.get("path") else [])
        return [str(path) for path in values if Path(path).is_file()]

    def _render_cover_gallery(self):
        if not hasattr(self, "cover_gallery_body") or not self.cover_gallery_body.winfo_exists():
            return
        for child in self.cover_gallery_body.winfo_children():
            child.destroy()
        self.cover_preview_images = []
        rendered = 0
        for index, item in enumerate(self.cover_items):
            paths = self._cover_result_paths(item)
            if not paths:
                continue
            rendered += 1
            row = tk.Frame(self.cover_gallery_body, bg=CARD, padx=10, pady=9,
                           highlightbackground=BORDER, highlightthickness=1)
            row.pack(fill="x", pady=5)
            info = tk.Frame(row, bg=CARD, width=210)
            info.pack(side="left", fill="y")
            info.pack_propagate(False)
            tk.Label(info, text=f"{index + 1}. {item['title']}", bg=CARD, fg=TEXT,
                     wraplength=195, justify="left", font=("Segoe UI Semibold", 9)).pack(anchor="w")
            tk.Label(info, text=f"{len(paths)} вариантов", bg=CARD, fg="#35D99A",
                     font=("Segoe UI", 8)).pack(anchor="w", pady=(5, 0))
            pictures = tk.Frame(row, bg=CARD)
            pictures.pack(side="left", fill="x", expand=True, padx=(12, 0))
            selected = item.get("selected_path") or item.get("path")
            for path in paths:
                try:
                    with Image.open(path) as source:
                        source.thumbnail((165, 98))
                        preview = ImageTk.PhotoImage(source.copy())
                except Exception:
                    continue
                selected_now = path == selected
                tile = tk.Button(pictures, image=preview, command=lambda i=index, p=path: self._select_cover_variant(i, p),
                                 bg="#1D65A6" if selected_now else CARD_2, activebackground=BLUE,
                                 relief="flat", bd=0, padx=3, pady=3, cursor="hand2",
                                 highlightbackground=BLUE if selected_now else BORDER,
                                 highlightthickness=2 if selected_now else 1)
                tile.image = preview
                tile.pack(side="left", padx=4)
                self.cover_preview_images.append(preview)
        if not rendered:
            tk.Label(self.cover_gallery_body, text="После генерации здесь появятся варианты. Выберите лучший кликом — он станет основной обложкой сценария.",
                     bg=CARD_2, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=8)

    def _select_cover_variant(self, item_index: int, path: str):
        if not 0 <= item_index < len(self.cover_items) or not Path(path).is_file():
            return
        item = self.cover_items[item_index]
        item["selected_path"] = path
        item["path"] = path
        self._save_cover_queue()
        self.system_status.config(text=f"Выбрана обложка: {Path(path).name}")
        self._render_cover_items()

    def _delete_cover_items(self):
        if self.covers_running:
            return
        selected = {int(value) for value in self.cover_table.selection()}
        self.cover_items = [item for index, item in enumerate(self.cover_items) if index not in selected]
        self._save_cover_queue()
        self._render_cover_items()

    def _delete_cover_range(self):
        value = self._ask_text("Удалить диапазон", "Номера, например 8-60 или 2, 5-9:")
        if not value:
            return
        try:
            indexes = self._parse_number_ranges(value, len(self.cover_items))
            self.cover_items = [item for index, item in enumerate(self.cover_items, 1) if index not in indexes]
            self._save_cover_queue()
            self._render_cover_items()
        except ValueError as exc:
            messagebox.showerror("Удалить диапазон", str(exc), parent=self.root)

    def _open_cover_folder(self):
        folder = Path(self.settings.cover_output_folder)
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)

    def _open_selected_cover(self):
        selected = self.cover_table.selection()
        if selected:
            path = self.cover_items[int(selected[0])].get("path")
            if path and Path(path).exists():
                os.startfile(path)

    def _page_media(self):
        card = self._card(self.page, fill="x", pady=(4, 12))
        top = tk.Frame(card, bg=CARD, padx=18, pady=15)
        top.pack(fill="x")
        route = tk.Frame(top, bg=CARD)
        route.pack(fill="x", pady=(0, 10))
        tk.Label(route, text="СЕССИЯ CLAUDE", bg=CARD, fg=MUTED,
                 font=("Segoe UI Semibold", 8)).pack(side="left")
        self.media_session_entries = list(self.settings.chrome_sessions)
        self.media_session_combo = ttk.Combobox(
            route, state="readonly", style="Dark.TCombobox", width=23,
            values=[f"{i + 1}. {item.label}" for i, item in enumerate(self.media_session_entries)])
        if self.media_session_entries:
            self.media_session_combo.current(0)
        self.media_session_combo.pack(side="left", padx=8, ipady=6)
        self.media_session_combo.bind("<<ComboboxSelected>>", lambda _: self._load_media_chat_binding())
        self.media_limit_label = tk.Label(route, text="●", bg=CARD, fg=MUTED, font=("Segoe UI", 14))
        self.media_limit_label.pack(side="left", padx=(0, 6))
        tk.Label(route, text="ЧАТ", bg=CARD, fg=MUTED,
                 font=("Segoe UI Semibold", 8)).pack(side="left")
        self.media_chat_entry = self._entry(route)
        self.media_chat_entry.pack(side="left", fill="x", expand=True, padx=7, ipady=7)
        self._button(route, "Открыть", self._open_media_chat).pack(side="left", padx=4)
        self._button(route, "Сохранить чат", self._save_media_chat_binding, "primary").pack(side="left", padx=4)
        self._load_media_chat_binding()

        tabs = tk.Frame(top, bg=CARD)
        tabs.pack(fill="x")
        self._button(tabs, "Изображение", lambda: self._set_media_mode("image"),
                     "primary" if self.media_mode == "image" else "secondary").pack(side="left")
        self._button(tabs, "Видео", lambda: self._set_media_mode("video"),
                     "primary" if self.media_mode == "video" else "secondary").pack(side="left", padx=8)
        active_keys = sum(item.active for item in self.settings.cover_api_keys)
        tk.Label(tabs, text=f"FastGen: {active_keys} активных ключей", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="right", padx=8)
        self._button(tabs, "⚿ Ключи", self._manage_cover_keys).pack(side="right")
        self._button(tabs, "Лимиты", self._check_fastgen_usage).pack(side="right", padx=5)
        self.media_usage_label = tk.Label(top, text=self._fastgen_usage_summary(), bg=CARD, fg="#35D99A",
                                          font=("Segoe UI Semibold", 8), anchor="w")
        self.media_usage_label.pack(fill="x", pady=(8, 0))

        options = tk.Frame(top, bg=CARD)
        options.pack(fill="x", pady=(12, 0))
        models = self._fastgen_models(self.media_mode, COVER_MODELS if self.media_mode == "image" else VIDEO_MODELS)
        tk.Label(options, text="МОДЕЛЬ", bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 8)).pack(side="left")
        self.media_model_combo = ModelSelector(options, models, self.fastgen_model_status,
                                                next(iter(models.values())), width=38)
        self.media_model_combo.pack(side="left", padx=8, ipady=6)
        tk.Label(options, text="ФОРМАТ", bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 8)).pack(side="left", padx=(12, 5))
        ratios = ("16:9", "9:16") if self.media_mode == "video" else ("16:9", "4:3", "1:1", "3:4", "9:16")
        self.media_ratio_combo = ttk.Combobox(options, state="readonly", style="Dark.TCombobox", width=8, values=ratios)
        self.media_ratio_combo.current(0)
        self.media_ratio_combo.pack(side="left", ipady=6)
        tk.Label(options, text="ПРОМПТОВ", bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 8)).pack(side="left", padx=(12, 5))
        self.media_count_entry = self._entry(options, width=5)
        self.media_count_entry.insert(0, "10")
        self.media_count_entry.pack(side="left", ipady=7)
        tk.Label(options, text="SEED", bg=CARD, fg=MUTED, font=("Segoe UI Semibold", 8)).pack(side="left", padx=(12, 5))
        self.media_seed_entry = self._entry(options, width=10)
        self.media_seed_entry.pack(side="left", ipady=7)
        self._button(options, "Открыть папку", self._open_media_folder).pack(side="right")

        refs = tk.Frame(top, bg=CARD_2, highlightbackground=BORDER, highlightthickness=1)
        refs.pack(fill="x", pady=(10, 0))
        self.media_refs_label = tk.Label(refs, text=f"РЕФЕРЕНСЫ: {len(self.media_references)}/10", bg=CARD_2, fg=MUTED,
                                         font=("Segoe UI Semibold", 8))
        self.media_refs_label.pack(side="left", padx=12, pady=9)
        self._button(refs, "+ Добавить", lambda: self._add_references("media"), "primary").pack(side="left", pady=5)
        self._button(refs, "Очистить", lambda: self._clear_references("media"), "danger").pack(side="left", padx=7, pady=5)
        self.media_refs_names = tk.Label(refs, text=self._reference_names(self.media_references), bg=CARD_2, fg=TEXT,
                                         anchor="w", font=("Segoe UI", 8))
        self.media_refs_names.pack(side="left", fill="x", expand=True, padx=8)

        prompt_card = self._card(self.page, fill="x", pady=(0, 12))
        source_row = tk.Frame(prompt_card, bg=CARD)
        source_row.pack(fill="x", padx=18, pady=(10, 4))
        self._button(source_row, "Загрузить TXT-сценарий", self._load_media_source, "primary").pack(side="left")
        self._button(source_row, "Очистить текст", self._clear_media_source, "danger").pack(side="left", padx=5)
        self.media_source_label = tk.Label(
            source_row,
            text=(f"{Path(self.media_source_path).name} • {len(self.media_source_text)} символов"
                  if self.media_source_text else "Сценарий не загружен"),
            bg=CARD, fg=TEXT if self.media_source_text else MUTED, font=("Segoe UI", 8))
        self.media_source_label.pack(side="left", padx=10)
        self.media_auto_style_var = tk.BooleanVar(value=self.media_auto_style)
        tk.Checkbutton(source_row, text="Автовыбор стиля по анализу", variable=self.media_auto_style_var,
                       command=lambda: setattr(self, "media_auto_style", self.media_auto_style_var.get()),
                       bg=CARD, fg=TEXT, selectcolor=CARD_2, activebackground=CARD,
                       activeforeground=TEXT).pack(side="right")

        interval_row = tk.Frame(prompt_card, bg=CARD)
        interval_row.pack(fill="x", padx=18, pady=(2, 5))
        self.media_interval_var = tk.BooleanVar(value=self.media_use_interval)
        tk.Checkbutton(interval_row, text="Создавать промпт каждые", variable=self.media_interval_var,
                       command=lambda: setattr(self, "media_use_interval", self.media_interval_var.get()),
                       bg=CARD, fg=TEXT, selectcolor=CARD_2, activebackground=CARD,
                       activeforeground=TEXT).pack(side="left")
        self.media_interval_entry = self._entry(interval_row, width=8)
        self.media_interval_entry.insert(0, self.media_interval_chars)
        self.media_interval_entry.pack(side="left", padx=6, ipady=5)
        tk.Label(interval_row, text="символов • если галочка выключена, анализируется весь текст",
                 bg=CARD, fg=MUTED, font=("Segoe UI", 8)).pack(side="left")

        style_row = tk.Frame(prompt_card, bg=CARD)
        style_row.pack(fill="x", padx=18, pady=(12, 6))
        tk.Label(style_row, text="СТИЛЬ", bg=CARD, fg=MUTED,
                 font=("Segoe UI Semibold", 8)).pack(side="left")
        self.media_style_entries = [item for item in self.settings.media_styles
                                    if item.get("mode", self.media_mode) == self.media_mode]
        self.media_style_combo = ttk.Combobox(
            style_row, state="readonly", style="Dark.TCombobox", width=24,
            values=[item.get("name", "Без названия") for item in self.media_style_entries])
        self.media_style_combo.pack(side="left", padx=7, ipady=5)
        self.media_style_combo.bind("<<ComboboxSelected>>", lambda _: self._load_media_style())
        tk.Label(style_row, text="НАЗВАНИЕ", bg=CARD, fg=MUTED,
                 font=("Segoe UI Semibold", 8)).pack(side="left", padx=(10, 5))
        self.media_style_name_entry = self._entry(style_row, width=22)
        self.media_style_name_entry.pack(side="left", ipady=6)
        self._button(style_row, "Сохранить стиль", self._save_media_style, "primary").pack(side="right", padx=4)
        self._button(style_row, "Удалить", self._delete_media_style, "danger").pack(side="right", padx=4)
        self.media_style_widget = tk.Text(prompt_card, height=2, bg=CARD_2, fg=TEXT, insertbackground=TEXT,
                                          relief="flat", padx=12, pady=8, wrap="word", font=("Segoe UI", 9),
                                          highlightbackground=BORDER, highlightthickness=1)
        self.media_style_widget.pack(fill="x", padx=18, pady=(0, 8))
        self._install_edit_bindings(self.media_style_widget, multiline=True)
        if self.media_style_entries:
            self.media_style_combo.current(0)
            self._load_media_style()
        tk.Label(prompt_card, text="Задание Claude для создания промптов", bg=CARD, fg=TEXT, font=("Segoe UI Semibold", 11)).pack(anchor="w", padx=18, pady=(12, 6))
        self.media_prompt_widget = tk.Text(prompt_card, height=4, bg=CARD_2, fg=TEXT, insertbackground=TEXT,
                                           relief="flat", padx=12, pady=10, wrap="word", font=("Segoe UI", 9),
                                           highlightbackground=BORDER, highlightthickness=1)
        self.media_prompt_widget.pack(fill="x", padx=18)
        self._install_edit_bindings(self.media_prompt_widget, multiline=True)
        controls = tk.Frame(prompt_card, bg=CARD)
        controls.pack(fill="x", padx=18, pady=12)
        self.media_upscale_var = tk.BooleanVar(value=False)
        if self.media_mode == "image":
            tk.Checkbutton(controls, text="Апскейл 2×", variable=self.media_upscale_var, bg=CARD, fg=TEXT,
                           selectcolor=CARD_2, activebackground=CARD, activeforeground=TEXT).pack(side="left")
        self.media_prompt_button = self._button(controls, "Создать промпты в Claude", self._generate_media_prompts, "primary")
        self.media_prompt_button.pack(side="right")

        prompts_card = self._card(self.page, fill="both", expand=True, pady=(0, 12))
        prompt_actions = tk.Frame(prompts_card, bg=CARD)
        prompt_actions.pack(fill="x", padx=18, pady=10)
        self.media_prompts_label = tk.Label(prompt_actions, text=f"Промптов: {len(self.media_prompts)}", bg=CARD, fg=TEXT,
                                            font=("Segoe UI Semibold", 11))
        self.media_prompts_label.pack(side="left")
        self.media_generate_button = self._button(prompt_actions, "Создать фото" if self.media_mode == "image" else "Создать видео",
                                                  self._generate_media, "success")
        self.media_generate_button.pack(side="right")
        self._button(prompt_actions, "Удалить диапазон", self._delete_media_prompt_range).pack(side="right", padx=5)
        self._button(prompt_actions, "Удалить выбранные", self._delete_selected_media_prompts, "danger").pack(side="right", padx=5)
        self.media_prompts_list = tk.Listbox(prompts_card, bg=CARD_2, fg=TEXT, selectbackground=ACTIVE,
                                             relief="flat", selectmode="extended", height=7,
                                             highlightthickness=1, highlightbackground=BORDER, font=("Segoe UI", 9))
        self.media_prompts_list.pack(fill="both", expand=True, padx=18, pady=(0, 12))
        self._render_media_prompts()

        results = self._card(self.page, fill="x")
        tk.Label(results, text=f"Готовые файлы: {len(self.media_results)}", bg=CARD, fg=TEXT,
                 font=("Segoe UI Semibold", 11)).pack(anchor="w", padx=18, pady=12)
        self.media_results_list = tk.Listbox(results, bg=CARD_2, fg=TEXT, selectbackground=ACTIVE, relief="flat",
                                              highlightthickness=1, highlightbackground=BORDER, font=("Segoe UI", 9),
                                              height=4)
        self.media_results_list.pack(fill="x", padx=18, pady=(0, 16))
        for path in self.media_results:
            self.media_results_list.insert("end", path)
        self.media_results_list.bind("<Double-1>", lambda _: self._open_media_result())

    def _set_media_mode(self, mode):
        if self.media_running:
            return
        self.media_mode = mode
        self._show_page("media")

    def _selected_media_session(self):
        index = self.media_session_combo.current()
        if not 0 <= index < len(self.media_session_entries):
            raise ValueError("Выберите Chrome-сессию")
        return self.media_session_entries[index]

    def _media_chat_binding(self, session):
        return next((item for item in self.settings.media_chat_bindings
                     if item.get("profile_id") == session.profile_id and item.get("mode") == self.media_mode), None)

    def _load_media_chat_binding(self):
        if not hasattr(self, "media_chat_entry") or not self.media_chat_entry.winfo_exists():
            return
        try:
            session = self._selected_media_session()
            binding = self._media_chat_binding(session)
            url = binding.get("chat_url", "https://claude.ai/new") if binding else "https://claude.ai/new"
            color = "#FF5D73" if session.limit_status == "exhausted" else "#35D99A"
        except ValueError:
            url, color = "https://claude.ai/new", MUTED
        self.media_chat_entry.delete(0, "end")
        self.media_chat_entry.insert(0, url)
        self.media_limit_label.config(fg=color)

    def _store_media_chat_binding(self, session, url):
        if not url.startswith("https://claude.ai/"):
            raise ValueError("Вставьте ссылку на чат с сайта claude.ai")
        binding = self._media_chat_binding(session)
        data = {"profile_id": session.profile_id, "mode": self.media_mode, "chat_url": url}
        if binding:
            binding.update(data)
        else:
            self.settings.media_chat_bindings.append(data)
        save_settings(self.settings)

    def _save_media_chat_binding(self):
        try:
            session = self._selected_media_session()
            self._store_media_chat_binding(session, self.media_chat_entry.get().strip() or "https://claude.ai/new")
            messagebox.showinfo("Фото / Видео", f"Чат сохранён для сессии «{session.label}»", parent=self.root)
        except Exception as exc:
            messagebox.showerror("Фото / Видео", str(exc), parent=self.root)

    def _open_media_chat(self):
        try:
            session = self._selected_media_session()
            open_login_window(session, self.media_chat_entry.get().strip() or "https://claude.ai/new")
        except Exception as exc:
            messagebox.showerror("Фото / Видео", str(exc), parent=self.root)

    def _current_media_prompts(self):
        return [item for item in self.media_prompts if item.get("mode") == self.media_mode]

    def _load_media_source(self):
        path = filedialog.askopenfilename(filetypes=[("Текстовые файлы", "*.txt")])
        if not path:
            return
        raw = Path(path).read_bytes()
        for encoding in ("utf-8-sig", "utf-8", "cp1251"):
            try:
                self.media_source_text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            self.media_source_text = raw.decode("utf-8", errors="replace")
        self.media_source_path = path
        self.media_source_label.config(text=f"{Path(path).name} • {len(self.media_source_text)} символов", fg=TEXT)

    def _clear_media_source(self):
        self.media_source_text = ""
        self.media_source_path = ""
        self.media_source_label.config(text="Сценарий не загружен", fg=MUTED)

    def _load_media_style(self):
        index = self.media_style_combo.current()
        if not 0 <= index < len(self.media_style_entries):
            return
        style = self.media_style_entries[index]
        self.media_style_name_entry.delete(0, "end")
        self.media_style_name_entry.insert(0, style.get("name", ""))
        self.media_style_widget.delete("1.0", "end")
        self.media_style_widget.insert("1.0", style.get("style", ""))

    def _refresh_media_style_combo(self, selected_name=""):
        self.media_style_entries = [item for item in self.settings.media_styles
                                    if item.get("mode", self.media_mode) == self.media_mode]
        names = [item.get("name", "Без названия") for item in self.media_style_entries]
        self.media_style_combo.config(values=names)
        if selected_name in names:
            self.media_style_combo.current(names.index(selected_name))
        elif names:
            self.media_style_combo.current(0)

    def _save_media_style(self):
        name = self.media_style_name_entry.get().strip()
        style_text = self.media_style_widget.get("1.0", "end-1c").strip()
        if not name or not style_text:
            messagebox.showerror("Стиль", "Введите название и описание стиля", parent=self.root)
            return
        existing = next((item for item in self.settings.media_styles
                         if item.get("mode", self.media_mode) == self.media_mode and item.get("name") == name), None)
        data = {"mode": self.media_mode, "name": name, "style": style_text}
        if existing:
            existing.update(data)
        else:
            self.settings.media_styles.append(data)
        save_settings(self.settings)
        self._refresh_media_style_combo(name)
        messagebox.showinfo("Стиль", f"Стиль «{name}» сохранён", parent=self.root)

    def _delete_media_style(self):
        index = self.media_style_combo.current()
        if not 0 <= index < len(self.media_style_entries):
            return
        target = self.media_style_entries[index]
        self.settings.media_styles.remove(target)
        save_settings(self.settings)
        self._refresh_media_style_combo()
        self.media_style_name_entry.delete(0, "end")
        self.media_style_widget.delete("1.0", "end")
        if self.media_style_entries:
            self._load_media_style()

    def _render_media_prompts(self):
        if not hasattr(self, "media_prompts_list") or not self.media_prompts_list.winfo_exists():
            return
        self.media_prompts_list.delete(0, "end")
        current = self._current_media_prompts()
        for index, item in enumerate(current, 1):
            detail = f" — {item.get('status', 'Ожидает')}" if item.get("status") else ""
            preview = " ".join(item["prompt"].split())
            self.media_prompts_list.insert("end", f"{index}. {preview}{detail}")
        self.media_prompts_label.config(text=f"Промптов: {len(current)}")

    def _generate_media_prompts(self):
        if self.media_running:
            return
        try:
            instruction = self.media_prompt_widget.get("1.0", "end-1c").strip()
            if not instruction:
                raise ValueError("Опишите Claude, какие промпты нужно создать")
            source_text = self.media_source_text.strip()
            use_interval = self.media_interval_var.get()
            self.media_use_interval = use_interval
            self.media_interval_chars = self.media_interval_entry.get().strip() or "1000"
            if use_interval:
                if not source_text:
                    raise ValueError("Для режима по символам сначала загрузите TXT-сценарий")
                interval = int(self.media_interval_chars)
                if not 100 <= interval <= 50000:
                    raise ValueError("Интервал должен быть от 100 до 50000 символов")
                chunks = [source_text[index:index + interval] for index in range(0, len(source_text), interval)]
                if len(chunks) > 200:
                    raise ValueError("Получилось больше 200 фрагментов — увеличьте интервал")
                count = len(chunks)
                source_block = "\n\n".join(f"ФРАГМЕНТ {i + 1}:\n{chunk}" for i, chunk in enumerate(chunks))
            else:
                count = int(self.media_count_entry.get())
                if not 1 <= count <= 200:
                    raise ValueError("Количество промптов должно быть от 1 до 200")
                source_block = source_text[:150000]
            session = self._selected_media_session() if self.media_session_entries else None
            if session is not None and not session.active:
                raise ValueError("Выбранная Chrome-сессия выключена")
            chat_url = self.media_chat_entry.get().strip() or "https://claude.ai/new"
            if session is not None:
                self._store_media_chat_binding(session, chat_url)
            style_name = self.media_style_name_entry.get().strip()
            style_text = self.media_style_widget.get("1.0", "end-1c").strip()
            auto_style = self.media_auto_style_var.get()
            self.media_auto_style = auto_style
            media_name = "изображений" if self.media_mode == "image" else "видео"
            style_instruction = (f"\n\nНАЗВАНИЕ СТИЛЯ: {style_name}\nОПИСАНИЕ СТИЛЯ: {style_text}"
                                 if style_name or style_text else "")
            if auto_style:
                library = "\n".join(f"- {item['name']}: {item['style']}" for item in self.media_style_entries)
                style_instruction = (
                    "\n\nПроанализируй содержание каждого промпта и выбери для него наиболее подходящий стиль "
                    "из библиотеки ниже. Формат каждой строки: НАЗВАНИЕ СТИЛЯ || ПРОМПТ.\n"
                    f"БИБЛИОТЕКА СТИЛЕЙ:\n{library}"
                )
            source_instruction = f"\n\nСЦЕНАРИЙ ДЛЯ АНАЛИЗА:\n{source_block}" if source_block else ""
            interval_instruction = (" Создай ровно один промпт для каждого пронумерованного фрагмента, в том же порядке."
                                    if use_interval else "")
            task = (
                f"Создай ровно {count} отдельных подробных промптов для генерации {media_name}. "
                f"Каждый промпт должен быть самостоятельным.{interval_instruction} Верни только пронумерованный список: "
                "один промпт на одной строке, без вступления и пояснений.\n\n"
                f"ТРЕБОВАНИЯ ПОЛЬЗОВАТЕЛЯ:\n{instruction}{style_instruction}{source_instruction}"
            )
            self.media_running = True
            self.media_prompt_button.config(state="disabled")

            def work():
                try:
                    raw = asyncio.run(self._text_pool([session] if session else [], chat_url).generate(task))
                    prompts = self._parse_ideas(raw)[:count]
                    if not prompts:
                        raise ValueError("Claude не вернул список промптов")
                    self.media_prompts = [item for item in self.media_prompts if item.get("mode") != self.media_mode]
                    for prompt in prompts:
                        selected_name, selected_style, clean_prompt = style_name, style_text, prompt
                        if auto_style and "||" in prompt:
                            candidate, clean_prompt = (part.strip() for part in prompt.split("||", 1))
                            selected_name = re.sub(r"^(НАЗВАНИЕ СТИЛЯ|СТИЛЬ)\s*:\s*", "", candidate,
                                                   flags=re.IGNORECASE).strip()
                            match = next((item for item in self.media_style_entries
                                          if item.get("name", "").casefold() == selected_name.casefold()), None)
                            selected_style = match.get("style", "") if match else ""
                        final_prompt = clean_prompt
                        if selected_name or selected_style:
                            final_prompt = (f"НАЗВАНИЕ СТИЛЯ: {selected_name or 'Без названия'}\n"
                                            f"СТИЛЬ: {selected_style}\nПРОМПТ: {clean_prompt}")
                        self.media_prompts.append({"mode": self.media_mode, "prompt": final_prompt,
                                                   "style_name": selected_name, "style": selected_style,
                                                   "status": "Ожидает", "path": "", "error": ""})
                    if session is not None and session.limit_status != "exhausted":
                        session.limit_status = "available"
                    save_settings(self.settings)
                    self.events.put(("media_prompts_complete", len(prompts)))
                except ClaudeLimitError as exc:
                    if session is not None:
                        session.limit_status = "exhausted"
                    save_settings(self.settings)
                    self.events.put(("media_prompts_error", str(exc)))
                except Exception as exc:
                    self.events.put(("media_prompts_error", str(exc)))
            threading.Thread(target=work, daemon=True).start()
        except Exception as exc:
            messagebox.showerror("Фото / Видео", str(exc), parent=self.root)

    def _delete_selected_media_prompts(self):
        selected = set(self.media_prompts_list.curselection())
        current_index = 0
        kept = []
        for item in self.media_prompts:
            if item.get("mode") == self.media_mode:
                if current_index not in selected:
                    kept.append(item)
                current_index += 1
            else:
                kept.append(item)
        self.media_prompts = kept
        self._render_media_prompts()

    def _delete_media_prompt_range(self):
        value = self._ask_text("Удалить диапазон", "Номера, например 8-60 или 2, 5-9:")
        if not value:
            return
        try:
            indexes = self._parse_number_ranges(value, len(self._current_media_prompts()))
            current_index = 0
            kept = []
            for item in self.media_prompts:
                if item.get("mode") == self.media_mode:
                    current_index += 1
                    if current_index in indexes:
                        continue
                kept.append(item)
            self.media_prompts = kept
            self._render_media_prompts()
        except ValueError as exc:
            messagebox.showerror("Удалить диапазон", str(exc), parent=self.root)

    def _generate_media(self):
        if self.media_running:
            return
        try:
            pending = [item for item in self._current_media_prompts() if item.get("status") != "Готово"]
            if not pending:
                raise ValueError("Сначала создайте промпты в Claude")
            seed_text = self.media_seed_entry.get().strip()
            seed = int(seed_text) if seed_text else None
            models = self._fastgen_models(self.media_mode, COVER_MODELS if self.media_mode == "image" else VIDEO_MODELS)
            operation = self._selected_model_operation(self.media_model_combo)
            pool = FastGenPool(self.settings.cover_api_keys)
            output = self._media_output_folder()
            title = f"{self.media_mode}-{len(self.media_results) + 1}"
            references = list(self.media_references)
            operation = self._operation_with_references(operation, references)
            ratio = self.media_ratio_combo.get()
            upscale = self.media_upscale_var.get() if self.media_mode == "image" else False
            self.media_running = True
            self.media_generate_button.config(state="disabled")
            self.system_status.config(text="FastGen создаёт медиа…")
            def work():
                completed = []
                for number, item in enumerate(pending, 1):
                    item["status"] = "FastGen"
                    self.events.put(("media_prompt_job", item))
                    try:
                        item_title = f"{self.media_mode}-{len(self.media_results) + number:03d}"
                        paths = pool.generate_media(item["prompt"], output, item_title, operation, ratio,
                                                    references, 1, seed, upscale=upscale)
                        item.update(status="Готово", path=str(paths[0]), error="")
                        completed.extend(str(path) for path in paths)
                    except Exception as exc:
                        item.update(status="Ошибка", error=str(exc))
                    self.events.put(("media_prompt_job", item))
                self.events.put(("media_complete", completed))
            threading.Thread(target=work, daemon=True).start()
        except Exception as exc:
            messagebox.showerror("Фото / Видео", str(exc), parent=self.root)

    def _open_media_folder(self):
        folder = self._media_output_folder()
        folder.mkdir(parents=True, exist_ok=True)
        os.startfile(folder)

    def _media_output_folder(self):
        return Path(self.settings.media_output_folder) / ("Фото" if self.media_mode == "image" else "Видео")

    def _open_media_result(self):
        selected = self.media_results_list.curselection()
        if selected:
            path = self.media_results[selected[0]]
            if Path(path).exists():
                os.startfile(path)

    def _result_package_root(self) -> Path:
        return Path(self.settings.montage_output_folder) / "Результаты по роликам"

    def _matching_result_assets(self, title: str):
        cover = next((item for item in self.cover_items if item.get("title") == title and item.get("path")), None)
        seo = next((item for item in self.seo_items if item.get("source_title") == title and item.get("status") == "Готово"), None)
        job = next((item for item in self.jobs if item.request.title == title and item.state == RunState.DONE), None)
        return cover, seo, job

    @staticmethod
    def _hashtags_from_tags(tags: list[str]) -> list[str]:
        result = []
        for tag in tags:
            cleaned = re.sub(r"[^\w\s-]", "", str(tag), flags=re.UNICODE).strip().replace(" ", "")
            if cleaned:
                value = "#" + cleaned
                if value.casefold() not in {item.casefold() for item in result}:
                    result.append(value)
        return result[:15]

    def _package_video_result(self, video_path: str, title: str) -> dict:
        source = Path(video_path)
        if not source.is_file():
            raise FileNotFoundError(f"Не найден готовый MP4: {source}")
        title = title.strip() or source.stem
        folder = self._result_package_root() / safe_filename(title)
        folder.mkdir(parents=True, exist_ok=True)
        video_target = folder / f"{safe_filename(title)}.mp4"
        # Linking avoids a second multi-gigabyte copy when the output lives on
        # the same NTFS volume; copy only when linking is unavailable.
        if source.resolve() != video_target.resolve():
            try:
                if not video_target.exists():
                    os.link(source, video_target)
                elif source.stat().st_size != video_target.stat().st_size:
                    shutil.copy2(source, video_target)
            except OSError:
                shutil.copy2(source, video_target)
        cover, seo, job = self._matching_result_assets(title)
        (folder / "Заголовок.txt").write_text(title + "\n", encoding="utf-8-sig")
        (folder / "Сценарий.txt").write_text((job.result.strip() if job else "") + "\n", encoding="utf-8-sig")
        raw_tags = seo.get("tags") if seo else []
        tags = (list(raw_tags) if isinstance(raw_tags, (list, tuple))
                else [item.strip() for item in str(raw_tags or "").split(",") if item.strip()])
        description = str(seo.get("description") or "").strip() if seo else ""
        seo_title = str(seo.get("title") or title).strip() if seo else title
        (folder / "Описание.txt").write_text(description + "\n", encoding="utf-8-sig")
        (folder / "Теги.txt").write_text(", ".join(tags) + "\n", encoding="utf-8-sig")
        (folder / "Хештеги.txt").write_text(" ".join(self._hashtags_from_tags(tags)) + "\n", encoding="utf-8-sig")
        (folder / "SEO.txt").write_text(
            f"ЗАГОЛОВОК\n{seo_title}\n\nОПИСАНИЕ\n{description}\n\nТЕГИ\n{', '.join(tags)}\n\nХЕШТЕГИ\n{' '.join(self._hashtags_from_tags(tags))}\n",
            encoding="utf-8-sig",
        )
        if cover and Path(cover["path"]).is_file():
            cover_source = Path(cover["path"])
            cover_target = folder / f"Обложка{cover_source.suffix.casefold() or '.png'}"
            shutil.copy2(cover_source, cover_target)
        (folder / "README.txt").write_text(
            "Пакет готового ролика NewsFlow. Видео, обложка и метаданные лежат в одной папке.\n",
            encoding="utf-8-sig",
        )
        self.settings.video_result_packages[str(source)] = str(folder)
        self.last_saved_paths["outputs"] = str(folder)
        return {"folder": str(folder), "video": str(video_target)}

    def _package_existing_videos(self):
        created = 0
        for path in list(self.settings.pipeline_montage_outputs):
            if not Path(path).is_file():
                continue
            folder = self.settings.video_result_packages.get(path)
            if folder and Path(folder).is_dir():
                continue
            self._package_video_result(path, Path(path).stem)
            created += 1
        save_settings(self.settings)
        self._render_video_packages()
        messagebox.showinfo("Результаты", f"Создано пакетов роликов: {created}", parent=self.root)

    def _render_video_packages(self):
        if not hasattr(self, "video_packages_listbox") or not self.video_packages_listbox.winfo_exists():
            return
        self.video_packages_listbox.delete(0, "end")
        self.video_packages = []
        for video_path, folder in self.settings.video_result_packages.items():
            if Path(video_path).is_file() and Path(folder).is_dir():
                self.video_packages.append((video_path, folder))
                self.video_packages_listbox.insert("end", f"✓  {Path(folder).name}")

    def _open_selected_video_package(self):
        selected = self.video_packages_listbox.curselection() if hasattr(self, "video_packages_listbox") else ()
        if not selected:
            messagebox.showinfo("Результаты", "Выберите пакет ролика", parent=self.root)
            return
        os.startfile(self.video_packages[selected[0]][1])

    def _page_outputs(self):
        card = self._card(self.page, fill="x", pady=(4, 14))
        inner = tk.Frame(card, bg=CARD, padx=20, pady=19)
        inner.pack(fill="x")
        tk.Label(inner, text="Папка сохранения исходников", bg=CARD, fg=TEXT,
                 font=("Segoe UI Semibold", 12)).pack(anchor="w")
        tk.Label(inner, text="Каждая непустая строка — один сценарий — один TXT-файл с названием сценария",
                 bg=CARD, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", pady=(3, 0))
        path_row = tk.Frame(inner, bg=CARD); path_row.pack(fill="x", pady=(12, 0))
        self.output_entry = self._entry(path_row)
        self.output_entry.insert(0, self.settings.output_folder); self.output_entry.pack(side="left", fill="x", expand=True, ipady=8)
        self._button(path_row, "Выбрать", self._choose_output).pack(side="left", padx=(10, 0))
        output_actions = tk.Frame(inner, bg=CARD)
        output_actions.pack(fill="x", pady=(10, 0))
        self._button(output_actions, "Открыть папку с исходниками", self._open_output_folder).pack(side="left")
        self._button(output_actions, "Открыть выбранный файл", self._open_selected_output_file, "success").pack(side="left", padx=10)
        self._button(output_actions, "Экспортировать готовые", self._export, "primary").pack(side="right")

        packages = self._card(self.page, fill="x", pady=(0, 14))
        package_head = tk.Frame(packages, bg=CARD, padx=20, pady=8)
        package_head.pack(fill="x", pady=(7, 0))
        tk.Label(package_head, text="Пакеты готовых роликов", bg=CARD, fg=TEXT,
                 font=("Segoe UI Semibold", 12)).pack(side="left")
        tk.Label(package_head, text="MP4 + обложка + сценарий + SEO в отдельной папке", bg=CARD, fg=MUTED,
                 font=("Segoe UI", 8)).pack(side="left", padx=10)
        self._button(package_head, "Собрать пакеты", self._package_existing_videos, "primary").pack(side="right")
        self._button(package_head, "Открыть пакет", self._open_selected_video_package).pack(side="right", padx=8)
        self.video_packages_listbox = tk.Listbox(packages, height=5, bg=CARD_2, fg=TEXT, selectbackground=ACTIVE,
                                                selectforeground=TEXT, relief="flat", bd=0, highlightthickness=1,
                                                highlightbackground=BORDER, font=("Segoe UI", 9))
        self.video_packages_listbox.pack(fill="x", padx=20, pady=(0, 16))
        self.video_packages_listbox.bind("<Double-1>", lambda _: self._open_selected_video_package())
        self._render_video_packages()

        results = self._card(self.page, fill="both", expand=True)
        tk.Label(results, text=f"Готовые сценарии: {sum(job.state == RunState.DONE for job in self.jobs)}",
                 bg=CARD, fg=TEXT, font=("Segoe UI Semibold", 12)).pack(anchor="w", padx=20, pady=17)
        self.outputs_listbox = tk.Listbox(results, bg=CARD_2, fg=TEXT, selectbackground=ACTIVE, relief="flat",
                                          bd=0, highlightthickness=1, highlightbackground=BORDER, font=("Segoe UI", 10))
        self.outputs_listbox.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        self.output_jobs = [job for job in sorted(self.jobs, key=lambda item: item.request.index)
                            if job.state == RunState.DONE]
        for job in self.output_jobs:
            self.outputs_listbox.insert("end", f"✓  {job.request.title}")
        self.outputs_listbox.bind("<Double-1>", lambda _: self._open_selected_output_file())

    def _choose_output(self):
        folder = filedialog.askdirectory(initialdir=self.settings.output_folder or None)
        if folder:
            self.output_entry.delete(0, "end"); self.output_entry.insert(0, folder)
            self.settings.output_folder = folder; save_settings(self.settings)

    def _open_output_folder(self):
        try:
            folder = ""
            if hasattr(self, "output_entry") and self.output_entry.winfo_exists():
                folder = self.output_entry.get().strip()
            path = Path(folder or self.settings.output_folder)
            path.mkdir(parents=True, exist_ok=True)
            self.settings.output_folder = str(path)
            save_settings(self.settings)
            os.startfile(path)
        except Exception as exc:
            messagebox.showerror("Готовые сценарии", str(exc), parent=self.root)

    def _open_selected_output_file(self):
        try:
            if not hasattr(self, "outputs_listbox") or not self.outputs_listbox.winfo_exists():
                self._show_page("outputs")
                return
            selected = self.outputs_listbox.curselection()
            if not selected:
                messagebox.showinfo("Открыть файл", "Выберите готовый сценарий в списке", parent=self.root)
                return
            job = self.output_jobs[selected[0]]
            folder = self.output_entry.get().strip() or self.settings.output_folder
            target_folder = Path(folder)
            target_folder.mkdir(parents=True, exist_ok=True)
            path = target_folder / f"{safe_filename(job.request.title)}.txt"
            if not path.exists():
                path.write_text(job.result.strip() + "\n", encoding="utf-8")
            os.startfile(path)
        except Exception as exc:
            messagebox.showerror("Открыть файл", str(exc), parent=self.root)

    def _choose_txt(self):
        path = filedialog.askopenfilename(filetypes=[("Текстовые файлы", "*.txt")])
        if path: self._load_txt(path)

    def _drop_file(self, event):
        paths = self.root.tk.splitlist(event.data)
        if paths: self._load_txt(paths[0])
        return COPY

    def _enable_text_drop(self, receiver, target, multiline: bool):
        if not DND_FILES:
            return
        receiver.drop_target_register(DND_FILES)
        receiver.dnd_bind("<<Drop>>", lambda event, field=target, multi=multiline: self._drop_text(event, field, multi))

    def _enable_drop_group(self, container, target, multiline: bool):
        self._enable_text_drop(container, target, multiline)
        for child in container.winfo_children():
            self._enable_text_drop(child, target, multiline)
            for grandchild in child.winfo_children():
                self._enable_text_drop(grandchild, target, multiline)

    def _choose_text_for_widget(self, widget, multiline: bool):
        path = filedialog.askopenfilename(filetypes=[("Текстовые файлы", "*.txt")])
        if path:
            self._put_file_into_widget(path, widget, multiline)

    def _drop_text(self, event, widget, multiline: bool):
        paths = self.root.tk.splitlist(event.data)
        if not paths:
            return COPY
        try:
            self._put_file_into_widget(paths[0], widget, multiline)
        except Exception as exc:
            messagebox.showerror("Импорт TXT", str(exc), parent=self.root)
        return COPY

    def _put_file_into_widget(self, path, widget, multiline: bool):
        text = read_text_file(path).strip()
        if multiline:
            widget.delete("1.0", "end")
            widget.insert("1.0", text)
        else:
            widget.delete(0, "end")
            widget.insert(0, " ".join(text.split()))
        self.system_status.config(text=f"Загружен {Path(path).name}")

    def _load_txt(self, path):
        try:
            text = read_text_file(path)
            self.titles = parse_titles(text)
            self.jobs = []
            save_session(self.titles, self.jobs)
            self._populate_titles()
            self._update_counters()
        except Exception as exc:
            messagebox.showerror("Импорт", str(exc), parent=self.root)

    def _populate_titles(self):
        if not self.table:
            return
        self.table.delete(*self.table.get_children())
        job_map = {job.request.index: job for job in self.jobs}
        for i, title in enumerate(self.titles):
            job = job_map.get(i)
            state = job.state.value if job else RunState.WAITING.value
            detail = job.error if job and job.error else ("✓ Готов" if job and job.state == RunState.DONE else "")
            tag = "done" if job and job.state == RunState.DONE else "error" if job and job.state == RunState.ERROR else "paused" if job and job.state == RunState.PAUSED else ""
            self.table.insert("", "end", iid=str(i), values=(i + 1, title, state, detail), tags=(tag,))

    def _ranges_from_settings(self):
        return [PromptRange(int(item["start"]), int(item["end"]), item.get("prompt", "")) for item in self.settings.prompt_ranges]

    def _start(self):
        if self.running:
            return
        try:
            if self.ideas_running:
                raise ValueError("Сначала дождитесь завершения генерации идей")
            if not self.titles:
                raise ValueError("Сначала загрузите TXT со сценариями")
            active_api = any(item.active and item.secret.strip() for item in self.settings.openai_api_keys)
            if not self._sessions_for("scenarios") and not active_api:
                self._show_page("keys")
                raise ValueError("Добавьте Chrome-сессию или OpenAI API-ключ")
            requests = build_requests(self.titles, self.settings.template, self._ranges_from_settings())
            self.jobs = []
            self._run_requests(requests)
        except Exception as exc:
            messagebox.showerror("Запуск", str(exc), parent=self.root)

    def _retry_errors(self):
        self._run_requests([job.request for job in self.jobs if job.state in (RunState.ERROR, RunState.PAUSED)])

    def _rerun_selected(self):
        if not self.table:
            return
        selected = {int(item) for item in self.table.selection() if item != "empty"}
        current = {job.request.index: job.request for job in self.jobs}
        all_requests = build_requests(self.titles, self.settings.template, self._ranges_from_settings())
        requests = [current.get(index, all_requests[index]) for index in selected]
        self._run_requests(requests)

    def _select_all(self, _=None):
        if self.table:
            items = [item for item in self.table.get_children() if item != "empty"]
            self.table.selection_set(items)
        return "break"

    def _delete_selected(self):
        if self.running or not self.table:
            return
        indices = {int(item) for item in self.table.selection() if item != "empty"}
        if not indices:
            return
        self.titles, self.jobs = remove_scenarios(self.titles, self.jobs, indices)
        save_session(self.titles, self.jobs)
        self._populate_titles()
        if not self.titles:
            self.table.insert("", "end", iid="empty", values=("", "Перетащите TXT-файл сюда или нажмите «Добавить TXT»", "", ""))
        self._update_counters()

    def _clear_all(self):
        if self.running or not self.titles:
            return
        if not messagebox.askyesno("Очистить список", "Удалить все сценарии и сохранённые результаты из списка?", parent=self.root):
            return
        self.titles = []
        self.jobs = []
        save_session(self.titles, self.jobs)
        self._populate_titles()
        self.table.insert("", "end", iid="empty", values=("", "Перетащите TXT-файл сюда или нажмите «Добавить TXT»", "", ""))
        self._update_counters()

    def _edit_selected_title(self, index=None):
        if self.running:
            return
        if index is None:
            if not self.table:
                return
            selected = [int(item) for item in self.table.selection() if item != "empty"]
            if len(selected) != 1:
                messagebox.showinfo("Изменить тему", "Выберите один сценарий", parent=self.root)
                return
            index = selected[0]
        dialog = tk.Toplevel(self.root, bg=BG)
        dialog.title("Изменить тему")
        dialog.geometry("620x220")
        dialog.transient(self.root); dialog.grab_set()
        panel = tk.Frame(dialog, bg=CARD, padx=22, pady=20)
        panel.pack(fill="both", expand=True, padx=16, pady=16)
        tk.Label(panel, text="Новое название темы", bg=CARD, fg=TEXT,
                 font=("Segoe UI Semibold", 12)).pack(anchor="w")
        entry = self._entry(panel); entry.insert(0, self.titles[index]); entry.pack(fill="x", pady=14, ipady=8)
        entry.focus_set(); entry.selection_range(0, "end")
        def save():
            try:
                self.titles, self.jobs = rename_scenario(self.titles, self.jobs, index, entry.get())
                rebuilt = build_requests(self.titles, self.settings.template, self._ranges_from_settings())
                for job in self.jobs:
                    if job.request.index == index:
                        job.request = rebuilt[index]
                save_session(self.titles, self.jobs)
                self._populate_titles(); dialog.destroy()
            except Exception as exc:
                messagebox.showerror("Изменить тему", str(exc), parent=dialog)
        self._button(panel, "Сохранить", save, "primary").pack(anchor="e")
        entry.bind("<Return>", lambda _: save())

    def _run_requests(self, requests):
        if not requests or self.running:
            return
        active_api_keys = [item for item in self.settings.openai_api_keys if item.active and item.secret.strip()]
        scenario_sessions = self._sessions_for("scenarios")
        if not scenario_sessions and not active_api_keys:
            messagebox.showerror("Запуск", "Добавьте Chrome-сессию или OpenAI API-ключ", parent=self.root); return
        self.running = True
        if hasattr(self, "start_button") and self.start_button.winfo_exists():
            self.start_button.config(state="disabled")
        self.system_status.config(text="Claude пишет…")
        client = self._text_pool(scenario_sessions)
        workers = max(1, len(scenario_sessions) + len(active_api_keys))
        runner = ParallelRunner(client, workers, lambda job: self.events.put(("job", job)))
        self.active_runner = runner
        threading.Thread(target=self._run_async, args=(runner.run(requests),), daemon=True).start()

    def _toggle_pause(self):
        if not self.running or not self.active_runner:
            return
        if self.active_runner.is_paused:
            self.active_runner.resume()
            self.system_status.config(text="Claude пишет…")
            if hasattr(self, "pause_button") and self.pause_button.winfo_exists():
                self.pause_button.config(text="Ⅱ  Пауза")
        else:
            self.active_runner.pause()
            self.system_status.config(text="На паузе")
            if hasattr(self, "pause_button") and self.pause_button.winfo_exists():
                self.pause_button.config(text="▷  Продолжить")

    def _stop_all(self):
        if self.running and self.active_runner:
            self.active_runner.cancel()
            self.system_status.config(text="Останавливается…")

    def _run_async(self, coroutine):
        try:
            self.events.put(("complete", asyncio.run(coroutine)))
        except Exception as exc:
            self.events.put(("fatal", str(exc)))

    def _process_events(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "job":
                    job = data
                    existing = {item.request.index: item for item in self.jobs}
                    existing[job.request.index] = job
                    self.jobs = list(existing.values())
                    if self.table and self.table.exists(str(job.request.index)):
                        old = self.table.item(str(job.request.index), "values")
                        detail = job.error or ("✓ Готов" if job.state == RunState.DONE else "Claude пишет…")
                        tag = "done" if job.state == RunState.DONE else "error" if job.state == RunState.ERROR else "paused" if job.state == RunState.PAUSED else ""
                        self.table.item(str(job.request.index), values=(old[0], old[1], job.state.value, detail), tags=(tag,))
                    self._update_counters()
                elif kind == "complete":
                    existing = {item.request.index: item for item in self.jobs}
                    existing.update({item.request.index: item for item in data})
                    self.jobs = list(existing.values())
                    self.running = False
                    self.active_runner = None
                    save_session(self.titles, self.jobs)
                    try:
                        self._auto_export_completed()
                    except Exception as exc:
                        self.system_status.config(text="Ошибка сохранения")
                        messagebox.showerror("Автосохранение", str(exc), parent=self.root)
                    self.system_status.config(text="Система готова")
                    if hasattr(self, "start_button") and self.start_button.winfo_exists():
                        self.start_button.config(state="normal")
                    if hasattr(self, "run_status") and self.run_status.winfo_exists():
                        self.run_status.config(text="Все задачи завершены")
                    if hasattr(self, "pause_button") and self.pause_button.winfo_exists():
                        self.pause_button.config(text="Ⅱ  Пауза")
                    self._update_counters()
                    if self.auto_pipeline_active:
                        self._transfer_completed_to_next_steps()
                        self.system_status.config(text="Автоконвейер: сценарии готовы, запускаем озвучку…")
                        self._show_page("voice_create")
                        self.root.after(120, self._generate_voice_ranges)
                elif kind == "ideas_complete":
                    self.generated_ideas = data.get("ideas", []) if isinstance(data, dict) else self._parse_ideas(data)
                    self.ideas_running = False
                    self.system_status.config(text=f"Идеи готовы: {len(self.generated_ideas)}")
                    if hasattr(self, "idea_generate_button") and self.idea_generate_button.winfo_exists():
                        self.idea_generate_button.config(state="normal", text="✦  Сгенерировать план")
                    self._render_ideas()
                    if not self.generated_ideas:
                        messagebox.showwarning("Генерация идей", "Claude не вернул список идей", parent=self.root)
                elif kind == "ideas_error":
                    self.ideas_running = False
                    self.system_status.config(text="Ошибка генерации идей")
                    if hasattr(self, "idea_generate_button") and self.idea_generate_button.winfo_exists():
                        self.idea_generate_button.config(state="normal", text="✦  Сгенерировать план")
                    messagebox.showerror("Генерация идей", data, parent=self.root)
                elif kind == "ideas_progress":
                    done, total, topic = data
                    self.system_status.config(text=f"Идеи {done}/{total}: {topic}")
                elif kind == "idea_topics_suggested":
                    self.idea_topics_suggesting = False
                    added = [topic for topic in data if topic not in self.settings.idea_topics]
                    self.settings.idea_topics.extend(added)
                    if added:
                        self.idea_topic_entry.configure(values=self.settings.idea_topics)
                        self._select_idea_topic(added[0])
                        save_settings(self.settings)
                    if hasattr(self, "idea_suggest_button") and self.idea_suggest_button.winfo_exists():
                        self.idea_suggest_button.config(state="normal", text="✦ ИИ предложит")
                    self.system_status.config(text=f"ИИ добавил направлений: {len(added)}")
                    if not added:
                        messagebox.showinfo("ИИ-направления", "Новых направлений не найдено — попробуйте уточнить запрос.", parent=self.root)
                elif kind == "idea_topics_suggest_error":
                    self.idea_topics_suggesting = False
                    if hasattr(self, "idea_suggest_button") and self.idea_suggest_button.winfo_exists():
                        self.idea_suggest_button.config(state="normal", text="✦ ИИ предложит")
                    self.system_status.config(text="Не удалось подобрать направления")
                    messagebox.showerror("ИИ-направления", data, parent=self.root)
                elif kind == "web_footage":
                    self.web_footage_results = data
                    self.system_status.config(text=f"Найдено футажей: {len(data)}")
                    if self.current_page == "footage":
                        self._show_page("footage")
                elif kind == "footage_downloaded":
                    self.clip_index.add_item(data)
                    self.footage_items = self.clip_index.all_items()
                    self.system_status.config(text="Футаж скачан; запустите ИИ-индексацию для смыслового поиска")
                    messagebox.showinfo(
                        "Футажи", f"Скачано: {data.name}\nЛицензия: {data.license}", parent=self.root)
                elif kind == "cutter_progress":
                    self.system_status.config(text=f"Нарезка {data['current']}/{data['total']}: {data['source']}")
                elif kind == "cutter_complete":
                    self.cutter_running = False
                    folder = data["folder"]
                    if folder not in self.settings.footage_folders:
                        self.settings.footage_folders.append(folder)
                        save_settings(self.settings)
                    self.system_status.config(text=f"Нарезка готова: {data['count']} клипов")
                    if hasattr(self, "cutter_start_button") and self.cutter_start_button.winfo_exists():
                        self.cutter_start_button.config(state="normal", text="Нарезать и добавить в футажи")
                    messagebox.showinfo("Нарезка футажей", f"Готово: {data['count']} клипов. Папка добавлена в футажи — теперь запустите ИИ-индексацию.", parent=self.root)
                elif kind == "cutter_error":
                    self.cutter_running = False
                    if hasattr(self, "cutter_start_button") and self.cutter_start_button.winfo_exists():
                        self.cutter_start_button.config(state="normal", text="Нарезать и добавить в футажи")
                    messagebox.showerror("Нарезка футажей", data, parent=self.root)
                elif kind == "mixer_progress":
                    if hasattr(self, "mixer_progress_label") and self.mixer_progress_label.winfo_exists():
                        self.mixer_progress_label.config(text=f"Готово вариантов: {data['done']} / {data['total']}")
                elif kind == "mixer_complete":
                    self.cutter_running = False
                    if hasattr(self, "mixer_start_button") and self.mixer_start_button.winfo_exists():
                        self.mixer_start_button.config(state="normal", text="Собрать вариации")
                    self.system_status.config(text=f"Вариации готовы: {data['count']}")
                    messagebox.showinfo("Вариации футажей", f"Создано MP4: {data['count']}\n{data['folder']}", parent=self.root)
                elif kind == "mixer_error":
                    self.cutter_running = False
                    if hasattr(self, "mixer_start_button") and self.mixer_start_button.winfo_exists():
                        self.mixer_start_button.config(state="normal", text="Собрать вариации")
                    messagebox.showerror("Вариации футажей", data, parent=self.root)
                elif kind == "web_footage_error":
                    self.system_status.config(text="Ошибка поиска футажей")
                    messagebox.showerror("Футажи", data, parent=self.root)
                elif kind == "footage_index_progress":
                    if hasattr(self, "footage_progress") and self.footage_progress.winfo_exists():
                        self.footage_progress["maximum"] = max(1, data.total)
                        self.footage_progress["value"] = data.processed
                        self.footage_progress_label.config(
                            text=(f"{data.stage}: {data.processed}/{data.total} • новых {data.indexed} • "
                                  f"пропущено {data.skipped} • ошибок {data.failed} • {data.current}"))
                elif kind == "footage_index_complete":
                    self.index_running = False
                    self.footage_items = self.clip_index.all_items()
                    self.system_status.config(text="ИИ-индексация завершена")
                    if hasattr(self, "footage_index_button") and self.footage_index_button.winfo_exists():
                        self.footage_index_button.config(state="normal", text="ИИ-индексация")
                        self.footage_count_label.config(
                            text=f"ИИ-индекс: {self.clip_index.count(True)} / {self.clip_index.count()} видео")
                    messagebox.showinfo(
                        "ИИ-индексация",
                        f"Готово: {data.indexed}\nУже были готовы: {data.skipped}\nОшибок: {data.failed}",
                        parent=self.root,
                    )
                elif kind == "footage_index_error":
                    self.index_running = False
                    self.system_status.config(text="Ошибка ИИ-индексации")
                    if hasattr(self, "footage_index_button") and self.footage_index_button.winfo_exists():
                        self.footage_index_button.config(state="normal", text="ИИ-индексация")
                    messagebox.showerror("ИИ-индексация", data, parent=self.root)
                elif kind == "voicer_progress":
                    label, percent = data
                    self.system_status.config(text=f"Озвучка: {percent}%")
                    if hasattr(self, "voice_status_label") and self.voice_status_label.winfo_exists():
                        self.voice_status_label.config(text=f"{label} · {percent}%")
                elif kind == "voicer_catalog":
                    self.voicer_catalog = data
                    self.system_status.config(text=f"Загружено голосов: {len(data)}")
                    if self.current_page == "voice_profiles":
                        self._show_page("voice_profiles")
                elif kind == "voicer_batch_progress":
                    number, total, label, percent = data
                    self.system_status.config(text=f"Озвучка {number}/{total}: {percent}%")
                    if hasattr(self, "voice_status_label") and self.voice_status_label.winfo_exists():
                        self.voice_status_label.config(text=f"{number}/{total} · {label} · {percent}%")
                elif kind == "voicer_batch_item":
                    scenario_index, path, number, total = data
                    self.settings.voice_scenario_outputs[str(scenario_index)] = path
                    save_settings(self.settings)
                    self._refresh_pipeline_calculator()
                    self.system_status.config(text=f"MP3 готов: {number} / {total}")
                elif kind == "voicer_batch_done":
                    total, errors = data
                    self.voicer_running = False
                    self.voice_batch_running = False
                    if hasattr(self, "voice_batch_button") and self.voice_batch_button.winfo_exists():
                        self.voice_batch_button.config(state="normal", text="Озвучить готовые сценарии по диапазонам")
                    self._refresh_pipeline_calculator()
                    if errors:
                        self.system_status.config(text=f"Озвучка завершена с ошибками: {len(errors)}")
                        messagebox.showwarning("Озвучка по диапазонам", f"Очередь завершена. Ошибок: {len(errors)}\n\n" + "\n".join(errors[:8]), parent=self.root)
                    else:
                        self.system_status.config(text=f"Озвучка завершена: {total} MP3")
                        messagebox.showinfo("Озвучка по диапазонам", f"Готово MP3: {total}", parent=self.root)
                elif kind == "voicer_done":
                    self.voicer_running = False
                    try:
                        self._apply_voiceover(data)
                        self.system_status.config(text="Озвучка готова и передана в монтаж")
                    except Exception as exc:
                        self.system_status.config(text="Озвучка готова; добавьте её в монтаж вручную")
                    if hasattr(self, "voicer_generate_button") and self.voicer_generate_button.winfo_exists():
                        self.voicer_generate_button.config(state="normal", text="Создать MP3")
                    if hasattr(self, "voice_status_label") and self.voice_status_label.winfo_exists():
                        self.voice_status_label.config(text=f"Готово: {Path(data).name}")
                    if messagebox.askyesno("Озвучка", f"Готово:\n{data}\n\nОткрыть папку с MP3?", parent=self.root):
                        os.startfile(str(Path(data).parent))
                elif kind == "voicer_error":
                    self.voicer_running = False
                    self.system_status.config(text="Ошибка озвучки")
                    if hasattr(self, "voicer_generate_button") and self.voicer_generate_button.winfo_exists():
                        self.voicer_generate_button.config(state="normal", text="Создать MP3")
                    if hasattr(self, "voice_status_label") and self.voice_status_label.winfo_exists():
                        self.voice_status_label.config(text="Ошибка генерации")
                    messagebox.showerror("Озвучка", data, parent=self.root)
                elif kind == "montage_plan_complete":
                    self.montage_running = False
                    self.timeline_project = TimelineProject(
                        data["title"] or "Новый проект", self.montage_ratio.get(), data["clips"],
                        self.timeline_project.voiceover_path)
                    self.clip_index.mark_used(item.path for item in self.timeline_project.clips)
                    if self.timeline_project.voiceover_path and Path(self.timeline_project.voiceover_path).exists():
                        try:
                            self._fit_timeline_to_voiceover(
                                probe_media_duration(Path(self.timeline_project.voiceover_path)))
                        except Exception:
                            pass
                    self.system_status.config(text=f"Черновик собран: {len(self.timeline_project.clips)} сцен")
                    if hasattr(self, "montage_build_button") and self.montage_build_button.winfo_exists():
                        self.montage_build_button.config(state="normal", text="Агент: собрать черновик")
                    self._render_timeline_rows()
                elif kind == "montage_render_progress":
                    self.system_status.config(
                        text=f"Рендер {data['done']}/{data['total']}: {data['label']}")
                elif kind == "montage_render_complete":
                    self.montage_running = False
                    try:
                        package = self._package_video_result(data, self.timeline_project.title)
                        packaged_video = package["video"]
                    except Exception as exc:
                        package = None
                        packaged_video = data
                        self.system_status.config(text=f"Видео готово, но пакет не собран: {exc}")
                    if packaged_video not in self.settings.pipeline_montage_outputs:
                        self.settings.pipeline_montage_outputs.append(packaged_video)
                    save_settings(self.settings)
                    self._refresh_pipeline_calculator()
                    self.system_status.config(text="Готовый ролик и пакет результатов сохранены" if package else "Готовый ролик экспортирован")
                    if hasattr(self, "montage_render_button") and self.montage_render_button.winfo_exists():
                        self.montage_render_button.config(state="normal", text="Экспорт MP4")
                    if hasattr(self, "video_packages_listbox"):
                        self._render_video_packages()
                    destination = package["folder"] if package else data
                    if messagebox.askyesno("Экспорт", f"Готово:\n{destination}\n\nОткрыть результат?", parent=self.root):
                        os.startfile(destination)
                elif kind == "montage_error":
                    self.montage_running = False
                    self.system_status.config(text="Ошибка монтажа")
                    if hasattr(self, "montage_build_button") and self.montage_build_button.winfo_exists():
                        self.montage_build_button.config(state="normal", text="Агент: собрать черновик")
                    if hasattr(self, "montage_render_button") and self.montage_render_button.winfo_exists():
                        self.montage_render_button.config(state="normal", text="Экспорт MP4")
                    messagebox.showerror("Монтаж", data, parent=self.root)
                elif kind == "cover_job":
                    self._save_cover_queue()
                    self._render_cover_items()
                    self.system_status.config(text=f"Обложка: {data.get('title', '')}")
                elif kind == "cover_session_status":
                    if hasattr(self, "cover_limit_label") and self.cover_limit_label.winfo_exists():
                        color = "#FF5D73" if data.limit_status == "exhausted" else "#35D99A"
                        self.cover_limit_label.config(fg=color)
                elif kind == "covers_complete":
                    self.covers_running = False
                    self.system_status.config(text="Генерация обложек завершена")
                    if hasattr(self, "cover_generate_button") and self.cover_generate_button.winfo_exists():
                        self.cover_generate_button.config(state="normal")
                    self._render_cover_items()
                elif kind == "cover_prompts_complete":
                    self.covers_running = False
                    self.system_status.config(text="Промпты обложек готовы")
                    if hasattr(self, "cover_prompt_button") and self.cover_prompt_button.winfo_exists():
                        self.cover_prompt_button.config(state="normal")
                    self._render_cover_items()
                elif kind == "cover_key_valid":
                    self._apply_fastgen_model_status(data["models"])
                    self._apply_fastgen_capabilities(data["capabilities"])
                    self._refresh_model_combos()
                    self._update_fastgen_visible_status()
                    self.system_status.config(text="FastGen подключён")
                    image_count = len(data["capabilities"].get("image", []))
                    video_count = len(data["capabilities"].get("video", []))
                    messagebox.showinfo(
                        "FastGen API",
                        f"Ключ работает.\nИзображения: {image_count} моделей\nВидео: {video_count} моделей",
                        parent=self.root,
                    )
                elif kind == "cover_key_error":
                    for operation in self.fastgen_model_status:
                        self.fastgen_model_status[operation] = "unavailable"
                    self._refresh_model_combos()
                    self.system_status.config(text="Ошибка FastGen")
                    messagebox.showerror("FastGen API", data, parent=self.root)
                elif kind == "fastgen_usage":
                    self.fastgen_usage = data
                    self._update_fastgen_visible_status()
                    self.system_status.config(text="Лимиты FastGen обновлены")
                    lines = []
                    for item in data:
                        if item.get("error"):
                            lines.append(f"{item['label']}: ошибка проверки")
                            continue
                        usage = item["usage"]
                        image = self._usage_remaining(usage, "image_generation", "img_gen_per_hour_limit")
                        video = self._usage_remaining(usage, "video_generation", "video_gen_per_hour_limit")
                        prompt = self._usage_remaining(usage, "prompt_generation", "prompt_tokens_per_hour_limit")
                        lines.append(
                            f"{item['label']}\n"
                            f"  Изображения: {image[2]} осталось ({image[0]} / {image[1]} использовано)\n"
                            f"  Видео: {video[2]} осталось ({video[0]} / {video[1]} использовано)\n"
                            f"  Токены промптов: {prompt[2]} осталось ({prompt[0]} / {prompt[1]} использовано)"
                        )
                    messagebox.showinfo("Лимиты FastGen на текущий час", "\n\n".join(lines), parent=self.root)
                elif kind == "fastgen_usage_error":
                    self.system_status.config(text="Ошибка проверки лимитов FastGen")
                    messagebox.showerror("Лимиты FastGen", data, parent=self.root)
                elif kind == "fastgen_auto_status":
                    self._apply_fastgen_model_status(data["models"])
                    self._apply_fastgen_capabilities(data["capabilities"])
                    self.fastgen_usage = data["usage"]
                    self._refresh_model_combos()
                    self._update_fastgen_visible_status()
                    self._schedule_next_fastgen_refresh()
                elif kind == "fastgen_auto_error":
                    self.fastgen_sidebar_dot.config(fg="#FF5D73")
                    self.fastgen_sidebar_status.config(text="FastGen: ошибка проверки")
                    self._schedule_next_fastgen_refresh()
                elif kind == "openai_key_valid":
                    self.system_status.config(text="OpenAI API подключён")
                    messagebox.showinfo("OpenAI API", f"Ключ «{data}» работает", parent=self.root)
                elif kind == "openai_key_error":
                    self.system_status.config(text="Ошибка OpenAI API")
                    messagebox.showerror("OpenAI API", data, parent=self.root)
                elif kind == "media_complete":
                    self.media_running = False
                    self.media_results.extend(data)
                    self.system_status.config(text="Медиа готово")
                    if hasattr(self, "media_generate_button") and self.media_generate_button.winfo_exists():
                        self.media_generate_button.config(state="normal")
                    if self.current_page == "media":
                        self._show_page("media")
                elif kind == "media_prompt_job":
                    self._render_media_prompts()
                    self.system_status.config(text="FastGen обрабатывает промпты…")
                elif kind == "media_prompts_complete":
                    self.media_running = False
                    self.system_status.config(text=f"Claude создал промптов: {data}")
                    if hasattr(self, "media_prompt_button") and self.media_prompt_button.winfo_exists():
                        self.media_prompt_button.config(state="normal")
                    if hasattr(self, "media_limit_label") and self.media_limit_label.winfo_exists():
                        self.media_limit_label.config(fg="#35D99A")
                    self._render_media_prompts()
                elif kind == "media_prompts_error":
                    self.media_running = False
                    self.system_status.config(text="Ошибка создания промптов")
                    if hasattr(self, "media_prompt_button") and self.media_prompt_button.winfo_exists():
                        self.media_prompt_button.config(state="normal")
                    if "лимит" in data.lower() and hasattr(self, "media_limit_label") and self.media_limit_label.winfo_exists():
                        self.media_limit_label.config(fg="#FF5D73")
                    messagebox.showerror("Промпты Фото / Видео", data, parent=self.root)
                elif kind == "media_error":
                    self.media_running = False
                    self.system_status.config(text="Ошибка генерации медиа")
                    if hasattr(self, "media_generate_button") and self.media_generate_button.winfo_exists():
                        self.media_generate_button.config(state="normal")
                    messagebox.showerror("Фото / Видео", data, parent=self.root)
                elif kind == "seo_job":
                    self._render_seo_items()
                    self.system_status.config(text=f"SEO: {data.get('source_title', '')}")
                elif kind == "seo_complete":
                    self.seo_running = False
                    self.system_status.config(text="SEO-пакеты готовы")
                    if hasattr(self, "seo_generate_button") and self.seo_generate_button.winfo_exists():
                        self.seo_generate_button.config(state="normal")
                    self._render_seo_items()
                elif kind == "fatal":
                    self.running = False; self.active_runner = None; self.system_status.config(text="Ошибка")
                    messagebox.showerror("Ошибка", data, parent=self.root)
        except queue.Empty:
            pass
        self.root.after(100, self._process_events)

    def _update_counters(self):
        running = sum(job.state == RunState.RUNNING for job in self.jobs)
        done = sum(job.state == RunState.DONE for job in self.jobs)
        errors = sum(job.state == RunState.ERROR for job in self.jobs)
        cancelled = sum(job.state == RunState.CANCELLED for job in self.jobs)
        paused = sum(job.state == RunState.PAUSED for job in self.jobs)
        waiting = max(0, len(self.titles) - running - done - errors - cancelled - paused)
        self.counter_labels["waiting"].config(text=str(waiting))
        self.counter_labels["running"].config(text=str(running))
        self.counter_labels["done"].config(text=str(done))
        self._update_key_badge()
        self._refresh_pipeline_calculator()
        if hasattr(self, "progress") and self.progress.winfo_exists():
            finished = done + errors + cancelled + paused
            self.progress["maximum"] = max(1, len(self.titles)); self.progress["value"] = finished
            if hasattr(self, "run_status") and self.run_status.winfo_exists():
                self.run_status.config(text=f"Обработано {finished} из {len(self.titles)}")

    def _save_pipeline_target(self):
        try:
            self.settings.pipeline_target_count = max(1, int(self.pipeline_target_entry.get().strip()))
        except ValueError:
            messagebox.showerror("Конвейер", "Цель должна быть целым числом больше нуля.", parent=self.root)
            return
        self.pipeline_target_entry.delete(0, "end")
        self.pipeline_target_entry.insert(0, str(self.settings.pipeline_target_count))
        if self.settings.idea_target_follows_pipeline:
            self.settings.idea_target_count = self.settings.pipeline_target_count
            self._set_idea_target_entry(self.settings.idea_target_count)
        save_settings(self.settings)
        self._render_idea_plan()
        self._refresh_pipeline_calculator()

    def _refresh_pipeline_calculator(self):
        if not hasattr(self, "pipeline_labels"):
            return
        target = max(1, int(self.settings.pipeline_target_count))
        voice_ready = sum(1 for index, path in self.settings.voice_scenario_outputs.items()
                          if str(index).isdigit() and Path(path).is_file())
        montage_ready = sum(1 for path in self.settings.pipeline_montage_outputs if Path(path).is_file())
        values = {
            "ideas": len(self.titles),
            "scripts": sum(job.state == RunState.DONE for job in self.jobs),
            "voice": voice_ready,
            "montage": montage_ready,
        }
        for key, count in values.items():
            label = self.pipeline_labels.get(key)
            if label and label.winfo_exists():
                label.config(text=f"{count} / {target}", fg="#35D99A" if count >= target else TEXT)

    def _update_key_badge(self):
        self.key_badge.config(text=str(len(self.settings.active_sessions)))

    def _export_registry(self, page):
        export_root = storyflow_documents_root()
        export_root.mkdir(parents=True, exist_ok=True)
        if page == "covers":
            folder = Path(self.settings.cover_output_folder)
            folder.mkdir(parents=True, exist_ok=True)
            blocks = []
            for index, item in enumerate(self.cover_items, 1):
                blocks.append(f"{index}. {item['title']}\nПРОМПТ:\n{item.get('image_prompt', '')}\nФАЙЛ: {item.get('path', '')}")
            path = folder / "Обложки — готовое и промпты.txt"
            path.write_text("\n\n".join(blocks), encoding="utf-8-sig")
        elif page == "media":
            folder = self._media_output_folder()
            folder.mkdir(parents=True, exist_ok=True)
            blocks = []
            for index, item in enumerate(self._current_media_prompts(), 1):
                blocks.append(f"{index}.\n{item['prompt']}\nФАЙЛ: {item.get('path', '')}")
            kind = "Фото" if self.media_mode == "image" else "Видео"
            path = folder / f"{kind} — готовое и промпты.txt"
            path.write_text("\n\n".join(blocks), encoding="utf-8-sig")
        elif page == "templates":
            lines = ["ШАБЛОН СЦЕНАРИЯ", self.settings.template, "", "ШАБЛОНЫ ПО НИШАМ"]
            for index, item in enumerate(self.settings.scenario_templates, 1):
                lines.extend([f"{index}. {item.get('name', '')} — {item.get('topic', '')}", item.get("template", ""), ""])
            folder = export_root / "Шаблоны"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / "Шаблоны StoryFlow.txt"
            path.write_text("\n".join(lines), encoding="utf-8-sig")
        elif page == "keys":
            lines = ["CHROME-СЕССИИ STORYFLOW"]
            for index, item in enumerate(self.settings.chrome_sessions, 1):
                status = "включена" if item.active else "выключена"
                lines.append(f"{index}. {item.label} • {status} • профиль {item.profile_id[:12]}")
            folder = export_root / "Сессии Chrome"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / "Chrome-сессии.txt"
            path.write_text("\n".join(lines), encoding="utf-8-sig")
        elif page == "api_keys":
            lines = [f"МОДЕЛЬ: {self.settings.openai_model}", "", "OPENAI API-КЛЮЧИ (БЕЗ СЕКРЕТОВ)"]
            for index, item in enumerate(self.settings.openai_api_keys, 1):
                status = "включён" if item.active else "выключен"
                lines.append(f"{index}. {item.label} • {status}")
            folder = export_root / "API-ключи"
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / "OpenAI API — настройки.txt"
            path.write_text("\n".join(lines), encoding="utf-8-sig")
        else:
            return None
        self.last_saved_paths[page] = str(path)
        return path

    def _download_current(self):
        page = self.current_page
        try:
            if page == "ideas":
                path = self._save_ideas_txt()
            elif page in ("scenarios", "outputs"):
                paths = self._export()
                path = paths[0] if paths else None
            elif page == "seo":
                count = self._export_seo_separate(open_folder=False)
                if not count:
                    return
                self._export_seo_combined(open_folder=False)
                path = Path(self.settings.seo_output_folder) / "Все SEO-пакеты.txt"
                self.last_saved_paths[page] = str(path)
            else:
                path = self._export_registry(page)
            if path:
                messagebox.showinfo("Скачать готовое", f"Сохранено:\n{path}", parent=self.root)
        except Exception as exc:
            messagebox.showerror("Скачать готовое", str(exc), parent=self.root)

    def _open_current_saved(self):
        page = self.current_page
        try:
            folders = {
                "ideas": Path(self.settings.idea_output_folder),
                "scenarios": Path(self.settings.output_folder), "outputs": Path(self.settings.output_folder),
                "covers": Path(self.settings.cover_output_folder), "media": self._media_output_folder(),
                "seo": Path(self.settings.seo_output_folder),
                "templates": storyflow_documents_root() / "Шаблоны",
                "keys": storyflow_documents_root() / "Сессии Chrome",
                "api_keys": storyflow_documents_root() / "API-ключи",
            }
            saved = self.last_saved_paths.get(page)
            if saved and Path(saved).exists():
                os.startfile(saved)
                return
            folder = folders.get(page)
            if folder:
                folder.mkdir(parents=True, exist_ok=True)
                os.startfile(folder)
        except Exception as exc:
            messagebox.showerror("Открыть сохранённое", str(exc), parent=self.root)

    def _export(self):
        completed = [(job.request.title, job.result) for job in self.jobs if job.state == RunState.DONE]
        if not completed:
            messagebox.showinfo("Экспорт", "Пока нет готовых сценариев", parent=self.root); return []
        folder = ""
        if hasattr(self, "output_entry") and self.output_entry.winfo_exists():
            folder = self.output_entry.get().strip()
        folder = folder or self.settings.output_folder or filedialog.askdirectory()
        if folder:
            paths = write_exports(Path(folder), completed)
            self.settings.output_folder = folder; save_settings(self.settings)
            self.last_saved_paths["scenarios"] = str(paths[0]) if paths else str(folder)
            self.last_saved_paths["outputs"] = str(paths[0]) if paths else str(folder)
            messagebox.showinfo("Готово", f"Сохранено файлов: {len(paths)}", parent=self.root)
            return paths
        return []

    def _auto_export_completed(self):
        completed = [(job.request.title, job.result) for job in self.jobs if job.state == RunState.DONE]
        if not completed or not self.settings.output_folder:
            return []
        paths = write_exports(Path(self.settings.output_folder), completed)
        if hasattr(self, "run_status") and self.run_status.winfo_exists():
            self.run_status.config(text=f"Сохранено: {self.settings.output_folder}")
        return paths

    def _show_result(self, _):
        if not self.table:
            return
        selected = self.table.selection()
        if not selected or selected[0] == "empty":
            return
        index = int(selected[0])
        job = next((item for item in self.jobs if item.request.index == index), None)
        if not job:
            return
        window = tk.Toplevel(self.root, bg=BG); window.title(job.request.title); window.geometry("820x620")
        header = tk.Frame(window, bg=BG)
        header.pack(fill="x", padx=16, pady=(14, 0))
        color = "#35D99A" if job.state == RunState.DONE else "#FFD166" if job.state == RunState.PAUSED else "#FF7184"
        tk.Label(header, text=job.state.value, bg=BG, fg=color,
                 font=("Segoe UI Semibold", 11)).pack(side="left")
        self._button(header, "✎ Изменить тему", lambda: self._edit_selected_title(index)).pack(side="right")
        text = tk.Text(window, bg=CARD, fg=TEXT, insertbackground=TEXT, wrap="word", padx=20, pady=20,
                       relief="flat", font=("Segoe UI", 10))
        text.pack(fill="both", expand=True, padx=16, pady=16)
        details = [f"ТЕМА\n{job.request.title}", f"СТАТУС\n{job.state.value}"]
        if job.error:
            details.append(f"ПРИЧИНА / ОШИБКА\n{job.error}")
        details.append(f"ОТПРАВЛЕННЫЙ ПРОМПТ\n{job.request.prompt}")
        details.append(f"ОТВЕТ CLAUDE\n{job.result or 'Claude не вернул текстовый ответ.'}")
        text.insert("1.0", "\n\n".join(details))
        self._install_edit_bindings(text, multiline=True)

    def _close(self):
        if self.current_page == "templates":
            self._sync_template_settings()
        try:
            save_settings(self.settings)
            save_session(self.titles, self.jobs)
        finally:
            self.root.destroy()

    def run(self):
        self.root.mainloop()
