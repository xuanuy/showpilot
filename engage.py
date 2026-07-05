#!/usr/bin/env python3
"""Daily engagement helper (manual posting — NO automation, NO bots).

Prints today's batch of genuine comment starters + a short checklist. You open
Facebook yourself, find real donghua reels/posts, ADAPT a line to fit, and post it
by hand. This keeps engagement authentic (real you, real participation) while saving
you the "what do I even say" friction.

Usage:
  python3 engage.py [N]      # N = how many comments to surface (default 6)

The set rotates by date so you cycle through the whole bank without repeating.
"""
import datetime
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
BANK = os.path.join(ROOT, "engagement", "comment_bank.json")


def flatten(categories):
    """Round-robin across categories so a contiguous slice spans many series."""
    items = list(categories.items())
    maxlen = max(len(v) for _, v in items)
    flat = []
    for i in range(maxlen):
        for name, comments in items:
            if i < len(comments):
                flat.append((name, comments[i]))
    return flat


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    with open(BANK, encoding="utf-8") as f:
        bank = json.load(f)
    flat = flatten(bank["categories"])
    total = len(flat)
    n = min(n, total)

    today = datetime.date.today()
    start = (today.toordinal() * n) % total
    picks = [flat[(start + i) % total] for i in range(n)]

    print("=" * 64)
    print(" DAILY ENGAGEMENT PLAN  -  %s" % today.isoformat())
    print("=" * 64)
    print("""
TODAY'S 15 MINUTES (do it from your REAL account, by hand):
  [ ] Reply to every new comment on your own Pages first
  [ ] Find %d trending donghua/xianxia reels from OTHER creators
  [ ] Leave a genuine comment on each (adapt a starter below)
  [ ] Pop into 1 donghua Facebook Group, answer/start one thread
  RULE: adapt each line to the actual video. Never paste identically. No links.
""" % n)
    print("-" * 64)
    print(" COMMENT STARTERS (edit before posting):")
    print("-" * 64)
    for i, (cat, text) in enumerate(picks, 1):
        print("\n%d. [%s]\n   %s" % (i, cat.replace("_", " "), text))
    print("\n" + "-" * 64)
    print("Need fresh/specific ones? Ask Claude: \"write 5 comments for <reel topic>\".")


if __name__ == "__main__":
    main()
