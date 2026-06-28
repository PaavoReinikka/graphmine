"""Tests for encoder helpers (the subsystem heuristic + auto-depth)."""
from graphmine.encoders.base import auto_subsystem_depth
from graphmine.encoders.git_cochange import _subsystem as cc_sub
from graphmine.encoders.graph_coref import _subsystem as cr_sub


def test_subsystem_uses_directory_not_filename():
    # depth-2 of a deep file -> its directory
    assert cc_sub("src/database/x.sql", 2) == "src/database"
    # a shallow file must NOT become its own subsystem (the bug we fixed)
    assert cc_sub("documents/IPA-framework.md", 2) == "documents"
    assert cc_sub("src/x.py", 1) == "src"
    assert cc_sub("README.md", 1) == "(root)"        # root-level file


def test_coref_subsystem_directory_and_none():
    assert cr_sub("src/a/b.py", 2) == "src/a"
    assert cr_sub("top.py", 1) == "(root)"
    assert cr_sub(None, 1) == "?"


def test_auto_depth_top_level_components():
    # components at the top level (src/, tests/, docs/) -> depth 1 (Flask-like)
    paths = ["src/flask/app.py", "src/flask/cli.py", "tests/test_app.py",
             "tests/test_cli.py", "docs/index.rst", "examples/x/app.py"]
    assert auto_subsystem_depth(paths) == 1


def test_auto_depth_monorepo_under_src():
    # everything under src/ -> descend to depth 2 (the component level)
    paths = (["src/console/a.js"] + [f"src/database/{i}.sql" for i in range(8)] +
             ["src/functions/x.py", "src/functions/y.py", "infra/main.bicep"])
    assert auto_subsystem_depth(paths) == 2


def test_auto_depth_flat_and_monolithic():
    assert auto_subsystem_depth(["a.py", "b.py", "c.py"]) == 1          # root files
    assert auto_subsystem_depth([f"src/{c}.py" for c in "abcde"]) == 1  # flat src, won't split
