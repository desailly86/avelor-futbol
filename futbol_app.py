# -*- coding: utf-8 -*-
"""
AVELOR FUTBOL — 38 ligde Poisson tabanlı maç analizi
Tema: beyaz zemin, siyah metin, Candara, gri 3B butonlar (AVELOR ailesi).
Veri: football-data.co.uk (ücretsiz, tarihsel oranlar dahil).
"""
import json
import datetime
import requests
import pandas as pd
import streamlit as st

from futbol_motoru import (guc_hesapla, mac_tahmin, value_hesapla,
                           form_ozeti, backtest, en_iyi_uc, MARKET_ETIKET)
from futbol_veri import TUM_LIGLER, ANA_LIGLER, lig_verisi_cek, fikstur_cek

st.set_page_config(page_title="AVELOR Futbol", page_icon="⚽",
                   layout="wide", initial_sidebar_state="expanded")
API_URL = st.secrets.get("API_URL", "")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Questrial&display=swap');
:root{ --murekkep:#111; --kursun:#6A6A6A; --cizgi:#DCDCDC;
       --gumus-acik:#F5F5F5; --gumus:#E2E2E2; --gumus-koyu:#BFBFBF; }
html, body, .stApp, [data-testid="stSidebar"]{
  font-family: Candara, "Questrial", "Gill Sans", "Segoe UI", Optima, sans-serif !important; }
.stApp{ background:#FFF; color:var(--murekkep); }
[data-testid="stSidebar"]{ background:#FAFAFA; border-right:1px solid var(--cizgi); }
h1,h2,h3{ color:var(--murekkep) !important; }
.stButton>button, .stDownloadButton>button{
  color:var(--murekkep); background:linear-gradient(180deg,var(--gumus-acik),var(--gumus));
  border:1px solid var(--gumus-koyu); border-radius:6px; font-weight:600;
  box-shadow:0 3px 0 var(--gumus-koyu), 0 4px 6px rgba(0,0,0,.08); transition:all .08s; }
.stButton>button:active{ transform:translateY(2px); box-shadow:0 1px 0 var(--gumus-koyu); }
.stButton>button[kind="primary"]{ color:#FFF;
  background:linear-gradient(180deg,#4B4B4B,#2C2C2C); border:1px solid #1E1E1E;
  box-shadow:0 3px 0 #1E1E1E, 0 4px 8px rgba(0,0,0,.18); }
.mac{ border:1px solid var(--cizgi); border-radius:8px; background:#FFF;
      padding:12px 16px; margin-bottom:10px; box-shadow:0 1px 3px rgba(0,0,0,.05); }
.mac-ust{ display:flex; justify-content:space-between; border-bottom:2px solid var(--murekkep);
          padding-bottom:6px; margin-bottom:8px; }
.olasilik{ display:grid; grid-template-columns:repeat(6,1fr); gap:8px; text-align:center; }
.etiket{ color:var(--kursun); font-size:11px; text-transform:uppercase; letter-spacing:.5px; }
.deger{ font-weight:700; font-size:16px; }
.value-var{ color:#0A7A0A; font-weight:700; }
.bar-kap{ background:var(--gumus-acik); border:1px solid var(--cizgi);
          border-radius:4px; height:12px; overflow:hidden; }
.bar-ic{ background:var(--murekkep); height:100%; }
</style>""", unsafe_allow_html=True)

for anahtar, deger in [("lig_df", None), ("guc", None), ("lig_kod", None),
                       ("karne", []), ("menu", "Program")]:
    if anahtar not in st.session_state:
        st.session_state[anahtar] = deger

with st.sidebar:
    st.markdown("## ⚽ AVELOR Futbol")
    st.caption("38 lig · Poisson gol modeli · dürüst backtest")
    lig_kod = st.selectbox("Lig", list(TUM_LIGLER.keys()),
                           format_func=lambda k: TUM_LIGLER[k],
                           index=list(TUM_LIGLER.keys()).index("T1"))
    sezon_sayisi = st.slider("Model kaç sezona baksın", 1, 5, 3)
    st.write("---")
    for ad, ikon in [("Program", "📡"), ("Takım Güçleri", "🔬"),
                     ("Elle Tahmin", "🎯"), ("Backtest", "🧪"), ("Karne", "📈")]:
        if st.button(f"{ikon} {ad}", use_container_width=True,
                     type="primary" if st.session_state["menu"] == ad else "secondary"):
            st.session_state["menu"] = ad
            st.rerun()
    st.write("---")
    st.caption("Hiçbir model kazanç garantisi vermez; bahis şirketi marjı her orana "
               "gömülüdür. Sorumlu oynayın.")

menu = st.session_state["menu"]
df = st.session_state["lig_df"]
guc = st.session_state["guc"]


def model_kur():
    with st.spinner(f"{TUM_LIGLER[lig_kod]} verisi indiriliyor ve model kuruluyor…"):
        try:
            veri = lig_verisi_cek(lig_kod, sezon_sayisi)
            if veri.empty:
                st.error("Veri indirilemedi — lig kodu için dosya bulunamadı ya da site erişilemez.")
                return
            st.session_state.update(lig_df=veri, guc=guc_hesapla(veri), lig_kod=lig_kod)
            oynanmis = veri.dropna(subset=["FTHG"])
            st.success(f"✅ {len(oynanmis)} maçla model kuruldu "
                       f"({oynanmis['Date'].min():%d.%m.%Y} → {oynanmis['Date'].max():%d.%m.%Y})")
        except Exception as e:
            st.error(f"Model kurulamadı: {e}")


def mac_karti(ev, dep, t, oranlar=None, tarih="", anahtar="", bazlar=None):
    oneriler = en_iyi_uc(t, bazlar)
    madalya = ["🥇", "🥈", "🥉"]
    oneri_html = "".join(
        f"<div><div class='etiket'>{madalya[i]} CESUR ÖNERİ</div>"
        f"<div class='deger'>{o['market']}</div>"
        f"<div class='etiket'>%{o['olasilik']} · lig tabanı %{o['baz']} · <b>kenar +{o['kenar']}</b></div></div>"
        for i, o in enumerate(oneriler)) or \
        "<div class='etiket'>Lig tabanından yeterince sapan iddia yok — zorlama öneri verilmez</div>"
    # Halkın ana çizgisi her kartta sabit: 2.5 Alt/Üst
    au_secim = "Üst" if t["ust25"] >= 50 else "Alt"
    au_p = t["ust25"] if au_secim == "Üst" else t["alt25"]
    au_baz = (bazlar or {}).get("ust25" if au_secim == "Üst" else "alt25", 50)
    oneri_html += (f"<div style='border-left:1px solid var(--cizgi);padding-left:8px'>"
                   f"<div class='etiket'>⚖️ 2.5 ÇİZGİSİ</div><div class='deger'>{au_secim} 2.5</div>"
                   f"<div class='etiket'>%{au_p} · taban %{au_baz}</div></div>")
    notlar = " · ".join(t.get("notlar", []))
    st.markdown(f"<div class='mac'><div class='mac-ust'><b>{ev} — {dep}</b>"
                f"<span class='etiket'>{tarih} · xG {t['lam_ev']}-{t['lam_dep']} · skor {t['skor']}"
                f"{' · ' + notlar if notlar else ''}</span></div>"
                f"<div class='olasilik' style='grid-template-columns:repeat(4,1fr)'>{oneri_html}</div></div>",
                unsafe_allow_html=True)
    with st.expander(f"Tüm marketler — {ev} vs {dep}"):
        satirlar = []
        for kod, etiket in MARKET_ETIKET.items():
            if kod not in t:
                continue
            satir = {"Market": etiket, "Model %": t[kod]}
            if oranlar and kod in oranlar and oranlar[kod] and oranlar[kod] > 1:
                v = value_hesapla(t[kod], oranlar[kod])
                satir["Oran"] = oranlar[kod]
                satir["Value"] = f"+%{v['value']} ✅" if v["oynanabilir"] else f"%{v['value']}"
            satirlar.append(satir)
        st.dataframe(pd.DataFrame(satirlar), hide_index=True, use_container_width=True)
        if "korner_beklenti" in t or "kart_beklenti" in t:
            st.caption(f"Beklentiler — korner: {t.get('korner_beklenti','—')} · kart: {t.get('kart_beklenti','—')} "
                       "(takımların ev/deplasman korner-kart geçmişinden)")
        skorlar = " · ".join(f"{s} (%{p})" for s, p in t.get("skorlar", []))
        st.caption(f"En olası skorlar: {skorlar}")


def eksik_paneli(ev, dep, anahtar):
    """Fark yaratan kriter: kilit eksikleri (sakat/cezalı) elle işaretle."""
    with st.expander(f"🩹 Eksikler / cezalılar — {ev} vs {dep} (isteğe bağlı ama fark burada)"):
        st.caption("Haber sitelerinden öğrendiğin kilit eksikleri işaretle; model gol "
                   "beklentilerini kaydırır. 'Kilit' = ilk 11'in önemli ismi; rotasyon oyuncusu sayma.")
        c1, c2 = st.columns(2)
        with c1:
            eh = st.slider(f"{ev}: kilit HÜCUM eksiği", 0, 3, 0, key=f"eh{anahtar}")
            es = st.slider(f"{ev}: kilit SAVUNMA eksiği", 0, 3, 0, key=f"es{anahtar}")
        with c2:
            dh = st.slider(f"{dep}: kilit HÜCUM eksiği", 0, 3, 0, key=f"dh{anahtar}")
            ds = st.slider(f"{dep}: kilit SAVUNMA eksiği", 0, 3, 0, key=f"ds{anahtar}")
    return {"ev_hucum": eh, "ev_savunma": es, "dep_hucum": dh, "dep_savunma": ds}


if menu == "Program":
    st.markdown("# 📡 Program & Tahmin")
    st.caption("1) Modeli kur → 2) Yaklaşan maçları getir. Ana liglerde güncel oranlar "
               "fikstürle birlikte gelir ve value otomatik işaretlenir.")
    if st.button("1️⃣ Lig verisini çek ve modeli kur", type="primary", use_container_width=True):
        model_kur()
    if guc is not None and st.session_state["lig_kod"] == lig_kod:
        if lig_kod in ANA_LIGLER:
            if st.button("2️⃣ Yaklaşan maçları getir (oranlı fikstür)", use_container_width=True):
                try:
                    fx = fikstur_cek(lig_kod)
                    if fx.empty:
                        st.warning("Bugünden ileri tarihli maç bulunamadı. Kaynak fikstür dosyası "
                                   "haftalık güncellenir; hafta sonu maçları genelde Salı-Çarşamba "
                                   "dosyaya düşer. O güne kadar **Elle Tahmin** ekranından istediğin "
                                   "maçı analiz edebilirsin.")
                    else:
                        st.session_state["fikstur"] = fx
                except Exception as e:
                    st.error(f"Fikstür çekilemedi: {e}")
            for fi, m in st.session_state.get("fikstur", pd.DataFrame()).iterrows():
                eksik = eksik_paneli(m["HomeTeam"], m["AwayTeam"], f"f{fi}")
                t = mac_tahmin(guc, m["HomeTeam"], m["AwayTeam"],
                               mac_tarihi=m.get("Date"), eksikler=eksik)
                if not t:
                    continue
                oranlar = {"1": m.get("B365H"), "X": m.get("B365D"), "2": m.get("B365A")}
                oranlar = {k: float(v) for k, v in oranlar.items() if pd.notna(v)}
                mac_karti(m["HomeTeam"], m["AwayTeam"], t, oranlar,
                          m["Date"].strftime("%d.%m.%Y") if pd.notna(m.get("Date")) else "", f"f{fi}",
                          bazlar=guc.get("bazlar"))
        else:
            st.info("Bu ek ligde oranlı fikstür servisi yok — **Elle Tahmin** ekranından "
                    "iki takımı seçip (istersen oranları da girip) analiz alabilirsin.")
    elif guc is not None:
        st.info("Lig değişti — yeni lig için modeli tekrar kurun.")

elif menu == "Takım Güçleri":
    st.markdown("# 🔬 Takım Güçleri")
    if guc is None:
        st.info("Önce **Program** ekranından modeli kurun.")
    else:
        satirlar = []
        for takim, g in guc["takimlar"].items():
            f = form_ozeti(df, takim)
            satirlar.append({"Takım": takim, "Hücum": round(g["hucum"], 2),
                             "Savunma (düşük iyi)": round(g["savunma"], 2),
                             "Maç": g["mac"], "Son 5": f["dizi"], "Son 5 Puan": f["puan"],
                             "Attığı/Yediği": f"{f['attigi']}/{f['yedigi']}"})
        st.dataframe(pd.DataFrame(satirlar).sort_values("Hücum", ascending=False),
                     use_container_width=True, hide_index=True, height=560)
        st.caption(f"Ev avantajı çarpanı: {guc['ev_carpan']:.2f} · lig gol ort.: {guc['lig_ort']:.2f} · "
                   "Değerler zaman-ağırlıklıdır (yeni maçlar daha etkili).")

elif menu == "Elle Tahmin":
    st.markdown("# 🎯 Elle Tahmin")
    if guc is None:
        st.info("Önce **Program** ekranından modeli kurun.")
    else:
        takimlar = sorted(guc["takimlar"].keys())
        c1, c2 = st.columns(2)
        ev = c1.selectbox("Ev sahibi", takimlar)
        dep = c2.selectbox("Deplasman", takimlar, index=min(1, len(takimlar) - 1))
        st.caption("İsteğe bağlı: bahis oranlarını gir, value hesaplansın (tjk/iddaa/di̇ğer).")
        o1, ox, o2 = st.columns(3)
        oranlar = {"1": o1.number_input("Oran 1", 1.0, 100.0, 1.0, 0.05),
                   "X": ox.number_input("Oran X", 1.0, 100.0, 1.0, 0.05),
                   "2": o2.number_input("Oran 2", 1.0, 100.0, 1.0, 0.05)}
        eksik = eksik_paneli(ev, dep, "elle")
        if st.button("Analiz et", type="primary"):
            if ev == dep:
                st.warning("İki farklı takım seçin.")
            else:
                t = mac_tahmin(guc, ev, dep, eksikler=eksik)
                mac_karti(ev, dep, t, {k: v for k, v in oranlar.items() if v > 1.01}, anahtar="elle",
                          bazlar=guc.get("bazlar"))
                fe, fd = form_ozeti(df, ev), form_ozeti(df, dep)
                st.caption(f"Form — {ev}: {fe['dizi']} ({fe['puan']} puan) · "
                           f"{dep}: {fd['dizi']} ({fd['puan']} puan)")
                st.session_state["karne"].append({
                    "tarih": datetime.date.today().isoformat(), "lig": lig_kod,
                    "mac": f"{ev}-{dep}", "secim": max(("1", "X", "2"), key=lambda s: t[s]),
                    "olasilik": max(t["1"], t["X"], t["2"])})

elif menu == "Backtest":
    st.markdown("# 🧪 Backtest — Dürüst Sınav")
    st.caption("Her maç, yalnızca ondan ÖNCE oynanmış maçlarla kurulan modelle tahmin edilir "
               "(geleceğe bakma yok). Piyasa favorisi kıyası ve value stratejisinin geçmiş "
               "ROI'si birlikte raporlanır. Value ROI genelde sıfır civarı ya da eksidir — "
               "pozitifse bile geçmişin ölçümüdür, gelecek garantisi değildir.")
    if df is None:
        st.info("Önce **Program** ekranından modeli kurun.")
    elif st.button("Backtest'i çalıştır (birkaç dakika sürebilir)", type="primary"):
        with st.spinner("Kronolojik test koşuyor…"):
            oynanmis = df.dropna(subset=["FTHG"]).reset_index(drop=True)
            rapor = backtest(oynanmis.tail(600).reset_index(drop=True))
        c1, c2, c3 = st.columns(3)
        c1.metric("Test maçı", rapor["mac"])
        c2.metric("Model 1X2 isabeti", f"%{rapor['model_1x2_%']}")
        c3.metric("Piyasa favorisi isabeti", f"%{rapor['piyasa_1x2_%']}")
        c4, c5, c6 = st.columns(3)
        c4.metric("🥇🥈🥉 'En iyi 3' isabeti", f"%{rapor['en_iyi3_isabet_%']}",
                  help=f"{rapor['en_iyi3_oneri']} öneri test edildi")
        c5.metric("2.5 A/Ü isabeti", f"%{rapor['au25_%']}")
        c6.metric("KG isabeti", f"%{rapor['kg_%']}")
        c7, c8 = st.columns(2)
        c7.metric("Value bahis sayısı", rapor["value_bahis"])
        c8.metric("Value stratejisi ROI", f"%{rapor['value_roi_%']}")
        if rapor.get("market_kirilim"):
            st.markdown("### Öneri isabetinin market kırılımı")
            st.caption("Hangi market türüne güvenilir, hangisinden uzak durulur — kanıtı bu tablo. "
                       "İsabeti düşük çıkan marketleri birlikte budarız.")
            st.dataframe(pd.DataFrame([
                {"Market": m, "Öneri sayısı": v["oneri"], "İsabet %": v["isabet_%"]}
                for m, v in rapor["market_kirilim"].items()]),
                hide_index=True, use_container_width=True)
        st.caption(f"Ortalama log-kayıp: {rapor['ort_log_kayip']} (düşük iyi). "
                   "Model piyasaya yaklaşıyorsa iyi kalibre demektir; geçmek nadirdir.")

elif menu == "Karne":
    st.markdown("# 📈 Karne")
    if not st.session_state["karne"]:
        st.info("Elle Tahmin ekranından analiz yaptıkça seçimler burada birikir; sonuçları "
                "işaretleyip isabetinizi takip edebilirsiniz.")
    else:
        k = pd.DataFrame(st.session_state["karne"])
        st.dataframe(k, use_container_width=True, hide_index=True)
        if API_URL and st.button("Karneyi buluta kaydet"):
            try:
                requests.post(API_URL, json={"Tarih": datetime.date.today().isoformat(),
                                             "Kosu_No": "FUTBOL_KARNE", "Gelen_At": "futbol",
                                             "Detay": json.dumps(st.session_state["karne"])},
                              timeout=10)
                st.success("Kaydedildi.")
            except requests.RequestException as e:
                st.warning(f"Buluta yazılamadı: {e}")
