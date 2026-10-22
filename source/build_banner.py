"""Build the 12 ft x 2 ft shared shop banner (Shaizy + Boson Studio).

Boson Studio's green and Shaizy's navy blend into each other along a diagonal,
through stacked bands with flowing wavy edges. Logos sit either
side of the merge with their taglines underneath; each brand's contacts sit at
its own outer end.

Print rules this file sticks to, so everything survives flex printing:
- solid colours only (no opacity or transparency anywhere), all inside the
  CMYK gamut of solvent/eco-solvent printers;
- no detail thinner than 3 mm, no dot smaller than 12 mm;
- no filters; all text converted to outlines, so no fonts are needed.

Run with a Python that has fontTools installed:

    python build_banner.py
"""

import math
import re
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

# ---------------------------------------------------------------- content ---

CONTENT = {
    "shaizy": {
        "tagline": "Your passport to possibilities",
        "phone": "0336-5067600",
        "email": "contact@shaizyconsultant.com",
        "website": "shaizyconsultant.com",
    },
    "boson": {
        "tagline": "Software solutions for businesses",
        "phone": "0305-6230514",
        "email": "contact@bosonstudio.com",
        "website": "bosonstudio.com",
    },
}

# ----------------------------------------------------------------- layout ---

# 1 unit = 0.01 inch (0.254 mm), so the canvas is 144 in x 24 in (12 ft x 2 ft).
W, H = 14400, 2400
MID_X, MID_Y = W / 2, H / 2
SHAIZY_ON_LEFT = False          # which brand takes the left half
EDGE = 520                      # outer margin for contact pills (clear of eyelets/hem)
LOGO_CX = 4900                  # logo block centre, mirrored for Boson

TAGLINE_SIZE = 175
TAGLINE_MAX_W = 2650            # both taglines share one size, on one line
TAGLINE_GAP = 170               # logo bottom to tagline cap top
CONTACT_SIZE = 165
PILL_H, PILL_GAP = 300, 90
PILL_MAX_W = 2800

# Wave bands: solid colour bands with wavy edges, stepping from Shaizy navy to
# Boson green. Colours change along BAND_ACROSS; band edges wave along the
# perpendicular. WAVES are (amplitude, wavelength along the band, phase drift
# per unit across, phase); the drift terms must sum below 1 (amplitude/drift)
# so edges never cross.
BAND_COUNT = 18
BAND_ACROSS = (1, 0.45)
WAVES = ((1450, 4000, 2050, 0.0), (260, 1800, 1450, 1.7))
MIN_BAND = 60                   # thinnest any band may get (15 mm)

SHAIZY_GOLD = "#F0AE2E"         # ~C0 M33 Y88 K0
BOSON_GREEN = "#1FAF5A"         # ~C78 M0 Y88 K0; the logo's screen green is out of gamut
PRINT_SAFE = {"#00DC5F": BOSON_GREEN}

THEMES = {
    "dark": {
        # Band colour keyframes, Shaizy side to Boson side; brightest where they meet.
        "bands": [(0, "#14174A"), (0.3, "#2B3090"), (0.42, "#2A46A0"), (0.5, "#1F6290"),
                  (0.58, "#167463"), (0.7, "#0F5747"), (1, "#05261E")],
        "shaizy": {
            "logo": "shaizy/shaizy-logo-dark.svg", "logo_h": 620,
            "trail": SHAIZY_GOLD, "spark": "#F6C35A",
            "text": "#FFFFFF", "tagline": "#F6C35A",
            "pill_fill": "#1A1D5C", "pill_stroke": "#4B51B0",
            "icon_bg": SHAIZY_GOLD, "icon_fg": "#1B1E55",
        },
        "boson": {
            "logo": "bosonstudio/bosonstudio-logo-dark.svg", "logo_h": 740,
            "orbit": "#1A8A52", "particle": BOSON_GREEN, "spark": BOSON_GREEN,
            "text": "#FFFFFF", "tagline": "#8FDDB0",
            "pill_fill": "#0A3A30", "pill_stroke": "#2C7A60",
            "icon_bg": BOSON_GREEN, "icon_fg": "#062019",
        },
    },
    "light": {
        "bands": [(0, "#E9C47A"), (0.3, "#F8E3B4"), (0.45, "#FFF7E8"), (0.55, "#EDF8F1"),
                  (0.7, "#C9EAD6"), (1, "#9FD6B4")],
        "shaizy": {
            "logo": "shaizy/shaizy-logo-light.svg", "logo_h": 620,
            "trail": "#C98A12", "spark": "#E0A030",
            "text": "#1E2160", "tagline": "#9A6A0C",
            "pill_fill": "#FFFFFF", "pill_stroke": "#C9CBE0",
            "icon_bg": "#272B6E", "icon_fg": "#F6C35A",
        },
        "boson": {
            "logo": "bosonstudio/bosonstudio-logo-light.svg", "logo_h": 740,
            "orbit": "#4FB57E", "particle": "#168A47", "spark": BOSON_GREEN,
            "text": "#0B332C", "tagline": "#168A47",
            "pill_fill": "#FFFFFF", "pill_stroke": "#BFDCCD",
            "icon_bg": "#0B332C", "icon_fg": BOSON_GREEN,
        },
    },
}

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT = HERE.parent


def f(v):
    return f"{v:.1f}".rstrip("0").rstrip(".")


# ------------------------------------------------------------------ fonts ---


class Font:
    def __init__(self, path):
        self.tt = TTFont(path)
        self.upm = self.tt["head"].unitsPerEm
        self.cmap = self.tt.getBestCmap()
        self.glyphs = self.tt.getGlyphSet()
        self.hmtx = self.tt["hmtx"]
        self.cap = self.tt["OS/2"].sCapHeight
        self.kern = self._read_kerning()

    def _read_kerning(self):
        """Flatten GPOS 'kern' pair adjustments into {(left, right): dx}."""
        pairs = {}
        if "GPOS" not in self.tt:
            return pairs
        gpos = self.tt["GPOS"].table
        lookups = {
            i
            for fr in gpos.FeatureList.FeatureRecord
            if fr.FeatureTag == "kern"
            for i in fr.Feature.LookupListIndex
        }
        for li in sorted(lookups):
            lookup = gpos.LookupList.Lookup[li]
            for st in lookup.SubTable:
                if lookup.LookupType == 9:
                    st = st.ExtSubTable
                if getattr(st, "LookupType", 2) != 2:
                    continue
                firsts = st.Coverage.glyphs
                if st.Format == 1:
                    for g1, ps in zip(firsts, st.PairSet):
                        for rec in ps.PairValueRecord:
                            dx = getattr(rec.Value1, "XAdvance", 0) or 0
                            pairs.setdefault((g1, rec.SecondGlyph), dx)
                elif st.Format == 2:
                    cd1, cd2 = st.ClassDef1.classDefs, st.ClassDef2.classDefs
                    by_class2 = {}
                    for g, c in cd2.items():
                        by_class2.setdefault(c, []).append(g)
                    for g1 in firsts:
                        row = st.Class1Record[cd1.get(g1, 0)].Class2Record
                        for c2, rec in enumerate(row):
                            dx = getattr(rec.Value1, "XAdvance", 0) or 0
                            if dx and c2 in by_class2:
                                for g2 in by_class2[c2]:
                                    pairs.setdefault((g1, g2), dx)
        return pairs

    def cap_h(self, size):
        return self.cap * size / self.upm

    def layout(self, text, size, tracking=0):
        """Return [(glyph name, x offset in font units)] and total width."""
        names = [self.cmap[ord(ch)] for ch in text]
        out, x = [], 0
        for i, g in enumerate(names):
            out.append((g, x))
            x += self.hmtx[g][0] + tracking * self.upm
            if i + 1 < len(names):
                x += self.kern.get((g, names[i + 1]), 0)
        x -= tracking * self.upm
        return out, x * size / self.upm

    def width(self, text, size, tracking=0):
        return self.layout(text, size, tracking)[1]

    def path(self, text, size, x, baseline, anchor="start", tracking=0):
        glyphs, width = self.layout(text, size, tracking)
        if anchor == "middle":
            x -= width / 2
        s = size / self.upm
        pen = SVGPathPen(self.glyphs, ntos=f)
        for g, gx in glyphs:
            self.glyphs[g].draw(TransformPen(pen, (s, 0, 0, -s, x + gx * s, baseline)))
        return pen.getCommands()


def shared_size(font, texts, size, max_w, pad=0, tracking=0):
    """Largest size <= `size` at which every text (plus pad) fits in max_w."""
    while max(font.width(s, size, tracking) for s in texts) + pad > max_w:
        size *= 0.98
    return size


# ------------------------------------------------------------------ icons ---

# 24 x 24 icons (Lucide, ISC licence).
ICONS = {
    "phone": '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"/>',
    "mail": '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>',
    "globe": '<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/>',
}
PLANE = "M17.8 19.2 16 11l3.5-3.5C21 6 21.5 4 21 3c-1-.5-3 0-4.5 1.5L13 8 4.8 6.2c-.5-.1-.9.1-1.1.5l-.3.5c-.2.5-.1 1 .3 1.3L9 12l-2 3H4l-1 1 3 2 2 3 1-1v-3l3-2 3.5 5.3c.3.4.8.5 1.3.3l.5-.2c.4-.3.6-.7.5-1.2z"


def read_logo(rel_path):
    src = (ROOT / rel_path).read_text()
    vb_w, vb_h = map(float, re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', src).groups())
    inner = re.sub(r"^.*?<svg[^>]*>|</svg>\s*$", "", src, flags=re.S).strip()
    for screen, printable in PRINT_SAFE.items():
        inner = re.sub(screen, printable, inner, flags=re.I)
    return vb_w, vb_h, inner


# ------------------------------------------------------------- background ---


def lerp_colour(keys, t):
    for (t0, c0), (t1, c1) in zip(keys, keys[1:]):
        if t <= t1:
            k = (t - t0) / (t1 - t0)
            a = [int(c0[i:i + 2], 16) for i in (1, 3, 5)]
            b = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
            return "#" + "".join(f"{round(x + (y - x) * k):02X}" for x, y in zip(a, b))
    return keys[-1][1]


def clip_to_canvas(poly):
    """Sutherland-Hodgman clip of a polygon to the artboard."""
    edges = (
        (lambda p: p[0] >= 0, lambda a, b: (0, a[1] + (b[1] - a[1]) * (0 - a[0]) / (b[0] - a[0]))),
        (lambda p: p[0] <= W, lambda a, b: (W, a[1] + (b[1] - a[1]) * (W - a[0]) / (b[0] - a[0]))),
        (lambda p: p[1] >= 0, lambda a, b: (a[0] + (b[0] - a[0]) * (0 - a[1]) / (b[1] - a[1]), 0)),
        (lambda p: p[1] <= H, lambda a, b: (a[0] + (b[0] - a[0]) * (H - a[1]) / (b[1] - a[1]), H)),
    )
    for inside, cross in edges:
        out = []
        for i, cur in enumerate(poly):
            prev = poly[i - 1]
            if inside(cur):
                if not inside(prev):
                    out.append(cross(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(cross(prev, cur))
        poly = out
    return poly


def wave_bands(theme):
    """Stacked solid bands with wavy edges (no gradients, no transparency).

    Each edge is u = c + wave(v, c) in a frame where u runs across the bands
    and v along them. Because the wave's change with c is bounded below 1,
    neighbouring edges never cross.
    """
    ax, ay = BAND_ACROSS
    n = math.hypot(ax, ay)
    ux, uy = ax / n, ay / n
    vx, vy = -uy, ux
    corners = [(0, 0), (W, 0), (0, H), (W, H)]
    us = [(x - MID_X) * ux + (y - MID_Y) * uy for x, y in corners]
    vs = [(x - MID_X) * vx + (y - MID_Y) * vy for x, y in corners]
    u0, u1 = min(us), max(us)
    v0, v1 = min(vs) - 900, max(vs) + 900
    assert sum(a / drift for a, _, drift, _ in WAVES) < 1

    def wave(v, c):
        return sum(
            a * math.sin(2 * math.pi * v / length + c / drift + phase)
            for a, length, drift, phase in WAVES
        )

    step = (u1 - u0) / (BAND_COUNT - 1)
    levels = [u0 + step * (k + 0.5) for k in range(BAND_COUNT - 1)]
    vsamples = [v0 + (v1 - v0) * i / 240 for i in range(241)]
    edges = [[c + wave(v, c) for v in vsamples] for c in levels]
    for a, b in zip(edges, edges[1:]):
        assert min(y - x for x, y in zip(a, b)) >= MIN_BAND, "bands too thin; reduce WAVES"

    def to_xy(u, v):
        return MID_X + u * ux + v * vx, MID_Y + u * uy + v * vy

    keys = theme["bands"]
    if not SHAIZY_ON_LEFT:
        keys = [(1 - t, c) for t, c in reversed(keys)]
    colours = [lerp_colour(keys, k / (BAND_COUNT - 1)) for k in range(BAND_COUNT)]
    shapes = [f'<rect width="{W}" height="{H}" fill="{colours[-1]}"/>']
    far = u0 - 3000
    # Paint right to left: each shape covers everything left of its edge.
    for k in range(BAND_COUNT - 2, -1, -1):
        line = [to_xy(u, v) for u, v in zip(edges[k], vsamples)]
        poly = line + [to_xy(far, v1), to_xy(far, v0)]
        poly = clip_to_canvas(poly)
        d = "M" + "L".join(f"{f(x)} {f(y)}" for x, y in poly) + "Z"
        shapes.append(f'<path d="{d}" fill="{colours[k]}"/>')
    return shapes


def sparkle(x, y, s, colour):
    return (
        f'<path d="M{x} {y - s}Q{x} {y} {x + s} {y}Q{x} {y} {x} {y + s}'
        f'Q{x} {y} {x - s} {y}Q{x} {y} {x} {y - s}Z" fill="{colour}"/>'
    )


def shaizy_art(t, logo_cx):
    """Dashed flight path climbing over the logo, plus gold sparkles."""
    out = []
    p0 = (EDGE + 160, 540)
    c = (logo_cx - 1900, 600)
    p2 = (logo_cx - 150, 210)
    out.append(
        f'<path d="M{f(p0[0])} {f(p0[1])}Q{f(c[0])} {f(c[1])} {f(p2[0])} {f(p2[1])}" '
        f'stroke="{t["trail"]}" stroke-width="13" stroke-dasharray="52 42" stroke-linecap="round"/>'
    )
    out.append(f'<circle cx="{f(p0[0])}" cy="{f(p0[1])}" r="28" fill="{t["trail"]}"/>')
    out.append(f'<circle cx="{f(p0[0])}" cy="{f(p0[1])}" r="64" stroke="{t["trail"]}" stroke-width="12"/>')
    heading = math.degrees(math.atan2(p2[1] - c[1], p2[0] - c[0]))
    size = 240
    out.append(
        f'<g transform="translate({f(p2[0])} {f(p2[1])}) rotate({f(heading + 45)}) '
        f'scale({f(size / 24)}) translate(-12 -12)"><path d="{PLANE}" fill="{t["trail"]}"/></g>'
    )
    for x, y, s in ((2950, 330, 72), (1150, 2090, 55), (3700, 2110, 48), (5900, 2090, 58), (6400, 420, 48)):
        out.append(sparkle(x, y, s, t["spark"]))
    return out


def boson_art(t, logo_cx):
    """An orbit that seems to pass behind the merge, with particles."""
    out = []
    cx, cy, rx, ry = logo_cx + 500, MID_Y + 50, 2700, 1050

    def at(deg):
        a = math.radians(deg)
        return cx + rx * math.cos(a), cy + ry * math.sin(a)

    # Top arc (from upper-left, over the logo, down behind the pills) and
    # bottom arc (from behind the pills, under the tagline).
    for a0, a1 in ((225, 375), (20, 135)):
        x0, y0 = at(a0)
        x1, y1 = at(a1)
        large = 1 if (a1 - a0) > 180 else 0
        out.append(
            f'<path d="M{f(x0)} {f(y0)}A{rx} {ry} 0 {large} 1 {f(x1)} {f(y1)}" '
            f'stroke="{t["orbit"]}" stroke-width="12" stroke-linecap="round"/>'
        )
    for deg, r in ((250, 34), (318, 26), (118, 30)):
        x, y = at(deg)
        out.append(f'<circle cx="{f(x)}" cy="{f(y)}" r="{r}" fill="{t["particle"]}"/>')
    for x, y, s in ((13900, 300, 48), (12100, 2120, 55), (8800, 1960, 46)):
        out.append(sparkle(x, y, s, t["spark"]))
    return out


# ---------------------------------------------------------------- content ---


def logo_block(t, info, cx, semibold, size):
    """Logo with its tagline centred underneath on one line."""
    vb_w, vb_h, inner = read_logo(t["logo"])
    lh = t["logo_h"]
    k = lh / vb_h
    lw = vb_w * k

    cap = semibold.cap_h(size)
    block_h = lh + TAGLINE_GAP + cap
    top = MID_Y - block_h / 2 - 20

    out = [f'<g transform="translate({f(cx - lw / 2)} {f(top)}) scale({k:.5f})">\n{inner}\n</g>']
    y = top + lh + TAGLINE_GAP + cap
    d = semibold.path(info["tagline"], size, cx, y, anchor="middle", tracking=0.01)
    out.append(f'<path d="{d}" fill="{t["tagline"]}"/>')
    return out


def contacts_block(t, info, medium, align, size):
    """Three equal-width pills; align is 'left' or 'right' (outer edge)."""
    items = [("phone", info["phone"]), ("mail", info["email"]), ("globe", info["website"])]
    pad_l, pad_r = PILL_H + 40, 140
    pill_w = max(medium.width(v, size) for _, v in items) + pad_l + pad_r
    x = EDGE if align == "left" else W - EDGE - pill_w
    block_h = 3 * PILL_H + 2 * PILL_GAP
    y = MID_Y - block_h / 2

    cap = medium.cap_h(size)
    ir = PILL_H / 2 - 30
    out = []
    for icon, value in items:
        cy = y + PILL_H / 2
        out.append(
            f'<rect x="{f(x)}" y="{f(y)}" width="{f(pill_w)}" height="{PILL_H}" rx="{PILL_H / 2}" '
            f'fill="{t["pill_fill"]}" stroke="{t["pill_stroke"]}" stroke-width="12"/>'
        )
        icx = x + PILL_H / 2
        out.append(f'<circle cx="{f(icx)}" cy="{f(cy)}" r="{f(ir)}" fill="{t["icon_bg"]}"/>')
        isz = ir * 1.05
        out.append(
            f'<g transform="translate({f(icx - isz / 2)} {f(cy - isz / 2)}) scale({f(isz / 24)})" '
            f'fill="none" stroke="{t["icon_fg"]}" stroke-width="2.2" stroke-linecap="round" '
            f'stroke-linejoin="round">{ICONS[icon]}</g>'
        )
        out.append(f'<path d="{medium.path(value, size, x + pad_l, cy + cap / 2)}" fill="{t["text"]}"/>')
        y += PILL_H + PILL_GAP
    return out


# ------------------------------------------------------------------ build ---


def mirrored(parts):
    """Flip artwork left-right (only symmetric shapes, never text)."""
    return [f'<g transform="translate({W} 0) scale(-1 1)">', *parts, "</g>"]


def build(name, theme, semibold, medium):
    ts, tb = theme["shaizy"], theme["boson"]
    shaizy_cx, boson_cx = (LOGO_CX, W - LOGO_CX) if SHAIZY_ON_LEFT else (W - LOGO_CX, LOGO_CX)
    shaizy_side, boson_side = ("left", "right") if SHAIZY_ON_LEFT else ("right", "left")

    infos = CONTENT.values()
    tag_size = shared_size(semibold, [i["tagline"] for i in infos], TAGLINE_SIZE, TAGLINE_MAX_W, tracking=0.01)
    contact_size = shared_size(
        medium, [i[k] for i in infos for k in ("phone", "email", "website")],
        CONTACT_SIZE, PILL_MAX_W, pad=PILL_H + 40 + 140,
    )

    parts = wave_bands(theme)
    # The art is laid out for Shaizy on the left; mirror it when the brands swap.
    art = boson_art(tb, W - LOGO_CX) + shaizy_art(ts, LOGO_CX)
    parts += art if SHAIZY_ON_LEFT else mirrored(art)
    parts += logo_block(ts, CONTENT["shaizy"], shaizy_cx, semibold, tag_size)
    parts += logo_block(tb, CONTENT["boson"], boson_cx, semibold, tag_size)
    parts += contacts_block(ts, CONTENT["shaizy"], medium, shaizy_side, contact_size)
    parts += contacts_block(tb, CONTENT["boson"], medium, boson_side, contact_size)

    svg = (
        f'<svg width="144in" height="24in" viewBox="0 0 {W} {H}" fill="none" '
        f'xmlns="http://www.w3.org/2000/svg">\n' + "\n".join(parts) + "\n</svg>\n"
    )
    assert "opacity" not in svg, "transparency found; flex output must be solid colours"
    out = OUT / f"shop-banner-12x2ft-{name}.svg"
    out.write_text(svg)
    print(f"wrote {out.relative_to(ROOT)} ({len(svg) // 1024} KB)")


if __name__ == "__main__":
    semibold = Font(HERE / "fonts/Poppins-SemiBold.ttf")
    medium = Font(HERE / "fonts/Poppins-Medium.ttf")
    for name, theme in THEMES.items():
        build(name, theme, semibold, medium)
