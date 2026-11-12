#!/usr/bin/env python3
"""Met à jour data/events.json depuis des sources ouvertes (Opendatasoft et OpenAgenda)."""
import json, os, re, sys, time, unicodedata, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date, datetime, timedelta, timezone

OA_URL = ("https://openagenda.com/agendas/82470621/events.v2.rss?threshold=auto&detailed=1"
          "&sort=timingsWithFeatured.asc&relative%5B0%5D=current&relative%5B1%5D=upcoming")
# Communes retenues pour l'agenda de la métropole (à ajuster).
VILLES = ["Vertou", "Nantes", "Rezé", "Saint-Sébastien-sur-Loire", "Basse-Goulaine",
          "Les Sorinières", "Haute-Goulaine", "La Haie-Fouassière", "Château-Thébaud"]
SOURCES = [
    {"type": "ods", "nom": "Bibliothèques de Nantes", "base": "https://data.nantesmetropole.fr",
     "dataset": "244400404_agenda-animations-culturelles-bibliotheque-municipale-nantes", "ville": "Nantes"},
    {"type": "rss", "nom": "Agenda de Nantes Métropole", "url": OA_URL},
]
OUT = "data/events.json"
TODAY = date.today().isoformat()
ALL_AGES = ["0-3", "3-6", "6-12", "12+"]
BUCKETS = [("0-3", 0, 3), ("3-6", 3, 6), ("6-12", 6, 12), ("12+", 12, 99)]
MOIS = {m: i + 1 for i, m in enumerate("janvier fevrier mars avril mai juin juillet aout septembre octobre novembre decembre".split())}
KIDS = re.compile(r"enfant|en famille|pour les familles|jeune public|tout-petit|tout petit|bebe|marionnette|\bcontes?\b")


def get(url, raw=False):
    req = urllib.request.Request(url, headers={"User-Agent": "sorties-nantes/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = r.read()
    return data if raw else json.loads(data)


def plain(s):
    s = unicodedata.normalize("NFD", str(s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def iso(v):
    m = re.search(r"\d{4}-\d{2}-\d{2}", str(v or ""))
    return m.group(0) if m else None


def yes(v):
    return str(v).strip().lower() in ("oui", "true", "1", "yes")


def ages_from(text):
    t = plain(text)
    lo, hi = 0, 99
    m = re.search(r"age minimum\s*:\s*(\d+)\s*et\s*age maximum\s*:\s*(\d+)", t)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
    elif re.search(r"(\d+)\s*(?:a|-|/|et)\s*(\d+)\s*ans", t):
        m = re.search(r"(\d+)\s*(?:a|-|/|et)\s*(\d+)\s*ans", t)
        lo, hi = int(m.group(1)), int(m.group(2))
    else:
        m = re.search(r"(?:a partir de|des)\s*(\d+)\s*(ans|mois)", t)
        if m:
            lo = int(m.group(1)) / (12 if m.group(2) == "mois" else 1)
        elif re.search(r"bebe|tout-petit|tout petit|moins de 3", t):
            hi = 3
        elif re.search(r"adolescent|\bados?\b", t):
            lo = 12
    return [b for b, s, e in BUCKETS if e > lo and s <= hi] or list(ALL_AGES)


def clean(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(s or ""))).strip()


# ---------- Opendatasoft (bibliothèques de Nantes) ----------
def ods_event(rec, src):
    titre, debut = rec.get("nom"), iso(rec.get("date"))
    if not titre or not debut or debut < TODAY:
        return None
    if yes(rec.get("annule")) or yes(rec.get("reporte")) or not yes(rec.get("accueil_enfant")):
        return None
    g = rec.get("gratuit")
    prix = "inconnu" if g in (None, "") else ("gratuit" if yes(g) else "payant")
    heures = " - ".join(str(h) for h in (rec.get("heure_debut"), rec.get("heure_fin")) if h)
    desc = clean(rec.get("description"))
    if heures:
        desc = (heures + ". " + desc).strip()
    url = rec.get("url_site") or rec.get("lien_agenda")
    return {"n": str(titre)[:120], "w": "%s · %s" % (rec.get("ville") or src["ville"], str(rec.get("lieu") or src["nom"])[:80]),
            "d": desc[:240], "start": debut, "end": debut,
            "ages": ages_from("%s %s %s" % (rec.get("precisions_public") or "", titre, desc[:200])),
            "lieu": "int", "prix": prix,
            "url": url if isinstance(url, str) and url.startswith(("http://", "https://")) else None}


def fetch_ods(src):
    base = "%s/api/explore/v2.1/catalog/datasets/%s/records" % (src["base"], src["dataset"])
    last = None
    for params in ({"where": "date >= date'%s'" % TODAY, "order_by": "date"}, {}):
        try:
            out, offset, raw, publics = [], 0, 0, Counter()
            while offset < 2000:
                q = urllib.parse.urlencode(dict(params, limit=100, offset=offset))
                res = get("%s?%s" % (base, q)).get("results", [])
                raw += len(res)
                for rec in res:
                    publics[str(rec.get("precisions_public"))] += 1
                    ev = ods_event(rec, src)
                    if ev:
                        out.append(ev)
                if len(res) < 100:
                    break
                offset += 100
            print("Lus : %d, retenus : %d" % (raw, len(out)))
            print("Valeurs de precisions_public :", dict(publics.most_common(12)))
            return out
        except Exception as e:
            last = e
            print("Essai sans succès (%s) : %s" % (params or "sans filtre", e))
    raise last


# ---------- OpenAgenda (agenda de Nantes Métropole, flux RSS officiel) ----------
def rss_items(xml_bytes):
    items = []
    for it in ET.fromstring(xml_bytes).iter("item"):
        d = {}
        for ch in it:
            k = ch.tag.split("}")[-1].lower()
            d.setdefault(k, []).append((ch.text or "").strip() or " ".join(ch.attrib.values()))
        items.append({k: " | ".join(v) for k, v in d.items()})
    return items


def dates_of(rec):
    out = set()
    for k, v in rec.items():
        if k in ("link", "guid"):
            continue
        out.update(re.findall(r"\d{4}-\d{2}-\d{2}", v))
    for k in ("title", "description"):
        t = plain(rec.get(k))
        for j, m, a in re.findall(r"(\d{1,2})(?:er)?\s+(%s)\s+(\d{4})" % "|".join(MOIS), t):
            out.add("%s-%02d-%02d" % (a, MOIS[m], int(j)))
    return sorted(out)


def rss_event(rec):
    titre = clean(rec.get("title"))
    start, end = iso(rec.get("startdate")), iso(rec.get("enddate"))
    if not start:
        ds = [d for d in dates_of(rec) if d >= TODAY]
        start, end = (ds[0], ds[-1]) if ds else (None, None)
    end = end or start
    if not titre or not start or end < TODAY:
        return None
    blob = " ".join(str(v) for v in rec.values())
    pb = plain(blob)
    lieu = clean(rec.get("location"))
    ville = next((v for v in VILLES if plain(v) in plain(lieu)), None)
    if not ville or not KIDS.search(plain(titre + " " + str(rec.get("description") or ""))):
        return None
    if "expo" not in pb and date.fromisoformat(end) - date.fromisoformat(start) > timedelta(days=45):
        end = start
    link = rec.get("link") or ""
    ev = {"n": titre[:120], "w": lieu[:90], "d": clean(rec.get("description"))[:240], "start": start, "end": end,
          "ages": ages_from(blob), "lieu": "mixte", "prix": "gratuit" if "gratuit" in pb else "inconnu",
          "url": link if link.startswith(("http://", "https://")) else None}
    try:
        ev["lat"], ev["lon"] = float(rec["lat"]), float(rec["long"])
    except (KeyError, ValueError):
        pass
    return ev


def fetch_rss(src):
    deadline = time.time() + 90
    items = []
    for style in ("size=300&from=%d", "from=%d"):
        items, seen, pos = [], set(), 0
        for _ in range(6):
            if time.time() > deadline:
                print("Temps limite atteint, on s'arrête là.")
                break
            t0 = time.time()
            try:
                got = rss_items(get(src["url"] + "&" + style % pos, raw=True))
            except Exception as e:
                print("Requête en échec (%s) : %s" % (style % pos, e))
                break
            print("  requête %s : %d éléments en %.1f s" % (style % pos, len(got), time.time() - t0))
            new = [i for i in got if (i.get("guid") or i.get("link")) not in seen]
            if not new:
                break
            seen.update(i.get("guid") or i.get("link") for i in new)
            items += new
            pos += len(new)
            time.sleep(1)
        print("Méthode %s : %d éléments" % (style.split("=")[0], len(items)))
        if len(items) > 20 or time.time() > deadline:
            break
    if not items:
        raise RuntimeError("flux indisponible")
    print("Éléments dans le flux : %d" % len(items))
    print("Champs du premier élément :", sorted(items[0].keys()))
    out = [e for e in map(rss_event, items) if e]
    print("Retenus (commune + enfants + date) : %d" % len(out))
    for e in out[:5]:
        print("  -", e["start"], e["n"][:50], "|", e["w"][:40])
    return out


def main():
    events, ok = [], 0
    for src in SOURCES:
        try:
            got = fetch_ods(src) if src["type"] == "ods" else fetch_rss(src)
            print("%s : %d événements" % (src["nom"], len(got)))
            events += got
            ok += 1
        except Exception as e:
            print("ÉCHEC pour %s : %s" % (src["nom"], e))
    if not ok:
        print("Aucune source disponible : l'ancien fichier est conservé.")
        return
    seen, uniq = set(), []
    for e in sorted(events, key=lambda e: (e["start"], e["n"])):
        k = (e["n"], e["start"], e["w"])
        if k not in seen:
            seen.add(k)
            uniq.append(e)
    os.makedirs("data", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "events": uniq[:600]}, f, ensure_ascii=False, indent=1)
    print("Écrit : %d événements" % min(len(uniq), 600))


if __name__ == "__main__":
    sys.exit(main())
