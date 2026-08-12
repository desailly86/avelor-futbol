# -*- coding: utf-8 -*-
"""
futbol_bulten.py — Maç bülteni (ESPN açık API)
================================================
Maç PROGRAMI ayrı kaynaktan gelir: ESPN scoreboard API (anahtar yok, tüm ligler,
tarihe göre, canlı skor dahil). ESPN veri-merkezi IP'lerini bazen 403'ler; bu
yüzden güçlü tarayıcı başlıkları + iki alternatif ana adres denenir.
"""
from __future__ import annotations
import datetime
import requests
import pandas as pd

UA = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.espn.com/soccer/",
    "Origin": "https://www.espn.com",
    "Sec-Fetch-Site": "same-site",
    "Sec-Fetch-Mode": "cors",
}
TIMEOUT = 20
TSI_FARK = datetime.timedelta(hours=3)  # UTC → TSİ

# ESPN veri-merkezi IP'lerini bazen 403'ler; iki farklı ana adres deneriz
ESPN_KOKLER = [
    "https://site.api.espn.com/apis/site/v2/sports/soccer",
    "https://site.web.api.espn.com/apis/site/v2/sports/soccer",
]

# football-data lig kodu → ESPN lig slug'ı
ESPN_SLUG = {
    "T1": "tur.1", "E0": "eng.1", "E1": "eng.2", "E2": "eng.3", "E3": "eng.4",
    "SP1": "esp.1", "SP2": "esp.2", "D1": "ger.1", "D2": "ger.2",
    "I1": "ita.1", "I2": "ita.2", "F1": "fra.1", "F2": "fra.2",
    "N1": "ned.1", "P1": "por.1", "B1": "bel.1", "G1": "gre.1",
    "SC0": "sco.1", "SC1": "sco.2", "SC2": "sco.3", "SC3": "sco.4",
    "ARG": "arg.1", "AUT": "aut.1", "BRA": "bra.1", "CHN": "chn.1",
    "DNK": "den.1", "FIN": "fin.1", "IRL": "irl.1", "JPN": "jpn.1",
    "MEX": "mex.1", "NOR": "nor.1", "POL": "pol.1", "ROU": "rou.1",
    "RUS": "rus.1", "SWE": "swe.1", "SWZ": "sui.1", "USA": "usa.1",
}
SLUG_AD = {
    "tur.1": "🇹🇷 Süper Lig", "eng.1": "🏴 Premier League", "eng.2": "🏴 Championship",
    "esp.1": "🇪🇸 La Liga", "esp.2": "🇪🇸 Segunda", "ger.1": "🇩🇪 Bundesliga",
    "ger.2": "🇩🇪 2. Bundesliga", "ita.1": "🇮🇹 Serie A", "ita.2": "🇮🇹 Serie B",
    "fra.1": "🇫🇷 Ligue 1", "fra.2": "🇫🇷 Ligue 2", "ned.1": "🇳🇱 Eredivisie",
    "por.1": "🇵🇹 Liga Portugal", "bel.1": "🇧🇪 Pro League", "gre.1": "🇬🇷 Süper Lig",
    "sco.1": "🏴 Premiership", "usa.1": "🇺🇸 MLS", "uefa.champions": "🏆 Şampiyonlar Ligi",
    "uefa.europa": "🥈 Avrupa Ligi",
}

# "Tüm ligler" için taranacak ana ligler
ONEMLI_LIGLER = ["tur.1", "eng.1", "eng.2", "esp.1", "esp.2", "ger.1", "ger.2",
                 "ita.1", "ita.2", "fra.1", "fra.2", "ned.1", "por.1", "bel.1",
                 "gre.1", "sco.1", "usa.1", "uefa.champions", "uefa.europa"]


def _istek(slug: str, ymd: str):
    """Tek slug + gün için ham JSON döndür (iki ana adres dener). Yoksa None."""
    for kok in ESPN_KOKLER:
        try:
            r = requests.get(f"{kok}/{slug}/scoreboard",
                             params={"dates": ymd, "limit": 500},
                             headers=UA, timeout=TIMEOUT)
            if r.status_code == 200:
                return r.json()
        except Exception:
            continue
    return None


def _cek(slug: str, ymd: str) -> list[dict]:
    """Tek slug + gün için sadeleştirilmiş maç listesi."""
    veri = _istek(slug, ymd)
    if veri is None:
        return []
    lig_adi = SLUG_AD.get(slug)
    if not lig_adi:
        ligler = veri.get("leagues") or []
        lig_adi = ligler[0].get("name", slug) if ligler else slug
    maclar = []
    for ev in veri.get("events", []):
        try:
            comp = ev["competitions"][0]
            rk = comp["competitors"]
            e = next(c for c in rk if c["homeAway"] == "home")
            d = next(c for c in rk if c["homeAway"] == "away")
            utc = datetime.datetime.fromisoformat(ev["date"].replace("Z", "+00:00"))
            tsi = utc + TSI_FARK
            durum = ev["status"]["type"]["state"]  # pre / in / post
            hg, ag = e.get("score", ""), d.get("score", "")
            skor = f"{hg} - {ag}" if durum in ("in", "post") and hg != "" else ""
            maclar.append({
                "Saat": tsi.strftime("%H:%M"), "tsi_dt": tsi,
                "Ev": e["team"]["displayName"], "Dep": d["team"]["displayName"],
                "Skor": skor,
                "Durum": {"pre": "başlamadı", "in": "🔴 CANLI", "post": "bitti"}.get(durum, ""),
                "Lig": lig_adi,
            })
        except (KeyError, StopIteration, IndexError):
            continue
    return maclar


def gunun_maclari(tarih=None, lig_kodu=None) -> pd.DataFrame:
    """Seçili günün maçları. lig_kodu=None → önemli ligler tek tek çekilip birleştirilir."""
    gun = pd.Timestamp(tarih) if tarih else pd.Timestamp(datetime.date.today())
    ymd = gun.strftime("%Y%m%d")
    maclar = []
    if lig_kodu and lig_kodu in ESPN_SLUG:
        maclar = _cek(ESPN_SLUG[lig_kodu], ymd)
    else:
        for slug in ONEMLI_LIGLER:
            maclar.extend(_cek(slug, ymd))
    if not maclar:
        return pd.DataFrame(columns=["Saat", "Ev", "Dep", "Skor", "Durum", "Lig"])
    df = pd.DataFrame(maclar).sort_values("tsi_dt").reset_index(drop=True)
    return df.drop(columns=["tsi_dt"])


def hafta_ozeti(gun_sayisi: int = 7, tarih=None) -> pd.DataFrame:
    """Önümüzdeki N günde hangi tarihte kaç maç var (tüm ligler)."""
    bas = pd.Timestamp(tarih) if tarih else pd.Timestamp(datetime.date.today())
    satirlar = []
    for i in range(gun_sayisi):
        g = bas + pd.Timedelta(days=i)
        n = sum(len(_cek(s, g.strftime("%Y%m%d"))) for s in ONEMLI_LIGLER[:6])
        satirlar.append({"Tarih": g, "Gün": g.strftime("%d.%m.%Y (%a)"), "Maç": n})
    return pd.DataFrame(satirlar)


def teshis(lig_kodu="P1", tarih=None) -> str:
    """Teşhis: ESPN'den ne dönüyor? Her adresi tek tek dener, raporlar."""
    gun = pd.Timestamp(tarih) if tarih else pd.Timestamp(datetime.date.today())
    ymd = gun.strftime("%Y%m%d")
    slug = ESPN_SLUG.get(lig_kodu, lig_kodu)
    rapor = [f"Lig: {lig_kodu} → slug: {slug} · Tarih: {ymd}", ""]
    veri = None
    for kok in ESPN_KOKLER:
        url = f"{kok}/{slug}/scoreboard"
        rapor.append(f"Deneme: {url}?dates={ymd}")
        try:
            r = requests.get(url, params={"dates": ymd, "limit": 500},
                             headers=UA, timeout=TIMEOUT)
            rapor.append(f"  → HTTP {r.status_code}")
            if r.status_code == 200:
                veri = r.json()
                rapor.append("  → ✓ Bu adres çalıştı")
                break
            else:
                rapor.append(f"  → Yanıt: {r.text[:120]}")
        except Exception as ex:
            rapor.append(f"  → HATA: {ex}")
        rapor.append("")
    if veri is None:
        rapor.append("SONUÇ: Hiçbir adres veri vermedi — ESPN bu sunucuyu engelliyor olabilir.")
        return "\n".join(rapor)
    events = veri.get("events", [])
    ligler = veri.get("leagues", [])
    rapor.append("")
    rapor.append(f"Event sayısı: {len(events)}")
    rapor.append(f"Lig bilgisi: {ligler[0].get('name') if ligler else 'YOK'}")
    if events:
        ilk = events[0]
        rapor.append(f"İlk maç: {ilk.get('name', '?')}")
        rapor.append(f"Tarih: {ilk.get('date', '?')}")
    else:
        rapor.append("→ Bağlantı çalışıyor ama bu tarihte bu ligde maç yok.")
    return "\n".join(rapor)
