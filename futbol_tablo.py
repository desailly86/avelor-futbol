# -*- coding: utf-8 -*-
"""
futbol_tablo.py — Puan durumu ve iç/dış saha tabloları
=======================================================
Tek sezon (2026/27) maç sonuçlarından lig tablosu üretir:
genel puan durumu + iç saha tablosu + deplasman tablosu.
Girdi: standart maç df'i (Date, HomeTeam, AwayTeam, FTHG, FTAG).
"""
from __future__ import annotations
import pandas as pd


def _bos_satir(takim):
    return {"Takım": takim, "O": 0, "G": 0, "B": 0, "M": 0,
            "A": 0, "Y": 0, "AV": 0, "P": 0}


def puan_durumu(df: pd.DataFrame, mod: str = "genel") -> pd.DataFrame:
    """mod: 'genel' | 'ic' (sadece ev maçları) | 'dis' (sadece deplasman)."""
    d = df.dropna(subset=["FTHG", "FTAG"]).copy()
    tablo: dict = {}

    def kayit_ekle(takim, attigi, yedigi):
        if takim not in tablo:
            tablo[takim] = _bos_satir(takim)
        s = tablo[takim]
        s["O"] += 1; s["A"] += attigi; s["Y"] += yedigi
        if attigi > yedigi:
            s["G"] += 1; s["P"] += 3
        elif attigi == yedigi:
            s["B"] += 1; s["P"] += 1
        else:
            s["M"] += 1

    for _, m in d.iterrows():
        eh, ea = int(m["FTHG"]), int(m["FTAG"])
        if mod in ("genel", "ic"):
            kayit_ekle(m["HomeTeam"], eh, ea)
        if mod in ("genel", "dis"):
            kayit_ekle(m["AwayTeam"], ea, eh)

    if not tablo:
        return pd.DataFrame(columns=["Sıra"] + list(_bos_satir("").keys()))
    out = pd.DataFrame(tablo.values())
    out["AV"] = out["A"] - out["Y"]
    out = out.sort_values(["P", "AV", "A"], ascending=False).reset_index(drop=True)
    out.insert(0, "Sıra", range(1, len(out) + 1))
    return out


def son_mac_sonuclari(df: pd.DataFrame, gun: int = 14) -> pd.DataFrame:
    """Son N günün maç sonuçları (en yeni üstte)."""
    d = df.dropna(subset=["FTHG", "FTAG"]).copy()
    if d.empty:
        return d
    esik = d["Date"].max() - pd.Timedelta(days=gun)
    d = d[d["Date"] >= esik].sort_values("Date", ascending=False)
    d["Skor"] = d["FTHG"].astype(int).astype(str) + " - " + d["FTAG"].astype(int).astype(str)
    d["Tarih"] = d["Date"].dt.strftime("%d.%m")
    return d[["Tarih", "HomeTeam", "Skor", "AwayTeam"]].rename(
        columns={"HomeTeam": "Ev Sahibi", "AwayTeam": "Deplasman"})
