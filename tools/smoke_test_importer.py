"""Smoke test for the layered importer's face-offset measurement.

The importer decides where a face part lands on a body, and a wrong answer does not fail: it
produces a file that looks fine until somebody looks at the hair. Both faults that shipped
here were silent, so they are pinned here instead.

The measurement is only correct because of what it ignores. A face strip carries the same
face around the moving part, so the pixels that change from frame to frame are the
expression and everything else is background that has to land on the body exactly. Scoring
the whole rectangle is what let the first version settle on a cheek and stay there, so the
test drives the search from seeds that are deliberately wrong and a background that has no
period, because a striped or flat background matches at the wrong offset and would make the
test pass while proving nothing.
"""

import importlib.util
import os
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMPORTER = os.path.join(REPO, "tools", "import_layered_pack.py")

BODY_W, BODY_H = 200, 260
LAYER_W, LAYER_H = 60, 50
TRUE_OFFSET = (70, 90)
# The face patch, in the body's coordinates. It has to sit inside the rectangle the layer
# covers when it is placed correctly, or the fixture never puts a changed pixel under the
# measurement and cannot tell one metric from another.
FACE_BOX = (TRUE_OFFSET[0] + 15, TRUE_OFFSET[1] + 10, 34, 22)
PATCH = (32, 24, 16, 255)


def load_importer():
    spec = importlib.util.spec_from_file_location("layered_importer_smoke", IMPORTER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def have_magick():
    try:
        subprocess.run(["magick", "-version"], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def texture(x, y):
    """A background pixel with no period the search can slide through."""
    h = (x * 2654435761 ^ y * 40503) & 0xFFFF
    return (0xE0 + (h & 0x0F), 0xC0 + ((h >> 4) & 0x0F), 0xA0 + ((h >> 8) & 0x0F), 255)


def write_texture(path, width, height, face_at=None, origin=(0, 0)):
    """A textured field, optionally with the face patch painted over it.

    `origin` is where this image sits on the body. A face strip is cut from the same artwork
    as the body, so its background is the body's texture sampled at `origin` rather than a
    fresh patch of its own; sampling locally would leave the layer unmatchable at any offset
    and the measurement would have nothing to find.
    """
    fx, fy, fw, fh = face_at if face_at else (0, 0, 0, 0)
    data = bytearray()
    for y in range(height):
        for x in range(width):
            inside = face_at is not None and fx <= x < fx + fw and fy <= y < fy + fh
            data += bytes(PATCH) if inside else bytes(texture(origin[0] + x, origin[1] + y))
    subprocess.run(["magick", "-size", "%dx%d" % (width, height), "-depth", "8", "rgba:-", path],
                   input=bytes(data), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   check=True)
    return path


def body_with_face(path, expression=0):
    """The body: the same texture the strip carries, plus the face patch at `expression`."""
    x0, y0, fw, fh = FACE_BOX
    return write_texture(path, BODY_W, BODY_H, face_at=(x0 + expression, y0, fw, fh))


def local_face_box():
    """The same patch in the layer's own coordinates."""
    return (FACE_BOX[0] - TRUE_OFFSET[0], FACE_BOX[1] - TRUE_OFFSET[1], FACE_BOX[2], FACE_BOX[3])


def make_strip(path, count=4):
    """Frames that share a background and differ only inside the face box."""
    x, y, w, h = local_face_box()
    files = []
    for index in range(count):
        out = "%s_%d.png" % (path, index)
        write_texture(out, LAYER_W, LAYER_H, face_at=(x + index, y, w, h), origin=TRUE_OFFSET)
        files.append(out)
    return files


def main():
    if not have_magick():
        print("SKIP: ImageMagick is not installed, the offset measurement cannot be exercised")
        return 0

    importer = load_importer()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = os.path.realpath(tmp)
        body = body_with_face(os.path.join(tmp, "body.png"))
        frames = make_strip(os.path.join(tmp, "eyes"))

        # A layer cut out of the body at the true offset: placed there it changes nothing.
        true_layer = os.path.join(tmp, "true.png")
        subprocess.run(["magick", body, "-crop", "%dx%d+%d+%d" % (
            LAYER_W, LAYER_H, TRUE_OFFSET[0], TRUE_OFFSET[1]), "+repage", "-depth", "8", true_layer],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        base = importer.load_rgba(body)
        layer = importer.load_rgba(true_layer)
        mask = importer.varying_mask([importer.load_rgba(f) for f in frames], LAYER_W, LAYER_H)
        assert sum(mask) > 0, "the frames differ, so some pixels must be marked as the face"
        x, y, w, h = local_face_box()
        inside = sum(mask[r * LAYER_W + c] for r in range(y, y + h) for c in range(x, x + w))
        assert inside > 0, "the changing patch must be inside the marked face"

        def misses(dx, dy):
            return importer.background_misses(base, BODY_W, layer, LAYER_W, LAYER_H, mask, dx, dy)

        assert misses(*TRUE_OFFSET) == 0, "a layer taken from the body must match exactly"

        # The metric has to be blind to the expression, because the expression is *supposed*
        # to differ: this is what makes the answer sharp instead of a soft preference. A layer
        # carrying another frame's face shares the body's background exactly, so the background
        # count stays at zero while the face plainly does not match. Counting the whole
        # rectangle would score this the same as a misplaced layer and prefer whatever
        # position hides the difference best, which is how the first version ended up pasting
        # a face onto a cheek.
        bx, by, bw, bh = FACE_BOX
        other_body = write_texture(os.path.join(tmp, "other_body.png"), BODY_W, BODY_H,
                                   face_at=(bx + 2, by, bw, bh))
        other = os.path.join(tmp, "other_expression.png")
        subprocess.run(["magick", other_body, "-crop", "%dx%d+%d+%d" % (
            LAYER_W, LAYER_H, TRUE_OFFSET[0], TRUE_OFFSET[1]), "+repage", "-depth", "8", other],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        assert importer.changed_pixels(body, other_body, 0, 0,
                                       os.path.join(tmp, "s.png")) > 0, "фикстура должна менять лицо"
        assert importer.background_misses(
            base, BODY_W, importer.load_rgba(other), LAYER_W, LAYER_H, mask, *TRUE_OFFSET) == 0, (
            "фон должен совпадать независимо от выражения")

        # The background has to be what discriminates, so a wrong offset must cost something.
        assert min(misses(dx, dy) for dx in range(0, BODY_W - LAYER_W, 7)
                   for dy in range(0, BODY_H - LAYER_H, 7) if (dx, dy) != TRUE_OFFSET) > 0, (
            "the background has to be aperiodic, otherwise the measurement cannot fail")

        # Seeded off but inside the window: the search has to settle on the exact offset
        # rather than on the nearest place where the background also happens to line up.
        scratch = os.path.join(tmp, "scratch.png")
        packed = [importer.load_rgba(f) for f in frames]
        for name, seed in (("на 8 пикселей левее и 6 выше", (TRUE_OFFSET[0] - 8, TRUE_OFFSET[1] - 6)),
                           ("на 10 пикселей правее", (TRUE_OFFSET[0] + 10, TRUE_OFFSET[1])),
                           ("ровно", TRUE_OFFSET)):
            found = importer.find_offset(body, true_layer, packed, seed, scratch, window=12)
            assert found is not None, name
            assert (found[1], found[2]) == TRUE_OFFSET, "%s: получено %s, ожидалось %s" % (
                name, (found[1], found[2]), TRUE_OFFSET)

        # A wide window is what recovers a bad seed. A narrow one cannot: the true offset sits
        # outside it, the search returns the best point it can reach, and the face ends up
        # pasted slightly off with a seam along the top of the hair. This is the fault that
        # reached the game once, with the first pose of a set stuck while the poses after it
        # walked one window at a time onto the right answer.
        for name, seed in (("на 40 пикселей левее", (TRUE_OFFSET[0] - 40, TRUE_OFFSET[1])),
                           ("на 30 пикселей выше", (TRUE_OFFSET[0], TRUE_OFFSET[1] - 30))):
            found = importer.find_offset(body, true_layer, packed, seed, scratch, window=56)
            assert found is not None, name
            assert (found[1], found[2]) == TRUE_OFFSET, "%s: получено %s, ожидалось %s" % (
                name, (found[1], found[2]), TRUE_OFFSET)

        # And the reason the first pose of a set needs the wide window: with a narrow one the
        # true offset is simply not on the table, so the search answers with the best it can
        # reach and reports success. It has to keep failing until the window covers it.
        far = (TRUE_OFFSET[0] - 40, TRUE_OFFSET[1])
        assert abs(far[0] - TRUE_OFFSET[0]) > 12, "фикстура должна быть вне узкого окна"
        assert importer.find_offset(body, true_layer, packed, far, scratch, window=12)[1:3] \
            != TRUE_OFFSET, "узкое окно не должно доставать до истинного смещения"

        # A face the layer does not carry must be substituted, not pasted from nowhere: that
        # is what an outfit with three eye shapes and no mouth strip runs into.
        assert importer._available_frame({"eyes": "happy"}, "eyes", {"open", "closed", "wide"}) == "open"
        assert importer._available_frame({"eyes": "closed"}, "eyes", {"open", "closed"}) == "closed"
        assert importer._available_frame({"mouth": "grin"}, "mouth", set()) is None
        assert importer._available_frame({}, "eyes", {"open"}) is None

    print("IMPORTER SMOKE OK: varying mask, background metric, offset recovery, frame fallback")
    return 0


if __name__ == "__main__":
    sys.exit(main())
