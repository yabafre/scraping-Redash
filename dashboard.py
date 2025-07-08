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

        # Stockage des derniers seuils pour éviter les messages répétés
        self.last_gift_threshold = {0: 0, 1: 0, 2: 0}

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
            frame = ctk.CTkFrame(master=self, corner_radius=15)
            
            # CA J-N prend toute la largeur en bas
            if i == 2:  # CA J-N
                frame.grid(row=row, column=col, columnspan=2, padx=15, pady=15, sticky="nsew")
            else:
                frame.grid(row=row, column=col, padx=15, pady=15, sticky="nsew")

            # Titre avec style amélioré
            title_label = ctk.CTkLabel(
                frame, 
                text=title, 
                font=("Montserrat", 20, "bold"),
                text_color="#ffffff"
            )
            title_label.pack(pady=15)
            
            # Valeur principale
            data_lbl = ctk.CTkLabel(
                frame, 
                text="--", 
                font=("Montserrat", 56, "bold"),
                text_color="#ffffff"
            )
            data_lbl.pack(expand=True)
            
            # Indicateur de tendance
            trend_lbl = ctk.CTkLabel(
                frame, 
                text="→", 
                font=("Montserrat", 28)
            )
            trend_lbl.pack(pady=10)

            self.quadrants[i] = {"frame": frame, "data": data_lbl, "trend": trend_lbl}

        # Timestamp avec style amélioré
        self.ts_label = ctk.CTkLabel(
            master=self, 
            text="", 
            font=("Montserrat", 14),
            text_color="#888888"
        )
        self.ts_label.place(relx=1, rely=1, anchor="se", x=-15, y=-15)

    def format_number(self, value: float, unit: str) -> str:
        """Formate les nombres selon leur type"""
        if unit == "€":
            # Pour les montants en euros, formatage avec espaces
            return f"{math.ceil(value):,}€".replace(",", " ")
        else:
            # Pour les pourcentages, arrondi à l'entier supérieur
            return f"{math.ceil(value)}{unit}"

    def update_quadrant(self, idx: int, raw_value: float, ratio: float) -> None:
        if idx not in self.quadrants:
            logger.warning(f"Quadrant {idx} n'existe pas")
            return
            
        unit = self.units[idx]
        value_text = self.format_number(raw_value, unit)

        # Sélection de la couleur et de la flèche
        if ratio > 0:
            color, arrow = self.colors["positive"], "↗"
        elif ratio < 0:
            color, arrow = self.colors["negative"], "↘"
        else:
            color, arrow = self.colors["neutral"], "→"

        # Animation de fondu
        self.fade(self.quadrants[idx]["frame"], color)

        # Mise à jour des labels
        self.quadrants[idx]["data"].configure(text=value_text, text_color=color)
        
        # Affichage du ratio pour l'évolution
        if unit == "%":
            trend_text = f"{arrow} {math.ceil(ratio)}{unit}"
        else:
            trend_text = arrow
        self.quadrants[idx]["trend"].configure(text=trend_text, text_color=color)

        # Message cadeau sur palier de 10% en positif (uniquement pour %)
        if unit == "%" and ratio > 0:
            current_threshold = (math.ceil(ratio) // 10) * 10
            if current_threshold >= 10 and current_threshold > self.last_gift_threshold[idx]:
                self.show_gift(idx, current_threshold)
                self.last_gift_threshold[idx] = current_threshold

        logger.info(f"Quadrant {idx} mis à jour: {value_text}, ratio: {ratio:.1f}")

    def fade(self, widget: ctk.CTkFrame, target_color: str, steps: int = 15, delay: int = 40):
        """Animation de fondu pour les couleurs"""
        def anim(n=0):
            if n > steps:
                return
            # Progression plus douce
            alpha = n / steps
            widget.configure(fg_color=target_color)
            widget.after(delay, lambda: anim(n + 1))
        anim()

    def show_gift(self, idx: int, threshold: int) -> None:
        """Affiche un message de félicitations animé"""
        dlg = ctk.CTkToplevel(self)
        dlg.title("Félicitations! 🎁")
        dlg.geometry("400x200")
        dlg.attributes("-topmost", True)
        
        # Centrer la fenêtre
        dlg.geometry(f"+{self.winfo_x() + 300}+{self.winfo_y() + 200}")
        
        msg = (
            f"🎉 Fantastique ! 🎉\n\n"
            f"Vous avez atteint {threshold}% !\n\n"
            f"Voici votre gift : 🎁💝🌟"
        )
        
        label = ctk.CTkLabel(
            dlg,
            text=msg,
            font=("Montserrat", 16, "bold"),
            text_color="#ffffff",
            justify="center"
        )
        label.pack(expand=True, padx=20, pady=20)
        
        # Animation de la fenêtre (léger zoom)
        def animate_popup(scale=0.8):
            if scale <= 1.2:
                # Effet de zoom subtil
                dlg.after(30, lambda: animate_popup(scale + 0.02))
        
        animate_popup()
        dlg.after(4000, dlg.destroy)

    def start_auto_refresh(self) -> None:
        self.refresh_data()
        self.after(15000, self.start_auto_refresh)

    def refresh_data(self) -> None:
        async def fetch_all():
            try:
                for i, (scr, qid, mp) in enumerate(zip(self.scrapers, self.queries, self.mappings)):
                    start = time.perf_counter()
                    data = await scr.execute_query(qid)
                    duration = time.perf_counter() - start
                    logger.info("Query %s en %.2fs", qid, duration)
                    
                    rows = data.get("query_result", {}).get("data", {}).get("rows", [])
                    if rows:
                        row = rows[0]
                        
                        # Extraction des valeurs selon le mapping
                        raw_v = float(row.get(mp["value"], 0.0))
                        ratio = float(row.get(mp["ratio"], 0.0))
                        
                        logger.info(f"Query {qid}: value={raw_v}, ratio={ratio}")
                        
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
    
    # Configuration corrigée basée sur vos exemples JSON
    query_configs = [
        # Query 111: EVOL - utilise EVOL pour valeur et ratio
        {"id": 111, "api_key": os.getenv("KEY_EVOL", ""), "mapping": {"value": "EVOL", "ratio": "EVOL"}},
        
        # Query 110: CA J-1 H0 - utilise CA pour valeur et AVG pour ratio  
        {"id": 110, "api_key": os.getenv("KEY_CA_J1", ""), "mapping": {"value": "CA", "ratio": "AVG"}},
        
        # Query 109: CA J-N - utilise CA pour valeur et AVG pour ratio
        {"id": 109, "api_key": os.getenv("KEY_CA_JN", ""), "mapping": {"value": "CA", "ratio": "AVG"}},
    ]

    app = DashboardApp(base_url, query_configs)
    app.mainloop()

if __name__ == "__main__":
    main()
