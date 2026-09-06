"""Post-process the snake SVGs that Platane/snk generates.

snk's snake does not stay on the contribution grid: it slides in from a
staging row ABOVE the grid at the start of each loop and exits back up to it
at the end (keyframes at y=-16). It also leaves ~34px of dead space between
the grid and the progress bar underneath.

Cropping the viewBox alone is not enough — it hides the snake's body but not
its drop-shadow, which bleeds back over the top edge as a smear. So instead
of hiding the off-grid motion, this clamps it away:

1. Every snake keyframe with a negative y is pulled to y=0, so the snake
   enters and leaves along the top row and is never outside the grid.
2. The progress bar is moved up to sit just under the grid.
3. The viewBox is cropped to real content, with a few px of padding so the
   neon glow has room and never clips.
4. The snake colour cycles through a neon palette, with a glow that tracks it.

Run from the repo root, after snk has written into dist/.
"""

import math
import pathlib
import re
import sys

DIST = pathlib.Path("dist")

# Bright neon on dark; deeper tones on light so the snake stays visible on white.
PALETTES = {
    "dark": ["#00F5D4", "#7DF9FF", "#A855F7", "#F72585", "#FFD60A"],
    "light": ["#7C3AED", "#0891B2", "#C026D3", "#DB2777", "#4F46E5"],
}

GAP_UNDER_GRID = 8  # px between the grid's bottom row and the progress bar
PAD = 3             # px of breathing room so the glow never clips

RECT = re.compile(r"<rect\b[^>]*>")
TRANSLATE = re.compile(r"translate\((-?[\d.]+)px,\s*(-?[\d.]+)px\)")

report = []


def log(msg):
    print(msg)
    report.append(msg)


def attr(tag, name, default):
    m = re.search(r'\b%s="(-?[\d.]+)"' % name, tag)
    return float(m.group(1)) if m else default


def clamp_snake_onto_grid(svg):
    """Pull every off-grid snake keyframe (y<0) down onto the top row."""
    moved = [0]

    def fix(m):
        x, y = float(m.group(1)), float(m.group(2))
        if y < 0:
            moved[0] += 1
            y = 0.0
        return "translate(%gpx,%gpx)" % (x, y)

    return TRANSLATE.sub(fix, svg), moved[0]


def grid_bottom(svg):
    """Bottom edge of the contribution grid (ignores the progress bar)."""
    bottom = 0.0
    for tag in RECT.findall(svg):
        if re.search(r'class="c(?:\s|")', tag):
            bottom = max(bottom, attr(tag, "y", 0.0) + attr(tag, "height", 12.0))
    return bottom


def move_progress_bar(svg, target_y):
    """Slide the .u bar rects up so there is no dead band under the grid."""
    moved = [0]

    def fix(m):
        tag = m.group(0)
        if not re.search(r'class="u(?:\s|")', tag):
            return tag
        moved[0] += 1
        return re.sub(r'\by="[-\d.]+"', 'y="%g"' % target_y, tag)

    return RECT.sub(fix, svg), moved[0]


def content_extent(svg):
    maxx = maxy = 0.0
    found = False
    for tag in RECT.findall(svg):
        found = True
        maxx = max(maxx, attr(tag, "x", 0.0) + attr(tag, "width", 12.0))
        maxy = max(maxy, attr(tag, "y", 0.0) + attr(tag, "height", 12.0))
    return (maxx, maxy) if found and maxx > 0 and maxy > 0 else None


def neon_css(colours):
    ring = colours + [colours[0]]
    stops = "".join(
        "%d%%{--cs:%s}" % (round(i * 100 / (len(ring) - 1)), c)
        for i, c in enumerate(ring)
    )
    # "&lt;color&gt;", never "<color>". An .svg is parsed as XML, so a literal
    # "<" inside <style> closes the element and breaks the entire image. The
    # XML parser decodes the entity back to "<" before the CSS parser sees it,
    # so @property still registers and the colour interpolates smoothly.
    return (
        "@property --cs{syntax:'&lt;color&gt;';inherits:true;initial-value:%s}"
        "svg{animation:csx 6s linear infinite}"
        "@keyframes csx{%s}"
        ".s{filter:drop-shadow(0 0 2.5px var(--cs))}"
        "@media (prefers-reduced-motion:reduce){svg{animation:none}}" % (colours[0], stops)
    )


def polish(path):
    svg = path.read_text(encoding="utf-8")
    before = re.search(r'viewBox="([^"]*)"', svg)
    before = before.group(1) if before else "(none)"

    svg, clamped = clamp_snake_onto_grid(svg)
    log("%s: clamped %d off-grid keyframe(s) onto the grid" % (path.name, clamped))

    gb = grid_bottom(svg)
    if gb:
        svg, bars = move_progress_bar(svg, gb + GAP_UNDER_GRID)
        log("%s: grid bottom %g, moved %d bar rect(s) to y=%g"
            % (path.name, gb, bars, gb + GAP_UNDER_GRID))

    extent = content_extent(svg)
    if extent is None:
        log("%s: WARNING no <rect> found, leaving viewBox %s" % (path.name, before))
    else:
        w = math.ceil(extent[0]) + 2 * PAD
        h = math.ceil(extent[1]) + 2 * PAD
        svg = re.sub(r'viewBox="[^"]*"',
                     'viewBox="%d %d %d %d"' % (-PAD, -PAD, w, h), svg, count=1)
        svg = re.sub(r'width="[\d.]+"\s+height="[\d.]+"',
                     'width="%d" height="%d"' % (w, h), svg, count=1)
        log("%s: viewBox %s -> %d %d %d %d" % (path.name, before, -PAD, -PAD, w, h))

    colours = PALETTES["dark" if "dark" in path.name else "light"]
    if "</style>" in svg:
        svg = svg.replace("</style>", neon_css(colours) + "</style>", 1)
        log("%s: %d-colour neon cycle + glow" % (path.name, len(colours)))
    else:
        log("%s: WARNING no </style>, skipped colour animation" % path.name)

    path.write_text(svg, encoding="utf-8")


def main():
    if not DIST.is_dir():
        log("ERROR: dist/ does not exist - did the snk step run?")
        return 1

    svgs = sorted(p for p in DIST.glob("*.svg") if "snake" in p.name)
    log("found %d snake svg(s): %s" % (len(svgs), [p.name for p in svgs]))
    if not svgs:
        log("ERROR: no snake SVGs to process")
        return 1

    failures = 0
    for path in svgs:
        try:
            polish(path)
        except Exception as exc:
            failures += 1
            log("%s: ERROR %s: %s" % (path.name, type(exc).__name__, exc))

    # The report rides along to the output branch, which is the only way to see
    # what happened here without admin rights on the Actions logs. Never let a
    # failure to write it mask the real error above.
    try:
        (DIST / "_polish-report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    except Exception as exc:
        print("could not write report: %s: %s" % (type(exc).__name__, exc))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
