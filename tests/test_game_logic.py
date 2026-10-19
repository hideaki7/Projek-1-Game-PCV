"""Tes logika game. Jalankan dari folder proyek:  python -m pytest tests
atau tanpa pytest:  python tests/test_game_logic.py
"""
import os
import random
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from game_logic import (CATALOG, SINGLE, Board, Game, Spawner, can_place_all,  # noqa: E402
                        level_index)


def _piece(name):
    for groups in CATALOG.values():
        for group in groups:
            for p in group:
                if p.name == name:
                    return p
    raise KeyError(name)


def _tmp_game(seed=0):
    path = os.path.join(tempfile.mkdtemp(), "hs.json")
    return Game(random.Random(seed), highscore_path=path)


def test_catalog_tiers():
    assert all(CATALOG[t] for t in (1, 2, 3))
    assert SINGLE.cells == 1
    assert _piece("Silang").cells == 5
    names = {p.name for g in CATALOG[3] for p in g}
    assert "Garis 5 #1" in names and "Garis 5 #2" in names   # 1x5 dan 5x1


def test_fit_checking_bounds_and_overlap():
    b = Board()
    line5 = _piece("Garis 5 #1")
    assert b.can_place(line5, 0, 0)
    assert not b.can_place(line5, 0, 1)          # keluar tepi kanan
    assert not b.can_place(line5, -1, 0)
    b.grid[2, 2] = 3
    sq = _piece("2x2")
    assert not b.can_place(sq, 1, 1)             # menimpa petak warna 3
    assert b.can_place(sq, 0, 0)


def test_row_and_column_clear_together():
    b = Board()
    b.grid[0, :4] = 1      # baris 0 kurang kolom 4
    b.grid[1:, 4] = 1      # kolom 4 kurang baris 0
    rows, cols = b.place(SINGLE, 0, 4)
    assert rows == [0] and cols == [4]
    assert b.is_empty()


def test_scoring_and_combo():
    g = _tmp_game()
    g.board.grid[0, :4] = 1
    g.slots = [SINGLE, SINGLE, SINGLE]
    res = g.place(0, 0, 4)
    # 1 petak + 10*1^2 + bonus papan bersih
    assert res.points == 1 + 10 + config.BOARD_CLEAR_BONUS
    assert res.board_cleared and g.combo == 1
    g.board.grid[1, :4] = 1
    res = g.place(1, 1, 4)
    assert res.combo == 2
    assert res.points == 1 + int(round(10 * 1.5)) + config.BOARD_CLEAR_BONUS


def test_anchor_centers_and_clamps():
    sq = _piece("2x2")
    assert Game.anchor(SINGLE, 2.5, 2.5) == (2, 2)
    assert Game.anchor(sq, 2.0, 2.0) == (1, 1)
    assert Game.anchor(sq, 2.6, 2.6) == (2, 2)
    assert Game.anchor(sq, 4.9, 4.9) == (3, 3)   # di-clamp ke dalam papan
    assert Game.anchor(sq, -0.3, -0.3) == (0, 0)


def test_tier_table_levels():
    assert level_index(0) == 0 and level_index(199) == 0
    assert level_index(200) == 1 and level_index(499) == 1
    assert level_index(500) == 2
    sp = Spawner(random.Random(1))
    for score in (0, 150):
        for _ in range(200):
            assert all(p.tier < 3 for p in sp._draw_set(score))
    for _ in range(300):
        assert sum(p.tier == 3 for p in sp._draw_set(900)) <= config.MAX_TIER3_PER_SET


def test_spawner_fair_play_random_boards():
    rng = random.Random(42)
    sp = Spawner(rng)
    worst = 0.0
    for _ in range(300):
        b = Board()
        b.grid[:] = (rng.random() < 0.55) * 1
        for r in range(5):                     # jangan ada garis penuh
            if b.grid[r].all():
                b.grid[r, rng.randrange(5)] = 0
        for c in range(5):
            if b.grid[:, c].all():
                b.grid[rng.randrange(5), c] = 0
        t = time.perf_counter()
        pieces = sp.spawn(b, rng.choice([0, 300, 800]))
        worst = max(worst, time.perf_counter() - t)
        assert any(b.fits_anywhere(p) for p in pieces)
    assert worst < 1.0, f"spawn terlalu lambat: {worst:.2f}s"


def test_can_place_all_detects_impossible():
    b = Board()
    b.grid[:] = 1
    b.grid[0, 0] = 0
    b.grid[4, 4] = 0
    assert can_place_all(b.mask, [SINGLE, SINGLE])
    assert not can_place_all(b.mask, [_piece("1x2")])


def test_game_over_and_high_score():
    g = _tmp_game()
    g.board.grid[:] = 1
    for i in range(5):                 # lubang diagonal: hanya 1x1 yang muat
        g.board.grid[i, i] = 0
    g.slots = [SINGLE, _piece("2x2"), _piece("Silang")]
    g.place(0, 0, 0)                   # hapus baris 0 & kolom 0, dapat poin
    assert not g.game_over and g.score > 0
    g.board.grid[:] = 1
    for i in range(5):
        g.board.grid[i, i] = 0
    g._check_game_over()
    assert g.game_over                 # 2x2 dan silang tidak muat lagi
    g2 = Game(random.Random(0), highscore_path=g.highscore_path)
    assert g2.high_score == g.high_score > 0


def test_full_random_game_runs():
    g = _tmp_game(7)
    rng = random.Random(7)
    for _ in range(500):
        if g.game_over:
            break
        options = [(i, r, c) for i, p in enumerate(g.slots) if p
                   for r, c, _ in p.placements if g.can_place(i, r, c)]
        assert options, "slot ada yang muat tapi game belum over"
        g.place(*rng.choice(options))
    assert g.moves > 5


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("OK ", t.__name__)
    print(f"{len(tests)} tes lulus")
