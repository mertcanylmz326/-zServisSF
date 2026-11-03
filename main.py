import os
import datetime
import time
import threading
import psycopg2
from flask import Flask, render_template_string, request, send_file, session, redirect, url_for
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, Image
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

app = Flask(__name__)
app.secret_key = "iz_motor_gizli_anahtar_erp_postgres_v52"

SIFRE = "izmotor2026*"
TELEGRAM_ADMIN_CHAT_ID = None

# Supabase Havuz (Pooler) Bağlantı Adresi (Yeni şifre ve Frankfurt havuz bölgesiyle)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres.dcyoerlxjonqmbatennf:izmotor20261@aws-0-eu-central-1.pooler.supabase.com:6543/postgres")

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode='require')

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
        print("Supabase Havuz Veritabanı bağlantısı başarılı!")
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

HTML_LOGIN = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>İz Motorsiklet - Giriş</title>
    <style>
        body { font-family: 'Inter', sans-serif; background-color: #0b0f19; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; color: #f8fafc; }
        .login-box { background: rgba(11, 15, 25, 0.95); border: 1px solid rgba(250, 204, 21, 0.4); padding: 40px; border-radius: 20px; width: 100%; max-width: 350px; text-align: center; }
        input { width: 100%; padding: 14px; margin-bottom: 20px; background: #030712; border: 1px solid #334155; border-radius: 10px; color: #fff; text-align: center; font-size: 16px; outline: none; }
        button { background: linear-gradient(135deg, #facc15 0%, #ca8a04 100%); color: #030712; border: none; padding: 14px; border-radius: 10px; width: 100%; font-size: 16px; font-weight: 800; cursor: pointer; text-transform: uppercase; }
        .error { color: #ef4444; margin-bottom: 15px; font-size: 13px; font-weight: 700; }
    </style>
</head>
<body>
<div class="login-box">
    <h2>İZ MOTORSİKLET</h2>
    <p style="color:#94a3b8; font-size:13px; margin-bottom:20px;">Garaj Paneli Girişi</p>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
    <form method="POST">
        <input type="password" name="sifre" placeholder="Şifre" required autofocus>
        <button type="submit">Giriş Yap</button>
    </form>
</div>
</body>
</html>
"""

HTML_PANEL = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>İz Motorsiklet - ERP</title>
    <style>
        body { font-family: 'Inter', sans-serif; background-color: #050811; color: #f8fafc; margin: 0; padding: 10px; }
        .container { max-width: 900px; margin: 0 auto; background: rgba(11, 15, 25, 0.95); padding: 15px; border-radius: 15px; border: 1px solid rgba(250,204,21,0.2); }
        .card { background: rgba(18, 24, 40, 0.8); border: 1px solid #334155; padding: 15px; border-radius: 12px; margin-bottom: 12px; }
        .btn-action { background: #facc15; color: #030712; border: none; padding: 12px; border-radius: 10px; width: 100%; font-weight: 800; cursor: pointer; text-transform: uppercase; margin-top: 10px; }
        input, select, textarea { width: 100%; padding: 10px; margin-bottom: 10px; background: #030712; border: 1px solid #334155; border-radius: 8px; color: #fff; box-sizing: border-box; }
        .logout { float: right; color: #f87171; text-decoration: none; font-weight: bold; font-size: 12px; }
    </style>
</head>
<body>
<div class="container">
    <div><a href="/cikis" class="logout">Çıkış Yap</a></div>
    <h2>🏍️ İz Motorsiklet Paneli</h2>
    
    <div class="card">
        <h3>➕ Yeni Servis Kaydı</h3>
        <form action="/olustur" method="POST" enctype="multipart/form-data">
            <label>Logo (Zorunlu)</label><input type="file" name="logo" accept="image/*" required>
            <label>Müşteri Ad Soyad</label><input type="text" name="musteri_ad" required>
            <label>Müşteri Telefon</label><input type="text" name="musteri_tel" placeholder="90532..." required>
            <label>Plaka</label><input type="text" name="plaka" required>
            <label>Model</label><input type="text" name="model" required>
            <label>KM</label><input type="text" name="km" required>
            <label>İşlem / Parça Adı</label><input type="text" name="islem_ad[]" required>
            <label>Fiyat (TL)</label><input type="number" step="0.01" name="fiyat[]" required>
            <button type="submit" class="btn-action">Formu Oluştur & Kaydet</button>
        </form>
    </div>

    <div class="card">
        <h3>📋 Atölyedeki Aktif Araçlar</h3>
        {% if aktif_araclar %}
            {% for ts in aktif_araclar %}
            <div style="border-bottom: 1px solid #334155; padding-bottom: 8px; margin-bottom: 8px;">
                <b>{{ ts[1] }}</b> - {{ ts[2] }} ({{ ts[4] }}) | <b>Tutar:</b> {{ "%.2f"|format(ts[8]) }} TL
            </div>
            {% endfor %}
        {% else %}
            <p style="color: #94a3b8;">Aktif araç yok.</p>
        {% endif %}
    </div>
</div>
</body>
</html>
"""

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
    m_text = f"<b>Müşteri:</b> {veri.get('musteri_ad', '')} | <b>Tel:</b> {veri.get('musteri_tel', '')}"
    a_text = f"<b>Plaka:</b> {veri.get('plaka', '')} | <b>Model:</b> {veri.get('model', '')} | <b>KM:</b> {veri.get('km', '')}"
    story.append(Paragraph(m_text, style_normal))
    story.append(Paragraph(a_text, style_normal))
    doc.build(story)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if request.form.get('sifre') == SIFRE:
            session['giris'] = True
            return redirect(url_for('index'))
        return render_template_string(HTML_LOGIN, error="Hatalı Şifre!")
    if not session.get('giris'):
        return render_template_string(HTML_LOGIN)

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM servisler WHERE odeme_durumu != 'Ödendi' OR odeme_durumu IS NULL ORDER BY id DESC")
        aktif_araclar = cursor.fetchall()
        cursor.close()
        conn.close()
    except Exception as e:
        aktif_araclar = []
        print("DB sorgu hatası:", e)

    return render_template_string(HTML_PANEL, aktif_araclar=aktif_araclar)

@app.route('/olustur', methods=['POST'])
def olustur():
    if not session.get('giris'): return redirect(url_for('index'))
    ad, tel, plaka, model, km = request.form.get('musteri_ad'), request.form.get('musteri_tel'), request.form.get('plaka', '').strip(), request.form.get('model'), request.form.get('km')
    
    islem_ad = request.form.getlist('islem_ad[]')[0] if request.form.getlist('islem_ad[]') else "Bakım"
    try: fiyat = float(request.form.getlist('fiyat[]')[0])
    except: fiyat = 0.0

    logo_file = request.files.get('logo')
    logo_path = f"temp_logo_{plaka}.jpg" if logo_file and logo_file.filename != '' else None
    if logo_file and logo_path: logo_file.save(logo_path)

    pdf_filename = f"servis_formu_{plaka}_{int(datetime.datetime.now().timestamp())}.pdf"
    pdf_olustur(pdf_filename, {'musteri_ad': ad, 'musteri_tel': tel, 'plaka': plaka, 'model': model, 'km': km}, logo_path)

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO servisler (plaka, musteri_ad, musteri_tel, model, km, tarih, detaylar, toplam_tutar, durum, odeme_durumu, pdf_dosya) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Bekliyor', 'Borçlu / Veresiye', %s)", 
                       (plaka, ad, tel, model, km, datetime.date.today().strftime("%d.%m.%Y"), islem_ad, fiyat, pdf_filename))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print("Kayıt hatası:", e)

    if logo_path and os.path.exists(logo_path): os.remove(logo_path)
    return send_file(pdf_filename, as_attachment=True)

@app.route('/cikis')
def cikis():
    session.pop('giris', None)
    return redirect(url_for('index'))

# --- TELEGRAM BOTU ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Selam kanka! İz Motorsiklet botu aktif.")

def run_telegram_bot():
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN: return
    try:
        bot_app = Application.builder().token(TOKEN).drop_pending_updates(True).build()
        bot_app.add_handler(CommandHandler("start", start))
        bot_app.run_polling(stop_signals=None)
    except Exception as e:
        print("Telegram bot hata:", e)

if __name__ == '__main__':
    threading.Thread(target=run_telegram_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
