# destiny2-mcp

Serveur MCP pour suivre ses triomphes et sceaux Destiny 2 via l'API Bungie.

## Outils
- `list_seals` : liste les sceaux.
- `seal_progress` : triomphes restants d'un sceau.
- `search_triumph` : recherche un triomphe par mot-clé.
- `doable_triumphs` : triomphes faisables (sans les retirés ni les DLC non possédés).
- `calibrate_week` / `current_week` : rotation hebdomadaire (mission de Petra, défi Ascendant).
- `next_best_triumphs` : top des triomphes les plus rapides à finir.
- `monument_planner` : catégories du Monument des Triomphes, avec les triomphes faisables.
- `seal_roadmap` : plan d'un sceau (rapides, rotation, longs).
- `weekly_checklist` : rotation de la semaine et état des triomphes liés.
- `collections_missing` / `exotic_checklist` : objets de Collections manquants par source.
- `catalyst_tracker` : catalyseurs exotiques en cours.
- `recent_activities` / `raid_report` / `clan_overview` : activité, raids et clan.
- `compare_players` : compare un sceau avec un autre joueur.

## Installation
1. Crée une application sur https://www.bungie.net/en/Application (aucune permission OAuth requise,
   coche seulement la lecture des infos Destiny 2) et récupère la clé d'API.
2. `pip install -r requirements.txt`
3. Ajoute à la config MCP (par exemple `claude_desktop_config.json`) :

```json
"destiny2": {
  "command": "python",
  "args": ["C:\\chemin\\vers\\destiny2-mcp\\server.py"],
  "env": {
    "BUNGIE_API_KEY": "ta_cle",
    "BUNGIE_NAME": "Nom#1234"
  }
}
```

Le profil doit être public. Ne commite jamais ta clé : elle reste dans la config, pas dans le dépôt.
`week.json` (calibration locale) est ignoré par Git.
