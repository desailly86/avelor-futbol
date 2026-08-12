# -*- coding: utf-8 -*-
"""
futbol_kayit.py — Google Sheets kalıcı tahmin kaydı köprüsü
============================================================
Apps Script Web App ile konuşur. Tahminleri kaydeder (dondurulur),
oynanan maçların sonuçlarını eşleştirir, biriken market-bazlı isabeti okur.
Mimari: tahmin BİR KEZ yapılır → Sheet'e yazılır → maç oynanınca sonuç eşleşir
→ yüzde birikir. Baştan hesaplama YOK (hız). Kalıcı (uygulama kapansa da durur).
"""
import json
import datetime
import hashlib
import requests

TIMEOUT = 60


def _mac_id(lig, ev, dep, tarih):
    """Bir maç için benzersiz, tekrarlanabilir kimlik (aynı maç hep aynı id)."""
    ham = f"{lig}|{ev}|{dep}|{tarih}".lower().replace(" ", "")
    return hashlib.md5(ham.encode()).hexdigest()[:12]


def tahmin_kaydet(api_url, tahmin_listesi):
    """tahmin_listesi: [{lig, ev, dep, tarih, market, tahmin_yuzde}, ...]
    Her tahmine benzersiz id verilir; Sheet aynı id'yi tekrar yazmaz (dondurma)."""
    if not api_url:
        return {"hata": "API_URL yok"}
    kayitlar = []
    for t in tahmin_listesi:
        mid = _mac_id(t["lig"], t["ev"], t["dep"], t["tarih"])
        kayitlar.append({
            "id": f"{mid}_{t['market']}",  # maç+market benzersiz
            "tarih": str(t["tarih"]), "lig": t["lig"],
            "ev": t["ev"], "dep": t["dep"],
            "market": t["market"], "tahmin_yuzde": t["tahmin_yuzde"],
        })
    # Çok fazla kayıt tek istekte timeout'a yol açar → 150'lik parçalara böl
    toplam_eklenen = 0
    try:
        for bas in range(0, len(kayitlar), 150):
            parca = kayitlar[bas:bas + 150]
            r = requests.post(api_url, json={"islem": "tahmin_kaydet", "tahminler": parca},
                              timeout=TIMEOUT)
            sonuc = r.json()
            if "eklenen" in sonuc:
                toplam_eklenen += sonuc["eklenen"]
            elif "hata" in sonuc:
                return {"hata": sonuc["hata"], "kismi_eklenen": toplam_eklenen}
        return {"durum": "ok", "eklenen": toplam_eklenen}
    except Exception as e:
        return {"hata": str(e), "kismi_eklenen": toplam_eklenen}


def sonuc_guncelle(api_url, sonuc_sozlugu):
    """sonuc_sozlugu: {id: {sonuc: '1', tuttu: True}, ...}"""
    if not api_url:
        return {"hata": "API_URL yok"}
    try:
        r = requests.post(api_url, json={"islem": "sonuc_guncelle", "sonuclar": sonuc_sozlugu},
                          timeout=TIMEOUT)
        return r.json()
    except Exception as e:
        return {"hata": str(e)}


def kayitlari_oku(api_url):
    """Tüm tahmin kayıtlarını döndürür (liste)."""
    if not api_url:
        return {"hata": "API_URL yok"}
    try:
        r = requests.get(api_url, params={"islem": "oku"}, timeout=TIMEOUT)
        return r.json()
    except Exception as e:
        return {"hata": str(e)}


def ozet_oku(api_url):
    """Biriken market-bazlı isabet özetini döndürür (sonuçlanmış tahminlerden)."""
    if not api_url:
        return {"hata": "API_URL yok"}
    try:
        r = requests.get(api_url, params={"islem": "ozet"}, timeout=TIMEOUT)
        return r.json()
    except Exception as e:
        return {"hata": str(e)}


def baglanti_testi(api_url):
    """Bağlantı çalışıyor mu? Kısa, okunur bir rapor döndürür."""
    if not api_url:
        return "❌ API_URL tanımlı değil (Streamlit Secrets'a eklenmemiş)."
    try:
        r = requests.get(api_url, params={"islem": "oku"}, timeout=TIMEOUT)
        if r.status_code != 200:
            return f"❌ HTTP {r.status_code} — URL yanlış olabilir ya da dağıtım 'Anyone' değil."
        veri = r.json()
        if "kayitlar" in veri:
            return f"✅ Bağlantı çalışıyor! Sheet'te {len(veri['kayitlar'])} kayıt var."
        if "hata" in veri:
            return f"⚠️ Bağlandı ama Apps Script hata verdi: {veri['hata']}"
        return f"⚠️ Beklenm'dik yanıt: {str(veri)[:150]}"
    except Exception as e:
        return f"❌ Bağlanılamadı: {e}"
