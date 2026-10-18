"""Serveur MCP Destiny 2 : triomphes, sceaux et progression via l'API Bungie.

Variables d'environnement :
    BUNGIE_API_KEY   clé de l'application Bungie (obligatoire)
    BUNGIE_NAME      Bungie name par défaut, ex. "Nom#1234" (optionnel)
    D2_LANG          langue du manifeste, "fr" par défaut
"""
import json
import os
import sys
import urllib.request
from functools import lru_cache

from mcp.server.fastmcp import FastMCP

API = "https://www.bungie.net/Platform"
LANG = os.environ.get("D2_LANG", "fr")
mcp = FastMCP("destiny2")


def call(path, body=None):
    key = os.environ.get("BUNGIE_API_KEY")
    if not key:
        raise RuntimeError("BUNGIE_API_KEY n'est pas défini.")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        API + path,
        data=data,
        headers={"X-API-Key": key, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        out = json.load(r)
    if out.get("ErrorCode") != 1:
        raise RuntimeError(f"Erreur Bungie : {out.get('Message')}")
    return out["Response"]


@lru_cache(maxsize=4)
def definition(name):
    rel = call("/Destiny2/Manifest/")["jsonWorldComponentContentPaths"][LANG][name]
    with urllib.request.urlopen("https://www.bungie.net" + rel, timeout=120) as r:
        return json.load(r)


def player(bungie_name):
    bungie_name = bungie_name or os.environ.get("BUNGIE_NAME")
    if not bungie_name or "#" not in bungie_name:
        raise RuntimeError("Donne un Bungie name au format Nom#1234.")
    display, code = bungie_name.rsplit("#", 1)
    res = call(
        "/Destiny2/SearchDestinyPlayerByBungieName/-1/",
        {"displayName": display, "displayNameCode": int(code)},
    )
    if not res:
        raise RuntimeError("Joueur introuvable.")
    return res[0]["membershipType"], res[0]["membershipId"]


def profile_records(bungie_name):
    """Triomphes du compte, fusionnés avec ceux de chaque personnage.

    Beaucoup de triomphes (donjons, raids) sont propres à un personnage.
    On garde, pour chaque triomphe, la version la plus avancée.
    """
    mtype, mid = player(bungie_name)
    prof = call(f"/Destiny2/{mtype}/Profile/{mid}/?components=900,902")
    merged = dict(prof["profileRecords"]["data"]["records"])
    for char in prof.get("characterRecords", {}).get("data", {}).values():
        for h, rec in char["records"].items():
            if h not in merged or (done(rec) and not done(merged[h])):
                merged[h] = rec
    return merged


def done(rec):
    # Un triomphe absent des données n'est jamais compté comme fait.
    if not rec:
        return False
    state = rec["state"]
    return bool(state & 1) or not (state & 4)


def collect(node_hash, nodes, out):
    children = nodes[str(node_hash)].get("children", {})
    out.extend(r["recordHash"] for r in children.get("records", []))
    for c in children.get("presentationNodes", []):
        collect(c["presentationNodeHash"], nodes, out)


def seal_nodes():
    return {
        n["displayProperties"]["name"].lower(): n
        for n in definition("DestinyPresentationNodeDefinition").values()
        if n.get("completionRecordHash") and n["displayProperties"]["name"]
    }


@mcp.tool()
def list_seals() -> str:
    """Liste les noms des sceaux (titres) Destiny 2 disponibles."""
    return "\n".join(sorted(n["displayProperties"]["name"] for n in seal_nodes().values()))


@mcp.tool()
def seal_progress(seal: str, bungie_name: str = "", only_remaining: bool = True) -> str:
    """Progression d'un sceau : triomphes restants avec progression et description.

    seal: nom exact du sceau (voir list_seals), ex. "La Cité des rêves".
    bungie_name: "Nom#1234" ; par défaut BUNGIE_NAME. Le profil doit être public.
    """
    nodes = seal_nodes()
    node = nodes.get(seal.lower())
    if not node:
        raise RuntimeError("Sceau introuvable, utilise list_seals.")
    records = profile_records(bungie_name)
    rec_defs = definition("DestinyRecordDefinition")
    hashes = []
    collect(node["hash"], definition("DestinyPresentationNodeDefinition"), hashes)
    lines = []
    finished = 0
    for h in hashes:
        rec = records.get(str(h), {})
        ok = done(rec)
        finished += ok
        if ok and only_remaining:
            continue
        d = rec_defs[str(h)]["displayProperties"]
        prog = ", ".join(
            f"{o['progress']}/{o['completionValue']}" for o in rec.get("objectives", [])
        )
        lines.append(f"{'[x]' if ok else '[ ]'} {d['name']} [{prog}]\n    {d['description']}")
    head = f"{node['displayProperties']['name']} : {finished}/{len(hashes)}"
    return "\n".join([head, *lines])


@mcp.tool()
def search_triumph(query: str, bungie_name: str = "", limit: int = 15) -> str:
    """Cherche un triomphe par mot-clé (nom ou description) et affiche son état."""
    records = profile_records(bungie_name)
    q = query.lower()
    lines = []
    for h, rd in definition("DestinyRecordDefinition").items():
        d = rd.get("displayProperties", {})
        if q in d.get("name", "").lower() or q in d.get("description", "").lower():
            rec = records.get(h)
            if rec is None:
                continue
            prog = ", ".join(
                f"{o['progress']}/{o['completionValue']}" for o in rec.get("objectives", [])
            )
            lines.append(
                f"{'[x]' if done(rec) else '[ ]'} {d['name']} [{prog}]\n    {d.get('description', '')}"
            )
            if len(lines) >= limit:
                break
    return "\n".join(lines) or "Aucun triomphe trouvé."


def remaining_triumphs(seal_name, records):
    """Triomphes encore à faire d'un sceau, hors triomphes invisibles/non possédés.

    Bits d'état Bungie : 8 caché (secret), 16 invisible (retiré), 32 DLC non possédé.
    """
    node = seal_nodes()[seal_name.lower()]
    rec_defs = definition("DestinyRecordDefinition")
    hashes = []
    collect(node["hash"], definition("DestinyPresentationNodeDefinition"), hashes)
    out = []
    for h in hashes:
        rec = records.get(str(h))
        if not rec or done(rec):
            continue
        st = rec["state"]
        if st & 16 or st & 32:
            continue
        d = rec_defs[str(h)]["displayProperties"]
        prog = ", ".join(f"{o['progress']}/{o['completionValue']}" for o in rec.get("objectives", []))
        out.append((d["name"], d["description"], prog, bool(st & 8)))
    return out


@mcp.tool()
def doable_triumphs(seal: str = "", bungie_name: str = "") -> str:
    """Triomphes faisables maintenant, pour un sceau ou pour tous les sceaux non terminés.

    Exclut les triomphes invisibles (retirés) et ceux d'extensions non possédées.
    Un triomphe caché (secret) est marqué [secret].
    """
    records = profile_records(bungie_name)
    nodes = seal_nodes()
    names = [seal] if seal else sorted(n["displayProperties"]["name"] for n in nodes.values())
    rec_defs = definition("DestinyRecordDefinition")
    lines = []
    for name in names:
        node = nodes.get(name.lower())
        if not node:
            raise RuntimeError("Sceau introuvable, utilise list_seals.")
        comp = records.get(str(node["completionRecordHash"]), {})
        if comp and comp.get("state", 0) & 1:
            continue  # titre déjà obtenu
        rem = remaining_triumphs(name, records)
        if not rem:
            continue
        lines.append(f"## {name} ({len(rem)} faisables)")
        for n, desc, prog, secret in rem:
            lines.append(f"- {n} [{prog}]{' [secret]' if secret else ''} : {desc}")
    return "\n".join(lines) or "Rien de faisable."


WEEK_FILE =os.path.join(os.path.dirname(os.path.abspath(__file__)), "week.json")
MISSIONS = ["Courrier brisé", "Le Moteur de l'Oracle", "Monastère sombre"]
ASCENDANTS = [
    "Ouroborea", "Refuge de la Perte", "Ruines brisées",
    "Bastion des Lames affûtées", "Abîme d'Agonarch", "Garnison cimmérienne",
]
RESET_HOUR_UTC = 17  # reset hebdomadaire : mardi 17h UTC


def last_reset(now=None):
    from datetime import datetime, timedelta, timezone
    now = now or datetime.now(timezone.utc)
    d = now.replace(hour=RESET_HOUR_UTC, minute=0, second=0, microsecond=0)
    d -= timedelta(days=(d.weekday() - 1) % 7)  # mardi = 1
    if d > now:
        d -= timedelta(days=7)
    return d


@mcp.tool()
def calibrate_week(mission_semaine: int, defi_ascendant: str) -> str:
    """Calibre la rotation avec ce que le jeu affiche CETTE semaine.

    mission_semaine: 1 = Courrier brisé, 2 = Moteur de l'Oracle, 3 = Monastère sombre.
    defi_ascendant: nom du défi Ascendant actif (voir la liste dans la réponse d'erreur).
    """
    if mission_semaine not in (1, 2, 3):
        raise RuntimeError("mission_semaine doit valoir 1, 2 ou 3.")
    names = [a.lower() for a in ASCENDANTS]
    if defi_ascendant.lower() not in names:
        raise RuntimeError("Défis connus : " + ", ".join(ASCENDANTS))
    anchor = last_reset().date().isoformat()
    with open(WEEK_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {"anchor": anchor, "mission": mission_semaine - 1,
             "ascendant": names.index(defi_ascendant.lower())},
            f,
        )
    return f"Calibré sur le reset du {anchor}."


@mcp.tool()
def current_week() -> str:
    """Donne la semaine actuelle : mission de Petra et défi Ascendant en rotation."""
    from datetime import date
    if not os.path.exists(WEEK_FILE):
        raise RuntimeError("Pas calibré : lance calibrate_week une première fois.")
    with open(WEEK_FILE, encoding="utf-8") as f:
        cal = json.load(f)
    weeks = (last_reset().date() - date.fromisoformat(cal["anchor"])).days // 7
    mission = MISSIONS[(cal["mission"] + weeks) % 3]
    asc = ASCENDANTS[(cal["ascendant"] + weeks) % 6]
    return (
        f"Reset du {last_reset().date()} (semaine +{weeks} depuis la calibration)\n"
        f"Mission de Petra : {mission}\nDéfi Ascendant : {asc}"
    )


import extra  # noqa: E402  (outils supplémentaires)

extra.register(mcp, sys.modules[__name__])

if __name__ == "__main__":
    mcp.run()
