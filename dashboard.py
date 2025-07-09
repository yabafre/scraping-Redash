import customtkinter as ctk
import asyncio
import httpx
import threading
import logging
import os
import time
import math
import random
import platform
import glob
from datetime import datetime, timedelta
from dotenv import load_dotenv
from PIL import Image, ImageTk, ImageDraw
import tkinter as tk

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def lighten(hex_color: str, factor: float = 0.7) -> str:
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    r = int(r + (255 - r) * factor)
    g = int(g + (255 - g) * factor)
    b = int(b + (255 - b) * factor)
    return f"#{r:02x}{g:02x}{b:02x}"

def darken(hex_color: str, factor: float = 0.3) -> str:
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    r = int(r * (1 - factor))
    g = int(g * (1 - factor))
    b = int(b * (1 - factor))
    return f"#{r:02x}{g:02x}{b:02x}"

def ceil_signed(x: float) -> int:
    return math.ceil(x) if x >= 0 else math.floor(x)

def format_evolution(x: float) -> float:
    return x

def get_dynamic_titles():
    now = datetime.now()
    last_year = now - timedelta(days=365)
    titles = {
        0: "Évolution",
        1: f"CA {last_year.strftime('%d/%m/%Y')} à {now.strftime('%Hh%M')}",
        2: f"CA {now.strftime('%d/%m/%Y')} à {now.strftime('%Hh%M')}"
    }
    return titles

# ─────────────────────────────────────────────
# Data layer
# ─────────────────────────────────────────────

class RedashScraper:
    _client: httpx.AsyncClient | None = None
    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        if RedashScraper._client is None:
            RedashScraper._client = httpx.AsyncClient(timeout=10.0)
        self.client = RedashScraper._client

    async def execute_query(self, query_id: int) -> dict:
        url = f"{self.base_url}/api/queries/{query_id}/results.json"
        resp = await self.client.get(url, params={"api_key": self.api_key})
        resp.raise_for_status()
        return resp.json()

# ─────────────────────────────────────────────
# Animation Components
# ─────────────────────────────────────────────

class ConfettiAnimation:
    def __init__(self, parent_window):
        self.parent_window = parent_window
        self.canvas = None
        self.particles = []
        self.animation_running = False
        self.message_text = ""
        self.message_color = "#FFFFFF"
        self.bg_color = "#212121"
        self.gift_frames = []
        self.gif_frame_index = 0
        self.gif_delay = 100
        self.current_gif_path = ""

    def load_gif(self, gif_path):
        """Charge un GIF et extrait toutes ses frames"""
        try:
            self.gift_frames = []
            gif = Image.open(gif_path)

            # Extraire toutes les frames du GIF
            frame_count = 0
            while True:
                try:
                    gif.seek(frame_count)
                    frame = gif.copy()
                    # Redimensionner le frame pour l'affichage
                    frame = frame.resize((500, 400), Image.Resampling.LANCZOS)
                    # Convertir en PhotoImage pour tkinter
                    photo = ImageTk.PhotoImage(frame)
                    self.gift_frames.append(photo)
                    frame_count += 1
                except EOFError:
                    break

            # Récupérer le délai d'animation du GIF
            try:
                self.gif_delay = gif.info.get('duration', 100)
            except:
                self.gif_delay = 100

            self.gif_frame_index = 0
            self.current_gif_path = gif_path
            logger.info(f"GIF chargé: {gif_path} avec {len(self.gift_frames)} frames")
            return True

        except Exception as e:
            logger.error(f"Erreur lors du chargement du GIF {gif_path}: {e}")
            return False

    def get_appropriate_gif(self, threshold):
        """Retourne le chemin du GIF approprié selon le seuil"""
        abs_threshold = abs(threshold)
        if threshold > 0:
            if abs_threshold >= 20:
                return "gifts/gift_wow.gif"  # Très bon résultat
            else:
                return "gifts/gift_bof.gif"  # Résultat moyen
        else:
            return "gifts/gift_nul.gif"  # Résultat négatif

    def start_animation(self, positive=True, message="", threshold=10):
        if self.animation_running:
            return

        self.animation_running = True
        self.message_text = message
        self.message_color = "#FFFFFF"  # Toujours blanc

        # Charger le GIF approprié
        gif_path = self.get_appropriate_gif(threshold)
        self.load_gif(gif_path)

        canvas_width = self.parent_window.winfo_width()
        canvas_height = self.parent_window.winfo_height()

        # Couleur de fond selon si c'est positif ou négatif
        self.bg_color = "#1B5E20" if positive else "#B71C1C"  # Vert foncé si positif, rouge foncé si négatif

        self.canvas = tk.Canvas(
            self.parent_window,
            highlightthickness=0,
            width=canvas_width,
            height=canvas_height,
            bg=self.bg_color,
            relief='flat',
            borderwidth=0
        )
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)

        self.particles.clear()

        # Réinitialiser le compteur d'animation
        self._animation_frame_count = 0

        # Zone centrale pour le message (éviter les confettis dans cette zone)
        center_x = canvas_width // 2
        center_y = canvas_height // 2
        message_zone_width = 800
        message_zone_height = 600  # Augmenté pour inclure le GIF plus grand

        # Générer les confettis seulement si c'est positif
        if positive:
            for _ in range(40):
                # Générer des positions qui évitent la zone du message
                while True:
                    x = random.uniform(0, canvas_width)
                    y = random.uniform(-canvas_height//2, 0)

                    # Vérifier si la particule va passer dans la zone du message
                    future_y = y + canvas_height  # Position approximative quand elle sera au centre
                    if not (center_x - message_zone_width//2 < x < center_x + message_zone_width//2 and
                           center_y - message_zone_height//2 < future_y < center_y + message_zone_height//2):
                        break

                vx = random.uniform(-3, 3)
                vy = random.uniform(1, 4)
                color = random.choice(['#00C853', '#FF1744', '#00BCD4', '#FFC107', '#9C27B0', '#FF5722'])
                size = random.uniform(8, 15)
                angle = random.uniform(0, 360)
                self.particles.append({
                    'x': x, 'y': y, 'vx': vx, 'vy': vy, 'color': color, 'size': size, 'angle': angle, 'spin': random.uniform(-8, 8)
                })
        self._animate()

    def _animate(self):
        if not self.animation_running:
            return
        self.canvas.delete("all")

        # Dessiner les confettis seulement s'il y en a
        alive_particles = []
        canvas_height = self.canvas.winfo_height()
        canvas_width = self.canvas.winfo_width()

        for p in self.particles:
            p['x'] += p['vx']
            p['y'] += p['vy']
            p['vy'] += 0.15
            p['angle'] += p['spin']
            p['vx'] *= 0.999
            if p['y'] < canvas_height + 20:
                alive_particles.append(p)
                size = p['size']
                angle_rad = math.radians(p['angle'])
                hw = size * 0.6
                hh = size * 0.3
                cos_a = math.cos(angle_rad)
                sin_a = math.sin(angle_rad)
                points = []
                corners = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
                for cx, cy in corners:
                    rx = cx * cos_a - cy * sin_a + p['x']
                    ry = cx * sin_a + cy * cos_a + p['y']
                    points.extend([rx, ry])
                self.canvas.create_polygon(points, fill=p['color'], outline='', width=0)

        # Dessiner le message au centre par-dessus les confettis
        if self.message_text:
            center_x = canvas_width // 2
            center_y = canvas_height // 2

            # Fond de la même couleur que le canvas avec transparence
            self.canvas.create_rectangle(
                center_x - 400, center_y - 250,
                center_x + 400, center_y + 250,
                fill=self.bg_color, outline=""
            )

            # Texte du message (taille augmentée de 6px : 42 + 6 = 48px)
            self.canvas.create_text(
                center_x, center_y - 150,
                text=self.message_text,
                font=("Montserrat", 48, "bold"),
                fill=self.message_color,
                anchor="center"
            )

            # Affichage du GIF animé en dessous du texte avec gap
            if self.gift_frames and len(self.gift_frames) > 0:
                current_frame = self.gift_frames[self.gif_frame_index]
                self.canvas.create_image(
                    center_x, center_y + 120,
                    image=current_frame,
                    anchor="center"
                )
                # Passer à la frame suivante
                self.gif_frame_index = (self.gif_frame_index + 1) % len(self.gift_frames)

        self.particles = alive_particles
        
        # Continuer l'animation tant qu'il y a des particules OU qu'on a un message à afficher
        # Pour les cas négatifs sans confettis, on limite à 3.5 secondes (environ 110 frames à 32ms)
        if len(self.particles) > 0 or (self.message_text and hasattr(self, '_animation_frame_count')):
            if not hasattr(self, '_animation_frame_count'):
                self._animation_frame_count = 0
            self._animation_frame_count += 1
            
            # Arrêter après ~3.5 secondes si pas de confettis
            if len(self.particles) == 0 and self._animation_frame_count > 110:
                self.stop_animation()
            else:
                self.parent_window.after(32, self._animate)
        else:
            self.stop_animation()

    def stop_animation(self):
        self.animation_running = False
        if self.canvas:
            self.canvas.destroy()
            self.canvas = None
        self.particles = []

# ─────────────────────────────────────────────
# UI layer
# ─────────────────────────────────────────────

class DashboardApp(ctk.CTk):
    COLORS = {"positive": "#00C853", "negative": "#FF1744", "neutral": "#9E9E9E"}

    def __init__(self, base_url: str, cfgs: list[dict]):
        super().__init__()
        self.title("Dashboard Ventes")
        self.attributes("-fullscreen", True)
        self.bind("<Escape>", lambda *_: self.attributes("-fullscreen", False))
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        self.scrapers = [RedashScraper(c["api_key"], base_url) for c in cfgs]
        self.queries = [c["id"] for c in cfgs]
        self.mappings = [c["mapping"] for c in cfgs]
        self.units = {0: "%", 1: "€", 2: "€"}
        self.last_gift = {0: 0, 1: 0, 2: 0}

        self.test_mode = False
        self.logo_image = None
        self._last_ratios = {}  # Pour suivre les évolutions
        self.load_logo()
        self.confetti_animation = ConfettiAnimation(self)
        self._build_ui()
        self.bind_all("<KeyPress>", self._on_keypress)
        self._tick()
        self.after(1000, self.check_confetti_prerequisites)


        self._test_keys_pressed = set()

    def load_logo(self):
        logo_extensions = ['*.png', '*.PNG', '*.jpg', '*.JPG', '*.jpeg', '*.JPEG']
        for pattern in logo_extensions:
            for path in glob.glob(pattern):
                try:
                    image = Image.open(path).convert('RGBA')
                    # Resize ONLY, pas de fond blanc
                    original_width, original_height = image.size
                    
                    # D'abord réduire la taille du logo à 80% de sa taille originale
                    new_width = int(original_width * 0.8)
                    new_height = int(original_height * 0.8)
                    
                    # Ensuite, s'assurer que la largeur ne dépasse pas 198px
                    if new_width > 198:
                        ratio = 198 / new_width
                        new_width = 198
                        new_height = int(new_height * ratio)
                    elif new_width < 198:
                        # Si trop petit après réduction, agrandir jusqu'à 198px
                        ratio = 198 / new_width
                        new_width = 198
                        new_height = int(new_height * ratio)
                        
                    image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    self.logo_image = ctk.CTkImage(light_image=image, dark_image=image, size=image.size)
                    logger.info(f"Logo chargé (sans fond ajouté) : {path}")
                    return
                except Exception as e:
                    logger.warning(f"Erreur lors du chargement du logo {path}: {e}")
        logger.warning("Aucun logo trouvé dans le répertoire courant")


    def _build_ui(self):
        self.grid_rowconfigure((0, 1), weight=1)
        self.grid_columnconfigure((0, 1), weight=1)
        titles_dict = get_dynamic_titles()
        titles = [titles_dict[0], titles_dict[1], titles_dict[2]]
        pos = [(0, 0), (0, 1), (1, 0)]
        self.q = {}
        for i, ((r, c), title) in enumerate(zip(pos, titles)):
            frame = ctk.CTkFrame(self, corner_radius=14)
            if i == 2:
                frame.grid(row=r, column=c, columnspan=2, padx=14, pady=14, sticky="nsew")
            else:
                frame.grid(row=r, column=c, padx=14, pady=14, sticky="nsew")
            header_frame = ctk.CTkFrame(frame, fg_color="transparent")
            header_frame.pack(pady=12, fill="x")
            title_label = ctk.CTkLabel(
                header_frame,
                text=title,
                font=("Montserrat", 24, "bold"),
                text_color="#000000"
            )
            title_label.pack(anchor="center")
            val = ctk.CTkLabel(frame, text="--", font=("Montserrat", 76, "bold"), text_color="#ffffff")
            val.pack(expand=True)
            if i == 0:
                inspiration = ctk.CTkLabel(
                    frame,
                    text="",
                    font=("Montserrat", 22, "italic"),
                    text_color="#888888"
                )
                inspiration.pack(pady=(0, 20), expand=True)
                self.q[i] = {"frame": frame, "val": val, "title": title_label, "inspiration": inspiration}
            else:
                trend = ctk.CTkLabel(frame, text="→", font=("Montserrat", 40), text_color="#ffffff")
                trend.pack(pady=6)
                self.q[i] = {"frame": frame, "val": val, "trend": trend, "title": title_label}

        # -- Config/test panel (hidden by default)
        self.test_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.test_frame.place(relx=0.02, rely=0.02)
        self.test_frame.lower()
        self.test_frame.place_forget()  # hide at start

        # Test buttons inside test_frame
        test_confetti_btn = ctk.CTkButton(
            self.test_frame, text="Test Confettis", command=self._test_confetti, width=120, height=30, font=("Montserrat", 12))
        test_confetti_btn.pack(pady=2)
        toggle_test_btn = ctk.CTkButton(
            self.test_frame, text="Mode Test", command=self._toggle_test_mode, width=120, height=30, font=("Montserrat", 12))
        toggle_test_btn.pack(pady=2)
        simulate_btn = ctk.CTkButton(
            self.test_frame, text="Simuler Données", command=self._simulate_test_data, width=120, height=30, font=("Montserrat", 12))
        simulate_btn.pack(pady=2)
        reset_btn = ctk.CTkButton(
            self.test_frame, text="Reset", command=self._reset_test_state, width=120, height=30, font=("Montserrat", 12))
        reset_btn.pack(pady=2)
        help_label = ctk.CTkLabel(
            self.test_frame,
            text="Ctrl+T: Confettis\nCtrl+S: Simulation\nCtrl+R: Reset",
            font=("Montserrat", 10),
            text_color="#666666",
            justify="left"
        )
        help_label.pack(pady=(10, 0))

        # Block notification fullscreen (hidden at start)
        self.celebration_frame = ctk.CTkFrame(self, fg_color="#212121", corner_radius=18)
        self.celebration_frame.place(relx=0.5, rely=0.5, anchor="center", relwidth=1, relheight=1)
        self.celebration_label = ctk.CTkLabel(self.celebration_frame, text="", font=("Montserrat", 42, "bold"))
        self.celebration_label.pack(expand=True, pady=30)
        self.celebration_gift = ctk.CTkLabel(self.celebration_frame, image=None, text="", font=("Montserrat", 32))
        self.celebration_gift.pack()
        self.celebration_frame.place_forget()

        if self.logo_image:
            # Créer un fond pour le logo (couleur par défaut)
            self.logo_bg = ctk.CTkFrame(self, fg_color="#FFFFFF", corner_radius=12)
            self.logo_bg.place(relx=0.0, rely=0.0, anchor="nw", x=20, y=20)

            self.logo_label = ctk.CTkLabel(
                self.logo_bg, image=self.logo_image, text="", fg_color="transparent"
            )
            self.logo_label.pack(padx=10, pady=10)
            self.logo_label.lift()
            self.logo_label.update()

        self.ts = ctk.CTkLabel(self, text="", font=("Montserrat", 18), text_color="#888888")
        self.ts.place(relx=1, rely=1, anchor="se", x=-16, y=-16)

    # ──────────────────────────────────────────
    # KEYBIND: Alt+2+3 → toggle test menu
    # ──────────────────────────────────────────
    def _maybe_show_test_panel(self, event):
        self._test_keys_pressed.add(event.keysym)
        # Combo Alt+2+3: show/hide config test panel
        if "2" in self._test_keys_pressed and "3" in self._test_keys_pressed:
            if self.test_frame.winfo_ismapped():
                self.test_frame.place_forget()
            else:
                self.test_frame.place(relx=0.02, rely=0.02)
            self._test_keys_pressed.clear()
        else:
            # auto clear after 1s to éviter stuck
            self.after(1000, lambda: self._test_keys_pressed.clear())

    # ──────────────────────────────────────────
    # KEYBIND: Alt+T → toggle test menu
    # ──────────────────────────────────────────
    def _on_keypress(self, event):
        print(f"KEYPRESS DEBUG: key={event.keysym} state={event.state} char={event.char} keycode={event.keycode}")
        is_mac = platform.system() == "Darwin"
        key = event.keysym.lower()
        shift = (event.state & 0x1) != 0
        meta = (event.state & 0x8) != 0
        ctrl = (event.state & 0x4) != 0
        # Mac: Cmd+Shift+C, PC: Ctrl+Shift+C
        if (is_mac and key == 'c' and shift and meta) or (not is_mac and key == 'c' and shift and ctrl):
            self._toggle_test_panel()


    # ──────────────────────────────────────────
    # Affiche/Cache le panel test
    # ──────────────────────────────────────────
    def _toggle_test_panel(self, event=None):
        if self.test_frame.winfo_ismapped():
            self.test_frame.place_forget()
        else:
            self.test_frame.place(relx=0.02, rely=0.02)
            self.test_frame.lift()
            self.test_frame.tkraise()


    # ──────────────────────────────────────────
    # Test Methods
    # ──────────────────────────────────────────
    def _test_confetti(self):
        logger.info("Test des confettis déclenché")
        self.confetti_animation.start_animation(positive=True, message="10% Atteint", threshold=10)
        # Plus besoin d'afficher le block de célébration séparé
        self.after(3500, lambda: None)  # Juste un délai pour le test

    def _toggle_test_mode(self):
        self.test_mode = not self.test_mode
        logger.info(f"Mode test: {'ACTIVÉ' if self.test_mode else 'DÉSACTIVÉ'}")

    def _simulate_test_data(self, event=None):
        logger.info("Simulation de données de test")
        test_ratios = [5.0, 10.0, 20.0, -10.0, -20.0]
        for i, ratio in enumerate(test_ratios):
            self.after(i * 2000, lambda r=ratio: self._update_quad(0, r, r))

    def _reset_test_state(self, event=None):
        logger.info("Reset de l'état des tests")
        self.last_gift = {0: 0, 1: 0, 2: 0}
        self.confetti_animation.stop_animation()
        self._hide_celebration_block()

    def check_confetti_prerequisites(self):
        logger.info("Vérification des prérequis confettis:")
        logger.info(f"- Fenêtre dimensions: {self.winfo_width()}x{self.winfo_height()}")
        logger.info(f"- Animation instance: {self.confetti_animation}")
        logger.info(f"- Last gift status: {self.last_gift}")
        try:
            test_canvas = tk.Canvas(self, width=100, height=100)
            test_canvas.destroy()
            logger.info("- Canvas test: OK")
        except Exception as e:
            logger.error(f"- Canvas test: ERREUR {e}")

    # ──────────────────────────────────────────
    # Scheduler
    # ──────────────────────────────────────────
    def _tick(self):
        self._refresh()
        self.after(5_000, self._tick)

    # ──────────────────────────────────────────
    # Data fetch
    # ──────────────────────────────────────────
    def _refresh(self):
        async def fetch():
            if self.test_mode:
                for idx in range(3):
                    if idx == 0:
                        value = random.uniform(-30, 30)
                        ratio = value
                    else:
                        value = random.uniform(1000, 50000)
                        ratio = random.uniform(-10, 20)
                    self.after(0, self._update_quad, idx, value, ratio)
                self.after(0, lambda: self.ts.configure(text=f"Mode TEST - {datetime.now():%H:%M:%S}"))
                return
            for idx, (scr, qid, mp) in enumerate(zip(self.scrapers, self.queries, self.mappings)):
                t0 = time.perf_counter()
                try:
                    data = await scr.execute_query(qid)
                    logger.info("Query %s en %.2fs", qid, time.perf_counter() - t0)
                    rows = data.get("query_result", {}).get("data", {}).get("rows", [])
                    if not rows:
                        continue
                    row = rows[0]
                    value = float(row.get(mp["value"], 0))
                    ratio = float(row.get(mp["ratio"], 0))
                    logger.info("Query %s: value=%s, ratio=%s", qid, value, ratio)
                    self.after(0, self._update_quad, idx, value, ratio)
                except Exception as e:
                    logger.error(f"Erreur query {qid}: {e}")
            self.after(0, lambda: self.ts.configure(text=f"Dernière mise à jour : {datetime.now():%H:%M:%S}"))

        asyncio.run_coroutine_threadsafe(fetch(), self.loop)

    # ──────────────────────────────────────────
    # UI update
    # ──────────────────────────────────────────
    def _update_quad(self, idx: int, value: float, ratio: float):
        unit = self.units[idx]
        color, arrow = self._style(ratio)
        lighter = lighten(color, 0.85)
        title_color = "#000000"
        
        # Sauvegarder le ratio pour mise à jour du logo
        self._last_ratios[idx] = ratio
        
        titles_dict = get_dynamic_titles()
        self.q[idx]["title"].configure(text=titles_dict[idx], text_color=title_color)
        formatted_value = f"{format_evolution(value)}{unit}" if idx == 0 else self._fmt(value, unit)
        self.q[idx]["val"].configure(text=formatted_value, text_color=color)
        if idx == 0:
            pass
        else:
            trend_txt = f"{arrow} {ceil_signed(ratio)}%" if unit == "%" else arrow
            self.q[idx]["trend"].configure(text=trend_txt, text_color=color)
        self.q[idx]["frame"].configure(fg_color=lighter)
        if idx == 0:
            if ratio > 0:
                self.q[idx]["inspiration"].configure(
                    text=" 1% d'inspiration et 99% de transpiration.",
                    text_color="#000000"
                )
            elif ratio < 0:
                self.q[idx]["inspiration"].configure(
                    text=" Il n'y a de vie que dans les marges.",
                    text_color="#FF6B6B"
                )
            else:
                self.q[idx]["inspiration"].configure(
                    text=" L'équilibre est la clé du succès.",
                    text_color="#87CEEB"
                )

        # ----- FULLSCREEN CELEBRATION / WARNING -----
        if idx == 0:
            # Multiples de 10 positif (10, 20, 30, ...)
            if ratio >= 10:
                current_threshold = int(ratio // 10) * 10
                if current_threshold > self.last_gift[idx]:
                    self.last_gift[idx] = current_threshold
                    message = f"{current_threshold}% Atteint"
                    self.confetti_animation.start_animation(positive=True, message=message, threshold=current_threshold)
                    self._show_celebration_block(current_threshold, positive=True)
            # Multiples de 10 négatif (-10, -20, -30, ...)
            elif ratio <= -10:
                current_threshold = int(ratio // 10) * 10
                if current_threshold < self.last_gift[idx]:
                    self.last_gift[idx] = current_threshold
                    message = f"{current_threshold}% En Baisse"  # Garde le signe négatif
                    self.confetti_animation.start_animation(positive=False, message=message, threshold=current_threshold)
                    self._show_celebration_block(current_threshold, positive=False)
            else:
                # Auto-hide celebration if not at a multiple anymore
                self._hide_celebration_block()

        # Mettre à jour le fond du logo si c'est le premier quad
        if idx == 0:
            self._update_logo_background()

    # ──────────────────────────────────────────
    # Fullscreen "celebration" block
    # ──────────────────────────────────────────
    def _show_celebration_block(self, threshold: int, positive: bool = True):
        # Le message est maintenant intégré dans l'animation de confettis
        message = f"{abs(threshold)}% {'Atteint' if positive else 'En Baisse'}"
        # Plus besoin d'afficher le frame de célébration car tout est dans le canvas
        self.after(3500 if positive else 2500, self._hide_celebration_block)

    def _hide_celebration_block(self):
        # Plus besoin de cacher le frame car tout est géré par l'animation
        self.confetti_animation.stop_animation()

    # ──────────────────────────────────────────
    # Utils
    # ──────────────────────────────────────────
    def _style(self, r: float):
        if r > 0:
            return self.COLORS["positive"], "↗"
        if r < 0:
            return self.COLORS["negative"], "↘"
        return self.COLORS["neutral"], "→"

    @staticmethod
    def _fmt(num: float, unit: str):
        if unit == "€":
            return f"{ceil_signed(num):,}€".replace(",", " ")
        return f"{ceil_signed(num)}{unit}"

    def _update_logo_background(self):
        """Met à jour le fond du logo selon l'évolution du premier quad (idx=0)"""
        if hasattr(self, 'logo_bg') and len(self.q) > 0:
            try:
                # Récupérer la dernière évolution du premier quad
                if hasattr(self, '_last_ratios') and 0 in self._last_ratios:
                    ratio = self._last_ratios[0]
                    color, _ = self._style(ratio)
                    lighter = lighten(color, 0.9)  # Un peu plus clair que les blocks
                    self.logo_bg.configure(fg_color=lighter)
            except Exception as e:
                logger.error(f"Erreur lors de la mise à jour du fond du logo: {e}")

# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    load_dotenv()
    base_url = os.getenv("REDASH_BASE_URL", "").strip()
    if not base_url:
        raise SystemExit("REDASH_BASE_URL manquant dans .env")
    cfgs = [
        {"id": 111, "api_key": os.getenv("KEY_EVOL", ""), "mapping": {"value": "EVOL", "ratio": "EVOL"}},
        {"id": 110, "api_key": os.getenv("KEY_CA_J1", ""), "mapping": {"value": "CA", "ratio": "AVG"}},
        {"id": 109, "api_key": os.getenv("KEY_CA_JN", ""), "mapping": {"value": "CA", "ratio": "AVG"}},
    ]
    DashboardApp(base_url, cfgs).mainloop()

if __name__ == "__main__":
    main()
