import tkinter as tk
import requests
import threading
from datetime import datetime


class RedashScraper:
    def __init__(self, api_key: str, base_url: str) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.headers = {
            "Authorization": f"Key {self.api_key}",
            "Content-Type": "application/json",
        }

    def execute_query(self, query_id: int) -> dict:
        """Execute a Redash query and return JSON data."""
        url = f"{self.base_url}/api/queries/{query_id}/results"
        response = requests.post(
            url,
            headers=self.headers,
            json={"max_age": 0},
        )
        response.raise_for_status()
        return response.json()

    def get_conversion_ratio(self, data: dict) -> float:
        """Compute conversion ratio from data (example implementation)."""
        rows = data.get("query_result", {}).get("data", {}).get("rows", [])
        if not rows:
            return 0.0
        value = rows[0].get("conversion", 0)
        total = rows[0].get("total", 1)
        return (value / total) * 100


class DashboardApp:
    def __init__(
        self,
        master: tk.Tk,
        api_key: str,
        base_url: str,
        queries: list[int],
    ) -> None:
        self.master = master
        self.master.title("Dashboard Ventes")
        self.master.attributes("-fullscreen", True)
        self.master.bind("<Escape>", self.exit_fullscreen)

        self.scraper = RedashScraper(api_key, base_url)
        self.queries = queries

        self.colors = {
            "positive": "#2ECC71",
            "negative": "#E74C3C",
            "neutral": "#95A5A6",
        }

        self.setup_layout()
        self.start_auto_refresh()

    def setup_layout(self) -> None:
        for i in range(2):
            self.master.grid_rowconfigure(i, weight=1)
            self.master.grid_columnconfigure(i, weight=1)

        positions = [(0, 0), (0, 1), (1, 0), (1, 1)]
        titles = [
            "Ventes Journalières",
            "Conversion Web",
            "Objectifs Mensuels",
            "Performance Équipe",
        ]

        self.quadrants = {}
        for i, (row, col) in enumerate(positions):
            frame = tk.Frame(self.master, relief="raised", borderwidth=2)
            frame.grid(row=row, column=col, sticky="nsew", padx=5, pady=5)

            title_label = tk.Label(
                frame,
                text=titles[i],
                font=("Arial", 16, "bold"),
            )
            title_label.pack(pady=10)

            data_label = tk.Label(
                frame,
                text="--",
                font=("Arial", 48, "bold"),
            )
            data_label.pack(expand=True)

            trend_label = tk.Label(
                frame,
                text="→",
                font=("Arial", 24),
            )
            trend_label.pack(pady=5)

            self.quadrants[i] = {
                "frame": frame,
                "data": data_label,
                "trend": trend_label,
            }

        self.timestamp_label = tk.Label(
            self.master,
            text="",
            font=("Arial", 12),
        )
        self.timestamp_label.place(
            relx=1.0,
            rely=1.0,
            anchor="se",
            x=-10,
            y=-10,
        )

    def update_quadrant(
        self, quadrant_id: int, value: str, ratio: float
    ) -> None:
        quadrant = self.quadrants[quadrant_id]
        if ratio > 0:
            color = self.colors["positive"]
            trend = "↗"
            alert_needed = ratio > 20
        elif ratio < 0:
            color = self.colors["negative"]
            trend = "↘"
            alert_needed = ratio < -10
        else:
            color = self.colors["neutral"]
            trend = "→"
            alert_needed = False

        self.animate_color_change(quadrant["frame"], color)
        quadrant["data"].config(text=f"{value}", fg=color)
        quadrant["trend"].config(text=trend, fg=color)

        if alert_needed:
            self.show_alert(quadrant_id, ratio)

    def animate_color_change(
        self, widget: tk.Widget, target_color: str
    ) -> None:
        widget.config(bg=target_color, highlightbackground=target_color)

    def show_alert(self, quadrant_id: int, ratio: float) -> None:
        alert = tk.Toplevel(self.master)
        alert.title("Alerte Performance")
        alert.geometry("400x200")
        alert.attributes("-topmost", True)
        msg = f"Attention! Quadrant {quadrant_id + 1}\nRatio: {ratio:.1f}%"
        label = tk.Label(
            alert,
            text=msg,
            font=("Arial", 14, "bold"),
            fg="white",
            bg="red",
        )
        label.pack(expand=True)
        alert.after(5000, alert.destroy)

    def update_timestamp(self, timestamp: str) -> None:
        self.timestamp_label.config(text=f"Dernière mise à jour: {timestamp}")

    def extract_value(self, data: dict) -> str:
        rows = data.get("query_result", {}).get("data", {}).get("rows", [])
        if not rows:
            return "--"
        return str(rows[0].get("value", "--"))

    def refresh_data(self) -> None:
        def fetch() -> None:
            try:
                for i, query_id in enumerate(self.queries):
                    data = self.scraper.execute_query(query_id)
                    ratio = self.scraper.get_conversion_ratio(data)
                    value = self.extract_value(data)
                    self.master.after(
                        0,
                        lambda i=i, v=value, r=ratio:
                            self.update_quadrant(i, v, r),
                    )
                ts = datetime.now().strftime("%H:%M:%S")
                self.master.after(0, lambda: self.update_timestamp(ts))
            except Exception as exc:  # pragma: no cover - simple logging
                print(f"Erreur lors de l'actualisation: {exc}")

        threading.Thread(target=fetch, daemon=True).start()

    def start_auto_refresh(self) -> None:
        self.refresh_data()
        self.master.after(15000, self.start_auto_refresh)

    def exit_fullscreen(self, event=None) -> None:
        self.master.attributes("-fullscreen", False)


def main() -> None:
    api_key = "your_api_key"
    base_url = "your_redash_url"
    queries = [12, 34, 56, 78]
    root = tk.Tk()
    DashboardApp(root, api_key, base_url, queries)
    root.mainloop()


if __name__ == "__main__":
    main()
