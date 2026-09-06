"""Post-process the snake SVGs that Platane/snk generates.

Two jobs:

1. Crop the viewBox to the real content. snk emits viewBox="-16 -32 W H";
   that -32 of headroom exists only so the snake can park its segments one
   row ABOVE the grid while idle (keyframe: translate(0,-16px)). That parked
   row is what reads as "the snake is outside the grid". Cropping the top to
   y=0 clips it. The height is derived from the actual rect extents rather
   than a fixed trim, because the progress bar below the grid (y=144) has to
   survive the crop.

2. Animate the snake colour through a neon cycle, with a glow that tracks
   whichever colour it currently is.

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

RECT = re.compile(r"<rect\b[^>]*>")
report = []


def log(msg):
    print(msg)
    report.append(msg)


def attr(rect, name, default):
    m = re.search(r'\b%s="(-?[\d.]+)"' % name, rect)
    return float(m.group(1)) if m else default


def content_extent(svg):
    """Rightmost/bottommost edge of every <rect>, or None if there are none."""
    maxx = maxy = 0.0
    found = False
    for rect in RECT.findall(svg):
        found = True
        maxx = max(maxx, attr(rect, "x", 0.0) + attr(rect, "width", 12.0))
        maxy = max(maxy, attr(rect, "y", 0.0) + attr(rect, "height", 12.0))
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
        ".s{filter:drop-shadow(0 0 2.5px var(--cs))}" % (colours[0], stops)
    )


def main():
    if not DIST.is_dir():
        log("ERROR: dist/ does not exist - did the snk step run?")
        return 1

    svgs = sorted(DIST.glob("*.svg"))
    log("found %d svg(s): %s" % (len(svgs), [p.name for p in svgs]))
    if not svgs:
        log("ERROR: no SVGs to process")
        return 1

    failures = 0
    for path in svgs:
        try:
            svg = path.read_text(encoding="utf-8")
            before = re.search(r'viewBox="([^"]*)"', svg)
            before = before.group(1) if before else "(none)"

            extent = content_extent(svg)
            if extent is None:
                log("%s: WARNING no <rect> found, leaving viewBox %s" % (path.name, before))
            else:
                w, h = math.ceil(extent[0]) + 1, math.ceil(extent[1]) + 1
                svg = re.sub(r'viewBox="[^"]*"', 'viewBox="0 0 %d %d"' % (w, h), svg, count=1)
                svg = re.sub(
                    r'width="[\d.]+"\s+height="[\d.]+"',
                    'width="%d" height="%d"' % (w, h),
                    svg,
                    count=1,
                )
                log("%s: viewBox %s -> 0 0 %d %d" % (path.name, before, w, h))

            colours = PALETTES["dark" if "dark" in path.name else "light"]
            if "</style>" in svg:
                svg = svg.replace("</style>", neon_css(colours) + "</style>", 1)
                log("%s: %d-colour neon cycle + glow" % (path.name, len(colours)))
            else:
                log("%s: WARNING no </style>, skipped colour animation" % path.name)

            path.write_text(svg, encoding="utf-8")
        except Exception as exc:  # keep going; the report records what broke
            failures += 1
            log("%s: ERROR %s: %s" % (path.name, type(exc).__name__, exc))

    # The report rides along to the output branch, which is the only way to see
    # what happened here without admin rights on the Actions logs.
    (DIST / "_polish-report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
