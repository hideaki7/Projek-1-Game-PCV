from __future__ import annotations

import cv2
import numpy as np
from PIL import Image, ImageFont

import config

FONT = cv2.FONT_HERSHEY_SIMPLEX
AA = cv2.LINE_AA

_FONT_CACHE: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}
_MASK_CACHE: dict[tuple[str, bool, int, str], tuple[np.ndarray, tuple[int, int]]] = {}

# Palet Warna Retro Arcade (BGR)
C_BG = (36, 18, 16)           # biru-ungu malam (midnight arcade)
C_BG_GRID = (54, 28, 24)      # garis grid latar belakang
C_PANEL = (56, 30, 26)        # isi kotak panel
C_PANEL_DARK = (32, 16, 14)   # bayangan/dalam kotak
C_PANEL_HI = (96, 56, 46)     # highlight tepi atas/kiri panel
C_EDGE = (130, 82, 65)        # bingkai panel standar
C_BOARD = (44, 22, 20)        # dasar papan 5x5
C_BOARD_EDGE = (195, 140, 65) # bingkai luar papan retro
C_EMPTY = (62, 34, 28)        # petak kosong
C_EMPTY_DARK = (38, 18, 15)   # bayangan dalam petak kosong
C_EMPTY_HI = (86, 50, 42)     # tepi bawah/kanan petak kosong
C_TEXT = (250, 245, 240)      # putih terang
C_MUTED = (185, 160, 145)     # teks sekunder (ungu-abu muda)
C_ACCENT = (55, 215, 255)     # kuning-emas arcade
C_CYAN = (245, 225, 65)       # cyan neon
C_MAGENTA = (180, 75, 245)    # magenta neon
C_VALID = (120, 240, 95)      # hijau neon
C_INVALID = (80, 70, 245)     # merah-pink neon
C_CANCEL = (50, 165, 255)     # oranye
C_WARN = (75, 195, 255)       # kuning peringatan
C_GREY = (115, 100, 95)       # balok tidak muat

# Warna balok retro cerah (1..8) selaras dengan gradien logo BLAST BLOCK
PALETTE = {
    1: (75, 75, 245),     # merah arcade
    2: (50, 145, 255),    # oranye neon
    3: (45, 215, 250),    # kuning emas
    4: (95, 225, 75),     # hijau zamrud
    5: (215, 215, 55),    # cyan tosca
    6: (245, 135, 60),    # biru elektrik
    7: (220, 85, 165),    # ungu retro
    8: (165, 90, 245),    # magenta pink
}
RING_COLORS = {"pick": C_ACCENT, "place": C_VALID, "cancel": C_CANCEL, "button": C_CYAN}

KEY_HELP = [
    ("C", "Kalibrasi ulang"),
    ("D", "Debug mask"),
    ("S", "Simpan profil"),
    ("M", "Tangan / mouse"),
    ("R", "Main ulang"),
    ("Q", "Keluar"),
]


def shade(color, f: float):
    return tuple(int(min(255, max(0, v * f))) for v in color)


def blend_rect(img, x0, y0, x1, y1, color, alpha: float) -> None:
    H, W = img.shape[:2]
    x0, y0 = max(0, int(x0)), max(0, int(y0))
    x1, y1 = min(W, int(x1)), min(H, int(y1))
    if x1 <= x0 or y1 <= y0:
        return
    roi = img[y0:y1, x0:x1]
    overlay = np.empty_like(roi)
    overlay[:] = color
    img[y0:y1, x0:x1] = cv2.addWeighted(overlay, alpha, roi, 1 - alpha, 0)


def draw_retro_box(img, x0: int, y0: int, x1: int, y1: int,
                   fill=C_PANEL, border=C_EDGE, bevel: int = 2,
                   header_h: int = 0, header_fill=None, shadow: bool = True) -> None:
    """Kotak bergaya pixel-art retro dengan bayangan, bevel 3D, dan paku sudut."""
    x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
    if shadow:
        blend_rect(img, x0 + 4, y0 + 4, x1 + 4, y1 + 4, (12, 6, 5), 0.65)
    cv2.rectangle(img, (x0, y0), (x1, y1), fill, -1)
    if header_h > 0:
        hf = header_fill if header_fill is not None else shade(fill, 0.72)
        cv2.rectangle(img, (x0, y0), (x1, y0 + header_h), hf, -1)
        cv2.line(img, (x0, y0 + header_h), (x1, y0 + header_h), border, 2)

    # Bevel 3D dalam
    hi = shade(fill, 1.35)
    lo = shade(fill, 0.65)
    cv2.line(img, (x0 + 2, y0 + 2), (x1 - 2, y0 + 2), hi, 1)
    cv2.line(img, (x0 + 2, y0 + 2), (x0 + 2, y1 - 2), hi, 1)
    cv2.line(img, (x0 + 2, y1 - 2), (x1 - 2, y1 - 2), lo, 1)
    cv2.line(img, (x1 - 2, y0 + 2), (x1 - 2, y1 - 2), lo, 1)

    # Garis tepi luar & aksen sudut pixel
    cv2.rectangle(img, (x0, y0), (x1, y1), border, bevel)
    c_dot = shade(border, 1.35)
    for px, py in ((x0 + 4, y0 + 4), (x1 - 4, y0 + 4), (x0 + 4, y1 - 4), (x1 - 4, y1 - 4)):
        cv2.rectangle(img, (px - 1, py - 1), (px + 1, py + 1), c_dot, -1)


def _make_retro_bg(w: int, h: int) -> np.ndarray:
    """Buat kanvas latar retro (gradien + grid pixel + bintang + scanline CRT) sekali di awal."""
    bg = np.empty((h, w, 3), dtype=np.uint8)
    y_norm = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
    top = np.array([46, 22, 22], dtype=np.float32)
    bot = np.array([24, 10, 10], dtype=np.float32)
    grad = (top * (1.0 - y_norm) + bot * y_norm).astype(np.uint8)
    bg[:] = grad[:, None, :]

    # Grid pixel halus
    step = 40
    for x in range(0, w, step):
        bg[:, x] = np.minimum(255, bg[:, x].astype(np.uint16) + 10).astype(np.uint8)
    for y in range(0, h, step):
        bg[y, :] = np.minimum(255, bg[y, :].astype(np.uint16) + 10).astype(np.uint8)

    # Titik perpotongan grid & bintang pixel retro
    rng = np.random.RandomState(42)
    for _ in range(55):
        sx = int(rng.randint(12, w - 12))
        sy = int(rng.randint(76, h - 12))
        col = C_CYAN if rng.rand() < 0.35 else (C_ACCENT if rng.rand() < 0.5 else (140, 110, 100))
        size = 2 if rng.rand() < 0.3 else 1
        cv2.rectangle(bg, (sx, sy), (sx + size, sy + size), shade(col, 0.55), -1)

    # Efek scanline CRT tipis tiap 3 baris
    bg[::3, :] = (bg[::3, :].astype(np.uint16) * 88 // 100).astype(np.uint8)
    return bg


def _get_font(is_heading: bool, scale: float) -> tuple[ImageFont.FreeTypeFont | None, int]:
    path = config.FONT_HEADING_PATH if is_heading else config.FONT_BODY_PATH
    px = max(12, int(round(scale * (32 if is_heading else 40))))
    key = (path, px)
    if key not in _FONT_CACHE:
        try:
            _FONT_CACHE[key] = ImageFont.truetype(path, px)
        except OSError:
            return None, px
    return _FONT_CACHE[key], px


def _blit_mask(img: np.ndarray, mask: np.ndarray, x0: int, y0: int, color) -> None:
    H, W = img.shape[:2]
    mh, mw = mask.shape
    cx0, cy0 = max(0, x0), max(0, y0)
    cx1, cy1 = min(W, x0 + mw), min(H, y0 + mh)
    if cx1 <= cx0 or cy1 <= cy0:
        return
    sub_m = mask[cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0]
    roi = img[cy0:cy1, cx0:cx1]
    a = sub_m.astype(np.uint16)[..., None]
    c = np.array(color, dtype=np.uint16)
    roi[:] = ((roi.astype(np.uint16) * (255 - a) + c * a + 127) // 255).astype(np.uint8)


def draw_image_alpha(img: np.ndarray, bgra: np.ndarray, x: int, y: int) -> None:
    H, W = img.shape[:2]
    lh, lw = bgra.shape[:2]
    x0, y0 = max(0, int(x)), max(0, int(y))
    x1, y1 = min(W, int(x) + lw), min(H, int(y) + lh)
    if x1 <= x0 or y1 <= y0:
        return
    sub = bgra[y0 - int(y):y1 - int(y), x0 - int(x):x1 - int(x)]
    if sub.ndim < 3 or sub.shape[2] < 4:
        img[y0:y1, x0:x1] = sub[:, :, :3]
        return
    roi = img[y0:y1, x0:x1].astype(np.uint16)
    src = sub[:, :, :3].astype(np.uint16)
    alpha = sub[:, :, 3:4].astype(np.uint16)
    img[y0:y1, x0:x1] = ((src * alpha + roi * (255 - alpha) + 127) // 255).astype(np.uint8)


def _load_logo(target_h: int = 34) -> np.ndarray | None:
    try:
        with Image.open(config.LOGO_PATH) as im:
            rgba = im.convert("RGBA")
            bbox = rgba.getbbox()
            if bbox:
                rgba = rgba.crop(bbox)
            w, h = rgba.size
            if h > 0 and h != target_h:
                new_w = max(1, int(round(w * (target_h / h))))
                rgba = rgba.resize((new_w, target_h), Image.Resampling.LANCZOS)
            arr = np.array(rgba, dtype=np.uint8)
            return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGRA)
    except OSError:
        return None


def put_text(img, text, org, scale=0.7, color=C_TEXT, thick=2, align="left", shadow=True,
             font_role: str | None = None):
    """Gambar teks: thick >= 2 (atau font_role='heading') memakai PixelifySans, lainnya VT323."""
    if not text:
        return
    is_heading = (font_role == "heading") if font_role else (thick >= 2)
    font, px = _get_font(is_heading, scale)
    if font is None:
        (tw, _), _ = cv2.getTextSize(text, FONT, scale, thick)
        x, y = int(org[0]), int(org[1])
        if align == "center":
            x -= tw // 2
        elif align == "right":
            x -= tw
        if shadow:
            cv2.putText(img, text, (x + 2, y + 2), FONT, scale, (0, 0, 0), thick, AA)
        cv2.putText(img, text, (x, y), FONT, scale, color, thick, AA)
        return

    anchor = {"left": "ls", "center": "ms", "right": "rs"}.get(align, "ls")
    key = (text, is_heading, px, anchor)
    if key not in _MASK_CACHE:
        if len(_MASK_CACHE) > 512:
            _MASK_CACHE.clear()
        m, offset = font.getmask2(text, mode="L", anchor=anchor)
        arr = np.asarray(m, dtype=np.uint8).reshape(m.size[1], m.size[0])
        _MASK_CACHE[key] = (arr, offset)
    arr, (dx, dy) = _MASK_CACHE[key]
    x = int(org[0]) + dx
    y = int(org[1]) + dy
    if shadow:
        _blit_mask(img, arr, x + 2, y + 2, (10, 4, 4))
    _blit_mask(img, arr, x, y, color)


def wrap_text(text: str, width: int, scale: float, thick: int = 1,
              font_role: str | None = None) -> list[str]:
    is_heading = (font_role == "heading") if font_role else (thick >= 2)
    font, _ = _get_font(is_heading, scale)
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if font is not None:
            bbox = font.getbbox(trial)
            tw = (bbox[2] - bbox[0]) if bbox else 0
        else:
            tw = cv2.getTextSize(trial, FONT, scale, thick)[0][0]
        if tw <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def draw_cell(img, x, y, size, color, alpha: float = 1.0) -> None:
    """Gambar satu petak balok bergaya 3D pixel-art bevel dengan kilau sudut."""
    pad = max(2, size // 24)
    x0, y0, x1, y1 = int(x + pad), int(y + pad), int(x + size - pad), int(y + size - pad)
    if x1 <= x0 or y1 <= y0:
        return
    b = max(3, (x1 - x0) // 7)
    if alpha < 1.0:
        blend_rect(img, x0, y0, x1, y1, color, alpha)
        cv2.rectangle(img, (x0, y0), (x1, y1), shade(color, 1.25), 2)
        return

    # Dasar & bevel 3D (atas-kiri terang, bawah-kanan gelap)
    cv2.rectangle(img, (x0, y0), (x1, y1), color, -1)
    hi = shade(color, 1.38)
    lo = shade(color, 0.58)
    mid = shade(color, 0.92)
    cv2.rectangle(img, (x0, y0), (x1, y0 + b), hi, -1)
    cv2.rectangle(img, (x0, y0), (x0 + b, y1), hi, -1)
    cv2.rectangle(img, (x0, y1 - b), (x1, y1), lo, -1)
    cv2.rectangle(img, (x1 - b, y0), (x1, y1), lo, -1)
    cv2.rectangle(img, (x0 + b, y0 + b), (x1 - b, y1 - b), mid, -1)

    # Kilau pixel putih di pojok kiri-atas dalam
    sp = max(2, b // 2)
    sx, sy = x0 + b + 3, y0 + b + 3
    if sx + sp * 2 < x1 - b and sy + sp * 2 < y1 - b:
        shine = tuple(min(255, int(c * 0.4 + 255 * 0.6)) for c in color)
        cv2.rectangle(img, (sx, sy), (sx + sp * 2, sy + sp), shine, -1)
        cv2.rectangle(img, (sx, sy), (sx + sp, sy + sp * 2), shine, -1)

    # Garis luar gelap tegas ala pixel art
    cv2.rectangle(img, (x0, y0), (x1, y1), (20, 10, 10), max(1, size // 36))


def draw_empty(img, x, y, size) -> None:
    """Gambar petak papan kosong cekung (recessed arcade tile)."""
    pad = max(2, size // 24)
    x0, y0, x1, y1 = int(x + pad), int(y + pad), int(x + size - pad), int(y + size - pad)
    cv2.rectangle(img, (x0, y0), (x1, y1), C_EMPTY, -1)
    # Bayangan cekung di atas & kiri
    cv2.line(img, (x0, y0), (x1, y0), C_EMPTY_DARK, 2)
    cv2.line(img, (x0, y0), (x0, y1), C_EMPTY_DARK, 2)
    # Tepi terang tipis di bawah & kanan
    cv2.line(img, (x0, y1), (x1, y1), C_EMPTY_HI, 1)
    cv2.line(img, (x1, y0), (x1, y1), C_EMPTY_HI, 1)
    # Titik tengah halus
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    cv2.rectangle(img, (cx - 1, cy - 1), (cx + 1, cy + 1), shade(C_EMPTY, 1.18), -1)


def draw_piece(img, shape, color, center, cell: int, alpha: float = 1.0) -> None:
    h, w = shape.shape
    x0 = int(center[0] - w * cell / 2)
    y0 = int(center[1] - h * cell / 2)
    for r in range(h):
        for c in range(w):
            if shape[r, c]:
                draw_cell(img, x0 + c * cell, y0 + r * cell, cell, color, alpha)


# --- Koordinat & Tata Letak UI ---
class Layout:
    def __init__(self, w: int = config.CANVAS_W, h: int = config.CANVAS_H):
        n = config.BOARD_SIZE
        self.w, self.h = w, h
        self.header_h = 68
        self.cell = 92
        self.board_px = self.cell * n
        self.bx = (w - self.board_px) // 2
        self.by = 88

        self.slot_w, self.slot_h, gap = 210, 126, 30
        total = 3 * self.slot_w + 2 * gap
        sx = (w - total) // 2
        sy = self.by + self.board_px + 26
        self.slots = [(sx + i * (self.slot_w + gap), sy,
                       sx + i * (self.slot_w + gap) + self.slot_w, sy + self.slot_h)
                      for i in range(3)]
        self.slot_hit_pad = 14
        self.mini_cell = 24

        self.thumb = (w - 24 - 320, self.by - 12, w - 24)
        self.panel_x = 24
        self.panel_w = self.bx - 52
        self.button = (w // 2 - 155, h // 2 + 68, w // 2 + 155, h // 2 + 134)

    def slot_at(self, p):
        if p is None:
            return None
        x, y = p
        pad = self.slot_hit_pad
        for i, (x0, y0, x1, y1) in enumerate(self.slots):
            if x0 - pad <= x <= x1 + pad and y0 - pad <= y <= y1 + pad:
                return i
        return None

    def over_board(self, p) -> bool:
        m = config.BOARD_MARGIN * self.cell
        x, y = p
        return (self.bx - m <= x <= self.bx + self.board_px + m
                and self.by - m <= y <= self.by + self.board_px + m)

    def board_frac(self, p) -> tuple[float, float]:
        return (p[1] - self.by) / self.cell, (p[0] - self.bx) / self.cell

    def cell_xy(self, r: int, c: int) -> tuple[int, int]:
        return self.bx + c * self.cell, self.by + r * self.cell

    def in_button(self, p) -> bool:
        x0, y0, x1, y1 = self.button
        return p is not None and x0 <= p[0] <= x1 and y0 <= p[1] <= y1

    def map_from_camera(self, pt_norm) -> tuple[float, float]:
        x0, y0, x1, y1 = config.ACTIVE_ZONE
        u = min(max((pt_norm[0] - x0) / (x1 - x0), 0.0), 1.0)
        v = min(max((pt_norm[1] - y0) / (y1 - y0), 0.0), 1.0)
        return u * (self.w - 1), v * (self.h - 1)


class Effects:
    FLASH = 0.45
    POPUP = 1.0

    def __init__(self):
        self.flashes: list = []
        self.popups: list = []

    def clear(self) -> None:
        self.flashes.clear()
        self.popups.clear()

    def add_clear(self, cells, now: float) -> None:
        if cells:
            self.flashes.append((now, list(cells)))

    def add_popup(self, text: str, pos, now: float, color=C_ACCENT, scale: float = 1.0) -> None:
        self.popups.append((now, text, (int(pos[0]), int(pos[1])), color, scale))

    def draw(self, img, layout: Layout, now: float) -> None:
        self.flashes = [f for f in self.flashes if now - f[0] < self.FLASH]
        for t, cells in self.flashes:
            p = (now - t) / self.FLASH
            a = 0.88 * (1.0 - p)
            for r, c in cells:
                x, y = layout.cell_xy(r, c)
                blend_rect(img, x, y, x + layout.cell, y + layout.cell, C_CYAN, a * 0.6)
                pad = int(p * 14)
                blend_rect(img, x + pad, y + pad, x + layout.cell - pad, y + layout.cell - pad,
                           (255, 255, 255), a)
        self.popups = [p for p in self.popups if now - p[0] < self.POPUP]
        for t, text, (x, y), color, scale in self.popups:
            k = (now - t) / self.POPUP
            put_text(img, text, (x, y - int(60 * k)), scale, color, 2 if scale < 1.2 else 3, "center")


class Renderer:
    def __init__(self, layout: Layout):
        self.L = layout
        self.fx = Effects()
        self.logo = _load_logo(target_h=34)
        self.bg_base = _make_retro_bg(layout.w, layout.h)

    def render_game(self, game, inter, cursor, result, info: dict, now: float):
        L = self.L
        img = self.bg_base.copy()
        self._draw_header(img, game)
        self._draw_board(img, game, inter)
        self.fx.draw(img, L, now)
        self._draw_slots(img, game, inter)
        bottom = self._draw_camera(img, result, info)
        self._draw_keys(img, bottom + 14)
        self._draw_panel(img, game, inter, info, now)

        if inter.state == "hold" and inter.ghost is None and cursor is not None:
            piece = game.slots[inter.held]
            if piece is not None:
                draw_piece(img, piece.shape, PALETTE[piece.color], cursor,
                           int(L.cell * 0.8), alpha=0.65)
        if game.game_over:
            self._draw_game_over(img, game, inter)
        self._draw_cursor(img, cursor, inter, info)
        return img

    def _draw_header(self, img, game) -> None:
        L = self.L
        cv2.rectangle(img, (0, 0), (L.w, L.header_h), C_PANEL_DARK, -1)
        cv2.rectangle(img, (0, 0), (L.w, 3), C_ACCENT, -1)
        cv2.line(img, (0, L.header_h - 3), (L.w, L.header_h - 3), C_BOARD_EDGE, 2)
        cv2.line(img, (0, L.header_h - 1), (L.w, L.header_h - 1), (15, 8, 8), 1)

        if self.logo is not None:
            ly = (L.header_h - self.logo.shape[0]) // 2
            draw_image_alpha(img, self.logo, L.panel_x, ly)
        else:
            put_text(img, "BLAST BLOCK", (L.panel_x, 44), 0.85, C_ACCENT, 2)

        # Kotak skor tengah bergaya layar digital arcade
        sc_w = 250
        sc_x0, sc_x1 = L.w // 2 - sc_w // 2, L.w // 2 + sc_w // 2
        draw_retro_box(img, sc_x0, 9, sc_x1, L.header_h - 10, fill=C_PANEL, border=C_ACCENT,
                       bevel=2, shadow=False)
        put_text(img, "SKOR", (sc_x0 + 18, 43), 0.72, C_ACCENT, 2, "left")
        put_text(img, f"{game.score:04d}", (sc_x1 - 18, 46), 1.05, C_TEXT, 1, "right")

        # Kotak rekor terbaik di kanan
        best = max(game.high_score, game.score)
        hi_w = 235
        hi_x1 = L.w - L.panel_x
        hi_x0 = hi_x1 - hi_w
        draw_retro_box(img, hi_x0, 12, hi_x1, L.header_h - 12, fill=C_PANEL, border=C_EDGE,
                       bevel=2, shadow=False)
        put_text(img, "TERBAIK", (hi_x0 + 14, 42), 0.62, C_CYAN, 2, "left")
        put_text(img, f"{best:04d}", (hi_x1 - 14, 44), 0.90, C_TEXT, 1, "right")

    def _draw_board(self, img, game, inter) -> None:
        L = self.L
        n = config.BOARD_SIZE
        pad = 12
        draw_retro_box(img, L.bx - pad, L.by - pad,
                       L.bx + L.board_px + pad, L.by + L.board_px + pad,
                       fill=C_BOARD, border=C_BOARD_EDGE, bevel=3, shadow=True)
        # Garis dalam sekitar grid
        cv2.rectangle(img, (L.bx - 3, L.by - 3),
                      (L.bx + L.board_px + 3, L.by + L.board_px + 3), C_PANEL_DARK, 2)

        grid = game.board.grid
        for r in range(n):
            for c in range(n):
                x, y = L.cell_xy(r, c)
                v = int(grid[r, c])
                if v:
                    draw_cell(img, x, y, L.cell, PALETTE.get(v, C_GREY))
                else:
                    draw_empty(img, x, y, L.cell)

        if inter.state == "hold" and inter.ghost is not None:
            (r0, c0), valid = inter.ghost
            piece = game.slots[inter.held]
            if piece is None:
                return
            color = PALETTE[piece.color] if valid else C_INVALID
            for r, c in piece.coords:
                rr, cc = r0 + r, c0 + c
                if 0 <= rr < n and 0 <= cc < n:
                    x, y = L.cell_xy(rr, cc)
                    draw_cell(img, x, y, L.cell, color, alpha=0.6)
            if valid:
                rows, cols = inter.clear_preview
                for r in rows:
                    blend_rect(img, L.bx, L.by + r * L.cell, L.bx + L.board_px,
                               L.by + (r + 1) * L.cell, C_CYAN, 0.28)
                    cv2.rectangle(img, (L.bx, L.by + r * L.cell),
                                  (L.bx + L.board_px, L.by + (r + 1) * L.cell), C_CYAN, 2)
                for c in cols:
                    blend_rect(img, L.bx + c * L.cell, L.by, L.bx + (c + 1) * L.cell,
                               L.by + L.board_px, C_CYAN, 0.28)
                    cv2.rectangle(img, (L.bx + c * L.cell, L.by),
                                  (L.bx + (c + 1) * L.cell, L.by + L.board_px), C_CYAN, 2)

    def _draw_slots(self, img, game, inter) -> None:
        L = self.L
        for i, (x0, y0, x1, y1) in enumerate(L.slots):
            hovered = inter.state == "idle" and inter.hover_slot == i
            held_here = inter.state == "hold" and inter.held == i
            border_c = C_ACCENT if hovered else (C_CYAN if held_here else C_EDGE)
            fill_c = shade(C_PANEL, 1.15) if hovered else C_PANEL
            draw_retro_box(img, x0, y0, x1, y1, fill=fill_c, border=border_c,
                           bevel=3 if hovered else 2, shadow=True)

            # Label nomor slot kecil di pojok kiri atas
            put_text(img, f"#{i + 1}", (x0 + 10, y0 + 20), 0.42, C_MUTED, 1, shadow=False)

            center = ((x0 + x1) // 2, (y0 + y1) // 2 - 2)
            piece = game.slots[i]
            if piece is None:
                put_text(img, "KOSONG", (center[0], center[1] + 7), 0.55, C_EDGE, 1, "center", False)
                continue
            if held_here:
                draw_piece(img, piece.shape, PALETTE[piece.color], center, L.mini_cell, alpha=0.28)
                put_text(img, "DIPEGANG", (center[0], y1 - 10), 0.5, C_CYAN, 1, "center")
                continue
            fits = game.slot_fits(i)
            draw_piece(img, piece.shape, PALETTE[piece.color] if fits else C_GREY,
                       center, L.mini_cell)
            if not fits:
                put_text(img, "TIDAK MUAT", (center[0], y1 - 10), 0.5, C_INVALID, 1, "center")

    def _draw_camera(self, img, result, info) -> int:
        x0, y0, x1 = self.L.thumb
        tw = x1 - x0
        hdr = 30
        if result is None:
            th = 165
            box_h = hdr + th + 26
            draw_retro_box(img, x0, y0, x1, y0 + box_h, fill=C_PANEL_DARK, border=C_EDGE,
                           bevel=2, header_h=hdr, header_fill=C_PANEL)
            put_text(img, "MONITOR KAMERA", (x0 + 12, y0 + 21), 0.52, C_CYAN, 2)
            cv2.circle(img, (x1 - 16, y0 + 15), 5, C_WARN, -1, AA)
            msg = "MODE MOUSE AKTIF" if info.get("input_mode") == "mouse" else "KAMERA TIDAK AKTIF"
            put_text(img, msg, ((x0 + x1) // 2, y0 + hdr + th // 2 + 6), 0.6, C_MUTED, 1, "center")
            put_text(img, "Tekan [M] untuk ganti mode input", (x0 + 10, y0 + box_h - 8), 0.44, C_MUTED, 1)
            return y0 + box_h

        small = result.frame_small
        sh, sw = small.shape[:2]
        inner_w = tw - 12
        th = int(inner_w * sh / sw)
        box_h = hdr + th + 32
        draw_retro_box(img, x0, y0, x1, y0 + box_h, fill=C_PANEL_DARK, border=C_EDGE,
                       bevel=2, header_h=hdr, header_fill=C_PANEL)
        put_text(img, "SENSOR TANGAN", (x0 + 12, y0 + 21), 0.52, C_CYAN, 2)
        led_col = C_VALID if result.found else C_WARN
        cv2.circle(img, (x1 - 16, y0 + 15), 5, led_col, -1, AA)

        view = cv2.resize(small, (inner_w, th), interpolation=cv2.INTER_AREA)
        m = cv2.resize(result.mask, (inner_w, th), interpolation=cv2.INTER_NEAREST) > 0
        view[m] = (view[m] * 0.45 + np.array(C_VALID) * 0.55).astype(np.uint8)
        zx0, zy0, zx1, zy1 = config.ACTIVE_ZONE
        cv2.rectangle(view, (int(zx0 * inner_w), int(zy0 * th)),
                      (int(zx1 * inner_w), int(zy1 * th)), C_ACCENT, 1)
        if result.found:
            cv2.circle(view, (int(result.point[0] * inner_w), int(result.point[1] * th)), 5,
                       (0, 0, 255), -1, AA)
        vx0, vy0 = x0 + 6, y0 + hdr + 6
        img[vy0:vy0 + th, vx0:vx0 + inner_w] = view
        cv2.rectangle(img, (vx0, vy0), (vx0 + inner_w, vy0 + th), C_EDGE, 1)
        put_text(img, "Hijau = terdeteksi | Kotak = zona gerak", (x0 + 10, y0 + box_h - 8),
                 0.44, C_MUTED, 1)
        return y0 + box_h

    def _draw_keys(self, img, y: int) -> None:
        x0, _, x1 = self.L.thumb
        hdr = 30
        row_h = 26
        box_h = hdr + len(KEY_HELP) * row_h + 14
        draw_retro_box(img, x0, y, x1, y + box_h, fill=C_PANEL, border=C_EDGE,
                       bevel=2, header_h=hdr, header_fill=C_PANEL_DARK)
        put_text(img, "KONTROL ARCADE", (x0 + 12, y + 21), 0.54, C_ACCENT, 2)

        ky = y + hdr + 21
        for k_char, desc in KEY_HELP:
            # Tombol keycap pixel
            kx0, ky0 = x0 + 12, ky - 15
            kx1, ky1 = kx0 + 26, ky + 4
            cv2.rectangle(img, (kx0, ky0), (kx1, ky1), C_PANEL_DARK, -1)
            cv2.rectangle(img, (kx0, ky0), (kx1, ky1), C_ACCENT, 1)
            put_text(img, k_char, ((kx0 + kx1) // 2, ky - 1), 0.46, C_ACCENT, 2, "center", False)
            put_text(img, desc, (kx1 + 10, ky), 0.50, C_TEXT, 1)
            ky += row_h

    def _draw_panel(self, img, game, inter, info, now) -> None:
        L = self.L
        x0 = L.panel_x
        x1 = x0 + L.panel_w
        y0 = L.by - 12

        # --- Kartu 1: STATUS ---
        has_combo = game.combo > 1
        st_h = 192 if has_combo else 148
        draw_retro_box(img, x0, y0, x1, y0 + st_h, fill=C_PANEL, border=C_EDGE,
                       bevel=2, header_h=30, header_fill=C_PANEL_DARK)
        put_text(img, "STATUS PERMAINAN", (x0 + 12, y0 + 21), 0.54, C_ACCENT, 2)

        if info.get("input_mode") == "mouse":
            mode = "Mouse"
        else:
            mode = info.get("track_label", "Tangan")
            if not info.get("calibrated"):
                mode += " *"
        lvl_idx = min(game.level(), len(config.LEVEL_NAMES) - 1)
        level = config.LEVEL_NAMES[lvl_idx]
        lvl_colors = [C_VALID, C_ACCENT, C_INVALID]
        lvl_col = lvl_colors[min(lvl_idx, 2)]

        sy = y0 + 54
        put_text(img, "Input :", (x0 + 14, sy), 0.52, C_MUTED, 1)
        put_text(img, mode, (x0 + 82, sy), 0.52, C_TEXT, 1)
        sy += 28
        put_text(img, "Level :", (x0 + 14, sy), 0.52, C_MUTED, 1)
        # Badge level retro
        cv2.rectangle(img, (x0 + 80, sy - 15), (x0 + 158, sy + 5), C_PANEL_DARK, -1)
        cv2.rectangle(img, (x0 + 80, sy - 15), (x0 + 158, sy + 5), lvl_col, 1)
        put_text(img, level.upper(), (x0 + 119, sy - 1), 0.46, lvl_col, 2, "center", False)
        sy += 28
        put_text(img, "FPS   :", (x0 + 14, sy), 0.52, C_MUTED, 1)
        put_text(img, f"{info.get('fps', 0):.0f}", (x0 + 82, sy), 0.52, C_CYAN, 1)

        if has_combo:
            sy += 14
            cv2.rectangle(img, (x0 + 12, sy), (x1 - 12, sy + 32), C_PANEL_DARK, -1)
            cv2.rectangle(img, (x0 + 12, sy), (x1 - 12, sy + 32), C_ACCENT, 2)
            put_text(img, f"KOMBO AKTIF x{game.combo}!", ((x0 + x1) // 2, sy + 23),
                     0.68, C_ACCENT, 2, "center")

        # --- Kartu 2: PETUNJUK & NOTIFIKASI ---
        py0 = y0 + st_h + 16
        inner_w = L.panel_w - 28
        hint_lines = wrap_text(inter.hint(), inner_w, 0.52)
        notes = []
        if inter.message and now < inter.message_until:
            notes.append(inter.message)
        if info.get("warning"):
            notes.append(info["warning"])
        note_lines = [line for note in notes for line in wrap_text(note, inner_w, 0.50)]

        pt_h = max(165, 48 + len(hint_lines) * 24 + (len(note_lines) * 23 + 18 if note_lines else 0))
        draw_retro_box(img, x0, py0, x1, py0 + pt_h, fill=C_PANEL, border=C_EDGE,
                       bevel=2, header_h=30, header_fill=C_PANEL_DARK)
        put_text(img, "PETUNJUK", (x0 + 12, py0 + 21), 0.54, C_CYAN, 2)

        ty = py0 + 54
        for line in hint_lines:
            put_text(img, line, (x0 + 14, ty), 0.52, C_TEXT, 1)
            ty += 24
        if note_lines:
            ty += 4
            cv2.line(img, (x0 + 14, ty - 12), (x1 - 14, ty - 12), C_EDGE, 1)
            for line in note_lines:
                put_text(img, line, (x0 + 14, ty), 0.50, C_WARN, 1)
                ty += 23

        if info.get("input_mode") == "hand" and not info.get("calibrated"):
            put_text(img, "* Belum kalibrasi (tekan C)", (x0 + 4, L.h - 20), 0.48, C_WARN, 1)

    def _draw_game_over(self, img, game, inter) -> None:
        L = self.L
        blend_rect(img, 0, 0, L.w, L.h, (10, 4, 4), 0.72)
        cx, cy = L.w // 2, L.h // 2
        mw, mh = 460, 340
        mx0, my0, mx1, my1 = cx - mw // 2, cy - 175, cx + mw // 2, cy + 165
        draw_retro_box(img, mx0, my0, mx1, my1, fill=C_PANEL, border=C_ACCENT,
                       bevel=3, header_h=56, header_fill=C_PANEL_DARK, shadow=True)

        put_text(img, "GAME OVER", (cx, my0 + 40), 1.35, C_INVALID, 3, "center")
        put_text(img, f"SKOR AKHIR :  {game.score}", (cx, cy - 52), 0.85, C_TEXT, 1, "center")
        if game.new_record:
            cv2.rectangle(img, (cx - 110, cy - 22), (cx + 110, cy + 12), C_PANEL_DARK, -1)
            cv2.rectangle(img, (cx - 110, cy - 22), (cx + 110, cy + 12), C_ACCENT, 2)
            put_text(img, "REKOR BARU!", (cx, cy + 2), 0.75, C_ACCENT, 2, "center")
        else:
            put_text(img, f"TERBAIK :  {game.high_score}", (cx, cy), 0.72, C_MUTED, 1, "center")

        x0, y0, x1, y1 = L.button
        hovered = inter.progress_kind == "button"
        btn_fill = C_ACCENT if hovered else C_PANEL_DARK
        draw_retro_box(img, x0, y0, x1, y1, fill=btn_fill, border=C_CYAN if hovered else C_ACCENT,
                       bevel=3, shadow=False)
        put_text(img, "MAIN LAGI", (cx, (y0 + y1) // 2 + 10), 0.92,
                 C_PANEL_DARK if hovered else C_ACCENT, 2, "center", shadow=not hovered)
        put_text(img, "Tahan tangan di tombol, atau tekan [R]", (cx, my1 - 12), 0.50, C_MUTED, 1, "center")

    def _draw_cursor(self, img, cursor, inter, info) -> None:
        if cursor is None:
            last = info.get("last_cursor")
            if last is not None and info.get("input_mode") == "hand":
                p = (int(last[0]), int(last[1]))
                cv2.circle(img, p, 15, C_WARN, 2, AA)
                put_text(img, "?", (p[0], p[1] + 7), 0.6, C_WARN, 2, "center", shadow=False)
                put_text(img, "Tangan tidak terdeteksi", (p[0], p[1] + 40), 0.5, C_WARN, 1, "center")
            return
        px, py = int(cursor[0]), int(cursor[1])
        p = (px, py)
        if inter.progress_kind and inter.progress > 0:
            color = RING_COLORS.get(inter.progress_kind, C_ACCENT)
            cv2.circle(img, p, 28, (30, 15, 15), 5, AA)
            cv2.ellipse(img, p, (28, 28), -90, 0, 360 * inter.progress, color, 6, AA)

        # Target reticle bergaya arcade
        cv2.circle(img, p, 12, (20, 10, 10), 4, AA)
        cv2.circle(img, p, 12, C_CYAN, 2, AA)
        for dx, dy in ((-16, 0), (16, 0), (0, -16), (0, 16)):
            cv2.line(img, (px + dx // 2, py + dy // 2), (px + dx, py + dy), C_TEXT, 2)
        cv2.circle(img, p, 3, C_ACCENT, -1, AA)

    def render_calibration(self, frame, calib, tracker, result, info: dict):
        L = self.L
        if frame is None:
            img = self.bg_base.copy()
            cx, cy = L.w // 2, L.h // 2
            draw_retro_box(img, cx - 280, cy - 85, cx + 280, cy + 75,
                           fill=C_PANEL, border=C_WARN, bevel=3, header_h=42, header_fill=C_PANEL_DARK)
            put_text(img, "KAMERA TIDAK TERBACA", (cx, cy - 56), 0.85, C_WARN, 2, "center")
            put_text(img, "Tekan [M] untuk main dengan mouse, atau [Q] untuk keluar.",
                     (cx, cy + 20), 0.62, C_TEXT, 1, "center")
            return img
        img = cv2.resize(frame, (L.w, L.h), interpolation=cv2.INTER_LINEAR)

        if calib.phase == "preview" and result is not None:
            m = cv2.resize(result.mask, (L.w, L.h), interpolation=cv2.INTER_NEAREST) > 0
            img[m] = (img[m] * 0.45 + np.array(C_VALID) * 0.55).astype(np.uint8)
            if result.found:
                cv2.circle(img, (int(result.point[0] * L.w), int(result.point[1] * L.h)),
                           12, (0, 0, 255), -1, AA)
        else:
            x0, y0, x1, y1 = tracker.roi_rect_norm(frame.shape)
            p0, p1 = (int(x0 * L.w), int(y0 * L.h)), (int(x1 * L.w), int(y1 * L.h))
            cv2.rectangle(img, p0, p1, (20, 10, 10), 5)
            cv2.rectangle(img, p0, p1, C_ACCENT, 2)
            # Siku viewfinder sudut retro
            cl = 22
            for cx_c, cy_c, sx, sy in ((p0[0], p0[1], 1, 1), (p1[0], p0[1], -1, 1),
                                       (p0[0], p1[1], 1, -1), (p1[0], p1[1], -1, -1)):
                cv2.line(img, (cx_c, cy_c), (cx_c + sx * cl, cy_c), C_CYAN, 4)
                cv2.line(img, (cx_c, cy_c), (cx_c, cy_c + sy * cl), C_CYAN, 4)

            cx_box = p0[0] + (p1[0] - p0[0]) // 2
            draw_retro_box(img, cx_box - 125, p1[1] + 10, cx_box + 125, p1[1] + 82,
                           fill=C_PANEL_DARK, border=C_EDGE, bevel=2)
            put_text(img, "TARUH WARNA DI SINI", (cx_box, p1[1] + 34),
                     0.55, C_ACCENT, 2, "center")
            if tracker.mode == "glove":
                sw_x0, sw_y0 = cx_box - 92, p1[1] + 46
                sw_x1, sw_y1 = sw_x0 + 30, sw_y0 + 24
                cv2.rectangle(img, (sw_x0, sw_y0), (sw_x1, sw_y1), tracker.dominant_bgr, -1)
                cv2.rectangle(img, (sw_x0, sw_y0), (sw_x1, sw_y1), C_TEXT, 2)
                put_text(img, "Warna Dominan", (sw_x1 + 10, sw_y0 + 18), 0.52, C_TEXT, 2)

        draw_retro_box(img, 16, 12, L.w - 16, 168, fill=C_PANEL_DARK, border=C_ACCENT,
                       bevel=2, header_h=44, header_fill=C_PANEL, shadow=True)
        put_text(img, f"KALIBRASI SENSOR  -  {tracker.label}", (34, 42), 0.82, C_ACCENT, 2)
        thing = "objek/sarung tangan berwarna" if tracker.mode == "glove" else "telapak tangan"
        if calib.phase == "wait":
            extra = "   |   [L] Pakai profil tersimpan" if info.get("profile_exists") else ""
            lines = [f"1. Masukkan {thing} ke kotak target sampai penuh.",
                     f"2. Tekan [SPASI] (tahan 1 dtk) atau [ENTER] untuk kunci warna.   [{tracker.range_text()}]",
                     f"[ENTER] Kunci warna saat ini{extra}   |   [M] Mode mouse   |   [Q] Keluar"]
        elif calib.phase == "sampling":
            lines = ["Menganalisis warna dominan & membuat threshold... tahan diam."]
            bx0, by0 = 34, 112
            cv2.rectangle(img, (bx0, by0), (bx0 + 520, by0 + 22), C_PANEL, -1)
            cv2.rectangle(img, (bx0, by0), (bx0 + int(520 * calib.progress), by0 + 22), C_ACCENT, -1)
            cv2.rectangle(img, (bx0, by0), (bx0 + 520, by0 + 22), C_CYAN, 2)
        else:
            lines = ["Area HIJAU = yang terdeteksi. Pastikan hanya tangan/objek yang berwarna hijau.",
                     "[ENTER] Mulai main   |   [SPASI] Kalibrasi ulang   |   [D] Atur manual (debug)",
                     f"Threshold aktif:  {tracker.range_text()}"]
        for i, text in enumerate(lines):
            put_text(img, text, (34, 84 + i * 26), 0.58, C_TEXT, 1)

        notes = [n for n in (info.get("cam_note"), tracker.warning) if n]
        if notes:
            bh = 34 * len(notes) + 14
            draw_retro_box(img, 16, L.h - bh - 10, L.w - 16, L.h - 10,
                           fill=C_PANEL_DARK, border=C_WARN, bevel=2, shadow=False)
            for i, n in enumerate(notes):
                put_text(img, n, (32, L.h - bh - 10 + 26 + i * 32), 0.55, C_WARN, 1)
        return img


class DebugWindow:
    NAME = "Debug Mask"

    def __init__(self):
        self.is_open = False
        self._spec: list = []
        self._last = None

    @staticmethod
    def _make_spec(mode: str) -> list:
        if mode == "glove":
            return [("H min", 0, "lo", 179), ("H max", 0, "hi", 179),
                    ("S min", 1, "lo", 255), ("S max", 1, "hi", 255),
                    ("V min", 2, "lo", 255), ("V max", 2, "hi", 255)]
        return [("Cr min", 1, "lo", 255), ("Cr max", 1, "hi", 255),
                ("Cb min", 2, "lo", 255), ("Cb max", 2, "hi", 255)]

    def toggle(self, tracker) -> None:
        if self.is_open:
            self.close()
        else:
            self.open(tracker)

    def open(self, tracker) -> None:
        cv2.namedWindow(self.NAME, cv2.WINDOW_AUTOSIZE)
        self._spec = self._make_spec(tracker.mode)
        for name, _, _, maxv in self._spec:
            cv2.createTrackbar(name, self.NAME, 0, maxv, lambda _v: None)
        self.is_open = True
        self.sync(tracker)

    def close(self) -> None:
        try:
            cv2.destroyWindow(self.NAME)
        except cv2.error:
            pass
        self.is_open = False

    def _read(self):
        return tuple(cv2.getTrackbarPos(name, self.NAME) for name, *_ in self._spec)

    def sync(self, tracker) -> None:
        if not self.is_open:
            return
        for name, ch, which, _ in self._spec:
            val = tracker.lo[ch] if which == "lo" else tracker.hi[ch]
            cv2.setTrackbarPos(name, self.NAME, int(val))
        self._last = self._read()

    def apply(self, tracker) -> None:
        if not self.is_open:
            return
        try:
            if cv2.getWindowProperty(self.NAME, cv2.WND_PROP_VISIBLE) < 1:
                self.is_open = False
                return
            vals = self._read()
        except cv2.error:
            self.is_open = False
            return
        if vals != self._last:
            lo, hi = tracker.lo.copy(), tracker.hi.copy()
            for (_, ch, which, _), v in zip(self._spec, vals):
                (lo if which == "lo" else hi)[ch] = v
            tracker.set_range(lo, hi)
            self._last = vals

    def show(self, result) -> None:
        if not self.is_open or result is None:
            return
        vis = cv2.cvtColor(result.mask, cv2.COLOR_GRAY2BGR)
        if result.contour is not None:
            cv2.drawContours(vis, [result.contour], -1, (0, 255, 0), 2)
        if result.found:
            h, w = vis.shape[:2]
            cv2.circle(vis, (int(result.point[0] * w), int(result.point[1] * h)), 8, (0, 0, 255), -1)
        put_text(vis, f"area {result.area_frac * 100:.1f}%  min {config.MIN_AREA_FRAC * 100:.1f}%",
                 (10, 25), 0.6, (0, 255, 255), 1)
        both = np.hstack([result.frame_small, vis])
        scale = 960 / both.shape[1]
        cv2.imshow(self.NAME, cv2.resize(both, None, fx=scale, fy=scale))
