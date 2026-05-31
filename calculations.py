# -*- coding: utf-8 -*-
"""
Расчётная логика для Android/Kivy версии приложения "Капилляриметрия".
Без Tkinter, без Matplotlib, без Windows-зависимостей.
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PRESSURES = [0.25, 0.5, 1.0, 3.0, 5.0, 7.0, 10.0]
G_OST = 9.80665


def to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return default
        return float(value)
    text = str(value).strip().replace(",", ".")
    if not text:
        return default
    try:
        return float(text)
    except Exception:
        return default


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def r4(x: Any) -> str:
    v = to_float(x)
    if v is None or math.isnan(v) or math.isinf(v):
        return "—"
    return f"{v:.4f}"


def rho_from_salinity(salinity_g_l: Any) -> float:
    """Приближение из исходного скрипта: ρ = 0.9982 + 0.0008*C."""
    c = to_float(salinity_g_l, 0.0) or 0.0
    c = clamp(c, 0.0, 300.0)
    return clamp(0.9982 + 0.0008 * c, 0.6, 1.5)


def ost_apply_salt_correction_41(S_res: float, C_percent: float, gamma_b: float, gamma_p: float, gamma_o: float) -> float:
    try:
        C = float(C_percent)
        S = float(S_res)
        eps = 1e-12
        denom1 = (100.0 - C) if abs(100.0 - C) > eps else eps
        numer = gamma_b * (1.0 + C / denom1)
        denom = gamma_p * (1.0 + (S * C * gamma_b) / (gamma_o * denom1 if abs(gamma_o) > eps else eps))
        return S * (numer / denom)
    except Exception:
        return float("nan")


def ost_pc_to_h_51(Pc_lab_Pa: float, sigma_lab: float = 0.072, sigma_pl: float = 0.030,
                  delta_gamma_pl: float = 200.0, cos_theta_ratio: float = 1.0) -> float:
    try:
        Pc_pl = Pc_lab_Pa * (sigma_pl / (sigma_lab if sigma_lab else 1e-12)) * cos_theta_ratio
        return Pc_pl / (delta_gamma_pl * G_OST if delta_gamma_pl else 1e-12)
    except Exception:
        return float("nan")


def build_cubic_spline(x: List[float], y: List[float]) -> Optional[Dict[str, List[float]]]:
    n = len(x)
    if n < 2:
        return None
    a = y[:]
    h = [x[i + 1] - x[i] for i in range(n - 1)]
    if any(abs(v) < 1e-12 for v in h):
        return None
    alpha = [0.0] * (n - 1)
    for i in range(1, n - 1):
        alpha[i] = (3.0 / h[i]) * (a[i + 1] - a[i]) - (3.0 / h[i - 1]) * (a[i] - a[i - 1])
    l = [0.0] * n
    mu = [0.0] * n
    z = [0.0] * n
    l[0] = 1.0
    for i in range(1, n - 1):
        l[i] = 2.0 * (x[i + 1] - x[i - 1]) - h[i - 1] * mu[i - 1]
        if abs(l[i]) < 1e-12:
            return None
        mu[i] = h[i] / l[i]
        z[i] = (alpha[i] - h[i - 1] * z[i - 1]) / l[i]
    l[n - 1] = 1.0
    c = [0.0] * n
    b = [0.0] * (n - 1)
    d = [0.0] * (n - 1)
    for j in range(n - 2, -1, -1):
        c[j] = z[j] - mu[j] * c[j + 1]
        b[j] = (a[j + 1] - a[j]) / h[j] - h[j] * (c[j + 1] + 2.0 * c[j]) / 3.0
        d[j] = (c[j + 1] - c[j]) / (3.0 * h[j])
    return {"x": x[:-1], "a": a[:-1], "b": b, "c": c[:-1], "d": d}


def eval_spline(sp: Optional[Dict[str, List[float]]], xq: float) -> float:
    if sp is None:
        return float("nan")
    xs, a, b, c, d = sp["x"], sp["a"], sp["b"], sp["c"], sp["d"]
    if xq <= xs[0]:
        i = 0
    elif xq >= xs[-1]:
        i = len(xs) - 1
    else:
        i = 0
        for k in range(len(xs) - 1):
            if xs[k] <= xq <= xs[k + 1]:
                i = k
                break
    dx = xq - xs[i]
    return a[i] + b[i] * dx + c[i] * dx * dx + d[i] * dx * dx * dx


def lin_interp(x: float, pts: List[Tuple[float, float]]) -> float:
    if not pts:
        return float("nan")
    pts = sorted(pts, key=lambda t: t[0])
    if len(pts) == 1:
        return pts[0][1]
    if x <= pts[0][0]:
        (x1, y1), (x2, y2) = pts[0], pts[1]
    elif x >= pts[-1][0]:
        (x1, y1), (x2, y2) = pts[-2], pts[-1]
    else:
        x1 = y1 = x2 = y2 = None
        for i in range(len(pts) - 1):
            if pts[i][0] <= x <= pts[i + 1][0]:
                x1, y1 = pts[i]
                x2, y2 = pts[i + 1]
                break
        if x1 is None or x2 is None:
            return float("nan")
    if abs(x2 - x1) < 1e-12:
        return float("nan")
    return y1 + (x - x1) * ((y2 - y1) / (x2 - x1))


def _polyfit_slope(xs: List[float], ys: List[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if abs(den) < 1e-12:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den


def calculate_capillary(data: Dict[str, Any], step_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    D = to_float(data.get("D"))
    L = to_float(data.get("L"))
    rho = to_float(data.get("rho"))
    m_dry = to_float(data.get("m_dry"))
    m_sat = to_float(data.get("m_sat"))
    R0v = to_float(data.get("R0"))
    salinity = to_float(data.get("salinity"), 0.0) or 0.0
    rw = to_float(data.get("R_water"), 1.0) or 1.0

    required = {"D": D, "L": L, "rho": rho, "m_dry": m_dry, "m_sat": m_sat}
    missing = [k for k, v in required.items() if v is None]
    if missing:
        raise ValueError("Заполните поля: " + ", ".join(missing))
    if D <= 0 or L <= 0 or rho <= 0:
        raise ValueError("D, L и ρ должны быть больше нуля")
    if m_sat <= m_dry:
        raise ValueError("m нас должна быть больше m сух")

    # нормализуем строки ступеней по PRESSURES
    normalized = []
    by_p = {float(to_float(row.get("P"), p)): row for p, row in zip(PRESSURES, step_data)}
    for p in PRESSURES:
        row = by_p.get(float(p), {})
        normalized.append({
            "P": p,
            "en": bool(row.get("en", True)),
            "m": to_float(row.get("m")),
            "R": to_float(row.get("R")),
        })

    masses = [d["m"] for d in normalized]
    resistances = [d["R"] for d in normalized]
    enabled = [d["en"] for d in normalized]

    Vobr = math.pi * (D / 2.0) ** 2 * L * 1e-3
    Vp = (m_sat - m_dry) / rho

    # Массы: spline по log10(P)
    mass_pts = [(math.log10(p), m) for p, m, en in zip(PRESSURES, masses, enabled) if en and m is not None and p > 0]
    mass_pts.sort(key=lambda t: t[0])
    sp = build_cubic_spline([t[0] for t in mass_pts], [t[1] for t in mass_pts]) if len(mass_pts) >= 2 else None

    final_m: List[float] = []
    m_src: List[str] = []
    for p, m, en in zip(PRESSURES, masses, enabled):
        if en and m is not None:
            final_m.append(m)
            m_src.append("измерено")
        elif p > 0 and sp is not None:
            final_m.append(eval_spline(sp, math.log10(p)))
            m_src.append("интерп.")
        else:
            final_m.append(float("nan"))
            m_src.append("—")

    # Плато 10 = 7, если 10 не измерена
    i10 = PRESSURES.index(10.0)
    i7 = PRESSURES.index(7.0)
    if m_src[i10] != "измерено" and not math.isnan(final_m[i7]):
        final_m[i10] = final_m[i7]
        m_src[i10] = "интерп.(плато)"

    # R: линейно по P, плюс R0 при 0
    rpts: List[Tuple[float, float]] = []
    if R0v is not None:
        rpts.append((0.0, R0v))
    for p, r, en in zip(PRESSURES, resistances, enabled):
        if en and r is not None:
            rpts.append((float(p), r))
    rpts.sort(key=lambda t: t[0])

    final_R: List[float] = []
    r_src: List[str] = []
    for p, r, en in zip(PRESSURES, resistances, enabled):
        if en and r is not None:
            final_R.append(r)
            r_src.append("измерено")
        else:
            rp = lin_interp(float(p), rpts) if rpts else float("nan")
            final_R.append(rp)
            r_src.append("интерп." if not math.isnan(rp) else "—")

    rows: List[Dict[str, Any]] = []
    for i, p in enumerate(PRESSURES):
        m = final_m[i]
        R = final_R[i]
        Vv = (m_sat - m) / rho if not math.isnan(m) else float("nan")
        S = ((Vp - Vv) / Vp) if Vp > 0 and not math.isnan(Vv) else float("nan")
        S = clamp(S, 0.0, 1.0) if not math.isnan(S) else S
        Rcorr = (R * (rw / R0v)) if (R0v and R and not math.isnan(R)) else R
        lam = (R0v / Rcorr) if (R0v and Rcorr and not math.isnan(Rcorr) and Rcorr > 0) else float("nan")
        Pc_Pa = p * 101325.0
        rows.append({
            "P": p,
            "m": m,
            "mSrc": m_src[i],
            "R": Rcorr,
            "rSrc": r_src[i],
            "Vv": Vv,
            "S": S,
            "S_pct": S * 100.0 if not math.isnan(S) else float("nan"),
            "lam": lam,
            "Pc_Pa": Pc_Pa,
            "H_m": ost_pc_to_h_51(Pc_Pa),
        })

    # Archie: I = R / R0_ref, n from log(I) = -n log(Sw)
    valid = [(r["S"], r["R"]) for r in rows if r.get("S") and r.get("R") and r["S"] > 0 and r["R"] > 0]
    if valid:
        # reference R0: entered R0 first, otherwise point closest to Sw=1
        R_ref = R0v if R0v and R0v > 0 else min(valid, key=lambda x: abs(x[0] - 1.0))[1]
        xs: List[float] = []
        ys: List[float] = []
        for Sw, R in valid:
            I = R / R_ref
            if Sw > 0 and I > 0:
                xs.append(math.log10(Sw))
                ys.append(math.log10(I))
        slope = _polyfit_slope(xs, ys)
        n_value = -slope if slope is not None else float("nan")
        for r in rows:
            R = r.get("R")
            Sw = r.get("S")
            I = (R / R_ref) if R_ref and R and R > 0 else float("nan")
            r["I"] = I
            r["log_Sw"] = math.log10(Sw) if Sw and Sw > 0 else float("nan")
            r["log_I"] = math.log10(I) if I and I > 0 else float("nan")
            r["n"] = n_value

    # Последняя включённая ступень для остаточной воды
    k_last = None
    for idx in range(len(PRESSURES) - 1, -1, -1):
        if enabled[idx]:
            k_last = idx
            break
    sov_mass = float("nan")
    if k_last is not None:
        m_last = rows[k_last]["m"]
        if m_last is not None and not math.isnan(m_last):
            sov_mass = clamp((m_last - m_dry) / (m_sat - m_dry), 0.0, 1.0)

    C_percent = 0.1 * salinity
    sov_corr = ost_apply_salt_correction_41(sov_mass, C_percent, rho, rho, rho) if not math.isnan(sov_mass) else float("nan")
    if math.isnan(sov_corr):
        sov_corr = sov_mass
    sov_corr = clamp(sov_corr, 0.0, 1.0) if not math.isnan(sov_corr) else sov_corr
    kvo = 1.0 - sov_corr if not math.isnan(sov_corr) else float("nan")

    last = rows[-1]
    Kpor = last["Vv"] / Vobr if Vobr > 0 and not math.isnan(last["Vv"]) else float("nan")
    Kpor_eff = Kpor * (1.0 - sov_corr) if not math.isnan(Kpor) and not math.isnan(sov_corr) else float("nan")

    summary = {
        "Vobr": Vobr,
        "Vp": Vp,
        "m_water_total": m_sat - m_dry,
        "rho": rho,
        "R0": R0v,
        "Sov": sov_corr,
        "Sov_mass": sov_mass,
        "Kvo": kvo,
        "Kpor": Kpor,
        "Kpor_eff": Kpor_eff,
        "n": rows[0].get("n", float("nan")) if rows else float("nan"),
    }
    return {"rows": rows, "summary": summary}


def export_csv(path: str | Path, result: Dict[str, Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = result.get("rows", [])
    summary = result.get("summary", {})
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Summary"])
        for k, v in summary.items():
            w.writerow([k, v])
        w.writerow([])
        w.writerow(["P", "m", "mSrc", "R", "rSrc", "Vv", "S", "S_pct", "lambda", "I", "log_Sw", "log_I", "n", "Pc_Pa", "H_m"])
        for r in rows:
            w.writerow([r.get(k, "") for k in ["P", "m", "mSrc", "R", "rSrc", "Vv", "S", "S_pct", "lam", "I", "log_Sw", "log_I", "n", "Pc_Pa", "H_m"]])
    return path
