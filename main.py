import pygame
import random
import math

from characters import CharacterTemplate, CHARACTERS
from projectile import Projectile
from venue import Arena


# ── Constants ────────────────────────────────────────────────────────────────
WIDTH, HEIGHT = 800, 800
CENTER = (WIDTH // 2, HEIGHT // 2)
ARENA_RADIUS = 350
FPS = 60

PLAYER_RADIUS = 20
INITIAL_HP = 100

ARENA_BG = (30, 30, 40)
ARENA_BORDER = (80, 80, 100)
TEXT_COLOR = (220, 220, 220)
SELECT_BG = (20, 20, 30)


# ── Player ───────────────────────────────────────────────────────────────────
class Player:
    def __init__(self, x, y, char: CharacterTemplate):
        self.x = float(x)
        self.y = float(y)
        self.vx = random.uniform(-1.5, 1.5)
        self.vy = random.uniform(-1.5, 1.5)
        self.char = char
        self.hp = INITIAL_HP
        self.radius = PLAYER_RADIUS
        self.alive = True
        self.skill_timer = 0.0  # counts up to skill.cooldown

    def update(self, arena=None):
        if not self.alive:
            return

        # Random acceleration (physics-based perturbation)
        ax = random.uniform(-0.25, 0.25)
        ay = random.uniform(-0.25, 0.25)

        # Occasionally apply a stronger directional change
        if random.random() < 0.02:
            ax += random.uniform(-0.7, 0.7)
            ay += random.uniform(-0.7, 0.7)

        self.vx += ax
        self.vy += ay

        # Friction damping
        self.vx *= 0.995
        self.vy *= 0.995

        # Speed cap from character template
        speed = math.hypot(self.vx, self.vy)
        if speed > self.char.speed:
            self.vx = self.vx / speed * self.char.speed
            self.vy = self.vy / speed * self.char.speed

        self.x += self.vx
        self.y += self.vy

        # Arena boundary collision (with segment effects)
        if arena is not None:
            segment = arena.resolve_boundary(self)
            if segment:
                arena.apply_effect(self, segment)

    def draw(self, screen, font_small):
        pygame.draw.circle(screen, self.char.color, (int(self.x), int(self.y)), self.radius)
        pygame.draw.circle(screen, (60, 60, 60), (int(self.x), int(self.y)), self.radius, 2)
        # Name label above player
        name_surf = font_small.render(self.char.name, True, self.char.color)
        screen.blit(name_surf, (self.x - name_surf.get_width() // 2, self.y - self.radius - 22))

    def take_damage(self, amount):
        self.hp -= amount
        if self.hp <= 0:
            self.hp = 0
            self.alive = False


# ── Game ─────────────────────────────────────────────────────────────────────
class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("角斗场 Arena")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("WenQuanYi Micro Hei", 28, bold=True)
        self.font_small = pygame.font.SysFont("WenQuanYi Micro Hei", 16)
        self.font_large = pygame.font.SysFont("WenQuanYi Micro Hei", 56, bold=True)
        self.font_title = pygame.font.SysFont("WenQuanYi Micro Hei", 40, bold=True)
        self.running = True

        # State machine: "select_p1" | "select_p2" | "fighting" | "game_over"
        self.state = "select_p1"
        self.selection = [None, None]  # selected character indices for p1, p2
        self.player1 = None
        self.player2 = None
        self.projectiles: list[Projectile] = []
        self.arena = Arena()
        self.game_over = False
        self.winner = None

    # ── Selection screen ─────────────────────────────────────────────────────
    def handle_selection_input(self, event):
        if event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_ESCAPE:
            self.running = False
            return
        if event.key not in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
            return

        idx = event.key - pygame.K_1
        if idx >= len(CHARACTERS):
            return

        if self.state == "select_p1":
            self.selection[0] = idx
            self.state = "select_p2"
        elif self.state == "select_p2":
            if idx == self.selection[0]:
                return  # can't pick same character
            self.selection[1] = idx
            self.start_match()

    def draw_selection_screen(self):
        self.screen.fill(SELECT_BG)

        # Title
        title = self.font_title.render("角斗场 — 选择出战角色", True, TEXT_COLOR)
        self.screen.blit(title, (CENTER[0] - title.get_width() // 2, 40))

        # Prompt
        if self.state == "select_p1":
            prompt_text = "按 1-4 选择 左方 角色"
        else:
            c = CHARACTERS[self.selection[0]]
            prompt_text = f"已选左方: {c.name}  —  按 1-4 选择 右方 角色（不可重复）"
        prompt = self.font.render(prompt_text, True, (180, 180, 180))
        self.screen.blit(prompt, (CENTER[0] - prompt.get_width() // 2, 100))

        # Character cards
        card_w, card_h = 160, 280
        total_w = len(CHARACTERS) * card_w + (len(CHARACTERS) - 1) * 20
        start_x = CENTER[0] - total_w // 2
        card_y = 160

        for i, char in enumerate(CHARACTERS):
            cx = start_x + i * (card_w + 20)
            rect = pygame.Rect(cx, card_y, card_w, card_h)

            # Highlight selected character
            is_selected_p1 = self.selection[0] == i
            is_selected = is_selected_p1

            if is_selected:
                border_color = (255, 215, 0)
                bg_color = (50, 50, 60)
            elif self.state == "select_p2" and self.selection[0] == i:
                border_color = (100, 100, 100)
                bg_color = (35, 35, 45)
            else:
                border_color = (70, 70, 80)
                bg_color = (35, 35, 45)

            pygame.draw.rect(self.screen, bg_color, rect, border_radius=10)
            pygame.draw.rect(self.screen, border_color, rect, 2, border_radius=10)

            # Character color circle
            circle_cx = cx + card_w // 2
            pygame.draw.circle(self.screen, char.color, (circle_cx, card_y + 50), 30)
            pygame.draw.circle(self.screen, (60, 60, 60), (circle_cx, card_y + 50), 30, 2)

            # Name
            name_surf = self.font_small.render(char.name, True, char.color)
            self.screen.blit(name_surf, (cx + card_w // 2 - name_surf.get_width() // 2, card_y + 100))

            # Skill name
            skill_label = self.font_small.render(f"技能: {char.skill.name}", True, TEXT_COLOR)
            self.screen.blit(skill_label, (cx + card_w // 2 - skill_label.get_width() // 2, card_y + 130))

            # Stats
            speed_surf = self.font_small.render(f"速度: {char.speed:.1f}", True, (150, 150, 150))
            self.screen.blit(speed_surf, (cx + card_w // 2 - speed_surf.get_width() // 2, card_y + 155))

            cd_surf = self.font_small.render(f"冷却: {char.skill.cooldown:.1f}s", True, (150, 150, 150))
            self.screen.blit(cd_surf, (cx + card_w // 2 - cd_surf.get_width() // 2, card_y + 175))

            dmg_surf = self.font_small.render(f"伤害: {char.skill.damage}", True, (150, 150, 150))
            self.screen.blit(dmg_surf, (cx + card_w // 2 - dmg_surf.get_width() // 2, card_y + 195))

            # Movement type label
            mt = char.skill.movement_type.value
            mt_surf = self.font_small.render(f"模式: {mt}", True, (150, 150, 150))
            self.screen.blit(mt_surf, (cx + card_w // 2 - mt_surf.get_width() // 2, card_y + 215))

            # Key label
            key_surf = self.font.render(f"[{i + 1}]", True, TEXT_COLOR)
            self.screen.blit(key_surf, (cx + card_w // 2 - key_surf.get_width() // 2, card_y + card_h - 45))

    # ── Match start ──────────────────────────────────────────────────────────
    def start_match(self):
        p1_char = CHARACTERS[self.selection[0]]
        p2_char = CHARACTERS[self.selection[1]]
        self.player1 = Player(CENTER[0] - 100, CENTER[1], p1_char)
        self.player2 = Player(CENTER[0] + 100, CENTER[1], p2_char)

        # Give initial staggered cooldown so they don't fire at the same instant
        self.player1.skill_timer = random.uniform(0, p1_char.skill.cooldown * 0.5)
        self.player2.skill_timer = random.uniform(0, p2_char.skill.cooldown * 0.5)

        self.projectiles = []
        self.game_over = False
        self.winner = None
        self.state = "fighting"

    # ── Skill spawning ───────────────────────────────────────────────────────
    def try_use_skill(self, player: Player):
        if not player.alive:
            return
        if player.skill_timer >= player.char.skill.cooldown:
            player.skill_timer = 0.0
            skill = player.char.skill
            angle = random.uniform(0, 2 * math.pi)
            offset = player.radius + skill.radius + 2
            px = player.x + math.cos(angle) * offset
            py = player.y + math.sin(angle) * offset
            self.projectiles.append(
                Projectile(px, py, player.char.id, skill, owner=player)
            )

    # ── Player-to-player collision ──────────────────────────────────────────
    def resolve_player_collision(self):
        p1 = self.player1
        p2 = self.player2
        if not (p1.alive and p2.alive):
            return

        dx = p1.x - p2.x
        dy = p1.y - p2.y
        dist = math.hypot(dx, dy)
        min_dist = p1.radius + p2.radius

        if dist < min_dist and dist > 0.001:
            # Normal vector from p2 to p1
            nx = dx / dist
            ny = dy / dist

            # Separate players so they just touch
            overlap = min_dist - dist
            p1.x += nx * overlap / 2
            p1.y += ny * overlap / 2
            p2.x -= nx * overlap / 2
            p2.y -= ny * overlap / 2

            # Reflect velocities along collision normal (elastic collision)
            dvx = p1.vx - p2.vx
            dvy = p1.vy - p2.vy
            dv_dot_n = dvx * nx + dvy * ny

            if dv_dot_n < 0:  # moving toward each other
                p1.vx -= dv_dot_n * nx
                p1.vy -= dv_dot_n * ny
                p2.vx += dv_dot_n * nx
                p2.vy += dv_dot_n * ny

    # ── Projectile collision detection ───────────────────────────────────────
    def check_collisions(self):
        for proj in self.projectiles:
            # Player 1 takes damage from player 2's projectiles
            if (proj.owner_id != self.player1.char.id
                    and proj.collides_with(self.player1)
                    and self.player1.alive):
                self.player1.take_damage(proj.skill.damage)
            # Player 2 takes damage from player 1's projectiles
            if (proj.owner_id != self.player2.char.id
                    and proj.collides_with(self.player2)
                    and self.player2.alive):
                self.player2.take_damage(proj.skill.damage)

    # ── Win condition ────────────────────────────────────────────────────────
    def check_win_condition(self):
        if not self.player1.alive:
            self.game_over = True
            self.winner = self.player2.char.name
            self.state = "game_over"
        elif not self.player2.alive:
            self.game_over = True
            self.winner = self.player1.char.name
            self.state = "game_over"

    # ── Rendering ────────────────────────────────────────────────────────────
    def draw_arena(self):
        self.arena.draw(self.screen)

    def draw_hp(self):
        cx, cy = CENTER

        p1 = self.player1
        p2 = self.player2

        # P1 HP bar (left of center)
        hp_ratio_1 = p1.hp / INITIAL_HP
        bar_w, bar_h = 140, 18
        bar_x1 = cx - bar_w - 40
        bar_y = cy - 35

        name1 = self.font_small.render(p1.char.name, True, p1.char.color)
        self.screen.blit(name1, (bar_x1 + bar_w // 2 - name1.get_width() // 2, bar_y - 20))

        pygame.draw.rect(self.screen, (40, 40, 50), (bar_x1, bar_y, bar_w, bar_h), border_radius=4)
        hp_fill_w = int(bar_w * hp_ratio_1)
        if hp_fill_w > 0:
            pygame.draw.rect(self.screen, p1.char.color, (bar_x1, bar_y, hp_fill_w, bar_h), border_radius=4)
        pygame.draw.rect(self.screen, (80, 80, 90), (bar_x1, bar_y, bar_w, bar_h), 1, border_radius=4)

        hp_text1 = self.font_small.render(f"HP {p1.hp}/{INITIAL_HP}", True, TEXT_COLOR)
        self.screen.blit(hp_text1, (bar_x1 + bar_w // 2 - hp_text1.get_width() // 2, bar_y + 1))

        # P2 HP bar (right of center)
        hp_ratio_2 = p2.hp / INITIAL_HP
        bar_x2 = cx + 40
        bar_y = cy - 35

        name2 = self.font_small.render(p2.char.name, True, p2.char.color)
        self.screen.blit(name2, (bar_x2 + bar_w // 2 - name2.get_width() // 2, bar_y - 20))

        pygame.draw.rect(self.screen, (40, 40, 50), (bar_x2, bar_y, bar_w, bar_h), border_radius=4)
        hp_fill_w = int(bar_w * hp_ratio_2)
        if hp_fill_w > 0:
            pygame.draw.rect(self.screen, p2.char.color, (bar_x2, bar_y, hp_fill_w, bar_h), border_radius=4)
        pygame.draw.rect(self.screen, (80, 80, 90), (bar_x2, bar_y, bar_w, bar_h), 1, border_radius=4)

        hp_text2 = self.font_small.render(f"HP {p2.hp}/{INITIAL_HP}", True, TEXT_COLOR)
        self.screen.blit(hp_text2, (bar_x2 + bar_w // 2 - hp_text2.get_width() // 2, bar_y + 1))

        # Center VS
        vs_text = self.font.render("VS", True, TEXT_COLOR)
        self.screen.blit(vs_text, (cx - vs_text.get_width() // 2, cy - vs_text.get_height() // 2))

        # Skill info below center
        skill1 = self.font_small.render(
            f"{p1.char.skill.name} ({p1.char.skill.cooldown:.1f}s)",
            True, p1.char.skill.color)
        self.screen.blit(skill1, (bar_x1 + bar_w // 2 - skill1.get_width() // 2, bar_y + bar_h + 10))

        skill2 = self.font_small.render(
            f"{p2.char.skill.name} ({p2.char.skill.cooldown:.1f}s)",
            True, p2.char.skill.color)
        self.screen.blit(skill2, (bar_x2 + bar_w // 2 - skill1.get_width() // 2, bar_y + bar_h + 10))

    def draw_game_over(self):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.screen.blit(overlay, (0, 0))

        go_text = self.font_large.render("游戏结束", True, (255, 80, 80))
        win_text = self.font.render(f"获胜方: {self.winner}", True, TEXT_COLOR)
        restart_text = self.font_small.render("按 R 重新选择 / 按 Q 退出", True, (180, 180, 180))

        self.screen.blit(go_text, (CENTER[0] - go_text.get_width() // 2, CENTER[1] - 80))
        self.screen.blit(win_text, (CENTER[0] - win_text.get_width() // 2, CENTER[1] - 10))
        self.screen.blit(restart_text, (CENTER[0] - restart_text.get_width() // 2, CENTER[1] + 40))

    # ── Reset ────────────────────────────────────────────────────────────────
    def reset(self):
        self.state = "select_p1"
        self.selection = [None, None]
        self.player1 = None
        self.player2 = None
        self.projectiles = []
        self.game_over = False
        self.winner = None

    # ── Main loop ────────────────────────────────────────────────────────────
    def run(self):
        dt = 1.0 / FPS
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False

                if self.state in ("select_p1", "select_p2"):
                    self.handle_selection_input(event)

                if self.state == "game_over" and event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_r:
                        self.reset()
                    elif event.key == pygame.K_q:
                        self.running = False

            # ── Update ───────────────────────────────────────────────────────
            if self.state == "fighting" and not self.game_over:
                # Skill timers
                self.player1.skill_timer += dt
                self.player2.skill_timer += dt

                self.try_use_skill(self.player1)
                self.try_use_skill(self.player2)

                # Movement
                self.player1.update(self.arena)
                self.player2.update(self.arena)

                # Player-to-player bounce
                self.resolve_player_collision()

                # Update projectiles & remove expired ones
                for proj in self.projectiles:
                    proj.update(dt)
                self.projectiles = [p for p in self.projectiles if not p.is_expired()]

                # Collisions
                self.check_collisions()

                # Win condition
                self.check_win_condition()

            # ── Render ───────────────────────────────────────────────────────
            if self.state in ("select_p1", "select_p2"):
                self.draw_selection_screen()
            else:
                self.draw_arena()

                for proj in self.projectiles:
                    proj.draw(self.screen)

                if self.player1.alive:
                    self.player1.draw(self.screen, self.font_small)
                if self.player2.alive:
                    self.player2.draw(self.screen, self.font_small)

                self.draw_hp()

                if self.game_over:
                    self.draw_game_over()

            pygame.display.flip()
            self.clock.tick(FPS)

        pygame.quit()


if __name__ == "__main__":
    game = Game()
    game.run()
