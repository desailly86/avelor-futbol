# -*- coding: utf-8 -*-
"""
AVELOR FUTBOL — Puan-Ağırlık Motoru (tek sezon 2026/27)
========================================================
Poisson yok. Kriter puanı + öğrenilen ağırlık üstüne kurulu.
Menü: st.radio ile (otomatik kapanma sorunu çözüldü).
Ekranlar: Dashboard · Günün Bülteni (takvimli) · Program · Puan Durumu ·
          Bahis Oranları · Kriter Karnesi · Tahmin
"""
import datetime
import numpy as np
import pandas as pd
import streamlit as st

from futbol_veri import (TUM_LIGLER, ANA_LIGLER, lig_verisi_cek, fikstur_cek,
                         gunun_bulteni, fikstur_gunleri, sezon_etiketi)
from futbol_tablo import puan_durumu, son_mac_sonuclari
from futbol_kriter import (takim_defteri, hakem_defteri, mac_tahmin_puan,
                           en_iyi_uc, agirlik_sozlugu, agirlik_durumu, MARKET_ETIKET,
                           kriter_karne, KRITER_TANIM)

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
    menu = st.radio("Menü", ["Dashboard", "Günün Bülteni", "Program", "Puan Durumu",
                             "Bahis Oranları", "Kriter Karnesi", "Tahmin"],
                    label_visibility="collapsed")
    st.write("---")
    st.caption("Hiçbir model kazanç garantisi vermez; bahis şirketi marjı her orana gömülüdür. "
               "Sezon başında veri az → tahminler zayıf, bu normaldir.")

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
            f"<div><div class='etiket'>{madalya[i]} CESUR ÖNERİ</div>"
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
    if df is not None:
        ad = agirlik_durumu(df)
        durum_txt = ad["kademe"] if ad["durum"] == "Aktif" else "Bekliyor"
    else:
        durum_txt = "Boş"
    c4.markdown(f"<div class='kutu'><div class='etiket'>Ağırlık Olgunluğu</div>"
                f"<div class='buyuk' style='font-size:18px'>{durum_txt}</div></div>", unsafe_allow_html=True)
    st.write("")
    if df is None:
        st.info("Başlamak için soldan bir lig seçip **Program** ekranından veriyi çekin. "
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
            st.session_state["dash_bulten"] = gunun_bulteni(sadece_kalan=True, tsi_simdi=simdi)
        except Exception as e:
            st.error(f"Çekilemedi: {e}")
    bd = st.session_state.get("dash_bulten")
    if bd is not None and not bd.empty:
        for _, m in bd.head(15).iterrows():
            st.markdown(f"<div class='mac' style='padding:6px 14px'><b>{m.get('Saat_TSI','--:--')}</b> "
                        f"&nbsp; {m['HomeTeam']} — {m['AwayTeam']}"
                        f"<span class='etiket'> &nbsp; {m.get('Lig','')}</span></div>", unsafe_allow_html=True)
    elif bd is not None:
        st.info("Bugün kalan maç yok.")

# ============================================================ GÜNÜN BÜLTENİ (takvimli)
elif menu == "Günün Bülteni":
    st.markdown("# 🗓️ Günün Bülteni")
    simdi = datetime.datetime.utcnow() + datetime.timedelta(hours=3)
    st.caption(f"TSİ {simdi:%H:%M} · Bugün {simdi:%d.%m.%Y}. Bir gün seçip o günün maçlarını gör. "
               "**Not:** Kaynak, ileri tarihli fikstürü genelde 3-5 gün önceden yayınlar; "
               "çok ileri bir gün seçersen henüz maç görünmeyebilir.")

    # Hangi günlerde maç var? (kaynak fikstüründen özet — kullanıcı kör seçmesin)
    if st.button("📅 Önümüzdeki günlerde maç olan tarihleri göster"):
        try:
            gunler = fikstur_gunleri(21)
            if gunler.empty:
                st.warning("Kaynak fikstür dosyasında yaklaşan maç bulunamadı. Hafta ortasında "
                           "(genelde Salı-Çarşamba) hafta sonu maçları dosyaya düşer.")
            else:
                gunler["Gün"] = gunler["Date"].dt.strftime("%d.%m.%Y (%a)")
                st.dataframe(gunler[["Gün", "mac_sayisi"]].rename(
                    columns={"mac_sayisi": "Maç sayısı"}), hide_index=True, use_container_width=True)
                st.caption("↑ Bu tarihlerden birini aşağıdaki takvimden seçersen maçlar gelir.")
        except Exception as e:
            st.error(f"Tarih özeti çekilemedi: {e}")

    c1, c2 = st.columns([1, 1])
    secili_gun = c1.date_input("Gün seç", value=simdi.date(),
                               min_value=simdi.date() - datetime.timedelta(days=7),
                               max_value=simdi.date() + datetime.timedelta(days=21),
                               format="DD.MM.YYYY")
    bugun_mu = secili_gun == simdi.date()
    sadece_kalan = c2.toggle("Sadece kalan maçlar", value=True, disabled=not bugun_mu,
                             help="Yalnızca bugün için geçerli")
    if st.button("🗓️ Seçili günün maçlarını getir", type="primary", use_container_width=True):
        with st.spinner("Program çekiliyor…"):
            try:
                st.session_state["bulten"] = gunun_bulteni(
                    sadece_kalan=sadece_kalan and bugun_mu, tsi_simdi=simdi,
                    secili_gun=secili_gun, gecmis_df=df)
                st.session_state["bulten_gun"] = secili_gun
            except Exception as e:
                st.error(f"Bülten çekilemedi: {e}")
    b = st.session_state.get("bulten")
    if b is not None:
        secilen = st.session_state.get("bulten_gun", secili_gun)
        if b.empty:
            st.info(f"**{secilen:%d.%m.%Y}** için maç bulunamadı. Olası sebepler: (1) o gün "
                    "hiç maç yok, (2) ileri tarihli fikstür henüz kaynağa düşmemiş (3-5 gün "
                    "önceden gelir), (3) geçmiş bir gün seçtiysen o günün sonuçları yalnızca "
                    "yüklü ligin verisinde bulunur — üstteki '📅 tarihleri göster' ile hangi "
                    "günlerde maç olduğunu görebilirsin.")
        else:
            st.markdown(f"**{secilen:%d.%m.%Y} — {len(b)} maç**")
            for _, m in b.iterrows():
                skor = m.get("Skor", "")
                orta = f" <b>{skor}</b> " if skor else " — "
                oran = ""
                if not skor and pd.notna(m.get("B365H")):
                    oran = f" · {m['B365H']}/{m.get('B365D','-')}/{m.get('B365A','-')}"
                st.markdown(f"<div class='mac' style='padding:8px 14px'>"
                            f"<b>{m.get('Saat_TSI','--:--')}</b> &nbsp; {m['HomeTeam']}{orta}{m['AwayTeam']}"
                            f"<span class='etiket'> &nbsp; {m.get('Lig','')}{oran}</span></div>",
                            unsafe_allow_html=True)

# ============================================================ PROGRAM
elif menu == "Program":
    st.markdown("# 📡 Program & Tahmin")
    st.caption("1) Ligi seç, veriyi çek → 2) Yaklaşan maçların tahminini gör.")
    if st.button("1️⃣ Lig verisini çek ve ağırlıkları hesapla", type="primary", use_container_width=True):
        model_kur()
    if df is not None and st.session_state["lig_kod"] == lig_kod:
        if lig_kod in ANA_LIGLER and st.button("2️⃣ Yaklaşan maçları getir"):
            try:
                st.session_state["fikstur"] = fikstur_cek(lig_kod)
            except Exception as e:
                st.error(f"Fikstür çekilemedi: {e}")
        fx = st.session_state.get("fikstur", pd.DataFrame())
        if fx.empty and "fikstur" in st.session_state:
            st.info("Bu lig için yaklaşan maç bulunamadı. Sebebi: (1) bu hafta maç günü henüz "
                    "gelmedi, ya da (2) kaynak fikstür dosyası hafta sonu maçlarını genelde "
                    "**Cuma öğleden sonra** yayınlar — hafta ortasında boş olması normaldir. "
                    "Oynanmış maçları görmek için **Puan Durumu → Son Maçlar** sekmesine bakın.")
        for _, m in fx.iterrows():
            t = _tahmin(m["HomeTeam"], m["AwayTeam"], mac_tarihi=m.get("Date"))
            mac_karti(m["HomeTeam"], m["AwayTeam"], t,
                      m["Date"].strftime("%d.%m.%Y") if pd.notna(m.get("Date")) else "")
    elif df is not None:
        st.info("Lig değişti — yeni lig için veriyi tekrar çekin.")

# ============================================================ PUAN DURUMU
elif menu == "Puan Durumu":
    st.markdown("# 📊 Puan Durumu")
    st.caption("2026/27 — genel, iç saha, deplasman. Tek sezon.")
    if df is None:
        st.info("Önce **Program** ekranından veriyi çekin.")
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
        st.info("Önce **Program** ekranından veriyi çekin.")
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
        st.info("Önce **Program** ekranından veriyi çekin.")
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
    if df is None:
        st.info("Önce **Program** ekranından veriyi çekin.")
    else:
        defter_on = takim_defteri(df, df["Date"].max() + pd.Timedelta(days=1))
        takimlar = sorted([k for k in defter_on if not k.startswith("_")])
        if len(takimlar) < 2:
            st.warning("Bu ligde henüz yeterli takım verisi yok.")
        else:
            c1, c2 = st.columns(2)
            ev = c1.selectbox("Ev sahibi", takimlar)
            dep = c2.selectbox("Deplasman", takimlar, index=min(1, len(takimlar)-1))
            if st.button("Analiz et", type="primary"):
                if ev == dep:
                    st.warning("İki farklı takım seçin.")
                else:
                    mac_karti(ev, dep, _tahmin(ev, dep))
