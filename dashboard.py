import tkinter as tk
import asyncio
import httpx
import threading
import logging
import os
import time
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
        # client asynchrone avec timeout
        self.client = httpx.AsyncClient(timeout=10.0)

    async def close(self) -> None:
        await self.client.aclose()

    async def execute_query(self, query_id: int) -> dict:
        """
        Exécute une requête Redash et renvoie le JSON de résultat.
        Utilise l’endpoint unique /api/queries/:id/results.json?api_key=…
        """
        url = f"{self.base_url}/api/queries/{query_id}/results.json"
        response = await self.client.get(url, params={"api_key": self.api_key})
        response.raise_for_status()
        return response.json()

class DashboardApp:
    def __init__(
        self,
        master: tk.Tk,
        base_url: str,
        query_configs: list[dict[str, object]],
    ) -> None:
        self.master = master
        self.master.title("Dashboard Ventes")
        self.master.attributes("-fullscreen", True)
        self.master.bind("<Escape>", self.exit_fullscreen)

        # Création d’un scraper par requête (clé propre)
        self.scrapers = [
            RedashScraper(cfg["api_key"], base_url) for cfg in query_configs
        ]
        self.queries  = [cfg["id"]        for cfg in query_configs]
        self.mappings = [cfg["mapping"]   for cfg in query_configs]

        # Jeu de couleurs
        self.colors = {
            "positive": "#2ECC71",
            "negative": "#E74C3C",
            "neutral":  "#95A5A6",
        }

        self.setup_layout()
        self.start_auto_refresh()

    def setup_layout(self) -> None:
        """Configure la grille 2×2 et les widgets"""
        for i in range(2):
            self.master.grid_rowconfigure(i, weight=1)
            self.master.grid_columnconfigure(i, weight=1)

        titles = ["CA J-N", "Évolution", "CA J-1 H0", "Conversion"]
        self.quadrants = {}

        for i, title in enumerate(titles):
            row, col = divmod(i, 2)
            frame = tk.Frame(self.master, relief="raised", borderwidth=2)
            frame.grid(row=row, column=col, sticky="nsew", padx=5, pady=5)

            tk.Label(frame, text=title, font=("Arial", 16, "bold")).pack(pady=10)
            data_lbl  = tk.Label(frame, text="--", font=("Arial", 48, "bold"))
            trend_lbl = tk.Label(frame, text="→",  font=("Arial", 24))
            data_lbl.pack(expand=True)
            trend_lbl.pack(pady=5)

            self.quadrants[i] = {"frame": frame, "data": data_lbl, "trend": trend_lbl}

        # Timestamp
        self.ts_label = tk.Label(self.master, text="", font=("Arial", 12))
        self.ts_label.place(relx=1.0, rely=1.0, anchor="se", x=-10, y=-10)

    def update_quadrant(self, idx: int, value: str, ratio: float) -> None:
        """Mise à jour graphique avec fondu et alertes"""
        quad = self.quadrants[idx]
        if ratio > 0:
            color, arrow, alert = self.colors["positive"], "↗", ratio > 20
        elif ratio < 0:
            color, arrow, alert = self.colors["negative"], "↘", ratio < -10
        else:
            color, arrow, alert = self.colors["neutral"],  "→", False

        self.fade(quad["frame"], quad["frame"].cget("bg"), color)
        quad["data"].config(text=value, fg=color)
        quad["trend"].config(text=arrow, fg=color)

        if alert:
            self.show_alert(idx, ratio)

    def fade(self, widget: tk.Widget, start: str, end: str, steps: int = 10, delay: int = 50) -> None:
        """Interpolation de couleur pour animation en fondu"""
        sr, sg, sb = (int(start[i:i+2], 16) for i in (1,3,5))
        er, eg, eb = (int(end[i:i+2],   16) for i in (1,3,5))
        def step(n: int = 0):
            if n>steps: return
            r = sr + (er-sr)*n//steps
            g = sg + (eg-sg)*n//steps
            b = sb + (eb-sb)*n//steps
            c = f"#{r:02x}{g:02x}{b:02x}"
            widget.config(bg=c, highlightbackground=c)
            widget.after(delay, lambda: step(n+1))
        step()

    def show_alert(self, idx: int, ratio: float) -> None:
        """Popup animée + beep pour alerte"""
        alert = tk.Toplevel(self.master)
        alert.title("Alerte")
        alert.geometry("300x150")
        alert.attributes("-topmost", True)
        msg = f"Quadrant {idx+1}\nRatio: {ratio:.1f}%"
        tk.Label(alert, text=msg, font=("Arial",14,"bold"), fg="white", bg="red").pack(expand=True)
        # Shake
        def shake(n=0):
            if n>6: return
            x = 10 if n%2==0 else -10
            alert.geometry(f"+{alert.winfo_x()+x}+{alert.winfo_y()}")
            alert.after(50, lambda: shake(n+1))
        print("\a", end="")  # beep
        shake()
        alert.after(4000, alert.destroy)

    def start_auto_refresh(self) -> None:
        """Lance la mise à jour cyclique toutes les 15s"""
        self.refresh_data()
        self.master.after(15000, self.start_auto_refresh)

    def refresh_data(self) -> None:
        """Récupère et affiche les données asynchrones"""
        async def fetch_all():
            for i, (scraper, qid, mapping) in enumerate(zip(self.scrapers, self.queries, self.mappings)):
                start = time.perf_counter()
                data = await scraper.execute_query(qid)
                logger.info("Query %s en %.2fs", qid, time.perf_counter()-start)
                row = data["query_result"]["data"]["rows"][0] if data["query_result"]["data"]["rows"] else {}
                value = str(row.get(mapping["value"], "--"))
                ratio = float(row.get(mapping["ratio"], 0.0))
                self.master.after(0, lambda i=i, v=value, r=ratio: self.update_quadrant(i, v, r))
            ts = datetime.now().strftime("%H:%M:%S")
            self.master.after(0, lambda: self.ts_label.config(text=f"Dernière mise à jour: {ts}"))

        threading.Thread(target=lambda: asyncio.run(fetch_all()), daemon=True).start()

    def exit_fullscreen(self, event=None) -> None:
        self.master.attributes("-fullscreen", False)

def main():
    load_dotenv()
    base_url = os.getenv("REDASH_BASE_URL", "")
    # Configuration par requête : ID, clé API spécifique et mapping colonnes
    query_configs = [
        {"id": 193016, "api_key": os.getenv("KEY_CA_JN", ""),   "mapping": {"value": "CA",      "ratio": "AVG"}},
        {"id": 193017, "api_key": os.getenv("KEY_EVOL", ""),   "mapping": {"value": "EVOL",    "ratio": "EVOL"}},
        {"id": 193018, "api_key": os.getenv("KEY_CA_J1", ""),  "mapping": {"value": "CA",      "ratio": "AVG"}},
        {"id": 193019, "api_key": os.getenv("KEY_CONV", ""),  "mapping": {"value": "conversion", "ratio": "conversion"}},
    ]

    root = tk.Tk()
    DashboardApp(root, base_url, query_configs)
    root.mainloop()

if __name__ == "__main__":
    main()
