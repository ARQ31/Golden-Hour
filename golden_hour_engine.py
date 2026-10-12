"""Golden Hour: Live Scam Attack - Game Engine (Langflow custom component).

Deterministik: skor, pengacakan pilihan, dan kunci jawaban dihitung
di kode. Tidak ada LLM dan tidak ada kunci jawaban di prompt.
"""

import hashlib
import json
import os
import random
import re
import secrets
import tempfile
import threading
import time
import urllib.request

from lfx.custom.custom_component.component import Component
from lfx.io import DropdownInput, MessageTextInput, Output, SecretStrInput
from lfx.schema.message import Message


DISCLAIMER = "Ini simulasi pelatihan. Semua nama dan nomor dalam cerita adalah fiktif."

SCORE_GAIN = {"BEST": 10, "OK": 5, "RISKY": 0}
LABEL = {"BEST": "TEPAT", "OK": "AMAN TAPI BELUM CUKUP", "RISKY": "BERISIKO"}

# Format: opsi = (teks, nilai). Urutan di sini TIDAK dipakai pemain (diacak).
SCRIPT = {
    "bank": {
        "title": "Telepon dari CS Bank",
        "player": "Kamu berperan sebagai Rina, 29 tahun, karyawan swasta.",
        "steps": [
            {
                "sender": "CS Bank Nusantara Raya (nomor WhatsApp pribadi)",
                "text": "Selamat siang Bu Rina. Kami mendeteksi transaksi Rp8.500.000 ke Batam dari kartu Ibu. Jika bukan Ibu, balas YA agar kartu segera kami blokir. Layanan ini hanya berlaku 15 menit.",
                "options": [
                    ("Balas YA supaya kartu diblokir.", "RISKY"),
                    ("Telepon nomor yang tertera di pesan itu.", "RISKY"),
                    ("Buka aplikasi bank resmi dan cek mutasi sendiri.", "BEST"),
                    ("Abaikan pesan dan tidak melakukan apa-apa.", "OK"),
                ],
                "lesson": "Pesan dari nomor pribadi yang menekan dengan batas waktu. Cek lewat aplikasi resmi atau nomor di belakang kartu, bukan nomor di pesan.",
                "flags": ["Dikirim dari nomor pribadi", "Batas waktu yang menekan", "Meminta balasan cepat"],
            },
            {
                "sender": "Pak Dedi, Bagian Keamanan Bank (telepon)",
                "text": "Ibu Rina, saya Pak Dedi dari bagian keamanan. Untuk membatalkan transaksi tadi, sebutkan kode OTP yang baru masuk ke HP Ibu. Kalau tidak, dana akan terdebet dalam 5 menit.",
                "options": [
                    ("Sebutkan OTP karena takut dana hilang.", "RISKY"),
                    ("Minta nomor pegawai, lalu beri OTP kalau terdengar meyakinkan.", "RISKY"),
                    ("Tutup telepon, tidak beri OTP, lalu hubungi call center resmi di belakang kartu.", "BEST"),
                    ("Tutup telepon dan tidak melakukan apa-apa lagi.", "OK"),
                ],
                "lesson": "OTP itu rahasia. Bank asli tidak pernah memintanya, dan nomor pegawai bisa dikarang penipu.",
                "flags": ["Meminta kode OTP", "Ancaman dana terdebet", "Nomor pegawai mudah dikarang"],
            },
            {
                "sender": "Pak Dedi (telepon lagi)",
                "text": "Sistem kami mendeteksi rekening Ibu sedang diretas. Untuk keamanan, pindahkan seluruh saldo ke rekening aman atas nama Bank Nusantara Raya, nomor 0000-1111-2222. Batas waktu 10 menit.",
                "options": [
                    ("Pindahkan seluruh saldo ke rekening aman.", "RISKY"),
                    ("Pindahkan sebagian saja untuk jaga-jaga.", "RISKY"),
                    ("Tolak, simpan bukti, lalu lapor ke IASC (iasc.ojk.go.id) dan call center resmi bank.", "BEST"),
                    ("Blokir nomor itu saja.", "OK"),
                ],
                "lesson": "Rekening aman itu tidak ada. Permintaan transfer dengan tekanan waktu adalah tanda penipuan.",
                "flags": ["Disuruh transfer ke rekening aman", "Tekanan waktu", "Penelepon yang sama terus menghubungi"],
            },
        ],
    },
    "job": {
        "title": "Tawaran Kerja Online",
        "player": "Kamu berperan sebagai Dimas, 22 tahun, lulusan baru.",
        "steps": [
            {
                "sender": "Rekrutmen PT Karya Maju Digital (WhatsApp)",
                "text": "Halo Dimas! CV kamu lolos untuk kerja part-time review produk. Gaji Rp300.000 per hari, kerja dari HP. Hubungi admin kami di Telegram @karyamaju_hr sekarang, slot terbatas.",
                "options": [
                    ("Langsung chat admin di Telegram.", "RISKY"),
                    ("Cari perusahaannya di situs resmi, cek alamat dan kontak HR sebelum membalas.", "BEST"),
                    ("Tanya teman yang pernah kerja serupa.", "OK"),
                    ("Kirim CV dan foto KTP supaya cepat diproses.", "RISKY"),
                ],
                "lesson": "Lowongan yang datang sendiri, gaji besar untuk kerja mudah, dan pindah ke Telegram adalah tanda bahaya. Cek perusahaannya dulu.",
                "flags": ["Lowongan datang tanpa melamar", "Gaji besar untuk kerja mudah", "Diminta pindah ke Telegram"],
            },
            {
                "sender": "Admin Karya Maju (Telegram)",
                "text": "Tugas pertama selesai! Ini bayaran Rp50.000 untuk kamu. Untuk lanjut ke tugas VIP dengan komisi 30%, top up Rp200.000 dulu. Uangnya kembali lengkap beserta komisi.",
                "options": [
                    ("Top up Rp200.000 supaya bisa lanjut ke tugas VIP.", "RISKY"),
                    ("Top up Rp50.000 saja sebagai uji coba.", "RISKY"),
                    ("Berhenti, tidak kirim uang, dan simpan bukti chat.", "BEST"),
                    ("Tanya dulu apakah saldo bisa ditarik tanpa top up.", "OK"),
                ],
                "lesson": "Bayaran kecil di awal dipakai untuk membangun kepercayaan. Pekerjaan asli tidak meminta setoran uang.",
                "flags": ["Diminta setor uang untuk bekerja", "Bayaran awal sebagai pancingan", "Janji uang kembali plus komisi"],
            },
            {
                "sender": "Admin Karya Maju (Telegram)",
                "text": "Selamat, saldo komisi kamu Rp4.800.000! Penarikan terkunci karena akun belum terverifikasi. Bayar biaya verifikasi Rp600.000 hari ini, kalau tidak akun diblokir dan saldo hangus.",
                "options": [
                    ("Bayar biaya verifikasi supaya uang cair.", "RISKY"),
                    ("Pinjam uang ke teman untuk membayar biaya verifikasi.", "RISKY"),
                    ("Tidak bayar, laporkan ke IASC, dan beri tahu teman tentang modus ini.", "BEST"),
                    ("Tidak bayar dan diam saja.", "OK"),
                ],
                "lesson": "Biaya baru akan terus muncul sampai korban berhenti. Saldo atau bonus yang dijanjikan itu palsu.",
                "flags": ["Biaya verifikasi mendadak", "Ancaman akun diblokir", "Uang besar yang muncul tiba-tiba"],
            },
        ],
    },
    "apk": {
        "title": "Undangan Pernikahan APK",
        "player": "Kamu berperan sebagai Bu Sari, 52 tahun, ibu rumah tangga.",
        "steps": [
            {
                "sender": "Nomor tak dikenal (WhatsApp)",
                "text": "Assalamualaikum Bu, kami mengundang Ibu ke pernikahan putri kami. Silakan unduh undangan digital di sini: undangan-nikah-rani.apk. Terima kasih.",
                "options": [
                    ("Unduh dan buka karena tidak enak hati.", "RISKY"),
                    ("Balas dan tanya siapa pengirimnya.", "OK"),
                    ("Telepon kerabat yang mungkin mengenal pengirim, dan tidak memasang file apa pun.", "BEST"),
                    ("Teruskan ke grup keluarga supaya ikut lihat.", "RISKY"),
                ],
                "lesson": "Undangan sungguhan bukan file APK. APK dari nomor tak dikenal bisa membaca SMS dan OTP.",
                "flags": ["Pengirim tidak dikenal", "Undangan berupa file APK", "Rasa sungkan dimanfaatkan"],
            },
            {
                "sender": "Nomor tak dikenal (WhatsApp)",
                "text": "Bu, undangannya belum terbuka ya? Aplikasinya perlu izin pasang dari sumber tidak dikenal dan akses SMS supaya tampil. Tinggal izinkan saja, aman kok.",
                "options": [
                    ("Aktifkan izin dan pasang aplikasinya.", "RISKY"),
                    ("Pasang aplikasi tapi tidak beri akses SMS.", "RISKY"),
                    ("Tolak, minta undangan dikirim sebagai foto atau tautan biasa.", "BEST"),
                    ("Hapus pesan dan tidak membalas.", "OK"),
                ],
                "lesson": "Undangan tidak butuh izin SMS. Izin itu dipakai untuk mencuri kode OTP.",
                "flags": ["Izin pasang dari sumber tidak dikenal", "Minta akses SMS", "Meyakinkan bahwa aman"],
            },
            {
                "sender": "Nomor tak dikenal (WhatsApp)",
                "text": "Bu, undangannya masih belum tampil di HP Ibu ya. Coba pasang dari tautan baru yang kami kirim ulang, atau kirim saja foto KTP dan nomor HP Ibu, biar kami bantu pasangkan.",
                "options": [
                    ("Kirim foto KTP supaya dibantu.", "RISKY"),
                    ("Pasang dari tautan baru yang dikirim ulang.", "RISKY"),
                    ("Blokir nomor, laporkan ke IASC, dan beri tahu keluarga tentang modus undangan APK.", "BEST"),
                    ("Blokir nomor saja.", "OK"),
                ],
                "lesson": "Permintaan makin besar setiap langkah. Foto KTP bisa dipakai untuk pinjaman atas nama korban.",
                "flags": ["Minta foto KTP", "Permintaan makin besar", "Menawarkan bantuan memasang"],
            },
        ],
    },
}

# Cabang cerita: pesan langkah 2 dan 3 menyesuaikan hasil jawaban sebelumnya.
# bridge = kejadian yang terjadi akibat jawaban itu. text/sender kosong = pakai skrip asli.
_BANK2_RES = "Ibu Rina, saya Pak Dedi dari bagian keamanan. Transaksi ke Batam masih tertahan dan belum tampil di mutasi. Untuk membatalkannya, sebutkan kode OTP yang baru masuk ke HP Ibu. Kalau tidak, dana akan terdebet dalam 5 menit."
_BANK3_RES = "Ibu Rina, rekening Ibu sedang diretas dan tidak bisa menunggu. Jangan hubungi call center dulu. Pindahkan seluruh saldo ke rekening aman atas nama Bank Nusantara Raya, nomor 0000-1111-2222. Batas waktu 10 menit."
_JOB2_RES = "Halo Dimas, slot kerjamu masih kami tahan. Tugas percobaan kamu kami anggap selesai, ini bayaran Rp50.000. Untuk lanjut ke tugas VIP dengan komisi 30%, top up Rp200.000 dulu. Uangnya kembali lengkap beserta komisi."
_JOB3_RES = "Dimas, akun kerjamu masih aktif dan ada bonus Rp4.800.000 yang menunggu. Bonus hanya bisa cair setelah akun diverifikasi. Bayar biaya verifikasi Rp600.000 hari ini, kalau tidak akun diblokir dan bonus hangus."
_APK2_RES = "Bu, undangannya sudah dibuka belum ya? Kalau belum bisa, aplikasinya perlu izin pasang dari sumber tidak dikenal dan akses SMS supaya tampil. Tinggal izinkan saja, aman kok."

BRANCH = {
    "bank": {
        2: {
            "RISKY": {"bridge": "Kamu merespons pesan itu. Tidak lama kemudian, ada telepon masuk dari nomor yang sama."},
            "OK": {"bridge": "Kamu mengabaikan pesan itu, tetapi nomor yang sama langsung meneleponmu.", "text": _BANK2_RES},
            "BEST": {"bridge": "Kamu mengecek aplikasi resmi dan tidak melihat transaksi mencurigakan. Namun nomor yang tadi mengirim pesan malah meneleponmu.", "text": _BANK2_RES},
        },
        3: {
            "RISKY": {"bridge": "Kamu sudah menyebutkan kode OTP. Tidak lama kemudian, Pak Dedi menelepon lagi dengan nada lebih mendesak."},
            "OK": {"bridge": "Kamu menutup telepon dan tidak melakukan apa-apa lagi. Pak Dedi menelepon lagi dari nomor yang sama.", "text": _BANK3_RES},
            "BEST": {"bridge": "Call center resmi bank memastikan tidak ada masalah di rekeningmu. Tetapi nomor yang tadi menelepon menghubungimu lagi.", "text": _BANK3_RES},
        },
    },
    "job": {
        2: {
            "RISKY": {"bridge": "Kamu merespons tawaran itu, dan admin langsung memberimu tugas pertama yang segera kamu selesaikan."},
            "OK": {"bridge": "Temanmu tidak mengenal perusahaan itu. Namun admin sudah lebih dulu menghubungimu lagi.", "sender": "Admin Karya Maju", "text": _JOB2_RES},
            "BEST": {"bridge": "Kamu mengecek perusahaan di situs resminya dan tidak menemukan lowongan itu. Namun admin tetap menghubungimu lagi.", "sender": "Admin Karya Maju", "text": _JOB2_RES},
        },
        3: {
            "RISKY": {"bridge": "Uang top up sudah kamu kirim. Admin lalu menunjukkan saldo komisimu bertambah di aplikasi mereka."},
            "OK": {"bridge": "Admin menjawab bahwa penarikan harus lewat top up, lalu terus mengirim pesan.", "sender": "Admin Karya Maju", "text": _JOB3_RES},
            "BEST": {"bridge": "Kamu berhenti dan menyimpan bukti chat. Admin tidak menyerah dan mengirim pesan lagi.", "sender": "Admin Karya Maju", "text": _JOB3_RES},
        },
    },
    "apk": {
        2: {
            "RISKY": {"bridge": "Kamu menanggapi file undangan itu. Tidak lama kemudian, nomor yang sama mengirim pesan lagi."},
            "OK": {"bridge": "Kamu menanyakan siapa pengirimnya, tetapi tidak dijawab dengan jelas. Pengirim malah mengirim pesan lagi.", "text": _APK2_RES},
            "BEST": {"bridge": "Kerabatmu tidak mengenal pengirim itu dan kamu tidak memasang apa pun. Namun nomor tak dikenal itu mengirim pesan lagi.", "text": _APK2_RES},
        },
        3: {
            "RISKY": {"bridge": "Kamu sudah mengikuti petunjuk pemasangan, tetapi undangan tidak juga tampil. Pesan baru pun masuk."},
            "OK": {"bridge": "Kamu menghapus pesan itu dan tidak membalas, tetapi nomor yang sama mengirim pesan lagi."},
            "BEST": {"bridge": "Kamu meminta undangan dikirim sebagai foto atau tautan biasa. Pengirim tidak memenuhinya dan terus mendesakmu."},
        },
    },
}


# Saldo cerita. "loss" sejajar dengan urutan opsi di SCRIPT (A,B,C,D versi skrip).
# Kerugian hanya berlaku untuk jawaban BERISIKO dan tidak bisa melebihi saldo.
ECON = {
    "bank": {
        "owner": "Rina",
        "saldo": 15000000,
        "steps": [
            {"loss": [2000000, 2000000, 0, 0], "note": "Penipu mengambil alih percakapan dan menguras sebagian saldo."},
            {"loss": [5000000, 5000000, 0, 0], "note": "Kode OTP dipakai penipu untuk memindahkan dana dari rekeningmu."},
            {"loss": [8000000, 3000000, 0, 0], "note": "Dana kamu pindahkan sendiri ke rekening penipu."},
        ],
    },
    "job": {
        "owner": "Dimas",
        "saldo": 1000000,
        "steps": [
            {"loss": [0, 0, 0, 0], "note": ""},
            {"loss": [200000, 50000, 0, 0], "note": "Uang yang kamu setor langsung masuk ke rekening penipu."},
            {"loss": [600000, 600000, 0, 0], "note": "Biaya verifikasi hilang, dan penipu akan terus meminta biaya baru."},
        ],
    },
    "apk": {
        "owner": "Bu Sari",
        "saldo": 10000000,
        "steps": [
            {"loss": [1000000, 0, 0, 0], "note": "Aplikasi berbahaya terpasang dan mulai membaca SMS-mu."},
            {"loss": [6000000, 2000000, 0, 0], "note": "Izin SMS dipakai untuk mencuri kode OTP dan menguras saldo."},
            {"loss": [3000000, 3000000, 0, 0], "note": "Data KTP dan akses HP dipakai untuk menyedot dana dan membuat pinjaman atas namamu."},
        ],
    },
}


def _rp(n):
    return "Rp" + f"{n:,}".replace(",", ".")


def _hash_pin(pin: str, salt: str) -> str:
    """Hash PIN satu arah dengan salt per-user (sha256). PIN asli tidak disimpan."""
    return hashlib.sha256((salt + pin).encode("utf-8")).hexdigest()


def _verify_pin(pin: str, salt: str, stored_hash: str) -> bool:
    return _hash_pin(pin, salt) == stored_hash


RANKS = [(30, "Apex Untouchable"), (20, "Scam Hunter"), (10, "Firewall Aegis"), (0, "Alert Citizen")]
CUMULATIVE_RANKS = [(90, "Apex Untouchable"), (60, "Scam Hunter"), (30, "Firewall Aegis"), (0, "Alert Citizen")]


def _cumulative_rank(score):
    for minimum, name in CUMULATIVE_RANKS:
        if score >= minimum:
            return name
    return CUMULATIVE_RANKS[-1][1]


TIPS = {
    "bank": [
        "Bank tidak pernah meminta OTP atau PIN, kepada siapa pun.",
        "Cek lewat aplikasi resmi atau nomor di belakang kartu, bukan nomor yang dikirim lewat pesan.",
        "Tidak ada rekening aman. Jangan transfer atas permintaan telepon atau pesan.",
    ],
    "job": [
        "Cek perusahaan lewat situs resmi dan kontak HR sebelum membalas lowongan.",
        "Pekerjaan asli tidak meminta setoran, top up, atau biaya verifikasi.",
        "Jangan kirim KTP atau data pribadi ke perekrut yang belum terverifikasi.",
    ],
    "apk": [
        "Jangan pasang file APK dari pengirim yang tidak dikenal.",
        "Undangan digital tidak butuh izin SMS atau akses lain di HP.",
        "Jangan kirim foto KTP atau data pribadi lewat chat ke orang tak dikenal.",
    ],
}
REPORT_TIP = "Lapor ke IASC di iasc.ojk.go.id atau OJK 157 jika menemui penipuan."

SUMMARY = {
    "bank": (
        "Kamu tidak memberi OTP dan tidak memindahkan uang, walau ditekan batas waktu.",
        "Kamu sudah mengenali sebagian modus, tapi masih ada langkah yang membuat dana terancam.",
        "Banyak jebakan yang belum dikenali. Ingat: bank asli tidak meminta OTP atau transfer ke rekening aman.",
    ),
    "job": (
        "Kamu mengecek perusahaan dan menolak setoran uang, tanpa memberi data pribadi.",
        "Kamu sudah mengenali sebagian tanda lowongan palsu, tapi masih ada langkah yang membuat uang atau datamu terancam.",
        "Banyak jebakan yang belum dikenali. Waspadai gaji besar untuk kerja mudah, pindah ke Telegram, dan permintaan top up.",
    ),
    "apk": (
        "Kamu tidak memasang APK dan tidak memberi data pribadi kepada pengirim asing.",
        "Kamu sudah mengenali sebagian modus undangan APK, tapi masih ada langkah yang membuat saldo atau datamu terancam.",
        "Banyak jebakan yang belum dikenali. Undangan asli bukan file APK, dan tidak butuh izin SMS atau foto KTP.",
    ),
}

# ---- Penyimpanan status per sesi (memori proses, kedaluwarsa 2 jam) ----
# Langflow menjalankan ulang kode komponen di setiap pesan, jadi variabel modul
# tidak bertahan. Status disimpan di file agar tetap ada antar-pesan.
_STATE = {}
_LOCK = threading.Lock()
_IO_LOCK = threading.Lock()
_TTL = 2 * 60 * 60
_STORE = os.path.join(tempfile.gettempdir(), "golden_hour_state.json")
_LEADERBOARD_STORE = os.path.join(tempfile.gettempdir(), "golden_hour_leaderboard.json")


def _pin_prompt_set(name):
    return (
        f"Halo, {name}! Satu langkah lagi — buat PIN 4 digit untuk melindungi profilmu.\n"
        "(PIN ini mencegah orang lain mengklaim akunmu di leaderboard)\n\n"
        "⚠️ Pastikan tidak ada orang lain yang bisa melihat layarmu saat mengetik PIN.\n"
        "Ketik PIN 4 digit (angka saja):"
    )


def _pin_prompt_verify(name):
    return (
        f"Selamat datang kembali, {name}! 👋\n"
        "Profil kamu ditemukan di leaderboard. Masukkan PIN 4 digit untuk masuk:\n\n"
        "⚠️ Pastikan tidak ada orang lain yang bisa melihat layarmu saat mengetik PIN.\n"
        "Ketik PIN 4 digitmu:"
    )


def _pin_error_verify(name, attempts_left):
    return (
        f"Verifikasi gagal! Sisa percobaan: {attempts_left}.\n"
        "Ketik PIN 4 digitmu:"
    ) if attempts_left > 0 else (
        f"Terlalu banyak percobaan gagal. Profil '{name}' tidak dapat diakses saat ini.\n"
        "Kirim 'ganti nama' untuk masuk dengan akun baru."
    )


def _load():
    try:
        with open(_STORE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data):
    tmp = _STORE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, _STORE)
    except OSError:
        pass


def _purge():
    now = time.time()
    for key in [k for k, v in _STATE.items() if now - v["ts"] > _TTL]:
        del _STATE[key]


def _get_astra_config(astra_cfg=None):
    cfg = astra_cfg or {}
    token = (cfg.get("token") or os.getenv("ASTRA_DB_APPLICATION_TOKEN") or os.getenv("ASTRA_DB_TOKEN") or "").strip()
    endpoint = (cfg.get("endpoint") or os.getenv("ASTRA_DB_API_ENDPOINT") or "").strip().rstrip("/")
    keyspace = (cfg.get("keyspace") or os.getenv("ASTRA_DB_KEYSPACE") or "default_keyspace").strip()
    collection = (cfg.get("collection") or os.getenv("ASTRA_DB_COLLECTION") or "scam_game_records").strip()
    return token, endpoint, keyspace, collection


def _ensure_astra_collection(endpoint, keyspace, collection, token):
    try:
        url = f"{endpoint}/api/json/v1/{keyspace}"
        headers = {"Token": token, "Content-Type": "application/json"}
        payload = {"createCollection": {"name": collection}}
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=3) as resp:
            pass
    except Exception:
        pass


def _aggregate_leaderboard_docs(docs):
    """Pastikan setiap pemain hanya muncul satu kali dengan skor akumulasi tertinggi/terbaru."""
    players = {}
    for doc in docs:
        p_name = (doc.get("player") or "Pemain").strip()
        p_key = p_name.lower()
        if p_key not in players:
            players[p_key] = dict(doc)
        else:
            existing = players[p_key]
            if doc.get("score", 0) > existing.get("score", 0):
                players[p_key] = dict(doc)
            elif doc.get("score", 0) == existing.get("score", 0) and doc.get("scenarios_completed", 1) > existing.get("scenarios_completed", 1):
                players[p_key] = dict(doc)

    unique_docs = list(players.values())
    unique_docs.sort(key=lambda d: (d.get("score", 0), d.get("saldo_akhir", 0)), reverse=True)
    return unique_docs


def _save_pin_to_leaderboard(player_name, pin_hash, pin_salt):
    """Simpan pin_hash dan pin_salt ke dokumen pemain di local leaderboard store."""
    try:
        data = []
        if os.path.exists(_LEADERBOARD_STORE):
            with open(_LEADERBOARD_STORE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, list):
                    data = []
        p_id = player_name.strip().lower()
        for d in data:
            if (d.get("player") or "").strip().lower() == p_id:
                d["pin_hash"] = pin_hash
                d["pin_salt"] = pin_salt
                break
        else:
            # Pemain baru belum punya skor, tambahkan placeholder agar PIN tersimpan
            data.append({
                "player": player_name,
                "player_id": p_id,
                "score": 0,
                "total_score": 0,
                "rank": _cumulative_rank(0),
                "scenario": "",
                "scenarios_completed": 0,
                "scenario_scores": {},
                "pin_hash": pin_hash,
                "pin_salt": pin_salt,
                "created_at": int(time.time()),
            })
        with open(_LEADERBOARD_STORE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass


def _get_pin_from_leaderboard(player_name):
    """Ambil pin_hash dan pin_salt pemain dari local store (prioritas) atau Astra DB."""
    try:
        if os.path.exists(_LEADERBOARD_STORE):
            with open(_LEADERBOARD_STORE, "r", encoding="utf-8") as f:
                data = json.load(f)
            p_id = player_name.strip().lower()
            for d in data:
                if (d.get("player") or "").strip().lower() == p_id:
                    if d.get("pin_hash") and d.get("pin_salt"):
                        return d["pin_hash"], d["pin_salt"]
    except Exception:
        pass
    return None, None


def _save_local_leaderboard(player_name, scenario_key, current_score, final_state):
    """Upsert skor kumulatif pemain di penyimpanan lokal."""
    try:
        data = []
        if os.path.exists(_LEADERBOARD_STORE):
            with open(_LEADERBOARD_STORE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, list):
                    data = []

        player_id = (player_name or "Pemain").strip().lower()
        existing = None
        for d in data:
            if (d.get("player") or "").strip().lower() == player_id:
                existing = d
                break

        now_ts = int(time.time())
        now_date = time.strftime("%d/%m/%Y %H:%M", time.localtime())

        if existing:
            scen_scores = existing.get("scenario_scores") or {}
            if not scen_scores and existing.get("scenario"):
                scen_scores[existing["scenario"]] = existing.get("score", 0)
            scen_scores[scenario_key] = max(scen_scores.get(scenario_key, 0), current_score)

            scen_saldos = existing.get("scenario_saldos") or {}
            scen_saldos[scenario_key] = {
                "awal": final_state.get("awal", 0),
                "akhir": final_state.get("saldo", 0),
            }

            tot_score = sum(scen_scores.values())
            tot_awal = sum(s.get("awal", 0) for s in scen_saldos.values())
            tot_akhir = sum(s.get("akhir", 0) for s in scen_saldos.values())

            existing["player"] = player_name
            existing["player_id"] = player_id
            existing["score"] = tot_score
            existing["total_score"] = tot_score
            existing["rank"] = _cumulative_rank(tot_score)
            existing["scenario"] = ", ".join(sorted(scen_scores.keys()))
            existing["scenario_title"] = f"{len(scen_scores)}/3 Skenario Selesai"
            existing["scenarios_completed"] = len(scen_scores)
            existing["scenario_scores"] = scen_scores
            existing["scenario_saldos"] = scen_saldos
            existing["saldo_awal"] = tot_awal
            existing["saldo_akhir"] = tot_akhir
            existing["updated_at"] = now_ts
            existing["date_str"] = now_date
            cum_data = existing
        else:
            tot_score = current_score
            scen_scores = {scenario_key: current_score}
            scen_saldos = {scenario_key: {"awal": final_state.get("awal", 0), "akhir": final_state.get("saldo", 0)}}
            cum_data = {
                "player": player_name,
                "player_id": player_id,
                "score": tot_score,
                "total_score": tot_score,
                "rank": _cumulative_rank(tot_score),
                "scenario": scenario_key,
                "scenario_title": "1/3 Skenario Selesai",
                "scenarios_completed": 1,
                "scenario_scores": scen_scores,
                "scenario_saldos": scen_saldos,
                "saldo_awal": final_state.get("awal", 0),
                "saldo_akhir": final_state.get("saldo", 0),
                "created_at": now_ts,
                "date_str": now_date,
            }
            data.append(cum_data)

        data.sort(key=lambda d: (d.get("score", 0), d.get("saldo_akhir", 0)), reverse=True)
        data = data[:50]
        with open(_LEADERBOARD_STORE, "w", encoding="utf-8") as f:
            json.dump(data, f)

        return cum_data
    except Exception:
        return None


def _load_local_leaderboard(limit=5):
    try:
        if os.path.exists(_LEADERBOARD_STORE):
            with open(_LEADERBOARD_STORE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return _aggregate_leaderboard_docs(data)[:limit]
    except Exception:
        pass
    return []


def _save_game_result(player_name, scenario_key, current_score, final_state, astra_cfg=None, pin_hash=None, pin_salt=None):
    """Simpan hasil game ke local store dan Astra DB Cloud dengan skor akumulasi."""
    cum_data = _save_local_leaderboard(player_name, scenario_key, current_score, final_state)
    if not cum_data:
        cum_data = {
            "player": player_name,
            "score": current_score,
            "total_score": current_score,
            "rank": _cumulative_rank(current_score),
            "scenario": scenario_key,
            "scenario_title": "1/3 Skenario Selesai",
            "scenarios_completed": 1,
            "scenario_scores": {scenario_key: current_score},
            "saldo_akhir": final_state.get("saldo", 0),
        }

    token, endpoint, keyspace, collection = _get_astra_config(astra_cfg)
    if not token or not endpoint:
        return "Tersimpan di Leaderboard Lokal (Astra DB belum dikonfigurasi)", cum_data

    url = f"{endpoint}/api/json/v1/{keyspace}/{collection}"
    headers = {"Token": token, "Content-Type": "application/json"}

    try:
        _ensure_astra_collection(endpoint, keyspace, collection, token)

        # 1. Cari apakah pemain sudah memiliki dokumen di Astra DB
        existing_doc = None
        try:
            find_req = urllib.request.Request(
                url,
                data=json.dumps({"find": {"filter": {"player": player_name}, "options": {"limit": 1}}}).encode("utf-8"),
                headers=headers,
                method="POST"
            )
            with urllib.request.urlopen(find_req, timeout=4) as resp:
                f_data = json.loads(resp.read().decode("utf-8"))
                docs = f_data.get("data", {}).get("documents", [])
                if docs:
                    existing_doc = docs[0]
        except Exception:
            pass

        # Fallback cari secara case-insensitive jika filter exact belum ketemu
        if not existing_doc:
            try:
                find_all_req = urllib.request.Request(
                    url,
                    data=json.dumps({"find": {"options": {"limit": 50}}}).encode("utf-8"),
                    headers=headers,
                    method="POST"
                )
                with urllib.request.urlopen(find_all_req, timeout=4) as resp:
                    f_data = json.loads(resp.read().decode("utf-8"))
                    for d in f_data.get("data", {}).get("documents", []):
                        if (d.get("player") or "").strip().lower() == player_name.strip().lower():
                            existing_doc = d
                            break
            except Exception:
                pass

        now_ts = int(time.time())
        now_date = time.strftime("%d/%m/%Y %H:%M", time.localtime())

        if existing_doc and "_id" in existing_doc:
            scen_scores = existing_doc.get("scenario_scores") or {}
            if not scen_scores and existing_doc.get("scenario"):
                scen_scores[existing_doc["scenario"]] = existing_doc.get("score", 0)
            scen_scores[scenario_key] = max(scen_scores.get(scenario_key, 0), current_score)

            scen_saldos = existing_doc.get("scenario_saldos") or {}
            scen_saldos[scenario_key] = {
                "awal": final_state.get("awal", 0),
                "akhir": final_state.get("saldo", 0),
            }

            tot_score = sum(scen_scores.values())
            tot_awal = sum(s.get("awal", 0) for s in scen_saldos.values())
            tot_akhir = sum(s.get("akhir", 0) for s in scen_saldos.values())
            cum_rank = _cumulative_rank(tot_score)

            update_doc = {
                "score": tot_score,
                "total_score": tot_score,
                "rank": cum_rank,
                "scenario": ", ".join(sorted(scen_scores.keys())),
                "scenario_title": f"{len(scen_scores)}/3 Skenario Selesai",
                "scenarios_completed": len(scen_scores),
                "scenario_scores": scen_scores,
                "scenario_saldos": scen_saldos,
                "saldo_awal": tot_awal,
                "saldo_akhir": tot_akhir,
                "updated_at": now_ts,
                "date_str": now_date,
            }

            cum_data["score"] = tot_score
            cum_data["total_score"] = tot_score
            cum_data["rank"] = cum_rank
            cum_data["scenarios_completed"] = len(scen_scores)
            cum_data["scenario_scores"] = scen_scores
            cum_data["saldo_akhir"] = tot_akhir

            up_payload = {
                "updateOne": {
                    "filter": {"_id": existing_doc["_id"]},
                    "update": {"$set": update_doc}
                }
            }
            up_req = urllib.request.Request(url, data=json.dumps(up_payload).encode("utf-8"), headers=headers, method="POST")
            with urllib.request.urlopen(up_req, timeout=4) as resp:
                resp.read()
            return f"Tersinkronisasi ke Astra DB Cloud! (Skor Akumulasi: {tot_score}/90 Poin)", cum_data

        else:
            tot_score = current_score
            scen_scores = {scenario_key: current_score}
            scen_saldos = {scenario_key: {"awal": final_state.get("awal", 0), "akhir": final_state.get("saldo", 0)}}
            cum_rank = _cumulative_rank(tot_score)

            ins_doc = {
                "player": player_name,
                "player_id": player_name.strip().lower(),
                "score": tot_score,
                "total_score": tot_score,
                "rank": cum_rank,
                "scenario": scenario_key,
                "scenario_title": "1/3 Skenario Selesai",
                "scenarios_completed": 1,
                "scenario_scores": scen_scores,
                "scenario_saldos": scen_saldos,
                "saldo_awal": final_state.get("awal", 0),
                "saldo_akhir": final_state.get("saldo", 0),
                "created_at": now_ts,
                "date_str": now_date,
            }
            if pin_hash and pin_salt:
                ins_doc["pin_hash"] = pin_hash
                ins_doc["pin_salt"] = pin_salt
            ins_payload = {"insertOne": {"document": ins_doc}}
            ins_req = urllib.request.Request(url, data=json.dumps(ins_payload).encode("utf-8"), headers=headers, method="POST")
            with urllib.request.urlopen(ins_req, timeout=4) as resp:
                resp.read()
            return f"Tersinkronisasi ke Astra DB Cloud! (Skor Akumulasi: {tot_score}/90 Poin)", cum_data

    except Exception as e:
        return f"Tersimpan lokal (Astra DB: {type(e).__name__})", cum_data


def _get_combined_leaderboard(astra_cfg=None, limit=5):
    """Ambil data leaderboard dari Astra DB (prioritas) atau Fallback Lokal."""
    token, endpoint, keyspace, collection = _get_astra_config(astra_cfg)
    if token and endpoint:
        try:
            url = f"{endpoint}/api/json/v1/{keyspace}/{collection}"
            headers = {"Token": token, "Content-Type": "application/json"}
            payload = {"find": {"options": {"limit": 50}}}
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                docs = data.get("data", {}).get("documents", [])
                if docs:
                    aggregated = _aggregate_leaderboard_docs(docs)
                    return aggregated[:limit], "Astra DB Cloud"
        except Exception:
            pass

    local_docs = _load_local_leaderboard(limit=limit)
    return local_docs, "Penyimpanan Lokal"


def _render_leaderboard(docs, source="Penyimpanan Lokal", active_player=""):
    if not docs:
        return (
            "LEADERBOARD — SCAM BUSTERS (SKOR TERAKUMULASI)\n\n"
            f"Sumber Data: {source}\n"
            "Belum ada catatan skor di papan peringkat.\n"
            "Mainkan simulasi sekarang dan jadilah yang pertama masuk peringkat!\n\n"
            "Kirim 'menu' untuk mulai bermain."
        )

    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    lines = [
        "LEADERBOARD — SCAM BUSTERS (SKOR TERAKUMULASI)",
        f"Sumber Data: {source}\n",
    ]
    player_pos = None
    player_doc = None
    active_clean = active_player.strip().lower() if active_player else ""

    for idx, doc in enumerate(docs[:5]):
        icon = medals[idx] if idx < len(medals) else f"{idx+1}."
        player = doc.get("player") or "Pemain"
        score = doc.get("score", 0)
        rank = doc.get("rank") or _cumulative_rank(score)
        scen_title = doc.get("scenario_title") or f"{doc.get('scenarios_completed', 1)}/3 Skenario Selesai"
        scen_scores = doc.get("scenario_scores") or {}
        saldo = _rp(doc.get("saldo_akhir", 0))

        detail_scen = ""
        if scen_scores:
            detail_scen = " (" + ", ".join(f"{k}:{v}" for k, v in scen_scores.items()) + ")"

        if active_clean and player.lower() == active_clean:
            player_pos = idx + 1
            player_doc = doc

        lines.append(
            f"{icon} {player} — {score}/90 Poin ({rank})\n"
            f"   Progres: {scen_title}{detail_scen} | Saldo Selamat: {saldo}"
        )

    if player_pos and player_doc:
        unplayed = [s for s in ["bank", "job", "apk"] if s not in (player_doc.get("scenario_scores") or {})]
        hint = f" Mainkan skenario {' atau '.join(unplayed)} untuk nambah skor!" if unplayed else " Semua skenario selesai!"
        lines.append(f"\nKamu saat ini di posisi #{player_pos} ({player_doc.get('player')})!{hint}")

    lines.append("\nMau tambah skormu ke peringkat teratas? Kirim: menu")
    return "\n".join(lines)


def _get_player_record(player_name, astra_cfg=None):
    """Ambil data profil pemain yang sudah tersimpan di Astra DB atau lokal."""
    if not player_name:
        return None
    p_id = player_name.strip().lower()
    docs, _ = _get_combined_leaderboard(astra_cfg, limit=50)
    for doc in docs:
        if (doc.get("player") or "").strip().lower() == p_id:
            return doc
    return None


def _reset_session_game(state):
    """Reset status langkah permainan namun pertahankan identitas pemain sesi."""
    if not isinstance(state, dict):
        return
    saved_name = state.get("player_name", "")
    state["scenario"] = None
    state["step"] = 0
    state["score"] = 0
    state["pending_scenario"] = None
    state["cur"] = None
    state["key"] = None
    state["loss"] = None
    state["lines"] = None
    state["prev"] = None
    state["awaiting_pin"] = False
    state["awaiting_pin_set"] = False
    state["pin_attempts"] = 0
    if saved_name:
        state["player_name"] = saved_name
        state["awaiting_name"] = False


def _rank(score):
    for minimum, name in RANKS:
        if score >= minimum:
            return name
    return RANKS[-1][1]


def _present_step(state):
    """Acak pilihan langkah saat ini, simpan kunci di server, kembalikan teks."""
    step = SCRIPT[state["scenario"]]["steps"][state["step"] - 1]
    order = list(range(4))
    random.shuffle(order)
    state["cur"] = {"sender": step["sender"], "text": step["text"], "bridge": ""}
    prev = state.get("prev")
    if prev:
        extra = BRANCH.get(state["scenario"], {}).get(state["step"], {}).get(prev, {})
        state["cur"].update({k: v for k, v in extra.items() if k in ("sender", "text", "bridge")})
    losses = ECON[state["scenario"]]["steps"][state["step"] - 1]["loss"]
    state["key"] = {}
    state["loss"] = {}
    lines = []
    for letter, idx in zip("ABCD", order):
        text, grade = step["options"][idx]
        state["key"][letter] = grade
        state["loss"][letter] = losses[idx]
        lines.append(f"{letter}. {text}")
    state["lines"] = lines
    return step, lines


def _message_block(state, step, lines):
    cur = state["cur"]
    bridge = f"Kejadian: {cur['bridge']}\n\n" if cur["bridge"] else ""
    return (
        bridge
        + f"PESAN MASUK (langkah {state['step']} dari 3)\n"
        f"Dari: {cur['sender']}\n"
        f"Isi: {cur['text']}\n\n"
        "Pilihanmu:\n" + "\n".join(lines) + "\n\n"
        "Untuk lanjut, kirim satu huruf: A, B, C, atau D."
    )


def _final_block(score, state, save_status="", cum_data=None):
    rank_single = _rank(score)
    scen_key = state.get("scenario", "")
    scen_title = SCRIPT.get(scen_key, {}).get("title", "Simulasi")
    best, mid, low = SUMMARY.get(scen_key, ("", "", ""))
    summary = best if score >= 30 else mid if score >= 10 else low
    tips = random.sample(TIPS.get(scen_key, []), 2) + [REPORT_TIP]
    player = state.get("player_name") or "Pemain"
    status_line = f"Status Database: {save_status}\n" if save_status else ""

    cum_block = ""
    if cum_data:
        tot_score = cum_data.get("score", score)
        cum_rank = cum_data.get("rank") or _cumulative_rank(tot_score)
        completed = cum_data.get("scenarios_completed", 1)
        tot_saved = _rp(cum_data.get("saldo_akhir", state.get("saldo", 0)))

        all_scens = ["bank", "job", "apk"]
        played = list((cum_data.get("scenario_scores") or {}).keys())
        unplayed = [s for s in all_scens if s not in played]

        hint = ""
        if unplayed:
            unplayed_names = [f"'{s}'" for s in unplayed]
            hint = f"💡 Rekomendasi: Mainkan skenario {' atau '.join(unplayed_names)} untuk menambah skor hingga 90 poin!\n"
        else:
            hint = "🎉 Hebat! Kamu sudah menyelesaikan seluruh skenario (3/3)!\n"

        cum_block = (
            "PROFIL & SKOR AKUMULASI LEADERBOARD:\n"
            f"- Total Skor Akumulasi: {tot_score} dari 90 Poin\n"
            f"- Peringkat Akumulasi: {cum_rank}\n"
            f"- Progres: {completed}/3 Skenario Selesai\n"
            f"- Total Saldo Diselamatkan: {tot_saved}\n"
            f"{hint}\n"
        )

    return (
        "HASIL AKHIR\n"
        f"Pemain: {player}\n"
        f"Skenario: {scen_title}\n"
        f"Skor Skenario Ini: {score} dari 30 ({rank_single})\n"
        f"Uang di rekening {state['owner']} di akhir: {_rp(state['saldo'])} dari {_rp(state['awal'])}\n"
        f"Ringkasan: {summary}\n\n"
        + cum_block
        + status_line +
        "Tips di dunia nyata:\n"
        + "\n".join(f"{i}. {t}" for i, t in enumerate(tips, 1))
        + "\n\nKirim: 1, 2, atau 3 untuk lanjut skenario lain | Kirim: leaderboard | Kirim: menu"
    )


def _guide():
    return (
        "PANDUAN BERMAIN & SISTEM SKOR — GOLDEN HOUR 🛡️\n\n"
        "1. CARA BERMAIN:\n"
        "- Pilih salah satu dari 3 skenario simulasi penipuan online (bank, job, atau apk).\n"
        "- Setiap skenario terdiri dari 3 langkah serangan penipuan bertingkat.\n"
        "- Pada setiap langkah, kamu akan menerima pesan/telepon dari penipu dan harus memilih opsi (A, B, C, atau D).\n"
        "- Pilihan TEPAT (+10 poin) akan mengamankan dana dan membuka tanda bahaya penipuan.\n"
        "- Pilihan BERISIKO (0 poin) akan menguras saldo rekening dan membawamu ke jebakan penipu.\n\n"
        "2. SISTEM SKOR & SALDO REKENING:\n"
        "- Skor per skenario: Maksimal 30 Poin.\n"
        "- Saldo Cerita: Pertahankan uang di rekening korban agar tidak terkuras sampai langkah terakhir!\n\n"
        "3. AKUMULASI SKOR LEADERBOARD (ASTRA DB CLOUD):\n"
        "- Total skor diakumulasikan hingga 90 Poin dari 3 skenario:\n"
        "  * 1 Skenario Selesai: Maksimal 30 Poin (Gelar: Firewall Aegis)\n"
        "  * 2 Skenario Selesai: Maksimal 60 Poin (Gelar: Scam Hunter)\n"
        "  * 3 Skenario Selesai: Maksimal 90 Poin (Gelar Tertinggi: Apex Untouchable)\n"
        "- Mengulang skenario yang sama akan mengambil skor tertinggimu (best score).\n\n"
        "4. DAFTAR PERINTAH:\n"
        "- 'menu' : Kembali ke menu utama pilihan skenario.\n"
        "- '1', '2', atau '3' : Memilih skenario Bank, Job, atau APK.\n"
        "- 'leaderboard' : Lihat papan peringkat pemain teratas di Astra DB Cloud.\n"
        "- 'ganti nama [nama]' : Mengganti nama/akun pemain aktif.\n"
        "- 'lanjut' atau 'status' : Cek pesan terakhir jika koneksi sempat terputus.\n\n"
        "Siap bermain? Kirim: menu atau ketik 1, 2, atau 3"
    )


def _menu(player_name="", player_record=None):
    header = "GOLDEN HOUR: LIVE SCAM ATTACK\n"
    if player_name:
        if player_record:
            scen_comp = player_record.get("scenarios_completed") or len(player_record.get("scenario_scores") or {}) or 1
            score = player_record.get("score", 0)
            header += f"Pemain Aktif: {player_name} (Skor: {score}/90 Poin, {scen_comp}/3 Skenario Selesai)\n\n"
        else:
            header += f"Pemain Aktif: {player_name}\n\n"
    else:
        header += "\n"

    return (
        header +
        "Pilih skenario simulasi:\n"
        "1. Telepon dari CS Bank. Kirim: 1 atau bank\n"
        "2. Tawaran Kerja Online. Kirim: 2 atau job\n"
        "3. Undangan Pernikahan APK. Kirim: 3 atau apk\n"
        "4. Panduan & Cara Bermain. Kirim: 4 atau panduan\n\n"
        "Fitur Tambahan:\n"
        "- Kirim 'leaderboard' untuk melihat papan peringkat akumulasi (Astra DB Cloud).\n"
        "- Kirim 'ganti nama' jika ingin berganti profil pemain.\n\n"
        + DISCLAIMER
    )


def _set_and_welcome_player(player_name, state, astra_cfg=None):
    clean_name = player_name.strip()
    if clean_name.lower().startswith(("nama saya ", "halo saya ", "saya ", "panggil saya ", "namaku ")):
        clean_name = re.sub(r"^(?:nama saya|halo saya|saya|panggil saya|namaku)\s+", "", clean_name, flags=re.IGNORECASE).strip()

    clean_name = clean_name[:25].strip().title()
    state["player_name"] = clean_name
    state["awaiting_name"] = False
    state["ts"] = time.time()

    # Cek apakah pemain sudah punya profil dengan PIN
    pin_hash, pin_salt = _get_pin_from_leaderboard(clean_name)
    if pin_hash and pin_salt:
        # Pemain lama — minta verifikasi PIN sebelum lanjut
        state["awaiting_pin"] = True
        state["pin_attempts"] = 0
        return _pin_prompt_verify(clean_name)

    # Cek apakah ada profil tanpa PIN (pemain lama sebelum fitur PIN)
    existing = _get_player_record(clean_name, astra_cfg)
    if existing and existing.get("scenarios_completed", 0) > 0:
        # Profil lama tanpa PIN — minta buat PIN baru
        state["awaiting_pin_set"] = True
        return _pin_prompt_set(clean_name)

    # Pemain baru — minta buat PIN
    if existing is None or existing.get("scenarios_completed", 0) == 0:
        state["awaiting_pin_set"] = True
        return _pin_prompt_set(clean_name)

    return (
        f"Halo, {clean_name}! Selamat datang di Golden Hour. 🎯\n"
        "Kumpulkan skor hingga 90 poin dan raih gelar tertinggi Apex Untouchable!\n\n"
        + _menu(clean_name)
    )


def _complete_login(state, astra_cfg=None):
    """Selesaikan proses login setelah PIN terverifikasi atau PIN baru dibuat."""
    clean_name = state.get("player_name", "")
    existing = _get_player_record(clean_name, astra_cfg)

    # Jika ada skenario yang tertunda
    pending_scen = state.get("pending_scenario")
    if pending_scen and pending_scen in SCRIPT:
        state["pending_scenario"] = None
        eco = ECON[pending_scen]
        data = SCRIPT[pending_scen]
        state.update({
            "scenario": pending_scen, "step": 1, "score": 0,
            "owner": eco["owner"], "saldo": eco["saldo"], "awal": eco["saldo"],
        })
        step, lines = _present_step(state)
        return (
            f"SIMULASI DIMULAI: {data['title']}\n"
            f"Pemain: {clean_name} (Karakter: {data['player']})\n"
            "Skor: 0 dari 30\n"
            f"Uang di rekening {state['owner']}: {_rp(state['saldo'])}\n\n"
            + _message_block(state, step, lines)
            + f"\n\n{DISCLAIMER}"
        )

    if existing and existing.get("scenarios_completed", 0) > 0:
        tot_score = existing.get("score", 0)
        cum_rank = existing.get("rank") or _cumulative_rank(tot_score)
        completed = existing.get("scenarios_completed") or len(existing.get("scenario_scores") or {}) or 1
        scen_detail = ""
        if existing.get("scenario_scores"):
            scen_detail = " (" + ", ".join(f"{k}:{v}" for k, v in existing["scenario_scores"].items()) + ")"
        return (
            f"Selamat datang kembali, {clean_name}! 👋\n\n"
            f"Profil Leaderboard Ditemukan:\n"
            f"- Total Skor Akumulasi: {tot_score}/90 Poin ({cum_rank})\n"
            f"- Progres: {completed}/3 Skenario Selesai{scen_detail}\n"
            f"- Saldo Diselamatkan: {_rp(existing.get('saldo_akhir', 0))}\n\n"
            + _menu(clean_name, existing)
        )

    return (
        f"Halo, {clean_name}! Selamat datang di Golden Hour. 🎯\n"
        "Kumpulkan skor hingga 90 poin dan raih gelar tertinggi Apex Untouchable!\n\n"
        + _menu(clean_name)
    )


def _error(help_text):
    return f"TIDAK BISA DIPROSES\n{help_text}\n\n{DISCLAIMER}"


def handle(session_id, raw, astra_cfg=None):
    """Satu giliran permainan. Status dimuat dari file lalu disimpan kembali."""
    with _IO_LOCK:
        _STATE.clear()
        _STATE.update(_load())
        try:
            return _handle(session_id, raw, astra_cfg=astra_cfg)
        finally:
            _save(_STATE)


def _extract_answer(text, state):
    cleaned = re.sub(r"[*_`#]", "", text).strip().lower()

    # 1. Format eksplisit seperti 'A', 'a', 'pilih A', 'opsi A', 'A.', 'A)', 'A - blabla'
    m = re.match(r"^(?:pilih\s+|pilihan\s+|opsi\s+|jawab\s+|jawaban\s+|saya\s+pilih\s+)?([abcd])(?:[.)\s\-:]|$)", cleaned)
    if m:
        return m.group(1).upper()

    # 2. Kata kunci pilihan di dalam teks (misal: 'menurut saya pilih B')
    m2 = re.search(r"\b(?:pilih|pilihan|opsi|jawaban)\s+([abcd])\b", cleaned)
    if m2:
        return m2.group(1).upper()

    # 3. Huruf tunggal mandiri
    if cleaned in ("a", "b", "c", "d"):
        return cleaned.upper()

    # 4. Jika user mengetik sebagian isi teks opsi
    if state and "key" in state and state.get("scenario") and state.get("step"):
        step_idx = state["step"] - 1
        steps = SCRIPT.get(state["scenario"], {}).get("steps", [])
        if 0 <= step_idx < len(steps):
            for letter, grade in state.get("key", {}).items():
                for opt_text, opt_grade in steps[step_idx]["options"]:
                    if opt_grade == grade:
                        lead = opt_text.lower()[:15].strip()
                        if lead and lead in cleaned:
                            return letter

    return None


def _handle(session_id, raw, astra_cfg=None):
    raw_str = (raw or "").strip()
    text = raw_str.lower()
    with _LOCK:
        _purge()
        state = _STATE.get(session_id)

        # Fallback sesi aktif (untuk MCP Server / IBM Bob di mana session_id berganti tiap turn)
        if not state and _STATE:
            now = time.time()
            active_sessions = [
                (sid, s) for sid, s in _STATE.items()
                if isinstance(s, dict)
                and (s.get("player_name") or s.get("awaiting_name"))
                and (now - s.get("ts", 0) < 1800)
            ]
            if active_sessions:
                active_sessions.sort(key=lambda item: item[1].get("ts", 0), reverse=True)
                active_sid, active_state = active_sessions[0]
                state = dict(active_state)
                _STATE[session_id] = state

        # Inisialisasi state jika sesi baru
        if state is None:
            state = {
                "player_name": "",
                "awaiting_name": False,
                "awaiting_pin": False,
                "awaiting_pin_set": False,
                "pin_attempts": 0,
                "pending_scenario": None,
                "scenario": None,
                "step": 0,
                "score": 0,
                "ts": time.time(),
            }
            _STATE[session_id] = state

        # 0. Tangani input PIN verifikasi (pemain lama login)
        if state.get("awaiting_pin"):
            pin_input = raw_str.strip()
            clean_name = state.get("player_name", "")
            pin_hash, pin_salt = _get_pin_from_leaderboard(clean_name)
            if pin_hash and pin_salt and _verify_pin(pin_input, pin_salt, pin_hash):
                state["awaiting_pin"] = False
                state["pin_attempts"] = 0
                state["ts"] = time.time()
                return _complete_login(state, astra_cfg)
            else:
                state["pin_attempts"] = state.get("pin_attempts", 0) + 1
                attempts_left = 3 - state["pin_attempts"]
                if attempts_left <= 0:
                    state["awaiting_pin"] = False
                    state["pin_attempts"] = 0
                    state["player_name"] = ""
                    state["awaiting_name"] = True
                return _pin_error_verify(clean_name, attempts_left)

        # 0. Tangani input PIN baru (pemain baru atau profil lama tanpa PIN)
        if state.get("awaiting_pin_set"):
            pin_input = raw_str.strip()
            clean_name = state.get("player_name", "")
            if not re.fullmatch(r"\d{4}", pin_input):
                return (
                    "PIN harus tepat 4 digit angka (contoh: 1234).\n"
                    "Ketik PIN 4 digitmu:"
                )
            salt = secrets.token_hex(16)
            hashed = _hash_pin(pin_input, salt)
            _save_pin_to_leaderboard(clean_name, hashed, salt)
            state["awaiting_pin_set"] = False
            state["ts"] = time.time()
            return (
                f"PIN berhasil dibuat! Profilmu sekarang terlindungi. 🔐\n\n"
                + _complete_login(state, astra_cfg)
            )

        # 0. Pemicu Ganti Nama / Reset Profil
        is_change_name_trigger = (
            text in ("ganti nama", "ubah nama", "logout", "reset nama", "reset profil", "reset profile", "ganti profil", "ganti profile", "ganti akun", "reset akun")
            or text.startswith(("ganti nama ", "ubah nama ", "ganti profil ", "ubah profil "))
        )
        if is_change_name_trigger:
            parts = raw_str.split(maxsplit=2)
            new_name = parts[2].strip().title() if len(parts) >= 3 else ""
            if new_name and len(new_name) >= 2 and new_name.lower() not in ("a", "b", "c", "d"):
                _reset_session_game(state)
                return (
                    f"Profil pemain berhasil diubah ke: {new_name[:25]}! ✅\n\n"
                    + _set_and_welcome_player(new_name, state, astra_cfg)
                )
            else:
                _reset_session_game(state)
                state["player_name"] = ""
                state["awaiting_name"] = True
                state["ts"] = time.time()
                return (
                    "PROFIL PEMAIN DIRESET\n\n"
                    "Silakan ketik nama panggilan barumu (contoh: Ariq atau Zenith):"
                )

        # 0.1. Pemicu Leaderboard / Papan Peringkat
        is_leaderboard_intent = (
            text in ("leaderboard", "papan peringkat", "peringkat", "top", "score", "skor", "ranking")
            or "leaderboard" in text
            or "peringkat" in text
        )
        if is_leaderboard_intent:
            docs, source = _get_combined_leaderboard(astra_cfg)
            return _render_leaderboard(docs, source, active_player=state.get("player_name", ""))

        # 0.2. Pemicu Panduan & Cara Bermain
        is_guide_intent = (
            text in ("panduan", "bantuan", "help", "cara main", "cara bermain", "aturan", "info", "petunjuk", "4", "pilih 4")
            or "panduan" in text
            or "cara main" in text
            or "cara bermain" in text
            or "bantuan" in text
        )
        if is_guide_intent:
            return _guide()

        # 0.3. Tangani input nama jika game sedang menunggu nama pemain
        if state.get("awaiting_name"):
            clean_name = raw_str.strip()
            if clean_name.lower().startswith(("nama saya ", "halo saya ", "saya ", "panggil saya ", "namaku ")):
                clean_name = re.sub(r"^(?:nama saya|halo saya|saya|panggil saya|namaku)\s+", "", clean_name, flags=re.IGNORECASE).strip()

            # Validasi nama: wajib minimal 2 karakter dan bukan huruf opsi A/B/C/D
            if len(clean_name) < 2 or clean_name.lower() in ("a", "b", "c", "d"):
                return (
                    "Nama wajib diisi sebelum simulasi dimulai!\n"
                    "Nama ini akan dicatat di Papan Peringkat (Astra DB Leaderboard).\n\n"
                    "Silakan ketik nama panggilanmu (minimal 2 huruf, contoh: Ariq atau Zenith):"
                )

            return _set_and_welcome_player(clean_name, state, astra_cfg)

        # 0.4. Minta nama di awal SEBELUM menu jika pemain belum terdaftar di sesi ini
        if not state.get("player_name") and not state.get("scenario"):
            parts = raw_str.split(maxsplit=1)
            first_tok = parts[0].lower() if parts else ""
            tail_tok = parts[1].strip() if len(parts) > 1 else ""

            found_scen = None
            if first_tok in SCRIPT:
                found_scen = first_tok
            elif first_tok in ("1", "pilih 1") or "bank" in first_tok:
                found_scen = "bank"
            elif first_tok in ("2", "pilih 2") or "job" in first_tok or "kerja" in first_tok:
                found_scen = "job"
            elif first_tok in ("3", "pilih 3") or "apk" in first_tok or "undangan" in first_tok:
                found_scen = "apk"

            # Jika memilih skenario langsung dengan nama (contoh: 'bank Zenith' atau '1 Dimas')
            if found_scen and tail_tok and len(tail_tok) >= 2 and tail_tok.lower() not in ("a", "b", "c", "d"):
                state["player_name"] = tail_tok[:25].strip().title()
                state["awaiting_name"] = False
                state["ts"] = time.time()
                eco = ECON[found_scen]
                data = SCRIPT[found_scen]
                state.update({
                    "scenario": found_scen, "step": 1, "score": 0,
                    "owner": eco["owner"], "saldo": eco["saldo"], "awal": eco["saldo"],
                })
                step, lines = _present_step(state)
                return (
                    f"SIMULASI DIMULAI: {data['title']}\n"
                    f"Pemain: {state['player_name']} (Karakter: {data['player']})\n"
                    "Skor: 0 dari 30\n"
                    f"Uang di rekening {state['owner']}: {_rp(state['saldo'])}\n\n"
                    + _message_block(state, step, lines)
                    + f"\n\n{DISCLAIMER}"
                )

            # Jika memilih skenario tapi belum punya nama
            if found_scen:
                state["pending_scenario"] = found_scen
                state["awaiting_name"] = True
                return (
                    f"SIMULASI DIPILIH: {SCRIPT[found_scen]['title']}\n\n"
                    "Sebelum simulasi dimulai, masukkan nama panggilanmu:\n"
                    "(Nama ini akan dicatat di Leaderboard Astra DB Cloud)\n\n"
                    "Ketik nama panggilanmu (contoh: Ariq atau Zenith):"
                )

            # Deteksi apakah pesan user adalah sapaan umum atau langsung nama panggilan
            GREETINGS = (
                "halo", "hai", "hi", "hey", "mulai", "start", "menu", "game",
                "pagi", "siang", "sore", "malam", "tes", "test", "bot", "buka", "play"
            )
            clean = raw_str.strip()
            is_greeting = (
                not clean
                or clean.lower() in GREETINGS
                or any(clean.lower().startswith(g + " ") for g in ("halo", "hai", "hi", "hey", "selamat"))
            )

            if not is_greeting and len(clean) >= 2 and clean.lower() not in ("a", "b", "c", "d"):
                # Input user langsung berupa nama panggilan!
                return _set_and_welcome_player(clean, state, astra_cfg)

            # Sapaan awal untuk meminta nama sebelum menu dibuka
            state["awaiting_name"] = True
            return (
                "GOLDEN HOUR: LIVE SCAM ATTACK 🛡️\n"
                "Simulasi Pelatihan Keamanan Siber & Edukasi Anti-Penipuan Digital\n\n"
                "Sebelum masuk ke menu permainan, masukkan nama panggilanmu:\n"
                "(Nama ini digunakan untuk mencatat profil skormu di Astra DB Cloud Leaderboard)\n\n"
                "Ketik nama panggilanmu (contoh: Ariq atau Zenith):"
            )

        # 1. Pemicu Menu / Mulai Game (Pemain sudah terdaftar)
        is_menu_intent = (
            text in ("menu", "mulai", "ulang", "restart", "game", "main")
            or "menu" in text
            or "restart" in text
            or (not state.get("scenario") and any(k in text for k in ("game", "ngegame", "simulasi", "kuis", "main")))
        )
        if is_menu_intent:
            _reset_session_game(state)
            rec = _get_player_record(state.get("player_name"), astra_cfg)
            return _menu(state.get("player_name"), rec)

        # 1.6. Pemulihan Sesi: jika koneksi sempat terputus dan pemain ingin mengecek status / pesan terakhir
        if state.get("scenario") and text in ("lanjut", "status", "resume", "ulang pesan", "kembali", "pesan"):
            step = SCRIPT[state["scenario"]]["steps"][state["step"] - 1]
            lines = state.get("lines") or []
            if not lines:
                step, lines = _present_step(state)
            data = SCRIPT[state["scenario"]]
            return (
                f"SESI SIMULASI AKTIF: {data['title']}\n"
                f"Pemain: {state.get('player_name', 'Pemain')}\n"
                f"Skor Saat Ini: {state['score']} dari 30\n"
                f"Uang di rekening {state['owner']}: {_rp(state['saldo'])}\n\n"
                + _message_block(state, step, lines)
                + f"\n\n{DISCLAIMER}"
            )

        # 2. Pilihan Skenario (Pemain sudah punya nama!)
        scenario_key = None
        parts = raw_str.split(maxsplit=1)
        first_token = parts[0].lower() if parts else ""
        tail = parts[1].strip() if len(parts) > 1 else ""

        if first_token in SCRIPT:
            scenario_key = first_token
        elif first_token in ("1", "pilih 1") or "bank" in first_token:
            scenario_key = "bank"
        elif first_token in ("2", "pilih 2") or "job" in first_token or "kerja" in first_token:
            scenario_key = "job"
        elif first_token in ("3", "pilih 3") or "apk" in first_token or "undangan" in first_token:
            scenario_key = "apk"
        elif text in SCRIPT:
            scenario_key = text
        elif "bank" in text:
            scenario_key = "bank"
        elif "job" in text or "kerja" in text:
            scenario_key = "job"
        elif "apk" in text or "undangan" in text:
            scenario_key = "apk"

        if scenario_key and scenario_key in SCRIPT:
            # Jika user sengaja menuliskan nama baru di skenario: 'bank Budi'
            if tail and len(tail) >= 2 and tail.lower() not in ("a", "b", "c", "d"):
                state["player_name"] = tail[:25].strip().title()

            eco = ECON[scenario_key]
            data = SCRIPT[scenario_key]
            state.update({
                "scenario": scenario_key, "step": 1, "score": 0, "ts": time.time(),
                "owner": eco["owner"], "saldo": eco["saldo"], "awal": eco["saldo"],
                "awaiting_name": False, "pending_scenario": None,
            })
            step, lines = _present_step(state)
            return (
                f"SIMULASI DIMULAI: {data['title']}\n"
                f"Pemain: {state['player_name']} (Karakter: {data['player']})\n"
                "Skor: 0 dari 30\n"
                f"Uang di rekening {state['owner']}: {_rp(state['saldo'])}\n\n"
                + _message_block(state, step, lines)
                + f"\n\n{DISCLAIMER}"
            )

        # 3. Jawaban Langkah Permainan (A, B, C, atau D)
        ans_letter = _extract_answer(text, state)
        if ans_letter:
            if not state or not state.get("scenario"):
                return _error("Belum ada simulasi berjalan. Kirim 'menu' untuk memilih skenario.")

            letter = ans_letter
            if letter not in state.get("key", {}):
                return _error("Pilihan tidak valid. Kirim huruf A, B, C, atau D.")

            grade = state["key"][letter]
            data = SCRIPT[state["scenario"]]
            step_data = data["steps"][state["step"] - 1]
            answered = state["step"]

            state["score"] += SCORE_GAIN[grade]
            state["ts"] = time.time()

            consequence = ""
            if grade == "RISKY":
                lost = min(state["loss"][letter], state["saldo"])
                state["saldo"] -= lost
                if lost > 0:
                    note = ECON[state["scenario"]]["steps"][answered - 1]["note"]
                    consequence = f"Akibat: {note} Uang di rekening berkurang {_rp(lost)}.\n"
                else:
                    consequence = "Akibat: Belum ada uang berpindah, tapi kamu makin dekat ke jebakan penipu.\n"

            feedback = (
                f"HASIL JAWABAN LANGKAH {answered}: {LABEL[grade]}\n"
                f"Penjelasan: {step_data['lesson']}\n"
                + consequence +
                "Tanda bahaya yang perlu dikenali:\n"
                + "\n".join(f"- {f}" for f in step_data["flags"])
            )

            if answered == 3:
                score = state["score"]
                final_state = dict(state)
                player_name = final_state.get("player_name") or "Pemain"
                scenario_key = final_state["scenario"]

                save_status, cum_data = _save_game_result(
                    player_name, scenario_key, score, final_state, astra_cfg
                )

                # Reset sesi game skenario tapi PERTAHANKAN nama pemain sesi!
                _reset_session_game(state)

                return (
                    "SIMULASI SELESAI\n"
                    f"{feedback}\n\n"
                    + _final_block(score, final_state, save_status, cum_data)
                    + f"\n\n{DISCLAIMER}"
                )

            state["prev"] = grade
            state["step"] += 1
            step, lines = _present_step(state)
            return (
                f"{feedback}\n\n"
                f"Skor: {state['score']} dari 30\n"
                f"Uang di rekening {state['owner']}: {_rp(state['saldo'])}\n\n"
                + _message_block(state, step, lines)
                + f"\n\n{DISCLAIMER}"
            )

    return _error(
        "Kirim bank, job, atau apk untuk memilih skenario. "
        "Saat permainan berjalan, kirim satu huruf: A, B, C, atau D. "
        "Kirim menu untuk kembali ke awal."
    )


HEADERS = (
    "SIMULASI", "PESAN MASUK", "HASIL JAWABAN", "HASIL AKHIR",
    "LEADERBOARD", "GOLDEN HOUR", "TIDAK BISA DIPROSES",
    "PROFIL & SKOR AKUMULASI", "PANDUAN BERMAIN",
    "Pilihanmu:", "Tanda bahaya yang perlu dikenali:", "Tips di dunia nyata:", "Fitur Tambahan:",
)
LABEL_RE = re.compile(
    r"^(Pemain|Peran|Skor akhir|Skor Skenario Ini|Skor|Total Skor Akumulasi|Peringkat Akumulasi|Progres|Total Saldo Diselamatkan|Skenario|Uang di rekening[^:]*|Kejadian|Dari|Isi|Penjelasan|Akibat|Peringkat|Ringkasan|Status Penyimpanan|Status Database|Sumber Data):"
)


def to_markdown(text):
    """Ubah teks polos jadi markdown yang rapi di Chat Output."""
    out = []
    prev_kind = "blank"
    for line in text.split("\n"):
        if not line.strip():
            out.append("")
            prev_kind = "blank"
            continue
        if line.startswith(HEADERS):
            line, kind = f"**{line}**", "text"
        elif line == DISCLAIMER:
            line, kind = f"*{line}*", "text"
        elif line.startswith("- ") or re.match(r"^\d+\. ", line):
            kind = "list"
        else:
            m = LABEL_RE.match(line)
            if m:
                line = f"**{m.group(1)}:**" + line[m.end():]
            kind = "text"
        # dua spasi di akhir = pindah baris; daftar tidak perlu
        out.append(line + ("  " if kind == "text" else ""))
        prev_kind = kind
    return "\n".join(out)


class GoldenHourEngine(Component):
    display_name = "Golden Hour Engine"
    description = "Mesin game deterministik untuk simulasi penipuan dengan Cloud Leaderboard Astra DB."
    icon = "gamepad-2"
    name = "GoldenHourEngine"

    inputs = [
        MessageTextInput(
            name="user_input",
            display_name="Input Pemain",
            info="Sambungkan dari Chat Input.",
        ),
        MessageTextInput(
            name="session_override",
            display_name="Session ID (opsional)",
            info="Isi hanya jika session ID dari Chat Input tidak stabil.",
            advanced=True,
        ),
        SecretStrInput(
            name="astra_token",
            display_name="Astra DB Token (opsional)",
            info="Token Aplikasi Astra DB (AstraCS:...) atau via environment variable ASTRA_DB_APPLICATION_TOKEN.",
        ),
        MessageTextInput(
            name="astra_endpoint",
            display_name="Astra DB API Endpoint (opsional)",
            info="Endpoint API Astra DB (https://...apps.astra.datastax.com) atau via env ASTRA_DB_API_ENDPOINT.",
        ),
        MessageTextInput(
            name="astra_collection",
            display_name="Astra DB Collection (opsional)",
            value="scam_game_records",
            info="Nama collection di Astra DB untuk menyimpan riwayat permainan & leaderboard.",
        ),
        DropdownInput(
            name="output_format",
            display_name="Format Output",
            info="Markdown untuk Chat Output Langflow. Teks polos untuk klien yang tidak merender markdown.",
            options=["Markdown", "Teks polos"],
            value="Markdown",
        ),
    ]

    outputs = [
        Output(display_name="Respons Game", name="response", method="run_game"),
    ]

    def _session_id(self):
        override = (getattr(self, "session_override", "") or "").strip()
        if override:
            return override
        user_input = getattr(self, "user_input", None)
        user_sid = getattr(user_input, "session_id", None)
        if user_sid and str(user_sid).strip():
            return str(user_sid).strip()
        graph = getattr(self, "graph", None)
        sid = getattr(graph, "session_id", None) if graph else None
        return str(sid) if sid else "default"

    def run_game(self) -> Message:
        raw = self.user_input
        if hasattr(raw, "text"):
            raw = raw.text

        astra_cfg = {
            "token": (getattr(self, "astra_token", "") or "").strip(),
            "endpoint": (getattr(self, "astra_endpoint", "") or "").strip(),
            "collection": (getattr(self, "astra_collection", "") or "").strip() or "scam_game_records",
        }

        reply = handle(self._session_id(), str(raw or ""), astra_cfg=astra_cfg)
        if getattr(self, "output_format", "Markdown") == "Markdown":
            reply = to_markdown(reply)
        self.status = reply[:80]
        return Message(text=reply)
