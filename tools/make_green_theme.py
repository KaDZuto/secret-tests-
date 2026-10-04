"""One-shot recolour of the Living VN interface: dark navy/blue -> light mint/green (Doki Doki style).

The old look was light text on dark navy panels with blue accents. A new look is the opposite, the
way Doki Doki Literature Club does it: pale panels, dark text, one accent colour (green).
Every colour goes through the same function, so a text colour and the surface it sits on stay a
matching pair after the swap:

    dark surface        -> pale mint
    light text          -> dark green
    blue accent (fill)  -> mid green        (light-blue accent used as text -> dark green)
    grey                -> muted green-grey
    warm / red / gold   -> darkened, hue kept (readable on a pale surface)

It rewrites, in place, the `#rrggbb[aa]` literals of the .rpy files and the pixels of the small
`game/gui/**` PNGs (alpha kept), and it generates the three full-screen backgrounds. Pure stdlib
(zlib/struct), one file in memory at a time. It runs ONCE: `game/gui/.green_theme` marks that it
did, and the originals are in git.

    python3 tools/make_green_theme.py            # apply
    python3 tools/make_green_theme.py --dry-run  # report only
"""
import colorsys
import math
import os
import re
import struct
import sys
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME = os.path.join(ROOT, "game")
MARKER = os.path.join(GAME, "gui", ".green_theme")
RPY = ("gui.rpy", "screens.rpy", "vn_styles.rpy", "story_generating.rpy", "story_chapter.rpy",
       "options.rpy", "demo.rpy")
# Photographs / full-screen art are regenerated, never recoloured.
SKIP_PNG = {"main_menu.png", "game_menu.png", "window_icon.png"}
HUE = 0.385  # ~139 degrees, a fresh green


def map_rgb(r, g, b):
    """The one colour mapping (0-255 ints in and out)."""
    h, l, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
    if l < 0.35:                                   # dark surface
        nl = 0.95 - 0.45 * l
        out = colorsys.hls_to_rgb(HUE, nl, 0.32)
    elif s > 0.25 and 0.45 < h < 0.78:             # blue accent
        nl = 0.30 if l >= 0.65 else 0.62
        out = colorsys.hls_to_rgb(HUE, nl, 0.55)
    elif s > 0.25 and l > 0.45:                    # warm / green / red accents
        out = colorsys.hls_to_rgb(h, 0.33, min(0.8, s))
    elif l > 0.7:                                  # light text
        out = colorsys.hls_to_rgb(HUE, 0.12 + (1.0 - l) * 0.5, 0.45)
    else:                                          # grey
        out = colorsys.hls_to_rgb(HUE, 0.38, 0.18)
    return tuple(int(round(max(0.0, min(1.0, c)) * 255)) for c in out)


# ------------------------------------------------------------------ .rpy literals

HEX = re.compile(r"(?P<q>[\"'])#(?P<rgb>[0-9a-fA-F]{6})(?P<a>[0-9a-fA-F]{2})?(?P=q)")


def recolour_rpy(text):
    count = [0]

    def sub(m):
        rgb = m.group("rgb")
        r, g, b = (int(rgb[i:i + 2], 16) for i in (0, 2, 4))
        nr, ng, nb = map_rgb(r, g, b)
        count[0] += 1
        return "%s#%02x%02x%02x%s%s" % (m.group("q"), nr, ng, nb, m.group("a") or "", m.group("q"))

    return HEX.sub(sub, text), count[0]


# ------------------------------------------------------------------ PNG (stdlib)

def read_png(path):
    """(w, h, rgba bytearray) for 8-bit non-interlaced PNGs of colour type 0/2/3/4/6, else None."""
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    pos, idat, plte, trns = 8, [], None, None
    w = h = depth = ctype = interlace = None
    while pos < len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if kind == b"IHDR":
            w, h, depth, ctype, _c, _f, interlace = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            plte = body
        elif kind == b"tRNS":
            trns = body
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
    if depth != 8 or interlace or ctype not in (0, 2, 3, 4, 6):
        return None
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    raw = zlib.decompress(b"".join(idat))
    stride = w * channels
    rows, prev = [], bytearray(stride)
    p = 0
    for _ in range(h):
        ft = raw[p]
        line = bytearray(raw[p + 1:p + 1 + stride])
        p += 1 + stride
        if ft == 1:
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 255
        elif ft == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif ft == 3:
            for i in range(stride):
                left = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((left + prev[i]) >> 1)) & 255
        elif ft == 4:
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                b = prev[i]
                c = prev[i - channels] if i >= channels else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        elif ft != 0:
            return None
        rows.append(line)
        prev = line
    out = bytearray(w * h * 4)
    o = 0
    for line in rows:
        for x in range(w):
            if ctype == 6:
                out[o:o + 4] = line[x * 4:x * 4 + 4]
            elif ctype == 2:
                out[o:o + 3] = line[x * 3:x * 3 + 3]
                out[o + 3] = 255
            elif ctype == 0:
                out[o] = out[o + 1] = out[o + 2] = line[x]
                out[o + 3] = 255
            elif ctype == 4:
                out[o] = out[o + 1] = out[o + 2] = line[x * 2]
                out[o + 3] = line[x * 2 + 1]
            else:
                i = line[x]
                out[o:o + 3] = plte[i * 3:i * 3 + 3]
                out[o + 3] = trns[i] if trns and i < len(trns) else 255
            o += 4
    return w, h, out


def write_png(path, w, h, rgba):
    def chunk(kind, body):
        crc = zlib.crc32(kind + body) & 0xFFFFFFFF
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)

    stride = w * 4
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += rgba[y * stride:(y + 1) * stride]
    blob = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))
    with open(path, "wb") as fh:
        fh.write(blob)


def recolour_png(path):
    image = read_png(path)
    if image is None:
        return False
    w, h, px = image
    cache = {}
    for i in range(0, len(px), 4):
        key = (px[i], px[i + 1], px[i + 2])
        new = cache.get(key)
        if new is None:
            new = cache[key] = map_rgb(*key)
        px[i], px[i + 1], px[i + 2] = new
    write_png(path, w, h, px)
    return True


# ------------------------------------------------------------------ generated backgrounds

def polka(w, h, base_top, base_bottom, dot, dot_alpha, spacing=64, radius=9, vignette=0.0):
    """Soft vertical gradient with an offset grid of dots, the Doki Doki menu pattern in green."""
    px = bytearray(w * h * 4)
    cx, cy = w / 2.0, h / 2.0
    maxd = math.hypot(cx, cy)
    for y in range(h):
        t = y / float(h - 1)
        row = [int(base_top[k] + (base_bottom[k] - base_top[k]) * t) for k in range(3)]
        gy = y % spacing
        for x in range(w):
            r, g, b = row
            # alternate rows are shifted by half a cell
            gx = (x + (spacing // 2 if (y // spacing) % 2 else 0)) % spacing
            d2 = (gx - spacing / 2.0) ** 2 + (gy - spacing / 2.0) ** 2
            if d2 < radius * radius:
                edge = min(1.0, (radius - math.sqrt(d2)) / 1.5)
                a = dot_alpha * edge
                r = int(r + (dot[0] - r) * a)
                g = int(g + (dot[1] - g) * a)
                b = int(b + (dot[2] - b) * a)
            if vignette:
                v = 1.0 - vignette * (math.hypot(x - cx, y - cy) / maxd) ** 2
                r, g, b = int(r * v), int(g * v), int(b * v)
            o = (y * w + x) * 4
            px[o], px[o + 1], px[o + 2], px[o + 3] = r, g, b, 255
    return px


def generate_backgrounds(dry):
    jobs = [
        (os.path.join(GAME, "gui", "main_menu.png"), 1280, 720, (226, 245, 229), (184, 226, 196),
         (255, 255, 255), 0.55, 64, 9, 0.0),
        (os.path.join(GAME, "gui", "game_menu.png"), 1280, 720, (232, 247, 234), (203, 235, 211),
         (255, 255, 255), 0.45, 64, 9, 0.0),
        (os.path.join(GAME, "images", "menu_bg.png"), 1280, 720, (214, 240, 220), (150, 205, 170),
         (255, 255, 255), 0.35, 80, 12, 0.18),
    ]
    for path, w, h, top, bottom, dot, alpha, spacing, radius, vig in jobs:
        print("  background", os.path.relpath(path, ROOT))
        if not dry:
            write_png(path, w, h, polka(w, h, top, bottom, dot, alpha, spacing, radius, vig))


def main():
    dry = "--dry-run" in sys.argv
    if os.path.exists(MARKER) and not dry:
        print("already applied (%s); originals are in git" % os.path.relpath(MARKER, ROOT))
        return 0
    total = 0
    for name in RPY:
        path = os.path.join(GAME, name)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        new, n = recolour_rpy(text)
        total += n
        print("  %-24s %3d colour literals" % (name, n))
        if n and not dry:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(new)
    done = skipped = 0
    for base, _dirs, files in os.walk(os.path.join(GAME, "gui")):
        for name in sorted(files):
            if not name.endswith(".png") or name in SKIP_PNG:
                continue
            path = os.path.join(base, name)
            if dry:
                done += 1
                continue
            if recolour_png(path):
                done += 1
            else:
                skipped += 1
                print("  skipped (unsupported PNG): " + os.path.relpath(path, ROOT))
    print("  gui PNGs recoloured: %d, skipped: %d" % (done, skipped))
    generate_backgrounds(dry)
    if not dry:
        with open(MARKER, "w") as fh:
            fh.write("applied by tools/make_green_theme.py\n")
    print("literals: %d%s" % (total, " (dry run)" if dry else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
