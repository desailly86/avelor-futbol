# -*- coding: utf-8 -*-
"""
futbol_bulten.py — Maç bülteni (ESPN açık API)
================================================
football-data.co.uk fikstür konusunda zayıf olduğu için maç PROGRAMI ayrı
kaynaktan gelir: ESPN'in açık scoreboard API'si (anahtar yok, tüm ligler,
tarihe göre, canlı skor dahil).
  Tek gün, tüm ligler:  soccer/all/scoreboard?dates=YYYYMMDD
  Tek lig:              soccer/{slug}/scoreboard?dates=YYYYMMDD
Saatler UTC gelir → TSİ'ye çevrilir. Skor varsa gösterilir (oynanmış/canlı).
DÜRÜSTLÜK: ESPN resmi olmayan bir API'dir, yapısı değişebilir; ama yıllardır
kararlıdır ve tüm dünyanın gördüğü programı verir. Geliştirme ortamında dış ağ
kapalı olduğu için canlı ilk temas kullanıcının sunucusunda olacak.
"""
from __future__ import annotations
import datetime
import requests
import pandas as pd

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
TIMEOUT = 20
TSI_FARK = datetime.timedelta(hours=3)  # UTC → TSİ

ESPN_KOK = "https://site.api.espn.com/apis/site/v2/sports/soccer"

# football-data lig kodu → ESPN lig slug'ı (bülten için eşleme)
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
# ESPN lig adı → bizim gösterim adı (bayraklı)
SLUG_AD = {
    "tur.1": "🇹🇷 Süper Lig", "eng.1": "🏴 Premier League", "eng.2": "🏴 Championship",
    "esp.1": "🇪🇸 La Liga", "ger.1": "🇩🇪 Bundesliga", "ita.1": "🇮🇹 Serie A",
    "fra.1": "🇫🇷 Ligue 1", "ned.1": "🇳🇱 Eredivisie", "por.1": "🇵🇹 Liga Portugal",
    "bel.1": "🇧🇪 Pro League", "gre.1": "🇬🇷 Süper Lig", "sco.1": "🏴 Premiership",
    "usa.1": "🇺🇸 MLS", "uefa.champions": "🏆 Şampiyonlar Ligi",
    "uefa.europa": "🥈 Avrupa Ligi", "eng.2": "🏴 Championship",
    "esp.2": "🇪🇸 Segunda", "ger.2": "🇩🇪 2. Bundesliga", "ita.2": "🇮🇹 Serie B",
    "fra.2": "🇫🇷 Ligue 2",
}


def _cek(slug: str, tarih_yyyymmdd: str) -> list[dict]:
    """Tek slug + tek gün için ESPN scoreboard çek, sadeleştirilmiş maç listesi döndür."""
    url = f"{ESPN_KOK}/{slug}/scoreboard"
    try:
        r = requests.get(url, params={"dates": tarih_yyyymmdd, "limit": 500},
                         headers=UA, timeout=TIMEOUT)
        r.raise_for_status()
        veri = r.json()
    except Exception:
        return []
    lig_adi = SLUG_AD.get(slug)
    if not lig_adi:
        ligler = veri.get("leagues") or []
        lig_adi = ligler[0].get("name", slug) if ligler else slug
    maclar = []
    for ev in veri.get("events", []):
        try:
            comp = ev["competitions"][0]
            rakipler = comp["competitors"]
            ev_t = next(c for c in rakipler if c["homeAway"] == "home")
            dep_t = next(c for c in rakipler if c["homeAway"] == "away")
            utc = datetime.datetime.fromisoformat(ev["date"].replace("Z", "+00:00"))
            tsi = utc + TSI_FARK
            durum = ev["status"]["type"]  # state: pre / in / post
            hg = ev_t.get("score", "")
            ag = dep_t.get("score", "")
            skor = f"{hg} - {ag}" if durum["state"] in ("in", "post") and hg != "" else ""
            maclar.append({
                "Saat": tsi.strftime("%H:%M"), "tsi_dt": tsi,
                "Ev": ev_t["team"]["displayName"],
                "Dep": dep_t["team"]["displayName"],
                "Skor": skor,
                "Durum": {"pre": "başlamadı", "in": "🔴 CANLI", "post": "bitti"}.get(durum["state"], ""),
                "Lig": lig_adi,
            })
        except (KeyError, StopIteration, IndexError):
            continue
    return maclar


# "Tüm ligler" için taranacak ana ligler (all endpoint'i lig adını boş döndürdüğü
# için her ligi kendi slug'ıyla çekip birleştiriyoruz — bu kesin çalışıyor)
ONEMLI_LIGLER = ["tur.1", "eng.1", "eng.2", "esp.1", "esp.2", "ger.1", "ger.2",
                 "ita.1", "ita.2", "fra.1", "fra.2", "ned.1", "por.1", "bel.1",
                 "gre.1", "sco.1", "usa.1", "uefa.champions", "uefa.europa"]


def gunun_maclari(tarih=None, lig_kodu=None) -> pd.DataFrame:
    """Seçili günün maçları. lig_kodu=None → önemli liglerin hepsi tek tek çekilip
    birleştirilir. lig_kodu verilirse yalnızca o lig. Saate göre sıralı, TSİ."""
    gun = pd.Timestamp(tarih) if tarih else pd.Timestamp(datetime.date.today())
    ymd = gun.strftime("%Y%m%d")
    maclar = []
    if lig_kodu and lig_kodu in ESPN_SLUG:
        maclar = _cek(ESPN_SLUG[lig_kodu], ymd)
    else:
        # tüm ligler: her birini ayrı çek (all endpoint'i güvenilmez)
        for slug in ONEMLI_LIGLER:
            maclar.extend(_cek(slug, ymd))
    if not maclar:
        return pd.DataFrame(columns=["Saat", "Ev", "Dep", "Skor", "Durum", "Lig"])
    df = pd.DataFrame(maclar).sort_values("tsi_dt").reset_index(drop=True)
    return df.drop(columns=["tsi_dt"])


def hafta_ozeti(gun_sayisi: int = 7, tarih=None) -> pd.DataFrame:
    """Önümüzdeki N günde hangi tarihte kaç maç var (takvim için, tüm ligler)."""
    bas = pd.Timestamp(tarih) if tarih else pd.Timestamp(datetime.date.today())
    satirlar = []
    for i in range(gun_sayisi):
        g = bas + pd.Timedelta(days=i)
        try:
            n = len(_cek("all", g.strftime("%Y%m%d")))
        except Exception:
            n = 0
        satirlar.append({"Tarih": g, "Gün": g.strftime("%d.%m.%Y (%a)"), "Maç": n})
    return pd.DataFrame(satirlar)


def teshis(lig_kodu="P1", tarih=None):
    """Teşhis: ESPN'den ne dönüyor? Ham durumu string olarak döndürür."""
    gun = pd.Timestamp(tarih) if tarih else pd.Timestamp(datetime.date.today())
    ymd = gun.strftime("%Y%m%d")
    slug = ESPN_SLUG.get(lig_kodu, lig_kodu)
    url = f"{ESPN_KOK}/{slug}/scoreboard"
    rapor = [f"İstek: {url}?dates={ymd}"]
    try:
        r = requests.get(url, params={"dates": ymd, "limit": 500}, headers=UA, timeout=TIMEOUT)
        rapor.append(f"HTTP durum: {r.status_code}")
        if r.status_code != 200:
            rapor.append(f"Yanıt (ilk 300 karakter): {r.text[:300]}")
            return "\n".join(rapor)
        veri = r.json()
        events = veri.get("events", [])
        rapor.append(f"Event sayısı: {len(events)}")
        ligler = veri.get("leagues", [])
        rapor.append(f"Lig bilgisi: {ligler[0].get('name') if ligler else 'YOK (boş)'}")
        if events:
            ilk = events[0]
            rapor.append(f"İlk maç: {ilk.get('name', '?')}")
            rapor.append(f"İlk maç tarihi: {ilk.get('date', '?')}")
            rapor.append(f"Durum: {ilk.get('status', {}).get('type', {}).get('state', '?')}")
        else:
            rapor.append("→ Bu tarihte bu ligde maç yok (ya da sezon dışı/veri yok)")
    except Exception as e:
        rapor.append(f"HATA: {type(e).__name__}: {e}")
    return "\n".join(rapor)
