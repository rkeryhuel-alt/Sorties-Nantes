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
    # Pour ajouter une source du même type, copie le bloc ci-dessus.
]
OUT = "data/events.json"
TODAY = date.today().isoformat()


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "sorties-nantes/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def pick(rec, needles):
    for n in needles:
        for k, v in rec.items():
            if n in k.lower() and v not in (None, "", []):
                return v
    return None


def iso(v):
    m = re.search(r"\d{4}-\d{2}-\d{2}", str(v or ""))
    return m.group(0) if m else None


def normalise(rec, src):
    titre = pick(rec, ["titre", "title", "intitule", "nom", "libelle"])
    debut = iso(pick(rec, ["date_debut", "datedebut", "debut", "start", "date"]))
    if not titre or not debut:
        return None
    fin = iso(pick(rec, ["date_fin", "datefin", "end", "fin"])) or debut
    if fin < TODAY:
        return None
    tarif = pick(rec, ["tarif", "prix"])
    if tarif is None:
        prix = "inconnu"
    elif "gratuit" in str(tarif).lower():
        prix = "gratuit"
    else:
        prix = "payant"
    url = pick(rec, ["url", "lien", "site_web"])
    return {
        "n": str(titre)[:120],
        "w": "%s · %s" % (src["ville"], str(pick(rec, ["lieu", "bibliotheque", "equipement", "site", "adresse"]) or src["nom"])[:80]),
        "d": re.sub(r"<[^>]+>", " ", str(pick(rec, ["description", "descriptif", "resume", "texte"]) or ""))[:240].strip(),
        "start": debut,
        "end": fin,
        "ages": ["0-3", "3-6", "6-12", "12+"],
        "lieu": "int",
        "prix": prix,
        "url": url if isinstance(url, str) and url.startswith(("http://", "https://")) else None,
    }


def fetch_source(src):
    out, offset, first = [], 0, True
    while offset < 1000:
        q = urllib.parse.urlencode({"limit": 100, "offset": offset})
        url = "%s/api/explore/v2.1/catalog/datasets/%s/records?%s" % (src["base"], src["dataset"], q)
        res = get(url).get("results", [])
        if first and res:
            print("Champs disponibles :", sorted(res[0].keys()))
            print("Exemple :", json.dumps(res[0], ensure_ascii=False)[:600])
            first = False
        for rec in res:
            ev = normalise(rec, src)
            if ev:
                out.append(ev)
        if len(res) < 100:
            break
        offset += 100
    return out


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
