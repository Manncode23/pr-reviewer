from app.agents.supervisor import agents_for_file
from app.schemas.pr import FileDiff
from app.tools.diff_parser import parse_patch

PATCH = "@@ -0,0 +1,1 @@\n+x"


def _diff(path: str, status: str = "added", with_hunks: bool = True) -> FileDiff:
    return FileDiff(
        path=path, status=status, additions=1, patch=PATCH,
        hunks=parse_patch(PATCH) if with_hunks else [],
    )


def test_python_source_gets_all_four_agents():
    assert agents_for_file(_diff("app/service.py")) == ["security", "bugs", "style", "tests"]


def test_python_test_file_gets_bugs_and_style_only():
    assert agents_for_file(_diff("tests/test_service.py")) == ["bugs", "style"]


def test_removed_file_is_skipped():
    assert agents_for_file(_diff("app/old.py", status="removed")) == []


def test_docs_are_skipped():
    assert agents_for_file(_diff("README.md")) == []


def test_javascript_gets_security_and_bugs():
    assert agents_for_file(_diff("web/app.js")) == ["security", "bugs"]


def test_file_without_hunks_is_skipped():
    assert agents_for_file(_diff("app/big.py", with_hunks=False)) == []


def test_config_files_get_security_only():
    assert agents_for_file(_diff("deploy/config.yaml")) == ["security"]