#!/usr/bin/env python3
"""Met à jour data/events.json à partir de jeux de données ouverts (Opendatasoft)."""
import json, os, re, sys, urllib.parse, urllib.request
from datetime import date, datetime, timezone

SOURCES = [
    {
        "nom": "Bibliothèques de Nantes",
        "base": "https://data.nantesmetropole.fr",
        "dataset": "244400404_agenda-animations-culturelles-bibliotheque-municipale-nantes",
        "ville": "Nantes",
    },
]
OUT = "data/events.json"
TODAY = date.today().isoformat()


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "sorties-nantes/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def iso(v):
    m = re.search(r"\d{4}-\d{2}-\d{2}", str(v or ""))
    return m.group(0) if m else None


def yes(v):
    return str(v).strip().lower() in ("oui", "true", "1", "yes")


def normalise(rec, src):
    titre = rec.get("nom")
    debut = iso(rec.get("date"))
    if not titre or not debut or debut < TODAY:
        return None
    if yes(rec.get("annule")) or yes(rec.get("reporte")):
        return None
    if not yes(rec.get("accueil_enfant")):
        return None
    g = rec.get("gratuit")
    prix = "inconnu" if g in (None, "") else ("gratuit" if yes(g) else "payant")
    heures = " - ".join(str(h) for h in (rec.get("heure_debut"), rec.get("heure_fin")) if h)
    desc = re.sub(r"<[^>]+>", " ", str(rec.get("description") or "")).strip()
    if heures:
        desc = (heures + ". " + desc).strip()
    url = rec.get("url_site") or rec.get("lien_agenda")
    return {
        "n": str(titre)[:120],
        "w": "%s · %s" % (rec.get("ville") or src["ville"], str(rec.get("lieu") or src["nom"])[:80]),
        "d": desc[:240],
        "start": debut,
        "end": debut,
        "ages": ["0-3", "3-6", "6-12", "12+"],
        "lieu": "int",
        "prix": prix,
        "url": url if isinstance(url, str) and url.startswith(("http://", "https://")) else None,
    }


def collect(src, base, params):
    out, offset, raw = [], 0, 0
    while offset < 2000:
        q = urllib.parse.urlencode(dict(params, limit=100, offset=offset))
        res = get("%s?%s" % (base, q)).get("results", [])
        if offset == 0 and res:
            for r in res[:3]:
                print("Contrôle :", r.get("date"), "| enfant:", r.get("accueil_enfant"), "| gratuit:", r.get("gratuit"))
        raw += len(res)
        for rec in res:
            ev = normalise(rec, src)
            if ev:
                out.append(ev)
        if len(res) < 100:
            break
        offset += 100
    print("Enregistrements lus : %d, retenus : %d" % (raw, len(out)))
    return out


def fetch_source(src):
    base = "%s/api/explore/v2.1/catalog/datasets/%s/records" % (src["base"], src["dataset"])
    last = None
    for params in ({"where": "date >= date'%s'" % TODAY, "order_by": "date"}, {}):
        try:
            return collect(src, base, params)
        except Exception as e:
            last = e
            print("Essai sans succès (%s) : %s" % (params or "sans filtre", e))
    raise last


def main():
    events, ok = [], 0
    for src in SOURCES:
        try:
            got = fetch_source(src)
            print("%s : %d événements à venir" % (src["nom"], len(got)))
            events += got
            ok += 1
        except Exception as e:
            print("ÉCHEC pour %s : %s" % (src["nom"], e))
    if not ok:
        print("Aucune source disponible : l'ancien fichier est conservé.")
        return
    events.sort(key=lambda e: (e["start"], e["n"]))
    os.makedirs("data", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "events": events[:80]}, f, ensure_ascii=False, indent=1)
    print("Écrit : %d événements" % min(len(events), 80))


if __name__ == "__main__":
    sys.exit(main())
