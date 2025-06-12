# config.py

BUMP_CHANNEL_ID = 1374712467933888513    # ID du salon #bump
BUMP_ROLE_ID = 1377230605309313085       # ID du rôle à ping
BUMP_COOLDOWN = 2 * 60 * 60              # 2h en secondes
REMIND_INTERVAL = 60 * 60                # 1h en secondes pour les rappels si pas bump
DISBOARD_ID = 302050872383242240         # ID du bot Disboard

GUESS_CHANNEL_ID = 1378780388377231501   # ID du salon #guess-the-number
GAME_CATEGORY_ID = 1219179782462373971   # ID de la catégorie pour la création des salons privés du jeu

HELP_CHANNEL_ID = 1374478832853192755    # Salon “Commandes” : seule la commande !help y est autorisée
HELPJEU_CHANNEL_ID = 1378780388377231501 # Salon “Jeu”      : seule la commande !helpjeu y est autorisée

# ── NOUVEAU ──
HELPER_ROLE_ID = 1373412220641349753     # ID du rôle autorisé à utiliser !help / !helpadmin / !helpjeu / !helpjeuadmin
EXCLUDED_CHANNEL_IDS = [1378780388377231501,1374478832853192755,1377990979100999700]
WELCOME_CHANNEL_ID = 1374477839486685294