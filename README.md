# OpenCV Gesture Block Blast (5x5 Adaptive Edition)

Game puzzle penempatan balok yang dikontrol gerakan tangan, **tanpa MediaPipe**.
Tangan dilacak lewat segmentasi warna (sarung tangan biru muda di ruang HSV,
atau warna kulit di ruang YCrCb), lalu dikendalikan dengan mekanik **Hover & Dwell**.

## Struktur

```
gesture_block_blast/
├── main.py            # loop game, state machine Hover & Dwell, keyboard
├── hand_tracker.py    # kamera, kalibrasi, segmentasi warna, kontur, smoothing
├── game_logic.py      # papan 5x5, katalog balok, fit-checking, spawner, skor
├── ui.py              # rendering OpenCV (layout, papan, slot, kursor, debug)
├── config.py          # semua angka yang bisa disetel
├── requirements.txt
├── tests/test_game_logic.py
├── assets/            # tempat aset nanti (masih kosong)
└── profiles/          # profil warna hasil kalibrasi (dibuat otomatis)
```

## Instalasi & menjalankan

```bash
python -m venv venv
# Windows: venv\Scripts\activate     macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
python main.py
```

Butuh Python 3.10+. Pakai `opencv-python` versi 4.x (bukan `-headless`, karena
butuh jendela). Kalau kamera tidak terdeteksi, game otomatis jalan dengan mouse.

Tes logika game: `python tests/test_game_logic.py`

## Cara main

1. **Kalibrasi** (otomatis muncul di awal): masukkan telapak bersarung tangan ke
   kotak kuning sampai penuh, tekan **SPASI**, tahan diam ~1 detik.
2. Cek layar pratinjau: area **hijau** = yang terdeteksi. Pastikan hanya sarung
   tangan yang hijau. **ENTER** untuk mulai, **SPASI** untuk ulangi.
3. **Ambil balok**: arahkan tangan ke slot di bawah, tahan 1 detik.
4. **Taruh balok**: arahkan ke papan. Bayangan muncul (merah = tidak muat,
   baris/kolom yang akan terhapus ikut disorot). Tahan diam 1,2 detik.
5. **Batal**: tarik tangan keluar papan, atau tahan di slot asal 1 detik.
   Kalau tangan hilang dari kamera >1,5 detik, balok juga dikembalikan.

| Tombol | Fungsi |
|---|---|
| SPASI / ENTER | ambil sampel / selesai kalibrasi |
| L | (layar kalibrasi) pakai profil warna tersimpan |
| C | kalibrasi ulang kapan saja |
| D | jendela debug: mask + trackbar untuk setel rentang warna manual |
| S | simpan profil warna saat ini |
| M | ganti input tangan / mouse (mouse berguna untuk tes tanpa kamera) |
| R | main ulang |
| Q / ESC | keluar |

## Tips supaya tetap jalan di ruang kelas

- **Kalibrasi ulang di lokasi** (tombol C), setelah lampu ruangan menyala.
  Kamera dibiarkan otomatis dulu, lalu exposure & white balance **dikunci**
  tepat sebelum sampel diambil. Status penguncian tampil di bawah layar
  (tidak semua webcam mendukung).
- Simpan profil per lokasi: setelah kalibrasi, salin `profiles/profil_glove.json`
  jadi mis. `profil_kelas.json` sebagai cadangan.
- Hindari benda biru di belakang: jeans, kemeja biru, langit dari jendela, kursi
  plastik biru. Jangan membelakangi jendela/proyektor.
- Biru muda bisa terlihat keputihan di bawah cahaya sangat terang. Batas
  bawah **S (saturasi)** memisahkannya dari papan tulis. Kalau sarung tangan
  "bolong-bolong" di mask, turunkan `S min` lewat jendela debug (D); kalau papan
  tulis ikut hijau, naikkan.
- Kotak kuning di thumbnail kamera = **zona gerak**. Tangan cukup bergerak di
  dalam kotak itu untuk menjangkau seluruh layar (atur `ACTIVE_ZONE` di config).

## Pengaturan penting (`config.py`)

| Nama | Default | Keterangan |
|---|---|---|
| `TRACK_MODE` | `"glove"` | `"skin"` untuk mode warna kulit (YCrCb + hapus wajah) |
| `CAMERA_INDEX` | `0` | ganti ke 1/2 kalau pakai webcam eksternal |
| `CAMERA_BACKEND` | `None` | di Windows coba `"dshow"` kalau kamera lambat / lock tidak jalan |
| `CURSOR_POINT` | `"palm"` | `"centroid"` = momen kontur seperti PRD awal |
| `SMOOTHING` | `"oneeuro"` | `"ema"` = EMA α tetap seperti PRD (`EMA_ALPHA`) |
| `DWELL_PICK` / `DWELL_PLACE` | 1.0 / 1.2 s | waktu tahan ambil / taruh |
| `FAIR_PLAY` | `"strong"` | `"basic"` = minimal 1 balok muat (aturan PRD) |
| `TIER_TABLE` | sesuai PRD | peluang tier per rentang skor |
| `DISPLAY_SCALE` | 1.0 | kecilkan kalau jendela 1280x720 tidak muat di layar |

## Catatan desain (beda dari PRD awal)

- **Penanda**: sarung tangan biru muda (HSV) sebagai default; mode kulit tetap ada.
  Ubah poin "Batasan Teknis" di PRD sesuai.
- **Kalibrasi** memakai persentil 5–95 + margin (bukan min/max) dan membuang
  piksel outlier, jadi tidak rusak oleh sela jari atau latar di pojok kotak.
- **Titik kursor** default = pusat telapak (distance transform), tidak tertarik
  ke arah lengan seperti centroid.
- **Smoothing** One Euro Filter: EMA dengan α adaptif (halus saat diam untuk
  dwell, responsif saat bergerak).
- **Histeresis target**: sel target baru diterima setelah stabil 4 frame, jadi
  timer dwell tidak ter-reset karena jitter di perbatasan petak.
- **Snap ke tepi**: posisi balok di-clamp ke dalam papan.
- **Cancel** hanya aktif setelah balok pernah masuk papan (atau tahan di slot asal),
  supaya balok tidak langsung batal saat baru diambil dari slot di luar papan.
  Ada cooldown 0,8 detik dan slot yang baru dibatalkan tidak bisa langsung
  diambil lagi sebelum kursor keluar dulu.
- **Fair-play kuat**: spawner mencari set di mana ketiga balok bisa ditaruh dalam
  suatu urutan (pencarian bitmask, cepat di papan 5x5). Maksimal 1 balok Tier 3
  per set supaya papan kecil tidak langsung penuh.
- **Skor**: 1 poin/petak + 10 × (jumlah garis)² × pengali kombo
  (1 + 0,5 per kombo berturut-turut) + 50 bonus papan bersih.

## Mengganti UI dengan aset

Semua gambar ada di `ui.py`. Untuk memakai aset (PNG balok, latar, font), ganti
isi `draw_cell`, `Renderer._draw_header`, `_draw_slots`, dst. Simpan file aset di
folder `assets/`. Logika game dan state machine tidak perlu diubah.
