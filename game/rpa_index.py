"""Read-only access to Ren'Py `.rpa` archives.

A Ren'Py game keeps almost all of its art, music and voice inside `.rpa`
archives, so a scanner that only walks loose files sees the engine and nothing
else. This module reads the archive index in the same public format Ren'Py's own
loader uses, which is what the engine does at runtime.

Scope and limits, deliberately:

- Read-only. Nothing is written back into an archive, and no archive is modified.
- Only the standard `RPA-1.0`, `RPA-2.0` and `RPA-3.0` containers are opened by the
  built-in reader. Any other header, including an encrypted or protected archive,
  is refused and reported as such. There is no key search, no decryption and no
  unpacker for proprietary or DRM-protected containers.
- When Ren'Py itself is importable, its archive handlers are preferred, so the
  behaviour inside the game is exactly the engine's own.
- `unrpa` (https://github.com/lattyware/unrpa, GPL-3.0) is vendored under
  `game/vendor/unrpa/` and used as a **fallback** reader. The built-in reader is
  tried first; unrpa only steps in for the unofficial variants, which some real
  games ship and which the built-in reader refuses on purpose: `.rpi` index files
  (RPA-1.0 written with an index), RPA-3.2, RPA-4.0, and the `zix`/`alt` containers.
  A vendored copy of an installed `unrpa` takes precedence, so a system
  installation can be used instead.
"""

import importlib
import importlib.util
import os
import pickle
import sys
import zlib

try:
    import renpy.loader as _renpy_loader
except Exception:  # pragma: no cover - offline tools have no Ren'Py
    _renpy_loader = None

_UNRPA_SOURCE = None


def _load_unrpa():
    """Import unrpa, preferring an already installed copy over the vendored one.

    unrpa's own modules use absolute `from unrpa...` imports, so the vendored tree
    has to be importable as a top-level package: `game/vendor` goes on
    `sys.path`. That works the same way inside the engine and in the offline
    tools, which is why it is not done through a relative package.

    Returns `(UnRPA_class, source_name)`, or `(None, None)` on failure.
    """
    global _UNRPA_SOURCE
    try:
        from unrpa import UnRPA  # an installed distribution, if the user has one
        return UnRPA, "installed"
    except Exception:
        pass

    here = os.path.dirname(os.path.abspath(__file__))
    vendor_dir = os.path.join(here, "vendor")
    if not os.path.isdir(os.path.join(vendor_dir, "unrpa")):
        return None, None
    if vendor_dir not in sys.path:
        sys.path.append(vendor_dir)
    try:
        from unrpa import UnRPA
    except Exception:
        return None, None
    _UNRPA_SOURCE = "vendored"
    return UnRPA, "vendored"


_UNRPA, _UNRPA_KIND = _load_unrpa()


def unrpa_available():
    """True when the unrpa reader can be used as a fallback."""
    return _UNRPA is not None


def unrpa_source():
    """`"installed"`, `"vendored"` or `None`."""
    return _UNRPA_KIND


RPA_HEADERS = (b"RPA-1.0 ", b"RPA-2.0 ", b"RPA-3.0 ")


class ArchiveRefused(Exception):
    """The archive is not a standard Ren'Py container, so it is not opened."""


def _normalize_entry(entry):
    """Return (offset, length, start_bytes) from any index entry shape."""
    chunk = entry
    if isinstance(entry, (list, tuple)) and len(entry) == 1 and isinstance(entry[0], (list, tuple)):
        chunk = entry[0]
    parts = list(chunk)
    if len(parts) < 2:
        raise ArchiveRefused("unreadable index entry")
    offset, length = int(parts[0]), int(parts[1])
    start = parts[2] if len(parts) > 2 else b""
    if isinstance(start, str):
        start = start.encode("latin-1")
    if not isinstance(start, bytes):
        start = b""
    return offset, length, start


def _read_index_standalone(path):
    with open(path, "rb") as fh:
        header = fh.read(40)
        magic = header[:8]
        if magic not in RPA_HEADERS:
            raise ArchiveRefused(
                "not a standard Ren'Py archive (header %r): protected or unknown container" % magic)
        if magic == b"RPA-1.0 ":
            fh.seek(0)
            return pickle.loads(zlib.decompress(fh.read()))

        offset = int(header[8:24], 16)
        key = int(header[25:33], 16) if magic == b"RPA-3.0 " else 0
        fh.seek(offset)
        try:
            index = pickle.loads(zlib.decompress(fh.read()))
        except Exception as exc:
            raise ArchiveRefused("index is encrypted or corrupt: %s" % exc)
        if not isinstance(index, dict):
            raise ArchiveRefused("index is not a name table")
        if key:
            out = {}
            for name, entry in index.items():
                offset_raw, length_raw, start = _normalize_entry(entry)
                out[name] = (offset_raw ^ key, length_raw ^ key, start)
            return out
        return {name: _normalize_entry(entry) for name, entry in index.items()}


def _read_index_with_renpy(path):
    """Prefer Ren'Py's own handler, so the game sees engine-identical results."""
    for handler in getattr(_renpy_loader, "archive_handlers", ()):
        if os.path.splitext(path)[1].lower() not in handler.get_supported_extensions():
            continue
        with open(path, "rb") as fh:
            header = fh.read(40)
            if header[:8] not in handler.get_supported_headers():
                continue
            fh.seek(0)
            return handler.read_index(fh)
    return None


def _read_index_unrpa(path):
    """Wider net: the unrpa reader, for the unofficial variants we refuse.

    unrpa also understands `.rpi` index files, RPA-3.2, RPA-4.0 and the `zix`/`alt`
    containers. Returns None when it cannot help, so the caller keeps the original
    refusal.
    """
    if _UNRPA is None:
        return None
    try:
        with open(path, "rb") as fh:
            raw = _UNRPA(path, verbosity=-1).get_index(fh)
    except Exception:
        return None
    if not isinstance(raw, dict) or not raw:
        return None
    out = {}
    for name, entry in raw.items():
        key = str(name)
        if os.sep != "/":
            key = key.replace(os.sep, "/")
        try:
            out[key] = _normalize_entry(entry)
        except ArchiveRefused:
            continue
    return out or None


def read_index_with_reader(path):
    """`(index, reader_name)`, widening the net only as far as it is allowed.

    Order: Ren'Py's own handler, then the built-in standard-container reader,
    then unrpa for the unofficial variants. A container that nothing can read is
    refused rather than guessed at.
    """
    if not os.path.isfile(path):
        raise ArchiveRefused("archive not found: %s" % path)

    index = None
    reader = None
    if _renpy_loader is not None:
        try:
            index = _read_index_with_renpy(path)
        except Exception:
            index = None
        if index is not None:
            reader = "renpy"
    if index is None:
        try:
            index = _read_index_standalone(path)
            reader = "builtin"
        except ArchiveRefused as exc:
            index = _read_index_unrpa(path)
            if index is not None:
                reader = "unrpa:%s" % (_UNRPA_KIND or "?")
            else:
                raise exc
    return {str(name): _normalize_entry(value) for name, value in index.items()}, reader


def read_index(path):
    """`{archive-relative name: (offset, length, start_bytes)}`, or a refusal.

    Raises ArchiveRefused for a protected or unknown container instead of
    guessing at it.
    """
    return read_index_with_reader(path)[0]


def list_entries(path):
    """Sorted entry names, or `None` when the archive is refused."""
    try:
        return sorted(read_index(path))
    except ArchiveRefused:
        return None
    except Exception:
        return None


def read_entry(path, name, index=None):
    """The raw bytes of one archive entry."""
    if index is None:
        index = read_index(path)
    if name not in index:
        raise ArchiveRefused("entry not in archive: %s" % name)
    offset, length, start = index[name]
    with open(path, "rb") as fh:
        fh.seek(offset)
        data = fh.read(length)
    return (start or b"") + data


def describe(path):
    """A one-line report for the inspector, including a refusal reason."""
    try:
        index, reader = read_index_with_reader(path)
    except ArchiveRefused as exc:
        return {"path": path, "ok": False, "entries": 0, "reason": str(exc),
                "reader": None, "unrpa": unrpa_available()}
    except Exception as exc:
        return {"path": path, "ok": False, "entries": 0,
                "reason": "unreadable: %s" % exc, "reader": None,
                "unrpa": unrpa_available()}
    return {
        "path": path,
        "ok": True,
        "entries": len(index),
        "bytes": sum(length for _, length, _ in index.values()),
        "reason": None,
        "reader": reader,
        "unrpa": unrpa_available(),
    }
