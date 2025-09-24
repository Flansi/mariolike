import argparse
import json
import math
import os
import random
from collections import deque

import pygame

from level_io import load_level

# =========================
# 2D PLATFORMER (pygame only)
# =========================

# --- Window / Tiles ---
TILE = 48
WIDTH, HEIGHT = 1152, 672  # 24 x 14 Tiles
FPS = 60

# --- Player movement ---
GRAVITY = 2500.0
MAX_FALL = 1600.0
ACCEL = 4200.0
AIR_ACCEL = 2600.0
FRICTION = 2800.0
MAX_SPEED = 360.0

JUMP_VEL = -900.0
JUMP_CUT = 0.42
COYOTE_TIME = 0.12
JUMP_BUFFER = 0.12

# --- Dash ---
DASH_SPEED = 1150.0
DASH_TIME = 0.14
DASH_COOLDOWN = 1.1
INVINCIBLE_ON_DASH = 0.12

# --- Sprint (aktiv ab Levelstart) ---
SPRINT_SPEED_MULT   = 1.35
SPRINT_ACCEL_MULT   = 1.25
SPRINT_JUMP_MULT    = 1.15

# --- Skid / Turn (beim Sprint Richtungswechsel) ---
SKID_TRIGGER_SPEED  = MAX_SPEED * SPRINT_SPEED_MULT * 0.60
SKID_TIME           = 0.18
SKID_ACCEL_MULT     = 0.25
SKID_FRICTION_MULT  = 1.10
SKID_TILT_DEG       = 12.0

# --- Crouch / Duck (echte Hitbox) ---
CROUCH_SPEED_MULT   = 0.55
CROUCH_ACCEL_MULT   = 0.60
H_STAND             = 52
H_CROUCH            = 34
H_STAND_BIG         = 70
H_CROUCH_BIG        = 46

# --- Crouch-Slide (Sprint -> Duck) ---
CROUCH_SLIDE_TRIGGER_SPEED = MAX_SPEED * SPRINT_SPEED_MULT * 0.65
CROUCH_SLIDE_TIME_BASE     = 0.28         # Basiszeit (falls schneller Stopp)
CROUCH_SLIDE_DECEL_BASE    = 5200.0       # Basisabbremsen
CROUCH_SLIDE_MIN_DIST      = 90.0         # mindestens eine Sprite-Breite rutschen

# --- Cosmetics / juice ---
COL_BG1 = (18, 20, 28)
COL_BG2 = (26, 28, 38)
COL_TEXT = (235, 240, 245)
COL_DIM = (180, 185, 195)
COL_SOLID = (74, 96, 130)
COL_SOLID_TOP = (105, 135, 175)
COL_SPIKE = (240, 90, 90)
COL_COIN = (255, 225, 90)
COL_ITEM_BLOCK = (240, 190, 80)
COL_ITEM_BLOCK_TOP = (255, 225, 140)
COL_COIN_BLOCK = (245, 200, 70)
COL_COIN_BLOCK_TOP = (255, 235, 150)
COL_BREAKABLE = (200, 140, 90)
COL_BREAKABLE_TOP = (240, 195, 150)
COL_GATE = (110, 210, 255)
COL_FLAG = (255, 130, 180)
COL_PLAYER = (255, 190, 40)
COL_PLAYER_BIG = (255, 150, 60)
COL_DASHITEM = (130, 255, 220)
COL_GOOMBA = (190, 110, 70)
COL_MUSHROOM_TOP = (220, 80, 80)
COL_MUSHROOM_DOTS = (255, 235, 210)
COL_MUSHROOM_STEM = (235, 200, 140)

SAVE_FILE = "platformer_save.json"

# Map legend:
# 'X' = solider Boden/Block
# '=' = schwebende Plattform (auch solide)
# '^' = Stachel
# 'C' = Coin
# 'B' = Item-Block (spawnt Pilz)
# 'Q' = Coin-Block (gibt eine sofort gesammelte Münze)
# 'S' = Zerbrechlicher Block (nur als großer Spieler zerstörbar)
# '|' = Dash-Gate
# 'D' = Dash-Kern (Item)
# 'F' = Flagge / Ziel
# 'M' = Power-Up-Pilz

# ------------- Utilities -------------
def clamp(v, a, b):
    return a if v < a else b if v > b else v

def load_save():
    if os.path.exists(SAVE_FILE):
        try:
            with open(SAVE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"best_time": None}

def save_save(data):
    try:
        with open(SAVE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except:
        pass

# ------------- Level creation -------------
LEVEL, LEVEL_SOURCE = load_level(return_source=True)

# ------------- World helpers -------------
def tiles_in_aabb(tilemap, rect):
    min_tx = max(0, rect.left // TILE)
    max_tx = min(len(tilemap[0]) - 1, rect.right // TILE)
    min_ty = max(0, rect.top // TILE)
    max_ty = min(len(tilemap) - 1, rect.bottom // TILE)
    for ty in range(min_ty, max_ty + 1):
        row = tilemap[ty]
        for tx in range(min_tx, max_tx + 1):
            ch = row[tx]
            if ch != ' ':
                yield tx, ty, ch

def solid(ch): return ch in ('X', '=', 'B', 'S', 'Q')

# ------------- Entities -------------
class Particle:
    def __init__(self, x, y, vx, vy, life, color, size):
        self.x, self.y = x, y
        self.vx, self.vy = vx, vy
        self.life = life
        self.total = life
        self.color = color
        self.size = size
    def update(self, dt):
        self.x += self.vx*dt; self.y += self.vy*dt
        self.vy += 1800*dt
        self.life -= dt
        return self.life > 0
    def draw(self, surf, camx, camy):
        t = clamp(self.life/self.total, 0, 1)
        s = max(1, int(self.size*t))
        a = int(255*t)
        srf = pygame.Surface((s, s), pygame.SRCALPHA)
        pygame.draw.circle(srf, (*self.color, a), (s//2, s//2), s//2)
        surf.blit(srf, (self.x - camx - s//2, self.y - camy - s//2))

class Player:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.w = 36
        self.h_stand = H_STAND
        self.h_crouch = H_CROUCH
        self.h = self.h_stand
        self.form = "small"

        self.vx, self.vy = 0.0, 0.0
        self.on_ground = False
        self.since_ground = 0.0
        self.jump_buf = 0.0
        self.facing = 1
        self.trail = deque(maxlen=12)

        # dash/sprint/crouch
        self.dash_t = 0.0
        self.dash_cd = 0.0
        self.inv = 0.0
        self.dash_dir = 0
        self.sprint = False
        self.crouch = False
        self.dash_lock = False
        self.shift_held_prev = False
        self.dash_unlocked = False

        # Skid / Visuals
        self.skid_t = 0.0
        self.skid_dir = 0
        self.visual_tilt = 0.0

        # Crouch-Slide
        self.crouch_slide_t = 0.0
        self.crouch_slide_decel = CROUCH_SLIDE_DECEL_BASE  # dynamisch gesetzt
        self.crouch_slide_dir = 0

        self.coins = 0
        self.power_flash = 0.0

    @property
    def rect(self):
        return pygame.Rect(int(self.x - self.w/2), int(self.y - self.h), self.w, self.h)

    def add_trail(self): self.trail.append((self.x, self.y, 0.7))

    def input_axis(self, keys):
        left  = keys.get(pygame.K_a, False) or keys.get(pygame.K_LEFT, False)
        right = keys.get(pygame.K_d, False) or keys.get(pygame.K_RIGHT, False)
        ax = (-1.0 if left else 0.0) + (1.0 if right else 0.0)
        if ax != 0: self.facing = 1 if ax>0 else -1
        return ax

    def _can_stand(self, tilemap):
        stand_rect = pygame.Rect(int(self.x - self.w/2), int(self.y - self.h_stand), self.w, self.h_stand)
        for tx, ty, ch in tiles_in_aabb(tilemap, stand_rect.inflate(-8, -2)):
            if ch in ('|','^','F') or solid(ch):
                if stand_rect.colliderect(pygame.Rect(tx*TILE, ty*TILE, TILE, TILE)):
                    return False
        return True

    def _rect_fits(self, tilemap, height):
        if tilemap is None:
            return True
        rect = pygame.Rect(int(self.x - self.w/2), int(self.y - height), self.w, height)
        for tx, ty, ch in tiles_in_aabb(tilemap, rect.inflate(-8, -2)):
            if ch in ('|', '^', 'F') or solid(ch):
                if rect.colliderect(pygame.Rect(tx*TILE, ty*TILE, TILE, TILE)):
                    return False
        return True

    def set_form(self, form, tilemap=None):
        if form == self.form:
            return True

        if form == "big":
            can_stand = self._rect_fits(tilemap, H_STAND_BIG)
            if not can_stand and not self._rect_fits(tilemap, H_CROUCH_BIG):
                return False
            self.form = "big"
            self.h_stand = H_STAND_BIG
            self.h_crouch = H_CROUCH_BIG
            if can_stand and not self.crouch:
                self.h = self.h_stand
            else:
                self.crouch = True
                self.h = self.h_crouch
        else:
            self.form = "small"
            self.h_stand = H_STAND
            self.h_crouch = H_CROUCH
            if self.crouch and not self._rect_fits(tilemap, self.h_crouch):
                self.crouch = False
            if not self.crouch and not self._rect_fits(tilemap, self.h_stand):
                self.crouch = True
            self.h = self.h_crouch if self.crouch else self.h_stand
        return True

    def collect_powerup(self, kind, tilemap, particles):
        if kind == "mushroom":
            already_big = self.form == "big"
            grew = self.set_form("big", tilemap)
            if grew:
                self.power_flash = 0.6 if not already_big else 0.3
                self.inv = max(self.inv, 0.4)
                count = 20 if not already_big else 10
                for _ in range(count):
                    ang = random.random()*math.tau
                    spd = random.uniform(160, 360)
                    particles.append(Particle(self.x, self.y - self.h/2,
                                              math.cos(ang)*spd, math.sin(ang)*spd - 140,
                                              0.45, (255, 200, 120), 5))
            return grew
        return False

    def take_damage(self, tilemap, particles):
        if self.inv > 0:
            return False
        if self.form == "big":
            self.set_form("small", tilemap)
            self.inv = max(self.inv, 1.2)
            self.power_flash = 0.0
            self.vy = min(self.vy, -260)
            for _ in range(18):
                ang = random.random()*math.tau
                spd = random.uniform(120, 320)
                particles.append(Particle(self.x, self.y - self.h/2,
                                          math.cos(ang)*spd, math.sin(ang)*spd - 200,
                                          0.4, (255, 160, 120), 5))
            return False
        return True

    def _set_crouch(self, want_crouch, tilemap):
        if want_crouch and not self.crouch:
            self.h = self.h_crouch; self.crouch = True
        elif (not want_crouch) and self.crouch:
            if self._can_stand(tilemap):
                self.h = self.h_stand; self.crouch = False
            else:
                self.crouch = True

    def try_jump(self):
        if (self.on_ground or self.since_ground <= COYOTE_TIME) and self.jump_buf > 0:
            self.vy = JUMP_VEL * (SPRINT_JUMP_MULT if self.sprint else 1.0)
            self.on_ground = False; self.since_ground = 999; self.jump_buf = 0.0
            return True
        return False

    def start_dash(self):
        self.dash_t = DASH_TIME; self.dash_cd = DASH_COOLDOWN; self.inv = INVINCIBLE_ON_DASH
        self.dash_dir = self.facing if self.facing != 0 else 1
        self.vx = self.dash_dir * DASH_SPEED
        if self.vy > 0: self.vy = 0
        self.sprint = False

    def _spawn_skid_dust(self, particles, burst=False):
        if self.skid_dir == 0: return
        fx = self.x - self.skid_dir * 10; fy = self.y - 4
        n = 8 if burst else 1
        for _ in range(n):
            vx = -self.skid_dir * random.uniform(120, 220 if burst else 160)
            vy = -random.uniform(20, 140 if burst else 80)
            particles.append(Particle(fx, fy, vx, vy, 0.35 if burst else 0.25, (210,215,230), 5))

    def update(self, dt, keys, tilemap, particles, destroy_gate_cb, hit_block_cb=None):
        if self.since_ground < 10: self.since_ground += dt
        if self.jump_buf > 0: self.jump_buf -= dt
        if self.dash_t > 0: self.dash_t -= dt
        if self.dash_cd > 0: self.dash_cd -= dt
        if self.inv > 0: self.inv -= dt
        if self.skid_t > 0: self.skid_t -= dt
        if self.crouch_slide_t > 0: self.crouch_slide_t -= dt
        if self.power_flash > 0: self.power_flash = max(0.0, self.power_flash - dt)
        if self.trail:
            decay = 3.5 * dt
            maxlen = self.trail.maxlen
            new_trail = deque(maxlen=maxlen)
            for tx, ty, alpha in self.trail:
                alpha -= decay
                if alpha > 0:
                    new_trail.append((tx, ty, alpha))
            self.trail = new_trail

        ax = self.input_axis(keys)
        shift_held    = keys.get("shift_held", False)
        shift_pressed = keys.get("dash_pressed", False)
        crouch_held   = keys.get("crouch_held", False)
        crouch_pressed= keys.get("crouch_pressed", False)
        input_dir = 1 if ax > 0 else (-1 if ax < 0 else 0)
        moving_dir = 1 if self.vx > 20 else (-1 if self.vx < -20 else 0)

        prev_crouch = self.crouch
        prev_sprint = self.sprint

        # Crouch (inkl. erzwungenes Ducken)
        want_crouch = (self.dash_t <= 0) and crouch_held
        if not want_crouch and self.crouch and not self._can_stand(tilemap):
            want_crouch = True
        self._set_crouch(want_crouch, tilemap)

        # --- Crouch-Slide: dynamischer Decel, Mindeststrecke ---
        if (crouch_pressed and not prev_crouch and self.crouch and self.on_ground and
            prev_sprint and self.dash_t <= 0 and abs(self.vx) >= CROUCH_SLIDE_TRIGGER_SPEED):
            v0 = abs(self.vx)
            a_req = (v0*v0) / (2.0 * max(1.0, CROUCH_SLIDE_MIN_DIST))  # a <= a_req -> s >= MIN
            self.crouch_slide_decel = min(CROUCH_SLIDE_DECEL_BASE, a_req)
            t_stop = v0 / max(1.0, self.crouch_slide_decel)
            self.crouch_slide_t = max(CROUCH_SLIDE_TIME_BASE, t_stop)   # genug Zeit, um die Strecke zu rollen
            self.crouch_slide_dir = 1 if self.vx >= 0 else -1
            # Staub zum Start
            for _ in range(8):
                vx = -self.crouch_slide_dir * random.uniform(80, 160)
                vy = -random.uniform(20, 120)
                particles.append(Particle(self.x, self.y-6, vx, vy, 0.3, (210,215,230), 5))

        if self.crouch_slide_t > 0:
            self.h = self.h_crouch
            self.crouch = True

        # Dash nur wenn freigeschaltet, nicht geduckt und Platz
        if (self.dash_unlocked and shift_pressed and self.dash_cd <= 0 and self.dash_t <= 0
            and not self.dash_lock and not self.crouch and self._can_stand(tilemap)):
            self.start_dash(); self.dash_lock = True

        # Sprint (nicht während Dash/Duck)
        if self.dash_t <= 0 and shift_held and not self.crouch:
            self.sprint = True
        else:
            if not shift_held or self.crouch: self.sprint = False
        if not shift_held: self.dash_lock = False

        # Skid (Richtungswechsel im Sprint)
        if (self.on_ground and self.sprint and self.dash_t <= 0 and
            input_dir != 0 and moving_dir != 0 and input_dir != moving_dir and
            abs(self.vx) >= SKID_TRIGGER_SPEED and self.skid_t <= 0):
            self.skid_t = SKID_TIME; self.skid_dir = moving_dir; self.facing = input_dir
            self._spawn_skid_dust(particles, burst=True)

        # --- Horizontal ---
        if self.dash_t > 0:
            self.add_trail()
        else:
            accel_base = (ACCEL if self.on_ground else AIR_ACCEL)
            speed_mult = 1.0
            accel_mult = 1.0
            if self.sprint:
                speed_mult *= SPRINT_SPEED_MULT; accel_mult *= SPRINT_ACCEL_MULT
            if self.crouch and self.crouch_slide_t <= 0:
                speed_mult *= CROUCH_SPEED_MULT; accel_mult *= CROUCH_ACCEL_MULT
            accel = accel_base * accel_mult

            # Skid-Reibung
            if self.skid_t > 0 and self.on_ground:
                accel *= SKID_ACCEL_MULT
                self.vx -= math.copysign(FRICTION * SKID_FRICTION_MULT * dt, self.vx)
                if random.random() < 6.0*dt: self._spawn_skid_dust(particles, burst=False)

            # Crouch-Slide: konstante Abbremsung ohne Eingabe
            if self.crouch_slide_t > 0 and self.on_ground:
                dec = self.crouch_slide_decel * dt
                if abs(self.vx) <= dec: self.vx = 0
                else: self.vx -= math.copysign(dec, self.vx)
                if random.random() < 5.0*dt:
                    particles.append(Particle(self.x, self.y-6,
                                              -math.copysign(random.uniform(60,120), self.vx if self.vx!=0 else self.crouch_slide_dir),
                                              -random.uniform(10,80), 0.25, (210,215,230), 4))
            else:
                # normale Eingabe
                self.vx += accel * ax * dt
                if abs(ax) < 0.01 and self.on_ground:
                    if abs(self.vx) <= FRICTION*dt: self.vx = 0
                    else: self.vx -= FRICTION*dt * (1 if self.vx>0 else -1)

        # Max-Speed Clamp (Slide hat keine Crouch-Drossel)
        max_speed = MAX_SPEED
        if self.dash_t <= 0:
            if self.sprint: max_speed *= SPRINT_SPEED_MULT
            if self.crouch and self.crouch_slide_t <= 0: max_speed *= CROUCH_SPEED_MULT
            self.vx = clamp(self.vx, -max_speed, max_speed)

        # --- Gravity & Jump ---
        self.vy += GRAVITY * dt
        self.vy = clamp(self.vy, -9999, MAX_FALL)
        if keys.get("jump_pressed", False): self.jump_buf = JUMP_BUFFER
        if keys.get("jump_released", False) and self.vy < 0: self.vy *= JUMP_CUT

        # --- Move & Collide ---
        self.on_ground = False

        # Horizontal
        self.x += self.vx * dt
        r = self.rect
        collided_gate = None
        for tx, ty, ch in tiles_in_aabb(tilemap, r.inflate(2, -2)):
            tile_r = pygame.Rect(tx*TILE, ty*TILE, TILE, TILE)
            if ch == '|':
                if self.dash_t > 0:
                    collided_gate = (tx, ty)
                else:
                    if r.colliderect(tile_r):
                        if self.vx > 0: self.x = tile_r.left - (self.w/2)
                        elif self.vx < 0: self.x = tile_r.right + (self.w/2)
                        self.vx = 0
            if solid(ch):
                if r.colliderect(tile_r):
                    if self.vx > 0: self.x = tile_r.left - (self.w/2)
                    elif self.vx < 0: self.x = tile_r.right + (self.w/2)
                    self.vx = 0

        if collided_gate:
            destroy_gate_cb(*collided_gate)
            gx, gy = collided_gate
            cx, cy = gx*TILE + TILE/2, gy*TILE + TILE/2
            for _ in range(24):
                ang = random.random()*math.tau
                spd = random.uniform(200, 520)
                particles.append(Particle(cx, cy, math.cos(ang)*spd, math.sin(ang)*spd-200, 0.5, (110,210,255), 5))

        # Vertikal (sub-steps)
        total_dy = self.vy * dt
        steps = max(1, int(abs(total_dy)//max(1, TILE//6)) + 1)
        step_dy = total_dy / steps
        for _ in range(steps):
            prev_rect = self.rect.copy()
            self.y += step_dy
            r = self.rect
            for tx, ty, ch in tiles_in_aabb(tilemap, r.inflate(-8, 0)):
                if ch == '|' and self.dash_t > 0: continue
                if ch == '|' or solid(ch):
                    tile_r = pygame.Rect(tx*TILE, ty*TILE, TILE, TILE)
                    if not r.colliderect(tile_r): continue
                    if step_dy > 0:
                        if prev_rect.bottom <= tile_r.top and r.bottom >= tile_r.top:
                            self.y = tile_r.top; self.vy = 0; self.on_ground = True; self.since_ground = 0.0; r = self.rect
                    elif step_dy < 0:
                        if prev_rect.top >= tile_r.bottom and r.top <= tile_r.bottom:
                            self.y = tile_r.bottom + self.h; self.vy = 0; r = self.rect
                            if ch in ('B', 'S', 'Q') and hit_block_cb:
                                hit_block_cb(tx, ty, ch, self)

        # visueller Tilt
        tilt_target = (-SKID_TILT_DEG * self.skid_dir) if self.skid_t > 0 else 0.0
        self.visual_tilt += (tilt_target - self.visual_tilt) * min(1.0, 14*dt)

    def draw(self, surf, camx, camy):
        for i, (tx, ty, alpha) in enumerate(self.trail):
            t = clamp(alpha, 0.0, 1.0)
            a = int(200 * t)
            if len(self.trail) > 1:
                a = int(a * ((i + 1) / len(self.trail)))
            srf = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
            pygame.draw.rect(srf, (255,255,255,a//3), (0,0,self.w,self.h), border_radius=10)
            surf.blit(srf, (tx - self.w/2 - camx, ty - self.h - camy))

        color = (255, 215, 80) if self.sprint and self.dash_t<=0 else (COL_PLAYER_BIG if self.form == "big" else COL_PLAYER)
        foot_x = self.x - camx; foot_y = self.y - camy
        crouching = abs(self.h - self.h_stand) > 0.1
        if self.power_flash > 0:
            alpha = int(255 * clamp(self.power_flash / 0.6, 0.0, 1.0))
            glow = pygame.Surface((self.w + 20, self.h + 20), pygame.SRCALPHA)
            pygame.draw.ellipse(glow, (255, 220, 160, alpha), glow.get_rect())
            surf.blit(glow, (foot_x - (self.w + 20)/2, foot_y - self.h - 10))
        base = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        pygame.draw.rect(base, color, (0,0,self.w,self.h), border_radius=10)
        eye_x = self.w//2 + (8 * (1 if self.facing>0 else -1))
        if self.form == "big":
            eye_radius = 5
            eye_y = 18 if not crouching else 12
        else:
            eye_radius = 4
            eye_y = 12 if crouching else 14
        pygame.draw.circle(base, (40,40,60), (eye_x, eye_y), eye_radius)
        if self.inv > 0 and self.dash_t <= 0 and int(self.inv*15) % 2 == 0:
            shade = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
            shade.fill((255, 255, 255, 110))
            base.blit(shade, (0, 0), special_flags=pygame.BLEND_PREMULTIPLIED)
        img = pygame.transform.rotate(base, self.visual_tilt) if abs(self.visual_tilt) > 0.5 else base
        dest = img.get_rect(); dest.midbottom = (int(foot_x), int(foot_y))
        surf.blit(img, dest)

class MushroomItem:
    SPEED = 160.0
    EMERGE_SPEED = 180.0
    GRAVITY = GRAVITY
    MAX_FALL = MAX_FALL

    def __init__(self, x, block_top, direction):
        self.x = x
        self.w = 40
        self.h = 40
        self.target_y = block_top
        self.y = block_top + self.h
        self.vx = 0.0
        self.vy = 0.0
        self.direction = 1 if direction >= 0 else -1
        self.state = "emerging"
        self.remove = False

    @property
    def rect(self):
        return pygame.Rect(int(self.x - self.w/2), int(self.y - self.h), self.w, self.h)

    def update(self, dt, tilemap):
        if self.remove:
            return

        if self.state == "emerging":
            self.y -= self.EMERGE_SPEED * dt
            if self.y <= self.target_y:
                self.y = self.target_y
                self.state = "active"
                self.vx = self.direction * self.SPEED
            return

        self.vy += self.GRAVITY * dt
        self.vy = clamp(self.vy, -9999, self.MAX_FALL)

        self.x += self.vx * dt
        r = self.rect
        hit_wall = False
        for tx, ty, ch in tiles_in_aabb(tilemap, r.inflate(2, -4)):
            if ch in ('|', 'F'):
                ch = 'X'
            if solid(ch):
                tile_r = pygame.Rect(tx*TILE, ty*TILE, TILE, TILE)
                if r.colliderect(tile_r):
                    hit_wall = True
                    if self.vx > 0:
                        self.x = tile_r.left - (self.w/2)
                    elif self.vx < 0:
                        self.x = tile_r.right + (self.w/2)
                    r = self.rect
        if hit_wall:
            self.vx *= -1

        total_dy = self.vy * dt
        steps = max(1, int(abs(total_dy)//max(1, TILE//6)) + 1)
        step_dy = total_dy / steps
        for _ in range(steps):
            prev_rect = self.rect.copy()
            self.y += step_dy
            r = self.rect
            for tx, ty, ch in tiles_in_aabb(tilemap, r):
                if ch in ('|', 'F'):
                    ch = 'X'
                if solid(ch):
                    tile_r = pygame.Rect(tx*TILE, ty*TILE, TILE, TILE)
                    if not r.colliderect(tile_r):
                        continue
                    if step_dy > 0:
                        if prev_rect.bottom <= tile_r.top and r.bottom >= tile_r.top:
                            self.y = tile_r.top
                            self.vy = 0
                            r = self.rect
                    elif step_dy < 0:
                        if prev_rect.top >= tile_r.bottom and r.top <= tile_r.bottom:
                            self.y = tile_r.bottom + self.h
                            self.vy = 0
                            r = self.rect

        level_h = len(tilemap) * TILE
        if self.y > level_h + 200:
            self.remove = True

    def draw(self, surf, camx, camy):
        if self.remove:
            return
        rect = pygame.Rect(int(self.x - self.w/2 - camx), int(self.y - self.h - camy), self.w, self.h)
        cap_rect = pygame.Rect(rect.x + 6, rect.y + 6, rect.w - 12, rect.h//2)
        pygame.draw.ellipse(surf, COL_MUSHROOM_TOP, cap_rect)
        dot_radius = max(3, rect.w//10)
        pygame.draw.circle(surf, COL_MUSHROOM_DOTS, cap_rect.midleft, dot_radius)
        pygame.draw.circle(surf, COL_MUSHROOM_DOTS, cap_rect.midright, dot_radius)
        pygame.draw.circle(surf, COL_MUSHROOM_DOTS, (cap_rect.centerx, cap_rect.centery), dot_radius + 2)
        stem = pygame.Rect(rect.centerx - 6, rect.y + rect.h//2, 12, rect.h//2 - 6)
        pygame.draw.rect(surf, COL_MUSHROOM_STEM, stem, border_radius=4)

class Goomba:
    SPEED = 110.0
    GRAVITY = GRAVITY
    MAX_FALL = MAX_FALL

    def __init__(self, x, y):
        self.x, self.y = x, y
        self.w = 42
        self.h = 42
        self.vx = random.choice([-1, 1]) * self.SPEED
        self.vy = 0.0
        self.facing = 1 if self.vx >= 0 else -1
        self.alive = True
        self.remove = False
        self.squish_timer = 0.0

    @property
    def rect(self):
        height = self.current_height()
        return pygame.Rect(int(self.x - self.w/2), int(self.y - height), self.w, height)

    def current_height(self):
        if self.alive:
            return self.h
        return max(18, int(self.h * 0.45))

    def update(self, dt, tilemap):
        if self.remove:
            return
        if not self.alive:
            self.squish_timer -= dt
            if self.squish_timer <= 0:
                self.remove = True
            return

        self.vy += self.GRAVITY * dt
        self.vy = clamp(self.vy, -9999, self.MAX_FALL)

        self.x += self.vx * dt
        r = self.rect
        hit_wall = False
        for tx, ty, ch in tiles_in_aabb(tilemap, r.inflate(2, -4)):
            if ch in ('|', 'F') or solid(ch):
                tile_r = pygame.Rect(tx*TILE, ty*TILE, TILE, TILE)
                if r.colliderect(tile_r):
                    hit_wall = True
                    if self.vx > 0:
                        self.x = tile_r.left - (self.w/2)
                    elif self.vx < 0:
                        self.x = tile_r.right + (self.w/2)
                    r = self.rect
        if hit_wall:
            self.vx *= -1
            self.facing = 1 if self.vx >= 0 else -1

        total_dy = self.vy * dt
        steps = max(1, int(abs(total_dy)//max(1, TILE//6)) + 1)
        step_dy = total_dy / steps
        for _ in range(steps):
            prev_rect = self.rect.copy()
            self.y += step_dy
            r = self.rect
            for tx, ty, ch in tiles_in_aabb(tilemap, r):
                if ch in ('|', 'F'):
                    ch = 'X'
                if solid(ch):
                    tile_r = pygame.Rect(tx*TILE, ty*TILE, TILE, TILE)
                    if not r.colliderect(tile_r):
                        continue
                    if step_dy > 0:
                        if prev_rect.bottom <= tile_r.top and r.bottom >= tile_r.top:
                            self.y = tile_r.top
                            self.vy = 0
                            r = self.rect
                    elif step_dy < 0:
                        if prev_rect.top >= tile_r.bottom and r.top <= tile_r.bottom:
                            self.y = tile_r.bottom + self.current_height()
                            self.vy = 0
                            r = self.rect

        level_h = len(tilemap) * TILE
        if self.y > level_h + 200:
            self.remove = True

    def squish(self, particles):
        if not self.alive or self.remove:
            return
        self.alive = False
        self.vx = 0
        self.vy = 0
        self.squish_timer = 0.35
        for _ in range(10):
            vx = random.uniform(-140, 140)
            vy = random.uniform(-280, -120)
            particles.append(Particle(self.x, self.y - 12, vx, vy, 0.35, (220, 160, 120), 4))

    def hit_by_dash(self, particles, direction):
        if self.remove:
            return
        self.remove = True
        for _ in range(14):
            ang = random.uniform(-0.8, 0.8)
            spd = random.uniform(200, 420)
            vx = math.cos(ang) * spd * direction
            vy = math.sin(ang) * spd - 120
            particles.append(Particle(self.x, self.y - self.current_height()/2, vx, vy, 0.4, (235, 200, 150), 5))

    def draw(self, surf, camx, camy):
        if self.remove:
            return
        height = self.current_height()
        foot_x = self.x - camx
        foot_y = self.y - camy
        img = pygame.Surface((self.w, height), pygame.SRCALPHA)
        body_rect = pygame.Rect(0, max(0, height - self.h), self.w, height)
        pygame.draw.rect(img, COL_GOOMBA, body_rect, border_radius=height//2)
        eye_y = int(height*0.35)
        if self.alive:
            eye_offset = int(self.w*0.2)
            eye_radius = max(3, self.w//10)
            left = (self.w//2 - eye_offset, eye_y)
            right = (self.w//2 + eye_offset, eye_y)
            pygame.draw.circle(img, (255, 255, 255), left, eye_radius)
            pygame.draw.circle(img, (255, 255, 255), right, eye_radius)
            pupil = max(2, eye_radius//2)
            px = pupil if self.facing <= 0 else -pupil
            pygame.draw.circle(img, (40, 40, 60), (left[0] + px, left[1]), pupil)
            pygame.draw.circle(img, (40, 40, 60), (right[0] + px, right[1]), pupil)
        else:
            mouth = pygame.Rect(self.w*0.25, eye_y, self.w*0.5, 4)
            pygame.draw.rect(img, (40, 40, 60), mouth)
        dest = img.get_rect()
        dest.midbottom = (int(foot_x), int(foot_y))
        surf.blit(img, dest)

# ---------------- Game ----------------
class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Dash-Platformer – Level 1")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 32)
        self.font_big = pygame.font.Font(None, 56)
        self.font_small = pygame.font.Font(None, 24)
        self.reset()

    def reset(self):
        self.tilemap = [list(row) for row in LEVEL]
        start_x = 3*TILE + TILE//2
        ground_y = (len(self.tilemap)-1)*TILE
        self.player = Player(start_x, ground_y)
        self.player.set_form("small", self.tilemap)
        self.enemies = []
        self.items = []
        for ty, row in enumerate(self.tilemap):
            for tx, ch in enumerate(row):
                if ch == 'G':
                    gx = tx*TILE + TILE//2
                    gy = (ty+1)*TILE
                    self.enemies.append(Goomba(gx, gy))
                    self.tilemap[ty][tx] = ' '
        self.coins_total = sum(row.count('C') + row.count('Q') for row in self.tilemap)
        self.coins_got = 0
        self.time = 0.0
        self.state = "RUN"
        self.camera_x = 0.0
        self.camera_y = 0.0
        self.particles = []
        self.best_time = load_save().get("best_time")
        self.toast = ""
        self.toast_t = 0.0
        self._jp_last = False
        self._sh_last = False
        self._cr_last = False

        self.hints = [
            (TILE*0,   TILE*7, TILE*18,  TILE*13, "S oder ↓: DUCKEN – niedrige Durchgänge nur geduckt!", "always"),
            (TILE*10,  TILE*6, TILE*26,  TILE*12, "Pilze einsammeln: Du wirst groß und hältst einen Treffer aus!", "always"),
            (TILE*14,  TILE*6, TILE*28,  TILE*12, "Left-Shift: SPRINT (von Anfang an)", "always"),
            (TILE*32,  TILE*6, TILE*48,  TILE*12, "Sprint: schneller & höher/weiter springen", "always"),
            (TILE*92,  TILE*6, TILE*106, TILE*12, "★ Dash-Kern: Einsammeln zum Freischalten!", "locked"),
            (TILE*120, TILE*6, TILE*130, TILE*12, "Gate voraus – du brauchst den Dash!", "locked"),
            (TILE*130, TILE*6, TILE*142, TILE*12, "Left-Shift tippen: DASH (Gate zerstören)", "unlocked"),
            (TILE*136, TILE*8, TILE*160, TILE*13, "Nach dem Dash halten: SPRINT", "unlocked"),
            (TILE*140, TILE*6, TILE*168, TILE*12, "Sprint + Sprung: weiter & höher!", "unlocked"),
        ]

    def destroy_gate(self, tx, ty):
        if self.tilemap[ty][tx] == '|':
            self.tilemap[ty][tx] = ' '

    def hit_block(self, tx, ty, ch, player):
        if ty < 0 or ty >= len(self.tilemap):
            return
        if tx < 0 or tx >= len(self.tilemap[0]):
            return
        current = self.tilemap[ty][tx]
        if current != ch:
            return
        spawn_x = tx * TILE + TILE / 2
        block_top = ty * TILE

        if ch == 'B':
            self.tilemap[ty][tx] = 'X'
            direction = -1 if player.x >= spawn_x else 1
            self.items.append(MushroomItem(spawn_x, block_top, direction))
            for _ in range(6):
                vx = random.uniform(-120, 120)
                vy = random.uniform(-320, -160)
                self.particles.append(Particle(spawn_x, block_top, vx, vy, 0.25, (255, 220, 150), 4))
        elif ch == 'Q':
            self.tilemap[ty][tx] = 'X'
            self.coins_got += 1
            player.coins += 1
            coin_y = block_top - TILE * 0.4
            self.particles.append(Particle(spawn_x, coin_y, 0, -420, 0.35, COL_COIN, 18))
            for _ in range(8):
                ang = random.random()*math.tau
                spd = random.uniform(120, 360)
                self.particles.append(Particle(spawn_x,
                                              coin_y,
                                              math.cos(ang)*spd * 0.4,
                                              math.sin(ang)*spd - 140,
                                              0.4,
                                              (255, 240, 160),
                                              4))
        elif ch == 'S':
            if player.form != "big":
                return
            self.tilemap[ty][tx] = ' '
            for _ in range(12):
                speed = random.uniform(200, 420)
                angle = random.uniform(-math.pi, 0)
                vx = math.cos(angle) * speed
                vy = math.sin(angle) * speed - 60
                self.particles.append(Particle(spawn_x, block_top, vx, vy, 0.35, (235, 200, 150), 4))

    def camera_follow(self, dt):
        target_x = self.player.x - WIDTH*0.4
        level_w = len(self.tilemap[0]) * TILE
        target_x = clamp(target_x, 0, max(0, level_w - WIDTH))
        self.camera_x += (target_x - self.camera_x) * min(1.0, 10*dt)
        self.camera_y = 0

    def update(self, dt):
        if self.state != "RUN": return

        keys_raw = pygame.key.get_pressed()
        jp = keys_raw[pygame.K_SPACE]
        sh = keys_raw[pygame.K_LSHIFT]
        cr = keys_raw[pygame.K_s] or keys_raw[pygame.K_DOWN]

        prev_player_rect = self.player.rect.copy()

        keys = {
            pygame.K_a: keys_raw[pygame.K_a],
            pygame.K_d: keys_raw[pygame.K_d],
            pygame.K_LEFT: keys_raw[pygame.K_LEFT],
            pygame.K_RIGHT: keys_raw[pygame.K_RIGHT],
            "shift_held": sh,
            "dash_pressed": sh and not getattr(self, "_sh_last", False),
            "jump_pressed": jp and not getattr(self, "_jp_last", False),
            "jump_released": (not jp) and getattr(self, "_jp_last", False),
            "crouch_held": cr,
            "crouch_pressed": cr and not getattr(self, "_cr_last", False),
        }
        self._jp_last = jp; self._sh_last = sh; self._cr_last = cr

        self.player.update(dt, keys, self.tilemap, self.particles, self.destroy_gate, self.hit_block)
        if keys["jump_pressed"]: self.player.try_jump()

        for item in self.items:
            item.update(dt, self.tilemap)

        player_rect = self.player.rect
        for item in self.items:
            if item.remove or item.state != "active":
                continue
            if player_rect.colliderect(item.rect):
                if self.player.collect_powerup("mushroom", self.tilemap, self.particles):
                    item.remove = True
                else:
                    item.remove = True
                    cx, cy = item.x, item.y - item.h / 2
                    for _ in range(8):
                        ang = random.random()*math.tau
                        spd = random.uniform(80, 220)
                        self.particles.append(Particle(cx, cy,
                                                      math.cos(ang)*spd,
                                                      math.sin(ang)*spd - 80,
                                                      0.3,
                                                      (255, 200, 140),
                                                      4))

        self.items = [i for i in self.items if not i.remove]

        for enemy in self.enemies:
            enemy.update(dt, self.tilemap)

        # handle enemy-enemy collisions (currently only goombas)
        for i in range(len(self.enemies)):
            a = self.enemies[i]
            if a.remove or not getattr(a, "alive", False):
                continue
            rect_a = a.rect
            for j in range(i + 1, len(self.enemies)):
                b = self.enemies[j]
                if b.remove or not getattr(b, "alive", False):
                    continue
                rect_b = b.rect
                if not rect_a.colliderect(rect_b):
                    continue

                overlap_x = min(rect_a.right, rect_b.right) - max(rect_a.left, rect_b.left)
                overlap_y = min(rect_a.bottom, rect_b.bottom) - max(rect_a.top, rect_b.top)
                if overlap_x <= 0 or overlap_y <= 0:
                    continue

                # resolve primarily horizontal collisions and reverse directions
                if overlap_x <= overlap_y:
                    if a.x < b.x:
                        a.x -= overlap_x / 2
                        b.x += overlap_x / 2
                        a.vx = -abs(a.vx)
                        b.vx = abs(b.vx)
                    else:
                        a.x += overlap_x / 2
                        b.x -= overlap_x / 2
                        a.vx = abs(a.vx)
                        b.vx = -abs(b.vx)
                else:
                    # in case of vertical overlap, separate slightly to avoid sticking
                    if a.y < b.y:
                        a.y -= overlap_y / 2
                        b.y += overlap_y / 2
                    else:
                        a.y += overlap_y / 2
                        b.y -= overlap_y / 2

                a.facing = 1 if a.vx >= 0 else -1
                b.facing = 1 if b.vx >= 0 else -1
                rect_a = a.rect

        r = self.player.rect
        for enemy in self.enemies:
            if enemy.remove or not enemy.alive:
                continue
            er = enemy.rect
            if not r.colliderect(er):
                continue
            stomp = (
                prev_player_rect.bottom <= er.top + 6
                and self.player.vy >= 0
                and self.player.y >= prev_player_rect.bottom
            )
            if stomp:
                enemy.squish(self.particles)
                self.player.vy = JUMP_VEL * 0.55
                self.player.on_ground = False
                self.player.since_ground = 999
                self.player.y = er.top
                r = self.player.rect
                continue
            if self.player.dash_t > 0:
                direction = self.player.dash_dir if self.player.dash_dir else (1 if self.player.vx >= 0 else -1)
                enemy.hit_by_dash(self.particles, direction)
                continue
            if self.player.inv > 0:
                continue
            if self.player.take_damage(self.tilemap, self.particles):
                self.state = "DEAD"
                break
            knock = 1 if self.player.x >= enemy.x else -1
            self.player.vx = 280 * knock
            self.player.vy = -280
            self.player.x += knock * 8
            r = self.player.rect
            continue

        self.enemies = [e for e in self.enemies if not e.remove]

        r = self.player.rect
        for tx, ty, ch in tiles_in_aabb(self.tilemap, r.inflate(8,8)):
            if ch == 'C':
                self.tilemap[ty][tx] = ' '; self.coins_got += 1; self.player.coins += 1
                cx, cy = tx*TILE + TILE/2, ty*TILE + TILE/2
                for _ in range(10):
                    ang = random.random()*math.tau; spd = random.uniform(120, 360)
                    self.particles.append(Particle(cx, cy, math.cos(ang)*spd, math.sin(ang)*spd-120, 0.4, (255,225,90), 5))
            elif ch == 'D':
                self.tilemap[ty][tx] = ' '; self.player.dash_unlocked = True
                cx, cy = tx*TILE + TILE/2, ty*TILE + TILE/2
                for _ in range(26):
                    ang = random.random()*math.tau; spd = random.uniform(180, 480)
                    self.particles.append(Particle(cx, cy, math.cos(ang)*spd, math.sin(ang)*spd-160, 0.6, COL_DASHITEM, 6))
                self.toast = "Dash freigeschaltet!  Left-Shift tippen: Dash  •  Halten: Sprint"; self.toast_t = 4.0
            elif ch == 'M':
                if self.player.collect_powerup("mushroom", self.tilemap, self.particles):
                    self.tilemap[ty][tx] = ' '
                else:
                    # Kein Platz zum Wachsen -> Bonus-Funken statt Powerup
                    self.tilemap[ty][tx] = ' '
                    cx, cy = tx*TILE + TILE/2, ty*TILE + TILE/2
                    for _ in range(8):
                        ang = random.random()*math.tau; spd = random.uniform(80, 220)
                        self.particles.append(Particle(cx, cy, math.cos(ang)*spd, math.sin(ang)*spd-80, 0.3, (255, 200, 140), 4))
            elif ch == '^':
                if r.colliderect(pygame.Rect(tx*TILE, ty*TILE, TILE, TILE)):
                    if self.player.take_damage(self.tilemap, self.particles):
                        self.state = "DEAD"
            elif ch == 'F':
                if r.colliderect(pygame.Rect(tx*TILE, ty*TILE, TILE, TILE)):
                    self.state = "WIN"; break

        self.particles = [p for p in self.particles if p.update(dt)]

        if self.toast_t > 0:
            self.toast_t -= dt
            if self.toast_t <= 0: self.toast_t = 0; self.toast = ""

        level_h = len(self.tilemap)*TILE
        if self.player.y > level_h + 200: self.state = "DEAD"

        self.camera_follow(dt)
        self.time += dt

    def draw_bg(self):
        self.screen.fill(COL_BG1)
        pygame.draw.rect(self.screen, COL_BG2, (0, HEIGHT*0.55, WIDTH, HEIGHT*0.45))

    def draw_world(self):
        camx, camy = int(self.camera_x), int(self.camera_y)
        min_tx = max(0, camx // TILE - 1)
        max_tx = min(len(self.tilemap[0])-1, (camx + WIDTH)//TILE + 1)
        min_ty = 0; max_ty = len(self.tilemap)-1

        for ty in range(min_ty, max_ty+1):
            for tx in range(min_tx, max_tx+1):
                ch = self.tilemap[ty][tx]
                if ch == ' ': continue
                x, y = tx*TILE - camx, ty*TILE - camy
                if ch in ('X','='):
                    r = pygame.Rect(x, y, TILE, TILE)
                    pygame.draw.rect(self.screen, COL_SOLID, r, border_radius=6)
                    top = r.copy(); top.h = max(6, r.h//5)
                    pygame.draw.rect(self.screen, COL_SOLID_TOP, top, border_radius=6)
                elif ch == 'S':
                    r = pygame.Rect(x, y, TILE, TILE)
                    pygame.draw.rect(self.screen, COL_BREAKABLE, r, border_radius=6)
                    top = r.copy(); top.h = max(6, r.h//5)
                    pygame.draw.rect(self.screen, COL_BREAKABLE_TOP, top, border_radius=6)
                elif ch == 'B':
                    r = pygame.Rect(x, y, TILE, TILE)
                    pygame.draw.rect(self.screen, COL_ITEM_BLOCK, r, border_radius=6)
                    top = r.copy(); top.h = max(6, r.h//5)
                    pygame.draw.rect(self.screen, COL_ITEM_BLOCK_TOP, top, border_radius=6)
                    mark = pygame.Rect(r.centerx - 7, r.y + r.h//3 - 6, 14, 14)
                    pygame.draw.rect(self.screen, (90, 70, 40), mark, border_radius=6)
                    dot = pygame.Rect(r.centerx - 4, r.y + int(r.h*0.7), 8, 8)
                    pygame.draw.rect(self.screen, (90, 70, 40), dot, border_radius=4)
                elif ch == 'Q':
                    r = pygame.Rect(x, y, TILE, TILE)
                    pygame.draw.rect(self.screen, COL_COIN_BLOCK, r, border_radius=6)
                    top = r.copy(); top.h = max(6, r.h//5)
                    pygame.draw.rect(self.screen, COL_COIN_BLOCK_TOP, top, border_radius=6)
                    coin_rect = pygame.Rect(0, 0, max(12, TILE//2), max(12, TILE//2))
                    coin_rect.center = (r.centerx, r.y + r.h//2)
                    pygame.draw.ellipse(self.screen, COL_COIN, coin_rect)
                    pygame.draw.ellipse(self.screen, (255, 240, 160), coin_rect, 3)
                elif ch == '^':
                    pts = [(x, y+TILE), (x+TILE/2, y), (x+TILE, y+TILE)]
                    pygame.draw.polygon(self.screen, COL_SPIKE, pts)
                elif ch == 'C':
                    pygame.draw.circle(self.screen, COL_COIN, (x+TILE//2, y+TILE//2), 12)
                    pygame.draw.circle(self.screen, (255,240,140), (x+TILE//2, y+TILE//2), 12, 2)
                elif ch == '|':
                    pygame.draw.rect(self.screen, COL_GATE, (x+10, y, TILE-20, TILE))
                    pygame.draw.rect(self.screen, (255,255,255), (x+10, y, TILE-20, TILE), 2)
                elif ch == 'D':
                    glow = pygame.Surface((TILE, TILE), pygame.SRCALPHA)
                    pygame.draw.circle(glow, (130,255,220,120), (TILE//2, TILE//2), 18)
                    pygame.draw.circle(glow, (130,255,220,80), (TILE//2, TILE//2), 28)
                    self.screen.blit(glow, (x, y))
                    pts = [(x+TILE//2, y+12), (x+TILE-12, y+TILE//2), (x+TILE//2, y+TILE-12), (x+12, y+TILE//2)]
                    pygame.draw.polygon(self.screen, COL_DASHITEM, pts)
                    pygame.draw.polygon(self.screen, (255,255,255), pts, 2)
                elif ch == 'M':
                    cap_rect = pygame.Rect(x+6, y+6, TILE-12, TILE//2)
                    pygame.draw.ellipse(self.screen, COL_MUSHROOM_TOP, cap_rect)
                    dot_radius = max(3, TILE//10)
                    pygame.draw.circle(self.screen, COL_MUSHROOM_DOTS, cap_rect.midleft, dot_radius)
                    pygame.draw.circle(self.screen, COL_MUSHROOM_DOTS, cap_rect.midright, dot_radius)
                    pygame.draw.circle(self.screen, COL_MUSHROOM_DOTS, (cap_rect.centerx, cap_rect.centery), dot_radius+2)
                    stem = pygame.Rect(x+TILE//2-6, y+TILE//2, 12, TILE//2-6)
                    pygame.draw.rect(self.screen, COL_MUSHROOM_STEM, stem, border_radius=4)
                elif ch == 'F':
                    pole = pygame.Rect(x+TILE//2-2, y, 4, TILE*4)
                    pygame.draw.rect(self.screen, (220,220,230), pole)
                    pygame.draw.polygon(self.screen, COL_FLAG, [(pole.right, y+10), (pole.right+26, y+22), (pole.right, y+34)])

        for item in self.items:
            item.draw(self.screen, camx, camy)

        for enemy in self.enemies:
            enemy.draw(self.screen, camx, camy)

        for p in self.particles: p.draw(self.screen, camx, camy)
        self.player.draw(self.screen, camx, camy)

    def draw_ui(self):
        timg = self.font.render(f"Zeit: {self.time:0.2f}s", True, COL_TEXT); self.screen.blit(timg, (16, 12))
        cimg = self.font.render(f"Coins: {self.coins_got}/{self.coins_total}", True, COL_TEXT); self.screen.blit(cimg, (16, 44))
        sprint = "an" if (self.player.sprint and self.player.dash_t<=0) else "aus"
        crouch = "an" if self.player.crouch else "aus"
        s_dash = "freigeschaltet" if self.player.dash_unlocked else "gesperrt"
        form = "groß" if self.player.form == "big" else "klein"
        simg = self.font_small.render(
            f"Dash: {s_dash}   |   Sprint: {sprint}   |   Ducken: {crouch}   |   Form: {form}",
            True,
            COL_DIM,
        )
        self.screen.blit(simg, (16, 72))
        best = load_save().get("best_time")
        if best is not None:
            bimg = self.font_small.render(f"Bestzeit: {best:0.2f}s", True, COL_DIM)
            self.screen.blit(bimg, (16, 96))

        pr = self.player.rect
        for x1,y1,x2,y2,text,cond in self.hints:
            if cond == "locked" and self.player.dash_unlocked: continue
            if cond == "unlocked" and not self.player.dash_unlocked: continue
            if pr.colliderect(pygame.Rect(x1,y1,x2-x1,y2-y1)):
                tip = self.font_small.render(text, True, (220,230,255))
                bg = tip.get_rect(); bg.topleft = (16, HEIGHT-48); bg.inflate_ip(16, 10)
                shade = pygame.Surface(bg.size, pygame.SRCALPHA)
                pygame.draw.rect(shade, (20,26,40,180), shade.get_rect(), border_radius=8)
                self.screen.blit(shade, bg); self.screen.blit(tip, (bg.x+8, bg.y+4))
                break

        if hasattr(self, "toast_t") and self.toast_t > 0 and self.toast:
            tip = self.font.render(self.toast, True, (255,255,255))
            bg = tip.get_rect(center=(WIDTH//2, 36)); bg.inflate_ip(24, 14)
            shade = pygame.Surface(bg.size, pygame.SRCALPHA)
            pygame.draw.rect(shade, (20,26,40,200), shade.get_rect(), border_radius=10)
            self.screen.blit(shade, bg); self.screen.blit(tip, tip.get_rect(center=bg.center))

    def draw_end(self, win=True):
        msg = "LEVEL GESCHAFFT!" if win else "UPS! VERSUCH'S NOCHMAL"
        sub = "SPACE: Neustart   ESC: Beenden"
        best_time = load_save().get("best_time")
        if win and (best_time is None or self.time < best_time):
            data = load_save(); data["best_time"] = self.time; save_save(data)
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA); shade.fill((0,0,0,140))
        self.screen.blit(shade, (0,0))
        t = self.font_big.render(msg, True, (255, 240, 180) if win else (255, 190, 190))
        self.screen.blit(t, t.get_rect(center=(WIDTH//2, HEIGHT//2 - 40)))
        s = self.font.render(f"Zeit: {self.time:0.2f}s", True, COL_TEXT)
        self.screen.blit(s, s.get_rect(center=(WIDTH//2, HEIGHT//2 + 10)))
        s2 = self.font_small.render(sub, True, COL_DIM)
        self.screen.blit(s2, s2.get_rect(center=(WIDTH//2, HEIGHT//2 + 48)))

    def run(self):
        while True:
            dt = self.clock.tick(FPS)/1000.0
            for e in pygame.event.get():
                if e.type == pygame.QUIT: pygame.quit(); raise SystemExit
                if e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_ESCAPE: pygame.quit(); raise SystemExit
                    if e.key == pygame.K_SPACE and self.state in ("DEAD","WIN"): self.reset()

            if self.state == "RUN": self.update(dt)

            self.draw_bg(); self.draw_world(); self.draw_ui()
            if self.state == "DEAD": self.draw_end(win=False)
            elif self.state == "WIN": self.draw_end(win=True)
            pygame.display.flip()

# ------------- main -------------
def main():
    parser = argparse.ArgumentParser(description="Dash-Platformer starten")
    parser.add_argument(
        "--level",
        dest="level",
        help=(
            "Pfad zu einer Level-Datei (JSON oder Text). "
            "Fehlt der Parameter, wird zuerst die Umgebungsvariable "
            "PLATFORMER_LEVEL_FILE und dann custom_level.json geprüft."
        ),
    )
    args = parser.parse_args()

    global LEVEL, LEVEL_SOURCE
    LEVEL, LEVEL_SOURCE = load_level(args.level, return_source=True)

    if LEVEL_SOURCE:
        print(f"Level geladen aus: {LEVEL_SOURCE}")
    else:
        print("Standardlevel wird verwendet.")

    Game().run()


if __name__ == "__main__":
    main()
