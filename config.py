"""Konfigurasi global OpenCV Gesture Block Blast (5x5 Adaptive Edition).

Semua angka yang mungkin perlu disetel (kamera, tracking, dwell, balancing)
dikumpulkan di sini supaya modul lain tidak perlu diubah.
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --------------------------------------------------------------------------
# Kamera
# --------------------------------------------------------------------------
CAMERA_INDEX = 0
# None = backend default OpenCV. Di Windows bisa dicoba "dshow" atau "msmf"
# kalau kamera lambat dibuka atau setting exposure tidak berpengaruh.
CAMERA_BACKEND = None
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720
MIRROR = True            # balik horizontal supaya gerakan terasa seperti cermin
LOCK_CAMERA = True       # kunci auto exposure & white balance saat kalibrasi

# --------------------------------------------------------------------------
# Tracking
# --------------------------------------------------------------------------
# "glove" = sarung tangan berwarna (HSV), "skin" = warna kulit (YCrCb)
TRACK_MODE = "glove"
PROC_WIDTH = 640               # deteksi dikerjakan di resolusi ini (lebih cepat)
MIN_AREA_FRAC = 0.006          # kontur lebih kecil dari ini (fraksi luas frame) diabaikan
MORPH_KERNEL = 7               # ukuran kernel elips untuk morfologi
# Titik kursor: "palm" = pusat telapak (distance transform, tidak tertarik ke lengan)
#               "centroid" = pusat massa momen kontur (sesuai PRD awal)
CURSOR_POINT = "palm"

# Rentang awal sebelum kalibrasi: (low, high) di ruang warna masing-masing
GLOVE_DEFAULT_RANGE = ((85, 50, 120), (130, 255, 255))    # HSV, biru muda (V tinggi: bukan jeans)
SKIN_DEFAULT_RANGE = ((0, 133, 77), (255, 173, 127))      # YCrCb, rentang klasik

CALIB_FRAMES = 25              # jumlah frame sampel saat kalibrasi
CALIB_ROI_FRAC = 0.14          # sisi kotak kalibrasi (fraksi lebar frame)
GLOVE_MARGIN = (8, 35, 50)     # margin H, S, V di luar persentil 5-95
GLOVE_MIN_S = 40               # batas bawah saturasi: pemisah sarung tangan dari putih/abu
GLOVE_MIN_V = 40
SKIN_MARGIN = (6, 6)           # margin Cr, Cb
REMOVE_FACE = True             # mode skin: hapus area wajah dengan Haar cascade
PROFILE_DIR = "profiles"

# Bagian frame kamera (x0, y0, x1, y1 dalam fraksi) yang dipetakan ke seluruh layar.
# Lebih kecil = tangan cukup bergerak sedikit, tapi kursor lebih sensitif.
ACTIVE_ZONE = (0.15, 0.12, 0.85, 0.88)

# --------------------------------------------------------------------------
# Smoothing kursor
# --------------------------------------------------------------------------
SMOOTHING = "oneeuro"          # "oneeuro" (adaptif) atau "ema" (sesuai PRD)
EMA_ALPHA = 0.25
ONE_EURO_MIN_CUTOFF = 1.2      # makin kecil makin halus saat diam
ONE_EURO_BETA = 0.004          # makin besar makin responsif saat bergerak cepat
ONE_EURO_D_CUTOFF = 1.0
SMOOTHER_RESET_AFTER = 0.3     # detik tangan hilang sebelum filter di-reset

# --------------------------------------------------------------------------
# Interaksi Hover & Dwell
# --------------------------------------------------------------------------
DWELL_PICK = 1.0
DWELL_PLACE = 1.2
DWELL_CANCEL = 1.0
DWELL_BUTTON = 1.2
PICK_COOLDOWN = 0.8            # jeda setelah menaruh/membatalkan sebelum bisa ambil lagi
TARGET_STABLE_FRAMES = 4       # histeresis: target sel baru harus stabil sekian frame
BOARD_MARGIN = 0.35            # toleransi tepi papan (satuan sel)
CANCEL_OUTSIDE_TIME = 0.5      # detik di luar papan sebelum balok dibatalkan
HAND_LOST_CANCEL = 1.5         # detik tangan hilang saat memegang balok sebelum dibatalkan

# --------------------------------------------------------------------------
# Game
# --------------------------------------------------------------------------
BOARD_SIZE = 5
# "strong": harus ada urutan penempatan agar ketiga balok muat (lebih adil di 5x5)
# "basic" : minimal 1 dari 3 balok muat (aturan minimum di PRD)
FAIR_PLAY = "strong"
MAX_TIER3_PER_SET = 1
TIER_TABLE = [                 # (skor minimum, (peluang tier1, tier2, tier3))
    (0, (0.8, 0.2, 0.0)),
    (200, (0.3, 0.5, 0.2)),
    (500, (0.1, 0.4, 0.5)),
]
LEVEL_NAMES = ["Mudah", "Sedang", "Sulit"]
POINTS_PER_CELL = 1
LINE_POINTS = 10               # bonus garis = LINE_POINTS x (jumlah garis)^2
COMBO_STEP = 0.5               # tambahan pengali per kombo berturut-turut
BOARD_CLEAR_BONUS = 50
HIGHSCORE_FILE = "highscore.json"

# --------------------------------------------------------------------------
# Tampilan
# --------------------------------------------------------------------------
WINDOW_NAME = "Gesture Block Blast 5x5"
CANVAS_W = 1280
CANVAS_H = 720
DISPLAY_SCALE = 1.0            # kecilkan (mis. 0.85) kalau jendela tidak muat di layar
