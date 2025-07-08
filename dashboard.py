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

def transparent(color: str, alpha: str = "22") -> str:
    """Return the hex color with an added alpha channel (00‑FF)."""
    color = color.lstrip("#")
    if len(color) == 6:
        return f"#{color}{alpha}"
    return f"#{color}"

# ──────────────────────────────────────────────────────────────────────────────
# Data layer
# ──────────────────────────────────────────────────────────────────────────────

class RedashScraper:
    """Minimal async wrapper around the Redash /results.json endpoint."""

    _shared_client: httpx.AsyncClient | None = None

    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        if RedashScraper._shared_client is None:
            RedashScraper._shared_client = httpx.AsyncClient(timeout=10.0)
        self.client: httpx.AsyncClient = RedashScraper._shared_client

    async def execute_query(self, query_id: int) -> dict:
        url = f"{self.base_url}/api/queries/{query_id}/results.json"
        resp = await self.client.get(url, params={"api_key": self.api_key})
        resp.raise_for_status()
        return resp.json()

# ──────────────────────────────────────────────────────────────────────────────
# UI layer
# ──────────────────────────────────────────────────────────────────────────────

class DashboardApp(ctk.CTk):
    """3‑quadrant dashboard with live data from Redash."""

    COLORS = {
        "positive": "#2ECC71",
        "negative": "#E74C3C",
        "neutral": "#95A5A6",
    }

    def __init__(self, base_url: str, query_cfgs: list[dict]):
        super().__init__()
        self.title("Dashboard Ventes")
        self.attributes("-fullscreen", True)
        self.bind("<Escape>", lambda *_: self.attributes("-fullscreen", False))

        # Theme
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Async loop in background thread
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()

        # Prepare data sources
        self.scrapers = [RedashScraper(cfg["api_key"], base_url) for cfg in query_cfgs]
        self.queries  = [cfg["id"]         for cfg in query_cfgs]
        self.mappings = [cfg["mapping"]    for cfg in query_cfgs]

        # Quadrant meta
        self.units = {0: "%", 1: "€", 2: "€"}
        self.last_gift = {0: 0, 1: 0, 2: 0}

        # Build UI
        self._build_layout()
        self._schedule_refresh()

    # ───────────────────────────── internal helpers ──────────────────────────

    def _build_layout(self):
        self.grid_rowconfigure((0, 1), weight=1)
        self.grid_columnconfigure((0, 1), weight=1)

        titles = ["Évolution", "CA J‑1 H0", "CA J‑N"]
        pos    = [(0, 0), (0, 1), (1, 0)]  # 3rd takes full width

        self.q = {}
        for i, ((r, c), title) in enumerate(zip(pos, titles)):
            frame = ctk.CTkFrame(self, corner_radius=16)
            if i == 2:
                frame.grid(row=r, column=c, columnspan=2, sticky="nsew", padx=16, pady=16)
            else:
                frame.grid(row=r, column=c, sticky="nsew", padx=16, pady=16)

            ctk.CTkLabel(frame, text=title, font=("Montserrat", 20, "bold"), text_color="#ffffff").pack(pady=12)
            val = ctk.CTkLabel(frame, text="--", font=("Montserrat", 54, "bold"), text_color="#ffffff")
            val.pack(expand=True)
            trend = ctk.CTkLabel(frame, text="→", font=("Montserrat", 26), text_color="#ffffff")
            trend.pack(pady=8)
            self.q[i] = {"frame": frame, "val": val, "trend": trend}

        self.ts = ctk.CTkLabel(self, text="", font=("Montserrat", 14), text_color="#888888")
        self.ts.place(relx=1, rely=1, anchor="se", x=-18, y=-18)

    # ───────────────────────────── data refresh ──────────────────────────────

    def _schedule_refresh(self):
        self._refresh()
        self.after(15_000, self._schedule_refresh)

    def _refresh(self):
        async def fetch():
            for idx, (scraper, qid, mp) in enumerate(zip(self.scrapers, self.queries, self.mappings)):
                t0 = time.perf_counter()
                data = await scraper.execute_query(qid)
                logger.info("Query %s en %.2fs", qid, time.perf_counter() - t0)

                rows = data.get("query_result", {}).get("data", {}).get("rows", [])
                if not rows:
                    continue
                row = rows[0]
                raw = float(row.get(mp["value"], 0))
                ratio = float(row.get(mp["ratio"], 0))
                logger.info("Query %s: value=%s, ratio=%s", qid, raw, ratio)

                self.after(0, self._update_quad, idx, raw, ratio)

            # timestamp
            self.after(0, lambda: self.ts.configure(text=f"Dernière mise à jour : {datetime.now():%H:%M:%S}"))

        asyncio.run_coroutine_threadsafe(fetch(), self.loop)

    # ───────────────────────────── UI update ────────────────────────────────

    def _update_quad(self, idx: int, value: float, ratio: float):
        unit = self.units[idx]
        color, arrow = self._style_from_ratio(ratio)

        # Format output
        text_val = self._fmt(value, unit)
        text_tr  = f"{arrow} {math.ceil(ratio)}%" if unit == "%" else arrow

        logger.info("Quadrant %s mis à jour: %s, ratio: %.1f", idx, text_val, ratio)

        fr = self.q[idx]
        fr["val"].configure(text=text_val, text_color=color)
        fr["trend"].configure(text=text_tr, text_color=color)
        fr_color = transparent(color, "33")  # subtle tint
        fr["frame"].configure(fg_color=fr_color)

        # Gift popup every +10 %
        if unit == "%" and ratio > 0:
            palier = (math.ceil(ratio) // 10) * 10
            if palier >= 10 and palier > self.last_gift[idx]:
                self.last_gift[idx] = palier
                self._gift_popup(palier)

    # ───────────────────────────── visuals ──────────────────────────────────

    def _style_from_ratio(self, r: float):
        if r > 0:
            return self.COLORS["positive"], "↗"
        if r < 0:
            return self.COLORS["negative"], "↘"
        return self.COLORS["neutral"], "→"

    @staticmethod
    def _fmt(num: float, unit: str) -> str:
        if unit == "€":
            return f"{math.ceil(num):,}€".replace(",", " ")
        return f"{math.ceil(num)}{unit}"

    def _gift_popup(self, threshold: int):
        pop = ctk.CTkToplevel(self)
        pop.title("Good job ✨")
        pop.geometry("380x180")
        pop.attributes("-topmost", True)
        ctk.CTkLabel(pop, text=f"🎉 On a atteint {threshold}% !", font=("Montserrat", 18, "bold")).pack(expand=True)
        pop.after(3500, pop.destroy)

# ──────────────────────────────────────────────────────────────────────────────
# Main entry point
# ──────────────────────────────────────────────────────────────────────────────

def main():
    load_dotenv()
    base_url = os.getenv("REDASH_BASE_URL", "")
    cfgs = [
        {"id": 111, "api_key": os.getenv("KEY_EVOL", ""), "mapping": {"value": "EVOL", "ratio": "EVOL"}},
        {"id": 110, "api_key": os.getenv("KEY_CA_J1", ""), "mapping": {"value": "CA", "ratio": "AVG"}},
        {"id": 109, "api_key": os.getenv("KEY_CA_JN", ""), "mapping": {"value": "CA", "ratio": "AVG"}},
    ]

    if not base_url:
        raise SystemExit("REDASH_BASE_URL absent du .env")

    DashboardApp(base_url, cfgs).mainloop()


if __name__ == "__main__":
    main()
