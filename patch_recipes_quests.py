# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════════════════╗
║  PATCH — Onglets Recettes & Quêtes + Chargement données DVGuide        ║
║  À INTÉGRER dans dreamlight_checklist.py                                ║
║                                                                          ║
║  INSTRUCTIONS D'INTÉGRATION :                                            ║
║                                                                          ║
║  1. ÉTAPE DONNÉES : Lance download_dvguide_data.py une fois.             ║
║                                                                          ║
║  2. ÉTAPE CODE (3 endroits à modifier dans dreamlight_checklist.py) :   ║
║                                                                          ║
║     A) Juste après les imports (ligne ~30), ajouter :                    ║
║           ── BLOC A : Chargeur de données DVGuide ──                     ║
║                                                                          ║
║     B) Dans init_db(), ajouter les nouvelles tables SQL :                ║
║           ── BLOC B : Tables recipes_progress et quests_progress ──      ║
║                                                                          ║
║     C) Dans DDVState.load(), ajouter les deux nouvelles méthodes :       ║
║           ── BLOC C : _load_recipes_progress et _load_quests_progress ── ║
║                                                                          ║
║     D) Dans DDVApp._build_ui(), ajouter les deux onglets et appels :     ║
║           ── BLOC D : Déclaration + construction des onglets ──          ║
║                                                                          ║
║     E) Ajouter les méthodes _build_recipes_tab et _build_quests_tab :   ║
║           ── BLOC E : Corps des onglets ──                               ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

# ══════════════════════════════════════════════════════════════════════════════
# ── BLOC A : À coller juste après les imports (ligne ~30) ────────────────────
# ══════════════════════════════════════════════════════════════════════════════

DVGUIDE_DIR = Path.home() / ".ddv_checklist" / "dvguide_data"

def _load_dvguide_file(filename: str) -> list:
    """Charge un fichier JSON depuis le dossier dvguide_data. Retourne [] si absent."""
    fpath = DVGUIDE_DIR / filename
    if not fpath.exists():
        return []
    try:
        return json.loads(fpath.read_text(encoding="utf-8"))
    except Exception:
        return []

# Chargement global au démarrage (lecture unique)
DVGUIDE_RECIPES    = _load_dvguide_file("recipes.json")
DVGUIDE_QUESTS     = _load_dvguide_file("quests.json")
DVGUIDE_CHARACTERS = _load_dvguide_file("characters.json")
DVGUIDE_LOADED     = bool(DVGUIDE_RECIPES or DVGUIDE_QUESTS)


# ══════════════════════════════════════════════════════════════════════════════
# ── BLOC B : À ajouter dans init_db(), dans le conn.executescript(""" ...  ──
# ══════════════════════════════════════════════════════════════════════════════

EXTRA_SQL = """
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
"""
# → Coller ce SQL dans le conn.executescript(""" bloc de init_db()


# ══════════════════════════════════════════════════════════════════════════════
# ── BLOC C : Méthodes à ajouter dans la classe DDVState ──────────────────────
# ══════════════════════════════════════════════════════════════════════════════

def _load_recipes_progress(self):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT recipe_id, cooked, favorite FROM recipes_progress WHERE account_id=?",
            (self.account_id,)
        ).fetchall()
    self.recipes_progress = {r["recipe_id"]: {"cooked": bool(r["cooked"]), "favorite": bool(r["favorite"])} for r in rows}

def _save_recipes_progress(self, conn):
    for rid, data in self.recipes_progress.items():
        conn.execute(
            """INSERT INTO recipes_progress(account_id, recipe_id, cooked, favorite)
               VALUES(?,?,?,?)
               ON CONFLICT(account_id, recipe_id) DO UPDATE SET
               cooked=excluded.cooked, favorite=excluded.favorite""",
            (self.account_id, rid, int(data["cooked"]), int(data["favorite"]))
        )

def _load_quests_progress(self):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT quest_id, completed, in_progress, note FROM quests_progress WHERE account_id=?",
            (self.account_id,)
        ).fetchall()
    self.quests_progress = {
        r["quest_id"]: {
            "completed": bool(r["completed"]),
            "in_progress": bool(r["in_progress"]),
            "note": r["note"]
        } for r in rows
    }

def _save_quests_progress(self, conn):
    for qid, data in self.quests_progress.items():
        conn.execute(
            """INSERT INTO quests_progress(account_id, quest_id, completed, in_progress, note)
               VALUES(?,?,?,?,?)
               ON CONFLICT(account_id, quest_id) DO UPDATE SET
               completed=excluded.completed, in_progress=excluded.in_progress, note=excluded.note""",
            (self.account_id, qid, int(data["completed"]), int(data["in_progress"]), data["note"])
        )

# → Appeler ces méthodes dans DDVState.load() :
#       self._load_recipes_progress()
#       self._load_quests_progress()
#
# → Appeler les _save dans DDVState.save_all() :
#       self._save_recipes_progress(conn)
#       self._save_quests_progress(conn)


# ══════════════════════════════════════════════════════════════════════════════
# ── BLOC D : Dans DDVApp._build_ui(), ajouter après les tabs.add existants ──
# ══════════════════════════════════════════════════════════════════════════════

# self.tabs.add("🍳 Recettes")
# self.tabs.add("📜 Quêtes")
#
# self._build_recipes_tab()
# self._build_quests_tab()


# ══════════════════════════════════════════════════════════════════════════════
# ── BLOC E : Nouvelles méthodes de DDVApp (coller avant _build_settings_tab)
# ══════════════════════════════════════════════════════════════════════════════

def _build_recipes_tab(self):
    """Onglet Recettes — données issues du repo 0xWDG/DreamlightValleyGuide-Data."""
    tab = self.tabs.tab("🍳 Recettes")

    if not DVGUIDE_RECIPES:
        # Aucune donnée disponible → afficher les instructions
        frame = ctk.CTkFrame(tab, fg_color="transparent")
        frame.pack(expand=True)
        ctk.CTkLabel(frame, text="📥 Données non chargées",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(40, 10))
        msg = (
            "Pour activer cet onglet, lance le script de téléchargement :\n\n"
            "    python download_dvguide_data.py\n\n"
            "Ce script télécharge les données du repo GitHub\n"
            "0xWDG/DreamlightValleyGuide-Data et les sauvegarde\n"
            f"dans : {DVGUIDE_DIR}\n\n"
            "Redémarre l'application après le téléchargement."
        )
        ctk.CTkLabel(frame, text=msg, justify="center",
                     font=ctk.CTkFont(size=12), text_color="gray").pack(pady=4)
        ctk.CTkButton(
            frame, text="📂 Ouvrir le dossier de données",
            command=lambda: __import__("os").startfile(str(DVGUIDE_DIR))
            if __import__("sys").platform == "win32"
            else __import__("subprocess").Popen(["xdg-open", str(DVGUIDE_DIR)])
        ).pack(pady=12)
        return

    # ── Statistiques en en-tête ────────────────────────────────────────────
    stats_bar = ctk.CTkFrame(tab, fg_color="transparent")
    stats_bar.pack(fill="x", padx=8, pady=(6, 2))

    total_r = len(DVGUIDE_RECIPES)
    self._recipe_stat_label = ctk.CTkLabel(
        stats_bar, text="", font=ctk.CTkFont(size=12, weight="bold"))
    self._recipe_stat_label.pack(side="left")

    # ── Barre de recherche et filtres ─────────────────────────────────────
    ctrl = ctk.CTkFrame(tab, fg_color="transparent")
    ctrl.pack(fill="x", padx=8, pady=4)

    self._recipe_search_var = ctk.StringVar()
    search_entry = ctk.CTkEntry(ctrl, textvariable=self._recipe_search_var,
                                 placeholder_text="🔍 Rechercher une recette...", width=240)
    search_entry.pack(side="left", padx=4)

    # Catégories disponibles
    categories = sorted({r.get("category", "Autre") for r in DVGUIDE_RECIPES if r.get("category")})
    categories = ["Toutes"] + categories

    self._recipe_cat_var = ctk.StringVar(value="Toutes")
    ctk.CTkComboBox(ctrl, variable=self._recipe_cat_var, values=categories, width=160,
                    command=lambda _: self._refresh_recipes_list()).pack(side="left", padx=4)

    self._recipe_filter_var = ctk.StringVar(value="Toutes")
    ctk.CTkComboBox(ctrl, variable=self._recipe_filter_var,
                    values=["Toutes", "✅ Cuisinées", "⬜ Non cuisinées", "❤️ Favoris"],
                    width=150, command=lambda _: self._refresh_recipes_list()).pack(side="left", padx=4)

    ctk.CTkButton(ctrl, text="🔄 Rafraîchir", width=90,
                  command=self._refresh_recipes_list).pack(side="right", padx=4)

    self._recipe_search_var.trace_add("write", lambda *_: self._refresh_recipes_list())

    # ── Liste scrollable ──────────────────────────────────────────────────
    self._recipes_scroll = ctk.CTkScrollableFrame(tab, corner_radius=6)
    self._recipes_scroll.pack(fill="both", expand=True, padx=8, pady=4)

    self._refresh_recipes_list()


def _refresh_recipes_list(self):
    """Recharge la liste des recettes selon les filtres actifs."""
    for w in self._recipes_scroll.winfo_children():
        w.destroy()

    search  = self._recipe_search_var.get().lower().strip()
    cat_f   = self._recipe_cat_var.get()
    status_f = self._recipe_filter_var.get()

    cooked_count = 0
    fav_count = 0
    shown = 0

    for recipe in DVGUIDE_RECIPES:
        rid  = recipe.get("id") or recipe.get("name", "")
        name = recipe.get("name", "?")
        cat  = recipe.get("category", "Autre")
        ingr = recipe.get("ingredients", [])
        energy = recipe.get("energy", 0)

        prog = self.gs.recipes_progress.get(rid, {"cooked": False, "favorite": False})
        is_cooked = prog["cooked"]
        is_fav = prog["favorite"]

        if is_cooked:
            cooked_count += 1
        if is_fav:
            fav_count += 1

        # Filtres
        if search and search not in name.lower():
            continue
        if cat_f != "Toutes" and cat != cat_f:
            continue
        if status_f == "✅ Cuisinées" and not is_cooked:
            continue
        if status_f == "⬜ Non cuisinées" and is_cooked:
            continue
        if status_f == "❤️ Favoris" and not is_fav:
            continue

        shown += 1
        self._recipe_row(self._recipes_scroll, recipe, rid, is_cooked, is_fav)

    # Update stats
    total_r = len(DVGUIDE_RECIPES)
    pct = int(cooked_count / total_r * 100) if total_r else 0
    self._recipe_stat_label.configure(
        text=f"🍳 {cooked_count}/{total_r} cuisinées ({pct}%)  |  ❤️ {fav_count} favoris  |  Affichées : {shown}"
    )


def _recipe_row(self, parent, recipe: dict, rid: str, is_cooked: bool, is_fav: bool):
    """Affiche une ligne pour une recette."""
    row = ctk.CTkFrame(parent, corner_radius=6,
                       fg_color="#1e3a1e" if is_cooked else ("gray20" if ctk.get_appearance_mode() == "Dark" else "gray90"))
    row.pack(fill="x", padx=4, pady=2)

    # Checkbox cuit
    cooked_var = ctk.BooleanVar(value=is_cooked)
    def on_cooked_toggle(r=rid, v=cooked_var):
        if r not in self.gs.recipes_progress:
            self.gs.recipes_progress[r] = {"cooked": False, "favorite": False}
        self.gs.recipes_progress[r]["cooked"] = v.get()
        self.gs.save_all()
        self._refresh_recipes_list()

    cb = ctk.CTkCheckBox(row, text="", variable=cooked_var, command=on_cooked_toggle, width=24)
    cb.pack(side="left", padx=(8, 4))

    # Nom + catégorie
    name = recipe.get("name", "?")
    cat  = recipe.get("category", "")
    cat_colors = {
        "Dessert": "#f0a500", "Poisson": "#4aa8d8", "Légume": "#4caf50",
        "Viande": "#e74c3c", "Soupe": "#9b59b6", "Plat principal": "#e67e22",
    }
    cat_col = cat_colors.get(cat, "#7eb8f7")

    left = ctk.CTkFrame(row, fg_color="transparent")
    left.pack(side="left", fill="x", expand=True, padx=4)

    name_font = ctk.CTkFont(size=12, overstrike=is_cooked)
    ctk.CTkLabel(left, text=name, font=name_font, anchor="w").pack(anchor="w")

    # Ingrédients
    ingr = recipe.get("ingredients", [])
    if ingr:
        if isinstance(ingr[0], dict):
            ingr_str = ", ".join(i.get("name", str(i)) for i in ingr)
        else:
            ingr_str = ", ".join(str(i) for i in ingr)
        ctk.CTkLabel(left, text=f"🧂 {ingr_str}", font=ctk.CTkFont(size=10),
                     text_color="gray", anchor="w").pack(anchor="w")

    # Énergie + catégorie
    right_info = ctk.CTkFrame(row, fg_color="transparent")
    right_info.pack(side="right", padx=8)

    if energy := recipe.get("energy", 0):
        ctk.CTkLabel(right_info, text=f"⚡{energy}", font=ctk.CTkFont(size=10),
                     text_color="#f0a500").pack(side="left", padx=4)

    ctk.CTkLabel(right_info, text=cat, font=ctk.CTkFont(size=10),
                 text_color=cat_col).pack(side="left", padx=4)

    # Favori
    fav_var = ctk.BooleanVar(value=is_fav)
    def on_fav_toggle(r=rid, v=fav_var):
        if r not in self.gs.recipes_progress:
            self.gs.recipes_progress[r] = {"cooked": False, "favorite": False}
        self.gs.recipes_progress[r]["favorite"] = v.get()
        self.gs.save_all()
        self._refresh_recipes_list()

    ctk.CTkCheckBox(right_info, text="❤️", variable=fav_var,
                    command=on_fav_toggle, width=40,
                    checkbox_width=16, checkbox_height=16).pack(side="left", padx=2)


def _build_quests_tab(self):
    """Onglet Quêtes — données issues du repo 0xWDG/DreamlightValleyGuide-Data."""
    tab = self.tabs.tab("📜 Quêtes")

    if not DVGUIDE_QUESTS:
        frame = ctk.CTkFrame(tab, fg_color="transparent")
        frame.pack(expand=True)
        ctk.CTkLabel(frame, text="📥 Données non chargées",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(40, 10))
        msg = (
            "Pour activer cet onglet, lance le script de téléchargement :\n\n"
            "    python download_dvguide_data.py\n\n"
            "Redémarre l'application après le téléchargement."
        )
        ctk.CTkLabel(frame, text=msg, justify="center",
                     font=ctk.CTkFont(size=12), text_color="gray").pack(pady=4)
        return

    # ── Stats en-tête ─────────────────────────────────────────────────────
    stats_bar = ctk.CTkFrame(tab, fg_color="transparent")
    stats_bar.pack(fill="x", padx=8, pady=(6, 2))
    self._quest_stat_label = ctk.CTkLabel(
        stats_bar, text="", font=ctk.CTkFont(size=12, weight="bold"))
    self._quest_stat_label.pack(side="left")

    # ── Filtres ───────────────────────────────────────────────────────────
    ctrl = ctk.CTkFrame(tab, fg_color="transparent")
    ctrl.pack(fill="x", padx=8, pady=4)

    self._quest_search_var = ctk.StringVar()
    ctk.CTkEntry(ctrl, textvariable=self._quest_search_var,
                 placeholder_text="🔍 Rechercher une quête ou un personnage...",
                 width=260).pack(side="left", padx=4)
    self._quest_search_var.trace_add("write", lambda *_: self._refresh_quests_list())

    # Personnages disponibles dans les quêtes
    chars = sorted({q.get("character", "") for q in DVGUIDE_QUESTS if q.get("character")})
    chars = ["Tous"] + chars

    self._quest_char_var = ctk.StringVar(value="Tous")
    ctk.CTkComboBox(ctrl, variable=self._quest_char_var, values=chars, width=160,
                    command=lambda _: self._refresh_quests_list()).pack(side="left", padx=4)

    self._quest_status_var = ctk.StringVar(value="Toutes")
    ctk.CTkComboBox(ctrl, variable=self._quest_status_var,
                    values=["Toutes", "✅ Terminées", "🔄 En cours", "⬜ Non commencées"],
                    width=160, command=lambda _: self._refresh_quests_list()).pack(side="left", padx=4)

    # Groupement par personnage ou liste
    self._quest_group_var = ctk.BooleanVar(value=True)
    ctk.CTkCheckBox(ctrl, text="Grouper par personnage", variable=self._quest_group_var,
                    command=self._refresh_quests_list).pack(side="right", padx=8)

    # ── Liste scrollable ──────────────────────────────────────────────────
    self._quests_scroll = ctk.CTkScrollableFrame(tab, corner_radius=6)
    self._quests_scroll.pack(fill="both", expand=True, padx=8, pady=4)

    self._refresh_quests_list()


def _refresh_quests_list(self):
    """Recharge la liste des quêtes."""
    for w in self._quests_scroll.winfo_children():
        w.destroy()

    search    = self._quest_search_var.get().lower().strip()
    char_f    = self._quest_char_var.get()
    status_f  = self._quest_status_var.get()
    group_by  = self._quest_group_var.get()

    done_count = 0
    inprog_count = 0
    total_q = 0

    # Filtrer les quêtes
    filtered = []
    for quest in DVGUIDE_QUESTS:
        qid  = quest.get("id") or quest.get("name", "")
        name = quest.get("name", "?")
        char = quest.get("character", "")

        prog = self.gs.quests_progress.get(qid, {"completed": False, "in_progress": False, "note": ""})
        is_done = prog["completed"]
        is_prog = prog["in_progress"] and not is_done

        total_q += 1
        if is_done:
            done_count += 1
        elif is_prog:
            inprog_count += 1

        # Filtres
        if search and search not in name.lower() and search not in char.lower():
            continue
        if char_f != "Tous" and char != char_f:
            continue
        if status_f == "✅ Terminées" and not is_done:
            continue
        if status_f == "🔄 En cours" and not is_prog:
            continue
        if status_f == "⬜ Non commencées" and (is_done or is_prog):
            continue

        filtered.append((quest, qid, is_done, is_prog))

    # Mise à jour stats
    pct = int(done_count / total_q * 100) if total_q else 0
    self._quest_stat_label.configure(
        text=f"📜 {done_count}/{total_q} terminées ({pct}%)  |  🔄 {inprog_count} en cours  |  Affichées : {len(filtered)}"
    )

    if not filtered:
        ctk.CTkLabel(self._quests_scroll, text="Aucune quête correspondante.",
                     text_color="gray").pack(pady=20)
        return

    if group_by:
        # Grouper par personnage
        groups: dict[str, list] = {}
        for quest, qid, is_done, is_prog in filtered:
            char = quest.get("character", "Sans personnage") or "Sans personnage"
            groups.setdefault(char, []).append((quest, qid, is_done, is_prog))

        for char_name, quests_list in sorted(groups.items()):
            char_done = sum(1 for _, _, d, _ in quests_list if d)
            # En-tête personnage
            char_hdr = ctk.CTkFrame(self._quests_scroll, corner_radius=6,
                                    fg_color="#1a2a3a")
            char_hdr.pack(fill="x", padx=4, pady=(6, 2))
            ctk.CTkLabel(char_hdr,
                         text=f"👤 {char_name}   {char_done}/{len(quests_list)} ✅",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color="#7eb8f7").pack(anchor="w", padx=10, pady=4)

            for quest, qid, is_done, is_prog in quests_list:
                self._quest_row(self._quests_scroll, quest, qid, is_done, is_prog)
    else:
        for quest, qid, is_done, is_prog in filtered:
            self._quest_row(self._quests_scroll, quest, qid, is_done, is_prog)


def _quest_row(self, parent, quest: dict, qid: str, is_done: bool, is_prog: bool):
    """Affiche une ligne pour une quête avec ses étapes dépliables."""
    name = quest.get("name", "?")
    char = quest.get("character", "")
    desc = quest.get("description", "")
    steps = quest.get("steps", [])
    fship = quest.get("friendship_level", 0)

    # Couleur selon statut
    if is_done:
        bg = "#1e3a1e"
    elif is_prog:
        bg = "#2a2a1a"
    else:
        bg = "gray20" if ctk.get_appearance_mode() == "Dark" else "gray90"

    row = ctk.CTkFrame(parent, corner_radius=6, fg_color=bg)
    row.pack(fill="x", padx=4, pady=2)

    top = ctk.CTkFrame(row, fg_color="transparent")
    top.pack(fill="x", padx=6, pady=4)

    # Checkbox terminée
    done_var = ctk.BooleanVar(value=is_done)
    def on_done(r=qid, v=done_var):
        if r not in self.gs.quests_progress:
            self.gs.quests_progress[r] = {"completed": False, "in_progress": False, "note": ""}
        self.gs.quests_progress[r]["completed"] = v.get()
        if v.get():
            self.gs.quests_progress[r]["in_progress"] = False
        self.gs.save_all()
        self._refresh_quests_list()

    ctk.CTkCheckBox(top, text="", variable=done_var, command=on_done, width=24).pack(side="left")

    # Checkbox en cours
    prog_var = ctk.BooleanVar(value=is_prog)
    def on_prog(r=qid, v=prog_var):
        if r not in self.gs.quests_progress:
            self.gs.quests_progress[r] = {"completed": False, "in_progress": False, "note": ""}
        self.gs.quests_progress[r]["in_progress"] = v.get()
        self.gs.save_all()
        self._refresh_quests_list()

    ctk.CTkCheckBox(top, text="🔄", variable=prog_var, command=on_prog, width=40,
                    checkbox_width=16, checkbox_height=16,
                    text_color="#f0a500").pack(side="left", padx=(2, 8))

    # Nom
    name_col = "#4caf50" if is_done else ("#f0a500" if is_prog else None)
    name_font = ctk.CTkFont(size=11, weight="bold", overstrike=is_done)
    ctk.CTkLabel(top, text=name, font=name_font, anchor="w",
                 text_color=name_col or ("white" if ctk.get_appearance_mode() == "Dark" else "black")
                 ).pack(side="left", fill="x", expand=True)

    # Niveau amitié requis
    if fship:
        ctk.CTkLabel(top, text=f"💜 Niv.{fship}", font=ctk.CTkFont(size=10),
                     text_color="#9b59b6").pack(side="right", padx=6)

    # Description (si présente)
    if desc:
        ctk.CTkLabel(row, text=desc, font=ctk.CTkFont(size=10),
                     text_color="gray", anchor="w", wraplength=700).pack(anchor="w", padx=32, pady=(0, 2))

    # Étapes (si présentes) — bouton dépliable
    if steps:
        steps_frame = ctk.CTkFrame(row, fg_color="transparent")
        expanded = {"open": False}

        def toggle_steps(sf=steps_frame, exp=expanded):
            exp["open"] = not exp["open"]
            if exp["open"]:
                for w in sf.winfo_children():
                    w.destroy()
                for i, step in enumerate(steps, 1):
                    step_text = step if isinstance(step, str) else step.get("name", step.get("description", str(step)))
                    ctk.CTkLabel(sf, text=f"  {i}. {step_text}",
                                 font=ctk.CTkFont(size=10), text_color="gray",
                                 anchor="w", wraplength=680).pack(anchor="w", padx=36)
                sf.pack(fill="x")
            else:
                sf.pack_forget()

        ctk.CTkButton(top, text=f"📋 {len(steps)} étapes", width=90,
                      font=ctk.CTkFont(size=10), height=22,
                      command=toggle_steps).pack(side="right", padx=4)
