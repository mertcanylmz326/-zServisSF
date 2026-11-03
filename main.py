import os
import datetime
import time
import threading
import psycopg2
from flask import Flask, render_template_string, request, send_file, session, redirect, url_for
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

app = Flask(__name__)
app.secret_key = "iz_motor_gizli_anahtar_erp_postgres_v47"

SIFRE = "izmotor2026*"
TELEGRAM_ADMIN_CHAT_ID = None

# Doğrudan Supabase 5432 Portlu Doğrudan Bağlantı (Şifrendeki * işareti %2A yapılmıştır)
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:izmotor2026%2A@db.dcyoerlxjonqmbatennf.supabase.co:5432/postgres")

def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    return conn

# --- VERİTABANI KURULUMU (PostgreSQL) ---
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
        print("Supabase Veritabanı bağlantısı ve tablolar başarılı!")
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

# --- HTML ARAYÜZ (KARBON FİBER GARAJ TASARIMI) ---
HTML_LOGIN = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>İz Motorsiklet - Giriş</title>
    <style>
        body { 
            font-family: 'Inter', 'Segoe UI', sans-serif; 
            background-color: #0b0f19;
            background-image: 
                radial-gradient(rgba(250, 204, 21, 0.08) 1px, transparent 1px),
                linear-gradient(135deg, #050811 0%, #0f172a 100%);
            background-size: 20px 20px, 100% 100%;
            display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; padding: 20px; box-sizing: border-box; color: #f8fafc; 
        }
        .login-box { background: rgba(11, 15, 25, 0.92); backdrop-filter: blur(25px); border: 1px solid rgba(250, 204, 21, 0.4); padding: 45px 30px; border-radius: 28px; box-shadow: 0 30px 60px rgba(0,0,0,0.9); width: 100%; max-width: 380px; text-align: center; }
        .logo-badge { font-size: 52px; margin-bottom: 12px; filter: drop-shadow(0 0 15px rgba(250,204,21,0.5)); }
        h2 { color: #f8fafc; margin-bottom: 6px; letter-spacing: 2px; font-weight: 800; font-size: 24px; text-transform: uppercase; }
        p { color: #94a3b8; font-size: 13px; margin-bottom: 30px; font-weight: 500; }
        input { width: 100%; padding: 16px; margin-bottom: 20px; background: rgba(3, 7, 18, 0.95); border: 1px solid #334155; border-radius: 14px; color: #fff; box-sizing: border-box; font-size: 16px; outline: none; text-align: center; letter-spacing: 2px; transition: 0.3s; }
        input:focus { border-color: #facc15; box-shadow: 0 0 20px rgba(250,204,21,0.4); }
        button { background: linear-gradient(135deg, #facc15 0%, #ca8a04 100%); color: #030712; border: none; padding: 16px; border-radius: 14px; width: 100%; font-size: 16px; font-weight: 800; cursor: pointer; text-transform: uppercase; letter-spacing: 1px; box-shadow: 0 8px 25px rgba(250,204,21,0.35); transition: 0.2s; }
        button:active { transform: scale(0.98); }
        .error { color: #ef4444; margin-bottom: 18px; font-size: 13px; font-weight: 700; background: rgba(239,68,68,0.12); padding: 12px; border-radius: 10px; border: 1px solid rgba(239,68,68,0.3); }
    </style>
</head>
<body>
<div class="login-box">
    <div class="logo-badge">🏍️</div>
    <h2>İZ MOTORSİKLET</h2>
    <p>Supabase Garaj Paneli</p>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
    <form method="POST">
        <input type="password" name="sifre" placeholder="••••••••••••" required autofocus>
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
    <title>İz Motorsiklet - Karbon ERP Paneli</title>
    <style>
        :root {
            --bg-main: #050811;
            --bg-card: rgba(11, 15, 25, 0.9);
            --border-color: rgba(51, 65, 85, 0.6);
            --accent-gold: #facc15;
            --accent-gold-dark: #ca8a04;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
        }
        body { 
            font-family: 'Inter', 'Segoe UI', Tahoma, sans-serif; 
            background-color: var(--bg-main);
            background-image: 
                radial-gradient(rgba(250, 204, 21, 0.05) 1px, transparent 1px),
                linear-gradient(135deg, #030712 0%, #0b0f19 50%, #050811 100%);
            background-size: 16px 16px, 100% 100%;
            margin: 0; padding: 10px; color: var(--text-main); box-sizing: border-box; 
        }
        .container { max-width: 900px; margin: 0 auto; background: var(--bg-card); backdrop-filter: blur(25px); padding: 18px; border-radius: 22px; box-shadow: 0 25px 60px rgba(0,0,0,0.9); border: 1px solid rgba(250,204,21,0.25); }
        
        .top-navbar { position: sticky; top: 0; z-index: 100; display: flex; flex-direction: column; gap: 10px; background: rgba(5, 8, 17, 0.96); backdrop-filter: blur(20px); padding: 12px; border-radius: 16px; border: 1px solid rgba(250,204,21,0.3); margin-bottom: 18px; box-shadow: 0 10px 30px rgba(0,0,0,0.6); }
        .navbar-header { display: flex; justify-content: space-between; align-items: center; width: 100%; border-bottom: 1px solid rgba(51,65,85,0.4); padding-bottom: 8px; }
        .brand-mini { display: flex; align-items: center; gap: 10px; }
        .brand-logo { background: linear-gradient(135deg, var(--accent-gold), var(--accent-gold-dark)); width: 34px; height: 34px; border-radius: 10px; display: flex; justify-content: center; align-items: center; font-size: 18px; box-shadow: 0 0 15px rgba(250,204,21,0.45); flex-shrink: 0; }
        .brand-title h1 { color: var(--accent-gold); margin: 0; font-size: 14px; text-transform: uppercase; letter-spacing: 1px; font-weight: 800; }
        .logout a { color: #f87171; text-decoration: none; font-size: 11px; font-weight: 700; padding: 6px 10px; background: rgba(248,113,113,0.12); border-radius: 8px; border: 1px solid rgba(248,113,113,0.3); transition: 0.2s; }
        .logout a:active { transform: scale(0.95); }

        .nav-tabs { display: flex; gap: 6px; overflow-x: auto; white-space: nowrap; padding-bottom: 2px; scrollbar-width: none; }
        .nav-tabs::-webkit-scrollbar { display: none; }
        
        .tab-btn { background: rgba(15, 23, 42, 0.95); color: var(--text-muted); border: 1px solid #1f2937; padding: 8px 14px; border-radius: 10px; cursor: pointer; font-weight: 700; font-size: 12px; transition: 0.2s; flex-shrink: 0; }
        .tab-btn:hover { color: #fff; background: rgba(30,41,59,0.95); }
        .tab-btn.active { background: linear-gradient(135deg, var(--accent-gold), var(--accent-gold-dark)); color: #030712; border-color: var(--accent-gold); box-shadow: 0 4px 15px rgba(250,204,21,0.4); font-weight: 800; }

        .dashboard-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 18px; }
        @media(min-width: 600px) { .dashboard-grid { grid-template-columns: repeat(4, 1fr); } }
        
        .stat-card { background: rgba(20, 27, 45, 0.6); border: 1px solid var(--border-color); padding: 12px; border-radius: 14px; position: relative; overflow: hidden; }
        .stat-card::after { content: ''; position: absolute; top: 0; left: 0; width: 3px; height: 100%; background: var(--accent-gold); border-radius: 3px 0 0 3px; }
        .stat-card h3 { margin: 0; font-size: 17px; color: var(--accent-gold); font-weight: 800; }
        .stat-card p { margin: 4px 0 0 0; color: var(--text-muted); font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; }

        .tab-content { display: none; animation: fadeIn 0.3s ease; }
        .tab-content.active { display: block; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }

        h3 { color: var(--accent-gold); border-bottom: 1px solid rgba(51,65,85,0.6); padding-bottom: 10px; margin-top: 0; font-size: 16px; font-weight: 800; }
        .form-group { margin-bottom: 14px; }
        label { display: block; font-weight: 700; margin-bottom: 5px; font-size: 12px; color: #cbd5e1; }
        input, textarea, select { width: 100%; padding: 12px; background: rgba(5, 8, 17, 0.95); border: 1px solid var(--border-color); border-radius: 12px; color: #fff; box-sizing: border-box; font-size: 14px; outline: none; transition: 0.2s; }
        input:focus, textarea:focus, select:focus { border-color: var(--accent-gold); box-shadow: 0 0 12px rgba(250,204,21,0.3); }
        
        .item-row { display: flex; flex-direction: column; gap: 8px; margin-bottom: 10px; background: rgba(20, 27, 45, 0.5); padding: 10px; border-radius: 12px; border: 1px solid var(--border-color); }
        @media(min-width: 550px) { .item-row { flex-direction: row; align-items: center; } }
        .item-row input.name-input { flex: 2; }
        .item-row select { flex: 1.5; background: rgba(5,8,17,0.95); font-size: 12px; }
        .item-row input.small { flex: 0.8; }
        
        .btn-add { background: #0d9488; color: #fff; border: none; padding: 12px; border-radius: 12px; cursor: pointer; font-weight: 800; width: 100%; margin-bottom: 14px; transition: 0.2s; }
        .btn-add:active { transform: scale(0.98); }
        .btn-remove { background: #dc2626; color: #fff; border: none; padding: 8px 12px; border-radius: 8px; cursor: pointer; font-weight: 800; align-self: flex-end; }
        @media(min-width: 550px) { .btn-remove { align-self: center; } }
        
        button[type="submit"], .btn-action { background: linear-gradient(135deg, var(--accent-gold), var(--accent-gold-dark)); color: #030712; border: none; padding: 14px; border-radius: 12px; cursor: pointer; width: 100%; font-size: 14px; font-weight: 800; margin-top: 14px; text-transform: uppercase; letter-spacing: 0.5px; box-shadow: 0 6px 20px rgba(250,204,21,0.35); transition: 0.2s; }
        button[type="submit"]:active, .btn-action:active { transform: scale(0.98); }
        
        .card { background: rgba(18, 24, 40, 0.75); border: 1px solid var(--border-color); padding: 16px; border-radius: 16px; margin-bottom: 14px; font-size: 13px; line-height: 1.5; box-shadow: 0 10px 30px rgba(0,0,0,0.4); transition: 0.2s; }
        .card:hover { border-color: rgba(250,204,21,0.4); }
        
        .status-controls { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 12px; }
        .status-box label { font-size: 10px; color: var(--text-muted); margin-bottom: 3px; text-transform: uppercase; font-weight: 700; }
        .status-box select { padding: 9px; font-size: 12px; background: rgba(5,8,17,0.98); border-radius: 10px; border: 1px solid var(--border-color); color: #fff; width: 100%; font-weight: 700; }

        .action-buttons { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
        .whatsapp-btn { background: #25d366; color: #fff; padding: 8px 12px; border-radius: 9px; text-decoration: none; font-size: 11px; font-weight: 800; display: inline-block; box-shadow: 0 4px 12px rgba(37,211,102,0.35); transition: 0.2s; }
        .whatsapp-btn:active { transform: scale(0.95); }
        .pdf-btn { background: #0284c7; color: #fff; padding: 8px 12px; border-radius: 9px; text-decoration: none; font-size: 11px; font-weight: 800; display: inline-block; box-shadow: 0 4px 12px rgba(2,132,199,0.35); transition: 0.2s; }
        .pdf-btn:active { transform: scale(0.95); }
        
        .alert-box { background: rgba(250,204,21,0.15); border: 1px solid var(--accent-gold); padding: 12px; border-radius: 12px; color: var(--accent-gold); margin-bottom: 15px; font-weight: 800; text-align: center; display: none; font-size: 12px; }
    </style>
</head>
<body>
<div class="container">
    <div class="top-navbar">
        <div class="navbar-header">
            <div class="brand-mini">
                <div class="brand-logo">🏍️</div>
                <div class="brand-title">
                    <h1>İz Motorsiklet</h1>
                </div>
            </div>
            <div class="logout"><a href="/cikis">Çıkış</a></div>
        </div>
        
        <div class="nav-tabs">
            <button class="tab-btn active" onclick="switchTab('formTab', this)">🛠️ Servis</button>
            <button class="tab-btn" onclick="switchTab('araclarTab', this)">🏍️ Araçlar</button>
            <button class="tab-btn" onclick="switchTab('historyTab', this)">🔍 Geçmiş</button>
            <button class="tab-btn" onclick="switchTab('stockTab', this)">📦 Stok</button>
            <button class="tab-btn" onclick="switchTab('randevuTab', this)">📅 Randevu</button>
            <button class="tab-btn" onclick="switchTab('reminderTab', this)">⏰ Bakım</button>
        </div>
    </div>
    
    <div class="dashboard-grid">
        <div class="stat-card"><h3>{{ "%.2f"|format(toplam_ciro) }} TL</h3><p>Toplam Ciro</p></div>
        <div class="stat-card"><h3>{{ aktif_araclar|length }}</h3><p>Aktif Araç</p></div>
        <div class="stat-card"><h3>{{ stoklar|length }}</h3><p>Stok Çeşit</p></div>
        <div class="stat-card"><h3>{{ randevular|length }}</h3><p>Randevular</p></div>
    </div>

    <div id="duplicateAlert" class="alert-box">⚠️ Bu servis formu az önce kaydedildi! Tekrar işlem yapılmadı.</div>

    <!-- 1. SERVİS FORMU -->
    <div id="formTab" class="tab-content active">
        <div style="background: rgba(20, 27, 45, 0.5); border: 1px solid rgba(250,204,21,0.3); padding: 14px; border-radius: 14px; margin-bottom: 18px;">
            <label style="color: var(--accent-gold); margin-bottom: 6px;">⚡ Kayıtlı Aktif Araçtan Seç (Otomatik Doldur)</label>
            <select id="aracSecici" onchange="aracBilgileriniDoldur(this)" style="background: rgba(5,8,17,0.95); font-size: 13px; padding: 11px;">
                <option value="">-- Listeden Araç Seç (İsteğe Bağlı) --</option>
                {% for ts in aktif_araclar %}
                <option value="{{ ts[1] }}" data-ad="{{ ts[2] }}" data-tel="{{ ts[3] }}" data-model="{{ ts[4] }}" data-km="{{ ts[5] }}">
                    {{ ts[1] }} - {{ ts[2] }} ({{ ts[4] }})
                </option>
                {% endfor %}
            </select>
        </div>

        <form id="serviceForm" action="/olustur" method="POST" enctype="multipart/form-data" onsubmit="handleFormSubmit(event)">
            <div class="form-group"><label>Dükkan Logosu <span style="color:var(--accent-gold);">(Zorunlu)</span></label><input type="file" name="logo" accept="image/*" required></div>
            <div class="form-group"><label>Hasar / Durum Fotoğrafı <span style="color:var(--text-muted);">(İsteğe Bağlı)</span></label><input type="file" name="hasar_foto" accept="image/*"></div>
            <div class="form-group"><label>Müşteri Adı Soyadı</label><input type="text" id="musteri_ad" name="musteri_ad" placeholder="Örn: Ahmet Yılmaz" required></div>
            <div class="form-group"><label>Müşteri Telefon (WhatsApp)</label><input type="text" id="musteri_tel" name="musteri_tel" placeholder="Örn: 905320000000" required></div>
            <div class="form-group"><label>Motosiklet Plaka</label><input type="text" id="plaka" name="plaka" placeholder="Örn: 34 ABC 123" required></div>
            <div class="form-group"><label>Marka / Model</label><input type="text" id="model" name="model" placeholder="Örn: Honda PCX 125" required></div>
            <div class="form-group"><label>Kilometre (KM)</label><input type="text" id="km" name="km" placeholder="Örn: 15000" required></div>
            
            <div class="form-group">
                <label>Ödeme / Borç Durumu</label>
                <select name="odeme_durumu" style="background: rgba(5,8,17,0.95);">
                    <option value="Borçlu / Veresiye" selected>🔴 Borçlu / Veresiye</option>
                    <option value="Parça Bekliyor">🟡 Parça Bekliyor</option>
                    <option value="Ödendi">🟢 Ödendi (Arşive Gider)</option>
                </select>
            </div>

            <hr style="margin: 20px 0; border: 0; border-top: 1px solid rgba(51,65,85,0.5);">
            <label><b>🛠️ Yapılan İşlemler ve Parçalar</b></label>
            <div id="items-container">
                <div class="item-row">
                    <input type="text" name="islem_ad[]" class="name-input" placeholder="İşlem / Parça Adı" required>
                    <select name="stok_id[]">
                        <option value="">-- Stoktan Düş (İsteğe Bağlı) --</option>
                        {% for s in stoklar %}
                        <option value="{{ s[0] }}">{{ s[1] }} (Stok: {{ s[2] }} | {{ s[3] }} TL)</option>
                        {% endfor %}
                    </select>
                    <input type="number" name="adet[]" class="small" placeholder="Adet" value="1" min="1">
                    <input type="number" step="0.01" name="fiyat[]" class="small" placeholder="Fiyat" required>
                </div>
            </div>
            <button type="button" class="btn-add" onclick="addItemRow()">+ Yeni İşlem / Parça Satırı Ekle</button>

            <div class="form-group"><label>Ek İşçilik Tutarı (TL)</label><input type="number" step="0.01" name="iscilik" placeholder="Örn: 500" value="0"></div>
            <div class="form-group"><label>Notlar ve Tespitler</label><textarea name="notlar" rows="2" placeholder="Örn: Genel bakım yapıldı."></textarea></div>

            <button type="submit" id="submitBtn">Servis Formu PDF İndir & Kaydet</button>
        </form>
    </div>

    <!-- 2. ARAÇLAR & DURUM -->
    <div id="araclarTab" class="tab-content">
        <h3>Atölyedeki / Servisteki Aktif Araçlar</h3>
        
        <div style="background: rgba(20, 27, 45, 0.5); border: 1px solid rgba(250,204,21,0.3); padding: 14px; border-radius: 14px; margin-bottom: 18px;">
            <h4 style="color: var(--accent-gold); margin-top: 0; margin-bottom: 8px; font-size: 13px; font-weight: 800;">➕ Doğrudan Servise Yeni Araç Ekle</h4>
            
            <div class="form-group" style="margin-bottom: 10px;">
                <label style="color: var(--accent-gold);">⚡ Daha Önce Gelen Eski Araçtan Seç</label>
                <select id="hizliPlakaSecici" onchange="hizliAracBilgileriniDoldur(this)" style="background: rgba(5,8,17,0.95); font-size: 13px; padding: 11px;">
                    <option value="">-- Geçmiş Araçlardan Seç (İsteğe Bağlı) --</option>
                    {% for g in gecmis_araclar %}
                    <option value="{{ g[1] }}" data-ad="{{ g[2] }}" data-tel="{{ g[3] }}" data-model="{{ g[4] }}" data-km="{{ g[5] }}">
                        {{ g[1] }} - {{ g[2] }} ({{ g[4] }})
                    </option>
                    {% endfor %}
                </select>
            </div>

            <form action="/arac_ekle_hizli" method="POST">
                <div style="display: flex; flex-direction: column; gap: 8px;">
                    <input type="text" id="h_plaka" name="plaka" placeholder="Plaka (Örn: 34 ABC)" required>
                    <input type="text" id="h_musteri_ad" name="musteri_ad" placeholder="Müşteri Ad Soyad" required>
                    <input type="text" id="h_musteri_tel" name="musteri_tel" placeholder="Telefon (90532...)" required>
                    <input type="text" id="h_model" name="model" placeholder="Model (Örn: Honda Dio)" required>
                    <input type="text" id="h_km" name="km" placeholder="KM (Örn: 12000)" required>
                </div>
                <button type="submit" class="btn-action" style="margin-top: 10px; padding: 11px;">Hızlı Aracı Ekle</button>
            </form>
        </div>

        {% if aktif_araclar %}
            {% for ts in aktif_araclar %}
            <div class="card" style="border-left: 5px solid {% if ts[10] == 'Borçlu / Veresiye' %}#f87171{% else %}#facc15{% endif %};">
                <b>Plaka:</b> <span style="color:var(--accent-gold); font-size:15px; font-weight:800;">{{ ts[1] }}</span> | <b>Müşteri:</b> {{ ts[2] }} ({{ ts[3] }})<br>
                <b>Model / KM:</b> {{ ts[4] }} - {{ ts[5] }} KM | <b>Tarih:</b> {{ ts[6] }}<br>
                <b>Yapılanlar:</b> {{ ts[7] }} | <b>Toplam:</b> <span style="color:var(--accent-gold); font-weight:800;">{{ "%.2f"|format(ts[8]) }} TL</span><br>
                
                <hr style="border:0; border-top:1px solid rgba(51,65,85,0.5); margin: 10px 0;">
                
                <form action="/durum_guncelle" method="POST">
                    <input type="hidden" name="servis_id" value="{{ ts[0] }}">
                    <div class="status-controls">
                        <div class="status-box">
                            <label>Çalışma Durumu</label>
                            <select name="durum" onchange="this.form.submit()">
                                <option value="Bekliyor" {% if ts[9] == 'Bekliyor' %}selected{% endif %}>Bekliyor</option>
                                <option value="İşlemde" {% if ts[9] == 'İşlemde' %}selected{% endif %}>İşlemde</option>
                                <option value="Teslime Hazır" {% if ts[9] == 'Teslime Hazır' %}selected{% endif %}>Teslime Hazır</option>
                                <option value="Parça Bekliyor" {% if ts[9] == 'Parça Bekliyor' %}selected{% endif %}>Parça Bekliyor</option>
                            </select>
                        </div>
                        <div class="status-box">
                            <label>Ödeme Durumu</label>
                            <select name="odeme_durumu" onchange="this.form.submit()">
                                <option value="Borçlu / Veresiye" {% if ts[10] == 'Borçlu / Veresiye' %}selected{% endif %}>🔴 Borçlu</option>
                                <option value="Parça Bekliyor" {% if ts[10] == 'Parça Bekliyor' %}selected{% endif %}>🟡 Parça Bekliyor</option>
                                <option value="Ödendi">🟢 Ödendi (Arşive At)</option>
                            </select>
                        </div>
                    </div>
                </form>

                <div class="action-buttons">
                    <a href="https://wa.me/{{ ts[3] }}?text=Sayin%20{{ ts[2] }},%20Iz%20Motorsiklet%20servis%20ucretiniz%20{{ "%.2f"|format(ts[8]) }}%20TL%20durumu:%20{{ ts[10] or 'Borçlu' }}." target="_blank" class="whatsapp-btn">💬 WhatsApp</a>
                    {% if ts[11] %}
                    <a href="/pdf_indir/{{ ts[0] }}" class="pdf-btn">📄 Formu İndir (PDF)</a>
                    {% endif %}
                </div>
            </div>
            {% endfor %}
        {% else %}
            <p style="color: var(--text-muted); text-align: center;">Atölyede aktif bekleyen araç bulunmuyor.</p>
        {% endif %}
    </div>

    <!-- 3. MÜŞTERİ & PLAKA GEÇMİŞİ -->
    <div id="historyTab" class="tab-content">
        <form method="GET" action="/">
            <input type="hidden" name="tab" value="history">
            <div class="form-group"><label>Plaka veya Müşteri Adı ile Sorgula</label><input type="text" name="sorgu_plaka" placeholder="Örn: 34 ABC veya Ahmet..." value="{{ sorgu_plaka or '' }}"></div>
            <button type="submit" class="btn-action">Ödenmiş Geçmişte Ara</button>
        </form>
        <hr style="margin: 18px 0; border: 0; border-top: 1px solid rgba(51,65,85,0.5);">
        <h3>Tamamlanan & Ödenen Geçmiş Servisler</h3>
        {% if kayitlar %}
            {% for k in kayitlar %}
            <div class="card" style="border-left: 4px solid #4ade80;">
                <b>Plaka:</b> <span style="color:var(--accent-gold);">{{ k[1] }}</span> | <b>Tarih:</b> {{ k[6] }}<br>
                <b>Müşteri:</b> {{ k[2] }} ({{ k[3] }})<br>
                <b>İşlemler:</b> {{ k[7] }}<br>
                <b>Toplam Tutar:</b> <span style="color: var(--accent-gold); font-weight: 800;">{{ "%.2f"|format(k[8]) }} TL</span> | <b>Ödeme:</b> <span style="color: #4ade80; font-weight:800;">{{ k[10] }}</span>
                {% if k[11] %}
                <div style="margin-top: 8px;"><a href="/pdf_indir/{{ k[0] }}" class="pdf-btn">📄 Formu İndir (PDF)</a></div>
                {% endif %}
            </div>
            {% endfor %}
        {% else %}
            <p style="color: var(--text-muted); text-align: center;">Geçmişte ödenmiş kayıt bulunamadı.</p>
        {% endif %}
    </div>

    <!-- 4. STOK TAKİBİ -->
    <div id="stockTab" class="tab-content">
        <h3>Parça / Ürün Stok Yönetimi</h3>
        <form method="POST" action="/stok_ekle">
            <div class="form-group"><input type="text" name="parca_adi" placeholder="Parça Adı (Örn: Buji NGK)" required></div>
            <div class="form-group"><input type="number" name="adet" placeholder="Stok Adedi" required></div>
            <div class="form-group"><input type="number" step="0.01" name="fiyat" placeholder="Birim Satış Fiyatı (TL)" required></div>
            <button type="submit" class="btn-action">Stok Ekle / Güncelle</button>
        </form>
        <hr style="margin: 18px 0; border: 0; border-top: 1px solid rgba(51,65,85,0.5);">
        <h4>Mevcut Stoklar ve Uyarılar</h4>
        {% for s in stoklar %}
        <div class="card" style="border-left: 4px solid {% if s[2] < 3 %}#f87171{% else %}#4ade80{% endif %};">
            <b>{{ s[1] }}</b> - Adet: <span style="color: {% if s[2] < 3 %}#f87171{% else %}#4ade80{% endif %}; font-weight:800; font-size:14px;">{{ s[2] }}</span> | Fiyat: <b>{{ "%.2f"|format(s[3]) }} TL</b>
            {% if s[2] < 3 %}
            <br><span style="color: #f87171; font-weight: 800; font-size: 11px; display:inline-block; margin-top:5px; background:rgba(248,113,113,0.15); padding:3px 6px; border-radius:5px; border:1px solid rgba(248,113,113,0.35);">⚠️ KRİTİK STOK: Bu ürün 3 adedin altında!</span>
            {% endif %}
        </div>
        {% endfor %}
    </div>

    <!-- 5. RANDEVULAR -->
    <div id="randevuTab" class="tab-content">
        <h3>Atölye Randevu Takvimi</h3>
        <form method="POST" action="/randevu_ekle">
            <div class="form-group"><input type="text" name="musteri_ad" placeholder="Müşteri Adı Soyadı" required></div>
            <div class="form-group"><input type="text" name="tel" placeholder="Telefon Numarası (Örn: 90532...)" required></div>
            <div class="form-group"><input type="text" name="tarih_saat" placeholder="Randevu Tarih ve Saati (Örn: 05.11.2026 - 14:30)" required></div>
            <div class="form-group"><input type="text" name="notlar" placeholder="Randevu Notu"></div>
            <button type="submit" class="btn-action">Randevu Oluştur</button>
        </form>
        <hr style="margin: 18px 0; border: 0; border-top: 1px solid rgba(51,65,85,0.5);">
        <h4>Aktif Randevular</h4>
        {% for r in randevular %}
        <div class="card" style="border-left: 4px solid #0d9488;">
            <b>Müşteri:</b> {{ r[1] }} ({{ r[2] }})<br>
            <b>Zaman:</b> <span style="color:var(--accent-gold); font-weight:800;">{{ r[3] }}</span>
            {% if r[4] %}<br><b>Not:</b> {{ r[4] }}{% endif %}
            
            <div style="margin-top: 10px;">
                <a href="https://wa.me/{{ r[2] }}?text=Sayin%20{{ r[1] }},%20Iz%20Motorsiklet%20servisimizde%20{{ r[3] }}%20tarihli%20randevunuz%20bulunmaktadir,%20bekliyoruz." target="_blank" class="whatsapp-btn">💬 WhatsApp Hatırlat</a>
            </div>
        </div>
        {% endfor %}
    </div>

    <!-- 6. BAKIM HATIRLAT -->
    <div id="reminderTab" class="tab-content">
        <h3>Akıllı Bakım Hatırlatıcı (Ödenmiş Araçlar)</h3>
        {% if bakim_listesi %}
            {% for b in bakim_listesi %}
            <div class="card" style="border-left: 4px solid var(--accent-gold);">
                <b>Plaka:</b> <span style="color:var(--accent-gold); font-size:14px; font-weight:800;">{{ b[1] }}</span> | <b>Müşteri:</b> {{ b[2] }} ({{ b[3] }})<br>
                <b>Son Servis Tarihi:</b> {{ b[6] }} | <b>Geçen Süre:</b> <span style="color:var(--accent-gold); font-weight:800;">{{ b.gecen_sure }}</span><br>
                <b>Yapılan İşlem:</b> {{ b[7] }}
                
                <div style="margin-top: 12px;">
                    <a href="https://wa.me/{{ b[3] }}?text=Sayin%20{{ b[2] }},%20Iz%20Motorsiklet%20servisimizdeki%20son%20bakiminizdan%20beri%20sure%20gecti,%20yag%20ve%20genel%20bakim%20vaktiniz%20yaklasmis%20olabilir,%20bekleriz." target="_blank" class="whatsapp-btn">💬 Bakım Hatırlatması Gönder (WhatsApp)</a>
                </div>
            </div>
            {% endfor %}
        {% else %}
            <p style="color: var(--text-muted); text-align: center;">Bakım hatırlatılacak ödenmiş eski araç bulunmuyor.</p>
        {% endif %}
    </div>
</div>

<script>
let isSubmitted = false;
function switchTab(tabId, btn) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    document.getElementById(tabId).classList.add('active');
    btn.classList.add('active');
    window.scrollTo({ top: 0, behavior: 'smooth' });
}
function aracBilgileriniDoldur(selectObj) {
    const opt = selectObj.options[selectObj.selectedIndex];
    if (opt.value) {
        document.getElementById('plaka').value = opt.value;
        document.getElementById('musteri_ad').value = opt.getAttribute('data-ad') || '';
        document.getElementById('musteri_tel').value = opt.getAttribute('data-tel') || '';
        document.getElementById('model').value = opt.getAttribute('data-model') || '';
        document.getElementById('km').value = opt.getAttribute('data-km') || '';
    }
}
function hizliAracBilgileriniDoldur(selectObj) {
    const opt = selectObj.options[selectObj.selectedIndex];
    if (opt.value) {
        document.getElementById('h_plaka').value = opt.value;
        document.getElementById('h_musteri_ad').value = opt.getAttribute('data-ad') || '';
        document.getElementById('h_musteri_tel').value = opt.getAttribute('data-tel') || '';
        document.getElementById('h_model').value = opt.getAttribute('data-model') || '';
        document.getElementById('h_km').value = opt.getAttribute('data-km') || '';
    }
}
function addItemRow() {
    const container = document.getElementById('items-container');
    const row = document.createElement('div');
    row.className = 'item-row';
    row.innerHTML = `
        <input type="text" name="islem_ad[]" class="name-input" placeholder="İşlem / Parça Adı" required>
        <select name="stok_id[]">
            <option value="">-- Stoktan Düş (İsteğe Bağlı) --</option>
            {% for s in stoklar %}
            <option value="{{ s[0] }}">{{ s[1] }} (Stok: {{ s[2] }} | {{ s[3] }} TL)</option>
            {% endfor %}
        </select>
        <input type="number" name="adet[]" class="small" placeholder="Adet" value="1" min="1">
        <input type="number" step="0.01" name="fiyat[]" class="small" placeholder="Fiyat" required>
        <button type="button" class="btn-remove" onclick="this.parentElement.remove()">X</button>
    `;
    container.appendChild(row);
}
function handleFormSubmit(e) {
    if (isSubmitted) {
        e.preventDefault();
        const alertBox = document.getElementById('duplicateAlert');
        alertBox.style.display = 'block';
        setTimeout(() => { alertBox.style.display = 'none'; }, 4000);
        return false;
    }
    isSubmitted = true;
    const btn = document.getElementById('submitBtn');
    btn.innerText = "Form Kaydediliyor & İndiriliyor...";
    btn.disabled = true;
    setTimeout(() => { isSubmitted = false; btn.innerText = "Servis Formu PDF İndir & Kaydet"; btn.disabled = false; }, 5000);
}
const urlParams = new URLSearchParams(window.location.search);
const tab = urlParams.get('tab');
if(tab === 'araclar') switchTab('araclarTab', document.querySelectorAll('.tab-btn')[1]);
else if(tab === 'history') switchTab('historyTab', document.querySelectorAll('.tab-btn')[2]);
else if(tab === 'stock') switchTab('stockTab', document.querySelectorAll('.tab-btn')[3]);
else if(tab === 'randevu') switchTab('randevuTab', document.querySelectorAll('.tab-btn')[4]);
else if(tab === 'reminder') switchTab('reminderTab', document.querySelectorAll('.tab-btn')[5]);
</script>
</body>
</html>
"""

# --- PDF MOTORU ---
def pdf_olustur(filename, veri, logo_yolu, hasar_foto_yolu):
    doc = SimpleDocTemplate(filename, pagesize=A4, rightMargin=15, leftMargin=15, topMargin=12, bottomMargin=12)
    story = []
    style_normal = ParagraphStyle('Norm', fontName=FONT_NAME, fontSize=8.5, leading=10, textColor=colors.HexColor("#111111"))
    style_bold = ParagraphStyle('Bld', fontName=FONT_BOLD, fontSize=8.5, leading=10, textColor=colors.HexColor("#111111"))
    style_title = ParagraphStyle('Tit', fontName=FONT_BOLD, fontSize=12, leading=15, textColor=colors.HexColor("#1A1A1A"), alignment=1, spaceAfter=6)

    if logo_yolu and os.path.exists(logo_yolu):
        try:
            story.append(Image(logo_yolu, width=540, height=60))
            story.append(Spacer(1, 4))
        except Exception:
            pass

    story.append(Paragraph("MÜŞTERİ SERVİS FORMU", style_title))
    tarih_str = datetime.date.today().strftime("%d.%m.%Y")
    m_text = f"<b>MÜŞTERİ BİLGİLERİ</b><br/><br/><b>Adı Soyadı :</b> {veri.get('musteri_ad', '')}<br/><b>Telefon :</b> {veri.get('musteri_tel', '')}<br/><b>Tarih :</b> {tarih_str}"
    a_text = f"<b>ARAÇ BİLGİLERİ</b><br/><br/><b>Plaka :</b> {veri.get('plaka', '')}<br/><b>Marka / Model :</b> {veri.get('model', '')}<br/><b>Kilometre :</b> {veri.get('km', '')}"
    
    t_bilgi = Table([[Paragraph(m_text, style_normal), Paragraph(a_text, style_normal)]], colWidths=[275, 275])
    t_bilgi.setStyle(TableStyle([('BOX', (0,0), (-1,-1), 0.8, colors.HexColor("#CBD5E0")), ('PADDING', (0,0), (-1,-1), 5), ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#FAFAFA"))]))
    story.append(t_bilgi)
    story.append(Spacer(1, 6))

    hizmet_table_data = [["No", "Yapılan İşlem / Değişen Parça", "Adet / Miktar", "Tutar (TL)"]]
    islemler = veri.get('islemler', [])
    yedek_parca_toplam = 0.0
    toplam_satir_sayisi = max(10, len(islemler))

    for idx in range(toplam_satir_sayisi):
        if idx < len(islemler):
            item = islemler[idx]
            no = str(idx + 1)
            islem_adi = item['ad']
            adet = str(item['adet'])
            tutar_val = item['fiyat'] * item['adet']
            yedek_parca_toplam += tutar_val
            tutar_str = f"{tutar_val:.2f} TL"
        else:
            no = str(idx + 1)
            islem_adi, adet, tutar_str = "", "", ""
        hizmet_table_data.append([no, islem_adi, adet, tutar_str])

    iscilik_tutar = veri.get('iscilik', 0.0)
    genel_toplam = yedek_parca_toplam + iscilik_tutar
    hizmet_table_data.append(["", "İşçilik Tutarı", "", f"{iscilik_tutar:.2f} TL"])
    hizmet_table_data.append(["", "Yedek Parça Tutarı", "", f"{yedek_parca_toplam:.2f} TL"])
    hizmet_table_data.append(["", "GENEL TOPLAM", "", f"{genel_toplam:.2f} TL"])

    formatted_table_data = []
    for r_idx, row in enumerate(hizmet_table_data):
        new_row = []
        for c_idx, cell in enumerate(row):
            if r_idx == 0 or (r_idx >= len(hizmet_table_data) - 3 and c_idx in [1, 3]):
                p = Paragraph(f"<b>{cell}</b>", style_bold)
            else:
                p = Paragraph(str(cell), style_normal)
            new_row.append(p)
        formatted_table_data.append(new_row)

    t_hizmet = Table(formatted_table_data, colWidths=[30, 315, 90, 115])
    t_hizmet.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#E0E0E0")),
        ('ALIGN', (0,0), (0,-1), 'CENTER'),
        ('GRID', (0,0), (-1,-4), 0.5, colors.HexColor("#CBD5E0")),
        ('SPAN', (1,-3), (2,-3)), ('SPAN', (1,-2), (2,-2)), ('SPAN', (1,-1), (2,-1)),
        ('BACKGROUND', (1,-1), (-1,-1), colors.HexColor("#FFD54F")),
        ('PADDING', (0,0), (-1,-1), 3.5),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(t_hizmet)
    story.append(Spacer(1, 6))

    if hasar_foto_yolu and os.path.exists(hasar_foto_yolu):
        try:
            story.append(Paragraph("<b>Hasar / Durum Ek Fotoğrafı</b>", style_bold))
            story.append(Image(hasar_foto_yolu, width=200, height=120))
        except Exception:
            pass

    doc.build(story)

# --- WEB ROUTES ---
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if request.form.get('sifre') == SIFRE:
            session['giris'] = True
            return redirect(url_for('index'))
        return render_template_string(HTML_LOGIN, error="Hatalı Şifre Kanka!")
    if not session.get('giris'):
        return render_template_string(HTML_LOGIN)

    conn = get_db_connection()
    cursor = conn.cursor()

    sorgu_plaka = request.args.get('sorgu_plaka', '').strip()
    kayitlar = []
    
    if sorgu_plaka:
        cursor.execute("SELECT * FROM servisler WHERE (plaka ILIKE %s OR musteri_ad ILIKE %s) AND odeme_durumu = 'Ödendi' ORDER BY id DESC", ('%' + sorgu_plaka + '%', '%' + sorgu_plaka + '%'))
        kayitlar = cursor.fetchall()
    else:
        cursor.execute("SELECT * FROM servisler WHERE odeme_durumu = 'Ödendi' ORDER BY id DESC")
        kayitlar = cursor.fetchall()

    cursor.execute("SELECT * FROM servisler WHERE odeme_durumu != 'Ödendi' OR odeme_durumu IS NULL ORDER BY id DESC")
    aktif_araclar = cursor.fetchall()

    cursor.execute("SELECT * FROM stok")
    stoklar = cursor.fetchall()
    cursor.execute("SELECT * FROM randevular ORDER BY id DESC")
    randevular = cursor.fetchall()
    
    cursor.execute("SELECT * FROM servisler WHERE odeme_durumu = 'Ödendi' ORDER BY id DESC")
    odenen_servisler = cursor.fetchall()

    cursor.execute("SELECT SUM(toplam_tutar) FROM servisler")
    res = cursor.fetchone()
    toplam_ciro = res[0] if res and res[0] else 0.0

    bugun = datetime.date.today()
    bakim_listesi = []
    for b in odenen_servisler:
        try:
            s_tarih = datetime.datetime.strptime(b[6], "%d.%m.%Y").date()
            gun = (bugun - s_tarih).days
            sure_str = f"{gun} gün önce geldi"
        except Exception:
            sure_str = "Kayıtlı"
        b_item = list(b)
        b_item.append(sure_str)
        bakim_listesi.append(b_item)

    cursor.execute("SELECT DISTINCT plaka, musteri_ad, musteri_tel, model, km FROM servisler WHERE odeme_durumu != 'Ödendi' OR odeme_durumu IS NULL ORDER BY id DESC")
    tum_servisler = cursor.fetchall()

    cursor.execute("SELECT DISTINCT plaka, musteri_ad, musteri_tel, model, km FROM servisler ORDER BY id DESC")
    gecmis_araclar = cursor.fetchall()

    cursor.close()
    conn.close()
    return render_template_string(HTML_PANEL, kayitlar=kayitlar, sorgu_plaka=sorgu_plaka, stoklar=stoklar, randevular=randevular, tum_servisler=tum_servisler, aktif_araclar=aktif_araclar, gecmis_araclar=gecmis_araclar, bakim_listesi=bakim_listesi, toplam_ciro=toplam_ciro)

@app.route('/arac_ekle_hizli', methods=['POST'])
def arac_ekle_hizli():
    if not session.get('giris'): return redirect(url_for('index'))
    plaka = request.form.get('plaka', '').strip()
    musteri_ad = request.form.get('musteri_ad')
    musteri_tel = request.form.get('musteri_tel')
    model = request.form.get('model')
    km = request.form.get('km', '0')
    tarih_str = datetime.date.today().strftime("%d.%m.%Y")

    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id FROM servisler WHERE plaka = %s AND (odeme_durumu != 'Ödendi' OR odeme_durumu IS NULL)", (plaka,))
    mevcut = cursor.fetchone()
    
    if mevcut:
        cursor.execute('''
            UPDATE servisler 
            SET musteri_ad = %s, musteri_tel = %s, model = %s, km = %s, tarih = %s
            WHERE id = %s
        ''', (musteri_ad, musteri_tel, model, km, tarih_str, mevcut[0]))
    else:
        cursor.execute('''
            INSERT INTO servisler (plaka, musteri_ad, musteri_tel, model, km, tarih, detaylar, toplam_tutar, durum, odeme_durumu, pdf_dosya)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Bekliyor', 'Borçlu / Veresiye', NULL)
        ''', (plaka, musteri_ad, musteri_tel, model, km, tarih_str, "Hızlı Kayıt", 0.0))
        
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('index') + '?tab=araclar')

@app.route('/durum_guncelle', methods=['POST'])
def durum_guncelle():
    if not session.get('giris'): return redirect(url_for('index'))
    conn = get_db_connection()
    cursor = conn.cursor()
    yeni_durum = request.form.get('durum')
    yeni_odeme = request.form.get('odeme_durumu')
    servis_id = request.form.get('servis_id')
    
    if yeni_durum:
        cursor.execute("UPDATE servisler SET durum = %s WHERE id = %s", (yeni_durum, servis_id))
    if yeni_odeme:
        cursor.execute("UPDATE servisler SET odeme_durumu = %s WHERE id = %s", (yeni_odeme, servis_id))
        
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('index') + '?tab=araclar')

@app.route('/stok_ekle', methods=['POST'])
def stok_ekle():
    if not session.get('giris'): return redirect(url_for('index'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO stok (parca_adi, adet, fiyat) VALUES (%s, %s, %s)", (request.form.get('parca_adi'), int(request.form.get('adet', 0)), float(request.form.get('fiyat', 0))))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('index') + '?tab=stock')

@app.route('/randevu_ekle', methods=['POST'])
def randevu_ekle():
    if not session.get('giris'): return redirect(url_for('index'))
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO randevular (musteri_ad, tel, tarih_saat, notlar, hatirlatildi) VALUES (%s, %s, %s, %s, 0)", (request.form.get('musteri_ad'), request.form.get('tel'), request.form.get('tarih_saat'), request.form.get('notlar', '')))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('index') + '?tab=randevu')

@app.route('/olustur', methods=['POST'])
def olustur():
    if not session.get('giris'): return redirect(url_for('index'))
    ad, tel, plaka, model, km = request.form.get('musteri_ad'), request.form.get('musteri_tel'), request.form.get('plaka', '').strip(), request.form.get('model'), request.form.get('km')
    odeme_durumu = request.form.get('odeme_durumu', 'Borçlu / Veresiye')
    
    try:
        iscilik = float(request.form.get('iscilik', 0))
    except ValueError:
        iscilik = 0.0

    conn = get_db_connection()
    cursor = conn.cursor()

    islem_adlari = request.form.getlist('islem_ad[]')
    stok_idler = request.form.getlist('stok_id[]')
    adetler = request.form.getlist('adet[]')
    fiyatlar = request.form.getlist('fiyat[]')

    islemler = []
    yedek_parca_toplam = 0.0
    islem_ozeti_list = []

    for i in range(len(islem_adlari)):
        if islem_adlari[i].strip():
            try:
                ad_item = islem_adlari[i]
                s_id = stok_idler[i] if i < len(stok_idler) else ""
                adt = int(adetler[i]) if i < len(adetler) and adetler[i] else 1
                fyt = float(fiyatlar[i]) if i < len(fiyatlar) and fiyatlar[i] else 0.0
                
                tutar = adt * fyt
                yedek_parca_toplam += tutar
                
                islemler.append({'ad': ad_item, 'adet': adt, 'fiyat': fyt})
                islem_ozeti_list.append(f"{ad_item} (x{adt})")

                if s_id:
                    cursor.execute("SELECT adet FROM stok WHERE id = %s", (int(s_id),))
                    stok_item = cursor.fetchone()
                    if stok_item:
                        yeni_adet = max(0, stok_item[0] - adt)
                        cursor.execute("UPDATE stok SET adet = %s WHERE id = %s", (yeni_adet, int(s_id)))
            except Exception:
                continue

    genel_toplam = yedek_parca_toplam + iscilik
    islem_str = ", ".join(islem_ozeti_list) if islem_ozeti_list else "Genel Bakım"
    tarih_str = datetime.date.today().strftime("%d.%m.%Y")

    logo_file = request.files.get('logo')
    logo_path = f"temp_logo_{plaka}.jpg" if logo_file and logo_file.filename != '' else None
    if logo_file and logo_path: logo_file.save(logo_path)

    hasar_file = request.files.get('hasar_foto')
    hasar_path = f"temp_hasar_{plaka}.jpg" if hasar_file and hasar_file.filename != '' else None
    if hasar_file and hasar_path: hasar_file.save(hasar_path)

    pdf_filename = f"servis_formu_{plaka}_{int(datetime.datetime.now().timestamp())}.pdf"
    pdf_olustur(pdf_filename, {'musteri_ad': ad, 'musteri_tel': tel, 'plaka': plaka, 'model': model, 'km': km, 'islemler': islemler, 'iscilik': iscilik}, logo_path, hasar_path)

    cursor.execute("SELECT id, toplam_tutar, detaylar FROM servisler WHERE plaka = %s AND (odeme_durumu != 'Ödendi' OR odeme_durumu IS NULL)", (plaka,))
    mevcut = cursor.fetchone()

    if mevcut:
        m_id, eski_tutar, eski_detaylar = mevcut[0], mevcut[1], mevcut[2]
        yeni_toplam = (eski_tutar or 0.0) + genel_toplam
        yeni_detaylar = f"{eski_detaylar}, {islem_str}" if eski_detaylar and eski_detaylar != "Hızlı Kayıt" else islem_str
        
        cursor.execute('''
            UPDATE servisler 
            SET musteri_ad = %s, musteri_tel = %s, model = %s, km = %s, tarih = %s, detaylar = %s, toplam_tutar = %s, odeme_durumu = %s, pdf_dosya = %s
            WHERE id = %s
        ''', (ad, tel, model, km, tarih_str, yeni_detaylar, yeni_toplam, odeme_durumu, pdf_filename, m_id))
    else:
        cursor.execute('''
            INSERT INTO servisler (plaka, musteri_ad, musteri_tel, model, km, tarih, detaylar, toplam_tutar, durum, odeme_durumu, pdf_dosya)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Bekliyor', %s, %s)
        ''', (plaka, ad, tel, model, km, tarih_str, islem_str, genel_toplam, odeme_durumu, pdf_filename))

    conn.commit()
    cursor.close()
    conn.close()

    if logo_path and os.path.exists(logo_path): os.remove(logo_path)
    if hasar_path and os.path.exists(hasar_path): os.remove(hasar_path)

    return send_file(pdf_filename, as_attachment=True)

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
    return "PDF Formu bulunamadı kanka.", 404

@app.route('/cikis')
def cikis():
    session.pop('giris', None)
    return redirect(url_for('index'))

# --- TELEGRAM BOTU & ARKA PLAN HATIRLATICI ---
SIFRE_DURUMU = {}
BOT_DURUMLARI = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TELEGRAM_ADMIN_CHAT_ID
    user_id = update.effective_user.id
    TELEGRAM_ADMIN_CHAT_ID = update.effective_chat.id
    SIFRE_DURUMU[user_id] = False
    BOT_DURUMLARI[user_id] = {'adim': 'sifre'}
    await update.message.reply_text("Selam kanka! İz Motorsiklet Supabase Botuna hoş geldin.\nDevam etmek için önce **yönetici şifresini** gir kanka:")

async def mesaj_yoneticisi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global TELEGRAM_ADMIN_CHAT_ID
    user_id = update.effective_user.id
    TELEGRAM_ADMIN_CHAT_ID = update.effective_chat.id
    text = update.message.text
    photo = update.message.photo
    
    if not SIFRE_DURUMU.get(user_id, False):
        if text == SIFRE:
            SIFRE_DURUMU[user_id] = True
            BOT_DURUMLARI[user_id] = {'adim': 'menu'}
            keyboard = [
                ["🛠️ Servis Formu Oluştur", "📅 Randevu Ekle"],
                ["⚡ Hızlı Fiyat Teklifi", "🔍 Plaka Sorgula"],
                ["📊 Günlük Özet", "📦 Stok Listesi"],
                ["🏍️ Aktif Araçlar"]
            ]
            await update.message.reply_text("Şifre doğru kanka! Aşağıdaki menüden seçim yapabilirsin:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        else:
            await update.message.reply_text("Hatalı şifre kanka! Tekrar dene:")
        return

    user_state = BOT_DURUMLARI.get(user_id, {})
    durum_bilgisi = user_state.get('adim', 'menu')

    if durum_bilgisi == 'plaka_sor':
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT plaka, musteri_ad, musteri_tel, model, km, tarih, detaylar, toplam_tutar, durum, odeme_durumu FROM servisler WHERE (plaka ILIKE %s OR musteri_ad ILIKE %s) AND odeme_durumu = 'Ödendi' ORDER BY id DESC LIMIT 3", ('%' + text + '%', '%' + text + '%'))
        sonuclar = cursor.fetchall()
        cursor.close()
        conn.close()

        keyboard = [
            ["🛠️ Servis Formu Oluştur", "📅 Randevu Ekle"],
            ["⚡ Hızlı Fiyat Teklifi", "🔍 Plaka Sorgula"],
            ["📊 Günlük Özet", "📦 Stok Listesi"],
            ["🏍️ Aktif Araçlar"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

        if not sonuclar:
            await update.message.reply_text(f"❌ '{text}' ile eşleşen ödenmiş geçmiş kayıt bulunamadı kanka.", reply_markup=reply_markup)
        else:
            for r in sonuclar:
                msg = f"🔍 **Geçmiş Servis (Ödendi):**\n- **Plaka:** {r[0]}\n- **Müşteri:** {r[1]} ({r[2]})\n- **Model / KM:** {r[3]} - {r[4]}\n- **Tarih:** {r[5]}\n- **İşlemler:** {r[6]}\n- **Tutar:** `{r[7]:.2f} TL`"
                await update.message.reply_text(msg, parse_mode="Markdown")
            await update.message.reply_text("Ana menüdesin kanka:", reply_markup=reply_markup)
        
        BOT_DURUMLARI[user_id] = {'adim': 'menu'}
        return

    rand_adim = user_state.get('randevu_adim')
    if rand_adim == 'ad_al':
        BOT_DURUMLARI[user_id]['rand_ad'] = text
        BOT_DURUMLARI[user_id]['randevu_adim'] = 'tel_al'
        await update.message.reply_text("Müşteri **telefon numarasını** gir kanka (Örn: 90532...):", reply_markup=ReplyKeyboardRemove())
        return
    elif rand_adim == 'tel_al':
        BOT_DURUMLARI[user_id]['rand_tel'] = text
        BOT_DURUMLARI[user_id]['randevu_adim'] = 'zaman_al'
        await update.message.reply_text("Randevu **tarih ve saatini** gir kanka (Örn: 05.11.2026 - 14:30):")
        return
    elif rand_adim == 'zaman_al':
        ad = user_state['rand_ad']
        tel = user_state['rand_tel']
        zaman = text

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO randevular (musteri_ad, tel, tarih_saat, notlar, hatirlatildi) VALUES (%s, %s, %s, %s, 0)", (ad, tel, zaman, "Telegram Randevusu"))
        conn.commit()
        cursor.close()
        conn.close()

        keyboard = [
            ["🛠️ Servis Formu Oluştur", "📅 Randevu Ekle"],
            ["⚡ Hızlı Fiyat Teklifi", "🔍 Plaka Sorgula"],
            ["📊 Günlük Özet", "📦 Stok Listesi"],
            ["🏍️ Aktif Araçlar"]
        ]
        BOT_DURUMLARI[user_id] = {'adim': 'menu'}
        await update.message.reply_text(f"✅ **Randevu Başarıyla Kaydedildi!**\n- Müşteri: {ad} ({tel})\n- Zaman: `{zaman}`", parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        return

    servis_adim = user_state.get('servis_adim')
    
    if servis_adim == 'logo_al':
        logo_path = None
        if photo:
            file = await context.bot.get_file(photo[-1].file_id)
            logo_path = f"bot_logo_{user_id}.jpg"
            await file.download_to_drive(logo_path)
            BOT_DURUMLARI[user_id]['s_logo'] = logo_path
        else:
            BOT_DURUMLARI[user_id]['s_logo'] = None
            
        BOT_DURUMLARI[user_id]['servis_adim'] = 'plaka_al'
        await update.message.reply_text("Motosiklet **Plakasını** yaz kanka (Örn: 34 ABC 123):", reply_markup=ReplyKeyboardRemove())
        return

    elif servis_adim == 'plaka_al':
        BOT_DURUMLARI[user_id]['s_plaka'] = text
        BOT_DURUMLARI[user_id]['servis_adim'] = 'ad_al'
        await update.message.reply_text("Müşteri **Adı ve Soyadını** yaz kanka:")
        return
    elif servis_adim == 'ad_al':
        BOT_DURUMLARI[user_id]['s_ad'] = text
        BOT_DURUMLARI[user_id]['servis_adim'] = 'tel_al'
        await update.message.reply_text("Müşteri **Telefon Numarasını** yaz kanka (Örn: 90532...):")
        return
    elif servis_adim == 'tel_al':
        BOT_DURUMLARI[user_id]['s_tel'] = text
        BOT_DURUMLARI[user_id]['servis_adim'] = 'model_al'
        await update.message.reply_text("Motosiklet **Marka ve Modelini** yaz kanka (Örn: Honda Dio):")
        return
    elif servis_adim == 'model_al':
        BOT_DURUMLARI[user_id]['s_model'] = text
        BOT_DURUMLARI[user_id]['servis_adim'] = 'km_al'
        await update.message.reply_text("Motosiklet **Kilometresini (KM)** yaz kanka:")
        return
    elif servis_adim == 'km_al':
        BOT_DURUMLARI[user_id]['s_km'] = text
        BOT_DURUMLARI[user_id]['s_islemler'] = []
        BOT_DURUMLARI[user_id]['servis_adim'] = 'islem_ad_al'
        await update.message.reply_text("🛠️ Yapılan **İşlemi veya Parça Adını** yaz kanka (Örn: Buji Değişimi):")
        return
        
    elif servis_adim == 'islem_ad_al':
        BOT_DURUMLARI[user_id]['temp_islem'] = text
        BOT_DURUMLARI[user_id]['servis_adim'] = 'islem_fiyat_al'
        await update.message.reply_text(f"💰 '{text}' için **Birim Fiyatını (TL)** yaz kanka (Örn: 400):")
        return
        
    elif servis_adim == 'islem_fiyat_al':
        try:
            fiyat = float(text.replace(',', '.'))
        except ValueError:
            fiyat = 0.0
            
        islem_adi = user_state['temp_islem']
        if 's_islemler' not in user_state:
            user_state['s_islemler'] = []
            
        user_state['s_islemler'].append({'ad': islem_adi, 'adet': 1, 'fiyat': fiyat})
        BOT_DURUMLARI[user_id]['servis_adim'] = 'baska_islem_sor'
        
        kb = [["➕ Başka İşlem Ekle", "✅ Bitti / Formu Oluştur"]]
        await update.message.reply_text(f"✅ '{islem_adi}' ({fiyat:.2f} TL) eklendi kanka.\nBaşka bir işlem/parça eklemek istiyor musun?", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))
        return

    elif servis_adim == 'baska_islem_sor':
        if text == "➕ Başka İşlem Ekle":
            BOT_DURUMLARI[user_id]['servis_adim'] = 'islem_ad_al'
            await update.message.reply_text("🛠️ Sonraki **İşlemi veya Parça Adını** yaz kanka:", reply_markup=ReplyKeyboardRemove())
            return
        else:
            s_plaka = user_state.get('s_plaka', '34TEST').strip()
            s_ad = user_state.get('s_ad', 'Müşteri')
            s_tel = user_state.get('s_tel', '05000000000')
            s_model = user_state.get('s_model', 'Honda')
            s_km = user_state.get('s_km', '0')
            s_logo = user_state.get('s_logo')
            islemler = user_state.get('s_islemler', [])
            
            toplam_tutar = sum(item['fiyat'] * item['adet'] for item in islemler)
            islem_ozeti_list = [f"{item['ad']} (x{item['adet']})" for item in islemler]
            islem_str = ", ".join(islem_ozeti_list) if islem_ozeti_list else "Genel Bakım"
            tarih_str = datetime.date.today().strftime("%d.%m.%Y")

            pdf_filename = f"servis_formu_{s_plaka}_{int(datetime.datetime.now().timestamp())}.pdf"
            
            try:
                pdf_olustur(pdf_filename, {'musteri_ad': s_ad, 'musteri_tel': s_tel, 'plaka': s_plaka, 'model': s_model, 'km': s_km, 'islemler': islemler, 'iscilik': 0.0}, s_logo, None)
            except Exception as e:
                print("PDF hata:", e)

            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT id, toplam_tutar, detaylar FROM servisler WHERE plaka = %s AND (odeme_durumu != 'Ödendi' OR odeme_durumu IS NULL)", (s_plaka,))
            mevcut = cursor.fetchone()

            if mevcut:
                m_id, eski_tutar, eski_detaylar = mevcut[0], mevcut[1], mevcut[2]
                yeni_toplam = (eski_tutar or 0.0) + toplam_tutar
                yeni_detaylar = f"{eski_detaylar}, {islem_str}" if eski_detaylar and eski_detaylar != "Hızlı Kayıt" else islem_str
                
                cursor.execute('''
                    UPDATE servisler 
                    SET musteri_ad = %s, musteri_tel = %s, model = %s, km = %s, tarih = %s, detaylar = %s, toplam_tutar = %s, odeme_durumu = %s, pdf_dosya = %s
                    WHERE id = %s
                ''', (s_ad, s_tel, s_model, s_km, tarih_str, yeni_detaylar, yeni_toplam, 'Borçlu / Veresiye', pdf_filename, m_id))
            else:
                cursor.execute('''
                    INSERT INTO servisler (plaka, musteri_ad, musteri_tel, model, km, tarih, detaylar, toplam_tutar, durum, odeme_durumu, pdf_dosya)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Bekliyor', 'Borçlu / Veresiye', %s)
                ''', (s_plaka, s_ad, s_tel, s_model, s_km, tarih_str, islem_str, toplam_tutar, pdf_filename))
                
            conn.commit()
            cursor.close()
            conn.close()

            if s_logo and os.path.exists(s_logo):
                try: os.remove(s_logo)
                except: pass

            keyboard = [
                ["🛠️ Servis Formu Oluştur", "📅 Randevu Ekle"],
                ["⚡ Hızlı Fiyat Teklifi", "🔍 Plaka Sorgula"],
                ["📊 Günlük Özet", "📦 Stok Listesi"],
                ["🏍️ Aktif Araçlar"]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

            BOT_DURUMLARI[user_id] = {'adim': 'menu'}
            
            await update.message.reply_text(f"✅ **Servis Formu Tamamlandı ve Kaydedildi!**\n\n- Plaka: `{s_plaka}`\n- Müşteri: {s_ad}\n- Toplam Tutar: `{toplam_tutar:.2f} TL`", parse_mode="Markdown", reply_markup=reply_markup)
            
            if os.path.exists(pdf_filename):
                with open(pdf_filename, 'rb') as f:
                    await context.bot.send_document(chat_id=update.effective_chat.id, document=f, filename=f"Servis_Formu_{s_plaka}.pdf", caption="📄 **İz Motorsiklet Resmi Servis Formu**")
            return

    if text == "🛠️ Servis Formu Oluştur":
        BOT_DURUMLARI[user_id] = {'adim': 'servis_formu', 'servis_adim': 'logo_al'}
        await update.message.reply_text("📸 Dükkanınızın **Logosunu (Fotoğraf olarak)** gönderin kanka.\n*(Eğer logo göndermek istemiyorsanız doğrudan herhangi bir yazı yazıp atlayabilirsiniz)*", reply_markup=ReplyKeyboardRemove())
        
    elif text == "🔍 Plaka Sorgula":
        BOT_DURUMLARI[user_id] = {'adim': 'plaka_sor'}
        await update.message.reply_text("Sorgulamak istediğin **Plakayı veya Müşteri Adını** yaz kanka:", reply_markup=ReplyKeyboardRemove())
        
    elif text == "📅 Randevu Ekle":
        BOT_DURUMLARI[user_id] = {'adim': 'randevu', 'randevu_adim': 'ad_al'}
        await update.message.reply_text("Randevu vereceğin **Müşteri Adı Soyadını** yaz kanka:", reply_markup=ReplyKeyboardRemove())

    elif text == "⚡ Hızlı Fiyat Teklifi":
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT parca_adi, fiyat FROM stok")
        stoklar = cursor.fetchall()
        cursor.close()
        conn.close()
        msg = "⚡ **İZ MOTORSİKLET - FİYAT LİSTESİ**\n\n"
        for s in stoklar:
            msg += f"- {s[0]}: `{s[1]} TL`\n"
        await update.message.reply_text(msg or "Stokta ürün bulunmuyor kanka.", parse_mode="Markdown")
        
    elif text == "📊 Günlük Özet":
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
        msg = "📦 **Mevcut Stoklar ve Uyarılar:**\n\n"
        for s in stoklar:
            kritik = " ⚠️ (KRİTİK STOK!)" if s[2] < 3 else ""
            msg += f"- {s[1]} adet {s[0]} ({s[2]} TL){kritik}\n"
        await update.message.reply_text(msg or "Stok boş.", parse_mode="Markdown")

    elif text == "🏍️ Aktif Araçlar":
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT plaka, musteri_ad, model, durum, odeme_durumu FROM servisler WHERE odeme_durumu != 'Ödendi' OR odeme_durumu IS NULL ORDER BY id DESC LIMIT 5")
        araclar = cursor.fetchall()
        cursor.close()
        conn.close()
        msg = "🏍️ **Atölyedeki Aktif Araçlar:**\n\n"
        for a in araclar:
            msg += f"- {a[0]} | {a[1]} | {a[2]} (`{a[3]}` - {a[4] or 'Borçlu'})\n"
        await update.message.reply_text(msg or "Atölyede aktif araç yok kanka.", parse_mode="Markdown")
    else:
        await update.message.reply_text("Kanka menüden bir seçenek seçebilir veya /start yazabilirsin.")

# --- ARKA PLANDA ÇALIŞAN 30 DAKİKA KALA BİLDİRİM KONTROLÜ ---
def randevu_hatirlatici_thread(bot_token):
    from telegram import Bot
    bot = Bot(token=bot_token)
    while True:
        try:
            time.sleep(30)
            if not TELEGRAM_ADMIN_CHAT_ID:
                continue
                
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, musteri_ad, tel, tarih_saat FROM randevular WHERE hatirlatildi = 0")
            randevular = cursor.fetchall()
            
            simdi = datetime.datetime.now()
            
            for r in randevular:
                r_id, ad, tel, tarih_saat_str = r[0], r[1], r[2], r[3]
                try:
                    r_zaman = datetime.datetime.strptime(tarih_saat_str.strip(), "%d.%m.%Y - %H:%M")
                    fark_dakika = (r_zaman - simdi).total_seconds() / 60.0
                    
                    if 0 <= fark_dakika <= 30:
                        import asyncio
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        
                        mesaj = f"⏰ **RANDEVU HATIRLATMASI!**\n\n- Müşteri: **{ad}**\n- Telefon: `{tel}`\n- Randevu Saati: `{tarih_saat_str}`\n\n⚠️ Yaklaşık 30 dakika içinde randevusu var kanka, dükkana haberin olsun!"
                        loop.run_until_complete(bot.send_message(chat_id=TELEGRAM_ADMIN_CHAT_ID, text=mesaj, parse_mode="Markdown"))
                        loop.close()
                        
                        cursor.execute("UPDATE randevular SET hatirlatildi = 1 WHERE id = %s", (r_id,))
                        conn.commit()
                except Exception as ex:
                    print("Zaman parse hatası:", ex)
            cursor.close()
            conn.close()
        except Exception as e:
            print("Hatırlatıcı thread hata:", e)

def run_telegram_bot():
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN: return
    
    threading.Thread(target=randevu_hatirlatici_thread, args=(TOKEN,), daemon=True).start()
    
    bot_app = Application.builder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mesaj_yoneticisi))
    bot_app.add_handler(MessageHandler(filters.PHOTO, mesaj_yoneticisi))
    bot_app.run_polling(stop_signals=None)

if __name__ == '__main__':
    threading.Thread(target=run_telegram_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
