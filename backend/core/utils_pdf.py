import hashlib
from pathlib import Path

def sha256_bytes(b: bytes) -> str:
    import hashlib
    h = hashlib.sha256()
    h.update(b)
    return h.hexdigest()

def sha256_file(path: Path) -> str:
    with open(path, "rb") as f:
        return sha256_bytes(f.read())