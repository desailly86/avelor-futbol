# -*- coding: utf-8 -*-
"""
AVELOR FUTBOL — Puan-Ağırlık Motoru (tek sezon 2026/27)
========================================================
Poisson yok. Kriter puanı + öğrenilen ağırlık üstüne kurulu.
Menü: st.radio ile (otomatik kapanma sorunu çözüldü).
Ekranlar: Dashboard · Günün Bülteni (takvimli) · Tahmin · Puan Durumu ·
          Bahis Oranları · Kriter Karnesi · Tahmin
"""
import datetime
import numpy as np
import pandas as pd
import streamlit as st

from futbol_veri import (TUM_LIGLER, ANA_LIGLER, lig_verisi_cek, fikstur_cek,
                         sezon_etiketi)
from futbol_tablo import puan_durumu, son_mac_sonuclari
from futbol_bulten import gunun_maclari, hafta_ozeti, ESPN_SLUG, teshis
from futbol_kriter import (takim_defteri, hakem_defteri, mac_tahmin_puan,
                           en_iyi_uc, agirlik_sozlugu, agirlik_durumu, MARKET_ETIKET,
                           kriter_karne, KRITER_TANIM, tahmin_isabeti)

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
.stButton>button{ color:var(--murekkep);
  background:linear-gradient(180deg,var(--gumus-acik),var(--gumus));
  border:1px solid var(--gumus-koyu); border-radius:6px; font-weight:600;
  box-shadow:0 3px 0 var(--gumus-koyu), 0 4px 6px rgba(0,0,0,.08); }
.stButton>button:active{ transform:translateY(2px); box-shadow:0 1px 0 var(--gumus-koyu); }
.stButton>button[kind="primary"]{ color:#FFF;
  background:linear-gradient(180deg,#4B4B4B,#2C2C2C); border:1px solid #1E1E1E;
  box-shadow:0 3px 0 #1E1E1E, 0 4px 8px rgba(0,0,0,.18); }
.mac{ border:1px solid var(--cizgi); border-radius:8px; background:#FFF;
      padding:12px 16px; margin-bottom:10px; box-shadow:0 1px 3px rgba(0,0,0,.05); }
.mac-ust{ display:flex; justify-content:space-between; border-bottom:2px solid var(--murekkep);
          padding-bottom:6px; margin-bottom:8px; }
.olasilik{ display:grid; gap:8px; text-align:center; }
.etiket{ color:var(--kursun); font-size:11px; text-transform:uppercase; letter-spacing:.5px; }
.deger{ font-weight:700; font-size:16px; }
.kutu{ border:1px solid var(--cizgi); border-radius:10px; padding:16px 20px; background:#FFF;
       box-shadow:0 1px 3px rgba(0,0,0,.05); text-align:center; }
.kutu .buyuk{ font-size:30px; font-weight:800; }
</style>""", unsafe_allow_html=True)

for anahtar, deger in [("lig_df", None), ("agirliklar", {}), ("lig_kod", None),
                       ("karne", [])]:
    if anahtar not in st.session_state:
        st.session_state[anahtar] = deger

with st.sidebar:
    st.markdown("## ⚽ AVELOR Futbol")
    st.caption("Puan-ağırlık motoru · tek sezon 2026/27")
    lig_kod = st.selectbox("Lig", list(TUM_LIGLER.keys()),
                           format_func=lambda k: TUM_LIGLER[k],
                           index=list(TUM_LIGLER.keys()).index("T1"))
    st.write("---")
    # st.radio: seçim kalıcı, menü kapanmaz (rerun sorunu çözüldü)
    menu = st.radio("Menü", ["Dashboard", "Günün Bülteni", "Tahmin", "Puan Durumu",
                             "Bahis Oranları", "Kriter Karnesi", "Tahmin Karnesi"],
                    label_visibility="collapsed")
    st.write("---")
    st.caption("Hiçbir model kazanç garantisi vermez; bahis şirketi marjı her orana gömülüdür. "
               "Sezon başında veri az → tahminler zayıf, bu normaldir.")

@st.cache_data(show_spinner=False)
def _isabet_hesapla(kod, mac_sayisi):
    # kod+maç sayısı anahtar; veri değişince yeniden hesaplar
    return tahmin_isabeti(st.session_state["lig_df"])

df = st.session_state["lig_df"]
W = st.session_state["agirliklar"]


def model_kur():
    with st.spinner(f"{TUM_LIGLER[lig_kod]} verisi indiriliyor ve ağırlıklar hesaplanıyor…"):
        try:
            veri = lig_verisi_cek(lig_kod, 1)
            if veri.empty:
                st.error("Veri indirilemedi — lig dosyası bulunamadı ya da site erişilemez.")
                return
            oynanmis = veri.dropna(subset=["FTHG"])
            w = agirlik_sozlugu(veri)
            st.session_state.update(lig_df=veri, agirliklar=w, lig_kod=lig_kod)
            st.success(f"✅ {len(oynanmis)} maç yüklendi "
                       f"({oynanmis['Date'].min():%d.%m.%Y} → {oynanmis['Date'].max():%d.%m.%Y})")
            durum = agirlik_durumu(veri)
            if len(oynanmis) == 0:
                st.warning("📭 Bu ligde bu sezon **henüz hiç maç oynanmamış**. Tek sezon kuralı "
                           "gereği sistem yalnızca bu sezonun maçlarından öğrenir — ilk maçlar "
                           "oynanana kadar tahmin ve ağırlık üretilemez. Bu bir hata değil, "
                           "sezon başının doğal hali. İlk hafta oynandıktan sonra tekrar çekin; "
                           "sistem uyanmaya başlayacak.")
            elif durum["durum"] == "Bekliyor":
                st.warning(f"⚠️ {durum['aciklama']} Şimdilik tüm kriterler nötr (1.0). "
                           "Birkaç maç daha oynanınca ağırlıklar kendiliğinden devreye girer.")
            else:
                st.info(f"📊 Ağırlıklar oynanmış maçlardan hesaplandı — **{durum['kademe']}** olgunluk. "
                        f"{durum['aciklama']} Kriter Karnesi'nde detayları görebilirsin.")
        except Exception as e:
            st.error(f"Yüklenemedi: {e}")


def _tahmin(ev, dep, mac_tarihi=None, hakem=None):
    ref = pd.Timestamp(mac_tarihi) if mac_tarihi else df["Date"].max() + pd.Timedelta(days=1)
    return mac_tahmin_puan(ev, dep, takim_defteri(df, ref), hakem_defteri(df, ref),
                           agirliklar=W, hakem=hakem, mac_tarihi=mac_tarihi)


def mac_karti(ev, dep, t, tarih=""):
    if not t:
        st.markdown(f"<div class='mac'><b>{ev} — {dep}</b><br>"
                    f"<span class='etiket'>Yeterli veri yok</span></div>", unsafe_allow_html=True)
        return
    oneriler = en_iyi_uc(t)
    madalya = ["🥇", "🥈", "🥉"]
    if oneriler:
        oneri_html = "".join(
            f"<div><div class='etiket'>{madalya[i]} ÖNERİ</div>"
            f"<div class='deger'>{o['market']}</div>"
            f"<div class='etiket'>%{o['olasilik']} · kenar +{o['kenar']}</div></div>"
            for i, o in enumerate(oneriler))
    else:
        oneri_html = "<div class='etiket'>Lig tabanından yeterince sapan iddia yok</div>"
    guven_not = ("<span style='background:#B00;color:#fff;padding:1px 8px;border-radius:4px;font-size:11px'>⚠ AZ VERİ</span> "
                 if t.get("_guven") == "düşük" else "")
    st.markdown(f"<div class='mac'><div class='mac-ust'><b>{guven_not}{ev} — {dep}</b>"
                f"<span class='etiket'>{tarih} · veri: {t.get('_ev_mac','?')}/{t.get('_dep_mac','?')} maç</span></div>"
                f"<div class='olasilik' style='grid-template-columns:repeat(3,1fr)'>{oneri_html}</div></div>",
                unsafe_allow_html=True)
    with st.expander(f"Tüm marketler — {ev} vs {dep}"):
        satirlar = [{"Market": MARKET_ETIKET[k], "Model %": t[k]}
                    for k in MARKET_ETIKET if k in t and isinstance(t[k], (int, float))]
        st.dataframe(pd.DataFrame(satirlar), hide_index=True, use_container_width=True)


# ============================================================ DASHBOARD
if menu == "Dashboard":
    st.markdown("# 🏠 Dashboard")
    simdi = datetime.datetime.utcnow() + datetime.timedelta(hours=3)
    st.caption(f"AVELOR Futbol · TSİ {simdi:%H:%M} · {simdi:%d.%m.%Y} · Sezon {sezon_etiketi(simdi)}")
    c1, c2, c3, c4 = st.columns(4)
    oyn = len(df.dropna(subset=["FTHG"])) if df is not None else 0
    c1.markdown(f"<div class='kutu'><div class='etiket'>Seçili Lig</div>"
                f"<div class='buyuk' style='font-size:20px'>{TUM_LIGLER[lig_kod]}</div></div>", unsafe_allow_html=True)
    c2.markdown(f"<div class='kutu'><div class='etiket'>Yüklü Maç</div>"
                f"<div class='buyuk'>{oyn}</div></div>", unsafe_allow_html=True)
    c3.markdown(f"<div class='kutu'><div class='etiket'>Kriter Havuzu</div>"
                f"<div class='buyuk'>{len(KRITER_TANIM)}</div></div>", unsafe_allow_html=True)
    genel_isabet = None
    if df is not None and len(df.dropna(subset=["FTHG"])) >= 15:
        try:
            rap = _isabet_hesapla(st.session_state["lig_kod"], len(df.dropna(subset=["FTHG"])))
            genel_isabet = rap.get("_genel")
        except Exception:
            pass
    if genel_isabet and genel_isabet["deneme"] > 0:
        c4.markdown(f"<div class='kutu'><div class='etiket'>Tahmin İsabeti</div>"
                    f"<div class='buyuk'>%{genel_isabet['yuzde']}</div>"
                    f"<div class='etiket'>{genel_isabet['dogru']}/{genel_isabet['deneme']} tahmin</div></div>",
                    unsafe_allow_html=True)
    else:
        c4.markdown(f"<div class='kutu'><div class='etiket'>Tahmin İsabeti</div>"
                    f"<div class='buyuk' style='font-size:18px'>Veri az</div></div>", unsafe_allow_html=True)
    st.write("")
    if df is None:
        st.info("Başlamak için **Tahmin** ekranından bir lig seçip veriyi çekin. "
                "Ardından burada özet, aşağıda günün maçları görünür.")
    else:
        sol, sag = st.columns(2)
        with sol:
            st.markdown("### 📊 Puan durumu (ilk 5)")
            pd_tablo = puan_durumu(df, "genel").head(5)
            st.dataframe(pd_tablo[["Sıra", "Takım", "O", "P"]], hide_index=True, use_container_width=True)
        with sag:
            st.markdown("### 🔬 Öne çıkan kriterler")
            if W:
                en_iyi = sorted(W.items(), key=lambda x: -x[1])[:5]
                ad = {k[0]: k[1] for k in KRITER_TANIM}
                st.dataframe(pd.DataFrame([{"Kriter": ad.get(k, k), "Ağırlık": v} for k, v in en_iyi]),
                             hide_index=True, use_container_width=True)
            else:
                st.caption("Ağırlıklar henüz hesaplanmadı (veri az).")
    st.write("")
    st.markdown("### 🗓️ Bugünün maçları")
    if st.button("Bugünün programını getir"):
        try:
            st.session_state["dash_bulten"] = gunun_maclari(tarih=simdi.date())
        except Exception as e:
            st.error(f"Çekilemedi: {e}")
    bd = st.session_state.get("dash_bulten")
    if bd is not None and not bd.empty:
        for _, m in bd.head(15).iterrows():
            skor = m["Skor"]
            orta = f" <b style='color:#B00'>{skor}</b> " if skor else " — "
            st.markdown(f"<div class='mac' style='padding:6px 14px'><b>{m['Saat']}</b> "
                        f"&nbsp; {m['Ev']}{orta}{m['Dep']}"
                        f"<span class='etiket'> &nbsp; {m['Lig']}</span></div>", unsafe_allow_html=True)
    elif bd is not None:
        st.info("Bugün maç yok ya da kaynak yanıt vermedi.")

# ============================================================ GÜNÜN BÜLTENİ (takvimli)
elif menu == "Günün Bülteni":
    st.markdown("# 🗓️ Maç Bülteni")
    simdi = datetime.datetime.utcnow() + datetime.timedelta(hours=3)
    st.caption(f"TSİ {simdi:%H:%M} · Canlı maç programı (ESPN). Tüm dünyanın gördüğü fikstür — "
               "tarih seç, ligi seç, maçları gör. Oynanan maçlarda skor ve 🔴 CANLI durumu görünür.")

    c1, c2, c3 = st.columns([1, 1, 1])
    secili_gun = c1.date_input("Tarih", value=simdi.date(),
                               min_value=simdi.date() - datetime.timedelta(days=30),
                               max_value=simdi.date() + datetime.timedelta(days=30),
                               format="DD.MM.YYYY")
    lig_secim = c2.selectbox("Lig", ["Tüm ligler"] + list(TUM_LIGLER.keys()),
                             format_func=lambda k: "🌍 Tüm ligler" if k == "Tüm ligler" else TUM_LIGLER[k])
    c3.write(""); c3.write("")
    getir = c3.button("🗓️ Maçları getir", type="primary", use_container_width=True)

    if getir:
        with st.spinner("Maç programı çekiliyor (ESPN)…"):
            try:
                kod = None if lig_secim == "Tüm ligler" else lig_secim
                st.session_state["espn_bulten"] = gunun_maclari(tarih=secili_gun, lig_kodu=kod)
                st.session_state["espn_gun"] = secili_gun
            except Exception as e:
                st.error(f"Maçlar çekilemedi: {e}")

    b = st.session_state.get("espn_bulten")
    if b is not None:
        g = st.session_state.get("espn_gun", secili_gun)
        if b.empty:
            st.info(f"**{g:%d.%m.%Y}** için maç bulunamadı. O gün seçili ligde/liglerde maç "
                    "olmayabilir. Farklı bir tarih ya da 'Tüm ligler' deneyin.")
        else:
            st.markdown(f"### {g:%d.%m.%Y} — {len(b)} maç")
            # Lige göre grupla
            for lig in b["Lig"].unique():
                grup = b[b["Lig"] == lig]
                st.markdown(f"**{lig}**")
                for _, m in grup.iterrows():
                    skor = m["Skor"]
                    orta = f" <b style='color:#B00'>{skor}</b> " if skor else " — "
                    durum = f" <span class='etiket'>{m['Durum']}</span>" if m['Durum'] in ("🔴 CANLI", "bitti") else ""
                    st.markdown(f"<div class='mac' style='padding:6px 14px'>"
                                f"<b>{m['Saat']}</b> &nbsp; {m['Ev']}{orta}{m['Dep']}{durum}</div>",
                                unsafe_allow_html=True)
    else:
        st.info("Yukarıdan tarih ve lig seçip **Maçları getir**'e bas. Varsayılan: bugün, tüm ligler.")

    with st.expander("🔧 Teşhis (maç gelmiyorsa buraya bak)"):
        st.caption("ESPN'den tam olarak ne döndüğünü gösterir — sorunu birlikte görelim.")
        tc1, tc2 = st.columns(2)
        teshis_lig = tc1.selectbox("Test ligi", list(TUM_LIGLER.keys()),
                                   format_func=lambda k: TUM_LIGLER[k], key="teshis_lig")
        teshis_gun = tc2.date_input("Test tarihi", value=simdi.date(), key="teshis_gun",
                                    format="DD.MM.YYYY")
        if st.button("🔧 ESPN'i test et"):
            with st.spinner("ESPN sorgulanıyor…"):
                st.code(teshis(teshis_lig, teshis_gun))

elif menu == "Puan Durumu":
    st.markdown("# 📊 Puan Durumu")
    st.caption("2026/27 — genel, iç saha, deplasman. Tek sezon.")
    if df is None:
        st.info("Önce **Tahmin** ekranından ligi seçip veriyi çekin.")
    else:
        s1, s2, s3, s4 = st.tabs(["🏆 Genel", "🏠 İç Saha", "✈️ Deplasman", "📅 Son Maçlar"])
        with s1:
            st.dataframe(puan_durumu(df, "genel"), hide_index=True, use_container_width=True, height=560)
        with s2:
            st.dataframe(puan_durumu(df, "ic"), hide_index=True, use_container_width=True, height=560)
        with s3:
            st.dataframe(puan_durumu(df, "dis"), hide_index=True, use_container_width=True, height=560)
        with s4:
            sonuc = son_mac_sonuclari(df, gun=21)
            if not sonuc.empty:
                st.dataframe(sonuc, hide_index=True, use_container_width=True, height=560)
            else:
                st.info("Son 3 haftada maç yok.")

# ============================================================ BAHİS ORANLARI
elif menu == "Bahis Oranları":
    st.markdown("# 💱 Bahis Oranları")
    st.caption("15-16 firma ortalaması — **bizim tahminimiz DEĞİL**, piyasa oranı. 1X2 + Alt/Üst 2.5.")
    if st.session_state.get("lig_kod") != lig_kod or df is None:
        st.info("Önce **Tahmin** ekranından ligi seçip veriyi çekin.")
    else:
        if st.button("💱 Yaklaşan maçların oranlarını getir", type="primary"):
            try:
                st.session_state["oran_fikstur"] = fikstur_cek(lig_kod)
            except Exception as e:
                st.error(f"Oranlar çekilemedi: {e}")
        fx = st.session_state.get("oran_fikstur", pd.DataFrame())
        if not fx.empty:
            import re as _re
            satirlar = []
            for _, m in fx.iterrows():
                h = [m[c] for c in fx.columns if _re.search(r'[A-Za-z]+H$', str(c)) and pd.notna(m.get(c))]
                dd = [m[c] for c in fx.columns if _re.search(r'[A-Za-z]+D$', str(c)) and pd.notna(m.get(c))]
                a = [m[c] for c in fx.columns if _re.search(r'[A-Za-z]+A$', str(c)) and pd.notna(m.get(c))]
                satirlar.append({"Tarih": m["Date"].strftime("%d.%m") if pd.notna(m.get("Date")) else "",
                                 "Ev": m["HomeTeam"], "Dep": m["AwayTeam"],
                                 "1 (ort)": round(float(np.mean(h)), 2) if h else "-",
                                 "X (ort)": round(float(np.mean(dd)), 2) if dd else "-",
                                 "2 (ort)": round(float(np.mean(a)), 2) if a else "-"})
            st.dataframe(pd.DataFrame(satirlar), hide_index=True, use_container_width=True)
        else:
            st.info("Yaklaşan maç bulunamadı.")

# ============================================================ KRİTER KARNESİ
elif menu == "Kriter Karnesi":
    st.markdown("# 🔬 Kriter Karnesi")
    st.caption("21 kriterin oynanan maç sonuçlarıyla ne kadar tuttuğu. Her kriter kendi ALANINDA "
               "test edilir. Kriterler ATILMAZ — güçlülerin ağırlığı artar. Bu sezon = test sezonu.")
    if df is None:
        st.info("Önce **Tahmin** ekranından ligi seçip veriyi çekin.")
    else:
        oynanmis = df.dropna(subset=["FTHG"])
        st.metric("Değerlendirmeye giren maç", len(oynanmis))
        if len(oynanmis) < 20:
            st.warning(f"⚠️ Sadece {len(oynanmis)} maç. Kriter güçleri GÜVENİLMEZ (anlamlı için 100+).")
        if st.button("🔬 Kriterleri değerlendir", type="primary"):
            with st.spinner("Her maçta 21 kriter sınanıyor…"):
                karne = kriter_karne(df)
            st.dataframe(karne, hide_index=True, use_container_width=True, height=760)
            st.caption("Tutma %: kriterin kendi alanında doğru çıkma oranı (%50=şans). "
                       "İşe yaramayanlar atılmaz — düşük ağırlıkla kalır.")

# ============================================================ TAHMİN (elle)
elif menu == "Tahmin":
    st.markdown("# 🎯 Tahmin")
    st.caption("Ligi seç → o ligin verisini çek → yaklaşan haftanın maçları tahminleriyle gelsin. "
               "Alttan istersen iki takımı elle de seçebilirsin.")

    # Üstte lig seçimi (kenar çubuğundakinden bağımsız, bu ekrana özel)
    tc1, tc2 = st.columns([2, 1])
    tahmin_lig = tc1.selectbox("Lig seç", list(TUM_LIGLER.keys()),
                               format_func=lambda k: TUM_LIGLER[k],
                               index=list(TUM_LIGLER.keys()).index(lig_kod),
                               key="tahmin_lig_sec")
    tc2.write(""); tc2.write("")
    if tc2.button("📥 Bu ligin verisini çek", type="primary", use_container_width=True):
        with st.spinner(f"{TUM_LIGLER[tahmin_lig]} yükleniyor…"):
            try:
                veri = lig_verisi_cek(tahmin_lig, 1)
                oyn = veri.dropna(subset=["FTHG"])
                w = agirlik_sozlugu(veri)
                st.session_state.update(lig_df=veri, agirliklar=w, lig_kod=tahmin_lig)
                st.success(f"✅ {len(oyn)} maç yüklendi.")
            except Exception as e:
                st.error(f"Yüklenemedi: {e}")

    dft = st.session_state["lig_df"]
    Wt = st.session_state["agirliklar"]
    if dft is None or st.session_state["lig_kod"] != tahmin_lig:
        st.info("Yukarıdan ligi seçip **Bu ligin verisini çek**'e bas.")
    else:
        oynanmis = dft.dropna(subset=["FTHG"])
        if len(oynanmis) == 0:
            st.warning("📭 Bu ligde bu sezon henüz maç oynanmamış — tahmin için veri yok. "
                       "Sezon başladıktan sonra tekrar dene.")
        else:
            # O ligin yaklaşan maçları (ESPN'den) + tahminleri
            st.markdown("### 📅 Yaklaşan maçlar ve tahminleri")
            gun_sec = st.radio("Dönem", ["Bugün", "Bu hafta (7 gün)"], horizontal=True)
            if st.button("🎯 Maçları ve tahminleri getir", type="primary"):
                with st.spinner("Maçlar çekiliyor ve tahmin ediliyor…"):
                    try:
                        gunler = 1 if gun_sec == "Bugün" else 7
                        tum_mac = []
                        for i in range(gunler):
                            g = datetime.date.today() + datetime.timedelta(days=i)
                            mlar = gunun_maclari(tarih=g, lig_kodu=tahmin_lig)
                            for _, m in mlar.iterrows():
                                tum_mac.append({"tarih": g, "ev": m["Ev"], "dep": m["Dep"],
                                                "saat": m["Saat"], "skor": m["Skor"]})
                        st.session_state["tahmin_maclar"] = tum_mac
                    except Exception as e:
                        st.error(f"Çekilemedi: {e}")
            tm = st.session_state.get("tahmin_maclar", [])
            if tm:
                # ESPN takım adları football-data adlarıyla birebir aynı olmayabilir;
                # defterdeki en yakın adı bulmaya çalış
                defter = takim_defteri(dft, dft["Date"].max() + pd.Timedelta(days=1))
                mevcut = [k for k in defter if not k.startswith("_")]

                def eslesen(ad):
                    if ad in mevcut:
                        return ad
                    # basit yakınlık: adın ilk kelimesi geçiyor mu
                    ilk = ad.split()[0].lower() if ad else ""
                    for t in mevcut:
                        if ilk and (ilk in t.lower() or t.lower().split()[0] in ad.lower()):
                            return t
                    return None

                bulundu = 0
                for mc in tm:
                    ev_e = eslesen(mc["ev"]); dep_e = eslesen(mc["dep"])
                    baslik = f"{mc['tarih']:%d.%m} {mc['saat']} · {mc['ev']} — {mc['dep']}"
                    if ev_e and dep_e and ev_e != dep_e:
                        bulundu += 1
                        t = mac_tahmin_puan(ev_e, dep_e, defter, hakem_defteri(dft, dft["Date"].max()+pd.Timedelta(days=1)),
                                            agirliklar=Wt)
                        mac_karti(mc["ev"], mc["dep"], t, f"{mc['tarih']:%d.%m} {mc['saat']}")
                    else:
                        st.markdown(f"<div class='mac' style='padding:8px 14px'>{baslik}"
                                    f"<br><span class='etiket'>⚠ Bu takımların bu sezon verisi henüz "
                                    f"yok — tahmin üretilemedi (yeni çıkan takım ya da isim eşleşmedi)</span></div>",
                                    unsafe_allow_html=True)
                if bulundu == 0 and tm:
                    st.info("Maçlar bulundu ama takım adları veri tabanıyla eşleşmedi. Bu genelde "
                            "sezon çok yeniyken (takımların henüz maçı yok) olur.")
            elif "tahmin_maclar" in st.session_state:
                st.info("Seçili dönemde bu ligde maç bulunamadı.")

        # Elle tahmin (opsiyonel, altta)
        st.write("---")
        with st.expander("✋ Elle iki takım seç (isteğe bağlı)"):
            takimlar = sorted([k for k in takim_defteri(dft, dft["Date"].max()+pd.Timedelta(days=1)) if not k.startswith("_")])
            if len(takimlar) >= 2:
                e1, e2 = st.columns(2)
                ev = e1.selectbox("Ev sahibi", takimlar, key="elle_ev")
                dep = e2.selectbox("Deplasman", takimlar, index=min(1, len(takimlar)-1), key="elle_dep")
                if st.button("Analiz et"):
                    if ev == dep:
                        st.warning("İki farklı takım seçin.")
                    else:
                        mac_karti(ev, dep, _tahmin(ev, dep))
            else:
                st.caption("Yeterli takım verisi yok.")


elif menu == "Tahmin Karnesi":
    st.markdown("# 📈 Tahmin Karnesi")
    st.caption("Sistemin GERÇEK karnesi: her maç, yalnızca o güne kadarki veriyle tahmin edilip "
               "gerçek sonuçla kıyaslanır. 'En çok hangi tahminimiz tutuyor' sorusunun şeffaf cevabı. "
               "Örn. MS1 için 100 maçta 54 doğru → %54.")
    if df is None:
        st.info("Önce **Tahmin** ekranından ligi seçip veriyi çekin.")
    else:
        oynanmis = df.dropna(subset=["FTHG"])
        if len(oynanmis) < 15:
            st.warning(f"⚠️ Sadece {len(oynanmis)} maç oynanmış. Tahmin karnesi için en az 15 maç "
                       "gerekir (anlamlı sonuç için 50+). Sezon ilerledikçe bu tablo dolacak.")
        else:
            st.caption(f"⏱️ Hesaplama {len(oynanmis)} maçı tek tek yeniden tahmin eder — "
                       "birkaç dakika sürebilir, sabırlı olun. Sonuç önbelleğe alınır, "
                       "ikinci açılışta anında gelir.")
            if st.button("📈 Tahmin karnesini hesapla", type="primary"):
                with st.spinner("Her maç geçmiş veriyle yeniden tahmin ediliyor…"):
                    rapor = _isabet_hesapla(st.session_state["lig_kod"], len(oynanmis))
                genel = rapor.pop("_genel", {"deneme": 0, "dogru": 0, "yuzde": 0})
                c1, c2, c3 = st.columns(3)
                c1.metric("Genel isabet", f"%{genel['yuzde']}")
                c2.metric("Doğru tahmin", genel["dogru"])
                c3.metric("Toplam tahmin", genel["deneme"])
                st.write("")
                st.markdown("### Market market isabet (yüksekten düşüğe)")
                st.caption("Sistem her maçta hangi marketleri 'önerdi' ve kaçı tuttu. "
                           "En üsttekiler en güvenilir tahmin tiplerin.")
                satirlar = []
                for market, v in sorted(rapor.items(), key=lambda x: -x[1]["yuzde"]):
                    satirlar.append({"Tahmin Tipi": MARKET_ETIKET.get(market, market),
                                     "Doğru": v["dogru"], "Deneme": v["deneme"],
                                     "İsabet %": v["yuzde"]})
                tablo = pd.DataFrame(satirlar)
                st.dataframe(tablo, hide_index=True, use_container_width=True, height=500)
                st.caption("Not: '%50 = yazı-tura' çizgisidir. Bunun altındakiler bu ligde "
                           "işe yaramıyor; üstündekiler gerçek değer taşıyor. Kriterler atılmaz "
                           "ama en çok tutan tahmin tiplerine güvenmek mantıklıdır.")
