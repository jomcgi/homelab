# Tests for unused-auth-variable rule.
import os

# ruleid: unused-auth-variable
MY_SERVICE_API_KEY = os.getenv("MY_SERVICE_API_KEY", "")

# ruleid: unused-auth-variable
WEBHOOK_API_KEY = os.getenv("WEBHOOK_API_KEY")

# ok: key is compared in a validation check
VALID_API_KEY = os.getenv("VALID_API_KEY", "")
if VALID_API_KEY:
    pass  # auth is configured

# ok: not an API key variable name
DATABASE_URL = os.getenv("DATABASE_URL", "postgres://localhost/db")

# ok: plain string constant (not from env)
SOME_API_KEY = "hardcoded-value"
