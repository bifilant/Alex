# -*- coding: utf-8 -*-
from __future__ import annotations

import math
from pathlib import Path

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Ellipse, Line, Rectangle
from kivy.metrics import dp
from kivy.properties import ListProperty, ObjectProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

from calculations import PRESSURES, calculate_capillary, export_csv, r4, rho_from_salinity, to_float

Window.clearcolor = (0.96, 0.96, 0.96, 1)

CLR_MEAS = (0.18, 0.49, 0.20, 1)
CLR_INTR = (0.94, 0.42, 0.00, 1)
CLR_MAN = (0.08, 0.40, 0.75, 1)
CLR_FIRST = (0, 0, 0, 1)
CLR_GRID = (0.72, 0.72, 0.72, 1)
CLR_LINE = (0.44, 0.48, 0.50, 1)
CLR_BG = (1, 1, 1, 1)


def ftext(v, digits=4):
    x = to_float(v)
    if x is None or math.isnan(x) or math.isinf(x):
        return "—"
    return f"{x:.{digits}f}"


class FieldRow(BoxLayout):
    def __init__(self, title: str, default: str = "", **kwargs):
        super().__init__(orientation="horizontal", size_hint_y=None, height=dp(42), spacing=dp(6), **kwargs)
        self.add_widget(Label(text=title, halign="right", valign="middle", size_hint_x=0.54, color=(0.05, 0.05, 0.05, 1)))
        self.input = TextInput(text=default, multiline=False, input_filter=None, font_size=dp(15), size_hint_x=0.46)
        self.add_widget(self.input)


class GraphWidget(Widget):
    points = ListProperty([])
    title = StringProperty("")
    mode = StringProperty("ps")  # ps or rp
    app_ref = ObjectProperty(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(pos=lambda *_: self.redraw(), size=lambda *_: self.redraw(), points=lambda *_: self.redraw())
        self._drag_index = None

    def set_points(self, points):
        self.points = points or []

    def _plot_area(self):
        x0 = self.x + dp(44)
        y0 = self.y + dp(34)
        w = max(dp(40), self.width - dp(62))
        h = max(dp(40), self.height - dp(68))
        return x0, y0, w, h

    def _ranges(self):
        if self.mode == "ps":
            return 0.0, 1.0, 0.0, 10.0
        ys = [p[1] for p in self.points if p[1] is not None and not math.isnan(p[1])]
        ymax = max(ys) if ys else 1.0
        return 10.0, 0.0, 0.0, max(1.0, ymax * 1.15)

    def data_to_screen(self, xd, yd):
        x0, y0, w, h = self._plot_area()
        xmin, xmax, ymin, ymax = self._ranges()
        # supports inverted x if xmax < xmin
        tx = (xd - xmin) / (xmax - xmin) if abs(xmax - xmin) > 1e-12 else 0
        ty = (yd - ymin) / (ymax - ymin) if abs(ymax - ymin) > 1e-12 else 0
        return x0 + tx * w, y0 + ty * h

    def screen_to_data(self, xs, ys):
        x0, y0, w, h = self._plot_area()
        xmin, xmax, ymin, ymax = self._ranges()
        tx = (xs - x0) / w
        ty = (ys - y0) / h
        return xmin + tx * (xmax - xmin), ymin + ty * (ymax - ymin)

    def redraw(self):
        self.canvas.clear()
        with self.canvas:
            Color(*CLR_BG)
            Rectangle(pos=self.pos, size=self.size)
            x0, y0, w, h = self._plot_area()
            Color(0.08, 0.08, 0.08, 1)
            Line(rectangle=(x0, y0, w, h), width=1)
            Color(*CLR_GRID)
            for i in range(1, 5):
                xx = x0 + w * i / 5
                yy = y0 + h * i / 5
                Line(points=[xx, y0, xx, y0 + h], width=0.7)
                Line(points=[x0, yy, x0 + w, yy], width=0.7)
            # линии
            screen_points = []
            for xd, yd, color, idx, label in self.points:
                if yd is None or math.isnan(yd) or xd is None or math.isnan(xd):
                    continue
                sx, sy = self.data_to_screen(float(xd), float(yd))
                screen_points.append((sx, sy))
            if len(screen_points) >= 2:
                Color(*CLR_LINE)
                Line(points=[v for p in screen_points for v in p], width=1.2)
            # точки
            for xd, yd, color, idx, label in self.points:
                if yd is None or math.isnan(yd) or xd is None or math.isnan(xd):
                    continue
                sx, sy = self.data_to_screen(float(xd), float(yd))
                Color(*color)
                r = dp(5.5) if idx != -100 else dp(7)
                Ellipse(pos=(sx - r, sy - r), size=(2 * r, 2 * r))

    def nearest_point(self, touch):
        best = None
        best_d2 = dp(28) ** 2
        for xd, yd, color, idx, label in self.points:
            if idx is None or idx < 0:
                continue
            if yd is None or math.isnan(yd) or xd is None or math.isnan(xd):
                continue
            sx, sy = self.data_to_screen(float(xd), float(yd))
            d2 = (touch.x - sx) ** 2 + (touch.y - sy) ** 2
            if d2 < best_d2:
                best_d2 = d2
                best = idx
        return best

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False
        idx = self.nearest_point(touch)
        if idx is not None:
            self._drag_index = idx
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if self._drag_index is None:
            return super().on_touch_move(touch)
        xd, yd = self.screen_to_data(touch.x, touch.y)
        if self.app_ref:
            if self.mode == "ps":
                self.app_ref.drag_s(self._drag_index, max(0.0, min(1.0, xd)))
            else:
                self.app_ref.drag_r(self._drag_index, max(0.0, yd))
        return True

    def on_touch_up(self, touch):
        self._drag_index = None
        return super().on_touch_up(touch)


class CapillAndroidApp(App):
    def build(self):
        self.title = "Капилляриметрия"
        self.current_result = None
        self.manual_s = {}
        self.manual_r = {}

        root = BoxLayout(orientation="vertical", padding=dp(6), spacing=dp(6))
        header = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        header.add_widget(Label(text="Капилляриметрия Android", font_size=dp(20), bold=True, color=(0, 0, 0, 1)))
        root.add_widget(header)

        body = BoxLayout(orientation="horizontal", spacing=dp(6))
        root.add_widget(body)

        left_scroll = ScrollView(size_hint_x=0.46)
        left = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6), padding=dp(4))
        left.bind(minimum_height=left.setter("height"))
        left_scroll.add_widget(left)
        body.add_widget(left_scroll)

        self.fields = {}
        for key, title, default in [
            ("D", "D, мм", ""),
            ("L", "L, мм", ""),
            ("salinity", "Минерализация, г/л", ""),
            ("rho", "ρ, г/см³", "1.0000"),
            ("m_dry", "m сух, г", ""),
            ("m_sat", "m нас, г", ""),
            ("R0", "R₀, Ом·м", ""),
            ("R_water", "ρв воды, Ом·м", "1.0"),
        ]:
            row = FieldRow(title, default)
            left.add_widget(row)
            self.fields[key] = row.input

        auto_box = BoxLayout(orientation="horizontal", size_hint_y=None, height=dp(38))
        auto_box.add_widget(Label(text="Авто ρ по минерализации", color=(0, 0, 0, 1)))
        self.auto_rho = CheckBox(active=True, size_hint_x=None, width=dp(56))
        auto_box.add_widget(self.auto_rho)
        left.add_widget(auto_box)
        self.fields["salinity"].bind(text=lambda *_: self.update_rho())
        self.auto_rho.bind(active=lambda *_: self.update_rho())

        left.add_widget(Label(text="Ступени", size_hint_y=None, height=dp(28), bold=True, color=(0, 0, 0, 1)))
        self.step_rows = []
        grid = GridLayout(cols=4, size_hint_y=None, spacing=dp(3), row_default_height=dp(38))
        grid.bind(minimum_height=grid.setter("height"))
        for h in ["P", "Вкл", "Масса", "R"]:
            grid.add_widget(Label(text=h, bold=True, color=(0, 0, 0, 1), size_hint_y=None, height=dp(28)))
        for p in PRESSURES:
            p_label = Label(text=str(p).rstrip("0").rstrip("."), color=(0, 0, 0, 1), size_hint_y=None, height=dp(38))
            en = CheckBox(active=True, size_hint_y=None, height=dp(38))
            mass = TextInput(text="", multiline=False, size_hint_y=None, height=dp(38), font_size=dp(14))
            res = TextInput(text="", multiline=False, size_hint_y=None, height=dp(38), font_size=dp(14))
            grid.add_widget(p_label); grid.add_widget(en); grid.add_widget(mass); grid.add_widget(res)
            self.step_rows.append({"P": p, "en": en, "m": mass, "R": res})
        left.add_widget(grid)

        btns = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        calc_btn = Button(text="Рассчитать")
        calc_btn.bind(on_press=lambda *_: self.calculate())
        export_btn = Button(text="CSV")
        export_btn.bind(on_press=lambda *_: self.export())
        reset_btn = Button(text="Сброс drag")
        reset_btn.bind(on_press=lambda *_: self.reset_drag())
        btns.add_widget(calc_btn); btns.add_widget(export_btn); btns.add_widget(reset_btn)
        left.add_widget(btns)

        self.status = Label(text="Введите данные и нажмите Рассчитать", color=(0, 0, 0, 1), size_hint_y=None, height=dp(90), halign="left", valign="top")
        self.status.bind(size=lambda inst, *_: setattr(inst, "text_size", inst.size))
        left.add_widget(self.status)

        right = BoxLayout(orientation="vertical", size_hint_x=0.54, spacing=dp(6))
        body.add_widget(right)
        right.add_widget(Label(text="P–S: точку можно двигать по X", color=(0, 0, 0, 1), size_hint_y=None, height=dp(24)))
        self.graph_ps = GraphWidget(mode="ps", app_ref=self, size_hint_y=0.48)
        right.add_widget(self.graph_ps)
        right.add_widget(Label(text="R–P: точку можно двигать по Y", color=(0, 0, 0, 1), size_hint_y=None, height=dp(24)))
        self.graph_rp = GraphWidget(mode="rp", app_ref=self, size_hint_y=0.48)
        right.add_widget(self.graph_rp)

        self.results = Label(text="", color=(0, 0, 0, 1), font_size=dp(12), size_hint_y=None, height=dp(116), halign="left", valign="top")
        self.results.bind(size=lambda inst, *_: setattr(inst, "text_size", inst.size))
        right.add_widget(self.results)
        Clock.schedule_once(lambda *_: self.update_rho(), 0.1)
        return root

    def update_rho(self):
        if self.auto_rho.active:
            self.fields["rho"].text = f"{rho_from_salinity(self.fields['salinity'].text):.4f}"

    def get_data(self):
        return {k: v.text for k, v in self.fields.items()}

    def get_steps(self):
        steps = []
        for row in self.step_rows:
            steps.append({
                "P": row["P"],
                "en": row["en"].active,
                "m": row["m"].text,
                "R": row["R"].text,
            })
        return steps

    def calculate(self):
        try:
            self.current_result = calculate_capillary(self.get_data(), self.get_steps())
            self.apply_manual_drag()
            self.render_result()
        except Exception as e:
            self.status.text = f"Ошибка: {e}"

    def apply_manual_drag(self):
        # Пересчитываем таблицу вручную после drag без изменения исходных TextInput, кроме отображения графиков.
        if not self.current_result:
            return
        rows = self.current_result["rows"]
        for idx, s in self.manual_s.items():
            if 0 <= idx < len(rows):
                rows[idx]["S"] = s
                rows[idx]["S_pct"] = s * 100
        for idx, rv in self.manual_r.items():
            if 0 <= idx < len(rows):
                rows[idx]["R"] = rv

    def render_result(self):
        if not self.current_result:
            return
        rows = self.current_result["rows"]
        s = self.current_result["summary"]
        self.status.text = (
            f"Vобр={r4(s.get('Vobr'))} см³ | Vp={r4(s.get('Vp'))} см³\n"
            f"Kво={r4(s.get('Kvo'))} | Sов={r4(s.get('Sov'))} | Kпор={r4(s.get('Kpor'))}\n"
            f"Kпор эфф={r4(s.get('Kpor_eff'))} | n Арчи={r4(s.get('n'))}"
        )
        lines = ["P     S%      R       m"]
        for r in rows:
            lines.append(f"{r['P']:<4} {ftext(r.get('S_pct'),2):<7} {ftext(r.get('R'),3):<8} {ftext(r.get('m'),3)}")
        self.results.text = "\n".join(lines[:8])

        ps_points = [(1.0, 0.0, CLR_FIRST, -100, "S=1")]
        for i, r in enumerate(rows):
            color = CLR_MAN if i in self.manual_s else (CLR_MEAS if r.get("mSrc") == "измерено" else CLR_INTR)
            ps_points.append((r.get("S", float("nan")), r.get("P", float("nan")), color, i, str(r.get("P"))))
        self.graph_ps.set_points(ps_points)

        rp_points = []
        # порядок слева 10 -> справа 0
        for p in [10.0, 7.0, 5.0, 3.0, 1.0, 0.5, 0.25]:
            i = PRESSURES.index(p)
            r = rows[i]
            color = CLR_MAN if i in self.manual_r else (CLR_MEAS if r.get("rSrc") == "измерено" else CLR_INTR)
            rp_points.append((p, r.get("R", float("nan")), color, i, str(p)))
        R0 = to_float(self.fields["R0"].text)
        if R0 is not None:
            rp_points.append((0.0, R0, (0.08, 0.40, 0.75, 1), -100, "R0"))
        self.graph_rp.set_points(rp_points)

    def drag_s(self, idx, new_s):
        self.manual_s[idx] = new_s
        if self.current_result:
            self.apply_manual_drag()
            self.render_result()

    def drag_r(self, idx, new_r):
        self.manual_r[idx] = new_r
        if self.current_result:
            self.apply_manual_drag()
            self.render_result()

    def reset_drag(self):
        self.manual_s.clear()
        self.manual_r.clear()
        self.calculate()

    def export(self):
        if not self.current_result:
            self.status.text = "Сначала выполните расчёт"
            return
        try:
            # На Android обычно доступно private storage приложения.
            path = Path(self.user_data_dir) / "capill_result.csv"
            export_csv(path, self.current_result)
            self.status.text = f"CSV сохранён:\n{path}"
        except Exception as e:
            self.status.text = f"Ошибка CSV: {e}"


if __name__ == "__main__":
    CapillAndroidApp().run()
