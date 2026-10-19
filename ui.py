"""Rendering antarmuka dengan primitif OpenCV (belum memakai aset gambar).

Semua elemen digambar dari kotak, lingkaran, dan teks. Nanti saat aset sudah
siap, cukup ganti fungsi draw_* / method _draw_* di sini; logika game dan
state machine tidak perlu disentuh.
"""
from __future__ import annotations

import cv2
import numpy as np

import config

FONT = cv2.FONT_HERSHEY_SIMPLEX
AA = cv2.LINE_AA

# Warna (BGR)
C_BG = (38, 26, 20)
C_PANEL = (60, 44, 35)
C_EDGE = (95, 75, 62)
C_BOARD = (70, 50, 40)
C_EMPTY = (92, 70, 56)
C_EMPTY_EDGE = (112, 88, 72)
C_TEXT = (240, 235, 230)
C_MUTED = (165, 155, 145)
C_ACCENT = (40, 200, 255)     # kuning-oranye
C_VALID = (120, 220, 120)
C_INVALID = (80, 80, 235)
C_CANCEL = (60, 150, 255)
C_WARN = (90, 180, 255)
C_GREY = (120, 115, 110)

PALETTE = {
    1: (80, 80, 235),    # merah
    2: (60, 150, 250),   # oranye
    3: (60, 205, 240),   # kuning
    4: (110, 200, 80),   # hijau
    5: (215, 195, 60),   # tosca
    6: (235, 140, 60),   # biru
    7: (205, 90, 160),   # ungu
    8: (170, 100, 240),  # pink
}
RING_COLORS = {"pick": C_ACCENT, "place": C_VALID, "cancel": C_CANCEL, "button": C_ACCENT}

KEY_HELP = [
    "[C] Kalibrasi ulang",
    "[D] Jendela debug mask",
    "[S] Simpan profil warna",
    "[M] Ganti tangan / mouse",
    "[R] Main ulang",
    "[Q] Keluar",
]


# --------------------------------------------------------------------------
# Primitif gambar
# --------------------------------------------------------------------------
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


def put_text(img, text, org, scale=0.7, color=C_TEXT, thick=2, align="left", shadow=True):
    (tw, _), _ = cv2.getTextSize(text, FONT, scale, thick)
    x, y = int(org[0]), int(org[1])
    if align == "center":
        x -= tw // 2
    elif align == "right":
        x -= tw
    if shadow:
        cv2.putText(img, text, (x + 2, y + 2), FONT, scale, (0, 0, 0), thick, AA)
    cv2.putText(img, text, (x, y), FONT, scale, color, thick, AA)


def wrap_text(text: str, width: int, scale: float, thick: int = 1) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if cv2.getTextSize(trial, FONT, scale, thick)[0][0] <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def draw_cell(img, x, y, size, color, alpha: float = 1.0) -> None:
    pad = max(2, size // 22)
    x0, y0, x1, y1 = int(x + pad), int(y + pad), int(x + size - pad), int(y + size - pad)
    if alpha >= 1.0:
        cv2.rectangle(img, (x0, y0), (x1, y1), color, -1)
        band = max(2, (y1 - y0) // 7)
        cv2.rectangle(img, (x0, y0), (x1, y0 + band), shade(color, 1.3), -1)
        cv2.rectangle(img, (x0, y1 - band), (x1, y1), shade(color, 0.7), -1)
    else:
        blend_rect(img, x0, y0, x1, y1, color, alpha)
    cv2.rectangle(img, (x0, y0), (x1, y1), shade(color, 0.55), max(1, size // 40))


def draw_empty(img, x, y, size) -> None:
    pad = max(2, size // 22)
    cv2.rectangle(img, (x + pad, y + pad), (x + size - pad, y + size - pad), C_EMPTY, -1)
    cv2.rectangle(img, (x + pad, y + pad), (x + size - pad, y + size - pad), C_EMPTY_EDGE, 1)


def draw_piece(img, shape, color, center, cell: int, alpha: float = 1.0) -> None:
    h, w = shape.shape
    x0 = int(center[0] - w * cell / 2)
    y0 = int(center[1] - h * cell / 2)
    for r in range(h):
        for c in range(w):
            if shape[r, c]:
                draw_cell(img, x0 + c * cell, y0 + r * cell, cell, color, alpha)


# --------------------------------------------------------------------------
# Tata letak
# --------------------------------------------------------------------------
class Layout:
    """Semua koordinat piksel elemen UI di kanvas (default 1280x720)."""

    def __init__(self, w: int = config.CANVAS_W, h: int = config.CANVAS_H):
        n = config.BOARD_SIZE
        self.w, self.h = w, h
        self.header_h = 66
        self.cell = 92
        self.board_px = self.cell * n
        self.bx = (w - self.board_px) // 2
        self.by = 88

        self.slot_w, self.slot_h, gap = 210, 128, 30
        total = 3 * self.slot_w + 2 * gap
        sx = (w - total) // 2
        sy = self.by + self.board_px + 24
        self.slots = [(sx + i * (self.slot_w + gap), sy,
                       sx + i * (self.slot_w + gap) + self.slot_w, sy + self.slot_h)
                      for i in range(3)]
        self.slot_hit_pad = 14
        self.mini_cell = 24

        self.thumb = (w - 20 - 300, self.by, w - 20)        # x0, y0, x1 (tinggi ikut aspek)
        self.panel_x = 24
        self.panel_w = self.bx - 60
        self.button = (w // 2 - 150, h // 2 + 70, w // 2 + 150, h // 2 + 135)

    # --- uji posisi kursor
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
        """Posisi kursor dalam satuan sel (baris, kolom), boleh pecahan."""
        return (p[1] - self.by) / self.cell, (p[0] - self.bx) / self.cell

    def cell_xy(self, r: int, c: int) -> tuple[int, int]:
        return self.bx + c * self.cell, self.by + r * self.cell

    def in_button(self, p) -> bool:
        x0, y0, x1, y1 = self.button
        return p is not None and x0 <= p[0] <= x1 and y0 <= p[1] <= y1

    def map_from_camera(self, pt_norm) -> tuple[float, float]:
        """Petakan titik kamera (0..1) dari ACTIVE_ZONE ke seluruh kanvas."""
        x0, y0, x1, y1 = config.ACTIVE_ZONE
        u = min(max((pt_norm[0] - x0) / (x1 - x0), 0.0), 1.0)
        v = min(max((pt_norm[1] - y0) / (y1 - y0), 0.0), 1.0)
        return u * (self.w - 1), v * (self.h - 1)


# --------------------------------------------------------------------------
# Efek
# --------------------------------------------------------------------------
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
            a = 0.85 * (1 - (now - t) / self.FLASH)
            for r, c in cells:
                x, y = layout.cell_xy(r, c)
                blend_rect(img, x, y, x + layout.cell, y + layout.cell, (255, 255, 255), a)
        self.popups = [p for p in self.popups if now - p[0] < self.POPUP]
        for t, text, (x, y), color, scale in self.popups:
            k = (now - t) / self.POPUP
            put_text(img, text, (x, y - int(60 * k)), scale, color, 2 if scale < 1.2 else 3, "center")


# --------------------------------------------------------------------------
# Renderer utama
# --------------------------------------------------------------------------
class Renderer:
    def __init__(self, layout: Layout):
        self.L = layout
        self.fx = Effects()

    # ================================================================ game
    def render_game(self, game, inter, cursor, result, info: dict, now: float):
        L = self.L
        img = np.full((L.h, L.w, 3), C_BG, np.uint8)
        self._draw_header(img, game)
        self._draw_board(img, game, inter)
        self.fx.draw(img, L, now)
        self._draw_slots(img, game, inter)
        bottom = self._draw_camera(img, result, info)
        self._draw_keys(img, bottom + 30)
        self._draw_panel(img, game, inter, info, now)

        if inter.state == "hold" and inter.ghost is None and cursor is not None:
            piece = game.slots[inter.held]
            if piece is not None:
                draw_piece(img, piece.shape, PALETTE[piece.color], cursor,
                           int(L.cell * 0.8), alpha=0.6)
        if game.game_over:
            self._draw_game_over(img, game, inter)
        self._draw_cursor(img, cursor, inter, info)
        return img

    def _draw_header(self, img, game) -> None:
        L = self.L
        cv2.rectangle(img, (0, 0), (L.w, L.header_h), C_PANEL, -1)
        put_text(img, "BLOCK BLAST 5x5", (24, 43), 0.85, C_ACCENT, 2)
        put_text(img, f"SKOR  {game.score}", (L.w // 2, 46), 1.15, C_TEXT, 3, "center")
        best = max(game.high_score, game.score)
        put_text(img, f"TERBAIK  {best}", (L.w - 24, 43), 0.75, C_MUTED, 2, "right")

    def _draw_board(self, img, game, inter) -> None:
        L = self.L
        n = config.BOARD_SIZE
        pad = 10
        cv2.rectangle(img, (L.bx - pad, L.by - pad),
                      (L.bx + L.board_px + pad, L.by + L.board_px + pad), C_BOARD, -1)
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
                    draw_cell(img, x, y, L.cell, color, alpha=0.55)
            if valid:   # sorot baris/kolom yang akan terhapus
                rows, cols = inter.clear_preview
                for r in rows:
                    blend_rect(img, L.bx, L.by + r * L.cell, L.bx + L.board_px,
                               L.by + (r + 1) * L.cell, (255, 255, 255), 0.22)
                for c in cols:
                    blend_rect(img, L.bx + c * L.cell, L.by, L.bx + (c + 1) * L.cell,
                               L.by + L.board_px, (255, 255, 255), 0.22)

    def _draw_slots(self, img, game, inter) -> None:
        L = self.L
        for i, (x0, y0, x1, y1) in enumerate(L.slots):
            hovered = inter.state == "idle" and inter.hover_slot == i
            cv2.rectangle(img, (x0, y0), (x1, y1), C_PANEL, -1)
            cv2.rectangle(img, (x0, y0), (x1, y1), C_ACCENT if hovered else C_EDGE, 3 if hovered else 2)
            center = ((x0 + x1) // 2, (y0 + y1) // 2)
            piece = game.slots[i]
            if piece is None:
                put_text(img, "-", (center[0], center[1] + 10), 0.9, C_EDGE, 2, "center", False)
                continue
            if inter.state == "hold" and inter.held == i:
                draw_piece(img, piece.shape, PALETTE[piece.color], center, L.mini_cell, alpha=0.25)
                put_text(img, "dipegang", (center[0], y1 - 10), 0.5, C_MUTED, 1, "center")
                continue
            fits = game.slot_fits(i)
            draw_piece(img, piece.shape, PALETTE[piece.color] if fits else C_GREY,
                       center, L.mini_cell)
            if not fits:
                put_text(img, "tidak muat", (center[0], y1 - 8), 0.5, C_WARN, 1, "center")

    def _draw_camera(self, img, result, info) -> int:
        """Thumbnail kamera + mask + zona aktif. Kembalikan koordinat y bawahnya."""
        x0, y0, x1 = self.L.thumb
        tw = x1 - x0
        if result is None:
            th = 170
            cv2.rectangle(img, (x0, y0), (x1, y0 + th), C_PANEL, -1)
            msg = "Mode mouse" if info.get("input_mode") == "mouse" else "Kamera tidak aktif"
            put_text(img, msg, ((x0 + x1) // 2, y0 + th // 2 + 8), 0.6, C_MUTED, 1, "center")
            cv2.rectangle(img, (x0, y0), (x1, y0 + th), C_EDGE, 2)
            return y0 + th
        small = result.frame_small
        sh, sw = small.shape[:2]
        th = int(tw * sh / sw)
        view = cv2.resize(small, (tw, th), interpolation=cv2.INTER_AREA)
        m = cv2.resize(result.mask, (tw, th), interpolation=cv2.INTER_NEAREST) > 0
        view[m] = (view[m] * 0.45 + np.array(C_VALID) * 0.55).astype(np.uint8)
        zx0, zy0, zx1, zy1 = config.ACTIVE_ZONE
        cv2.rectangle(view, (int(zx0 * tw), int(zy0 * th)), (int(zx1 * tw), int(zy1 * th)),
                      C_ACCENT, 1)
        if result.found:
            cv2.circle(view, (int(result.point[0] * tw), int(result.point[1] * th)), 5,
                       (0, 0, 255), -1, AA)
        img[y0:y0 + th, x0:x1] = view
        cv2.rectangle(img, (x0, y0), (x1, y0 + th), C_EDGE, 2)
        put_text(img, "Hijau = terdeteksi, kotak = zona gerak", (x0, y0 + th + 20), 0.45, C_MUTED, 1)
        return y0 + th + 20

    def _draw_keys(self, img, y) -> None:
        x0 = self.L.thumb[0]
        put_text(img, "KONTROL", (x0, y), 0.6, C_ACCENT, 2)
        for i, line in enumerate(KEY_HELP):
            put_text(img, line, (x0, y + 28 + i * 25), 0.52, C_TEXT, 1)

    def _draw_panel(self, img, game, inter, info, now) -> None:
        L = self.L
        x, y, width = L.panel_x, L.by + 10, L.panel_w
        put_text(img, "STATUS", (x, y), 0.6, C_ACCENT, 2)
        y += 30
        if info.get("input_mode") == "mouse":
            mode = "Mouse"
        else:
            mode = info.get("track_label", "Tangan")
            if not info.get("calibrated"):
                mode += " *"
        level = config.LEVEL_NAMES[min(game.level(), len(config.LEVEL_NAMES) - 1)]
        for text in (f"Input : {mode}", f"Level : {level}", f"FPS   : {info.get('fps', 0):.0f}"):
            put_text(img, text, (x, y), 0.55, C_TEXT, 1)
            y += 26
        if game.combo > 1:
            put_text(img, f"KOMBO x{game.combo}", (x, y + 8), 0.85, C_ACCENT, 2)
            y += 42
        y += 18
        put_text(img, "PETUNJUK", (x, y), 0.6, C_ACCENT, 2)
        y += 28
        for line in wrap_text(inter.hint(), width, 0.52):
            put_text(img, line, (x, y), 0.52, C_TEXT, 1)
            y += 24
        notes = []
        if inter.message and now < inter.message_until:
            notes.append(inter.message)
        if info.get("warning"):
            notes.append(info["warning"])
        for note in notes:
            y += 14
            for line in wrap_text(note, width, 0.5):
                put_text(img, line, (x, y), 0.5, C_WARN, 1)
                y += 23
        if info.get("input_mode") == "hand" and not info.get("calibrated"):
            put_text(img, "* belum kalibrasi (tekan C)", (x, L.h - 24), 0.48, C_MUTED, 1)

    def _draw_game_over(self, img, game, inter) -> None:
        L = self.L
        blend_rect(img, 0, 0, L.w, L.h, (0, 0, 0), 0.62)
        cx, cy = L.w // 2, L.h // 2
        put_text(img, "GAME OVER", (cx, cy - 110), 1.8, C_INVALID, 4, "center")
        put_text(img, f"Skor: {game.score}", (cx, cy - 45), 1.0, C_TEXT, 2, "center")
        if game.new_record:
            put_text(img, "REKOR BARU!", (cx, cy + 5), 0.9, C_ACCENT, 2, "center")
        else:
            put_text(img, f"Terbaik: {game.high_score}", (cx, cy + 5), 0.8, C_MUTED, 2, "center")
        x0, y0, x1, y1 = L.button
        hovered = inter.progress_kind == "button"
        cv2.rectangle(img, (x0, y0), (x1, y1), C_ACCENT if hovered else C_PANEL, -1)
        cv2.rectangle(img, (x0, y0), (x1, y1), C_ACCENT, 2)
        put_text(img, "MAIN LAGI", (cx, (y0 + y1) // 2 + 11), 0.95,
                 C_BG if hovered else C_TEXT, 2, "center", shadow=not hovered)
        put_text(img, "Tahan tangan di tombol, atau tekan R", (cx, y1 + 32), 0.55, C_MUTED, 1, "center")

    def _draw_cursor(self, img, cursor, inter, info) -> None:
        if cursor is None:
            last = info.get("last_cursor")
            if last is not None and info.get("input_mode") == "hand":
                p = (int(last[0]), int(last[1]))
                cv2.circle(img, p, 14, C_MUTED, 2, AA)
                put_text(img, "?", (p[0], p[1] + 7), 0.6, C_MUTED, 2, "center", shadow=False)
                put_text(img, "Tangan tidak terdeteksi", (p[0], p[1] + 42), 0.5, C_WARN, 1, "center")
            return
        p = (int(cursor[0]), int(cursor[1]))
        if inter.progress_kind and inter.progress > 0:
            color = RING_COLORS.get(inter.progress_kind, C_ACCENT)
            cv2.circle(img, p, 28, (80, 80, 80), 3, AA)
            # Dwell bar: busur 0..360 derajat, mulai dari atas
            cv2.ellipse(img, p, (28, 28), -90, 0, 360 * inter.progress, color, 6, AA)
        cv2.circle(img, p, 11, (255, 255, 255), 2, AA)
        cv2.circle(img, p, 3, (255, 255, 255), -1, AA)

    # ========================================================= kalibrasi
    def render_calibration(self, frame, calib, tracker, result, info: dict):
        L = self.L
        if frame is None:
            img = np.full((L.h, L.w, 3), C_BG, np.uint8)
            put_text(img, "Kamera tidak terbaca.", (L.w // 2, L.h // 2 - 20), 1.0, C_TEXT, 2, "center")
            put_text(img, "Tekan M untuk main dengan mouse, atau Q untuk keluar.",
                     (L.w // 2, L.h // 2 + 25), 0.7, C_MUTED, 2, "center")
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
            cv2.rectangle(img, p0, p1, C_ACCENT, 3)
            cx_box = p0[0] + (p1[0] - p0[0]) // 2
            put_text(img, "taruh warna di sini", (cx_box, p1[1] + 28),
                     0.6, C_ACCENT, 2, "center")
            if tracker.mode == "glove":
                # Kotak pratinjau warna dominan yang terdeteksi di dalam area kalibrasi
                sw_x0, sw_y0 = cx_box - 95, p1[1] + 42
                sw_x1, sw_y1 = sw_x0 + 32, sw_y0 + 26
                cv2.rectangle(img, (sw_x0, sw_y0), (sw_x1, sw_y1), tracker.dominant_bgr, -1)
                cv2.rectangle(img, (sw_x0, sw_y0), (sw_x1, sw_y1), (255, 255, 255), 2)
                put_text(img, "Warna Dominan", (sw_x1 + 10, sw_y0 + 19), 0.55, C_TEXT, 1)

        blend_rect(img, 0, 0, L.w, 168, (0, 0, 0), 0.6)
        put_text(img, f"KALIBRASI WARNA  -  {tracker.label}", (30, 45), 0.95, C_ACCENT, 2)
        thing = "objek/sarung tangan warna apa saja" if tracker.mode == "glove" else "telapak tangan"
        if calib.phase == "wait":
            extra = "   L: pakai profil tersimpan" if info.get("profile_exists") else ""
            lines = [f"1. Masukkan {thing} ke kotak kuning sampai penuh.",
                     f"2. Tekan SPASI (tahan 1 dtk) atau ENTER untuk kunci warna.   [Threshold: {tracker.range_text()}]",
                     f"ENTER: kunci warna saat ini{extra}   M: mode mouse   Q: keluar"]
        elif calib.phase == "sampling":
            lines = ["Menganalisis warna dominan & membuat threshold... tahan diam."]
            bx0, by0 = 30, 100
            cv2.rectangle(img, (bx0, by0), (bx0 + 500, by0 + 18), C_EDGE, 2)
            cv2.rectangle(img, (bx0, by0), (bx0 + int(500 * calib.progress), by0 + 18), C_ACCENT, -1)
        else:
            lines = ["Area HIJAU = yang terdeteksi. Pastikan hanya tangan/objek yang hijau.",
                     "ENTER: mulai main    SPASI: kalibrasi ulang    D: atur manual (debug)",
                     f"Threshold aktif: {tracker.range_text()}"]
        for i, text in enumerate(lines):
            put_text(img, text, (30, 82 + i * 28), 0.60, C_TEXT, 1 if i else 2)

        notes = [n for n in (info.get("cam_note"), tracker.warning) if n]
        if notes:
            blend_rect(img, 0, L.h - 34 * len(notes) - 10, L.w, L.h, (0, 0, 0), 0.6)
            for i, n in enumerate(notes):
                put_text(img, n, (30, L.h - 34 * (len(notes) - i) + 14), 0.55, C_WARN, 1)
        return img


# --------------------------------------------------------------------------
# Jendela debug (mask + trackbar untuk setel rentang warna manual)
# --------------------------------------------------------------------------
class DebugWindow:
    NAME = "Debug Mask"

    def __init__(self):
        self.is_open = False
        self._spec: list = []
        self._last = None

    @staticmethod
    def _make_spec(mode: str) -> list:
        # (nama trackbar, kanal, "lo"/"hi", nilai maksimum)
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
        """Samakan posisi trackbar dengan rentang tracker (mis. setelah kalibrasi)."""
        if not self.is_open:
            return
        for name, ch, which, _ in self._spec:
            val = tracker.lo[ch] if which == "lo" else tracker.hi[ch]
            cv2.setTrackbarPos(name, self.NAME, int(val))
        self._last = self._read()

    def apply(self, tracker) -> None:
        """Terapkan perubahan trackbar ke tracker."""
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
