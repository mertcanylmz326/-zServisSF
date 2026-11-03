import os
import datetime
import time
import threading
import psycopg2
from flask import Flask, render_template_string, request, send_file, session, redirect, url_for
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

app = Flask(__name__)
app.secret_key = "iz_motor_gizli_anahtar_erp_postgres_v58"

SIFRE = "izmotor2026*"
TELEGRAM_ADMIN_CHAT_ID = None

# Supabase Frankfurt Session Pooler (Doğru Port: 6543)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres.viewtgvofqdoqgodbbne:izmotor20261@aws-1-eu-central-1.pooler.supabase.com:6543/postgres")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

# --- VERİTABANI TABLOLARI ---
def init_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS servisler (
                id SERIAL PRIMARY KEY,
                plaka TEXT,
                musteri_ad TEXT,
                musteri_tel TEXT,
                model TEXT,
                km TEXT,
                tarih TEXT,
                detaylar TEXT,
                toplam_tutar REAL,
                durum TEXT DEFAULT 'Bekliyor',
                odeme_durumu TEXT DEFAULT 'Borçlu / Veresiye',
                pdf_dosya TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stok (
                id SERIAL PRIMARY KEY,
                parca_adi TEXT,
                adet INTEGER,
                fiyat REAL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS randevular (
                id SERIAL PRIMARY KEY,
                musteri_ad TEXT,
                tel TEXT,
                tarih_saat TEXT,
                notlar TEXT,
                hatirlatildi INTEGER DEFAULT 0
            )
        ''')
        conn.commit()
        cursor.close()
        conn.close()
        print("Tüm Supabase tabloları başarıyla kuruldu!")
    except Exception as e:
        print("Veritabanı kurulum hatası:", e)

init_db()

# --- TÜRKÇE FONT ---
try:
    pdfmetrics.registerFont(TTFont('DejaVu', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
    pdfmetrics.registerFont(TTFont('DejaVu-Bold', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'))
    FONT_NAME = 'DejaVu'
    FONT_BOLD = 'DejaVu-Bold'
except Exception:
    FONT_NAME = 'Helvetica'
    FONT_BOLD = 'Helvetica-Bold'

# --- HTML ARAYÜZ (GİRİŞ) ---
HTML_LOGIN = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>İz Motorsiklet - Giriş</title>
    <style>
        body { font-family: 'Inter', sans-serif; background-color: #0b0f19; background-image: radial-gradient(rgba(250, 204, 21, 0.08) 1px, transparent 1px); display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; color: #f8fafc; }
        .login-box { background: rgba(11, 15, 25, 0.95); border: 1px solid rgba(250, 204, 21, 0.4); padding: 40px; border-radius: 20px; width: 100%; max-width: 350px; text-align: center; box-shadow: 0 20px 40px rgba(0,0,0,0.8); }
        h2 { color: #facc15; margin-bottom: 5px; text-transform: uppercase; letter-spacing: 1px; }
        input { width: 100%; padding: 14px; margin-bottom: 20px; background: #030712; border: 1px solid #334155; border-radius: 10px; color: #fff; text-align: center; font-size: 16px; outline: none; }
        input:focus { border-color: #facc15; }
        button { background: linear-gradient(135deg, #facc15 0%, #ca8a04 100%); color: #030712; border: none; padding: 14px; border-radius: 10px; width: 100%; font-size: 16px; font-weight: 800; cursor: pointer; text-transform: uppercase; }
        .error { color: #ef4444; margin-bottom: 15px; font-size: 13px; font-weight: 700; }
    </style>
</head>
<body>
<div class="login-box">
    <h2>İZ MOTORSİKLET</h2>
    <p style="color:#94a3b8; font-size:13px; margin-bottom:20px;">Tam Donanımlı Garaj Paneli</p>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
    <form method="POST">
        <input type="password" name="sifre" placeholder="••••••••" required autofocus>
        <button type="submit">Güvenli Giriş Yap</button>
    </form>
</div>
</body>
</html>
"""

# --- HTML ARAYÜZ (ANA PANEL) ---
HTML_PANEL = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>İz Motorsiklet - ERP Paneli</title>
    <style>
        :root { --bg-main: #050811; --card-bg: rgba(11, 15, 25, 0.9); --accent: #facc15; --text-main: #f8fafc; --text-muted: #94a3b8; }
        body { font-family: 'Inter', sans-serif; background-color: var(--bg-main); color: var(--text-main); margin: 0; padding: 10px; }
        .container { max-width: 900px; margin: 0 auto; background: var(--card-bg); padding: 18px; border-radius: 20px; border: 1px solid rgba(250,204,21,0.25); box-shadow: 0 20px 50px rgba(0,0,0,0.9); }
        .top-navbar { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #334155; padding-bottom: 10px; margin-bottom: 15px; }
        .nav-tabs { display: flex; gap: 6px; overflow-x: auto; padding-bottom: 5px; }
        .tab-btn { background: #0f172a; color: var(--text-muted); border: 1px solid #334155; padding: 8px 12px; border-radius: 8px; cursor: pointer; font-weight: 700; font-size: 12px; white-space: nowrap; }
        .tab-btn.active { background: var(--accent); color: #030712; border-color: var(--accent); font-weight: 800; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .card { background: rgba(18, 24, 40, 0.8); border: 1px solid #334155; padding: 15px; border-radius: 14px; margin-bottom: 14px; font-size: 13px; }
        h3 { color: var(--accent); margin-top: 0; font-size: 15px; border-bottom: 1px solid #334155; padding-bottom: 8px; }
        input, select, textarea { width: 100%; padding: 11px; margin-bottom: 10px; background: #030712; border: 1px solid #334155; border-radius: 10px; color: #fff; box-sizing: border-box; font-size: 13px; }
        label { display: block; font-weight: 700; margin-bottom: 4px; font-size: 11px; color: #cbd5e1; text-transform: uppercase; }
        .btn-action { background: linear-gradient(135deg, var(--accent), #ca8a04); color: #030712; border: none; padding: 13px; border-radius: 10px; width: 100%; font-size: 14px; font-weight: 800; cursor: pointer; text-transform: uppercase; margin-top: 8px; }
        .whatsapp-btn { background: #25d366; color: #fff; padding: 7px 10px; border-radius: 8px; text-decoration: none; font-size: 11px; font-weight: 800; display: inline-block; margin-top: 5px; }
        .pdf-btn { background: #0284c7; color: #fff; padding: 7px 10px; border-radius: 8px; text-decoration: none; font-size: 11px; font-weight: 800; display: inline-block; margin-top: 5px; }
        .logout { color: #f87171; text-decoration: none; font-weight: 700; font-size: 12px; background: rgba(248,113,113,0.1); padding: 5px 10px; border-radius: 6px; border: 1px solid rgba(248,113,113,0.3); }
        .stat-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 15px; }
        @media(min-width: 600px) { .stat-grid { grid-template-columns: repeat(4, 1fr); } }
        .stat-box { background: rgba(20,27,45,0.7); border: 1px solid #334155; padding: 10px; border-radius: 10px; text-align: center; }
        .stat-box h4 { margin: 0; color: var(--accent); font-size: 16px; }
        .stat-box p { margin: 3px 0 0 0; color: var(--text-muted); font-size: 10px; text-transform: uppercase; font-weight: 700; }
    </style>
</head>
<body>
<div class="container">
    <div class="top-navbar">
        <h2 style="margin:0; color:var(--accent); font-size:16px;">🏍️ İZ MOTORSİKLET</h2>
        <a href="/cikis" class="logout">Çıkış</a>
    </div>

    <div class="nav-tabs">
        <button class="tab-btn active" onclick="switchTab('formTab', this)">🛠️ Servis</button>
        <button class="tab-btn" onclick="switchTab('araclarTab', this)">🏍️ Aktif Araçlar</button>
        <button class="tab-btn" onclick="switchTab('historyTab', this)">🔍 Geçmiş</button>
        <button class="tab-btn" onclick="switchTab('stockTab', this)">📦 Stok</button>
        <button class="tab-btn" onclick="switchTab('randevuTab', this)">📅 Randevu</button>
    </div>

    <div class="stat-grid" style="margin-top: 15px;">
        <div class="stat-box"><h4>{{ "%.2f"|format(toplam_ciro) }} TL</h4><p>Toplam Ciro</p></div>
        <div class="stat-box"><h4>{{ aktif_araclar|length }}</h4><p>Aktif Araç</p></div>
        <div class="stat-box"><h4>{{ stoklar|length }}</h4><p>Stok Çeşit</p></div>
        <div class="stat-box"><h4>{{ randevular|length }}</h4><p>Randevular</p></div>
    </div>

    <!-- 1. SERVİS FORMU -->
    <div id="formTab" class="tab-content active">
        <div class="card">
            <h3>⚡ Yeni Servis Formu Oluştur</h3>
            <form action="/olustur" method="POST" enctype="multipart/form-data">
                <label>Dükkan Logosu (Zorunlu)</label><input type="file" name="logo" accept="image/*" required>
                <label>Müşteri Ad Soyad</label><input type="text" name="musteri_ad" placeholder="Örn: Ahmet Yılmaz" required>
                <label>Müşteri Telefon (WhatsApp)</label><input type="text" name="musteri_tel" placeholder="Örn: 905320000000" required>
                <label>Motosiklet Plaka</label><input type="text" name="plaka" placeholder="Örn: 34 ABC 123" required>
                <label>Marka / Model</label><input type="text" name="model" placeholder="Örn: Honda Dio" required>
                <label>Kilometre (KM)</label><input type="text" name="km" placeholder="Örn: 15000" required>
                
                <label>Ödeme Durumu</label>
                <select name="odeme_durumu">
                    <option value="Borçlu / Veresiye" selected>🔴 Borçlu / Veresiye</option>
                    <option value="Parça Bekliyor">🟡 Parça Bekliyor</option>
                    <option value="Ödendi">🟢 Ödendi (Arşive Gider)</option>
                </select>

                <label style="margin-top: 15px;">İşlem / Parça Adı</label><input type="text" name="islem_ad[]" placeholder="Örn: Yağ Değişimi / Buji" required>
                <label>Tutar (TL)</label><input type="number" step="0.01" name="fiyat[]" placeholder="Örn: 500" required>
                
                <button type="submit" class="btn-action">Formu Oluştur & Kaydet (PDF)</button>
            </form>
        </div>
    </div>

    <!-- 2. AKTİF ARAÇLAR -->
    <div id="araclarTab" class="tab-content">
        <h3>Atölyedeki Aktif Araçlar</h3>
        {% if aktif_araclar %}
            {% for ts in aktif_araclar %}
            <div class="card" style="border-left: 4px solid {% if ts[10] == 'Borçlu / Veresiye' %}#f87171{% else %}#facc15{% endif %};">
                <b>Plaka:</b> <span style="color:var(--accent); font-size:14px;">{{ ts[1] }}</span> | <b>Müşteri:</b> {{ ts[2] }} ({{ ts[3] }})<br>
                <b>Model / KM:</b> {{ ts[4] }} - {{ ts[5] }} KM | <b>Tarih:</b> {{ ts[6] }}<br>
                <b>Yapılanlar:</b> {{ ts[7] }} | <b>Tutar:</b> <span style="color:var(--accent); font-weight:800;">{{ "%.2f"|format(ts[8]) }} TL</span><br>
                
                <form action="/durum_guncelle" method="POST" style="margin-top: 10px; display:flex; gap:8px;">
                    <input type="hidden" name="servis_id" value="{{ ts[0] }}">
                    <select name="odeme_durumu" onchange="this.form.submit()" style="margin:0; font-size:11px; padding:6px;">
                        <option value="Borçlu / Veresiye" {% if ts[10] == 'Borçlu / Veresiye' %}selected{% endif %}>🔴 Borçlu</option>
                        <option value="Parça Bekliyor" {% if ts[10] == 'Parça Bekliyor' %}selected{% endif %}>🟡 Parça Bekliyor</option>
                        <option value="Ödendi">🟢 Ödendi (Arşive At)</option>
                    </select>
                </form>

                <div style="margin-top: 8px;">
                    <a href="https://wa.me/{{ ts[3] }}?text=Sayin%20{{ ts[2] }},%20Iz%20Motorsiklet%20servis%20ucretiniz%20{{ "%.2f"|format(ts[8]) }}%20TL." target="_blank" class="whatsapp-btn">💬 WhatsApp</a>
                    {% if ts[11] %}<a href="/pdf_indir/{{ ts[0] }}" class="pdf-btn">📄 PDF İndir</a>{% endif %}
                </div>
            </div>
            {% endfor %}
        {% else %}
            <p style="color: var(--text-muted); text-align: center;">Atölyede aktif araç bulunmuyor.</p>
        {% endif %}
    </div>

    <!-- 3. GEÇMİŞ -->
    <div id="historyTab" class="tab-content">
        <form method="GET" action="/">
            <input type="hidden" name="tab" value="history">
            <label>Plaka veya Müşteri Adı ile Ara</label>
            <input type="text" name="sorgu_plaka" placeholder="Örn: 34 RAP..." value="{{ sorgu_plaka or '' }}">
            <button type="submit" class="btn-action" style="padding:10px;">Geçmişte Sorgula</button>
        </form>
        <hr style="border:0; border-top:1px solid #334155; margin: 15px 0;">
        <h3>Ödenmiş Geçmiş Servisler</h3>
        {% if kayitlar %}
            {% for k in kayitlar %}
            <div class="card" style="border-left: 4px solid #4ade80;">
                <b>Plaka:</b> <span style="color:var(--accent);">{{ k[1] }}</span> | <b>Tarih:</b> {{ k[6] }}<br>
                <b>Müşteri:</b> {{ k[2] }} ({{ k[3] }})<br>
                <b>İşlemler:</b> {{ k[7] }}<br>
                <b>Tutar:</b> <span style="color:var(--accent);">{{ "%.2f"|format(k[8]) }} TL</span> | <span style="color:#4ade80; font-weight:800;">{{ k[10] }}</span>
                {% if k[11] %}<br><a href="/pdf_indir/{{ k[0] }}" class="pdf-btn" style="margin-top:8px;">📄 Formu İndir</a>{% endif %}
            </div>
            {% endfor %}
        {% else %}
            <p style="color: var(--text-muted); text-align: center;">Geçmiş kayıt bulunamadı.</p>
        {% endif %}
    </div>

    <!-- 4. STOK -->
    <div id="stockTab" class="tab-content">
        <h3>Parça / Ürün Stok Yönetimi</h3>
        <form method="POST" action="/stok_ekle">
            <label>Parça Adı</label><input type="text" name="parca_adi" placeholder="Örn: Buji NGK" required>
            <label>Stok Adedi</label><input type="number" name="adet" placeholder="Adet" required>
            <label>Birim Fiyat (TL)</label><input type="number" step="0.01" name="fiyat" placeholder="Fiyat" required>
            <button type="submit" class="btn-action">Stok Ekle</button>
        </form>
        <hr style="border:0; border-top:1px solid #334155; margin: 15px 0;">
        <h3>Mevcut Stoklar</h3>
        {% for s in stoklar %}
        <div class="card" style="border-left: 4px solid {% if s[2] < 3 %}#f87171{% else %}#4ade80{% endif %};">
            <b>{{ s[1] }}</b> - Adet: <span style="color: {% if s[2] < 3 %}#f87171{% else %}#4ade80{% endif %}; font-weight:800;">{{ s[2] }}</span> | Fiyat: <b>{{ "%.2f"|format(s[3]) }} TL</b>
            {% if s[2] < 3 %}<br><span style="color:#f87171; font-weight:800; font-size:11px;">⚠️ Kritik Stok!</span>{% endif %}
        </div>
        {% endfor %}
    </div>

    <!-- 5. RANDEVU -->
    <div id="randevuTab" class="tab-content">
        <h3>Atölye Randevuları</h3>
        <form method="POST" action="/randevu_ekle">
            <label>Müşteri Ad Soyad</label><input type="text" name="musteri_ad" placeholder="Ad Soyad" required>
            <label>Telefon</label><input type="text" name="tel" placeholder="90532..." required>
            <label>Tarih ve Saat</label><input type="text" name="tarih_saat" placeholder="05.11.2026 - 14:30" required>
            <button type="submit" class="btn-action">Randevu Oluştur</button>
        </form>
        <hr style="border:0; border-top:1px solid #334155; margin: 15px 0;">
        <h3>Aktif Randevular</h3>
        {% for r in randevular %}
        <div class="card" style="border-left: 4px solid #0d9488;">
            <b>Müşteri:</b> {{ r[1] }} ({{ r[2] }})<br>
            <b>Zaman:</b> <span style="color:var(--accent); font-weight:800;">{{ r[3] }}</span>
            <div style="margin-top:8px;"><a href="https://wa.me/{{ r[2] }}?text=Randevu%20hatirlatmasi" target="_blank" class="whatsapp-btn">💬 WhatsApp Hatırlat</a></div>
        </div>
        {% endfor %}
    </div>
</div>

<script>
function switchTab(tabId, btn) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    document.getElementById(tabId).classList.add('active');
    btn.classList.add('active');
}
</script>
</body>
</html>
"""

# --- PDF MOTORU ---
def pdf_olustur(filename, veri, logo_yolu):
    doc = SimpleDocTemplate(filename, pagesize=A4, rightMargin=15, leftMargin=15, topMargin=12, bottomMargin=12)
    story = []
    style_normal = ParagraphStyle('Norm', fontName=FONT_NAME, fontSize=9, leading=11, textColor=colors.HexColor("#111111"))
    style_title = ParagraphStyle('Tit', fontName=FONT_BOLD, fontSize=12, leading=15, textColor=colors.HexColor("#1A1A1A"), alignment=1, spaceAfter=6)

    if logo_yolu and os.path.exists(logo_yolu):
        try:
            story.append(Image(logo_yolu, width=540, height=60))
            story.append(Spacer(1, 4))
        except: pass

    story.append(Paragraph("MÜŞTERİ SERVİS FORMU", style_title))
    m_text = f"<b>Müşteri:</b> {veri.get('musteri_ad', '')} | <b>Tel:</b> {veri.get('musteri_tel', '')} | <b>Tarih:</b> {datetime.date.today().strftime('%d.%m.%Y')}"
    a_text = f"<b>Plaka:</b> {veri.get('plaka', '')} | <b>Model:</b> {veri.get('model', '')} | <b>KM:</b> {veri.get('km', '')}"
    story.append(Paragraph(m_text, style_normal))
    story.append(Paragraph(a_text, style_normal))
    story.append(Spacer(1, 10))

    hizmet_data = [["No", "Yapılan İşlem / Parça", "Adet", "Tutar"]]
    hizmet_data.append(["1", veri.get('islem_ad', 'Bakım'), "1", f"{veri.get('fiyat', 0.0):.2f} TL"])
    hizmet_data.append(["", "GENEL TOPLAM", "", f"{veri.get('fiyat', 0.0):.2f} TL"])

    t_hizmet = Table(hizmet_data, colWidths=[30, 350, 60, 100])
    t_hizmet.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#E0E0E0")),
        ('GRID', (0,0), (-1,-2), 0.5, colors.HexColor("#CBD5E0")),
        ('BACKGROUND', (1,-1), (-1,-1), colors.HexColor("#FFD54F")),
        ('PADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(t_hizmet)
    doc.build(story)

# --- WEB ROUTES ---
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if request.form.get('sifre') == SIFRE:
            session['giris'] = True
            return redirect(url_for('index'))
        return render_template_string(HTML_LOGIN, error="Hatalı Şifre!")
    if not session.get('giris'):
        return render_template_string(HTML_LOGIN)

    conn = get_db_connection()
    cursor = conn.cursor()

    sorgu_plaka = request.args.get('sorgu_plaka', '').strip()
    if sorgu_plaka:
        cursor.execute("SELECT * FROM servisler WHERE (plaka ILIKE %s OR musteri_ad ILIKE %s) AND odeme_durumu = 'Ödendi' ORDER BY id DESC", ('%' + sorgu_plaka + '%', '%' + sorgu_plaka + '%'))
    else:
        cursor.execute("SELECT * FROM servisler WHERE odeme_durumu = 'Ödendi' ORDER BY id DESC")
    kayitlar = cursor.fetchall()

    cursor.execute("SELECT * FROM servisler WHERE odeme_durumu != 'Ödendi' OR odeme_durumu IS NULL ORDER BY id DESC")
    aktif_araclar = cursor.fetchall()

    cursor.execute("SELECT * FROM stok")
    stoklar = cursor.fetchall()
    cursor.execute("SELECT * FROM randevular ORDER BY id DESC")
    randevular = cursor.fetchall()

    cursor.execute("SELECT SUM(toplam_tutar) FROM servisler")
    res = cursor.fetchone()
    toplam_ciro = res[0] if res and res[0] else 0.0

    cursor.close()
    conn.close()
    return render_template_string(HTML_PANEL, kayitlar=kayitlar, sorgu_plaka=sorgu_plaka, stoklar=stoklar, randevular=randevular, aktif_araclar=aktif_araclar, toplam_ciro=toplam_ciro)

@app.route('/olustur', methods=['POST'])
def olustur():
    if not session.get('giris'): return redirect(url_for('index'))
    ad, tel, plaka, model, km = request.form.get('musteri_ad'), request.form.get('musteri_tel'), request.form.get('plaka', '').strip(), request.form.get('model'), request.form.get('km')
    odeme_durumu = request.form.get('odeme_durumu', 'Borçlu / Veresiye')
    islem_ad = request.form.getlist('islem_ad[]')[0] if request.form.getlist('islem_ad[]') else "Genel Bakım"
    try: fiyat = float(request.form.getlist('fiyat[]')[0])
    except: fiyat = 0.0

    logo_file = request.files.get('logo')
    logo_path = f"temp_logo_{plaka}.jpg" if logo_file and logo_file.filename != '' else None
    if logo_file and logo_path: logo_file.save(logo_path)

    pdf_filename = f"servis_formu_{plaka}_{int(datetime.datetime.now().timestamp())}.pdf"
    pdf_olustur(pdf_filename, {'musteri_ad': ad, 'musteri_tel': tel, 'plaka': plaka, 'model': model, 'km': km, 'islem_ad': islem_ad, 'fiyat': fiyat}, logo_path)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO servisler (plaka, musteri_ad, musteri_tel, model, km, tarih, detaylar, toplam_tutar, durum, odeme_durumu, pdf_dosya) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Bekliyor', %s, %s)", 
                   (plaka, ad, tel, model, km, datetime.date.today().strftime("%d.%m.%Y"), islem_ad, fiyat, odeme_durumu, pdf_filename))
    conn.commit()
    cursor.close()
    conn.close()

    if logo_path and os.path.exists(logo_path): os.remove(logo_path)
    return send_file(pdf_filename, as_attachment=True)

@app.route('/durum_guncelle', methods=['POST'])
def durum_guncelle():
    if not session.get('giris'): return redirect(url_for('index'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE servisler SET odeme_durumu = %s WHERE id = %s", (request.form.get('odeme_durumu'), request.form.get('servis_id')))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('index'))

@app.route('/stok_ekle', methods=['POST'])
def stok_ekle():
    if not session.get('giris'): return redirect(url_for('index'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO stok (parca_adi, adet, fiyat) VALUES (%s, %s, %s)", (request.form.get('parca_adi'), int(request.form.get('adet', 0)), float(request.form.get('fiyat', 0))))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('index'))

@app.route('/randevu_ekle', methods=['POST'])
def randevu_ekle():
    if not session.get('giris'): return redirect(url_for('index'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO randevular (musteri_ad, tel, tarih_saat, notlar, hatirlatildi) VALUES (%s, %s, %s, %s, 0)", (request.form.get('musteri_ad'), request.form.get('tel'), request.form.get('tarih_saat'), 'Randevu'))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('index'))

@app.route('/pdf_indir/<int:servis_id>')
def pdf_indir(servis_id):
    if not session.get('giris'): return redirect(url_for('index'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT pdf_dosya FROM servisler WHERE id = %s", (servis_id,))
    res = cursor.fetchone()
    cursor.close()
    conn.close()
    if res and res[0] and os.path.exists(res[0]):
        return send_file(res[0], as_attachment=True)
    return "PDF Bulunamadı", 404

@app.route('/cikis')
def cikis():
    session.pop('giris', None)
    return redirect(url_for('index'))

# --- TELEGRAM BOTU ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        ["🛠️ Servis Formu Oluştur", "📅 Randevu Ekle"],
        ["🔍 Plaka Sorgula", "📦 Stok Listesi"],
        ["📊 Günlük Özet", "🏍️ Aktif Araçlar"]
    ]
    await update.message.reply_text("Selam kanka! İz Motorsiklet Supabase Botuna hoş geldin:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

async def telegram_mesaj(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "📊 Günlük Özet":
        bugun = datetime.date.today().strftime("%d.%m.%Y")
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(toplam_tutar), COUNT(id) FROM servisler WHERE tarih = %s", (bugun,))
        res = cursor.fetchone()
        cursor.close()
        conn.close()
        ciro = res[0] if res and res[0] else 0.0
        adet = res[1] if res and res[1] else 0
        await update.message.reply_text(f"📊 **Günlük Özet ({bugun}):**\n- Giren Araç: {adet}\n- Toplam Ciro: `{ciro:.2f} TL`", parse_mode="Markdown")
    elif text == "📦 Stok Listesi":
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT parca_adi, adet, fiyat FROM stok")
        stoklar = cursor.fetchall()
        cursor.close()
        conn.close()
        msg = "📦 **Stok Durumu:**\n\n"
        for s in stoklar:
            msg += f"- {s[0]}: {s[1]} adet ({s[3]} TL)\n"
        await update.message.reply_text(msg or "Stok boş.", parse_mode="Markdown")
    else:
        await update.message.reply_text("Kanka menüden seçim yapabilirsin.")

def run_telegram_bot():
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN: return
    try:
        bot_app = Application.builder().token(TOKEN).drop_pending_updates(True).build()
        bot_app.add_handler(CommandHandler("start", start))
        bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, telegram_mesaj))
        bot_app.run_polling(stop_signals=None)
    except Exception as e:
        print("Telegram bot hata:", e)

if __name__ == '__main__':
    threading.Thread(target=run_telegram_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
