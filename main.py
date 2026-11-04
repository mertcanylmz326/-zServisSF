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
app.secret_key = "iz_motor_gizli_anahtar_erp_postgres_v61"

SIFRE = "izmotor2026*"

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
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <title>İz Motorsiklet - ERP Paneli</title>
    <style>
        :root { --bg-main: #050811; --card-bg: rgba(11, 15, 25, 0.95); --accent: #facc15; --text-main: #f8fafc; --text-muted: #94a3b8; }
        body { font-family: 'Inter', sans-serif; background-color: var(--bg-main); color: var(--text-main); margin: 0; padding: 10px; }
        .container { max-width: 900px; margin: 0 auto; background: var(--card-bg); padding: 16px; border-radius: 20px; border: 1px solid rgba(250,204,21,0.25); box-shadow: 0 20px 50px rgba(0,0,0,0.9); }
        
        .header-box { display: flex; justify-content: space-between; align-items: center; background: rgba(18, 24, 40, 0.9); border: 1px solid #334155; padding: 12px 15px; border-radius: 14px; margin-bottom: 12px; }
        .brand-title { display: flex; align-items: center; gap: 10px; color: var(--accent); font-weight: 800; font-size: 15px; text-transform: uppercase; }
        .brand-icon { background: var(--accent); color: #030712; padding: 6px 10px; border-radius: 8px; font-size: 16px; }
        .logout { color: #f87171; text-decoration: none; font-weight: 700; font-size: 12px; background: rgba(248,113,113,0.1); padding: 6px 10px; border-radius: 8px; border: 1px solid rgba(248,113,113,0.3); }

        .nav-tabs { display: flex; gap: 6px; overflow-x: auto; padding-bottom: 5px; margin-bottom: 12px; }
        .tab-btn { background: #0f172a; color: var(--text-muted); border: 1px solid #334155; padding: 9px 14px; border-radius: 10px; cursor: pointer; font-weight: 700; font-size: 12px; white-space: nowrap; text-decoration: none; display: inline-flex; align-items: center; gap: 5px; }
        .tab-btn.active { background: var(--accent); color: #030712; border-color: var(--accent); font-weight: 800; }
        
        .tab-content { display: none; }
        .tab-content.active { display: block; }

        .stat-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; margin-bottom: 15px; }
        @media(min-width: 600px) { .stat-grid { grid-template-columns: repeat(4, 1fr); } }
        .stat-box { background: rgba(18, 24, 40, 0.8); border: 1px solid #334155; border-left: 4px solid var(--accent); padding: 12px; border-radius: 12px; text-align: left; box-shadow: 0 0 10px rgba(250,204,21,0.05); }
        .stat-box h4 { margin: 0; color: var(--accent); font-size: 16px; font-weight: 800; }
        .stat-box p { margin: 4px 0 0 0; color: var(--text-muted); font-size: 10px; text-transform: uppercase; font-weight: 700; }

        .card { background: rgba(18, 24, 40, 0.8); border: 1px solid #334155; padding: 15px; border-radius: 14px; margin-bottom: 14px; font-size: 13px; box-shadow: 0 4px 20px rgba(0,0,0,0.5); }
        h3 { color: var(--accent); margin-top: 0; font-size: 15px; border-bottom: 1px solid #334155; padding-bottom: 8px; }
        
        input, select, textarea { width: 100%; padding: 11px; margin-bottom: 10px; background: #030712; border: 1px solid #334155; border-radius: 10px; color: #fff; box-sizing: border-box; font-size: 13px; outline: none; }
        input:focus, select:focus { border-color: var(--accent); box-shadow: 0 0 8px rgba(250,204,21,0.3); }
        label { display: block; font-weight: 700; margin-bottom: 4px; font-size: 11px; color: #cbd5e1; text-transform: uppercase; }
        
        .btn-action { background: linear-gradient(135deg, var(--accent), #ca8a04); color: #030712; border: none; padding: 13px; border-radius: 10px; width: 100%; font-size: 14px; font-weight: 800; cursor: pointer; text-transform: uppercase; margin-top: 5px; transition: 0.2s; }
        .btn-action:active { transform: scale(0.98); }
        
        .whatsapp-btn { background: #25d366; color: #fff; padding: 8px 12px; border-radius: 8px; text-decoration: none; font-size: 11px; font-weight: 800; display: inline-flex; align-items: center; gap: 5px; margin-top: 6px; }
        .pdf-btn { background: #0284c7; color: #fff; padding: 8px 12px; border-radius: 8px; text-decoration: none; font-size: 11px; font-weight: 800; display: inline-flex; align-items: center; gap: 5px; margin-top: 6px; }
        .edit-btn { background: #d97706; color: #fff; padding: 8px 12px; border-radius: 8px; text-decoration: none; font-size: 11px; font-weight: 800; display: inline-flex; align-items: center; gap: 5px; margin-top: 6px; border: none; cursor: pointer; }
        
        .quick-chips { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 12px; }
        .chip { background: #1e293b; border: 1px solid #475569; color: #f8fafc; padding: 6px 10px; border-radius: 8px; font-size: 11px; cursor: pointer; font-weight: 700; }
        .chip:hover { border-color: var(--accent); color: var(--accent); }

        /* Yükleniyor Overlay */
        #loadingOverlay { display: none; position: fixed; top:0; left:0; width:100%; height:100%; background: rgba(3,7,18,0.85); z-index:9999; justify-content: center; align-items: center; flex-direction: column; color: var(--accent); font-weight: 800; font-size: 16px; }
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
    <div class="header-box">
        <div class="brand-title"><span class="brand-icon">🏍️</span> İZ MOTORSİKLET GARAJ</div>
        <a href="/cikis" class="logout">Çıkış Yap</a>
    </div>

    <div class="nav-tabs">
        <button class="tab-btn {% if aktif_tab == 'servis' %}active{% endif %}" onclick="switchTab('servisTab', this)">🛠️ Servis Formu</button>
        <button class="tab-btn {% if aktif_tab == 'araclar' %}active{% endif %}" onclick="switchTab('araclarTab', this)">🏍️ Aktif Araçlar</button>
        <button class="tab-btn {% if aktif_tab == 'gecmis' %}active{% endif %}" onclick="switchTab('gecmisTab', this)">🔍 Geçmiş & Borçlar</button>
        <button class="tab-btn {% if aktif_tab == 'stok' %}active{% endif %}" onclick="switchTab('stokTab', this)">📦 Stoklar</button>
        <button class="tab-btn {% if aktif_tab == 'randevu' %}active{% endif %}" onclick="switchTab('randevuTab', this)">📅 Randevular</button>
        <button class="tab-btn {% if aktif_tab == 'bakim' %}active{% endif %}" onclick="switchTab('bakimTab', this)">⏰ Bakım</button>
    </div>

    <div class="stat-grid">
        <div class="stat-box"><h4>{{ "%.2f"|format(toplam_ciro) }} TL</h4><p>Toplam Ciro</p></div>
        <div class="stat-box"><h4>{{ aktif_araclar|length }}</h4><p>Aktif Araç</p></div>
        <div class="stat-box"><h4>{{ stoklar|length }}</h4><p>Stok Çeşit</p></div>
        <div class="stat-box"><h4>{{ randevular|length }}</h4><p>Randevular</p></div>
    </div>

    <!-- 1. SERVİS FORMU -->
    <div id="servisTab" class="tab-content {% if aktif_tab == 'servis' %}active{% endif %}">
        <div class="card">
            <h3>⚡ Yeni Servis Formu Oluştur</h3>
            
            <div style="margin-bottom: 12px;">
                <label>Kayıtlı Araçtan Seç (Geçmiş Dahil Otomatik Doldur)</label>
                <select id="kayitliAracSec" onchange="aracBilgileriniDoldur()">
                    <option value="">-- Listeden Araç Seç (İsteğe Bağlı) --</option>
                    {% for ar in tum_araclar %}
                    <option value="{{ ar[1] }}" data-ad="{{ ar[2] }}" data-tel="{{ ar[3] }}" data-model="{{ ar[4] }}" data-km="{{ ar[5] }}">
                        {{ ar[1] }} - {{ ar[2] }} ({{ ar[4] }})
                    </option>
                    {% endfor %}
                </select>
            </div>

            <form action="/olustur" method="POST" enctype="multipart/form-data" onsubmit="showLoading()">
                <label>Dükkan Logosu (Zorunlu)</label><input type="file" name="logo" accept="image/*" required>
                <label>Hasar / Durum Fotoğrafı (İsteğe Bağlı)</label><input type="file" name="hasar_foto" accept="image/*">
                
                <label>Müşteri Ad Soyad</label><input type="text" id="musteri_ad" name="musteri_ad" placeholder="Örn: Ahmet Yılmaz" required>
                <label>Müşteri Telefon (WhatsApp)</label><input type="text" id="musteri_tel" name="musteri_tel" placeholder="Örn: 905320000000" required>
                <label>Motosiklet Plaka</label><input type="text" id="plaka" name="plaka" placeholder="Örn: 34 ABC 123" required>
                <label>Marka / Model</label><input type="text" id="model" name="model" placeholder="Örn: Honda Dio" required>
                <label>Kilometre (KM)</label><input type="text" id="km" name="km" placeholder="Örn: 15000" required>
                
                <label>Ödeme Durumu</label>
                <select name="odeme_durumu">
                    <option value="Borçlu / Veresiye" selected>🔴 Borçlu / Veresiye</option>
                    <option value="Parça Bekliyor">🟡 Parça Bekliyor</option>
                    <option value="Ödendi">🟢 Ödendi (Arşive Gider)</option>
                </select>

                <label style="margin-top: 15px;">Hızlı İşlem Seç:</label>
                <div class="quick-chips">
                    <div class="chip" onclick="islemEkle('Yağ Değişimi', 350)">🛢️ Yağ (350 TL)</div>
                    <div class="chip" onclick="islemEkle('Buji Değişimi', 200)">🔌 Buji (200 TL)</div>
                    <div class="chip" onclick="islemEkle('Balata Değişimi', 500)">🛑 Balata (500 TL)</div>
                    <div class="chip" onclick="islemEkle('Genel Bakım', 1000)">⚙️ Genel Bakım (1000 TL)</div>
                </div>

                <label>İşlem / Parça Adı</label><input type="text" id="islem_input" name="islem_ad[]" placeholder="Örn: Yağ Değişimi / Buji" required>
                <label>Tutar (TL)</label><input type="number" step="0.01" id="fiyat_input" name="fiyat[]" placeholder="Örn: 500" required>
                
                <button type="submit" class="btn-action">Formu Oluştur & Kaydet (PDF)</button>
            </form>
        </div>
    </div>

    <!-- 2. AKTİF ARAÇLAR -->
    <div id="araclarTab" class="tab-content {% if aktif_tab == 'araclar' %}active{% endif %}">
        <div class="card" style="border-left: 4px solid var(--accent);">
            <h3>➕ Doğrudan Servise Yeni Araç Ekle</h3>
            <form action="/hizli_arac_ekle" method="POST" onsubmit="showLoading()">
                <input type="text" name="plaka" placeholder="Plaka (Örn: 34 ABC)" required>
                <input type="text" name="musteri_ad" placeholder="Müşteri Ad Soyad" required>
                <input type="text" name="tel" placeholder="Telefon (90532...)" required>
                <input type="text" name="model" placeholder="Model (Örn: Honda Dio)" required>
                <input type="text" name="km" placeholder="KM (Örn: 12000)" required>
                <button type="submit" class="btn-action">HIZLI ARACI EKLE</button>
            </form>
        </div>

        <h3>Atölyedeki / Servisteki Aktif Araçlar</h3>
        {% if aktif_araclar %}
            {% for ts in aktif_araclar %}
            <div class="card" style="border-left: 4px solid {% if ts[10] == 'Borçlu / Veresiye' %}#f87171{% else %}#4ade80{% endif %};">
                <b>Plaka:</b> <span style="color:var(--accent); font-size:14px;">{{ ts[1] }}</span> | <b>Müşteri:</b> {{ ts[2] }} ({{ ts[3] }})<br>
                <b>Model / KM:</b> {{ ts[4] }} - {{ ts[5] }} KM | <b>Tarih:</b> {{ ts[6] }}<br>
                <b>Yapılanlar:</b> {{ ts[7] }} | <b>Tutar:</b> <span style="color:var(--accent); font-weight:800;">{{ "%.2f"|format(ts[8]) }} TL</span><br>
                
                <form action="/durum_guncelle" method="POST" style="margin-top: 10px; display:flex; gap:8px;" onsubmit="showLoading()">
                    <input type="hidden" name="servis_id" value="{{ ts[0] }}">
                    <div style="flex:1;">
                        <label style="font-size:9px;">Çalışma Durumu</label>
                        <select name="durum" onchange="this.form.submit()" style="margin:0; font-size:11px; padding:6px;">
                            <option value="Bekliyor" {% if ts[9] == 'Bekliyor' %}selected{% endif %}>Bekliyor</option>
                            <option value="Parça Bekliyor" {% if ts[9] == 'Parça Bekliyor' %}selected{% endif %}>Parça Bekliyor</option>
                            <option value="Hazır" {% if ts[9] == 'Hazır' %}selected{% endif %}>Hazır</option>
                            <option value="Teslime Hazır" {% if ts[9] == 'Teslime Hazır' %}selected{% endif %}>Teslime Hazır</option>
                        </select>
                    </div>
                    <div style="flex:1;">
                        <label style="font-size:9px;">Ödeme Durumu</label>
                        <select name="odeme_durumu" onchange="this.form.submit()" style="margin:0; font-size:11px; padding:6px;">
                            <option value="Borçlu / Veresiye" {% if ts[10] == 'Borçlu / Veresiye' %}selected{% endif %}>🔴 Borçlu</option>
                            <option value="Parça Bekliyor" {% if ts[10] == 'Parça Bekliyor' %}selected{% endif %}>🟡 Parça Bekliyor</option>
                            <option value="Ödendi" {% if ts[10] == 'Ödendi' %}selected{% endif %}>🟢 Ödendi</option>
                        </select>
                    </div>
                </form>

                <div style="margin-top: 8px; display: flex; gap: 6px; flex-wrap: wrap;">
                    <a href="https://wa.me/{{ ts[3] }}?text=Sayin%20{{ ts[2] }},%20Iz%20Motorsiklet%20servis%20ucretiniz%20{{ "%.2f"|format(ts[8]) }}%20TL." target="_blank" class="whatsapp-btn">💬 WhatsApp</a>
                    {% if ts[11] %}<a href="/pdf_indir/{{ ts[0] }}" class="pdf-btn">📄 PDF İndir</a>{% endif %}
                    <a href="/duzenle/{{ ts[0] }}" class="edit-btn">✏️ Düzenle</a>
                </div>
            </div>
            {% endfor %}
        {% else %}
            <p style="color: var(--text-muted); text-align: center;">Atölyede aktif araç bulunmuyor.</p>
        {% endif %}
    </div>

    <!-- 3. GEÇMİŞ & BORÇLAR -->
    <div id="gecmisTab" class="tab-content {% if aktif_tab == 'gecmis' %}active{% endif %}">
        <form method="GET" action="/" onsubmit="showLoading()">
            <input type="hidden" name="tab" value="gecmis">
            <label>Plaka veya Müşteri Adı ile Sorgula</label>
            <input type="text" name="sorgu_plaka" placeholder="Örn: 34 RAP 619" value="{{ sorgu_plaka or '' }}">
            <button type="submit" class="btn-action">HIZLI ARAMA YAP</button>
        </form>
        <hr style="border:0; border-top:1px solid #334155; margin: 15px 0;">
        <h3 style="color:var(--accent);">Geçmiş Servisler ve Borçlu Defteri</h3>
        {% if kayitlar %}
            {% for k in kayitlar %}
            <div class="card" style="border-left: 4px solid {% if k[10] == 'Ödendi' %}#4ade80{% else %}#f87171{% endif %};">
                <b>Plaka:</b> <span style="color:var(--accent);">{{ k[1] }}</span> | <b>Tarih:</b> {{ k[6] }}<br>
                <b>Müşteri:</b> {{ k[2] }} ({{ k[3] }})<br>
                <b>İşlemler:</b> {{ k[7] }}<br>
                <b>Toplam Tutar:</b> <span style="color:var(--accent);">{{ "%.2f"|format(k[8]) }} TL</span> | <b>Ödeme:</b> <span style="color:{% if k[10] == 'Ödendi' %}#4ade80{% else %}#f87171{% endif %}; font-weight:800;">{{ k[10] }}</span>
                
                <div style="margin-top: 8px; display: flex; gap: 6px; flex-wrap: wrap;">
                    {% if k[11] %}<a href="/pdf_indir/{{ k[0] }}" class="pdf-btn">📄 Formu İndir</a>{% endif %}
                    <a href="/duzenle/{{ k[0] }}" class="edit-btn">✏️ Düzenle / Not Ekle</a>
                </div>
            </div>
            {% endfor %}
        {% else %}
            <p style="color: var(--text-muted); text-align: center;">Kayıt bulunamadı.</p>
        {% endif %}
    </div>

    <!-- 4. STOKLAR -->
    <div id="stokTab" class="tab-content {% if aktif_tab == 'stok' %}active{% endif %}">
        <h3>Parça / Ürün Stok Yönetimi</h3>
        <form method="POST" action="/stok_ekle" onsubmit="showLoading()">
            <label>Parça Adı</label><input type="text" name="parca_adi" placeholder="Örn: Buji NGK" required>
            <label>Stok Adedi</label><input type="number" name="adet" placeholder="Adet" required>
            <label>Birim Fiyat (TL)</label><input type="number" step="0.01" name="fiyat" placeholder="Fiyat" required>
            <button type="submit" class="btn-action">STOK EKLE</button>
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

    <!-- 5. RANDEVULAR -->
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
            <div style="margin-top:8px;"><a href="https://wa.me/{{ r[2] }}?text=Randevu%20hatirlatmasi" target="_blank" class="whatsapp-btn">💬 WhatsApp Hatırlat</a></div>
        </div>
        {% endfor %}
    </div>

    <!-- 6. BAKIM -->
    <div id="bakimTab" class="tab-content {% if aktif_tab == 'bakim' %}active{% endif %}">
        <h3 style="color:var(--accent);">Akıllı Bakım Hatırlatıcı</h3>
        <p style="color:var(--text-muted); font-size:12px;">Daha önce servis kaydı açılmış motorlar için periyodik bakım hatırlatması gönderebilirsiniz.</p>
        {% if tum_araclar %}
            {% for ts in tum_araclar %}
            <div class="card" style="border-left: 4px solid var(--accent);">
                <b>Plaka:</b> <span style="color:var(--accent);">{{ ts[1] }}</span> | <b>Müşteri:</b> {{ ts[2] }} ({{ ts[3] }})<br>
                <b>Model / KM:</b> {{ ts[4] }} - {{ ts[5] }} KM<br>
                <div style="margin-top:10px;">
                    <a href="https://wa.me/{{ ts[3] }}?text=Sayin%20{{ ts[2] }},%20Iz%20Motorsiklet%20periyodik%20bakim%20vaktiniz%20yaklasmistir.%20Bekliyoruz." target="_blank" class="whatsapp-btn">💬 Bakım Hatırlatması Gönder</a>
                </div>
            </div>
            {% endfor %}
        {% else %}
            <p style="color: var(--text-muted); text-align: center;">Kayıtlı araç bulunmuyor.</p>
        {% endif %}
    </div>
</div>

<script>
function switchTab(tabId, btn) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
    document.getElementById(tabId).classList.add('active');
    btn.classList.add('active');
}

function showLoading() {
    document.getElementById('loadingOverlay').style.display = 'flex';
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

function islemEkle(isim, fiyat) {
    document.getElementById('islem_input').value = isim;
    document.getElementById('fiyat_input').value = fiyat;
}
</script>
</body>
</html>
"""

# --- KAYIT DÜZENLEME HTML SAYFASI ---
HTML_DUZENLE = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Servis Kaydını Düzenle</title>
    <style>
        body { font-family: 'Inter', sans-serif; background-color: #050811; color: #f8fafc; padding: 20px; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }
        .box { background: rgba(11, 15, 25, 0.95); border: 1px solid #334155; padding: 25px; border-radius: 16px; width: 100%; max-width: 450px; box-shadow: 0 20px 40px rgba(0,0,0,0.8); }
        h3 { color: #facc15; margin-top: 0; border-bottom: 1px solid #334155; padding-bottom: 8px; }
        input, select, textarea { width: 100%; padding: 12px; margin-bottom: 12px; background: #030712; border: 1px solid #334155; border-radius: 10px; color: #fff; box-sizing: border-box; font-size: 13px; }
        label { display: block; font-weight: 700; margin-bottom: 4px; font-size: 11px; color: #cbd5e1; text-transform: uppercase; }
        .btn { background: linear-gradient(135deg, #facc15, #ca8a04); color: #030712; border: none; padding: 12px; border-radius: 10px; width: 100%; font-weight: 800; cursor: pointer; text-transform: uppercase; margin-top: 5px; }
        .back { display: block; text-align: center; margin-top: 15px; color: #94a3b8; text-decoration: none; font-size: 12px; font-weight: 700; }
    </style>
</head>
<body>
<div class="box">
    <h3>✏️ Servis Kaydını Düzenle</h3>
    <form method="POST">
        <label>Müşteri Ad Soyad</label><input type="text" name="musteri_ad" value="{{ kayit[2] }}" required>
        <label>Telefon</label><input type="text" name="musteri_tel" value="{{ kayit[3] }}" required>
        <label>Plaka</label><input type="text" name="plaka" value="{{ kayit[1] }}" required>
        <label>Model / KM</label><input type="text" name="model" value="{{ kayit[4] }}" required>
        <label>Yapılan İşlem / Notlar</label><textarea name="detaylar" rows="3" required>{{ kayit[7] }}</textarea>
        <label>Toplam Tutar (TL)</label><input type="number" step="0.01" name="toplam_tutar" value="{{ kayit[8] }}" required>
        <label>Ödeme Durumu</label>
        <select name="odeme_durumu">
            <option value="Borçlu / Veresiye" {% if kayit[10] == 'Borçlu / Veresiye' %}selected{% endif %}>🔴 Borçlu / Veresiye</option>
            <option value="Parça Bekliyor" {% if kayit[10] == 'Parça Bekliyor' %}selected{% endif %}>🟡 Parça Bekliyor</option>
            <option value="Ödendi" {% if kayit[10] == 'Ödendi' %}selected{% endif %}>🟢 Ödendi</option>
        </select>
        <button type="submit" class="btn">Değişiklikleri Kaydet</button>
    </form>
    <a href="/" class="back">← Panele Geri Dön</a>
</div>
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

    aktif_tab = request.args.get('tab', 'servis')
    sorgu_plaka = request.args.get('sorgu_plaka', '').strip()
    
    if sorgu_plaka:
        cursor.execute("SELECT * FROM servisler WHERE (plaka ILIKE %s OR musteri_ad ILIKE %s) ORDER BY id DESC", ('%' + sorgu_plaka + '%', '%' + sorgu_plaka + '%'))
    else:
        cursor.execute("SELECT * FROM servisler ORDER BY id DESC")
    kayitlar = cursor.fetchall()

    cursor.execute("SELECT * FROM servisler WHERE odeme_durumu != 'Ödendi' OR odeme_durumu IS NULL ORDER BY id DESC")
    aktif_araclar = cursor.fetchall()

    cursor.execute("SELECT * FROM servisler ORDER BY id DESC")
    tum_araclar = cursor.fetchall()

    cursor.execute("SELECT * FROM stok")
    stoklar = cursor.fetchall()
    cursor.execute("SELECT * FROM randevular ORDER BY id DESC")
    randevular = cursor.fetchall()

    cursor.execute("SELECT SUM(toplam_tutar) FROM servisler")
    res = cursor.fetchone()
    toplam_ciro = res[0] if res and res[0] else 0.0

    cursor.close()
    conn.close()
    return render_template_string(HTML_PANEL, kayitlar=kayitlar, sorgu_plaka=sorgu_plaka, stoklar=stoklar, randevular=randevular, aktif_araclar=aktif_araclar, tum_araclar=tum_araclar, toplam_ciro=toplam_ciro, aktif_tab=aktif_tab)

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
        tutar = float(request.form.get('toplam_tutar', 0))
        odeme = request.form.get('odeme_durumu')
        
        cursor.execute("UPDATE servisler SET musteri_ad=%s, musteri_tel=%s, plaka=%s, model=%s, detaylar=%s, toplam_tutar=%s, odeme_durumu=%s WHERE id=%s",
                       (ad, tel, plaka, model, detaylar, tutar, odeme, kayit_id))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('index', tab='gecmis'))

    cursor.execute("SELECT * FROM servisler WHERE id = %s", (kayit_id,))
    kayit = cursor.fetchone()
    cursor.close()
    conn.close()
    return render_template_string(HTML_DUZENLE, kayit=kayit)

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

@app.route('/hizli_arac_ekle', methods=['POST'])
def hizli_arac_ekle():
    if not session.get('giris'): return redirect(url_for('index'))
    plaka, ad, tel, model, km = request.form.get('plaka'), request.form.get('musteri_ad'), request.form.get('tel'), request.form.get('model'), request.form.get('km')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO servisler (plaka, musteri_ad, musteri_tel, model, km, tarih, detaylar, toplam_tutar, durum, odeme_durumu) VALUES (%s, %s, %s, %s, %s, %s, %s, 0.0, 'Bekliyor', 'Borçlu / Veresiye')", 
                   (plaka, ad, tel, model, km, datetime.date.today().strftime("%d.%m.%Y"), "Hızlı Kayıt"))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('index', tab='araclar'))

@app.route('/durum_guncelle', methods=['POST'])
def durum_guncelle():
    if not session.get('giris'): return redirect(url_for('index'))
    conn = get_db_connection()
    cursor = conn.cursor()
    durum = request.form.get('durum')
    odeme = request.form.get('odeme_durumu')
    servis_id = request.form.get('servis_id')
    
    if durum:
        cursor.execute("UPDATE servisler SET durum = %s WHERE id = %s", (durum, servis_id))
    if odeme:
        cursor.execute("UPDATE servisler SET odeme_durumu = %s WHERE id = %s", (odeme, servis_id))
        
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('index', tab='araclar'))

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
    await update.message.reply_text("Selam kanka! İz Motorsiklet Supabase Botuna hoş geldin:\nPlaka geçmişi için: `/plaka 34` yazabilirsin.", reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))

async def telegram_plaka_sorgu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text.startswith("/plaka"):
        parcalar = text.split(maxsplit=1)
        if len(parcalar) < 2:
            await update.message.reply_text("Kanka plaka yazmadın! Örnek: `/plaka 34RAP`", parse_mode="Markdown")
            return
        sorgu = parcalar[1].strip()
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT plaka, musteri_ad, musteri_tel, tarih, detaylar, toplam_tutar, odeme_durumu FROM servisler WHERE plaka ILIKE %s ORDER BY id DESC", ('%' + sorgu + '%',))
        sonuclar = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if not sonuclar:
            await update.message.reply_text(f"🔍 `{sorgu}` plakasına ait geçmiş kayıt bulunamadı.", parse_mode="Markdown")
            return
            
        msg = f"🔍 **Plaka Sorgu Sonucu ({sorgu}):**\n\n"
        for s in sonuclar:
            msg += f"🏍️ **Plaka:** {s[0]}\n👤 **Müşteri:** {s[1]} ({s[2]})\n📅 **Tarih:** {s[3]}\n🔧 **İşlem:** {s[4]}\n💰 **Tutar:** {s[5]:.2f} TL\n📌 **Durum:** {s[6]}\n-------------------\n"
        await update.message.reply_text(msg, parse_mode="Markdown")

async def telegram_mesaj(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text.startswith("/plaka"):
        await telegram_plaka_sorgu(update, context)
        return
        
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
    elif text == "🏍️ Aktif Araçlar":
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT plaka, musteri_ad, model, odeme_durumu FROM servisler WHERE odeme_durumu != 'Ödendi' ORDER BY id DESC")
        araclar = cursor.fetchall()
        cursor.close()
        conn.close()
        msg = "🏍️ **Atölyedeki Aktif Araçlar:**\n\n"
        for a in araclar:
            msg += f"- Plaka: {a[0]} | {a[1]} ({a[2]}) | Durum: {a[3]}\n"
        await update.message.reply_text(msg or "Aktif araç yok.", parse_mode="Markdown")
    else:
        await update.message.reply_text("Kanka menüden seçim yapabilir ya da `/plaka 34` yazarak araç sorgulayabilirsin.")

def run_telegram_bot():
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN: return
    try:
        bot_app = Application.builder().token(TOKEN).drop_pending_updates(True).build()
        bot_app.add_handler(CommandHandler("start", start))
        bot_app.add_handler(CommandHandler("plaka", telegram_plaka_sorgu))
        bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, telegram_mesaj))
        bot_app.run_polling(stop_signals=None)
    except Exception as e:
        print("Telegram bot hata:", e)

if __name__ == '__main__':
    threading.Thread(target=run_telegram_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
