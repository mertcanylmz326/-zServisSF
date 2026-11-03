import os
import datetime
import threading
import asyncio
from flask import Flask
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    filters, ConversationHandler, ContextTypes
)
from xhtml2pdf import pisa
from io import BytesIO

# --- FLASK MINI SUNUCU ---
app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return "Bot aktif ve çalışıyor kanka!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app_flask.run(host='0.0.0.0', port=port)

# --- ADIM KODLARI ---
MUSTERI_AD, MUSTERI_TEL, ARAÇ_PLAKA, ARAÇ_MODEL, ARAÇ_KM, ISLEM_EKLE, ISLEM_ADET, ISLEM_FIYAT, ISCILIK, NOTLAR = range(10)

# --- HTML/CSS İLE PDF OLUŞTURMA FONKSİYONU ---
def pdf_olustur(filename, veri):
    tarih_str = datetime.date.today().strftime("%d.%m.%Y")
    
    islemler = veri.get('islemler', [])
    yedek_parca_toplam = 0.0
    
    # Tablo satırlarını oluşturuyoruz (10 satıra tamamlama)
    rows_html = ""
    for idx in range(10):
        if idx < len(islemler):
            item = islemler[idx]
            no = idx + 1
            islem_adi = item['ad']
            adet = item['adet']
            tutar_val = item['fiyat'] * item['adet']
            yedek_parca_toplam += tutar_val
            tutar_str = f"{tutar_val:.2f} TL"
        else:
            no = idx + 1
            islem_adi = ""
            adet = ""
            tutar_str = ""
            
        rows_html += f"""
        <tr>
            <td style="text-align: center; width: 35px;">{no}</td>
            <td>{islem_adi}</td>
            <td style="text-align: center; width: 75px;">{adet}</td>
            <td style="text-align: right; width: 100px;">{tutar_str}</td>
        </tr>
        """

    iscilik_tutar = veri.get('iscilik', 0.0)
    genel_toplam = yedek_parca_toplam + iscilik_tutar
    notlar_text = veri.get('notlar', '')

    # HTML & CSS Tasarımı (Motor Tamirhane Konsepti)
    html_content = f"""
    <!DOCTYPE html>
    <html lang="tr">
    <head>
        <meta charset="UTF-8">
        <style>
            @page {{
                size: A4;
                margin: 12mm;
            }}
            body {{
                font-family: Helvetica, Arial, sans-serif;
                color: #111111;
                font-size: 10pt;
                line-height: 1.2;
            }}
            .header-box {{
                background-color: #121212;
                color: #ffffff;
                padding: 12px;
                text-align: center;
                border-bottom: 4px solid #E65100;
                margin-bottom: 10px;
            }}
            .header-box h1 {{
                margin: 0;
                font-size: 20pt;
                letter-spacing: 2px;
                font-weight: bold;
            }}
            .header-box p {{
                margin: 4px 0 0 0;
                font-size: 10pt;
                color: #FFB300;
                letter-spacing: 1px;
            }}
            .form-title {{
                text-align: center;
                font-size: 13pt;
                font-weight: bold;
                background-color: #E0E0E0;
                padding: 6px;
                margin-bottom: 10px;
                border: 1px solid #B0B0B0;
                text-transform: uppercase;
            }}
            .info-table, .main-table, .footer-table {{
                width: 100%;
                border-collapse: collapse;
                margin-bottom: 8px;
            }}
            .info-table td {{
                width: 50%;
                vertical-align: top;
                border: 1px solid #B0B0B0;
                padding: 8px;
                background-color: #FAFAFA;
            }}
            .section-title {{
                font-weight: bold;
                font-size: 9.5pt;
                border-bottom: 1px solid #CCCCCC;
                padding-bottom: 4px;
                margin-bottom: 6px;
                color: #333333;
            }}
            .main-table th, .main-table td {{
                border: 1px solid #B0B0B0;
                padding: 5px 6px;
                font-size: 9.5pt;
            }}
            .main-table th {{
                background-color: #212121;
                color: #ffffff;
                text-align: center;
                font-size: 9.5pt;
            }}
            .total-row {{
                font-weight: bold;
                background-color: #EEEEEE;
            }}
            .grand-total {{
                font-weight: bold;
                background-color: #FFD54F;
                color: #000000;
            }}
            .notes-box {{
                border: 1px solid #B0B0B0;
                padding: 6px;
                min-height: 35px;
                margin-bottom: 10px;
                background-color: #FAFAFA;
            }}
            .signature-table {{
                width: 100%;
                margin-top: 15px;
            }}
            .signature-table td {{
                width: 50%;
                text-align: center;
                padding: 10px;
                vertical-align: top;
            }}
            .sig-line {{
                border-top: 1px solid #777777;
                margin-top: 35px;
                padding-top: 4px;
                font-size: 8.5pt;
                color: #555555;
            }}
            .footer {{
                margin-top: 15px;
                font-size: 8pt;
                color: #666666;
                border-top: 1px solid #DDDDDD;
                padding-top: 4px;
            }}
        </style>
    </head>
    <body>

        <!-- ŞIK MOTORCU ÜST LOGO & BAŞLIK ALANI -->
        <div class="header-box">
            <h1>İZ MOTORSİKLET ÇEKMEKÖY</h1>
            <p>TAMİR • BAKIM • ONARIM • SERVİS</p>
        </div>

        <div class="form-title">MÜŞTERİ SERVİS FORMU</div>

        <!-- MÜŞTERİ & ARAÇ BİLGİLERİ -->
        <table class="info-table">
            <tr>
                <td>
                    <div class="section-title">MÜŞTERİ BİLGİLERİ</div>
                    <b>Adı Soyadı :</b> {veri.get('musteri_ad', '')}<br/>
                    <b>Telefon :</b> {veri.get('musteri_tel', '')}<br/>
                    <b>Tarih :</b> {tarih_str}
                </td>
                <td>
                    <div class="section-title">ARAÇ BİLGİLERİ</div>
                    <b>Plaka :</b> {veri.get('plaka', '')}<br/>
                    <b>Marka / Model :</b> {veri.get('model', '')}<br/>
                    <b>Kilometre :</b> {veri.get('km', '')}
                </td>
            </tr>
        </table>

        <!-- İŞLEMLER TABLOSU -->
        <table class="main-table">
            <thead>
                <tr>
                    <th>No</th>
                    <th>Yapılan İşlem / Değişen Parça</th>
                    <th>Adet / Miktar</th>
                    <th>Tutar (TL)</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
                <tr class="total-row">
                    <td colspan="3" style="text-align: right;">İşçilik Tutarı:</td>
                    <td style="text-align: right;">{iscilik_tutar:.2f} TL</td>
                </tr>
                <tr class="total-row">
                    <td colspan="3" style="text-align: right;">Yedek Parça Tutarı:</td>
                    <td style="text-align: right;">{yedek_parca_toplam:.2f} TL</td>
                </tr>
                <tr class="grand-total">
                    <td colspan="3" style="text-align: right; font-size: 10pt;">GENEL TOPLAM:</td>
                    <td style="text-align: right; font-size: 10pt;">{genel_toplam:.2f} TL</td>
                </tr>
            </tbody>
        </table>

        <!-- NOTLAR VE TESPİTLER -->
        <div style="font-size: 9pt; font-weight: bold; margin-bottom: 2px;">Notlar ve Tespitler</div>
        <div class="notes-box">
            {notlar_text}
        </div>

        <!-- İMZALAR -->
        <table class="signature-table">
            <tr>
                <td>
                    <b>Müşteri Onayı</b>
                    <div class="sig-line">Ad / Soyad / İmza</div>
                </td>
                <td>
                    <b>Servis Yetkilisi</b>
                    <div class="sig-line">Kaşe / İmza</div>
                </td>
            </tr>
        </table>

        <!-- SAYFA ALT BİLGİSİ -->
        <table class="footer">
            <tr>
                <td style="text-align: left;">İz Motorsiklet Çekmeköy Servis Sistemi</td>
                <td style="text-align: right;">Sayfa 1 / 1</td>
            </tr>
        </table>

    </body>
    </html>
    """

    # PDF Derleme
    result_file = open(filename, "w+b")
    pisa.CreatePDF(BytesIO(html_content.encode("utf-8")), dest=result_file)
    result_file.close()

# --- BOT KOMUTLARI & AKIŞI ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Selam kanka! HTML tasarımlı profesyonel servis formu için /yeni_servis yazabilirsin.")

async def yeni_servis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['islemler'] = []
    await update.message.reply_text("Müşteri Adı ve Soyadını gir kanka:")
    return MUSTERI_AD

async def musteri_ad_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['musteri_ad'] = update.message.text
    await update.message.reply_text("Müşteri Telefon Numarasını gir kanka:")
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
    await update.message.reply_text("Motosiklet KM bilgisini gir kanka (Örn: 86.000 KM):")
    return ARAÇ_KM

async def arac_km_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['km'] = update.message.text
    await update.message.reply_text("1. Yapılan İşlem veya Değişen Parça adını gir kanka:")
    return ISLEM_EKLE

async def islem_ad_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['gecici_islem'] = update.message.text
    await update.message.reply_text(f"'{update.message.text}' için Adet/Miktar gir (Örn: 1):")
    return ISLEM_ADET

async def islem_adet_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['gecici_adet'] = int(update.message.text)
        await update.message.reply_text("Birim Fiyatını (TL) gir kanka (Örn: 450):")
        return ISLEM_FIYAT
    except ValueError:
        await update.message.reply_text("Lütfen adet miktarını sayı olarak gir kanka (Örn: 1):")
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
        await update.message.reply_text(
            "Eklendi! Başka parça/işlem ekleyecek misin?",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
        )
        return ISLEM_EKLE
    except ValueError:
        await update.message.reply_text("Lütfen geçerli bir fiyat gir kanka (Örn: 450 veya 450.50):")
        return ISLEM_FIYAT

async def islem_karar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == '+ Başka Parça/İşlem Ekle':
        await update.message.reply_text("Diğer yapılan işlemi/parçayı yaz kanka:", reply_markup=ReplyKeyboardRemove())
        return ISLEM_EKLE
    else:
        await update.message.reply_text("Toplam İşçilik Tutarını (TL) gir kanka (Yoksa 0 yaz):", reply_markup=ReplyKeyboardRemove())
        return ISCILIK

async def iscilik_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data['iscilik'] = float(update.message.text.replace(',', '.'))
        await update.message.reply_text("Forma eklemek istediğin 'Notlar ve Tespitler' var mı? (Yoksa 'Yok' yazabilirsin):")
        return NOTLAR
    except ValueError:
        await update.message.reply_text("Lütfen sayı olarak işçilik tutarını gir kanka (Örn: 200 veya 0):")
        return ISCILIK

async def notlar_ve_bitis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    context.user_data['notlar'] = "" if text.lower() == "yok" else text
    
    await update.message.reply_text("HTML tabanlı servis formu hazırlanıyor...", reply_markup=ReplyKeyboardRemove())
    
    pdf_path = f"servis_formu_{context.user_data['plaka']}.pdf"
    pdf_olustur(pdf_path, context.user_data)
    
    with open(pdf_path, 'rb') as doc:
        await update.message.reply_document(document=doc, caption="İşte tam istediğin HTML tasarımlı motorcu servis formu kanka!")
        
    if os.path.exists(pdf_path):
        os.remove(pdf_path)
        
    return ConversationHandler.END

async def iptal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("İşlem iptal edildi kanka.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

def main():
    threading.Thread(target=run_flask, daemon=True).start()

    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN:
        raise ValueError("BOT_TOKEN ortam değişkeni bulunamadı!")
    
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('yeni_servis', yeni_servis)],
        states={
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

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)

    print("Bot çalışıyor...")
    asyncio.run(app.run_polling())

if __name__ == '__main__':
    main()
