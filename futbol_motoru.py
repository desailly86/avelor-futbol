# -*- coding: utf-8 -*-
"""
futbol_motoru.py v2 — AVELOR Futbol analiz çekirdeği
=====================================================
FARK YARATAN KRİTERLER (sıradan form karışımının ötesi):
  1. Ev/deplasman AYRIK güçler — takımın evdeki ve deplasmandaki hücum/savunma
     profili ayrı ölçülür (çoğu basit model bunu birleştirir).
  2. Şut kalitesi düzeltmesi — gol şans işidir, isabetli şut sinyaldir; hücum
     gücü %70 gol + %30 isabetli-şut-beklentisiyle harmanlanır (xG vekili).
  3. Fikstür yoğunluğu — son maçtan bu yana <4 gün ise yorgunluk cezası.
  4. Eksik oyuncu ayarı — kilit hücum/savunma eksikleri elle işaretlenir,
     model gol beklentilerini buna göre kaydırır (profesyonellerin gerçek
     "haber avantajı" tam olarak budur ve otomatikleşemez; dürüst yol elle).
  5. Korner ve kart modelleri — football-data'nın HC/AC/HY/AY/HR/AR
     kolonlarından ayrı Poisson modelleri: korner 8.5/9.5/10.5, kart 3.5/4.5.
  6. İlk yarı yaklaşımı — gol temposunun ~%44'ü ilk yarıda: İY 0.5/1.5 üstü.
TÜM MARKETLER tek modelden türetilir; en_iyi_uc() her maç için güven+çeşitlilik
kuralıyla ilk 3 tahmini seçer.
DÜRÜSTLÜK: Hiçbir kombinasyon kazanç garantisi değildir. backtest() geçmişte,
yalnızca o güne kadarki veriyle ne tutturduğunu ölçer — güvenilecek rakam odur.
"""
from __future__ import annotations
import math
import numpy as np
import pandas as pd

YARI_OMUR_GUN = 240.0
RHO = -0.10
MAX_GOL = 8
SUT_HARMAN = 0.30          # hücum gücünde isabetli şut payı
IY_PAY = 0.44              # gollerin ilk yarı payı
YORGUNLUK_GUN = 4          # bundan kısa dinlenme → ceza
YORGUNLUK_CEZA = 0.94
EKSIK_HUCUM_ETKI = 0.92    # kilit hücum eksiği başına hücum çarpanı
EKSIK_SAVUNMA_ETKI = 1.08  # kilit savunma eksiği başına rakip hücum çarpanı


def _agirliklar(tarihler: pd.Series, referans) -> np.ndarray:
    gun = (referans - tarihler).dt.days.clip(lower=0).to_numpy(dtype=float)
    return np.power(0.5, gun / YARI_OMUR_GUN)


def _agirlikli_ort(degerler, w):
    degerler = np.asarray(degerler, dtype=float)
    m = ~np.isnan(degerler)
    if not m.any() or w[m].sum() == 0:
        return None
    return float(np.average(degerler[m], weights=w[m]))


def guc_hesapla(df: pd.DataFrame, referans=None) -> dict:
    """Ev/deplasman ayrık, şut-kalitesi harmanlı, zaman-ağırlıklı güçler."""
    d = df.dropna(subset=["FTHG", "FTAG"]).copy()
    if len(d) < 30:
        raise ValueError(f"Model için en az 30 oynanmış maç gerekir (elde {len(d)}).")
    referans = referans or d["Date"].max()
    w = _agirliklar(d["Date"], referans)
    ev_gol = float(np.average(d["FTHG"], weights=w))
    dep_gol = float(np.average(d["FTAG"], weights=w))
    lig_ort = (ev_gol + dep_gol) / 2.0
    sut_var = "HST" in d.columns and d["HST"].notna().sum() > len(d) * 0.5
    if sut_var:
        donusum = (d["FTHG"].sum() + d["FTAG"].sum()) / max((d["HST"].sum() + d["AST"].sum()), 1)
    korner_var = "HC" in d.columns and d["HC"].notna().sum() > len(d) * 0.5
    kart_var = "HY" in d.columns and d["HY"].notna().sum() > len(d) * 0.5
    lig_korner = float(np.average((d["HC"] + d["AC"]).dropna())) if korner_var else None
    if kart_var:
        kartlar = d["HY"].fillna(0) + d["AY"].fillna(0) + \
                  d.get("HR", pd.Series(0, index=d.index)).fillna(0) + \
                  d.get("AR", pd.Series(0, index=d.index)).fillna(0)
        lig_kart = float(np.average(kartlar))
    else:
        lig_kart = None

    takimlar = {}
    for takim in pd.unique(pd.concat([d["HomeTeam"], d["AwayTeam"]])):
        ev = (d["HomeTeam"] == takim).to_numpy()
        dep = (d["AwayTeam"] == takim).to_numpy()

        def taraf(maske, gol_kol, yenen_kol, sut_kol, rakip_sut_kol, korner_kol, kart_kol):
            wt = w[maske]
            if wt.sum() < 1.5:
                return None
            gol = _agirlikli_ort(d.loc[maske, gol_kol], wt)
            yenen = _agirlikli_ort(d.loc[maske, yenen_kol], wt)
            hucum = (gol or lig_ort) / lig_ort
            if sut_var:
                sut_bek = _agirlikli_ort(d.loc[maske, sut_kol], wt)
                if sut_bek is not None:
                    hucum = (1 - SUT_HARMAN) * hucum + SUT_HARMAN * (sut_bek * donusum / lig_ort)
            savunma = (yenen or lig_ort) / lig_ort
            if sut_var:
                r_sut = _agirlikli_ort(d.loc[maske, rakip_sut_kol], wt)
                if r_sut is not None:
                    savunma = (1 - SUT_HARMAN) * savunma + SUT_HARMAN * (r_sut * donusum / lig_ort)
            guven = wt.sum() / (wt.sum() + 4.0)  # az maç → 1.0'a (lig ort.) büzül
            hucum = 1.0 + (hucum - 1.0) * guven
            savunma = 1.0 + (savunma - 1.0) * guven
            return {"hucum": hucum, "savunma": savunma, "mac": int(maske.sum()),
                    "korner": _agirlikli_ort(d.loc[maske, korner_kol], wt) if korner_var else None,
                    "kart": _agirlikli_ort(d.loc[maske, kart_kol], wt) if kart_var else None}

        ev_p = taraf(ev, "FTHG", "FTAG", "HST", "AST", "HC", "HY") if ev.any() else None
        dep_p = taraf(dep, "FTAG", "FTHG", "AST", "HST", "AC", "AY") if dep.any() else None
        genel = {"hucum": np.mean([p["hucum"] for p in (ev_p, dep_p) if p]) if (ev_p or dep_p) else 1.0,
                 "savunma": np.mean([p["savunma"] for p in (ev_p, dep_p) if p]) if (ev_p or dep_p) else 1.0}
        # son maç tarihi (yorgunluk için)
        maclar = d[ev | dep]
        son_tarih = maclar["Date"].max() if len(maclar) else None
        takimlar[takim] = {"ev": ev_p, "dep": dep_p, "genel": genel,
                           "mac": int(ev.sum() + dep.sum()), "son_mac": son_tarih,
                           "hucum": genel["hucum"], "savunma": genel["savunma"]}
    toplam_gol = d["FTHG"] + d["FTAG"]
    bazlar = {"1": float((d["FTHG"] > d["FTAG"]).mean() * 100),
              "X": float((d["FTHG"] == d["FTAG"]).mean() * 100),
              "2": float((d["FTHG"] < d["FTAG"]).mean() * 100),
              "ust15": float((toplam_gol > 1).mean() * 100),
              "ust25": float((toplam_gol > 2).mean() * 100),
              "ust35": float((toplam_gol > 3).mean() * 100),
              "kg_var": float(((d["FTHG"] > 0) & (d["FTAG"] > 0)).mean() * 100)}
    bazlar["alt15"] = 100 - bazlar["ust15"]; bazlar["alt25"] = 100 - bazlar["ust25"]
    bazlar["alt35"] = 100 - bazlar["ust35"]; bazlar["kg_yok"] = 100 - bazlar["kg_var"]
    bazlar["1X"] = bazlar["1"] + bazlar["X"]; bazlar["12"] = bazlar["1"] + bazlar["2"]
    bazlar["X2"] = bazlar["X"] + bazlar["2"]
    if "HTHG" in d.columns and d["HTHG"].notna().sum() > len(d) * 0.5:
        iy = d["HTHG"].fillna(0) + d["HTAG"].fillna(0)
        bazlar["iy_ust05"] = float((iy > 0).mean() * 100)
        bazlar["iy_ust15"] = float((iy > 1).mean() * 100)
    if korner_var:
        kt = (d["HC"] + d["AC"]).dropna()
        for esik in (8, 9, 10):
            bazlar[f"korner_ust{esik}5"] = float((kt > esik).mean() * 100)
    if kart_var:
        for esik in (3, 4):
            bazlar[f"kart_ust{esik}5"] = float((kartlar > esik).mean() * 100)
    return {"takimlar": takimlar, "ev_carpan": ev_gol / lig_ort, "dep_carpan": dep_gol / lig_ort,
            "lig_ort": lig_ort, "lig_korner": lig_korner, "lig_kart": lig_kart,
            "bazlar": {k: round(v, 1) for k, v in bazlar.items()}}


def _dc(x, y, lh, la):
    if x == 0 and y == 0: return 1 - lh * la * RHO
    if x == 0 and y == 1: return 1 + lh * RHO
    if x == 1 and y == 0: return 1 + la * RHO
    if x == 1 and y == 1: return 1 - RHO
    return 1.0


def _poisson_ustu(lam, esik):
    """Toplamın esik'ten BÜYÜK olma olasılığı (Poisson, tam sayı eşik+0.5)."""
    p = 0.0
    for i in range(int(esik) + 1):
        p += math.exp(-lam) * lam ** i / math.factorial(i)
    return 1 - p


def mac_tahmin(guc: dict, ev: str, dep: str, mac_tarihi=None,
               eksikler: dict | None = None) -> dict | None:
    """eksikler: {'ev_hucum':0-3,'ev_savunma':0-3,'dep_hucum':0-3,'dep_savunma':0-3}"""
    te, td = guc["takimlar"].get(ev), guc["takimlar"].get(dep)
    if not te or not td:
        return None
    ev_hucum = (te["ev"] or te)["hucum"] if te.get("ev") else te["genel"]["hucum"]
    ev_savunma = (te["ev"] or te)["savunma"] if te.get("ev") else te["genel"]["savunma"]
    dep_hucum = (td["dep"] or td)["hucum"] if td.get("dep") else td["genel"]["hucum"]
    dep_savunma = (td["dep"] or td)["savunma"] if td.get("dep") else td["genel"]["savunma"]

    lam_ev = guc["lig_ort"] * guc["ev_carpan"] * ev_hucum * dep_savunma
    lam_dep = guc["lig_ort"] * guc["dep_carpan"] * dep_hucum * ev_savunma

    notlar = []
    if mac_tarihi is not None:
        for etiket, takim, taraf in (("ev", te, "lam_ev"), ("dep", td, "lam_dep")):
            if takim.get("son_mac") is not None:
                dinlenme = (pd.Timestamp(mac_tarihi) - takim["son_mac"]).days
                if 0 <= dinlenme < YORGUNLUK_GUN:
                    if taraf == "lam_ev": lam_ev *= YORGUNLUK_CEZA
                    else: lam_dep *= YORGUNLUK_CEZA
                    notlar.append(f"{etiket} yorgun ({dinlenme}g)")
    e = eksikler or {}
    lam_ev *= EKSIK_HUCUM_ETKI ** e.get("ev_hucum", 0)
    lam_dep *= EKSIK_HUCUM_ETKI ** e.get("dep_hucum", 0)
    lam_ev *= EKSIK_SAVUNMA_ETKI ** e.get("dep_savunma", 0)
    lam_dep *= EKSIK_SAVUNMA_ETKI ** e.get("ev_savunma", 0)
    if any(e.values()):
        notlar.append("eksik ayarı uygulandı")
    lam_ev = max(0.05, min(6.0, lam_ev)); lam_dep = max(0.05, min(6.0, lam_dep))

    p_ev = [math.exp(-lam_ev) * lam_ev ** i / math.factorial(i) for i in range(MAX_GOL + 1)]
    p_dep = [math.exp(-lam_dep) * lam_dep ** i / math.factorial(i) for i in range(MAX_GOL + 1)]
    izgara = np.outer(p_ev, p_dep)
    for x in (0, 1):
        for y in (0, 1):
            izgara[x, y] *= _dc(x, y, lam_ev, lam_dep)
    izgara /= izgara.sum()

    p1 = float(np.tril(izgara, -1).sum()); p0 = float(np.trace(izgara))
    p2 = float(np.triu(izgara, 1).sum())
    toplam_p = {esik: float(sum(izgara[x, y] for x in range(MAX_GOL + 1)
                                for y in range(MAX_GOL + 1) if x + y > esik))
                for esik in (1, 2, 3)}
    kg = float(izgara[1:, 1:].sum())
    skorlar = sorted(((izgara[x, y], f"{x}-{y}") for x in range(6) for y in range(6)),
                     reverse=True)[:3]
    iy_lam = (lam_ev + lam_dep) * IY_PAY

    t = {"lam_ev": round(lam_ev, 2), "lam_dep": round(lam_dep, 2),
         "1": round(p1 * 100, 1), "X": round(p0 * 100, 1), "2": round(p2 * 100, 1),
         "1X": round((p1 + p0) * 100, 1), "12": round((p1 + p2) * 100, 1),
         "X2": round((p0 + p2) * 100, 1),
         "ust15": round(toplam_p[1] * 100, 1), "alt15": round((1 - toplam_p[1]) * 100, 1),
         "ust25": round(toplam_p[2] * 100, 1), "alt25": round((1 - toplam_p[2]) * 100, 1),
         "ust35": round(toplam_p[3] * 100, 1), "alt35": round((1 - toplam_p[3]) * 100, 1),
         "kg_var": round(kg * 100, 1), "kg_yok": round((1 - kg) * 100, 1),
         "iy_ust05": round(float(_poisson_ustu(iy_lam, 0)) * 100, 1),
         "iy_ust15": round(float(_poisson_ustu(iy_lam, 1)) * 100, 1),
         "skorlar": [(s, round(p * 100, 1)) for p, s in skorlar],
         "skor": skorlar[0][1], "notlar": notlar,
         "ev_mac": te["mac"], "dep_mac": td["mac"]}

    if guc.get("lig_korner"):
        ke = (te.get("ev") or {}).get("korner"); kd = (td.get("dep") or {}).get("korner")
        if ke is not None and kd is not None:
            lam_k = ke + kd
            for esik in (8, 9, 10):
                t[f"korner_ust{esik}5"] = round(float(_poisson_ustu(lam_k, esik)) * 100, 1)
            t["korner_beklenti"] = round(lam_k, 1)
    if guc.get("lig_kart"):
        ce = (te.get("ev") or {}).get("kart"); cd = (td.get("dep") or {}).get("kart")
        if ce is not None and cd is not None:
            lam_c = ce + cd
            for esik in (3, 4):
                t[f"kart_ust{esik}5"] = round(float(_poisson_ustu(lam_c, esik)) * 100, 1)
            t["kart_beklenti"] = round(lam_c, 1)
    return t


MARKET_ETIKET = {
    "1": "MS 1 (ev)", "X": "MS X", "2": "MS 2 (dep)",
    "1X": "Çifte Şans 1-X", "12": "Çifte Şans 1-2", "X2": "Çifte Şans X-2",
    "ust15": "1.5 Üst", "alt15": "1.5 Alt", "ust25": "2.5 Üst", "alt25": "2.5 Alt",
    "ust35": "3.5 Üst", "alt35": "3.5 Alt", "kg_var": "KG Var", "kg_yok": "KG Yok",
    "iy_ust05": "İY 0.5 Üst", "iy_ust15": "İY 1.5 Üst",
    "korner_ust85": "Korner 8.5 Üst", "korner_ust95": "Korner 9.5 Üst",
    "korner_ust105": "Korner 10.5 Üst", "kart_ust35": "Kart 3.5 Üst", "kart_ust45": "Kart 4.5 Üst",
}
MARKET_GRUP = {  # aynı gruptan en fazla 1 öneri (çeşitlilik kuralı)
    "1": "sonuc", "X": "sonuc", "2": "sonuc", "1X": "sonuc", "12": "sonuc", "X2": "sonuc",
    "ust15": "gol", "alt15": "gol", "ust25": "gol", "alt25": "gol", "ust35": "gol", "alt35": "gol",
    "kg_var": "kg", "kg_yok": "kg", "iy_ust05": "iy", "iy_ust15": "iy",
    "korner_ust85": "korner", "korner_ust95": "korner", "korner_ust105": "korner",
    "kart_ust35": "kart", "kart_ust45": "kart",
}


def en_iyi_uc(t: dict, bazlar: dict | None = None,
              min_olasilik: float = 50.0, min_kenar: float = 5.0) -> list[dict]:
    """CESUR ÖNERİ SEÇİCİ: ham olasılıkla değil, modelin LİG ORTALAMASINDAN
    ne kadar saptığıyla (kenar) sıralar. 'Çifte şans %92' gibi herkesin
    bildiği kolay tahminler kenarı düşük olduğu için elenir; '2.5 Üst %64
    (lig tabanı %52 → kenar +12)' gibi gerçek iddialar öne çıkar.
    Kurallar: olasılık ≥ %50 (yazı-turadan iyi olmalı), kenar ≥ min_kenar,
    aynı market grubundan tek öneri. Şartları aşan yoksa liste kısa kalır —
    zorlama öneri üretilmez."""
    bazlar = bazlar or {}
    # Backtest kırılımının güvenilmez bulduğu uç marketler önerilmez (tabloda kalır):
    YASAKLI = {"kart_ust45", "korner_ust105", "ust35", "iy_ust15"}
    OZEL_ESIK = {"kg_var": 56.0, "kg_yok": 56.0, "korner_ust95": 55.0}
    adaylar = []
    for k in MARKET_ETIKET:
        if k in YASAKLI or k not in t or not isinstance(t[k], (int, float)):
            continue
        p = float(t[k])
        baz = float(bazlar.get(k, 50.0))
        kenar = p - baz
        if p >= max(min_olasilik, OZEL_ESIK.get(k, 0)) and kenar >= min_kenar:
            adaylar.append((kenar, p, k))
    adaylar.sort(reverse=True)
    secim, gruplar = [], set()
    for kenar, p, k in adaylar:
        g = MARKET_GRUP[k]
        if g in gruplar:
            continue
        secim.append({"market": MARKET_ETIKET[k], "kod": k,
                      "olasilik": round(p, 1), "kenar": round(kenar, 1),
                      "baz": round(float(bazlar.get(k, 50.0)), 1)})
        gruplar.add(g)
        if len(secim) == 3:
            break
    return secim


def value_hesapla(olasilik_yuzde: float, oran: float) -> dict:
    p = olasilik_yuzde / 100.0
    deger = p * oran - 1.0
    return {"ima": round(100.0 / oran, 1), "value": round(deger * 100, 1),
            "oynanabilir": deger > 0.05}


def form_ozeti(df: pd.DataFrame, takim: str, son: int = 5) -> dict:
    d = df.dropna(subset=["FTHG", "FTAG"])
    maclar = d[(d["HomeTeam"] == takim) | (d["AwayTeam"] == takim)].sort_values("Date").tail(son)
    dizi, puan, ag, yg = [], 0, 0, 0
    for _, m in maclar.iterrows():
        evde = m["HomeTeam"] == takim
        a, y = (m["FTHG"], m["FTAG"]) if evde else (m["FTAG"], m["FTHG"])
        ag += a; yg += y
        if a > y: dizi.append("G"); puan += 3
        elif a == y: dizi.append("B"); puan += 1
        else: dizi.append("M")
    return {"dizi": "".join(dizi), "puan": puan, "attigi": int(ag), "yedigi": int(yg)}


def backtest(df: pd.DataFrame, minimum_mac: int = 120) -> dict:
    """Kronolojik dürüst test (v2 modeliyle): 1X2 + 2.5 A/Ü + KG + 'en iyi 3' isabeti."""
    d = df.dropna(subset=["FTHG", "FTAG"]).sort_values("Date").reset_index(drop=True)
    r = {"mac": 0, "model_1x2": 0, "piyasa_1x2": 0, "au25": 0, "kg": 0,
         "log_kayip": 0.0, "value_bahis": 0, "value_kar": 0.0,
         "oneri": 0, "oneri_tutan": 0}
    for i in range(minimum_mac, len(d)):
        m = d.iloc[i]
        try:
            guc = guc_hesapla(d.iloc[:i], referans=m["Date"])
        except ValueError:
            continue
        t = mac_tahmin(guc, m["HomeTeam"], m["AwayTeam"], mac_tarihi=m["Date"])
        if not t:
            continue
        r["mac"] += 1
        gercek = "1" if m["FTHG"] > m["FTAG"] else ("X" if m["FTHG"] == m["FTAG"] else "2")
        toplam = m["FTHG"] + m["FTAG"]
        kg_gercek = m["FTHG"] > 0 and m["FTAG"] > 0
        r["model_1x2"] += max(("1", "X", "2"), key=lambda s: t[s]) == gercek
        r["log_kayip"] += -math.log(max(t[gercek] / 100.0, 1e-9))
        r["au25"] += (t["ust25"] >= 50) == (toplam >= 3)
        r["kg"] += (t["kg_var"] >= 50) == kg_gercek
        # En iyi 3 önerinin gerçekleşme testi
        for o in en_iyi_uc(t, guc.get("bazlar")):
            r["oneri"] += 1
            k = o["kod"]
            tutan = {"1": gercek == "1", "X": gercek == "X", "2": gercek == "2",
                     "1X": gercek in "1X", "12": gercek in "12", "X2": gercek in "X2",
                     "ust15": toplam > 1, "alt15": toplam <= 1, "ust25": toplam > 2,
                     "alt25": toplam <= 2, "ust35": toplam > 3, "alt35": toplam <= 3,
                     "kg_var": kg_gercek, "kg_yok": not kg_gercek,
                     "iy_ust05": pd.notna(m.get("HTHG")) and (m["HTHG"] + m["HTAG"]) > 0,
                     "iy_ust15": pd.notna(m.get("HTHG")) and (m["HTHG"] + m["HTAG"]) > 1,
                     "korner_ust85": pd.notna(m.get("HC")) and (m["HC"] + m["AC"]) > 8,
                     "korner_ust95": pd.notna(m.get("HC")) and (m["HC"] + m["AC"]) > 9,
                     "korner_ust105": pd.notna(m.get("HC")) and (m["HC"] + m["AC"]) > 10,
                     "kart_ust35": pd.notna(m.get("HY")) and (m["HY"] + m["AY"]) > 3,
                     "kart_ust45": pd.notna(m.get("HY")) and (m["HY"] + m["AY"]) > 4,
                     }.get(k, False)
            r["oneri_tutan"] += bool(tutan)
            mk = r.setdefault("market_kirilim", {}).setdefault(o["market"], [0, 0])
            mk[0] += 1; mk[1] += bool(tutan)
        oranlar = {s: m.get(f"B365{h}") for s, h in (("1", "H"), ("X", "D"), ("2", "A"))}
        if all(pd.notna(o) and o and o > 1 for o in oranlar.values()):
            r["piyasa_1x2"] += min(oranlar, key=oranlar.get) == gercek
            for s, o in oranlar.items():
                if value_hesapla(t[s], float(o))["oynanabilir"]:
                    r["value_bahis"] += 1
                    r["value_kar"] += (float(o) - 1) if s == gercek else -1.0
    n = max(r["mac"], 1)
    return {"mac": r["mac"], "model_1x2_%": round(r["model_1x2"] / n * 100, 1),
            "piyasa_1x2_%": round(r["piyasa_1x2"] / n * 100, 1),
            "au25_%": round(r["au25"] / n * 100, 1), "kg_%": round(r["kg"] / n * 100, 1),
            "ort_log_kayip": round(r["log_kayip"] / n, 3),
            "en_iyi3_isabet_%": round(r["oneri_tutan"] / max(r["oneri"], 1) * 100, 1),
            "en_iyi3_oneri": r["oneri"],
            "value_bahis": r["value_bahis"],
            "value_roi_%": round(r["value_kar"] / max(r["value_bahis"], 1) * 100, 1),
            "market_kirilim": {m: {"oneri": v[0], "isabet_%": round(v[1] / v[0] * 100, 1)}
                               for m, v in sorted(r.get("market_kirilim", {}).items(),
                                                  key=lambda x: -x[1][0])}}
