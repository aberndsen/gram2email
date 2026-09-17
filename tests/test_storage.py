"""Tests for state storage and persistence functions."""

import json

from gram2email.storage import (
    is_post_seen,
    load_seen_posts,
    mark_post_seen,
    save_seen_posts,
)


def test_load_seen_posts_missing_file(tmp_path):
    missing_file = tmp_path / "nonexistent.json"
    seen = load_seen_posts(missing_file)
    assert seen == set()


def test_load_seen_posts_empty_file(tmp_path):
    empty_file = tmp_path / "empty.json"
    empty_file.write_text("", encoding="utf-8")
    seen = load_seen_posts(empty_file)
    assert seen == set()


def test_load_seen_posts_invalid_json(tmp_path):
    invalid_file = tmp_path / "invalid.json"
    invalid_file.write_text("{broken", encoding="utf-8")
    seen = load_seen_posts(invalid_file)
    assert seen == set()


def test_load_seen_posts_list_format(tmp_path):
    state_file = tmp_path / "list_state.json"
    state_file.write_text(json.dumps(["post1", "post2"]), encoding="utf-8")
    seen = load_seen_posts(state_file)
    assert seen == {"post1", "post2"}


def test_load_seen_posts_dict_format(tmp_path):
    state_file = tmp_path / "dict_state.json"
    state_file.write_text(
        json.dumps({"seen_posts": ["postA", "postB"], "count": 2}),
        encoding="utf-8",
    )
    seen = load_seen_posts(state_file)
    assert seen == {"postA", "postB"}


def test_save_and_reload_seen_posts(tmp_path):
    state_file = tmp_path / "subdir" / "state.json"
    initial_posts = {"code1", "code2", "code3"}
    save_seen_posts(state_file, initial_posts)

    assert state_file.exists()
    reloaded = load_seen_posts(state_file)
    assert reloaded == initial_posts


def test_is_and_mark_post_seen():
    seen = {"post1", "post2"}
    assert is_post_seen(seen, "post1") is True
    assert is_post_seen(seen, "post3") is False

    updated = mark_post_seen(seen, "post3")
    assert is_post_seen(updated, "post3") is True
    assert len(updated) == 3
    # Original set remains unchanged (functional pure behavior)
    assert len(seen) == 2
