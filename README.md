Voilà un **README complet et à jour** pour ton dashboard Redash sur Raspberry Pi, en version claire, **vraiment plug & play**, avec tout ce qu’il faut (prérequis, env, dépendances réelles, .env, service systemd, tips SSH si besoin).
À la fin, je te mets aussi le bloc `requirement.txt` propre (préfère `pip install -r requirement.txt`).

---

````markdown
# Dashboard Ventes Redash – Raspberry Pi

Dashboard graphique pour afficher en temps réel les indicateurs clés (ventes, évolution…) via API Redash, conçu pour tourner en plein écran sur un Raspberry Pi.

---

## 🚦 Fonctionnalités

- Interface CustomTkinter : affichage moderne, chiffres XXL, animations confettis.
- Données live depuis Redash (requêtes paramétrables).
- Plug & play sur tout Raspberry Pi OS avec écran HDMI.
- Mode "kiosque" (plein écran, démarrage auto au boot).

---

## 🛠️ Prérequis système

- **Raspberry Pi** (modèle 3 minimum recommandé pour la réactivité).
- **Raspberry Pi OS 64‑bit** avec interface graphique ("Desktop").
- **Python 3.11+** (installé d’office sur Pi OS récent).
- **Accès internet** (pour installer les dépendances au setup).

---

## 📦 Installation étape par étape

1. **Préparer le Pi**
   ```bash
   sudo apt update && sudo apt upgrade -y
   sudo apt install python3-pip python3-venv python3-tk unclutter git
````

2. **Cloner le projet ou copier les fichiers**

   ```bash
   git clone <url-du-dépôt> ~/dashboard-project
   cd ~/dashboard-project
   ```

3. **Créer l'environnement virtuel**

   ```bash
   python3 -m venv venv_dashboard
   source venv_dashboard/bin/activate
   ```

4. **Installer les dépendances Python**

   > **Astuce :** utilise le fichier requirement.txt pour tout installer d’un coup

   ```bash
   pip install -r requirement.txt
   ```

   Si tu n’as pas `requirement.txt`, installe à la main :

   ```bash
   pip install customtkinter httpx python-dotenv pillow
   ```

5. **Préparer le fichier `.env`**

   ```env
   # Dans ~/dashboard-project/.env
   REDASH_BASE_URL=https://ton.redash.url
   KEY_EVOL=ta_clé_api_1
   KEY_CA_J1=ta_clé_api_2
   KEY_CA_JN=ta_clé_api_3
   ```

   > Les noms des variables doivent matcher les attentes du code.

6. **Lancer le dashboard**

   ```bash
   python dashboard.py
   ```

---

## 🪩 Lancement auto au boot (optionnel, mode borne)

Pour lancer le dashboard automatiquement au démarrage du Pi :

1. **Créer le service systemd**

   ```ini
   # /etc/systemd/system/dashboard.service
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
   WantedBy=graphical.target
   ```

2. **Activer et démarrer**

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable dashboard.service
   sudo systemctl start dashboard.service
   ```

---

## 🖥️ Contrôle à distance (SSH)

* **Activer le SSH sur le Pi**

  ```bash
  sudo raspi-config
  # Interface > SSH > Enable
  ```
* **Se connecter à distance :**

  ```bash
  ssh pi@ip.du.pi
  ```

> Attention : l’interface graphique s’affiche *localement* sur l’écran du Pi, pas à travers SSH (sauf X11 forwarding – lent).

---

## 📄 Example requirement.txt

```txt
anyio==4.9.0
certifi==2025.7.9
customtkinter==5.2.2
darkdetect==0.8.0
h11==0.16.0
httpcore==1.0.9
httpx==0.28.1
idna==3.10
packaging==25.0
pillow==11.3.0
python-dotenv==1.1.1
sniffio==1.3.1
typing_extensions==4.14.1
```

---

## 🧑‍💻 Dépannage rapide

* **Fenêtre ne s’ouvre pas** : tu es probablement connecté en SSH sans X11 (impossible d’ouvrir une GUI sans écran ou X11).
* **Erreur "no display name and no \$DISPLAY"** : même raison, la GUI ne peut se lancer que sur un écran relié au Pi ou via un bureau à distance (ou X11, mais lent).
* **Confettis/animations ne s’affichent pas** : vérifier la présence des fichiers GIF dans `gifts/` et les droits sur le dossier.

---

## ✨ Astuces

* Pour un vrai affichage kiosque, pense à `unclutter` pour cacher la souris, et à désactiver l’économiseur d’écran.
* Tu peux créer un script `dashboard.sh` :

  ```bash
  #!/bin/bash
  cd ~/dashboard-project
  source venv_dashboard/bin/activate
  python dashboard.py
  ```

  Puis :
  `chmod +x dashboard.sh`

---

## 🏁 Résumé setup

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3-pip python3-venv python3-tk unclutter git
git clone <repo> ~/dashboard-project
cd ~/dashboard-project
python3 -m venv venv_dashboard
source venv_dashboard/bin/activate
pip install -r requirement.txt
# Crée le .env puis :
python dashboard.py
```


