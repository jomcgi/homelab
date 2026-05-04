# Tests for subprocess-run-no-timeout rule.
import subprocess


def bad_bare_call():
    # ruleid: subprocess-run-no-timeout
    subprocess.run(["ls", "-la"])


def bad_with_check_no_timeout():
    # ruleid: subprocess-run-no-timeout
    subprocess.run(["git", "status"], check=True)


def ok_with_timeout():
    # ok: timeout is specified
    subprocess.run(["sleep", "1"], timeout=30)


def ok_with_check_and_timeout():
    # ok: both check and timeout are specified
    subprocess.run(["git", "fetch"], check=True, timeout=60)


def bad_subprocess_call_no_timeout():
    # ruleid: subprocess-run-no-timeout
    subprocess.call(["echo", "hello"])


def ok_subprocess_call_with_timeout():
    # ok: timeout is specified
    subprocess.call(["echo", "hello"], timeout=10)
