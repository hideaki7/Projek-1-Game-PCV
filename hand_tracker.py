"""Pelacak tangan tanpa MediaPipe: segmentasi warna + kontur + smoothing.

Dua mode (atur di config.TRACK_MODE):
  - "glove": sarung tangan berwarna, segmentasi di ruang HSV (default).
  - "skin" : warna kulit, segmentasi kanal Cr/Cb (YCrCb) + penghapusan wajah.

Alur per frame:
  frame -> resize -> konversi warna -> inRange -> morfologi (open, close)
        -> kontur terbesar -> titik kursor (pusat telapak / centroid)
"""
from __future__ import annotations

import json
import math
import os
import platform
from dataclasses import dataclass

import cv2
import numpy as np

import config

# --------------------------------------------------------------------------
# Kamera
# --------------------------------------------------------------------------
_BACKENDS = {
    None: cv2.CAP_ANY,
    "dshow": cv2.CAP_DSHOW,
    "msmf": cv2.CAP_MSMF,
    "v4l2": cv2.CAP_V4L2,
    "avfoundation": cv2.CAP_AVFOUNDATION,
}

# Nilai CAP_PROP_AUTO_EXPOSURE berbeda per backend:
# V4L2 (Linux): 1 = manual, 3 = otomatis. DirectShow/MSMF (Windows): 0.25 / 0.75.
_LINUX = platform.system() == "Linux"
_AE_MANUAL = 1 if _LINUX else 0.25
_AE_AUTO = 3 if _LINUX else 0.75


def open_camera(index: int = config.CAMERA_INDEX,
                width: int = config.CAMERA_WIDTH,
                height: int = config.CAMERA_HEIGHT,
                backend: str | None = config.CAMERA_BACKEND):
    """Buka webcam. Kembalikan None kalau gagal (game lalu jalan dengan mouse)."""
    cap = cv2.VideoCapture(index, _BACKENDS.get(backend, cv2.CAP_ANY))
    if not cap.isOpened():
        cap.release()
        return None
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    ok, _ = cap.read()
    if not ok:
        cap.release()
        return None
    return cap


def lock_camera(cap) -> str:
    """Matikan auto exposure & auto white balance supaya warna stabil.

    Tidak semua webcam/driver menurut. Hasilnya dilaporkan sebagai teks.
    """
    notes = []
    exposure = cap.get(cv2.CAP_PROP_EXPOSURE)
    if cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, _AE_MANUAL):
        if exposure != 0:
            cap.set(cv2.CAP_PROP_EXPOSURE, exposure)
        notes.append("exposure dikunci")
    else:
        notes.append("exposure tidak bisa dikunci")
    wb = cap.get(cv2.CAP_PROP_WB_TEMPERATURE)
    if cap.set(cv2.CAP_PROP_AUTO_WB, 0):
        if wb > 0:
            cap.set(cv2.CAP_PROP_WB_TEMPERATURE, wb)
        notes.append("white balance dikunci")
    else:
        notes.append("white balance tidak bisa dikunci")
    return "Kamera: " + ", ".join(notes)


def unlock_camera(cap) -> None:
    """Kembalikan kamera ke mode otomatis (dipakai sebelum kalibrasi ulang)."""
    cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, _AE_AUTO)
    cap.set(cv2.CAP_PROP_AUTO_WB, 1)


# --------------------------------------------------------------------------
# Smoothing
# --------------------------------------------------------------------------
class EmaFilter:
    """P_t = P_{t-1} + alpha * (P_raw - P_{t-1})  (sesuai PRD)."""

    def __init__(self, alpha: float = config.EMA_ALPHA):
        self.alpha = alpha
        self.reset()

    def reset(self) -> None:
        self.x = None

    def __call__(self, x, t: float):
        x = np.asarray(x, dtype=float)
        if self.x is None:
            self.x = x
        else:
            self.x = self.x + self.alpha * (x - self.x)
        return self.x


class OneEuroFilter:
    """EMA dengan alpha adaptif: halus saat tangan diam, responsif saat bergerak.

    Casiez et al., "1 Euro Filter" (CHI 2012).
    """

    def __init__(self, min_cutoff: float = config.ONE_EURO_MIN_CUTOFF,
                 beta: float = config.ONE_EURO_BETA,
                 d_cutoff: float = config.ONE_EURO_D_CUTOFF):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self.reset()

    def reset(self) -> None:
        self.x = None
        self.dx = np.zeros(2)
        self.t = None

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def __call__(self, x, t: float):
        x = np.asarray(x, dtype=float)
        if self.x is None:
            self.x, self.t = x, t
            return x
        dt = max(t - self.t, 1e-3)
        self.t = t
        dx = (x - self.x) / dt
        a_d = self._alpha(self.d_cutoff, dt)
        self.dx = a_d * dx + (1 - a_d) * self.dx
        cutoff = self.min_cutoff + self.beta * float(np.linalg.norm(self.dx))
        a = self._alpha(cutoff, dt)
        self.x = a * x + (1 - a) * self.x
        return self.x


class CursorSmoother:
    def __init__(self, method: str = config.SMOOTHING):
        self.filter = OneEuroFilter() if method == "oneeuro" else EmaFilter()

    def __call__(self, point, t: float) -> tuple[float, float]:
        x = self.filter(point, t)
        return float(x[0]), float(x[1])

    def reset(self) -> None:
        self.filter.reset()


# --------------------------------------------------------------------------
# Tracker
# --------------------------------------------------------------------------
@dataclass
class TrackResult:
    found: bool
    point: tuple[float, float] | None     # (x, y) ternormalisasi 0..1 pada frame
    frame_small: np.ndarray               # frame yang diproses (sudah di-resize)
    mask: np.ndarray                      # mask biner hasil segmentasi
    contour: np.ndarray | None = None
    area_frac: float = 0.0


class HandTracker:
    def __init__(self, mode: str = config.TRACK_MODE):
        if mode not in ("glove", "skin"):
            raise ValueError("mode harus 'glove' atau 'skin'")
        self.mode = mode
        default = config.GLOVE_DEFAULT_RANGE if mode == "glove" else config.SKIN_DEFAULT_RANGE
        self.lo = np.array(default[0], dtype=np.uint8)
        self.hi = np.array(default[1], dtype=np.uint8)
        self.calibrated = False
        self.warning = ""
        k = config.MORPH_KERNEL
        self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))

        self.face_cascade = None
        if mode == "skin" and config.REMOVE_FACE:
            self.face_cascade = self._load_face_cascade()
            if self.face_cascade is None:
                self.warning = ("Deteksi wajah tidak tersedia di versi OpenCV ini; "
                                "jaga wajah di luar zona gerak.")
        self._faces: list = []
        self._frame_i = 0

    @staticmethod
    def _load_face_cascade():
        """Haar cascade bawaan OpenCV 4.x. Di OpenCV 5 dipindah ke contrib."""
        Cascade = getattr(cv2, "CascadeClassifier", None)
        data = getattr(cv2, "data", None)
        if Cascade is None or data is None:
            return None
        cascade = Cascade(os.path.join(data.haarcascades, "haarcascade_frontalface_default.xml"))
        return None if cascade.empty() else cascade

    @property
    def label(self) -> str:
        return "Sarung tangan (HSV)" if self.mode == "glove" else "Kulit (YCrCb)"

    # ------------------------------------------------------------ helper
    @staticmethod
    def resize(frame: np.ndarray) -> np.ndarray:
        h, w = frame.shape[:2]
        if w <= config.PROC_WIDTH:
            return frame
        s = config.PROC_WIDTH / w
        return cv2.resize(frame, (config.PROC_WIDTH, int(round(h * s))),
                          interpolation=cv2.INTER_AREA)

    def convert(self, small: np.ndarray) -> np.ndarray:
        code = cv2.COLOR_BGR2HSV if self.mode == "glove" else cv2.COLOR_BGR2YCrCb
        return cv2.cvtColor(small, code)

    @staticmethod
    def roi_rect(shape) -> tuple[int, int, int, int]:
        """Kotak kalibrasi di tengah frame (koordinat piksel)."""
        h, w = shape[:2]
        side = int(config.CALIB_ROI_FRAC * w)
        cx, cy = w // 2, h // 2
        return cx - side // 2, cy - side // 2, cx + side // 2, cy + side // 2

    @classmethod
    def roi_rect_norm(cls, shape) -> tuple[float, float, float, float]:
        h, w = shape[:2]
        x0, y0, x1, y1 = cls.roi_rect(shape)
        return x0 / w, y0 / h, x1 / w, y1 / h

    def set_range(self, lo, hi) -> None:
        self.lo = np.clip(np.asarray(lo), 0, 255).astype(np.uint8)
        self.hi = np.clip(np.asarray(hi), 0, 255).astype(np.uint8)

    def range_text(self) -> str:
        lo, hi = self.lo, self.hi
        if self.mode == "glove":
            return (f"H {lo[0]}-{hi[0]}   S {lo[1]}-{hi[1]}   V {lo[2]}-{hi[2]}")
        return f"Cr {lo[1]}-{hi[1]}   Cb {lo[2]}-{hi[2]}"

    # -------------------------------------------------------- kalibrasi
    def calibrate(self, samples: list[np.ndarray]) -> None:
        """Hitung rentang warna dari kumpulan piksel ROI (sudah dalam HSV/YCrCb)."""
        px = np.vstack(samples).astype(np.float32)
        if self.mode == "glove":
            self._calibrate_glove(px)
        else:
            self._calibrate_skin(px)
        self.calibrated = True

    def _calibrate_glove(self, px: np.ndarray) -> None:
        # Buang piksel yang jelas bukan sarung tangan (sela jari, latar)
        keep = (np.abs(px[:, 0] - np.median(px[:, 0])) <= 20) & (px[:, 1] >= 15)
        if keep.sum() > 0.3 * len(px):
            px = px[keep]
        margin = np.array(config.GLOVE_MARGIN, dtype=np.float32)
        lo = np.percentile(px, 5, axis=0) - margin
        hi = np.percentile(px, 95, axis=0) + margin
        lo[0], hi[0] = max(lo[0], 0), min(hi[0], 179)
        lo[1] = max(lo[1], config.GLOVE_MIN_S)
        lo[2] = max(lo[2], config.GLOVE_MIN_V)
        hi[1], hi[2] = 255, 255
        self.set_range(lo, hi)
        s_p5 = float(np.percentile(px[:, 1], 5))
        self.warning = ""
        if s_p5 < config.GLOVE_MIN_S + 10:
            self.warning = ("Saturasi sarung tangan rendah. Kurangi cahaya terlalu terang, "
                            "atau turunkan 'S min' di jendela debug (tombol D).")

    def _calibrate_skin(self, px: np.ndarray) -> None:
        cr, cb = px[:, 1], px[:, 2]
        keep = (np.abs(cr - np.median(cr)) <= 15) & (np.abs(cb - np.median(cb)) <= 15)
        if keep.sum() > 0.3 * len(px):
            px = px[keep]
        p5 = np.percentile(px, 5, axis=0)
        p95 = np.percentile(px, 95, axis=0)
        m_cr, m_cb = config.SKIN_MARGIN
        self.set_range((0, p5[1] - m_cr, p5[2] - m_cb), (255, p95[1] + m_cr, p95[2] + m_cb))
        self.warning = ""

    # ------------------------------------------------------- segmentasi
    def segment(self, conv: np.ndarray, small_bgr: np.ndarray) -> np.ndarray:
        mask = cv2.inRange(conv, self.lo, self.hi)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self.kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self.kernel, iterations=2)
        if self.face_cascade is not None:
            self._remove_faces(mask, small_bgr)
        return mask

    def _remove_faces(self, mask: np.ndarray, small_bgr: np.ndarray) -> None:
        if self._frame_i % 3 == 0:     # deteksi wajah tiap 3 frame saja (hemat CPU)
            gray = cv2.cvtColor(small_bgr, cv2.COLOR_BGR2GRAY)
            faces = self.face_cascade.detectMultiScale(gray, 1.2, 5, minSize=(40, 40))
            self._faces = list(faces) if len(faces) else []
        H, W = mask.shape
        for (x, y, w, h) in self._faces:
            # perbesar ke bawah supaya leher ikut terhapus
            x0, x1 = max(0, int(x - 0.15 * w)), min(W, int(x + 1.15 * w))
            y0, y1 = max(0, int(y - 0.25 * h)), min(H, int(y + 1.6 * h))
            mask[y0:y1, x0:x1] = 0

    # ---------------------------------------------------------- tracking
    def process(self, frame: np.ndarray) -> TrackResult:
        """Proses satu frame BGR (sudah di-mirror bila perlu)."""
        self._frame_i += 1
        small = self.resize(frame)
        mask = self.segment(self.convert(small), small)
        h, w = mask.shape
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return TrackResult(False, None, small, mask)
        contour = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(contour) / float(w * h)
        if area < config.MIN_AREA_FRAC:
            return TrackResult(False, None, small, mask, contour, area)

        if config.CURSOR_POINT == "centroid":
            m = cv2.moments(contour)
            if m["m00"] == 0:
                return TrackResult(False, None, small, mask, contour, area)
            px, py = m["m10"] / m["m00"], m["m01"] / m["m00"]
        else:
            # Pusat telapak = titik terjauh dari tepi kontur.
            # Tidak ikut tertarik ke arah lengan seperti centroid.
            hand = np.zeros_like(mask)
            cv2.drawContours(hand, [contour], -1, 255, cv2.FILLED)
            dist = cv2.distanceTransform(hand, cv2.DIST_L2, 5)
            _, _, _, (px, py) = cv2.minMaxLoc(dist)
        return TrackResult(True, (px / w, py / h), small, mask, contour, area)

    # ------------------------------------------------------------ profil
    def save_profile(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"mode": self.mode, "lo": self.lo.tolist(), "hi": self.hi.tolist()},
                      f, indent=2)

    def load_profile(self, path: str) -> bool:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("mode") != self.mode:
                return False
            self.set_range(data["lo"], data["hi"])
        except (OSError, ValueError, KeyError, TypeError):
            return False
        self.calibrated = True
        self.warning = ""
        return True


class Calibrator:
    """Mengumpulkan sampel warna dari kotak ROI selama beberapa frame.

    Fase: "wait" (menunggu SPASI) -> "sampling" -> "preview" (cek mask).
    """

    def __init__(self, tracker: HandTracker, cap):
        self.tracker = tracker
        self.cap = cap
        self.phase = "wait"
        self.samples: list[np.ndarray] = []
        self.skip = 0
        self.cam_note = ""

    def start(self) -> None:
        self.phase = "wait"
        self.samples = []
        if self.cap is not None and config.LOCK_CAMERA:
            unlock_camera(self.cap)   # biarkan kamera menyesuaikan cahaya ruangan dulu
            self.cam_note = "Kamera mode otomatis, menyesuaikan cahaya ruangan..."

    def begin_sampling(self) -> None:
        self.samples = []
        self.phase = "sampling"
        self.skip = 5                 # abaikan beberapa frame setelah kamera dikunci
        if self.cap is not None and config.LOCK_CAMERA:
            self.cam_note = lock_camera(self.cap)

    def feed(self, frame: np.ndarray) -> None:
        if self.phase != "sampling":
            return
        if self.skip > 0:
            self.skip -= 1
            return
        small = self.tracker.resize(frame)
        conv = self.tracker.convert(small)
        x0, y0, x1, y1 = self.tracker.roi_rect(small.shape)
        self.samples.append(conv[y0:y1, x0:x1].reshape(-1, 3).copy())
        if len(self.samples) >= config.CALIB_FRAMES:
            self.tracker.calibrate(self.samples)
            self.phase = "preview"

    @property
    def progress(self) -> float:
        return min(1.0, len(self.samples) / config.CALIB_FRAMES)
