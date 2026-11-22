"""Validation for model-generated mutation filenames."""

import keyword
import os
from pathlib import Path
import stat


_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
}


def validate_mutation_filename(name):
    """Return a simple Python filename; reject paths rather than rewriting them."""
    if not isinstance(name, str) or not name:
        raise ValueError("Mutation target must be a non-empty filename")
    if "/" in name or "\\" in name or ":" in name:
        raise ValueError("Mutation target must not contain a path")
    filename = name if name.endswith(".py") else name + ".py"
    stem = filename[:-3]
    if not stem.isidentifier() or keyword.iskeyword(stem) or stem.upper() in _WINDOWS_RESERVED:
        raise ValueError("Mutation target must be a valid Python module filename")
    return filename


def reject_link_or_reparse(path):
    """Reject an existing symlink or Windows reparse point at the target."""
    try:
        info = Path(path).lstat()
    except FileNotFoundError:
        return
    attributes = getattr(info, "st_file_attributes", 0)
    if stat.S_ISLNK(info.st_mode) or attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
        raise ValueError(f"Mutation target must not be a link or reparse point: {os.fspath(path)}")
