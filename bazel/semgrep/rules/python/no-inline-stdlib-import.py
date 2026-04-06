# Tests for no-inline-stdlib-import rule.
# Positive cases have `# ruleid:` on the line before the import.
# Negative cases have `# ok:` on the line before the import.

# Module-level imports are always OK and do not require annotations.
import os as _os


# --- Violations (should be flagged) ---


def bad_inline_datetime():
    # ruleid: no-inline-stdlib-import
    from datetime import datetime

    return datetime.now()


def bad_inline_os():
    # ruleid: no-inline-stdlib-import
    import os

    return os.getcwd()


def bad_inline_sys():
    # ruleid: no-inline-stdlib-import
    import sys

    return sys.argv


def bad_inline_typing():
    # ruleid: no-inline-stdlib-import
    from typing import Optional

    return None


def bad_inline_sqlalchemy():
    # ruleid: no-inline-stdlib-import
    from sqlalchemy import text

    return text("SELECT 1")


def bad_inline_sqlalchemy_exc():
    # ruleid: no-inline-stdlib-import
    from sqlalchemy.exc import IntegrityError

    raise IntegrityError("test", {}, None)


def bad_inline_sqlalchemy_orm():
    # ruleid: no-inline-stdlib-import
    from sqlalchemy.orm import Session

    return Session


def bad_inline_logging():
    # ruleid: no-inline-stdlib-import
    import logging

    return logging.getLogger(__name__)


class MyClass:
    def bad_method_inline_json(self):
        # ruleid: no-inline-stdlib-import
        import json

        return json.dumps({})


# --- OK cases (should not be flagged) ---


def ok_uses_module_level_import():
    # ok: _os was imported at module level
    return _os.getcwd()


def ok_non_stdlib_import():
    # ok: httpx is not in the banned stdlib/core list
    import httpx

    return httpx.AsyncClient()


def ok_app_code_import():
    # ok: application-code imports are allowed inline
    from myapp.utils import helper

    return helper()


def ok_non_banned_third_party():
    # ok: sqlmodel is not in the banned list
    from sqlmodel import Session

    return Session


def ok_dotted_import_form():
    # ok: `import os.path` binds $MOD="os.path" which does not match ^(os)$;
    # dotted import form is a known gap in this rule — add the full dotted name
    # to the metavariable-regex if it becomes a real pattern in this codebase.
    import os.path

    return os.path.join("a", "b")
