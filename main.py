"""Gesture Block Blast 5x5: loop game, state machine Hover & Dwell, input keyboard.

Jalankan:  python main.py

State interaksi:
  idle -> (dwell di slot 1.0 s)  -> hold
  hold -> (dwell di petak valid 1.2 s) -> taruh balok -> idle / over
  hold -> (keluar papan / dwell di slot asal / tangan hilang) -> batal -> idle
  over -> (dwell di tombol MAIN LAGI / tekan R) -> idle
"""
from __future__ import annotations

import os
import time

import cv2

import config
from game_logic import Game
from hand_tracker import Calibrator, CursorSmoother, HandTracker, open_camera
from ui import C_ACCENT, C_VALID, DebugWindow, Layout, Renderer

IDLE, HOLD, OVER = "idle", "hold", "over"


class DwellTimer:
    """Menghitung lama kursor 'berdiam' pada satu target.

    Waktu hanya bertambah saat update() dipanggil dengan target yang sama, jadi
    kalau tangan hilang sebentar (update tidak dipanggil) timer otomatis tertahan.
    """

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self.key = None
        self.elapsed = 0.0

    def update(self, key, dt: float, duration: float) -> float:
        if key != self.key:
            self.key = key
            self.elapsed = 0.0
        else:
            self.elapsed += dt
        return min(1.0, self.elapsed / duration)


class TargetStabilizer:
    """Histeresis: sel target baru diterima setelah stabil beberapa frame.

    Mencegah timer dwell ter-reset karena kursor bergetar di perbatasan petak.
    """

    def __init__(self, frames: int):
        self.frames = frames
        self.reset()

    def reset(self) -> None:
        self.current = None
        self.pending = None
        self.count = 0

    def update(self, value):
        if value == self.current:
            self.pending, self.count = None, 0
            return self.current
        if value == self.pending:
            self.count += 1
        else:
            self.pending, self.count = value, 1
        if self.current is None or self.count >= self.frames:
            self.current, self.pending, self.count = value, None, 0
        return self.current


class Interaction:
    """State machine Hover & Dwell."""

    def __init__(self, game: Game, layout: Layout, effects):
        self.game = game
        self.L = layout
        self.fx = effects
        self.dwell = DwellTimer()
        self.stab = TargetStabilizer(config.TARGET_STABLE_FRAMES)
        self.message = ""
        self.message_until = 0.0
        self.reset()

    def reset(self) -> None:
        self.state = OVER if self.game.game_over else IDLE
        self.held = None
        self.ghost = None                 # ((r0, c0), valid)
        self.clear_preview = ([], [])
        self.progress = 0.0
        self.progress_kind = None
        self.hover_slot = None
        self.entered_board = False
        self.left_origin = False
        self.outside_t = 0.0
        self.cooldown_until = 0.0
        self.blocked_slot = None
        self.lost_t = 0.0
        self.dwell.reset()
        self.stab.reset()

    def toast(self, text: str, now: float, duration: float = 2.5) -> None:
        self.message, self.message_until = text, now + duration

    def hint(self) -> str:
        if self.state == IDLE:
            return "Arahkan tangan ke salah satu balok di bawah, tahan 1 detik untuk mengambil."
        if self.state == HOLD:
            if self.ghost is not None:
                if self.ghost[1]:
                    return "Tahan diam untuk menaruh balok."
                return "Posisi tidak muat. Geser tangan ke tempat lain."
            return ("Bawa balok ke papan. Untuk batal: tahan di slot asal, "
                    "atau tarik tangan keluar papan.")
        return "Tahan tangan di tombol MAIN LAGI, atau tekan R."

    # ------------------------------------------------------------ update
    def update(self, cursor, now: float, dt: float) -> None:
        self.progress, self.progress_kind, self.hover_slot = 0.0, None, None
        if cursor is None:
            self.lost_t += dt
            if self.state == HOLD and self.lost_t >= config.HAND_LOST_CANCEL:
                self.cancel(now, "Tangan hilang, balok dikembalikan.")
            return
        self.lost_t = 0.0
        if self.state == IDLE:
            self._update_idle(cursor, now, dt)
        elif self.state == HOLD:
            self._update_hold(cursor, now, dt)
        else:
            self._update_over(cursor, now, dt)

    def _update_idle(self, cursor, now, dt) -> None:
        slot = self.L.slot_at(cursor)
        self.hover_slot = slot
        if self.blocked_slot is not None and slot != self.blocked_slot:
            self.blocked_slot = None      # kursor sudah keluar dari slot yang baru dibatalkan
        if (slot is None or self.game.slots[slot] is None
                or slot == self.blocked_slot or now < self.cooldown_until):
            self.dwell.reset()
            return
        p = self.dwell.update(("pick", slot), dt, config.DWELL_PICK)
        self.progress, self.progress_kind = p, "pick"
        if p >= 1.0:
            self.state = HOLD
            self.held = slot
            self.entered_board = False
            self.left_origin = False
            self.outside_t = 0.0
            self.ghost = None
            self.stab.reset()
            self.dwell.reset()

    def _update_hold(self, cursor, now, dt) -> None:
        piece = self.game.slots[self.held]
        if self.L.over_board(cursor):
            self.entered_board = self.left_origin = True
            self.outside_t = 0.0
            fr, fc = self.L.board_frac(cursor)
            target = self.stab.update(Game.anchor(piece, fr, fc))
            valid = self.game.can_place(self.held, *target)
            self.ghost = (target, valid)
            self.clear_preview = self.game.preview_clears(self.held, *target) if valid else ([], [])
            if not valid:
                self.dwell.reset()
                return
            p = self.dwell.update(("place", target), dt, config.DWELL_PLACE)
            self.progress, self.progress_kind = p, "place"
            if p >= 1.0:
                self._place(target, now)
            return

        # Di luar papan
        self.ghost = None
        self.clear_preview = ([], [])
        self.stab.reset()
        slot = self.L.slot_at(cursor)
        if slot != self.held:
            self.left_origin = True
        if slot == self.held and self.left_origin:
            p = self.dwell.update(("cancel",), dt, config.DWELL_CANCEL)
            self.progress, self.progress_kind = p, "cancel"
            if p >= 1.0:
                self.cancel(now, "Balok dikembalikan ke slot.")
            return
        self.dwell.reset()
        if self.entered_board:
            self.outside_t += dt
            if self.outside_t >= config.CANCEL_OUTSIDE_TIME:
                self.cancel(now, "Keluar papan, balok dikembalikan.")

    def _update_over(self, cursor, now, dt) -> None:
        if self.L.in_button(cursor):
            p = self.dwell.update(("restart",), dt, config.DWELL_BUTTON)
            self.progress, self.progress_kind = p, "button"
            if p >= 1.0:
                self.restart(now)
        else:
            self.dwell.reset()

    # ------------------------------------------------------------ aksi
    def _place(self, target, now: float) -> None:
        piece = self.game.slots[self.held]
        res = self.game.place(self.held, *target)
        if res is None:
            return
        n = config.BOARD_SIZE
        cleared = {(r, c) for r in res.rows for c in range(n)}
        cleared |= {(r, c) for c in res.cols for r in range(n)}
        self.fx.add_clear(cleared, now)
        x, y = self.L.cell_xy(*target)
        center = (x + piece.w * self.L.cell / 2, y + piece.h * self.L.cell / 2)
        self.fx.add_popup(f"+{res.points}", center, now, C_VALID)
        if res.combo > 1:
            self.fx.add_popup(f"KOMBO x{res.combo}", (self.L.w / 2, self.L.by + 40), now, C_ACCENT, 1.3)
        if res.board_cleared:
            self.fx.add_popup("PAPAN BERSIH!", (self.L.w / 2, self.L.by + self.L.board_px / 2),
                              now, C_ACCENT, 1.5)
        self.held = None
        self.ghost = None
        self.clear_preview = ([], [])
        self.dwell.reset()
        self.stab.reset()
        self.cooldown_until = now + config.PICK_COOLDOWN
        self.state = OVER if self.game.game_over else IDLE

    def cancel(self, now: float, message: str = "") -> None:
        if self.state != HOLD:
            return
        self.blocked_slot = self.held
        self.held = None
        self.ghost = None
        self.clear_preview = ([], [])
        self.dwell.reset()
        self.stab.reset()
        self.cooldown_until = now + config.PICK_COOLDOWN
        self.state = IDLE
        if message:
            self.toast(message, now)

    def restart(self, now: float) -> None:
        self.game.reset()
        self.fx.clear()
        self.reset()
        self.cooldown_until = now + config.PICK_COOLDOWN


def profile_path(mode: str) -> str:
    return os.path.join(config.BASE_DIR, config.PROFILE_DIR, f"profil_{mode}.json")


def main() -> None:
    layout = Layout()
    renderer = Renderer(layout)
    game = Game()
    inter = Interaction(game, layout, renderer.fx)
    tracker = HandTracker(config.TRACK_MODE)
    prof = profile_path(tracker.mode)
    debug = DebugWindow()
    smoother = CursorSmoother()

    print("Membuka kamera...")
    cap = open_camera()
    calib = Calibrator(tracker, cap)
    if cap is None:
        print("Kamera tidak ditemukan. Game berjalan dengan mouse.")
        input_mode, app = "mouse", "play"
    else:
        input_mode, app = "hand", "calib"
        calib.start()

    scale = config.DISPLAY_SCALE
    mouse = {"pos": None}

    def on_mouse(_event, x, y, _flags, _param):
        mouse["pos"] = (x / scale, y / scale)

    cv2.namedWindow(config.WINDOW_NAME, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(config.WINDOW_NAME, on_mouse)

    prev = time.monotonic()
    fps = 0.0
    last_cursor = None
    if cap is None:
        inter.toast("Kamera tidak ditemukan, mode mouse aktif.", prev, 5)

    try:
        while True:
            now = time.monotonic()
            raw_dt = now - prev
            dt = min(raw_dt, 0.1)
            prev = now
            if raw_dt > 0:
                fps = 1 / raw_dt if fps == 0 else 0.9 * fps + 0.1 / raw_dt

            frame = None
            if cap is not None:
                ok, f = cap.read()
                if ok:
                    frame = cv2.flip(f, 1) if config.MIRROR else f
            result = tracker.process(frame) if frame is not None else None

            if app == "calib":
                if frame is not None:
                    before = calib.phase
                    calib.feed(frame)
                    if calib.phase == "wait" and debug.is_open:
                        debug.sync(tracker)
                    elif before == "sampling" and calib.phase == "preview":
                        tracker.save_profile(prof)
                        debug.sync(tracker)          # trackbar ikut hasil kalibrasi baru
                canvas = renderer.render_calibration(
                    frame, calib, tracker, result,
                    {"profile_exists": os.path.exists(prof), "cam_note": calib.cam_note})
            else:
                cursor = None
                if input_mode == "mouse":
                    cursor = mouse["pos"]
                elif result is not None and result.found:
                    cursor = smoother(layout.map_from_camera(result.point), now)
                elif inter.lost_t >= config.SMOOTHER_RESET_AFTER:
                    smoother.reset()
                if cursor is not None:
                    last_cursor = cursor
                inter.update(cursor, now, dt)
                info = {
                    "fps": fps,
                    "input_mode": input_mode,
                    "track_label": tracker.label,
                    "calibrated": tracker.calibrated,
                    "warning": tracker.warning if input_mode == "hand" else "",
                    "last_cursor": last_cursor,
                }
                canvas = renderer.render_game(game, inter, cursor, result, info, now)

            if app != "calib" or calib.phase == "preview":
                debug.apply(tracker)
            debug.show(result)
            if scale != 1.0:
                canvas = cv2.resize(canvas, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            cv2.imshow(config.WINDOW_NAME, canvas)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            try:
                if cv2.getWindowProperty(config.WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
                    break
            except cv2.error:
                break

            # ------------------------------------------------ keyboard
            if key == ord("d") and cap is not None:
                debug.toggle(tracker)
            elif key == ord("s") and cap is not None:
                tracker.save_profile(prof)
                inter.toast(f"Profil warna disimpan ({os.path.basename(prof)}).", now)

            if app == "calib":
                if key == 32 and calib.phase in ("wait", "preview"):         # SPASI
                    calib.begin_sampling()
                elif key in (13, 10):                                        # ENTER
                    if calib.phase == "preview":
                        tracker.save_profile(prof)
                        inter.toast("Kalibrasi selesai, profil disimpan.", now)
                    elif calib.phase == "wait":
                        calib.calibrate_instant(frame)
                        tracker.save_profile(prof)
                        debug.sync(tracker)
                        inter.toast("Warna dominan di kotak dikunci & disimpan.", now)
                    if calib.phase != "sampling":
                        app = "play"
                        smoother.reset()
                elif key == ord("l") and calib.phase == "wait":
                    if tracker.load_profile(prof):
                        calib.phase = "preview"
                        debug.sync(tracker)
                elif key == ord("m"):
                    input_mode, app = "mouse", "play"
            else:
                if key == ord("c") and cap is not None:
                    inter.cancel(now)
                    calib.start()
                    app = "calib"
                elif key == ord("m"):
                    if input_mode == "mouse" and cap is not None:
                        input_mode = "hand"
                        smoother.reset()
                    else:
                        input_mode = "mouse"
                    inter.cancel(now)
                    inter.toast(f"Input: {'mouse' if input_mode == 'mouse' else 'tangan'}.", now)
                elif key == ord("r"):
                    inter.restart(now)
    finally:
        if cap is not None:
            cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
