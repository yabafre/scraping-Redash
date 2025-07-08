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

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RedashScraper:
    def __init__(self, api_key: str, base_url: str) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Key {self.api_key}"}
        self.client = httpx.AsyncClient(timeout=10.0)

    async def close(self) -> None:
        await self.client.aclose()

    async def execute_query(self, query_id: int) -> dict:
        url = f"{self.base_url}/api/queries/{query_id}/results.json"
        resp = await self.client.get(url, params={"api_key": self.api_key})
        resp.raise_for_status()
        return resp.json()

class DashboardApp(ctk.CTk):
    def __init__(self, base_url: str, query_configs: list[dict]) -> None:
        super().__init__()
        self.title("Dashboard Ventes")
        self.attributes("-fullscreen", True)
        self.bind("<Escape>", lambda e: self.attributes("-fullscreen", False))

        # Scrapers, requêtes et mappings
        self.scrapers = [RedashScraper(cfg["api_key"], base_url) for cfg in query_configs]
        self.queries  = [cfg["id"] for cfg in query_configs]
        self.mappings = [cfg["mapping"] for cfg in query_configs]

        # Unités par quadrant (3 quadrants maintenant)
        # 0: Évolution (%), 1: CA J-1 H0 (€), 2: CA J-N (€)
        self.units = {0: "%", 1: "€", 2: "€"}

        # Couleurs
        self.colors = {"positive": "#2ECC71", "negative": "#E74C3C", "neutral": "#95A5A6"}

        # Thème CustomTkinter
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Boucle asyncio dédiée
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()

        self.setup_layout()
        self.start_auto_refresh()

    def setup_layout(self) -> None:
        # Configuration pour 3 quadrants : 2 en haut, 1 en bas
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # Titres et positions : Évolution et CA J-1 H0 en haut, CA J-N en bas
        titles = ["Évolution", "CA J-1 H0", "CA J-N"]
        positions = [(0, 0), (0, 1), (1, 0)]  # (row, col)
        
        self.quadrants = {}

        for i, (title, (row, col)) in enumerate(zip(titles, positions)):
            frame = ctk.CTkFrame(master=self, corner_radius=10)
            
            # CA J-N prend toute la largeur en bas
            if i == 2:  # CA J-N
                frame.grid(row=row, column=col, columnspan=2, padx=10, pady=10, sticky="nsew")
            else:
                frame.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")

            ctk.CTkLabel(frame, text=title, font=("Arial", 16, "bold")).pack(pady=5)
            data_lbl  = ctk.CTkLabel(frame, text="--", font=("Arial", 48, "bold"))
            trend_lbl = ctk.CTkLabel(frame, text="→",  font=("Arial", 24))
            data_lbl.pack(expand=True)
            trend_lbl.pack(pady=5)

            self.quadrants[i] = {"frame": frame, "data": data_lbl, "trend": trend_lbl}

        # Timestamp
        self.ts_label = ctk.CTkLabel(master=self, text="", font=("Arial", 12))
        self.ts_label.place(relx=1, rely=1, anchor="se", x=-10, y=-10)

    def update_quadrant(self, idx: int, raw_value: float, ratio: float) -> None:
        if idx not in self.quadrants:
            return
            
        # Arrondi au plafond
        val_int = math.ceil(raw_value)
        unit = self.units[idx]
        value_text = f"{val_int:,}{unit}".replace(",", " ")  # Formatage des nombres

        # Sélection de la couleur et de la flèche
        if ratio > 0:
            color, arrow = self.colors["positive"], "↗"
        elif ratio < 0:
            color, arrow = self.colors["negative"], "↘"
        else:
            color, arrow = self.colors["neutral"],  "→"

        # Animation de fondu
        self.fade(self.quadrants[idx]["frame"], color)

        # Mise à jour des labels
        self.quadrants[idx]["data"].configure(text=value_text, text_color=color)
        
        # Affichage du ratio avec unité pour l'évolution
        if unit == "%":
            trend_text = f"{arrow} {math.ceil(ratio)}{unit}"
        else:
            trend_text = arrow
        self.quadrants[idx]["trend"].configure(text=trend_text, text_color=color)

        # Message cadeau sur palier de 10% en positif (pour les %)
        if unit == "%" and ratio >= 10 and math.ceil(ratio) % 10 == 0:
            self.show_gift(idx, math.ceil(ratio))

    def fade(self, widget: ctk.CTkFrame, target_color: str, steps: int = 10, delay: int = 30):
        def anim(n=0):
            if n > steps:
                return
            widget.configure(fg_color=target_color)
            widget.after(delay, lambda: anim(n + 1))
        anim()

    def show_gift(self, idx: int, threshold: int) -> None:
        dlg = ctk.CTkToplevel(self)
        dlg.title("Cadeau 🎁")
        dlg.geometry("300x150")
        dlg.attributes("-topmost", True)
        msg = (
            f"Félicitations !\n"
            f"Vous avez dépassé {threshold}% !\n"
            f"Voici votre gift : 💝"
        )
        ctk.CTkLabel(
            dlg,
            text=msg,
            font=("Arial", 14, "bold"),
            text_color="#ffffff",
            fg_color="#3b8ed2"
        ).pack(expand=True, padx=10, pady=10)
        dlg.after(3000, dlg.destroy)

    def start_auto_refresh(self) -> None:
        self.refresh_data()
        self.after(15000, self.start_auto_refresh)

    def refresh_data(self) -> None:
        async def fetch_all():
            try:
                for i, (scr, qid, mp) in enumerate(zip(self.scrapers, self.queries, self.mappings)):
                    start = time.perf_counter()
                    data = await scr.execute_query(qid)
                    logger.info("Query %s en %.2fs", qid, time.perf_counter() - start)
                    
                    rows = data.get("query_result", {}).get("data", {}).get("rows", [])
                    if rows:
                        row = rows[0]
                        raw_v = float(row.get(mp["value"], 0.0))
                        ratio = float(row.get(mp["ratio"], 0.0))
                        
                        # Correction de la closure : capture des valeurs actuelles
                        def update_with_values(idx=i, rv=raw_v, r=ratio):
                            self.update_quadrant(idx, rv, r)
                        
                        self.after(0, update_with_values)
                    else:
                        logger.warning("Pas de données pour la query %s", qid)

                ts = datetime.now().strftime("%H:%M:%S")
                self.after(0, lambda: self.ts_label.configure(text=f"Dernière mise à jour : {ts}"))
            except Exception as e:
                logger.error("Erreur dans fetch_all: %s", e)

        asyncio.run_coroutine_threadsafe(fetch_all(), self.loop)

def main():
    load_dotenv()
    base_url = os.getenv("REDASH_BASE_URL", "")
    
    # Configuration pour 3 quadrants seulement (suppression de CONV)
    query_configs = [
        {"id": 111, "api_key": os.getenv("KEY_EVOL", ""),   "mapping": {"value": "EVOL", "ratio": "EVOL"}},
        {"id": 110, "api_key": os.getenv("KEY_CA_J1", ""),  "mapping": {"value": "CA",   "ratio": "AVG"}},
        {"id": 109, "api_key": os.getenv("KEY_CA_JN", ""),  "mapping": {"value": "CA",   "ratio": "AVG"}},
    ]

    app = DashboardApp(base_url, query_configs)
    app.mainloop()

if __name__ == "__main__":
    main()
