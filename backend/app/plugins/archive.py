"""Safe extraction of a plugin's source tarball.

GitHub tarballs have one top-level folder (``<repo>-<sha>/``), which is stripped. Only regular files and
folders are written; links, devices, absolute or ``..`` paths, too many files or too much data abort the
installation. File modes from the archive are ignored (files 0644, folders 0755).
"""

from __future__ import annotations

import io
import os
import tarfile
from pathlib import Path, PurePosixPath

MAX_FILES = 2000
MAX_TOTAL_BYTES = 50 * 1024 * 1024
MAX_FILE_BYTES = 10 * 1024 * 1024
CHUNK = 64 * 1024


class ArchiveError(ValueError):
    """The archive is not acceptable; the message is German and meant for the admin."""


def _relative(name: str) -> PurePosixPath:
    if "\x00" in name or "\\" in name or name.startswith("/"):
        raise ArchiveError("Das Archiv enthält ungültige Pfade")
    path = PurePosixPath(name)
    if any(part == ".." for part in path.parts):
        raise ArchiveError("Das Archiv enthält ungültige Pfade")
    return path


def safe_extract(data: bytes, dest: Path) -> int:
    """Extract ``data`` (tar.gz) into the empty folder ``dest``; returns the number of files written."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    files = 0
    total = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            for member in tar:
                path = _relative(member.name)
                parts = path.parts[1:]  # strip the top-level folder
                if not parts:
                    continue
                if not (member.isreg() or member.isdir()):
                    raise ArchiveError("Das Archiv enthält Verknüpfungen oder Sondereinträge und wird abgelehnt")
                target = (root / PurePosixPath(*parts)).resolve()
                if root != target and root not in target.parents:
                    raise ArchiveError("Das Archiv enthält ungültige Pfade")
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True, mode=0o755)
                    continue
                files += 1
                if files > MAX_FILES:
                    raise ArchiveError(f"Das Archiv enthält mehr als {MAX_FILES} Dateien")
                if member.size > MAX_FILE_BYTES:
                    raise ArchiveError("Das Archiv enthält eine Datei über 10 MB")
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
                src = tar.extractfile(member)
                if src is None:
                    raise ArchiveError("Das Archiv ist beschädigt")
                written = 0
                fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
                with os.fdopen(fd, "wb") as out:
                    while chunk := src.read(CHUNK):
                        written += len(chunk)
                        total += len(chunk)
                        if written > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
                            raise ArchiveError("Das Archiv ist entpackt größer als 50 MB")
                        out.write(chunk)
    except ArchiveError:
        raise
    except (tarfile.TarError, EOFError, OSError, ValueError) as exc:
        raise ArchiveError("Das Archiv ist beschädigt oder kann nicht entpackt werden") from exc
    if not files:
        raise ArchiveError("Das Archiv ist leer")
    return files
