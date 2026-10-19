"""Logika game: papan 5x5, katalog balok, fit-checking, spawner adaptif, skor.

Modul ini tidak bergantung pada OpenCV sama sekali, jadi bisa dites terpisah.
Papan disimpan sebagai matriks NumPy (0 = kosong, >0 = kode warna). Untuk
pencarian cepat (fair-play spawner), papan juga direpresentasikan sebagai
bitmask 25-bit.
"""
from __future__ import annotations

import json
import math
import os
import random
from dataclasses import dataclass

import numpy as np

import config

N = config.BOARD_SIZE
PALETTE_SIZE = 8


# --------------------------------------------------------------------------
# Bitmask helper
# --------------------------------------------------------------------------
def _bit(r: int, c: int) -> int:
    return 1 << (r * N + c)


ROW_MASKS = [sum(_bit(r, c) for c in range(N)) for r in range(N)]
COL_MASKS = [sum(_bit(r, c) for r in range(N)) for c in range(N)]
LINE_MASKS = ROW_MASKS + COL_MASKS


def apply_placement(board_mask: int, piece_mask: int) -> tuple[int, int]:
    """Simulasi menaruh balok di bitmask: kembalikan (mask_baru, jumlah_garis_hapus)."""
    filled = board_mask | piece_mask
    cleared = 0
    lines = 0
    for lm in LINE_MASKS:
        if (filled & lm) == lm:
            cleared |= lm
            lines += 1
    return filled & ~cleared, lines


def full_lines(mask: int) -> tuple[list[int], list[int]]:
    """Daftar baris & kolom yang penuh pada bitmask."""
    rows = [i for i, lm in enumerate(ROW_MASKS) if (mask & lm) == lm]
    cols = [i for i, lm in enumerate(COL_MASKS) if (mask & lm) == lm]
    return rows, cols


# --------------------------------------------------------------------------
# Katalog balok
# --------------------------------------------------------------------------
class PieceType:
    """Satu bentuk balok dalam satu orientasi."""

    __slots__ = ("name", "tier", "shape", "color", "cells", "coords", "placements")

    def __init__(self, name: str, tier: int, shape, color: int):
        self.name = name
        self.tier = tier
        self.shape = np.array(shape, dtype=np.uint8)
        self.color = color
        self.coords = [(int(r), int(c)) for r, c in np.argwhere(self.shape > 0)]
        self.cells = len(self.coords)
        h, w = self.shape.shape
        # Semua posisi (r0, c0) yang tidak keluar papan, beserta bitmask-nya
        self.placements: list[tuple[int, int, int]] = []
        for r0 in range(N - h + 1):
            for c0 in range(N - w + 1):
                m = 0
                for r, c in self.coords:
                    m |= _bit(r0 + r, c0 + c)
                self.placements.append((r0, c0, m))

    @property
    def h(self) -> int:
        return self.shape.shape[0]

    @property
    def w(self) -> int:
        return self.shape.shape[1]

    def mask_at(self, r0: int, c0: int) -> int:
        m = 0
        for r, c in self.coords:
            m |= _bit(r0 + r, c0 + c)
        return m

    def __repr__(self) -> str:
        return f"PieceType({self.name!r}, tier={self.tier})"


def _unique_rotations(shape) -> list[np.ndarray]:
    base = np.array(shape, dtype=np.uint8)
    out: list[np.ndarray] = []
    for k in range(4):
        rot = np.rot90(base, k)
        if not any(rot.shape == o.shape and np.array_equal(rot, o) for o in out):
            out.append(np.ascontiguousarray(rot))
    return out


# (nama, tier, bentuk, pakai_rotasi)
PIECE_DEFS = [
    # Tier 1 - Mudah
    ("1x1", 1, [[1]], False),
    ("1x2", 1, [[1, 1]], False),
    ("2x1", 1, [[1], [1]], False),
    ("2x2", 1, [[1, 1], [1, 1]], False),
    # Tier 2 - Sedang
    ("L kecil", 2, [[1, 0], [1, 1]], True),
    ("1x3", 2, [[1, 1, 1]], False),
    ("3x1", 2, [[1], [1], [1]], False),
    ("T mini", 2, [[1, 1, 1], [0, 1, 0]], True),
    # Tier 3 - Sulit
    ("L besar", 3, [[1, 0, 0], [1, 0, 0], [1, 1, 1]], True),
    ("Garis 4", 3, [[1, 1, 1, 1]], True),        # 1x4 dan 4x1
    ("Garis 5", 3, [[1, 1, 1, 1, 1]], True),     # 1x5 dan 5x1
    ("Silang", 3, [[0, 1, 0], [1, 1, 1], [0, 1, 0]], False),
]


def _build_catalog() -> dict[int, list[list[PieceType]]]:
    """Katalog per tier. Tiap tier berisi grup; satu grup = semua rotasi satu bentuk.

    Spawner memilih grup dulu (peluang sama per bentuk), baru rotasinya, supaya
    bentuk yang punya 4 rotasi tidak jadi lebih sering muncul.
    """
    catalog: dict[int, list[list[PieceType]]] = {1: [], 2: [], 3: []}
    for idx, (name, tier, shape, rotate) in enumerate(PIECE_DEFS):
        color = idx % PALETTE_SIZE + 1
        shapes = _unique_rotations(shape) if rotate else [np.array(shape, dtype=np.uint8)]
        group = []
        for k, s in enumerate(shapes):
            label = name if len(shapes) == 1 else f"{name} #{k + 1}"
            piece = PieceType(label, tier, s, color)
            if piece.placements:          # buang bentuk yang lebih besar dari papan
                group.append(piece)
        if group:
            catalog[tier].append(group)
    return catalog


CATALOG = _build_catalog()
SINGLE = CATALOG[1][0][0]   # balok 1x1, cadangan terakhir spawner


# --------------------------------------------------------------------------
# Papan
# --------------------------------------------------------------------------
class Board:
    def __init__(self, n: int = N):
        self.n = n
        self.grid = np.zeros((n, n), dtype=np.int16)

    @property
    def mask(self) -> int:
        m = 0
        for i in np.flatnonzero(self.grid):
            m |= 1 << int(i)
        return m

    def can_place(self, piece: PieceType, r0: int, c0: int) -> bool:
        """Fit-checking: tidak keluar tepi dan tidak menimpa petak terisi (!= 0)."""
        h, w = piece.shape.shape
        if r0 < 0 or c0 < 0 or r0 + h > self.n or c0 + w > self.n:
            return False
        region = self.grid[r0:r0 + h, c0:c0 + w]
        return not np.any(region[piece.shape > 0] != 0)

    def fits_anywhere(self, piece: PieceType) -> bool:
        m = self.mask
        return any((pm & m) == 0 for _, _, pm in piece.placements)

    def place(self, piece: PieceType, r0: int, c0: int) -> tuple[list[int], list[int]]:
        """Taruh balok, lalu hapus baris & kolom penuh secara bersamaan."""
        h, w = piece.shape.shape
        region = self.grid[r0:r0 + h, c0:c0 + w]
        region[piece.shape > 0] = piece.color
        rows = [r for r in range(self.n) if np.all(self.grid[r, :] != 0)]
        cols = [c for c in range(self.n) if np.all(self.grid[:, c] != 0)]
        for r in rows:
            self.grid[r, :] = 0
        for c in cols:
            self.grid[:, c] = 0
        return rows, cols

    def is_empty(self) -> bool:
        return not np.any(self.grid)


# --------------------------------------------------------------------------
# Spawner adaptif
# --------------------------------------------------------------------------
def can_place_all(mask: int, pieces: list[PieceType], _memo: dict | None = None) -> bool:
    """True jika ada urutan & posisi agar semua balok bisa ditaruh (garis ikut terhapus)."""
    if not pieces:
        return True
    if _memo is None:
        _memo = {}
    key = (mask, tuple(sorted(p.name for p in pieces)))
    if key in _memo:
        return _memo[key]
    result = False
    seen: set[str] = set()
    for i, piece in enumerate(pieces):
        if piece.name in seen:
            continue
        seen.add(piece.name)
        rest = pieces[:i] + pieces[i + 1:]
        for _, _, pm in piece.placements:
            if pm & mask:
                continue
            new_mask, _ = apply_placement(mask, pm)
            if can_place_all(new_mask, rest, _memo):
                result = True
                break
        if result:
            break
    _memo[key] = result
    return result


def level_index(score: int) -> int:
    idx = 0
    for i, (min_score, _) in enumerate(config.TIER_TABLE):
        if score >= min_score:
            idx = i
    return idx


class Spawner:
    def __init__(self, rng: random.Random):
        self.rng = rng

    @staticmethod
    def tier_probs(score: int) -> tuple[float, float, float]:
        return config.TIER_TABLE[level_index(score)][1]

    def _draw_piece(self, tier: int) -> PieceType:
        if not CATALOG.get(tier):
            tier = 1
        group = self.rng.choice(CATALOG[tier])
        return self.rng.choice(group)

    def _draw_set(self, score: int) -> list[PieceType]:
        probs = list(self.tier_probs(score))
        tiers: list[int] = []
        for _ in range(3):
            p = probs[:]
            if tiers.count(3) >= config.MAX_TIER3_PER_SET:
                p[2] = 0.0
            if sum(p) <= 0:
                p = [1.0, 0.0, 0.0]
            tiers.append(self.rng.choices([1, 2, 3], weights=p, k=1)[0])
        return [self._draw_piece(t) for t in tiers]

    def spawn(self, board: Board, score: int, attempts: int = 40) -> list[PieceType]:
        mask = board.mask
        if config.FAIR_PLAY == "strong":
            for _ in range(attempts):
                pieces = self._draw_set(score)
                if can_place_all(mask, pieces):
                    return pieces
        # Aturan PRD: minimal 1 dari 3 balok muat
        for _ in range(attempts):
            pieces = self._draw_set(score)
            if any(board.fits_anywhere(p) for p in pieces):
                return pieces
        # Cadangan terakhir: paksa satu slot jadi 1x1 (selalu muat, karena papan
        # tidak mungkin penuh total: baris penuh pasti terhapus)
        pieces = self._draw_set(score)
        pieces[self.rng.randrange(3)] = SINGLE
        return pieces


# --------------------------------------------------------------------------
# Game
# --------------------------------------------------------------------------
@dataclass
class PlaceResult:
    cells: int
    rows: list
    cols: list
    points: int
    combo: int
    board_cleared: bool

    @property
    def lines(self) -> int:
        return len(self.rows) + len(self.cols)


class Game:
    def __init__(self, rng: random.Random | None = None, highscore_path: str | None = None):
        self.rng = rng or random.Random()
        self.spawner = Spawner(self.rng)
        self.highscore_path = highscore_path or os.path.join(config.BASE_DIR, config.HIGHSCORE_FILE)
        self.high_score = self._load_high_score()
        self.reset()

    def reset(self) -> None:
        self.board = Board()
        self.score = 0
        self.combo = 0
        self.moves = 0
        self.game_over = False
        self.new_record = False
        self._best_at_start = self.high_score
        self.slots: list[PieceType | None] = self.spawner.spawn(self.board, self.score)

    # ---------------------------------------------------------------- query
    def level(self) -> int:
        return level_index(self.score)

    def slot_fits(self, i: int) -> bool:
        p = self.slots[i]
        return p is not None and self.board.fits_anywhere(p)

    def can_place(self, i: int, r0: int, c0: int) -> bool:
        p = self.slots[i]
        return p is not None and self.board.can_place(p, r0, c0)

    def preview_clears(self, i: int, r0: int, c0: int) -> tuple[list[int], list[int]]:
        """Baris & kolom yang akan terhapus kalau balok slot i ditaruh di (r0, c0)."""
        p = self.slots[i]
        if p is None:
            return [], []
        return full_lines(self.board.mask | p.mask_at(r0, c0))

    @staticmethod
    def anchor(piece: PieceType, fr: float, fc: float) -> tuple[int, int]:
        """Ubah posisi kursor (satuan sel, pecahan) jadi pojok kiri-atas balok.

        Kursor dianggap berada di tengah balok. Hasil di-clamp supaya balok
        selalu di dalam papan (snap ke tepi), jadi menaruh di pinggir lebih mudah.
        """
        r0 = math.floor(fr - piece.h / 2 + 0.5)
        c0 = math.floor(fc - piece.w / 2 + 0.5)
        r0 = min(max(r0, 0), N - piece.h)
        c0 = min(max(c0, 0), N - piece.w)
        return r0, c0

    # --------------------------------------------------------------- action
    def place(self, i: int, r0: int, c0: int) -> PlaceResult | None:
        if self.game_over or not self.can_place(i, r0, c0):
            return None
        piece = self.slots[i]
        rows, cols = self.board.place(piece, r0, c0)
        lines = len(rows) + len(cols)

        points = piece.cells * config.POINTS_PER_CELL
        if lines:
            self.combo += 1
            mult = 1 + config.COMBO_STEP * (self.combo - 1)
            points += int(round(config.LINE_POINTS * lines * lines * mult))
        else:
            self.combo = 0
        board_cleared = lines > 0 and self.board.is_empty()
        if board_cleared:
            points += config.BOARD_CLEAR_BONUS

        self.score += points
        self.moves += 1
        if self.score > self.high_score:
            self.high_score = self.score
            self._save_high_score()
        self.new_record = self.score > self._best_at_start

        self.slots[i] = None
        if all(s is None for s in self.slots):
            self.slots = self.spawner.spawn(self.board, self.score)
        self._check_game_over()
        return PlaceResult(piece.cells, rows, cols, points, self.combo, board_cleared)

    def _check_game_over(self) -> None:
        remaining = [p for p in self.slots if p is not None]
        if remaining and not any(self.board.fits_anywhere(p) for p in remaining):
            self.game_over = True

    # ----------------------------------------------------------- high score
    def _load_high_score(self) -> int:
        try:
            with open(self.highscore_path, "r", encoding="utf-8") as f:
                return int(json.load(f).get("high_score", 0))
        except (OSError, ValueError, TypeError, AttributeError):
            return 0

    def _save_high_score(self) -> None:
        try:
            with open(self.highscore_path, "w", encoding="utf-8") as f:
                json.dump({"high_score": self.high_score}, f)
        except OSError:
            pass
