#!/usr/bin/env python3
"""Generate the neutral character placeholder used when a character has no pack.

The placeholder used to be a black rectangle, which on screen read as a hole in the
scene rather than as a hero. This draws a full-body mannequin silhouette instead:

* one closed outline for body, arms and legs, so the figure has a single clean contour;
* a light translucent gradient fill plus a dark outline, which keeps the figure readable
  on both a dark night background and a bright outdoor one;
* a soft halo behind it and a contact shadow under the feet, so it sits in the frame;
* a blank oval face -- a mannequin, deliberately without features;
* one hue per emotion (`neutral`, `happy`, `sad`), so a scene that changes emotion changes
  the placeholder visibly instead of pretending nothing happened.

The three files land in `game/images/` and are what `assets.DEMO_STATE_FILES` points at.

    python3 tools/make_char_placeholder.py            # rewrite the three PNGs
    python3 tools/make_char_placeholder.py --out /tmp # render elsewhere first

Rendering goes through rsvg-convert (librsvg) when it is installed, ImageMagick
otherwise; the geometry is plain SVG either way.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

WIDTH = 600
HEIGHT = 1000

# The outline of the left half of the figure, from the centre of the neck down to the
# centre of the crotch. The right half is the same commands mirrored around the vertical
# centre line and walked backwards, which keeps the figure symmetric without hand-writing
# both sides.
#
# The arm and the torso only touch at the armpit: below it they part and leave a slit
# between the arm and the body that opens again below the hand. That slit is what makes
# the silhouette read as a person with arms instead of one solid slab of a torso.
NECK_TOP = (300, 150)
BODY_LEFT = [
    ("C", 284, 150, 277, 158, 275, 170),      # neck, left side
    ("C", 273, 188, 274, 204, 275, 220),      # neck base
    ("C", 268, 236, 240, 252, 214, 266),      # trapezius
    ("C", 196, 276, 178, 282, 168, 296),      # deltoid
    ("C", 166, 320, 165, 350, 164, 384),      # upper arm, outer edge
    ("C", 163, 424, 162, 466, 162, 504),
    ("C", 162, 530, 163, 552, 164, 576),      # elbow
    ("C", 165, 618, 166, 656, 167, 690),      # forearm, outer edge
    ("C", 168, 706, 169, 718, 170, 730),      # wrist
    ("C", 168, 750, 169, 772, 174, 784),      # hand, outer edge
    ("C", 180, 796, 196, 800, 208, 796),      # fingertips
    ("C", 218, 792, 223, 780, 223, 764),      # hand, inner edge
    ("C", 223, 744, 221, 730, 220, 716),      # wrist, inner edge
    ("C", 218, 690, 217, 660, 216, 626),      # forearm, inner edge
    ("C", 215, 590, 215, 550, 216, 512),
    ("C", 217, 470, 219, 430, 222, 396),      # upper arm, inner edge
    ("C", 224, 366, 227, 344, 230, 330),      # armpit: the slit closes here
    ("C", 230, 356, 229, 380, 229, 404),      # torso, side
    ("C", 230, 434, 232, 458, 234, 482),      # waist
    ("C", 232, 512, 228, 542, 225, 570),      # hip
    ("C", 228, 604, 233, 628, 238, 652),      # thigh, outer edge
    ("C", 244, 692, 250, 740, 254, 786),
    ("C", 257, 824, 258, 860, 258, 894),      # knee, then shin
    ("C", 257, 912, 256, 924, 256, 936),      # ankle
    ("C", 252, 956, 247, 972, 249, 982),      # foot, outer edge
    ("C", 251, 991, 258, 994, 268, 994),      # sole
    ("L", 288, 994),
    ("C", 294, 994, 297, 988, 296, 978),      # foot, inner edge
    ("C", 294, 962, 292, 948, 291, 936),      # ankle, inner edge
    ("C", 289, 906, 287, 878, 286, 852),      # shin, inner edge
    ("C", 287, 812, 288, 776, 290, 742),      # thigh, inner edge
    ("C", 293, 700, 297, 650, 299, 604),
    ("C", 300, 588, 300, 574, 300, 560),      # crotch
]

HEAD = {"cx": 300, "cy": 118, "rx": 64, "ry": 76}
FACE = {"cx": 300, "cy": 126, "rx": 48, "ry": 58}

# One hue per emotion: the geometry is identical, the light and the tint are not.
MOODS = {
    "neutral": {
        "file": "char_demo.png",
        "top": "#F6F9FE",
        "bottom": "#C7D2E6",
        "stroke": "#2E3A50",
        "accent": "#8FB0E4",
        "halo": 0.55,
        "face": 0.42,
        "tilt": 0,
    },
    "happy": {
        "file": "char_demo_happy.png",
        "top": "#FFFBF4",
        "bottom": "#EAD9C4",
        "stroke": "#4A3B2C",
        "accent": "#F5B971",
        "halo": 0.6,
        "face": 0.48,
        "tilt": 4,
    },
    "sad": {
        "file": "char_demo_sad.png",
        "top": "#E6EAF9",
        "bottom": "#9BA5D2",
        "stroke": "#232741",
        "accent": "#6E7BD8",
        "halo": 0.55,
        "face": 0.26,
        "tilt": -4,
    },
}


def _end(segment):
    return segment[-2], segment[-1]


def _mirrored_back(segments, start):
    """`segments` walked backwards and mirrored around the vertical centre line."""
    points = [start]
    for segment in segments:
        points.append(_end(segment))
    out = []
    for index in range(len(segments) - 1, -1, -1):
        segment = segments[index]
        p0 = points[index]
        p1 = points[index + 1]
        m0 = (WIDTH - p0[0], p0[1])
        if segment[0] == "L":
            out.append("L %d %d" % m0)
        else:
            _kind, c1x, c1y, c2x, c2y, _ex, _ey = segment
            # Reversing a cubic swaps its control points; mirroring then flips x twice.
            out.append("C %d %d %d %d %d %d" % (
                WIDTH - c2x, c2y, WIDTH - c1x, c1y, m0[0], m0[1]))
    return out


def body_path():
    commands = ["M %d %d" % NECK_TOP]
    for segment in BODY_LEFT:
        if segment[0] == "L":
            commands.append("L %d %d" % (segment[1], segment[2]))
        else:
            commands.append("C %d %d %d %d %d %d" % segment[1:])
    commands.extend(_mirrored_back(BODY_LEFT, NECK_TOP))
    commands.append("Z")
    return " ".join(commands)


def svg(mood):
    path = body_path()
    stroke = mood["stroke"]
    head = ('<ellipse cx="%(cx)d" cy="%(cy)d" rx="%(rx)d" ry="%(ry)d" />' % HEAD)
    face_oval = ('<ellipse cx="%(cx)d" cy="%(cy)d" rx="%(rx)d" ry="%(ry)d" '
                 'fill="#FFFFFF" opacity="%(face).2f"/>' % dict(FACE, face=mood["face"]))
    head_drawn = (
        '<ellipse cx="%(cx)d" cy="%(cy)d" rx="%(rx)d" ry="%(ry)d"\n'
        '         fill="url(#body)" stroke="%(stroke)s" stroke-width="6"/>' % dict(
            HEAD, stroke=stroke))
    return """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="%(width)d" height="%(height)d"
     viewBox="0 0 %(width)d %(height)d">
  <defs>
    <linearGradient id="body" gradientUnits="userSpaceOnUse" x1="0" y1="40" x2="0" y2="995">
      <stop offset="0" stop-color="%(top)s" stop-opacity="0.97"/>
      <stop offset="0.55" stop-color="%(top)s" stop-opacity="0.84"/>
      <stop offset="1" stop-color="%(bottom)s" stop-opacity="0.96"/>
    </linearGradient>
    <linearGradient id="shine" gradientUnits="userSpaceOnUse" x1="150" y1="0" x2="430" y2="0">
      <stop offset="0" stop-color="#FFFFFF" stop-opacity="0.34"/>
      <stop offset="0.5" stop-color="#FFFFFF" stop-opacity="0.05"/>
      <stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/>
    </linearGradient>
    <filter id="blur" x="-40%%" y="-40%%" width="180%%" height="180%%">
      <feGaussianBlur stdDeviation="13"/>
    </filter>
    <filter id="ground" x="-60%%" y="-120%%" width="220%%" height="340%%">
      <feGaussianBlur stdDeviation="9"/>
    </filter>
    <clipPath id="figure">
      <path d="%(path)s"/>
      %(head)s
    </clipPath>
  </defs>

  <!-- contact shadow: grounds the figure on whatever background the scene uses -->
  <ellipse cx="300" cy="986" rx="138" ry="16" fill="#0D1220" opacity="0.40"
           filter="url(#ground)"/>

  <!-- halo: keeps the silhouette readable against a dark night background -->
  <g filter="url(#blur)" opacity="%(halo).2f" fill="%(accent)s">
    <path d="%(path)s"/>
    %(head)s
  </g>

  <!-- body: fill, then the highlight clipped to the fill, then the contour on top -->
  <path d="%(path)s" fill="url(#body)"/>
  <path d="%(path)s" fill="url(#shine)" clip-path="url(#figure)"/>
  <path d="%(path)s" fill="none" stroke="%(stroke)s" stroke-width="6"
        stroke-linejoin="round"/>

  <!-- head, drawn over the neck so its outline reads as a jaw line -->
  <g transform="rotate(%(tilt)d 300 205)">
    %(head_drawn)s
    %(face_oval)s
  </g>

  <!-- mannequin seams: a collar and a waistband, faint enough to stay neutral -->
  <g stroke="%(stroke)s" stroke-width="5" fill="none" stroke-linecap="round" opacity="0.28">
    <path d="M 256 246 Q 300 272 344 246"/>
    <path d="M 236 482 L 364 482"/>
  </g>
</svg>
""" % {
        "width": WIDTH,
        "height": HEIGHT,
        "top": mood["top"],
        "bottom": mood["bottom"],
        "stroke": stroke,
        "accent": mood["accent"],
        "halo": mood["halo"],
        "path": path,
        "head": head,
        "head_drawn": head_drawn,
        "face_oval": face_oval,
        "tilt": mood["tilt"],
    }


def render(markup, out_path):
    """Write `markup` (SVG) to `out_path` as a 600x1000 PNG with alpha."""
    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "placeholder.svg")
        with open(src, "w", encoding="utf-8") as fh:
            fh.write(markup)
        if shutil.which("rsvg-convert"):
            subprocess.run(
                ["rsvg-convert", "--width", str(WIDTH), "--height", str(HEIGHT),
                 "--output", out_path, src],
                check=True)
            return "rsvg-convert"
        if shutil.which("magick"):
            subprocess.run(
                ["magick", "-background", "none", "-density", "96",
                 src, "-resize", "%dx%d!" % (WIDTH, HEIGHT), out_path],
                check=True)
            return "magick"
        raise SystemExit("Neither rsvg-convert nor magick is installed.")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=None,
                        help="directory for the PNGs (default: game/images)")
    args = parser.parse_args()

    out_dir = args.out or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "game", "images")
    os.makedirs(out_dir, exist_ok=True)

    engine = None
    for name, mood in MOODS.items():
        target = os.path.join(out_dir, mood["file"])
        engine = render(svg(mood), target)
        size = os.path.getsize(target)
        print("%s -> %s (%d bytes)" % (name, target, size))
        if size < 4096:
            raise SystemExit("Placeholder %s is suspiciously small." % target)
    print("Rendered with %s." % engine)
    return 0


if __name__ == "__main__":
    sys.exit(main())
