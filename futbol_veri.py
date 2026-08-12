# -*- coding: utf-8 -*-
"""
futbol_veri.py — AVELOR Futbol veri katmanı (football-data.co.uk)
==================================================================
Kaynak tamamen ücretsizdir ve tarihsel BAHİS ORANLARINI da içerir.
- Ana ligler: sezon dosyaları https://www.football-data.co.uk/mmz4281/{sezon}/{kod}.csv
- Ek ligler: tek dosya https://www.football-data.co.uk/new/{kod}.csv
- Yaklaşan maçlar (oranlı): https://www.football-data.co.uk/fixtures.csv (ana ligler)
DÜRÜSTLÜK: Geliştirme ortamında dış ağ kapalıydı; adres kalıpları bilinen
resmi kalıplardır ama canlı ilk temas sizin sunucunuzda olacak. Ek liglerde
fixtures.csv kapsamı yoktur → oranlar elle girilir.
"""
from __future__ import annotations
import io
import datetime
import requests
import pandas as pd

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
TIMEOUT = 25

ANA_LIGLER = {  # kod → ad (sezon dosyalı, fixtures.csv kapsamında)
    "T1": "🇹🇷 Türkiye Süper Lig",
    "E0": "🏴 İngiltere Premier League", "E1": "🏴 İngiltere Championship",
    "E2": "🏴 İngiltere League One", "E3": "🏴 İngiltere League Two",
    "EC": "🏴 İngiltere Conference",
    "SP1": "🇪🇸 İspanya La Liga", "SP2": "🇪🇸 İspanya Segunda",
    "D1": "🇩🇪 Almanya Bundesliga", "D2": "🇩🇪 Almanya 2. Bundesliga",
    "I1": "🇮🇹 İtalya Serie A", "I2": "🇮🇹 İtalya Serie B",
    "F1": "🇫🇷 Fransa Ligue 1", "F2": "🇫🇷 Fransa Ligue 2",
    "N1": "🇳🇱 Hollanda Eredivisie", "P1": "🇵🇹 Portekiz Liga",
    "B1": "🇧🇪 Belçika Pro League", "G1": "🇬🇷 Yunanistan Süper Lig",
    "SC0": "🏴 İskoçya Premiership", "SC1": "🏴 İskoçya Championship",
    "SC2": "🏴 İskoçya League One", "SC3": "🏴 İskoçya League Two",
}
EK_LIGLER = {  # kod → ad (tek dosya, tüm sezonlar birlikte)
    "ARG": "🇦🇷 Arjantin", "AUT": "🇦🇹 Avusturya", "BRA": "🇧🇷 Brezilya",
    "CHN": "🇨🇳 Çin", "DNK": "🇩🇰 Danimarka", "FIN": "🇫🇮 Finlandiya",
    "IRL": "🇮🇪 İrlanda", "JPN": "🇯🇵 Japonya", "MEX": "🇲🇽 Meksika",
    "NOR": "🇳🇴 Norveç", "POL": "🇵🇱 Polonya", "ROU": "🇷🇴 Romanya",
    "RUS": "🇷🇺 Rusya", "SWE": "🇸🇪 İsveç", "SWZ": "🇨🇭 İsviçre", "USA": "🇺🇸 ABD MLS",
}
TUM_LIGLER = {**ANA_LIGLER, **EK_LIGLER}


def _sezon_kodlari(kac: int = 3) -> list[str]:
    """Bugüne göre son N sezon kodu (ör. Temmuz 2026 → ['2627','2526','2425'][:N]).
    Avrupa sezonu Ağustos'ta başlar; Temmuz'da hâlâ '2526' en günceldir."""
    simdi = datetime.date.today()
    yil = simdi.year if simdi.month >= 8 else simdi.year - 1
    return [f"{str(y)[2:]}{str(y+1)[2:]}" for y in range(yil, yil - kac, -1)]


def _csv_oku(icerik: bytes) -> pd.DataFrame:
    for enc in ("utf-8-sig", "latin-1"):
        try:
            df = pd.read_csv(io.BytesIO(icerik), encoding=enc, on_bad_lines="skip")
            if "HomeTeam" in df.columns or "Home" in df.columns:
                return df
        except Exception:
            continue
    return pd.DataFrame()


def sezon_etiketi(tarih) -> str:
    """Avrupa sezonu Ağustos'ta başlar: 12.03.2026 → '2025/26'."""
    t = pd.Timestamp(tarih)
    yil = t.year if t.month >= 7 else t.year - 1
    return f"{yil}/{str(yil + 1)[2:]}"


def _standartlastir(df: pd.DataFrame) -> pd.DataFrame:
    """Ana ve ek lig dosyalarını ortak kolon adlarına getirir."""
    d = df.rename(columns={"Home": "HomeTeam", "Away": "AwayTeam",
                           "HG": "FTHG", "AG": "FTAG",
                           "PH": "B365H", "PD": "B365D", "PA": "B365A"})
    if "Date" in d.columns:
        d["Date"] = pd.to_datetime(d["Date"], dayfirst=True, errors="coerce")
    if "Date" in d.columns:
        d["Sezon"] = d["Date"].map(lambda x: sezon_etiketi(x) if pd.notna(x) else "")
    gerekli = ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "Sezon"]
    d = d[[c for c in d.columns if c in gerekli + ["B365H", "B365D", "B365A", "Div", "Time",
                                                    "HST", "AST", "HC", "AC", "HY", "AY",
                                                    "HR", "AR", "HTHG", "HTAG"]]]
    return d.dropna(subset=["Date", "HomeTeam", "AwayTeam"])


def lig_verisi_cek(kod: str, sezon_sayisi: int = 3) -> pd.DataFrame:
    """Seçilen ligin son sezonlarını indirir (oynanmış maçlar + oranlar)."""
    parcalar = []
    if kod in ANA_LIGLER:
        for sezon in _sezon_kodlari(sezon_sayisi):
            url = f"https://www.football-data.co.uk/mmz4281/{sezon}/{kod}.csv"
            try:
                resp = requests.get(url, headers=UA, timeout=TIMEOUT)
                if resp.status_code == 200 and len(resp.content) > 500:
                    parcalar.append(_standartlastir(_csv_oku(resp.content)))
            except requests.RequestException:
                continue
    else:
        url = f"https://www.football-data.co.uk/new/{kod}.csv"
        resp = requests.get(url, headers=UA, timeout=TIMEOUT)
        resp.raise_for_status()
        d = _standartlastir(_csv_oku(resp.content))
        if not d.empty:  # ek lig dosyası tüm tarihçedir; son ~3 yıla kırp
            esik = d["Date"].max() - pd.Timedelta(days=365 * sezon_sayisi)
            parcalar.append(d[d["Date"] >= esik])
    if not parcalar:
        return pd.DataFrame()
    return pd.concat(parcalar, ignore_index=True).sort_values("Date").reset_index(drop=True)


def fikstur_cek(kod: str | None = None, sadece_gelecek: bool = True) -> pd.DataFrame:
    """Yaklaşan maçlar + güncel oranlar (yalnızca ana ligler).
    Kaynak dosya haftalık güncellenir ve haftanın OYNANMIŞ maçlarını da içerir;
    bu yüzden varsayılan olarak bugünden önceki maçlar elenir."""
    resp = requests.get("https://www.football-data.co.uk/fixtures.csv",
                        headers=UA, timeout=TIMEOUT)
    resp.raise_for_status()
    d = _standartlastir(_csv_oku(resp.content))
    ham = _csv_oku(resp.content)
    if "Div" in ham.columns:
        d["Div"] = ham["Div"]
        if kod:
            d = d[d["Div"] == kod]
    if "Time" in d.columns:
        d["Saat_TSI"] = d["Time"].map(_saat_tsi)
    if sadece_gelecek and "Date" in d.columns:
        bugun = pd.Timestamp(datetime.date.today())
        d = d[d["Date"] >= bugun]
    return d.sort_values("Date").reset_index(drop=True)


# ---------------------------------------------------------------------------
# GÜNÜN BÜLTENİ (TSİ) — tüm liglerin bugünkü maçları, saate göre sıralı
# ---------------------------------------------------------------------------
TSI_FARK_SAAT = 2  # kaynak saatleri Londra (BST) verir; TSİ = +2 (yaz), kışın +3


def _saat_tsi(saat_metni) -> str:
    """'19:45' (kaynak saati) → TSİ karşılığı."""
    try:
        s, d = str(saat_metni).strip().split(":")[:2]
        toplam = (int(s) + TSI_FARK_SAAT) % 24
        return f"{toplam:02d}:{int(d):02d}"
    except (ValueError, AttributeError):
        return ""


def gunun_bulteni(sadece_kalan: bool = True, tsi_simdi: datetime.datetime | None = None,
                  secili_gun=None) -> pd.DataFrame:
    """Seçili günün (varsayılan bugün) TÜM lig maçları, TSİ saatine göre sıralı.
    sadece_kalan=True → şu andan sonra başlayacak maçlar (yalnızca bugün için anlamlı).
    secili_gun verilirse o günün maçları gösterilir (takvimden seçim)."""
    d = fikstur_cek(kod=None, sadece_gelecek=False)
    if d.empty or "Date" not in d.columns:
        return d
    hedef = pd.Timestamp(secili_gun) if secili_gun else pd.Timestamp(datetime.date.today())
    bugun = pd.Timestamp(datetime.date.today())
    d = d[d["Date"] == hedef].copy()
    if d.empty:
        return d
    if "Saat_TSI" not in d.columns and "Time" in d.columns:
        d["Saat_TSI"] = d["Time"].map(_saat_tsi)
    d["Lig"] = d.get("Div", "").map(lambda k: TUM_LIGLER.get(k, k))
    if sadece_kalan and hedef == bugun and "Saat_TSI" in d.columns:
        simdi = (tsi_simdi or datetime.datetime.utcnow() + datetime.timedelta(hours=3)).strftime("%H:%M")
        d = d[d["Saat_TSI"].fillna("") >= simdi]
    sirala = "Saat_TSI" if "Saat_TSI" in d.columns else "Date"
    return d.sort_values(sirala).reset_index(drop=True)


def fikstur_gunleri(ileri_gun: int = 14) -> pd.DataFrame:
    """Önümüzdeki N günde hangi tarihlerde kaç maç var — takvim için özet."""
    d = fikstur_cek(kod=None, sadece_gelecek=True)
    if d.empty or "Date" not in d.columns:
        return pd.DataFrame(columns=["Date", "mac_sayisi"])
    bugun = pd.Timestamp(datetime.date.today())
    d = d[d["Date"] <= bugun + pd.Timedelta(days=ileri_gun)]
    return d.groupby("Date").size().reset_index(name="mac_sayisi")
