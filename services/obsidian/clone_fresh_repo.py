from pathlib import Path
import subprocess

def clone_repo():
    clone_command = """ \
    GIT_SSH_COMMAND="ssh -i ~/.ssh/obs_repo_key" \
    git clone git@github.com:jomcgi/obsidian.git repo \
        --branch main \
        --depth 1
    """

    repo_path = Path(__file__).parent.joinpath("repo")
    if repo_path.exists():
        subprocess.run(f"rm -rf {repo_path}", shell=True)
    repo_path.mkdir(parents=True, exist_ok=True)

    # Clone the repository
    subprocess.run(clone_command, shell=True, cwd=repo_path)