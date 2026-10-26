<div align="center">

![Blast Block Logo](game%20assets/BLAST%20BLOCK.png)

### Puzzle Balok 5x5 Interaktif Berbasis Gestur Tangan

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![OpenCV](https://img.shields.io/badge/OpenCV-4.x-5C3EE8?style=for-the-badge&logo=opencv&logoColor=white)](https://opencv.org/)
[![NumPy](https://img.shields.io/badge/NumPy-1.24%2B-013243?style=for-the-badge&logo=numpy&logoColor=white)](https://numpy.org/)

---

[**1. Konsep Game**](#1-penjelasan-game-dan-konsepnya) |
[**2. Tampilan Game**](#2-tampilan-game) |
[**3. Cara Bermain**](#3-panduan-cara-bermain) |
[**4. Fitur Game**](#4-fitur-utama-di-dalam-game) |
[**5. Tech Stack & Tools**](#5-dokumentasi-tech-stack-dan-tools)

</div>

---

## 1. Penjelasan Game dan Konsepnya

**Blast Block** adalah game puzzle penempatan balok pada papan berukuran **5x5** yang dikendalikan langsung menggunakan **gesture tangan di depan kamera**, murni menggunakan pengolahan citra OpenCV tanpa bantuan MediaPipe.

### Konsep Utama
1. **Pelacakan Warna Klasik (Computer Vision):**
   Sistem mendeteksi tangan atau sarung tangan/objek berwarna menggunakan segmentasi ruang warna **HSV** (*warna objek dominan*) atau **YCrCb** (*warna kulit*), dilengkapi operasi morfologi dan *Distance Transform* untuk menemukan titik pusat telapak tangan yang stabil.
2. **Interaksi *Hover & Dwell* (Arahkan & Tahan):**
   Pemain tidak perlu melakukan klik fisik atau gestur jari yang rumit. Cukup **arahkan kursor tangan** ke balok atau petak papan, lalu **tahan diam sebentar (*dwell*)** hingga cincin indikator melingkar penuh untuk mengambil atau menaruh balok.
3. **Pecahkan Baris & Kolom (*Blast!*):**
   Susun balok di papan 5x5 hingga membentuk satu baris penuh (horizontal) atau satu kolom penuh (vertikal). Garis yang penuh akan langsung hancur (*blast*), memberikan poin bonus serta pengganda **Kombo** jika dilakukan berturut-turut.

---

## 2. Tampilan Game

Antarmuka **Blast Block** dirancang dengan nuansa mesin *retro arcade* lengkap dengan efek *scanline* CRT, balok 3D *pixel-bevel*, indikator LED kamera, serta papan skor digital.

### A. Layar Kalibrasi Sensor
Layar awal saat game dibuka untuk mengenali warna objek/sarung tangan atau telapak tangan sesuai kondisi cahaya ruangan Anda.

<div align="center">
  <img src="Documentations/Kalibrasi Tangan.png" alt="[Placeholder] Screenshot Tampilan Kalibrasi" width="780" />
  <br>
  <em>Gambar 1: Tampilan Layar Kalibrasi Sensor Warna</em>
</div>

---

### B. Layar Utama Permainan (*In-Game*)
Tampilan utama saat bermain yang terdiri dari **Header Skor & Rekor**, **Panel Status & Petunjuk** di kiri, **Papan 5x5 & 3 Slot Balok** di tengah, serta **Monitor Sensor Kamera & Kontrol Arcade** di kanan.

<div align="center">
  <img src="Documentations/Tampilan Ingame.png" alt="[Placeholder] Screenshot Tampilan In-Game" width="780" />
  <br>
  <em>Gambar 2: Tampilan Utama Permainan Blast Block</em>
</div>

---

## 3. Panduan Cara Bermain

### Persiapan & Menjalankan Game
Pastikan Anda menggunakan **Python 3.10+**, lalu jalankan perintah berikut di terminal:

```bash
# 1. Buat & aktifkan virtual environment (opsional tapi disarankan)
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate # macOS / Linux

# 2. Instal seluruh dependensi
pip install -r requirements.txt

# 3. Mulai bermain
python main.py
```

---

### Langkah 1: Kalibrasi Warna Tangan / Objek
1. Saat game pertama kali dibuka, layar **Kalibrasi Sensor** akan tampil otomatis.
2. Masukkan objek berwarna / tangan bersarung tangan ke dalam **kotak target di tengah layar** hingga memenuhi kotak.
3. Tekan **`ENTER`** untuk langsung mengunci warna dominan saat ini, atau tekan **`SPASI`** (tahan diam sekitar 1 detik) untuk mengambil sampel beberapa *frame*.
4. Pastikan pada layar pratinjau hanya objek/tangan Anda yang berubah menjadi warna **Hijau**. Tekan **`ENTER`** sekali lagi untuk masuk ke permainan.

<div align="center">
  <!-- Ganti src dengan path GIF atau MP4 demo kalibrasi Anda -->
  <img src="Documentations/Kalibrasi Tangan.gif" alt="[Placeholder Video/GIF] Demo Cara Kalibrasi" width="680" />
  <br>
  <em>Video 1: Demo singkat proses kalibrasi warna objek/tangan</em>
</div>

---

### Langkah 2: Mengambil Balok (*Pick Block*)
1. Perhatikan **3 Slot Balok** yang tersedia di bagian bawah papan.
2. Gerakkan tangan Anda di dalam zona kamera hingga kursor *reticle* berada di atas salah satu slot balok.
3. **Tahan tangan diam selama `1.0 detik`** hingga cincin kuning penuh, maka balok akan terangkat dan mengikuti kursor Anda.

<div align="center">
  <!-- Ganti src dengan path GIF atau MP4 demo pick block Anda -->
  <img src="Documentations/Meletakkan Blok.png" alt="[Placeholder Video/GIF] Demo Cara Pick Block" width="680" />
  <br>
  <em>Gambar 3: Mengarahkan kursor dan menahan 1 detik untuk mengambil balok</em>
</div>

---

### Langkah 3: Meletakkan Balok & Mencetak Poin (*Place & Blast*)
1. Bawa balok yang sedang dipegang ke atas **Papan 5x5**.
2. Bayangan balok (*ghost preview*) akan muncul di papan:
   - **Warna Asli Balok:** Posisi valid dan muat ditempatkan.
   - **Merah:** Posisi tidak muat / menabrak balok lain.
   - **Sorotan Cyan Neon:** Menandakan baris/kolom tersebut akan pecah (*Blast!*) jika balok ditaruh di sana.
3. **Tahan tangan diam selama `1.2 detik`** pada posisi valid untuk meletakkan balok.
4. **Membatalkan Balok:** Tarik kursor keluar dari area papan selama `0.5 detik` atau tahan kembali di slot asal selama `1.0 detik` untuk mengembalikan balok ke slot.

<div align="center">
  <!-- Ganti src dengan path GIF atau MP4 demo place block Anda -->
  <img src="Documentations/Meletakkan Blok.gif" alt="[Placeholder Video/GIF] Demo Cara Place Block & Blast" width="680" />
  <br>
  <em>Video 2: Demo meletakkan balok ke papan 5x5 dan menghancurkan baris/kolom</em>
</div>

---

### Daftar Tombol Kontrol (*Keyboard Shortcuts*)

| Tombol | Fungsi |
| :---: | :--- |
| **`SPASI`** | Mengambil sampel warna beruntun saat di layar kalibrasi |
| **`ENTER`** | Mengunci warna dominan & memulai permainan |
| **`L`** | Memuat profil warna terakhir yang tersimpan (di layar kalibrasi) |
| **`C`** | Masuk kembali ke layar **Kalibrasi Sensor** kapan saja |
| **`D`** | Membuka/menutup jendela **Debug Mask** (pengaturan manual HSV) |
| **`S`** | Menyimpan profil rentang warna saat ini ke folder `profiles/` |
| **`M`** | Berpindah mode input antara **Tangan (Kamera)** dan **Mouse** |
| **`R`** | Mengulang permainan dari awal (*Restart*) |
| **`Q` / `ESC`** | Keluar dari permainan |

---

## 4. Fitur Utama di Dalam Game

### 1. *Fair-Play Adaptive Spawner* & Sistem Level
Game ini dilengkapi algoritma pencari kombinasi (*backtracking bitmask*) yang memastikan setiap 3 balok baru yang muncul **selalu memiliki solusi penempatan** di papan 5x5 Anda. Tingkat kesulitan balok juga meningkat otomatis mengikuti skor:
- **Level Mudah (Skor 0 sampai 199):** Dominan balok kecil (`1x1`, `1x2`, `2x2`).
- **Level Sedang (Skor 200 sampai 499):** Kombinasi balok menengah (`L kecil`, `1x3`, `T mini`).
- **Level Sulit (Skor 500+):** Balok tantangan berukuran besar (`L besar`, `Garis 4`, `Garis 5`, `Silang`).

### 2. *One-Euro Filter Smoothing* & *Target Stabilizer*
Agar kursor tidak bergetar saat tangan menahan posisi (*dwell*), sistem memakai **One-Euro Filter** yang adaptif (stabil saat tangan diam, namun tetap cepat dan responsif saat tangan berpindah) ditambah histeresis **Target Stabilizer** antar-petak.

### 3. *Backsound & SFX*
Dilengkapi sistem audio *multi-track* secara *real-time*:
- **Backsound (`Happy Ever After`):** Berputar otomatis ketika game dibuka.
- **Sound Effects:** Efek suara saat menaruh balok (`Place.mp3`), memecahkan baris/kolom (`Blast.mp3`), dan saat permainan berakhir (`Game Over (2).mp3`).

### 4. *Debug Mask* & Pengaturan Manual HSV (`Tombol D`)
Jika kondisi pencahayaan ruangan sangat ekstrem (misalnya pantulan lampu proyektor atau latar belakang berwarna serupa), Anda dapat menekan tombol **`D`** untuk membuka jendela **Debug Mask** dan menyetel *trackbar* rentang warna secara langsung.

<div align="center">
  <img src="Documentations/Kalibrasi HSV.gif" alt="[Placeholder] Cara Mengatur HSV di Jendela Debug Mask" width="720" />
  <br>
  <em>Video 3: Jendela Debug Mask (Tombol D) untuk mengatur batas H, S, dan V secara manual</em>
</div>

**Tips Mengatur Trackbar HSV di Jendela Debug:**
- **`H min` & `H max` (*Hue* / Rona Warna):** Geser hingga sesuai dengan warna dasar sarung tangan/objek Anda.
- **`S min` & `S max` (*Saturation* / Kepekatan):** Jika sarung tangan terlihat berlubang-lubang hitam di layar *mask*, **turunkan `S min`**. Sebaliknya, jika dinding putih/papan tulis ikut terdeteksi putih, **naikkan `S min`**.
- **`V min` & `V max` (*Value* / Kecerahan):** Turunkan `V min` jika ruangan agak redup, atau naikkan jika bayangan gelap ikut terdeteksi.
- Tekan **`S`** setelah selesai agar setelan tersimpan ke profil.

---

## 5. Dokumentasi Tech Stack dan Tools

### Struktur Proyek
```text
gesture_block_blast/
├── main.py                  # Game loop utama, state machine Hover & Dwell, AudioManager, input
├── game_logic.py            # Logika papan 5x5 (bitmask), katalog balok, spawner adaptif, skor
├── hand_tracker.py          # Kamera, kalibrasi warna dominan, segmentasi HSV/YCrCb, One-Euro filter
├── ui.py                    # Renderer antarmuka Retro Arcade, efek partikel/garis, jendela debug
├── config.py                # Pusat konfigurasi angka (kamera, dwell time, level, gain audio, path)
├── requirements.txt         # Daftar pustaka Python yang dibutuhkan
├── game assets/             # Aset gambar logo, font pixel (.ttf), dan efek suara/musik (.mp3)
├── profiles/                # Penyimpanan profil kalibrasi warna (.json)
└── tests/
    └── test_game_logic.py   # Unit test logika permainan & fair-play spawner
```

### Coding Stack & Pustaka Utama
- **Python 3.10+**: Bahasa pemrograman utama.
- **OpenCV (`opencv-python`)**: Akuisisi kamera, konversi ruang warna (`HSV`/`YCrCb`), morfologi citra, pencarian kontur, *Distance Transform*, dan pembuatan kanvas tampilan.
- **NumPy (`numpy`)**: Operasi matriks cepat untuk papan permainan, perhitungan *bitmask*, manipulasi piksel *frame*, serta *mixing* buffer audio.
- **Pillow (`PIL`)**: *Rendering* tipografi kustom bergaya pixel-art (`PixelifySans-Bold.ttf` & `VT323-Regular.ttf`) serta pemrosesan transparansi logo.
- **SoundDevice & SoundFile (`sounddevice`, `soundfile`)**: Pemutaran *stream* audio berlatensi rendah untuk *backsound looping* dan efek suara simultan dengan pengaturan *decibel gain*.

### Tools & AI Assistants
Pengembangan proyek **Blast Block** ini didukung oleh berbagai *tools* desain dan asisten AI:
- **Figma**: Digunakan untuk merancang aset visual, tata letak konsep UI, serta pembuatan logo **BLAST BLOCK**.
- **Claude**: Membantu dalam perancangan arsitektur awal algoritma permainan, logika *computer vision*, serta struktur sistem.
- **Antigravity**: Membantu dalam *debugging*, penambahan fitur, dan perombakan UI.
