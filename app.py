"""
Watch a minesweeper board on the screen and play the certain moves.

Nothing here opens Chrome or attaches to the page. You open the game yourself
and draw a box around the cells. After each change the tool reads the pixels,
flags the red cells, clicks a number that already has enough flags so the game
opens around it, then opens the green cells.

    python screen_solver.py
    python screen_solver.py --difficulty expert
"""

from __future__ import annotations

import argparse
import ctypes
import importlib.util
import sys
import time
import types
from pathlib import Path

import tkinter as tk
from PIL import ImageGrab

# rows, columns, mines. Expert is 16 rows by 30 columns.
DIFFICULTIES = {
    "beginner": (9, 9, 10),
    "intermediate": (16, 16, 40),
    "expert": (16, 30, 99),
}


def enable_dpi():
    """Use real pixels on every monitor, so screenshot, overlay and clicks agree.

    This must run before pyautogui is imported: pyautogui switches the process to
    the older system-wide mode, and after that Windows refuses any change. On a
    second monitor with another scale the clicks then land off the cells.
    """
    try:
        # Per-monitor v2.
        if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


enable_dpi()

try:
    import pyautogui
except ImportError:
    pyautogui = None


def virtual_screen() -> tuple[int, int, int, int]:
    """Left, top, width and height of the area covering every monitor."""
    metrics = ctypes.windll.user32.GetSystemMetrics
    return metrics(76), metrics(77), metrics(78), metrics(79)


def grab(bbox):
    """Screenshot in screen pixels, also on a monitor left of or above the main one."""
    left, top, right, bottom = bbox
    main_w = ctypes.windll.user32.GetSystemMetrics(0)
    main_h = ctypes.windll.user32.GetSystemMetrics(1)
    if left >= 0 and top >= 0 and right <= main_w and bottom <= main_h:
        return ImageGrab.grab(bbox=bbox)
    return ImageGrab.grab(bbox=bbox, all_screens=True)


def load_solver():
    _stub_vision_imports()
    path = Path(__file__).with_name("minesweeper AI.py")
    spec = importlib.util.spec_from_file_location("minesweeper_ai", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load solver from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.grids = []
    module.nums = []
    return module


def _stub_vision_imports():
    def missing(name: str) -> bool:
        if name in sys.modules and not hasattr(sys.modules[name], "__file__"):
            return True
        try:
            __import__(name)
            return False
        except ModuleNotFoundError:
            return True

    for name in ("pyautogui", "PIL", "numpy"):
        missing(name)
    if missing("cv2"):
        cv2_mod = types.ModuleType("cv2")
        cv2_mod.__version__ = "4.0.0"
        sys.modules["cv2"] = cv2_mod
    if missing("numpy"):
        numpy_mod = types.ModuleType("numpy")
        numpy_mod.array = lambda *args, **kwargs: None
        sys.modules["numpy"] = numpy_mod
    if missing("pyautogui"):
        gui = types.ModuleType("pyautogui")
        gui.PAUSE = 0
        gui.click = lambda *args, **kwargs: None
        gui.rightClick = lambda *args, **kwargs: None
        gui.moveTo = lambda *args, **kwargs: None
        sys.modules["pyautogui"] = gui
    if missing("PIL"):
        pil = types.ModuleType("PIL")
        pil.__path__ = []
        pil.__package__ = "PIL"
        grabber = types.ModuleType("PIL.ImageGrab")
        grabber.grab = lambda *args, **kwargs: None
        pil.ImageGrab = grabber
        sys.modules["PIL"] = pil
        sys.modules["PIL.ImageGrab"] = grabber


def _at(img, x: int, y: int) -> tuple[int, int, int]:
    value = img[x, y]
    return value[:3]


def _neutral(rgb: tuple[int, int, int]) -> bool:
    return abs(rgb[0] - rgb[1]) < 28 and abs(rgb[1] - rgb[2]) < 28


def _axis_score(pixels, width: int, height: int, vertical: bool) -> list[int]:
    size = width if vertical else height
    score = [0] * size
    if vertical:
        for y in range(0, height, 2):
            for x in range(2, width - 1):
                color = _at(pixels, x, y)
                if _neutral(color) and color[0] < 160 and _at(pixels, x - 2, y)[0] > color[0] + 30:
                    score[x] += 1
    else:
        for x in range(0, width, 2):
            for y in range(2, height - 1):
                color = _at(pixels, x, y)
                if _neutral(color) and color[0] < 160 and _at(pixels, x, y - 2)[0] > color[0] + 30:
                    score[y] += 1
    return score


def _fundamental_period(score: list[int]) -> int | None:
    if len(score) < 24 or max(score) < 8:
        return None
    ranked = []
    limit = min(56, max(12, len(score) // 4))
    for period in range(8, limit):
        samples = range(0, len(score) - period, 2)
        total = sum(score[index] * score[index + period] for index in samples)
        ranked.append((total / max(1, len(list(samples))), period))
    ranked.sort(reverse=True)
    best_score, best_period = ranked[0]
    for score_value, period in sorted(ranked, key=lambda item: item[1]):
        if period >= best_period:
            break
        ratio = best_period / period
        nearest = round(ratio)
        if nearest >= 2 and abs(ratio - nearest) < 0.12 and score_value >= best_score * 0.62:
            return period
    return best_period


def _period_choices(score: list[int]) -> list[int]:
    fundamental = _fundamental_period(score)
    if fundamental is None:
        return []
    limit = min(56, max(12, len(score) // 4))
    best_period = fundamental
    best_score = -1.0
    for period in range(8, limit):
        samples = range(0, len(score) - period, 2)
        total = sum(score[index] * score[index + period] for index in samples)
        value = total / max(1, len(list(samples)))
        if value > best_score:
            best_score = value
            best_period = period
    choices = [fundamental]
    if best_period != fundamental:
        choices.append(best_period)
    return choices


def _peaks(score: list[int]) -> list[int]:
    threshold = max(score) * 0.35
    peaks = []
    for index in range(1, len(score) - 1):
        if score[index] < threshold or score[index] < score[index - 1] or score[index] < score[index + 1]:
            continue
        if peaks and index - peaks[-1] <= 2:
            if score[index] > score[peaks[-1]]:
                peaks[-1] = index
        else:
            peaks.append(index)
    return peaks


def _walk(score: list[int], peaks: list[int], period: int, start: int) -> list[int] | None:
    borders = [start]
    limit = len(score) - 1
    while borders[-1] < len(score) - period:
        low = borders[-1] + int(period * 0.85)
        high = min(limit, borders[-1] + int(period * 1.2))
        window = [index for index in peaks if low <= index <= high]
        nxt = max(window, key=lambda index: score[index]) if window else borders[-1] + period
        if nxt <= borders[-1] or nxt >= limit:
            break
        borders.append(nxt)
    if len(borders) < 4:
        return None
    return borders


def _border_options(score: list[int]) -> list[list[int]]:
    peaks = _peaks(score)
    if len(peaks) < 3:
        return []
    options = []
    seen = set()
    for period in _period_choices(score):
        starts = [peak for peak in peaks if peak <= peaks[0] + period]
        for start in starts[:4]:
            borders = _walk(score, peaks, period, start)
            if not borders:
                continue
            key = (len(borders), borders[0], borders[1] - borders[0])
            if key in seen:
                continue
            seen.add(key)
            options.append(borders)
    return options


def _ink_vote(red: int, green: int, blue: int) -> int:
    """One ink pixel, for the classic palette and its anti-aliased blends.

    1 blue, 2 green, 3 red, 4 navy or purple, 5 maroon or orange, 6 teal.
    Black 7 and gray 8 have no color, so they are counted in _read_cells.
    """
    # Bright blue 1. A navy 4 half-blended into the gray background is also
    # blue-ish, so a 1 must be either saturated or almost free of red.
    if blue >= 140 and blue >= red + 40 and blue >= green + 30 and (blue >= 200 or (red < 60 and blue >= 170)):
        return 1
    # Teal 6: green and blue high and close together, red low.
    if green >= 60 and blue >= 60 and abs(green - blue) < 30 and red + 25 < min(green, blue):
        return 6
    # Green 2: green clearly above both red and blue.
    if green >= 70 and green >= red + 15 and green >= blue + 25 and red < 160:
        return 2
    # Orange 5 (Google style): red high, green mid, blue low.
    if red >= 180 and 90 <= green <= 190 and blue < 90 and green - blue >= 40 and red - green >= 50:
        return 5
    # Red 3: bright red; its blends keep red above 180.
    if red >= 180 and red >= green + 60 and red >= blue + 60:
        return 3
    # Maroon 5: dark red, green and blue low and alike. Blends stay under 180.
    if 90 <= red < 180 and green <= red - 40 and blue <= red - 40 and abs(green - blue) < 30:
        return 5
    # Navy 4.
    if 40 <= blue < 170 and red < 110 and green <= 120 and blue >= green + 15 and blue + 20 >= red:
        return 4
    # Purple 4.
    if red >= 60 and blue >= 60 and green + 25 < min(red, blue) and max(red, blue) < 200:
        return 4
    return 0


def _digit(chroma: list[tuple[int, int, int]]) -> int:
    votes = [0] * 9
    for red, green, blue in chroma:
        vote = _ink_vote(red, green, blue)
        if vote:
            votes[vote] += 1
    best = max(range(1, 9), key=lambda number: votes[number])
    if votes[best] < 3:
        return -1
    return best


def _demote_false_zeros(cells, cols: int, rows: int):
    """A real blank has every neighbor opened. A blank beside a closed cell is a misread."""
    cleaned = list(cells)
    for row in range(rows):
        for col in range(cols):
            index = row * cols + col
            if cleaned[index] != ("open", 0):
                continue
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                other_row = row + dr
                other_col = col + dc
                if not (0 <= other_row < rows and 0 <= other_col < cols):
                    continue
                if cleaned[other_row * cols + other_col][0] == "closed":
                    cleaned[index] = ("closed", -1)
                    break
    return cleaned


def _read_cells(pixels, x_borders: list[int], y_borders: list[int]) -> tuple[list[tuple[str, int]], int]:
    """Read every cell. The second value is how many cells have a raised 3D edge."""
    cells: list[tuple[str, int]] = []
    raised = 0
    for row in range(len(y_borders) - 1):
        y0, y1 = y_borders[row] + 1, y_borders[row + 1]
        for col in range(len(x_borders) - 1):
            x0, x1 = x_borders[col] + 1, x_borders[col + 1]
            if x1 - x0 < 4 or y1 - y0 < 4:
                cells.append(("closed", -1))
                continue
            width_px = x1 - x0
            height_px = y1 - y0
            samples = width_px * height_px
            # A flag is a black star in the middle. Keep a wide center so a small
            # star is not missed, and keep the outer edge out so a neighbor's star
            # does not count.
            margin_x = max(1, width_px // 6)
            margin_y = max(1, height_px // 6)
            cx0 = x0 + margin_x
            cx1 = x1 - margin_x
            cy0 = y0 + margin_y
            cy1 = y1 - margin_y
            corner = max(2, min(width_px, height_px) // 3)
            center_black = 0
            edge_black = 0
            center_gray = 0
            chroma = []
            reds = 0
            bright = 0
            tl_sum = tl_count = 0
            br_sum = br_count = 0
            for y in range(y0, y1):
                for x in range(x0, x1):
                    red, green, blue = _at(pixels, x, y)
                    if max(red, green, blue) < 80 and max(red, green, blue) - min(red, green, blue) < 28:
                        if cx0 <= x < cx1 and cy0 <= y < cy1:
                            center_black += 1
                        else:
                            edge_black += 1
                    elif max(red, green, blue) - min(red, green, blue) > 55:
                        chroma.append((red, green, blue))
                    elif 90 <= max(red, green, blue) <= 150 and max(red, green, blue) - min(red, green, blue) < 28:
                        # Mid gray: the ink of an 8. Only the center counts, so the
                        # shadow edge of a closed cell is left out.
                        if cx0 <= x < cx1 and cy0 <= y < cy1:
                            center_gray += 1
                    if red > 160 and red > green + 50 and red > blue + 50:
                        reds += 1
                    if red > 225 and abs(red - green) < 20 and abs(green - blue) < 20:
                        bright += 1
                    shade = red + green + blue
                    if x < x0 + corner and y < y0 + corner:
                        tl_sum += shade
                        tl_count += 1
                    if x >= x1 - corner and y >= y1 - corner:
                        br_sum += shade
                        br_count += 1
            # Raised cells are bright at the top-left and dark at the bottom-right,
            # even when the highlight is gray rather than pure white.
            bevel = (tl_sum / tl_count) - (br_sum / br_count) if tl_count and br_count else 0
            if bevel >= 30:
                raised += 1
            digit = _digit(chroma) if len(chroma) >= 4 else 0
            flat = bevel < 15
            if reds > samples * 0.62:
                cells.append(("dead", -1))
            elif center_black >= 3 and center_black > edge_black and (reds >= 2 or not flat):
                # A flag is a black base on a raised cell, with or without a red
                # cloth above it. Colored digits have no black ink, so this is
                # decided before the digit.
                cells.append(("flag", -1))
            elif reds >= 3 and center_black + edge_black >= 2 and bevel >= 10:
                # A red cloth on a raised cell with a thin black pole. A red 3 sits
                # on a flat cell and has no black pixels at all.
                cells.append(("flag", -1))
            elif center_black >= 3 and center_black > edge_black and flat and reds < 2 and digit <= 0:
                # Black ink on a flat open cell: a 7.
                cells.append(("open", 7))
            elif digit > 0 and bright <= samples * 0.45:
                cells.append(("open", digit))
            elif center_gray >= 3 and flat and center_black == 0 and digit == 0:
                # Gray ink on a flat open cell with no colored ink: an 8.
                cells.append(("open", 8))
            elif bevel >= 30:
                cells.append(("closed", -1))
            else:
                cells.append(("open", 0))
    return cells, raised


def parse_board(
    img,
    x_borders: list[int] | None = None,
    y_borders: list[int] | None = None,
) -> tuple[list[int], list[int], list[tuple[str, int]]] | None:
    """Find the real cell grid, then read each cell. Returns None if no grid is visible."""
    pixels = img.load()
    width, height = img.size
    if x_borders is not None and y_borders is not None:
        cells, _raised = _read_cells(pixels, x_borders, y_borders)
        cols = len(x_borders) - 1
        rows = len(y_borders) - 1
        return x_borders, y_borders, _demote_false_zeros(cells, cols, rows)

    x_options = _border_options(_axis_score(pixels, width, height, True))
    y_options = _border_options(_axis_score(pixels, width, height, False))
    best = None
    best_key = (-1, -1)
    for x_choice in x_options:
        for y_choice in y_options:
            cells, raised = _read_cells(pixels, x_choice, y_choice)
            # A correct grid lines the 3D edges up, so far more cells look raised.
            key = (raised, len(cells))
            if key > best_key:
                best_key = key
                best = (x_choice, y_choice, cells)
    if best is None:
        return None
    x_borders, y_borders, cells = best
    cols = len(x_borders) - 1
    rows = len(y_borders) - 1
    return x_borders, y_borders, _demote_false_zeros(cells, cols, rows)


def select_region() -> tuple[int, int, int, int] | None:
    root = tk.Tk()
    # Cover every monitor, so the board can be boxed on either screen.
    vx, vy, vw, vh = virtual_screen()
    root.overrideredirect(True)
    root.geometry(f"{vw}x{vh}+{vx}+{vy}")
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.25)
    root.configure(bg="black")
    canvas = tk.Canvas(root, bg="black", highlightthickness=0, cursor="cross")
    canvas.pack(fill="both", expand=True)
    root.focus_force()
    main_w = ctypes.windll.user32.GetSystemMetrics(0)
    canvas.create_text(
        main_w // 2 - vx,
        40 - vy,
        text="Kéo sát quanh các ô. Tool tự đếm lưới. Esc để hủy.",
        fill="white",
        font=("Segoe UI", 16),
    )
    state = {"x0": 0, "y0": 0, "rect": None, "result": None}

    def press(event):
        state["x0"] = event.x_root
        state["y0"] = event.y_root
        if state["rect"] is not None:
            canvas.delete(state["rect"])
        state["rect"] = canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="#00ff66", width=2)

    def drag(event):
        if state["rect"] is None:
            return
        canvas.coords(
            state["rect"],
            state["x0"] - root.winfo_rootx(),
            state["y0"] - root.winfo_rooty(),
            event.x,
            event.y,
        )

    def release(event):
        x0, y0 = state["x0"], state["y0"]
        x1, y1 = event.x_root, event.y_root
        left, right = sorted((x0, x1))
        top, bottom = sorted((y0, y1))
        if right - left > 40 and bottom - top > 40:
            state["result"] = (left, top, right - left, bottom - top)
        root.destroy()

    canvas.bind("<ButtonPress-1>", press)
    canvas.bind("<B1-Motion>", drag)
    canvas.bind("<ButtonRelease-1>", release)
    root.bind("<Escape>", lambda _event: root.destroy())
    root.mainloop()
    return state["result"]


def make_clickthrough(window):
    window.update_idletasks()
    hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
    style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
    ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x00080000 | 0x00000020)


def hide_from_capture(window) -> bool:
    """Ask Windows to leave this window out of screenshots (Windows 10 2004+).

    When this works the overlay stays on screen while the board is read, so
    the marks never blink. Returns False on older Windows.
    """
    window.update_idletasks()
    hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
    try:
        return bool(ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, 0x00000011))
    except Exception:
        return False


PROBE_COLOR = (0, 255, 102)


def capture_ignores(window, canvas, region) -> bool:
    """Draw a probe on the overlay and check that a screenshot does not see it."""
    _x, _y, width, height = region
    size = max(6, min(24, width // 10, height // 10))
    probe = canvas.create_rectangle(0, 0, size, size, fill="#00ff66", outline="")
    window.deiconify()
    window.lift()
    window.update()
    time.sleep(0.12)
    try:
        left = window.winfo_rootx()
        top = window.winfo_rooty()
        shot = grab((left, top, left + size, top + size))
        pixels = shot.load()
        for py in range(shot.height):
            for px in range(shot.width):
                red, green, blue = pixels[px, py][:3]
                if abs(red - PROBE_COLOR[0]) < 40 and abs(green - PROBE_COLOR[1]) < 40 and abs(blue - PROBE_COLOR[2]) < 40:
                    return False
        return True
    except Exception:
        return False
    finally:
        canvas.delete(probe)
        window.update()


def satisfied_numbers(grids) -> list[int]:
    """Open numbers whose flags already match, with a closed neighbor still to open.

    Clicking that number is the chord: the game opens every remaining neighbor.
    Only flags already visible on the board count, so a mine is never chorded
    open before its flag exists.
    """
    targets = []
    for cell in grids:
        if not cell.flipped or cell.num <= 0:
            continue
        flags = 0
        closed = False
        for index in cell.adj_grids:
            other = grids[index]
            if other.flagged and not other.flipped:
                flags += 1
            elif not other.flipped:
                closed = True
        if closed and flags == cell.num:
            targets.append(cell.index)
    return targets


def render(ai, mines: set[int] | None = None) -> str:
    cols = ai.Grid.columns
    rows = ai.Grid.rows
    mines = mines or set()
    lines = []
    for row in range(rows):
        chars = []
        for col in range(cols):
            cell = ai.grids[row * cols + col]
            if cell.flagged and not cell.flipped:
                chars.append("F")
            elif not cell.flipped:
                chars.append("*" if cell.index in mines else "#")
            elif cell.num <= 0:
                chars.append("." if cell.num == 0 else "?")
            else:
                chars.append(str(cell.num))
        lines.append("".join(chars))
    return "\n".join(lines)


TANK_LIMIT = 22  # largest frontier group that is enumerated exhaustively
TANK_BUDGET = 0.08  # seconds allowed for enumeration per reading


def _constraints(grids, mines: set[int], safe: set[int]) -> list[tuple[int, int, frozenset[int]]]:
    """(cell index, mines still needed, hidden neighbors) for every readable number."""
    out = []
    for cell in grids:
        if not cell.flipped or cell.num <= 0:
            continue
        hidden = []
        need = cell.num
        unreadable = False
        for index in cell.adj_grids:
            other = grids[index]
            if other.flipped:
                if other.num < 0:
                    unreadable = True
                    break
                continue
            if other.flagged or index in mines:
                need -= 1
            elif index not in safe:
                hidden.append(index)
        if unreadable or need < 0 or not hidden:
            continue
        out.append((cell.index, need, frozenset(hidden)))
    return out


def _tank(groups: list[list[int]], cons: list[tuple[int, int, frozenset[int]]], mines: set[int], safe: set[int], deadline: float) -> bool:
    """Enumerate every mine layout of a small frontier. Cells with one answer are certain."""
    changed = False
    for group in groups:
        if len(group) > TANK_LIMIT or time.perf_counter() > deadline:
            continue
        member = set(group)
        local = [(need, hidden) for _index, need, hidden in cons if hidden & member]
        touching = {cell: [k for k, (_need, hidden) in enumerate(local) if cell in hidden] for cell in group}
        order = sorted(group, key=lambda cell: -len(touching[cell]))
        placed = [0] * len(local)
        left = [len(hidden) for _need, hidden in local]
        count = [0] * len(order)
        total = 0
        state = {}

        def search(pos: int) -> bool:
            nonlocal total
            if time.perf_counter() > deadline:
                return False
            if pos == len(order):
                total += 1
                for i, cell in enumerate(order):
                    count[i] += state[cell]
                return True
            cell = order[pos]
            for value in (0, 1):
                ok = True
                for k in touching[cell]:
                    placed[k] += value
                    left[k] -= 1
                    need = local[k][0]
                    if placed[k] > need or placed[k] + left[k] < need:
                        ok = False
                if ok:
                    state[cell] = value
                    if not search(pos + 1):
                        return False
                for k in touching[cell]:
                    placed[k] -= value
                    left[k] += 1
            return True

        if not search(0) or total == 0:
            continue
        for i, cell in enumerate(order):
            if count[i] == total and cell not in mines:
                mines.add(cell)
                changed = True
            elif count[i] == 0 and cell not in safe:
                safe.add(cell)
                changed = True
    return changed


def suggest(ai, known_mines: set[int] | None = None) -> tuple[str, list[tuple[str, int]], set[int]]:
    """Find every cell that is certainly a mine or certainly safe.

    Mines found earlier are used like flags, so one mine unlocks the next, and
    the whole chain is marked in one pass instead of one number at a time.
    """
    grids = ai.grids
    opened = [cell for cell in grids if cell.flipped]
    if any(cell.num == -2 for cell in grids):
        return "lose", [], set()
    if opened and not any(not cell.flipped and not cell.flagged for cell in grids):
        return "win", [], set()
    if not opened:
        return "wait", [], set()

    mines: set[int] = {
        index for index in (known_mines or set())
        if index < len(grids) and not grids[index].flipped and not grids[index].flagged
    }
    safe: set[int] = set()
    deadline = time.perf_counter() + TANK_BUDGET

    while True:
        cons = _constraints(grids, mines, safe)
        changed = False
        # Rule 1: a number with as many hidden cells as mines left, or none left.
        for _index, need, hidden in cons:
            if need == 0:
                safe |= hidden
                changed = True
            elif need == len(hidden):
                mines |= hidden
                changed = True
        if changed:
            continue
        # Rule 2: subset elimination between two numbers that share hidden cells.
        by_cell: dict[int, list[int]] = {}
        for k, (_index, _need, hidden) in enumerate(cons):
            for cell in hidden:
                by_cell.setdefault(cell, []).append(k)
        for k, (_index, need_a, hidden_a) in enumerate(cons):
            partners = {j for cell in hidden_a for j in by_cell[cell] if j != k}
            for j in partners:
                _other, need_b, hidden_b = cons[j]
                if not hidden_b < hidden_a:
                    continue
                unique = hidden_a - hidden_b
                diff = need_a - need_b
                if diff == len(unique):
                    mines |= unique
                    changed = True
                elif diff == 0:
                    safe |= unique
                    changed = True
        if changed:
            continue
        # Rule 3: enumerate small frontier groups exhaustively.
        groups: list[list[int]] = []
        seen: set[int] = set()
        for cell in by_cell:
            if cell in seen:
                continue
            stack = [cell]
            group = []
            seen.add(cell)
            while stack:
                current = stack.pop()
                group.append(current)
                for j in by_cell[current]:
                    for other in cons[j][2]:
                        if other not in seen:
                            seen.add(other)
                            stack.append(other)
            groups.append(group)
        groups.sort(key=len)
        if _tank(groups, cons, mines, safe, deadline):
            continue
        break

    actions = [("flag", index) for index in sorted(mines)]
    actions += [("open", index) for index in sorted(safe - mines)]
    if actions:
        return "play", actions, mines
    return "wait", [], mines


class Watcher:
    def __init__(self, region, mine_override: int | None):
        self.region = region
        self.mine_override = mine_override
        self.mine_total = mine_override if mine_override is not None else 0
        self.rows = 0
        self.cols = 0
        self.x_borders: list[int] | None = None
        self.y_borders: list[int] | None = None
        self.pending: tuple | None = None
        self.stable: tuple | None = None
        self.ai = load_solver()
        self.ai.grids = []
        self.running = True
        x, y, width, height = region

        self.panel = tk.Tk()
        self.panel.title("Minesweeper screen reader")
        self.overlay = tk.Toplevel(self.panel)
        self.overlay.overrideredirect(True)
        self.overlay.attributes("-topmost", True)
        self.overlay.attributes("-transparentcolor", "magenta")
        self.overlay.geometry(f"{width}x{height}+{x}+{y}")
        self.overlay.configure(bg="magenta")
        self.canvas = tk.Canvas(self.overlay, bg="magenta", highlightthickness=0, width=width, height=height)
        self.canvas.pack()
        self.overlay.update_idletasks()
        make_clickthrough(self.overlay)
        # If Windows can leave the overlay out of screenshots, it is never hidden
        # between readings and the marks stay still. Otherwise fall back to a
        # quick hide-read-show on a slower clock.
        self.quiet = hide_from_capture(self.overlay) and capture_ignores(self.overlay, self.canvas, region)
        self.interval = 180 if self.quiet else 400
        self.last_marks: tuple | None = None
        # Auto click starts off. The button or the T key turns it on and off.
        self.auto = False
        self.t_down = False
        self.last_reading: tuple | None = None
        self.changed_at = time.perf_counter()
        self.acted_at = 0.0
        self.acted_board: tuple | None = None
        self.flag_tries: dict[int, int] = {}
        if pyautogui is not None:
            pyautogui.FAILSAFE = True
            pyautogui.PAUSE = 0
        self.panel.attributes("-topmost", True)
        self.panel.geometry(self._panel_geometry(520, 380))
        mode = "Overlay không chớp." if self.quiet else "Windows cũ: overlay phải ẩn khi đọc, sẽ hơi chớp."
        self.status = tk.StringVar(value=f"Tool tô ô chắc. Bấm nút hoặc phím T để bật tự động. {mode}")
        self.auto_text = tk.StringVar()
        tk.Label(self.panel, textvariable=self.auto_text, anchor="w", font=("Segoe UI", 10, "bold")).pack(fill="x", padx=8, pady=(8, 0))
        tk.Label(self.panel, textvariable=self.status, anchor="w", justify="left", wraplength=500).pack(fill="x", padx=8)
        self.board = tk.Text(self.panel, height=16, width=62, font=("Consolas", 8), wrap="none")
        self.board.pack(fill="both", expand=True, padx=8, pady=8)
        # Read only, so pressing T while the panel has focus does not type into it.
        self.board.bind("<Key>", lambda _event: "break")
        buttons = tk.Frame(self.panel)
        buttons.pack(pady=(0, 8))
        tk.Button(buttons, text="Đọc lại lưới", command=self.reset_grid).pack(side="left", padx=4)
        self.auto_button = tk.Button(buttons, command=self.toggle_auto, width=18)
        self.auto_button.pack(side="left", padx=4)
        tk.Button(buttons, text="Dừng", command=self.stop).pack(side="left", padx=4)
        self._show_auto_state()
        self.panel.protocol("WM_DELETE_WINDOW", self.stop)
        self.panel.bind("<Escape>", lambda _event: self.stop())
        self.panel.after(200, self.tick)
        self.panel.after(40, self.poll_keys)

    def _panel_geometry(self, panel_w: int, panel_h: int) -> str:
        """Put the panel beside the board, so an auto click never lands on it."""
        x, y, width, height = self.region
        vx, vy, vw, vh = virtual_screen()
        gap = 16
        spots = (
            (x + width + gap, y),
            (x - panel_w - gap, y),
            (x, y + height + gap + 40),
            (x, y - panel_h - gap - 40),
            (vx + 20, vy + 20),
        )
        for px, py in spots:
            inside = vx <= px and vy <= py and px + panel_w <= vx + vw and py + panel_h + 40 <= vy + vh
            overlap = px < x + width and x < px + panel_w and py < y + height and y < py + panel_h + 40
            if inside and not overlap:
                return f"{panel_w}x{panel_h}+{px}+{py}"
        return f"{panel_w}x{panel_h}+{vx + 20}+{vy + 20}"

    def _show_auto_state(self):
        if self.auto:
            self.auto_text.set("TỰ ĐỘNG: BẬT  (bấm T để tắt)")
            self.auto_button.configure(text="Tắt tự động (T)")
        else:
            self.auto_text.set("TỰ ĐỘNG: TẮT  (bấm T để bật)")
            self.auto_button.configure(text="Bật tự động (T)")

    def poll_keys(self):
        """Watch the T key everywhere, also while the browser has focus."""
        if not self.running:
            return
        state = ctypes.windll.user32.GetAsyncKeyState
        down = bool(state(0x54) & 0x8000)
        # Ctrl, Alt and the Windows keys: Ctrl+T opens a browser tab, so skip it.
        modifier = any(state(key) & 0x8000 for key in (0x11, 0x12, 0x5B, 0x5C))
        if down and not self.t_down and not modifier:
            self.toggle_auto()
        self.t_down = down
        self.panel.after(40, self.poll_keys)

    def _t_pressed(self) -> bool:
        """True when T is being pressed now, used to stop in the middle of a click run."""
        return bool(ctypes.windll.user32.GetAsyncKeyState(0x54) & 0x8000)

    def reset_grid(self):
        self.x_borders = None
        self.y_borders = None
        self.pending = None
        self.stable = None
        self.last_marks = None
        self.last_reading = None
        self.acted_board = None
        self.flag_tries.clear()
        self.status.set("Đang tìm lại lưới ô")

    def toggle_auto(self):
        if pyautogui is None:
            self.status.set("Chưa cài pyautogui. Chạy: pip install pyautogui")
            return
        self.auto = not self.auto
        self.acted_board = None
        self.acted_at = 0.0
        self.flag_tries.clear()
        self._show_auto_state()

    def stop(self):
        self.running = False
        try:
            self.panel.destroy()
        except tk.TclError:
            pass

    def tick(self):
        if not self.running:
            return
        try:
            self._read_and_mark()
        except Exception as error:
            self.status.set(f"Lỗi đọc màn hình: {error}")
        if self.running:
            self.panel.after(self.interval, self.tick)

    def _fit_model(self, rows: int, cols: int):
        if self.ai.grids and self.ai.Grid.rows == rows and self.ai.Grid.columns == cols:
            return
        self.rows = rows
        self.cols = cols
        self.ai.Grid.rows = rows
        self.ai.Grid.columns = cols
        self.ai.grids = [self.ai.Grid(0, 0, row * cols + col) for row in range(rows) for col in range(cols)]
        matched = next((mines for known_rows, known_cols, mines in DIFFICULTIES.values() if known_rows == rows and known_cols == cols), None)
        if self.mine_override is not None:
            self.mine_total = self.mine_override
        elif matched is not None:
            self.mine_total = matched
        else:
            # Unknown custom board. A high cap keeps the local rules from inventing mines.
            self.mine_total = rows * cols

    def _show_overlay(self):
        x, y, width, height = self.region
        if self.overlay.state() == "withdrawn":
            self.overlay.deiconify()
            self.overlay.geometry(f"{width}x{height}+{x}+{y}")
        self.overlay.lift()
        self.overlay.update_idletasks()

    def _read_and_mark(self):
        if not self.quiet:
            self.overlay.withdraw()
            self.panel.update()
            time.sleep(0.04)
        x, y, width, height = self.region
        image = grab((x, y, x + width, y + height))
        parsed = parse_board(image, self.x_borders, self.y_borders)
        if parsed is None:
            self.status.set("Chưa thấy lưới. Khoanh sát các ô, rồi bấm Đọc lại lưới.")
            self._show_overlay()
            return
        x_borders, y_borders, cells = parsed
        rows = len(y_borders) - 1
        cols = len(x_borders) - 1
        if rows < 4 or cols < 4 or rows * cols != len(cells):
            self.status.set("Lưới đọc được quá nhỏ. Khoanh lại đúng phần ô.")
            self._show_overlay()
            return
        if self.x_borders is None or self.y_borders is None:
            self.x_borders = x_borders
            self.y_borders = y_borders
        if self.stable is not None and len(self.stable) != len(cells):
            self.stable = None
            self.pending = None
        reading = tuple(cells)
        confirmed = reading == self.pending
        if reading != self.last_reading:
            self.last_reading = reading
            self.changed_at = time.perf_counter()
        if reading == self.pending:
            self.stable = reading
        else:
            self.pending = reading
            if self.stable is None:
                self.stable = reading
        shown = self.stable or reading
        self._fit_model(rows, cols)
        saw_dead = False
        for index, (kind, number) in enumerate(shown):
            cell = self.ai.grids[index]
            cell.prob = 0
            if kind == "dead":
                saw_dead = True
                cell.flipped = True
                cell.flagged = False
                cell.num = -2
            elif kind == "flag":
                cell.flipped = False
                cell.flagged = True
                cell.num = -1
            elif kind == "open":
                cell.flipped = True
                cell.flagged = False
                cell.num = number
            else:
                cell.flipped = False
                cell.flagged = False
                cell.num = -1
        flagged = sum(cell.flagged for cell in self.ai.grids)
        self.ai.Grid.mines_remaining = max(self.mine_total - flagged, 0)
        self.ai.nums = [
            cell.index
            for cell in self.ai.grids
            if cell.flipped and cell.num > 0 and cell.adj_unflagged()
        ]
        if saw_dead:
            status, actions, mines = "lose", [], set()
        else:
            # Every mine is re-derived from the numbers on each reading, so a
            # mine stays red for as long as it is provable, and a misread never sticks.
            status, actions, mines = suggest(self.ai)
        picture = render(self.ai, mines)

        # Show the overlay first, then measure where Windows really put it. Any
        # difference from the boxed region is added to every mark, so the marks
        # land on the same pixels the screenshot came from.
        self._show_overlay()
        shift_x = x - self.overlay.winfo_rootx()
        shift_y = y - self.overlay.winfo_rooty()
        scale_x = width / image.width
        scale_y = height / image.height
        # Redraw only when something changed, so steady marks never blink.
        marks = (tuple(actions), shift_x, shift_y, tuple(x_borders), tuple(y_borders))
        if marks != self.last_marks:
            self.last_marks = marks
            self._draw_marks(actions, x_borders, y_borders, scale_x, scale_y, shift_x, shift_y)
        opens = sum(1 for kind, _index in actions if kind == "open")
        flags_to_place = sum(1 for kind, _index in actions if kind == "flag")
        if status == "play":
            advice = f"Chắc chắn: {flags_to_place} mìn (đỏ), {opens} ô an toàn (xanh)."
        elif status == "wait":
            advice = "Chưa có nước chắc. Bạn mở thêm một ô, tool tính tiếp."
        elif status == "win":
            advice = "Hết bàn an toàn."
        else:
            advice = "Đã nổ mìn."
        self.status.set(f"{cols} cột × {rows} hàng. {advice}")
        if self.board.get("1.0", "end-1c") != picture:
            self.board.delete("1.0", "end")
            self.board.insert("end", picture)
        self._auto_play(status, actions, confirmed, x_borders, y_borders, scale_x, scale_y, shown)

    def _cell_point(self, index, x_borders, y_borders, scale_x, scale_y) -> tuple[int, int]:
        cell = self.ai.grids[index]
        center_x = (x_borders[cell.column] + 1 + x_borders[cell.column + 1]) / 2
        center_y = (y_borders[cell.row] + 1 + y_borders[cell.row + 1]) / 2
        origin_x, origin_y, _width, _height = self.region
        return round(origin_x + center_x * scale_x), round(origin_y + center_y * scale_y)

    def _park_mouse(self):
        """Leave the cursor off the board so a hover highlight is not read as a cell."""
        origin_x, origin_y, width, height = self.region
        screen_w = self.panel.winfo_screenwidth()
        screen_h = self.panel.winfo_screenheight()
        vx, vy, vw, vh = virtual_screen()
        candidates = (
            (origin_x + width + 24, origin_y + 12),
            (origin_x - 24, origin_y + 12),
            (origin_x + 12, origin_y + height + 24),
            (origin_x + 12, origin_y - 24),
        )
        for px, py in candidates:
            on_board = origin_x <= px < origin_x + width and origin_y <= py < origin_y + height
            on_screen = vx + 12 <= px <= vx + vw - 12 and vy + 12 <= py <= vy + vh - 12
            if on_screen and not on_board:
                pyautogui.moveTo(px, py)
                return
        pyautogui.moveTo(max(12, screen_w // 2), 12)

    def _click_cell(self, index, button, x_borders, y_borders, scale_x, scale_y):
        """Move, let the page see the hover, then press and release.

        A browser game reads the cell under the pointer. Moving and clicking in
        the same instant can hit the cell the pointer was on a moment earlier.
        """
        sx, sy = self._cell_point(index, x_borders, y_borders, scale_x, scale_y)
        pyautogui.moveTo(sx, sy)
        time.sleep(0.03)
        pyautogui.mouseDown(sx, sy, button=button)
        time.sleep(0.03)
        pyautogui.mouseUp(sx, sy, button=button)
        time.sleep(0.04)

    def _auto_play(self, status, actions, confirmed, x_borders, y_borders, scale_x, scale_y, shown):
        """One step per settled board, in this order:

        1. click a number that already has enough flags, so the game opens the rest;
        2. right-click the red cells to flag them;
        3. left-click the green cells.

        After each step the board is read again before the next step.
        """
        if not self.auto or not self.running or pyautogui is None or not confirmed or status in ("lose", "win"):
            return
        now = time.perf_counter()
        # Wait until the board has stopped changing, so an opening or flag
        # animation is not read as the real board.
        if now - self.changed_at < 0.35 or now - self.acted_at < 0.5:
            return
        # The same board after a step means the step did nothing. Try again only
        # after a longer pause.
        if shown == self.acted_board and now - self.acted_at < 2.0:
            return

        grids = self.ai.grids
        safe = {index for kind, index in actions if kind == "open"}
        red = [index for kind, index in actions if kind == "flag"]
        # Chord only when the solver agrees every hidden neighbor is safe. A
        # misread flag then cannot make the game open a mine.
        chords = []
        for index in satisfied_numbers(grids):
            hidden = [n for n in grids[index].adj_grids if not grids[n].flipped and not grids[n].flagged]
            if hidden and all(n in safe for n in hidden):
                chords.append(index)
        # A right-click on a flag removes it, so each cell gets at most two tries.
        flags = [index for index in red if self.flag_tries.get(index, 0) < 2]
        opens = [index for index in sorted(safe) if not grids[index].flagged]

        if chords:
            step, button, cells = "Click số đã đủ cờ", "left", chords
        elif flags:
            step, button, cells = "Cắm cờ ô đỏ", "right", flags
        elif opens:
            step, button, cells = "Mở ô xanh", "left", opens
        else:
            return

        self.acted_board = shown
        done = 0
        try:
            for index in cells:
                if not self.auto or self._t_pressed():
                    break
                if button == "right":
                    self.flag_tries[index] = self.flag_tries.get(index, 0) + 1
                self._click_cell(index, button, x_borders, y_borders, scale_x, scale_y)
                done += 1
        except pyautogui.FailSafeException:
            self.auto = False
            self._show_auto_state()
            self.status.set("Đã dừng tự động: chuột chạm góc màn hình.")
            return
        finally:
            self.acted_at = time.perf_counter()
            if done:
                self._park_mouse()
        self.status.set(f"{step}: {done} ô.")

    def _draw_marks(self, actions, x_borders, y_borders, scale_x, scale_y, shift_x, shift_y):
        self.canvas.delete("all")
        for kind, index in actions:
            cell = self.ai.grids[index]
            # Cell pixels run from just after one groove to the next groove.
            left = (x_borders[cell.column] + 1) * scale_x + shift_x
            right = x_borders[cell.column + 1] * scale_x + shift_x
            top = (y_borders[cell.row] + 1) * scale_y + shift_y
            bottom = y_borders[cell.row + 1] * scale_y + shift_y
            color = {"open": "#00e676", "flag": "#ff1744", "guess": "#ffea00"}[kind]
            inset = max(1, min(right - left, bottom - top) * 0.12)
            self.canvas.create_rectangle(
                left + inset, top + inset, right - inset, bottom - inset, outline=color, width=2
            )
            cx = (left + right) / 2
            cy = (top + bottom) / 2
            radius = max(2, min(right - left, bottom - top) * 0.16)
            self.canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, fill=color, outline="")


def main():
    enable_dpi()
    parser = argparse.ArgumentParser(description="Read a minesweeper board from the screen")
    parser.add_argument(
        "--difficulty",
        choices=tuple(DIFFICULTIES),
        help="Không cần chọn. Hàng và cột được đếm từ màn hình.",
    )
    parser.add_argument("--mines", type=int, help="Tổng số mìn, nếu bàn không phải Beginner, Intermediate hoặc Expert")
    args = parser.parse_args()
    mines = args.mines
    print("Mở game bằng trình duyệt bình thường, rồi khoanh sát các ô.")
    print("Tự động tắt sẵn. Bấm nút 'Bật tự động (T)' hoặc phím T để bật/tắt.")
    print("Khi bật: click số đã đủ cờ, cắm cờ ô đỏ, rồi mở ô xanh.")
    print("Dừng khẩn cấp: bấm T, hoặc đưa chuột vào góc màn hình chính.")
    region = select_region()
    if region is None:
        print("Đã hủy.")
        return
    watcher = Watcher(region, mines)
    watcher.panel.mainloop()


if __name__ == "__main__":
    main()
