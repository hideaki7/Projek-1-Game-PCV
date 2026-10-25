from __future__ import annotations

import os
import threading
import time

import cv2
import numpy as np

try:
    import sounddevice as sd
    import soundfile as sf
except ImportError:
    sd = None
    sf = None

import config
from game_logic import Game
from hand_tracker import Calibrator, CursorSmoother, HandTracker, open_camera
from ui import C_ACCENT, C_VALID, DebugWindow, Layout, Renderer

IDLE, HOLD, OVER = "idle", "hold", "over"


# --- Audio Mixer (Backsound Loop & Sound Effects) ---
class AudioManager:
    SAMPLE_RATE = 48000

    def __init__(self):
        self.bgm: np.ndarray | None = None
        self.bgm_pos = 0
        self.bgm_paused = False
        self.sfx: dict[str, np.ndarray] = {}
        self.active_sfx: list[list] = []
        self.lock = threading.Lock()
        self.stream = None
        self._load_assets()

    @staticmethod
    def _load_wave(path: str, gain_db: float) -> np.ndarray | None:
        if sf is None or not os.path.exists(path):
            return None
        try:
            data, _ = sf.read(path, dtype="float32", always_2d=True)
        except Exception:
            return None
        if len(data) == 0:
            return None
        if data.shape[1] == 1:
            data = np.repeat(data, 2, axis=1)
        elif data.shape[1] > 2:
            data = data[:, :2]
        # Normalisasi puncak dasar ke -6 dBFS (0.5) lalu kalikan faktor gain dB
        peak = float(np.max(np.abs(data)))
        if peak > 1e-5:
            data = data * (0.5 / peak)
        gain = 10.0 ** (gain_db / 20.0)
        return np.clip(data * gain, -1.0, 1.0).astype(np.float32)

    def _load_assets(self) -> None:
        self.bgm = self._load_wave(config.BGM_PATH, config.BGM_GAIN_DB)
        sfx_specs = {
            "place": (config.SFX_PLACE_PATH, config.SFX_PLACE_GAIN_DB),
            "blast": (config.SFX_BLAST_PATH, config.SFX_BLAST_GAIN_DB),
            "gameover": (config.SFX_GAMEOVER_PATH, config.SFX_GAMEOVER_GAIN_DB),
        }
        for name, (path, gain_db) in sfx_specs.items():
            wav = self._load_wave(path, gain_db)
            if wav is not None:
                self.sfx[name] = wav

    def _callback(self, outdata: np.ndarray, frames: int, _time, _status) -> None:
        outdata.fill(0.0)
        if self.bgm is not None and not self.bgm_paused:
            n = len(self.bgm)
            rem = frames
            out_idx = 0
            while rem > 0:
                chunk = min(rem, n - self.bgm_pos)
                outdata[out_idx:out_idx + chunk] += self.bgm[self.bgm_pos:self.bgm_pos + chunk]
                self.bgm_pos = (self.bgm_pos + chunk) % n
                out_idx += chunk
                rem -= chunk

        with self.lock:
            still_active = []
            for item in self.active_sfx:
                buf, pos = item
                chunk = min(frames, len(buf) - pos)
                if chunk > 0:
                    outdata[:chunk] += buf[pos:pos + chunk]
                    item[1] += chunk
                if item[1] < len(buf):
                    still_active.append(item)
            self.active_sfx = still_active

        np.clip(outdata, -1.0, 1.0, out=outdata)

    def start(self) -> None:
        if sd is None or (self.bgm is None and not self.sfx):
            return
        try:
            self.stream = sd.OutputStream(
                samplerate=self.SAMPLE_RATE,
                channels=2,
                dtype="float32",
                callback=self._callback,
            )
            self.stream.start()
        except Exception:
            self.stream = None

    def play(self, name: str) -> None:
        buf = self.sfx.get(name)
        if buf is None or self.stream is None:
            return
        with self.lock:
            self.active_sfx.append([buf, 0])

    def pause_bgm(self) -> None:
        self.bgm_paused = True

    def resume_bgm(self) -> None:
        self.bgm_paused = False

    def stop(self) -> None:
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None


class DwellTimer:
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
        return min(1.0, self.elapsed / max(duration, 1e-6))


class TargetStabilizer:
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


# --- State Machine Interaksi (idle / hold / over) ---
class Interaction:
    def __init__(self, game: Game, layout: Layout, effects, audio: AudioManager | None = None):
        self.game = game
        self.L = layout
        self.fx = effects
        self.audio = audio
        self.dwell = DwellTimer()
        self.stab = TargetStabilizer(config.TARGET_STABLE_FRAMES)
        self.message = ""
        self.message_until = 0.0
        self.reset()

    def reset(self) -> None:
        self.state = OVER if self.game.game_over else IDLE
        self.held = None
        self.ghost = None
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
            self.blocked_slot = None
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
        if self.held is None or self.game.slots[self.held] is None:
            self.reset()
            return
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

    def _place(self, target, now: float) -> None:
        if self.held is None:
            return
        piece = self.game.slots[self.held]
        if piece is None:
            return
        res = self.game.place(self.held, *target)
        if res is None:
            return
        n = config.BOARD_SIZE
        cleared = {(r, c) for r in res.rows for c in range(n)}
        cleared |= {(r, c) for c in res.cols for r in range(n)}
        if self.audio is not None:
            self.audio.play("place")
            if cleared:
                self.audio.play("blast")
            if self.game.game_over:
                self.audio.pause_bgm()
                self.audio.play("gameover")
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
        self.dwell.reset()
        self.stab.reset()
        self.hover_slot = None
        if self.state != HOLD:
            return
        self.blocked_slot = self.held
        self.held = None
        self.ghost = None
        self.clear_preview = ([], [])
        self.cooldown_until = now + config.PICK_COOLDOWN
        self.state = IDLE
        if message:
            self.toast(message, now)

    def restart(self, now: float) -> None:
        self.game.reset()
        self.fx.clear()
        self.reset()
        self.cooldown_until = now + config.PICK_COOLDOWN
        if self.audio is not None:
            self.audio.resume_bgm()


def profile_path(mode: str) -> str:
    return os.path.join(config.BASE_DIR, config.PROFILE_DIR, f"profil_{mode}.json")


def main() -> None:
    layout = Layout()
    renderer = Renderer(layout)
    game = Game()
    audio = AudioManager()
    audio.start()
    inter = Interaction(game, layout, renderer.fx, audio)
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
                        debug.sync(tracker)
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

            # --- Kontrol Keyboard ---
            if key == ord("d") and cap is not None:
                debug.toggle(tracker)
            elif key == ord("s") and cap is not None:
                tracker.save_profile(prof)
                inter.toast(f"Profil warna disimpan ({os.path.basename(prof)}).", now)

            if app == "calib":
                if key == 32 and calib.phase in ("wait", "preview"):
                    calib.begin_sampling()
                elif key in (13, 10):
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
        audio.stop()
        if cap is not None:
            cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
