# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Rectangle, RoundedRectangle, Line, Ellipse
from kivy.metrics import dp
from kivy.properties import ListProperty, StringProperty, ObjectProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.label import Label
from kivy.uix.widget import Widget

from calculations import PRESSURES, calculate_capillary, export_csv, rho_from_salinity, to_float, r4

Window.clearcolor = (0.035, 0.040, 0.052, 1)
Window.softinput_mode = "below_target"

BG = (0.035, 0.040, 0.052, 1)
PANEL = (0.075, 0.083, 0.105, 1)
PANEL2 = (0.105, 0.115, 0.145, 1)
FIELD_BG = (0.045, 0.052, 0.067, 1)
TEXT = (0.93, 0.95, 0.98, 1)
MUTED = (0.66, 0.70, 0.77, 1)
GRID = (0.36, 0.40, 0.48, 1)
ACC = (0.10, 0.58, 0.98, 1)
OK = (0.08, 0.72, 0.35, 1)
WARN = (1.00, 0.56, 0.12, 1)
MAN = (0.18, 0.56, 1.00, 1)
BAD = (0.92, 0.20, 0.20, 1)


def safe_float(v: Any, default: Optional[float] = None) -> Optional[float]:
    x = to_float(v, default)
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return default
    return x


def fmt(v: Any, n: int = 3) -> str:
    x = safe_float(v)
    return "—" if x is None else f"{x:.{n}f}"


class Card(BoxLayout):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.padding = dp(8)
        self.spacing = dp(6)
        self.bind(pos=self._draw_bg, size=self._draw_bg)

    def _draw_bg(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*PANEL)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(8)])


class T(Label):
    def __init__(self, **kw):
        kw.setdefault("color", TEXT)
        kw.setdefault("font_size", dp(12))
        kw.setdefault("halign", "left")
        kw.setdefault("valign", "middle")
        super().__init__(**kw)
        self.bind(size=lambda obj, *_: setattr(obj, "text_size", obj.size))


class CButton(Button):
    def __init__(self, **kw):
        kw.setdefault("font_size", dp(12))
        kw.setdefault("background_normal", "")
        kw.setdefault("background_color", (0.17, 0.19, 0.23, 1))
        kw.setdefault("color", TEXT)
        super().__init__(**kw)


class NavButton(CButton):
    def set_active(self, active: bool):
        self.background_color = ACC if active else (0.16, 0.17, 0.20, 1)


class NumberInput(TextInput):
    def __init__(self, **kw):
        kw.setdefault("multiline", False)
        kw.setdefault("font_size", dp(14))
        kw.setdefault("foreground_color", TEXT)
        kw.setdefault("background_normal", "")
        kw.setdefault("background_active", "")
        kw.setdefault("background_color", FIELD_BG)
        kw.setdefault("cursor_color", ACC)
        kw.setdefault("padding", [dp(8), dp(7), dp(8), dp(7)])
        super().__init__(**kw)


class FieldRow(BoxLayout):
    def __init__(self, caption: str, default: str = "", **kw):
        super().__init__(orientation="horizontal", size_hint_y=None, height=dp(34), spacing=dp(6), **kw)
        self.add_widget(T(text=caption, size_hint_x=0.46, color=MUTED, halign="right", font_size=dp(12)))
        self.input = NumberInput(text=str(default))
        self.add_widget(self.input)


class Plot(Widget):
    points = ListProperty([])
    mode = StringProperty("ps")
    app_ref = ObjectProperty(None)

    def __init__(self, **kw):
        super().__init__(**kw)
        self.drag_idx = None
        self.bind(pos=lambda *_: self.draw(), size=lambda *_: self.draw(), points=lambda *_: self.draw())

    def chart_rect(self):
        return (self.x + dp(55), self.y + dp(36), max(dp(220), self.width - dp(85)), max(dp(140), self.height - dp(72)))

    def ranges(self):
        if self.mode == "ps":
            return 0.0, 100.0, math.log10(0.25), math.log10(10.0)
        vals = [safe_float(p[1]) for p in self.points if safe_float(p[1]) is not None]
        if not vals:
            return 10.0, 0.0, 0.0, 1.0
        lo, hi = min(vals), max(vals)
        if hi - lo < 1e-9:
            hi = lo + 1.0
        pad = (hi - lo) * 0.18
        return 10.0, 0.0, max(0.0, lo - pad), hi + pad

    def map_y(self, y):
        if self.mode == "ps":
            return math.log10(max(0.25, float(y)))
        return float(y)

    def data_to_screen(self, x, y):
        ax, ay, w, h = self.chart_rect()
        xmin, xmax, ymin, ymax = self.ranges()
        if self.mode == "rp":  # pressure axis is inverted: 10 at left, 0 at right
            sx = ax + (xmin - float(x)) / (xmin - xmax) * w
        else:
            sx = ax + (float(x) - xmin) / (xmax - xmin) * w
        yy = self.map_y(y)
        sy = ay + (yy - ymin) / (ymax - ymin) * h
        return sx, sy

    def screen_to_data(self, sx, sy):
        ax, ay, w, h = self.chart_rect()
        xmin, xmax, ymin, ymax = self.ranges()
        tx = max(0.0, min(1.0, (sx - ax) / w))
        ty = max(0.0, min(1.0, (sy - ay) / h))
        if self.mode == "rp":
            x = xmin - tx * (xmin - xmax)
        else:
            x = xmin + tx * (xmax - xmin)
        y = ymin + ty * (ymax - ymin)
        if self.mode == "ps":
            y = 10 ** y
        return x, y

    def label(self, text, x, y, size=10, color=MUTED, anchor="c"):
        lab = CoreLabel(text=str(text), font_size=dp(size), color=color)
        lab.refresh()
        tex = lab.texture
        tw, th = tex.size
        px = x - tw / 2 if anchor == "c" else (x - tw if anchor == "r" else x)
        py = y - th / 2
        Color(1, 1, 1, 1)
        Rectangle(texture=tex, pos=(px, py), size=tex.size)

    def draw(self):
        self.canvas.clear()
        with self.canvas:
            Color(0.025, 0.030, 0.040, 1)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(8)])
            ax, ay, w, h = self.chart_rect()
            Color(0.065, 0.073, 0.090, 1)
            Rectangle(pos=(ax, ay), size=(w, h))
            Color(*GRID)
            if self.mode == "ps":
                for x in [0, 20, 40, 60, 80, 100]:
                    sx, _ = self.data_to_screen(x, 0.25)
                    Line(points=[sx, ay, sx, ay + h], width=0.75)
                    self.label(x, sx, ay - dp(15), 9)
                for y in [0.25, 0.5, 1, 3, 5, 7, 10]:
                    _, sy = self.data_to_screen(0, y)
                    Line(points=[ax, sy, ax + w, sy], width=0.75)
                    self.label(y, ax - dp(8), sy, 9, anchor="r")
                self.label("S, %", ax + w / 2, self.y + dp(13), 11, TEXT)
                self.label("P, атм", self.x + dp(26), ay + h + dp(13), 11, TEXT)
            else:
                xmin, xmax, ymin, ymax = self.ranges()
                for x in [10, 7, 5, 3, 1, 0]:
                    sx, _ = self.data_to_screen(x, ymin)
                    Line(points=[sx, ay, sx, ay + h], width=0.75)
                    self.label(x, sx, ay - dp(15), 9)
                for i in range(5):
                    y = ymin + (ymax - ymin) * i / 4
                    _, sy = self.data_to_screen(0, y)
                    Line(points=[ax, sy, ax + w, sy], width=0.75)
                    self.label(fmt(y, 2), ax - dp(8), sy, 9, anchor="r")
                self.label("P, атм  (10 → 0)", ax + w / 2, self.y + dp(13), 11, TEXT)
                self.label("R, Ом·м", self.x + dp(28), ay + h + dp(13), 11, TEXT)
            Color(0.85, 0.88, 0.94, 1)
            Line(rectangle=(ax, ay, w, h), width=1.0)
            valid = []
            for x, y, col, idx, label, src in self.points:
                if safe_float(x) is None or safe_float(y) is None:
                    continue
                sx, sy = self.data_to_screen(x, y)
                valid.append((sx, sy, col, idx, label, src, x, y))
            valid.sort(key=lambda q: q[7] if self.mode == "ps" else -q[6])
            if len(valid) > 1:
                Color(0.78, 0.82, 0.88, 1)
                Line(points=[v for p in valid for v in p[:2]], width=1.4)
            for sx, sy, col, idx, lab, src, x, y in valid:
                Color(*col)
                Ellipse(pos=(sx - dp(8), sy - dp(8)), size=(dp(16), dp(16)))
                self.label(lab, sx + dp(12), sy + dp(11), 9, TEXT, anchor="l")

    def nearest(self, touch):
        best = (None, 1e18)
        for x, y, col, idx, label, src in self.points:
            if safe_float(x) is None or safe_float(y) is None:
                continue
            sx, sy = self.data_to_screen(x, y)
            d = (touch.x - sx) ** 2 + (touch.y - sy) ** 2
            if d < best[1]:
                best = (idx, d)
        return best[0] if best[1] <= dp(45) ** 2 else None

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        self.drag_idx = self.nearest(touch)
        return self.drag_idx is not None

    def on_touch_move(self, touch):
        if self.drag_idx is None:
            return False
        x, y = self.screen_to_data(touch.x, touch.y)
        if self.app_ref:
            if self.mode == "ps":
                self.app_ref.drag_s(self.drag_idx, max(0, min(100, x)) / 100.0)
            else:
                self.app_ref.drag_r(self.drag_idx, max(0.0, y))
        return True

    def on_touch_up(self, touch):
        self.drag_idx = None
        return False


class CapillApp(App):
    title = "Капилляриметрия Android"

    def build(self):
        Window.orientation = "landscape"
        self.fields: Dict[str, NumberInput] = {}
        self.step_rows: List[Dict[str, Any]] = []
        self.manual_s: Dict[int, float] = {}
        self.manual_r: Dict[int, float] = {}
        self.current: Optional[Dict[str, Any]] = None
        self.current_screen = "data"

        root = BoxLayout(orientation="vertical", padding=[dp(8), dp(4)], spacing=dp(5))
        header = BoxLayout(size_hint_y=None, height=dp(34))
        header.add_widget(T(text="Капилляриметрия Android FULL", font_size=dp(20), bold=True, halign="center"))
        root.add_widget(header)

        self.nav = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(4))
        self.nav_buttons = {}
        for key, title in [("data", "Исходные"), ("steps", "Ступени"), ("graphs", "Графики"), ("results", "Результаты"), ("files", "Файлы")]:
            b = NavButton(text=title)
            b.bind(on_press=lambda _, k=key: self.show(k))
            self.nav_buttons[key] = b
            self.nav.add_widget(b)
        root.add_widget(self.nav)

        self.content = BoxLayout()
        root.add_widget(self.content)
        self.status = T(text="Готово", size_hint_y=None, height=dp(25), color=MUTED)
        root.add_widget(self.status)

        self.init_data_widgets()
        self.show("data")
        Clock.schedule_once(lambda *_: self.update_rho(), 0.1)
        return root

    def set_card_title(self, box, title):
        box.add_widget(T(text=title, size_hint_y=None, height=dp(24), font_size=dp(14), bold=True))

    def init_data_widgets(self):
        pass

    def show(self, key):
        self.current_screen = key
        for k, b in self.nav_buttons.items():
            b.set_active(k == key)
        self.content.clear_widgets()
        if key == "data":
            self.build_data_screen()
        elif key == "steps":
            self.build_steps_screen()
        elif key == "graphs":
            self.build_graphs_screen()
        elif key == "results":
            self.build_results_screen()
        else:
            self.build_files_screen()

    def input_panel(self):
        panel = Card(orientation="vertical", size_hint_x=0.36)
        self.set_card_title(panel, "Исходные данные")
        scroll = ScrollView()
        grid = GridLayout(cols=1, size_hint_y=None, spacing=dp(4))
        grid.bind(minimum_height=grid.setter("height"))
        fields = [
            ("D", "D, мм", ""), ("L", "L, мм", ""), ("salinity", "Минерал., г/л", "0"),
            ("rho", "ρ, г/см³", "0.9982"), ("m_dry", "m сух, г", ""), ("m_sat", "m насыщ, г", ""),
            ("R0", "R0, Ом·м", ""), ("R_water", "Rw, Ом·м", "1"),
        ]
        for key, cap, default in fields:
            if key not in self.fields:
                row = FieldRow(cap, default)
                self.fields[key] = row.input
                row.input.bind(text=lambda *_: self.live())
                setattr(self, "fieldrow_" + key, row)
            grid.add_widget(getattr(self, "fieldrow_" + key))
        ar = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(6))
        ar.add_widget(T(text="Авто ρ по минерализации", color=MUTED, halign="right"))
        if not hasattr(self, "auto_rho"):
            self.auto_rho = CheckBox(active=True, size_hint_x=None, width=dp(46))
            self.auto_rho.bind(active=lambda *_: self.update_rho())
        ar.add_widget(self.auto_rho)
        grid.add_widget(ar)
        scroll.add_widget(grid)
        panel.add_widget(scroll)
        btns = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))
        for title, cb, color in [("Рассчитать", self.calculate, ACC), ("Сброс drag", self.reset_drag, (0.18,0.20,0.24,1)), ("Очистить", self.clear_steps, (0.18,0.20,0.24,1))]:
            b = CButton(text=title, background_color=color)
            b.bind(on_press=lambda _, f=cb: f())
            btns.add_widget(b)
        panel.add_widget(btns)
        return panel

    def summary_panel(self):
        panel = Card(orientation="vertical")
        self.set_card_title(panel, "Сводка")
        if not hasattr(self, "summary_label"):
            self.summary_label = T(text="Заполните исходные данные и ступени.", font_size=dp(13))
        panel.add_widget(self.summary_label)
        return panel

    def build_data_screen(self):
        box = BoxLayout(orientation="horizontal", spacing=dp(6))
        box.add_widget(self.input_panel())
        right = BoxLayout(orientation="vertical", spacing=dp(6))
        right.add_widget(self.summary_panel())
        quick = Card(orientation="vertical", size_hint_y=0.45)
        self.set_card_title(quick, "Быстрая проверка")
        if not hasattr(self, "hint_label"):
            self.hint_label = T(text="Введите D, L, m сух, m насыщ. Затем заполните массу/R на вкладке Ступени и нажмите Рассчитать.", color=MUTED)
        quick.add_widget(self.hint_label)
        right.add_widget(quick)
        box.add_widget(right)
        self.content.add_widget(box)

    def ensure_step_widgets(self):
        if self.step_rows:
            return
        for p in PRESSURES:
            cb = CheckBox(active=True)
            m = NumberInput(text="")
            r = NumberInput(text="")
            cb.bind(active=lambda *_: self.live())
            m.bind(text=lambda *_: self.live())
            r.bind(text=lambda *_: self.live())
            self.step_rows.append({"P": p, "en": cb, "m": m, "R": r})

    def build_steps_screen(self):
        self.ensure_step_widgets()
        panel = Card(orientation="vertical")
        self.set_card_title(panel, "Ступени опыта: P / включение / масса / сопротивление")
        hdr = GridLayout(cols=4, size_hint_y=None, height=dp(30), spacing=dp(4))
        for text, sx in [("P, атм", .16), ("Вкл", .10), ("Масса, г", .37), ("R, Ом·м", .37)]:
            hdr.add_widget(T(text=text, bold=True, halign="center", font_size=dp(13)))
        panel.add_widget(hdr)
        scroll = ScrollView()
        grid = GridLayout(cols=4, size_hint_y=None, spacing=dp(4), row_default_height=dp(44))
        grid.bind(minimum_height=grid.setter("height"))
        for row in self.step_rows:
            grid.add_widget(T(text=str(row["P"]), halign="center", font_size=dp(13)))
            grid.add_widget(row["en"])
            grid.add_widget(row["m"])
            grid.add_widget(row["R"])
        scroll.add_widget(grid)
        panel.add_widget(scroll)
        self.content.add_widget(panel)

    def ensure_graph_widgets(self):
        if not hasattr(self, "gps"):
            self.gps = Plot(mode="ps", app_ref=self)
            self.grp = Plot(mode="rp", app_ref=self)

    def build_graphs_screen(self):
        self.ensure_graph_widgets()
        box = BoxLayout(orientation="horizontal", spacing=dp(6))
        left = Card(orientation="vertical")
        right = Card(orientation="vertical")
        left.add_widget(T(text="P–S: перетаскивание точки по X меняет насыщенность S%", size_hint_y=None, height=dp(24), bold=True))
        right.add_widget(T(text="R–P: перетаскивание точки по Y меняет сопротивление R", size_hint_y=None, height=dp(24), bold=True))
        left.add_widget(self.gps)
        right.add_widget(self.grp)
        box.add_widget(left)
        box.add_widget(right)
        self.content.add_widget(box)
        self.refresh_plots_only()

    def build_results_screen(self):
        panel = Card(orientation="vertical")
        self.set_card_title(panel, "Результаты расчёта")
        scroll = ScrollView(do_scroll_x=True, do_scroll_y=True)
        if not hasattr(self, "res_grid"):
            self.res_grid = GridLayout(cols=13, size_hint=(None, None), row_default_height=dp(30), spacing=dp(2))
            self.res_grid.bind(minimum_height=self.res_grid.setter("height"))
            self.res_grid.bind(minimum_width=self.res_grid.setter("width"))
        scroll.add_widget(self.res_grid)
        panel.add_widget(scroll)
        self.content.add_widget(panel)
        self.render_results_table()

    def build_files_screen(self):
        panel = Card(orientation="vertical")
        self.set_card_title(panel, "Файлы и экспорт")
        for txt, cb in [("Сохранить проект JSON", self.save_project), ("Загрузить проект JSON", self.load_project), ("Экспорт CSV", self.export_csv_file)]:
            b = CButton(text=txt, size_hint_y=None, height=dp(44))
            b.bind(on_press=lambda _, f=cb: f())
            panel.add_widget(b)
        if not hasattr(self, "file_info"):
            self.file_info = T(text="Файлы сохраняются в папку приложения Android.", color=MUTED)
        panel.add_widget(self.file_info)
        self.content.add_widget(panel)

    def update_rho(self):
        if hasattr(self, "auto_rho") and self.auto_rho.active and "rho" in self.fields:
            self.fields["rho"].text = f"{rho_from_salinity(self.fields.get('salinity').text):.4f}"

    def live(self):
        if hasattr(self, "auto_rho") and self.auto_rho.active:
            self.update_rho()

    def data(self):
        return {k: v.text for k, v in self.fields.items()}

    def steps(self):
        self.ensure_step_widgets()
        return [{"P": r["P"], "en": r["en"].active, "m": r["m"].text, "R": r["R"].text} for r in self.step_rows]

    def calculate(self):
        try:
            self.current = calculate_capillary(self.data(), self.steps())
            self.apply_manual()
            self.render_all()
            self.status.text = "Расчёт выполнен"
        except Exception as e:
            self.status.text = "Ошибка: " + str(e)

    def apply_manual(self):
        if not self.current:
            return
        rows = self.current.get("rows", [])
        for i, v in self.manual_s.items():
            if 0 <= i < len(rows):
                rows[i]["S"] = v
                rows[i]["S_pct"] = v * 100.0
                rows[i]["mSrc"] = "drag"
        for i, v in self.manual_r.items():
            if 0 <= i < len(rows):
                rows[i]["R"] = v
                rows[i]["rSrc"] = "drag"

    def render_all(self):
        self.render_summary()
        self.refresh_plots_only()
        self.render_results_table()

    def render_summary(self):
        if not hasattr(self, "summary_label") or not self.current:
            return
        s = self.current.get("summary", {})
        self.summary_label.text = (
            f"Vобр = {r4(s.get('Vobr'))} см³\n"
            f"Vp = {r4(s.get('Vp'))} см³\n"
            f"m воды = {r4(s.get('m_water_total'))} г\n"
            f"Sов = {r4(s.get('Sov'))}\n"
            f"Kво = {r4(s.get('Kvo'))}\n"
            f"Kпор = {r4(s.get('Kpor'))}\n"
            f"Kпор эфф = {r4(s.get('Kpor_eff'))}\n"
            f"n Archie = {r4(s.get('n'))}"
        )

    def refresh_plots_only(self):
        if not hasattr(self, "gps") or not hasattr(self, "grp"):
            return
        if not self.current:
            self.gps.points = []
            self.grp.points = []
            return
        ps, rp = [], []
        for i, row in enumerate(self.current.get("rows", [])):
            msrc = row.get("mSrc")
            rsrc = row.get("rSrc")
            cm = MAN if i in self.manual_s else (OK if msrc == "измерено" else WARN)
            cr = MAN if i in self.manual_r else (OK if rsrc == "измерено" else WARN)
            ps.append((row.get("S_pct"), row.get("P"), cm, i, str(row.get("P")), msrc))
            rp.append((row.get("P"), row.get("R"), cr, i, str(row.get("P")), rsrc))
        self.gps.points = ps
        self.grp.points = rp

    def render_results_table(self):
        if not hasattr(self, "res_grid"):
            return
        self.res_grid.clear_widgets()
        headers = ["P", "m", "m src", "S%", "R", "R src", "Vv", "λ", "I", "logSw", "logI", "H м", "n"]
        for h in headers:
            cell = T(text=h, bold=True, halign="center", font_size=dp(10), size_hint_x=None, width=dp(86))
            self.res_grid.add_widget(cell)
        if not self.current:
            return
        for r in self.current.get("rows", []):
            vals = [
                r.get("P"), fmt(r.get("m"), 4), r.get("mSrc"), fmt(r.get("S_pct"), 2), fmt(r.get("R"), 4), r.get("rSrc"),
                fmt(r.get("Vv"), 4), fmt(r.get("lam"), 4), fmt(r.get("I"), 4), fmt(r.get("log_Sw"), 4), fmt(r.get("log_I"), 4), fmt(r.get("H_m"), 3), fmt(r.get("n"), 4)
            ]
            for v in vals:
                self.res_grid.add_widget(T(text=str(v), halign="center", font_size=dp(10), size_hint_x=None, width=dp(86)))

    def drag_s(self, idx, sval):
        self.manual_s[int(idx)] = float(sval)
        self.apply_manual()
        self.render_all()
        self.status.text = "S изменено вручную drag"

    def drag_r(self, idx, rval):
        self.manual_r[int(idx)] = float(rval)
        self.apply_manual()
        self.render_all()
        self.status.text = "R изменено вручную drag"

    def reset_drag(self):
        self.manual_s.clear()
        self.manual_r.clear()
        if self.current:
            self.calculate()
        else:
            self.status.text = "Drag сброшен"

    def clear_steps(self):
        self.ensure_step_widgets()
        for r in self.step_rows:
            r["m"].text = ""
            r["R"].text = ""
            r["en"].active = True
        self.manual_s.clear()
        self.manual_r.clear()
        self.current = None
        self.render_all()
        self.status.text = "Ступени очищены"

    def project_path(self):
        return Path(self.user_data_dir) / "capill_project.json"

    def save_project(self):
        obj = {"data": self.data(), "steps": self.steps(), "manual_s": self.manual_s, "manual_r": self.manual_r, "time": time.time()}
        p = self.project_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        if hasattr(self, "file_info"):
            self.file_info.text = "Сохранено: " + str(p)
        self.status.text = "Проект сохранён"

    def load_project(self):
        p = self.project_path()
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
            for k, v in obj.get("data", {}).items():
                if k in self.fields:
                    self.fields[k].text = str(v)
            self.ensure_step_widgets()
            for src, dst in zip(obj.get("steps", []), self.step_rows):
                dst["en"].active = bool(src.get("en", True))
                dst["m"].text = str(src.get("m") or "")
                dst["R"].text = str(src.get("R") or "")
            self.manual_s = {int(k): float(v) for k, v in obj.get("manual_s", {}).items()}
            self.manual_r = {int(k): float(v) for k, v in obj.get("manual_r", {}).items()}
            self.calculate()
            if hasattr(self, "file_info"):
                self.file_info.text = "Загружено: " + str(p)
        except Exception as e:
            if hasattr(self, "file_info"):
                self.file_info.text = "Ошибка загрузки: " + str(e)
            self.status.text = "Ошибка загрузки: " + str(e)

    def export_csv_file(self):
        if not self.current:
            self.calculate()
        if not self.current:
            return
        p = Path(self.user_data_dir) / ("capill_results_%d.csv" % int(time.time()))
        export_csv(p, self.current)
        if hasattr(self, "file_info"):
            self.file_info.text = "CSV: " + str(p)
        self.status.text = "CSV экспортирован"


if __name__ == "__main__":
    CapillApp().run()
