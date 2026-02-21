# 🏰 DDV Checklist — Disney Dreamlight Valley

Une application desktop complète pour suivre ta progression dans **Disney Dreamlight Valley**, avec un bot Discord intégré pour les notifications et rappels.

---

## ✨ Fonctionnalités

### Application Desktop (`dreamlight_checklist.py`)
- ✅ **Checklist quotidienne** — tâches personnalisables avec catégories, priorités et cooldowns
- 👥 **Gestion des villageois** — suivi des niveaux d'amitié et des cadeaux quotidiens
- 🏆 **Trophées** — suivi de progression (Platine, Or, Argent, Bronze)
- 📊 **Statistiques & graphiques** — historique, streaks, répartition des niveaux
- 🌿 **Ressources par biome** — checklist de collecte par zone
- 🎪 **Tâches événementielles** — suivi des events limités
- 👤 **Multi-comptes** — plusieurs profils de joueur indépendants
- 💀 **Mode Hardcore** — streak remis à zéro si la journée n'est pas complète
- 🌙 **Thème clair/sombre** — changement à chaud
- 📤 **Export CSV / PDF** — sauvegarde de ta progression

### Bot Discord (`bot_discord.py`)
- `/daily` — affiche les tâches du jour avec boutons interactifs ✅
- `/streak` — affiche le streak actuel et le record
- `/trophee` — infos et progression d'un trophée
- `/stats` — résumé global de la progression
- `/rappel` — active/désactive les rappels quotidiens à 22h
- `/bestioles` — active/désactive les notifications bestioles rares
- `/bestioles_now` — affiche les bestioles rares actives en ce moment
- 🐾 **Watcher automatique** — notification en temps réel dès qu'une bestiole rare apparaît

---

## 🛠️ Installation

### Prérequis

- Python **3.10+**
- pip

### Dépendances

```bash
# Application desktop (obligatoire)
pip install customtkinter

# Bot Discord (optionnel)
pip install discord.py

# Export PDF (optionnel)
pip install fpdf2
```

---

## 🚀 Lancement

### Application Desktop

```bash
python dreamlight_checklist.py
```

> La base de données SQLite est créée automatiquement dans `~/.ddv_checklist/ddv.db` au premier lancement.

### Bot Discord

1. Va sur [discord.com/developers/applications](https://discord.com/developers/applications)
2. Crée une application → onglet **Bot** → **Reset Token** → copie le token
3. Dans **OAuth2 > URL Generator** : coche `bot` + `applications.commands`
4. Colle ton token dans `bot_discord.py` (variable `BOT_TOKEN`)
5. Lance le bot :

```bash
python bot_discord.py
```

> ⚠️ Lance d'abord `dreamlight_checklist.py` au moins une fois pour initialiser la base de données.

---

## 📦 Compilation en `.exe` (Windows)

```bash
python -m PyInstaller --onefile --windowed --clean \
  --exclude-module matplotlib \
  --exclude-module scipy \
  --exclude-module numpy.testing \
  --exclude-module tkinter.test \
  dreamlight_checklist.py
```

L'exécutable sera généré dans le dossier `dist/`.

---

## 🗄️ Architecture

```
project/
├── dreamlight_checklist.py   # Application desktop principale
├── dreamlight_checklist.spec # Config PyInstaller
├── bot_discord.py            # Bot Discord
└── bot_discord.spec          # Config PyInstaller (bot)
```

**Base de données partagée :** `~/.ddv_checklist/ddv.db`

Les deux composants (app desktop + bot Discord) lisent et écrivent dans la même base SQLite — pas besoin de synchronisation manuelle.

### Tables SQLite

| Table | Description |
|---|---|
| `accounts` | Profils multi-comptes |
| `daily_tasks` | État des tâches par jour |
| `tasks_meta` | Métadonnées des tâches (nom, catégorie, priorité…) |
| `villagers` | Suivi quotidien des villageois |
| `villager_levels` | Niveaux d'amitié persistants |
| `trophies` | Progression des trophées |
| `streak` | Streak actuel, dernier jour complet, record |
| `history` | Historique quotidien (tâches faites/total) |
| `biome_resources` | Ressources collectées par biome |
| `event_tasks` | Tâches des événements limités |
| `preferences` | Préférences utilisateur |

---

## 🐾 Bestioles rares suivies

| Bestiole | Biome | Rareté |
|---|---|---|
| 🐿️ Écureuil Noir | Plaza | Dimanche, 8h–20h |
| 🐰 Lapin Calico | Clairière Paisible | Dimanche, 8h–14h |
| 🐢 Tortue Violette | Plage Ensoleillée | Lun. & Dim., 20h–6h |
| 🦝 Raton Laveur Bleu | Forêt des Rêves | Mercredi, 16h–22h |
| 🐊 Crocodile Doré | Clairière de Confiance | Dimanche, 8h–14h |
| 🦜 Oiseau Violet | Plateau Ensoleillé | Dimanche, 8h–14h |
| 🦊 Renard Arc-en-ciel | Sommets Enneigés | Dimanche, 8h–14h |
| 🐦 Corbeau Doré | Terres Oubliées | Dimanche, 20h–2h |

---

## ⚙️ Configuration du bot Discord

| Variable | Description | Défaut |
|---|---|---|
| `BOT_TOKEN` | Token Discord du bot | *(à renseigner)* |
| `GUILD_ID` | ID du serveur pour sync instantanée | `None` (global) |
| `RAPPEL_HEURE` | Heure du rappel quotidien | `22` |
| `RAPPEL_MINUTE` | Minute du rappel quotidien | `0` |

---

## 📝 Licence

Projet personnel — non affilié à Disney ou Gameloft.