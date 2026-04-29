import os

SAFE_FILE_DIR = os.path.join(os.path.expanduser("~"), ".sauce-mcp", "files")


def validate_path(file_path: str) -> str:
    """Validate that a file path resolves within SAFE_FILE_DIR."""
    os.makedirs(SAFE_FILE_DIR, exist_ok=True)
    resolved = os.path.realpath(os.path.join(SAFE_FILE_DIR, os.path.basename(file_path)))
    if not resolved.startswith(os.path.realpath(SAFE_FILE_DIR)):
        raise ValueError(
            f"Path '{file_path}' resolves outside the safe directory. "
            f"Files are restricted to {SAFE_FILE_DIR}"
        )
    return resolved
