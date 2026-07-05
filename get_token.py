#!/usr/bin/env python3
"""Helper: turn a short-lived User token into long-lived PAGE tokens + IDs,
ready to paste into secrets.env.

What you still do by hand (2 min, can't be automated — needs your login):
  1. developers.facebook.com -> create an App (type: Business). Note the App ID
     and App Secret (Settings -> Basic).
  2. Tools -> Graph API Explorer -> pick your app -> add permissions:
     pages_show_list, pages_read_engagement, pages_manage_posts, publish_video
     -> "Generate Access Token" -> copy the (short-lived) USER token.

Then run:
  python3 get_token.py <APP_ID> <APP_SECRET> <SHORT_LIVED_USER_TOKEN>

It prints, for every Page you admin, the long-lived Page token + Page ID and the
matching secrets.env keys. Page tokens derived this way effectively don't expire.
"""
import json
import sys
import urllib.parse
import urllib.request

GRAPH = "https://graph.facebook.com/v21.0"


def _get(path, params):
    url = "%s/%s?%s" % (GRAPH, path, urllib.parse.urlencode(params))
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read().decode())


def main():
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    app_id, app_secret, short_token = sys.argv[1:4]

    # 1) short-lived USER token -> long-lived USER token
    longed = _get("oauth/access_token", {
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": app_secret,
        "fb_exchange_token": short_token,
    })
    user_token = longed["access_token"]

    # 1b) verify the required permissions are actually granted
    REQUIRED = {"pages_manage_posts", "publish_video",
                "pages_read_engagement", "pages_show_list"}
    perms = _get("me/permissions", {"access_token": user_token}).get("data", [])
    granted = {p["permission"] for p in perms if p.get("status") == "granted"}
    missing = REQUIRED - granted
    if missing:
        print("!! MISSING PERMISSIONS: %s" % ", ".join(sorted(missing)))
        print("!! In Graph API Explorer, add these, click Generate Access Token,")
        print("!! approve them (and toggle your Page ON in the consent popup), then")
        print("!! re-run this with the NEW user token.\n")

    # 2) list Pages; each comes with a long-lived PAGE token
    accounts = _get("me/accounts", {"access_token": user_token})
    pages = accounts.get("data", [])
    if not pages:
        print("No Pages found for this user. Make sure you admin a Page and "
              "granted pages_show_list.")
        return

    print("\n# ==== paste the relevant lines into secrets.env ====\n")
    for pg in pages:
        name = pg.get("name", "?")
        pid = pg.get("id", "")
        ptoken = pg.get("access_token", "")
        key = name.upper().replace("&", "AND").replace(" ", "_")
        key = "".join(c for c in key if c.isalnum() or c == "_")
        print("# Page: %s" % name)
        print("%s_PAGE_ID=%s" % (key, pid))
        print("%s_TOKEN=%s\n" % (key, ptoken))

    print("# NOTE: the key above is derived from the Page NAME. Match it to your")
    print("# channel id in channels.json (e.g. 'Donghua Decoded' -> DONGHUA_DECODED_*).")


if __name__ == "__main__":
    main()
