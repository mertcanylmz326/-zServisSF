import os
import threading
from flask import Flask
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    filters, ConversationHandler, ContextTypes
)
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# --- FLASK MINI SUNUCU (Render Web Service için) ---
app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return "Bot aktif ve çalışıyor kanka!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app_flask.run(host='0.0.0.0', port=port)

# --- ADIM KODLARI ---
MUSTERI, ARAÇ, HIZMET_EKLE, HIZMET_FIYAT, ODEME = range(5)

# --- PDF OLUŞTURMA FONKSİYONU ---
def pdf_olustur(filename, veri):
    doc = SimpleDocTemplate(filename, pagesize=A4, rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20)
    story = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Heading1'],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#1A365D"),
        alignment=1,
        spaceAfter=10
    )
    
    story.append(Paragraph("<b>İZ MOTORSİKLET SERVİS FORMU</b>", title_style))
    story.append(Spacer(1, 10))

    # Müşteri & Araç Bilgileri Tablosu
    bilgi_data = [
        [Paragraph(f"<b>Müşteri:</b> {veri['musteri']}", styles['Normal']), Paragraph(f"<b>Plaka:</b> {veri['plaka']}", styles['Normal'])],
        [Paragraph(f"<b>Araç/Model:</b> {veri['model']}", styles['Normal']), Paragraph(f"<b>KM:</b> {veri['km']}", styles['Normal'])],
    ]
    t_bilgi = Table(bilgi_data, colWidths=[270, 270])
    t_bilgi.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F7FAFC")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#CBD5E0")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t_bilgi)
    story.append(Spacer(1, 15))

    # Hizmetler Tablosu
    hizmet_table_data = [["Hizmet / Açıklama", "Tutar (TL)"]]
    toplam = 0
    for h in veri['hizmetler']:
        hizmet_table_data.append([h['ad'], f"{h['fiyat']:.2f} TL"])
        toplam += h['fiyat']

    hizmet_table_data.append(["TOPLAM TUTAR", f"{toplam:.2f} TL"])

    t_hizmet = Table(hizmet_table_data, colWidths=[400, 140])
    t_hizmet.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1A365D")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('BOTTOMPADDING', (0,0), (-1,0), 6),
        ('GRID', (0,0), (-1,-2), 0.5, colors.HexColor("#CBD5E0")),
        ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor("#EDF2F7")),
        ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t_hizmet)
    story.append(Spacer(1, 15))
    
    # Ödeme Bilgisi
    story.append(Paragraph(f"<b>Ödeme Türü:</b> {veri['odeme']}", styles['Normal']))
    
    doc.build(story)

# --- BOT KOMUTLARI & AKIŞI ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Selam kanka! Yeni bir servis formu oluşturmak için /yeni_servis yazabilirsin.")

async def yeni_servis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['hizmetler'] = []
    await update.message.reply_text("Müşterinin Adı ve Telefonunu gir kanka (Örn: Ahmet Yılmaz - 0532xxx):")
    return MUSTERI

async def musteri_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['musteri'] = update.message.text
    await update.message.reply_text("Araç Model, Plaka ve KM bilgilerini gir (Örn: Honda PCX - 34 ABC 123 - 15.000 KM):")
    return ARAÇ

async def arac_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.split('-')
    context.user_data['model'] = text[0].strip() if len(text) > 0 else update.message.text
    context.user_data['plaka'] = text[1].strip() if len(text) > 1 else "-"
    context.user_data['km'] = text[2].strip() if len(text) > 2 else "-"
    
    await update.message.reply_text("Yapılan ilk hizmeti/parçayı yaz kanka (Örn: Yağ Değişimi & Filtre):")
    return HIZMET_EKLE

async def hizmet_ad_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['gecici_hizmet'] = update.message.text
    await update.message.reply_text(f"'{update.message.text}' için fiyatı gir (Örn: 850):")
    return HIZMET_FIYAT

async def hizmet_fiyat_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        fiyat = float(update.message.text.replace(',', '.'))
        context.user_data['hizmetler'].append({
            'ad': context.user_data['gecici_hizmet'],
            'fiyat': fiyat
        })
        
        reply_keyboard = [['+ Başka Hizmet Ekle', 'Bitti / Ödemeye Geç']]
        await update.message.reply_text(
            "Hizmet eklendi! Başka ekleyecek misin yoksa bitti mi?",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
        )
        return HIZMET_EKLE
    except ValueError:
        await update.message.reply_text("Lütfen geçerli bir sayı gir kanka (Örn: 450 veya 450.50):")
        return HIZMET_FIYAT

async def hizmet_karar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == '+ Başka Hizmet Ekle':
        await update.message.reply_text("Diğer hizmeti yaz kanka:", reply_markup=ReplyKeyboardRemove())
        return HIZMET_EKLE
    else:
        reply_keyboard = [['Nakit', 'Kredi Kartı', 'Havale/EFT']]
        await update.message.reply_text(
            "Ödeme türünü seç kanka:",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
        )
        return ODEME

async def odeme_ve_bitis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['odeme'] = update.message.text
    await update.message.reply_text("Servis formu hazırlanıyor, bekle kanka...", reply_markup=ReplyKeyboardRemove())
    
    pdf_path = f"servis_formu_{context.user_data['plaka']}.pdf"
    pdf_olustur(pdf_path, context.user_data)
    
    with open(pdf_path, 'rb') as doc:
        await update.message.reply_document(document=doc, caption="İşte hazır servis formu kanka!")
        
    if os.path.exists(pdf_path):
        os.remove(pdf_path)
        
    return ConversationHandler.END

async def iptal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("İşlem iptal edildi kanka.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

def main():
    # Flask web sunucusunu ayrı bir thred'de başlatıyoruz
    threading.Thread(target=run_flask, daemon=True).start()

    TOKEN = os.getenv("BOT_TOKEN")
    if not TOKEN:
        raise ValueError("BOT_TOKEN ortam değişkeni bulunamadı!")
    
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('yeni_servis', yeni_servis)],
        states={
            MUSTERI: [MessageHandler(filters.TEXT & ~filters.COMMAND, musteri_al)],
            ARAÇ: [MessageHandler(filters.TEXT & ~filters.COMMAND, arac_al)],
            HIZMET_EKLE: [
                MessageHandler(filters.Regex('^\+ Başka Hizmet Ekle$'), hizmet_karar),
                MessageHandler(filters.Regex('^Bitti / Ödemeye Geç$'), hizmet_karar),
                MessageHandler(filters.TEXT & ~filters.COMMAND, hizmet_ad_al)
            ],
            HIZMET_FIYAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, hizmet_fiyat_al)],
            ODEME: [MessageHandler(filters.TEXT & ~filters.COMMAND, odeme_ve_bitis)],
        },
        fallbacks=[CommandHandler('iptal', iptal)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)

    print("Bot ve Web sunucusu çalışıyor...")
    app.run_polling()

if __name__ == '__main__':
    main()
