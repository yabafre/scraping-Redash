import tkinter as tk
import asyncio
import httpx
import threading
import logging
import os
import time
from datetime import datetime
from dotenv import load_dotenv

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
        """Execute a Redash query and return JSON data."""
        url = f"{self.base_url}/api/queries/{query_id}/results"
        response = await self.client.post(url, headers=self.headers, json={"max_age": 0})
        response.raise_for_status()
        data = response.json()

        job = data.get("job")
        if job:
            job_id = job.get("id")
            while True:
                job_resp = await self.client.get(f"{self.base_url}/api/jobs/{job_id}", headers=self.headers)
                job_resp.raise_for_status()
                job_data = job_resp.json()["job"]
                status = job_data.get("status")
                if status == 3:
                    result_id = job_data.get("query_result_id")
                    result_resp = await self.client.get(
                        f"{self.base_url}/api/queries/results/{result_id}.json",
                        headers=self.headers,
                    )
                    result_resp.raise_for_status()
                    return result_resp.json()
                if status in (4, 5):
                    raise RuntimeError(f"Job {job_id} failed with status {status}")
                await asyncio.sleep(1)

        return data


class DashboardApp:
    def __init__(
        self,
        master: tk.Tk,
        api_key: str,
        base_url: str,
        queries: list[int],
        mappings: list[dict[str, str]],
    ) -> None:
        self.master = master
        self.master.title("Dashboard Ventes")
        self.master.attributes("-fullscreen", True)
        self.master.bind("<Escape>", self.exit_fullscreen)

        self.scraper = RedashScraper(api_key, base_url)
        self.queries = queries
        self.mappings = mappings

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

        self.fade(quadrant["frame"], quadrant["frame"].cget("bg"), color)
        quadrant["data"].config(text=f"{value}", fg=color)
        quadrant["trend"].config(text=trend, fg=color)

        if alert_needed:
            self.show_alert(quadrant_id, ratio)

    def fade(
        self, widget: tk.Widget, start: str, end: str, steps: int = 10, delay: int = 50
    ) -> None:
        sr, sg, sb = (int(start[i : i + 2], 16) for i in (1, 3, 5))
        er, eg, eb = (int(end[i : i + 2], 16) for i in (1, 3, 5))

        def step(n: int = 0) -> None:
            if n > steps:
                return
            r = sr + (er - sr) * n // steps
            g = sg + (eg - sg) * n // steps
            b = sb + (eb - sb) * n // steps
            c = f"#{r:02x}{g:02x}{b:02x}"
            widget.config(bg=c, highlightbackground=c)
            widget.after(delay, lambda: step(n + 1))

        step()

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

        def shake(count: int = 0) -> None:
            if count > 10:
                return
            x = 10 if count % 2 == 0 else -10
            alert.geometry(f"+{alert.winfo_x()+x}+{alert.winfo_y()}")
            alert.after(50, lambda: shake(count + 1))

        print("\a", end="")  # simple beep
        shake()
        alert.after(5000, alert.destroy)

    def update_timestamp(self, timestamp: str) -> None:
        self.timestamp_label.config(text=f"Dernière mise à jour: {timestamp}")

    def extract_value(self, row: dict, column: str) -> str:
        return str(row.get(column, "--"))

    def compute_ratio(self, row: dict, column: str) -> float:
        try:
            return float(row.get(column, 0))
        except (TypeError, ValueError):
            return 0.0

    def refresh_data(self) -> None:
        async def fetch() -> None:
            try:
                for i, query_id in enumerate(self.queries):
                    start = time.perf_counter()
                    data = await self.scraper.execute_query(query_id)
                    duration = time.perf_counter() - start
                    logger.info("Appel Redash %s en %.2fs", query_id, duration)
                    rows = data.get("query_result", {}).get("data", {}).get("rows", [])
                    row = rows[0] if rows else {}
                    mapping = self.mappings[i]
                    value = self.extract_value(row, mapping["value"])
                    ratio = self.compute_ratio(row, mapping["ratio"])
                    self.master.after(
                        0,
                        lambda i=i, v=value, r=ratio: self.update_quadrant(i, v, r),
                    )
                ts = datetime.now().strftime("%H:%M:%S")
                self.master.after(0, lambda: self.update_timestamp(ts))
            except Exception as exc:  # pragma: no cover - simple logging
                logger.error("Erreur lors de l'actualisation: %s", exc)

        threading.Thread(target=lambda: asyncio.run(fetch()), daemon=True).start()

    def start_auto_refresh(self) -> None:
        self.refresh_data()
        self.master.after(15000, self.start_auto_refresh)

    def exit_fullscreen(self, event=None) -> None:
        self.master.attributes("-fullscreen", False)


def main() -> None:
    load_dotenv()
    api_key = os.getenv("REDASH_API_KEY", "")
    base_url = os.getenv("REDASH_BASE_URL", "")
    queries = [12, 34, 56, 78]
    mappings = [
        {"value": "value", "ratio": "conversion"},
        {"value": "value", "ratio": "conversion"},
        {"value": "value", "ratio": "conversion"},
        {"value": "value", "ratio": "conversion"},
    ]
    root = tk.Tk()
    DashboardApp(root, api_key, base_url, queries, mappings)
    root.mainloop()


if __name__ == "__main__":
    main()
