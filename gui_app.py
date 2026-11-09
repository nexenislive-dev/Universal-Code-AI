#!/usr/bin/env python3
"""Mobile UI for Universal Code AI. Long-running work is kept off the UI thread."""
from __future__ import annotations
import threading
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView

from config import SUPPORTED_LANGUAGES, PROJECTS_DIR
from core.knowledge_db import KnowledgeDB
from core.training_manager import TrainingManager
from core.code_generator import CodeGenerator
from core.local_model import LocalModel
from core.module_manager import ModuleManager
from core.model_manager import ModelManager
from core.project_generator import ProjectGenerator


class MainLayout(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", padding=dp(8), spacing=dp(6), **kwargs)
        self.db = KnowledgeDB()
        self.trainer = TrainingManager(self.db)
        self.generator = CodeGenerator(self.db)
        self.modules = ModuleManager(self.db)
        self.model = LocalModel()
        self.model_manager = ModelManager()
        self.project_writer = ProjectGenerator(PROJECTS_DIR)
        self.last_content = ""

        self.status = Label(text="Universal Code AI | Checking local model…", size_hint_y=None,
                            height=dp(42), halign="left", valign="middle")
        self.status.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        self.add_widget(self.status)

        langrow = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(5))
        langrow.add_widget(Label(text="Language", size_hint_x=.28))
        self.lang = Spinner(text="auto", values=["auto"] + SUPPORTED_LANGUAGES)
        langrow.add_widget(self.lang)
        self.add_widget(langrow)

        self.request = TextInput(hint_text="Describe what code or project you want…",
                                 multiline=True, size_hint_y=None, height=dp(112))
        self.add_widget(self.request)

        actions = GridLayout(cols=2, size_hint_y=None, height=dp(92), spacing=dp(5))
        self.generate_btn = Button(text="Generate code")
        self.generate_btn.bind(on_press=self.generate)
        actions.add_widget(self.generate_btn)
        save_btn = Button(text="Save project ZIP")
        save_btn.bind(on_press=self.save_project)
        actions.add_widget(save_btn)
        progress_btn = Button(text="Learning progress")
        progress_btn.bind(on_press=lambda *_: self.run_bg(self.show_progress))
        actions.add_widget(progress_btn)
        model_btn = Button(text="Local model status")
        model_btn.bind(on_press=lambda *_: self.run_bg(self.show_model_status))
        actions.add_widget(model_btn)
        self.add_widget(actions)

        online_row = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(5))
        self.online_btn = Button(text=self.online_label())
        self.online_btn.bind(on_press=self.toggle_online)
        online_row.add_widget(self.online_btn)
        learn_btn = Button(text="Learn documentation URL")
        learn_btn.bind(on_press=self.learn_url_dialog)
        online_row.add_widget(learn_btn)
        self.add_widget(online_row)

        scroll = ScrollView(do_scroll_x=False)
        self.output = TextInput(text="Ready. Start llama.cpp in Termux, then connect to 127.0.0.1:8080.",
                                readonly=True, multiline=True, size_hint_y=None, font_size="13sp")
        self.output.bind(minimum_height=self.output.setter("height"))
        self.output.height = dp(360)
        scroll.add_widget(self.output)
        self.add_widget(scroll)
        Clock.schedule_once(lambda *_: self.refresh_status(), 0.2)

    def online_label(self):
        return "Online learning: ON" if self.modules.online_enabled() else "Online learning: OFF"

    def refresh_status(self):
        stats = self.db.get_stats()
        health = self.model.health()
        model_state = "LOCAL MODEL ONLINE" if health.get("available") else "LOCAL MODEL OFFLINE"
        self.status.text = (f"{model_state} | Verified examples: {stats.get('verified_examples', 0)} | "
                            f"Languages: {stats.get('languages_covered', 0)}")
        self.online_btn.text = self.online_label()

    def run_bg(self, fn, *args):
        self.output.text = "Working…"
        def worker():
            try:
                result = fn(*args)
                Clock.schedule_once(lambda dt: setattr(self.output, "text", str(result)), 0)
                Clock.schedule_once(lambda dt: self.refresh_status(), 0)
            except Exception as exc:
                message = str(exc)
                Clock.schedule_once(lambda dt, msg=message: setattr(self.output, "text", f"Error: {msg}"), 0)
            finally:
                Clock.schedule_once(lambda dt: setattr(self.generate_btn, "disabled", False), 0)
        threading.Thread(target=worker, daemon=True).start()

    def generate(self, *_):
        request = self.request.text.strip()
        if not request:
            self.output.text = "Please describe the code you need."
            return
        language = None if self.lang.text == "auto" else self.lang.text
        self.generate_btn.disabled = True
        def work():
            result = self.generator.generate(request, language=language)
            self.last_content = result.get("content", "")
            mode = result.get("mode", "unknown").upper()
            return (f"MODE: {mode} | LANGUAGE: {result.get('language', '?')}\n"
                    f"VERIFIED: {result.get('verified', False)}\n\n{self.last_content}")
        self.run_bg(work)

    def save_project(self, *_):
        if not self.last_content.strip():
            self.output.text = "Generate a multi-file project first."
            return
        name_input = TextInput(text="my_project", multiline=False)
        box = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(8))
        box.add_widget(Label(text="Project name"))
        box.add_widget(name_input)
        popup = Popup(title="Export project ZIP", content=box, size_hint=(.9, .35))
        btn = Button(text="Create ZIP", size_hint_y=None, height=dp(44))
        def save(*_):
            popup.dismiss()
            self.run_bg(lambda: self.project_writer.save(self.last_content, name_input.text.strip()))
        btn.bind(on_press=save)
        box.add_widget(btn)
        popup.open()

    def show_progress(self):
        return self.trainer.get_report()

    def show_model_status(self):
        info = self.model_manager.device_info()
        info["server_health"] = self.model.health()
        info["model_list"] = self.model.list_models()
        return info

    def toggle_online(self, *_):
        if self.modules.online_enabled():
            self.modules.disable_online_learning()
        else:
            if self.db.get_state("online_learning_removed", "0") == "1":
                self.output.text = "Online module was marked removed. Restore it from backup before re-enabling."
                return
            self.modules.enable_online_learning()
        self.refresh_status()
        self.output.text = self.online_label() + ". Local model and local database are unchanged."

    def learn_url_dialog(self, *_):
        url_input = TextInput(hint_text="https://official-documentation.example/", multiline=False)
        box = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(8))
        box.add_widget(url_input)
        btn = Button(text="Fetch and save", size_hint_y=None, height=dp(44))
        popup = Popup(title="Learn public documentation", content=box, size_hint=(.92, .32))
        def learn(*_):
            url = url_input.text.strip()
            popup.dismiss()
            if not url.startswith("https://"):
                self.output.text = "Use a valid HTTPS documentation URL."
                return
            self.run_bg(lambda: self.generator.learn_url(url))
        btn.bind(on_press=learn)
        box.add_widget(btn)
        popup.open()


class UniversalCodeAIApp(App):
    def build(self):
        self.title = "Universal Code AI"
        return MainLayout()
