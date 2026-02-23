# Guide d'intégration — Recettes & Quêtes dans DDV Checklist

## Vue d'ensemble

Tu as 2 fichiers à utiliser :
- **`download_dvguide_data.py`** — Script à lancer **une seule fois** pour télécharger les données
- **`patch_recipes_quests.py`** — Code à intégrer dans `dreamlight_checklist.py`

---

## Étape 1 — Télécharger les données

```bash
pip install requests
python download_dvguide_data.py
```

Ce script télécharge `recipes.json` et `quests.json` depuis le repo GitHub dans :
```
~/.ddv_checklist/dvguide_data/
```

---

## Étape 2 — Intégrer le patch dans dreamlight_checklist.py

Il y a **5 endroits** à modifier. Chaque bloc est clairement marqué dans `patch_recipes_quests.py`.

---

### 🅐 Après les imports (ligne ~30)

Colle le **BLOC A** juste après :
```python
import sqlite3, os, csv, time, io, json
from datetime import date, timedelta, datetime
from pathlib import Path
```

→ Ajoute le chargeur `_load_dvguide_file()` et les variables globales `DVGUIDE_RECIPES`, `DVGUIDE_QUESTS`.

---

### 🅑 Dans `init_db()` — Nouvelles tables SQL

Dans le `conn.executescript("""...""")` de `init_db()`, ajoute avant le `""")` fermant :

```sql
CREATE TABLE IF NOT EXISTS recipes_progress (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id  INTEGER NOT NULL REFERENCES accounts(id),
    recipe_id   TEXT NOT NULL,
    cooked      INTEGER NOT NULL DEFAULT 0,
    favorite    INTEGER NOT NULL DEFAULT 0,
    UNIQUE(account_id, recipe_id)
);

CREATE TABLE IF NOT EXISTS quests_progress (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id  INTEGER NOT NULL REFERENCES accounts(id),
    quest_id    TEXT NOT NULL,
    completed   INTEGER NOT NULL DEFAULT 0,
    in_progress INTEGER NOT NULL DEFAULT 0,
    note        TEXT NOT NULL DEFAULT '',
    UNIQUE(account_id, quest_id)
);
```

---

### 🅒 Dans la classe `DDVState` — 4 nouvelles méthodes

Colle les 4 fonctions du **BLOC C** à l'intérieur de la classe `DDVState` (n'importe où parmi les autres méthodes `_load_*`).

Puis dans `DDVState.load()`, ajoute à la fin :
```python
self._load_recipes_progress()
self._load_quests_progress()
```

Et dans `DDVState.save_all()`, à l'intérieur du `with get_db() as conn:` :
```python
self._save_recipes_progress(conn)
self._save_quests_progress(conn)
```

Aussi initialiser les dicts dans `DDVState.__init__()` :
```python
self.recipes_progress: dict = {}
self.quests_progress: dict = {}
```

---

### 🅓 Dans `DDVApp._build_ui()` — Déclarer les 2 nouveaux onglets

Dans le bloc des `self.tabs.add(...)`, ajouter après `"👥 Villageois"` :
```python
self.tabs.add("🍳 Recettes")
self.tabs.add("📜 Quêtes")
```

Et dans le bloc des `self._build_*_tab()`, ajouter après `self._build_villager_tab()` :
```python
self._build_recipes_tab()
self._build_quests_tab()
```

---

### 🅔 Dans la classe `DDVApp` — 5 nouvelles méthodes

Colle **tout le BLOC E** dans la classe `DDVApp`, juste avant `_build_settings_tab`.

Les 5 méthodes à ajouter :
- `_build_recipes_tab(self)`
- `_refresh_recipes_list(self)`
- `_recipe_row(self, parent, recipe, rid, is_cooked, is_fav)`
- `_build_quests_tab(self)`
- `_refresh_quests_list(self)`
- `_quest_row(self, parent, quest, qid, is_done, is_prog)`

---

## Résultat attendu

| Onglet | Fonctionnalités |
|--------|----------------|
| 🍳 Recettes | Recherche, filtre par catégorie, cocher "cuisinée", marquer en favori, stats de progression |
| 📜 Quêtes | Recherche, filtre par personnage, statut (terminée / en cours), groupement par personnage, étapes dépliables |

Les deux onglets affichent un message d'aide si les données n'ont pas encore été téléchargées, sans bloquer le reste de l'application.

---

## FAQ

**Le script de téléchargement plante ?**
Lance-le et lis les messages d'erreur. Si le repo a changé sa structure de fichiers, ouvre `download_dvguide_data.py` et adapte `FILES_TO_FETCH` avec les vrais chemins des JSON.

**Les données sont vides après téléchargement ?**
Vérifie le contenu de `~/.ddv_checklist/dvguide_data/`. Si les JSON sont présents mais vides, ouvre-les pour voir leur structure et adapte les fonctions `normalize_*` dans `download_dvguide_data.py`.

**Puis-je mettre les données à jour ?**
Oui, relance simplement `download_dvguide_data.py`. Les anciennes données seront remplacées. Ta progression (recettes cuisinées, quêtes terminées) reste en base SQLite, elle n'est pas touchée.
