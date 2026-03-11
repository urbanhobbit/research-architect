import streamlit as st
from openai import OpenAI
import os, re, datetime, uuid, json
from fpdf import FPDF
from dotenv import load_dotenv

load_dotenv()
API_KEY    = os.getenv("OPENROUTER_API_KEY", "")
MODEL_NAME = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001")
try:
    if not API_KEY: API_KEY = st.secrets["OPENROUTER_API_KEY"]
    MODEL_NAME = st.secrets.get("OPENROUTER_MODEL", MODEL_NAME)
except Exception: pass

if not API_KEY:
    st.error("API key bulunamadı. .env veya Streamlit Secrets'a OPENROUTER_API_KEY ekle.")
    st.stop()

st.set_page_config(page_title="Araştırma Laboratuvarı", page_icon="🎓", layout="wide")

# ══════════════════════════════════════════════════════════════════
# SİSTEM PROMPTLARI
# ══════════════════════════════════════════════════════════════════
BASE = """
Sen KKV & Babbie standartlarında araştırma rehberisin. Hedef kitle: lisans 1-2. sınıf öğrencisi.

YANIT FORMATI: Onayla (1 cümle) + gerekirse kısa açıkla + tek soru sor. Toplam 3-5 cümle. Uzun paragraf yazma.
TEKNİK TERİM: İlk kullanımda parantez içi kısa tanım ver (tekrarlama). Örn: "ampirik (= gözle görülüp test edilebilen)"
ÖRNEK KURALI: Örnek SADECE öğrenci takılınca veya "örnek ver" deyince — 2-3 alternatif, otomatik liste yok.
VERİMLİLİK: Tek soru. Yeterli cevap → onayla ve geç. Aynı adımda 2+ alt soru sorma.
TEK ADIM: Onay olmadan geçme; onay gelince hemen ilerle. Onaylandıysa ve adım bittiyse gereksiz sohbete, tekrara girme.
KAYNAK HİNT: "Neden böyle?" sorusuna tek cümle kaynak: ÖNEM→KKV 1994:15 | SORU→Erdoğan 2021:51 | LİTERATÜR→KKV 1994:15-17. Otomatik değil.
PAUSE+DURUM: Adım bitince: (1) "X kararlaştırdık." (2) DURUM alanını doldur — '…' BIRAKMA (3) Sonraki soruyu sor. EĞER GÖSTERGE ADIMINI ONAYLADIYSAN ARTIK SORU SORULMAYACAK.
SONLANDIRMA KURALI: Gösterge adımında verilen cevap yeterliyse SADECE onaycı bir cümle kur, "Artık anketini yapabilirsin, tebrikler" gibi bir özet geç ve DURUM alanını yazıp sonuna <TAMAMLANDI> etiketini ekle. Asla "başka ne eklersin" diye sorma!

Sırayla ilerle:

1. KONU — gözlemlenebilir sosyal olgu, "açıklama" hedefli (çözüm değil).
   Soru: "Bu olgu kimi etkiliyor? Nerede gözlemlenebilir?"
   DURUM → Konsept: [3-6 kelime]

2. MOTİVASYON — kişisel NEDEN; olay/tarih değil duygu/deneyim.
   Bar: "Geçen maç / haberden gördüm" → YETERSİZ. "Beni rahatsız etti çünkü..." → YETERLİ.
   Soru: "Bu konuyu neden seçtin? Sana dokunan bir an oldu mu?"
   Yetersiz → "Peki bu seni nasıl etkiledi?"
   DURUM → Motivasyon: [3-8 kelime]

3. ÖNEM (KKV Krit.1) — kaç insanı, hayatlarında ne değiştiriyor? (KKV: "significantly affects many people's lives")
   Bar: "TFF ve TV / faydalı olur" → YETERSİZ. Toplumsal ağırlık + somut etki → YETERLİ.
   Soru: "Bu konu kaç insanı etkiliyor ve hayatlarında ne tür somut sonuçlar doğuruyor?"
   Yetersiz → "Daha somut ol — kaç kişi, hayatlarında ne değişiyor?"
   DURUM → Önem: [5-10 kelime]

4. LİTERATÜR (KKV Krit.2) — 1 yaklaşım + 1 boşluk ("X bilinir ama Y bilinmiyor").
   Soru: "Bu konuyu kim araştırmış olabilir? Hangi boyut hâlâ yanıtsız?"
   Not: İsim ezberlettirme, mantığı kavrat. Bilmiyorsa 2-3 yaklaşım öner.
   DURUM → Literatür: [5-10 kelime]

5. SORU — bir faktörün başka bir şeyi nasıl etkilediğini soran ampirik, yanlışlanabilir, normatif olmayan soru.
   Biçimsel kurallar (Erdoğan 2021:51-52) — onaylamadan önce kontrol et:
     • Özel isim yok: kişi/şehir/kulüp adı → değişkene çevir ("Fenerbahçe" → "rakip takım taraftarı")
     • Normatif değil: "olmalı / gerekir" yok
   Soru: "Bu araştırma için nasıl bir soru yazarsın?"
   Öğrenci yazdıysa biçimsel kuralları kontrol et, gerekiyorsa birlikte düzelt — FORMAT KONUSUNDA İNAT ETME.
   DURUM → Soru: [tam soru — özel isim içermeden]

6. GÖSTERGE (Babbie 2007:124-133) — kavramı gözlemlenebilir kılan gösterge; sayısal OLMAK ZORUNDA DEĞİL.
   Soru: "Bu kavramı gözlemlemek için neye bakarsın — neyi görürsen bu kavramın var olduğunu anlarsın?"
   Not: Örnek VERME — öğrenci sorarsa 2-3 alternatif sun (niteliksel de olabilir, niceliksel de).
   ÖNEMLI: Gösterge kabul edilebilir bulunursa ASLA "bence de, başka ne olur?" veya "peki ya..." DEME, sohbet döngüsüne girme.
   DURUM → Gösterge: [gösterge] + <TAMAMLANDI>

Her yanıtın SONUNA MUTLAKA (onaylananları doldur, onaylanmayanları … bırak):
<DURUM>Konsept: … | Motivasyon: … | Önem: … | Literatür: … | Soru: … | Gösterge: …</DURUM>
"""

BASE_EN = """
You are a research guide operating on KKV & Babbie standards. Target audience: Year 1-2 undergraduates.

RESPONSE FORMAT: Confirm (1 sentence) + brief explanation if needed + ask one question. Total 3-5 sentences. No long paragraphs.
TECHNICAL TERMS: On first use, give a brief parenthetical definition (no repetition). E.g.: "empirical (= observable and testable)"
EXAMPLE RULE: Give examples ONLY when the student is stuck or says "give me an example" — 2-3 alternatives, no automatic lists.
EFFICIENCY: One question. Sufficient answer → confirm and move on. Don't ask 2+ sub-questions in the same step.
ONE STEP: Don't move forward without confirmation; when confirmation comes, proceed immediately. If approved, do not engage in small talk.
SOURCE HINT: For "Why like this?" questions, one-sentence source: SIGNIFICANCE→KKV 1994:15 | QUESTION→Erdoğan 2021:51 | LITERATURE→KKV 1994:15-17. Not automatic.
PAUSE+STATUS: When a step ends: (1) "We've decided on X." (2) Fill STATUS field — DON'T leave '…' (3) Ask the next question. IF INDICATOR IS APPROVED, ASK NO MORE QUESTIONS.
TERMINATION RULE: When the indicator is approved, write ONE congratulatory sentence, fill out the STATUS field and append <TAMAMLANDI>. NEVER ask "what else would you add?" or loop the conversation.

Proceed in order:

1. TOPIC — an observable social phenomenon, aimed at "explanation" (not a solution).
   Question: "Who is affected by this phenomenon? Where can it be observed?"
   STATUS → Konsept: [3-6 words]

2. MOTIVATION — personal WHY; an emotion/experience, not an event/date.
   Bar: "Last week's match / saw it in the news" → INSUFFICIENT. "It bothered me because..." → SUFFICIENT.
   Question: "Why did you choose this topic? Was there a moment that touched you?"
   If insufficient → "How did this affect you personally?"
   STATUS → Motivasyon: [3-8 words]

3. SIGNIFICANCE (KKV Crit.1) — how many people does it affect, what does it change in their lives? (KKV: "significantly affects many people's lives")
   Bar: "Football federation and TV / could be useful" → INSUFFICIENT. Societal weight + concrete impact → SUFFICIENT.
   Question: "How many people does this topic affect and what kinds of concrete outcomes does it produce in their lives?"
   If insufficient → "Be more specific — how many people, what changes in their lives?"
   STATUS → Önem: [5-10 words]

4. LITERATURE (KKV Crit.2) — 1 approach + 1 gap ("X is known but Y is unknown").
   Question: "Who might have researched this topic? Which dimension is still unanswered?"
   Note: Don't make them memorize names, help them grasp the logic. If they don't know, suggest 2-3 approaches.
   STATUS → Literatür: [5-10 words]

5. QUESTION — an empirical, falsifiable, non-normative question asking how one factor affects another.
   Formal rules (Erdoğan 2021:51-52) — check before confirming:
     • No proper nouns: person/city/club names → convert to variable ("Fenerbahçe" → "rival team supporter")
     • Not normative: no "should / must"
   Question: "What kind of question would you write for this research?"
   If student writes one, check formal rules, correct together if needed — DON'T BE RIGID ABOUT FORMAT.
   STATUS → Soru: [full question — without proper nouns]

6. INDICATOR (Babbie 2007:124-133) — what makes the concept observable; DOESN'T HAVE TO BE NUMERICAL.
   Question: "What would you look at to observe this concept — what would you see that tells you this concept exists?"
   Note: DON'T give examples — if student asks, offer 2-3 alternatives (can be qualitative or quantitative).
   IMPORTANT: If indicator is approved NEVER engage in a feedback loop asking "what else?".
   STATUS → Gösterge: [indicator] + <TAMAMLANDI>

At the END of every response, ALWAYS include (fill confirmed ones, leave … for unconfirmed):
<DURUM>Konsept: … | Motivasyon: … | Önem: … | Literatür: … | Soru: … | Gösterge: …</DURUM>
"""

# ══════════════════════════════════════════════════════════════════
# PERSONAS  (internal key = TR, always)
# ══════════════════════════════════════════════════════════════════
PERSONAS = {
    "🌱 Destekleyici Mentor": {
        "prompt_tr": f"Sen sıcak, vizyon katan bir danışmansın; 'İlginç, peki şöyle düşünelim...' tarzında köprüler kurarsın. {BASE}",
        "prompt_en": f"You are a warm, vision-adding advisor; you build bridges in the style of 'Interesting, let's think about it this way...' {BASE_EN}",
        "label_en": "🌱 Supportive Mentor",
        "desc_tr": "Sıcak, cesaretlendirici. Basit fikirlere akademik vizyon katar.",
        "desc_en": "Warm, encouraging. Adds academic vision to simple ideas.",
    },
    "🎓 Dengeli Akademisyen": {
        "prompt_tr": f"Sen net ve standartları koruyan bir hocasın; KKV/Babbie'yi doğal olarak referans verirsin. {BASE}",
        "prompt_en": f"You are a clear, standards-maintaining instructor; you naturally reference KKV/Babbie. {BASE_EN}",
        "label_en": "🎓 Balanced Academic",
        "desc_tr": "Yapıcı ama titiz. KKV ve Babbie'yi doğrudan referans verir.",
        "desc_en": "Constructive but rigorous. Directly references KKV and Babbie.",
    },
    "😈 Şeytanın Avukatı": {
        "prompt_tr": f"Sen keskin sorularla zorlayan ama her zaman çıkış yolu gösteren bir eleştirmensin. {BASE}",
        "prompt_en": f"You are a critic who challenges with sharp questions but always shows a way out. {BASE_EN}",
        "label_en": "😈 Devil's Advocate",
        "desc_tr": "Zayıf noktaları açığa çıkarır — ama çıkış yolu gösterir.",
        "desc_en": "Exposes weak points — but shows the way out.",
    },
}

# ══════════════════════════════════════════════════════════════════
# UI STRINGS (TR / EN)
# ══════════════════════════════════════════════════════════════════
STRINGS = {
    "tr": {
        # Stage 0
        "hero_module":  "🎯 Modül 1 · KKV Gatekeeper",
        "hero_heading": "15 dakikada gerçek bir araştırma sorusu yaz.",
        "hero_body":    ("Kafandaki fikri bir AI danışmanıyla <b>6 adımda</b> akademik standartlarda "
                         "bir araştırma sorusuna dönüştüreceksin.<br>"
                         "Ne yapacağını bilmene gerek yok — sadece merak ettiğin bir şeyi söyle."),
        "hero_pills":   ["⏱ ~15 dakika", "📋 6 adım", "📄 PDF rapor", "💡 AI ile birlikte — AI'ye rağmen"],
        "choose_advisor": "**Danışmanını seç:**",
        "btn_selected": "✓ Seçildi",
        "btn_select":   "Seç",
        "btn_start":    "Başla →",
        # Stage 1
        "chat_input":   "Yanıtınızı yazın...",
        "thinking":     "*Düşünüyor...*",
        "err_timeout":  "⚠️ Zaman aşımı. Tekrar deneyin.",
        "err_quota":    "⚠️ API kotası doldu. Biraz bekleyin.",
        "opening":      ("Merhaba! 🎯 Seni rahatsız eden, merak uyandıran ya da anlamak istediğin "
                         "sosyal bir şey var mı? Tek cümleyle anlat — hiçbir konu çok sıradan ya da çok basit değil."),
        # Sidebar
        "sidebar_draft":       "### 📝 Araştırma Taslağın",
        "sidebar_empty":       "⬜ henüz belirlenmedi",
        "sidebar_steps_title": "📍 KKV Adımları",
        "sidebar_step_names":  ["Konu", "Motivasyon", "Önem", "Literatür", "Soru", "Gösterge"],
        "sidebar_advisor":     "Danışman",
        "session_label":       "📊 Oturum",
        "reset_btn":           "↺ Sıfırla",
        # Field display labels (for sidebar draft + Stage 2 draft + PDF)
        "field_labels": {
            "Konsept":    "Konsept",
            "Motivasyon": "Motivasyon",
            "Önem":       "Önem",
            "Literatür":  "Literatür",
            "Soru":       "Soru",
            "Gösterge":   "Gösterge",
        },
        # Milestone
        "milestone_names": {
            "Konsept":    "Konu",
            "Motivasyon": "Motivasyon",
            "Önem":       "Önem",
            "Literatür":  "Literatür",
            "Soru":       "Soru",
            "Gösterge":   "Gösterge",
        },
        "milestone_suffix": " 🚀 Araştırma sorum hazır!",
        "milestone_fmt":    "**{n}/6** ✅  {name} adımı tamamlandı{suffix}",
        # Stage 2
        "s2_banner":       "🎉 Modül 1 tamamlandı! KKV & Babbie standartlarında araştırma sorun hazır.",
        "s2_name_label":   "Ad Soyad",
        "s2_name_ph":      "Adını ve soyadını yaz",
        "s2_draft_title":  "📋 Araştırma Taslağın",
        "s2_refl_title":   "🪞 Refleksiyon",
        "s2_refl_caption": "Bu yanıtlar sınıf tartışması ve YZ kullanım beyanı için kullanılabilir.",
        "s2_learning_hdr": "Öğrenme Süreci",
        "s2_ai_hdr":       "YZ ile Çalışma",
        "r1_q":  "Hangi aşama seni en çok zorladı ve neden?",
        "r1_ph": "Örn: Gösterge — kavramın 'sonucu' değil 'varlığını' göstermek arasındaki farkı anlamak zordu.",
        "r2_q":  "Bu süreç olmadan araştırma sorusunu nasıl yazardın?",
        "r2_ph": "Örn: 'Futbol psikolojisi' derdim. Şimdi bağımlı/bağımsız değişkenim var.",
        "r3_q":  "YZ sana bu süreçte en çok neyi öğretti veya hangi yönde yönlendirdi?",
        "r3_ph": "Örn: Gösterge kavramını anlamamı sağladı — 'kavramın sonucunu değil varlığını ölç' mantığını oturttu.",
        "r4_q":  "Bu konuyu araştırmak için bir dahaki sefere YZ'ye nasıl soru sorardın?",
        "r4_ph": "Örn: Direkt 'bağımsız değişkenim ne olabilir?' diye sorardım.",
        "pdf_btn":      "📥 PDF Olarak İndir",
        "txt_btn":      "📄 TXT Olarak İndir",
        "pdf_err":      "PDF oluşturulamadı",
        "submit_note":  "⬆️ Bu PDF'i ödeve ek olarak yükle.",
        # PDF strings
        "pdf_title":      "Research Architect  ·  Modül 1: KKV Gatekeeper",
        "pdf_meta":       "Danışman: {advisor}     |     Tarih: {date}",
        "pdf_sec_draft":  "ARAŞTIRMA TASLAGI",
        "pdf_sec_ai":     "YZ İLE ÇALIŞMA",
        "pdf_ai_learned": "YZ'den öğrendiklerim",
        "pdf_ai_next":    "Bir dahaki sefere nasıl kullanırım",
        "pdf_sec_refl":   "ÖĞRENME SÜRECİ REFLEKSİYONU",
        "pdf_refl_hard":  "En çok zorlayan aşama",
        "pdf_refl_before":"Süreç öncesi vs. sonrası",
        "pdf_sec_chat":   "SOHBET GÜNLÜĞÜ",
        "pdf_advisor":    "Danışman",
        "pdf_student":    "Öğrenci",
        "pdf_date":       "Tarih",
        # PDF sayfa 1 — DEĞERLENDİRME tablosu
        "pdf_sec_question":  "ARAŞTIRMA SORUSU",
        "pdf_rubric_title":  "DEĞERLENDİRME — YZ KULLANIMI",
        "pdf_rubric_guide":  "1 = Yüzeysel  |  2 = Gelişiyor  |  3 = Derinlikli     Toplam: ___ / 6",
        "pdf_rubric_r3":     "YZ'den öğrenme derinliği  (r3)",
        "pdf_rubric_r4":     "Sonraki kullanım farkındalığı  (r4)",
        "pdf_rubric_total":  "Toplam:  ___ / 6",
        "pdf_rubric_note":   "Not: ___________",
        # TXT
        "txt_header":  "MODÜL 1 — KKV GATEKEEPER",
        "txt_advisor": "Danışman",
        "txt_draft":   "ARAŞTIRMA TASLAK",
        "txt_chat":    "SOHBET GÜNLÜĞÜ",
        "txt_refl":    "REFLEKSİYON",
        "txt_learning":"[Öğrenme Süreci]",
        "txt_r1":      "1. En çok zorlayan aşama",
        "txt_r2":      "2. Süreç öncesi vs. sonrası",
        "txt_ai":      "[YZ ile Çalışma]",
        "txt_r3":      "3. YZ'den öğrendiklerim",
        "txt_r4":      "4. Bir dahaki sefere nasıl kullanırım",
        # Refleksiyon — sıralı adım
        "refl_continue_btn": "İlerle →",
        "refl_done_msg":     "✅ Harika! Tüm refleksiyonları tamamladın.",
        # Attribution
        "attr_caption":      "IR342 · Araştırma Laboratuvarı · Emre Erdoğan · İstanbul Bilgi Üniversitesi",
        "pdf_footer_attr":   "IR342 · Emre Erdoğan · İstanbul Bilgi Üniversitesi",
    },
    "en": {
        # Stage 0
        "hero_module":  "🎯 Module 1 · KKV Gatekeeper",
        "hero_heading": "Write a real research question in 15 minutes.",
        "hero_body":    ("You'll turn your idea into an academically sound research question in "
                         "<b>6 steps</b> with an AI advisor.<br>"
                         "You don't need to know what to do — just share something you're curious about."),
        "hero_pills":   ["⏱ ~15 minutes", "📋 6 steps", "📄 PDF report", "💡 With AI — not despite it"],
        "choose_advisor": "**Choose your advisor:**",
        "btn_selected": "✓ Selected",
        "btn_select":   "Select",
        "btn_start":    "Start →",
        # Stage 1
        "chat_input":   "Type your answer...",
        "thinking":     "*Thinking...*",
        "err_timeout":  "⚠️ Timeout. Please try again.",
        "err_quota":    "⚠️ API quota exceeded. Please wait.",
        "opening":      ("Hello! 🎯 Is there something social that bothers you, makes you curious, "
                         "or that you want to understand? Tell me in one sentence — "
                         "no topic is too ordinary or too simple."),
        # Sidebar
        "sidebar_draft":       "### 📝 Your Research Draft",
        "sidebar_empty":       "⬜ not yet defined",
        "sidebar_steps_title": "📍 KKV Steps",
        "sidebar_step_names":  ["Topic", "Motivation", "Significance", "Literature", "Question", "Indicator"],
        "sidebar_advisor":     "Advisor",
        "session_label":       "📊 Session",
        "reset_btn":           "↺ Reset",
        # Field display labels
        "field_labels": {
            "Konsept":    "Topic",
            "Motivasyon": "Motivation",
            "Önem":       "Significance",
            "Literatür":  "Literature",
            "Soru":       "Question",
            "Gösterge":   "Indicator",
        },
        # Milestone
        "milestone_names": {
            "Konsept":    "Topic",
            "Motivasyon": "Motivation",
            "Önem":       "Significance",
            "Literatür":  "Literature",
            "Soru":       "Question",
            "Gösterge":   "Indicator",
        },
        "milestone_suffix": " 🚀 My research question is ready!",
        "milestone_fmt":    "**{n}/6** ✅  {name} step completed{suffix}",
        # Stage 2
        "s2_banner":       "🎉 Module 1 complete! Your research question meets KKV & Babbie standards.",
        "s2_name_label":   "Full Name",
        "s2_name_ph":      "Enter your first and last name",
        "s2_draft_title":  "📋 Your Research Draft",
        "s2_refl_title":   "🪞 Reflection",
        "s2_refl_caption": "Your answers may be used for class discussion and AI usage disclosure.",
        "s2_learning_hdr": "Learning Process",
        "s2_ai_hdr":       "Working with AI",
        "r1_q":  "Which step challenged you the most and why?",
        "r1_ph": "E.g.: Indicator — understanding the difference between measuring 'existence' vs 'outcome' of a concept was hard.",
        "r2_q":  "How would you have written the research question without this process?",
        "r2_ph": "E.g.: I would have said 'football psychology'. Now I have dependent and independent variables.",
        "r3_q":  "What did AI teach you or guide you toward most in this process?",
        "r3_ph": "E.g.: It helped me understand the indicator concept — it settled the logic of 'measure existence, not outcome'.",
        "r4_q":  "How would you prompt AI differently next time you research this topic?",
        "r4_ph": "E.g.: I'd directly ask 'what could my independent variable be?' Instead of narrowing the topic myself, I'd consult AI first.",
        "pdf_btn":      "📥 Download as PDF",
        "txt_btn":      "📄 Download as TXT",
        "pdf_err":      "Could not create PDF",
        "submit_note":  "⬆️ Attach this PDF to your assignment.",
        # PDF strings
        "pdf_title":      "Research Architect  ·  Module 1: KKV Gatekeeper",
        "pdf_meta":       "Advisor: {advisor}     |     Date: {date}",
        "pdf_sec_draft":  "RESEARCH DRAFT",
        "pdf_sec_ai":     "WORKING WITH AI",
        "pdf_ai_learned": "What I learned from AI",
        "pdf_ai_next":    "How I'll use it next time",
        "pdf_sec_refl":   "LEARNING PROCESS REFLECTION",
        "pdf_refl_hard":  "Most challenging step",
        "pdf_refl_before":"Before vs. after the process",
        "pdf_sec_chat":   "CHAT LOG",
        "pdf_advisor":    "Advisor",
        "pdf_student":    "Student",
        "pdf_date":       "Date",
        # PDF page 1 — ASSESSMENT table
        "pdf_sec_question":  "RESEARCH QUESTION",
        "pdf_rubric_title":  "ASSESSMENT — AI USAGE",
        "pdf_rubric_guide":  "1 = Superficial  |  2 = Developing  |  3 = Deep     Total: ___ / 6",
        "pdf_rubric_r3":     "Depth of learning from AI  (r3)",
        "pdf_rubric_r4":     "Next-use awareness  (r4)",
        "pdf_rubric_total":  "Total:  ___ / 6",
        "pdf_rubric_note":   "Grade: ___________",
        # TXT
        "txt_header":  "MODULE 1 — KKV GATEKEEPER",
        "txt_advisor": "Advisor",
        "txt_draft":   "RESEARCH DRAFT",
        "txt_chat":    "CHAT LOG",
        "txt_refl":    "REFLECTION",
        "txt_learning":"[Learning Process]",
        "txt_r1":      "1. Most challenging step",
        "txt_r2":      "2. Before vs. after",
        "txt_ai":      "[Working with AI]",
        "txt_r3":      "3. What I learned from AI",
        "txt_r4":      "4. How I'll prompt differently next time",
        # Reflection — sequential step
        "refl_continue_btn": "Continue →",
        "refl_done_msg":     "✅ Great! You've completed all reflections.",
        # Attribution
        "attr_caption":      "IR342 · Research Lab · Emre Erdoğan · Istanbul Bilgi University",
        "pdf_footer_attr":   "IR342 · Emre Erdoğan · Istanbul Bilgi University",
    },
}

# ══════════════════════════════════════════════════════════════════
def get_model(persona_prompt):
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=API_KEY,
    )
    return client, persona_prompt

# ══════════════════════════════════════════════════════════════════
# SESSION STATE
# ══════════════════════════════════════════════════════════════════
DURUM_ALANLARI = ["Konsept", "Motivasyon", "Önem", "Literatür", "Soru", "Gösterge"]

for k, v in {
    "lang":                 "tr",
    "stage":                0,
    "display_history":      [],
    "api_history":          [],
    "taslak_raw":           "",
    "taslak_dict":          {a: "" for a in DURUM_ALANLARI},
    "selected":             None,
    "total_prompt_tokens":  0,
    "total_output_tokens":  0,
    "total_turns":          0,
    "balloons_shown":       False,
    "student_name":         "",
    "refl_step":            0,
    "pdf_session_id":       "",
    "r1_val": "", "r2_val": "", "r3_val": "", "r4_val": "",
    "local_log_saved":      False,
    "sheets_log_saved":     False,
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ══════════════════════════════════════════════════════════════════
# TASLAK PARSE
# ══════════════════════════════════════════════════════════════════
def parse_taslak(raw: str) -> dict:
    result = {a: "" for a in DURUM_ALANLARI}
    for part in raw.split("|"):
        part = part.strip()
        if ":" in part:
            key, _, val = part.partition(":")
            key = key.strip(); val = val.strip()
            if key in result and val and val not in ("…", "—", "..."):
                result[key] = val
    return result

# ══════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════
def stream(model_info, messages):
    client, persona_prompt = model_info
    
    oai_messages = [{"role": "system", "content": persona_prompt}]
    for m in messages:
        role = "assistant" if m["role"] == "model" else m["role"]
        content = m["parts"][0] if isinstance(m.get("parts"), list) else m.get("content", "")
        oai_messages.append({"role": role, "content": content})

    return client.chat.completions.create(
        model=MODEL_NAME,
        messages=oai_messages,
        temperature=0.6,
        max_tokens=600,
        stream=True,
        timeout=60,
        stream_options={"include_usage": True},
        extra_headers={"HTTP-Referer": "http://localhost:8501", "X-Title": "Research Assistant"}
    )

def get_current_step_reminder(taslak_dict, lang="tr"):
    td = taslak_dict
    if lang == "en":
        steps = [
            (not td.get("Konsept"),    "STEP:1/TOPIC — Fill Concept, don't move on."),
            (not td.get("Motivasyon"), "STEP:2/MOTIVATION — Personal connection. Fill Motivation, don't move on."),
            (not td.get("Önem"),       "STEP:3/SIGNIFICANCE — Concrete impact. Fill Significance, don't move on."),
            (not td.get("Literatür"),  "STEP:4/LITERATURE — Approach+gap. Fill Literature, don't move on."),
            (not td.get("Soru"),       "STEP:5/QUESTION — Empirical question. Fill Question, don't move on."),
        ]
        fallback = "STEP:6/INDICATOR — Observable entity. Fill Indicator."
    else:
        steps = [
            (not td.get("Konsept"),    "ADİM:1/KONU — Konsept'i doldur, geçme."),
            (not td.get("Motivasyon"), "ADİM:2/MOTİVASYON — Kişisel bağ. Motivasyon'u doldur, geçme."),
            (not td.get("Önem"),       "ADİM:3/ÖNEM — Somut aktör+eylem. Önem'i doldur, geçme."),
            (not td.get("Literatür"),  "ADİM:4/LİTERATÜR — Yaklaşım+boşluk. Literatür'ü doldur, geçme."),
            (not td.get("Soru"),       "ADİM:5/SORU — X→Y ampirik soru. Soru'yu doldur, geçme."),
        ]
        fallback = "ADİM:6/GÖSTERGE — Sayılabilir varlık. Gösterge'yi doldur."
    for cond, msg in steps:
        if cond:
            return msg
    return fallback

def build_messages(api_history, taslak_raw, taslak_dict, lang="tr"):
    recent    = api_history[-4:] if len(api_history) > 4 else api_history
    step_hint = get_current_step_reminder(taslak_dict, lang)
    if lang == "en":
        q1 = "What have we decided so far and which step am I on?"
        q2 = "Which step am I on now?"
        durum_note = (
            "MANDATORY REMINDER: end EVERY response with the full status tag — "
            "<DURUM>Konsept: … | Motivasyon: … | Önem: … | Literatür: … | Soru: … | Gösterge: …</DURUM> "
            "Fill confirmed fields with their values; use … only for unconfirmed fields. Never skip this tag."
        )
    else:
        q1 = "Şu ana kadar ne kararlaştırdık ve şu an hangi adımdayım?"
        q2 = "Hangi adımdayım şu an?"
        durum_note = (
            "ZORUNLU HATIRLATMA: her yanıtının SONUNA tam durum etiketini ekle — "
            "<DURUM>Konsept: … | Motivasyon: … | Önem: … | Literatür: … | Soru: … | Gösterge: …</DURUM> "
            "Onaylanan alanları değerleriyle doldur; onaylanmamışları … bırak. Bu etiketi ASLA atlama."
        )
    if taslak_raw:
        memo = [
            {"role": "user",  "parts": [q1]},
            {"role": "model", "parts": [f"<DURUM>{taslak_raw}</DURUM>\n{step_hint}"]},
            {"role": "user",  "parts": [durum_note]},
            {"role": "model", "parts": ["Anlaşıldı, her yanıtımın sonuna DURUM etiketini ekleyeceğim." if lang == "tr" else "Understood, I will append the DURUM tag to every response."]},
        ]
    else:
        memo = [
            {"role": "user",  "parts": [q2]},
            {"role": "model", "parts": [step_hint]},
            {"role": "user",  "parts": [durum_note]},
            {"role": "model", "parts": ["Anlaşıldı, her yanıtımın sonuna DURUM etiketini ekleyeceğim." if lang == "tr" else "Understood, I will append the DURUM tag to every response."]},
        ]
    return memo + recent

# ══════════════════════════════════════════════════════════════════
# GOOGLE SHEETS
# ══════════════════════════════════════════════════════════════════
SHEETS_HEADER = [
    "Tarih", "Danışman", "Dil", "Tur", "P.Token", "O.Token", "Toplam", "Maliyet",
    "Konsept", "Motivasyon", "Önem", "Literatür", "Soru", "Gösterge",
    "YZ_Öğrenme", "YZ_SonrakiKullanım", "Not1", "Not2", "Not3",
]

@st.cache_resource
def get_sheet():
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

def log_session(taslak_dict, selected, lang, turns, pt, ot, r3="", r4=""):
    """Tamamlanan oturumu Google Sheets'e yazar (YZ yanıtları dahil)."""
    sheet, conn_err = get_sheet()
    if sheet is None:
        st.session_state.sheets_error = f"Bağlantı hatası: {conn_err}"
        return
    try:
        # Auto-header: sheet boşsa başlık satırı ekle
        existing = sheet.get_all_values()
        if not existing:
            sheet.append_row(SHEETS_HEADER, value_input_option="USER_ENTERED")

        maliyet = round((pt * 0.075 + ot * 0.30) / 1_000_000, 6)
        row = [
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            selected,
            lang,
            turns,
            pt, ot, pt + ot, maliyet,
            taslak_dict.get("Konsept",    "—"),
            taslak_dict.get("Motivasyon", "—")[:100],
            taslak_dict.get("Önem",       "—")[:100],
            taslak_dict.get("Literatür",  "—")[:100],
            taslak_dict.get("Soru",       "—")[:150],
            taslak_dict.get("Gösterge",   "—")[:100],
            (r3 or "—")[:200],   # YZ_Öğrenme
            (r4 or "—")[:200],   # YZ_SonrakiKullanım
            "", "", "",           # Not1, Not2, Not3 (hoca doldurur)
        ]
        sheet.append_row(row, value_input_option="USER_ENTERED")
        st.session_state.sheets_error = ""
    except Exception as e:
        st.session_state.sheets_error = str(e)[:300]

def log_to_file(data: dict):
    """Oturum verisini yerel sessions.jsonl dosyasına ekler. Hata varsa sessizce atlar."""
    try:
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "sessions.jsonl")
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(data, ensure_ascii=False) + "\n")
    except Exception:
        pass  # Log hatası uygulamayı durdurmasın

# ══════════════════════════════════════════════════════════════════
# PDF OLUŞTURUCU
# ══════════════════════════════════════════════════════════════════
class ResearchPDF(FPDF):
    """FPDF alt sınıfı — her sayfanın altına attribution + session damgası ekler."""
    _footer_attr: str = ""
    _session_id:  str = ""

    def footer(self):
        self.set_y(-13)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(160, 160, 160)
        self.cell(145, 5, self._footer_attr, align="L")
        self.cell(0,   5, f"#{self._session_id}", align="R")


def build_pdf(selected, taslak_dict, display_history, r1, r2, r3, r4,
              lang="tr", student_name="", session_id=""):
    S = STRINGS[lang]
    pdf = ResearchPDF(orientation="P", unit="mm", format="A4")
    pdf._footer_attr = S.get("pdf_footer_attr", "IR342 · Emre Erdoğan")
    pdf._session_id  = session_id if session_id else "--------"
    pdf.set_margins(20, 20, 20)
    pdf.set_auto_page_break(auto=True, margin=22)

    _dir = os.path.dirname(os.path.abspath(__file__))
    font_paths = [
        (os.path.join(_dir, "fonts", "DejaVuSans.ttf"),
         os.path.join(_dir, "fonts", "DejaVuSans-Bold.ttf")),
        (r"C:\Windows\Fonts\arial.ttf",   r"C:\Windows\Fonts\arialbd.ttf"),
        (r"C:\Windows\Fonts\calibri.ttf", r"C:\Windows\Fonts\calibrib.ttf"),
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
    G  = (46, 125, 50)
    LG = (232, 245, 233)
    GR = (248, 249, 250)
    DG = (100, 100, 100)
    BL = (30, 30, 30)

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

    def big_field(label, value):
        """Araştırma sorusu için daha büyük kutu."""
        pdf.set_text_color(*DG)
        pdf.set_font(f, "B", 8)
        pdf.cell(0, 5, label.upper(), new_x="LMARGIN", new_y="NEXT")
        pdf.set_fill_color(*LG)
        pdf.set_text_color(*BL)
        pdf.set_font(f, "B", 11)
        pdf.multi_cell(0, 8, value or "—", fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

    field_labels = S["field_labels"]

    # ══════════════════════════════════════════════════════════════
    # SAYFA 1 — Değerlendirme Sayfası (hoca için)
    # ══════════════════════════════════════════════════════════════
    pdf.add_page()

    # Başlık bandı
    pdf.set_fill_color(*G)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font(f, "B", 13)
    pdf.cell(0, 13, S["pdf_title"], fill=True, align="C", new_x="LMARGIN", new_y="NEXT")

    # Meta: Öğrenci | Danışman | Tarih
    name_display = student_name.strip() if student_name else "—"
    meta_line = (
        f"{S['pdf_student']}: {name_display}     |     "
        f"{S['pdf_advisor']}: {selected}     |     "
        f"{S['pdf_date']}: {tarih}"
    )
    pdf.set_fill_color(*LG)
    pdf.set_text_color(*DG)
    pdf.set_font(f, "", 9)
    pdf.cell(0, 7, meta_line, fill=True, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    # Araştırma Sorusu (büyük kutu)
    section_header(S["pdf_sec_question"])
    big_field(
        field_labels.get("Soru", "Soru"),
        taslak_dict.get("Soru", "") or "—",
    )

    # YZ ile Çalışma (r3 + r4)
    pdf.ln(2)
    section_header(S["pdf_sec_ai"])
    field(S["pdf_ai_learned"], r3)
    field(S["pdf_ai_next"],    r4)

    # DEĞERLENDİRME — Rubrik tablosu (hoca dolduracak)
    pdf.ln(4)
    rw = 131   # kriter sütunu genişliği
    sc = 13    # puan sütunu genişliği (3 × 13 = 39, toplam 170 mm)

    # Başlık satırı
    pdf.set_fill_color(*G)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font(f, "B", 9)
    pdf.cell(rw + sc * 3, 7, S["pdf_rubric_title"], border=1, fill=True, align="C")
    pdf.ln()

    # Ölçek kılavuzu satırı
    pdf.set_fill_color(*LG)
    pdf.set_text_color(*DG)
    pdf.set_font(f, "", 8)
    pdf.cell(rw + sc * 3, 5, S["pdf_rubric_guide"], border=1, fill=True, align="C")
    pdf.ln()

    # Sütun başlıkları (boş | 1 | 2 | 3)
    pdf.set_fill_color(220, 230, 220)
    pdf.set_text_color(*BL)
    pdf.set_font(f, "B", 9)
    pdf.cell(rw, 6, "", border=1, fill=True)
    for s_lbl in ["1", "2", "3"]:
        pdf.cell(sc, 6, s_lbl, border=1, fill=True, align="C")
    pdf.ln()

    # Kriter satırları
    pdf.set_fill_color(255, 255, 255)
    pdf.set_text_color(*BL)
    pdf.set_font(f, "", 8)
    for crit in [S["pdf_rubric_r3"], S["pdf_rubric_r4"]]:
        pdf.cell(rw, 8, crit, border=1)
        for _ in range(3):
            pdf.cell(sc, 8, "", border=1, align="C")
        pdf.ln()

    # Toplam / Not satırı
    pdf.set_fill_color(*LG)
    pdf.set_font(f, "B", 9)
    pdf.cell(85, 7, f"  {S['pdf_rubric_total']}", border=1, fill=True)
    pdf.cell(85, 7, f"  {S['pdf_rubric_note']}", border=1, fill=True)
    pdf.ln()

    # ══════════════════════════════════════════════════════════════
    # SAYFA 2+ — Süreç Belgesi (arşiv)
    # ══════════════════════════════════════════════════════════════
    pdf.add_page()

    # 6 adım taslağı (tamamı)
    section_header(S["pdf_sec_draft"])
    for alan in DURUM_ALANLARI:
        field(field_labels.get(alan, alan), taslak_dict.get(alan, "") or "—")

    pdf.ln(2)

    # Öğrenme süreci refleksiyonu (r1 + r2)
    section_header(S["pdf_sec_refl"])
    field(S["pdf_refl_hard"],   r1)
    field(S["pdf_refl_before"], r2)
    pdf.ln(4)

    # Sohbet günlüğü
    section_header(S["pdf_sec_chat"])
    for msg in display_history:
        if msg.get("role") == "milestone":
            continue
        role_label = S["pdf_advisor"] if msg["role"] == "assistant" else S["pdf_student"]
        pdf.set_text_color(*DG)
        pdf.set_font(f, "B", 8)
        pdf.cell(0, 5, f"[{role_label}]", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(*BL)
        pdf.set_font(f, "", 9)
        pdf.multi_cell(0, 5, msg["content"], new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    return bytes(pdf.output())

# ══════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════
with st.sidebar:
    lang = st.session_state.get("lang", "tr")
    S    = STRINGS[lang]

    st.markdown(S["sidebar_draft"])
    td = st.session_state.taslak_dict
    field_labels = S["field_labels"]

    for alan in DURUM_ALANLARI:
        display_name = field_labels.get(alan, alan)
        deger = td.get(alan, "")
        if deger:
            st.markdown(
                f"<div style='margin-bottom:8px;'>"
                f"<span style='font-size:.75em;color:#666;text-transform:uppercase;letter-spacing:.05em;'>{display_name}</span><br>"
                f"<span style='font-size:.88em;color:#1e1e1e;'>✅ {deger}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"<div style='margin-bottom:8px;opacity:.45;'>"
                f"<span style='font-size:.75em;text-transform:uppercase;letter-spacing:.05em;'>{display_name}</span><br>"
                f"<span style='font-size:.88em;'>{S['sidebar_empty']}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

    # 6 adım ilerleme göstergesi (yalnız Stage 1'de)
    if st.session_state.stage == 1:
        st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)
        step_names = S["sidebar_step_names"]
        adimlar = [(step_names[i], bool(td.get(DURUM_ALANLARI[i]))) for i in range(6)]
        current = next((i for i, (_, v) in enumerate(adimlar) if not v), len(adimlar))
        n_done  = sum(1 for _, v in adimlar if v)
        st.markdown(
            f"<p style='font-size:.72em;color:#666;font-weight:600;"
            f"text-transform:uppercase;letter-spacing:.05em;margin:0 0 4px 0;'>"
            f"{S['sidebar_steps_title']}</p>",
            unsafe_allow_html=True,
        )
        rows = ""
        for i, (ad, done) in enumerate(adimlar):
            if done:
                icon, color, weight = "✅", "#2e7d32", "normal"
            elif i == current:
                icon, color, weight = "▶", "#1565c0", "600"
            else:
                icon, color, weight = "⬜", "#bbb", "normal"
            rows += (
                f"<div style='font-size:.80em;color:{color};font-weight:{weight};"
                f"margin-bottom:2px;'>{icon} {i+1}. {ad}</div>"
            )
        st.markdown(rows, unsafe_allow_html=True)
        st.progress(n_done / len(adimlar))

    st.divider()
    if st.session_state.selected:
        pname = st.session_state.selected
        display = PERSONAS[pname]["label_en"] if lang == "en" else pname
        st.caption(f"{S['sidebar_advisor']}: **{display}**")

    # Token istatistikleri
    pt = st.session_state.total_prompt_tokens
    ot = st.session_state.total_output_tokens
    if pt or ot:
        toplam  = pt + ot
        maliyet = (pt * 0.075 + ot * 0.30) / 1_000_000
        st.markdown(
            f"<div style='font-size:.75em;color:#666;margin-top:4px;'>"
            f"<b>{S['session_label']}</b><br>"
            f"Tur: {st.session_state.total_turns} &nbsp;·&nbsp; "
            f"Toplam: {toplam:,} token<br>"
            f"Gönderilen: {pt:,} &nbsp;·&nbsp; Alınan: {ot:,}<br>"
            f"<span style='color:#2e7d32;'>~${maliyet:.5f}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    st.divider()
    if st.button(S["reset_btn"]):
        st.session_state.clear()
        st.rerun()

# ══════════════════════════════════════════════════════════════════
# ANA EKRAN
# ══════════════════════════════════════════════════════════════════
lang = st.session_state.get("lang", "tr")
S    = STRINGS[lang]

# ── ADMIN LOG PANELİ (yalnızca eğitmen) ──────────────────────────
_ADMIN_PW    = os.getenv("ADMIN_PASSWORD", "")
_admin_param = st.query_params.get("admin", "")
if _ADMIN_PW and _admin_param == _ADMIN_PW:
    st.title("📊 Oturum Logları — IR342")
    st.caption("Bu sayfa yalnızca eğitmene görünür · Research Architect")
    import pandas as _pd

    # ── Önce Google Sheets'ten oku (Streamlit Cloud için kalıcı) ──
    _sheet, _sheet_err = get_sheet()
    if _sheet is not None:
        try:
            _all = _sheet.get_all_values()
            if len(_all) > 1:
                _df = _pd.DataFrame(_all[1:], columns=_all[0])
                st.success(f"✅ {len(_df)} oturum kaydı · Google Sheets")
                st.dataframe(_df, use_container_width=True)
                _csv = _df.to_csv(index=False).encode("utf-8")
                st.download_button("⬇️ CSV İndir", _csv, "sessions.csv", "text/csv")
            else:
                st.info("Google Sheets'te henüz kayıt yok.")
        except Exception as _e:
            st.error(f"Sheets okuma hatası: {_e}")
    else:
        # ── Fallback: yerel JSONL (lokal ortam) ───────────────────
        _log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "sessions.jsonl")
        if os.path.exists(_log_path):
            _rows = []
            with open(_log_path, encoding="utf-8") as _fh:
                for _line in _fh:
                    _line = _line.strip()
                    if _line:
                        try:
                            _rows.append(json.loads(_line))
                        except Exception:
                            pass
            if _rows:
                _df = _pd.DataFrame(_rows)
                st.success(f"✅ {len(_df)} oturum kaydı · Yerel log")
                st.dataframe(_df, use_container_width=True)
                _csv = _df.to_csv(index=False).encode("utf-8")
                st.download_button("⬇️ CSV İndir", _csv, "sessions.csv", "text/csv")
            else:
                st.info("Henüz kayıt yok.")
        else:
            st.info("Kayıt bulunamadı. Google Sheets yapılandırılmamış ve yerel log dosyası yok.")
        if _sheet_err:
            st.caption(f"ℹ️ Google Sheets bağlantısı yok: {_sheet_err}")
    st.stop()

# ── STAGE 0: Persona + Dil seçimi ────────────────────────────────
if st.session_state.stage == 0:

    # Dil toggle (sağ üst köşe)
    tc1, tc2 = st.columns([5, 1])
    with tc2:
        lang_opts = ["🇹🇷 Türkçe", "🇬🇧 English"]
        lang_choice = st.radio(
            "Language",
            lang_opts,
            index=1 if st.session_state.lang == "en" else 0,
            horizontal=True,
            label_visibility="collapsed",
            key="lang_radio",
        )
        new_lang = "en" if "English" in lang_choice else "tr"
        if new_lang != st.session_state.lang:
            st.session_state.lang = new_lang
            st.rerun()

    # Hero banner
    pills_html = "".join(
        f"<span style='font-size:.82em;color:#555;background:rgba(255,255,255,.7);"
        f"padding:4px 10px;border-radius:20px;'>{p}</span>"
        for p in S["hero_pills"]
    )
    st.markdown(f"""
    <div style='background:linear-gradient(135deg,#e8f5e9 0%,#f0f4ff 100%);
    border-radius:16px;padding:28px 32px;margin-bottom:24px;'>
      <div style='font-size:.85em;color:#2e7d32;font-weight:700;
      text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px;'>
      {S["hero_module"]}</div>
      <div style='font-size:1.55em;font-weight:700;color:#1a1a1a;
      line-height:1.3;margin-bottom:10px;'>
      {S["hero_heading"]}</div>
      <div style='font-size:.93em;color:#444;margin-bottom:18px;line-height:1.6;'>
      {S["hero_body"]}
      </div>
      <div style='display:flex;gap:20px;flex-wrap:wrap;'>
        {pills_html}
      </div>
    </div>
    """, unsafe_allow_html=True)
    st.caption(S["attr_caption"])

    st.markdown(S["choose_advisor"])
    st.markdown("<br>", unsafe_allow_html=True)

    cols = st.columns(3)
    persona_secimi = st.session_state.get("_secim", list(PERSONAS.keys())[0])

    for i, (isim, bilgi) in enumerate(PERSONAS.items()):
        with cols[i]:
            secili = (persona_secimi == isim)
            border_color = "#2e7d32" if secili else "#dee2e6"
            bg_color     = "#f0f7f0" if secili else "#ffffff"
            label   = bilgi["label_en"] if lang == "en" else isim
            desc    = bilgi["desc_en"]  if lang == "en" else bilgi["desc_tr"]
            emoji   = isim.split()[0]
            name    = " ".join(label.split()[1:])
            st.markdown(
                f"""<div style='border:2px solid {border_color};background:{bg_color};
                border-radius:12px;padding:18px;min-height:130px;cursor:pointer;
                transition:all .2s;'>
                <div style='font-size:1.6em;margin-bottom:6px;'>{emoji}</div>
                <div style='font-weight:600;margin-bottom:6px;font-size:.95em;'>{name}</div>
                <div style='font-size:.82em;color:#555;'>{desc}</div>
                </div>""",
                unsafe_allow_html=True,
            )
            btn_label = S["btn_selected"] if secili else S["btn_select"]
            if st.button(btn_label, key=f"btn_{i}", type="secondary", use_container_width=True):
                st.session_state["_secim"] = isim
                st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    secilen = st.session_state.get("_secim", list(PERSONAS.keys())[0])
    if st.button(S["btn_start"], type="primary"):
        st.session_state.selected = secilen
        ilk = S["opening"]
        st.session_state.display_history.append({"role": "assistant", "content": ilk})
        st.session_state.api_history = [
            {"role": "user",  "parts": ["Başlamak istiyorum." if lang == "tr" else "I want to start."]},
            {"role": "model", "parts": [ilk]},
        ]
        st.session_state.stage = 1
        st.rerun()

# ── STAGE 1: Sohbet ───────────────────────────────────────────────
elif st.session_state.stage == 1:
    for msg in st.session_state.display_history:
        if msg.get("role") == "milestone":
            st.success(msg["content"])
        else:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    user_input = st.chat_input(S["chat_input"])

    if user_input:
        st.session_state.display_history.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        st.session_state.api_history.append({"role": "user", "parts": [user_input]})

        with st.chat_message("assistant"):
            placeholder = st.empty()
            thinking    = st.empty()
            thinking.markdown(S["thinking"])
            full_text = ""
            ok = True

            try:
                prompt_key = "prompt_en" if lang == "en" else "prompt_tr"
                model    = get_model(PERSONAS[st.session_state.selected][prompt_key])
                messages = build_messages(
                    st.session_state.api_history,
                    st.session_state.taslak_raw,
                    st.session_state.taslak_dict,
                    lang,
                )
                response = stream(model, messages)

                prompt_tokens_used = 0
                output_tokens_used = 0
                for chunk in response:
                    if getattr(chunk, 'usage', None):
                        prompt_tokens_used = chunk.usage.prompt_tokens
                        output_tokens_used = chunk.usage.completion_tokens
                    if getattr(chunk, 'choices', None) and len(chunk.choices) > 0 and chunk.choices[0].delta.content:
                        thinking.empty()
                        full_text += chunk.choices[0].delta.content
                        # Tekrar döngüsü algılama
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
                    st.session_state.total_prompt_tokens  += prompt_tokens_used or 0
                    st.session_state.total_output_tokens  += output_tokens_used or 0
                    st.session_state.total_turns          += 1
                except Exception:
                    pass

                # DURUM → sidebar + milestone kutlaması
                m = re.search(r'<DURUM>(.*?)</DURUM>', full_text, re.DOTALL)
                if m:
                    raw      = m.group(1).strip().replace("\n", " ")
                    old_dict = dict(st.session_state.taslak_dict)
                    new_dict = parse_taslak(raw)
                    st.session_state.taslak_raw  = raw
                    st.session_state.taslak_dict = new_dict
                    milestone_names = S["milestone_names"]
                    for alan in DURUM_ALANLARI:
                        if new_dict.get(alan) and not old_dict.get(alan):
                            n_done = sum(1 for a in DURUM_ALANLARI if new_dict.get(a))
                            suffix = S["milestone_suffix"] if alan == "Gösterge" else ""
                            kutlama = S["milestone_fmt"].format(
                                n=n_done, name=milestone_names[alan], suffix=suffix
                            )
                            st.session_state.display_history.append(
                                {"role": "milestone", "content": kutlama}
                            )

                clean = re.sub(r'<DURUM>.*?</DURUM>', '', full_text, flags=re.DOTALL)
                clean = clean.replace('<TAMAMLANDI>', '').strip()
                placeholder.markdown(clean)

            except Exception as e:
                ok  = False
                err = str(e)
                if st.session_state.api_history and st.session_state.api_history[-1]["role"] == "user":
                    st.session_state.api_history.pop()
                if st.session_state.display_history and st.session_state.display_history[-1]["role"] == "user":
                    st.session_state.display_history.pop()
                if "timeout" in err.lower():
                    placeholder.warning(S["err_timeout"])
                elif "429" in err or "quota" in err.lower():
                    placeholder.warning(S["err_quota"])
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

    # PDF damgası için session ID — bir kez üret
    if not st.session_state.get("pdf_session_id"):
        st.session_state["pdf_session_id"] = uuid.uuid4().hex[:8].upper()

    # Konfeti yalnızca bir kez
    if not st.session_state.balloons_shown:
        st.balloons()
        st.session_state.balloons_shown = True

    st.success(S["s2_banner"])

    # ── Öğrenci Adı ───────────────────────────────────────────────
    name_col, _ = st.columns([2, 3])
    with name_col:
        sname = st.text_input(
            S["s2_name_label"],
            value=st.session_state.get("student_name", ""),
            placeholder=S["s2_name_ph"],
            key="student_name_input",
        )
        st.session_state["student_name"] = sname

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Araştırma Taslağı (tam genişlik) ──────────────────────────
    st.markdown(f"### {S['s2_draft_title']}")
    td = st.session_state.taslak_dict
    field_labels = S["field_labels"]
    bos = "<i style='color:#aaa'>—</i>"

    draft_cols = st.columns(2)
    for idx, alan in enumerate(DURUM_ALANLARI):
        deger   = td.get(alan, "")
        icerik  = deger if deger else bos
        label   = field_labels.get(alan, alan)
        with draft_cols[idx % 2]:
            st.markdown(
                f"<div style='margin-bottom:14px;padding:12px 14px;background:#f8f9fa;"
                f"border-radius:8px;border-left:4px solid #2e7d32;'>"
                f"<span style='font-size:.72em;color:#888;text-transform:uppercase;"
                f"letter-spacing:.06em;'>{label}</span><br>"
                f"<span style='font-size:.92em;color:#1e1e1e;'>{icerik}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

    st.divider()

    # ── Refleksiyon (sıralı adımlar) ──────────────────────────────
    st.markdown(f"### {S['s2_refl_title']}")
    st.caption(S["s2_refl_caption"])

    refl_step = st.session_state.get("refl_step", 0)

    # (key, soru, placeholder, min_chars, özet_etiketi)
    REFL_STEPS = [
        ("r1", S["r1_q"], S["r1_ph"], 60, S["pdf_refl_hard"]),
        ("r2", S["r2_q"], S["r2_ph"], 60, S["pdf_refl_before"]),
        ("r3", S["r3_q"], S["r3_ph"], 80, S["pdf_ai_learned"]),
        ("r4", S["r4_q"], S["r4_ph"], 80, S["pdf_ai_next"]),
    ]

    def _summary_box(label, text):
        st.markdown(
            f"<div style='background:#e8f5e9;border-radius:8px;padding:10px 14px;"
            f"margin-bottom:10px;border-left:3px solid #2e7d32;'>"
            f"<span style='font-size:.72em;color:#2e7d32;font-weight:600;"
            f"text-transform:uppercase;letter-spacing:.04em;'>{label}</span><br>"
            f"<span style='font-size:.9em;color:#1e1e1e;'>{text or '—'}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )

    def _section_hdr(icon, label):
        st.markdown(
            f"<p style='font-size:.8em;color:#666;font-weight:600;text-transform:uppercase;"
            f"letter-spacing:.06em;margin:12px 0 4px 0;'>{icon} {label}</p>",
            unsafe_allow_html=True,
        )

    # Tamamlanan adımları özet kutularıyla göster
    for i in range(refl_step):
        key, _, _, _, lbl = REFL_STEPS[i]
        if i == 0:
            _section_hdr("📚", S["s2_learning_hdr"])
        elif i == 2:
            _section_hdr("🤖", S["s2_ai_hdr"])
        _summary_box(lbl, st.session_state.get(f"{key}_val", ""))

    # Aktif adımı göster (henüz tamamlanmadıysa)
    if refl_step < 4:
        key, question, placeholder, min_chars, _ = REFL_STEPS[refl_step]
        if refl_step == 0:
            _section_hdr("📚", S["s2_learning_hdr"])
        elif refl_step == 2:
            _section_hdr("🤖", S["s2_ai_hdr"])

        val = st.text_area(question, placeholder=placeholder, key=key, height=100)
        char_count  = len(val) if val else 0
        char_color  = "#2e7d32" if char_count >= min_chars else "#e65100"
        st.markdown(
            f"<p style='font-size:.75em;color:{char_color};text-align:right;margin-top:-10px;'>"
            f"{char_count} / {min_chars}</p>",
            unsafe_allow_html=True,
        )
        if st.button(S["refl_continue_btn"], disabled=(char_count < min_chars), type="primary"):
            st.session_state[f"{key}_val"] = val
            st.session_state["refl_step"]  = refl_step + 1
            st.rerun()

    else:
        # Tüm 4 refleksiyon tamamlandı
        st.success(S["refl_done_msg"])

        # ── Otomatik yerel log (bir kez) ──────────────────────────
        if not st.session_state.get("local_log_saved"):
            pt = st.session_state.total_prompt_tokens
            ot = st.session_state.total_output_tokens
            log_to_file({
                "tarih":       datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                "session_id":  st.session_state.get("pdf_session_id", ""),
                "ogrenci":     st.session_state.get("student_name", "") or "—",
                "danisman":    st.session_state.get("selected", ""),
                "dil":         lang,
                "tur":         st.session_state.total_turns,
                "p_token":     pt,
                "o_token":     ot,
                "toplam":      pt + ot,
                "maliyet_usd": round((pt * 0.075 + ot * 0.30) / 1_000_000, 6),
                "konsept":     st.session_state.taslak_dict.get("Konsept",    ""),
                "motivasyon":  st.session_state.taslak_dict.get("Motivasyon", ""),
                "onem":        st.session_state.taslak_dict.get("Önem",       ""),
                "literatur":   st.session_state.taslak_dict.get("Literatür",  ""),
                "soru":        st.session_state.taslak_dict.get("Soru",       ""),
                "gosterge":    st.session_state.taslak_dict.get("Gösterge",   ""),
                "r1":          st.session_state.get("r1_val", ""),
                "r2":          st.session_state.get("r2_val", ""),
                "r3":          st.session_state.get("r3_val", ""),
                "r4":          st.session_state.get("r4_val", ""),
            })
            st.session_state["local_log_saved"] = True

        # ── Otomatik Google Sheets log (bir kez) ──────────────────
        if not st.session_state.get("sheets_log_saved"):
            try:
                pt = st.session_state.total_prompt_tokens
                ot = st.session_state.total_output_tokens
                log_session(
                    st.session_state.taslak_dict,
                    st.session_state.get("selected", ""),
                    lang,
                    st.session_state.total_turns,
                    pt, ot,
                    r3=st.session_state.get("r3_val", ""),
                    r4=st.session_state.get("r4_val", ""),
                )
            except Exception:
                pass  # Sheets bağlantısı yoksa sessizce atla
            st.session_state["sheets_log_saved"] = True

        st.divider()
        st.markdown(
            f"<p style='font-size:.85em;color:#2e7d32;font-weight:600;'>"
            f"{S['submit_note']}</p>",
            unsafe_allow_html=True,
        )
        col_pdf, _ = st.columns([1, 4])
        with col_pdf:
            name_ok = bool(st.session_state.get("student_name", "").strip())
            if name_ok:
                try:
                    pdf_bytes = build_pdf(
                        st.session_state.selected,
                        st.session_state.taslak_dict,
                        st.session_state.display_history,
                        st.session_state.get("r1_val", ""),
                        st.session_state.get("r2_val", ""),
                        st.session_state.get("r3_val", ""),
                        st.session_state.get("r4_val", ""),
                        lang=lang,
                        student_name=st.session_state.get("student_name", ""),
                        session_id=st.session_state.get("pdf_session_id", ""),
                    )
                    pdf_name = "Module1_KKV_Report.pdf" if lang == "en" else "Modul1_KKV_Raporu.pdf"
                    st.download_button(
                        S["pdf_btn"], pdf_bytes, pdf_name, "application/pdf",
                        use_container_width=True, type="primary",
                    )
                except Exception as e:
                    st.warning(f"{S['pdf_err']}: {e}")
            else:
                st.button(S["pdf_btn"], disabled=True, use_container_width=True, type="primary")
                name_req = "Ad Soyad gerekli ↑" if lang == "tr" else "Name required ↑"
                st.caption(f"⚠️ {name_req}")
