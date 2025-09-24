import argparse
import os
from typing import List, Tuple

import pygame

from level_io import DEFAULT_LEVEL_FILE, load_level, save_level


WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 800
PALETTE_HEIGHT = 140
TILE_SIZE = 32
CAMERA_SPEED = 600

PALETTE: List[Tuple[str, str, Tuple[int, int, int]]] = [
    (" ", "Leer", (30, 32, 44)),
    ("X", "Block", (74, 96, 130)),
    ("=", "Plattform", (105, 135, 175)),
    ("^", "Stachel", (240, 90, 90)),
    ("C", "Coin", (255, 225, 90)),
    ("G", "Goomba", (190, 110, 70)),
    ("|", "Gate", (110, 210, 255)),
    ("D", "Dash-Kern", (130, 255, 220)),
    ("F", "Flagge", (255, 130, 180)),
]


def draw_tile(surface: pygame.Surface, char: str, rect: pygame.Rect) -> None:
    if char == " ":
        pygame.draw.rect(surface, (40, 44, 58), rect)
        return

    if char in ("X", "="):
        base_col = (74, 96, 130) if char == "X" else (105, 135, 175)
        pygame.draw.rect(surface, base_col, rect, border_radius=6)
        top = rect.copy()
        top.height = max(4, rect.height // 4)
        pygame.draw.rect(surface, (140, 160, 200), top, border_radius=6)
        return

    if char == "^":
        points = [
            (rect.centerx, rect.top + 4),
            (rect.left + 4, rect.bottom - 4),
            (rect.right - 4, rect.bottom - 4),
        ]
        pygame.draw.polygon(surface, (240, 90, 90), points)
        return

    if char == "C":
        pygame.draw.circle(surface, (255, 225, 90), rect.center, rect.width // 2 - 6)
        pygame.draw.circle(surface, (255, 240, 140), rect.center, rect.width // 2 - 6, 2)
        return

    if char == "G":
        body = rect.inflate(-6, -8)
        pygame.draw.ellipse(surface, (190, 110, 70), body)
        eye_radius = max(2, rect.width // 10)
        eye_y = body.top + body.height // 2 - 4
        left = (body.left + body.width // 3, eye_y)
        right = (body.right - body.width // 3, eye_y)
        pygame.draw.circle(surface, (255, 255, 255), left, eye_radius)
        pygame.draw.circle(surface, (255, 255, 255), right, eye_radius)
        pygame.draw.circle(surface, (40, 40, 60), (left[0] - eye_radius // 2, eye_y), eye_radius // 2)
        pygame.draw.circle(surface, (40, 40, 60), (right[0] - eye_radius // 2, eye_y), eye_radius // 2)
        return

    if char == "|":
        gate = rect.inflate(-rect.width // 3, -4)
        pygame.draw.rect(surface, (110, 210, 255), gate)
        pygame.draw.rect(surface, (255, 255, 255), gate, 2)
        return

    if char == "D":
        glow = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.circle(glow, (130, 255, 220, 120), (rect.width // 2, rect.height // 2), rect.width // 2 - 4)
        surface.blit(glow, rect)
        diamond = [
            (rect.centerx, rect.top + 6),
            (rect.right - 6, rect.centery),
            (rect.centerx, rect.bottom - 6),
            (rect.left + 6, rect.centery),
        ]
        pygame.draw.polygon(surface, (130, 255, 220), diamond)
        pygame.draw.polygon(surface, (255, 255, 255), diamond, 2)
        return

    if char == "F":
        pole = pygame.Rect(rect.centerx - 2, rect.top, 4, rect.height)
        pygame.draw.rect(surface, (220, 220, 230), pole)
        flag = [
            (pole.right, rect.top + 6),
            (pole.right + rect.width // 2, rect.top + rect.height // 3),
            (pole.right, rect.top + rect.height // 2),
        ]
        pygame.draw.polygon(surface, (255, 130, 180), flag)
        return


class LevelEditor:
    def __init__(self, level_path: str | None):
        pygame.init()
        pygame.display.set_caption("Level-Editor")
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        self.clock = pygame.time.Clock()

        self.font = pygame.font.Font(None, 28)
        self.font_small = pygame.font.Font(None, 22)

        level_data, source = load_level(level_path, return_source=True)
        self.level_path = level_path or source or DEFAULT_LEVEL_FILE
        self.grid = [list(row) for row in level_data]
        self.height = len(self.grid)
        self.width = len(self.grid[0]) if self.grid else 0

        self.camera_x = 0.0
        self.camera_y = 0.0
        self.selected_index = 1  # Standard: Block
        self.dragging = False
        self.drag_start = (0, 0)
        self.camera_start = (0.0, 0.0)
        self.message = ""
        self.message_timer = 0.0

        if source:
            self._show_message(f"Level geladen aus: {os.path.abspath(source)}")
        else:
            self._show_message("Standardlevel geladen")

    # ------------- Hilfsmethoden -------------
    def _clamp_camera(self) -> None:
        max_x = max(0, self.width * TILE_SIZE - self.work_area.width)
        max_y = max(0, self.height * TILE_SIZE - self.work_area.height)
        self.camera_x = max(0.0, min(self.camera_x, max_x))
        self.camera_y = max(0.0, min(self.camera_y, max_y))

    def _tile_at_pos(self, pos: Tuple[int, int]) -> Tuple[int, int] | None:
        if not self.grid:
            return None
        mx, my = pos
        if not self.work_area.collidepoint(mx, my):
            return None
        world_x = mx + self.camera_x - self.work_area.x
        world_y = my + self.camera_y - self.work_area.y
        tx = int(world_x // TILE_SIZE)
        ty = int(world_y // TILE_SIZE)
        if 0 <= tx < self.width and 0 <= ty < self.height:
            return tx, ty
        return None

    def _set_tile(self, tx: int, ty: int, char: str) -> None:
        if self.grid[ty][tx] != char:
            self.grid[ty][tx] = char

    def _cycle_selection(self, direction: int) -> None:
        self.selected_index = (self.selected_index + direction) % len(PALETTE)

    def _show_message(self, text: str) -> None:
        self.message = text
        self.message_timer = 3.0

    def _handle_mouse(self) -> None:
        mouse_buttons = pygame.mouse.get_pressed()
        mouse_pos = pygame.mouse.get_pos()

        if mouse_buttons[1]:  # mittlere Taste -> Kamera ziehen
            if not self.dragging:
                self.dragging = True
                self.drag_start = mouse_pos
                self.camera_start = (self.camera_x, self.camera_y)
        else:
            self.dragging = False

        if self.dragging:
            dx = self.drag_start[0] - mouse_pos[0]
            dy = self.drag_start[1] - mouse_pos[1]
            self.camera_x = self.camera_start[0] + dx
            self.camera_y = self.camera_start[1] + dy
            self._clamp_camera()
            return

        tile = self._tile_at_pos(mouse_pos)
        if tile is None:
            return

        tx, ty = tile
        if mouse_buttons[0]:
            char = PALETTE[self.selected_index][0]
            self._set_tile(tx, ty, char)
        elif mouse_buttons[2]:
            self._set_tile(tx, ty, " ")

    def _handle_keys(self, dt: float) -> None:
        keys = pygame.key.get_pressed()
        move_x = 0
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
            move_x += 1
        if keys[pygame.K_a] or keys[pygame.K_LEFT]:
            move_x -= 1

        move_y = 0
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            move_y += 1
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            move_y -= 1

        speed = CAMERA_SPEED * dt
        if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]:
            speed *= 1.8

        if move_x:
            self.camera_x += speed * move_x
        if move_y:
            self.camera_y += speed * move_y

        self._clamp_camera()

    def _save(self) -> None:
        save_level(["".join(row) for row in self.grid], self.level_path)
        self._show_message(f"Level gespeichert: {os.path.abspath(self.level_path)}")

    def _reload(self) -> None:
        data, source = load_level(self.level_path, return_source=True)
        self.grid = [list(row) for row in data]
        self.height = len(self.grid)
        self.width = len(self.grid[0]) if self.grid else 0
        if source:
            self._show_message(f"Level neu geladen aus: {os.path.abspath(source)}")
        else:
            self._show_message("Standardlevel neu geladen")

    # ------------- Hauptschleife -------------
    def run(self) -> None:
        running = True
        self.work_area = pygame.Rect(0, 0, WINDOW_WIDTH, WINDOW_HEIGHT - PALETTE_HEIGHT)

        while running:
            dt = self.clock.tick(60) / 1000.0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    elif event.key == pygame.K_TAB:
                        direction = -1 if pygame.key.get_mods() & pygame.KMOD_SHIFT else 1
                        self._cycle_selection(direction)
                    elif event.key == pygame.K_s and not pygame.key.get_mods() & pygame.KMOD_CTRL:
                        self._save()
                    elif event.key == pygame.K_l:
                        self._reload()
                    elif event.key in (pygame.K_0, pygame.K_KP0):
                        self.selected_index = 0
                    else:
                        for idx in range(1, min(len(PALETTE), 9)):
                            if event.key in (getattr(pygame, f"K_{idx}"), getattr(pygame, f"K_KP{idx}")):
                                self.selected_index = idx
                                break

                    if event.key == pygame.K_s and pygame.key.get_mods() & pygame.KMOD_CTRL:
                        self._save()

            self._handle_keys(dt)
            self._handle_mouse()

            if self.message_timer > 0:
                self.message_timer -= dt
                if self.message_timer <= 0:
                    self.message_timer = 0
                    self.message = ""

            self.draw()

        pygame.quit()

    # ------------- Rendering -------------
    def draw(self) -> None:
        self.screen.fill((18, 20, 28))

        # Spielfeld
        work_surf = pygame.Surface(self.work_area.size)
        work_surf.fill((26, 28, 38))

        camx = int(self.camera_x)
        camy = int(self.camera_y)

        start_tx = max(0, camx // TILE_SIZE)
        end_tx = min(self.width, (camx + self.work_area.width) // TILE_SIZE + 1)
        start_ty = max(0, camy // TILE_SIZE)
        end_ty = min(self.height, (camy + self.work_area.height) // TILE_SIZE + 1)

        for ty in range(start_ty, end_ty):
            for tx in range(start_tx, end_tx):
                rect = pygame.Rect(
                    tx * TILE_SIZE - camx,
                    ty * TILE_SIZE - camy,
                    TILE_SIZE,
                    TILE_SIZE,
                )
                draw_tile(work_surf, self.grid[ty][tx], rect)
                pygame.draw.rect(work_surf, (36, 40, 54), rect, 1)

        mouse_tile = self._tile_at_pos(pygame.mouse.get_pos())
        if mouse_tile:
            tx, ty = mouse_tile
            rect = pygame.Rect(
                tx * TILE_SIZE - camx,
                ty * TILE_SIZE - camy,
                TILE_SIZE,
                TILE_SIZE,
            )
            pygame.draw.rect(work_surf, (255, 255, 255), rect, 2)

        self.screen.blit(work_surf, self.work_area.topleft)

        # Palette & Infos
        panel = pygame.Surface((WINDOW_WIDTH, PALETTE_HEIGHT))
        panel.fill((16, 18, 26))
        pygame.draw.rect(panel, (60, 66, 90), panel.get_rect(), 2)

        title = self.font.render("Level-Editor", True, (235, 240, 245))
        panel.blit(title, (16, 10))

        info_lines = [
            f"Datei: {os.path.abspath(self.level_path)}",
            "Maus: Linksklick malt, Rechtsklick löscht, Mittelklick/Drag bewegt Kamera",
            "WASD/Pfeile: Kamera, Tab/Shift+Tab: Palette wechseln, 0-7: Schnellauswahl, S oder Strg+S: speichern, L: neu laden",
        ]
        for i, text in enumerate(info_lines):
            surf = self.font_small.render(text, True, (200, 205, 215))
            panel.blit(surf, (16, 44 + i * 22))

        if self.message:
            msg = self.font.render(self.message, True, (255, 255, 200))
            panel.blit(msg, (16, PALETTE_HEIGHT - 36))

        # Palette Zeichnen
        palette_x = 640
        for idx, (char, label, color) in enumerate(PALETTE):
            slot = pygame.Rect(palette_x + idx * 70, 16, 56, 56)
            pygame.draw.rect(panel, (40, 42, 56), slot, border_radius=8)
            inner = slot.inflate(-10, -10)
            pygame.draw.rect(panel, color, inner, border_radius=6)
            if idx == self.selected_index:
                pygame.draw.rect(panel, (255, 255, 255), slot, 2, border_radius=8)

            label_surf = self.font_small.render(f"{idx}: {label}", True, (210, 215, 225))
            panel.blit(label_surf, (slot.x, slot.bottom + 6))

        self.screen.blit(panel, (0, self.work_area.bottom))
        pygame.display.flip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Grafischer Level-Editor")
    parser.add_argument(
        "--level",
        dest="level",
        help="Pfad zur Level-Datei. Ohne Angabe wird custom_level.json verwendet.",
    )
    args = parser.parse_args()

    editor = LevelEditor(args.level)
    editor.run()


if __name__ == "__main__":
    main()
