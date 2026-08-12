# -*- coding: utf-8 -*-
"""
futbol_espn.py — ESPN açık API'sinden zengin veri (bağımsız modül)
===================================================================
Beş veri türü, her biri KENDİ BAŞINA çalışır (biri patlasa diğerleri ayakta):
  1. puan_durumu_espn   → lig tablosu (puan, averaj, form)
  2. mac_oranlari_espn  → maç bazlı bahis oranları
  3. sakatlik_espn      → takım sakatlık/eksik listesi
  4. gol_krallari_espn  → lig gol kralları / istatistik liderleri
  5. mac_olaylari_espn  → maç içi olaylar (gol, kart, kazanma olasılığı)

DÜRÜSTLÜK: Hepsi ESPN'in resmi olmayan API'sidir; yapı değişebilir, bazı
endpoint'ler (özellikle oyuncu stat) futbolda kısıtlıdır. Her fonksiyon hata
durumunda boş/None döner, uygulamayı çökertmez. Geliştirme ortamı dış ağa
kapalı olduğundan canlı ilk temas kullanıcının sunucusunda olacak.
"""
from __future__ import annotations
import datetime
import requests
import pandas as pd

from futbol_bulten import UA, TIMEOUT, ESPN_SLUG, ESPN_KOKLER

# standings ve leaders farklı base kullanır
SITE_V2 = ["https://site.api.espn.com/apis/v2/sports/soccer",
           "https://site.web.api.espn.com/apis/v2/sports/soccer"]
CORE = "https://sports.core.api.espn.com/v2/sports/soccer/leagues"
SITE = "https://site.api.espn.com/apis/site/v2/sports/soccer"


def _json(url, params=None):
    """Tek URL dene, 200 ise JSON döndür, değilse None."""
    try:
        r = requests.get(url, params=params or {}, headers=UA, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def _json_coklu(urller, params=None):
    """Birden fazla base dene (biri 403/boş verirse diğeri)."""
    for u in urller:
        veri = _json(u, params)
        if veri:
            return veri
    return None


# ---------------------------------------------------------------------------
# 1. PUAN DURUMU (standings) — puan, averaj, form
# ---------------------------------------------------------------------------
def puan_durumu_espn(lig_kodu) -> pd.DataFrame:
    """ESPN lig tablosu. /apis/v2/ kullanır (site/v2 boş döner)."""
    slug = ESPN_SLUG.get(lig_kodu, lig_kodu)
    veri = _json_coklu([f"{b}/{slug}/standings" for b in SITE_V2])
    if not veri:
        return pd.DataFrame()
    # ESPN standings yapısı: children[].standings.entries[] ya da standings.entries[]
    entries = []
    try:
        if "children" in veri and veri["children"]:
            for grup in veri["children"]:
                st = grup.get("standings", {})
                entries.extend(st.get("entries", []))
        elif "standings" in veri:
            entries = veri["standings"].get("entries", [])
    except Exception:
        return pd.DataFrame()

    satirlar = []
    for e in entries:
        try:
            takim = e["team"]["displayName"]
            stats = {s["name"]: s.get("value", s.get("displayValue"))
                     for s in e.get("stats", [])}
            satirlar.append({
                "Takım": takim,
                "O": int(stats.get("gamesPlayed", 0) or 0),
                "G": int(stats.get("wins", 0) or 0),
                "B": int(stats.get("ties", 0) or 0),
                "M": int(stats.get("losses", 0) or 0),
                "AG": int(stats.get("pointsFor", 0) or 0),
                "YG": int(stats.get("pointsAgainst", 0) or 0),
                "Av": int(stats.get("pointDifferential", 0) or 0),
                "P": int(stats.get("points", 0) or 0),
            })
        except Exception:
            continue
    if not satirlar:
        return pd.DataFrame()
    df = pd.DataFrame(satirlar).sort_values(["P", "Av", "AG"], ascending=False).reset_index(drop=True)
    df.insert(0, "Sıra", range(1, len(df) + 1))
    return df


# ---------------------------------------------------------------------------
# 2. MAÇ ORANLARI (odds) — maç bazlı bahis oranları
# ---------------------------------------------------------------------------
def mac_oranlari_espn(lig_kodu, tarih=None) -> pd.DataFrame:
    """Seçili günün maçları için ESPN bahis oranları (scoreboard içinden)."""
    slug = ESPN_SLUG.get(lig_kodu, lig_kodu)
    gun = pd.Timestamp(tarih) if tarih else pd.Timestamp(datetime.date.today())
    ymd = gun.strftime("%Y%m%d")
    veri = _json_coklu([f"{k}/{slug}/scoreboard" for k in ESPN_KOKLER],
                       params={"dates": ymd})
    if not veri:
        return pd.DataFrame()
    satirlar = []
    for ev in veri.get("events", []):
        try:
            comp = ev["competitions"][0]
            rk = comp["competitors"]
            e = next(c for c in rk if c["homeAway"] == "home")
            d = next(c for c in rk if c["homeAway"] == "away")
            ev_ad = e["team"]["displayName"]
            dep_ad = d["team"]["displayName"]
            oran = comp.get("odds", [])
            if oran:
                o = oran[0]  # ilk sağlayıcı
                satirlar.append({
                    "Ev": ev_ad, "Dep": dep_ad,
                    "Detay": o.get("details", "-"),
                    "1 (ev)": o.get("homeTeamOdds", {}).get("moneyLine", "-"),
                    "2 (dep)": o.get("awayTeamOdds", {}).get("moneyLine", "-"),
                    "Alt/Üst": o.get("overUnder", "-"),
                    "Sağlayıcı": o.get("provider", {}).get("name", "-"),
                })
            else:
                satirlar.append({"Ev": ev_ad, "Dep": dep_ad, "Detay": "oran yok",
                                 "1 (ev)": "-", "2 (dep)": "-", "Alt/Üst": "-", "Sağlayıcı": "-"})
        except (KeyError, StopIteration, IndexError):
            continue
    return pd.DataFrame(satirlar)


# ---------------------------------------------------------------------------
# 3. SAKATLIKLAR (injuries) — takım bazlı
# ---------------------------------------------------------------------------
def _takimlar_espn(lig_kodu) -> dict:
    """Lig takımları: {takım_adı: team_id}. Diğer fonksiyonlar id için kullanır."""
    slug = ESPN_SLUG.get(lig_kodu, lig_kodu)
    veri = _json(f"{SITE}/{slug}/teams")
    harita = {}
    try:
        for grup in veri["sports"][0]["leagues"][0]["teams"]:
            t = grup["team"]
            harita[t["displayName"]] = t["id"]
    except (KeyError, TypeError, IndexError):
        pass
    return harita


def sakatlik_espn(lig_kodu) -> pd.DataFrame:
    """Ligin tüm takımlarının sakatlık/eksik listesi. DİKKAT: ESPN verisi
    futbolda güncel olmayabilir — kullanıcı doğruluğunu kendi teyit etmeli."""
    slug = ESPN_SLUG.get(lig_kodu, lig_kodu)
    takimlar = _takimlar_espn(lig_kodu)
    if not takimlar:
        return pd.DataFrame()
    satirlar = []
    for takim_adi, tid in takimlar.items():
        veri = _json(f"{SITE}/{slug}/teams/{tid}/injuries")
        if not veri:
            continue
        for inj in veri.get("injuries", []):
            try:
                oyuncu = inj.get("athlete", {}).get("displayName", "?")
                durum = inj.get("status", "?")
                detay = inj.get("details", {})
                aciklama = detay.get("type", "") if isinstance(detay, dict) else ""
                satirlar.append({"Takım": takim_adi, "Oyuncu": oyuncu,
                                 "Durum": durum, "Detay": aciklama})
            except Exception:
                continue
    return pd.DataFrame(satirlar)


# ---------------------------------------------------------------------------
# 4. GOL KRALLARI / LİDERLER (leaders)
# ---------------------------------------------------------------------------
def gol_krallari_espn(lig_kodu, sezon=None) -> pd.DataFrame:
    """Lig gol kralları ve istatistik liderleri (Core API)."""
    slug = ESPN_SLUG.get(lig_kodu, lig_kodu)
    if sezon:
        url = f"{CORE}/{slug}/seasons/{sezon}/leaders"
    else:
        url = f"{CORE}/{slug}/leaders"
    veri = _json(url)
    if not veri:
        return pd.DataFrame()
    satirlar = []
    try:
        for kategori in veri.get("categories", []):
            kat_ad = kategori.get("displayName", kategori.get("name", ""))
            if "goal" not in kat_ad.lower() and "scor" not in kat_ad.lower():
                continue  # sadece gol kategorisi
            for lider in kategori.get("leaders", [])[:15]:
                # atlet ve değer $ref ile gelir; displayValue genelde hazır
                deger = lider.get("displayValue", lider.get("value", ""))
                atlet_ref = lider.get("athlete", {})
                ad = atlet_ref.get("displayName", "")
                if not ad and "$ref" in atlet_ref:
                    at = _json(atlet_ref["$ref"])
                    ad = at.get("displayName", "?") if at else "?"
                satirlar.append({"Kategori": kat_ad, "Oyuncu": ad, "Değer": deger})
    except Exception:
        return pd.DataFrame()
    return pd.DataFrame(satirlar)


# ---------------------------------------------------------------------------
# 5. MAÇ OLAYLARI (plays / probabilities) — belirli bir maç için
# ---------------------------------------------------------------------------
def mac_olaylari_espn(lig_kodu, event_id) -> dict:
    """Bir maçın özeti: goller, kartlar, kazanma olasılığı. summary endpoint."""
    slug = ESPN_SLUG.get(lig_kodu, lig_kodu)
    veri = _json(f"{SITE}/{slug}/summary", params={"event": event_id})
    if not veri:
        return {}
    sonuc = {"olaylar": [], "istatistik": []}
    try:
        # goller, kartlar (key events)
        for k in veri.get("keyEvents", veri.get("commentary", []))[:50]:
            tip = k.get("type", {}).get("text", "")
            dk = k.get("clock", {}).get("displayValue", "")
            metin = k.get("text", "")
            if tip or metin:
                sonuc["olaylar"].append({"Dakika": dk, "Tip": tip, "Açıklama": metin})
    except Exception:
        pass
    try:
        # takım istatistikleri (topla oynama, şut vb)
        for takim in veri.get("boxscore", {}).get("teams", []):
            ad = takim.get("team", {}).get("displayName", "")
            for s in takim.get("statistics", [])[:20]:
                sonuc["istatistik"].append({
                    "Takım": ad, "İstatistik": s.get("label", s.get("name", "")),
                    "Değer": s.get("displayValue", "")})
    except Exception:
        pass
    return sonuc


def mac_id_bul(lig_kodu, tarih=None) -> list:
    """Seçili günün maçlarının (event_id, ev, dep) listesi — olaylar için gerekli."""
    slug = ESPN_SLUG.get(lig_kodu, lig_kodu)
    gun = pd.Timestamp(tarih) if tarih else pd.Timestamp(datetime.date.today())
    veri = _json_coklu([f"{k}/{slug}/scoreboard" for k in ESPN_KOKLER],
                       params={"dates": gun.strftime("%Y%m%d")})
    if not veri:
        return []
    liste = []
    for ev in veri.get("events", []):
        try:
            comp = ev["competitions"][0]
            rk = comp["competitors"]
            e = next(c for c in rk if c["homeAway"] == "home")
            d = next(c for c in rk if c["homeAway"] == "away")
            liste.append({"id": ev["id"], "ev": e["team"]["displayName"],
                          "dep": d["team"]["displayName"],
                          "durum": ev["status"]["type"]["state"]})
        except (KeyError, StopIteration, IndexError):
            continue
    return liste
