import os
import datetime
import sqlite3
import threading
import asyncio
from flask import Flask, render_template_string, request, send_file, session, redirect, url_for
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    filters, ConversationHandler, ContextTypes, CallbackQueryHandler
)
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

app = Flask(__name__)
app.secret_key = "iz_motor_gizli_anahtar_erp_v16"

SIFRE = "izmotor2026*"

# --- VERİTABANI KURULUMU ---
def init_db():
    conn = sqlite3.connect('iz_motor_servis.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS servisler (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plaka TEXT,
            musteri_ad TEXT,
            musteri_tel TEXT,
            model TEXT,
            km TEXT,
            tarih TEXT,
            detaylar TEXT,
            toplam_tutar REAL,
            durum TEXT DEFAULT 'Bekliyor'
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stok (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parca_adi TEXT,
            adet INTEGER,
            fiyat REAL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS randevular (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            musteri_ad TEXT,
            tel TEXT,
            tarih_saat TEXT,
            notlar TEXT
        )
    ''')
    conn.commit()
    conn.close()

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

# --- HTML / PROFESYONEL CAFCAFLI ARAYÜZ ---
HTML_LOGIN = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>İz Motorsiklet - Giriş</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: radial-gradient(circle at center, #1e293b 0%, #0f172a 100%); display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; color: #f8fafc; }
        .login-box { background: rgba(15, 23, 42, 0.9); backdrop-filter: blur(16px); padding: 45px 35px; border-radius: 20px; box-shadow: 0 20px 50px rgba(0,0,0,0.7); width: 100%; max-width: 380px; text-align: center; border: 1px solid rgba(250,204,21,0.3); }
        .logo-icon { font-size: 42px; margin-bottom: 10px; }
        h2 { color: #facc15; margin-bottom: 8px; letter-spacing: 2px; text-transform: uppercase; font-size: 24px; text-shadow: 0 0 15px rgba(250,204,21,0.4); }
        p { color: #94a3b8; font-size: 13px; margin-bottom: 30px; }
        input { width: 100%; padding: 14px; margin-bottom: 20px; background: #0b0f19; border: 1px solid #334155; border-radius: 10px; color: #fff; box-sizing: border-box; font-size: 16px; outline: none; transition: 0.3s; text-align: center; letter-spacing: 2px; }
        input:focus { border-color: #facc15; box-shadow: 0 0 15px rgba(250,204,21,0.4); }
        button { background: linear-gradient(135deg, #facc15, #ca8a04); color: #0b0f19; border: none; padding: 14px; border-radius: 10px; width: 100%; font-size: 16px; font-weight: bold; cursor: pointer; transition: 0.3s; box-shadow: 0 4px 15px rgba(250,204,21,0.3); }
        button:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(250,204,21,0.5); }
        .error { color: #f87171; margin-bottom: 15px; font-size: 13px; font-weight: bold; background: rgba(248,113,113,0.1); padding: 8px; border-radius: 6px; border: 1px solid rgba(248,113,113,0.2); }
    </style>
</head>
<body>
<div class="login-box">
    <div class="logo-icon">🏍️</div>
    <h2>İZ MOTORSİKLET</h2>
    <p>Profesyonel Servis & Yönetim Paneli</p>
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
    <title>İz Motorsiklet - Profesyonel ERP Paneli</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #07090e; margin: 0; padding: 20px; color: #f1f5f9; }
        .container { max-width: 850px; margin: 0 auto; background: #0f172a; padding: 30px; border-radius: 20px; box-shadow: 0 15px 50px rgba(0,0,0,0.8); border: 1px solid rgba(250,204,21,0.25); }
        
        /* HEADER / MARKA ALANI */
        .header-section { display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #1e293b; padding-bottom: 20px; margin-bottom: 25px; }
        .brand-box { display: flex; align-items: center; gap: 15px; }
        .brand-logo { background: linear-gradient(135deg, #facc15, #ca8a04); width: 50px; height: 50px; border-radius: 14px; display: flex; justify-content: center; align-items: center; font-size: 26px; box-shadow: 0 0 20px rgba(250,204,21,0.4); }
        .brand-title h1 { color: #facc15; margin: 0; font-size: 22px; text-transform: uppercase; letter-spacing: 1.5px; text-shadow: 0 0 10px rgba(250,204,21,0.3); }
        .brand-title p { color: #94a3b8; margin: 2px 0 0 0; font-size: 12px; font-weight: 500; }
        
        .logout a { color: #f87171; text-decoration: none; font-size: 13px; font-weight: bold; padding: 6px 12px; background: rgba(248,113,113,0.1); border-radius: 8px; border: 1px solid rgba(248,113,113,0.3); transition: 0.3s; }
        .logout a:hover { background: rgba(248,113,113,0.2); }

        /* GRAFİK ÖZET KARTLARI (DASHBOARD STATS) */
        .dashboard-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 25px; }
        .stat-card { background: linear-gradient(135deg, #1e293b, #111827); border: 1px solid #334155; padding: 20px; border-radius: 14px; position: relative; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.3); transition: 0.3s; }
        .stat-card:hover { border-color: #facc15; transform: translateY(-3px); box-shadow: 0 8px 25px rgba(250,204,21,0.2); }
        .stat-card h3 { margin: 0; font-size: 24px; color: #facc15; font-weight: 700; text-shadow: 0 0 10px rgba(250,204,21,0.2); }
        .stat-card p { margin: 5px 0 0 0; color: #94a3b8; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
        .stat-icon { position: absolute; right: 15px; top: 15px; font-size: 26px; opacity: 0.2; }

        /* SEKMELER */
        .tabs { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; margin-bottom: 25px; background: #0b0f19; padding: 10px; border-radius: 12px; border: 1px solid #1e293b; }
        .tab-btn { background: #111827; color: #94a3b8; border: 1px solid #1f2937; padding: 10px 14px; border-radius: 8px; cursor: pointer; font-weight: bold; font-size: 12px; transition: 0.3s; }
        .tab-btn:hover { color: #facc15; border-color: #334155; }
        .tab-btn.active { background: linear-gradient(135deg, #facc15, #ca8a04); color: #07090e; border-color: #facc15; box-shadow: 0 0 15px rgba(250,204,21,0.4); }
        
        .tab-content { display: none; }
        .tab-content.active { display: block; animation: fadeIn 0.4s ease-in-out; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }

        /* FORM VE ELEMANLAR */
        h3 { color: #facc15; border-bottom: 1px solid #1e293b; padding-bottom: 10px; margin-top: 0; font-size: 18px; }
        .form-group { margin-bottom: 15px; }
        label { display: block; font-weight: bold; margin-bottom: 6px; font-size: 13px; color: #cbd5e1; }
        input, textarea, select { width: 100%; padding: 12px; background: #0b0f19; border: 1px solid #334155; border-radius: 10px; color: #fff; box-sizing: border-box; font-size: 14px; transition: 0.3s; outline: none; }
        input:focus, textarea:focus, select:focus { border-color: #facc15; box-shadow: 0 0 10px rgba(250,204,21,0.3); }
        
        .item-row { display: flex; gap: 8px; margin-bottom: 10px; align-items: center; background: #1e293b; padding: 10px; border-radius: 10px; border: 1px solid #334155; }
        .item-row input.name-input { flex: 2; }
        .item-row select { flex: 1.5; background: #0b0f19; font-size: 12px; }
        .item-row input.small { flex: 0.8; }
        
        .btn-add { background: #0d9488; color: #fff; border: none; padding: 12px; border-radius: 10px; cursor: pointer; font-weight: bold; width: 100%; margin-bottom: 15px; transition: 0.3s; }
        .btn-add:hover { background: #0f766e; }
        
        .btn-remove { background: #dc2626; color: #fff; border: none; padding: 8px 12px; border-radius: 8px; cursor: pointer; font-weight: bold; }
        
        button[type="submit"], .btn-action { background: linear-gradient(135deg, #facc15, #ca8a04); color: #0b0f19; border: none; padding: 14px; border-radius: 10px; cursor: pointer; width: 100%; font-size: 15px; font-weight: bold; margin-top: 15px; transition: 0.3s; box-shadow: 0 4px 15px rgba(250,204,21,0.3); }
        button[type="submit"]:hover, .btn-action:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(250,204,21,0.5); }
        button:disabled { opacity: 0.6; cursor: not-allowed; }

        .card { background: #162032; border: 1px solid #334155; padding: 16px; border-radius: 12px; margin-bottom: 12px; font-size: 14px; box-shadow: 0 4px 10px rgba(0,0,0,0.3); transition: 0.3s; }
        .card:hover { border-color: #475569; }
        .whatsapp-btn { display: inline-block; margin-top: 10px; background: #25d366; color: #fff; padding: 8px 14px; border-radius: 8px; text-decoration: none; font-size: 12px; font-weight: bold; box-shadow: 0 3px 10px rgba(37,211,102,0.3); transition: 0.3s; }
        .whatsapp-btn:hover { background: #20ba5a; }
        .alert-box { background: rgba(250,204,21,0.1); border: 1px solid #facc15; padding: 12px; border-radius: 10px; color: #facc15; margin-bottom: 15px; font-weight: bold; text-align: center; display: none; }
    </style>
</head>
<body>
<div class="container">
    
    <!-- PROFESYONEL BAŞLIK VE MARKA ALANI -->
    <div class="header-section">
        <div class="brand-box">
            <div class="brand-logo">🏍️</div>
            <div class="brand-title">
                <h1>İz Motorsiklet</h1>
                <p>Profesyonel Atölye & Servis Yönetim Sistemi</p>
            </div>
        </div>
        <div class="logout"><a href="/cikis">Çıkış</a></div>
    </div>

    <!-- GRAFİKSEL ÖZET KARTLARI -->
    <div class="dashboard-grid">
        <div class="stat-card">
            <div class="stat-icon">💰</div>
            <h3>{{ "%.2f"|format(toplam_ciro) }} TL</h3>
            <p>Toplam Servis Cirosu</p>
        </div>
        <div class="stat-card">
            <div class="stat-icon">🏍️</div>
            <h3>{{ tum_servisler|length }}</h3>
            <p>Kayıtlı Toplam Araç</p>
        </div>
        <div class="stat-card">
            <div class="stat-icon">📦</div>
            <h3>{{ stoklar|length }}</h3>
            <p>Stoktaki Çeşit Ürün</p>
        </div>
        <div class="stat-card">
            <div class="stat-icon">📅</div>
            <h3>{{ randevular|length }}</h3>
            <p>Aktif Randevu Sayısı</p>
        </div>
    </div>

    <div id="duplicateAlert" class="alert-box">⚠️ Bu servis formu az önce kaydedildi! Tekrar işlem yapılmadı.</div>

    <!-- SEKMELER -->
    <div class="tabs">
        <button class="tab-btn active" onclick="switchTab('formTab', this)">🛠️ Servis Formu</button>
        <button class="tab-btn" onclick="switchTab('araclarTab', this)">🏍️ Araçlar & Durum</button>
        <button class="tab-btn" onclick="switchTab('historyTab', this)">🔍 Müşteri & Plaka</button>
        <button class="tab-btn" onclick="switchTab('stockTab', this)">📦 Stok Takibi</button>
        <button class="tab-btn" onclick="switchTab('randevuTab', this)">📅 Randevular</button>
        <button class="tab-btn" onclick="switchTab('reminderTab', this)">⏰ Bakım Hatırlat</button>
    </div>

    <!-- 1. SEKME: SERVİS FORMU -->
    <div id="formTab" class="tab-content active">
        <form id="serviceForm" action="/olustur" method="POST" enctype="multipart/form-data" onsubmit="handleFormSubmit(event)">
            <div class="form-group">
                <label>Dükkan Logosu <span style="color:#facc15;">(Zorunlu)</span></label>
                <input type="file" name="logo" accept="image/*" required>
            </div>
            <div class="form-group">
                <label>Hasar / Durum Fotoğrafı <span style="color:#94a3af; font-weight:normal;">(İsteğe Bağlı)</span></label>
                <input type="file" name="hasar_foto" accept="image/*">
            </div>
            <div class="form-group">
                <label>Müşteri Adı Soyadı</label>
                <input type="text" name="musteri_ad" placeholder="Örn: Ahmet Yılmaz" required>
            </div>
            <div class="form-group">
                <label>Müşteri Telefon (WhatsApp)</label>
                <input type="text" name="musteri_tel" placeholder="Örn: 905320000000" required>
            </div>
            <div class="form-group">
                <label>Motosiklet Plaka</label>
                <input type="text" name="plaka" placeholder="Örn: 34 ABC 123" required>
            </div>
            <div class="form-group">
                <label>Marka / Model</label>
                <input type="text" name="model" placeholder="Örn: Honda PCX 125" required>
            </div>
            <div class="form-group">
                <label>Kilometre (KM)</label>
                <input type="text" name="km" placeholder="Örn: 15000" required>
            </div>

            <hr style="margin: 20px 0; border: 0; border-top: 1px solid #1e293b;">
            
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

            <div class="form-group">
                <label>Ek İşçilik Tutarı (TL)</label>
                <input type="number" step="0.01" name="iscilik" placeholder="Örn: 500" value="0">
            </div>

            <div class="form-group">
                <label>Notlar ve Tespitler</label>
                <textarea name="notlar" rows="2" placeholder="Örn: Genel bakım yapıldı."></textarea>
            </div>

            <button type="submit" id="submitBtn">Servis Formu PDF İndir & Kaydet</button>
        </form>
    </div>

    <!-- ARAÇLAR (SERVİS DURUM TAKİBİ) -->
    <div id="araclarTab" class="tab-content">
        <h3>Atölyedeki / Servisteki Araçlar</h3>
        <p style="font-size: 13px; color: #94a3b8; margin-bottom: 15px;">Motorların anlık servis durumlarını buradan güncelleyebilirsin:</p>
        {% if tum_servisler %}
            {% for ts in tum_servisler %}
            <div class="card">
                <b>Plaka:</b> <span style="color:#facc15;">{{ ts[1] }}</span> | <b>Müşteri:</b> {{ ts[2] }} ({{ ts[3] }})<br>
                <b>Model / KM:</b> {{ ts[4] }} - {{ ts[5] }} | <b>Tarih:</b> {{ ts[6] }}<br>
                <b>Yapılanlar:</b> {{ ts[7] }} | <b>Toplam:</b> {{ "%.2f"|format(ts[8]) }} TL<br>
                <hr style="border:0; border-top:1px solid #1e293b; margin: 10px 0;">
                <form action="/durum_guncelle" method="POST" style="display: flex; gap: 8px; align-items: center;">
                    <input type="hidden" name="servis_id" value="{{ ts[0] }}">
                    <label style="font-size:12px; margin:0;">Durum:</label>
                    <select name="durum" style="padding: 6px; font-size: 12px; background: #07090e;" onchange="this.form.submit()">
                        <option value="Bekliyor" {% if ts[9] == 'Bekliyor' %}selected{% endif %}>Bekliyor</option>
                        <option value="İşlemde" {% if ts[9] == 'İşlemde' %}selected{% endif %}>İşlemde</option>
                        <option value="Hazır" {% if ts[9] == 'Hazır' %}selected{% endif %}>Hazır</option>
                        <option value="Teslime Hazır" {% if ts[9] == 'Teslime Hazır' %}selected{% endif %}>Teslime Hazır</option>
                        <option value="Parça Bekliyor" {% if ts[9] == 'Parça Bekliyor' %}selected{% endif %}>Parça Bekliyor</option>
                    </select>
                </form>
                <a href="https://wa.me/{{ ts[3] }}?text=Sayin%20{{ ts[2] }},%20Iz%20Motorsiklet%20servisindeki%20motosikletinizin%20durumu:%20{{ ts[9] }}.%20Detaylar%20icin%20bekleriz." target="_blank" class="whatsapp-btn">💬 Müşteriye Durum Mesajı Gönder</a>
            </div>
            {% endfor %}
        {% else %}
            <p style="color: #94a3b8; text-align: center;">Kayıtlı aktif araç bulunmuyor.</p>
        {% endif %}
    </div>

    <!-- MÜŞTERİ & PLAKA GEÇMİŞİ -->
    <div id="historyTab" class="tab-content">
        <form method="GET" action="/">
            <input type="hidden" name="tab" value="history">
            <div class="form-group">
                <label>Plaka, Müşteri Adı veya Telefon ile Sorgula</label>
                <input type="text" name="sorgu_plaka" placeholder="Örn: 34 ABC veya Ahmet..." value="{{ sorgu_plaka or '' }}">
            </div>
            <button type="submit" class="btn-action">Hızlı Arama Yap</button>
        </form>
        <hr style="margin: 20px 0; border: 0; border-top: 1px solid #1e293b;">
        <h3>Arama Sonuçları / Geçmiş</h3>
        {% if kayitlar %}
            {% for k in kayitlar %}
            <div class="card">
                <b>Plaka:</b> {{ k[1] }} | <b>Tarih:</b> {{ k[6] }}<br>
                <b>Müşteri:</b> {{ k[2] }} ({{ k[3] }})<br>
                <b>Model / KM:</b> {{ k[4] }} - {{ k[5] }}<br>
                <b>Yapılanlar:</b> {{ k[7] }}<br>
                <b>Toplam Tutar:</b> <span style="color: #facc15; font-weight: bold;">{{ "%.2f"|format(k[8]) }} TL</span><br>
                <a href="https://wa.me/{{ k[3] }}?text=Sayin%20{{ k[2] }},%20Iz%20Motorsiklet%20servis%20formunuz%20hazirdir.%20Toplam%20Tutar:%20{{ "%.2f"|format(k[8]) }}%20TL.%20Iyi%20gunler%20dileriz." target="_blank" class="whatsapp-btn">💬 Fatura / Form Bilgisi Gönder</a>
            </div>
            {% endfor %}
        {% else %}
            <p style="color: #94a3b8; text-align: center;">Kayıt bulunamadı.</p>
        {% endif %}
    </div>

    <!-- STOK TAKİBİ -->
    <div id="stockTab" class="tab-content">
        <h3>Parça / Ürün Stok Yönetimi</h3>
        <form method="POST" action="/stok_ekle">
            <div class="form-group"><input type="text" name="parca_adi" placeholder="Parça Adı (Örn: Buji NGK)" required></div>
            <div class="form-group"><input type="number" name="adet" placeholder="Stok Adedi" required></div>
            <div class="form-group"><input type="number" step="0.01" name="fiyat" placeholder="Birim Satış Fiyatı (TL)" required></div>
            <button type="submit" class="btn-action">Stok Ekle / Güncelle</button>
        </form>
        <hr style="margin: 20px 0; border: 0; border-top: 1px solid #1e293b;">
        <h4>Mevcut Stoklar</h4>
        {% if stoklar %}
            {% for s in stoklar %}
            <div class="card">
                <b>{{ s[1] }}</b> - Adet: <span style="color: {% if s[2] < 3 %}#f87171{% else %}#4ade80{% endif %}; font-weight:bold;">{{ s[2] }}</span> | Fiyat: {{ "%.2f"|format(s[3]) }} TL
            </div>
            {% endfor %}
        {% else %}
            <p style="color: #94a3b8; text-align: center;">Stokta ürün bulunmuyor.</p>
        {% endif %}
    </div>

    <!-- RANDEVULAR -->
    <div id="randevuTab" class="tab-content">
        <h3>Atölye Randevu Takvimi</h3>
        <form method="POST" action="/randevu_ekle">
            <div class="form-group"><input type="text" name="musteri_ad" placeholder="Müşteri Adı Soyadı" required></div>
            <div class="form-group"><input type="text" name="tel" placeholder="Telefon Numarası" required></div>
            <div class="form-group"><input type="text" name="tarih_saat" placeholder="Randevu Tarih ve Saati (Örn: 05.11.2026 - 14:30)" required></div>
            <div class="form-group"><input type="text" name="notlar" placeholder="Randevu Notu (Örn: Periyodik bakım)"></div>
            <button type="submit" class="btn-action">Randevu Oluştur</button>
        </form>
        <hr style="margin: 20px 0; border: 0; border-top: 1px solid #1e293b;">
        <h4>Aktif Randevular</h4>
        {% if randevular %}
            {% for r in randevular %}
            <div class="card" style="border-left: 4px solid #0d9488;">
                <b>Müşteri:</b> {{ r[1] }} ({{ r[2] }})<br>
                <b>Zaman:</b> <span style="color:#facc15;">{{ r[3] }}</span><br>
                <b>Not:</b> {{ r[4] }}<br>
                <a href="https://wa.me/{{ r[2] }}?text=Sayin%20{{ r[1] }},%20Iz%20Motorsiklet%20icin%20{{ r[3] }}%20tarihli%20randevunuzu%20bekliyoruz." target="_blank" class="whatsapp-btn">💬 Randevu Hatırlat</a>
            </div>
            {% endfor %}
        {% else %}
            <p style="color: #94a3b8; text-align: center;">Kayıtlı randevu bulunmuyor.</p>
        {% endif %}
    </div>

    <!-- AKILLI BAKIM HATIRLATMA -->
    <div id="reminderTab" class="tab-content">
        <h3>Akıllı Bakım Hatırlatıcı</h3>
        <p style="font-size: 13px; color: #94a3b8; margin-bottom: 15px;">Daha önce gelen motorların üzerinden geçen süreler:</p>
        {% if bakim_listesi %}
            {% for b in bakim_listesi %}
            <div class="card" style="border-left: 4px solid #facc15;">
                <b>Plaka:</b> {{ b[1] }} | <b>Müşteri:</b> {{ b[2] }} ({{ b[3] }})<br>
                <b>Son Servis Tarihi:</b> {{ b[6] }} <span style="color:#facc15; font-weight:bold;">({{ b.gecen_sure }})</span><br>
                <b>Model / KM:</b> {{ b[4] }} - {{ b[5] }}<br>
                <a href="https://wa.me/{{ b[3] }}?text=Sayin%20{{ b[2] }},%20Iz%20Motorsiklet%20servisimizdeki%20son%20bakiminizin%20uzerinden%20sure%20gecti.%20Motorunuzun%20bakim%20vakti%20yaklasti,%20bekleriz.%20Iyi%20gunler%20dileriz." target="_blank" class="whatsapp-btn">💬 Bakım Hatırlatması Gönder</a>
            </div>
            {% endfor %}
        {% else %}
            <p style="color: #94a3b8; text-align: center;">Kayıtlı bakım geçmişi bulunmuyor.</p>
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
    
    setTimeout(() => {
        isSubmitted = false;
        btn.innerText = "Servis Formu PDF İndir & Kaydet";
        btn.disabled = false;
    }, 5000);
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
    t_bilgi.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 0.8, colors.HexColor("#CBD5E0")),
        ('INNERGRID', (0,0), (-1,-1), 0.8, colors.HexColor("#CBD5E0")),
        ('PADDING', (0,0), (-1,-1), 5),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#FAFAFA")),
    ]))
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
            islem_adi = ""
            adet = ""
            tutar_str = ""
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
        ('ALIGN', (2,0), (2,-4), 'CENTER'),
        ('ALIGN', (3,0), (3,-1), 'RIGHT'),
        ('GRID', (0,0), (-1,-4), 0.5, colors.HexColor("#CBD5E0")),
        ('LINEBELOW', (0,-4), (-1,-1), 0.5, colors.HexColor("#CBD5E0")),
        ('SPAN', (1,-3), (2,-3)),
        ('SPAN', (1,-2), (2,-2)),
        ('SPAN', (1,-1), (2,-1)),
        ('BACKGROUND', (1,-1), (-1,-1), colors.HexColor("#FFD54F")),
        ('PADDING', (0,0), (-1,-1), 3.5),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(t_hizmet)
    story.append(Spacer(1, 6))

    notlar_text = veri.get('notlar', '')
    p_notlar = Paragraph(f"<b>Notlar ve Tespitler</b><br/>{notlar_text}<br/><br/>", style_normal)
    t_notlar = Table([[p_notlar]], colWidths=[550])
    t_notlar.setStyle(TableStyle([('LINEBELOW', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0")), ('PADDING', (0,0), (-1,-1), 3)]))
    story.append(t_notlar)
    story.append(Spacer(1, 4))

    if hasar_foto_yolu and os.path.exists(hasar_foto_yolu):
        try:
            story.append(Paragraph("<b>Hasar / Durum Ek Fotoğrafı</b>", style_bold))
            story.append(Spacer(1, 2))
            story.append(Image(hasar_foto_yolu, width=200, height=120))
            story.append(Spacer(1, 4))
        except Exception:
            pass

    imza_data = [
        [Paragraph("<b>Müşteri Onayı</b>", style_bold), Paragraph("<b>Servis Yetkilisi</b>", style_bold)],
        ["", ""],
        [Paragraph("<font size=7.5 color='#666666'>Ad / Soyad / İmza</font>", style_normal), Paragraph("<font size=7.5 color='#666666'>Kaşe / İmza</font>", style_normal)]
    ]
    t_imza = Table(imza_data, colWidths=[275, 275])
    t_imza.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('LINEBELOW', (0,0), (0,0), 0.5, colors.HexColor("#A0AEC0")),
        ('LINEBELOW', (1,0), (1,0), 0.5, colors.HexColor("#A0AEC0")),
        ('PADDING', (0,0), (-1,-1), 2),
    ]))
    story.append(t_imza)
    story.append(Spacer(1, 6))

    footer_data = [[
        Paragraph("<font size=7.5 color='#888888'>İz Motorsiklet Çekmeköy Servis Sistemi</font>", style_normal),
        Paragraph("<font size=7.5 color='#888888'>Sayfa 1 / 1</font>", style_normal)
    ]]
    t_footer = Table(footer_data, colWidths=[275, 275])
    t_footer.setStyle(TableStyle([('ALIGN', (0,0), (0,0), 'LEFT'), ('ALIGN', (1,0), (1,0), 'RIGHT'), ('PADDING', (0,0), (-1,-1), 0)]))
    story.append(t_footer)

    doc.build(story)

# --- WEB ROUTES ---
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        girilen_sifre = request.form.get('sifre')
        if girilen_sifre == SIFRE:
            session['giris'] = True
            return redirect(url_for('index'))
        else:
            return render_template_string(HTML_LOGIN, error="Hatalı Şifre Kanka!")
            
    if not session.get('giris'):
        return render_template_string(HTML_LOGIN)

    conn = sqlite3.connect('iz_motor_servis.db', check_same_thread=False)
    cursor = conn.cursor()

    sorgu_plaka = request.args.get('sorgu_plaka', '').strip()
    kayitlar = []
    if sorgu_plaka:
        cursor.execute("SELECT * FROM servisler WHERE plaka LIKE ? OR musteri_ad LIKE ? OR musteri_tel LIKE ? ORDER BY id DESC", 
                       ('%' + sorgu_plaka + '%', '%' + sorgu_plaka + '%', '%' + sorgu_plaka + '%'))
        kayitlar = cursor.fetchall()

    cursor.execute("SELECT * FROM stok")
    stoklar = cursor.fetchall()

    cursor.execute("SELECT * FROM randevular ORDER BY id DESC")
    randevular = cursor.fetchall()

    cursor.execute("SELECT * FROM servisler ORDER BY id DESC")
    tum_servisler = cursor.fetchall()

    cursor.execute("SELECT SUM(toplam_tutar) FROM servisler")
    res = cursor.fetchone()
    toplam_ciro = res[0] if res and res[0] else 0.0

    cursor.execute("SELECT * FROM servisler ORDER BY id DESC")
    ham_bakimlar = cursor.fetchall()
    bakim_listesi = []
    
    bugun = datetime.date.today()
    for b in ham_bakimlar:
        tarih_str = b[6]
        gecen_sure_str = "Yeni kayıt"
        try:
            servis_tarihi = datetime.datetime.strptime(tarih_str, "%d.%m.%Y").date()
            fark_gun = (bugun - servis_tarihi).days
            if fark_gun == 0:
                gecen_sure_str = "Bugün geldi"
            elif fark_gun < 30:
                gecen_sure_str = f"{fark_gun} gün önce geldi"
            elif fark_gun < 365:
                ay = fark_gun // 30
                gecen_sure_str = f"{ay} ay önce geldi"
            else:
                yil = fark_gun // 365
                gecen_sure_str = f"{yil} yıl önce geldi"
        except Exception:
            pass
        
        b_item = list(b)
        b_item.append(gecen_sure_str)
        bakim_listesi.append(b_item)

    conn.close()
        
    return render_template_string(HTML_PANEL, kayitlar=kayitlar, sorgu_plaka=sorgu_plaka, stoklar=stoklar, randevular=randevular, tum_servisler=tum_servisler, toplam_ciro=toplam_ciro, bakim_listesi=bakim_listesi)

@app.route('/durum_guncelle', methods=['POST'])
def durum_guncelle():
    if not session.get('giris'): return redirect(url_for('index'))
    servis_id = request.form.get('servis_id')
    yeni_durum = request.form.get('durum')

    conn = sqlite3.connect('iz_motor_servis.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("UPDATE servisler SET durum = ? WHERE id = ?", (yeni_durum, servis_id))
    conn.commit()
    conn.close()
    return redirect(url_for('index') + '?tab=araclar')

@app.route('/stok_ekle', methods=['POST'])
def stok_ekle():
    if not session.get('giris'): return redirect(url_for('index'))
    parca = request.form.get('parca_adi')
    adet = int(request.form.get('adet', 0))
    fiyat = float(request.form.get('fiyat', 0.0))

    conn = sqlite3.connect('iz_motor_servis.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO stok (parca_adi, adet, fiyat) VALUES (?, ?, ?)", (parca, adet, fiyat))
    conn.commit()
    conn.close()
    return redirect(url_for('index') + '?tab=stock')

@app.route('/randevu_ekle', methods=['POST'])
def randevu_ekle():
    if not session.get('giris'): return redirect(url_for('index'))
    musteri_ad = request.form.get('musteri_ad')
    tel = request.form.get('tel')
    tarih_saat = request.form.get('tarih_saat')
    notlar = request.form.get('notlar', '')

    conn = sqlite3.connect('iz_motor_servis.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO randevular (musteri_ad, tel, tarih_saat, notlar) VALUES (?, ?, ?, ?)", (musteri_ad, tel, tarih_saat, notlar))
    conn.commit()
    conn.close()
    return redirect(url_for('index') + '?tab=randevu')

@app.route('/cikis')
def cikis():
    session.pop('giris', None)
    return redirect(url_for('index'))

@app.route('/olustur', methods=['POST'])
def olustur():
    if not session.get('giris'):
        return redirect(url_for('index'))

    musteri_ad = request.form.get('musteri_ad')
    musteri_tel = request.form.get('musteri_tel')
    plaka = request.form.get('plaka')
    model = request.form.get('model')
    km = request.form.get('km', '0')
    notlar = request.form.get('notlar', '')
    
    try:
        iscilik = float(request.form.get('iscilik', 0))
    except ValueError:
        iscilik = 0.0

    conn = sqlite3.connect('iz_motor_servis.db', check_same_thread=False)
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
                ad = islem_adlari[i]
                s_id = stok_idler[i] if i < len(stok_idler) else ""
                adt = int(adetler[i]) if i < len(adetler) and adetler[i] else 1
                fyt = float(fiyatlar[i]) if i < len(fiyatlar) and fiyatlar[i] else 0.0
                tutar = adt * fyt
                yedek_parca_toplam += tutar
                
                islemler.append({'ad': ad, 'adet': adt, 'fiyat': fyt})
                islem_ozeti_list.append(f"{ad} (x{adt})")

                if s_id:
                    cursor.execute("SELECT adet FROM stok WHERE id = ?", (s_id,))
                    stok_item = cursor.fetchone()
                    if stok_item:
                        mevcut_adet = stok_item[0]
                        yeni_adet = max(0, mevcut_adet - adt)
                        cursor.execute("UPDATE stok SET adet = ? WHERE id = ?", (yeni_adet, s_id))
            except Exception:
                continue

    genel_toplam = yedek_parca_toplam + iscilik
    islem_str = ", ".join(islem_ozeti_list) if islem_ozeti_list else "İşlem belirtilmedi"
    tarih_str = datetime.date.today().strftime("%d.%m.%Y")

    cursor.execute('''
        INSERT INTO servisler (plaka, musteri_ad, musteri_tel, model, km, tarih, detaylar, toplam_tutar, durum)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Bekliyor')
    ''', (plaka, musteri_ad, musteri_tel, model, km, tarih_str, islem_str, genel_toplam))
    
    conn.commit()
    conn.close()

    veri = {
        'musteri_ad': musteri_ad, 'musteri_tel': musteri_tel, 'plaka': plaka,
        'model': model, 'km': km, 'notlar': notlar, 'iscilik': iscilik, 'islemler': islemler
    }

    logo_file = request.files.get('logo')
    logo_path = None
    if logo_file and logo_file.filename != '':
        logo_path = f"temp_logo_web_{plaka}.jpg"
        logo_file.save(logo_path)

    hasar_file = request.files.get('hasar_foto')
    hasar_path = None
    if hasar_file and hasar_file.filename != '':
        hasar_path = f"temp_hasar_web_{plaka}.jpg"
        hasar_file.save(hasar_path)

    pdf_path = f"servis_formu_{plaka}.pdf"
    pdf_olustur(pdf_path, veri, logo_path, hasar_path)

    response = send_file(pdf_path, as_attachment=True)
    @response.call_on_close
    def cleanup():
        if os.path.exists(pdf_path): os.remove(pdf_path)
        if logo_path and os.path.exists(logo_path): os.remove(logo_path)
        if hasar_path and os.path.exists(hasar_path): os.remove(hasar_path)

    return response


# --- TELEGRAM BOTU (DÜZELTİLMİŞ AKIŞ VE ŞİFRE YÖNETİMİ) ---
SIFRE_DURUMU = {}
LOGO_AL, HASAR_AL, MUSTERI_AD, MUSTERI_TEL, ARAÇ_PLAKA, ARAÇ_MODEL, ARAÇ_KM, ISLEM_EKLE, ISLEM_FIYAT, ISLEM_ADET, ISCILIK, NOTLAR = range(100, 112)
STOK_AD, STOK_ADET, STOK_FIYAT = range(200, 203)
SIFRE_BEKLE = range(500, 501)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    SIFRE_DURUMU[user_id] = False
    await update.message.reply_text("Selam kanka! İz Motorsiklet Botuna hoş geldin.\nDevam etmek için önce **yönetici şifresini** gir kanka:")
    return SIFRE_BEKLE

async def sifre_giris_kontrol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    if text == SIFRE:
        SIFRE_DURUMU[user_id] = True
        keyboard = [
            ["🛠️ Servis Formu Oluştur", "📅 Randevu Ekle"],
            ["⚡ Hızlı Fiyat Teklifi", "🔍 Plaka Sorgula"],
            ["📊 Günlük / Haftalık Özet", "🔔 Günün Randevuları"],
            ["🏍️ Araçlar", "📦 Stok Ekle"],
            ["📦 Stok Listesi"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Şifre doğru kanka! Aşağıdaki butonlardan yapmak istediğin işlemi seçebilirsin:", reply_markup=reply_markup)
        return ConversationHandler.END
    else:
        await update.message.reply_text("Hatalı şifre kanka! Tekrar dene:")
        return SIFRE_BEKLE

async def logo_uyari(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Kanka yazı değil, **logo fotoğrafı** göndermen gerekiyor:")
    return LOGO_AL

async def hizli_fiyat_teklifi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not SIFRE_DURUMU.get(update.effective_user.id, False):
        await update.message.reply_text("Önce şifreyi girmen gerekiyor kanka! /start yazabilirsin.")
        return
        
    conn = sqlite3.connect('iz_motor_servis.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT parca_adi, fiyat FROM stok")
    stoklar = cursor.fetchall()
    conn.close()

    fiyatlar_sozlugu = {s[0].lower(): s[1] for s in stoklar}

    def bul_fiyat(anahtar_kelimeler):
        for k, f in fiyatlar_sozlugu.items():
            if any(kelime in k for kelime in anahtar_kelimeler):
                return f
        return None

    yag_fiyat = bul_fiyat(["yağ", "motor yağı", "oil"])
    buji_fiyat = bul_fiyat(["buji", "ngk"])
    kayis_fiyat = bul_fiyat(["kayış", "varyatör", "kayis"])
    far_fiyat = bul_fiyat(["far", "ampul", "led", "lamba"])

    msg = "⚡ **İZ MOTORSİKLET - HIZLI FİYAT TEKLİFİ**\n\n"
    msg += f"🛢️ **Yağ Değişimi:** {fiyat_str(yag_fiyat)}\n"
    msg += f"⚡ **Buji Değişimi:** {fiyat_str(buji_fiyat)}\n"
    msg += f"⚙️ **Kayış Değişimi:** {fiyat_str(kayis_fiyat)}\n"
    msg += f"💡 **Far / Ampul Değişimi:** {fiyat_str(far_fiyat)}\n\n"
    
    genel_toplam_tahmin = (yag_fiyat or 0) + (buji_fiyat or 0) + (kayis_fiyat or 0) + (far_fiyat or 0) + 500
    if genel_toplam_tahmin > 500:
        msg += f"🛠️ **Ortalama Genel Bakım (Parçalar + İşçilik):** `~{genel_toplam_tahmin:.2f} TL`\n"
    else:
        msg += f"🛠️ **Genel Bakım:** Stoklarda bazı temel parçalar eksik, fiyat tam hesaplanamadı.\n"
    
    msg += "\n_(Not: Fiyatlar stoktaki güncel birim fiyatlarına göre otomatik hesaplanmıştır.)_"

    keyboard = [
        ["🛠️ Servis Formu Oluştur", "📅 Randevu Ekle"],
        ["⚡ Hızlı Fiyat Teklifi", "🔍 Plaka Sorgula"],
        ["📊 Günlük / Haftalık Özet", "🔔 Günün Randevuları"],
        ["🏍️ Araçlar", "📦 Stok Ekle"],
        ["📦 Stok Listesi"]
    ]
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

def fiyat_str(val):
    if val is not None:
        return f"`{val:.2f} TL`"
    return "_Stokta yok / Tanımsız_"

async def plaka_sorgu_baslat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not SIFRE_DURUMU.get(update.effective_user.id, False):
        await update.message.reply_text("Önce şifreyi girmen gerekiyor kanka! /start yazabilirsin.")
        return ConversationHandler.END
        
    await update.message.reply_text("Sorgulamak istediğin **Plakayı veya Müşteri Adını** yaz kanka:", reply_markup=ReplyKeyboardRemove())
    return PLAKA_SORGU

async def plaka_sorgu_yap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sorgu = update.message.text.strip()
    conn = sqlite3.connect('iz_motor_servis.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT plaka, musteri_ad, musteri_tel, model, km, tarih, detaylar, toplam_tutar, durum FROM servisler WHERE plaka LIKE ? OR musteri_ad LIKE ? ORDER BY id DESC", 
                   ('%' + sorgu + '%', '%' + sorgu + '%'))
    sonuclar = cursor.fetchall()
    conn.close()

    keyboard = [
        ["🛠️ Servis Formu Oluştur", "📅 Randevu Ekle"],
        ["⚡ Hızlı Fiyat Teklifi", "🔍 Plaka Sorgula"],
        ["📊 Günlük / Haftalık Özet", "🔔 Günün Randevuları"],
        ["🏍️ Araçlar", "📦 Stok Ekle"],
        ["📦 Stok Listesi"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    if not sonuclar:
        await update.message.reply_text(f"❌ '{sorgu}' ile eşleşen geçmiş servis kaydı bulunamadı kanka.", reply_markup=reply_markup)
        return ConversationHandler.END

    for r in sonuclar[:3]:
        plaka, ad, tel, model, km, tarih, detay, tutar, durum = r
        msg = f"🔍 **Servis Geçmişi Bulundu:**\n\n"
        msg += f"🏍️ **Plaka:** {plaka}\n"
        msg += f"👤 **Müşteri:** {ad} ({tel})\n"
        msg += f"🛵 **Model / KM:** {model} - {km} KM\n"
        msg += f"📅 **Tarih:** {tarih}\n"
        msg += f"🛠️ **Yapılanlar:** {detay}\n"
        msg += f"💵 **Toplam Tutar:** `{tutar:.2f} TL`\n"
        msg += f"📌 **Son Durum:** `{durum}`"
        await update.message.reply_text(msg, parse_mode="Markdown")

    await update.message.reply_text("Ana menüdesin kanka:", reply_markup=reply_markup)
    return ConversationHandler.END

async def gunluk_haftalik_ozet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not SIFRE_DURUMU.get(update.effective_user.id, False):
        await update.message.reply_text("Önce şifreyi girmen gerekiyor kanka! /start yazabilirsin.")
        return
        
    bugun_str = datetime.date.today().strftime("%d.%m.%Y")
    
    conn = sqlite3.connect('iz_motor_servis.db', check_same_thread=False)
    cursor = conn.cursor()
    
    cursor.execute("SELECT SUM(toplam_tutar), COUNT(id) FROM servisler WHERE tarih = ?", (bugun_str,))
    bugun_res = cursor.fetchone()
    bugun_ciro = bugun_res[0] if bugun_res and bugun_res[0] else 0.0
    bugun_adet = bugun_res[1] if bugun_res and bugun_res[1] else 0

    cursor.execute("SELECT SUM(toplam_tutar), COUNT(id) FROM servisler")
    toplam_res = cursor.fetchone()
    toplam_ciro = toplam_res[0] if toplam_res and toplam_res[0] else 0.0
    toplam_adet = toplam_res[1] if toplam_res and toplam_res[1] else 0

    cursor.execute("SELECT COUNT(id) FROM stok WHERE adet < 3")
    kritik_res = cursor.fetchone()
    kritik_adet = kritik_res[0] if kritik_res else 0

    conn.close()

    msg = "📊 **İZ MOTORSİKLET - ÖZET RAPORU**\n\n"
    msg += f"📅 **Bugünkü Tarih:** {bugun_str}\n"
    msg += f"🟢 **Bugün Giren Araç:** {bugun_adet} adet\n"
    msg += f"💵 **Bugünkü Ciro:** `{bugun_ciro:.2f} TL`\n\n"
    msg += f"───────────────────\n"
    msg += f"📈 **Toplam Servis Sayısı:** {toplam_adet} adet\n"
    msg += f"💰 **Tüm Zamanlar Cirosu:** `{toplam_ciro:.2f} TL`\n"
    msg += f"⚠️ **Kritik Stok (Azalan Ürün):** {kritik_adet} parça\n"

    keyboard = [
        ["🛠️ Servis Formu Oluştur", "📅 Randevu Ekle"],
        ["⚡ Hızlı Fiyat Teklifi", "🔍 Plaka Sorgula"],
        ["📊 Günlük / Haftalık Özet", "🔔 Günün Randevuları"],
        ["🏍️ Araçlar", "📦 Stok Ekle"],
        ["📦 Stok Listesi"]
    ]
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

async def gunun_randevulari(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not SIFRE_DURUMU.get(update.effective_user.id, False):
        await update.message.reply_text("Önce şifreyi girmen gerekiyor kanka! /start yazabilirsin.")
        return
        
    conn = sqlite3.connect('iz_motor_servis.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT musteri_ad, tel, tarih_saat, notlar FROM randevular ORDER BY id DESC")
    randevular = cursor.fetchall()
    conn.close()

    msg = "🔔 **KAYITLI RANDEVULAR LİSTESİ**\n\n"
    if randevular:
        for r in randevular:
            ad, tel, zaman, notlar = r
            msg += f"👤 **Müşteri:** {ad} ({tel})\n"
            msg += f"⏰ **Zaman:** `{zaman}`\n"
            msg += f"📝 **Not:** {notlar or 'Belirtilmemiş'}\n"
            msg += f"───────────────────\n"
    else:
        msg += "Aktif kayıtlı randevu bulunmuyor kanka."

    keyboard = [
        ["🛠️ Servis Formu Oluştur", "📅 Randevu Ekle"],
        ["⚡ Hızlı Fiyat Teklifi", "🔍 Plaka Sorgula"],
        ["📊 Günlük / Haftalık Özet", "🔔 Günün Randevuları"],
        ["🏍️ Araçlar", "📦 Stok Ekle"],
        ["📦 Stok Listesi"]
    ]
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

async def yeni_servis_baslat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not SIFRE_DURUMU.get(update.effective_user.id, False):
        await update.message.reply_text("Önce şifreyi girmen gerekiyor kanka! /start yazabilirsin.")
        return ConversationHandler.END

    context.user_data['islemler'] = []
    context.user_data['hasar_path'] = None
    await update.message.reply_text("1️⃣ Önce dükkanın **logosunu** fotoğraf olarak gönder kanka (Zorunlu):", reply_markup=ReplyKeyboardRemove())
    return LOGO_AL

async def logo_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("Kanka yazı değil, **logo fotoğrafı** göndermen gerekiyor:")
        return LOGO_AL

    photo_file = await update.message.photo[-1].get_file()
    logo_path = f"temp_logo_tg_{update.effective_user.id}.jpg"
    await photo_file.download_to_drive(logo_path)
    context.user_data['logo_path'] = logo_path
    
    keyboard = [['❌ Hasar Fotoğrafı Yok / Geç']]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Logo alındı! Şimdi varsa **hasar / durum fotoğrafını** gönder kanka. Yoksa aşağıdaki butona basıp geçebilirsin:", reply_markup=reply_markup)
    return HASAR_AL

async def hasar_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        photo_file = await update.message.photo[-1].get_file()
        hasar_path = f"temp_hasar_tg_{update.effective_user.id}.jpg"
        await photo_file.download_to_drive(hasar_path)
        context.user_data['hasar_path'] = hasar_path
    
    await update.message.reply_text("Hasar fotoğrafı kaydedildi! Şimdi **Müşteri Adı ve Soyadını** gir kanka:", reply_markup=ReplyKeyboardRemove())
    return MUSTERI_AD

async def hasar_gec(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['hasar_path'] = None
    await update.message.reply_text("Hasar fotoğrafı atlandı. Şimdi **Müşteri Adı ve Soyadını** gir kanka:", reply_markup=ReplyKeyboardRemove())
    return MUSTERI_AD

async def musteri_ad_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['musteri_ad'] = update.message.text
    await update.message.reply_text("Müşteri Telefon Numarasını gir kanka (Örn: 90532...):")
    return MUSTERI_TEL

async def musteri_tel_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['musteri_tel'] = update.message.text
    await update.message.reply_text("Motosiklet Plakasını gir kanka:")
    return ARAÇ_PLAKA

async def arac_plaka_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['plaka'] = update.message.text
    await update.message.reply_text("Marka / Model bilgisini gir kanka (Örn: Honda Dio):")
    return ARAÇ_MODEL

async def arac_model_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['model'] = update.message.text
    await update.message.reply_text("Motosiklet KM bilgisini gir kanka:")
    return ARAÇ_KM

async def arac_km_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['km'] = update.message.text
    await update.message.reply_text("1. Yapılan İşlem veya Parça adını gir kanka:")
    return ISLEM_EKLE

async def islem_ad_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['gecici_islem'] = update.message.text
    await update.message.reply_text("Bu işlem/parça için Birim Fiyat (TL) gir kanka:")
    return ISLEM_FIYAT

async def islem_fiyat_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        fiyat = float(update.message.text.replace(',', '.'))
        context.user_data['gecici_fiyat'] = fiyat
        await update.message.reply_text("Adet / Miktar gir kanka:")
        return ISLEM_ADET
    except ValueError:
        await update.message.reply_text("Geçerli bir fiyat gir kanka:")
        return ISLEM_FIYAT

async def islem_adet_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        adet = int(update.message.text)
        context.user_data['islemler'].append({
            'ad': context.user_data['gecici_islem'],
            'adet': adet,
            'fiyat': context.user_data['gecici_fiyat']
        })
        reply_keyboard = [['+ Başka İşlem/Parça Ekle', 'İşlemler Bitti / İşçiliğe Geç']]
        await update.message.reply_text("Eklendi! Başka ekleyecek misin?", reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True))
        return ISLEM_EKLE
    except ValueError:
        await update.message.reply_text("Lütfen geçerli bir sayı gir kanka:")
        return ISLEM_ADET

async def islem_karar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == '+ Başka İşlem/Parça Ekle':
        await update.message.reply_text("Sonraki işlem veya parça adını yaz kanka:", reply_markup=ReplyKeyboardRemove())
        return ISLEM_EKLE
    else:
        await update.message.reply_text("Toplam İşçilik Tutarını (TL) gir kanka (Yoksa 0 yaz):", reply_markup=ReplyKeyboardRemove())
        return ISCILIK

async def iscilik_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['iscilik'] = float(update.message.text.replace(',', '.'))
        await update.message.reply_text("Notlar ve Tespitler var mı? (Yoksa 'Yok' yaz):")
        return NOTLAR
    except ValueError:
        await update.message.reply_text("Geçerli tutar gir kanka:")
        return ISCILIK

async def notlar_ve_bitis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    context.user_data['notlar'] = "" if text.lower() == "yok" else text
    
    await update.message.reply_text("Servis formu hazırlanıyor...", reply_markup=ReplyKeyboardRemove())
    
    plaka = context.user_data['plaka']
    pdf_path = f"servis_formu_{plaka}.pdf"
    logo_yolu = context.user_data.get('logo_path')
    hasar_yolu = context.user_data.get('hasar_path')
    
    musteri_ad = context.user_data['musteri_ad']
    musteri_tel = context.user_data['musteri_tel']
    islemler = context.user_data.get('islemler', [])
    iscilik = context.user_data.get('iscilik', 0.0)
    yedek_parca_toplam = sum(i['fiyat'] * i['adet'] for i in islemler)
    genel_toplam = yedek_parca_toplam + iscilik
    islem_ozeti_list = [f"{i['ad']} (x{i['adet']})" for i in islemler]
    islem_str = ", ".join(islem_ozeti_list) if islem_ozeti_list else "İşlem belirtilmedi"
    tarih_str = datetime.date.today().strftime("%d.%m.%Y")

    conn = sqlite3.connect('iz_motor_servis.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO servisler (plaka, musteri_ad, musteri_tel, model, km, tarih, detaylar, toplam_tutar, durum)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Bekliyor')
    ''', (plaka, musteri_ad, musteri_tel, context.user_data['model'], context.user_data['km'], tarih_str, islem_str, genel_toplam))
    conn.commit()
    conn.close()

    pdf_olustur(pdf_path, context.user_data, logo_yolu, hasar_yolu)
    
    with open(pdf_path, 'rb') as doc:
        keyboard = [
            ["🛠️ Servis Formu Oluştur", "📅 Randevu Ekle"],
            ["⚡ Hızlı Fiyat Teklifi", "🔍 Plaka Sorgula"],
            ["📊 Günlük / Haftalık Özet", "🔔 Günün Randevuları"],
            ["🏍️ Araçlar", "📦 Stok Ekle"],
            ["📦 Stok Listesi"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        wa_url = f"https://wa.me/{musteri_tel}?text=Sayin%20{musteri_ad},%20Iz%20Motorsiklet%20servis%20formunuz%20hazirdir.%20Toplam%20Tutar:%20{genel_toplam:.2f}%20TL.%20Iyi%20gunler%20dileriz."
        inline_kb = InlineKeyboardMarkup([[InlineKeyboardButton("💬 Müşteriye WhatsApp ile Gönder", url=wa_url)]])
        
        await update.message.reply_document(document=doc, caption="İşte servis formu kanka!", reply_markup=inline_kb)
        await update.message.reply_text("Ana menüye döndün kanka:", reply_markup=reply_markup)
        
    if os.path.exists(pdf_path): os.remove(pdf_path)
    if logo_yolu and os.path.exists(logo_yolu): os.remove(logo_yolu)
    if hasar_yolu and os.path.exists(hasar_yolu): os.remove(hasar_yolu)
        
    return ConversationHandler.END

async def randevu_baslat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not SIFRE_DURUMU.get(update.effective_user.id, False):
        await update.message.reply_text("Önce şifreyi girmen gerekiyor kanka! /start yazabilirsin.")
        return ConversationHandler.END
    await update.message.reply_text("Randevu vereceğin **Müşteri Adı Soyadını** yaz kanka:", reply_markup=ReplyKeyboardRemove())
    return RANDEVU_AD

async def randevu_ad_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['randevu_ad'] = update.message.text
    await update.message.reply_text("Müşteri **telefon numarasını** gir kanka (Örn: 90532...):")
    return RANDEVU_TEL

async def randevu_tel_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['randevu_tel'] = update.message.text
    await update.message.reply_text("Randevu **tarih ve saatini** gir kanka (Örn: 05.11.2026 - 15:00):")
    return RANDEVU_ZAMAN

async def randevu_zaman_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['randevu_zaman'] = update.message.text
    await update.message.reply_text("Randevu için **not veya işlem** yaz kanka (Yoksa 'Yok' yaz):")
    return RANDEVU_NOT

async def randevu_not_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    notlar = "" if text.lower() == "yok" else text
    
    ad = context.user_data['randevu_ad']
    tel = context.user_data['randevu_tel']
    zaman = context.user_data['randevu_zaman']

    conn = sqlite3.connect('iz_motor_servis.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO randevular (musteri_ad, tel, tarih_saat, notlar) VALUES (?, ?, ?, ?)", (ad, tel, zaman, notlar))
    conn.commit()
    conn.close()

    keyboard = [
        ["🛠️ Servis Formu Oluştur", "📅 Randevu Ekle"],
        ["⚡ Hızlı Fiyat Teklifi", "🔍 Plaka Sorgula"],
        ["📊 Günlük / Haftalık Özet", "🔔 Günün Randevuları"],
        ["🏍️ Araçlar", "📦 Stok Ekle"],
        ["📦 Stok Listesi"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(f"🚨 **YENİ RANDEVU BİLDİRİMİ!**\n- **Müşteri:** {ad} ({tel})\n- **Zaman:** `{zaman}`\n- **Not:** {notlar or 'Yok'}", parse_mode="Markdown", reply_markup=reply_markup)
    return ConversationHandler.END

async def stok_baslat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not SIFRE_DURUMU.get(update.effective_user.id, False):
        await update.message.reply_text("Önce şifreyi girmen gerekiyor kanka! /start yazabilirsin.")
        return ConversationHandler.END
    await update.message.reply_text("Eklenecek **Parça Adını** yaz kanka:", reply_markup=ReplyKeyboardRemove())
    return STOK_AD

async def stok_ad_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['stok_parca'] = update.message.text
    await update.message.reply_text("Stok **adet miktarını** gir kanka (Örn: 10):")
    return STOK_ADET

async def stok_adet_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['stok_adet'] = int(update.message.text)
        await update.message.reply_text("Birim **satış fiyatını (TL)** gir kanka (Örn: 250):")
        return STOK_FIYAT
    except ValueError:
        await update.message.reply_text("Geçerli bir sayı gir kanka:")
        return STOK_ADET

async def stok_fiyat_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        fiyat = float(update.message.text.replace(',', '.'))
        parca = context.user_data['stok_parca']
        adet = context.user_data['stok_adet']

        conn = sqlite3.connect('iz_motor_servis.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO stok (parca_adi, adet, fiyat) VALUES (?, ?, ?)", (parca, adet, fiyat))
        conn.commit()
        conn.close()

        keyboard = [
            ["🛠️ Servis Formu Oluştur", "📅 Randevu Ekle"],
            ["⚡ Hızlı Fiyat Teklifi", "🔍 Plaka Sorgula"],
            ["📊 Günlük / Haftalık Özet", "🔔 Günün Randevuları"],
            ["🏍️ Araçlar", "📦 Stok Ekle"],
            ["📦 Stok Listesi"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(f"✅ Başarıyla eklendi kanka!\n- **{parca}**: {adet} adet ({fiyat} TL)", parse_mode="Markdown", reply_markup=reply_markup)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Geçerli bir fiyat gir kanka:")
        return STOK_FIYAT

async def bot_araclar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not SIFRE_DURUMU.get(update.effective_user.id, False):
        await update.message.reply_text("Önce şifreyi girmen gerekiyor kanka! /start yazabilirsin.")
        return

    conn = sqlite3.connect('iz_motor_servis.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT id, plaka, musteri_ad, musteri_tel, model, durum FROM servisler ORDER BY id DESC LIMIT 5")
    araclar = cursor.fetchall()
    conn.close()

    if not araclar:
        await update.message.reply_text("Atölyede kayıtlı araç bulunmuyor kanka.")
        return

    for a in araclar:
        a_id, plaka, musteri, tel, model, durum = a
        keyboard = [
            [
                InlineKeyboardButton("Bekliyor", callback_data=f"durum_{a_id}_Bekliyor"),
                InlineKeyboardButton("İşlemde", callback_data=f"durum_{a_id}_İşlemde"),
                InlineKeyboardButton("Hazır", callback_data=f"durum_{a_id}_Hazır")
            ],
            [
                InlineKeyboardButton("Teslime Hazır", callback_data=f"durum_{a_id}_Teslime Hazır"),
                InlineKeyboardButton("Parça Bekliyor", callback_data=f"durum_{a_id}_Parça Bekliyor")
            ],
            [
                InlineKeyboardButton("💬 WhatsApp Bildirimi Gönder", url=f"https://wa.me/{tel}?text=Sayin%20{musteri},%20Iz%20Motorsiklet%20servisindeki%20motosikletinizin%20durumu:%20{durum}.%20Bekleriz.")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"🏍️ **Plaka:** {plaka}\n"
            f"👤 **Müşteri:** {musteri} ({tel})\n"
            f"🛵 **Model:** {model}\n"
            f"📌 **Durum:** `{durum}`",
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

async def durum_degistir_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")
    servis_id = data[1]
    yeni_durum = data[2]

    conn = sqlite3.connect('iz_motor_servis.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("UPDATE servisler SET durum = ? WHERE id = ?", (yeni_durum, servis_id))
    conn.commit()
    conn.close()

    await query.edit_message_text(text=f"✅ Araç durumu güncellendi: *{yeni_durum}*", parse_mode="Markdown")

async def bot_stok(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not SIFRE_DURUMU.get(update.effective_user.id, False):
        await update.message.reply_text("Önce şifreyi girmen gerekiyor kanka! /start yazabilirsin.")
        return

    conn = sqlite3.connect('iz_motor_servis.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT parca_adi, adet, fiyat FROM stok")
    stoklar = cursor.fetchall()
    conn.close()

    msg = "📦 **Mevcut Stok Listesi:**\n\n"
    if stoklar:
        for s in stoklar:
            msg += f"- {s[0]}: **{s[1]} adet** ({s[2]} TL)\n"
    else:
        msg += "Stokta ürün bulunmuyor."
    await update.message.reply_text(msg, parse_mode="Markdown")

async def iptal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logo_yolu = context.user_data.get('logo_path')
    hasar_yolu = context.user_data.get('hasar_path')
    if logo_yolu and os.path.exists(logo_yolu): os.remove(logo_yolu)
    if hasar_yolu and os.path.exists(hasar_yolu): os.remove(hasar_yolu)
    
    keyboard = [
        ["🛠️ Servis Formu Oluştur", "📅 Randevu Ekle"],
        ["⚡ Hızlı Fiyat Teklifi", "🔍 Plaka Sorgula"],
        ["📊 Günlük / Haftalık Özet", "🔔 Günün Randevuları"],
        ["🏍️ Araçlar", "📦 Stok Ekle"],
        ["📦 Stok Listesi"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("İşlem iptal edildi kanka.", reply_markup=reply_markup)
    return ConversationHandler.END

def run_telegram_bot():
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN: 
        print("HATA: BOT_TOKEN çevre değişkeni bulunamadı!")
        return
    
    print("Telegram bot başlatılıyor...")
    bot_app = Application.builder().token(TOKEN).build()

    # Şifre doğrulama akışı (ConversationHandler içine alındı)
    sifre_conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SIFRE_BEKLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, sifre_giris_kontrol)],
        },
        fallbacks=[CommandHandler('iptal', iptal)]
    )

    stok_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^📦 Stok Ekle$'), stok_baslat)],
        states={
            STOK_AD: [MessageHandler(filters.TEXT & ~filters.COMMAND, stok_ad_al)],
            STOK_ADET: [MessageHandler(filters.TEXT & ~filters.COMMAND, stok_adet_al)],
            STOK_FIYAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, stok_fiyat_al)],
        },
        fallbacks=[CommandHandler('iptal', iptal)]
    )

    randevu_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^📅 Randevu Ekle$'), randevu_baslat)],
        states={
            RANDEVU_AD: [MessageHandler(filters.TEXT & ~filters.COMMAND, randevu_ad_al)],
            RANDEVU_TEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, randevu_tel_al)],
            RANDEVU_ZAMAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, randevu_zaman_al)],
            RANDEVU_NOT: [MessageHandler(filters.TEXT & ~filters.COMMAND, randevu_not_al)],
        },
        fallbacks=[CommandHandler('iptal', iptal)]
    )

    plaka_sorgu_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^🔍 Plaka Sorgula$'), plaka_sorgu_baslat)],
        states={
            PLAKA_SORGU: [MessageHandler(filters.TEXT & ~filters.COMMAND, plaka_sorgu_yap)],
        },
        fallbacks=[CommandHandler('iptal', iptal)]
    )

    servis_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^🛠️ Servis Formu Oluştur$'), yeni_servis_baslat)],
        states={
            LOGO_AL: [MessageHandler(filters.PHOTO, logo_al), MessageHandler(filters.TEXT & ~filters.COMMAND, logo_uyari)],
            HASAR_AL: [
                MessageHandler(filters.PHOTO, hasar_al), 
                MessageHandler(filters.Regex(r'^❌ Hasar Fotoğrafı Yok / Geç$'), hasar_gec)
            ],
            MUSTERI_AD: [MessageHandler(filters.TEXT & ~filters.COMMAND, musteri_ad_al)],
            MUSTERI_TEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, musteri_tel_al)],
            ARAÇ_PLAKA: [MessageHandler(filters.TEXT & ~filters.COMMAND, arac_plaka_al)],
            ARAÇ_MODEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, arac_model_al)],
            ARAÇ_KM: [MessageHandler(filters.TEXT & ~filters.COMMAND, arac_km_al)],
            ISLEM_EKLE: [
                MessageHandler(filters.Regex(r'^\+ Başka İşlem/Parça Ekle$'), islem_karar),
                MessageHandler(filters.Regex(r'^İşlemler Bitti / İşçiliğe Geç$'), islem_karar),
                MessageHandler(filters.TEXT & ~filters.COMMAND, islem_ad_al)
            ],
            ISLEM_FIYAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, islem_fiyat_al)],
            ISLEM_ADET: [MessageHandler(filters.TEXT & ~filters.COMMAND, islem_adet_al)],
            ISCILIK: [MessageHandler(filters.TEXT & ~filters.COMMAND, iscilik_al)],
            NOTLAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, notlar_ve_bitis)],
        },
        fallbacks=[CommandHandler('iptal', iptal)]
    )

    bot_app.add_handler(sifre_conv)
    bot_app.add_handler(stok_conv)
    bot_app.add_handler(randevu_conv)
    bot_app.add_handler(plaka_sorgu_conv)
    bot_app.add_handler(servis_conv)
    bot_app.add_handler(CallbackQueryHandler(durum_degistir_callback, pattern="^durum_"))
    bot_app.add_handler(MessageHandler(filters.Regex('^⚡ Hızlı Fiyat Teklifi$'), hizli_fiyat_teklifi))
    bot_app.add_handler(MessageHandler(filters.Regex('^📊 Günlük / Haftalık Özet$'), gunluk_haftalik_ozet))
    bot_app.add_handler(MessageHandler(filters.Regex('^🔔 Günün Randevuları$'), gunun_randevulari))
    bot_app.add_handler(MessageHandler(filters.Regex('^🏍️ Araçlar$'), bot_araclar))
    bot_app.add_handler(MessageHandler(filters.Regex('^📦 Stok Listesi$'), bot_stok))

    bot_app.run_polling(stop_signals=None)

if __name__ == '__main__':
    threading.Thread(target=run_telegram_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
