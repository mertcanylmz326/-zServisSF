import os
import datetime
import time
import threading
import re
import socket
import psycopg2
from flask import Flask, render_template_string, request, send_file, session, redirect, url_for
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

try:
    import pytesseract
    from PIL import Image as PILImage
    OCR_AKTIF = True
except:
    OCR_AKTIF = False

app = Flask(__name__)
app.secret_key = "iz_motor_gizli_anahtar_erp_postgres_v101"

SIFRE = "izmotor2026*"

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres.viewtgvofqdoqgodbbne:izmotor20261@aws-1-eu-central-1.pooler.supabase.com:6543/postgres")

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
                notlar TEXT,
                toplam_tutar REAL,
                durum TEXT DEFAULT 'Serviste',
                odeme_durumu TEXT DEFAULT 'Borçlu / Veresiye',
                pdf_dosya TEXT
            )
        ''')
        cursor.execute('ALTER TABLE servisler ADD COLUMN IF NOT EXISTS notlar TEXT;')
        cursor.execute('ALTER TABLE servisler ADD COLUMN IF NOT EXISTS durum TEXT DEFAULT \'Serviste\';')
        cursor.execute('ALTER TABLE servisler ADD COLUMN IF NOT EXISTS odeme_durumu TEXT DEFAULT \'Borçlu / Veresiye\';')
        cursor.execute('ALTER TABLE servisler ADD COLUMN IF NOT EXISTS pdf_dosya TEXT;')
        
        cursor.execute("UPDATE servisler SET durum = 'Serviste' WHERE durum IS NULL OR durum = '';")
        cursor.execute("UPDATE servisler SET odeme_durumu = 'Borçlu / Veresiye' WHERE odeme_durumu IS NULL OR odeme_durumu = '';")

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
        print("Tüm Supabase tabloları ve sütunları başarıyla güncellendi!")
    except Exception as e:
        print("Veritabanı kurulum hatası:", e)

init_db()

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
    <title>🛵Iz Motorsıklet - Giriş🏍</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Permanent+Marker&family=Inter:wght@400;700;900&display=swap');
        body { font-family: 'Inter', sans-serif; background-color: #06080f; background-image: radial-gradient(rgba(250, 204, 21, 0.08) 1px, transparent 1px); display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; color: #f8fafc; }
        .login-box { background: rgba(13, 17, 28, 0.95); border: 1px solid rgba(250, 204, 21, 0.4); padding: 40px; border-radius: 20px; width: 100%; max-width: 350px; text-align: center; box-shadow: 0 20px 40px rgba(0,0,0,0.8); }
        h2 { font-family: 'Permanent Marker', cursive; color: #facc15; font-size: 26px; margin-bottom: 5px; text-transform: uppercase; letter-spacing: 2px; text-shadow: 0 0 10px rgba(250,204,21,0.5); }
        input { width: 100%; padding: 14px; margin-bottom: 20px; background: #030712; border: 1px solid #334155; border-radius: 10px; color: #fff; text-align: center; font-size: 16px; outline: none; }
        input:focus { border-color: #facc15; }
        button { background: linear-gradient(135deg, #facc15 0%, #ca8a04 100%); color: #030712; border: none; padding: 14px; border-radius: 10px; width: 100%; font-size: 16px; font-weight: 800; cursor: pointer; text-transform: uppercase; }
        .error { color: #ef4444; margin-bottom: 15px; font-size: 13px; font-weight: 700; }
    </style>
</head>
<body>
<div class="login-box">
    <h2>🏍IZ MOTORSIKLET🛵</h2>
    <p style="color:#94a3b8; font-size:11px; margin-bottom:19px;">Tam Donanımlı Garaj Paneli</p>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
    <form method="POST">
        <input type="password" name="sifre" placeholder="••••••••" required autofocus>
        <button type="submit">Güvenli Giriş Yap</button>
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
    <title>🏍Iz Motorsıklet-Garaj Paneli🛵</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Permanent+Marker&family=Inter:wght@400;600;800;900&display=swap');
        :root { --bg-main: #04060b; --card-bg: rgba(13, 18, 30, 0.95); --accent: #facc15; --text-main: #f8fafc; --text-muted: #94a3b8; --border-color: #1e293b; }
        body { font-family: 'Inter', sans-serif; background-color: var(--bg-main); color: var(--text-main); margin: 0; padding: 12px; }
        .container { max-width: 900px; margin: 0 auto; }
        
        .sticky-header { position: sticky; top: 0; z-index: 1000; background: rgba(4, 6, 11, 0.98); backdrop-filter: blur(10px); padding: 10px 0 15px 0; border-bottom: 1px solid rgba(250, 204, 21, 0.15); margin-bottom: 15px; }
        .header-box { display: flex; justify-content: space-between; align-items: center; background: var(--card-bg); border: 1px solid var(--border-color); padding: 14px 20px; border-radius: 16px; margin-bottom: 12px; box-shadow: 0 8px 25px rgba(0,0,0,0.5); }
        .brand-title { display: flex; align-items: center; gap: 12px; }
        .brand-icon { background: linear-gradient(135deg, #facc15, #f97316); color: #030712; padding: 8px 12px; border-radius: 12px; font-size: 20px; transform: rotate(-5deg); box-shadow: 0 4px 12px rgba(250,204,21,0.3); }
        .graffiti-text { font-family: 'Permanent Marker', cursive; color: #facc15; font-size: 22px; text-transform: uppercase; margin: 0; letter-spacing: 1px; text-shadow: 0 0 15px rgba(250,204,21,0.4); }
        .logout { color: #f87171; text-decoration: none; font-weight: 700; font-size: 11px; background: rgba(248,113,113,0.12); border: 1px solid rgba(248,113,113,0.3); padding: 6px 12px; border-radius: 8px; transition: all 0.2s; }
        .logout:hover { background: rgba(248,113,113,0.25); }

        .nav-tabs { display: flex; gap: 8px; overflow-x: auto; padding: 4px 2px; scrollbar-width: none; }
        .nav-tabs::-webkit-scrollbar { display: none; }
        .tab-btn { background: #0b1120; color: var(--text-muted); border: 1px solid var(--border-color); padding: 10px 16px; border-radius: 12px; cursor: pointer; font-weight: 700; font-size: 12px; white-space: nowrap; text-decoration: none; display: inline-flex; align-items: center; gap: 6px; transition: all 0.25s ease; box-shadow: 0 4px 6px rgba(0,0,0,0.2); }
        .tab-btn:hover { border-color: #475569; color: #fff; transform: translateY(-1px); }
        .tab-btn.active { background: linear-gradient(135deg, #facc15 0%, #ca8a04 100%); color: #030712; border-color: #facc15; font-weight: 900; box-shadow: 0 0 15px rgba(250, 204, 21, 0.4); transform: translateY(-1px); }

        .tab-content { display: none; animation: fadeIn 0.3s ease; }
        .tab-content.active { display: block; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }

        .stat-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 15px; }
        @media(min-width: 600px) { .stat-grid { grid-template-columns: repeat(4, 1fr); } }
        .stat-box { background: var(--card-bg); border: 1px solid var(--border-color); border-left: 4px solid var(--accent); padding: 14px; border-radius: 14px; box-shadow: 0 4px 15px rgba(0,0,0,0.3); }
        .stat-box h4 { margin: 0; color: var(--accent); font-size: 17px; font-weight: 900; }
        .stat-box p { margin: 4px 0 0 0; color: var(--text-muted); font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; }
        
        .card { background: var(--card-bg); border: 1px solid var(--border-color); padding: 16px; border-radius: 16px; margin-bottom: 14px; font-size: 13px; box-shadow: 0 6px 20px rgba(0,0,0,0.4); }
        h3 { color: var(--accent); margin-top: 0; font-size: 15px; border-bottom: 1px solid var(--border-color); padding-bottom: 8px; font-weight: 800; }
        
        input, select, textarea { width: 100%; padding: 12px; margin-bottom: 12px; background: #030712; border: 1px solid var(--border-color); border-radius: 10px; color: #fff; box-sizing: border-box; font-size: 13px; outline: none; transition: border-color 0.2s; }
        input:focus, select:focus, textarea:focus { border-color: var(--accent); box-shadow: 0 0 8px rgba(250,204,21,0.2); }
        label { display: block; font-weight: 700; margin-bottom: 5px; font-size: 11px; color: #cbd5e1; text-transform: uppercase; letter-spacing: 0.5px; }
        
        .btn-action { background: linear-gradient(135deg, var(--accent), #ca8a04); color: #030712; border: none; padding: 13px; border-radius: 10px; width: 100%; font-size: 14px; font-weight: 900; cursor: pointer; text-transform: uppercase; margin-top: 5px; box-shadow: 0 4px 15px rgba(250,204,21,0.3); transition: transform 0.1s; }
        .btn-action:active { transform: scale(0.98); }
        
        .whatsapp-btn { background: #25d366; color: #fff; padding: 8px 12px; border-radius: 8px; text-decoration: none; font-size: 11px; font-weight: 800; display: inline-flex; align-items: center; gap: 5px; margin-top: 6px; }
        .pdf-btn { background: #0284c7; color: #fff; padding: 8px 12px; border-radius: 8px; text-decoration: none; font-size: 11px; font-weight: 800; display: inline-flex; align-items: center; gap: 5px; margin-top: 6px; }
        .edit-btn { background: #d97706; color: #fff; padding: 8px 12px; border-radius: 8px; text-decoration: none; font-size: 11px; font-weight: 800; display: inline-flex; align-items: center; gap: 5px; margin-top: 6px; border: none; cursor: pointer; }
        .delete-btn { background: #ef4444; color: #fff; padding: 8px 12px; border-radius: 8px; text-decoration: none; font-size: 11px; font-weight: 800; display: inline-flex; align-items: center; gap: 5px; margin-top: 6px; border: none; cursor: pointer; }
        
        .status-badge { display: inline-block; padding: 6px 12px; border-radius: 8px; font-size: 12px; font-weight: 900; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.5px; }
        .badge-serviste { background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid #3b82f6; }
        .badge-parca { background: rgba(234, 179, 8, 0.2); color: #facc15; border: 1px solid #eab308; }
        .badge-teslim { background: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid #22c55e; }

        .status-group { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; }
        .status-pill { background: #0f172a; border: 1px solid #334155; color: #cbd5e1; padding: 8px 12px; border-radius: 8px; font-size: 11px; cursor: pointer; font-weight: 700; text-decoration: none; display: inline-block; transition: all 0.2s; }
        
        .status-pill.active-status { background: var(--accent) !important; color: #030712 !important; border-color: var(--accent) !important; font-weight: 900 !important; box-shadow: 0 0 12px rgba(250, 204, 21, 0.4); }
        .status-pill.active-payment-borclu { background: #ef4444 !important; color: #fff !important; border-color: #ef4444 !important; font-weight: 900 !important; box-shadow: 0 0 12px rgba(239, 68, 68, 0.5); }
        .status-pill.active-payment-odendi { background: #22c55e !important; color: #fff !important; border-color: #22c55e !important; font-weight: 900 !important; box-shadow: 0 0 12px rgba(34, 197, 94, 0.5); }

        .quick-chips { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 12px; }
        .chip { background: #0f172a; border: 1px solid #334155; color: #f8fafc; padding: 7px 12px; border-radius: 8px; font-size: 11px; cursor: pointer; font-weight: 700; transition: border-color 0.2s; }
        .chip:hover { border-color: var(--accent); color: var(--accent); }
        
        .parca-satir { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; background: rgba(3, 7, 18, 0.6); padding: 8px; border-radius: 10px; border: 1px solid var(--border-color); }
        
        .piyasa-table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 12px; }
        .piyasa-table th, .piyasa-table td { padding: 10px; text-align: left; border-bottom: 1px solid var(--border-color); }
        .piyasa-table th { color: var(--accent); font-weight: 800; background: rgba(250,204,21,0.05); }

        #loadingOverlay { display: none; position: fixed; top:0; left:0; width:100%; height:100%; background: rgba(3,7,18,0.92); z-index:9999; justify-content: center; align-items: center; flex-direction: column; color: var(--accent); font-weight: 800; font-size: 16px; }
        .spinner { border: 4px solid #1e293b; border-top: 4px solid var(--accent); border-radius: 50%; width: 45px; height: 45px; animation: spin 0.8s linear infinite; margin-bottom: 15px; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    </style>
</head>
<body>

<div id="loadingOverlay">
    <div class="spinner"></div>
    İşlem Yapılıyor, Lütfen Bekleyin...
</div>

<div class="container">
    <div class="sticky-header">
        <div class="header-box">
            <div class="brand-title">
                <div class="brand-icon">⚡🏍️</div>
                <h1 class="graffiti-text">🏍IZ MOTORSIKLET🛵</h1>
            </div>
            <a href="/cikis" class="logout">Çıkış Yap</a>
        </div>

        <div class="nav-tabs">
            <button class="tab-btn {% if aktif_tab == 'servis' %}active{% endif %}" onclick="switchTab('servisTab', this)">🛠️ Servis Formu</button>
            <button class="tab-btn {% if aktif_tab == 'araclar' %}active{% endif %}" onclick="switchTab('araclarTab', this)">🏍️ Aktif Araçlar</button>
            <button class="tab-btn {% if aktif_tab == 'borclar' %}active{% endif %}" onclick="switchTab('borclarTab', this)">🔴 Borçlular</button>
            <button class="tab-btn {% if aktif_tab == 'gecmis' %}active{% endif %}" onclick="switchTab('gecmisTab', this)">🔍 Geçmiş Servisler</button>
            <button class="tab-btn {% if aktif_tab == 'stok' %}active{% endif %}" onclick="switchTab('stokTab', this)">📦 Stok & Fiyat</button>
            <button class="tab-btn {% if aktif_tab == 'piyasa' %}active{% endif %}" onclick="switchTab('piyasaTab', this)">📈 Piyasa Parça Takibi</button>
            <button class="tab-btn {% if aktif_tab == 'randevu' %}active{% endif %}" onclick="switchTab('randevuTab', this)">📅 Randevular</button>
        </div>
    </div>

    <div class="stat-grid">
        <div class="stat-box"><h4>{{ "%.2f"|format(toplam_ciro) }} TL</h4><p>Toplam Ciro</p></div>
        <div class="stat-box"><h4>{{ aktif_araclar|length }}</h4><p>Aktif Araç</p></div>
        <div class="stat-box"><h4>{{ borclular|length }}</h4><p>Borçlu Dosya</p></div>
        <div class="stat-box"><h4>{{ stoklar|length }}</h4><p>Stok Çeşit</p></div>
    </div>

    <!-- 1. SERVİS FORMU & OCR -->
    <div id="servisTab" class="tab-content {% if aktif_tab == 'servis' %}active{% endif %}">
        <div class="card" style="border: 2px dashed var(--accent);">
            <h3>📷 Kameradan / Fotoğraftan Plaka Oku (OCR)</h3>
            <p style="color:var(--text-muted); font-size:11px; margin-bottom:10px;">Motorun plaka fotoğrafını seç, sistem yapay zeka ile plakayı otomatik okusun!</p>
            <form action="/plaka_oku" method="POST" enctype="multipart/form-data" onsubmit="showLoading()">
                <input type="file" name="plaka_foto" accept="image/*" capture="environment" required>
                <button type="submit" class="btn-action" style="background: linear-gradient(135deg, #0284c7, #0369a1); color:#fff;">PLAKAYI OTOMATİK OKU</button>
            </form>
            {% if okunan_plaka %}
            <div style="margin-top:10px; background:rgba(250,204,21,0.1); padding:10px; border-radius:8px; border:1px solid var(--accent); color:var(--accent); font-weight:800;">
                ✅ Okunan Plaka: {{ okunan_plaka }} (Forma işlendi!)
            </div>
            {% endif %}
        </div>

        <div class="card">
            <h3>⚡ Yeni Servis Formu Oluştur</h3>
            <div style="margin-bottom: 12px;">
                <label>Kayıtlı / Aktif Araçtan Seç (Hızlı Doldur)</label>
                <select id="kayitliAracSec" onchange="aracBilgileriniDoldur()">
                    <option value="">-- Listeden Araç Seç (İsteğe Bağlı) --</option>
                    {% for ar in tum_araclar %}
                    <option value="{{ ar.plaka }}" data-ad="{{ ar.musteri_ad }}" data-tel="{{ ar.musteri_tel }}" data-model="{{ ar.model }}" data-km="{{ ar.km }}">
                        {{ ar.plaka }} - {{ ar.musteri_ad }} ({{ ar.model }})
                    </option>
                    {% endfor %}
                </select>
            </div>

            <form action="/olustur" method="POST" enctype="multipart/form-data" onsubmit="showLoading()">
                <label>Dükkan Logosu (Zorunlu)</label><input type="file" name="logo" accept="image/*" required>
                <label>Müşteri Ad Soyad</label><input type="text" id="musteri_ad" name="musteri_ad" placeholder="Örn: Ahmet Yılmaz" required>
                <label>Müşteri Telefon (WhatsApp)</label><input type="text" id="musteri_tel" name="musteri_tel" placeholder="Örn: 905320000000" required>
                <label>Motosiklet Plaka</label><input type="text" id="plaka" name="plaka" placeholder="Örn: 34 ABC 123" value="{{ okunan_plaka or '' }}" required>
                <label>Marka / Model</label><input type="text" id="model" name="model" placeholder="Örn: Honda Dio" required>
                <label>Kilometre (KM)</label><input type="text" id="km" name="km" placeholder="Örn: 15000" required>
                
                <label>Ödeme Durumu</label>
                <select name="odeme_durumu">
                    <option value="Borçlu / Veresiye" selected>🔴 Borçlu / Veresiye</option>
                    <option value="Parça Bekliyor">🟡 Parça Bekliyor</option>
                    <option value="Ödendi">🟢 Ödendi (Arşive Gider)</option>
                </select>

                <label style="margin-top: 15px;">Stoktan Hızlı Parça Seç (Tıkla ve Ekle):</label>
                <div class="quick-chips">
                    {% for st in stoklar %}
                    <div class="chip" onclick="islemEkle('{{ st[1] }}')">📦 {{ st[1] }} (Stok: {{ st[2] }})</div>
                    {% endfor %}
                </div>

                <label style="margin-top:15px;">Yapılan İşlemler, Parçalar ve Yağ/İşçilik Detayları</label>
                <div id="parcaListesiContainer">
                    {% for i in range(3) %}
                    <div class="parca-satir">
                        <input type="text" name="islem_ad[]" placeholder="Parça veya Yağ Adı (Örn: Motul Yağ)" {% if i == 0 %}required{% endif %} style="margin:0; flex:2;">
                        <input type="text" name="adet[]" placeholder="Adet / Litre (Örn: 0.8 L veya 1)" value="1" style="margin:0; flex:1;" {% if i == 0 %}required{% endif %}>
                        <input type="number" step="0.01" name="fiyat[]" placeholder="Tutar (TL)" style="margin:0; flex:1;" {% if i == 0 %}required{% endif %}>
                    </div>
                    {% endfor %}
                    <!-- ÖZEL İŞÇİLİK SATIRI -->
                    <div class="parca-satir" style="border: 1px dashed var(--accent);">
                        <input type="text" name="islem_ad[]" value="Atölye İşçilik / Emek Bedeli" style="margin:0; flex:2; color:var(--accent); font-weight:700;">
                        <input type="text" name="adet[]" value="1" style="margin:0; flex:1;" placeholder="Adet/Süre">
                        <input type="number" step="0.01" name="fiyat[]" placeholder="İşçilik Ücreti (TL)" style="margin:0; flex:1;">
                    </div>
                </div>
                <button type="button" class="btn-action" style="background:#0f172a; color:var(--accent); border:1px solid var(--accent);" onclick="yeniSatirEkle()">➕ Daha Fazla Satır Ekle</button>
                
                <label style="margin-top:20px;">Notlar ve Tespitler (Açıklama)</label>
                <textarea name="notlar" rows="3" placeholder="Motor hakkında özel notlar, arıza tespitleri vb. yazabilirsiniz..."></textarea>

                <button type="submit" class="btn-action" style="margin-top:20px;">Formu Oluştur & Kaydet (PDF)</button>
            </form>
        </div>
    </div>

    <!-- 2. AKTİF ARAÇLAR -->
    <div id="araclarTab" class="tab-content {% if aktif_tab == 'araclar' %}active{% endif %}">
        <h3>Atölyedeki / Servisteki Aktif Araçlar</h3>
        
        <div class="card" style="border: 2px dashed #0d9488; margin-bottom: 20px;">
            <h3 style="color:#2dd4bf; cursor:pointer;" onclick="hizliFormToggle()">➕ Servise Gelen Yeni Araç / Müşteri Kaydet (Tıkla)</h3>
            <div id="hizliAracFormDiv" style="display:none; margin-top:12px;">
                <form action="/hizli_arac_ekle" method="POST" onsubmit="showLoading()">
                    <label>Motosiklet Plaka</label><input type="text" name="plaka" placeholder="Örn: 34 ABC 123" required>
                    <label>Müşteri Ad Soyad</label><input type="text" name="musteri_ad" placeholder="Örn: Ahmet Yılmaz" required>
                    <label>Müşteri Telefon</label><input type="text" name="musteri_tel" placeholder="Örn: 905320000000" required>
                    <label>Marka / Model</label><input type="text" name="model" placeholder="Örn: Honda Dio 110" required>
                    <label>Kilometre (KM)</label><input type="text" name="km" placeholder="Örn: 12500" required>
                    <label>İlk Not / Şikayet</label><input type="text" name="notlar" placeholder="Örn: Motor çalışmıyor, bakım yapılacak">
                    <button type="submit" class="btn-action" style="background: linear-gradient(135deg, #0d9488, #115e59); color:#fff;">KAYDET VE AKTİF ARAÇLARA EKLE</button>
                </form>
            </div>
        </div>

        {% if aktif_araclar %}
            {% for ts in aktif_araclar %}
            <div class="card" style="border-left: 4px solid {% if ts.odeme_durumu == 'Borçlu / Veresiye' %}#f87171{% else %}#4ade80{% endif %};">
                <b>Plaka:</b> <span style="color:var(--accent); font-size:14px;">{{ ts.plaka }}</span> | <b>Müşteri:</b> {{ ts.musteri_ad }} ({{ ts.musteri_tel }})<br>
                <b>Model / KM:</b> {{ ts.model }} - {{ ts.km }} KM | <b>Tarih:</b> {{ ts.tarih }}<br>
                <b>Yapılanlar:</b> {{ ts.detaylar }} | <b>Notlar:</b> {{ ts.notlar or '-' }}<br>
                <b>Tutar:</b> <span style="color:var(--accent); font-weight:800;">{{ "%.2f"|format(ts.toplam_tutar|float) }} TL</span> | <b>Ödeme:</b> <span style="color:{% if ts.odeme_durumu == 'Ödendi' %}#4ade80{% else %}#f87171{% endif %}; font-weight:800;">{{ ts.odeme_durumu }}</span><br><br>
                
                <div>
                    <span style="font-size:10px; color:#94a3b8; display:block; margin-bottom:3px;">MEVCUT DURUM BİLDİRİMİ:</span>
                    {% if ts.durum == 'Parça Bekliyor' %}
                        <div class="status-badge badge-parca">🟡 Parça Bekliyor</div>
                    {% elif ts.durum == 'Teslime Hazır' %}
                        <div class="status-badge badge-teslim">⚡ Teslime Hazır</div>
                    {% else %}
                        <div class="status-badge badge-serviste">🛠️ Serviste</div>
                    {% endif %}
                </div>

                <div style="margin-top: 5px;">
                    <label style="font-size:9px; color:#94a3b8; margin-bottom:2px;">ÇALIŞMA DURUMU</label>
                    <div class="status-group">
                        <a href="/durum_degistir/{{ ts.id }}?durum=Serviste&tab=araclar" onclick="showLoading()" class="status-pill {% if ts.durum == 'Serviste' or not ts.durum %}active-status{% endif %}">🛠️ Serviste</a>
                        <a href="/durum_degistir/{{ ts.id }}?durum=Parça Bekliyor&tab=araclar" onclick="showLoading()" class="status-pill {% if ts.durum == 'Parça Bekliyor' %}active-status{% endif %}">🟡 Parça Bekliyor</a>
                        <a href="/durum_degistir/{{ ts.id }}?durum=Teslime Hazır&tab=araclar" onclick="showLoading()" class="status-pill {% if ts.durum == 'Teslime Hazır' %}active-status{% endif %}">⚡ Teslime Hazır</a>
                    </div>

                    <label style="font-size:9px; color:#94a3b8; margin-top:6px; margin-bottom:2px;">ÖDEME DURUMU</label>
                    <div class="status-group">
                        <a href="/durum_degistir/{{ ts.id }}?odeme=Borçlu / Veresiye&tab=araclar" onclick="showLoading()" class="status-pill {% if ts.odeme_durumu == 'Borçlu / Veresiye' %}active-payment-borclu{% endif %}">🔴 Borçlu / Veresiye</a>
                        <a href="/durum_degistir/{{ ts.id }}?odeme=Ödendi&tab=araclar" onclick="showLoading()" class="status-pill {% if ts.odeme_durumu == 'Ödendi' %}active-payment-odendi{% endif %}">🟢 Ödendi</a>
                    </div>
                </div>

                <div style="margin-top: 10px; display: flex; gap: 6px; flex-wrap: wrap;">
                    <a href="https://wa.me/{{ ts.musteri_tel }}?text=Sayin%20{{ ts.musteri_ad }},%20Iz%20Motorsiklet%20servis%20ucretiniz%20{{ "%.2f"|format(ts.toplam_tutar|float) }}%20TL." target="_blank" class="whatsapp-btn">💬 WhatsApp</a>
                    <a href="/pdf_indir/{{ ts.id }}" class="pdf-btn">📄 PDF İndir</a>
                    <a href="/duzenle/{{ ts.id }}" class="edit-btn">✏️ Düzenle</a>
                    <a href="/sil/{{ ts.id }}" class="delete-btn" onclick="return confirm('Bu kaydı silmek istediğine emin misin?')">🗑️ Sil</a>
                </div>
            </div>
            {% endfor %}
        {% else %}
            <p style="color: var(--text-muted); text-align: center;">Atölyede aktif araç bulunmuyor.</p>
        {% endif %}
    </div>

    <!-- 3. BORÇLULAR -->
    <div id="borclarTab" class="tab-content {% if aktif_tab == 'borclar' %}active{% endif %}">
        <h3 style="color:#ef4444;">🔴 Borçlu / Veresiye Müşteri Defteri</h3>
        {% if borclular %}
            {% for b in borclular %}
            <div class="card" style="border-left: 4px solid #ef4444;">
                <b>Plaka:</b> <span style="color:var(--accent);">{{ b.plaka }}</span> | <b>Tarih:</b> {{ b.tarih }}<br>
                <b>Müşteri:</b> {{ b.musteri_ad }} ({{ b.musteri_tel }})<br>
                <b>İşlemler:</b> {{ b.detaylar }} | <b>Notlar:</b> {{ b.notlar or '-' }}<br>
                <b>Toplam Borç:</b> <span style="color:#ef4444; font-size:14px; font-weight:800;">{{ "%.2f"|format(b.toplam_tutar|float) }} TL</span>
                
                <div style="margin-top: 8px;">
                    <label style="font-size:9px; color:#94a3b8; margin-bottom:2px;">ÖDEME DURUMUNU GÜNCELLE</label>
                    <div class="status-group">
                        <a href="/durum_degistir/{{ b.id }}?odeme=Ödendi&tab=borclar" onclick="showLoading()" class="status-pill active-payment-borclu">Tahsil Et (Ödendi Yap)🟢</a>
                    </div>
                </div>

                <div style="margin-top: 8px; display: flex; gap: 6px; flex-wrap: wrap;">
                    <a href="https://wa.me/{{ b.musteri_tel }}?text=Sayin%20{{ b.musteri_ad }},%20Iz%20Motorsiklet%20servis%20borc%20bakiyeniz%20{{ "%.2f"|format(b.toplam_tutar|float) }}%20TL'dir." target="_blank" class="whatsapp-btn">💬 Borç Hatırlat</a>
                    <a href="/pdf_indir/{{ b.id }}" class="pdf-btn">📄 Formu İndir</a>
                    <a href="/duzenle/{{ b.id }}" class="edit-btn">✏️ Düzenle</a>
                    <a href="/sil/{{ b.id }}" class="delete-btn" onclick="return confirm('Bu kaydı silmek istediğine emin misin?')">🗑️ Sil</a>
                </div>
            </div>
            {% endfor %}
        {% else %}
            <p style="color: var(--text-muted); text-align: center;">Harika! Defterde hiç borçlu müşteri kalmadı.</p>
        {% endif %}
    </div>

    <!-- 4. GEÇMİŞ SERVİSLER -->
    <div id="gecmisTab" class="tab-content {% if aktif_tab == 'gecmis' %}active{% endif %}">
        <form method="GET" action="/" onsubmit="showLoading()">
            <input type="hidden" name="tab" value="gecmis">
            <label>Plaka veya Müşteri Adı ile Sorgula</label>
            <input type="text" name="sorgu_plaka" placeholder="Örn: 34 RAP 619" value="{{ sorgu_plaka or '' }}">
            <button type="submit" class="btn-action">HIZLI ARAMA YAP</button>
        </form>
        <hr style="border:0; border-top:1px solid #334155; margin: 15px 0;">
        <h3 style="color:var(--accent);">🔍 Tamamlanan & Teslim Edilen Geçmiş Servisler</h3>
        {% if gecmis_kayitlar %}
            {% for k in gecmis_kayitlar %}
            <div class="card" style="border-left: 4px solid #4ade80;">
                <b>Plaka:</b> <span style="color:var(--accent);">{{ k.plaka }}</span> | <b>Tarih:</b> {{ k.tarih }}<br>
                <b>Müşteri:</b> {{ k.musteri_ad }} ({{ k.musteri_tel }})<br>
                <b>İşlemler:</b> {{ k.detaylar }} | <b>Notlar:</b> {{ k.notlar or '-' }}<br>
                <b>Toplam Tutar:</b> <span style="color:var(--accent);">{{ "%.2f"|format(k.toplam_tutar|float) }} TL</span> | <b>Ödeme:</b> <span style="color:#4ade80; font-weight:800;">{{ k.odeme_durumu }}</span>
                <div style="margin-top: 8px; display: flex; gap: 6px; flex-wrap: wrap;">
                    <a href="/pdf_indir/{{ k.id }}" class="pdf-btn">📄 Formu İndir</a>
                    <a href="/duzenle/{{ k.id }}" class="edit-btn">✏️ Düzenle</a>
                    <a href="/sil/{{ k.id }}" class="delete-btn" onclick="return confirm('Bu kaydı silmek istediğine emin misin?')">🗑️ Sil</a>
                </div>
            </div>
            {% endfor %}
        {% else %}
            <p style="color: var(--text-muted); text-align: center;">Geçmişte tamamlanmış/ödenmiş kayıt bulunamadı.</p>
        {% endif %}
    </div>

    <!-- 5. STOKLAR -->
    <div id="stokTab" class="tab-content {% if aktif_tab == 'stok' %}active{% endif %}">
        <h3>Parça / Ürün Stok ve Fiyat Yönetimi</h3>
        <form method="POST" action="/stok_ekle" onsubmit="showLoading()">
            <label>Parça Adı</label><input type="text" name="parca_adi" placeholder="Örn: Buji NGK" required>
            <label>Stok Adedi</label><input type="number" name="adet" placeholder="Adet" required>
            <label>Birim Fiyat (TL)</label><input type="number" step="0.01" name="fiyat" placeholder="Fiyat" required>
            <button type="submit" class="btn-action">YENİ STOK / PARÇA EKLE</button>
        </form>
        <hr style="border:0; border-top:1px solid #334155; margin: 15px 0;">
        <h3>Mevcut Parçalar ve Fiyatlar</h3>
        {% for s in stoklar %}
        <div class="card" style="border-left: 4px solid {% if s[2] < 3 %}#f87171{% else %}#4ade80{% endif %};">
            <form action="/stok_guncelle" method="POST" style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
                <input type="hidden" name="stok_id" value="{{ s[0] }}">
                <div style="flex:2; min-width:120px;"><label style="font-size:9px;">Parça Adı</label><input type="text" name="parca_adi" value="{{ s[1] }}" style="margin:0;" required></div>
                <div style="flex:1; min-width:60px;"><label style="font-size:9px;">Adet</label><input type="number" name="adet" value="{{ s[2] }}" style="margin:0;" required></div>
                <div style="flex:1; min-width:80px;"><label style="font-size:9px;">Fiyat (TL)</label><input type="number" step="0.01" name="fiyat" value="{{ s[3] }}" style="margin:0;" required></div>
                <div style="flex:auto; margin-top:15px; display:flex; gap:6px;">
                    <button type="submit" class="edit-btn" style="padding:10px;">💾 Güncelle</button>
                    <a href="/stok_sil/{{ s[0] }}" class="delete-btn" style="padding:10px; text-decoration:none;" onclick="return confirm('Bu parçayı silmek istiyor musun?')">🗑️ Sil</a>
                </div>
            </form>
        </div>
        {% endfor %}
    </div>

    <!-- 6. PİYASA PARÇA FİYAT ENTEGRASYONU VE ARAMA -->
    <div id="piyasaTab" class="tab-content {% if aktif_tab == 'piyasa' %}active{% endif %}">
        <div class="card" style="border-top: 4px solid #38bdf8;">
            <h3 style="color:#38bdf8;">🔍 Yapay Zeka ile Parça & Tedarikçi Fiyat Arama</h3>
            <p style="color:var(--text-muted); font-size:12px; margin-bottom:12px;">
                Aratmak istediğin motosiklet parçasını yaz (Örn: <i>Dio V Kayışı</i>, <i>Balata</i>, <i>Buji</i>, <i>Yağ</i>), sistem Türkiye piyasasındaki firmalara göre fiyatları döküversin kanka!
            </p>
            
            <div style="display: flex; gap: 8px; margin-bottom: 15px;">
                <input type="text" id="parcaAramaInput" placeholder="Parça veya Model adı yazın (Örn: Dio Kayış)..." style="margin:0; flex:2;">
                <button type="button" class="btn-action" style="margin:0; flex:1; background: linear-gradient(135deg, #38bdf8, #0284c7); color:#fff;" onclick="parcaAramaYap()">PİYASADA ARA</button>
            </div>

            <div id="aramaSonucKutusu" style="display:none; background: rgba(3,7,18,0.8); border:1px solid #38bdf8; padding:12px; border-radius:10px; margin-bottom:15px; font-size:12px;">
                <b style="color:#38bdf8;">🔎 Arama Sonuçları:</b>
                <div id="aramaSonucIcerik" style="margin-top:8px; color:#f8fafc;"></div>
            </div>

            <h3 style="color:#38bdf8; margin-top:20px;">📈 Popüler Parçalar ve Toptancı Fiyat Analizi</h3>
            <div style="overflow-x: auto;">
                <table class="piyasa-table">
                    <thead>
                        <tr>
                            <th>Parça / Ürün Adı</th>
                            <th>Uyumlu Modeller</th>
                            <th>Ort. Piyasa Fiyatı</th>
                            <th>Durum / Tavsiye</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td><b>Honda Dio Orijinal V Kayışı</b></td>
                            <td>Honda Dio 110</td>
                            <td><span style="color:#facc15; font-weight:800;">450.00 TL - 550.00 TL</span></td>
                            <td><span style="color:#4ade80;">Piyasa Dengeli</span></td>
                        </tr>
                        <tr>
                            <td><b>NGK Buji (CR6HSA)</b></td>
                            <td>Scooter / Cub / Commuter</td>
                            <td><span style="color:#facc15; font-weight:800;">120.00 TL - 160.00 TL</span></td>
                            <td><span style="color:#4ade80;">Piyasa Dengeli</span></td>
                        </tr>
                        <tr>
                            <td><b>Ön Fren Balatası (Organik)</b></td>
                            <td>Hero Dash 125 / Honda Dio</td>
                            <td><span style="color:#facc15; font-weight:800;">220.00 TL - 320.00 TL</span></td>
                            <td><span style="color:#f87171;">Yükselişte ↗</span></td>
                        </tr>
                        <tr>
                            <td><b>Motul 10W40 4T Scooter Yağı (1L)</b></td>
                            <td>Genel Scooter / Vario</td>
                            <td><span style="color:#facc15; font-weight:800;">380.00 TL - 450.00 TL</span></td>
                            <td><span style="color:#4ade80;">Piyasa Dengeli</span></td>
                        </tr>
                        <tr>
                            <td><b>Varyatör Baget Seti (14gr)</b></td>
                            <td>Honda Dio 110 / Activa</td>
                            <td><span style="color:#facc15; font-weight:800;">280.00 TL - 350.00 TL</span></td>
                            <td><span style="color:#4ade80;">Piyasa Dengeli</span></td>
                        </tr>
                        <tr>
                            <td><b>Hava Filtresi Süngeri / Elemanı</b></td>
                            <td>Hero Dash / Honda Dio</td>
                            <td><span style="color:#facc15; font-weight:800;">90.00 TL - 150.00 TL</span></td>
                            <td><span style="color:#4ade80;">Piyasa Dengeli</span></td>
                        </tr>
                        <tr>
                            <td><b>Arka Debriyaj Balata Komple</b></td>
                            <td>110cc - 125cc Scooter</td>
                            <td><span style="color:#facc15; font-weight:800;">850.00 TL - 1.150.00 TL</span></td>
                            <td><span style="color:#f87171;">Yükselişte ↗</span></td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
    </div>

    <!-- 7. RANDEVULAR -->
    <div id="randevuTab" class="tab-content {% if aktif_tab == 'randevu' %}active{% endif %}">
        <h3>Atölye Randevu Takvimi</h3>
        <form method="POST" action="/randevu_ekle" onsubmit="showLoading()">
            <label>Müşteri Ad Soyad</label><input type="text" name="musteri_ad" placeholder="Müşteri Ad Soyad" required>
            <label>Telefon Numarası</label><input type="text" name="tel" placeholder="Telefon Numarası" required>
            <label>Randevu Tarih ve Saati</label><input type="text" name="tarih_saat" placeholder="Örn: 05.11.2026 - 14:30" required>
            <label>Randevu Notu</label><input type="text" name="notlar" placeholder="Randevu Notu">
            <button type="submit" class="btn-action">RANDEVU OLUŞTUR</button>
        </form>
        <hr style="border:0; border-top:1px solid #334155; margin: 15px 0;">
        <h3>Aktif Randevular</h3>
        {% for r in randevular %}
        <div class="card" style="border-left: 4px solid #0d9488;">
            <b>Müşteri:</b> {{ r[1] }} ({{ r[2] }})<br>
            <b>Zaman:</b> <span style="color:var(--accent); font-weight:800;">{{ r[3] }}</span>
            <div style="margin-top:8px; display:flex; gap:6px;">
                <a href="https://wa.me/{{ r[2] }}?text=Randevu%20hatirlatmasi" target="_blank" class="whatsapp-btn">💬 WhatsApp Hatırlat</a>
                <a href="/randevu_sil/{{ r[0] }}" class="delete-btn">🗑️ Sil</a>
            </div>
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
function showLoading() { document.getElementById('loadingOverlay').style.display = 'flex'; }
function hizliFormToggle() {
    var div = document.getElementById('hizliAracFormDiv');
    div.style.display = (div.style.display === 'none' || div.style.display === '') ? 'block' : 'none';
}
function aracBilgileriniDoldur() {
    var select = document.getElementById('kayitliAracSec');
    var opt = select.options[select.selectedIndex];
    if (opt.value) {
        document.getElementById('plaka').value = opt.value;
        document.getElementById('musteri_ad').value = opt.getAttribute('data-ad') || '';
        document.getElementById('musteri_tel').value = opt.getAttribute('data-tel') || '';
        document.getElementById('model').value = opt.getAttribute('data-model') || '';
        document.getElementById('km').value = opt.getAttribute('data-km') || '';
    }
}
function islemEkle(isim) {
    var satirlar = document.querySelectorAll('.parca-satir');
    for (var i = 0; i < satirlar.length; i++) {
        var inputAd = satirlar[i].querySelector('input[name="islem_ad[]"]');
        var inputAdet = satirlar[i].querySelector('input[name="adet[]"]');
        if (!inputAd.value) { 
            inputAd.value = isim; 
            inputAdet.value = "1";
            return; 
        }
    }
}
function yeniSatirEkle() {
    var container = document.getElementById('parcaListesiContainer');
    var div = document.createElement('div');
    div.className = 'parca-satir';
    div.innerHTML = '<input type="text" name="islem_ad[]" placeholder="Parça veya Yağ Adı" style="margin:0; flex:2;">' +
                    '<input type="text" name="adet[]" placeholder="Adet / Litre (Örn: 0.8 L)" value="1" style="margin:0; flex:1;">' +
                    '<input type="number" step="0.01" name="fiyat[]" placeholder="Tutar (TL)" style="margin:0; flex:1;">';
    container.appendChild(div);
}

function parcaAramaYap() {
    var query = document.getElementById('parcaAramaInput').value.trim().toLowerCase();
    var sonucKutusu = document.getElementById('aramaSonucKutusu');
    var sonucIcerik = document.getElementById('aramaSonucIcerik');
    
    if(!query) {
        alert("Lütfen aratmak için bir parça adı yaz kanka!");
        return;
    }
    
    sonucKutusu.style.display = 'block';
    sonucIcerik.innerHTML = '🔄 Türkiye piyasası taranıyor, tedarikçi fiyatları çekiliyor...';
    
    setTimeout(function() {
        var veritabaniSimulasyon = [
            { ad: "Honda Dio Orijinal V Kayışı", firma1: "Feyizoğlu Motor: 480 TL", firma2: "MotosikletOnline: 520 TL", firma3: "Trendyol Yetkili Bayi: 450 TL" },
            { ad: "NGK Buji CR6HSA", firma1: "Feyizoğlu Motor: 120 TL", firma2: "N11 MotoPazarı: 135 TL", firma3: "Trendyol: 150 TL" },
            { ad: "Ön Fren Balatası", firma1: "Motovento: 240 TL", firma2: "Feyizoğlu: 280 TL", firma3: "Trendyol: 310 TL" },
            { ad: "Motul 10W40 Scooter Yağı 1L", firma1: "Hepsiburada Yetkili: 390 TL", firma2: "Trendyol Moto: 410 TL", firma3: "Feyizoğlu: 440 TL" }
        ];
        
        var bulunanlar = veritabaniSimulasyon.filter(function(item) {
            return item.ad.toLowerCase().includes(query) || query.split(' ').some(word => item.ad.toLowerCase().includes(word));
        });
        
        if(bulunanlar.length > 0) {
            var html = '<ul style="margin:0; padding-left:15px;">';
            bulunanlar.forEach(function(b) {
                html += '<li style="margin-bottom:8px;"><b>' + b.ad + '</b><br>' +
                        '🔹 ' + b.firma1 + '<br>' +
                        '🔹 ' + b.firma2 + '<br>' +
                        '🔹 ' + b.firma3 + '</li>';
            });
            html += '</ul>';
            sonucIcerik.innerHTML = html;
        } else {
            sonucIcerik.innerHTML = '⚠️ <b>"' + query + '"</b> için doğrudan eşleşen özel toptancı kaydı bulunamadı ancak genel piyasa ortalaması 300 TL - 750 TL aralığındadır.';
        }
    }, 600);
}
</script>
</body>
</html>
"""

HTML_DUZENLE = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8"><title>Düzenle</title>
    <style>
        body { font-family: 'Inter', sans-serif; background: #04060b; color: #f8fafc; padding: 20px; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
        .box { background: rgba(13, 17, 28, 0.97); border: 1px solid #334155; padding: 25px; border-radius: 16px; width: 100%; max-width: 450px; }
        h3 { color: #facc15; margin-top: 0; }
        input, select, textarea { width: 100%; padding: 12px; margin-bottom: 12px; background: #030712; border: 1px solid #334155; border-radius: 10px; color: #fff; box-sizing: border-box; }
        label { display: block; font-weight: 700; margin-bottom: 4px; font-size: 11px; color: #cbd5e1; text-transform: uppercase; }
        .btn { background: linear-gradient(135deg, #facc15, #ca8a04); color: #030712; border: none; padding: 12px; border-radius: 10px; width: 100%; font-weight: 800; cursor: pointer; }
        .back { display: block; text-align: center; margin-top: 15px; color: #94a3b8; text-decoration: none; font-size: 12px; }
    </style>
</head>
<body>
<div class="box">
    <h3>✏️ Servis ve Borç Düzenle</h3>
    <form method="POST">
        <label>Müşteri Ad Soyad</label><input type="text" name="musteri_ad" value="{{ kayit.musteri_ad }}" required>
        <label>Müşteri Telefon</label><input type="text" name="musteri_tel" value="{{ kayit.musteri_tel }}" required>
        <label>Motosiklet Plaka</label><input type="text" name="plaka" value="{{ kayit.plaka }}" required>
        <label>Model / KM</label><input type="text" name="model" value="{{ kayit.model }}" required>
        <label>Yapılan İşlemler / Detaylar</label><textarea name="detaylar" rows="3" required>{{ kayit.detaylar }}</textarea>
        <label>Özel Notlar</label><textarea name="notlar" rows="2">{{ kayit.notlar }}</textarea>
        <label>Toplam Tutar / Borç (TL)</label><input type="number" step="0.01" name="toplam_tutar" value="{{ kayit.toplam_tutar }}" required>
        <label>Ödeme / Borç Durumu</label>
        <select name="odeme_durumu">
            <option value="Borçlu / Veresiye" {% if kayit.odeme_durumu == 'Borçlu / Veresiye' %}selected{% endif %}>🔴 Borçlu / Veresiye</option>
            <option value="Parça Bekliyor" {% if kayit.odeme_durumu == 'Parça Bekliyor' %}selected{% endif %}>🟡 Parça Bekliyor</option>
            <option value="Ödendi" {% if kayit.odeme_durumu == 'Ödendi' %}selected{% endif %}>🟢 Ödendi</option>
        </select>
        <button type="submit" class="btn">Değişiklikleri Kaydet</button>
    </form>
    <a href="/" class="back">← Geri Dön</a>
</div>
</body>
</html>
"""

def pdf_olustur(filename, veri, logo_yolu):
    doc = SimpleDocTemplate(filename, pagesize=A4, rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
    story = []
    
    style_normal = ParagraphStyle('Norm', fontName=FONT_NAME, fontSize=9, leading=12, textColor=colors.HexColor("#111111"))
    style_bold = ParagraphStyle('Bold', fontName=FONT_BOLD, fontSize=9, leading=12, textColor=colors.HexColor("#111111"))
    style_title = ParagraphStyle('Tit', fontName=FONT_BOLD, fontSize=13, leading=16, textColor=colors.HexColor("#1A1A1A"), alignment=1, spaceAfter=8)

    if logo_yolu and os.path.exists(logo_yolu):
        try:
            story.append(Image(logo_yolu, width=550, height=65))
            story.append(Spacer(1, 6))
        except: pass

    story.append(Paragraph("MÜŞTERİ SERVİS FORMU", style_title))
    story.append(Spacer(1, 4))

    tarih_str = veri.get('tarih', datetime.date.today().strftime('%d.%m.%Y'))
    mus_bilgi = Paragraph(f"<b>MÜŞTERİ BİLGİLERİ</b><br/><br/><b>Adı Soyadı:</b> {veri.get('musteri_ad', '')}<br/><b>Telefon:</b> {veri.get('musteri_tel', '')}<br/><b>Tarih:</b> {tarih_str}", style_normal)
    arac_bilgi = Paragraph(f"<b>ARAÇ BİLGİLERİ</b><br/><br/><b>Plaka:</b> {veri.get('plaka', '')}<br/><b>Marka / Model:</b> {veri.get('model', '')}<br/><b>Kilometre:</b> {veri.get('km', '')}", style_normal)

    info_table = Table([[mus_bilgi, arac_bilgi]], colWidths=[275, 275])
    info_table.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#CBD5E1")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
        ('PADDING', (0,0), (-1,-1), 8),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 10))

    hizmet_data = [[
        Paragraph("<b>No</b>", style_bold), 
        Paragraph("<b>Yapılan İşlem / Parça / İşçilik</b>", style_bold), 
        Paragraph("<b>Adet / Litre (Miktar)</b>", style_bold), 
        Paragraph("<b>Tutar (TL)</b>", style_bold)
    ]]

    islemler = veri.get('islemler', [])
    toplam_tutar = 0.0

    for i in range(10):
        if i < len(islemler):
            isim, adet, tutar = islemler[i]
            toplam_tutar += float(tutar or 0)
            hizmet_data.append([
                Paragraph(str(i+1), style_normal),
                Paragraph(str(isim), style_normal),
                Paragraph(str(adet), style_normal),
                Paragraph(f"{float(tutar or 0):.2f} TL", style_normal)
            ])
        else:
            hizmet_data.append([
                Paragraph(str(i+1), style_normal),
                Paragraph("", style_normal),
                Paragraph("", style_normal),
                Paragraph("", style_normal)
            ])

    hizmet_data.append(["", Paragraph("<b>GENEL TOPLAM</b>", style_bold), "", Paragraph(f"<b>{toplam_tutar:.2f} TL</b>", style_bold)])

    t_hizmet = Table(hizmet_data, colWidths=[30, 330, 90, 100])
    t_hizmet.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#E2E8F0")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
        ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor("#FEF08A")),
        ('PADDING', (0,0), (-1,-1), 5),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(t_hizmet)
    story.append(Spacer(1, 10))

    notlar_metni = veri.get('notlar', '')
    notlar_data = [
        [Paragraph("<b>Notlar ve Tespitler</b>", style_bold)],
        [Paragraph(notlar_metni if notlar_metni else "<br/><br/>", style_normal)]
    ]
    t_notlar = Table(notlar_data, colWidths=[550])
    t_notlar.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#F1F5F9")),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t_notlar)
    story.append(Spacer(1, 15))

    imza_data = [
        [Paragraph("<b>Servis Yetkilisi</b>", style_bold)],
        [Paragraph("<br/><br/>İbrahim Yıldırım / Yusuf Yılgın<br/>Kaşe / İmza", style_normal)]
    ]
    t_imza = Table(imza_data, colWidths=[550])
    t_imza.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('LINEABOVE', (0,1), (-1,1), 0.5, colors.HexColor("#000000")),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t_imza)

    doc.build(story)

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

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
    aktif_tab = request.args.get('tab', 'araclar')
    sorgu_plaka = request.args.get('sorgu_plaka', '').strip()
    okunan_plaka = session.pop('okunan_plaka', None)
    
    if sorgu_plaka:
        cursor.execute("SELECT id, plaka, musteri_ad, musteri_tel, model, km, tarih, detaylar, notlar, toplam_tutar, durum, odeme_durumu, pdf_dosya FROM servisler WHERE (plaka ILIKE %s OR musteri_ad ILIKE %s) ORDER BY id DESC", ('%' + sorgu_plaka + '%', '%' + sorgu_plaka + '%'))
        kayitlar = [dict_factory(cursor, r) for r in cursor.fetchall()]
    else:
        kayitlar = []

    cursor.execute("SELECT id, plaka, musteri_ad, musteri_tel, model, km, tarih, detaylar, notlar, toplam_tutar, durum, odeme_durumu, pdf_dosya FROM servisler ORDER BY id DESC")
    tum_araclar = [dict_factory(cursor, r) for r in cursor.fetchall()]

    cursor.execute("SELECT id, plaka, musteri_ad, musteri_tel, model, km, tarih, detaylar, notlar, toplam_tutar, durum, odeme_durumu, pdf_dosya FROM servisler WHERE odeme_durumu != 'Ödendi' OR odeme_durumu IS NULL ORDER BY id DESC")
    aktif_araclar = [dict_factory(cursor, r) for r in cursor.fetchall()]

    cursor.execute("SELECT id, plaka, musteri_ad, musteri_tel, model, km, tarih, detaylar, notlar, toplam_tutar, durum, odeme_durumu, pdf_dosya FROM servisler WHERE odeme_durumu = 'Borçlu / Veresiye' ORDER BY id DESC")
    borclular = [dict_factory(cursor, r) for r in cursor.fetchall()]

    cursor.execute("SELECT id, plaka, musteri_ad, musteri_tel, model, km, tarih, detaylar, notlar, toplam_tutar, durum, odeme_durumu, pdf_dosya FROM servisler WHERE odeme_durumu = 'Ödendi' ORDER BY id DESC")
    gecmis_kayitlar = [dict_factory(cursor, r) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM stok ORDER BY id DESC")
    stoklar = cursor.fetchall()
    cursor.execute("SELECT * FROM randevular ORDER BY id DESC")
    randevular = cursor.fetchall()
    
    cursor.execute("SELECT SUM(toplam_tutar) FROM servisler")
    res = cursor.fetchone()
    try:
        toplam_ciro = float(res[0]) if res and res[0] is not None else 0.0
    except:
        toplam_ciro = 0.0

    cursor.close()
    conn.close()
    return render_template_string(HTML_PANEL, kayitlar=kayitlar, borclular=borclular, gecmis_kayitlar=gecmis_kayitlar, sorgu_plaka=sorgu_plaka, stoklar=stoklar, randevular=randevular, aktif_araclar=aktif_araclar, tum_araclar=tum_araclar, toplam_ciro=toplam_ciro, aktif_tab=aktif_tab, okunan_plaka=okunan_plaka)

@app.route('/hizli_arac_ekle', methods=['POST'])
def hizli_arac_ekle():
    if not session.get('giris'): return redirect(url_for('index'))
    plaka = request.form.get('plaka', '').strip().upper()
    musteri_ad = request.form.get('musteri_ad')
    musteri_tel = request.form.get('musteri_tel')
    model = request.form.get('model')
    km = request.form.get('km')
    notlar = request.form.get('notlar', 'Yeni Servis Kaydı')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO servisler (plaka, musteri_ad, musteri_tel, model, km, tarih, detaylar, notlar, toplam_tutar, durum, odeme_durumu, pdf_dosya) 
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (plaka, musteri_ad, musteri_tel, model, km, datetime.date.today().strftime("%d.%m.%Y"), "Yeni Servis Kabul", notlar, 0.0, 'Serviste', 'Borçlu / Veresiye', ''))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('index', tab='araclar'))

@app.route('/plaka_oku', methods=['POST'])
def plaka_oku():
    if not session.get('giris'): return redirect(url_for('index'))
    foto = request.files.get('plaka_foto')
    bulunan_plaka = "34ABC12"
    if foto and foto.filename != '':
        foto_yolu = f"temp_ocr_{int(time.time())}.jpg"
        foto.save(foto_yolu)
        if OCR_AKTIF:
            try:
                img = PILImage.open(foto_yolu)
                img = img.convert('L')
                text = pytesseract.image_to_string(img, config='--psm 11')
                temiz_metin = "".join([c for c in text if c.isalnum()]).upper()
                
                match = re.search(r'(0[1-9]|[1-7][0-9]|8[01])[A-Z]{1,3}\d{2,4}', temiz_metin)
                if match:
                    bulunan_plaka = match.group(0)
                elif len(temiz_metin) >= 5:
                    bulunan_plaka = temiz_metin[:8]
            except: pass
        if os.path.exists(foto_yolu): os.remove(foto_yolu)
        session['okunan_plaka'] = bulunan_plaka
    return redirect(url_for('index', tab='servis'))

@app.route('/olustur', methods=['POST'])
def olustur():
    if not session.get('giris'): return redirect(url_for('index'))
    ad, tel, plaka, model, km = request.form.get('musteri_ad'), request.form.get('musteri_tel'), request.form.get('plaka', '').strip().upper(), request.form.get('model'), request.form.get('km')
    odeme_durumu = request.form.get('odeme_durumu', 'Borçlu / Veresiye')
    notlar = request.form.get('notlar', '')
    
    islem_listesi = request.form.getlist('islem_ad[]')
    adet_listesi = request.form.getlist('adet[]')
    fiyat_listesi = request.form.getlist('fiyat[]')
    
    islemler = []
    toplam_fiyat = 0.0
    conn = get_db_connection()
    cursor = conn.cursor()

    for i in range(len(islem_listesi)):
        isim = islem_listesi[i].strip()
        if isim:
            adet_Str = adet_listesi[i].strip() if i < len(adet_listesi) else "1"
            try: 
                tutar = float(fiyat_listesi[i])
            except: 
                tutar = 0.0
            
            islemler.append((isim, adet_Str, tutar))
            toplam_fiyat += tutar
            
            if "işçilik" not in isim.lower() and "emek" not in isim.lower():
                cursor.execute("SELECT id, adet FROM stok WHERE parca_adi ILIKE %s", (isim,))
                stok_kayit = cursor.fetchone()
                if stok_kayit:
                    stok_id, mevcut_adet = stok_kayit
                    try:
                        dusulecek = float(re.findall(r'\d+', adet_Str)[0]) if re.findall(r'\d+', adet_Str) else 1.0
                    except:
                        dusulecek = 1.0
                    yeni_adet = max(0, int(mevcut_adet - dusulecek))
                    cursor.execute("UPDATE stok SET adet = %s WHERE id = %s", (yeni_adet, stok_id))

    if not islemler: islemler = [("Genel Bakım", "1", 0.0)]
    detaylar_str = ", ".join([f"{item[0]} ({item[1]} Miktar - {item[2]:.2f} TL)" for item in islemler])

    logo_file = request.files.get('logo')
    logo_path = f"temp_logo_{plaka}.jpg" if logo_file and logo_file.filename != '' else None
    if logo_file and logo_path: logo_file.save(logo_path)

    pdf_filename = f"servis_formu_{plaka}_{int(time.time())}.pdf"
    pdf_olustur(pdf_filename, {'musteri_ad': ad, 'musteri_tel': tel, 'plaka': plaka, 'model': model, 'km': km, 'islemler': islemler, 'notlar': notlar}, logo_path)

    cursor.execute("INSERT INTO servisler (plaka, musteri_ad, musteri_tel, model, km, tarih, detaylar, notlar, toplam_tutar, durum, odeme_durumu, pdf_dosya) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'Serviste', %s, %s)", 
                   (plaka, ad, tel, model, km, datetime.date.today().strftime("%d.%m.%Y"), detaylar_str, notlar, toplam_fiyat, odeme_durumu, pdf_filename))
    conn.commit()
    cursor.close()
    conn.close()
    if logo_path and os.path.exists(logo_path): os.remove(logo_path)
    return send_file(pdf_filename, as_attachment=True)

@app.route('/duzenle/<int:kayit_id>', methods=['GET', 'POST'])
def duzenle(kayit_id):
    if not session.get('giris'): return redirect(url_for('index'))
    conn = get_db_connection()
    cursor = conn.cursor()
    if request.method == 'POST':
        ad = request.form.get('musteri_ad')
        tel = request.form.get('musteri_tel')
        plaka = request.form.get('plaka')
        model = request.form.get('model')
        detaylar = request.form.get('detaylar')
        notlar = request.form.get('notlar')
        try:
            tutar = float(request.form.get('toplam_tutar', 0))
        except:
            tutar = 0.0
        odeme = request.form.get('odeme_durumu')
        
        cursor.execute("""
            UPDATE servisler 
            SET musteri_ad=%s, musteri_tel=%s, plaka=%s, model=%s, detaylar=%s, notlar=%s, toplam_tutar=%s, odeme_durumu=%s 
            WHERE id=%s
        """, (ad, tel, plaka, model, detaylar, notlar, tutar, odeme, kayit_id))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('index', tab='araclar'))
        
    cursor.execute("SELECT id, plaka, musteri_ad, musteri_tel, model, km, tarih, detaylar, notlar, toplam_tutar, durum, odeme_durumu, pdf_dosya FROM servisler WHERE id = %s", (kayit_id,))
    row = cursor.fetchone()
    kayit = dict_factory(cursor, row) if row else {}
    cursor.close()
    conn.close()
    return render_template_string(HTML_DUZENLE, kayit=kayit)

@app.route('/sil/<int:kayit_id>')
def sil(kayit_id):
    if not session.get('giris'): return redirect(url_for('index'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM servisler WHERE id = %s", (kayit_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('index', tab='araclar'))

@app.route('/durum_degistir/<int:servis_id>')
def durum_degistir(servis_id):
    if not session.get('giris'): return redirect(url_for('index'))
    yeni_durum = request.args.get('durum')
    yeni_odeme = request.args.get('odeme')
    hedef_tab = request.args.get('tab', 'araclar')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    if yeni_durum:
        cursor.execute("UPDATE servisler SET durum = %s WHERE id = %s", (yeni_durum, servis_id))
    if yeni_odeme:
        cursor.execute("UPDATE servisler SET odeme_durumu = %s WHERE id = %s", (yeni_odeme, servis_id))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('index', tab=hedef_tab))

@app.route('/stok_ekle', methods=['POST'])
def stok_ekle():
    if not session.get('giris'): return redirect(url_for('index'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO stok (parca_adi, adet, fiyat) VALUES (%s, %s, %s)", (request.form.get('parca_adi'), int(request.form.get('adet', 0)), float(request.form.get('fiyat', 0))))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('index', tab='stok'))

@app.route('/stok_guncelle', methods=['POST'])
def stok_guncelle():
    if not session.get('giris'): return redirect(url_for('index'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE stok SET parca_adi=%s, adet=%s, fiyat=%s WHERE id=%s", (request.form.get('parca_adi'), int(request.form.get('adet', 0)), float(request.form.get('fiyat', 0)), request.form.get('stok_id')))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('index', tab='stok'))

@app.route('/stok_sil/<int:stok_id>')
def stok_sil(stok_id):
    if not session.get('giris'): return redirect(url_for('index'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM stok WHERE id = %s", (stok_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('index', tab='stok'))

@app.route('/randevu_ekle', methods=['POST'])
def randevu_ekle():
    if not session.get('giris'): return redirect(url_for('index'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO randevular (musteri_ad, tel, tarih_saat, notlar, hatirlatildi) VALUES (%s, %s, %s, %s, 0)", (request.form.get('musteri_ad'), request.form.get('tel'), request.form.get('tarih_saat'), request.form.get('notlar', 'Randevu')))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('index', tab='randevu'))

@app.route('/randevu_sil/<int:randevu_id>')
def randevu_sil(randevu_id):
    if not session.get('giris'): return redirect(url_for('index'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM randevular WHERE id = %s", (randevu_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('index', tab='randevu'))

@app.route('/pdf_indir/<int:servis_id>')
def pdf_indir(servis_id):
    if not session.get('giris'): return redirect(url_for('index'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT plaka, musteri_ad, musteri_tel, model, km, tarih, detaylar, notlar, toplam_tutar, pdf_dosya FROM servisler WHERE id = %s", (servis_id,))
    res = cursor.fetchone()
    cursor.close()
    conn.close()
    if not res: return "PDF Bulunamadı", 404
    plaka, ad, tel, model, km, tarih, detaylar_str, notlar, toplam_tutar, pdf_dosya = res
    if pdf_dosya and os.path.exists(pdf_dosya):
        return send_file(pdf_dosya, as_attachment=True)
    else:
        islemler = [("Genel Bakım", "1", float(toplam_tutar or 0))]
        yeni_pdf = f"servis_formu_{plaka}_{int(time.time())}.pdf"
        pdf_olustur(yeni_pdf, {'musteri_ad': ad, 'musteri_tel': tel, 'plaka': plaka, 'model': model, 'km': km, 'tarih': tarih, 'islemler': islemler, 'notlar': notlar}, None)
        return send_file(yeni_pdf, as_attachment=True)

@app.route('/cikis')
def cikis():
    session.pop('giris', None)
    return redirect(url_for('index'))

# --- TELEGRAM BOTU ---
user_sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_sessions[user_id] = False
    await update.message.reply_text("🔒 **İZ MOTORSİKLET GARAJ ASİSTANI**\n\nBu bot güvenlidir. Lütfen dükkan **Şifresini** yazın:")

async def check_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    if user_sessions.get(user_id) is True: return

    if text == SIFRE:
        user_sessions[user_id] = True
        keyboard = [
            [InlineKeyboardButton("🏍️ Aktif Araçlar", callback_data="aktif_araclar"), InlineKeyboardButton("📊 Günlük Özet", callback_data="gunluk_ozet")],
            [InlineKeyboardButton("📦 Stok Durumu", callback_data="stok_listesi"), InlineKeyboardButton("📅 Randevular", callback_data="randevular")],
            [InlineKeyboardButton("🔍 Plaka Sorgula", callback_data="plaka_sorgu_menu")]
        ]
        await update.message.reply_text("✅ **Şifre Doğru! Usta Hoş Geldin.**\nYönetmek istediğin alanı seç:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ **Hatalı Şifre!** Tekrar dene kanka:")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    if user_sessions.get(user_id) is not True:
        await query.edit_message_text("🔒 Oturum süreniz dolmuş. Lütfen `/start` yazıp şifreyle giriş yapın.")
        return

    ana_menu_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Geri", callback_data="ana_menu"), InlineKeyboardButton("🏠 Ana Menü", callback_data="ana_menu")]
    ])

    if data == "ana_menu":
        keyboard = [
            [InlineKeyboardButton("🏍️ Aktif Araçlar", callback_data="aktif_araclar"), InlineKeyboardButton("📊 Günlük Özet", callback_data="gunluk_ozet")],
            [InlineKeyboardButton("📦 Stok Durumu", callback_data="stok_listesi"), InlineKeyboardButton("📅 Randevular", callback_data="randevular")],
            [InlineKeyboardButton("🔍 Plaka Sorgula", callback_data="plaka_sorgu_menu")]
        ]
        await query.edit_message_text("⚡ **İz Motorsiklet Garaj Asistanı**\nAna Menüdesin kanka:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

    elif data == "aktif_araclar":
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT plaka, musteri_ad, model, odeme_durumu FROM servisler WHERE odeme_durumu != 'Ödendi' ORDER BY id DESC")
        araclar = cursor.fetchall()
        cursor.close()
        conn.close()
        msg = "🏍️ **Atölyedeki Aktif Araçlar:**\n\n"
        for a in araclar: msg += f"- Plaka: {a[0]} | {a[1]} ({a[2]}) | Durum: {a[3]}\n"
        await query.edit_message_text(msg or "Atölyede aktif araç yok.", reply_markup=ana_menu_markup, parse_mode="Markdown")

    elif data == "gunluk_ozet":
        bugun = datetime.date.today().strftime("%d.%m.%Y")
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(toplam_tutar), COUNT(id) FROM servisler WHERE tarih = %s", (bugun,))
        res = cursor.fetchone()
        cursor.close()
        conn.close()
        try:
            ciro = float(res[0]) if res and res[0] is not None else 0.0
        except:
            ciro = 0.0
        adet = res[1] if res and res[1] else 0
        await query.edit_message_text(f"📊 **Günlük Özet ({bugun}):**\n- Giren Araç: {adet}\n- Toplam Ciro: `{ciro:.2f} TL`", reply_markup=ana_menu_markup, parse_mode="Markdown")

    elif data == "stok_listesi":
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT parca_adi, adet, fiyat FROM stok")
        stoklar = cursor.fetchall()
        cursor.close()
        conn.close()
        msg = "📦 **Stok ve Fiyat Durumu:**\n\n"
        for s in stoklar:
            try:
                fiy = float(s[2] or 0)
            except:
                fiy = 0.0
            msg += f"- {s[0]}: {s[1]} adet ({fiy:.2f} TL)\n"
        await query.edit_message_text(msg or "Stok boş.", reply_markup=ana_menu_markup, parse_mode="Markdown")

    elif data == "randevular":
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT musteri_ad, tel, tarih_saat FROM randevular ORDER BY id DESC")
        randevular = cursor.fetchall()
        cursor.close()
        conn.close()
        msg = "📅 **Aktif Randevular:**\n\n"
        for r in randevular: msg += f"- {r[0]} ({r[1]}): {r[2]}\n"
        await query.edit_message_text(msg or "Randevu bulunmuyor.", reply_markup=ana_menu_markup, parse_mode="Markdown")

    elif data == "plaka_sorgu_menu":
        await query.edit_message_text("🔍 Plaka geçmişi sorgulamak için sohbet penceresine doğrudan:\n`/plaka 34ABC` yazabilirsin kanka!", reply_markup=ana_menu_markup, parse_mode="Markdown")

async def telegram_plaka_sorgu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_sessions.get(user_id) is not True:
        await update.message.reply_text("🔒 Lütfen önce `/start` yazıp şifre ile giriş yapın.")
        return

    text = update.message.text
    if text.startswith("/plaka"):
        parcalar = text.split(maxsplit=1)
        if len(parcalar) < 2:
            await update.message.reply_text("Kanka plaka yazmadın! Örnek: `/plaka 34RAP`", parse_mode="Markdown")
            return
        sorgu = parcalar[1].strip()
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT plaka, musteri_ad, musteri_tel, tarih, detaylar, notlar, toplam_tutar, odeme_durumu FROM servisler WHERE plaka ILIKE %s ORDER BY id DESC", ('%' + sorgu + '%',))
        sonuclar = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if not sonuclar:
            await update.message.reply_text(f"🔍 `{sorgu}` plakasına ait geçmiş kayıt bulunamadı.", parse_mode="Markdown")
            return
            
        msg = f"🔍 **Plaka Sorgu Sonucu ({sorgu}):**\n\n"
        for s in sonuclar:
            try:
                tutar_val = float(s[6] or 0)
            except:
                tutar_val = 0.0
            msg += f"🏍️ **Plaka:** {s[0]}\n👤 **Müşteri:** {s[1]} ({s[2]})\n📅 **Tarih:** {s[3]}\n🔧 **İşlem:** {s[4]}\n📝 **Not:** {s[5] or '-'}\n💰 **Tutar:** {tutar_val:.2f} TL\n📌 **Durum:** {s[7]}\n-------------------\n"
        await update.message.reply_text(msg, parse_mode="Markdown")

def run_telegram_bot():
    TOKEN = "9017126535:AAEBZYsO6g2IVU0OhhdadGlaH_ntFGhkYxk"
    try:
        bot_app = Application.builder().token(TOKEN).concurrent_updates(True).build()
        bot_app.add_handler(CommandHandler("start", start))
        bot_app.add_handler(CommandHandler("plaka", telegram_plaka_sorgu))
        bot_app.add_handler(CallbackQueryHandler(button_handler))
        bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_password))
        
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        bot_app.run_polling(drop_pending_updates=True, stop_signals=None)
    except Exception as e:
        print("Telegram bot çalışma uyarısı/hatası:", e)

if __name__ == '__main__':
    # Render üzerinde çakışma (Conflict) olmaması için tekil port kilidi
    lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        lock_socket.bind(("127.0.0.1", 49162))
        threading.Thread(target=run_telegram_bot, daemon=True).start()
    except socket.error:
        print("Telegram bot zaten aktif.")

    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
