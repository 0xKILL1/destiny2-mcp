"""Outils supplémentaires du serveur MCP Destiny 2 (lecture seule, sans OAuth)."""
import re
from collections import defaultdict

RAID_TYPE = 2043403989  # activityTypeHash des raids


def register(mcp, h):
    """Enregistre les outils. `h` est le module server (call, definition, etc.)."""

    def get_profile(bungie_name, comps):
        mtype, mid = h.player(bungie_name)
        prof = h.call(f"/Destiny2/{mtype}/Profile/{mid}/?components={comps}")
        return mtype, mid, prof

    def prog_text(rec):
        return ", ".join(f"{o['progress']}/{o['completionValue']}" for o in rec.get("objectives", []))

    def ratio(rec):
        objs = rec.get("objectives", [])
        if not objs:
            return 0.0
        return sum(min(o["progress"], o["completionValue"]) / max(o["completionValue"], 1) for o in objs) / len(objs)

    def pending_seals(records):
        rd = h.definition("DestinyRecordDefinition")
        for name, node in h.seal_nodes().items():
            comp = records.get(str(node["completionRecordHash"]), {})
            if comp and comp.get("state", 0) & 1:
                continue
            for n, desc, prog, secret in h.remaining_triumphs(node["displayProperties"]["name"], records):
                yield node["displayProperties"]["name"], n, desc, prog, secret

    # ---------------------------------------------------------------- triomphes
    @mcp.tool()
    def next_best_triumphs(top: int = 10, bungie_name: str = "") -> str:
        """Top des triomphes les plus rapides à finir, tous sceaux confondus.

        Score : progression déjà faite, peu d'objectifs, pas de compteur énorme.
        """
        records = h.profile_records(bungie_name)
        rd = h.definition("DestinyRecordDefinition")
        scored = []
        for hh, node in ((k, v) for k, v in h.seal_nodes().items()):
            pass
        for seal, name, desc, prog, secret in pending_seals(records):
            meta = re.search(r"Terminez des Triomphes dans", desc)
            if meta or "Badge associé" in desc:
                continue  # entrées « méta » : pas d'action directe
            nums = [int(x) for p in prog.replace(" ", "").split(",") if "/" in p for x in p.split("/")]
            total = sum(nums[1::2]) if nums else 1
            done_ = sum(nums[0::2]) if nums else 0
            score = (done_ / total if total else 0) - min(total, 100) / 400
            scored.append((score, seal, name, prog, desc))
        scored.sort(reverse=True)
        lines = [f"{i+1}. [{s}] {n} [{p}] : {d[:120]}" for i, (_, s, n, p, d) in enumerate(scored[:top])]
        return "\n".join(lines) or "Rien à proposer."

    @mcp.tool()
    def monument_planner(bungie_name: str = "", per_category: int = 8) -> str:
        """Catégories du Monument des Triomphes : combien en valider et lesquels sont faisables."""
        records = h.profile_records(bungie_name)
        nd = h.definition("DestinyPresentationNodeDefinition")
        rd = h.definition("DestinyRecordDefinition")
        parent = {}
        for k, n in nd.items():
            for c in n.get("children", {}).get("presentationNodes", []):
                parent[str(c["presentationNodeHash"])] = k
        seal = h.seal_nodes()["monument des triomphes"]
        hashes = []
        h.collect(seal["hash"], nd, hashes)
        out = []
        for rh in hashes:
            meta = rd[str(rh)]["displayProperties"]
            rec = records.get(str(rh), {})
            m = re.search(r"cat\w+gorie\s+(.+?)\s*:\s*(.+?)\.", meta["description"])
            if not m or h.done(rec):
                continue
            top, sub = (x.strip() for x in m.groups())
            norm = lambda s: re.sub(r"\s+", " ", s).strip().lower()
            cands = [
                k for k, n in nd.items()
                if norm(n["displayProperties"]["name"]) == norm(sub)
                and norm(nd.get(parent.get(k, ""), {}).get("displayProperties", {}).get("name", "")) == norm(top)
            ] or [k for k, n in nd.items() if norm(n["displayProperties"]["name"]) == norm(sub)]
            need = rec.get("objectives", [{}])[0]
            header = f"## {top} : {sub} ({need.get('progress', '?')}/{need.get('completionValue', '?')})"
            if not cands:
                out.append(header + "\n  (liste non lisible : ouvre-la en jeu)")
                continue
            hs = []
            h.collect(cands[0], nd, hs)
            todo = []
            for k in hs:
                r2 = records.get(str(k))
                if not r2 or h.done(r2) or r2["state"] & (16 | 32) or k == rh:
                    continue
                d = rd[str(k)]["displayProperties"]
                todo.append(f"- {d['name']} [{prog_text(r2)}] : {d['description'][:100]}")
            out.append(header + "\n" + "\n".join(todo[:per_category]))
        return "\n\n".join(out) or "Monument terminé."

    @mcp.tool()
    def seal_roadmap(seal: str, bungie_name: str = "") -> str:
        """Plan pour un sceau : triomphes triés du plus rapide au plus long, avec les dépendances de rotation."""
        records = h.profile_records(bungie_name)
        rem = h.remaining_triumphs(seal, records)
        if not rem:
            return "Sceau terminé (ou rien de faisable)."
        rot_words = ("semaine", "hebdomadaire", "Ascendant", "Chasse", "Cauchemar", "cour de la Reine", "malédiction")
        quick, rotation, long_ = [], [], []
        for n, desc, prog, secret in rem:
            nums = [int(x) for p in prog.replace(" ", "").split(",") if "/" in p for x in p.split("/")]
            total = sum(nums[1::2]) if nums else 1
            line = f"- {n} [{prog}] : {desc[:110]}"
            if any(w.lower() in (n + desc).lower() for w in rot_words):
                rotation.append(line)
            elif total <= 3:
                quick.append(line)
            else:
                long_.append(line)
        parts = [f"# {seal} : {len(rem)} faisables"]
        parts.append("## Rapides (1 à 3 actions)\n" + ("\n".join(quick) or "-"))
        parts.append("## Dépendent de la rotation (à étaler sur plusieurs semaines)\n" + ("\n".join(rotation) or "-"))
        parts.append("## Longs (compteurs élevés)\n" + ("\n".join(long_) or "-"))
        weeks = max(1, len(rotation))
        parts.append(f"Estimation grossière : au moins {weeks} semaine(s) à cause de la rotation.")
        return "\n\n".join(parts)

    @mcp.tool()
    def compare_players(seal: str, other_bungie_name: str, bungie_name: str = "") -> str:
        """Compare ton avancement sur un sceau avec celui d'un autre joueur (profil public)."""
        mine = h.profile_records(bungie_name)
        theirs = h.profile_records(other_bungie_name)
        node = h.seal_nodes().get(seal.lower())
        if not node:
            raise RuntimeError("Sceau introuvable, utilise list_seals.")
        rd = h.definition("DestinyRecordDefinition")
        hashes = []
        h.collect(node["hash"], h.definition("DestinyPresentationNodeDefinition"), hashes)
        only_me, only_them = [], []
        for k in hashes:
            a, b = h.done(mine.get(str(k), {})), h.done(theirs.get(str(k), {}))
            name = rd[str(k)]["displayProperties"]["name"]
            if a and not b:
                only_me.append(name)
            elif b and not a:
                only_them.append(name)
        return (
            f"{seal}\nFaits par toi seulement ({len(only_me)}) : {', '.join(only_me) or '-'}\n"
            f"Faits par l'autre seulement ({len(only_them)}) : {', '.join(only_them) or '-'}"
        )

    # ------------------------------------------------------------ hebdomadaire
    @mcp.tool()
    def weekly_checklist(bungie_name: str = "") -> str:
        """Ce qu'il y a à faire cette semaine : rotation (calibrée) et état des triomphes liés."""
        lines = []
        try:
            lines.append(h.current_week())
        except Exception as e:  # semaine non calibrée
            lines.append(f"Semaine : {e}")
        ms = h.call("/Destiny2/Milestones/")
        mdef = h.definition("DestinyMilestoneDefinition")
        raids = sorted({mdef.get(k, {}).get("displayProperties", {}).get("name", "?") for k in ms} - {"?"})
        lines.append("Jalons actifs : " + ", ".join(raids))
        records = h.profile_records(bungie_name)
        rd = h.definition("DestinyRecordDefinition")
        watch = ("Le Gardien de la situation", "Pro des Chasses aux Cauchemars contre-la-montre",
                 "Pilleur de tombes", "Omelette altérée", "Monde inconnu")
        for k, rec in records.items():
            name = rd.get(k, {}).get("displayProperties", {}).get("name", "")
            if name in watch:
                lines.append(f"{'[x]' if h.done(rec) else '[ ]'} {name} [{prog_text(rec)}]")
        return "\n".join(lines)

    # -------------------------------------------------------------- collections
    def inventory_lite():
        return h.definition("DestinyInventoryItemLiteDefinition")

    @mcp.tool()
    def collections_missing(kind: str = "exotic", bungie_name: str = "", limit: int = 40) -> str:
        """Objets de Collections non obtenus, groupés par source.

        kind: "exotic" (exotiques), "weapon" (toutes armes) ou "armor" (armures).
        """
        mtype, mid, prof = get_profile(bungie_name, "800")
        states = dict(prof.get("profileCollectibles", {}).get("data", {}).get("collectibles", {}))
        for c in prof.get("characterCollectibles", {}).get("data", {}).values():
            for k, v in c["collectibles"].items():
                if k not in states or (states[k]["state"] & 1 and not v["state"] & 1):
                    states[k] = v
        cdef = h.definition("DestinyCollectibleDefinition")
        items = inventory_lite()
        groups = defaultdict(list)
        for k, st in states.items():
            if not st["state"] & 1:
                continue  # obtenu
            if st["state"] & 4:
                continue  # invisible
            c = cdef.get(k)
            if not c:
                continue
            it = items.get(str(c.get("itemHash")), {})
            tier = it.get("inventory", {}).get("tierTypeName", "")
            itype = it.get("itemType")  # 3 arme, 2 armure
            if kind == "exotic" and (tier != "Exotique" or itype not in (2, 3)):
                continue
            if "everversum" in (c.get("sourceString") or "").lower():
                continue  # cosmétiques de la boutique, jamais utiles pour le coffre
            if kind == "weapon" and itype != 3:
                continue
            if kind == "armor" and itype != 2:
                continue
            groups[(c.get("sourceString") or "Source inconnue").strip()].append(c["displayProperties"]["name"])
        lines = []
        for src, names in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            shown = sorted(names)[:25]
            more = f" … (+{len(names) - 25})" if len(names) > 25 else ""
            lines.append(f"{src} ({len(names)}) : {', '.join(shown)}{more}")
            if len(lines) >= limit:
                break
        return "\n".join(lines) or "Rien de manquant."

    @mcp.tool()
    def exotic_checklist(bungie_name: str = "") -> str:
        """Exotiques non obtenus et leur source (raccourci de collections_missing)."""
        return collections_missing("exotic", bungie_name)

    @mcp.tool()
    def catalyst_tracker(bungie_name: str = "", limit: int = 40) -> str:
        """Catalyseurs exotiques commencés ou en cours, avec leur progression."""
        records = h.profile_records(bungie_name)
        rd = h.definition("DestinyRecordDefinition")
        rows = []
        for k, rec in records.items():
            d = rd.get(k, {}).get("displayProperties", {})
            name = d.get("name", "")
            if "catalyseur" in name.lower() and not h.done(rec) and not rec["state"] & (16 | 32):
                rows.append((ratio(rec), name, prog_text(rec)))
        rows.sort(reverse=True)
        return "\n".join(f"- {n} [{p}]" for _, n, p in rows[:limit]) or "Aucun catalyseur en cours."

    # ------------------------------------------------------------------- activité
    def character_ids(bungie_name):
        mtype, mid, prof = get_profile(bungie_name, "200")
        return mtype, mid, list(prof["characters"]["data"].keys())

    @mcp.tool()
    def recent_activities(count: int = 10, bungie_name: str = "") -> str:
        """Tes dernières activités (tous modes), du plus récent au plus ancien."""
        mtype, mid, chars = character_ids(bungie_name)
        adef = h.definition("DestinyActivityDefinition")
        rows = []
        for c in chars:
            res = h.call(f"/Destiny2/{mtype}/Account/{mid}/Character/{c}/Stats/Activities/?count={count}&mode=0")
            rows += res.get("activities", [])
        rows.sort(key=lambda a: a["period"], reverse=True)
        lines = []
        for a in rows[:count]:
            name = adef.get(str(a["activityDetails"]["directorActivityHash"]), {}).get("displayProperties", {}).get("name", "?")
            v = a["values"]
            kd = v.get("killsDeathsRatio", {}).get("basic", {}).get("displayValue", "?")
            mins = int(v["timePlayedSeconds"]["basic"]["value"] // 60)
            ok = "terminée" if v.get("completed", {}).get("basic", {}).get("value") == 1 else "non terminée"
            lines.append(f"{a['period'][:16].replace('T', ' ')} | {name} | {ok} | K/D {kd} | {mins} min")
        return "\n".join(lines) or "Aucune activité."

    @mcp.tool()
    def raid_report(bungie_name: str = "") -> str:
        """Complétions par raid, tous personnages confondus."""
        mtype, mid, chars = character_ids(bungie_name)
        adef = h.definition("DestinyActivityDefinition")
        totals = defaultdict(int)
        for c in chars:
            res = h.call(f"/Destiny2/{mtype}/Account/{mid}/Character/{c}/Stats/AggregateActivityStats/")
            for a in res.get("activities", []):
                d = adef.get(str(a["activityHash"]))
                if not d or d.get("activityTypeHash") != RAID_TYPE:
                    continue
                n = a["values"]["activityCompletions"]["basic"]["value"]
                if n:
                    totals[d["displayProperties"]["name"]] += int(n)
        return "\n".join(f"{n} : {v}" for n, v in sorted(totals.items(), key=lambda kv: -kv[1])) or "Aucun raid terminé."

    @mcp.tool()
    def clan_overview(bungie_name: str = "") -> str:
        """Ton clan : effectif et dernière connexion des membres."""
        mtype, mid = h.player(bungie_name)
        groups = h.call(f"/GroupV2/User/{mtype}/{mid}/0/1/").get("results", [])
        if not groups:
            return "Pas de clan."
        g = groups[0]["group"]
        members = h.call(f"/GroupV2/{g['groupId']}/Members/").get("results", [])
        lines = [f"{g['name']} : {len(members)} membres"]
        members.sort(key=lambda m: int(m.get("lastOnlineStatusChange", 0)), reverse=True)
        from datetime import datetime, timezone
        for m in members[:25]:
            ts = datetime.fromtimestamp(int(m.get("lastOnlineStatusChange", 0)), timezone.utc).strftime("%Y-%m-%d")
            name = m["destinyUserInfo"].get("bungieGlobalDisplayName") or m["destinyUserInfo"].get("displayName")
            lines.append(f"- {name} (dernière connexion {ts}){' [en ligne]' if m.get('isOnline') else ''}")
        return "\n".join(lines)
