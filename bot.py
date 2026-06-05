"""
Bot Telegram Laporan Harian
============================
Perintah:
  /mulai         - Mulai sesi laporan baru
  /laporan       - Isi laporan harian (interaktif)
  /rekap         - Rekap laporan hari ini
  /rekap_minggu  - Rekap 7 hari terakhir
  /rekap_bulan   - Rekap bulan ini
  /export        - Export rekap ke file teks
  /hapus         - Hapus laporan hari ini
  /bantuan       - Tampilkan menu bantuan
"""

import logging
import sqlite3
import os
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ConversationHandler, ContextTypes, filters
)

# ── Konfigurasi ──────────────────────────────────────────────
BOT_TOKEN = "8677071742:AAF8jOFBbIT23JRreALUYhZLTuYFz4OfFQU"  # Dari @BotFather
DB_FILE   = "laporan.db"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── State Conversation ────────────────────────────────────────
(NAMA, PEKERJAAN, MEETING, TARGET, HAMBATAN, RENCANA, KONFIRMASI) = range(7)

PERTANYAAN = {
    PEKERJAAN : ("💼 Pekerjaan selesai hari ini?\n\nContoh: Finalisasi laporan Q2, review proposal klien A", "pekerjaan"),
    MEETING   : ("📅 Meeting / rapat hari ini?\n\nContoh: Rapat tim jam 10:00 - 11:00, review dengan manager\n\n(ketik '-' jika tidak ada)", "meeting"),
    TARGET    : ("🎯 Progress target / pencapaian?\n\nContoh: Target bulanan 85% tercapai, 3 dari 5 task selesai", "target"),
    HAMBATAN  : ("⚠️ Hambatan / kendala hari ini?\n\nContoh: Dokumen dari vendor belum masuk\n\n(ketik '-' jika tidak ada)", "hambatan"),
    RENCANA   : ("📋 Rencana kerja besok?\n\nContoh: Follow up proposal klien B, meeting dengan divisi HRD", "rencana"),
}

# ── Database ──────────────────────────────────────────────────
def init_db():
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS laporan (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            username   TEXT,
            nama       TEXT,
            tanggal    TEXT NOT NULL,
            pekerjaan  TEXT,
            meeting    TEXT,
            target     TEXT,
            hambatan   TEXT,
            rencana    TEXT,
            dibuat_at  TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    con.commit()
    con.close()

def simpan_laporan(user_id, username, nama, tanggal, data: dict):
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute("""
        INSERT INTO laporan (user_id, username, nama, tanggal, pekerjaan, meeting, target, hambatan, rencana)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (user_id, username, nama, tanggal,
          data.get("pekerjaan"), data.get("meeting"),
          data.get("target"),    data.get("hambatan"),
          data.get("rencana")))
    con.commit()
    con.close()

def hapus_laporan_hari_ini(user_id, tanggal):
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute("DELETE FROM laporan WHERE user_id=? AND tanggal=?", (user_id, tanggal))
    rows = cur.rowcount
    con.commit()
    con.close()
    return rows

def ambil_laporan(user_id, tanggal_mulai, tanggal_akhir):
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute("""
        SELECT nama, tanggal, pekerjaan, meeting, target, hambatan, rencana, dibuat_at
        FROM laporan
        WHERE user_id=? AND tanggal BETWEEN ? AND ?
        ORDER BY tanggal ASC, dibuat_at ASC
    """, (user_id, tanggal_mulai, tanggal_akhir))
    rows = cur.fetchall()
    con.close()
    return rows

# ── Helper ────────────────────────────────────────────────────
def tgl_sekarang(): return datetime.now().strftime("%Y-%m-%d")
def tgl_label(tgl): 
    d = datetime.strptime(tgl, "%Y-%m-%d")
    return d.strftime("%A, %d %B %Y")

def format_laporan_singkat(row):
    nama, tgl, pkj, mtg, tgt, hmb, rnc, _ = row
    baris = [f"📅 *{tgl_label(tgl)}*  |  👤 {nama}"]
    if pkj: baris.append(f"💼 *Pekerjaan:* {pkj}")
    if mtg and mtg != "-": baris.append(f"📅 *Meeting:* {mtg}")
    if tgt: baris.append(f"🎯 *Target:* {tgt}")
    if hmb and hmb != "-": baris.append(f"⚠️ *Hambatan:* {hmb}")
    if rnc: baris.append(f"📋 *Rencana Besok:* {rnc}")
    return "\n".join(baris)

def format_rekap(rows, judul):
    if not rows:
        return f"📭 Belum ada laporan untuk *{judul}*."
    
    teks = [f"📊 *REKAP {judul.upper()}*\n{'─'*30}"]
    for row in rows:
        teks.append(format_laporan_singkat(row))
        teks.append("─" * 20)
    teks.append(f"✅ Total: *{len(rows)} laporan*")
    return "\n".join(teks)

def format_export(rows, judul):
    if not rows:
        return f"Belum ada laporan untuk {judul}."
    lines = [f"REKAP {judul.upper()}", "=" * 40, ""]
    for row in rows:
        nama, tgl, pkj, mtg, tgt, hmb, rnc, dibuat = row
        lines += [
            f"Tanggal   : {tgl_label(tgl)}",
            f"Pelapor   : {nama}",
            f"Pekerjaan : {pkj or '-'}",
            f"Meeting   : {mtg or '-'}",
            f"Target    : {tgt or '-'}",
            f"Hambatan  : {hmb or '-'}",
            f"Rencana   : {rnc or '-'}",
            f"Dicatat   : {dibuat}",
            "-" * 40, ""
        ]
    lines.append(f"Total: {len(rows)} laporan")
    return "\n".join(lines)

# ── Handlers ──────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Selamat datang di Bot Laporan Harian!*\n\n"
        "Bot ini membantu kamu mencatat dan merekap laporan kerja harian.\n\n"
        "🚀 Ketik /laporan untuk mulai mengisi laporan\n"
        "📊 Ketik /rekap untuk melihat rekap hari ini\n"
        "❓ Ketik /bantuan untuk semua perintah",
        parse_mode="Markdown"
    )

async def bantuan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *PANDUAN BOT LAPORAN HARIAN*\n\n"
        "➕ *Mengisi Laporan*\n"
        "/laporan - Isi laporan harian baru\n\n"
        "📊 *Melihat Rekap*\n"
        "/rekap - Rekap hari ini\n"
        "/rekap\\_minggu - Rekap 7 hari terakhir\n"
        "/rekap\\_bulan - Rekap bulan ini\n\n"
        "📁 *Lainnya*\n"
        "/export - Export rekap ke file .txt\n"
        "/hapus - Hapus laporan hari ini\n"
        "/bantuan - Tampilkan menu ini\n\n"
        "💡 *Tips:* Isi laporan setiap akhir hari kerja untuk rekap yang akurat!",
        parse_mode="Markdown"
    )

# ── Conversation: Isi Laporan ─────────────────────────────────
async def laporan_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    ctx.user_data["tanggal"] = tgl_sekarang()
    
    # Ambil nama dari username jika sudah pernah laporan
    user_id = update.effective_user.id
    rows = ambil_laporan(user_id, tgl_sekarang(), tgl_sekarang())
    
    if rows:
        # Tanya apakah mau tambah atau timpa
        keyboard = [
            [InlineKeyboardButton("➕ Tambah laporan baru", callback_data="tambah")],
            [InlineKeyboardButton("❌ Batalkan", callback_data="batal")],
        ]
        await update.message.reply_text(
            f"⚠️ Kamu sudah punya *{len(rows)} laporan* hari ini.\n"
            "Mau menambah laporan baru?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return KONFIRMASI

    await update.message.reply_text(
        f"📝 *LAPORAN HARIAN*\n📅 {tgl_label(tgl_sekarang())}\n\n"
        "Halo! Pertama, siapa nama kamu?\n\n_Contoh: Budi Santoso_",
        parse_mode="Markdown"
    )
    return NAMA

async def konfirmasi_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "batal":
        await query.edit_message_text("❌ Dibatalkan. Ketik /laporan kapan saja untuk mengisi laporan.")
        return ConversationHandler.END
    # tambah
    await query.edit_message_text(
        f"📝 *LAPORAN HARIAN BARU*\n📅 {tgl_label(tgl_sekarang())}\n\n"
        "Siapa nama kamu?",
        parse_mode="Markdown"
    )
    return NAMA

async def terima_nama(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["nama"] = update.message.text.strip()
    q, _ = PERTANYAAN[PEKERJAAN]
    await update.message.reply_text(f"✅ Halo, *{ctx.user_data['nama']}*!\n\n{q}", parse_mode="Markdown")
    return PEKERJAAN

async def buat_handler_poin(state_sekarang, state_berikut):
    async def handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        _, key = PERTANYAAN[state_sekarang]
        ctx.user_data[key] = update.message.text.strip()
        if state_berikut in PERTANYAAN:
            q, _ = PERTANYAAN[state_berikut]
            await update.message.reply_text(q, parse_mode="Markdown")
            return state_berikut
        else:
            return await tampilkan_preview(update, ctx)
    return handler

async def tampilkan_preview(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    _, key = PERTANYAAN[RENCANA]
    ctx.user_data[key] = update.message.text.strip()
    d = ctx.user_data
    preview = (
        f"📋 *PREVIEW LAPORAN*\n"
        f"{'─'*28}\n"
        f"👤 *Nama:* {d.get('nama')}\n"
        f"📅 *Tanggal:* {tgl_label(d.get('tanggal',''))}\n"
        f"{'─'*28}\n"
        f"💼 *Pekerjaan:*\n{d.get('pekerjaan','-')}\n\n"
        f"📅 *Meeting:*\n{d.get('meeting','-')}\n\n"
        f"🎯 *Target:*\n{d.get('target','-')}\n\n"
        f"⚠️ *Hambatan:*\n{d.get('hambatan','-')}\n\n"
        f"📋 *Rencana Besok:*\n{d.get('rencana','-')}\n"
        f"{'─'*28}"
    )
    keyboard = [
        [InlineKeyboardButton("✅ Simpan Laporan", callback_data="simpan")],
        [InlineKeyboardButton("🔄 Isi Ulang", callback_data="ulang")],
        [InlineKeyboardButton("❌ Batalkan", callback_data="batal")],
    ]
    await update.message.reply_text(preview, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    return KONFIRMASI

async def simpan_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "batal":
        await query.edit_message_text("❌ Laporan dibatalkan.")
        return ConversationHandler.END
    
    if query.data == "ulang":
        await query.edit_message_text("🔄 Oke, mulai lagi dari awal...")
        await query.message.reply_text(
            "Siapa nama kamu?", parse_mode="Markdown"
        )
        ctx.user_data.clear()
        ctx.user_data["tanggal"] = tgl_sekarang()
        return NAMA
    
    if query.data == "simpan":
        d = ctx.user_data
        user = query.from_user
        simpan_laporan(
            user.id, user.username or "", d.get("nama", ""),
            d.get("tanggal", tgl_sekarang()),
            {k: d.get(k) for k in ("pekerjaan","meeting","target","hambatan","rencana")}
        )
        await query.edit_message_text(
            "✅ *Laporan berhasil disimpan!*\n\n"
            "📊 Ketik /rekap untuk melihat rekap hari ini\n"
            "📁 Ketik /export untuk export ke file",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Pengisian laporan dibatalkan.")
    return ConversationHandler.END

# ── Rekap ─────────────────────────────────────────────────────
async def rekap_hari(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    tgl  = tgl_sekarang()
    rows = ambil_laporan(uid, tgl, tgl)
    await update.message.reply_text(format_rekap(rows, f"Hari Ini ({tgl_label(tgl)})"), parse_mode="Markdown")

async def rekap_minggu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid   = update.effective_user.id
    akhir = tgl_sekarang()
    mulai = (datetime.now() - timedelta(days=6)).strftime("%Y-%m-%d")
    rows  = ambil_laporan(uid, mulai, akhir)
    await update.message.reply_text(format_rekap(rows, "7 Hari Terakhir"), parse_mode="Markdown")

async def rekap_bulan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid   = update.effective_user.id
    now   = datetime.now()
    mulai = now.strftime("%Y-%m-01")
    akhir = tgl_sekarang()
    rows  = ambil_laporan(uid, mulai, akhir)
    label = now.strftime("%B %Y")
    await update.message.reply_text(format_rekap(rows, label), parse_mode="Markdown")

async def export_laporan(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid   = update.effective_user.id
    now   = datetime.now()
    mulai = now.strftime("%Y-%m-01")
    akhir = tgl_sekarang()
    rows  = ambil_laporan(uid, mulai, akhir)
    label = now.strftime("%B %Y")
    isi   = format_export(rows, label)
    nama_file = f"laporan_{now.strftime('%Y_%m')}.txt"
    with open(nama_file, "w", encoding="utf-8") as f:
        f.write(isi)
    with open(nama_file, "rb") as f:
        await update.message.reply_document(
            document=f, filename=nama_file,
            caption=f"📁 Rekap laporan {label} — {len(rows)} entri"
        )
    os.remove(nama_file)

async def hapus_hari_ini(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    tgl = tgl_sekarang()
    keyboard = [
        [InlineKeyboardButton("🗑️ Ya, hapus", callback_data=f"hapus_{tgl}")],
        [InlineKeyboardButton("❌ Batalkan", callback_data="batal_hapus")],
    ]
    await update.message.reply_text(
        f"⚠️ Yakin hapus semua laporan hari ini (*{tgl_label(tgl)}*)?",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown"
    )

async def hapus_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("hapus_"):
        tgl = query.data.replace("hapus_", "")
        n   = hapus_laporan_hari_ini(query.from_user.id, tgl)
        await query.edit_message_text(f"🗑️ {n} laporan hari ini berhasil dihapus.")
    else:
        await query.edit_message_text("❌ Penghapusan dibatalkan.")

# ── Main ──────────────────────────────────────────────────────
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    # Handler conversation isi laporan
    handler_poin = [
        buat_handler_poin(PEKERJAAN, MEETING),
        buat_handler_poin(MEETING, TARGET),
        buat_handler_poin(TARGET, HAMBATAN),
        buat_handler_poin(HAMBATAN, RENCANA),
    ]

    import asyncio
    handlers_resolved = [asyncio.get_event_loop().run_until_complete(h) if asyncio.iscoroutine(h) else h for h in handler_poin]

    # Buat handler secara langsung
    async def h_pekerjaan(u, c):
        _, key = PERTANYAAN[PEKERJAAN]; c.user_data[key] = u.message.text.strip()
        q, _ = PERTANYAAN[MEETING]; await u.message.reply_text(q, parse_mode="Markdown"); return MEETING
    async def h_meeting(u, c):
        _, key = PERTANYAAN[MEETING]; c.user_data[key] = u.message.text.strip()
        q, _ = PERTANYAAN[TARGET]; await u.message.reply_text(q, parse_mode="Markdown"); return TARGET
    async def h_target(u, c):
        _, key = PERTANYAAN[TARGET]; c.user_data[key] = u.message.text.strip()
        q, _ = PERTANYAAN[HAMBATAN]; await u.message.reply_text(q, parse_mode="Markdown"); return HAMBATAN
    async def h_hambatan(u, c):
        _, key = PERTANYAAN[HAMBATAN]; c.user_data[key] = u.message.text.strip()
        q, _ = PERTANYAAN[RENCANA]; await u.message.reply_text(q, parse_mode="Markdown"); return RENCANA

    conv = ConversationHandler(
        entry_points=[CommandHandler("laporan", laporan_start)],
        states={
            NAMA      : [MessageHandler(filters.TEXT & ~filters.COMMAND, terima_nama)],
            PEKERJAAN : [MessageHandler(filters.TEXT & ~filters.COMMAND, h_pekerjaan)],
            MEETING   : [MessageHandler(filters.TEXT & ~filters.COMMAND, h_meeting)],
            TARGET    : [MessageHandler(filters.TEXT & ~filters.COMMAND, h_target)],
            HAMBATAN  : [MessageHandler(filters.TEXT & ~filters.COMMAND, h_hambatan)],
            RENCANA   : [MessageHandler(filters.TEXT & ~filters.COMMAND, tampilkan_preview)],
            KONFIRMASI: [CallbackQueryHandler(simpan_callback, pattern="^(simpan|ulang|batal|tambah)$"),
                         CallbackQueryHandler(konfirmasi_callback, pattern="^(tambah|batal)$")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("start",        start))
    app.add_handler(CommandHandler("mulai",        start))
    app.add_handler(CommandHandler("bantuan",      bantuan))
    app.add_handler(CommandHandler("rekap",        rekap_hari))
    app.add_handler(CommandHandler("rekap_minggu", rekap_minggu))
    app.add_handler(CommandHandler("rekap_bulan",  rekap_bulan))
    app.add_handler(CommandHandler("export",       export_laporan))
    app.add_handler(CommandHandler("hapus",        hapus_hari_ini))
    app.add_handler(CallbackQueryHandler(hapus_callback, pattern="^(hapus_|batal_hapus)"))

    print("🤖 Bot Laporan Harian aktif...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
