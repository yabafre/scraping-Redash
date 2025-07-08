# Dashboard de Ventes sur Raspberry Pi

Ce projet contient une application Tkinter affichant les données provenant de Redash. Elle est conçue pour fonctionner sur un Raspberry Pi en mode plein écran afin d'afficher un tableau de bord de ventes.

## Objectif

* Visualiser en continu les indicateurs clés issus de requêtes Redash.
* Utiliser un Raspberry Pi comme écran d'information autonome.

## Prérequis

1. **Raspberry Pi OS (64‑bit)** installé sur la carte microSD.
2. Mise à jour du système et installation de `pip` et de l'outil pour créer des environnements virtuels :
   ```bash
   sudo apt update && sudo apt upgrade -y
   sudo apt install python3-pip python3-venv unclutter
   ```
3. **Tkinter** est inclus avec Python. Si besoin :
   ```bash
   sudo apt install python3-tk
   ```

## Installation

1. **Création du projet et de l'environnement virtuel**
   ```bash
   mkdir ~/dashboard-project
   cd ~/dashboard-project
   python3 -m venv venv_dashboard
   source venv_dashboard/bin/activate
   ```
2. **Installation des dépendances Python**
   ```bash
   pip install httpx python-dotenv
   ```
3. **Création d'un fichier `.env`** contenant votre clé et l'URL Redash :
   ```bash
   REDASH_API_KEY=ma_cle
   REDASH_BASE_URL=https://redash.exemple.com
   ```
4. **Copie du fichier `dashboard.py`** du dépôt et configuration des IDs de requêtes.
4. **Test de l'application**
   ```bash
   python dashboard.py
   ```

## Lancement automatique avec systemd

Pour démarrer le dashboard au boot, créez un service systemd :

1. Fichier `/etc/systemd/system/dashboard.service` :
   ```ini
   [Unit]
   Description=Dashboard Ventes Redash
   After=network.target

   [Service]
   User=pi
   WorkingDirectory=/home/pi/dashboard-project
   EnvironmentFile=/home/pi/dashboard-project/.env
   ExecStart=/home/pi/dashboard-project/venv_dashboard/bin/python dashboard.py
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```
2. Activez le service :
   ```bash
   sudo systemctl enable dashboard.service
   sudo systemctl start dashboard.service
   ```

## Récapitulatif rapide

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip python3-venv unclutter
mkdir ~/dashboard-project && cd ~/dashboard-project
python3 -m venv venv_dashboard
source venv_dashboard/bin/activate
pip install httpx python-dotenv
python dashboard.py
```

Le Raspberry Pi est alors prêt à exécuter le tableau de bord automatiquement au prochain redémarrage. Pensez à personnaliser `dashboard.py` pour vos propres requêtes Redash.
