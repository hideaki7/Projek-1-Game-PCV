import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Kamera ---
CAMERA_INDEX = 0               # ganti ke 1/2 jika memakai webcam eksternal
CAMERA_BACKEND = None          # None, "dshow", atau "msmf"
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720
MIRROR = True
LOCK_CAMERA = False            # kunci exposure & white balance saat kalibrasi

# --- Pelacakan Tangan ---
TRACK_MODE = "glove"           # "glove" (warna objek/HSV) atau "skin" (kulit/YCrCb)
PROC_WIDTH = 640               # resolusi pemrosesan deteksi
MIN_AREA_FRAC = 0.006          # batas minimum ukuran kontur tangan (fraksi layar)
MORPH_KERNEL = 7
CURSOR_POINT = "palm"          # "palm" (pusat telapak) atau "centroid"

GLOVE_DEFAULT_RANGE = ((95, 45, 25), (135, 255, 255))
SKIN_DEFAULT_RANGE = ((0, 133, 77), (255, 173, 127))

CALIB_FRAMES = 25              # jumlah sampel frame saat kalibrasi tahan SPASI
CALIB_ROI_FRAC = 0.14          # ukuran kotak kalibrasi (fraksi lebar layar)
GLOVE_MARGIN = (10, 40, 45)    # toleransi H, S, V dari warna dominan
GLOVE_MIN_S = 20
GLOVE_MIN_V = 15
SKIN_MARGIN = (6, 6)           # toleransi Cr, Cb
REMOVE_FACE = True
PROFILE_DIR = "profiles"

ACTIVE_ZONE = (0.15, 0.12, 0.85, 0.88)  # area gerak tangan di kamera (x0, y0, x1, y1)

# --- Penghalus Kursor (Smoothing) ---
SMOOTHING = "oneeuro"          # "oneeuro" atau "ema"
EMA_ALPHA = 0.25
ONE_EURO_MIN_CUTOFF = 1.2      # makin kecil makin stabil saat diam
ONE_EURO_BETA = 0.004          # makin besar makin responsif saat gerak cepat
ONE_EURO_D_CUTOFF = 1.0
SMOOTHER_RESET_AFTER = 0.3

# --- Interaksi Hover & Dwell (detik) ---
DWELL_PICK = 1.0               # tahan untuk ambil balok
DWELL_PLACE = 1.2              # tahan untuk taruh balok
DWELL_CANCEL = 1.0             # tahan di slot asal untuk batal
DWELL_BUTTON = 1.2             # tahan di tombol Main Lagi
PICK_COOLDOWN = 0.8
TARGET_STABLE_FRAMES = 4
BOARD_MARGIN = 0.35
CANCEL_OUTSIDE_TIME = 0.5
HAND_LOST_CANCEL = 1.5

# --- Aturan Game & Skor ---
BOARD_SIZE = 5
FAIR_PLAY = "strong"           # "strong" (3 balok pasti muat) atau "basic" (min 1 muat)
MAX_TIER3_PER_SET = 1
TIER_TABLE = [                 # (skor_minimum, (peluang_tier1, tier2, tier3))
    (0, (0.8, 0.2, 0.0)),
    (200, (0.3, 0.5, 0.2)),
    (500, (0.1, 0.4, 0.5)),
]
LEVEL_NAMES = ["Mudah", "Sedang", "Sulit"]
POINTS_PER_CELL = 1
LINE_POINTS = 10               # bonus garis = LINE_POINTS * (jumlah_garis ^ 2)
COMBO_STEP = 0.5               # tambahan multiplier per kombo berturut-turut
BOARD_CLEAR_BONUS = 50
HIGHSCORE_FILE = "highscore.json"

# --- Tampilan & Aset ---
WINDOW_NAME = "Blast Block"
CANVAS_W = 1280
CANVAS_H = 720
DISPLAY_SCALE = 1.0            # skala ukuran jendela (mis. 0.85 untuk layar kecil)

ASSETS_DIR = os.path.join(BASE_DIR, "game assets")
LOGO_PATH = os.path.join(ASSETS_DIR, "BLAST BLOCK.png")
FONT_HEADING_PATH = os.path.join(ASSETS_DIR, "PixelifySans-Bold.ttf")
FONT_BODY_PATH = os.path.join(ASSETS_DIR, "VT323-Regular.ttf")

# --- Audio & Gain (dB) ---
BGM_PATH = os.path.join(ASSETS_DIR, "Happy Ever After.mp3")
SFX_PLACE_PATH = os.path.join(ASSETS_DIR, "Place.mp3")
SFX_BLAST_PATH = os.path.join(ASSETS_DIR, "Blast.mp3")
SFX_GAMEOVER_PATH = os.path.join(ASSETS_DIR, "Game Over (2).mp3")

BGM_GAIN_DB = -6.0             # gain backsound (dB, negatif = suara kecil)
SFX_PLACE_GAIN_DB = 3.0        # gain suara saat meletakkan balok (dB)
SFX_BLAST_GAIN_DB = 6.0        # gain suara saat blast / dapat poin (dB)
SFX_GAMEOVER_GAIN_DB = -3.0    # gain suara saat game over (dB)
