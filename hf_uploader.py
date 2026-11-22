"""Upload explicitly selected, reviewed files to a user-specified Hugging Face repo."""

import argparse
import os
from pathlib import Path
import stat

from huggingface_hub import HfApi


PRIVATE_DIRS = {".git", "memory", "lessons", "meta_ai_package", "projects", "logs"}
PRIVATE_NAMES = {".env", "credentials.json", "token.json", "secrets.json", "config.json"}
PRIVATE_SUFFIXES = {".log", ".db", ".pem", ".key", ".p12", ".pfx"}


def _is_link_or_reparse(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def select_files(folder: Path, names: list[str]) -> list[tuple[Path, str]]:
    """Validate all selections before any upload; never follow selected symlinks."""
    folder = Path(folder)
    if not folder.is_dir():
        raise ValueError("The source folder must be an existing directory.")
    absolute_folder = folder.absolute()
    for ancestor in (absolute_folder, *absolute_folder.parents):
        if _is_link_or_reparse(ancestor):
            raise ValueError("The source folder must not contain links or reparse points.")
    if not names:
        raise ValueError("Select at least one file explicitly.")

    selected = []
    seen = set()
    for name in names:
        relative = Path(name)
        if relative.anchor or not relative.parts or ".." in relative.parts:
            raise ValueError(f"Not a relative file path: {name}")
        if any(part.lower() in PRIVATE_DIRS for part in relative.parts):
            raise ValueError(f"Private directory is not allowed: {name}")
        filename = relative.name.lower()
        if (filename in PRIVATE_NAMES or filename.startswith(".env.")
                or any(word in filename for word in ("secret", "token", "credential", "api_key"))
                or relative.suffix.lower() in PRIVATE_SUFFIXES):
            raise ValueError(f"Private file is not allowed: {name}")
        current = folder
        for part in relative.parts:
            current = current / part
            try:
                is_link = _is_link_or_reparse(current)
            except FileNotFoundError as exc:
                raise ValueError(f"Not an existing file: {name}") from exc
            if is_link:
                raise ValueError(f"Symlinks and reparse points are not allowed: {name}")
        if not current.is_file():
            raise ValueError(f"Not an existing file: {name}")
        target = relative.as_posix()
        if target in seen:
            raise ValueError(f"File selected more than once: {name}")
        seen.add(target)
        selected.append((current, target))
    return selected


def upload_fenrir_to_hf(folder: Path, repo_id: str, names: list[str], token: str):
    if not repo_id.strip():
        raise ValueError("A target repository is required.")
    if not token.strip():
        raise ValueError("Set HF_TOKEN to your own Hugging Face token.")
    files = select_files(folder, names)
    api = HfApi(token=token)
    for source, target in files:
        api.upload_file(
            path_or_fileobj=str(source),
            path_in_repo=target,
            repo_id=repo_id,
            repo_type="model",
        )


def main():
    parser = argparse.ArgumentParser(
        description="Select reviewed files explicitly. File selection does not prove they are private-data free."
    )
    parser.add_argument("--folder", required=True, type=Path, help="Directory containing reviewed files")
    parser.add_argument("--repo-id", required=True, help="Your existing Hugging Face model repository")
    parser.add_argument("--file", required=True, action="append", dest="files", help="Relative file path; repeat to select more")
    parser.add_argument("--upload", action="store_true", help="Actually upload; without this flag only validate and list")
    args = parser.parse_args()
    try:
        selected = select_files(args.folder, args.files)
        for _, name in selected:
            print(name)
        if args.upload:
            upload_fenrir_to_hf(args.folder, args.repo_id, args.files, os.environ.get("HF_TOKEN", ""))
            print("Selected files uploaded.")
        else:
            print("Preview only; nothing uploaded.")
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
