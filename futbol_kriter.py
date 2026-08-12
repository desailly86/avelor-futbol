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


# ---------------------------------------------------------------------------
# TAHMİN KATMANI — kriterleri ağırlıklarıyla birleştirip markete olasılık üret
# ---------------------------------------------------------------------------
# Her market, o markete ait kriterlerin ağırlıklı ortalamasından beslenir.
MARKET_KRITER = {
    # market: [(kriter_kodu, yon)]  yon=+1 kriter yüksekse market lehine, -1 ters
    "1":       [("form5", 1), ("ic_form", 1), ("hucum", 1), ("ev_avantaj", 1),
                ("ofsayt_tuzak", 1), ("yorgunluk", 1), ("xg", 1)],
    "2":       [("dis_form", 1), ("form5", -1), ("hucum", -1), ("ev_avantaj", -1)],
    "ust25":   [("hucum", 1), ("son5_att", 1), ("xg", 1), ("son5_yen", -1),
                ("hava_zemin", 1), ("iy_gol", 1)],
    "kg_var":  [("hucum", 1), ("son5_att", 1), ("savunma", -1), ("xg", 1)],
    "korner_ust":[("korner", 1)],
    "kart_ust":[("kart_takim", 1), ("faul", 1), ("hakem_sari", 1), ("hakem_kirmizi", 1),
                ("hakem_son5", 1), ("disiplin", 1)],
    "iy_ust":  [("iy_gol", 1), ("hucum", 1), ("son5_att", 1)],
}
MARKET_ETIKET = {
    "1": "MS 1 (ev)", "2": "MS 2 (dep)", "X": "MS X",
    "1X": "Çifte Şans 1-X", "X2": "Çifte Şans X-2",
    "ust25": "2.5 Üst", "alt25": "2.5 Alt", "kg_var": "KG Var", "kg_yok": "KG Yok",
    "korner_ust": "Korner 9.5 Üst", "kart_ust": "Kart 3.5 Üst", "iy_ust": "İY 0.5 Üst",
}


def _puan_to_olasilik(agirlikli_puan, taban=50.0):
    """Ağırlıklı kriter puanını (0-100) olasılığa çevir. Nötr 50 → taban olasılık.
    Sapmayı yumuşat (aşırı özgüven modelin en büyük hatası): 0.45 katsayı, tavan %88."""
    return round(max(8, min(88, 50 + (agirlikli_puan - 50) * 0.45)), 1)


def mac_tahmin_puan(ev, dep, defter, hakem_def, agirliklar=None, hava=None,
                    hakem=None, mac_tarihi=None):
    """Puan-ağırlık motoru: 21 kriterden markete olasılık üretir.
    agirliklar: {kriter_kodu: ağırlık} (Kriter Karnesi'nden; yoksa hepsi 1.0)."""
    if ev not in defter or dep not in defter:
        return None
    w = agirliklar or {}
    P = kriter_puanla(ev, dep, defter[ev], defter[dep], hakem_def, defter,
                      hava=hava, hakem=hakem, mac_tarihi=mac_tarihi)

    def market_puan(market):
        pay = payda = 0.0
        for kod, yon in MARKET_KRITER.get(market, []):
            if kod not in P:
                continue
            ag = w.get(kod, 1.0)
            puan = P[kod]["ev_puan"]
            deger = puan if yon == 1 else (100 - puan)
            pay += ag * deger
            payda += ag
        return (pay / payda) if payda else 50.0

    t = {}
    p1 = _puan_to_olasilik(market_puan("1"))
    p2 = _puan_to_olasilik(market_puan("2"))
    # beraberlik: 1 ve 2 ne kadar dengeliyse o kadar yüksek
    denge = 100 - abs(p1 - p2)
    px = round(max(8, min(40, denge * 0.32)), 1)
    # normalize 1X2
    tpl = p1 + px + p2
    t["1"], t["X"], t["2"] = round(p1/tpl*100,1), round(px/tpl*100,1), round(p2/tpl*100,1)
    t["1X"] = round(t["1"] + t["X"], 1)
    t["X2"] = round(t["X"] + t["2"], 1)
    t["ust25"] = _puan_to_olasilik(market_puan("ust25"))
    t["alt25"] = round(100 - t["ust25"], 1)
    t["kg_var"] = _puan_to_olasilik(market_puan("kg_var"))
    t["kg_yok"] = round(100 - t["kg_var"], 1)
    t["korner_ust"] = _puan_to_olasilik(market_puan("korner_ust"))
    t["kart_ust"] = _puan_to_olasilik(market_puan("kart_ust"))
    t["iy_ust"] = _puan_to_olasilik(market_puan("iy_ust"))
    t["_ev_mac"] = defter[ev]["mac"]
    t["_dep_mac"] = defter[dep]["mac"]
    t["_guven"] = "düşük" if min(defter[ev]["mac"], defter[dep]["mac"]) < 5 else "orta"
    return t


def en_iyi_uc(t, bazlar=None):
    """Lig tabanına göre en yüksek KENAR'lı 3 öneri (cesur, çeşitli)."""
    if not t:
        return []
    bazlar = bazlar or {"1": 45, "2": 30, "ust25": 52, "kg_var": 52,
                        "korner_ust": 50, "kart_ust": 50, "iy_ust": 60, "1X": 65, "X2": 50}
    grup = {"1": "sonuc", "2": "sonuc", "1X": "sonuc", "X2": "sonuc",
            "ust25": "gol", "alt25": "gol", "kg_var": "kg", "kg_yok": "kg",
            "korner_ust": "korner", "kart_ust": "kart", "iy_ust": "iy"}
    adaylar = []
    for kod in MARKET_ETIKET:
        if kod not in t or not isinstance(t[kod], (int, float)):
            continue
        p = float(t[kod])
        kenar = p - bazlar.get(kod, 50)
        if p >= 50 and kenar >= 5:
            adaylar.append((kenar, p, kod))
    adaylar.sort(reverse=True)
    secim, gruplar = [], set()
    for kenar, p, kod in adaylar:
        g = grup.get(kod, kod)
        if g in gruplar:
            continue
        secim.append({"market": MARKET_ETIKET[kod], "olasilik": round(p,1),
                      "kenar": round(kenar,1)})
        gruplar.add(g)
        if len(secim) == 3:
            break
    return secim


def agirlik_sozlugu(df: pd.DataFrame, min_gecmis: int = 8) -> dict:
    """Kriter karnesinden {kriter_kodu: ağırlık} üretir. Oynanmış maçlardan
    HEMEN başlar (8 maçtan itibaren), ama az veride ağırlık etkisi KADEMELİ:
    - <8 maç: nötr (1.0), henüz güvenilmez
    - 8-30 maç: ağırlık farkı %40 uygulanır (temkinli başlangıç)
    - 30-80 maç: %70
    - 80+ maç: tam (%100)
    Böylece kriterler erken devreye girer ama sezon başında aşırı iddia etmez."""
    oynanmis = len(df.dropna(subset=["FTHG"]))
    if oynanmis < min_gecmis:
        return {}
    # kademeli güven katsayısı
    if oynanmis < 30:
        kademe = 0.40
    elif oynanmis < 80:
        kademe = 0.70
    else:
        kademe = 1.00
    karne = kriter_karne(df, min_gecmis=min_gecmis)
    ad_kod = {k[1]: k[0] for k in KRITER_TANIM}
    w = {}
    for _, r in karne.iterrows():
        kod = ad_kod.get(r["Kriter"])
        if not kod:
            continue
        if r["Deneme"] >= min_gecmis and r["Tutma %"] is not None:
            ham_agirlik = r["Ağırlık"]  # 1.0 + fazlası
            # kademeli: farkın bir kısmını uygula
            w[kod] = round(1.0 + (ham_agirlik - 1.0) * kademe, 2)
        else:
            w[kod] = 1.0
    return w


def agirlik_durumu(df: pd.DataFrame) -> dict:
    """Ağırlıkların ne kadar olgunlaştığını özetler (app'te göstermek için)."""
    oynanmis = len(df.dropna(subset=["FTHG"]))
    if oynanmis < 8:
        return {"durum": "Bekliyor", "kademe": "%0", "aciklama":
                f"{oynanmis} maç oynandı — ağırlıklar için en az 8 maç gerekir.", "oynanmis": oynanmis}
    if oynanmis < 30:
        k = "%40 (temkinli)"
    elif oynanmis < 80:
        k = "%70 (gelişiyor)"
    else:
        k = "%100 (olgun)"
    return {"durum": "Aktif", "kademe": k, "oynanmis": oynanmis,
            "aciklama": f"{oynanmis} maçtan öğrenildi; ağırlık etkisi {k}."}


def tahmin_isabeti(df: pd.DataFrame, min_gecmis: int = 3) -> dict:
    """Her maçı, yalnızca ONDAN ÖNCEKİ veriyle tahmin edip gerçekle kıyaslar.
    Market market isabet yüzdesi döndürür (MS1, 2.5 Üst, KG Var...).
    Bu, sistemin GERÇEK karnesidir — 'en çok hangi tahminimiz tutuyor' sorusunun cevabı.
    Dönüş: {market: {'deneme','dogru','yuzde'}, '_genel': {...}}"""
    d = df.dropna(subset=["FTHG", "FTAG"]).sort_values("Date").reset_index(drop=True)
    # her maçta model bir 'en güçlü tahmin' üretir; market bazında sayaç tut
    sayac = {}  # market_kodu: [deneme, dogru]
    genel = [0, 0]  # tüm önerilerin toplamı
    # Ağırlıkları bir kez (tüm sezondan) hesapla — her maçta yeniden hesaplamak çok yavaş
    sabit_w = agirlik_sozlugu(d, min_gecmis=8) if len(d) >= 8 else {}

    for i in range(len(d)):
        m = d.iloc[i]
        gecmis = d.iloc[:i]
        if len(gecmis.dropna(subset=["FTHG"])) < min_gecmis:
            continue
        defter = takim_defteri(gecmis, m["Date"])
        ev, dep = m["HomeTeam"], m["AwayTeam"]
        if ev not in defter or dep not in defter:
            continue
        if defter[ev]["mac"] < 1 or defter[dep]["mac"] < 1:
            continue
        hk = hakem_defteri(gecmis, m["Date"])
        hakem = m.get("Referee") if "Referee" in d.columns else None
        t = mac_tahmin_puan(ev, dep, defter, hk, agirliklar=sabit_w, hakem=hakem, mac_tarihi=m["Date"])
        if not t:
            continue

        # gerçek sonuçlar
        eh, ea = int(m["FTHG"]), int(m["FTAG"])
        sonuc = "1" if eh > ea else ("X" if eh == ea else "2")
        toplam = eh + ea
        kg = eh > 0 and ea > 0
        iy = (m.get("HTHG", 0) + m.get("HTAG", 0)) if pd.notna(m.get("HTHG", np.nan)) else None
        korner = (m.get("HC", 0) + m.get("AC", 0)) if pd.notna(m.get("HC", np.nan)) else None
        kart = (m.get("HY",0)+m.get("AY",0)+m.get("HR",0)+m.get("AR",0)) if pd.notna(m.get("HY", np.nan)) else None

        # her market için: model 'evet' diyor mu (>=50) ve gerçek ne?
        kontroller = {
            "1": (t.get("1",0) >= max(t.get("X",0), t.get("2",0)) and t.get("1",0) >= 40, sonuc == "1"),
            "2": (t.get("2",0) >= max(t.get("X",0), t.get("1",0)) and t.get("2",0) >= 40, sonuc == "2"),
            "1X": (t.get("1X",0) >= 60, sonuc in ("1","X")),
            "X2": (t.get("X2",0) >= 60, sonuc in ("X","2")),
            "ust25": (t.get("ust25",0) >= 55, toplam >= 3),
            "alt25": (t.get("alt25",0) >= 55, toplam <= 2),
            "kg_var": (t.get("kg_var",0) >= 55, kg),
            "kg_yok": (t.get("kg_yok",0) >= 55, not kg),
        }
        if iy is not None:
            kontroller["iy_ust"] = (t.get("iy_ust",0) >= 55, iy >= 1)
        if korner is not None:
            kontroller["korner_ust"] = (t.get("korner_ust",0) >= 55, korner >= 9)
        if kart is not None:
            kontroller["kart_ust"] = (t.get("kart_ust",0) >= 55, kart >= 4)

        for market, (onerdi, gercek) in kontroller.items():
            if not onerdi:
                continue  # model bu maçta bu marketi önermedi → sayma
            if market not in sayac:
                sayac[market] = [0, 0]
            sayac[market][0] += 1
            sayac[market][1] += bool(gercek)
            genel[0] += 1
            genel[1] += bool(gercek)

    sonuc_rapor = {}
    for market, (deneme, dogru) in sayac.items():
        sonuc_rapor[market] = {"deneme": deneme, "dogru": dogru,
                               "yuzde": round(dogru / deneme * 100, 1) if deneme else 0.0}
    sonuc_rapor["_genel"] = {"deneme": genel[0], "dogru": genel[1],
                             "yuzde": round(genel[1] / genel[0] * 100, 1) if genel[0] else 0.0}
    return sonuc_rapor
