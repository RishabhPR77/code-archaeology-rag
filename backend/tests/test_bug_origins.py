from pathlib import Path

import git
import pytest

from ingestion.bug_origins import is_docs_or_tests, find_bug_origins, summarize
from ingestion.git_loader import load_commits

CALC_V1 = "def add(a, b):\n    return a + b\n\n\ndef div(a, b):\n    return a / b\n"
CALC_BUGGY = CALC_V1.replace("a / b", "a // b")
CALC_COMMENTED = CALC_BUGGY.replace("\n\ndef div", "\n# divide two numbers\ndef div")
CALC_FIXED = "def add(a, b):\n    return a + b\n\n# divide two numbers\ndef div(a, b):\n    return a / b\n"
TEST_V1 = "from calc import div\n\n\ndef test_div():\n    assert div(4, 2) == 2\n"


def _commit(repo: git.Repo, files: dict[str, str], message: str, date: str, author: str = "alice") -> str:
    for path, text in files.items():
        target = Path(repo.working_tree_dir, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    repo.git.add(A=True)
    who = {"GIT_AUTHOR_NAME": author, "GIT_AUTHOR_EMAIL": f"{author}@x.io",
           "GIT_COMMITTER_NAME": author, "GIT_COMMITTER_EMAIL": f"{author}@x.io",
           "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
    repo.git.commit("-m", message, env=who)
    return repo.head.commit.hexsha


@pytest.fixture
def history(tmp_path):
    """A tiny repo where one commit introduces a bug and a later commit fixes it."""
    repo = git.Repo.init(tmp_path / "src")
    repo.git.config("core.autocrlf", "false")
    shas = {
        "base": _commit(repo, {"calc.py": CALC_V1, "tests/test_calc.py": TEST_V1}, "add calculator",
                        "2024-01-01T10:00:00"),
        "bug": _commit(repo, {"calc.py": CALC_BUGGY}, "use floor division for speed", "2024-01-10T10:00:00", "bob"),
        "docs": _commit(repo, {"calc.py": CALC_COMMENTED, "README.md": "Calculator\nTODO\n"}, "docs: explain div",
                        "2024-01-20T10:00:00"),
        "fix": _commit(repo, {"calc.py": CALC_FIXED, "tests/test_calc.py": TEST_V1 + "    assert div(5, 2) == 2.5\n"},
                       "fix division returning integers", "2024-02-09T10:00:00"),
        "readme": _commit(repo, {"README.md": "Calculator\n"}, "fix typo in readme", "2024-02-10T10:00:00"),
        "added": _commit(repo, {"calc.py": CALC_FIXED + "\n\ndef mod(a, b):\n    return a % b\n"},
                         "fix: add the missing mod function", "2024-02-11T10:00:00"),
    }
    return repo, shas


def _by_sha(fixes):
    return {f["sha"]: f for f in fixes}


def test_fix_is_traced_to_the_commit_that_wrote_the_bug(history):
    repo, shas = history
    fixes = _by_sha(find_bug_origins(repo.working_tree_dir, load_commits(repo.working_tree_dir, max_count=10)))
    assert set(fixes) == {shas["fix"][:7], shas["readme"][:7], shas["added"][:7]}   # only fix commits

    fix = fixes[shas["fix"][:7]]
    assert fix["status"] == "traced"
    # The removed blank line and the test-file change are ignored; only the buggy line is blamed
    assert [(o["sha"], o["lines"], o["author"], o["ingested"]) for o in fix["origins"]] == [
        (shas["bug"][:7], 1, "bob", True)]
    assert fix["days"] == 30


def test_docs_only_and_add_only_fixes_have_nothing_to_trace(history):
    repo, shas = history
    fixes = _by_sha(find_bug_origins(repo.working_tree_dir, load_commits(repo.working_tree_dir, max_count=10)))
    assert fixes[shas["readme"][:7]]["status"] == "nothing_to_trace"
    assert fixes[shas["added"][:7]]["status"] == "nothing_to_trace"
    assert fixes[shas["added"][:7]]["origins"] == []


def test_lines_older_than_a_shallow_clone_are_reported_as_older(history, tmp_path):
    repo, shas = history
    # Depth 4 keeps the fix and its parent, but the buggy line was written before the cut
    shallow = git.Repo.clone_from(Path(repo.working_tree_dir).as_uri(), tmp_path / "shallow", depth=4)
    fixes = _by_sha(find_bug_origins(shallow.working_tree_dir, load_commits(shallow.working_tree_dir, max_count=3)))
    fix = fixes[shas["fix"][:7]]
    assert fix["status"] == "older" and fix["origins"] == [] and fix["older_lines"] == 1


def test_summary_counts_and_repeat_origins(history):
    repo, shas = history
    summary = summarize(find_bug_origins(repo.working_tree_dir, load_commits(repo.working_tree_dir, max_count=10)))
    assert summary == {"fixes": 3, "traced": 1, "older": 0, "nothing_to_trace": 2, "median_days": 30,
                       "repeat_origins": []}

    origin = {"sha": "abc1234", "message": "m", "author": "a", "timestamp": "2024-01-01T00:00:00",
              "lines": 2, "ingested": True}
    twice = summarize([{"origins": [origin], "status": "traced", "days": 3},
                       {"origins": [origin], "status": "traced", "days": 5}])
    assert twice["repeat_origins"] == [{"sha": "abc1234", "message": "m", "author": "a",
                                        "timestamp": "2024-01-01T00:00:00", "ingested": True, "fixes": 2}]
    assert twice["median_days"] == 4


@pytest.mark.parametrize("path, skipped", [
    ("src/app.py", False), ("README.md", True), ("docs/guide.rst", True), ("CHANGELOG", True),
    ("tests/test_app.py", True), ("src/app_test.go", True), ("web/button.spec.ts", True),
    ("conftest.py", True), ("poetry.lock", True), ("src/contest.py", False),
])
def test_docs_and_tests_are_not_blamed(path, skipped):
    assert is_docs_or_tests(path) is skipped
