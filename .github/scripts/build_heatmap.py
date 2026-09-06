"""Build a themed contribution heatmap, one SVG per colour scheme.

ghchart.rshah.org hardcodes empty days to #EEEEEE and its labels to #767676,
with no way to change either. On a dark page that turns the whole chart into
a pale grey slab - which is exactly the "dull" problem this replaces.

Contribution data comes from the public endpoint GitHub already serves for
the profile calendar (no token required):

    https://github.com/users/<login>/contributions

Writes dist/github-heatmap.svg (light) and dist/github-heatmap-dark.svg.
"""

import datetime as dt
import pathlib
import re
import sys
import urllib.request

DIST = pathlib.Path("dist")
LOGIN = sys.argv[1] if len(sys.argv) > 1 else "Xender007"

CELL, GAP = 10, 2
PITCH = CELL + GAP
PAD_L, PAD_T = 30, 16   # gutters for day / month labels
PAD_R, PAD_B = 6, 6

THEMES = {
    "light": {
        "file": "github-heatmap.svg",
        "levels": ["#EBEDF0", "#DDD6FE", "#A78BFA", "#7C3AED", "#5B21B6"],
        "label": "#57606A",
        "glow": "#5B21B6",
    },
    "dark": {
        "file": "github-heatmap-dark.svg",
        "levels": ["#161B22", "#3C1E5E", "#6D28D9", "#A855F7", "#00F5D4"],
        "label": "#8B949E",
        "glow": "#00F5D4",
    },
}

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def fetch_days(login):
    url = "https://github.com/users/%s/contributions" % login
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "ignore")

    days = []
    # Attribute order is not guaranteed, so pull them out of each tag separately.
    for tag in re.findall(r"<(?:td|rect)\b[^>]*data-date[^>]*>", html):
        d = re.search(r'data-date="(\d{4}-\d{2}-\d{2})"', tag)
        lvl = re.search(r'data-level="(\d+)"', tag)
        if d and lvl:
            days.append((dt.date.fromisoformat(d.group(1)), int(lvl.group(1))))
    days.sort()
    return days


def build(days, theme):
    cfg = THEMES[theme]
    first = days[0][0]
    # GitHub's calendar columns start on Sunday.
    origin = first - dt.timedelta(days=(first.weekday() + 1) % 7)

    cells, months, seen = [], [], set()
    max_week = 0
    for date, level in days:
        week = (date - origin).days // 7
        dow = (date.weekday() + 1) % 7
        max_week = max(max_week, week)
        x = PAD_L + week * PITCH
        y = PAD_T + dow * PITCH
        # Stagger the pulse so contributions cascade rather than blink in unison.
        delay = (week * 0.11) % 3
        cls = "c l%d" % level
        cells.append(
            '<rect class="%s" x="%d" y="%d" width="%d" height="%d" rx="2" '
            'style="animation-delay:-%.2fs"><title>%s - %s</title></rect>'
            % (cls, x, y, CELL, CELL, delay, date.isoformat(),
               "no contributions" if level == 0 else "level %d" % level)
        )
        if date.day <= 7 and date.month not in seen:
            seen.add(date.month)
            months.append('<text class="lbl" x="%d" y="11">%s</text>'
                          % (x, MONTHS[date.month - 1]))

    for dow, name in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        y = PAD_T + dow * PITCH + CELL - 1
        months.append('<text class="lbl" x="0" y="%d">%s</text>' % (y, name))

    w = PAD_L + (max_week + 1) * PITCH + PAD_R
    h = PAD_T + 7 * PITCH + PAD_B

    fills = "".join(".l%d{fill:%s}" % (i, c) for i, c in enumerate(cfg["levels"]))
    # Animate opacity, not filter, and only on days that actually have
    # contributions. A brightness sweep over every cell washes the pale light
    # theme out to white on a white page, and setting filter here would also
    # clobber the level-4 glow below.
    style = (
        ".c{shape-rendering:geometricPrecision}"
        + fills
        + ".l1,.l2,.l3,.l4{animation:pulse 3s ease-in-out infinite}"
        + ".l4{filter:drop-shadow(0 0 2px %s)}" % cfg["glow"]
        + ".lbl{fill:%s;font:9px -apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif}"
          % cfg["label"]
        + "@keyframes pulse{0%,100%{opacity:1}50%{opacity:.55}}"
        + "@media (prefers-reduced-motion:reduce){.l1,.l2,.l3,.l4{animation:none}}"
    )

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'viewBox="0 0 %d %d" role="img" aria-label="Contribution heatmap">'
        "<title>Contribution heatmap</title><style>%s</style>%s%s</svg>\n"
        % (w, h, w, h, style, "".join(months), "".join(cells))
    )


def main():
    DIST.mkdir(exist_ok=True)
    days = fetch_days(LOGIN)
    if not days:
        print("ERROR: parsed 0 days from the contributions endpoint")
        return 1
    active = sum(1 for _, l in days if l > 0)
    print("%s: %d days, %d with contributions" % (LOGIN, len(days), active))

    for theme in THEMES:
        svg = build(days, theme)
        out = DIST / THEMES[theme]["file"]
        out.write_text(svg, encoding="utf-8")
        print("  wrote %s (%d bytes)" % (out.name, len(svg)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
