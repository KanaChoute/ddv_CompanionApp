# -*- coding: utf-8 -*-
"""
DDV Guide Data Downloader
═════════════════════════
Script à lancer UNE SEULE FOIS pour télécharger les données du repo
GitHub : 0xWDG/DreamlightValleyGuide-Data

Les données seront sauvegardées dans :
    ~/.ddv_checklist/dvguide_data/

Utilisation :
    pip install requests
    python download_dvguide_data.py

Ce script télécharge et normalise :
  • recipes.json      → toutes les recettes
  • quests.json       → toutes les quêtes par personnage
  • characters.json   → tous les personnages/villageois
  • items.json        → objets, meubles, vêtements
  • critters.json     → bestioles
  • fish.json         → poissons
"""

import json
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("❌ Le module 'requests' est manquant.")
    print("   Installe-le avec : pip install requests")
    sys.exit(1)

# ── Configuration ──────────────────────────────────────────────────────────────

OUTPUT_DIR = Path.home() / ".ddv_checklist" / "dvguide_data"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://raw.githubusercontent.com/0xWDG/DreamlightValleyGuide-Data/main"

# Fichiers à récupérer dans le repo — adapter selon la structure réelle du repo
# Format : (chemin_dans_le_repo, nom_local)
FILES_TO_FETCH = [
    ("recipes.json",    "recipes.json"),
    ("quests.json",     "quests.json"),
    ("characters.json", "characters.json"),
    ("items.json",      "items.json"),
    ("critters.json",   "critters.json"),
    ("fish.json",       "fish.json"),
]

# Fichiers alternatifs si la structure est en sous-dossiers
FALLBACK_PATHS = {
    "recipes.json":    ["Data/recipes.json", "data/recipes.json", "Recipes/recipes.json"],
    "quests.json":     ["Data/quests.json",  "data/quests.json",  "Quests/quests.json"],
    "characters.json": ["Data/characters.json", "data/characters.json", "Characters/characters.json"],
    "items.json":      ["Data/items.json",   "data/items.json",   "Items/items.json"],
    "critters.json":   ["Data/critters.json","data/critters.json","Critters/critters.json"],
    "fish.json":       ["Data/fish.json",    "data/fish.json",    "Fish/fish.json"],
}


def fetch_json(url: str) -> dict | list | None:
    """Télécharge et parse un JSON depuis une URL."""
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return None
        print(f"  ⚠️  HTTP {e.response.status_code} pour {url}")
        return None
    except Exception as e:
        print(f"  ❌ Erreur : {e}")
        return None


def try_fetch_file(local_name: str, primary_path: str) -> tuple[dict | list | None, str]:
    """Essaie le chemin principal puis les fallbacks."""
    url = f"{BASE_URL}/{primary_path}"
    print(f"  Tentative : {url}")
    data = fetch_json(url)
    if data is not None:
        return data, url

    for fallback in FALLBACK_PATHS.get(local_name, []):
        url = f"{BASE_URL}/{fallback}"
        print(f"  Fallback  : {url}")
        data = fetch_json(url)
        if data is not None:
            return data, url

    return None, ""


def discover_repo_structure() -> dict:
    """
    Tente de récupérer la liste des fichiers du repo via l'API GitHub.
    Retourne un dict {nom_fichier: url_raw}.
    """
    api_url = "https://api.github.com/repos/0xWDG/DreamlightValleyGuide-Data/git/trees/main?recursive=1"
    try:
        r = requests.get(api_url, timeout=15)
        if r.status_code == 200:
            tree = r.json().get("tree", [])
            return {
                item["path"]: f"{BASE_URL}/{item['path']}"
                for item in tree
                if item["type"] == "blob" and item["path"].endswith(".json")
            }
    except Exception:
        pass
    return {}


def normalize_recipes(data: list | dict) -> list:
    """Normalise les recettes vers un format standard."""
    if isinstance(data, dict):
        # Cas où c'est un dict avec une clé principale
        for key in ("recipes", "Recipes", "data", "items"):
            if key in data:
                data = data[key]
                break
        if isinstance(data, dict):
            data = list(data.values())

    normalized = []
    for item in data:
        if not isinstance(item, dict):
            continue
        normalized.append({
            "id":           item.get("id", item.get("identifier", "")),
            "name":         item.get("name", item.get("title", item.get("recipeName", ""))),
            "category":     item.get("category", item.get("type", "Autre")),
            "ingredients":  item.get("ingredients", item.get("items", [])),
            "energy":       item.get("energy", item.get("energyRestored", 0)),
            "sell_price":   item.get("sellPrice", item.get("sell_price", item.get("price", 0))),
            "description":  item.get("description", ""),
            "image":        item.get("image", item.get("icon", "")),
            "unlock":       item.get("unlock", item.get("unlockedBy", "")),
        })
    return normalized


def normalize_quests(data: list | dict) -> list:
    """Normalise les quêtes vers un format standard."""
    if isinstance(data, dict):
        for key in ("quests", "Quests", "data"):
            if key in data:
                data = data[key]
                break
        if isinstance(data, dict):
            data = list(data.values())

    normalized = []
    for item in data:
        if not isinstance(item, dict):
            continue
        normalized.append({
            "id":          item.get("id", item.get("identifier", "")),
            "name":        item.get("name", item.get("title", item.get("questName", ""))),
            "character":   item.get("character", item.get("npc", item.get("villager", ""))),
            "description": item.get("description", item.get("desc", "")),
            "type":        item.get("type", item.get("questType", "Story")),
            "steps":       item.get("steps", item.get("tasks", item.get("objectives", []))),
            "rewards":     item.get("rewards", item.get("reward", [])),
            "requires":    item.get("requires", item.get("prerequisite", "")),
            "friendship_level": item.get("friendshipLevel", item.get("friendship_level", item.get("level", 0))),
        })
    return normalized


def normalize_characters(data: list | dict) -> list:
    """Normalise les personnages."""
    if isinstance(data, dict):
        for key in ("characters", "Characters", "villagers", "data"):
            if key in data:
                data = data[key]
                break
        if isinstance(data, dict):
            data = list(data.values())

    normalized = []
    for item in data:
        if not isinstance(item, dict):
            continue
        normalized.append({
            "id":       item.get("id", item.get("identifier", "")),
            "name":     item.get("name", ""),
            "realm":    item.get("realm", item.get("world", item.get("biome", ""))),
            "role":     item.get("role", item.get("type", "")),
            "gifts":    item.get("gifts", item.get("favoriteGifts", [])),
            "schedule": item.get("schedule", []),
            "image":    item.get("image", item.get("icon", "")),
        })
    return normalized


NORMALIZERS = {
    "recipes.json":    normalize_recipes,
    "quests.json":     normalize_quests,
    "characters.json": normalize_characters,
}


def main():
    print("╔══════════════════════════════════════════════════════╗")
    print("║  DDV Guide Data Downloader                           ║")
    print("║  0xWDG/DreamlightValleyGuide-Data → ~/.ddv_checklist ║")
    print("╚══════════════════════════════════════════════════════╝\n")

    # Essai de découverte automatique de la structure du repo
    print("📡 Récupération de la structure du repo GitHub...")
    repo_files = discover_repo_structure()
    if repo_files:
        print(f"  ✅ {len(repo_files)} fichiers JSON trouvés dans le repo.")
        # Sauvegarder l'index pour référence
        (OUTPUT_DIR / "_repo_index.json").write_text(
            json.dumps({"files": list(repo_files.keys())}, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
    else:
        print("  ⚠️  Impossible d'accéder à l'API GitHub (rate limit ou réseau). Tentative directe...")

    # Mapping intelligent depuis l'index
    def find_url_in_repo(local_name: str) -> str | None:
        """Cherche l'URL correspondant à un type de données dans l'index du repo."""
        keyword = local_name.replace(".json", "").lower()
        for path, url in repo_files.items():
            if keyword in path.lower():
                return url
        return None

    results = {}
    print()

    for repo_path, local_name in FILES_TO_FETCH:
        print(f"📥 {local_name}...")

        # Chercher d'abord dans l'index du repo
        url_from_index = find_url_in_repo(local_name) if repo_files else None
        data = None

        if url_from_index:
            print(f"  Via index : {url_from_index}")
            data = fetch_json(url_from_index)
            used_url = url_from_index
        else:
            data, used_url = try_fetch_file(local_name, repo_path)

        if data is None:
            print(f"  ❌ {local_name} introuvable — fichier ignoré.\n")
            continue

        # Normalisation
        normalizer = NORMALIZERS.get(local_name)
        if normalizer:
            try:
                data = normalizer(data)
                print(f"  ✅ Normalisé : {len(data)} entrées")
            except Exception as e:
                print(f"  ⚠️  Normalisation échouée ({e}), données brutes sauvegardées")

        # Sauvegarde
        out_path = OUTPUT_DIR / local_name
        out_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  💾 Sauvegardé : {out_path}\n")
        results[local_name] = len(data) if isinstance(data, list) else 1

    # Rapport final
    print("═══════════════════════════════════════════")
    print("✅ Téléchargement terminé !\n")
    print("Fichiers téléchargés :")
    for fname, count in results.items():
        print(f"  • {fname} : {count} entrées")

    print(f"\n📁 Dossier : {OUTPUT_DIR}")
    print("\n💡 Lance maintenant dreamlight_checklist.py — les")
    print("   onglets Recettes et Quêtes chargeront ces données.")

    if not results:
        print("\n⚠️  AUCUN fichier téléchargé.")
        print("   Vérifie ta connexion internet, ou que le repo")
        print("   0xWDG/DreamlightValleyGuide-Data est bien public.")
        print("   Tu peux aussi cloner le repo manuellement et copier")
        print(f"   les JSON dans : {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
