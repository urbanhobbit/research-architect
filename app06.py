import streamlit as st
import google.generativeai as genai
import os
import re
import datetime
from fpdf import FPDF
from dotenv import load_dotenv

load_dotenv()
API_KEY   = os.getenv("GOOGLE_API_KEY", "")
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
try:                                        # Streamlit Cloud secrets
    if not API_KEY:
        API_KEY = st.secrets["GOOGLE_API_KEY"]
    MODEL_NAME = st.secrets.get("GEMINI_MODEL", MODEL_NAME)
except Exception:
    pass

if not API_KEY:
    st.error("API key bulunamadı. .env dosyasına veya Streamlit Secrets'a GOOGLE_API_KEY ekle.")
    st.stop()

genai.configure(api_key=API_KEY)
st.set_page_config(page_title="Araştırma Laboratuvarı", page_icon="🎓", layout="wide")

# ── SİSTEM PROMPTU ───────────────────────────────────────────────
BASE = """
Sen KKV & Babbie standartlarında araştırma rehberisin.
YANIT FORMATI: 1 köprü cümlesi + 1 soru. Kısa tut.
ÖRNEK KURALI: Yönlendirici örnek verirken TEK seçenek önerme — her zaman 2-3 alternatif sun.
  Yanlış → "Örneğin, güzellik algısının kampanya başarısı üzerindeki etkisini inceleyebiliriz."
  Doğru  → "Örneğin: (a) güzellik algısının oy tercihine etkisi, (b) yüz simetrisinin güven puanına etkisi, (c) medyada görünürlüğün seçim sonucuna etkisi — hangisi sana daha yakın geliyor?"

PAUSE KURALI: Yeni bir konuya geçmeden önce tek cümleyle ne kararlaştırıldığını özetle, sonra sor.
Örnek: "Konunu 'kolektif kimlik' olarak belirledik. Şimdi motivasyona geçelim: ..."

Sırayla ilerle — kriter karşılanmadan bir sonraki adıma geçme:
1. Konu      → gündelik fikri ampirik sosyal olguya çevir, onayla.
               Öğrenci zaten sosyal bilim terimi kullandıysa (örn. "kutuplaşma", "kimlik", "ayrımcılık") doğrudan onayla — yeniden tanımlamaya/somutlaştırmaya çalışma.
2. Motivasyon→ kişisel ilgiyi akademik merak olarak yeniden çerçevele
3. Önem      → somut bir politika/toplumsal soruna bağla (KKV 1994:15 Krit.1)
4. Literatür → spesifik teori/yazar + hangi boşluğu kapattığını talep et (KKV 1994:15 Krit.2)
5. Soru      → ampirik · yanlışlanabilir · evrensel forma dönüştür ve onayla
6. Gösterge  → kavramın varlığını doğrudan gösteren, sayılabilir şeye indir (Babbie 2007:127 — sonuç/korelasyon değil)

Her yanıtın sonuna ekle:
<DURUM>Konsept: … | Önem: … | Literatür: … | Soru: … | Gösterge: …</DURUM>

Gösterge onaylandığında yanıtının sonuna ekle: <TAMAMLANDI>
"""

# Persona tanımları: (sistem promptu, kısa açıklama)
PERSONAS = {
    "🌱 Destekleyici Mentor": {
        "prompt": f"Sen sıcak, vizyon katan bir danışmansın; 'İlginç, peki şöyle düşünelim...' tarzında köprüler kurarsın. {BASE}",
        "aciklama": "Sıcak, cesaretlendirici. Basit fikirlere akademik vizyon katar."
    },
    "🎓 Dengeli Akademisyen": {
        "prompt": f"Sen net ve standartları koruyan bir hocasın; KKV/Babbie'yi doğal olarak referans verirsin. {BASE}",
        "aciklama": "Yapıcı ama titiz. KKV ve Babbie'yi doğrudan referans verir."
    },
    "😈 Şeytanın Avukatı": {
        "prompt": f"Sen keskin sorularla zorlayan ama her zaman çıkış yolu gösteren bir eleştirmensin. {BASE}",
        "aciklama": "Zayıf noktaları açığa çıkarır — ama çıkış yolu gösterir."
    },
}

# ── MODEL ─────────────────────────────────────────────────────────
@st.cache_resource
def get_model(persona_prompt):
    return genai.GenerativeModel(
        model_name=MODEL_NAME,
        system_instruction=persona_prompt,
        generation_config={"max_output_tokens": 200, "temperature": 0.6},
    )

# ── SESSION STATE ─────────────────────────────────────────────────
DURUM_ALANLARI = ["Konsept", "Önem", "Literatür", "Soru", "Gösterge"]

for k, v in {
    "stage": 0,
    "display_history": [],
    "api_history": [],
    "taslak_raw": "",
    "taslak_dict": {a: "" for a in DURUM_ALANLARI},
    "selected": None,
    "total_prompt_tokens": 0,
    "total_output_tokens": 0,
    "total_turns": 0,
    "analytics_logged": False,
    "sheets_error": "",
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── TASLAK PARSE ──────────────────────────────────────────────────
def parse_taslak(raw: str) -> dict:
    """'Konsept: X | Önem: Y | ...' formatını dict'e çevirir."""
    result = {a: "" for a in DURUM_ALANLARI}
    for part in raw.split("|"):
        part = part.strip()
        if ":" in part:
            key, _, val = part.partition(":")
            key = key.strip()
            val = val.strip()
            if key in result and val and val not in ("…", "—", "..."):
                result[key] = val
    return result

# ── SIDEBAR ───────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 📝 Araştırma Taslağın")
    td = st.session_state.taslak_dict
    for alan in DURUM_ALANLARI:
        deger = td.get(alan, "")
        if deger:
            st.markdown(
                f"<div style='margin-bottom:8px;'>"
                f"<span style='font-size:.75em;color:#666;text-transform:uppercase;letter-spacing:.05em;'>{alan}</span><br>"
                f"<span style='font-size:.88em;color:#1e1e1e;'>✅ {deger}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"<div style='margin-bottom:8px;opacity:.45;'>"
                f"<span style='font-size:.75em;text-transform:uppercase;letter-spacing:.05em;'>{alan}</span><br>"
                f"<span style='font-size:.88em;'>⬜ henüz belirlenmedi</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
    st.divider()
    if st.session_state.selected:
        st.caption(f"Danışman: **{st.session_state.selected}**")

    # Token istatistikleri
    pt = st.session_state.total_prompt_tokens
    ot = st.session_state.total_output_tokens
    if pt or ot:
        toplam = pt + ot
        maliyet = (pt * 0.075 + ot * 0.30) / 1_000_000
        st.markdown(
            f"<div style='font-size:.75em;color:#666;margin-top:4px;'>"
            f"<b>📊 Oturum</b><br>"
            f"Tur: {st.session_state.total_turns} &nbsp;·&nbsp; "
            f"Toplam: {toplam:,} token<br>"
            f"Gönderilen: {pt:,} &nbsp;·&nbsp; Alınan: {ot:,}<br>"
            f"<span style='color:#2e7d32;'>~${maliyet:.5f}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.divider()
    if st.button("↺ Sıfırla"):
        st.session_state.clear()
        st.rerun()

# ── YARDIMCILAR ───────────────────────────────────────────────────
def stream(model, messages):
    return model.generate_content(messages, stream=True, request_options={"timeout": 30})

def build_messages(api_history, taslak_raw):
    recent = api_history[-4:] if len(api_history) > 4 else api_history
    if taslak_raw:
        memo = [
            {"role": "user",  "parts": ["Şu ana kadar ne kararlaştırdık?"]},
            {"role": "model", "parts": [f"<DURUM>{taslak_raw}</DURUM>"]},
        ]
        return memo + recent
    return recent

# ── GOOGLE SHEETS ANALİTİK ────────────────────────────────────────
@st.cache_resource
def get_sheet():
    """Streamlit secrets'tan credentials alır, (sheet, hata) tuple'ı döner."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ],
        )
        gc = gspread.authorize(creds)
        sheet_name = st.secrets.get("ANALYTICS_SHEET", "Research Architect Analytics")
        return gc.open(sheet_name).sheet1, None
    except Exception as e:
        return None, str(e)[:300]

def log_session(taslak_dict, selected, turns, pt, ot):
    """Tamamlanan oturumu Google Sheets'e yazar. Hata session_state'e kaydedilir."""
    sheet, conn_err = get_sheet()
    if sheet is None:
        st.session_state.sheets_error = f"Bağlantı hatası: {conn_err}"
        return
    try:
        maliyet = round((pt * 0.075 + ot * 0.30) / 1_000_000, 6)
        row = [
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            selected,
            turns,
            pt,
            ot,
            pt + ot,
            maliyet,
            taslak_dict.get("Konsept",   "—"),
            taslak_dict.get("Önem",      "—")[:100],
            taslak_dict.get("Literatür", "—")[:100],
            taslak_dict.get("Soru",      "—")[:150],
            taslak_dict.get("Gösterge",  "—")[:100],
        ]
        sheet.append_row(row, value_input_option="USER_ENTERED")
        st.session_state.sheets_error = ""   # başarılı
    except Exception as e:
        st.session_state.sheets_error = str(e)[:300]


# ── PDF OLUŞTURUCU ────────────────────────────────────────────────
def build_pdf(selected, taslak_dict, display_history, r1, r2, r3, r4):
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_margins(20, 20, 20)
    pdf.set_auto_page_break(auto=True, margin=22)

    # Türkçe karakter desteği — önce repo içi bundled font, sonra sistem fontları
    _dir = os.path.dirname(os.path.abspath(__file__))
    font_paths = [
        # 1. Repo içi bundled — her platformda çalışır (Windows + Streamlit Cloud)
        (os.path.join(_dir, "fonts", "DejaVuSans.ttf"),
         os.path.join(_dir, "fonts", "DejaVuSans-Bold.ttf")),
        # 2. Windows sistem fontları (fallback)
        (r"C:\Windows\Fonts\arial.ttf",   r"C:\Windows\Fonts\arialbd.ttf"),
        (r"C:\Windows\Fonts\calibri.ttf", r"C:\Windows\Fonts\calibrib.ttf"),
        # 3. Linux / Streamlit Cloud Ubuntu sistem fontları (fallback)
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
         "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ]
    f = "Helvetica"
    for reg, bold in font_paths:
        try:
            pdf.add_font("Ana", "",  reg)
            pdf.add_font("Ana", "B", bold)
            f = "Ana"
            break
        except Exception:
            continue

    tarih = datetime.date.today().strftime("%d.%m.%Y")
    G = (46, 125, 50)       # yeşil
    LG = (232, 245, 233)    # açık yeşil
    GR = (248, 249, 250)    # gri arka plan
    DG = (100, 100, 100)    # koyu gri (label)
    BL = (30, 30, 30)       # siyah (içerik)

    def section_header(title):
        pdf.set_fill_color(*G)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font(f, "B", 9)
        pdf.cell(0, 7, title, fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    def field(label, value):
        pdf.set_text_color(*DG)
        pdf.set_font(f, "B", 7)
        pdf.cell(0, 4, label.upper(), new_x="LMARGIN", new_y="NEXT")
        pdf.set_fill_color(*GR)
        pdf.set_text_color(*BL)
        pdf.set_font(f, "", 9)
        pdf.multi_cell(0, 5, value or "—", fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    # ── SAYFA 1: Özet ─────────────────────────────────────────────
    pdf.add_page()

    pdf.set_fill_color(*G)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font(f, "B", 13)
    pdf.cell(0, 13, "Research Architect  ·  Modül 1: KKV Gatekeeper",
             fill=True, align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.set_fill_color(*LG)
    pdf.set_text_color(*DG)
    pdf.set_font(f, "", 9)
    pdf.cell(0, 7, f"Danışman: {selected}     |     Tarih: {tarih}",
             fill=True, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    section_header("ARAŞTIRMA TASLAGI")
    for alan in DURUM_ALANLARI:
        field(alan, taslak_dict.get(alan, "") or "—")

    pdf.ln(2)
    section_header("YZ KULLANIM BEYANI")
    field("Seçim ve gerekçem", r3)
    field("Özgün katkım / YZ katkısı", r4)

    # ── SAYFA 2+: Süreç Belgesi ────────────────────────────────────
    pdf.add_page()

    section_header("ÖĞRENME SÜRECİ REFLEKSİYONU")
    field("En çok zorlayan aşama", r1)
    field("Süreç öncesi vs. sonrası", r2)
    pdf.ln(4)

    section_header("SOHBET GÜNLÜĞÜ")
    for msg in display_history:
        role = "Danışman" if msg["role"] == "assistant" else "Öğrenci"
        pdf.set_text_color(*DG)
        pdf.set_font(f, "B", 8)
        pdf.cell(0, 5, f"[{role}]", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(*BL)
        pdf.set_font(f, "", 9)
        pdf.multi_cell(0, 5, msg["content"], new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    return bytes(pdf.output())


# ── ANA EKRAN ─────────────────────────────────────────────────────
st.title("Araştırma Laboratuvarı 🎓")

# ── STAGE 0: Persona seçimi ───────────────────────────────────────
if st.session_state.stage == 0:
    st.markdown("### Modül 1: KKV Gatekeeper")
    st.caption("Bir danışman seç — seni 6 adımda akademik bir araştırma sorusuna götürecek.")
    st.markdown("<br>", unsafe_allow_html=True)

    cols = st.columns(3)
    persona_secimi = st.session_state.get("_secim", list(PERSONAS.keys())[0])

    for i, (isim, bilgi) in enumerate(PERSONAS.items()):
        with cols[i]:
            secili = persona_secimi == isim
            border_color = "#2e7d32" if secili else "#dee2e6"
            bg_color = "#f0f7f0" if secili else "#ffffff"
            st.markdown(
                f"""<div style='border:2px solid {border_color};background:{bg_color};
                border-radius:12px;padding:18px;min-height:130px;cursor:pointer;
                transition:all .2s;'>
                <div style='font-size:1.6em;margin-bottom:6px;'>{isim.split()[0]}</div>
                <div style='font-weight:600;margin-bottom:6px;font-size:.95em;'>
                    {" ".join(isim.split()[1:])}</div>
                <div style='font-size:.82em;color:#555;'>{bilgi['aciklama']}</div>
                </div>""",
                unsafe_allow_html=True,
            )
            if st.button("Seç" if not secili else "✓ Seçildi",
                         key=f"btn_{i}",
                         type="primary" if secili else "secondary",
                         use_container_width=True):
                st.session_state["_secim"] = isim
                st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    secilen = st.session_state.get("_secim", list(PERSONAS.keys())[0])
    if st.button(f"Başla →", type="primary", use_container_width=False):
        st.session_state.selected = secilen
        ilk = "Merhaba! Sosyal dünyada ampirik olarak incelemek istediğin konuyu bir-iki cümleyle anlat."
        st.session_state.display_history.append({"role": "assistant", "content": ilk})
        st.session_state.api_history = [
            {"role": "user",  "parts": ["Başlamak istiyorum."]},
            {"role": "model", "parts": [ilk]},
        ]
        st.session_state.stage = 1
        st.rerun()

# ── STAGE 1: Sohbet ───────────────────────────────────────────────
elif st.session_state.stage == 1:
    for msg in st.session_state.display_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_input = st.chat_input("Yanıtınızı yazın...")

    if user_input:
        st.session_state.display_history.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        st.session_state.api_history.append({"role": "user", "parts": [user_input]})

        with st.chat_message("assistant"):
            placeholder = st.empty()
            thinking  = st.empty()
            thinking.markdown("*Düşünüyor...*")
            full_text = ""
            ok = True

            try:
                model = get_model(PERSONAS[st.session_state.selected]["prompt"])
                messages = build_messages(st.session_state.api_history, st.session_state.taslak_raw)
                response = stream(model, messages)
                for chunk in response:
                    if chunk.text:
                        thinking.empty()
                        full_text += chunk.text
                        # Tekrar döngüsü algılama: aynı kelime 6+ kez geçiyorsa dur
                        words = full_text.split()
                        if len(words) > 12:
                            last_word = words[-1]
                            if words[-6:].count(last_word) >= 5:
                                break
                        visible = re.sub(r'<DURUM>.*', '', full_text, flags=re.DOTALL).strip()
                        visible = visible.replace('<TAMAMLANDI>', '').strip()
                        placeholder.markdown(visible + "▌")

                # Token kullanımını kaydet
                try:
                    u = response.usage_metadata
                    st.session_state.total_prompt_tokens  += u.prompt_token_count or 0
                    st.session_state.total_output_tokens  += u.candidates_token_count or 0
                    st.session_state.total_turns          += 1
                except Exception:
                    pass

                # DURUM'u sidebar'a aktar
                m = re.search(r'<DURUM>(.*?)</DURUM>', full_text, re.DOTALL)
                if m:
                    raw = m.group(1).strip().replace("\n", " ")
                    st.session_state.taslak_raw  = raw
                    st.session_state.taslak_dict = parse_taslak(raw)

                clean = re.sub(r'<DURUM>.*?</DURUM>', '', full_text, flags=re.DOTALL)
                clean = clean.replace('<TAMAMLANDI>', '').strip()
                placeholder.markdown(clean)

            except Exception as e:
                ok = False
                if st.session_state.api_history and st.session_state.api_history[-1]["role"] == "user":
                    st.session_state.api_history.pop()
                if st.session_state.display_history and st.session_state.display_history[-1]["role"] == "user":
                    st.session_state.display_history.pop()
                err = str(e)
                if "timeout" in err.lower():
                    placeholder.warning("⚠️ Zaman aşımı. Tekrar deneyin.")
                elif "429" in err or "quota" in err.lower():
                    placeholder.warning("⚠️ API kotası doldu. Biraz bekleyin.")
                else:
                    placeholder.warning(f"⚠️ Hata: {err[:120]}")

            if ok and full_text:
                st.session_state.api_history.append({"role": "model", "parts": [full_text]})
                st.session_state.display_history.append({"role": "assistant", "content": clean})
                if "<TAMAMLANDI>" in full_text:
                    st.session_state.stage = 2
                    st.rerun()

# ── STAGE 2: Tamamlandı ───────────────────────────────────────────
elif st.session_state.stage == 2:
    # Oturumu bir kez logla (sayfa her render'da tekrar çalışır, flag bunu önler)
    if not st.session_state.analytics_logged:
        log_session(
            st.session_state.taslak_dict,
            st.session_state.selected,
            st.session_state.total_turns,
            st.session_state.total_prompt_tokens,
            st.session_state.total_output_tokens,
        )
        st.session_state.analytics_logged = True

    st.balloons()
    st.success("🎉 Modül 1 tamamlandı! KKV & Babbie standartlarında araştırma sorun hazır.")
    if st.session_state.get("sheets_error"):
        st.warning(f"📊 Sheets log hatası — {st.session_state.sheets_error}")
    st.markdown("<br>", unsafe_allow_html=True)

    col_taslak, col_refleks = st.columns([1, 1], gap="large")

    with col_taslak:
        st.markdown("#### 📋 Araştırma Taslağın")
        td = st.session_state.taslak_dict
        bos = "<i style='color:#aaa'>—</i>"
        for alan in DURUM_ALANLARI:
            deger = td.get(alan, "")
            icerik = deger if deger else bos
            st.markdown(
                f"<div style='margin-bottom:14px;padding:12px 14px;background:#f8f9fa;"
                f"border-radius:8px;border-left:4px solid #2e7d32;'>"
                f"<span style='font-size:.72em;color:#888;text-transform:uppercase;"
                f"letter-spacing:.06em;'>{alan}</span><br>"
                f"<span style='font-size:.92em;color:#1e1e1e;'>{icerik}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

    with col_refleks:
        st.markdown("#### 🪞 Refleksiyon")
        st.caption("Bu yanıtlar sınıf tartışması ve YZ kullanım beyanı için kullanılabilir.")

        st.markdown("<p style='font-size:.8em;color:#666;font-weight:600;text-transform:uppercase;"
                    "letter-spacing:.06em;margin-bottom:4px;'>Öğrenme Süreci</p>",
                    unsafe_allow_html=True)
        r1 = st.text_area(
            "Hangi aşama seni en çok zorladı ve neden?",
            placeholder="Örn: Gösterge — kavramın 'sonucu' değil 'varlığını' göstermek arasındaki farkı anlamak zordu.",
            key="r1", height=90
        )
        r2 = st.text_area(
            "Bu süreç olmadan araştırma sorusunu nasıl yazardın?",
            placeholder="Örn: 'Futbol psikolojisi' derdim. Şimdi bağımlı/bağımsız değişkenim var.",
            key="r2", height=90
        )

        st.markdown("<p style='font-size:.8em;color:#666;font-weight:600;text-transform:uppercase;"
                    "letter-spacing:.06em;margin-top:12px;margin-bottom:4px;'>YZ Eleştirisi</p>",
                    unsafe_allow_html=True)
        r3 = st.text_area(
            "AI bir seçenek önerdiğinde hangisini seçtin — ya da neden farklı bir yol izledin?",
            placeholder="Örn: AI 'sosyal medya paylaşım sayısı' önerdi, ben 'nefret söylemi oranı'nı seçtim — çünkü kavramın varlığını daha doğrudan gösteriyor.",
            key="r3", height=100
        )
        r4 = st.text_area(
            "Bu araştırma sorusunda senin özgün fikrin neydi — AI neyi dönüştürdü?",
            placeholder="Örn: 'Kutuplaşma' fikri bendendi. AI bunu 'duygusal kutuplaşmanın gruplararası güvensizliğe etkisi' formuna taşıdı.",
            key="r4", height=100
        )

    st.divider()

    # Çıktı dosyası
    log  = f"MODÜL 1 — KKV GATEKEEPER\nDanışman: {st.session_state.selected}\n{'='*40}\n\n"
    log += "ARAŞTIRMA TASLAK\n"
    for alan in DURUM_ALANLARI:
        log += f"  {alan}: {st.session_state.taslak_dict.get(alan, '—')}\n"
    log += f"\n{'='*40}\nSOHBET GÜNLÜĞÜ\n\n"
    for msg in st.session_state.display_history:
        role = "Danışman" if msg["role"] == "assistant" else "Öğrenci"
        log += f"[{role}]\n{msg['content']}\n\n"
    log += f"{'='*40}\nREFLEKSİYON\n\n"
    log += f"[Öğrenme Süreci]\n"
    log += f"1. En çok zorlayan aşama:\n{r1 or '—'}\n\n"
    log += f"2. Süreç öncesi vs. sonrası:\n{r2 or '—'}\n\n"
    log += f"[YZ Eleştirisi]\n"
    log += f"3. Seçim ve gerekçe:\n{r3 or '—'}\n\n"
    log += f"4. Özgün katkı vs. YZ katkısı:\n{r4 or '—'}\n"

    col_dl1, col_dl2 = st.columns([1, 3])
    with col_dl1:
        try:
            pdf_bytes = build_pdf(
                st.session_state.selected,
                st.session_state.taslak_dict,
                st.session_state.display_history,
                r1, r2, r3, r4,
            )
            st.download_button(
                "📥 PDF Olarak İndir",
                pdf_bytes,
                "Modul1_KKV_Raporu.pdf",
                "application/pdf",
                use_container_width=True,
                type="primary",
            )
        except Exception as e:
            st.warning(f"PDF oluşturulamadı: {e}")
            st.download_button("📄 TXT Olarak İndir", log, "Modul1_KKV.txt", "text/plain",
                               use_container_width=True)
