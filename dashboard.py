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

        self._build_ui()
        self._tick()

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

            ctk.CTkLabel(frame, text=title, font=("Montserrat", 20, "bold"), text_color="#ffffff").pack(pady=12)
            val = ctk.CTkLabel(frame, text="--", font=("Montserrat", 52, "bold"), text_color="#ffffff")
            val.pack(expand=True)
            trend = ctk.CTkLabel(frame, text="→", font=("Montserrat", 26), text_color="#ffffff")
            trend.pack(pady=6)
            self.q[i] = {"frame": frame, "val": val, "trend": trend}

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

        self.q[idx]["val"].configure(text=self._fmt(value, unit), text_color=color)
        trend_txt = f"{arrow} {ceil_signed(ratio)}%" if unit == "%" else arrow
        self.q[idx]["trend"].configure(text=trend_txt, text_color=color)
        self.q[idx]["frame"].configure(fg_color=lighter)

        if unit == "%" and ratio > 0:
            palier = (ceil_signed(ratio) // 10) * 10
            if palier >= 10 and palier > self.last_gift[idx]:
                self.last_gift[idx] = palier
                self._gift_popup(palier)

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
        pop.title("👏 Bravo !")
        pop.geometry("360x160")
        pop.attributes("-topmost", True)
        ctk.CTkLabel(pop, text=f"🎉 {thresh}% atteint !", font=("Montserrat", 18, "bold"), text_color="#ffffff").pack(expand=True)
        pop.after(3200, pop.destroy)

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
