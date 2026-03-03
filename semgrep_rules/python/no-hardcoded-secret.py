import os

# ruleid: no-hardcoded-secret
password = "CHANGE_ME"

# ruleid: no-hardcoded-secret
api_key = "placeholder_key"

# ruleid: no-hardcoded-secret
secret_key = "my_secret_value"

# ruleid: no-hardcoded-secret
auth_token = "placeholder_token"

# ruleid: no-hardcoded-secret
private_key = "placeholder_private"

# ruleid: no-hardcoded-secret
APIKEY = "placeholder_key"

# ok: no-hardcoded-secret
password = ""

# ok: no-hardcoded-secret
password = os.environ.get("PASSWORD")

# ok: no-hardcoded-secret
username = "admin"

# ok: no-hardcoded-secret
database_url = "postgresql://localhost/mydb"

# ok: no-hardcoded-secret
api_key = ""
