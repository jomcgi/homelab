import os
import subprocess

# ruleid: no-os-system
os.system("ls -la")

# ruleid: no-os-system
os.system("rm -rf /tmp/build")

# ok: no-os-system
subprocess.run(["ls", "-la"])

# ok: no-os-system
os.path.exists("/tmp/build")

# ok: no-os-system
os.environ.get("HOME")
