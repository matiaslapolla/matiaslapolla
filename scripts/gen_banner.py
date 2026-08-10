"""Generate the GitHub profile banner SVGs from matiaslapolla.com's own tokens.

The banner mirrors src/components/StreamingHero.tsx: the name types out, then the
bio, with an orange caret at the typing position. Text is emitted as outlines so
it renders identically wherever GitHub proxies the file (no webfont loading in an
<img> context), and the typing is a discrete SMIL clip animation keyed to real
per-character advance widths.
"""

import math
import os
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.pens.svgPathPen import SVGPathPen

# The site's own font file. Override with INSTRUMENT_SANS=/path/to/InstrumentSans-VF.ttf
FONT = os.environ.get(
    'INSTRUMENT_SANS',
    os.path.expanduser('~/Developer/personal/portfolio/public/fonts/InstrumentSans-VF.ttf'),
)
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'assets')

NAME = 'Matias Lapolla'
BIO = (
    'I build software drinking Argentine Mate, with a focus on product, '
    'solving user problems with great UX and fast iteration processes.'
)
BIO_LINES = [
    'I build software drinking Argentine Mate, with a focus on product,',
    'solving user problems with great UX and fast iteration processes.',
]
assert ' '.join(BIO_LINES) == BIO, 'bio lines must reassemble the site bio verbatim'

# Site timings, from StreamingHero's TYPE_SPEED_MS.
NAME_MS, BIO_MS, PAUSE_MS, HOLD_MS = 55, 18, 400, 3000


# --- oklch -> sRGB, so the banner uses the site's literal token values ---------

def oklch_to_hex(L, C, h_deg):
    h = math.radians(h_deg)
    a, b = C * math.cos(h), C * math.sin(h)
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    r = +4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    bl = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s

    def enc(u):
        u = 1.055 * (u ** (1 / 2.4)) - 0.055 if u > 0.0031308 else 12.92 * u
        return max(0, min(255, round(u * 255)))

    return '#%02x%02x%02x' % (enc(r), enc(g), enc(bl))


THEMES = {
    'light': {
        'bg': (0.96, 0.00, 0), 'fg': (0.18, 0.00, 0), 'muted': (0.45, 0.00, 0),
        'accent': (0.60, 0.17, 38), 'border': (0.87, 0.00, 0),
    },
    'dark': {
        'bg': (0.14, 0.00, 0), 'fg': (0.94, 0.00, 0), 'muted': (0.60, 0.00, 0),
        'accent': (0.68, 0.16, 38), 'border': (0.25, 0.00, 0),
    },
}


# --- text layout --------------------------------------------------------------

def load(weight):
    f = instantiateVariableFont(TTFont(FONT), {'wght': weight}, updateFontNames=False)
    return f, f.getGlyphSet(), f['cmap'].getBestCmap(), f['head'].unitsPerEm


def layout(text, weight, size, x0, baseline):
    """Return (svg path d, [cumulative x after each char])."""
    font, gs, cmap, upem = load(weight)
    scale = size / upem
    kern = font['kern'].kernTables[0].kernTable if 'kern' in font else {}
    d, xs, pen_x, prev = [], [], 0.0, None
    for ch in text:
        gname = cmap.get(ord(ch))
        if gname is None:
            raise SystemExit(f'glyph missing for {ch!r}')
        if prev is not None:
            pen_x += kern.get((prev, gname), 0)
        if ch != ' ':
            pen = SVGPathPen(gs)
            gs[gname].draw(pen)
            seg = pen.getCommands()
            if seg:
                # Flip the y axis (font units go up, SVG user units go down).
                d.append(
                    f'<path transform="translate({x0 + pen_x * scale:.2f} {baseline}) '
                    f'scale({scale:.6f} {-scale:.6f})" d="{seg}"/>'
                )
        pen_x += gs[gname].width
        xs.append(x0 + pen_x * scale)
        prev = gname
    return '\n    '.join(d), xs


# --- timeline -----------------------------------------------------------------

name_dur = len(NAME) * NAME_MS
bio_dur = sum(len(l) for l in BIO_LINES) * BIO_MS
TOTAL = name_dur + PAUSE_MS + bio_dur + HOLD_MS


def keyframes(start_ms, xs, per_char_ms, x_left):
    """Discrete clip-width keyframes: nothing before start, one step per char,
    final width held to the end of the loop."""
    times, widths = [0.0], [0.0]
    for i, x in enumerate(xs):
        times.append((start_ms + i * per_char_ms) / TOTAL)
        widths.append(x - x_left)
    times.append(1.0)
    widths.append(xs[-1] - x_left)
    return (
        ';'.join(f'{t:.5f}' for t in times),
        ';'.join(f'{w:.2f}' for w in widths),
    )


def caret_frames(start_ms, xs, per_char_ms, x_left):
    """Caret x positions, stepping with the text it trails."""
    times, pos = [0.0], [x_left]
    for i, x in enumerate(xs):
        times.append((start_ms + i * per_char_ms) / TOTAL)
        pos.append(x)
    times.append(1.0)
    pos.append(xs[-1])
    return ';'.join(f'{t:.5f}' for t in times), ';'.join(f'{p:.2f}' for p in pos)


def visible(spans):
    """Opacity keyframes: 1 only inside the given (start_ms, end_ms) span."""
    s, e = spans
    t = [0.0, s / TOTAL, e / TOTAL, 1.0]
    v = [0, 1, 0, 0]
    return (';'.join(f'{x:.5f}' for x in t), ';'.join(str(x) for x in v))


# --- geometry -----------------------------------------------------------------

W, H = 960, 290
PAD = 64
NAME_SIZE, BIO_SIZE = 58, 25
NAME_BASE = 118
BIO_BASE = [182, 220]
CARET_W = 3

name_d, name_xs = layout(NAME, 600, NAME_SIZE, PAD, NAME_BASE)
bio0_d, bio0_xs = layout(BIO_LINES[0], 400, BIO_SIZE, PAD, BIO_BASE[0])
bio1_d, bio1_xs = layout(BIO_LINES[1], 400, BIO_SIZE, PAD, BIO_BASE[1])

bio0_start = name_dur + PAUSE_MS
bio1_start = bio0_start + len(BIO_LINES[0]) * BIO_MS
bio_end = bio1_start + len(BIO_LINES[1]) * BIO_MS

DUR = f'{TOTAL / 1000:.3f}s'


def clip(cid, x, y, h, times, widths, animate):
    inner = f'<rect x="{x}" y="{y}" width="{"0" if animate else widths.split(";")[-1]}" height="{h}">'
    if animate:
        inner += (
            f'<animate attributeName="width" dur="{DUR}" repeatCount="indefinite" '
            f'calcMode="discrete" keyTimes="{times}" values="{widths}"/>'
        )
    return f'<clipPath id="{cid}">{inner}</rect></clipPath>'


def caret(x_times, x_vals, o_times, o_vals, y, h, accent, animate):
    if not animate:
        return ''
    return (
        f'<rect y="{y}" width="{CARET_W}" height="{h}" fill="{accent}" rx="1" opacity="0">'
        f'<animate attributeName="x" dur="{DUR}" repeatCount="indefinite" '
        f'calcMode="discrete" keyTimes="{x_times}" values="{x_vals}"/>'
        f'<animate attributeName="opacity" dur="{DUR}" repeatCount="indefinite" '
        f'calcMode="discrete" keyTimes="{o_times}" values="{o_vals}"/>'
        f'</rect>'
    )


def build(theme, animate):
    t = {k: oklch_to_hex(*v) for k, v in THEMES[theme].items()}
    n_t, n_w = keyframes(0, name_xs, NAME_MS, PAD)
    b0_t, b0_w = keyframes(bio0_start, bio0_xs, BIO_MS, PAD)
    b1_t, b1_w = keyframes(bio1_start, bio1_xs, BIO_MS, PAD)

    ncx, ncv = caret_frames(0, name_xs, NAME_MS, PAD)
    b0cx, b0cv = caret_frames(bio0_start, bio0_xs, BIO_MS, PAD)
    b1cx, b1cv = caret_frames(bio1_start, bio1_xs, BIO_MS, PAD)

    # Caret is 0.78em tall and sits just past the baseline, as in StreamingHero.
    def cbox(baseline, size):
        return baseline - round(0.72 * size), round(0.78 * size)

    carets = (
        caret(ncx, ncv, *visible((0, bio0_start)), *cbox(NAME_BASE, NAME_SIZE), t['accent'], animate)
        + caret(b0cx, b0cv, *visible((bio0_start, bio1_start)), *cbox(BIO_BASE[0], BIO_SIZE), t['accent'], animate)
        + caret(b1cx, b1cv, *visible((bio1_start, TOTAL)), *cbox(BIO_BASE[1], BIO_SIZE), t['accent'], animate)
    )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{NAME} — {BIO}">
  <title>{NAME}</title>
  <defs>
    {clip('cn', PAD, NAME_BASE - NAME_SIZE, round(1.4 * NAME_SIZE), n_t, n_w, animate)}
    {clip('c0', PAD, BIO_BASE[0] - BIO_SIZE, round(1.4 * BIO_SIZE), b0_t, b0_w, animate)}
    {clip('c1', PAD, BIO_BASE[1] - BIO_SIZE, round(1.4 * BIO_SIZE), b1_t, b1_w, animate)}
  </defs>
  <rect width="{W}" height="{H}" rx="14" fill="{t['bg']}"/>
  <rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="13.5" fill="none" stroke="{t['border']}"/>
  <g clip-path="url(#cn)" fill="{t['fg']}">
    {name_d}
  </g>
  <g clip-path="url(#c0)" fill="{t['muted']}">
    {bio0_d}
  </g>
  <g clip-path="url(#c1)" fill="{t['muted']}">
    {bio1_d}
  </g>
  {carets}
</svg>
'''


os.makedirs(OUT, exist_ok=True)
for theme in ('light', 'dark'):
    for animate, suffix in ((True, ''), (False, '-static')):
        path = f'{OUT}/banner-{theme}{suffix}.svg'
        with open(path, 'w') as fh:
            fh.write(build(theme, animate))
        print(path, os.path.getsize(path) // 1024, 'KB')
print(f'loop {TOTAL}ms  (name {name_dur} + pause {PAUSE_MS} + bio {bio_dur} + hold {HOLD_MS})')
print('light accent', oklch_to_hex(*THEMES['light']['accent']), 'dark accent', oklch_to_hex(*THEMES['dark']['accent']))
