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
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# --- FLASK MINI SUNUCU (Render Web Service İçin) ---
app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return "Bot aktif ve çalışıyor kanka!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app_flask.run(host='0.0.0.0', port=port)

# --- ADIM KODLARI ---
MUSTERI_AD, MUSTERI_TEL, ARAÇ_PLAKA, ARAÇ_MODEL, ARAÇ_KM, ISLEM_EKLE, ISLEM_ADET, ISLEM_FIYAT, ISCILIK, NOTLAR = range(10)

# --- PDF OLUŞTURMA FONKSİYONU ---
def pdf_olustur(filename, veri):
    doc = SimpleDocTemplate(
        filename, 
        pagesize=A4, 
        rightMargin=15, 
        leftMargin=15, 
        topMargin=15, 
        bottomMargin=15
    )
    story = []
    styles = getSampleStyleSheet()

    # --- LOGO (Eğer proje dizininde logo.png varsa otomatik ekler) ---
    if os.path.exists("logo.png"):
        try:
            story.append(Image("logo.png", width=320, height=80))
            story.append(Spacer(1, 4))
        except Exception:
            pass

    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Heading1'],
        fontSize=15,
        leading=18,
        textColor=colors.HexColor("#1A1A1A"),
        alignment=1,
        spaceAfter=8,
        fontName="Helvetica-Bold"
    )
    story.append(Paragraph("MÜŞTERİ SERVİS FORMU", title_style))

    # --- MÜŞTERİ VE ARAÇ BİLGİLERİ ---
    tarih_str = datetime.date.today().strftime("%d.%m.%Y")
    
    m_text = f"<b>MÜŞTERİ BİLGİLERİ</b><br/><br/>" \
             f"<b>Adı Soyadı :</b> {veri.get('musteri_ad', '')}<br/>" \
             f"<b>Telefon :</b> {veri.get('musteri_tel', '')}<br/>" \
             f"<b>Tarih :</b> {tarih_str}"

    a_text = f"<b>ARAÇ BİLGİLERİ</b><br/><br/>" \
             f"<b>Plaka :</b> {veri.get('plaka', '')}<br/>" \
             f"<b>Marka / Model :</b> {veri.get('model', '')}<br/>" \
             f"<b>Kilometre :</b> {veri.get('km', '')}"

    p_m = Paragraph(m_text, styles['Normal'])
    p_a = Paragraph(a_text, styles['Normal'])

    t_bilgi = Table([[p_m, p_a]], colWidths=[280, 280])
    t_bilgi.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 0.8, colors.HexColor("#CBD5E0")),
        ('INNERGRID', (0,0), (-1,-1), 0.8, colors.HexColor("#CBD5E0")),
        ('PADDING', (0,0), (-1,-1), 8),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#FAFAFA")),
    ]))
    story.append(t_bilgi)
    story.append(Spacer(1, 8))

    # --- YAPIŞAN İŞLEMLER TABLOSU (10 Satırlı Birebir Şablon) ---
    hizmet_table_data = [["No", "Yapılan İşlem / Değişen Parça", "Adet / Miktar", "Tutar (TL)"]]
    
    islemler = veri.get('islemler', [])
    yedek_parca_toplam = 0.0

    for idx in range(10):
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

    t_hizmet = Table(hizmet_table_data, colWidths=[30, 320, 90, 120])
    t_hizmet.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#F2F2F2")),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('ALIGN', (0,0), (0,-1), 'CENTER'),
        ('ALIGN', (2,0), (2,-4), 'CENTER'),
        ('ALIGN', (3,0), (3,-1), 'RIGHT'),
        ('GRID', (0,0), (-1,-4), 0.5, colors.HexColor("#CBD5E0")),
        ('LINEBELOW', (0,-4), (-1,-1), 0.5, colors.HexColor("#CBD5E0")),
        ('FONTNAME', (1,-3), (-1,-1), 'Helvetica-Bold'),
        ('SPAN', (1,-3), (2,-3)),
        ('SPAN', (1,-2), (2,-2)),
        ('SPAN', (1,-1), (2,-1)),
        ('BACKGROUND', (1,-1), (-1,-1), colors.HexColor("#E2E8F0")),
        ('PADDING', (0,0), (-1,-1), 4.5),
    ]))
    story.append(t_hizmet)
    story.append(Spacer(1, 8))

    # --- NOTLAR VE TESPİTLER ---
    notlar_text = veri.get('notlar', '')
    p_notlar = Paragraph(f"<b>Notlar ve Tespitler</b><br/>{notlar_text}<br/><br/>", styles['Normal'])
    t_notlar = Table([[p_notlar]], colWidths=[560])
    t_notlar.setStyle(TableStyle([
        ('LINEBELOW', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E0")),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    story.append(t_notlar)
    story.append(Spacer(1, 15))

    # --- İMZA VE ALT BİLGİ ---
    imza_data = [
        [Paragraph("<b>Müşteri Onayı</b>", styles['Normal']), Paragraph("<b>Servis Yetkilisi</b>", styles['Normal'])],
        ["", ""],
        [Paragraph("<font size=8 color='#666666'>Ad / Soyad / İmza</font>", styles['Normal']),
         Paragraph("<font size=8 color='#666666'>Kaşe / İmza</font>", styles['Normal'])]
    ]
    t_imza = Table(imza_data, colWidths=[280, 280])
    t_imza.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('LINEBELOW', (0,0), (0,0), 0.5, colors.HexColor("#A0AEC0")),
        ('LINEBELOW', (1,0), (1,0), 0.5, colors.HexColor("#A0AEC0")),
        ('PADDING', (0,0), (-1,-1), 2),
    ]))
    story.append(t_imza)
    story.append(Spacer(1, 20))

    # Sayfa Alt Bilgisi
    footer_data = [[
        Paragraph("<font size=8 color='#888888'>İz Motorsiklet Çekmeköy</font>", styles['Normal']),
        Paragraph("<font size=8 color='#888888'>Sayfa 1 / 1</font>", styles['Normal'])
    ]]
    t_footer = Table(footer_data, colWidths=[280, 280])
    t_footer.setStyle(TableStyle([
        ('ALIGN', (0,0), (0,0), 'LEFT'),
        ('ALIGN', (1,0), (1,0), 'RIGHT'),
        ('PADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(t_footer)

    doc.build(story)

# --- BOT KOMUTLARI & AKIŞI ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Selam kanka! Servis formu oluşturmak için /yeni_servis yazabilirsin.")

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
    await update.message.reply_text("Marka / Model bilgisini gir kanka (Örn: Honda PCX 125):")
    return ARAÇ_MODEL

async def arac_model_al(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['model'] = update.message.text
    await update.message.reply_text("Motosiklet KM bilgisini gir kanka (Örn: 14.500 KM):")
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
    
    await update.message.reply_text("Servis formu hazırlanıyor...", reply_markup=ReplyKeyboardRemove())
    
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
