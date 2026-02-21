# -*- coding: utf-8 -*-
"""
DDV Checklist — Bot Discord
════════════════════════════
Partage la même base SQLite que l'application desktop.

Installation :
    pip install discord.py

Configuration :
    1. Va sur https://discord.com/developers/applications
    2. Crée une application → onglet "Bot" → "Reset Token" → copie le token
    3. Dans "OAuth2 > URL Generator" : coche "bot" + "applications.commands"
    4. Colle ton token dans BOT_TOKEN ci-dessous
    5. Lance : python bot_discord.py

Commandes disponibles :
    /daily          Affiche les tâches du jour avec boutons ✅
    /streak         Affiche le streak actuel et le record
    /trophee        Infos et progression d'un trophée
    /stats          Résumé global de la progression
    /rappel         Active/désactive les rappels quotidiens à 22h
    /bestioles      Active/désactive les notifications bestioles rares
    /bestioles_now  Affiche les bestioles rares actives maintenant
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
import sqlite3
from datetime import date, timedelta, datetime
from pathlib import Path

# ══════════════════════════════════════════════════════════════════════════════
#  CONFIGURATION  ← MODIFIE ICI
# ══════════════════════════════════════════════════════════════════════════════

BOT_TOKEN    = "BOT_TOKEN"
GUILD_ID     = None       # ID de ton serveur pour sync instantanée (optionnel)
RAPPEL_HEURE  = 22        # heure du rappel quotidien tâches
RAPPEL_MINUTE = 0

CONFIG_DIR = Path.home() / ".ddv_checklist"
DB_PATH    = CONFIG_DIR / "ddv.db"

# ══════════════════════════════════════════════════════════════════════════════
#  DONNÉES BESTIOLES (identiques à l'app desktop)
# ══════════════════════════════════════════════════════════════════════════════

CRITTERS = [
    {"species":"Écureuil","biome":"Plaza","icon":"🐿️",
     "food_love":"Cacahuètes (achat chez Remy niv.4)",
     "food_like":["Noix","Noisettes","Fruits secs"],
     "approach":"Marche vers eux directement, ils viennent d'eux-mêmes quand ils ont faim.",
     "variants":[
        {"color":"Gris",    "days":[0,1,2,3,4,5,6],"hours":(8,20),"rare":False},
        {"color":"Marron",  "days":[0,1,2,3,4,5,6],"hours":(8,20),"rare":False},
        {"color":"Blanc",   "days":[0,2,4],         "hours":(8,20),"rare":False},
        {"color":"Roux",    "days":[1,3,5],         "hours":(8,20),"rare":False},
        {"color":"Noir ⭐", "days":[6],             "hours":(8,20),"rare":True},
    ]},
    {"species":"Lapin","biome":"Clairière Paisible","icon":"🐰",
     "food_love":"Carottes (Goofy's Stall ou culture)",
     "food_like":["Carotte au miel","Salade de carottes","Légumes du jardin"],
     "approach":"Le poursuivre 2-3 fois jusqu'à ce qu'il s'arrête.",
     "variants":[
        {"color":"Gris",      "days":[0,1,2,3,4,5,6],"hours":(8,20),"rare":False},
        {"color":"Blanc",     "days":[0,1,2,3,4,5,6],"hours":(8,20),"rare":False},
        {"color":"Marron",    "days":[0,2,4,6],       "hours":(8,20),"rare":False},
        {"color":"Noir",      "days":[1,3,5],         "hours":(8,20),"rare":False},
        {"color":"Calico ⭐", "days":[6],             "hours":(8,14),"rare":True},
    ]},
    {"species":"Tortue de mer","biome":"Plage Ensoleillée","icon":"🐢",
     "food_love":"Algues (pêche sans bulles, tous biomes)",
     "food_like":["Salade d'algues","Soupe aux algues","Poisson cuit"],
     "approach":"S'approcher lentement, s'arrêter quand elle rentre dans sa carapace, attendre.",
     "variants":[
        {"color":"Verte",      "days":[0,1,2,3,4,5,6],"hours":(8,20),"rare":False},
        {"color":"Bleue",      "days":[0,2,4,6],       "hours":(8,20),"rare":False},
        {"color":"Rose",       "days":[1,3,5],         "hours":(8,20),"rare":False},
        {"color":"Violette ⭐","days":[0,6],           "hours":(20,6),"rare":True},
        {"color":"Rouge ⭐",   "days":[3],             "hours":(8,14),"rare":True},
    ]},
    {"species":"Raton laveur","biome":"Forêt des Rêves","icon":"🦝",
     "food_love":"Myrtilles (buissons Forêt des Rêves ou Goofy's Stall)",
     "food_like":["Tarte aux myrtilles","Muffin aux myrtilles","Fruits de la forêt"],
     "approach":"Avancer très lentement quand sa tête est baissée, s'arrêter dès qu'il regarde.",
     "variants":[
        {"color":"Gris",    "days":[0,1,2,3,4,5,6],"hours":(20,6),"rare":False},
        {"color":"Marron",  "days":[0,2,4,6],       "hours":(20,6),"rare":False},
        {"color":"Roux",    "days":[1,3,5],         "hours":(20,6),"rare":False},
        {"color":"Noir",    "days":[0,6],           "hours":(20,2),"rare":False},
        {"color":"Bleu ⭐", "days":[2],             "hours":(16,22),"rare":True},
    ]},
    {"species":"Crocodile","biome":"Clairière de Confiance","icon":"🐊",
     "food_love":"Homard (pêche bulles Plage Ensoleillée)",
     "food_like":["Bisque de homard","Homard grillé","Soupe de fruits de mer"],
     "approach":"Avancer quand la tête est baissée, s'arrêter sinon. Très patient !",
     "variants":[
        {"color":"Vert",       "days":[0,1,2,3,4,5,6],"hours":(8,20),"rare":False},
        {"color":"Gris",       "days":[0,2,4,6],       "hours":(8,20),"rare":False},
        {"color":"Bleu",       "days":[1,3,5],         "hours":(8,20),"rare":False},
        {"color":"Rouge",      "days":[0,6],           "hours":(8,14),"rare":False},
        {"color":"Violet",     "days":[2],             "hours":(8,14),"rare":False},
        {"color":"Doré ⭐",    "days":[6],             "hours":(8,14),"rare":True},
    ]},
    {"species":"Oiseau Soleil","biome":"Plateau Ensoleillé","icon":"🦜",
     "food_love":"Fleur assortie à la couleur de la variante",
     "food_like":["Toute fleur de la bonne couleur"],
     "approach":"Les suivre dans la zone, ils s'arrêtent près des plantes.",
     "variants":[
        {"color":"Émeraude",   "days":[0,1,2,3,4,5,6],"hours":(8,20),"rare":False},
        {"color":"Doré",       "days":[0,2,4,6],       "hours":(8,20),"rare":False},
        {"color":"Bleu",       "days":[1,3,5],         "hours":(8,20),"rare":False},
        {"color":"Rouge",      "days":[0,3,6],         "hours":(8,20),"rare":False},
        {"color":"Violet ⭐",  "days":[6],             "hours":(8,14),"rare":True},
    ]},
    {"species":"Renard","biome":"Sommets Enneigés","icon":"🦊",
     "food_love":"Esturgeon blanc (pêche eau libre, Sommets Enneigés)",
     "food_like":["Poisson grillé","Soupe de poisson","Esturgeon cuit"],
     "approach":"Le poursuivre jusqu'à ce qu'il s'arrête et t'invite à le nourrir.",
     "variants":[
        {"color":"Roux",           "days":[0,1,2,3,4,5,6],"hours":(8,20),"rare":False},
        {"color":"Blanc",          "days":[0,2,4,6],       "hours":(8,20),"rare":False},
        {"color":"Gris",           "days":[1,3,5],         "hours":(8,20),"rare":False},
        {"color":"Noir",           "days":[0,6],           "hours":(8,20),"rare":False},
        {"color":"Arc-en-ciel ⭐", "days":[6],             "hours":(8,14),"rare":True},
    ]},
    {"species":"Corbeau","biome":"Terres Oubliées","icon":"🐦",
     "food_love":"N'importe quel repas 5 étoiles (cuisiné)",
     "food_like":["Repas 4 étoiles","Plats élaborés 3+ ingrédients"],
     "approach":"S'approcher lentement, attendre qu'il vole en cercle au-dessus avant de descendre.",
     "variants":[
        {"color":"Noir",       "days":[0,1,2,3,4,5,6],"hours":(20,6),"rare":False},
        {"color":"Blanc",      "days":[0,2,4,6],       "hours":(20,6),"rare":False},
        {"color":"Bleu",       "days":[1,3,5],         "hours":(20,6),"rare":False},
        {"color":"Violet",     "days":[0,6],           "hours":(20,2),"rare":False},
        {"color":"Doré ⭐",    "days":[6],             "hours":(20,2),"rare":True},
    ]},
]

JOURS = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]


def is_critter_active(variant: dict, now: datetime = None) -> bool:
    if now is None:
        now = datetime.now()
    day  = now.weekday()
    hour = now.hour
    if day not in variant["days"]:
        return False
    h_start, h_end = variant["hours"]
    if h_start < h_end:
        return h_start <= hour < h_end
    return hour >= h_start or hour < h_end


def get_active_rare_critters(now: datetime = None) -> list[dict]:
    """Retourne la liste des bestioles rares actives à l'instant donné."""
    if now is None:
        now = datetime.now()
    result = []
    for sp in CRITTERS:
        for v in sp["variants"]:
            if v.get("rare") and is_critter_active(v, now):
                result.append({
                    "species":   sp["species"],
                    "icon":      sp["icon"],
                    "biome":     sp["biome"],
                    "color":     v["color"],
                    "hours":     v["hours"],
                    "days":      v["days"],
                    "food_love": sp["food_love"],
                    "food_like": sp["food_like"],
                    "approach":  sp.get("approach",""),
                })
    return result


def make_critter_embed(critter: dict, now: datetime) -> discord.Embed:
    """Crée un embed Discord pour une bestiole rare."""
    h_start, h_end = critter["hours"]
    hours_str = f"{h_start:02d}h00 → {h_end:02d}h00"
    days_str  = " · ".join(JOURS[d] for d in critter["days"])
    food_like = "\n".join(f"  • {f}" for f in critter["food_like"])

    embed = discord.Embed(
        title=f"{critter['icon']} Bestiole rare disponible !",
        description=(
            f"**Hey ! Une bestiole rare est disponible** 🌟\n\n"
            f"Il s'agit du **{critter['species']} {critter['color']}**"
        ),
        color=0xf0a500
    )
    embed.add_field(
        name="📍 Biome",
        value=critter["biome"],
        inline=True
    )
    embed.add_field(
        name="⏰ Disponible",
        value=f"{hours_str}\n{days_str}",
        inline=True
    )
    embed.add_field(
        name="❤️ Plat préféré",
        value=critter["food_love"],
        inline=False
    )
    embed.add_field(
        name="💛 Ce qu'elle aime aussi",
        value=food_like if food_like else "—",
        inline=False
    )
    if critter.get("approach"):
        embed.add_field(
            name="🦶 Astuce d'approche",
            value=f"*{critter['approach']}*",
            inline=False
        )

    # Temps restant avant la fin de la fenêtre
    h_end_val = h_end if h_end > now.hour else h_end + 24
    minutes_left = (h_end_val - now.hour) * 60 - now.minute
    embed.set_footer(text=f"⏳ Disponible encore ~{minutes_left} minutes · {now.strftime('%H:%M')}")
    return embed


# ══════════════════════════════════════════════════════════════════════════════
#  ACCÈS BASE DE DONNÉES
# ══════════════════════════════════════════════════════════════════════════════

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_account_id(account: str = "default") -> int:
    with get_db() as conn:
        row = conn.execute("SELECT id FROM accounts WHERE name=?", (account,)).fetchone()
    return row["id"] if row else 1


def get_streak(account_id: int) -> dict:
    with get_db() as conn:
        row = conn.execute(
            "SELECT count, last_complete_date, best FROM streak WHERE account_id=?",
            (account_id,)
        ).fetchone()
    return dict(row) if row else {"count": 0, "last_complete_date": "", "best": 0}


def get_daily_tasks(account_id: int) -> list[dict]:
    today = date.today().isoformat()
    with get_db() as conn:
        meta_rows = conn.execute(
            "SELECT task_idx, name, category, priority FROM tasks_meta WHERE account_id=? ORDER BY task_idx",
            (account_id,)
        ).fetchall()
        checked_rows = conn.execute(
            "SELECT task_idx, checked FROM daily_tasks WHERE account_id=? AND task_date=?",
            (account_id, today)
        ).fetchall()
    checked_map = {r["task_idx"]: bool(r["checked"]) for r in checked_rows}
    return [{"idx": r["task_idx"], "name": r["name"], "category": r["category"],
             "priority": r["priority"], "checked": checked_map.get(r["task_idx"], False)}
            for r in meta_rows]


def check_task_in_db(account_id: int, task_idx: int, checked: bool):
    today = date.today().isoformat()
    with get_db() as conn:
        conn.execute(
            """INSERT INTO daily_tasks(account_id, task_date, task_idx, checked) VALUES(?,?,?,?)
               ON CONFLICT(account_id, task_date, task_idx) DO UPDATE SET checked=excluded.checked""",
            (account_id, today, task_idx, int(checked))
        )


def get_trophies(account_id: int) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT trophy_id, unlocked, progress FROM trophies WHERE account_id=?",
            (account_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_history(account_id: int, days: int = 7) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            """SELECT task_date, done, total FROM history
               WHERE account_id=? ORDER BY task_date DESC LIMIT ?""",
            (account_id, days)
        ).fetchall()
    return [dict(r) for r in rows]


def get_accounts() -> list[str]:
    with get_db() as conn:
        rows = conn.execute("SELECT name FROM accounts ORDER BY name").fetchall()
    return [r["name"] for r in rows]


# ══════════════════════════════════════════════════════════════════════════════
#  DONNÉES TROPHÉES
# ══════════════════════════════════════════════════════════════════════════════

TROPHIES_DATA = [
    {"id":"plat_01","name":"Maître de Dreamlight",     "type":"platinum","max_value":None},
    {"id":"gold_01","name":"Fléau des épines",          "type":"gold",    "max_value":3000},
    {"id":"gold_02","name":"Virtuose de la pêche",      "type":"gold",    "max_value":1800},
    {"id":"gold_03","name":"Géologue",                  "type":"gold",    "max_value":1800},
    {"id":"gold_04","name":"Chef hors pair",             "type":"gold",    "max_value":900},
    {"id":"gold_05","name":"Main verte",                 "type":"gold",    "max_value":4500},
    {"id":"gold_06","name":"Camarade suprême",           "type":"gold",    "max_value":15},
    {"id":"gold_07","name":"Exemple de générosité",      "type":"gold",    "max_value":540},
    {"id":"gold_08","name":"Économe",                    "type":"gold",    "max_value":1800000},
    {"id":"gold_09","name":"Toujours en mission",        "type":"gold",    "max_value":1100},
    {"id":"silver_01","name":"Moulin à paroles",         "type":"silver",  "max_value":1000},
    {"id":"silver_02","name":"Actionnaire de Dingo",     "type":"silver",  "max_value":None},
    {"id":"silver_03","name":"Spécialiste en rénovation","type":"silver",  "max_value":30},
    {"id":"silver_04","name":"As de la construction",    "type":"silver",  "max_value":None},
    {"id":"bronze_01","name":"Providence de la vallée",  "type":"bronze",  "max_value":None},
    {"id":"bronze_02","name":"Photographe",              "type":"bronze",  "max_value":50},
]
TROPHY_MAP = {t["name"].lower(): t for t in TROPHIES_DATA}
TROPHY_MAP.update({t["id"]: t for t in TROPHIES_DATA})

PRIORITY_ICONS = {"high": "🔴", "medium": "🟡", "low": "🟢"}
TYPE_ICONS     = {"platinum": "🏆", "gold": "🥇", "silver": "🥈", "bronze": "🥉"}

# ══════════════════════════════════════════════════════════════════════════════
#  BOT SETUP
# ══════════════════════════════════════════════════════════════════════════════

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# guild_id → channel_id pour les rappels tâches
rappel_channels: dict[int, int] = {}

# guild_id → channel_id pour les notifications bestioles
critter_channels: dict[int, int] = {}

# Suivi des bestioles déjà notifiées ce cycle (évite le spam)
# clé : "species_color_YYYY-MM-DD_HH" → déjà envoyée
notified_critters: set[str] = set()


@bot.event
async def on_ready():
    print(f"✅ Bot connecté : {bot.user} ({bot.user.id})")
    if GUILD_ID:
        guild = discord.Object(id=GUILD_ID)
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
        print(f"   Slash commands sync sur le serveur {GUILD_ID}")
    else:
        await tree.sync()
        print("   Slash commands sync globalement (peut prendre ~1h)")
    daily_reminder.start()
    critter_watcher.start()
    print("   ✅ Watcher bestioles rares démarré")


# ══════════════════════════════════════════════════════════════════════════════
#  COMMANDES SLASH
# ══════════════════════════════════════════════════════════════════════════════

@tree.command(name="daily", description="📋 Affiche tes tâches du jour")
@app_commands.describe(compte="Nom du compte DDV (défaut: default)")
async def cmd_daily(interaction: discord.Interaction, compte: str = "default"):
    await interaction.response.defer()
    acc_id = get_account_id(compte)
    tasks  = get_daily_tasks(acc_id)
    if not tasks:
        await interaction.followup.send("❌ Aucune tâche trouvée. Lance d'abord l'application desktop.")
        return
    done  = sum(1 for t in tasks if t["checked"])
    total = len(tasks)
    pct   = int(done/total*100) if total else 0
    bar   = "█"*(pct//10) + "░"*(10-pct//10)
    embed = discord.Embed(
        title=f"📋 Tâches du jour — {date.today().isoformat()}",
        description=f"**{bar}** {done}/{total} ({pct}%)",
        color=0x4caf50 if pct == 100 else 0xf0a500 if pct >= 50 else 0xe74c3c
    )
    embed.set_footer(text=f"Compte : {compte}")
    cats: dict[str, list] = {}
    for t in tasks:
        cats.setdefault(t["category"], []).append(t)
    for cat, cat_tasks in cats.items():
        lines = [f"{'✅' if t['checked'] else '⬜'} {PRIORITY_ICONS.get(t['priority'],'⚪')} {t['name']}"
                 for t in cat_tasks]
        embed.add_field(name=cat, value="\n".join(lines), inline=False)
    view = TaskView(tasks, acc_id, compte)
    await interaction.followup.send(embed=embed, view=view)


@tree.command(name="streak", description="🔥 Affiche ton streak actuel")
@app_commands.describe(compte="Nom du compte DDV (défaut: default)")
async def cmd_streak(interaction: discord.Interaction, compte: str = "default"):
    acc_id = get_account_id(compte)
    streak = get_streak(acc_id)
    count  = streak.get("count", 0)
    best   = streak.get("best", 0)
    last   = streak.get("last_complete_date", "jamais")
    emoji  = "🔥" if count >= 7 else "⭐" if count > 0 else "💤"
    color  = 0xf0a500 if count >= 7 else 0x7eb8f7 if count > 0 else 0x888888
    embed  = discord.Embed(title=f"{emoji} Streak — {compte}", color=color)
    embed.add_field(name="Streak actuel",            value=f"**{count}** jours", inline=True)
    embed.add_field(name="Record",                   value=f"**{best}** jours",  inline=True)
    embed.add_field(name="Dernière journée complète",value=last,                 inline=False)
    await interaction.response.send_message(embed=embed)


@tree.command(name="trophee", description="🏆 Infos et progression d'un trophée")
@app_commands.describe(nom="Nom ou ID du trophée", compte="Nom du compte DDV")
async def cmd_trophee(interaction: discord.Interaction, nom: str, compte: str = "default"):
    nom_lower = nom.lower().strip()
    trophy = TROPHY_MAP.get(nom_lower)
    if not trophy:
        matches = [t for t in TROPHIES_DATA if nom_lower in t["name"].lower()]
        if not matches:
            await interaction.response.send_message(
                f"❌ Trophée '{nom}' non trouvé.\nExemples : " +
                ", ".join(t["name"] for t in TROPHIES_DATA[:4]) + "...", ephemeral=True)
            return
        trophy = matches[0]
    acc_id = get_account_id(compte)
    saved  = {r["trophy_id"]: r for r in
              get_db().execute("SELECT * FROM trophies WHERE account_id=?", (acc_id,)).fetchall()}
    td     = saved.get(trophy["id"], {"unlocked": 0, "progress": 0, "note": ""})
    icon   = TYPE_ICONS.get(trophy["type"], "🏅")
    embed  = discord.Embed(
        title=f"{icon} {trophy['name']}",
        description=f"Type : **{trophy['type'].title()}**",
        color=0x4caf50 if td["unlocked"] else 0xf0a500
    )
    if trophy["max_value"]:
        progress = td.get("progress", 0)
        pct  = int(progress / trophy["max_value"] * 100)
        bar  = "█"*(pct//10) + "░"*(10-pct//10)
        embed.add_field(name="Progression",
                        value=f"{bar}\n{progress:,}/{trophy['max_value']:,} ({pct}%)", inline=False)
    embed.add_field(name="Statut", value="✅ Obtenu !" if td["unlocked"] else "⏳ En cours", inline=True)
    embed.set_footer(text=f"Compte : {compte}")
    await interaction.response.send_message(embed=embed)


@tree.command(name="stats", description="📊 Résumé global de ta progression")
@app_commands.describe(compte="Nom du compte DDV (défaut: default)")
async def cmd_stats(interaction: discord.Interaction, compte: str = "default"):
    await interaction.response.defer()
    acc_id   = get_account_id(compte)
    streak   = get_streak(acc_id)
    trophies = get_trophies(acc_id)
    history  = get_history(acc_id, 7)
    done_t   = sum(1 for t in trophies if t["unlocked"])
    vals     = [int(r["done"]/r["total"]*100) for r in history if r["total"]]
    avg7     = f"{int(sum(vals)/len(vals))}%" if vals else "N/A"
    embed    = discord.Embed(title=f"📊 Stats — {compte}", color=0x7eb8f7)
    embed.add_field(name="🔥 Streak",   value=f"{streak.get('count',0)}j", inline=True)
    embed.add_field(name="🏅 Record",   value=f"{streak.get('best',0)}j",  inline=True)
    embed.add_field(name="🏆 Trophées", value=f"{done_t}/{len(TROPHIES_DATA)}", inline=True)
    embed.add_field(name="📈 Moy. 7j",  value=avg7, inline=True)
    if history:
        lines = []
        for r in reversed(history):
            pct = int(r["done"]/r["total"]*100) if r["total"] else 0
            bar = "█"*(pct//10) + "░"*(10-pct//10)
            lines.append(f"`{r['task_date']}` {bar} {pct}%")
        embed.add_field(name="📅 Historique 7j", value="\n".join(lines), inline=False)
    await interaction.followup.send(embed=embed)


@tree.command(name="rappel", description="🔔 Active/désactive les rappels de tâches à 22h dans ce channel")
async def cmd_rappel(interaction: discord.Interaction):
    gid = interaction.guild_id
    cid = interaction.channel_id
    if gid in rappel_channels and rappel_channels[gid] == cid:
        del rappel_channels[gid]
        await interaction.response.send_message("🔕 Rappels tâches désactivés.", ephemeral=True)
    else:
        rappel_channels[gid] = cid
        await interaction.response.send_message(
            f"🔔 Rappels tâches activés dans ce channel à {RAPPEL_HEURE:02d}h{RAPPEL_MINUTE:02d} !", ephemeral=True)


@tree.command(name="bestioles", description="🐾 Active/désactive les notifications bestioles rares dans ce channel")
async def cmd_bestioles(interaction: discord.Interaction):
    gid = interaction.guild_id
    cid = interaction.channel_id
    if gid in critter_channels and critter_channels[gid] == cid:
        del critter_channels[gid]
        await interaction.response.send_message("🔕 Notifications bestioles désactivées.", ephemeral=True)
    else:
        critter_channels[gid] = cid
        await interaction.response.send_message(
            "🐾 Notifications bestioles rares activées dans ce channel !\n"
            "Tu seras alerté dès qu'une bestiole rare apparaît.", ephemeral=True)


@tree.command(name="bestioles_now", description="🐾 Affiche les bestioles rares actives en ce moment")
async def cmd_bestioles_now(interaction: discord.Interaction):
    now     = datetime.now()
    rares   = get_active_rare_critters(now)
    if not rares:
        # Cherche les prochaines fenêtres rares
        prochaines = []
        for sp in CRITTERS:
            for v in sp["variants"]:
                if not v.get("rare"):
                    continue
                for offset in range(1, 8*24):   # cherche dans les 7 prochains jours
                    candidate = now.replace(minute=0, second=0) + timedelta(hours=offset)
                    if is_critter_active(v, candidate):
                        h_s, h_e = v["hours"]
                        prochaines.append(
                            f"{sp['icon']} **{sp['species']} {v['color']}** — "
                            f"{JOURS[candidate.weekday()]} à {h_s:02d}h00"
                        )
                        break
        embed = discord.Embed(
            title="🐾 Aucune bestiole rare active en ce moment",
            description="**Prochaines apparitions :**\n" + "\n".join(prochaines[:6]) if prochaines else "Aucune prévue.",
            color=0x888888
        )
        embed.set_footer(text=f"Vérifié à {now.strftime('%H:%M')}")
        await interaction.response.send_message(embed=embed)
        return

    await interaction.response.defer()
    for critter in rares:
        embed = make_critter_embed(critter, now)
        await interaction.followup.send(embed=embed)


# ══════════════════════════════════════════════════════════════════════════════
#  WATCHER BESTIOLES RARES — tourne toutes les minutes
# ══════════════════════════════════════════════════════════════════════════════

@tasks.loop(minutes=1)
async def critter_watcher():
    """Vérifie chaque minute si une bestiole rare vient de devenir active et notifie."""
    if not critter_channels:
        return

    now   = datetime.now()
    rares = get_active_rare_critters(now)

    for critter in rares:
        # Clé unique par bestiole + heure de début de fenêtre (évite le spam)
        h_start = critter["hours"][0]
        key = f"{critter['species']}_{critter['color']}_{now.date()}_{h_start:02d}"

        if key in notified_critters:
            continue   # déjà notifiée pour cette fenêtre

        # Vérifie qu'on est dans les 5 premières minutes de la fenêtre
        window_start_min = h_start * 60
        current_min      = now.hour * 60 + now.minute
        if current_min - window_start_min > 5:
            # Fenêtre déjà commencée depuis longtemps → on marque comme vue sans notifier
            notified_critters.add(key)
            continue

        # Envoie la notification dans tous les channels configurés
        notified_critters.add(key)
        embed = make_critter_embed(critter, now)

        for guild_id, channel_id in critter_channels.items():
            channel = bot.get_channel(channel_id)
            if channel:
                try:
                    await channel.send(
                        content="@here 🚨 **Bestiole rare disponible !**",
                        embed=embed
                    )
                    print(f"[Critter] Notification envoyée : {critter['species']} {critter['color']}")
                except discord.Forbidden:
                    print(f"[Critter] Pas la permission d'écrire dans le channel {channel_id}")

    # Nettoyage des clés trop vieilles (> 24h) pour éviter une croissance infinie
    today_str = str(now.date())
    notified_critters.difference_update(
        {k for k in notified_critters if today_str not in k}
    )


# ══════════════════════════════════════════════════════════════════════════════
#  RAPPELS TÂCHES QUOTIDIENNES
# ══════════════════════════════════════════════════════════════════════════════

@tasks.loop(minutes=1)
async def daily_reminder():
    now = datetime.now()
    if now.hour != RAPPEL_HEURE or now.minute != RAPPEL_MINUTE:
        return
    for guild_id, channel_id in rappel_channels.items():
        channel = bot.get_channel(channel_id)
        if not channel:
            continue
        acc_id     = get_account_id("default")
        tasks_list = get_daily_tasks(acc_id)
        done  = sum(1 for t in tasks_list if t["checked"])
        total = len(tasks_list)
        if done == total:
            await channel.send(f"🌙 **DDV Checklist** — Toutes les tâches du jour sont complètes ! 🎉 ({done}/{total})")
        else:
            remaining = total - done
            await channel.send(
                f"⏰ **DDV Checklist — Rappel {RAPPEL_HEURE:02d}h**\n"
                f"Il reste **{remaining}** tâche(s) à faire ({done}/{total}).\n"
                f"Lance `/daily` pour voir lesquelles !"
            )


# ══════════════════════════════════════════════════════════════════════════════
#  VUE INTERACTIVE POUR /daily
# ══════════════════════════════════════════════════════════════════════════════

class TaskView(discord.ui.View):
    def __init__(self, tasks: list[dict], account_id: int, account_name: str):
        super().__init__(timeout=300)
        self.tasks        = tasks
        self.account_id   = account_id
        self.account_name = account_name
        unchecked = [t for t in tasks if not t["checked"]][:10]
        for t in unchecked:
            btn = discord.ui.Button(
                label=t["name"][:50],
                style=discord.ButtonStyle.success,
                custom_id=f"task_{t['idx']}"
            )
            btn.callback = self._make_callback(t["idx"])
            self.add_item(btn)

    def _make_callback(self, task_idx: int):
        async def callback(interaction: discord.Interaction):
            check_task_in_db(self.account_id, task_idx, True)
            for item in self.children:
                if hasattr(item, "custom_id") and item.custom_id == f"task_{task_idx}":
                    item.disabled = True
                    item.style    = discord.ButtonStyle.secondary
                    item.label    = f"✅ {item.label}"
                    break
            tasks_updated = get_daily_tasks(self.account_id)
            done  = sum(1 for t in tasks_updated if t["checked"])
            total = len(tasks_updated)
            await interaction.response.edit_message(
                content=f"✅ Tâche cochée ! Progression : **{done}/{total}**",
                view=self
            )
        return callback


# ══════════════════════════════════════════════════════════════════════════════
#  LANCEMENT
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if BOT_TOKEN == "COLLE_TON_TOKEN_ICI":
        print("❌ Configure ton token Discord dans bot_discord.py (variable BOT_TOKEN) !")
        print("   Voir : https://discord.com/developers/applications")
        exit(1)
    if not DB_PATH.exists():
        print(f"❌ Base de données introuvable : {DB_PATH}")
        print("   Lance d'abord dreamlight_checklist.py au moins une fois.")
        exit(1)
    print(f"🤖 Démarrage du bot DDV...")
    print(f"   Base de données : {DB_PATH}")
    print(f"   Watcher bestioles rares : actif (vérification toutes les minutes)")
    bot.run(BOT_TOKEN)