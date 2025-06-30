# bot_scheduler.py

import telegram
import asyncio
import datetime
import json
import os
from dotenv import load_dotenv
from telegram.ext import Application, MessageHandler, filters, CommandHandler

# Muat variabel lingkungan dari file .env
load_dotenv()

# --- Konfigurasi ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID") # ID Channel untuk penjadwal konten
GROUP_ID = os.getenv("GROUP_ID")     # ID Grup Diskusi untuk fitur FAQ dan interaksi

# Validasi konfigurasi
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN tidak ditemukan. Pastikan ada di file .env")
if not CHANNEL_ID:
    raise ValueError("CHANNEL_ID tidak ditemukan. Pastikan ada di file .env")
if not GROUP_ID:
    raise ValueError("GROUP_ID tidak ditemukan. Pastikan ada di file .env")

try:
    CHANNEL_ID = int(CHANNEL_ID)
    GROUP_ID = int(GROUP_ID)
except ValueError:
    raise ValueError("CHANNEL_ID dan GROUP_ID harus berupa angka. Cek kembali file .env Anda.")

# Nama file untuk menyimpan jadwal konten
SCHEDULE_FILE = "scheduled_posts.json"
# Nama file untuk menyimpan FAQ
FAQ_FILE = "faqs.json"

# --- Fungsi Bantuan Penjadwal ---
async def send_message_to_channel(bot: telegram.Bot, chat_id: int, text: str):
    """Mengirim pesan teks ke channel tertentu."""
    try:
        # Menggunakan ParseMode.HTML untuk format teks (bold, italic, link)
        await bot.send_message(chat_id=chat_id, text=text, parse_mode=telegram.constants.ParseMode.HTML)
        print(f"Pesan berhasil dikirim ke channel {chat_id}: {text[:50]}...")
    except telegram.error.TelegramError as e:
        print(f"Gagal mengirim pesan ke channel {chat_id}: {e}")
    except Exception as e:
        print(f"Terjadi error tak terduga saat mengirim pesan: {e}")

def load_schedule():
    """Memuat jadwal konten dari file."""
    if os.path.exists(SCHEDULE_FILE):
        try:
            with open(SCHEDULE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"Error: File {SCHEDULE_FILE} rusak atau kosong. Membuat jadwal baru.")
            return []
    return []

def save_schedule(schedule):
    """Menyimpan jadwal konten ke file."""
    with open(SCHEDULE_FILE, 'w', encoding='utf-8') as f:
        json.dump(schedule, f, indent=4, ensure_ascii=False)

# --- Fungsi Utama Penjadwal ---
async def scheduler_loop():
    """Loop utama untuk memeriksa dan mengirim konten terjadwal."""
    bot = telegram.Bot(token=BOT_TOKEN)
    print("Scheduler berjalan...")

    while True:
        schedule = load_schedule()
        current_time = datetime.datetime.now()
        updated_schedule = []
        
        for post in schedule:
            try:
                scheduled_time = datetime.datetime.fromisoformat(post['time'])
                if current_time >= scheduled_time:
                    await send_message_to_channel(bot, CHANNEL_ID, post['text'])
                else:
                    updated_schedule.append(post)
            except (KeyError, ValueError) as e:
                print(f"Peringatan: Postingan dalam jadwal bermasalah dan dilewati: {post} ({e})")
                
        save_schedule(updated_schedule)
        await asyncio.sleep(60) # Cek setiap 60 detik

# --- Fungsi untuk Menambah Jadwal ---
def add_post_to_schedule(text: str, schedule_datetime: datetime.datetime):
    """Menambahkan postingan baru ke jadwal."""
    schedule = load_schedule()
    schedule.append({
        "text": text,
        "time": schedule_datetime.isoformat()
    })
    save_schedule(schedule)
    print(f"Konten ditambahkan ke jadwal untuk {schedule_datetime}.")

# --- Fungsi untuk FAQ Otomatis ---
def load_faqs():
    """Memuat daftar FAQ dari file JSON."""
    if os.path.exists(FAQ_FILE):
        try:
            with open(FAQ_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"Error: File {FAQ_FILE} rusak atau kosong. Membuat FAQ baru.")
            return []
    return []

def save_faqs(faqs):
    """Menyimpan daftar FAQ ke file JSON."""
    with open(FAQ_FILE, 'w', encoding='utf-8') as f:
        json.dump(faqs, f, indent=4, ensure_ascii=False)

async def handle_faq_query(update: telegram.Update, context):
    """Menangani pertanyaan dari pengguna dan mencari jawaban di FAQ."""
    # Pastikan pesan berasal dari GROUP_ID yang dikonfigurasi
    if update.effective_chat.id != GROUP_ID:
        return # Abaikan pesan dari chat lain

    user_message = update.message.text.lower()
    faqs = load_faqs()

    best_match_response = None
    best_match_score = 0
    
    for faq_item in faqs:
        keywords = [k.lower() for k in faq_item.get('keywords', [])]
        
        current_score = 0
        for keyword in keywords:
            if keyword in user_message:
                current_score += 1
        
        if current_score > best_match_score:
            best_match_score = current_score
            best_match_response = faq_item
    
    if best_match_response:
        answer_text = best_match_response.get('answer')
        image_url = best_match_response.get('image_url')

        if answer_text:
            await update.message.reply_text(answer_text, parse_mode=telegram.constants.ParseMode.HTML)
        
        if image_url:
            try:
                await update.message.reply_photo(photo=image_url)
                print(f"Mengirim gambar dari URL: {image_url}")
            except telegram.error.BadRequest as e:
                print(f"Gagal mengirim foto dari URL '{image_url}': {e}. Pastikan URL valid dan publik.")
            except Exception as e:
                print(f"Terjadi error tak terduga saat mengirim foto: {e}")
        
        print(f"Menjawab FAQ untuk '{user_message[:50]}'")

async def add_faq_command(update: telegram.Update, context):
    """Command untuk menambahkan FAQ baru (hanya untuk admin)."""
    args = context.args
    # Format: /addfaq <keywords_dipisahkan_koma> <jawaban> [--image_url <url_gambar>]
    
    if len(args) < 2:
        await update.message.reply_text("Penggunaan: /addfaq <keywords_dipisahkan_koma> <jawaban> [--image_url <url_gambar>]")
        return

    image_url = None
    if '--image_url' in args:
        try:
            image_url_index = args.index('--image_url')
            image_url = args[image_url_index + 1]
            args = args[:image_url_index] # Hapus bagian --image_url dan URL dari argumen utama
        except IndexError:
            await update.message.reply_text("URL gambar tidak ditemukan setelah --image_url.")
            return

    keywords_str = args[0]
    keywords = [k.strip() for k in keywords_str.split(',')]
    answer = " ".join(args[1:])

    faqs = load_faqs()
    faqs.append({"keywords": keywords, "answer": answer, "image_url": image_url})
    save_faqs(faqs)
    
    response_msg = "FAQ berhasil ditambahkan!"
    if image_url:
        response_msg += f"\nDengan gambar dari: {image_url}"
    
    await update.message.reply_text(response_msg)
    print(f"FAQ ditambahkan: Keywords={keywords}, Answer={answer[:50]}, Image_URL={image_url}")

async def list_faqs_command(update: telegram.Update, context):
    """Command untuk menampilkan daftar FAQ (hanya untuk admin)."""
    faqs = load_faqs()
    if not faqs:
        await update.message.reply_text("Belum ada FAQ yang tersimpan.")
        return
    
    faq_list_text = "<b>Daftar FAQ:</b>\n\n"
    for i, faq_item in enumerate(faqs):
        faq_list_text += f"<b>{i+1}.</b> <b>Keyword(s):</b> {', '.join(faq_item.get('keywords', ['-']))}\n"
        faq_list_text += f"   <b>Jawaban:</b> {faq_item.get('answer', '-')[:100]}...\n"
        if faq_item.get('image_url'):
            faq_list_text += f"   <b>Gambar:</b> <a href='{faq_item.get('image_url')}'>Link Gambar</a>\n"
        faq_list_text += "\n"
    
    await update.message.reply_text(faq_list_text, parse_mode=telegram.constants.ParseMode.HTML)


# --- Eksekusi Utama ---
async def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # --- Setup Penjadwalan Konten (Berjalan di background) ---
    # Anda bisa mengaktifkan contoh penjadwalan di sini jika ingin menguji saat bot dijalankan
    # time_2_min_from_now = datetime.datetime.now() + datetime.timedelta(minutes=2)
    # add_post_to_schedule("🌟 Penawaran Spesial: Dapatkan diskon <b>15%</b> untuk 2000 followers TikTok hari ini! Buruan sebelum kehabisan!", time_2_min_from_now)

    # time_5_min_from_now = datetime.datetime.now() + datetime.timedelta(minutes=5)
    # add_post_to_schedule("⚡️ Buktikan Sendiri! Ratusan pelanggan sudah puas dengan layanan followers kami. Kunjungi channel untuk info lebih lanjut!", time_5_min_from_now)

    asyncio.create_task(scheduler_loop())

    # --- Setup FAQ Otomatis (Untuk Grup Diskusi) ---
    # Handler untuk pesan teks biasa di grup (bukan command)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.Chat(GROUP_ID), handle_faq_query))
    
    # Handler untuk command admin
    application.add_handler(CommandHandler("addfaq", add_faq_command))
    application.add_handler(CommandHandler("listfaqs", list_faqs_command))

    print("Bot Telegram berjalan (siap menerima pesan dan command)...")
    await application.run_polling(allowed_updates=telegram.Update.ALL_TYPES)

if __name__ == "__main__":
    asyncio.run(main())

