#!/usr/bin/env python3
"""
Bokutachi IR Tracker — Daily BMS Score / Lamp / BP Change Summary.
Read-only. Uses session API (deltas + isNewScore) and PB composedFrom
for accurate improvement detection. No cache needed.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests

API_BASE = "https://boku.tachi.ac/api/v1"
DEFAULT_GAMES = ["bms-7k", "bms-14k"]
CACHE_DIR = Path.home() / ".bokutachi_tracker"

LAMP_ORDER = [
    "NO PLAY", "FAILED", "ASSIST CLEAR", "EASY CLEAR",
    "CLEAR", "HARD CLEAR", "EX HARD CLEAR", "FULL COMBO",
]
LAMP_DISPLAY = [
    "FULL COMBO", "EX HARD CLEAR", "HARD CLEAR", "CLEAR",
    "EASY CLEAR", "ASSIST CLEAR", "FAILED",
]
LAMP_COLOR = {
    "FULL COMBO": "#ff79c6",
    "EX HARD CLEAR": "#f0c040",
    "HARD CLEAR": "#f0f6fc",
    "CLEAR": "#58a6ff",
    "EASY CLEAR": "#7ee83e",
    "ASSIST CLEAR": "#c084fc",
    "FAILED": "#f85149",
}
_TABLE_PRIORITY = {"st": 0, "sl": 1, "★": 2, "重発狂": 3}

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "BokutachiIR-Tracker/1.0 (daily personal use; read-only)"
SESSION.headers["Accept"] = "application/json"


def _api_get(url, timeout=30):
    resp = SESSION.get(url, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(f"API: {data.get('description')}")
    return data["body"]


def find_user(username):
    body = _api_get(f"{API_BASE}/users?search={requests.utils.quote(username)}")
    users = body if isinstance(body, list) else body.get("users", body)
    wanted = username.strip().lower()
    for u in users:
        if u.get("username", "").lower() == wanted:
            return u["id"], u["username"]
        if u.get("usernameLowercase", "") == wanted:
            return u["id"], u["username"]
    return None


def _table_info(chart):
    folders = chart.get("data", {}).get("tableFolders", {})
    sgl = chart.get("data", {}).get("sglEC")
    best_prio, best_level, labels = 99, 0, []
    for key, val in folders.items():
        try: lv = int(val)
        except (ValueError, TypeError): lv = 0
        prio = _TABLE_PRIORITY.get(key, 90)
        if prio < best_prio or (prio == best_prio and lv > best_level):
            best_prio, best_level = prio, lv
        labels.append(f"{key.replace('重発狂','重')}{val}")
    def _lp(lbl):
        for p in ["st","sl","★","重"]:
            if lbl.startswith(p):
                return _TABLE_PRIORITY.get("重発狂" if p=="重" else p, 90)
        return 99
    labels.sort(key=lambda l: (_lp(l), l))
    label = " ".join(labels) if labels else (f"▼{sgl:.2f}" if sgl else "")
    return (best_prio, -best_level, -(sgl or 0)), label


def _date_window(date_str):
    d = datetime.strptime(date_str, "%Y-%m-%d") if date_str else datetime.now()
    start = d.replace(hour=0, minute=0, second=0, microsecond=0)
    start_ms = int(start.timestamp() * 1000)
    return start_ms, start_ms + 86400000


def _hdr(text):
    print(f"\n{'─' * 60}\n  {text}\n{'─' * 60}")


def _pe(idx, e, ml, mb, me, indent="  "):
    parts = [e["title"]]
    if e.get("artist"): parts.append(f"({e['artist']})")
    if e.get("table_label"): parts.append(f"[{e['table_label']}]")
    if e.get("notecount"): parts.append(f"★{e['notecount']}")
    parts.append(f"@ {e['time']}")
    badges = []
    if ml: badges.append("LAMP")
    if mb: badges.append("BP↓")
    if me: badges.append("EX↑")
    if badges: parts.append("[" + ",".join(badges) + "]")
    print(f"{indent}{idx:>3}. {' '.join(parts)}")
    bp_s = f", BP: {e['bp']}" if e["bp"] is not None else ""
    g_s = f" [{e['gauge']}]" if e.get("gauge") and e["gauge"] != "NORMAL" else ""
    print(f"{indent}     Lamp: {e['lamp']}, EX: {e['ex']} ({e['pct']:.2f}%){bp_s}{g_s}")


def run(game, user_id, date_str, image_path=None, image_mode=None):
    label = date_str or datetime.now().strftime("%Y-%m-%d")
    start_ms, end_ms = _date_window(date_str)

    # 1. Session list → filter by date
    try:
        sess_list = _api_get(
            f"{API_BASE}/users/{user_id}/games/{game}/sessions/recent")
    except requests.HTTPError as e:
        if e.response.status_code == 404: return False
        raise
    except Exception as e:
        print(f"\n{game}: {e}"); return False

    target = [ses for ses in (sess_list if isinstance(sess_list, list) else [])
              if start_ms <= ses.get("timeStarted", 0) < end_ms]

    if not target:
        print(f"\n{game}: No sessions on {label}.")
        return False

    # 2. Session details + PBs
    all_entries = []
    all_chart_ids = set()
    for ses in target:
        try:
            detail = _api_get(f"{API_BASE}/sessions/{ses['sessionID']}")
        except Exception:
            continue
        sindex = detail.get("index", "?")
        sname = detail.get("session", {}).get("name", "?")
        charts = {c["chartID"]: c for c in detail.get("charts", [])}
        score_info = {si["scoreID"]: si for si in detail.get("scoreInfo", [])}

        entries = []
        for s in detail.get("scores", []):
            sd = s.get("scoreData", {})
            cid = s["chartID"]
            all_chart_ids.add(cid)
            chart = charts.get(cid, {})
            song = chart.get("song", {})
            ta = s.get("timeAchieved")
            si = score_info.get(s.get("scoreID", ""), {})
            is_new = si.get("isNewScore", False)
            deltas = si.get("deltas", {})
            sort_key, table_label = _table_info(chart)

            lamp_ok = deltas.get("lamp", 0) > 0 and sd.get("lamp", "?") not in (
                "NO PLAY", "FAILED", "?")
            ex_ok = deltas.get("score", 0) > 0
            bp_ok = False

            if is_new and not deltas:
                lamp_val = sd.get("lamp", "?")
                if lamp_val not in ("NO PLAY", "FAILED", "?"):
                    lamp_ok = True
                if sd.get("optional", {}).get("bp") is not None:
                    bp_ok = True
                if sd.get("score", 0) > 0:
                    ex_ok = True

            entries.append(dict(
                title=song.get("title", cid),
                artist=song.get("artist", ""),
                notecount=chart.get("data", {}).get("notecount", 0),
                table_label=table_label, sort_key=sort_key,
                lamp=sd.get("lamp", "?"), ex=sd.get("score", 0),
                pct=sd.get("percent", 0),
                bp=sd.get("optional", {}).get("bp"),
                gauge=s.get("scoreMeta", {}).get("gauge", ""),
                time=datetime.fromtimestamp(ta / 1000).strftime("%H:%M") if ta else "",
                lamp_ok=lamp_ok, bp_ok=bp_ok, ex_ok=ex_ok,
                chartID=cid, scoreID=s.get("scoreID", ""),
            ))
        all_entries.append((sindex, sname, entries))

    if not all_entries:
        print(f"\n{game}: No data on {label}.")
        return False

    # 3. PBs → composedFrom for additional detail
    pb_map = {}
    try:
        pbs_data = _api_get(f"{API_BASE}/users/{user_id}/games/{game}/pbs/all")
        for pb in pbs_data.get("pbs", []):
            comp = {}
            for c in pb.get("composedFrom", []):
                comp[c["scoreID"]] = c.get("name", "")
            pb_map[pb["chartID"]] = comp
    except Exception:
        pass

    for _, _, entries in all_entries:
        for e in entries:
            comp = pb_map.get(e["chartID"], {})
            name = comp.get(e.get("scoreID", ""), "")
            if "Lamp" in name and e["lamp"] not in ("NO PLAY", "FAILED", "?"):
                e["lamp_ok"] = True
            if "BP" in name or "bp" in name.lower(): e["bp_ok"] = True
            if "Score" in name: e["ex_ok"] = True

    # 4. Deduplicate: per chart, keep only the best for each metric
    def _best(entries, key_fn):
        """Keep only the best entry per chartID according to key_fn."""
        best = {}
        for e in entries:
            cid = e["chartID"]
            if cid not in best or key_fn(e) > key_fn(best[cid]):
                best[cid] = e
        return sorted(best.values(), key=lambda e: e["sort_key"])

    lamp_list = _best(
        [e for _, _, es in all_entries for e in es if e["lamp_ok"]],
        key_fn=lambda e: LAMP_ORDER.index(e["lamp"]) if e["lamp"] in LAMP_ORDER else -1
    )
    bp_list = _best(
        [e for _, _, es in all_entries for e in es if e["bp_ok"]],
        key_fn=lambda e: - (e["bp"] or 99999)
    )
    ex_list = _best(
        [e for _, _, es in all_entries for e in es if e["ex_ok"]],
        key_fn=lambda e: e["ex"]
    )

    total = sum(len(es) for _, _, es in all_entries)

    # Image output
    if image_path and image_mode:
        _render_image(game, label, total, lamp_list, bp_list, ex_list,
                      all_entries, image_path, image_mode)
        return True

    # 5. Display (text mode)
    _hdr(f"{game.upper()} — {label}  ({total} plays)")
    print(f"  ランプ更新: {len(lamp_list)}曲  /  BP更新: {len(bp_list)}曲  /  EX更新: {len(ex_list)}曲")
    all_entries.sort(key=lambda x: -x[0] if isinstance(x[0], int) else 0)
    print(f"\n  ◆ セッション")
    for sindex, sname, entries in all_entries:
        ln = sum(1 for e in entries if e["lamp_ok"])
        bn = sum(1 for e in entries if e["bp_ok"])
        en = sum(1 for e in entries if e["ex_ok"])
        badges = []
        if ln: badges.append(f"Lamp:{ln}")
        if bn: badges.append(f"BP:{bn}")
        if en: badges.append(f"EX:{en}")
        print(f"\n    Session #{sindex}: {sname}"
              + (f"  ({', '.join(badges)})" if badges else ""))
        for j, e in enumerate(entries):
            _pe(j + 1, e, e["lamp_ok"], e["bp_ok"], e["ex_ok"], "      ")

    # Categorized Lamp
    if lamp_list:
        by_lamp = {}
        for e in lamp_list:
            by_lamp.setdefault(e["lamp"], []).append(e)
        print(f"\n  ◆ クリアランプ更新 ({len(lamp_list)})")
        for lv in LAMP_DISPLAY:
            if lv not in by_lamp: continue
            print(f"\n    ── {lv} ──")
            for i, e in enumerate(sorted(by_lamp[lv], key=lambda e: e["sort_key"])):
                _pe(i + 1, e, True, False, False)

    # Categorized BP
    if bp_list:
        print(f"\n  ◆ BP更新 ({len(bp_list)})")
        for i, e in enumerate(sorted(bp_list, key=lambda e: e["sort_key"])):
            _pe(i + 1, e, False, True, False)

    # Categorized EX
    if ex_list:
        print(f"\n  ◆ EX更新 ({len(ex_list)})")
        for i, e in enumerate(sorted(ex_list, key=lambda e: e["sort_key"])):
            _pe(i + 1, e, False, False, True)

    # Image output
    if image_path:
        _render_image(game, label, total, lamp_list, bp_list, ex_list,
                      all_entries, image_path)

    return True


# ── Image output ──────────────────────────────────────────────────────────

CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0d1117;color:#c9d1d9;font-family:-apple-system,"Helvetica Neue",sans-serif;padding:24px;width:780px}
.hdr{background:linear-gradient(135deg,#161b22,#0d1117);border:1px solid #30363d;border-radius:10px;padding:14px 22px;margin-bottom:16px}
.hdr-row{display:flex;align-items:center;justify-content:space-between}
.hdr-left h1{font-size:17px;color:#58a6ff;line-height:1.3}
.hdr-left .sub{font-size:11px;color:#8b949e;line-height:1.3}
.stats{display:flex;gap:8px}
.stat{background:#161b22;border:1px solid #30363d;border-radius:7px;padding:6px 12px;text-align:center;min-width:54px}
.stat .n{font-size:20px;font-weight:700;line-height:1.1}
.stat .l{font-size:9px;color:#8b949e;line-height:1.1;text-transform:uppercase;letter-spacing:0.5px}
.s-lamp .n{color:#f0883e}
.s-bp .n{color:#3fb950}
.s-ex .n{color:#58a6ff}
.sec{font-size:13px;font-weight:600;color:#f0f6fc;margin:18px 0 8px;padding-bottom:4px;border-bottom:1px solid #30363d}
.ses-t{font-size:12px;font-weight:600;color:#8b949e;margin:10px 0 4px}
.ses-b{font-size:10px;color:#484f58;margin-left:6px}
table{width:100%;border-collapse:collapse;font-size:11px;table-layout:fixed}
col.c1{width:260px}
col.c2{width:130px}
col.c3{width:90px}
col.c4{width:56px}
td{padding:2px 6px;border-bottom:1px solid #161b22;vertical-align:top;white-space:nowrap}
.t-title{color:#f0f6fc;font-weight:500;overflow:hidden;text-overflow:ellipsis}
.t-artist{color:#8b949e;font-size:10px;overflow:hidden;text-overflow:ellipsis}
.t-tbl{color:#58a6ff;font-size:10px}
.t-badges{text-align:right}
.t-det{color:#6e7681;font-size:10px;padding-top:0}
.b-lamp{color:#f0883e;font-weight:700;font-size:10px}
.b-bp{color:#3fb950;font-weight:700;font-size:10px}
.b-ex{color:#58a6ff;font-weight:700;font-size:10px}
.lgrp{font-size:11px;font-weight:600;color:#d2a8ff;margin:8px 0 3px;padding-left:6px;border-left:2px solid #d2a8ff}
"""


def _render_image(game, label, total, lamp_list, bp_list, ex_list,
                  all_entries, output_path, mode):
    from playwright.sync_api import sync_playwright

    html = _build_html(game, label, total, lamp_list, bp_list, ex_list,
                       all_entries, mode)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 780, "height": 600})
        page.set_content(html)
        page.wait_for_timeout(800)
        height = page.evaluate("document.body.scrollHeight")
        page.set_viewport_size({"width": 780, "height": height + 20})
        page.screenshot(path=output_path, full_page=True)
        browser.close()

    print(f"\n  Image saved: {output_path}")


def _esc(s):
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _row(title, artist, tbl, badges=""):
    t = f"<td class=\"t-title\">{_esc(title)}</td>"
    a = f"<td class=\"t-artist\">{_esc(artist)}</td>" if artist else "<td></td>"
    tb = f"<td class=\"t-tbl\">{_esc(tbl)}</td>" if tbl else "<td></td>"
    bd = f"<td class=\"t-badges\">{badges}</td>" if badges else "<td></td>"
    return f"<tr>{t}{a}{tb}{bd}</tr>"


def _build_html(game, label, total, lamp_list, bp_list, ex_list,
                all_entries, mode):
    show_sessions = mode in ("all", "sessions")
    show_updates = mode in ("all", "updates", "lamp")

    parts = []

    # ── Header: only show relevant stats ──
    stat_cards = []
    if mode in ("all", "sessions", "updates", "lamp") and lamp_list:
        stat_cards.append(f'<div class="stat s-lamp"><div class="n">{len(lamp_list)}</div><div class="l">Lamp更新</div></div>')
    if mode in ("all", "sessions", "updates") and bp_list:
        stat_cards.append(f'<div class="stat s-bp"><div class="n">{len(bp_list)}</div><div class="l">BP更新</div></div>')
    if mode in ("all", "sessions", "updates") and ex_list:
        stat_cards.append(f'<div class="stat s-ex"><div class="n">{len(ex_list)}</div><div class="l">EX更新</div></div>')

    stats_html = f'<div class="stats">{"".join(stat_cards)}</div>' if stat_cards else ""

    parts.append(f"""<div class="hdr">
<div class="hdr-row">
<div class="hdr-left"><h1>Bokutachi IR Tracker — {_esc(game.upper())}</h1><div class="sub">{label} · {total} plays</div></div>
{stats_html}
</div></div>""")

    # ── Sessions ──
    if show_sessions:
        parts.append('<div class="sec">Sessions</div>')
        ordered = sorted(all_entries, key=lambda x: -x[0] if isinstance(x[0], int) else 0)
        for sindex, sname, entries in ordered:
            ln = sum(1 for e in entries if e["lamp_ok"])
            bn = sum(1 for e in entries if e["bp_ok"])
            en = sum(1 for e in entries if e["ex_ok"])
            bs = []
            if ln: bs.append(f'<span class="b-lamp">Lamp:{ln}</span>')
            if bn: bs.append(f'<span class="b-bp">BP:{bn}</span>')
            if en: bs.append(f'<span class="b-ex">EX:{en}</span>')
            bstr = " ".join(bs)
            parts.append(
                f'<div class="ses-t">Session #{sindex}: {_esc(sname)}'
                f'<span class="ses-b">{bstr}</span></div>'
            )
            rows = ""
            for e in entries:
                ib = []
                if e["lamp_ok"]: ib.append('<span class="b-lamp">L</span>')
                if e["bp_ok"]: ib.append('<span class="b-bp">B</span>')
                if e["ex_ok"]: ib.append('<span class="b-ex">E</span>')
                tbl = f"[{e.get('table_label','')}]" if e.get('table_label') else ""
                rows += _row(e["title"], e.get("artist",""), tbl, "".join(ib))
                bp_s = f", BP: {e['bp']}" if e["bp"] is not None else ""
                rows += (f'<tr><td colspan="4" class="t-det">'
                         f'Lamp: {_esc(e["lamp"])}, EX: {e["ex"]} '
                         f'({e["pct"]:.2f}%){bp_s}</td></tr>')
            parts.append(f'<table><colgroup><col class="c1"><col class="c2"><col class="c3"><col class="c4"></colgroup>{rows}</table>')

    # ── Updates (flat list, sorted by difficulty) ──
    if show_updates:
        if lamp_list:
            parts.append(f'<div class="sec">Lamp Updates ({len(lamp_list)} charts)</div>')
            by_lamp = {}
            for e in lamp_list:
                by_lamp.setdefault(e["lamp"], []).append(e)
            for lv in LAMP_DISPLAY:
                if lv not in by_lamp: continue
                color = LAMP_COLOR.get(lv, "#8b949e")
                if lv == "FULL COMBO":
                    style = (
                        "background:linear-gradient(90deg,#ff79c6,#bd93f9,#8be9fd,"
                        "#50fa7b,#f1fa8c,#ffb86c);-webkit-background-clip:text;"
                        "-webkit-text-fill-color:transparent;"
                        "border-left:2px solid #ff79c6"
                    )
                else:
                    style = f"color:{color};border-left-color:{color}"
                parts.append(f'<div class="lgrp" style="{style}">{_esc(lv)}</div>')
                rows = ""
                for e in sorted(by_lamp[lv], key=lambda e: e["sort_key"]):
                    tbl = f"[{e.get('table_label','')}]" if e.get('table_label') else ""
                    rows += _row(e["title"], e.get("artist",""), tbl)
                    rows += (f'<tr><td colspan="4" class="t-det">'
                             f'Lamp: {_esc(e["lamp"])}, EX: {e["ex"]} '
                             f'({e["pct"]:.2f}%)</td></tr>')
                parts.append(f'<table><colgroup><col class="c1"><col class="c2"><col class="c3"><col class="c4"></colgroup>{rows}</table>')

        if bp_list and mode != "lamp":
            parts.append(f'<div class="sec">BP Updates ({len(bp_list)} charts)</div>')
            rows = ""
            for e in sorted(bp_list, key=lambda e: e["sort_key"]):
                tbl = f"[{e.get('table_label','')}]" if e.get('table_label') else ""
                rows += _row(e["title"], e.get("artist",""), tbl)
                rows += (f'<tr><td colspan="4" class="t-det">'
                         f'BP: {e["bp"]}</td></tr>')
            parts.append(f'<table><colgroup><col class="c1"><col class="c2"><col class="c3"><col class="c4"></colgroup>{rows}</table>')

        if ex_list and mode != "lamp":
            parts.append(f'<div class="sec">EX Updates ({len(ex_list)} charts)</div>')
            rows = ""
            for e in sorted(ex_list, key=lambda e: e["sort_key"]):
                tbl = f"[{e.get('table_label','')}]" if e.get('table_label') else ""
                rows += _row(e["title"], e.get("artist",""), tbl)
                rows += (f'<tr><td colspan="4" class="t-det">'
                         f'EX: {e["ex"]} ({e["pct"]:.2f}%)</td></tr>')
            parts.append(f'<table><colgroup><col class="c1"><col class="c2"><col class="c3"><col class="c4"></colgroup>{rows}</table>')

    body = "".join(parts)
    return f"<!DOCTYPE html><html><head><meta charset=\"utf-8\"><style>{CSS}</style></head><body>{body}</body></html>"


def main():
    p = argparse.ArgumentParser(description="Bokutachi IR Tracker")
    mx = p.add_mutually_exclusive_group()
    mx.add_argument("-u", "--user-id", type=int)
    mx.add_argument("--find-user-id", metavar="USERNAME")
    p.add_argument("--games", nargs="+", default=DEFAULT_GAMES)
    p.add_argument("--today", action="store_true")
    p.add_argument("--date", metavar="YYYY-MM-DD")
    p.add_argument("--image", metavar="OUTPUT.png", help="Generate image (sessions + updates)")
    p.add_argument("--image-sessions", metavar="OUTPUT.png", help="Image: session play log")
    p.add_argument("--image-updates", metavar="OUTPUT.png", help="Image: lamp+BP+EX updates")
    p.add_argument("--image-lamp", metavar="OUTPUT.png", help="Image: lamp updates only")
    args = p.parse_args()

    if args.today and args.date:
        p.error("--today and --date are mutually exclusive.")

    uid = args.user_id
    if args.find_user_id:
        print(f"Searching for '{args.find_user_id}' ...")
        r = find_user(args.find_user_id)
        if r is None:
            print(f"Not found.", file=sys.stderr); return 1
        uid, name = r
        print(f"Found: {name} (ID: {uid})")
    if uid is None:
        p.error("User ID required.")

    if not args.today and not args.date:
        date_str = None  # today
    else:
        date_str = args.date if args.date else None

    for g in args.games:
        img = args.image or args.image_sessions or args.image_updates or args.image_lamp
        img_mode = ("all" if args.image else
                    "sessions" if args.image_sessions else
                    "updates" if args.image_updates else
                    "lamp" if args.image_lamp else None)
        try: run(g, uid, date_str, img, img_mode)
        except Exception as e: print(f"\n{g}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
