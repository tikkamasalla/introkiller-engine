"""Resolve show slugs to AnimeThemes OP/ED ogg URLs, over GraphQL.

The JSON:API is deprecated, so this module posts to the GraphQL endpoint at
https://graphql.animethemes.moe/ (limit: 90 requests per minute) and keeps a
1.2 s gap between requests. Only the requested show is ever fetched.
"""
import json
import time
import urllib.request

from .settings import API_DELAY_S, MAX_CAND, UA

GRAPHQL = "https://graphql.animethemes.moe/"

SHOW_SLUGS = {
    "beelz": "beelzebub",
    "humanity": "jinrui_wa_suitai_shimashita",
    "haibane": "haibane_renmei",
    "bloodc": "blood_c",
    "lain": "serial_experiments_lain",
    "planetes": "planetes",
    "ideon": "densetsu_kyojin_ideon",
    "glt": "shoujo_shuumatsu_ryokou",
    "gundam": "mobile_suit_gundam",
    "mononoke": "mononoke",
    "conan": "detective_conan",
    "zipang": "zipang",
    "hellgirl": "jigoku_shoujo",
    "bloodplus": "blood",
    "tex": "texhnolyze",
    "logh": "ginga_eiyuu_densetsu_die_neue_these_kaikou",
    "ragnarok": "shuumatsu_no_walkure",
}

ANIME_QUERY = """query($slug: String!) { anime(slug: $slug) {
  slug title { romaji }
  animethemes { type sequence slug
    animethemeentries { episodes videos { nodes { audio { link size } } } } } } } }"""

ANILIST_QUERY = """query($id: [Int!]) { findAnimeByExternalSite(site: ANILIST, id: $id) {
  slug title { romaji } } }"""


def _post(query, variables):
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(GRAPHQL, data=body,
                                 headers={"Content-Type": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def _themes_of(node):
    out = []
    for t in node.get("animethemes", []) or []:
        for e in t.get("animethemeentries", []) or []:
            nodes = ((e.get("videos") or {}).get("nodes")) or []
            if not nodes or not nodes[0].get("audio"):
                continue
            out.append({
                "type": t["type"], "sequence": t["sequence"], "slug": t["slug"],
                "episodes": e.get("episodes"), "audio": nodes[0]["audio"]["link"],
                "size": nodes[0]["audio"].get("size"),
            })
    return out


def fetch_anime(slug):
    d = _post(ANIME_QUERY, {"slug": slug})["data"]["anime"]
    return {"slug": slug, "id": None, "name": (d.get("title") or {}).get("romaji"),
            "themes": _themes_of(d)}


def slug_for_anilist(external_id):
    d = _post(ANILIST_QUERY, {"id": [external_id]})["data"]["findAnimeByExternalSite"]
    return [a["slug"] for a in d or [] if a.get("slug")]


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--anilist", type=int, default=None)
    ap.add_argument("--slug", default=None)
    ap.add_argument("--show", default=None)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    if a.slug:
        slugs = [a.slug]
    elif a.show:
        slugs = [SHOW_SLUGS[a.show]]
    elif a.anilist is not None:
        slugs = slug_for_anilist(a.anilist)
        if not slugs:
            raise SystemExit("no slug maps to external id %s" % a.anilist)
    else:
        slugs = sorted(set(SHOW_SLUGS.values()))
    man = {}
    for i, slug in enumerate(slugs):
        if i:
            time.sleep(API_DELAY_S)
        man[slug] = fetch_anime(slug)
    json.dump(man, open(a.out, "w", encoding="utf-8"), indent=1)
    n = sum(len(v["themes"]) for v in man.values())
    print("slugs=%d themes=%d -> %s" % (len(man), n, a.out))


if __name__ == "__main__":
    main()
