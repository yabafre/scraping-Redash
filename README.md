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
   pip install requests schedule
   ```
3. **Copie du fichier `dashboard.py`** du dépôt et configuration des variables `api_key`, `base_url` et des IDs de requêtes.
4. **Test de l'application**
   ```bash
   python dashboard.py
   ```

## Lancement automatique en mode plein écran

Pour démarrer le dashboard à l'ouverture de session :

1. Activez l'autologin dans `raspi-config` : `System Options` → `Boot / Auto Login` → `Desktop Autologin`.
2. Créez ou modifiez `~/.config/lxsession/LXDE-pi/autostart` et ajoutez :
   ```bash
   @lxpanel --profile LXDE-pi
   @pcmanfm --desktop --profile LXDE-pi
   @xscreensaver -no-splash
   @unclutter -idle 1
   @bash /home/pi/dashboard-project/run_dashboard.sh
   ```
3. Créez le script `~/dashboard-project/run_dashboard.sh` :
   ```bash
   #!/bin/bash
   cd /home/pi/dashboard-project
   source venv_dashboard/bin/activate
   python3 dashboard.py
   ```
   Rendez-le exécutable :
   ```bash
   chmod +x ~/dashboard-project/run_dashboard.sh
   ```
4. Optionnel : pour empêcher la mise en veille de l'écran, ajoutez dans `/etc/xdg/lxsession/LXDE-pi/autostart` :
   ```bash
   @xset s off
   @xset -dpms
   @xset s noblank
   ```

## Récapitulatif rapide

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip python3-venv unclutter
mkdir ~/dashboard-project && cd ~/dashboard-project
python3 -m venv venv_dashboard
source venv_dashboard/bin/activate
pip install requests schedule
python dashboard.py
```

Le Raspberry Pi est alors prêt à exécuter le tableau de bord automatiquement au prochain redémarrage. Pensez à personnaliser `dashboard.py` pour vos propres requêtes Redash.
