# Tests for dulwich-commit-missing-author rule.
from dulwich import porcelain

# ruleid: dulwich-commit-missing-author
porcelain.commit(repo, message=b"fix: update config")

# ruleid: dulwich-commit-missing-author
porcelain.commit(
    repo, message=b"chore: bump version", committer=b"Bot <bot@example.com>"
)

# ok: dulwich-commit-missing-author
porcelain.commit(
    repo,
    message=b"fix: update config",
    author=b"Bot <bot@example.com>",
    committer=b"Bot <bot@example.com>",
)
