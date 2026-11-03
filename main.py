import os
import datetime
import sqlite3
import threading
import asyncio
from flask import Flask, render_template_string, request, send_file, session, redirect, url_for
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    filters, ConversationHandler, ContextTypes
)
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

app = Flask(__name__)
app.secret_key = "iz_motor_gizli_anahtar_erp"

SIFRE = "izmotor2026*"
GOOGLE_MAPS_LINK = "https://maps.app.goo.gl/QxqqpoFoHuo2fFEr5?g_st=ac"

# --- VERİTABANI BAĞLANTI & KURULUMU ---
def init_db():
    conn = sqlite3.connect('iz_motor_servis.db', check_same_thread=False)
    cursor = conn.cursor()
    
    # 1. Servis Geçmişi (Çift INTEGER hatası giderildi)
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
            toplam_tutar REAL
        )
    ''')
    
    # 2. Stok / Parça Takibi
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stok (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parca_adi TEXT,
            adet INTEGER,
            fiyat REAL
        )
    ''')
    
    # 3. Bakım / Randevu Takibi
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bakimlar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plaka TEXT,
            musteri_ad TEXT,
            telefon TEXT,
            sonraki_bakim_km TEXT,
            hatirlatma_tarihi TEXT
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

# --- HTML / CSS GELİŞMİŞ ERP PANELİ ---
HTML_LOGIN = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>İz Motorsiklet - Giriş</title>
    <style>
        body { font-family: sans-serif; background: #f4f6f9; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
        .login-box { background: #fff; padding: 30px; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); width: 100%; max-width: 350px; text-align: center; }
        h2 { color: #1a365d; margin-bottom: 20px; }
        input { width: 100%; padding: 12px; margin-bottom: 15px; border: 1px solid #cbd5e0; border-radius: 4px; box-sizing: border-box; font-size: 16px; }
        button { background: #1a365d; color: #fff; border: none; padding: 12px; border-radius: 4px; width: 100%; font-size: 16px; font-weight: bold; cursor: pointer; }
        button:hover { background: #2c5282; }
        .error { color: #e53e3e; margin-bottom: 10px; font-size: 14px; }
    </style>
</head>
<body>
<div class="login-box">
    <h2>İZ MOTORSİKLET</h2>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
    <form method="POST">
        <input type="password" name="sifre" placeholder="Şifreyi girin..." required autofocus>
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
    <title>İz Motorsiklet ERP Paneli</title>
    <style>
        body { font-family: sans-serif; background: #f4f6f9; margin: 0; padding: 15px; color: #333; }
        .container { max-width: 700px; margin: 0 auto; background: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        h2 { text-align: center; color: #1a365d; margin-bottom: 15px; }
        .tabs { display: flex; flex-wrap: wrap; justify-content: center; gap: 5px; margin-bottom: 20px; }
        .tab-btn { background: #cbd5e0; border: none; padding: 8px 12px; border-radius: 4px; cursor: pointer; font-weight: bold; font-size: 13px; }
        .tab-btn.active { background: #1a365d; color: #fff; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .form-group { margin-bottom: 12px; }
        label { display: block; font-weight: bold; margin-bottom: 4px; font-size: 14px; }
        input, textarea, select { width: 100%; padding: 9px; border: 1px solid #cbd5e0; border-radius: 4px; box-sizing: border-box; }
        .item-row { display: flex; gap: 6px; margin-bottom: 8px; align-items: center; }
        .item-row input { flex: 2; }
        .item-row input.small { flex: 1; }
        .btn-add { background: #319795; color: #fff; border: none; padding: 8px; border-radius: 4px; cursor: pointer; font-weight: bold; width: 100%; margin-bottom: 15px; }
        .btn-remove { background: #e53e3e; color: #fff; border: none; padding: 8px 12px; border-radius: 4px; cursor: pointer; }
        button[type="submit"], .btn-action { background: #1a365d; color: #fff; border: none; padding: 11px; border-radius: 4px; cursor: pointer; width: 100%; font-size: 15px; font-weight: bold; margin-top: 10px; }
        .logout { text-align: right; margin-bottom: 5px; }
        .logout a { color: #e53e3e; text-decoration: none; font-size: 13px; font-weight: bold; }
        .google-box { background: #ebf8ff; border: 1px solid #bee3f8; padding: 10px; border-radius: 6px; margin-bottom: 15px; text-align: center; font-size: 14px; }
        .google-box a { color: #2b6cb0; font-weight: bold; text-decoration: none; }
        .card { background: #f7fafc; border: 1px solid #e2e8f0; padding: 10px; border-radius: 6px; margin-bottom: 8px; font-size: 14px; }
        .stats-box { background: #fffaf0; border: 1px solid #feebc8; padding: 15px; border-radius: 6px; text-align: center; margin-bottom: 15px; }
    </style>
</head>
<body>
<div class="container">
    <div class="logout"><a href="/cikis">Çıkış Yap</a></div>
    <h2>İZ MOTORSİKLET YÖNETİM PANELİ</h2>

    <!-- GOOGLE YORUMLARI WIDGET -->
    <div class="google-box">
        ⭐ <b>Google İşletme Değerlendirmeleri:</b> Puanımızı incelemek için <a href="https://maps.app.goo.gl/QxqqpoFoHuo2fFEr5?g_st=ac" target="_blank">tıklayın</a>!
    </div>

    <!-- SEKMELER -->
    <div class="tabs">
        <button class="tab-btn active" onclick="switchTab('formTab', this)">Servis Formu</button>
        <button class="tab-btn" onclick="switchTab('historyTab', this)">Plaka Geçmişi</button>
        <button class="tab-btn" onclick="switchTab('stockTab', this)">Stok Takibi</button>
        <button class="tab-btn" onclick="switchTab('financeTab', this)">Ciro Raporu</button>
        <button class="tab-btn" onclick="switchTab('reminderTab', this)">Bakım Hatırlat</button>
    </div>

    <!-- 1. SEKME: SERVİS FORMU -->
    <div id="formTab" class="tab-content active">
        <form action="/olustur" method="POST" enctype="multipart/form-data">
            <div class="form-group">
                <label>Dükkan Logosu / Hasar Fotoğrafı</label>
                <input type="file" name="logo" accept="image/*" required>
            </div>
            <div class="form-group">
                <label>Müşteri Adı Soyadı</label>
                <input type="text" name="musteri_ad" placeholder="Örn: Ahmet Yılmaz" required>
            </div>
            <div class="form-group">
                <label>Müşteri Telefon (WhatsApp için)</label>
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
                <input type="text" name="km" placeholder="Örn: 15.000 KM" required>
            </div>

            <hr style="margin: 15px 0; border: 0; border-top: 1px solid #e2e8f0;">
            <label><b>Yapılan İşlemler / Parçalar</b></label>
            
            <div id="items-container">
                <div class="item-row">
                    <input type="text" name="islem[]" placeholder="Parça / İşlem Adı">
                    <input type="number" name="adet[]" class="small" placeholder="Adet" value="1">
                    <input type="number" step="0.01" name="fiyat[]" class="small" placeholder="Fiyat (TL)">
                </div>
            </div>
            
            <button type="button" class="btn-add" onclick="addItem()">+ Yeni Satır Ekle</button>

            <div class="form-group">
                <label>İşçilik Tutarı (TL)</label>
                <input type="number" step="0.01" name="iscilik" placeholder="Örn: 500" value="0">
            </div>

            <div class="form-group">
                <label>Notlar ve Sonraki Bakım KM / Tarihi</label>
                <textarea name="notlar" rows="2" placeholder="Örn: 20.000 km'de yağ değişimi yapılacak."></textarea>
            </div>

            <button type="submit">Servis Formu PDF İndir & Kaydet</button>
        </form>
    </div>

    <!-- 2. SEKME: PLAKA GEÇMİŞİ -->
    <div id="historyTab" class="tab-content">
        <form method="GET" action="/">
            <input type="hidden" name="tab" value="history">
            <div class="form-group">
                <label>Plaka ile Sorgula</label>
                <input type="text" name="sorgu_plaka" placeholder="Örn: 34 ABC 123" value="{{ sorgu_plaka or '' }}">
            </div>
            <button type="submit" class="btn-action">Geçmişi Ara</button>
        </form>
        <hr style="margin: 15px 0; border: 0; border-top: 1px solid #e2e8f0;">
        <h3>Kayıtlar</h3>
        {% if kayitlar %}
            {% for k in kayitlar %}
            <div class="card">
                <b>Plaka:</b> {{ k[1] }} | <b>Tarih:</b> {{ k[6] }}<br>
                <b>Müşteri:</b> {{ k[2] }} ({{ k[3] }})<br>
                <b>Model / KM:</b> {{ k[4] }} - {{ k[5] }}<br>
                <b>Yapılanlar:</b> {{ k[7] }}<br>
                <b>Toplam Tutar:</b> <span style="color: #2b6cb0; font-weight: bold;">{{ "%.2f"|format(k[8]) }} TL</span><br>
                <a href="https://wa.me/{{ k[3] }}?text=Sayin%20{{ k[2] }},%20Iz%20Motorsiklet%20servis%20formunuz%20hazirdir.%20Iyi%20gunler%20dileriz." target="_blank" style="display:inline-block; margin-top:5px; background:#25d366; color:#fff; padding:4px 8px; border-radius:4px; text-decoration:none; font-size:12px; font-weight:bold;">💬 WhatsApp Mesajı Gönder</a>
            </div>
            {% endfor %}
        {% else %}
            <p style="color: #718096; text-align: center;">Kayıt bulunamadı.</p>
        {% endif %}
    </div>

    <!-- 3. SEKME: STOK TAKİBİ -->
    <div id="stockTab" class="tab-content">
        <h3>Parça / Ürün Stok Yönetimi</h3>
        <form method="POST" action="/stok_ekle">
            <div class="form-group"><input type="text" name="parca_adi" placeholder="Parça Adı (Örn: Buji NGK)" required></div>
            <div class="form-group"><input type="number" name="adet" placeholder="Stok Adedi" required></div>
            <div class="form-group"><input type="number" step="0.01" name="fiyat" placeholder="Birim Satış Fiyatı (TL)" required></div>
            <button type="submit" class="btn-action">Stok Ekle / Güncelle</button>
        </form>
        <hr style="margin: 15px 0; border: 0; border-top: 1px solid #e2e8f0;">
        <h4>Mevcut Stoklar</h4>
        {% if stoklar %}
            {% for s in stoklar %}
            <div class="card">
                <b>{{ s[1] }}</b> - Adet: <span style="color: {% if s[2] < 3 %}red{% else %}green{% endif %}; font-weight:bold;">{{ s[2] }}</span> | Fiyat: {{ "%.2f"|format(s[3]) }} TL
            </div>
            {% endfor %}
        {% else %}
            <p style="color: #718096; text-align: center;">Stokta ürün bulunmuyor.</p>
        {% endif %}
    </div>

    <!-- 4. SEKME: CİRO / FİNANS RAPORU -->
    <div id="financeTab" class="tab-content">
        <h3>Finansal Özet ve Ciro</h3>
        <div class="stats-box">
            <h2 style="color: #d69e2e; margin: 0;">{{ "%.2f"|format(toplam_ciro) }} TL</h2>
            <p style="margin: 5px 0 0 0; font-weight: bold; color: #4a5568;">Toplam Servis Cirosu</p>
        </div>
        <h4>Son Yapılan İşlemler</h4>
        {% if tum_servisler %}
            {% for ts in tum_servisler[:10] %}
            <div class="card">
                <b>{{ ts[1] }}</b> - {{ ts[6] }} : <span style="color: #2b6cb0; font-weight: bold;">{{ "%.2f"|format(ts[8]) }} TL</span>
            </div>
            {% endfor %}
        {% endif %}
    </div>

    <!-- 5. SEKME: BAKIM HATIRLATMA -->
    <div id="reminderTab" class="tab-content">
        <h3>Bakım ve Randevu Takibi</h3>
        {% if randevular %}
            {% for r in randevular %}
            <div class="card" style="border-left: 4px solid #319795;">
                <b>Plaka:</b> {{ r[1] }} | <b>Müşteri:</b> {{ r[2] }}<br>
                <b>Hedef Bakım KM:</b> {{ r[4] }}<br>
                <a href="https://wa.me/{{ r[3] }}?text=Sayin%20{{ r[2] }},%20Iz%20Motorsiklet%20bakim%20vaktiniz%20yaklasmistir.%20Bekleriz." target="_blank" style="display:inline-block; margin-top:5px; background:#25d366; color:#fff; padding:4px 8px; border-radius:4px; text-decoration:none; font-size:12px; font-weight:bold;">💬 Bakım Hatırlatması Gönder</a>
            </div>
            {% endfor %}
        {% else %}
            <p style="color: #718096; text-align: center;">Kayıtlı bakım hatırlatması bulunmuyor.</p>
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

function addItem() {
    const container = document.getElementById('items-container');
    const row = document.createElement('div');
    row.className = 'item-row';
    row.innerHTML = `
        <input type="text" name="islem[]" placeholder="Parça / İşlem Adı">
        <input type="number" name="adet[]" class="small" placeholder="Adet" value="1">
        <input type="number" step="0.01" name="fiyat[]" class="small" placeholder="Fiyat (TL)">
        <button type="button" class="btn-remove" onclick="this.parentElement.remove()">X</button>
    `;
    container.appendChild(row);
}

const urlParams = new URLSearchParams(window.location.search);
const tab = urlParams.get('tab');
if(tab === 'history') switchTab('historyTab', document.querySelectorAll('.tab-btn')[1]);
else if(tab === 'stock') switchTab('stockTab', document.querySelectorAll('.tab-btn')[2]);
else if(tab === 'finance') switchTab('financeTab', document.querySelectorAll('.tab-btn')[3]);
else if(tab === 'reminder') switchTab('reminderTab', document.querySelectorAll('.tab-btn')[4]);
</script>

</body>
</html>
"""

# --- PDF MOTORU ---
def pdf_olustur(filename, veri, logo_yolu):
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
    story.append(Spacer(1, 8))

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
    story.append(Spacer(1, 8))

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
        cursor.execute("SELECT * FROM servisler WHERE plaka LIKE ? ORDER BY id DESC", ('%' + sorgu_plaka + '%',))
        kayitlar = cursor.fetchall()

    cursor.execute("SELECT * FROM stok")
    stoklar = cursor.fetchall()

    cursor.execute("SELECT * FROM servisler ORDER BY id DESC")
    tum_servisler = cursor.fetchall()

    cursor.execute("SELECT SUM(toplam_tutar) FROM servisler")
    res = cursor.fetchone()
    toplam_ciro = res[0] if res and res[0] else 0.0

    cursor.execute("SELECT * FROM bakimlar")
    randevular = cursor.fetchall()

    conn.close()
        
    return render_template_string(HTML_PANEL, kayitlar=kayitlar, sorgu_plaka=sorgu_plaka, stoklar=stoklar, tum_servisler=tum_servisler, toplam_ciro=toplam_ciro, randevular=randevular)

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
    km = request.form.get('km')
    notlar = request.form.get('notlar', '')
    
    try:
        iscilik = float(request.form.get('iscilik', 0))
    except ValueError:
        iscilik = 0.0

    islem_adlari = request.form.getlist('islem[]')
    adet_listesi = request.form.getlist('adet[]')
    fiyat_listesi = request.form.getlist('fiyat[]')
    
    islemler = []
    yedek_parca_toplam = 0.0
    islem_ozeti_list = []

    for i in range(len(islem_adlari)):
        if islem_adlari[i].strip():
            try:
                adt = int(adet_listesi[i]) if adet_listesi[i] else 1
                fyt = float(fiyat_listesi[i]) if fiyat_listesi[i] else 0.0
                tutar = adt * fyt
                yedek_parca_toplam += tutar
                islemler.append({'ad': islem_adlari[i], 'adet': adt, 'fiyat': fyt})
                islem_ozeti_list.append(f"{islem_adlari[i]} (x{adt})")
            except ValueError:
                continue

    genel_toplam = yedek_parca_toplam + iscilik
    islem_str = ", ".join(islem_ozeti_list) if islem_ozeti_list else "İşlem belirtilmedi"
    tarih_str = datetime.date.today().strftime("%d.%m.%Y")

    conn = sqlite3.connect('iz_motor_servis.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO servisler (plaka, musteri_ad, musteri_tel, model, km, tarih, detaylar, toplam_tutar)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (plaka, musteri_ad, musteri_tel, model, km, tarih_str, islem_str, genel_toplam))
    
    cursor.execute("INSERT INTO bakimlar (plaka, musteri_ad, telefon, sonraki_bakim_km, hatirlatma_tarihi) VALUES (?, ?, ?, ?, ?)", 
                   (plaka, musteri_ad, musteri_tel, "5000 km sonra", "3 Ay Sonra"))
    
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

    pdf_path = f"servis_formu_{plaka}.pdf"
    pdf_olustur(pdf_path, veri, logo_path)

    response = send_file(pdf_path, as_attachment=True)
    @response.call_on_close
    def cleanup():
        if os.path.exists(pdf_path): os.remove(pdf_path)
        if logo_path and os.path.exists(logo_path): os.remove(logo_path)

    return response


# --- TELEGRAM BOTU ---
SIFRE_DURUMU = {}
LOGO_AL, MUSTERI_AD, MUSTERI_TEL, ARAÇ_PLAKA, ARAÇ_MODEL, ARAÇ_KM, ISLEM_EKLE, ISLEM_ADET, ISLEM_FIYAT, ISCILIK, NOTLAR = range(11)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    SIFRE_DURUMU[user_id] = False
    await update.message.reply_text("Selam kanka! İz Motorsiklet Botuna hoş geldin.\nDevam etmek için lütfen **şifreyi** gir kanka:")

async def sifre_kontrol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    if SIFRE_DURUMU.get(user_id, False): return
    if text == SIFRE:
        SIFRE_DURUMU[user_id] = True
        await update.message.reply_text("Şifre doğru kanka! Yeni servis formu için `/yeni_servis` yazabilirsin.")
    else:
        await update.message.reply_text("Hatalı şifre kanka! Tekrar dene:")

async def yeni_servis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not SIFRE_DURUMU.get(user_id, False):
        await update.message.reply_text("Önce şifreyi girmen gerekiyor kanka! /start yaz.")
        return ConversationHandler.END
    context.user_data['islemler'] = []
    await update.message.reply_text("Önce dükkanın logosunu veya hasar fotoğrafını **fotoğraf olarak** gönder kanka:")
    return LOGO_AL

async def logo_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_file = await update.message.photo[-1].get_file()
    logo_path = f"temp_logo_tg_{update.effective_user.id}.jpg"
    await photo_file.download_to_drive(logo_path)
    context.user_data['logo_path'] = logo_path
    await update.message.reply_text("Logo alındı! Şimdi Müşteri Adı ve Soyadını gir kanka:")
    return MUSTERI_AD

async def logo_uyari(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Kanka yazı değil, **fotoğraf** göndermen gerekiyor! Hadi bekliyorum:")
    return LOGO_AL

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
    await update.message.reply_text("1. Yapılan İşlem veya Değişen Parça adını gir kanka:")
    return ISLEM_EKLE

async def islem_ad_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['gecici_islem'] = update.message.text
    await update.message.reply_text(f"'{update.message.text}' için Adet/Miktar gir:")
    return ISLEM_ADET

async def islem_adet_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['gecici_adet'] = int(update.message.text)
        await update.message.reply_text("Birim Fiyatını (TL) gir kanka:")
        return ISLEM_FIYAT
    except ValueError:
        await update.message.reply_text("Lütfen sayı gir kanka:")
        return ISLEM_ADET

async def islem_fiyat_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        fiyat = float(update.message.text.replace(',', '.'))
        context.user_data['islemler'].append({
            'ad': context.user_data['gecici_islem'],
            'adet': context.user_data['gecici_adet'],
            'fiyat': fiyat
        })
        reply_keyboard = [['+ Başka Parça/İşlem Ekle', 'Parçalar Bitti / İşçiliğe Geç']]
        await update.message.reply_text("Eklendi! Başka parça ekleyecek misin?", reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True))
        return ISLEM_EKLE
    except ValueError:
        await update.message.reply_text("Geçerli bir fiyat gir kanka:")
        return ISLEM_FIYAT

async def islem_karar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == '+ Başka Parça/İşlem Ekle':
        await update.message.reply_text("Diğer yapılan işlemi yaz kanka:", reply_markup=ReplyKeyboardRemove())
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
        INSERT INTO servisler (plaka, musteri_ad, musteri_tel, model, km, tarih, detaylar, toplam_tutar)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (plaka, context.user_data['musteri_ad'], context.user_data['musteri_tel'], context.user_data['model'], context.user_data['km'], tarih_str, islem_str, genel_toplam))
    conn.commit()
    conn.close()

    pdf_olustur(pdf_path, context.user_data, logo_yolu)
    
    with open(pdf_path, 'rb') as doc:
        await update.message.reply_document(document=doc, caption="İşte servis formu kanka!")
        
    if os.path.exists(pdf_path): os.remove(pdf_path)
    if logo_yolu and os.path.exists(logo_yolu): os.remove(logo_yolu)
        
    return ConversationHandler.END

async def iptal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logo_yolu = context.user_data.get('logo_path')
    if logo_yolu and os.path.exists(logo_yolu): os.remove(logo_yolu)
    await update.message.reply_text("İşlem iptal edildi kanka.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

def run_telegram_bot():
    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN: return
    bot_app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('yeni_servis', yeni_servis)],
        states={
            LOGO_AL: [MessageHandler(filters.PHOTO, logo_al), MessageHandler(filters.TEXT & ~filters.COMMAND, logo_uyari)],
            MUSTERI_AD: [MessageHandler(filters.TEXT & ~filters.COMMAND, musteri_ad_al)],
            MUSTERI_TEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, musteri_tel_al)],
            ARAÇ_PLAKA: [MessageHandler(filters.TEXT & ~filters.COMMAND, arac_plaka_al)],
            ARAÇ_MODEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, arac_model_al)],
            ARAÇ_KM: [MessageHandler(filters.TEXT & ~filters.COMMAND, arac_km_al)],
            ISLEM_EKLE: [
                MessageHandler(filters.Regex(r'^\+ Başka Parça/İşlem Ekle$'), islem_karar),
                MessageHandler(filters.Regex(r'^Parçalar Bitti / İşçiliğe Geç$'), islem_karar),
                MessageHandler(filters.TEXT & ~filters.COMMAND, islem_ad_al)
            ],
            ISLEM_ADET: [MessageHandler(filters.TEXT & ~filters.COMMAND, islem_adet_al)],
            ISLEM_FIYAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, islem_fiyat_al)],
            ISCILIK: [MessageHandler(filters.TEXT & ~filters.COMMAND, iscilik_al)],
            NOTLAR: [MessageHandler(filters.TEXT & ~filters.COMMAND, notlar_ve_bitis)],
        },
        fallbacks=[CommandHandler('iptal', iptal)]
    )

    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(conv_handler)
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, sifre_kontrol))

    bot_app.run_polling(stop_signals=None)

if __name__ == '__main__':
    threading.Thread(target=run_telegram_bot, daemon=True).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
