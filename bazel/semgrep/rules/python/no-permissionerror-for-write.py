# Tests for no-permissionerror-for-write rule.
from pathlib import Path


# ruleid: no-permissionerror-for-write
def bad_open_write_permissionerror(path: str, content: str) -> None:
    try:
        with open(path, "w") as f:
            f.write(content)
    except PermissionError:
        pass  # misses EROFS (errno 30) and ENOSPC (errno 28)


# ruleid: no-permissionerror-for-write
def bad_open_writebinary_permissionerror(path: str, data: bytes) -> None:
    try:
        with open(path, "wb") as f:
            f.write(data)
    except PermissionError as e:
        raise RuntimeError("write failed") from e


# ruleid: no-permissionerror-for-write
def bad_write_text_permissionerror(path: Path, content: str) -> None:
    try:
        path.write_text(content)
    except PermissionError:
        pass


# ruleid: no-permissionerror-for-write
def bad_write_bytes_permissionerror(path: Path, data: bytes) -> None:
    try:
        path.write_bytes(data)
    except PermissionError:
        pass


# ok: catches OSError which covers PermissionError, EROFS, and ENOSPC
def ok_open_write_oserror(path: str, content: str) -> None:
    try:
        with open(path, "w") as f:
            f.write(content)
    except OSError:
        pass


# ok: catches OSError for Path.write_text
def ok_write_text_oserror(path: Path, content: str) -> None:
    try:
        path.write_text(content)
    except OSError:
        pass


# ok: catches OSError for Path.write_bytes
def ok_write_bytes_oserror(path: Path, data: bytes) -> None:
    try:
        path.write_bytes(data)
    except OSError:
        pass


# ok: read-only open — PermissionError is appropriate for reads
def ok_open_read_permissionerror(path: str) -> str:
    try:
        with open(path, "r") as f:
            return f.read()
    except PermissionError:
        return ""
