import customtkinter as ctk
import asyncio
import httpx
import threading
import logging
import os
import time
import math
from datetime import datetime
from dotenv import load_dotenv
from PIL import Image, ImageTk  # logo support

try:
    import cairosvg  # optional svg → png
except ImportError:
    cairosvg = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def lighten(hex_color: str, factor: float = 0.75) -> str:
    """Return a lighter hex color (factor 0‑1)."""
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    r = int(r + (255 - r) * factor)
    g = int(g + (255 - g) * factor)
    b = int(b + (255 - b) * factor)
    return f"#{r:02x}{g:02x}{b:02x}"


def ceil_signed(x: float) -> int:
    """Round toward +∞ for positives, −∞ for negatives."""
    return math.ceil(x) if x >= 0 else math.floor(x)

# ──────────────────────────────────────────────────────────────────────────────
# Data layer
# ──────────────────────────────────────────────────────────────────────────────

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

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # logo (PNG or SVG)
        logo_path = os.getenv("DASH_LOGO", "")
        if logo_path and os.path.isfile(logo_path):
            img = self._load_logo(logo_path)
            if img:
                self.logo = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                ctk.CTkLabel(self, image=self.logo, text="").place(x=20, y=20)

        # async loop
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()

        # data
        self.scrapers = [RedashScraper(c["api_key"], base_url) for c in cfgs]
        self.queries = [c["id"] for c in cfgs]
        self.mappings = [c["mapping"] for c in cfgs]

        self.units = {0: "%", 1: "€", 2: "€"}
        self.last_gift = {0: 0, 1: 0, 2: 0}

        self._build_ui()
        self._tick()

    # ───────────────────────────── logo helper ────────────────────────────

    def _load_logo(self, path: str):
        try:
            if path.lower().endswith(".svg") and cairosvg:
                png_bytes = cairosvg.svg2png(url=path)
                from io import BytesIO
                return Image.open(BytesIO(png_bytes)).resize((120, 40), Image.LANCZOS)
            else:
                return Image.open(path).resize((120, 40), Image.LANCZOS)
        except Exception as e:
            logger.warning("Impossible de charger le logo %s : %s", path, e)
            return None

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

            title_lbl = ctk.CTkLabel(frame, text=title, font=("Montserrat", 20, "bold"), text_color="#000000")
            title_lbl.pack(pady=10)
            val = ctk.CTkLabel(frame, text="--", font=("Montserrat", 52, "bold"), text_color="#ffffff")
            val.pack(expand=True)
            trend = ctk.CTkLabel(frame, text="→", font=("Montserrat", 26), text_color="#ffffff")
            trend.pack(pady=6)
            self.q[i] = {"frame": frame, "val": val, "trend": trend, "title": title_lbl}

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
                data = await scr.execute_query(qid)
                rows = data.get("query_result", {}).get("data", {}).get("rows", [])
                if not rows:
                    continue
                row = rows[0]
                value = float(row.get(mp["value"], 0))
                ratio = float(row.get(mp["ratio"], 0))
                self.after(0, self._update_quad, idx, value, ratio)

            self.after(0, lambda: self.ts.configure(text=datetime.now().strftime("%H:%M:%S")))

        asyncio.run_coroutine_threadsafe(fetch(), self.loop)

    # ───────────────────────────── UI update ───────────────────────────────

    def _update_quad(self, idx: int, value: float, ratio: float):
        unit = self.units[idx]
        color, arrow = self._style(ratio)
        bg = lighten(color, 0.8)

        quad = self.q[idx]
        quad["val"].configure(text=self._fmt(value, unit), text_color=color)
        quad["trend"].configure(text=f"{arrow} {ceil_signed(ratio)}%" if unit == "%" else arrow, text_color=color)
        quad["frame"].configure(fg_color=bg)
        quad["title"].configure(text_color=color if unit == "%" else "#000000")

        # gift every 5 % on evolution
        if idx == 0 and ratio > 0:
            step = 5
            thresh = (ceil_signed(ratio) // step) * step
            if thresh >= step and thresh > self.last_gift[idx]:
                self.last_gift[idx] = thresh
                self._gift_popup(thresh)

        # confetti when CA J-N positive
        if idx == 2 and ratio > 0:
            self._confetti(quad["frame"])

    # ───────────────────────────── Effects ─────────────────────────────────

    def _gift_popup(self, thresh: int):
        pop = ctk.CTkToplevel(self)
        pop.title("🎁 Gift")
        pop.geometry("320x140")
        pop.attributes("-topmost", True)
        ctk.CTkLabel(pop, text=f"🌟 +{thresh}% !
