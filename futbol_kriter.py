# -*- coding: utf-8 -*-
"""
futbol_kriter.py — Puan-ağırlık motoru + kriter değerlendirme
==============================================================
FELSEFE (Ali ile kararlaştırıldı):
- Tek sezon (2026/27). Eski veri yok.
- İki katman: TAKIM katmanı (her sezon sıfırlanır) + KRİTER AĞIRLIK katmanı
  (sezonlar arası öğrenir, taşınır).
- Kriterler asla atılmaz; sadece ağırlıkları oynar.
- Her kriter, kendi ALANINDA (maç sonucu / gol / kart / korner...) test edilir.
- İlk haftalarda veri az → kriter güçleri zayıf; dürüstçe gösterilir.

Her kriter üç şey döndürür:
  1. deger(df, takim, rakip, ev_mi): o maç için 0-100 puan (yüksek = lehte)
  2. alan: hangi markette test edilir ("sonuc","gol","kart","korner","iy")
  3. yon: kriter neyin yükseleceğini söyler (sonuç için ev/dep, gol için üst...)

değerlendirme: her tamamlanmış maçta, kriterin o maç için ürettiği tahmin
gerçekle karşılaştırılır → kriterin "tutma oranı" birikir. Bu oran ağırlığa
dönüşür (0.50=şans→düşük ağırlık, 0.70=güçlü→yüksek ağırlık).
"""
from __future__ import annotations
import numpy as np
import pandas as pd

YARI_OMUR_GUN = 9999  # tek sezon: zaman ağırlığı kapalı (tüm sezon eşit sayılır)


# ---------------------------------------------------------------------------
# TAKIM İSTATİSTİK DEFTERİ — bir maçtan ÖNCE, o güne kadarki veriyle
# ---------------------------------------------------------------------------
def takim_defteri(df: pd.DataFrame, tarih_once) -> dict:
    """tarih_once gününden ÖNCEKİ maçlarla her takımın istatistik defteri.
    Sızıntı yok: bir maçı tahmin ederken o maç ve sonrası kullanılmaz."""
    d = df[df["Date"] < tarih_once].dropna(subset=["FTHG", "FTAG"])
    defter: dict = {}
    lig_gol = (d["FTHG"].sum() + d["FTAG"].sum()) / max(len(d) * 2, 1) if len(d) else 1.3

    for takim in pd.unique(pd.concat([d["HomeTeam"], d["AwayTeam"]])):
        ev = d[d["HomeTeam"] == takim]
        dep = d[d["AwayTeam"] == takim]
        n = len(ev) + len(dep)
        if n == 0:
            continue
        # gol
        att = ev["FTHG"].sum() + dep["FTAG"].sum()
        yen = ev["FTAG"].sum() + dep["FTHG"].sum()
        # şut (varsa)
        def kol(çer, k):
            return çer[k].sum() if k in çer.columns else np.nan
        isabet = (kol(ev, "HST") + kol(dep, "AST"))
        toplam_sut = (kol(ev, "HS") + kol(dep, "AS"))
        korner = (kol(ev, "HC") + kol(dep, "AC"))
        faul = (kol(ev, "HF") + kol(dep, "AF"))
        sari = (kol(ev, "HY") + kol(dep, "AY"))
        kirmizi = (kol(ev, "HR") + kol(dep, "AR"))
        # rakibe yaptırılan ofsayt: ev iken AO, dep iken HO
        ofsayt_yaptirdi = (kol(ev, "AO") + kol(dep, "HO"))
        ofsayt_dustu = (kol(ev, "HO") + kol(dep, "AO"))
        # son 5 form
        son5 = pd.concat([ev, dep]).sort_values("Date").tail(5)
        form_p = 0
        for _, m in son5.iterrows():
            evde = m["HomeTeam"] == takim
            a, y = (m["FTHG"], m["FTAG"]) if evde else (m["FTAG"], m["FTHG"])
            form_p += 3 if a > y else (1 if a == y else 0)

        defter[takim] = {
            "mac": n, "ev_mac": len(ev), "dep_mac": len(dep),
            "att_ort": att / n, "yen_ort": yen / n,
            "ev_att": ev["FTHG"].mean() if len(ev) else np.nan,
            "ev_yen": ev["FTAG"].mean() if len(ev) else np.nan,
            "dep_att": dep["FTAG"].mean() if len(dep) else np.nan,
            "dep_yen": dep["FTHG"].mean() if len(dep) else np.nan,
            "ev_puan_ort": _puan_ort(ev, takim, True),
            "dep_puan_ort": _puan_ort(dep, takim, False),
            "form5": form_p / max(len(son5), 1),
            "isabet_ort": isabet / n, "sut_ort": toplam_sut / n,
            "korner_ort": korner / n, "faul_ort": faul / n,
            "sari_ort": sari / n, "kirmizi_ort": kirmizi / n,
            "ofsayt_yaptirdi": ofsayt_yaptirdi / n, "ofsayt_dustu": ofsayt_dustu / n,
            "son_mac_tarih": pd.concat([ev, dep])["Date"].max(),
        }
    defter["_lig_gol"] = lig_gol
    return defter


def _puan_ort(maclar, takim, evde):
    if len(maclar) == 0:
        return np.nan
    p = 0
    for _, m in maclar.iterrows():
        a, y = (m["FTHG"], m["FTAG"]) if evde else (m["FTAG"], m["FTHG"])
        p += 3 if a > y else (1 if a == y else 0)
    return p / len(maclar)


# ---------------------------------------------------------------------------
# HAKEM DEFTERİ — hakemin o güne kadarki kart eğilimi
# ---------------------------------------------------------------------------
def hakem_defteri(df: pd.DataFrame, tarih_once) -> dict:
    d = df[df["Date"] < tarih_once].dropna(subset=["FTHG", "FTAG"])
    if "Referee" not in d.columns:
        return {}
    defter = {}
    for hakem, grup in d.groupby("Referee"):
        if not str(hakem).strip() or str(hakem) == "nan":
            continue
        n = len(grup)
        sari = (grup.get("HY", 0).sum() + grup.get("AY", 0).sum())
        kirmizi = (grup.get("HR", 0).sum() + grup.get("AR", 0).sum())
        son5 = grup.sort_values("Date").tail(5)
        son5_kart = ((son5.get("HY", 0).sum() + son5.get("AY", 0).sum() +
                      son5.get("HR", 0).sum() + son5.get("AR", 0).sum()) / max(len(son5), 1))
        defter[hakem] = {"mac": n, "sari_ort": sari / n, "kirmizi_ort": kirmizi / n,
                         "son5_kart": son5_kart}
    return defter


# ---------------------------------------------------------------------------
# 21 KRİTER — her biri: (ad, alan, fonksiyon)
# fonksiyon(ev_def, dep_def, hakem_def, lig_gol) → ev ve dep için puan/işaret
# alan: hangi markette test edilir
# ---------------------------------------------------------------------------
def _n(x, dizi):
    """x'i dizinin min-max'ına göre 0-100'e ölçekle."""
    d = [v for v in dizi if v is not None and not (isinstance(v, float) and np.isnan(v))]
    if x is None or (isinstance(x, float) and np.isnan(x)) or len(d) < 2 or max(d) == min(d):
        return 50.0
    return float((x - min(d)) / (max(d) - min(d)) * 100)


KRITER_TANIM = [
    # (kod, ad, alan, açıklama)
    ("hucum", "Hücum gücü", "gol", "attığı gol ort., lige normalize"),
    ("savunma", "Savunma gücü", "gol", "yediği gol ort. (düşük iyi)"),
    ("xg", "AVELOR-xG", "gol", "gol+isabetli+isabetsiz şut harmanı"),
    ("form5", "Son 5 form", "sonuc", "son 5 maç puanı"),
    ("son5_att", "Son 5 attığı gol", "gol", "son maçlardaki hücum verimi"),
    ("son5_yen", "Son 5 yediği gol", "gol", "son maçlardaki savunma"),
    ("ic_form", "İç saha formu", "sonuc", "sadece ev maçları puanı"),
    ("dis_form", "Deplasman formu", "sonuc", "sadece deplasman puanı"),
    ("ev_avantaj", "Ev avantajı", "sonuc", "ligin genel ev sahibi üstünlüğü"),
    ("yorgunluk", "Fikstür yorgunluğu", "sonuc", "<4 gün dinlenme cezası"),
    ("korner", "Korner eğilimi", "korner", "korner geçmişi ev/dep"),
    ("kart_takim", "Takım kart eğilimi", "kart", "takımın kart geçmişi"),
    ("faul", "Faul eğilimi", "kart", "faul → kart riski"),
    ("disiplin", "Disiplin profili", "kart", "faul başına kart"),
    ("hakem_sari", "Hakem sarı ort.", "kart", "hakemin sarı kart eğilimi"),
    ("hakem_kirmizi", "Hakem kırmızı ort.", "kart", "hakemin kırmızı eğilimi"),
    ("hakem_son5", "Hakem son 5 kart", "kart", "hakemin son form kartı"),
    ("iy_gol", "İlk yarı gol beklentisi", "iy", "erken gol eğilimi"),
    ("hava_zemin", "Hava + zemin", "gol", "yağış → ağır zemin → az gol"),
    ("ofsayt_tuzak", "Ofsayt tuzağı gücü", "sonuc", "rakibe yaptırdığı ofsayt"),
    ("ofsayt_dus", "Ofsayta düşme", "gol", "kendi düştüğü ofsayt (verimsizlik)"),
]


def kriter_puanla(ev, dep, ev_def, dep_def, hakem_def, defter, hava=None,
                  hakem=None, mac_tarihi=None):
    """Bir maç için 21 kriterin ev-lehine puanını üretir (0-100, 50=nötr).
    Dönüş: {kod: {'ev_puan','alan'}} — puan ev sahibi lehine yorumlanır."""
    lig_gol = defter.get("_lig_gol", 1.3)
    tum = [v for k, v in defter.items() if k != "_lig_gol"]
    e, d = ev_def, dep_def
    P = {}

    def qoy(kod, ev_puan, alan):
        P[kod] = {"ev_puan": round(float(ev_puan), 1), "alan": alan}

    # gücü: ev hücum vs dep savunma → ev lehine
    qoy("hucum", 50 + (_n(e.get("att_ort"), [x.get("att_ort") for x in tum]) - 50) * 0.5
                    + (50 - _n(d.get("yen_ort"), [x.get("yen_ort") for x in tum])) * 0.5, "gol")
    qoy("savunma", 50 + (50 - _n(e.get("yen_ort"), [x.get("yen_ort") for x in tum])) * 0.5
                      + (_n(d.get("att_ort"), [x.get("att_ort") for x in tum]) - 50) * 0.5, "gol")
    # AVELOR-xG: isabetli şut ağırlıklı üretim
    e_xg = (e.get("isabet_ort", 0) or 0) * 0.33 + ((e.get("sut_ort", 0) or 0) - (e.get("isabet_ort", 0) or 0)) * 0.05
    d_xg = (d.get("isabet_ort", 0) or 0) * 0.33 + ((d.get("sut_ort", 0) or 0) - (d.get("isabet_ort", 0) or 0)) * 0.05
    qoy("xg", _n(e_xg, [e_xg, d_xg]), "gol")
    qoy("form5", _n(e.get("form5"), [e.get("form5"), d.get("form5")]), "sonuc")
    qoy("son5_att", _n(e.get("att_ort"), [x.get("att_ort") for x in tum]), "gol")
    qoy("son5_yen", 100 - _n(e.get("yen_ort"), [x.get("yen_ort") for x in tum]), "gol")
    qoy("ic_form", _n(e.get("ev_puan_ort"), [x.get("ev_puan_ort") for x in tum]), "sonuc")
    qoy("dis_form", _n(d.get("dep_puan_ort"), [x.get("dep_puan_ort") for x in tum]), "sonuc")
    qoy("ev_avantaj", 62, "sonuc")  # sabit ev lehine eğilim (lig geneli ~%46 ev galibiyeti)
    # yorgunluk: ev son maçından beri az gün geçtiyse ev aleyhine
    if mac_tarihi is not None and e.get("son_mac_tarih") is not None:
        try:
            gun_ev = (pd.Timestamp(mac_tarihi) - e["son_mac_tarih"]).days
            gun_dep = (pd.Timestamp(mac_tarihi) - d["son_mac_tarih"]).days if d.get("son_mac_tarih") is not None else 7
            # ev daha yorgunsa ev aleyhine (<50), dep yorgunsa ev lehine
            fark = 50
            if 0 <= gun_ev < 4: fark -= 12
            if 0 <= gun_dep < 4: fark += 12
            qoy("yorgunluk", fark, "sonuc")
        except Exception:
            qoy("yorgunluk", 50, "sonuc")
    else:
        qoy("yorgunluk", 50, "sonuc")
    qoy("korner", _n(e.get("korner_ort"), [x.get("korner_ort") for x in tum]), "korner")
    qoy("kart_takim", _n((e.get("sari_ort", 0) or 0) + (d.get("sari_ort", 0) or 0),
                         [(x.get("sari_ort", 0) or 0) for x in tum]), "kart")
    qoy("faul", _n((e.get("faul_ort", 0) or 0) + (d.get("faul_ort", 0) or 0),
                   [(x.get("faul_ort", 0) or 0) for x in tum]), "kart")
    disip_e = (e.get("sari_ort", 0) or 0) / max(e.get("faul_ort", 1) or 1, 0.1)
    disip_d = (d.get("sari_ort", 0) or 0) / max(d.get("faul_ort", 1) or 1, 0.1)
    tum_disip = [((x.get("sari_ort", 0) or 0) / max(x.get("faul_ort", 1) or 1, 0.1)) for x in tum]
    qoy("disiplin", _n((disip_e + disip_d) / 2, tum_disip), "kart")
    # hakem: adı verildiyse ve defterde varsa gerçek eğilimini kullan
    hk = hakem_def.get(hakem) if (hakem and hakem_def) else None
    if hk and hk.get("mac", 0) >= 3:
        tum_h = [v for v in hakem_def.values() if v.get("mac", 0) >= 3]
        qoy("hakem_sari", _n(hk["sari_ort"], [x["sari_ort"] for x in tum_h]), "kart")
        qoy("hakem_kirmizi", _n(hk["kirmizi_ort"], [x["kirmizi_ort"] for x in tum_h]), "kart")
        qoy("hakem_son5", _n(hk["son5_kart"], [x["son5_kart"] for x in tum_h]), "kart")
    else:
        qoy("hakem_sari", 50, "kart"); qoy("hakem_kirmizi", 50, "kart"); qoy("hakem_son5", 50, "kart")
    qoy("iy_gol", _n((e.get("att_ort", 0) or 0) + (d.get("att_ort", 0) or 0),
                     [(x.get("att_ort", 0) or 0) + (x.get("att_ort", 0) or 0) for x in tum]), "iy")
    # hava+zemin: yağışlıysa gol beklentisi düşer (app'te hava geçilir)
    qoy("hava_zemin", 50 if not hava else (35 if hava.get("yagis_mm", 0) >= 5 else 55), "gol")
    qoy("ofsayt_tuzak", _n(e.get("ofsayt_yaptirdi"), [x.get("ofsayt_yaptirdi") for x in tum]), "sonuc")
    qoy("ofsayt_dus", 100 - _n(e.get("ofsayt_dustu"), [x.get("ofsayt_dustu") for x in tum]), "gol")
    return P


# ---------------------------------------------------------------------------
# KRİTER DEĞERLENDİRME — her kriterin maç sonuçlarıyla ne kadar tuttuğu
# ---------------------------------------------------------------------------
def kriter_karne(df: pd.DataFrame, min_gecmis: int = 20) -> pd.DataFrame:
    """Kronolojik: her tamamlanmış maçta 21 kriterin tahminini gerçekle
    karşılaştırır. Her kriterin ALANINA göre 'tuttu mu' ölçülür.
    Dönüş: kriter başına (deneme sayısı, tutma %, ağırlık önerisi)."""
    d = df.dropna(subset=["FTHG", "FTAG"]).sort_values("Date").reset_index(drop=True)
    skor = {k[0]: [0, 0] for k in KRITER_TANIM}  # [deneme, tuttu]

    for i in range(len(d)):
        m = d.iloc[i]
        defter = takim_defteri(d, m["Date"])
        ev, dep = m["HomeTeam"], m["AwayTeam"]
        if ev not in defter or dep not in defter:
            continue
        if defter[ev]["mac"] < 1 or defter[dep]["mac"] < 1:
            continue
        hakem_def = hakem_defteri(d, m["Date"])
        hakem_adi = m.get("Referee") if "Referee" in d.columns else None
        P = kriter_puanla(ev, dep, defter[ev], defter[dep], hakem_def, defter,
                          hakem=hakem_adi, mac_tarihi=m["Date"])

        # gerçek sonuçlar
        eh, ea = int(m["FTHG"]), int(m["FTAG"])
        gercek_sonuc = "1" if eh > ea else ("X" if eh == ea else "2")
        toplam = eh + ea
        kart_toplam = (m.get("HY", 0) + m.get("AY", 0) + m.get("HR", 0) + m.get("AR", 0)
                       if pd.notna(m.get("HY", np.nan)) else None)
        korner_toplam = (m.get("HC", 0) + m.get("AC", 0)
                         if pd.notna(m.get("HC", np.nan)) else None)
        iy_toplam = (m.get("HTHG", 0) + m.get("HTAG", 0)
                     if pd.notna(m.get("HTHG", np.nan)) else None)

        for kod, bilgi in P.items():
            p, alan = bilgi["ev_puan"], bilgi["alan"]
            if abs(p - 50) < 3:  # kriter nötr → bu maçta iddiası yok, sayma
                continue
            skor[kod][0] += 1
            tuttu = False
            if alan == "sonuc":
                # yüksek puan ev galibiyeti öngörür
                tahmin = "1" if p > 55 else ("2" if p < 45 else "X")
                tuttu = tahmin == gercek_sonuc
            elif alan == "gol":
                # yüksek puan çok gol (üst 2.5) öngörür
                tuttu = (p > 55) == (toplam >= 3)
            elif alan == "kart" and kart_toplam is not None:
                tuttu = (p > 55) == (kart_toplam >= 4)
            elif alan == "korner" and korner_toplam is not None:
                tuttu = (p > 55) == (korner_toplam >= 9)
            elif alan == "iy" and iy_toplam is not None:
                tuttu = (p > 55) == (iy_toplam >= 1)
            else:
                skor[kod][0] -= 1  # ölçülemedi, geri al
                continue
            skor[kod][1] += tuttu

    satirlar = []
    ad = {k[0]: k[1] for k in KRITER_TANIM}
    alan = {k[0]: k[2] for k in KRITER_TANIM}
    for kod, (deneme, tuttu) in skor.items():
        oran = (tuttu / deneme * 100) if deneme >= 1 else None
        # ağırlık önerisi: 0.50=şans→1.0, her %1 üstü +0.06 (at yarışı mantığı)
        agirlik = round(1.0 + max(0, (oran - 50)) * 0.06, 2) if oran else 1.0
        satirlar.append({"Kriter": ad[kod], "Alan": alan[kod], "Deneme": deneme,
                         "Tutma %": round(oran, 1) if oran else None,
                         "Ağırlık": agirlik if deneme >= min_gecmis else 1.0,
                         "Güvenilir mi": "✓" if deneme >= min_gecmis else "veri az"})
    return pd.DataFrame(satirlar).sort_values("Tutma %", ascending=False, na_position="last")
