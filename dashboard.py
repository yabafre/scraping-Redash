import customtkinter as ctk
import asyncio
import httpx
import threading
import logging
import os
import time
import math
import random
from datetime import datetime
from dotenv import load_dotenv
from PIL import Image, ImageTk
import tkinter as tk

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def lighten(hex_color: str, factor: float = 0.7) -> str:
    """Return a lighter 6‑digit hex color (0 < factor < 1 → closer to white)."""
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    r = int(r + (255 - r) * factor)
    g = int(g + (255 - g) * factor)
    b = int(b + (255 - b) * factor)
    return f"#{r:02x}{g:02x}{b:02x}"


def darken(hex_color: str, factor: float = 0.3) -> str:
    """Return a darker 6‑digit hex color (0 < factor < 1 → closer to black)."""
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    r = int(r * (1 - factor))
    g = int(g * (1 - factor))
    b = int(b * (1 - factor))
    return f"#{r:02x}{g:02x}{b:02x}"


def ceil_signed(x: float) -> int:
    """Ceil for positives, floor for negatives to keep sign direction."""
    return math.ceil(x) if x >= 0 else math.floor(x)

# ──────────────────────────────────────────────────────────────────────────────
# Data layer
# ──────────────────────────────────────────────────────────────────────────────

class RedashScraper:
    """Minimal async wrapper around the Redash /results.json endpoint."""

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

# ──────────────────────────────────────────────────────────────────────────────
# Animation Components
# ──────────────────────────────────────────────────────────────────────────────

class ConfettiParticle:
    def __init__(self, x, y, canvas_width, canvas_height):
        self.x = x
        self.y = y
        self.vx = random.uniform(-3, 3)
        self.vy = random.uniform(-8, -3)
        self.gravity = 0.3
        self.color = random.choice(['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD', '#98D8C8'])
        self.size = random.uniform(3, 8)
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
        self.rotation = random.uniform(0, 360)
        self.rotation_speed = random.uniform(-10, 10)
        
    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vy += self.gravity
        self.rotation += self.rotation_speed
        
        # Rebond sur les bords
        if self.x < 0 or self.x > self.canvas_width:
            self.vx *= -0.8
        if self.y > self.canvas_height:
            self.vy *= -0.6
            self.y = self.canvas_height
            
    def is_alive(self):
        return self.y < self.canvas_height + 50 and abs(self.vx) > 0.1

class ConfettiAnimation:
    def __init__(self, parent_frame):
        self.parent_frame = parent_frame
        self.canvas = None
        self.particles = []
        self.animation_running = False
        
    def start_animation(self):
        if self.animation_running:
            return
            
        self.animation_running = True
        
        # Créer le canvas par-dessus le frame
        self.canvas = tk.Canvas(
            self.parent_frame, 
            highlightthickness=0,
            background='',
            width=self.parent_frame.winfo_width(),
            height=self.parent_frame.winfo_height()
        )
        self.canvas.place(x=0, y=0, relwidth=1, relheight=1)
        
        # Créer les particules
        canvas_width = self.canvas.winfo_reqwidth()
        canvas_height = self.canvas.winfo_reqheight()
        
        for _ in range(50):
            x = random.uniform(0, canvas_width)
            y = random.uniform(canvas_height * 0.8, canvas_height)
            self.particles.append(ConfettiParticle(x, y, canvas_width, canvas_height))
        
        self._animate()
        
    def _animate(self):
        if not self.animation_running:
            return
            
        self.canvas.delete("all")
        
        alive_particles = []
        for particle in self.particles:
            particle.update()
            if particle.is_alive():
                alive_particles.append(particle)
                # Dessiner la particule
                self.canvas.create_oval(
                    particle.x - particle.size/2,
                    particle.y - particle.size/2,
                    particle.x + particle.size/2,
                    particle.y + particle.size/2,
                    fill=particle.color,
                    outline=""
                )
        
        self.particles = alive_particles
        
        if len(self.particles) > 0:
            self.parent_frame.after(16, self._animate)  # ~60 FPS
        else:
            self.stop_animation()
            
    def stop_animation(self):
        self.animation_running = False
        if self.canvas:
            self.canvas.destroy()
            self.canvas = None
        self.particles = []

# ──────────────────────────────────────────────────────────────────────────────
# UI layer
# ──────────────────────────────────────────────────────────────────────────────

class DashboardApp(ctk.CTk):
    COLORS = {"positive": "#2ECC71", "negative": "#E74C3C", "neutral": "#95A5A6"}

    def __init__(self, base_url: str, cfgs: list[dict]):
        super().__init__()
        self.title("Dashboard Ventes")
        self.attributes("-fullscreen", True)
        self.bind("<Escape>", lambda *_: self.attributes("-fullscreen", False))

        # Theme
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Async loop
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()

        # Data
        self.scrapers = [RedashScraper(c["api_key"], base_url) for c in cfgs]
        self.queries = [c["id"] for c in cfgs]
        self.mappings = [c["mapping"] for c in cfgs]

        self.units = {0: "%", 1: "€", 2: "€"}
        self.last_gift = {0: 0, 1: 0, 2: 0}
        
        # Logo
        self.logo_image = None
        self.load_logo()

        # Animation confettis
        self.confetti_animation = None

        self._build_ui()
        self._tick()

    def load_logo(self):
        """Charge le logo depuis un fichier logo.png ou logo.svg dans le répertoire courant"""
        logo_paths = ['logo.png', 'logo.svg', 'logo.jpg', 'logo.jpeg']
        for path in logo_paths:
            if os.path.exists(path):
                try:
                    if path.endswith('.svg'):
                        # Pour SVG, vous devrez installer cairosvg: pip install cairosvg
                        # import cairosvg
                        # png_data = cairosvg.svg2png(url=path)
                        # image = Image.open(io.BytesIO(png_data))
                        logger.info(f"SVG trouvé mais non implémenté: {path}")
                        continue
                    else:
                        image = Image.open(path)
                        # Redimensionner le logo
                        image = image.resize((60, 60), Image.Resampling.LANCZOS)
                        self.logo_image = ImageTk.PhotoImage(image)
                        logger.info(f"Logo chargé: {path}")
                        break
                except Exception as e:
                    logger.warning(f"Erreur lors du chargement du logo {path}: {e}")

    # ───────────────────────────── UI build ────────────────────────────────

    def _build_ui(self):
        self.grid_rowconfigure((0, 1), weight=1)
        self.grid_columnconfigure((0, 1), weight=1)

        titles = ["Évolution", "CA J-1 H0", "CA J-N"]
        pos = [(0, 0), (0, 1), (1, 0)]
        self.q = {}
        
        for i, ((r, c), title) in enumerate(zip(pos, titles)):
            frame = ctk.CTkFrame(self, corner_radius=14)
            if i == 2:
                frame.grid(row=r, column=c, columnspan=2, padx=14, pady=14, sticky="nsew")
            else:
                frame.grid(row=r, column=c, padx=14, pady=14, sticky="nsew")

            # Header avec logo et titre
            header_frame = ctk.CTkFrame(frame, fg_color="transparent")
            header_frame.pack(pady=12, fill="x")
            
            if self.logo_image and i == 0:  # Afficher le logo seulement sur le premier bloc
                logo_label = ctk.CTkLabel(header_frame, image=self.logo_image, text="")
                logo_label.pack(side="left", padx=(20, 10))
            
            title_label = ctk.CTkLabel(
                header_frame, 
                text=title, 
                font=("Montserrat", 20, "bold"), 
                text_color="#000000"  # Noir par défaut
            )
            title_label.pack(side="left" if self.logo_image and i == 0 else "top")

            val = ctk.CTkLabel(frame, text="--", font=("Montserrat", 52, "bold"), text_color="#ffffff")
            val.pack(expand=True)
            trend = ctk.CTkLabel(frame, text="→", font=("Montserrat", 26), text_color="#ffffff")
            trend.pack(pady=6)
            
            self.q[i] = {"frame": frame, "val": val, "trend": trend, "title": title_label}
            
            # Initialiser l'animation confettis pour le bloc CA J-N (index 2)
            if i == 2:
                self.confetti_animation = ConfettiAnimation(frame)

        self.ts = ctk.CTkLabel(self, text="", font=("Montserrat", 14), text_color="#888888")
        self.ts.place(relx=1, rely=1, anchor="se", x=-16, y=-16)

    # ───────────────────────────── Scheduler ───────────────────────────────

    def _tick(self):
        self._refresh()
        self.after(15_000, self._tick)

    # ───────────────────────────── Data fetch ──────────────────────────────

    def _refresh(self):
        async def fetch():
            for idx, (scr, qid, mp) in enumerate(zip(self.scrapers, self.queries, self.mappings)):
                t0 = time.perf_counter()
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

            self.after(0, lambda: self.ts.configure(text=f"Dernière mise à jour : {datetime.now():%H:%M:%S}"))

        asyncio.run_coroutine_threadsafe(fetch(), self.loop)

    # ───────────────────────────── UI update ───────────────────────────────

    def _update_quad(self, idx: int, value: float, ratio: float):
        unit = self.units[idx]
        color, arrow = self._style(ratio)
        lighter = lighten(color, 0.85)
        
        # Couleur du titre adaptée à l'état du bloc
        if ratio > 0:
            title_color = darken(self.COLORS["positive"], 0.2)  # Vert foncé
        elif ratio < 0:
            title_color = darken(self.COLORS["negative"], 0.2)  # Rouge foncé
        else:
            title_color = "#000000"  # Noir pour neutre

        self.q[idx]["title"].configure(text_color=title_color)
        self.q[idx]["val"].configure(text=self._fmt(value, unit), text_color=color)
        trend_txt = f"{arrow} {ceil_signed(ratio)}%" if unit == "%" else arrow
        self.q[idx]["trend"].configure(text=trend_txt, text_color=color)
        self.q[idx]["frame"].configure(fg_color=lighter)

        # Animation confettis pour CA J-N (index 2) quand positif
        if idx == 2 and ratio > 0 and self.confetti_animation:
            self.confetti_animation.start_animation()

        # Gestion des gifts à chaque 5% pour tous les blocs
        if ratio > 0:
            current_threshold = (ceil_signed(ratio) // 5) * 5
            if current_threshold >= 5 and current_threshold > self.last_gift[idx]:
                self.last_gift[idx] = current_threshold
                self._gift_popup(current_threshold)

    # ───────────────────────────── Utils ───────────────────────────────────

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

    def _gift_popup(self, thresh: int):
        pop = ctk.CTkToplevel(self)
        pop.title("🎉 Félicitations !")
        pop.geometry("400x200")
        pop.attributes("-topmost", True)
        
        # Centrer la popup
        pop.update_idletasks()
        x = (pop.winfo_screenwidth() // 2) - (400 // 2)
        y = (pop.winfo_screenheight() // 2) - (200 // 2)
        pop.geometry(f"400x200+{x}+{y}")
        
        # Contenu de la popup
        ctk.CTkLabel(
            pop, 
            text=f"🎁 {thresh}% atteint !", 
            font=("Montserrat", 24, "bold"), 
            text_color="#2ECC71"
        ).pack(expand=True, pady=20)
        
        ctk.CTkLabel(
            pop, 
            text="Excellent travail ! 👏", 
            font=("Montserrat", 16), 
            text_color="#ffffff"
        ).pack(pady=10)
        
        # Bouton fermer
        ctk.CTkButton(
            pop,
            text="Fermer",
            command=pop.destroy,
            width=100,
            height=30
        ).pack(pady=10)
        
        # Fermeture automatique après 5 secondes
        pop.after(5000, pop.destroy)

# ───────────────────────────── Main ─────────────────────────────────────────

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
