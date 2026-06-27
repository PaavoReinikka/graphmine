"""Tests for encoder helpers (the subsystem heuristic)."""
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
