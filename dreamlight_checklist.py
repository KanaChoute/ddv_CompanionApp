# -*- coding: utf-8 -*-
"""
Disney Dreamlight Valley — Checklist Complète (Refactored)
═══════════════════════════════════════════════════════════
Améliorations vs version originale :
  • CustomTkinter  : UI moderne, coins arrondis, thème natif à chaud
  • SQLite         : Remplacement complet des JSON — atomique, multi-comptes propre
  • PyInstaller    : Imports séparés pour réduire le bundle, no matplotlib
  • Architecture  : AppState centralisé, plus de variables globales dispersées
  • Bot Discord   : Infrastructure prête dans bot_discord.py séparé

Dépendances :
    pip install customtkinter
    pip install discord.py          (uniquement pour le bot)
    pip install fpdf2               (pour les PDF, remplace reportlab)

Compilation .exe :
    python -m PyInstaller --onefile --windowed --clean
           --exclude-module matplotlib --exclude-module scipy
           --exclude-module numpy.testing --exclude-module tkinter.test
           dreamlight_checklist.py
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, simpledialog, filedialog
import sqlite3, os, csv, time, io, json
from datetime import date, timedelta, datetime
from pathlib import Path

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIGURATION DOSSIERS & BASE DE DONNÉES
# ══════════════════════════════════════════════════════════════════════════════

CONFIG_DIR = Path.home() / ".ddv_checklist"
CONFIG_DIR.mkdir(exist_ok=True)
DB_PATH = CONFIG_DIR / "ddv.db"
PREFS_PATH = CONFIG_DIR / "preferences.json"


def get_db() -> sqlite3.Connection:
    """Retourne une connexion SQLite avec foreign keys activées."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Crée les tables si elles n'existent pas.
    Si le fichier DB est corrompu (ex: ancien JSON renommé), il est supprimé et recréé.
    """
    # Vérifie que le fichier est bien un SQLite valide avant d'aller plus loin
    if DB_PATH.exists():
        test_conn = None
        is_corrupt = False
        try:
            test_conn = sqlite3.connect(DB_PATH)
            test_conn.execute("PRAGMA integrity_check")
        except sqlite3.DatabaseError:
            is_corrupt = True
        finally:
            if test_conn:
                test_conn.close()   # ← obligatoire sur Windows avant tout déplacement/suppression
        if is_corrupt:
            try:
                backup = DB_PATH.with_suffix(".db.bak")
                if backup.exists():
                    backup.unlink()
                DB_PATH.rename(backup)
                print(f"[DDV] DB corrompue renommée en {backup.name}. Recréation...")
            except OSError:
                # En dernier recours : suppression directe
                DB_PATH.unlink(missing_ok=True)
                print("[DDV] DB corrompue supprimée. Recréation...")

    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS accounts (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            );
            INSERT OR IGNORE INTO accounts(name) VALUES('default');

            CREATE TABLE IF NOT EXISTS daily_tasks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id  INTEGER NOT NULL REFERENCES accounts(id),
                task_date   TEXT NOT NULL,
                task_idx    INTEGER NOT NULL,
                checked     INTEGER NOT NULL DEFAULT 0,
                UNIQUE(account_id, task_date, task_idx)
            );

            CREATE TABLE IF NOT EXISTS tasks_meta (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id  INTEGER NOT NULL REFERENCES accounts(id),
                task_idx    INTEGER NOT NULL,
                name        TEXT NOT NULL,
                category    TEXT NOT NULL DEFAULT 'Autre',
                priority    TEXT NOT NULL DEFAULT 'medium',
                cooldown    INTEGER,
                optional    INTEGER NOT NULL DEFAULT 0,
                note        TEXT NOT NULL DEFAULT '',
                UNIQUE(account_id, task_idx)
            );

            CREATE TABLE IF NOT EXISTS villagers (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id  INTEGER NOT NULL REFERENCES accounts(id),
                name        TEXT NOT NULL,
                task_date   TEXT NOT NULL,
                level       INTEGER NOT NULL DEFAULT 1,
                checked     INTEGER NOT NULL DEFAULT 0,
                gift1       INTEGER NOT NULL DEFAULT 0,
                gift2       INTEGER NOT NULL DEFAULT 0,
                gift3       INTEGER NOT NULL DEFAULT 0,
                UNIQUE(account_id, name, task_date)
            );

            CREATE TABLE IF NOT EXISTS villager_levels (
                account_id  INTEGER NOT NULL REFERENCES accounts(id),
                name        TEXT NOT NULL,
                level       INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(account_id, name)
            );

            CREATE TABLE IF NOT EXISTS trophies (
                account_id  INTEGER NOT NULL REFERENCES accounts(id),
                trophy_id   TEXT NOT NULL,
                unlocked    INTEGER NOT NULL DEFAULT 0,
                progress    INTEGER NOT NULL DEFAULT 0,
                note        TEXT NOT NULL DEFAULT '',
                PRIMARY KEY(account_id, trophy_id)
            );

            CREATE TABLE IF NOT EXISTS streak (
                account_id          INTEGER PRIMARY KEY REFERENCES accounts(id),
                count               INTEGER NOT NULL DEFAULT 0,
                last_complete_date  TEXT NOT NULL DEFAULT '',
                best                INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS history (
                account_id  INTEGER NOT NULL REFERENCES accounts(id),
                task_date   TEXT NOT NULL,
                done        INTEGER NOT NULL DEFAULT 0,
                total       INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(account_id, task_date)
            );

            CREATE TABLE IF NOT EXISTS biome_resources (
                account_id  INTEGER NOT NULL REFERENCES accounts(id),
                task_date   TEXT NOT NULL,
                biome       TEXT NOT NULL,
                resource    TEXT NOT NULL,
                checked     INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(account_id, task_date, biome, resource)
            );

            CREATE TABLE IF NOT EXISTS event_tasks (
                account_id  INTEGER NOT NULL REFERENCES accounts(id),
                event_name  TEXT NOT NULL,
                task_name   TEXT NOT NULL,
                checked     INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(account_id, event_name, task_name)
            );

            CREATE TABLE IF NOT EXISTS preferences (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)


# ══════════════════════════════════════════════════════════════════════════════
#  APP STATE — remplace toutes les variables globales dispersées
# ══════════════════════════════════════════════════════════════════════════════

class DDVState:
    """Conteneur centralisé pour tout l'état mutable de l'application."""

    def __init__(self):
        self.current_account: str = "default"
        self.account_id: int = 1
        self.today: str = date.today().isoformat()

        self.daily_checked: list[bool] = []
        self.tasks_meta: list[dict] = []
        self.cooldown_timers: dict[str, float] = {}

        self.villagers_data: dict[str, dict] = {}
        self.dlc_enabled: dict[str, bool] = {"dlc1": False, "dlc2": False, "dlc3": False}

        self.trophy_data: dict[str, dict] = {}
        self.biome_data: dict[str, dict] = {}
        self.event_data: dict[str, dict] = {}

        self.streak: dict = {"count": 0, "last_complete_date": "", "best": 0}
        self.history: dict[str, dict] = {}

        self.hardcore_mode: bool = False
        self.theme: str = "dark"

    def get_account_id(self, name: str) -> int:
        with get_db() as conn:
            row = conn.execute("SELECT id FROM accounts WHERE name=?", (name,)).fetchone()
            return row["id"] if row else 1

    def load(self, account: str = "default"):
        self.current_account = account
        self.today = date.today().isoformat()

        # Ensure account exists
        with get_db() as conn:
            conn.execute("INSERT OR IGNORE INTO accounts(name) VALUES(?)", (account,))
            row = conn.execute("SELECT id FROM accounts WHERE name=?", (account,)).fetchone()
            self.account_id = row["id"]

        self._load_tasks_meta()
        self._load_daily_checked()
        self._load_villagers()
        self._load_trophies()
        self._load_biomes()
        self._load_events()
        self._load_streak()
        self._load_history()
        self._load_preferences()

    def _load_tasks_meta(self):
        with get_db() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks_meta WHERE account_id=? ORDER BY task_idx",
                (self.account_id,)
            ).fetchall()
            if rows:
                self.tasks_meta = [dict(r) for r in rows]
            else:
                # Première fois : insérer les tâches par défaut
                self.tasks_meta = [dict(t) | {"note": ""} for t in DEFAULT_TASKS]
                for i, t in enumerate(self.tasks_meta):
                    conn.execute(
                        """INSERT OR IGNORE INTO tasks_meta
                           (account_id, task_idx, name, category, priority, cooldown, optional, note)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        (self.account_id, i, t["name"], t["category"], t["priority"],
                         t.get("cooldown"), int(t.get("optional", False)), t.get("note", ""))
                    )

    def _load_daily_checked(self):
        self.daily_checked = [False] * len(self.tasks_meta)
        with get_db() as conn:
            rows = conn.execute(
                "SELECT task_idx, checked FROM daily_tasks WHERE account_id=? AND task_date=?",
                (self.account_id, self.today)
            ).fetchall()
            for r in rows:
                idx = r["task_idx"]
                if idx < len(self.daily_checked):
                    self.daily_checked[idx] = bool(r["checked"])

    def _load_villagers(self):
        with get_db() as conn:
            # Niveaux persistants
            levels = {r["name"]: r["level"] for r in conn.execute(
                "SELECT name, level FROM villager_levels WHERE account_id=?",
                (self.account_id,)
            ).fetchall()}
            # État quotidien
            daily = {r["name"]: dict(r) for r in conn.execute(
                "SELECT * FROM villagers WHERE account_id=? AND task_date=?",
                (self.account_id, self.today)
            ).fetchall()}

        self.villagers_data = {}
        for name in ALL_VILLAGERS:
            lvl = levels.get(name, 1)
            d = daily.get(name, {})
            self.villagers_data[name] = {
                "level":   lvl,
                "checked": bool(d.get("checked", 0)),
                "gifts":   [bool(d.get("gift1", 0)), bool(d.get("gift2", 0)), bool(d.get("gift3", 0))],
            }

    def _load_trophies(self):
        with get_db() as conn:
            rows = conn.execute(
                "SELECT trophy_id, unlocked, progress, note FROM trophies WHERE account_id=?",
                (self.account_id,)
            ).fetchall()
        saved = {r["trophy_id"]: dict(r) for r in rows}
        self.trophy_data = {}
        for t in TROPHIES:
            self.trophy_data[t["id"]] = saved.get(t["id"], {"unlocked": False, "progress": 0, "note": ""})

    def _load_biomes(self):
        with get_db() as conn:
            rows = conn.execute(
                "SELECT biome, resource, checked FROM biome_resources WHERE account_id=? AND task_date=?",
                (self.account_id, self.today)
            ).fetchall()
        saved = {(r["biome"], r["resource"]): bool(r["checked"]) for r in rows}
        self.biome_data = {}
        for biome, res in BIOMES.items():
            self.biome_data[biome] = {}
            for cat, items in res.items():
                for item in items:
                    key = f"{cat}:{item}"
                    self.biome_data[biome][key] = saved.get((biome, key), False)

    def _load_events(self):
        with get_db() as conn:
            rows = conn.execute(
                "SELECT event_name, task_name, checked FROM event_tasks WHERE account_id=?",
                (self.account_id,)
            ).fetchall()
        saved = {(r["event_name"], r["task_name"]): bool(r["checked"]) for r in rows}
        self.event_data = {}
        for ev in DEFAULT_EVENTS:
            self.event_data[ev["name"]] = {
                t: saved.get((ev["name"], t), False) for t in ev["tasks"]
            }

    def _load_streak(self):
        with get_db() as conn:
            row = conn.execute(
                "SELECT count, last_complete_date, best FROM streak WHERE account_id=?",
                (self.account_id,)
            ).fetchone()
            if row:
                self.streak = dict(row)
            else:
                self.streak = {"count": 0, "last_complete_date": "", "best": 0}

    def _load_history(self):
        with get_db() as conn:
            rows = conn.execute(
                "SELECT task_date, done, total FROM history WHERE account_id=?",
                (self.account_id,)
            ).fetchall()
        self.history = {r["task_date"]: {"done": r["done"], "total": r["total"]} for r in rows}

    def _load_preferences(self):
        with get_db() as conn:
            rows = conn.execute("SELECT key, value FROM preferences").fetchall()
        prefs = {r["key"]: r["value"] for r in rows}
        self.theme = prefs.get("theme", "dark")
        self.hardcore_mode = prefs.get("hardcore_mode", "0") == "1"

        # Legacy migration from old JSON preferences file
        if PREFS_PATH.exists():
            try:
                old = json.loads(PREFS_PATH.read_text())
                self.theme = old.get("theme", self.theme)
                PREFS_PATH.unlink()
            except Exception:
                pass

    # ── Sauvegarde atomique dans SQLite ──────────────────────────────────────

    def save_all(self):
        with get_db() as conn:
            self._save_tasks_meta(conn)
            self._save_daily_checked(conn)
            self._save_villagers(conn)
            self._save_trophies(conn)
            self._save_biomes(conn)
            self._save_events(conn)
            self._save_streak(conn)
            self._save_history(conn)
            self._save_preferences(conn)

    def _save_tasks_meta(self, conn):
        for i, t in enumerate(self.tasks_meta):
            conn.execute(
                """INSERT INTO tasks_meta(account_id,task_idx,name,category,priority,cooldown,optional,note)
                   VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(account_id,task_idx) DO UPDATE SET
                   name=excluded.name, category=excluded.category, priority=excluded.priority,
                   cooldown=excluded.cooldown, optional=excluded.optional, note=excluded.note""",
                (self.account_id, i, t["name"], t["category"], t["priority"],
                 t.get("cooldown"), int(t.get("optional", False)), t.get("note", ""))
            )

    def _save_daily_checked(self, conn):
        for i, checked in enumerate(self.daily_checked):
            conn.execute(
                """INSERT INTO daily_tasks(account_id,task_date,task_idx,checked)
                   VALUES(?,?,?,?)
                   ON CONFLICT(account_id,task_date,task_idx) DO UPDATE SET checked=excluded.checked""",
                (self.account_id, self.today, i, int(checked))
            )

    def _save_villagers(self, conn):
        for name, d in self.villagers_data.items():
            conn.execute(
                """INSERT INTO villager_levels(account_id,name,level) VALUES(?,?,?)
                   ON CONFLICT(account_id,name) DO UPDATE SET level=excluded.level""",
                (self.account_id, name, d["level"])
            )
            g = d["gifts"]
            conn.execute(
                """INSERT INTO villagers(account_id,name,task_date,level,checked,gift1,gift2,gift3)
                   VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(account_id,name,task_date) DO UPDATE SET
                   level=excluded.level,checked=excluded.checked,
                   gift1=excluded.gift1,gift2=excluded.gift2,gift3=excluded.gift3""",
                (self.account_id, name, self.today, d["level"],
                 int(d["checked"]), int(g[0]), int(g[1]), int(g[2]))
            )

    def _save_trophies(self, conn):
        for tid, td in self.trophy_data.items():
            conn.execute(
                """INSERT INTO trophies(account_id,trophy_id,unlocked,progress,note)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(account_id,trophy_id) DO UPDATE SET
                   unlocked=excluded.unlocked,progress=excluded.progress,note=excluded.note""",
                (self.account_id, tid, int(td["unlocked"]), td["progress"], td.get("note", ""))
            )

    def _save_biomes(self, conn):
        for biome, res in self.biome_data.items():
            for key, val in res.items():
                conn.execute(
                    """INSERT INTO biome_resources(account_id,task_date,biome,resource,checked)
                       VALUES(?,?,?,?,?)
                       ON CONFLICT(account_id,task_date,biome,resource) DO UPDATE SET checked=excluded.checked""",
                    (self.account_id, self.today, biome, key, int(val))
                )

    def _save_events(self, conn):
        for ev_name, tasks in self.event_data.items():
            for task_name, checked in tasks.items():
                conn.execute(
                    """INSERT INTO event_tasks(account_id,event_name,task_name,checked)
                       VALUES(?,?,?,?)
                       ON CONFLICT(account_id,event_name,task_name) DO UPDATE SET checked=excluded.checked""",
                    (self.account_id, ev_name, task_name, int(checked))
                )

    def _save_streak(self, conn):
        conn.execute(
            """INSERT INTO streak(account_id,count,last_complete_date,best)
               VALUES(?,?,?,?)
               ON CONFLICT(account_id) DO UPDATE SET
               count=excluded.count,last_complete_date=excluded.last_complete_date,best=excluded.best""",
            (self.account_id, self.streak["count"],
             self.streak["last_complete_date"], self.streak["best"])
        )

    def _save_history(self, conn):
        for d_str, entry in self.history.items():
            conn.execute(
                """INSERT INTO history(account_id,task_date,done,total)
                   VALUES(?,?,?,?)
                   ON CONFLICT(account_id,task_date) DO UPDATE SET done=excluded.done,total=excluded.total""",
                (self.account_id, d_str, entry["done"], entry["total"])
            )

    def _save_preferences(self, conn):
        conn.execute(
            "INSERT INTO preferences(key,value) VALUES('theme',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (self.theme,)
        )
        conn.execute(
            "INSERT INTO preferences(key,value) VALUES('hardcore_mode',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ("1" if self.hardcore_mode else "0",)
        )

    def get_accounts(self) -> list[str]:
        with get_db() as conn:
            rows = conn.execute("SELECT name FROM accounts ORDER BY name").fetchall()
        return [r["name"] for r in rows]

    def create_account(self, name: str):
        with get_db() as conn:
            conn.execute("INSERT OR IGNORE INTO accounts(name) VALUES(?)", (name,))

    def reset_day(self):
        for i in range(len(self.daily_checked)):
            self.daily_checked[i] = False
        for n in self.villagers_data:
            self.villagers_data[n]["checked"] = False
            self.villagers_data[n]["gifts"] = [False, False, False]
        self.cooldown_timers.clear()
        for bn in self.biome_data:
            for k in self.biome_data[bn]:
                self.biome_data[bn][k] = False
        self.save_all()

    def reset_all(self):
        self.reset_day()
        for n in self.villagers_data:
            self.villagers_data[n] = {"level": 1, "checked": False, "gifts": [False, False, False]}
        for t in TROPHIES:
            self.trophy_data[t["id"]] = {"unlocked": False, "progress": 0, "note": ""}
        self.history.clear()
        self.streak = {"count": 0, "last_complete_date": "", "best": 0}
        self.save_all()


# ══════════════════════════════════════════════════════════════════════════════
#  DONNÉES STATIQUES
# ══════════════════════════════════════════════════════════════════════════════

TROPHIES = [
    {"id":"plat_01","name":"Maître de Dreamlight","description":"Obtenir tous les trophées",
     "type":"platinum","theme":"Général","condition":"Débloquer les 15 autres trophées",
     "max_value":None,"difficulty":"Très difficile","rarity":7.76,
     "tip":"Le dernier à tomber — nécessite ~300 jours à cause des Épines nocturnes."},
    {"id":"gold_01","name":"Fléau des épines","description":"Éliminer 3 000 Épines nocturnes",
     "type":"gold","theme":"Exploration","condition":"Retirer 3 000 Épines nocturnes (max 10/jour)",
     "max_value":3000,"difficulty":"Très difficile","rarity":9.0,
     "tip":"10 épines/jour → ~300 jours minimum. Le trophée le plus long du jeu."},
    {"id":"gold_02","name":"Virtuose de la pêche","description":"Pêcher 1 800 poissons",
     "type":"gold","theme":"Collecte","condition":"Réclamer la récompense 'Pêcher 1 800 poissons'",
     "max_value":1800,"difficulty":"Difficile","rarity":18.0,
     "tip":"Pas de limite journalière. Varie les biomes pour progresser sur d'autres tâches."},
    {"id":"gold_03","name":"Géologue","description":"Extraire des minerais 1 800 fois",
     "type":"gold","theme":"Collecte","condition":"Réclamer la récompense 'Extraire 1 800 minerais'",
     "max_value":1800,"difficulty":"Difficile","rarity":18.0,
     "tip":"Aucune limite journalière. À combiner avec la pêche."},
    {"id":"gold_04","name":"Chef hors pair","description":"Cuisiner 900 plats",
     "type":"gold","theme":"Cuisine","condition":"Réclamer la récompense 'Cuisiner 900 plats'",
     "max_value":900,"difficulty":"Moyen","rarity":25.0,
     "tip":"Cuire des plats à 1 ingrédient sur plusieurs feux accélère."},
    {"id":"gold_05","name":"Main verte","description":"Récolter 4 500 légumes",
     "type":"gold","theme":"Collecte","condition":"Réclamer la récompense 'Récolter 4 500 légumes'",
     "max_value":4500,"difficulty":"Moyen","rarity":26.0,
     "tip":"Agrandir le jardin de Wall-E et planter des cultures à pousse rapide."},
    {"id":"gold_06","name":"Camarade suprême","description":"Avoir 15 meilleurs amis (niveau 10)",
     "type":"gold","theme":"Social","condition":"Atteindre le niveau 10 avec 15 villageois",
     "max_value":15,"difficulty":"Moyen","rarity":27.0,
     "tip":"Assigne des villageois à des professions pour XP passif."},
    {"id":"gold_07","name":"Exemple de générosité","description":"Offrir 540 cadeaux",
     "type":"gold","theme":"Social","condition":"Réclamer la récompense 'Offrir 540 cadeaux'",
     "max_value":540,"difficulty":"Moyen","rarity":30.0,
     "tip":"3 cadeaux/jour/villageois. Avec 52 villageois de base c'est vite bouclé."},
    {"id":"gold_08","name":"Économe","description":"Récupérer 1 800 000 pièces étoiles",
     "type":"gold","theme":"Commerce","condition":"Réclamer la récompense '1 800 000 pièces étoiles'",
     "max_value":1800000,"difficulty":"Moyen","rarity":35.0,
     "tip":"Vendre des plats cuisinés rapporte bien plus que des ressources brutes."},
    {"id":"gold_09","name":"Toujours en mission","description":"Accomplir 1 100 Missions Dreamlight",
     "type":"gold","theme":"Quêtes","condition":"Réclamer la récompense '1 100 Missions Dreamlight'",
     "max_value":1100,"difficulty":"Facile","rarity":24.52,
     "tip":"S'accumule naturellement. Vérifie régulièrement le menu Dreamlight."},
    {"id":"silver_01","name":"Moulin à paroles","description":"Engager 1 000 discussions quotidiennes",
     "type":"silver","theme":"Social","condition":"Réclamer la récompense '1 000 discussions quotidiennes'",
     "max_value":1000,"difficulty":"Long","rarity":38.0,
     "tip":"1 discussion/jour/villageois. Avec 52 villageois = ~19 jours si tu parles à tous."},
    {"id":"silver_02","name":"Actionnaire de Dingo","description":"Débloquer tous les stands de Dingo",
     "type":"silver","theme":"Commerce","condition":"Réparer tous les stands de Dingo dans chaque biome",
     "max_value":None,"difficulty":"Facile","rarity":54.0,
     "tip":"Un stand par biome. Nécessite d'abord de débloquer tous les biomes."},
    {"id":"silver_03","name":"Spécialiste en rénovation","description":"Construire 30 maisons",
     "type":"silver","theme":"Construction","condition":"Construire ou déplacer 30 maisons de villageois",
     "max_value":30,"difficulty":"Facile","rarity":55.0,
     "tip":"Déplacer une maison compte aussi."},
    {"id":"silver_04","name":"As de la construction","description":"Améliorer sa maison au maximum",
     "type":"silver","theme":"Construction","condition":"Améliorer sa maison au niveau max chez Picsou",
     "max_value":None,"difficulty":"Moyen","rarity":52.0,
     "tip":"Coûte de plus en plus cher à chaque niveau. Commence tôt !"},
    {"id":"bronze_01","name":"Providence de la vallée","description":"Débloquer tous les biomes",
     "type":"bronze","theme":"Exploration","condition":"Débloquer les 8 biomes",
     "max_value":None,"difficulty":"Facile","rarity":62.0,
     "tip":"Nécessaire pour les quêtes principales. Se fait naturellement."},
    {"id":"bronze_02","name":"Photographe","description":"Prendre 50 photos",
     "type":"bronze","theme":"Général","condition":"Prendre 50 photos avec le téléphone",
     "max_value":50,"difficulty":"Très facile","rarity":72.0,
     "tip":"Équipe le téléphone et enchaîne les photos. ~5 minutes."},
]

TROPHY_TYPE_INFO = {
    "platinum": ("🏆", "Platine", "#b0c4de"),
    "gold":     ("🥇", "Or",      "#ffd700"),
    "silver":   ("🥈", "Argent",  "#c0c0c0"),
    "bronze":   ("🥉", "Bronze",  "#cd7f32"),
}
TROPHY_THEMES = sorted(set(t["theme"] for t in TROPHIES))

DEFAULT_TASKS = [
    {"name":"Discuter avec chaque villageois",                      "category":"Social",   "priority":"high",  "cooldown":None, "optional":False},
    {"name":"Ouvrir coffre vert et bleu (Moonstones)",              "category":"Collecte", "priority":"high",  "cooldown":None, "optional":False},
    {"name":"Nourrir chaque bestiole (critters)",                   "category":"Social",   "priority":"medium","cooldown":None, "optional":False},
    {"name":"Récolter jardin Wall-E (30+ cultures)",                "category":"Collecte", "priority":"high",  "cooldown":None, "optional":False},
    {"name":"Récupérer poissons bateau Moana",                      "category":"Collecte", "priority":"high",  "cooldown":7200, "optional":False},
    {"name":"Acheter blueprint Eric (si dispo)",                    "category":"Commerce", "priority":"low",   "cooldown":None, "optional":True},
    {"name":"Nettoyer Night Thorns (10/jour)",                      "category":"Collecte", "priority":"medium","cooldown":None, "optional":False},
    {"name":"Récolter ressources : fleurs, fruits, bois, minerais", "category":"Collecte", "priority":"medium","cooldown":None, "optional":False},
    {"name":"Pêcher dans tous les biomes",                          "category":"Collecte", "priority":"medium","cooldown":None, "optional":False},
    {"name":"Vérifier boutiques Scrooge/Kristoff/stands",           "category":"Commerce", "priority":"medium","cooldown":None, "optional":False},
    {"name":"Compléter quêtes Dreamlight Duties du jour",           "category":"Quêtes",   "priority":"high",  "cooldown":None, "optional":False},
    {"name":"Récolter Dreamlight Fruits (si Simba débloqué)",       "category":"Collecte", "priority":"low",   "cooldown":None, "optional":True},
]
CATEGORIES = ["Collecte", "Social", "Commerce", "Quêtes", "Autre"]
PRIORITIES  = {"high": ("🔴", "Prioritaire"), "medium": ("🟡", "Normal"), "low": ("🟢", "Optionnel")}

BIOMES = {
    "Clairière Paisible":  {"poissons":["Poisson-clown","Poisson rouge"],"fleurs":["Fleur de coton blanc","Fleur de Rêve bleue"],"minerais":["Or","Fer"],"bestioles":["Écureuil","Lapin"],"fruits":["Pomme","Bleuet"]},
    "Forêt des Rêves":     {"poissons":["Anguille","Carpe"],"fleurs":["Fleur de Rêve rouge","Jonquille"],"minerais":["Cobalt","Shiny Shards"],"bestioles":["Chouette","Renard"],"fruits":["Myrtille"]},
    "Plage Ensoleillée":   {"poissons":["Crevette","Saumon","Poisson-lune"],"fleurs":["Fleur de sable","Cosmos orange"],"minerais":["Sable de verre","Corail"],"bestioles":["Tortue de mer","Crabe"],"fruits":["Noix de coco"]},
    "Terres Oubliées":     {"poissons":["Brochet","Perche"],"fleurs":["Fleur Nocturnale","Rose noire"],"minerais":["Onyx","Topaze"],"bestioles":["Corbeau","Chauve-souris"],"fruits":["Citrouille","Grenade"]},
    "Savane Brillante":    {"poissons":["Tilapia","Poisson-chat"],"fleurs":["Fleur de savane","Hibiscus jaune"],"minerais":["Citrouille dorée","Améthyste"],"bestioles":["Gazelle","Éléphant"],"fruits":["Mangue","Banane"]},
    "Marais Brumeux":      {"poissons":["Grenouille","Anguille des marais"],"fleurs":["Nénuphar","Iris violet"],"minerais":["Tourbe","Emeraude"],"bestioles":["Libellule","Alligator"],"fruits":["Fruit de la passion"]},
    "Sommet Enneigé":      {"poissons":["Truite arc-en-ciel","Poisson des glaces"],"fleurs":["Fleur de givre","Héliotrope"],"minerais":["Glace","Diamant"],"bestioles":["Renard arctique","Pingouin"],"fruits":["Groseille"]},
    "Royaume Ancien":      {"poissons":["Poisson fantôme","Lotte"],"fleurs":["Orchidée mystique","Fleur d'or"],"minerais":["Pierre antique","Rubis"],"bestioles":["Papillon doré","Cerf"],"fruits":["Figue","Datte"]},
}

DEFAULT_EVENTS = [
    {"name":"Festival de l'Amitié","start":"2025-02-01","end":"2025-02-28",
     "tasks":["Offrir des cadeaux spéciaux à 5 villageois","Décorer la vallée pour la St-Valentin","Cuisiner 3 plats roses"]},
    {"name":"Fête du Printemps","start":"2025-03-20","end":"2025-04-20",
     "tasks":["Planter 50 fleurs printanières","Photographier 10 bestioles","Compléter les quêtes de Cendrillon"]},
    {"name":"Halloween Dreamlight","start":"2025-10-01","end":"2025-10-31",
     "tasks":["Décorer avec 20 citrouilles","Cuisiner 10 plats d'Halloween","Débloquer le costume de sorcière"]},
    {"name":"Noël Enchanté","start":"2025-12-01","end":"2025-12-31",
     "tasks":["Décorer avec 30 ornements","Offrir des cadeaux de Noël à tous","Cuisiner la bûche de Noël"]},
]

VILLAGERS_BASE = sorted([
    "Aladdin","Jasmine","Alice","Chat de Cheshire","Belle","Big Ben","La Bête","Lumiere",
    "Cendrillon","La Bonne Fée","L'Oublié","Mirabel","Anna","Elsa","Kristoff","Olaf",
    "Joie","Tristesse","Lady","Clochard","Stitch","Daisy","Donald","Dingo","Mickey",
    "Minnie","Picsou","Maui","Moana","Bob","Sully","Mulan","Mushu","Peter Pan","Remy",
    "Mere Gothel","Nala","Pumbaa","Scar","Simba","Timon","Ariel","Eric","Ursula",
    "Tiana","Merlin","Jack Skellington","Sally","Buzz l'éclair","Woody","WALL-E","Vanellope",
], key=str.lower)
VILLAGERS_DLC1 = sorted(["EVE","Gaston","Jafar","Raiponce","Oswald"], key=str.lower)
VILLAGERS_DLC2 = sorted(["Merida","Flynn","Hades","Aurore","Maléfique"], key=str.lower)
VILLAGERS_DLC3 = sorted(["Cruella","Blanche-Neige","Tigrou","Clochette"], key=str.lower)
ALL_VILLAGERS  = VILLAGERS_BASE + VILLAGERS_DLC1 + VILLAGERS_DLC2 + VILLAGERS_DLC3

DAILY_RESETS = [
    {"name":"Coffres bleu & vert",      "time":"00:00","utc":False,"icon":"🗝️", "tip":"Minuit heure locale"},
    {"name":"Discussions villageois",   "time":"00:00","utc":False,"icon":"💬", "tip":"Minuit heure locale"},
    {"name":"Nourrir bestioles",        "time":"00:00","utc":False,"icon":"🐾", "tip":"Minuit heure locale"},
    {"name":"Cadeaux villageois (x3)",  "time":"00:00","utc":False,"icon":"🎁", "tip":"Minuit heure locale"},
    {"name":"Épines nocturnes (x10)",   "time":"00:00","utc":False,"icon":"🌑", "tip":"Minuit heure locale"},
    {"name":"Fleurs séchées",           "time":"05:00","utc":False,"icon":"🌸", "tip":"5h heure locale, spawn dans 1 biome aléatoire"},
    {"name":"Boutique Picsou",          "time":"08:00","utc":True, "icon":"🏪", "tip":"8h UTC — même heure mondiale"},
    {"name":"Stands Dingo & Kristoff",  "time":"08:00","utc":True, "icon":"🛒", "tip":"8h UTC — même heure mondiale"},
    {"name":"Bateau Moana (poissons)",  "time":"cooldown_2h","utc":False,"icon":"⛵","tip":"Toutes les 2h après collecte"},
    {"name":"Dreamlight Duties",        "time":"restart","utc":False,"icon":"📜","tip":"Nécessite un redémarrage du jeu"},
    {"name":"Boutique Premium",         "time":"weekly_wed","utc":True,"icon":"💎","tip":"Mercredi 9h UTC"},
    {"name":"Dream Snaps",              "time":"weekly_wed","utc":True,"icon":"📸","tip":"Mercredi 9h UTC"},
]

TIMED_FISH = [
    {"name":"Here and There Fish", "hours":[(6,10),(18,22)], "biome":"Tous les biomes","icon":"🐟","note":"Matin 6h-10h et soir 18h-22h. Eau libre (sans bulles)."},
    {"name":"Fugu",                "hours":"rain",           "biome":"Dazzle Beach","icon":"🐡","note":"Uniquement par temps de pluie."},
    {"name":"Anglerfish festif",   "hours":[(20,6)],         "biome":"Terres Oubliées","icon":"🎄","note":"Nuit uniquement (événement hivernal)."},
]

CRITTERS = [
    # ── JEU DE BASE ────────────────────────────────────────────────────────────
    {
        "species": "Écureuil", "biome": "Plaza", "icon": "🐿️",
        "dlc": None,
        "food_love": "Cacahuètes (achetées chez Remy niv.4)",
        "food_like": ["Tout type de fruit", "Raifort", "Noix de muscade", "Groseille à maquereau"],
        "approach": "Approchez directement — ils viennent d'eux-mêmes quand ils ont faim.",
        "variants": [
            {"color": "Classique",  "days": [5, 6],          "hours": (0, 24), "rare": False},
            {"color": "Noir",       "days": [1, 2, 3, 4],    "hours": (0, 24), "rare": False},
            {"color": "Gris",       "days": [2, 3],          "hours": (0, 24), "rare": False},
            {"color": "Blanc ⭐",   "days": [6],             "hours": (10, 16), "rare": True},
        ],
    },
    {
        "species": "Lapin", "biome": "Clairière Paisible", "icon": "🐰",
        "dlc": None,
        "food_love": "Carottes (stand Goofy ou culture)",
        "food_like": ["Tout légume", "Feuilles crues", "Salade"],
        "approach": "Courez après lui 3 fois — il s'arrête ensuite pour vous laisser nourrir.",
        "variants": [
            {"color": "Classique",   "days": [3, 4],          "hours": (0, 24), "rare": False},
            {"color": "Noir",        "days": [0, 1, 2, 3, 5], "hours": (0, 24), "rare": False},
            {"color": "Marron",      "days": [1, 2, 5, 6],    "hours": (0, 24), "rare": False},
            {"color": "Calico ⭐",   "days": [3],             "hours": (8, 14), "rare": True},
        ],
    },
    {
        "species": "Tortue de mer", "biome": "Plage Ensoleillée", "icon": "🐢",
        "dlc": None,
        "food_love": "Algues (pêche sans bulles, tous biomes)",
        "food_like": ["Tout fruit de mer / coquillage"],
        "approach": "Approchez — elle se cache dans sa carapace, attendez qu'elle ressorte la tête.",
        "variants": [
            {"color": "Classique",   "days": [3, 4],          "hours": (0, 24), "rare": False},
            {"color": "Marron",      "days": [0, 1, 2, 5],    "hours": (0, 24), "rare": False},
            {"color": "Violette",    "days": [1, 2],          "hours": (0, 24), "rare": False},
            {"color": "Blanche",     "days": [5, 6],          "hours": (0, 24), "rare": False},
            {"color": "Noire ⭐",    "days": [0],             "hours": (10, 16), "rare": True},
        ],
    },
    {
        "species": "Raton laveur", "biome": "Forêt de Valeur", "icon": "🦝",
        "dlc": None,
        "food_love": "Myrtilles (buissons Forêt de Valeur ou stand Goofy)",
        "food_like": ["Tout autre type de baie"],
        "approach": "Feu rouge / feu vert : avancez quand sa tête est baissée, stoppez quand il vous regarde.",
        "variants": [
            {"color": "Classique",   "days": [0, 3, 4],       "hours": (0, 24), "rare": False},
            {"color": "Noir",        "days": [1, 2, 3, 5, 6], "hours": (0, 24), "rare": False},
            {"color": "Rouge",       "days": [4, 5],          "hours": (0, 24), "rare": False},
            {"color": "Bleu ⭐",     "days": [2],             "hours": (16, 22), "rare": True},
        ],
    },
    {
        "species": "Crocodile", "biome": "Clairière de Confiance", "icon": "🐊",
        "dlc": None,
        "food_love": "Homard (pêche — bulles dorées Clairière de Confiance)",
        "food_like": ["Hareng", "Calmar", "Fruits de mer"],
        "approach": "Feu rouge / feu vert (comme raton) — ils lèvent la tête et regardent de côté quand ils vous repèrent.",
        "variants": [
            {"color": "Classique",   "days": [3, 4, 6],       "hours": (0, 24), "rare": False},
            {"color": "Bleu",        "days": [0, 1, 2, 3, 5], "hours": (0, 24), "rare": False},
            {"color": "Doré",        "days": [1, 2],          "hours": (0, 24), "rare": False},
            {"color": "Blanc ⭐",    "days": [6],             "hours": (18, 0), "rare": True},
            {"color": "Rose ⭐",     "days": [5],             "hours": (6, 12), "rare": True},
        ],
    },
    {
        "species": "Oiseau-soleil", "biome": "Plateau Ensoleillé", "icon": "🦜",
        "dlc": None,
        "food_love": "Fleur de couleur assortie à sa couleur (voir variantes)",
        "food_like": ["Toutes les baies", "Toutes les fleurs"],
        "approach": "Facile — approchez quand il est posé sur un arbre ou une plante.",
        "variants": [
            {"color": "Doré (🌸 Houseleek orange)",    "days": [0, 3, 4, 5], "hours": (0, 24), "rare": False},
            {"color": "Émeraude (🌿 Pensée verte)",    "days": [1, 2, 3, 5, 6], "hours": (0, 24), "rare": False},
            {"color": "Rouge (🌺 Broméliacée rouge)",  "days": [0, 1],       "hours": (0, 24), "rare": False},
            {"color": "Turquoise (🌸 Houseleek rose)", "days": [4, 5, 6],   "hours": (0, 24), "rare": False},
            {"color": "Orchidée ⭐ (💜 Impatiente pourpre)", "days": [4],    "hours": (9, 15), "rare": True},
        ],
    },
    {
        "species": "Renard", "biome": "Sommets Enneigés", "icon": "🦊",
        "dlc": None,
        "food_love": "Esturgeon blanc (pêche bulles dorées — Sommets Enneigés)",
        "food_like": ["Tout poisson natif des Sommets Enneigés", "Saumon"],
        "approach": "Courez après lui comme pour le lapin — il s'arrête après 3 séquences.",
        "variants": [
            {"color": "Classique",   "days": [0, 3, 4, 5],   "hours": (0, 24), "rare": False},
            {"color": "Noir",        "days": [1, 2, 3, 5, 6], "hours": (0, 24), "rare": False},
            {"color": "Bleu",        "days": [0, 3, 4, 5],   "hours": (0, 24), "rare": False},
            {"color": "Rouge ⭐",    "days": [5],             "hours": (16, 22), "rare": True},
        ],
    },
    {
        "species": "Corbeau", "biome": "Terres Oubliées", "icon": "🐦‍⬛",
        "dlc": None,
        "food_love": "Tout plat 5 étoiles cuisiné",
        "food_like": ["Tout plat 3 ou 4 étoiles"],
        "approach": "Approchez — il s'envole, restez sur place, il revient se poser près de vous.",
        "variants": [
            {"color": "Classique",   "days": [0, 5, 6],       "hours": (0, 24), "rare": False},
            {"color": "Bleu",        "days": [0, 1, 2, 3, 4, 5], "hours": (0, 24), "rare": False},
            {"color": "Rouge",       "days": [2, 3],          "hours": (0, 24), "rare": False},
            {"color": "Marron ⭐",   "days": [1],             "hours": (18, 0), "rare": True},
        ],
    },
    # ── DLC : A Rift in Time (Île Éternité) ───────────────────────────────────
    {
        "species": "Singe", "biome": "Débarquement Antique", "icon": "🐒",
        "dlc": "rift",
        "food_love": "Banana Split (recette : Banane + Crème glacée + Sirop de chocolat)",
        "food_like": ["Repas 3, 4 ou 5 étoiles"],
        "approach": "Courez après lui comme pour le lapin — il s'arrête après quelques poursuites.",
        "variants": [
            {"color": "Classique",            "days": [0, 1, 4, 5], "hours": (0, 24), "rare": False},
            {"color": "Noir & Marron",         "days": [2, 3, 5, 6], "hours": (0, 24), "rare": False},
            {"color": "Beige",                "days": [0, 3, 4],    "hours": (0, 24), "rare": False},
            {"color": "Rouge",                "days": [2, 6],       "hours": (0, 24), "rare": False},
            {"color": "Noir & Gris ⭐",        "days": [1],          "hours": (18, 0), "rare": True},
        ],
    },
    {
        "species": "Cobra", "biome": "Dunes Brillantes", "icon": "🐍",
        "dlc": "rift",
        "food_love": "Œufs (achetés chez Remy ou récoltés)",
        "food_like": ["Scorpions"],
        "approach": "Feu rouge / feu vert — même comportement que le crocodile.",
        "variants": [
            {"color": "Classique",               "days": [0, 1, 2, 3, 5, 6], "hours": (0, 24), "rare": False},
            {"color": "Bleu & Rouge Rayé",        "days": [0, 3, 4],          "hours": (0, 24), "rare": False},
            {"color": "Jaune & Violet Rayé",      "days": [1, 2],             "hours": (0, 24), "rare": False},
            {"color": "Rose Tacheté",             "days": [0, 2, 4, 6],       "hours": (0, 24), "rare": False},
            {"color": "Vert & Blanc Rayé ⭐",     "days": [3],                "hours": (6, 12), "rare": True},
        ],
    },
    {
        "species": "Capybara", "biome": "Enchevêtrement Sauvage", "icon": "🦫",
        "dlc": "rift",
        "food_love": "Chou (culture ou stand Goofy)",
        "food_like": ["Cannelle", "Majestea", "Bambou", "Céleri"],
        "approach": "Approchez directement — très facile, comme les écureuils.",
        "variants": [
            {"color": "Classique",               "days": [0, 1, 2, 3, 5], "hours": (0, 24), "rare": False},
            {"color": "Noir & Blanc",             "days": [1, 2, 3, 4],   "hours": (0, 24), "rare": False},
            {"color": "Bleu Rayé",                "days": [5, 6],          "hours": (0, 24), "rare": False},
            {"color": "Gris Tacheté",             "days": [0, 4, 6],       "hours": (0, 24), "rare": False},
            {"color": "Rouge & Blanc Rayé ⭐",    "days": [5],             "hours": (12, 18), "rare": True},
        ],
    },
    # ── DLC : The Storybook Vale ──────────────────────────────────────────────
    {
        "species": "Hibou", "biome": "Le Lien", "icon": "🦉",
        "dlc": "storybook",
        "food_love": "Orge (récolté dans le Lien)",
        "food_like": ["Riz"],
        "approach": "Approchez directement — comme les écureuils et capybaras.",
        "variants": [
            {"color": "Clair",   "days": [0, 1, 2, 3, 4, 5], "hours": (0, 24), "rare": False},
            {"color": "Violet",  "days": [0, 1, 2, 3, 4, 5], "hours": (0, 24), "rare": False},
            {"color": "Marron",  "days": [1, 2, 3, 4, 5],    "hours": (0, 24), "rare": False},
            {"color": "Sombre",  "days": [0, 6],              "hours": (0, 24), "rare": False},
        ],
    },
    {
        "species": "Bébé Dragon", "biome": "Après-Toujours", "icon": "🐲",
        "dlc": "storybook",
        "food_love": "Pierres précieuses (Glace Pure, Magma, Saphir Étoilé — gems de l'Après-Toujours)",
        "food_like": ["Autres pierres précieuses"],
        "approach": "Comme la tortue — il fuit, restez sur place, attendez qu'il revienne.",
        "variants": [
            {"color": "Bleu & Sarcelle", "days": [0, 1, 2, 3, 4, 5, 6], "hours": (0, 24), "rare": False, "zone": "Bois Sauvages"},
            {"color": "Vert",            "days": [0, 1, 2, 3, 4, 5, 6], "hours": (0, 24), "rare": False, "zone": "Forteresse Déchue"},
            {"color": "Violet",          "days": [0, 1, 2, 3, 4, 5, 6], "hours": (0, 24), "rare": False, "zone": "Marais du Haricot"},
            {"color": "Rouge",           "days": [0, 5, 6],             "hours": (0, 24), "rare": False, "zone": "Chutes Théière"},
            {"color": "Vert (lun 10-18h)","days": [0],                  "hours": (10, 18), "rare": False, "zone": "Forteresse Déchue"},
        ],
    },
    {
        "species": "Pégase", "biome": "Mythopia", "icon": "🦄",
        "dlc": "storybook",
        "food_love": "Bouillabaisse (5★ à base de légumes) ou repas végétarien 5★",
        "food_like": ["Tout repas à base de plantes"],
        "approach": "Courez après lui comme pour le lapin — il s'arrête après quelques poursuites.",
        "variants": [
            {"color": "Rose & Noir",  "days": [0, 3, 4, 5, 6], "hours": (0, 24), "rare": False, "zone": "Champs Élysées / Mt Olympe"},
            {"color": "Bleu",        "days": [0, 1, 2, 3],     "hours": (0, 24), "rare": False, "zone": "Plaines de Feu"},
            {"color": "Jaune",       "days": [1, 4, 5, 6],     "hours": (0, 24), "rare": False, "zone": "Ombre de la Statue"},
        ],
    },
    # ── DLC : Wishblossom Ranch ───────────────────────────────────────────────
    {
        "species": "Oie", "biome": "Alpes du Vœu", "icon": "🪿",
        "dlc": "wishblossom",
        "food_love": "Groseille rouge (récoltée dans les Alpes)",
        "food_like": ["Autres fruits ?"],
        "approach": "Comme la tortue et le dragon — restez sur place, elle revient.",
        "variants": [
            {"color": "Classique",       "days": [0, 1, 2, 3, 4, 5, 6], "hours": (0, 24), "rare": False, "zone": "Ranch Wishblossom"},
            {"color": "Dorée",           "days": [0, 1, 2, 3, 4, 5, 6], "hours": (0, 24), "rare": False, "zone": "Delver Dale"},
            {"color": "Bleue",           "days": [0, 1, 2, 3, 4, 5, 6], "hours": (0, 24), "rare": False, "zone": "Wishing Way"},
            {"color": "True North",      "days": [1, 2, 3, 4, 5, 6],   "hours": (0, 24), "rare": False, "zone": "Ranch Highlands"},
            {"color": "Noire",           "days": [0, 1, 2, 3, 4, 5, 6], "hours": (0, 24), "rare": False, "zone": "Silver Summit"},
        ],
    },
    {
        "species": "Mouffette", "biome": "Glamour Gulch", "icon": "🦨",
        "dlc": "wishblossom",
        "food_love": "Pêche Pincushion (récoltée dans Glamour Gulch)",
        "food_like": ["Champignon de Paris"],
        "approach": "Feu rouge / feu vert — comme raton et crocodile.",
        "variants": [
            {"color": "Marron",   "days": [0, 1, 2, 3, 4, 5, 6], "hours": (12, 0), "rare": False, "zone": "Runaway River / Paisley Park"},
            {"color": "Blanche",  "days": [1, 2, 3, 4, 6],       "hours": (12, 0), "rare": False, "zone": "Modish Marsh"},
            {"color": "Rayée ☁️", "days": [0, 1, 2, 3, 4, 5, 6], "hours": (12, 0), "rare": False, "zone": "Haute Plateau (pluie uniquement)"},
        ],
    },
    {
        "species": "Abeille", "biome": "Pixie Acres", "icon": "🐝",
        "dlc": "wishblossom",
        "food_love": "Corail Miel (récolté dans Pixie Acres)",
        "food_like": ["???"],
        "approach": "Courez après elle comme le lapin, renard ou singe.",
        "variants": [
            {"color": "Classique", "days": [0, 1, 2, 3, 4, 5, 6], "hours": (0, 24), "rare": False, "zone": "Sundae Shores"},
            {"color": "Blanche",   "days": [0, 1, 2, 3, 4, 5, 6], "hours": (0, 24), "rare": False, "zone": "Hundred-Acre Fields"},
            {"color": "Rose",      "days": [0, 1, 2, 3, 4, 5, 6], "hours": (0, 24), "rare": False, "zone": "Pixie Flats"},
            {"color": "Bleue ☁️",  "days": [0, 1, 2, 3, 4, 5, 6], "hours": (0, 24), "rare": False, "zone": "Hunny Falls (beau temps uniquement)"},
        ],
    },
]

# ── Mapping DLC → libellé ────────────────────────────────────────────────────
CRITTER_DLC_LABELS = {
    None:          "🏰 Jeu de base",
    "rift":        "⏳ A Rift in Time",
    "storybook":   "📖 Storybook Vale",
    "wishblossom": "🌸 Wishblossom Ranch",
}

VILLAGER_SCHEDULES = [
    {"name":"Mickey Mouse","schedule":[
        {"days":[0,1,2,3,4,5,6],"hours":(7,10),"location":"Sa maison"},
        {"days":[0,1,2,3,4,5,6],"hours":(10,14),"location":"Plaza / Vallée"},
        {"days":[0,1,2,3,4,5,6],"hours":(14,18),"location":"Chez Remy (repas)"},
        {"days":[0,1,2,3,4,5,6],"hours":(18,22),"location":"Plaza / Vallée"},
        {"days":[0,1,2,3,4,5,6],"hours":(22,7),"location":"Dort (maison)"},
    ]},
    {"name":"Merlin","schedule":[
        {"days":[0,1,2,3,4,5,6],"hours":(8,12),"location":"Sa maison"},
        {"days":[0,1,2,3,4,5,6],"hours":(12,22),"location":"Plaza / Vallée"},
    ]},
]


def today_str():
    return date.today().isoformat()

def is_critter_active(variant, now=None):
    if now is None:
        now = datetime.now()
    day = now.weekday()
    hour = now.hour
    if day not in variant["days"]:
        return False
    h_start, h_end = variant["hours"]
    if h_start == 0 and h_end == 24:
        return True
    if h_start < h_end:
        return h_start <= hour < h_end
    return hour >= h_start or hour < h_end

def get_next_reset(reset_info, now=None):
    if now is None:
        now = datetime.now()
    time_str = reset_info["time"]
    if time_str in ("restart", "weekly_wed", "cooldown_2h"):
        return None
    h, m = map(int, time_str.split(":"))
    if reset_info.get("utc"):
        import time as tm
        utc_offset = -tm.timezone // 3600
        h_local = (h + utc_offset) % 24
    else:
        h_local = h
    target = now.replace(hour=h_local, minute=m, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    diff = target - now
    total_sec = int(diff.total_seconds())
    hh, rem = divmod(total_sec, 3600)
    mm = rem // 60
    return f"{hh:02d}h{mm:02d}"


# ══════════════════════════════════════════════════════════════════════════════
#  EXPORT CSV / PDF (fpdf2 remplace reportlab — plus léger)
# ══════════════════════════════════════════════════════════════════════════════

def export_csv(state: DDVState):
    fpath = filedialog.asksaveasfilename(
        defaultextension=".csv", filetypes=[("CSV","*.csv")],
        initialfile=f"ddv_backup_{today_str()}.csv")
    if not fpath:
        return
    try:
        with open(fpath, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["=== TÂCHES ==="])
            w.writerow(["Nom","Catégorie","Priorité","Cochée","Note"])
            for i, t in enumerate(state.tasks_meta):
                w.writerow([t["name"], t["category"], t["priority"],
                            state.daily_checked[i], t.get("note","")])
            w.writerow([])
            w.writerow(["=== VILLAGEOIS ==="])
            w.writerow(["Nom","Niveau","Discuté","Don1","Don2","Don3"])
            for name, d in state.villagers_data.items():
                w.writerow([name, d["level"], d["checked"], *d["gifts"]])
            w.writerow([])
            w.writerow(["=== TROPHÉES ==="])
            w.writerow(["ID","Nom","Type","Débloqué","Progression","Note"])
            for t in TROPHIES:
                td = state.trophy_data[t["id"]]
                w.writerow([t["id"],t["name"],t["type"],td["unlocked"],td["progress"],td.get("note","")])
            w.writerow([])
            w.writerow(["=== HISTORIQUE ==="])
            w.writerow(["Date","Tâches faites","Total"])
            for d_str, entry in sorted(state.history.items()):
                w.writerow([d_str, entry["done"], entry["total"]])
        messagebox.showinfo("Export réussi", f"Sauvegardé dans :\n{fpath}")
    except Exception as e:
        messagebox.showerror("Erreur", str(e))


def export_pdf(state: DDVState):
    """Export PDF avec fpdf2 (pip install fpdf2) — bien plus léger que reportlab."""
    fpath = filedialog.asksaveasfilename(
        defaultextension=".pdf", filetypes=[("PDF","*.pdf")],
        initialfile=f"ddv_rapport_{today_str()}.pdf")
    if not fpath:
        return
    try:
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 10, "Rapport Disney Dreamlight Valley", new_x="LMARGIN", new_y="NEXT", align="C")
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 8, f"Généré le {today_str()} — Compte : {state.current_account}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

        # Streak
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, f"Streak actuel : {state.streak.get('count',0)} jours  |  Record : {state.streak.get('best',0)} jours", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

        # Trophées
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Avancement Trophées", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        for t in TROPHIES:
            td = state.trophy_data[t["id"]]
            prog = f"{td['progress']}/{t['max_value']}" if t["max_value"] else "-"
            status = "Obtenu" if td["unlocked"] else "En cours"
            pdf.cell(0, 6, f"  [{TROPHY_TYPE_INFO[t['type']][1]}] {t['name']} — {prog} — {status}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

        # Historique 7j
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "Historique des 7 derniers jours", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        today2 = date.today()
        for i in range(6, -1, -1):
            d = (today2 - timedelta(days=i)).isoformat()
            entry = state.history.get(d)
            if entry:
                pct = int(entry["done"]/entry["total"]*100) if entry["total"] else 0
                pdf.cell(0, 6, f"  {d} — {entry['done']}/{entry['total']} ({pct}%)", new_x="LMARGIN", new_y="NEXT")
            else:
                pdf.cell(0, 6, f"  {d} — pas de données", new_x="LMARGIN", new_y="NEXT")

        pdf.output(fpath)
        messagebox.showinfo("Export PDF", f"PDF généré !\n{fpath}")
    except ImportError:
        messagebox.showerror("Dépendance manquante", "Installe fpdf2 : pip install fpdf2")
    except Exception as e:
        messagebox.showerror("Erreur PDF", str(e))


# ══════════════════════════════════════════════════════════════════════════════
#  GRAPHIQUES SANS MATPLOTLIB — Canvas Tkinter natif
# ══════════════════════════════════════════════════════════════════════════════

def draw_bar_chart_native(parent, labels, values, colors_list, title, max_val=100, height=200):
    """Graphique en barres 100% tkinter — pas de matplotlib."""
    for w in parent.winfo_children():
        w.destroy()
    c = tk.Canvas(parent, height=height, bg="#1e1e2e", highlightthickness=0)
    c.pack(fill="x", padx=8, pady=4)

    pad_left, pad_right, pad_top, pad_bottom = 40, 10, 20, 40
    c.update_idletasks()
    W = c.winfo_width() or 600
    H = height

    n = len(labels)
    if n == 0:
        return
    bar_w = max(4, (W - pad_left - pad_right) // n - 4)

    # Titre
    c.create_text(W//2, pad_top//2 + 4, text=title, fill="white", font=("Arial", 10, "bold"))

    # Axe Y
    c.create_line(pad_left, pad_top, pad_left, H - pad_bottom, fill="#555577")
    for pct in [0, 25, 50, 75, 100]:
        y = H - pad_bottom - int((pct / max_val) * (H - pad_top - pad_bottom))
        c.create_line(pad_left - 4, y, pad_left, y, fill="#555577")
        c.create_text(pad_left - 6, y, text=str(pct), fill="#aaaaaa", font=("Arial", 7), anchor="e")

    # Barres
    for i, (label, val, col) in enumerate(zip(labels, values, colors_list)):
        x0 = pad_left + i * ((W - pad_left - pad_right) // n) + 2
        bar_height = int((val / max_val) * (H - pad_top - pad_bottom)) if max_val else 0
        y0 = H - pad_bottom - bar_height
        y1 = H - pad_bottom
        c.create_rectangle(x0, y0, x0 + bar_w, y1, fill=col, outline="")
        c.create_text(x0 + bar_w//2, H - pad_bottom + 4, text=label,
                      fill="#aaaaaa", font=("Arial", 7), angle=45 if n > 10 else 0, anchor="n")
        if val > 0:
            c.create_text(x0 + bar_w//2, y0 - 6, text=str(val),
                          fill="white", font=("Arial", 7))


# ══════════════════════════════════════════════════════════════════════════════
#  INTERFACE PRINCIPALE — CustomTkinter
# ══════════════════════════════════════════════════════════════════════════════

class DDVApp(ctk.CTk):
    """Fenêtre principale de l'application."""

    def __init__(self, state: DDVState):
        super().__init__()
        self.gs = state
        self._apply_theme()
        self.title(f"🏰 DDV Checklist — {state.current_account}")
        self.geometry("1000x900")
        self.resizable(True, True)
        self._build_ui()

    def _apply_theme(self):
        ctk.set_appearance_mode("dark" if self.gs.theme == "dark" else "light")
        ctk.set_default_color_theme("blue")

    def _build_ui(self):
        # ── Barre supérieure ──
        topbar = ctk.CTkFrame(self, height=48, corner_radius=0)
        topbar.pack(fill="x", padx=0, pady=0)
        topbar.pack_propagate(False)

        ctk.CTkLabel(topbar, text="🏰 Disney Dreamlight Valley Checklist",
                     font=ctk.CTkFont(size=16, weight="bold")).pack(side="left", padx=16)

        btn_frame = ctk.CTkFrame(topbar, fg_color="transparent")
        btn_frame.pack(side="right", padx=8)

        self.theme_btn = ctk.CTkButton(
            btn_frame, text="☀️ Clair" if self.gs.theme == "dark" else "🌙 Sombre",
            width=90, command=self._toggle_theme
        )
        self.theme_btn.pack(side="right", padx=4)

        ctk.CTkButton(btn_frame, text="🌅 Nouveau jour", width=110, command=self._nouveau_jour).pack(side="right", padx=4)
        ctk.CTkButton(btn_frame, text="📤 CSV", width=70, command=lambda: export_csv(self.gs)).pack(side="right", padx=2)
        ctk.CTkButton(btn_frame, text="📄 PDF", width=70, command=lambda: export_pdf(self.gs)).pack(side="right", padx=2)

        # ── Status bar ──
        self.statusbar = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=11))
        self.statusbar.pack(fill="x", padx=10, pady=2)

        # ── Tabview principal ──
        self.tabs = ctk.CTkTabview(self, corner_radius=8)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=(0, 8))

        self.tabs.add("📋 Tâches")
        self.tabs.add("📅 Historique")
        self.tabs.add("🕐 En ce moment")
        self.tabs.add("🎉 Événements")
        self.tabs.add("🏆 Trophées")
        self.tabs.add("👥 Villageois")
        self.tabs.add("📊 Stats")
        self.tabs.add("⚙️ Paramètres")

        self._build_tasks_tab()
        self._build_history_tab()
        self._build_time_tab()
        self._build_events_tab()
        self._build_trophy_tab()
        self._build_villager_tab()
        self._build_stats_tab()
        self._build_settings_tab()

        self._update_statusbar()

    # ─────────────────────────────────────────────────────────────────────────
    # ONGLET TÂCHES QUOTIDIENNES
    # ─────────────────────────────────────────────────────────────────────────

    def _build_tasks_tab(self):
        tab = self.tabs.tab("📋 Tâches")

        # En-tête progression
        hdr = ctk.CTkFrame(tab, fg_color="transparent")
        hdr.pack(fill="x", padx=4, pady=4)
        self.prog_label = ctk.CTkLabel(hdr, text="", font=ctk.CTkFont(size=12, weight="bold"))
        self.prog_label.pack(side="left")
        self.streak_label = ctk.CTkLabel(hdr, text="", font=ctk.CTkFont(size=12), text_color="#f0a500")
        self.streak_label.pack(side="right")
        self.hardcore_label = ctk.CTkLabel(tab, text="", text_color="#e74c3c", font=ctk.CTkFont(size=10))
        self.hardcore_label.pack()

        self.progress_bar = ctk.CTkProgressBar(tab, height=12)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=8, pady=(0, 6))

        # Filtres
        flt = ctk.CTkFrame(tab, fg_color="transparent")
        flt.pack(fill="x", padx=4, pady=2)
        ctk.CTkLabel(flt, text="Vue :").pack(side="left")
        self.view_var = ctk.StringVar(value="Toutes")
        ctk.CTkComboBox(flt, variable=self.view_var, width=130,
                        values=["Toutes","Restantes","Complétées"] + CATEGORIES,
                        command=lambda _: self._refresh_task_list()).pack(side="left", padx=4)
        ctk.CTkLabel(flt, text="Priorité :").pack(side="left", padx=(8, 0))
        self.prio_var = ctk.StringVar(value="Toutes")
        ctk.CTkComboBox(flt, variable=self.prio_var, width=130,
                        values=["Toutes","🔴 Prioritaire","🟡 Normal","🟢 Optionnel"],
                        command=lambda _: self._refresh_task_list()).pack(side="left", padx=4)

        ctk.CTkButton(flt, text="➕ Ajouter une tâche", width=140,
                      command=self._add_task).pack(side="right", padx=4)

        # Zone scrollable des tâches
        self.tasks_scroll = ctk.CTkScrollableFrame(tab, corner_radius=6)
        self.tasks_scroll.pack(fill="both", expand=True, padx=4, pady=4)

        self._refresh_task_list()

    def _refresh_task_list(self):
        for w in self.tasks_scroll.winfo_children():
            w.destroy()

        view = self.view_var.get()
        prio_filter = self.prio_var.get()
        cat_icons = {"Collecte":"🌿","Social":"💬","Commerce":"🛒","Quêtes":"📜","Autre":"📌"}
        cats_seen = []
        for t in self.gs.tasks_meta:
            if t["category"] not in cats_seen:
                cats_seen.append(t["category"])

        for cat in cats_seen:
            visible = []
            for i, t in enumerate(self.gs.tasks_meta):
                if t["category"] != cat:
                    continue
                if view == "Restantes"  and self.gs.daily_checked[i]: continue
                if view == "Complétées" and not self.gs.daily_checked[i]: continue
                if view in CATEGORIES and t["category"] != view: continue
                if prio_filter == "🔴 Prioritaire" and t["priority"] != "high":   continue
                if prio_filter == "🟡 Normal"       and t["priority"] != "medium": continue
                if prio_filter == "🟢 Optionnel"    and t["priority"] != "low":    continue
                visible.append((i, t))
            if not visible:
                continue

            ctk.CTkLabel(self.tasks_scroll,
                         text=f"{cat_icons.get(cat,'📌')} {cat}",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color="#7eb8f7").pack(anchor="w", padx=6, pady=(10, 2))

            for i, t in visible:
                self._build_task_row(i, t)

        self._update_progress()
        if self.gs.hardcore_mode:
            self.hardcore_label.configure(text="💀 MODE HARDCORE — Manquer une tâche reset le streak !")
        else:
            self.hardcore_label.configure(text="")

    def _build_task_row(self, idx: int, task: dict):
        p_icon = PRIORITIES[task["priority"]][0]
        row = ctk.CTkFrame(self.tasks_scroll, corner_radius=6, height=36)
        row.pack(fill="x", padx=4, pady=2)
        row.pack_propagate(False)

        var = ctk.BooleanVar(value=self.gs.daily_checked[idx])

        def on_check(i=idx, v=var):
            self.gs.daily_checked[i] = v.get()
            if v.get() and self.gs.tasks_meta[i].get("cooldown"):
                self.gs.cooldown_timers[self.gs.tasks_meta[i]["name"]] = time.time()
            self._update_progress()
            self.gs.save_all()

        ctk.CTkLabel(row, text=p_icon, width=24).pack(side="left", padx=(4, 0))
        cb = ctk.CTkCheckBox(row, text="", variable=var, command=on_check, width=24)
        cb.pack(side="left")

        name_font = ctk.CTkFont(size=11, overstrike=self.gs.daily_checked[idx])
        name_lbl = ctk.CTkLabel(row, text=task["name"], font=name_font, anchor="w", width=320)
        name_lbl.pack(side="left", padx=4)

        def _update_strike(*_):
            name_lbl.configure(font=ctk.CTkFont(size=11, overstrike=var.get()))
        var.trace_add("write", _update_strike)

        # Note inline
        note_entry = ctk.CTkEntry(row, placeholder_text="📝 note...", width=160)
        if task.get("note"):
            note_entry.insert(0, task["note"])
        note_entry.pack(side="left", padx=4)

        def save_note(e, i=idx, entry=note_entry):
            self.gs.tasks_meta[i]["note"] = entry.get().strip()
            self.gs.save_all()
        note_entry.bind("<FocusOut>", save_note)

        # Cycle priorité
        def cycle_prio(i=idx):
            order = ["high", "medium", "low"]
            self.gs.tasks_meta[i]["priority"] = order[(order.index(self.gs.tasks_meta[i]["priority"])+1)%3]
            self.gs.save_all()
            self._refresh_task_list()
        ctk.CTkButton(row, text="⇅", width=28, command=cycle_prio).pack(side="left", padx=2)

        # Supprimer (tâches custom uniquement)
        if idx >= len(DEFAULT_TASKS):
            def del_task(i=idx):
                if messagebox.askyesno("Supprimer", f"Supprimer \"{self.gs.tasks_meta[i]['name']}\" ?"):
                    self.gs.tasks_meta.pop(i)
                    self.gs.daily_checked.pop(i)
                    self.gs.save_all()
                    self._refresh_task_list()
            ctk.CTkButton(row, text="🗑", width=28, fg_color="#e74c3c",
                          hover_color="#c0392b", command=del_task).pack(side="left", padx=2)

    def _update_progress(self):
        total = len(self.gs.tasks_meta)
        done  = sum(self.gs.daily_checked)
        pct   = done / total if total else 0
        self.progress_bar.set(pct)
        self.prog_label.configure(text=f"Progression : {done}/{total} ({int(pct*100)}%)")

        today2 = today_str()
        if done == total and total > 0:
            last = self.gs.streak.get("last_complete_date", "")
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            if last != today2:
                if last == yesterday:
                    self.gs.streak["count"] += 1
                else:
                    self.gs.streak["count"] = 1
                self.gs.streak["last_complete_date"] = today2
            self.gs.streak["best"] = max(self.gs.streak.get("best", 0), self.gs.streak["count"])
            self.gs.history[today2] = {"done": done, "total": total}

        c = self.gs.streak.get("count", 0)
        best = self.gs.streak.get("best", 0)
        if c >= 7:
            self.streak_label.configure(text=f"🔥 Streak : {c}j  |  Record : {best}j")
        elif c > 0:
            self.streak_label.configure(text=f"⭐ Streak : {c}j  |  Record : {best}j")
        else:
            self.streak_label.configure(text=f"Record : {best}j" if best else "")

    def _add_task(self):
        name = simpledialog.askstring("Nouvelle tâche", "Nom de la tâche :")
        if not name or not name.strip():
            return
        cat = simpledialog.askstring("Catégorie", f"Catégorie ({', '.join(CATEGORIES)}) :", initialvalue="Autre")
        if cat not in CATEGORIES:
            cat = "Autre"
        self.gs.tasks_meta.append({"name": name.strip(), "category": cat, "priority": "medium",
                                       "cooldown": None, "optional": True, "note": ""})
        self.gs.daily_checked.append(False)
        self.gs.save_all()
        self._refresh_task_list()

    # ─────────────────────────────────────────────────────────────────────────
    # ONGLET HISTORIQUE
    # ─────────────────────────────────────────────────────────────────────────

    def _build_history_tab(self):
        tab = self.tabs.tab("📅 Historique")
        ctk.CTkLabel(tab, text="Historique des 30 derniers jours",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(pady=8)
        self.history_scroll = ctk.CTkScrollableFrame(tab, corner_radius=6)
        self.history_scroll.pack(fill="both", expand=True, padx=8, pady=4)
        self._refresh_history()

    def _refresh_history(self):
        for w in self.history_scroll.winfo_children():
            w.destroy()
        today2 = date.today()
        for i in range(29, -1, -1):
            d = (today2 - timedelta(days=i)).isoformat()
            entry = self.gs.history.get(d)
            if entry:
                done2, total2 = entry["done"], entry["total"]
                pct = int(done2/total2*100) if total2 else 0
                bar = "█"*(pct//10) + "░"*(10 - pct//10)
                color = "#4caf50" if pct == 100 else "#f0a500" if pct >= 50 else "#e74c3c"
                ctk.CTkLabel(self.history_scroll,
                             text=f"{d}   {bar}  {done2}/{total2} ({pct}%)",
                             font=ctk.CTkFont(family="Courier", size=11),
                             text_color=color).pack(anchor="w", padx=16, pady=1)
            else:
                ctk.CTkLabel(self.history_scroll,
                             text=f"{d}   {'░'*10}  —",
                             font=ctk.CTkFont(family="Courier", size=11),
                             text_color="gray").pack(anchor="w", padx=16, pady=1)

    # ─────────────────────────────────────────────────────────────────────────
    # ONGLET EN CE MOMENT
    # ─────────────────────────────────────────────────────────────────────────

    def _build_time_tab(self):
        tab = self.tabs.tab("🕐 En ce moment")

        # Horloge
        clk_frame = ctk.CTkFrame(tab, fg_color="transparent")
        clk_frame.pack(fill="x", padx=10, pady=6)
        self.clock_lbl = ctk.CTkLabel(clk_frame, text="", font=ctk.CTkFont(size=24, weight="bold"),
                                       text_color="#7eb8f7")
        self.clock_lbl.pack(side="left")
        self.date_lbl = ctk.CTkLabel(clk_frame, text="", font=ctk.CTkFont(size=13), text_color="gray")
        self.date_lbl.pack(side="left", padx=12)
        self._tick_clock()

        # Sous-onglets
        inner = ctk.CTkTabview(tab, corner_radius=6)
        inner.pack(fill="both", expand=True, padx=6, pady=4)
        inner.add("🌟 Maintenant")
        inner.add("⏱️ Resets")
        inner.add("🐾 Bestioles")
        inner.add("🐟 Poissons")
        inner.add("📅 Semaine")

        self._build_now_tab(inner.tab("🌟 Maintenant"))
        self._build_resets_tab(inner.tab("⏱️ Resets"))
        self._build_critters_tab(inner.tab("🐾 Bestioles"))
        self._build_fish_tab(inner.tab("🐟 Poissons"))
        self._build_calendar_tab(inner.tab("📅 Semaine"))

    def _tick_clock(self):
        JOURS = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]
        now = datetime.now()
        self.clock_lbl.configure(text=now.strftime("%H:%M:%S"))
        self.date_lbl.configure(text=f"{JOURS[now.weekday()]} {now.strftime('%d/%m/%Y')}")
        self.after(1000, self._tick_clock)

    def _build_now_tab(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, corner_radius=0)
        scroll.pack(fill="both", expand=True)

        def refresh():
            for w in scroll.winfo_children():
                w.destroy()
            now = datetime.now()

            ctk.CTkLabel(scroll, text="🐟 Poissons exclusifs actifs",
                         font=ctk.CTkFont(size=12, weight="bold"), text_color="#7eb8f7").pack(anchor="w", padx=8, pady=(8,2))
            fish_found = False
            for fish in TIMED_FISH:
                if fish["hours"] == "rain":
                    ctk.CTkLabel(scroll, text=f"  {fish['icon']} {fish['name']} — 🌧️ par temps de pluie ({fish['biome']})",
                                 text_color="gray").pack(anchor="w", padx=16)
                    fish_found = True
                    continue
                for h_start, h_end in fish["hours"]:
                    active = (h_start <= now.hour < h_end) if h_start < h_end else (now.hour >= h_start or now.hour < h_end)
                    if active:
                        ctk.CTkLabel(scroll, text=f"  {fish['icon']} {fish['name']} — {fish['biome']} ✅",
                                     text_color="#4caf50", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=16)
                        fish_found = True
            if not fish_found:
                ctk.CTkLabel(scroll, text="  Aucun poisson temporaire en ce moment.", text_color="gray").pack(anchor="w", padx=16)

            ctk.CTkLabel(scroll, text="🐾 Bestioles disponibles maintenant",
                         font=ctk.CTkFont(size=12, weight="bold"), text_color="#7eb8f7").pack(anchor="w", padx=8, pady=(12,2))
            active_critters, rare_critters = [], []
            for sp in CRITTERS:
                for v in sp["variants"]:
                    if is_critter_active(v, now):
                        entry = (sp["icon"], sp["species"], v["color"], sp["biome"],
                                 sp.get("food_love","?"), sp.get("food_like",[]))
                        if v.get("rare", False):
                            rare_critters.append(entry)
                        else:
                            active_critters.append(entry)
            if rare_critters:
                ctk.CTkLabel(scroll, text="  ⚠️ RARES disponibles !",
                             font=ctk.CTkFont(size=10, weight="bold"), text_color="#f0a500").pack(anchor="w", padx=16)
                for icon,sp,col,biome,food_love,food_like in rare_critters:
                    ctk.CTkLabel(scroll, text=f"    {icon} {sp} {col} — {biome}",
                                 text_color="#f0a500", font=ctk.CTkFont(size=10, weight="bold")).pack(anchor="w", padx=20)
                    ctk.CTkLabel(scroll, text=f"       ❤️ Adore : {food_love}",
                                 text_color="#e74c3c", font=ctk.CTkFont(size=9)).pack(anchor="w", padx=24)
            for icon,sp,col,biome,food_love,food_like in active_critters:
                ctk.CTkLabel(scroll, text=f"  {icon} {sp} {col} — {biome}  ❤️ {food_love.split('(')[0].strip()}",
                             text_color="#cccccc").pack(anchor="w", padx=16)
            if not active_critters and not rare_critters:
                ctk.CTkLabel(scroll, text="  Aucune bestiole active.", text_color="gray").pack(anchor="w", padx=16)

            ctk.CTkButton(scroll, text="🔄 Actualiser", width=120, command=refresh).pack(anchor="w", padx=8, pady=8)

        refresh()
        self.after(60000, refresh)

    def _build_resets_tab(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, corner_radius=0)
        scroll.pack(fill="both", expand=True)
        ctk.CTkLabel(scroll, text="Comptes à rebours jusqu'au prochain reset",
                     font=ctk.CTkFont(size=12, weight="bold"), text_color="#7eb8f7").pack(anchor="w", padx=8, pady=8)

        self._reset_labels = {}
        for r in DAILY_RESETS:
            row = ctk.CTkFrame(scroll, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=2)
            ctk.CTkLabel(row, text=r["icon"], width=30).pack(side="left")
            ctk.CTkLabel(row, text=r["name"], width=220, anchor="w").pack(side="left")
            val_lbl = ctk.CTkLabel(row, text="...", text_color="#f0a500",
                                   font=ctk.CTkFont(size=11, weight="bold"), width=90)
            val_lbl.pack(side="left")
            ctk.CTkLabel(row, text=f"  💡 {r['tip']}", text_color="gray",
                         font=ctk.CTkFont(size=9)).pack(side="left")
            self._reset_labels[r["name"]] = (val_lbl, r)

        self._update_reset_timers()

    def _update_reset_timers(self):
        now = datetime.now()
        for name, (lbl, r) in self._reset_labels.items():
            t = r["time"]
            if t == "restart":
                lbl.configure(text="↩️ Redémarrer", text_color="#e74c3c")
            elif t == "cooldown_2h":
                lbl.configure(text="⏱ 2h après col.", text_color="#7eb8f7")
            elif t == "weekly_wed":
                days_until = (2 - now.weekday()) % 7
                if days_until == 0 and now.hour >= 9:
                    days_until = 7
                lbl.configure(text=f"🗓 {days_until}j", text_color="#7eb8f7")
            else:
                remaining = get_next_reset(r, now)
                if remaining:
                    lbl.configure(text=remaining, text_color="#f0a500")
        self.after(30000, self._update_reset_timers)

    def _build_critters_tab(self, parent):
        JOURS = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]
        JOURS_COURTS = ["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"]
        now = datetime.now()

        # ── Barre de filtres ──────────────────────────────────────────────────
        ctrl = ctk.CTkFrame(parent, fg_color="transparent")
        ctrl.pack(fill="x", padx=8, pady=(6, 2))

        ctk.CTkLabel(ctrl, text="DLC :").pack(side="left")
        self._critter_dlc_var = ctk.StringVar(value="Tous")
        dlc_values = ["Tous", "🏰 Jeu de base", "⏳ A Rift in Time",
                      "📖 Storybook Vale", "🌸 Wishblossom Ranch"]
        ctk.CTkComboBox(ctrl, variable=self._critter_dlc_var, width=180,
                        values=dlc_values,
                        command=lambda _: self._refresh_critters_tab()).pack(side="left", padx=4)

        ctk.CTkLabel(ctrl, text="Afficher :").pack(side="left", padx=(12,0))
        self._critter_show_var = ctk.StringVar(value="Toutes")
        ctk.CTkComboBox(ctrl, variable=self._critter_show_var, width=160,
                        values=["Toutes","Actives maintenant","Rares seulement"],
                        command=lambda _: self._refresh_critters_tab()).pack(side="left", padx=4)

        ctk.CTkButton(ctrl, text="🔄 Actualiser", width=100,
                      command=self._refresh_critters_tab).pack(side="right", padx=4)

        self._critter_scroll = ctk.CTkScrollableFrame(parent, corner_radius=0)
        self._critter_scroll.pack(fill="both", expand=True)

        self._refresh_critters_tab()

    def _refresh_critters_tab(self):
        JOURS_COURTS = ["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"]
        now = datetime.now()
        scroll = self._critter_scroll
        for w in scroll.winfo_children():
            w.destroy()

        dlc_filter = self._critter_dlc_var.get()
        show_filter = self._critter_show_var.get()

        # Reverse mapping DLC label → clé
        # Sentinel "_TOUS_" pour distinguer "Tous" de la clé None (jeu de base)
        _SENTINEL = "_TOUS_"
        dlc_key_map = {v: k for k, v in CRITTER_DLC_LABELS.items()}
        dlc_key_filter = _SENTINEL if dlc_filter == "Tous" else dlc_key_map.get(dlc_filter, _SENTINEL)

        ctk.CTkLabel(scroll,
                     text=f"🐾 Planning bestioles — {['Lun','Mar','Mer','Jeu','Ven','Sam','Dim'][now.weekday()]} {now.strftime('%H:%M')}",
                     font=ctk.CTkFont(size=12, weight="bold"), text_color="#7eb8f7"
                     ).pack(anchor="w", padx=8, pady=(8, 4))

        # Regrouper par DLC
        groups: dict[str, list] = {}
        for sp in CRITTERS:
            if dlc_key_filter != _SENTINEL and sp["dlc"] != dlc_key_filter:
                continue
            label = CRITTER_DLC_LABELS.get(sp["dlc"], "Autre")
            groups.setdefault(label, []).append(sp)

        for dlc_label, species_list in groups.items():
            # On filtre d'abord les espèces qui passent le filtre "Afficher"
            # et on calcule les variantes à afficher pour chacune
            visible_species = []
            for sp in species_list:
                all_variants = sp["variants"]

                if show_filter == "Actives maintenant":
                    variants_to_show = [v for v in all_variants if is_critter_active(v, now)]
                elif show_filter == "Rares seulement":
                    variants_to_show = [v for v in all_variants if v.get("rare", False)]
                else:
                    variants_to_show = all_variants

                if variants_to_show:
                    visible_species.append((sp, variants_to_show))

            # L'en-tête DLC n'est affiché que si au moins une espèce est visible
            if not visible_species:
                continue
            ctk.CTkLabel(scroll, text=dlc_label,
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#a78bfa").pack(anchor="w", padx=8, pady=(12, 2))

            for sp, variants_to_show in visible_species:
                any_active = any(is_critter_active(v, now) for v in sp["variants"])

                # Carte espèce
                card = ctk.CTkFrame(scroll, corner_radius=8)
                card.pack(fill="x", padx=8, pady=3)

                # En-tête espèce
                hdr_row = ctk.CTkFrame(card, fg_color="transparent")
                hdr_row.pack(fill="x", padx=8, pady=(6, 2))
                ctk.CTkLabel(hdr_row,
                             text=f"{sp['icon']}  {sp['species']}",
                             font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
                ctk.CTkLabel(hdr_row,
                             text=f"📍 {sp['biome']}",
                             text_color="gray",
                             font=ctk.CTkFont(size=10)).pack(side="left", padx=8)
                if any_active:
                    ctk.CTkLabel(hdr_row, text="✅ ACTIVE",
                                 text_color="#4caf50",
                                 font=ctk.CTkFont(size=10, weight="bold")).pack(side="right", padx=4)

                # Nourriture
                ctk.CTkLabel(card,
                             text=f"  ❤️ Adore : {sp['food_love']}",
                             text_color="#e74c3c",
                             font=ctk.CTkFont(size=10)).pack(anchor="w", padx=8)
                likes = " / ".join(sp.get("food_like", []))
                ctk.CTkLabel(card,
                             text=f"  💛 Aime aussi : {likes}",
                             text_color="#f0a500",
                             font=ctk.CTkFont(size=10)).pack(anchor="w", padx=8)

                # Approche
                if sp.get("approach"):
                    ctk.CTkLabel(card,
                                 text=f"  🦶 {sp['approach']}",
                                 text_color="#9ca3af",
                                 font=ctk.CTkFont(size=9),
                                 wraplength=750, justify="left").pack(anchor="w", padx=8, pady=(1, 4))

                # Séparateur
                ctk.CTkFrame(card, height=1, fg_color="#333355").pack(fill="x", padx=12, pady=2)

                # Variantes filtrées uniquement
                for v in variants_to_show:
                    active = is_critter_active(v, now)
                    is_rare = v.get("rare", False)
                    days_str = " ".join(JOURS_COURTS[d] for d in v["days"])
                    h_s, h_e = v["hours"]
                    hours_str = "Toute la journée" if (h_s == 0 and h_e == 24) else f"{h_s:02d}h–{h_e:02d}h"

                    vrow = ctk.CTkFrame(card, fg_color="transparent")
                    vrow.pack(anchor="w", padx=12, pady=1)

                    if active:
                        ind_color, ind_text = "#4caf50", "✅"
                    elif is_rare:
                        ind_color, ind_text = "#f0a500", "⭐"
                    else:
                        ind_color, ind_text = "#6b7280", "  "

                    ctk.CTkLabel(vrow, text=ind_text, width=22,
                                 text_color=ind_color,
                                 font=ctk.CTkFont(size=10)).pack(side="left")
                    ctk.CTkLabel(vrow, text=v["color"], width=180, anchor="w",
                                 text_color="#4caf50" if active else (ind_color if is_rare else "#d1d5db"),
                                 font=ctk.CTkFont(size=10, weight="bold" if active or is_rare else "normal")
                                 ).pack(side="left")
                    ctk.CTkLabel(vrow, text=days_str, width=200, anchor="w",
                                 text_color="#6b7280" if not active else "#9ca3af",
                                 font=ctk.CTkFont(size=9)).pack(side="left")
                    ctk.CTkLabel(vrow, text=hours_str, width=140, anchor="w",
                                 text_color="#7eb8f7" if active else "#6b7280",
                                 font=ctk.CTkFont(size=9)).pack(side="left")
                    if "zone" in v:
                        ctk.CTkLabel(vrow, text=f"🗺 {v['zone']}",
                                     text_color="#6b7280",
                                     font=ctk.CTkFont(size=9)).pack(side="left", padx=4)

                # Padding bas de carte
                ctk.CTkFrame(card, height=4, fg_color="transparent").pack()

    def _build_fish_tab(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, corner_radius=0)
        scroll.pack(fill="both", expand=True)
        now = datetime.now()
        for fish in TIMED_FISH:
            card = ctk.CTkFrame(scroll, corner_radius=8)
            card.pack(fill="x", padx=10, pady=5)
            if fish["hours"] == "rain":
                ctk.CTkLabel(card, text=f"{fish['icon']} {fish['name']}",
                             font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=8, pady=(6,2))
                ctk.CTkLabel(card, text="🌧️ Disponible uniquement par temps de PLUIE",
                             text_color="#7eb8f7").pack(anchor="w", padx=16)
            else:
                active_now = any(
                    (h_s <= now.hour < h_e) if h_s < h_e else (now.hour >= h_s or now.hour < h_e)
                    for h_s, h_e in fish["hours"]
                )
                windows = [f"{h_s:02d}h00 – {h_e:02d}h00" for h_s, h_e in fish["hours"]]
                title = f"{fish['icon']} {fish['name']} {'✅ ACTIF !' if active_now else ''}"
                ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=12, weight="bold"),
                             text_color="#4caf50" if active_now else "white").pack(anchor="w", padx=8, pady=(6,2))
                ctk.CTkLabel(card, text=f"⏰ {' | '.join(windows)}", text_color="#7eb8f7").pack(anchor="w", padx=16)
            ctk.CTkLabel(card, text=f"📍 {fish['biome']}", text_color="gray").pack(anchor="w", padx=16)
            ctk.CTkLabel(card, text=f"💡 {fish['note']}", text_color="#f0a500",
                         font=ctk.CTkFont(size=9)).pack(anchor="w", padx=16, pady=(0, 6))

    def _build_calendar_tab(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, corner_radius=0)
        scroll.pack(fill="both", expand=True)
        JOURS = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]
        now = datetime.now()
        ctk.CTkLabel(scroll, text="Calendrier de la semaine",
                     font=ctk.CTkFont(size=12, weight="bold"), text_color="#7eb8f7").pack(pady=8)
        for day_offset in range(7):
            day_dow = (now.weekday() + day_offset) % 7
            day_date = date.today() + timedelta(days=day_offset)
            is_today = (day_offset == 0)
            card = ctk.CTkFrame(scroll, corner_radius=6)
            card.pack(fill="x", padx=8, pady=3)
            prefix = "👉 " if is_today else ""
            ctk.CTkLabel(card, text=f"{prefix}{JOURS[day_dow]} {day_date.strftime('%d/%m')}",
                         font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=8, pady=(6,2))
            rares = []
            for sp in CRITTERS:
                for v in sp["variants"]:
                    if v.get("rare", False) and day_dow in v["days"]:
                        h_s, h_e = v["hours"]
                        rares.append(f"{sp['icon']} {sp['species']} {v['color']} ({h_s:02d}h-{h_e:02d}h)")
            active_events = [ev["name"] for ev in DEFAULT_EVENTS
                             if date.fromisoformat(ev["start"]) <= day_date <= date.fromisoformat(ev["end"])]
            if day_dow == 2:
                ctk.CTkLabel(card, text="💎 Reset Boutique Premium & Dream Snaps (9h UTC)",
                             text_color="#f0a500").pack(anchor="w", padx=16)
            for r in rares:
                ctk.CTkLabel(card, text=f"  ⭐ RARE : {r}",
                             text_color="#f0a500", font=ctk.CTkFont(size=10, weight="bold")).pack(anchor="w", padx=16)
            for ev_txt in active_events:
                ctk.CTkLabel(card, text=f"  🎉 {ev_txt}", text_color="#4caf50").pack(anchor="w", padx=16)
            if not rares and not active_events and day_dow != 2:
                ctk.CTkLabel(card, text="  Jour standard — bestioles communes",
                             text_color="gray", font=ctk.CTkFont(size=9)).pack(anchor="w", padx=16, pady=(0, 4))

    # ─────────────────────────────────────────────────────────────────────────
    # ONGLET ÉVÉNEMENTS
    # ─────────────────────────────────────────────────────────────────────────

    def _build_events_tab(self):
        tab = self.tabs.tab("🎉 Événements")
        ctk.CTkLabel(tab, text="Événements saisonniers & deadlines",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(pady=6)

        scroll = ctk.CTkScrollableFrame(tab, corner_radius=6)
        scroll.pack(fill="both", expand=True, padx=8, pady=4)
        today2 = date.today()

        for ev in DEFAULT_EVENTS:
            try:
                start = date.fromisoformat(ev["start"])
                end   = date.fromisoformat(ev["end"])
            except Exception:
                continue
            active = start <= today2 <= end
            expired = today2 > end
            days_left = (end - today2).days if active else None
            days_until = (start - today2).days if not active and not expired else None

            if expired:
                status_txt, status_col = "✅ Terminé", "gray"
            elif active:
                status_txt, status_col = f"🟢 EN COURS — {days_left}j restants !", "#4caf50"
            else:
                status_txt, status_col = f"⏳ Dans {days_until} jours", "#f0a500"

            card = ctk.CTkFrame(scroll, corner_radius=8)
            card.pack(fill="x", padx=4, pady=5)
            ctk.CTkLabel(card, text=f"📌 {ev['name']}",
                         font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=10, pady=(6,2))
            ctk.CTkLabel(card, text=f"📅 {ev['start']} → {ev['end']}   {status_txt}",
                         text_color=status_col, font=ctk.CTkFont(size=10, weight="bold")).pack(anchor="w", padx=16)
            ev_tasks = self.gs.event_data.get(ev["name"], {})
            for task_name in ev["tasks"]:
                var = ctk.BooleanVar(value=ev_tasks.get(task_name, False))
                def on_ev(en=ev["name"], tn=task_name, v=var):
                    if en not in self.gs.event_data:
                        self.gs.event_data[en] = {}
                    self.gs.event_data[en][tn] = v.get()
                    self.gs.save_all()
                ctk.CTkCheckBox(card, text=task_name, variable=var, command=on_ev).pack(
                    anchor="w", padx=24, pady=2)

        def add_event():
            name = simpledialog.askstring("Nouvel événement", "Nom de l'événement :")
            if not name:
                return
            start_s = simpledialog.askstring("Début", "Date de début (YYYY-MM-DD) :", initialvalue=today_str())
            end_s   = simpledialog.askstring("Fin",   "Date de fin (YYYY-MM-DD) :",   initialvalue=today_str())
            task1   = simpledialog.askstring("Tâche", "Première tâche :")
            tasks_list = [t.strip() for t in [task1] if t and t.strip()]
            DEFAULT_EVENTS.append({"name": name, "start": start_s or today_str(),
                                   "end": end_s or today_str(), "tasks": tasks_list})
            self.gs.event_data[name] = {t: False for t in tasks_list}
            self.gs.save_all()
            messagebox.showinfo("Ajouté", f"Événement '{name}' ajouté ! Rouvre l'onglet pour le voir.")

        ctk.CTkButton(tab, text="➕ Ajouter un événement", width=180, command=add_event).pack(pady=6)

    # ─────────────────────────────────────────────────────────────────────────
    # ONGLET TROPHÉES
    # ─────────────────────────────────────────────────────────────────────────

    def _build_trophy_tab(self):
        tab = self.tabs.tab("🏆 Trophées")

        # Résumé
        summary = ctk.CTkFrame(tab, corner_radius=8)
        summary.pack(fill="x", padx=8, pady=(6,4))
        self._trophy_summary_lbls = {}
        sum_inner = ctk.CTkFrame(summary, fg_color="transparent")
        sum_inner.pack()
        for ttype, (icon, label, color) in TROPHY_TYPE_INFO.items():
            f = ctk.CTkFrame(sum_inner, fg_color="transparent")
            f.pack(side="left", padx=18, pady=6)
            ctk.CTkLabel(f, text=icon, font=ctk.CTkFont(size=20)).pack()
            lbl = ctk.CTkLabel(f, text="0/0", font=ctk.CTkFont(size=11, weight="bold"))
            lbl.pack()
            ctk.CTkLabel(f, text=label, font=ctk.CTkFont(size=9), text_color="gray").pack()
            self._trophy_summary_lbls[ttype] = lbl

        prog_row = ctk.CTkFrame(tab, fg_color="transparent")
        prog_row.pack(fill="x", padx=10, pady=(0,4))
        self.trophy_prog_lbl = ctk.CTkLabel(prog_row, text="", font=ctk.CTkFont(size=11, weight="bold"))
        self.trophy_prog_lbl.pack(side="left")
        self.trophy_prog_bar = ctk.CTkProgressBar(prog_row, width=300)
        self.trophy_prog_bar.set(0)
        self.trophy_prog_bar.pack(side="left", padx=10)

        # Filtres
        flt = ctk.CTkFrame(tab, fg_color="transparent")
        flt.pack(fill="x", padx=8, pady=2)
        self.trophy_type_var   = ctk.StringVar(value="Tous")
        self.trophy_status_var = ctk.StringVar(value="Tous")
        self.trophy_theme_var  = ctk.StringVar(value="Tous")
        self.trophy_search_var = ctk.StringVar()

        for lbl_txt, var, vals in [
            ("Type :", self.trophy_type_var, ["Tous","🏆 Platine","🥇 Or","🥈 Argent","🥉 Bronze"]),
            ("Statut :", self.trophy_status_var, ["Tous","✅ Obtenu","⏳ En cours"]),
            ("Thème :", self.trophy_theme_var, ["Tous"] + TROPHY_THEMES),
        ]:
            ctk.CTkLabel(flt, text=lbl_txt).pack(side="left")
            ctk.CTkComboBox(flt, variable=var, width=130, values=vals,
                            command=lambda _: self._refresh_trophies()).pack(side="left", padx=(2,8))
        ctk.CTkLabel(flt, text="🔍").pack(side="left")
        search_entry = ctk.CTkEntry(flt, textvariable=self.trophy_search_var, width=130)
        search_entry.pack(side="left", padx=2)
        self.trophy_search_var.trace_add("write", lambda *_: self._refresh_trophies())

        self.trophy_scroll = ctk.CTkScrollableFrame(tab, corner_radius=6)
        self.trophy_scroll.pack(fill="both", expand=True, padx=8, pady=4)

        self._refresh_trophies()

    def _refresh_trophies(self):
        for w in self.trophy_scroll.winfo_children():
            w.destroy()

        tv  = self.trophy_type_var.get()
        sv  = self.trophy_status_var.get()
        thv = self.trophy_theme_var.get()
        sq  = self.trophy_search_var.get().lower()
        theme_icons = {"Général":"🌟","Social":"💬","Collecte":"🌿","Cuisine":"🍳",
                       "Commerce":"🛒","Quêtes":"📜","Exploration":"🗺️","Construction":"🏗️"}
        themes_present = []
        for t in TROPHIES:
            if t["theme"] not in themes_present:
                themes_present.append(t["theme"])

        for theme in themes_present:
            if thv != "Tous" and thv != theme:
                continue
            visible = [t for t in TROPHIES if t["theme"] == theme
                       and (tv == "Tous" or
                            (tv == "🏆 Platine" and t["type"] == "platinum") or
                            (tv == "🥇 Or"     and t["type"] == "gold") or
                            (tv == "🥈 Argent" and t["type"] == "silver") or
                            (tv == "🥉 Bronze" and t["type"] == "bronze"))
                       and (sv == "Tous" or
                            (sv == "✅ Obtenu"   and self.gs.trophy_data[t["id"]]["unlocked"]) or
                            (sv == "⏳ En cours" and not self.gs.trophy_data[t["id"]]["unlocked"]))
                       and (not sq or sq in t["name"].lower() or sq in t["description"].lower())]
            if not visible:
                continue
            ctk.CTkLabel(self.trophy_scroll,
                         text=f"{theme_icons.get(theme,'📌')} {theme}",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color="#7eb8f7").pack(anchor="w", padx=8, pady=(10,2))
            for t in visible:
                self._build_trophy_card(t)

        # Mettre à jour le résumé
        total_all = len(TROPHIES)
        done_all  = sum(1 for t in TROPHIES if self.gs.trophy_data[t["id"]]["unlocked"])
        pct = done_all / total_all if total_all else 0
        self.trophy_prog_lbl.configure(text=f"Progression : {done_all}/{total_all} ({int(pct*100)}%)")
        self.trophy_prog_bar.set(pct)
        for ttype in TROPHY_TYPE_INFO:
            g = [t for t in TROPHIES if t["type"] == ttype]
            d = sum(1 for t in g if self.gs.trophy_data[t["id"]]["unlocked"])
            self._trophy_summary_lbls[ttype].configure(text=f"{d}/{len(g)}")

    def _build_trophy_card(self, trophy: dict):
        td = self.gs.trophy_data[trophy["id"]]
        icon, type_label, color = TROPHY_TYPE_INFO[trophy["type"]]
        bg_color = ("#2a3a2a" if self.gs.theme == "dark" else "#e8f5e9") if td["unlocked"] else ("gray17" if self.gs.theme == "dark" else "gray90")

        card = ctk.CTkFrame(self.trophy_scroll, corner_radius=8, fg_color=bg_color)
        card.pack(fill="x", padx=6, pady=3)

        top_row = ctk.CTkFrame(card, fg_color="transparent")
        top_row.pack(fill="x", padx=8, pady=(6,0))

        ctk.CTkLabel(top_row, text=icon, font=ctk.CTkFont(size=20), width=36).pack(side="left")

        unlocked_var = ctk.BooleanVar(value=td["unlocked"])
        def on_toggle(t=trophy, v=unlocked_var):
            td2 = self.gs.trophy_data[t["id"]]
            td2["unlocked"] = v.get()
            if v.get() and t["max_value"]:
                td2["progress"] = t["max_value"]
            self.gs.save_all()
            self._refresh_trophies()
        ctk.CTkCheckBox(top_row, text="", variable=unlocked_var, command=on_toggle, width=28).pack(side="left")

        name_style = ctk.CTkFont(size=12, weight="bold", overstrike=td["unlocked"])
        ctk.CTkLabel(top_row, text=trophy["name"], font=name_style,
                     text_color="#888888" if td["unlocked"] else "white").pack(side="left", padx=4)
        ctk.CTkLabel(top_row, text=f"{trophy['rarity']:.1f}% joueurs  •  {trophy['difficulty']}",
                     font=ctk.CTkFont(size=9), text_color="gray").pack(side="right", padx=8)

        ctk.CTkLabel(card, text=trophy["description"],
                     font=ctk.CTkFont(size=10), anchor="w").pack(anchor="w", padx=50)
        ctk.CTkLabel(card, text=f"📋 {trophy['condition']}",
                     font=ctk.CTkFont(size=9), text_color="gray",
                     anchor="w", wraplength=550).pack(anchor="w", padx=50, pady=(1,0))

        if trophy["max_value"] and not td["unlocked"]:
            pr = ctk.CTkFrame(card, fg_color="transparent")
            pr.pack(fill="x", padx=50, pady=(4,0))
            prog_var = ctk.IntVar(value=td["progress"])
            pct_init = td["progress"] / trophy["max_value"] if trophy["max_value"] else 0
            prog_bar = ctk.CTkProgressBar(pr, width=200)
            prog_bar.set(pct_init)
            prog_bar.pack(side="left")
            pct = int(pct_init * 100)
            prog_lbl = ctk.CTkLabel(pr, text=f"  {td['progress']:,}/{trophy['max_value']:,} ({pct}%)",
                                    font=ctk.CTkFont(size=9), text_color="gray")
            prog_lbl.pack(side="left")
            spin = ctk.CTkEntry(pr, textvariable=prog_var, width=80)
            spin.pack(side="left", padx=6)
            def on_prog(*_, tid=trophy["id"], mv=trophy["max_value"], pv=prog_var, pl=prog_lbl, pb=prog_bar):
                try:
                    val = min(int(pv.get()), mv)
                    self.gs.trophy_data[tid]["progress"] = val
                    pl.configure(text=f"  {val:,}/{mv:,} ({int(val/mv*100)}%)")
                    pb.set(val / mv)
                    self.gs.save_all()
                except Exception:
                    pass
            prog_var.trace_add("write", on_prog)

        ctk.CTkLabel(card, text=f"💡 {trophy['tip']}",
                     font=ctk.CTkFont(size=9), text_color="#f0a500",
                     anchor="w", wraplength=550).pack(anchor="w", padx=50, pady=(2,0))

        note_entry = ctk.CTkEntry(card, placeholder_text="📝 Note personnelle...", width=380)
        if td.get("note"):
            note_entry.insert(0, td["note"])
        note_entry.pack(anchor="w", padx=50, pady=(4,6))
        def save_note(e, tid=trophy["id"], entry=note_entry):
            self.gs.trophy_data[tid]["note"] = entry.get().strip()
            self.gs.save_all()
        note_entry.bind("<FocusOut>", save_note)

    # ─────────────────────────────────────────────────────────────────────────
    # ONGLET VILLAGEOIS
    # ─────────────────────────────────────────────────────────────────────────

    def _get_visible_groups(self):
        groups = [("🏰 Base Game", VILLAGERS_BASE)]
        if self.gs.dlc_enabled.get("dlc1"): groups.append(("⭐ DLC 1", VILLAGERS_DLC1))
        if self.gs.dlc_enabled.get("dlc2"): groups.append(("⭐ DLC 2", VILLAGERS_DLC2))
        if self.gs.dlc_enabled.get("dlc3"): groups.append(("⭐ DLC 3", VILLAGERS_DLC3))
        return groups

    def _build_villager_tab(self):
        tab = self.tabs.tab("👥 Villageois")

        # DLC
        dlc_frame = ctk.CTkFrame(tab, corner_radius=8)
        dlc_frame.pack(fill="x", padx=8, pady=(6,4))
        ctk.CTkLabel(dlc_frame, text="🎮 DLC Installés",
                     font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=10)
        self._dlc_vars = {}
        for key, label in [("dlc1","⭐ DLC 1"),("dlc2","⭐ DLC 2"),("dlc3","⭐ DLC 3")]:
            var = ctk.BooleanVar(value=self.gs.dlc_enabled.get(key, False))
            self._dlc_vars[key] = var
            def on_dlc(k=key, v=var):
                self.gs.dlc_enabled[k] = v.get()
                self.gs.save_all()
                self._populate_villager_list()
            ctk.CTkCheckBox(dlc_frame, text=label, variable=var, command=on_dlc).pack(side="left", padx=15, pady=6)

        # Priorités niveau 10
        near10_frame = ctk.CTkFrame(tab, corner_radius=6)
        near10_frame.pack(fill="x", padx=8, pady=(0,4))
        self.near10_lbl = ctk.CTkLabel(near10_frame, text="",
                                        text_color="#f0a500", font=ctk.CTkFont(size=10))
        self.near10_lbl.pack(anchor="w", padx=10, pady=4)

        # Recherche
        sf = ctk.CTkFrame(tab, fg_color="transparent")
        sf.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(sf, text="🔍 Rechercher :").pack(side="left")
        self.v_search_var = ctk.StringVar()
        self.v_search_var.trace_add("write", lambda *_: self._populate_villager_list())
        ctk.CTkEntry(sf, textvariable=self.v_search_var, width=220).pack(side="left", padx=6)
        ctk.CTkLabel(sf, text="Clic ✅ = discuté  |  +/- niveau  |  🎁 cadeaux",
                     font=ctk.CTkFont(size=9), text_color="gray").pack(side="right", padx=4)

        # Liste scrollable
        self.v_scroll = ctk.CTkScrollableFrame(tab, corner_radius=6)
        self.v_scroll.pack(fill="both", expand=True, padx=8, pady=4)

        self._populate_villager_list()

    def _populate_villager_list(self):
        for w in self.v_scroll.winfo_children():
            w.destroy()

        sq = self.v_search_var.get().lower()
        for group_label, group_villagers in self._get_visible_groups():
            filtered = [v for v in group_villagers if not sq or sq in v.lower()]
            if not filtered:
                continue
            ctk.CTkLabel(self.v_scroll, text=f"── {group_label} ──",
                         font=ctk.CTkFont(size=11, weight="bold"),
                         text_color="#aaaacc").pack(anchor="w", padx=8, pady=(8,2))
            for villager in filtered:
                self._build_villager_row(villager)

        # Près du niveau 10
        near10 = sorted([(n, d["level"]) for n, d in self.gs.villagers_data.items()
                          if 7 <= d["level"] < 10], key=lambda x: -x[1])[:5]
        if near10:
            self.near10_lbl.configure(
                text="🎯 Proches du max : " + " | ".join(f"{n} (niv.{l})" for n, l in near10))
        else:
            self.near10_lbl.configure(text="Tous les villageois actifs sont au max ou en dessous de 7 !")

    def _build_villager_row(self, name: str):
        d = self.gs.villagers_data[name]
        row = ctk.CTkFrame(self.v_scroll, corner_radius=6, height=36)
        row.pack(fill="x", padx=4, pady=2)
        row.pack_propagate(False)

        # Checked
        check_var = ctk.BooleanVar(value=d["checked"])
        def on_check(n=name, v=check_var):
            was = self.gs.villagers_data[n]["checked"]
            self.gs.villagers_data[n]["checked"] = v.get()
            # Sync trophée Moulin à paroles
            td = self.gs.trophy_data.get("silver_01")
            if td and not td["unlocked"]:
                if v.get() and not was:
                    td["progress"] = min(1000, td["progress"] + 1)
                elif not v.get() and was:
                    td["progress"] = max(0, td["progress"] - 1)
                if td["progress"] >= 1000:
                    td["unlocked"] = True
            self.gs.save_all()
        ctk.CTkCheckBox(row, text="", variable=check_var, command=on_check, width=28).pack(side="left", padx=2)

        # Nom
        ctk.CTkLabel(row, text=name, width=160, anchor="w",
                     font=ctk.CTkFont(size=11)).pack(side="left", padx=4)

        # Niveau
        level_lbl = ctk.CTkLabel(row, text=f"Niv.{d['level']}", width=50,
                                  font=ctk.CTkFont(size=11, weight="bold"),
                                  text_color="#7eb8f7" if d["level"] < 10 else "#4caf50")
        level_lbl.pack(side="left")

        def inc_level(n=name, lbl=level_lbl):
            d2 = self.gs.villagers_data[n]
            old = d2["level"]
            d2["level"] = min(10, d2["level"] + 1)
            td6 = self.gs.trophy_data.get("gold_06")
            if td6 and not td6["unlocked"]:
                if d2["level"] == 10 and old < 10:
                    td6["progress"] = min(15, td6["progress"] + 1)
                if td6["progress"] >= 15:
                    td6["unlocked"] = True
            lbl.configure(text=f"Niv.{d2['level']}",
                          text_color="#4caf50" if d2["level"] == 10 else "#7eb8f7")
            self.gs.save_all()

        def dec_level(n=name, lbl=level_lbl):
            d2 = self.gs.villagers_data[n]
            old = d2["level"]
            d2["level"] = max(1, d2["level"] - 1)
            td6 = self.gs.trophy_data.get("gold_06")
            if td6 and not td6["unlocked"]:
                if d2["level"] < 10 and old == 10:
                    td6["progress"] = max(0, td6["progress"] - 1)
            lbl.configure(text=f"Niv.{d2['level']}",
                          text_color="#4caf50" if d2["level"] == 10 else "#7eb8f7")
            self.gs.save_all()

        ctk.CTkButton(row, text="+", width=28, command=inc_level).pack(side="left", padx=1)
        ctk.CTkButton(row, text="-", width=28, command=dec_level).pack(side="left", padx=1)

        # Cadeaux
        for gift_idx in range(3):
            gvar = ctk.BooleanVar(value=d["gifts"][gift_idx])
            def on_gift(n=name, gi=gift_idx, v=gvar):
                was = self.gs.villagers_data[n]["gifts"][gi]
                self.gs.villagers_data[n]["gifts"][gi] = v.get()
                td = self.gs.trophy_data.get("gold_07")
                if td and not td["unlocked"]:
                    if v.get() and not was:
                        td["progress"] = min(540, td["progress"] + 1)
                    elif not v.get() and was:
                        td["progress"] = max(0, td["progress"] - 1)
                    if td["progress"] >= 540:
                        td["unlocked"] = True
                self.gs.save_all()
            ctk.CTkCheckBox(row, text="🎁", variable=gvar, command=on_gift,
                            width=50, font=ctk.CTkFont(size=10)).pack(side="left", padx=1)

    # ─────────────────────────────────────────────────────────────────────────
    # ONGLET STATS (graphiques natifs — sans matplotlib)
    # ─────────────────────────────────────────────────────────────────────────

    def _build_stats_tab(self):
        tab = self.tabs.tab("📊 Stats")

        # Cartes résumé
        summary = ctk.CTkFrame(tab, corner_radius=8)
        summary.pack(fill="x", padx=8, pady=8)
        self._stat_lbls = {}
        stat_items = [
            ("streak",     "🔥 Streak actuel",      lambda: self.gs.streak.get("count", 0)),
            ("best",       "🏅 Meilleur streak",     lambda: self.gs.streak.get("best", 0)),
            ("tasks_done", "✅ Tâches aujourd'hui",  lambda: f"{sum(self.gs.daily_checked)}/{len(self.gs.tasks_meta)}"),
            ("vill_10",    "👥 Villageois niv.10",   lambda: sum(1 for d in self.gs.villagers_data.values() if d["level"]==10)),
            ("trophies",   "🏆 Trophées débloqués",  lambda: f"{sum(1 for t in TROPHIES if self.gs.trophy_data[t['id']]['unlocked'])}/{len(TROPHIES)}"),
            ("avg7",       "📈 Moy. 7j",             lambda: self._avg_completion(7)),
            ("avg30",      "📈 Moy. 30j",            lambda: self._avg_completion(30)),
        ]
        for idx, (key, label, fn) in enumerate(stat_items):
            r, c = divmod(idx, 4)
            f = ctk.CTkFrame(summary, corner_radius=6)
            f.grid(row=r, column=c, padx=6, pady=6, sticky="nsew")
            summary.columnconfigure(c, weight=1)
            ctk.CTkLabel(f, text=label, font=ctk.CTkFont(size=9), text_color="gray").pack(pady=(6,0))
            lbl = ctk.CTkLabel(f, text="...", font=ctk.CTkFont(size=16, weight="bold"))
            lbl.pack(pady=(0,6))
            self._stat_lbls[key] = (lbl, fn)

        ctk.CTkButton(tab, text="🔄 Actualiser les stats", width=160,
                      command=self._refresh_stats).pack(pady=4)

        # Graphiques natifs
        graphs_nb = ctk.CTkTabview(tab, corner_radius=6)
        graphs_nb.pack(fill="both", expand=True, padx=8, pady=4)
        graphs_nb.add("📅 Complétion 14j")
        graphs_nb.add("👥 Niveaux villageois")
        graphs_nb.add("🏆 Trophées")

        self._chart_frames = {
            "completion": graphs_nb.tab("📅 Complétion 14j"),
            "villagers":  graphs_nb.tab("👥 Niveaux villageois"),
            "trophies":   graphs_nb.tab("🏆 Trophées"),
        }
        self._refresh_stats()

    def _avg_completion(self, days: int) -> str:
        today2 = date.today()
        vals = []
        for i in range(days):
            d = (today2 - timedelta(days=i)).isoformat()
            entry = self.gs.history.get(d)
            if entry and entry["total"]:
                vals.append(int(entry["done"]/entry["total"]*100))
        return f"{int(sum(vals)/len(vals))}%" if vals else "N/A"

    def _refresh_stats(self):
        for key, (lbl, fn) in self._stat_lbls.items():
            lbl.configure(text=str(fn()))

        # Complétion 14j
        today2 = date.today()
        labels, values, colors_list = [], [], []
        for i in range(13, -1, -1):
            d = (today2 - timedelta(days=i)).isoformat()
            labels.append(d[5:])
            entry = self.gs.history.get(d)
            v = int(entry["done"]/entry["total"]*100) if entry and entry["total"] else 0
            values.append(v)
            colors_list.append("#4caf50" if v==100 else "#f0a500" if v>=50 else "#e74c3c")
        draw_bar_chart_native(self._chart_frames["completion"], labels, values, colors_list,
                              "Complétion quotidienne (14 jours)", 100, 220)
        ctk.CTkButton(self._chart_frames["completion"], text="🔄", width=60,
                      command=self._refresh_stats).pack(pady=2)

        # Niveaux villageois
        counts = [0]*10
        for d in self.gs.villagers_data.values():
            lvl = max(1, min(10, d["level"]))
            counts[lvl-1] += 1
        draw_bar_chart_native(self._chart_frames["villagers"],
                              [str(i+1) for i in range(10)], counts,
                              ["#7eb8f7"]*10, "Répartition des niveaux d'amitié", max(counts or [1]), 220)

        # Trophées
        types = ["platinum","gold","silver","bronze"]
        labels2 = ["Platine","Or","Argent","Bronze"]
        done_vals = [sum(1 for t in TROPHIES if t["type"]==tp and self.gs.trophy_data[t["id"]]["unlocked"])
                     for tp in types]
        total_vals = [sum(1 for t in TROPHIES if t["type"]==tp) for tp in types]
        cols = ["#b0c4de","#ffd700","#c0c0c0","#cd7f32"]
        draw_bar_chart_native(self._chart_frames["trophies"], labels2, done_vals, cols,
                              "Trophées obtenus", max(total_vals or [1]), 220)

    # ─────────────────────────────────────────────────────────────────────────
    # ONGLET PARAMÈTRES
    # ─────────────────────────────────────────────────────────────────────────

    def _build_settings_tab(self):
        tab = self.tabs.tab("⚙️ Paramètres")
        scroll = ctk.CTkScrollableFrame(tab, corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=8, pady=8)

        # ── Multi-comptes ──────────────────────────────────────────────────
        ctk.CTkLabel(scroll, text="👤 Gestion des comptes",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=4, pady=(8,4))

        accounts_frame = ctk.CTkFrame(scroll, corner_radius=8)
        accounts_frame.pack(fill="x", padx=4, pady=4)

        self._acc_radio_var = ctk.StringVar(value=self.gs.current_account)
        self._accounts_inner = ctk.CTkFrame(accounts_frame, fg_color="transparent")
        self._accounts_inner.pack(anchor="w", padx=10, pady=6)
        self._refresh_accounts_ui()

        def new_account():
            name = simpledialog.askstring("Nouveau compte", "Nom du compte :")
            if not name or not name.strip():
                return
            name = name.strip().replace(" ", "_")
            existing = self.gs.get_accounts()
            if name in existing:
                messagebox.showwarning("Existe déjà", f"Le compte '{name}' existe déjà.")
                return
            self.gs.create_account(name)
            self._switch_account(name)
        ctk.CTkButton(accounts_frame, text="➕ Nouveau compte", width=160, command=new_account).pack(padx=10, pady=(0,8))

        # ── Mode Hardcore ──────────────────────────────────────────────────
        ctk.CTkLabel(scroll, text="⚙️ Options",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=4, pady=(16,4))
        opts_frame = ctk.CTkFrame(scroll, corner_radius=8)
        opts_frame.pack(fill="x", padx=4, pady=4)

        hc_var = ctk.BooleanVar(value=self.gs.hardcore_mode)
        def toggle_hc():
            self.gs.hardcore_mode = hc_var.get()
            self.gs.save_all()
            if self.gs.hardcore_mode:
                messagebox.showwarning("Mode Hardcore",
                    "💀 Mode Hardcore activé !\nSi tu passes une journée sans tout cocher, ton streak est remis à zéro.")
        ctk.CTkCheckBox(opts_frame, text="💀 Mode Hardcore (streak reset si journée incomplète)",
                        variable=hc_var, command=toggle_hc).pack(anchor="w", padx=12, pady=8)

        # ── Actions dangereuses ──────────────────────────────────────────
        ctk.CTkLabel(scroll, text="🔄 Actions",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=4, pady=(16,4))
        act_frame = ctk.CTkFrame(scroll, corner_radius=8)
        act_frame.pack(fill="x", padx=4, pady=4)

        def nouveau_jour():
            self.gs.reset_day()
            self._refresh_task_list()
            self._populate_villager_list()
            messagebox.showinfo("Nouveau jour", "✅ Bonne journée ! Toutes les tâches ont été remises à zéro.")
        ctk.CTkButton(act_frame, text="🌅 Nouveau jour", width=160, command=nouveau_jour).pack(side="left", padx=10, pady=10)

        def tout_reinit():
            if not messagebox.askyesno("Confirmer", "⚠️ Tout réinitialiser (niveaux, trophées, historique) ?"):
                return
            self.gs.reset_all()
            self._refresh_all()
        ctk.CTkButton(act_frame, text="🔄 Tout réinitialiser", width=160,
                      fg_color="#e74c3c", hover_color="#c0392b", command=tout_reinit).pack(side="left", padx=4, pady=10)

        # ── Info bot Discord ──────────────────────────────────────────────
        ctk.CTkLabel(scroll, text="🤖 Bot Discord",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=4, pady=(16,4))
        discord_frame = ctk.CTkFrame(scroll, corner_radius=8)
        discord_frame.pack(fill="x", padx=4, pady=4)
        info_text = (
            "Pour activer le bot Discord :\n"
            "  1. Va sur https://discord.com/developers/applications et crée une application\n"
            "  2. Dans 'Bot', génère un token et copie-le\n"
            "  3. Installe discord.py : pip install discord.py\n"
            "  4. Lance bot_discord.py séparément (même dossier que ce fichier)\n"
            "  5. Commandes disponibles : /daily  /streak  /trophee  /stats\n\n"
            f"  Base de données partagée : {DB_PATH}"
        )
        ctk.CTkLabel(discord_frame, text=info_text, justify="left",
                     font=ctk.CTkFont(size=10), text_color="gray",
                     anchor="w", wraplength=700).pack(anchor="w", padx=12, pady=10)

    def _refresh_accounts_ui(self):
        for w in self._accounts_inner.winfo_children():
            w.destroy()
        for acc in self.gs.get_accounts():
            def switch(a=acc):
                self._switch_account(a)
            prefix = "✅ " if acc == self.gs.current_account else "   "
            ctk.CTkButton(self._accounts_inner, text=f"{prefix}{acc}", width=140,
                          command=switch,
                          fg_color="#2a4a2a" if acc == self.gs.current_account else None).pack(side="left", padx=4)

    def _switch_account(self, account: str):
        self.gs.save_all()
        self.gs.load(account)
        self.title(f"🏰 DDV Checklist — {account}")
        self._refresh_all()
        self._refresh_accounts_ui()
        messagebox.showinfo("Compte changé", f"Compte actif : {account}")

    # ─────────────────────────────────────────────────────────────────────────
    # UTILITAIRES
    # ─────────────────────────────────────────────────────────────────────────

    def _toggle_theme(self):
        self.gs.theme = "light" if self.gs.theme == "dark" else "dark"
        ctk.set_appearance_mode("dark" if self.gs.theme == "dark" else "light")
        self.theme_btn.configure(text="☀️ Clair" if self.gs.theme == "dark" else "🌙 Sombre")
        self.gs.save_all()

    def _nouveau_jour(self):
        self.gs.reset_day()
        self._refresh_task_list()
        self._populate_villager_list()
        messagebox.showinfo("Nouveau jour", "✅ Bonne journée ! Toutes les tâches ont été remises à zéro.")

    def _refresh_all(self):
        self._refresh_task_list()
        self._refresh_history()
        self._refresh_trophies()
        self._refresh_stats()
        self._populate_villager_list()
        self._update_progress()

    def _update_statusbar(self):
        done = sum(self.gs.daily_checked)
        v_done = sum(1 for d in self.gs.villagers_data.values() if d["checked"])
        visible_count = sum(len(g[1]) for g in self._get_visible_groups())
        t_done = sum(1 for t in TROPHIES if self.gs.trophy_data[t["id"]]["unlocked"])
        hc_txt = " 💀HARDCORE" if self.gs.hardcore_mode else ""
        self.statusbar.configure(
            text=f"Tâches {done}/{len(self.gs.tasks_meta)}  |  Villageois {v_done}/{visible_count}  |  Trophées {t_done}/{len(TROPHIES)}{hc_txt}  |  [{self.gs.current_account}]"
        )
        self.after(3000, self._update_statusbar)


# ══════════════════════════════════════════════════════════════════════════════
#  POINT D'ENTRÉE
# ══════════════════════════════════════════════════════════════════════════════

def main():
    init_db()
    state = DDVState()
    state.load("default")
    app = DDVApp(state)
    app.mainloop()


if __name__ == "__main__":
    main()