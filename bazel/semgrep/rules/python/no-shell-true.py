import subprocess

# ruleid: no-shell-true
subprocess.run("ls -la", shell=True)

# ruleid: no-shell-true
subprocess.call("echo hello", shell=True)

# ruleid: no-shell-true
subprocess.Popen("cat /etc/passwd", shell=True)

# ruleid: no-shell-true
subprocess.check_call("make build", shell=True)

# ruleid: no-shell-true
subprocess.check_output("git status", shell=True)

# ok: no-shell-true
subprocess.run(["ls", "-la"])

# ok: no-shell-true
subprocess.call(["echo", "hello"])

# ok: no-shell-true
subprocess.Popen(["cat", "/etc/passwd"])

# ok: no-shell-true
subprocess.check_call(["make", "build"])

# ok: no-shell-true
subprocess.check_output(["git", "status"])
