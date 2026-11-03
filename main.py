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
app.secret_key = "iz_motor_gizli_anahtar_erp_v7"

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

# --- HTML / CAFCAFLI ARAYÜZ ---
HTML_LOGIN = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>İz Motorsiklet - Giriş</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0f172a; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; color: #f8fafc; }
        .login-box { background: rgba(30, 41, 59, 0.85); backdrop-filter: blur(10px); padding: 40px; border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); width: 100%; max-width: 350px; text-align: center; border: 1px solid rgba(255,215,0,0.3); }
        h2 { color: #facc15; margin-bottom: 25px; letter-spacing: 1px; text-transform: uppercase; font-size: 22px; }
        input { width: 100%; padding: 14px; margin-bottom: 20px; background: #0f172a; border: 1px solid #475569; border-radius: 8px; color: #fff; box-sizing: border-box; font-size: 16px; outline: none; transition: 0.3s; }
        input:focus { border-color: #facc15; box-shadow: 0 0 10px rgba(250,204,21,0.4); }
        button { background: linear-gradient(135deg, #facc15, #ca8a04); color: #0f172a; border: none; padding: 14px; border-radius: 8px; width: 100%; font-size: 16px; font-weight: bold; cursor: pointer; transition: 0.3s; }
        button:hover { transform: translateY(-2px); box-shadow: 0 5px 15px rgba(250,204,21,0.4); }
        .error { color: #f87171; margin-bottom: 15px; font-size: 14px; font-weight: bold; }
    </style>
</head>
<body>
<div class="login-box">
    <h2>İZ MOTORSİKLET</h2>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
    <form method="POST">
        <input type="password" name="sifre" placeholder="🔒 Yönetici Şifresi..." required autofocus>
        <button type="submit">Sisteme Giriş Yap</button>
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
    <title>İz Motorsiklet ERP Paneli</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0b0f19; margin: 0; padding: 15px; color: #f1f5f9; }
        .container { max-width: 720px; margin: 0 auto; background: #111827; padding: 25px; border-radius: 16px; box-shadow: 0 10px 40px rgba(0,0,0,0.6); border: 1px solid rgba(250,204,21,0.2); }
        h2 { text-align: center; color: #facc15; margin-bottom: 20px; font-size: 24px; text-transform: uppercase; letter-spacing: 1px; text-shadow: 0 0 10px rgba(250,204,21,0.3); }
        
        .logout { text-align: right; margin-bottom: 10px; }
        .logout a { color: #f87171; text-decoration: none; font-size: 13px; font-weight: bold; padding: 5px 10px; background: rgba(248,113,113,0.1); border-radius: 6px; border: 1px solid rgba(248,113,113,0.3); }

        .tabs { display: flex; flex-wrap: wrap; justify-content: center; gap: 6px; margin-bottom: 25px; }
        .tab-btn { background: #1f2937; color: #9ca3af; border: 1px solid #374151; padding: 9px 12px; border-radius: 8px; cursor: pointer; font-weight: bold; font-size: 12px; transition: 0.3s; }
        .tab-btn.active { background: linear-gradient(135deg, #facc15, #ca8a04); color: #0b0f19; border-color: #facc15; box-shadow: 0 0 15px rgba(250,204,21,0.4); }
        .tab-content { display: none; }
        .tab-content.active { display: block; animation: fadeIn 0.4s ease-in-out; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }

        .form-group { margin-bottom: 15px; }
        label { display: block; font-weight: bold; margin-bottom: 6px; font-size: 13px; color: #cbd5e1; }
        input, textarea, select { width: 100%; padding: 12px; background: #0f172a; border: 1px solid #374151; border-radius: 8px; color: #fff; box-sizing: border-box; font-size: 14px; transition: 0.3s; outline: none; }
        input:focus, textarea:focus, select:focus { border-color: #facc15; box-shadow: 0 0 8px rgba(250,204,21,0.3); }
        
        .item-row { display: flex; gap: 6px; margin-bottom: 10px; align-items: center; background: #1e293b; padding: 8px; border-radius: 8px; border: 1px solid #334155; }
        .item-row input.name-input { flex: 2; }
        .item-row select { flex: 1.5; background: #0f172a; font-size: 12px; }
        .item-row input.small { flex: 0.8; }
        
        .btn-add { background: #0d9488; color: #fff; border: none; padding: 10px; border-radius: 8px; cursor: pointer; font-weight: bold; width: 100%; margin-bottom: 15px; transition: 0.3s; }
        .btn-add:hover { background: #0f766e; }
        
        .btn-remove { background: #dc2626; color: #fff; border: none; padding: 8px 10px; border-radius: 6px; cursor: pointer; font-weight: bold; }
        
        button[type="submit"], .btn-action { background: linear-gradient(135deg, #facc15, #ca8a04); color: #0b0f19; border: none; padding: 14px; border-radius: 8px; cursor: pointer; width: 100%; font-size: 15px; font-weight: bold; margin-top: 15px; transition: 0.3s; box-shadow: 0 4px 15px rgba(250,204,21,0.3); }
        button[type="submit"]:hover, .btn-action:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(250,204,21,0.5); }
        button:disabled { opacity: 0.6; cursor: not-allowed; }

        .card { background: #1e293b; border: 1px solid #334155; padding: 14px; border-radius: 10px; margin-bottom: 12px; font-size: 14px; box-shadow: 0 4px 6px rgba(0,0,0,0.2); }
        .stats-box { background: linear-gradient(135deg, #1e293b, #0f172a); border: 1px solid #facc15; padding: 20px; border-radius: 12px; text-align: center; margin-bottom: 20px; box-shadow: 0 0 15px rgba(250,204,21,0.2); }
        .whatsapp-btn { display: inline-block; margin-top: 8px; background: #25d366; color: #fff; padding: 6px 12px; border-radius: 6px; text-decoration: none; font-size: 12px; font-weight: bold; box-shadow: 0 3px 10px rgba(37,211,102,0.3); }
        .alert-box { background: rgba(250,204,21,0.1); border: 1px solid #facc15; padding: 12px; border-radius: 8px; color: #facc15; margin-bottom: 15px; font-weight: bold; text-align: center; display: none; }
    </style>
</head>
<body>
<div class="container">
    <div class="logout"><a href="/cikis">Çıkış Yap</a></div>
    <h2>İZ MOTORSİKLET YÖNETİM</h2>

    <div id="duplicateAlert" class="alert-box">⚠️ Bu servis formu az önce kaydedildi! Tekrar işlem yapılmadı.</div>

    <!-- SEKMELER -->
    <div class="tabs">
        <button class="tab-btn active" onclick="switchTab('formTab', this)">Servis Formu</button>
        <button class="tab-btn" onclick="switchTab('araclarTab', this)">Araçlar (Durum)</button>
        <button class="tab-btn" onclick="switchTab('historyTab', this)">Müşteri & Plaka</button>
        <button class="tab-btn" onclick="switchTab('stockTab', this)">Stok Takibi</button>
        <button class="tab-btn" onclick="switchTab('financeTab', this)">Ciro Raporu</button>
        <button class="tab-btn" onclick="switchTab('reminderTab', this)">Bakım Hatırlat</button>
    </div>

    <!-- 1. SEKME: SERVİS FORMU -->
    <div id="formTab" class="tab-content active">
        <form id="serviceForm" action="/olustur" method="POST" enctype="multipart/form-data" onsubmit="handleFormSubmit(event)">
            <div class="form-group">
                <label>Dükkan Logosu <span style="color:#facc15;">(Zorunlu)</span></label>
                <input type="file" name="logo" accept="image/*" required>
            </div>
            <div class="form-group">
                <label>Hasar / Durum Fotoğrafı <span style="color:#9ca3af; font-weight:normal;">(İsteğe Bağlı)</span></label>
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

            <hr style="margin: 20px 0; border: 0; border-top: 1px solid #374151;">
            
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
        <p style="font-size: 13px; color: #9ca3af; margin-bottom: 15px;">Motorların anlık servis durumlarını buradan güncelleyebilirsin:</p>
        {% if tum_servisler %}
            {% for ts in tum_servisler %}
            <div class="card">
                <b>Plaka:</b> <span style="color:#facc15;">{{ ts[1] }}</span> | <b>Müşteri:</b> {{ ts[2] }} ({{ ts[3] }})<br>
                <b>Model / KM:</b> {{ ts[4] }} - {{ ts[5] }} | <b>Tarih:</b> {{ ts[6] }}<br>
                <b>Yapılanlar:</b> {{ ts[7] }}<br>
                <hr style="border:0; border-top:1px solid #334155; margin: 10px 0;">
                <form action="/durum_guncelle" method="POST" style="display: flex; gap: 8px; align-items: center;">
                    <input type="hidden" name="servis_id" value="{{ ts[0] }}">
                    <label style="font-size:12px; margin:0;">Durum:</label>
                    <select name="durum" style="padding: 6px; font-size: 12px; background: #0f172a;" onchange="this.form.submit()">
                        <option value="Bekliyor" {% if ts[9] == 'Bekliyor' %}selected{% endif %}>Bekliyor</option>
                        <option value="İşlemde" {% if ts[9] == 'İşlemde' %}selected{% endif %}>İşlemde</option>
                        <option value="Hazır" {% if ts[9] == 'Hazır' %}selected{% endif %}>Hazır</option>
                        <option value="Teslime Hazır" {% if ts[9] == 'Teslime Hazır' %}selected{% endif %}>Teslime Hazır</option>
                        <option value="Parça Bekliyor" {% if ts[9] == 'Parça Bekliyor' %}selected{% endif %}>Parça Bekliyor</option>
                    </select>
                </form>
            </div>
            {% endfor %}
        {% else %}
            <p style="color: #9ca3af; text-align: center;">Kayıtlı aktif araç bulunmuyor.</p>
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
        <hr style="margin: 20px 0; border: 0; border-top: 1px solid #374151;">
        <h3>Arama Sonuçları / Geçmiş</h3>
        {% if kayitlar %}
            {% for k in kayitlar %}
            <div class="card">
                <b>Plaka:</b> {{ k[1] }} | <b>Tarih:</b> {{ k[6] }}<br>
                <b>Müşteri:</b> {{ k[2] }} ({{ k[3] }})<br>
                <b>Model / KM:</b> {{ k[4] }} - {{ k[5] }}<br>
                <b>Yapılanlar:</b> {{ k[7] }}<br>
                <b>Toplam Tutar:</b> <span style="color: #facc15; font-weight: bold;">{{ "%.2f"|format(k[8]) }} TL</span><br>
                <a href="https://wa.me/{{ k[3] }}?text=Sayin%20{{ k[2] }},%20Iz%20Motorsiklet%20servis%20formunuz%20hazirdir.%20Iyi%20gunler%20dileriz." target="_blank" class="whatsapp-btn">💬 WhatsApp Mesajı Gönder</a>
            </div>
            {% endfor %}
        {% else %}
            <p style="color: #9ca3af; text-align: center;">Kayıt bulunamadı.</p>
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
        <hr style="margin: 20px 0; border: 0; border-top: 1px solid #374151;">
        <h4>Mevcut Stoklar</h4>
        {% if stoklar %}
            {% for s in stoklar %}
            <div class="card">
                <b>{{ s[1] }}</b> - Adet: <span style="color: {% if s[2] < 3 %}#f87171{% else %}#4ade80{% endif %}; font-weight:bold;">{{ s[2] }}</span> | Fiyat: {{ "%.2f"|format(s[3]) }} TL
            </div>
            {% endfor %}
        {% else %}
            <p style="color: #9ca3af; text-align: center;">Stokta ürün bulunmuyor.</p>
        {% endif %}
    </div>

    <!-- CİRO / FİNANS RAPORU -->
    <div id="financeTab" class="tab-content">
        <h3>Finansal Özet ve Ciro</h3>
        <div class="stats-box">
            <h2 style="color: #facc15; margin: 0; font-size: 28px;">{{ "%.2f"|format(toplam_ciro) }} TL</h2>
            <p style="margin: 5px 0 0 0; font-weight: bold; color: #94a3b8;">Toplam Servis Cirosu</p>
        </div>
        <h4>Son Yapılan İşlemler</h4>
        {% if tum_servisler %}
            {% for ts in tum_servisler[:10] %}
            <div class="card">
                <b>{{ ts[1] }}</b> - {{ ts[6] }} : <span style="color: #facc15; font-weight: bold;">{{ "%.2f"|format(ts[8]) }} TL</span>
            </div>
            {% endfor %}
        {% endif %}
    </div>

    <!-- AKILLI BAKIM HATIRLATMA -->
    <div id="reminderTab" class="tab-content">
        <h3>Akıllı Bakım Hatırlatıcı</h3>
        <p style="font-size: 13px; color: #9ca3af; margin-bottom: 15px;">Daha önce gelen motorların üzerinden geçen süreler:</p>
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
            <p style="color: #9ca3af; text-align: center;">Kayıtlı bakım geçmişi bulunmuyor.</p>
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
else if(tab === 'finance') switchTab('financeTab', document.querySelectorAll('.tab-btn')[4]);
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
        
    return render_template_string(HTML_PANEL, kayitlar=kayitlar, sorgu_plaka=sorgu_plaka, stoklar=stoklar, tum_servisler=tum_servisler, toplam_ciro=toplam_ciro, bakim_listesi=bakim_listesi)

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


# --- TELEGRAM BOTU ---
SIFRE_DURUMU = {}
STOK_EKLE_AD = range(1, 4) # Stok ekleme conversation adımları için
LOGO_AL, HASAR_AL, MUSTERI_AD, MUSTERI_TEL, ARAÇ_PLAKA, ARAÇ_MODEL, ARAÇ_KM, ISLEM_EKLE, ISLEM_FIYAT, ISLEM_ADET, ISCILIK, NOTLAR = range(100, 112)
STOK_AD, STOK_ADET, STOK_FIYAT = range(200, 203)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    SIFRE_DURUMU[user_id] = False
    await update.message.reply_text("Selam kanka! İz Motorsiklet Botuna hoş geldin.\nDevam etmek için önce **yönetici şifresini** gir kanka:")

async def sifre_kontrol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    if SIFRE_DURUMU.get(user_id, False): return
    if text == SIFRE:
        SIFRE_DURUMU[user_id] = True
        keyboard = [
            ["🛠️ Servis Formu Oluştur"],
            ["🏍️ Araçlar", "📦 Stok Ekle"],
            ["💰 Ciro Raporu", "📦 Stok Listesi"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("Şifre doğru kanka! Aşağıdaki butonlardan yapmak istediğin işlemi seçebilirsin:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("Hatalı şifre kanka! Tekrar dene:")

# Buton Yönlendiricileri
async def ana_menu_yoneticisi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not SIFRE_DURUMU.get(user_id, False):
        await update.message.reply_text("Önce şifreyi girmen gerekiyor kanka! /start yaz.")
        return
    
    text = update.message.text
    if text == "🛠️ Servis Formu Oluştur":
        # /yeni_servis komutunu tetikler gibi akışı başlatıyoruz
        return await yeni_servis_baslat(update, context)
    elif text == "🏍️ Araçlar":
        return await bot_araclar(update, context)
    elif text == "📦 Stok Ekle":
        await update.message.reply_text("Eklenecek **Parça Adını** yaz kanka:", reply_markup=ReplyKeyboardRemove())
        return STOK_AD
    elif text == "💰 Ciro Raporu":
        return await bot_ciro(update, context)
    elif text == "📦 Stok Listesi":
        return await bot_stok(update, context)

# --- STOK EKLEME CONVERSATION ---
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
            ["🛠️ Servis Formu Oluştur"],
            ["🏍️ Araçlar", "📦 Stok Ekle"],
            ["💰 Ciro Raporu", "📦 Stok Listesi"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(f"✅ Başarıyla eklendi kanka!\n- **{parca}**: {adet} adet ({fiyat} TL)", parse_mode="Markdown", reply_markup=reply_markup)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Geçerli bir fiyat gir kanka:")
        return STOK_FIYAT

# --- ARAÇLAR LİSTESİ (BOT) ---
async def bot_araclar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('iz_motor_servis.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT id, plaka, musteri_ad, model, durum FROM servisler ORDER BY id DESC LIMIT 5")
    araclar = cursor.fetchall()
    conn.close()

    if not araclar:
        await update.message.reply_text("Atölyede kayıtlı araç bulunmuyor kanka.")
        return

    for a in araclar:
        a_id, plaka, musteri, model, durum = a
        keyboard = [
            [
                InlineKeyboardButton("Bekliyor", callback_data=f"durum_{a_id}_Bekliyor"),
                InlineKeyboardButton("İşlemde", callback_data=f"durum_{a_id}_İşlemde"),
                InlineKeyboardButton("Hazır", callback_data=f"durum_{a_id}_Hazır")
            ],
            [
                InlineKeyboardButton("Teslime Hazır", callback_data=f"durum_{a_id}_Teslime Hazır"),
                InlineKeyboardButton("Parça Bekliyor", callback_data=f"durum_{a_id}_Parça Bekliyor")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"🏍️ **Plaka:** {plaka}\n"
            f"👤 **Müşteri:** {musteri}\n"
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

async def bot_ciro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('iz_motor_servis.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(toplam_tutar) FROM servisler")
    res = cursor.fetchone()
    toplam = res[0] if res and res[0] else 0.0
    conn.close()
    await update.message.reply_text(f"💰 **Toplam Servis Cirosu:** `{toplam:.2f} TL`", parse_mode="Markdown")

# --- SERVİS FORMU OLUŞTURMA AKIŞI ---
async def yeni_servis_baslat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['islemler'] = []
    context.user_data['hasar_path'] = None
    await update.message.reply_text("1️⃣ Önce dükkanın **logosunu** fotoğraf olarak gönder kanka (Zorunlu):", reply_markup=ReplyKeyboardRemove())
    return LOGO_AL

async def logo_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_file = await update.message.photo[-1].get_file()
    logo_path = f"temp_logo_tg_{update.effective_user.id}.jpg"
    await photo_file.download_to_drive(logo_path)
    context.user_data['logo_path'] = logo_path
    
    keyboard = [['Fotoğraf Yok / Geç']]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Logo alındı! Şimdi varsa **hasar / durum fotoğrafını** gönder kanka (İsteğe bağlı, geçebilirsin):", reply_markup=reply_markup)
    return HASAR_AL

async def logo_uyari(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Kanka yazı değil, **logo fotoğrafı** göndermen gerekiyor:")
    return LOGO_AL

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
    await update.message.reply_text("Tamamdir. Şimdi **Müşteri Adı ve Soyadını** gir kanka:", reply_markup=ReplyKeyboardRemove())
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
    ''', (plaka, context.user_data['musteri_ad'], context.user_data['musteri_tel'], context.user_data['model'], context.user_data['km'], tarih_str, islem_str, genel_toplam))
    conn.commit()
    conn.close()

    pdf_olustur(pdf_path, context.user_data, logo_yolu, hasar_yolu)
    
    with open(pdf_path, 'rb') as doc:
        keyboard = [
            ["🛠️ Servis Formu Oluştur"],
            ["🏍️ Araçlar", "📦 Stok Ekle"],
            ["💰 Ciro Raporu", "📦 Stok Listesi"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_document(document=doc, caption="İşte servis formu kanka!", reply_markup=reply_markup)
        
    if os.path.exists(pdf_path): os.remove(pdf_path)
    if logo_yolu and os.path.exists(logo_yolu): os.remove(logo_yolu)
    if hasar_yolu and os.path.exists(hasar_yolu): os.remove(hasar_yolu)
        
    return ConversationHandler.END

async def iptal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logo_yolu = context.user_data.get('logo_path')
    hasar_yolu = context.user_data.get('hasar_path')
    if logo_yolu and os.path.exists(logo_yolu): os.remove(logo_yolu)
    if hasar_yolu and os.path.exists(hasar_yolu): os.remove(hasar_yolu)
    
    keyboard = [
        ["🛠️ Servis Formu Oluştur"],
        ["🏍️ Araçlar", "📦 Stok Ekle"],
        ["💰 Ciro Raporu", "📦 Stok Listesi"]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text("İşlem iptal edildi kanka.", reply_markup=reply_markup)
    return ConversationHandler.END

def run_telegram_bot():
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN: return
    bot_app = Application.builder().token(TOKEN).build()

    # Stok Ekleme Konuşması
    stok_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^📦 Stok Ekle$'), lambda u, c: (u.message.reply_text("Eklenecek **Parça Adını** yaz kanka:", reply_markup=ReplyKeyboardRemove()), STOK_AD)[1])],
        states={
            STOK_AD: [MessageHandler(filters.TEXT & ~filters.COMMAND, stok_ad_al)],
            STOK_ADET: [MessageHandler(filters.TEXT & ~filters.COMMAND, stok_adet_al)],
            STOK_FIYAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, stok_fiyat_al)],
        },
        fallbacks=[CommandHandler('iptal', iptal)]
    )

    # Servis Formu Konuşması
    servis_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^🛠️ Servis Formu Oluştur$'), yeni_servis_baslat)],
        states={
            LOGO_AL: [MessageHandler(filters.PHOTO, logo_al), MessageHandler(filters.TEXT & ~filters.COMMAND, logo_uyari)],
            HASAR_AL: [MessageHandler(filters.PHOTO, hasar_al), MessageHandler(filters.Regex(r'^Fotoğraf Yok / Geç$'), hasar_gec)],
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

    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(stok_conv)
    bot_app.add_handler(servis_conv)
    bot_app.add_handler(CallbackQueryHandler(durum_degistir_callback, pattern="^durum_"))
    bot_app.add_handler(MessageHandler(filters.Regex('^🏍️ Araçlar$'), bot_araclar))
    bot_app.add_handler(MessageHandler(filters.Regex('^📦 Stok Listesi$'), bot_stok))
    bot_app.add_handler(MessageHandler(filters.Regex('^💰 Ciro Raporu$'), bot_ciro))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, sifre_kontrol))

    bot_app.run_polling(stop_signals=None)

if __name__ == '__main__':
    threading.Thread(target=run_telegram_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
