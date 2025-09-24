import json
import os
from typing import Iterable, List, Optional, Tuple, Union


# Datei, in der benutzerdefinierte Level gespeichert werden.
DEFAULT_LEVEL_FILE = "custom_level.json"

# Kontrolliert die Höhe der ersten Plattform im Standardlevel.
FIRST_PLATFORM_IS_LOW = True  # 1 Tile Luft -> nur geduckt passierbar


def make_default_level() -> List[str]:
    """Erzeugt das ursprüngliche Level aus app.py als Fallback."""

    width, height = 180, 14
    grid = [[" " for _ in range(width)] for _ in range(height)]
    ground_y = height - 1

    for x in range(width):
        grid[ground_y][x] = "X"

    # niedrige Plattform (nur geduckt)
    y1 = ground_y - 2 if FIRST_PLATFORM_IS_LOW else ground_y - 3
    for x in range(6, 14):
        grid[y1][x] = "="
    grid[y1 - 1][10] = "G"
    grid[y1 - 1][7] = "M"

    # zweite, höher
    y2 = ground_y - 4
    for x in range(18, 28):
        grid[y2][x] = "="
    grid[y2 - 1][22] = "G"
    grid[y2 - 2][24] = "M"

    # kleiner Abgrund
    for x in range(34, 37):
        grid[ground_y][x] = " "

    # Stacheln + Coins
    grid[ground_y - 1][42] = "^"
    for x in range(44, 50):
        grid[ground_y - 4][x] = "="
        grid[ground_y - 5][x] = "C"

    for x in range(52, 56):
        grid[ground_y - 3][x] = "="
    for x in range(58, 62):
        grid[ground_y - 5][x] = "="
        grid[ground_y - 6][x] = "C"

    for x in range(68, 72):
        grid[ground_y - 2][x] = "="
    for x in range(76, 80):
        grid[ground_y - 3][x] = "="
    grid[ground_y - 1][78] = "G"

    # Dash-Kern
    for x in range(94, 102):
        grid[ground_y - 2][x] = "="
    grid[ground_y - 3][98] = "D"

    # Gate-Korridor
    for x in range(122, 132):
        grid[ground_y - 3][x] = "="
    for x in range(118, 122):
        grid[ground_y - 1][x] = "="
    gx = 128
    grid[ground_y - 1][gx] = "|"
    grid[ground_y - 2][gx] = "|"
    for x in range(130, 136):
        grid[ground_y - 2][x] = "="
        grid[ground_y - 3][x] = "C"
    grid[ground_y - 3][124] = "M"

    # breite Lücke
    for x in range(144, 152):
        grid[ground_y][x] = " "
    for x in range(138, 142):
        grid[ground_y - 1][x] = "="
    for x in range(152, 158):
        grid[ground_y - 1][x] = "="
    for x in range(154, 157):
        grid[ground_y - 3][x] = "C"

    grid[ground_y - 1][160] = "^"
    grid[ground_y - 1][161] = "^"
    for x in range(164, 169):
        grid[ground_y - 4][x] = "="
    for x in range(165, 169):
        grid[ground_y - 5][x] = "C"

    grid[ground_y - 4][172] = "F"
    for y in range(ground_y - 3, ground_y + 1):
        grid[y][172] = "X"

    return ["".join(row) for row in grid]


def _normalise_rows(rows: Iterable[str]) -> Optional[List[str]]:
    rows = [str(r) for r in rows]
    if not rows:
        return None

    width = max(len(row) for row in rows)
    if width == 0:
        return None

    return [row.ljust(width) for row in rows]


def _load_level_file(path: str) -> Optional[List[str]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            if path.lower().endswith(".json"):
                data = json.load(f)
            else:
                data = f.read()
    except (OSError, json.JSONDecodeError):
        return None

    if isinstance(data, dict):
        rows = data.get("tiles") or data.get("level") or data.get("rows")
    elif isinstance(data, list):
        rows = data
    elif isinstance(data, str):
        rows = data.splitlines()
    else:
        rows = None

    if rows is None:
        return None

    return _normalise_rows(rows)


def load_level(
    path: Optional[str] = None, *, return_source: bool = False
) -> Union[List[str], Tuple[List[str], Optional[str]]]:
    """Lädt ein Level aus Datei oder liefert das Standardlevel.

    Die Reihenfolge der Kandidaten lautet:
      1. Expliziter Pfad (`path` Argument)
      2. Umgebungsvariable `PLATFORMER_LEVEL_FILE`
      3. DEFAULT_LEVEL_FILE
      4. Standardlevel aus dem Code
    """

    candidates = []
    if path:
        candidates.append(path)

    env_path = os.environ.get("PLATFORMER_LEVEL_FILE")
    if env_path:
        candidates.append(env_path)

    if DEFAULT_LEVEL_FILE not in candidates:
        candidates.append(DEFAULT_LEVEL_FILE)

    for candidate in candidates:
        level = _load_level_file(candidate)
        if level:
            return (level, candidate) if return_source else level

    default = make_default_level()
    return (default, None) if return_source else default


def save_level(level: Iterable[Iterable[str]], path: str = DEFAULT_LEVEL_FILE) -> None:
    """Speichert ein Level als JSON-Datei."""

    rows = ["".join(row) if not isinstance(row, str) else row for row in level]
    rows = _normalise_rows(rows) or make_default_level()

    data = {"tiles": rows}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
