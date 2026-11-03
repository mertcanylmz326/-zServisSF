import os
import datetime
import sqlite3
import threading
import asyncio
from flask import Flask, render_template_string, request, send_file, session, redirect, url_for
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    filters, ContextTypes, CallbackQueryHandler
)
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

app = Flask(__name__)
app.secret_key = "iz_motor_gizli_anahtar_erp_full_v19"

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
        .header-section { display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #1e293b; padding-bottom: 20px; margin-bottom: 25px; }
        .brand-box { display: flex; align-items: center; gap: 15px; }
        .brand-logo { background: linear-gradient(135deg, #facc15, #ca8a04); width: 50px; height: 50px; border-radius: 14px; display: flex; justify-content: center; align-items: center; font-size: 26px; box-shadow: 0 0 20px rgba(250,204,21,0.4); }
        .brand-title h1 { color: #facc15; margin: 0; font-size: 22px; text-transform: uppercase; letter-spacing: 1.5px; }
        .brand-title p { color: #94a3b8; margin: 2px 0 0 0; font-size: 12px; font-weight: 500; }
        .logout a { color: #f87171; text-decoration: none; font-size: 13px; font-weight: bold; padding: 6px 12px; background: rgba(248,113,113,0.1); border-radius: 8px; border: 1px solid rgba(248,113,113,0.3); }
        .dashboard-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 25px; }
        .stat-card { background: linear-gradient(135deg, #1e293b, #111827); border: 1px solid #334155; padding: 20px; border-radius: 14px; position: relative; }
        .stat-card h3 { margin: 0; font-size: 24px; color: #facc15; font-weight: 700; }
        .stat-card p { margin: 5px 0 0 0; color: #94a3b8; font-size: 12px; font-weight: 600; text-transform: uppercase; }
        .tabs { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; margin-bottom: 25px; background: #0b0f19; padding: 10px; border-radius: 12px; border: 1px solid #1e293b; }
        .tab-btn { background: #111827; color: #94a3b8; border: 1px solid #1f2937; padding: 10px 14px; border-radius: 8px; cursor: pointer; font-weight: bold; font-size: 12px; }
        .tab-btn.active { background: linear-gradient(135deg, #facc15, #ca8a04); color: #07090e; border-color: #facc15; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        h3 { color: #facc15; border-bottom: 1px solid #1e293b; padding-bottom: 10px; margin-top: 0; font-size: 18px; }
        .form-group { margin-bottom: 15px; }
        label { display: block; font-weight: bold; margin-bottom: 6px; font-size: 13px; color: #cbd5e1; }
        input, textarea, select { width: 100%; padding: 12px; background: #0b0f19; border: 1px solid #334155; border-radius: 10px; color: #fff; box-sizing: border-box; font-size: 14px; outline: none; }
        .item-row { display: flex; gap: 8px; margin-bottom: 10px; align-items: center; background: #1e293b; padding: 10px; border-radius: 10px; border: 1px solid #334155; }
        .item-row input.name-input { flex: 2; }
        .item-row select { flex: 1.5; background: #0b0f19; font-size: 12px; }
        .item-row input.small { flex: 0.8; }
        .btn-add { background: #0d9488; color: #fff; border: none; padding: 12px; border-radius: 10px; cursor: pointer; font-weight: bold; width: 100%; margin-bottom: 15px; }
        .btn-remove { background: #dc2626; color: #fff; border: none; padding: 8px 12px; border-radius: 8px; cursor: pointer; font-weight: bold; }
        button[type="submit"], .btn-action { background: linear-gradient(135deg, #facc15, #ca8a04); color: #0b0f19; border: none; padding: 14px; border-radius: 10px; cursor: pointer; width: 100%; font-size: 15px; font-weight: bold; margin-top: 15px; }
        .card { background: #162032; border: 1px solid #334155; padding: 16px; border-radius: 12px; margin-bottom: 12px; font-size: 14px; }
        .whatsapp-btn { display: inline-block; margin-top: 10px; background: #25d366; color: #fff; padding: 8px 14px; border-radius: 8px; text-decoration: none; font-size: 12px; font-weight: bold; }
        .alert-box { background: rgba(250,204,21,0.1); border: 1px solid #facc15; padding: 12px; border-radius: 10px; color: #facc15; margin-bottom: 15px; font-weight: bold; text-align: center; display: none; }
    </style>
</head>
<body>
<div class="container">
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
    
    <div class="dashboard-grid">
        <div class="stat-card"><h3>{{ "%.2f"|format(toplam_ciro) }} TL</h3><p>Toplam Servis Cirosu</p></div>
        <div class="stat-card"><h3>{{ tum_servisler|length }}</h3><p>Kayıtlı Toplam Araç</p></div>
        <div class="stat-card"><h3>{{ stoklar|length }}</h3><p>Stoktaki Çeşit Ürün</p></div>
        <div class="stat-card"><h3>{{ randevular|length }}</h3><p>Aktif Randevu Sayısı</p></div>
    </div>

    <div id="duplicateAlert" class="alert-box">⚠️ Bu servis formu az önce kaydedildi! Tekrar işlem yapılmadı.</div>

    <div class="tabs">
        <button class="tab-btn active" onclick="switchTab('formTab', this)">🛠️ Servis Formu</button>
        <button class="tab-btn" onclick="switchTab('araclarTab', this)">🏍️ Araçlar & Durum</button>
        <button class="tab-btn" onclick="switchTab('historyTab', this)">🔍 Müşteri & Plaka</button>
        <button class="tab-btn" onclick="switchTab('stockTab', this)">📦 Stok Takibi</button>
        <button class="tab-btn" onclick="switchTab('randevuTab', this)">📅 Randevular</button>
        <button class="tab-btn" onclick="switchTab('reminderTab', this)">⏰ Bakım Hatırlat</button>
    </div>

    <!-- 1. SERVİS FORMU -->
    <div id="formTab" class="tab-content active">
        <form id="serviceForm" action="/olustur" method="POST" enctype="multipart/form-data" onsubmit="handleFormSubmit(event)">
            <div class="form-group"><label>Dükkan Logosu <span style="color:#facc15;">(Zorunlu)</span></label><input type="file" name="logo" accept="image/*" required></div>
            <div class="form-group"><label>Hasar / Durum Fotoğrafı <span style="color:#94a3af;">(İsteğe Bağlı)</span></label><input type="file" name="hasar_foto" accept="image/*"></div>
            <div class="form-group"><label>Müşteri Adı Soyadı</label><input type="text" name="musteri_ad" placeholder="Örn: Ahmet Yılmaz" required></div>
            <div class="form-group"><label>Müşteri Telefon (WhatsApp)</label><input type="text" name="musteri_tel" placeholder="Örn: 905320000000" required></div>
            <div class="form-group"><label>Motosiklet Plaka</label><input type="text" name="plaka" placeholder="Örn: 34 ABC 123" required></div>
            <div class="form-group"><label>Marka / Model</label><input type="text" name="model" placeholder="Örn: Honda PCX 125" required></div>
            <div class="form-group"><label>Kilometre (KM)</label><input type="text" name="km" placeholder="Örn: 15000" required></div>

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

            <div class="form-group"><label>Ek İşçilik Tutarı (TL)</label><input type="number" step="0.01" name="iscilik" placeholder="Örn: 500" value="0"></div>
            <div class="form-group"><label>Notlar ve Tespitler</label><textarea name="notlar" rows="2" placeholder="Örn: Genel bakım yapıldı."></textarea></div>

            <button type="submit" id="submitBtn">Servis Formu PDF İndir & Kaydet</button>
        </form>
    </div>

    <!-- 2. ARAÇLAR & DURUM -->
    <div id="araclarTab" class="tab-content">
        <h3>Atölyedeki / Servisteki Araçlar</h3>
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
                <a href="https://wa.me/{{ ts[3] }}?text=Sayin%20{{ ts[2] }},%20Iz%20Motorsiklet%20servisindeki%20motosikletinizin%20durumu:%20{{ ts[9] }}.%20Bekleriz." target="_blank" class="whatsapp-btn">💬 Müşteriye Durum Mesajı Gönder</a>
            </div>
            {% endfor %}
        {% else %}
            <p style="color: #94a3b8; text-align: center;">Kayıtlı aktif araç bulunmuyor.</p>
        {% endif %}
    </div>

    <!-- 3. MÜŞTERİ & PLAKA GEÇMİŞİ -->
    <div id="historyTab" class="tab-content">
        <form method="GET" action="/">
            <input type="hidden" name="tab" value="history">
            <div class="form-group"><label>Plaka veya Müşteri Adı ile Sorgula</label><input type="text" name="sorgu_plaka" placeholder="Örn: 34 ABC veya Ahmet..." value="{{ sorgu_plaka or '' }}"></div>
            <button type="submit" class="btn-action">Hızlı Arama Yap</button>
        </form>
        <hr style="margin: 20px 0; border: 0; border-top: 1px solid #1e293b;">
        <h3>Arama Sonuçları / Geçmiş</h3>
        {% if kayitlar %}
            {% for k in kayitlar %}
            <div class="card">
                <b>Plaka:</b> {{ k[1] }} | <b>Tarih:</b> {{ k[6] }}<br>
                <b>Müşteri:</b> {{ k[2] }} ({{ k[3] }})<br>
                <b>İşlemler:</b> {{ k[7] }}<br>
                <b>Toplam Tutar:</b> <span style="color: #facc15; font-weight: bold;">{{ "%.2f"|format(k[8]) }} TL</span>
            </div>
            {% endfor %}
        {% else %}
            <p style="color: #94a3b8; text-align: center;">Kayıt bulunamadı.</p>
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
        <hr style="margin: 20px 0; border: 0; border-top: 1px solid #1e293b;">
        <h4>Mevcut Stoklar</h4>
        {% for s in stoklar %}
        <div class="card"><b>{{ s[1] }}</b> - Adet: <span style="color: {% if s[2] < 3 %}#f87171{% else %}#4ade80{% endif %}; font-weight:bold;">{{ s[2] }}</span> | Fiyat: {{ "%.2f"|format(s[3]) }} TL</div>
        {% endfor %}
    </div>

    <!-- 5. RANDEVULAR -->
    <div id="randevuTab" class="tab-content">
        <h3>Atölye Randevu Takvimi</h3>
        <form method="POST" action="/randevu_ekle">
            <div class="form-group"><input type="text" name="musteri_ad" placeholder="Müşteri Adı Soyadı" required></div>
            <div class="form-group"><input type="text" name="tel" placeholder="Telefon Numarası" required></div>
            <div class="form-group"><input type="text" name="tarih_saat" placeholder="Randevu Tarih ve Saati (Örn: 05.11.2026 - 14:30)" required></div>
            <div class="form-group"><input type="text" name="notlar" placeholder="Randevu Notu"></div>
            <button type="submit" class="btn-action">Randevu Oluştur</button>
        </form>
        <hr style="margin: 20px 0; border: 0; border-top: 1px solid #1e293b;">
        <h4>Aktif Randevular</h4>
        {% for r in randevular %}
        <div class="card" style="border-left: 4px solid #0d9488;"><b>Müşteri:</b> {{ r[1] }} ({{ r[2] }})<br><b>Zaman:</b> <span style="color:#facc15;">{{ r[3] }}</span></div>
        {% endfor %}
    </div>

    <!-- 6. BAKIM HATIRLAT -->
    <div id="reminderTab" class="tab-content">
        <h3>Akıllı Bakım Hatırlatıcı</h3>
        {% for b in bakim_listesi %}
        <div class="card" style="border-left: 4px solid #facc15;"><b>Plaka:</b> {{ b[1] }} | <b>Müşteri:</b> {{ b[2] }} ({{ b[3] }})<br><b>Geçen Süre:</b> <span style="color:#facc15; font-weight:bold;">{{ b.gecen_sure }}</span><br><a href="https://wa.me/{{ b[3] }}?text=Sayin%20{{ b[2] }},%20Iz%20Motorsiklet%20servisimizdeki%20bakim%20vaktiniz%20yaklasti,%20bekleriz." target="_blank" class="whatsapp-btn">💬 Bakım Hatırlatması Gönder</a></div>
        {% endfor %}
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

    conn = sqlite3.connect('iz_motor_servis.db', check_same_thread=False)
    cursor = conn.cursor()

    sorgu_plaka = request.args.get('sorgu_plaka', '').strip()
    kayitlar = []
    if sorgu_plaka:
        cursor.execute("SELECT * FROM servisler WHERE plaka LIKE ? OR musteri_ad LIKE ? ORDER BY id DESC", ('%' + sorgu_plaka + '%', '%' + sorgu_plaka + '%'))
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

    bugun = datetime.date.today()
    bakim_listesi = []
    for b in tum_servisler:
        try:
            s_tarih = datetime.datetime.strptime(b[6], "%d.%m.%Y").date()
            gun = (bugun - s_tarih).days
            sure_str = f"{gun} gün önce geldi"
        except Exception:
            sure_str = "Kayıtlı"
        b_item = list(b)
        b_item.append(sure_str)
        bakim_listesi.append(b_item)

    conn.close()
    return render_template_string(HTML_PANEL, kayitlar=kayitlar, sorgu_plaka=sorgu_plaka, stoklar=stoklar, randevular=randevular, tum_servisler=tum_servisler, toplam_ciro=toplam_ciro, bakim_listesi=bakim_listesi)

@app.route('/durum_guncelle', methods=['POST'])
def durum_guncelle():
    if not session.get('giris'): return redirect(url_for('index'))
    conn = sqlite3.connect('iz_motor_servis.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("UPDATE servisler SET durum = ? WHERE id = ?", (request.form.get('durum'), request.form.get('servis_id')))
    conn.commit()
    conn.close()
    return redirect(url_for('index') + '?tab=araclar')

@app.route('/stok_ekle', methods=['POST'])
def stok_ekle():
    if not session.get('giris'): return redirect(url_for('index'))
    conn = sqlite3.connect('iz_motor_servis.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO stok (parca_adi, adet, fiyat) VALUES (?, ?, ?)", (request.form.get('parca_adi'), int(request.form.get('adet', 0)), float(request.form.get('fiyat', 0))))
    conn.commit()
    conn.close()
    return redirect(url_for('index') + '?tab=stock')

@app.route('/randevu_ekle', methods=['POST'])
def randevu_ekle():
    if not session.get('giris'): return redirect(url_for('index'))
    conn = sqlite3.connect('iz_motor_servis.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO randevular (musteri_ad, tel, tarih_saat, notlar) VALUES (?, ?, ?, ?)", (request.form.get('musteri_ad'), request.form.get('tel'), request.form.get('tarih_saat'), request.form.get('notlar', '')))
    conn.commit()
    conn.close()
    return redirect(url_for('index') + '?tab=randevu')

@app.route('/olustur', methods=['POST'])
def olustur():
    if not session.get('giris'): return redirect(url_for('index'))
    ad, tel, plaka, model, km = request.form.get('musteri_ad'), request.form.get('musteri_tel'), request.form.get('plaka'), request.form.get('model'), request.form.get('km')
    
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
                ad_item = islem_adlari[i]
                s_id = stok_idler[i] if i < len(stok_idler) else ""
                adt = int(adetler[i]) if i < len(adetler) and adetler[i] else 1
                fyt = float(fiyatlar[i]) if i < len(fiyatlar) and fiyatlar[i] else 0.0
                tutar = adt * fyt
                yedek_parca_toplam += tutar
                
                islemler.append({'ad': ad_item, 'adet': adt, 'fiyat': fyt})
                islem_ozeti_list.append(f"{ad_item} (x{adt})")

                if s_id:
                    cursor.execute("SELECT adet FROM stok WHERE id = ?", (s_id,))
                    stok_item = cursor.fetchone()
                    if stok_item:
                        yeni_adet = max(0, stok_item[0] - adt)
                        cursor.execute("UPDATE stok SET adet = ? WHERE id = ?", (yeni_adet, s_id))
            except Exception:
                continue

    genel_toplam = yedek_parca_toplam + iscilik
    islem_str = ", ".join(islem_ozeti_list) if islem_ozeti_list else "Genel Bakım"
    tarih_str = datetime.date.today().strftime("%d.%m.%Y")

    cursor.execute('''
        INSERT INTO servisler (plaka, musteri_ad, musteri_tel, model, km, tarih, detaylar, toplam_tutar, durum)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Bekliyor')
    ''', (plaka, ad, tel, model, km, tarih_str, islem_str, genel_toplam))
    conn.commit()
    conn.close()

    logo_file = request.files.get('logo')
    logo_path = f"temp_logo_{plaka}.jpg" if logo_file and logo_file.filename != '' else None
    if logo_file and logo_path: logo_file.save(logo_path)

    hasar_file = request.files.get('hasar_foto')
    hasar_path = f"temp_hasar_{plaka}.jpg" if hasar_file and hasar_file.filename != '' else None
    if hasar_file and hasar_path: hasar_file.save(hasar_path)

    pdf_path = f"servis_formu_{plaka}.pdf"
    pdf_olustur(pdf_path, {'musteri_ad': ad, 'musteri_tel': tel, 'plaka': plaka, 'model': model, 'km': km, 'islemler': islemler, 'iscilik': iscilik}, logo_path, hasar_path)
    
    response = send_file(pdf_path, as_attachment=True)
    @response.call_on_close
    def cleanup():
        if os.path.exists(pdf_path): os.remove(pdf_path)
        if logo_path and os.path.exists(logo_path): os.remove(logo_path)
        if hasar_path and os.path.exists(hasar_path): os.remove(hasar_path)
    return response

@app.route('/cikis')
def cikis():
    session.pop('giris', None)
    return redirect(url_for('index'))

# --- TELEGRAM BOTU ---
SIFRE_DURUMU = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    SIFRE_DURUMU[user_id] = False
    await update.message.reply_text("Selam kanka! İz Motorsiklet Botuna hoş geldin.\nDevam etmek için önce **yönetici şifresini** gir kanka:")

async def mesaj_yoneticisi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    if not SIFRE_DURUMU.get(user_id, False):
        if text == SIFRE:
            SIFRE_DURUMU[user_id] = True
            keyboard = [
                ["🛠️ Servis Formu Oluştur", "📅 Randevu Ekle"],
                ["⚡ Hızlı Fiyat Teklifi", "🔍 Plaka Sorgula"],
                ["📊 Günlük Özet", "📦 Stok Listesi"],
                ["🏍️ Araçlar"]
            ]
            await update.message.reply_text("Şifre doğru kanka! Aşağıdaki menüden seçim yapabilirsin:", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))
        else:
            await update.message.reply_text("Hatalı şifre kanka! Tekrar dene:")
        return

    # Menü İşlemleri
    if text == "⚡ Hızlı Fiyat Teklifi":
        conn = sqlite3.connect('iz_motor_servis.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT parca_adi, fiyat FROM stok")
        stoklar = cursor.fetchall()
        conn.close()
        msg = "⚡ **İZ MOTORSİKLET - FİYAT LİSTESİ**\n\n"
        for s in stoklar:
            msg += f"- {s[0]}: `{s[1]} TL`\n"
        await update.message.reply_text(msg or "Stokta ürün bulunmuyor kanka.", parse_mode="Markdown")
        
    elif text == "📊 Günlük Özet":
        bugun = datetime.date.today().strftime("%d.%m.%Y")
        conn = sqlite3.connect('iz_motor_servis.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT SUM(toplam_tutar), COUNT(id) FROM servisler WHERE tarih = ?", (bugun,))
        res = cursor.fetchone()
        conn.close()
        ciro = res[0] if res and res[0] else 0.0
        adet = res[1] if res and res[1] else 0
        await update.message.reply_text(f"📊 **Günlük Özet ({bugun}):**\n- Giren Araç: {adet}\n- Toplam Ciro: `{ciro:.2f} TL`", parse_mode="Markdown")

    elif text == "📦 Stok Listesi":
        conn = sqlite3.connect('iz_motor_servis.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT parca_adi, adet, fiyat FROM stok")
        stoklar = cursor.fetchall()
        conn.close()
        msg = "📦 **Mevcut Stoklar:**\n\n"
        for s in stoklar:
            msg += f"- {s[1]} adet {s[0]} ({s[2]} TL)\n"
        await update.message.reply_text(msg or "Stok boş.", parse_mode="Markdown")

    elif text == "🏍️ Araçlar":
        conn = sqlite3.connect('iz_motor_servis.db', check_same_thread=False)
        cursor = conn.cursor()
        cursor.execute("SELECT plaka, musteri_ad, model, durum FROM servisler ORDER BY id DESC LIMIT 5")
        araclar = cursor.fetchall()
        conn.close()
        msg = "🏍️ **Son Giren Araçlar:**\n\n"
        for a in araclar:
            msg += f"- {a[0]} | {a[1]} | {a[2]} (`{a[3]}`)\n"
        await update.message.reply_text(msg or "Kayıtlı araç yok.", parse_mode="Markdown")
    else:
        await update.message.reply_text("Kanka menüden bir seçenek seçebilir veya /start yazabilirsin.")

def run_telegram_bot():
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN: return
    bot_app = Application.builder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mesaj_yoneticisi))
    bot_app.run_polling(stop_signals=None)

if __name__ == '__main__':
    threading.Thread(target=run_telegram_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
