"""Tests for Instagram scraping and media extraction."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from gram2email.instagram import (
    create_loader,
    download_media_content,
    extract_media_items,
    fetch_recent_posts,
)


def test_create_loader():
    loader = create_loader(user_agent="CustomBot/1.0")
    assert loader is not None
    assert loader.context.user_agent == "CustomBot/1.0"


def test_download_media_content_success():
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.content = b"fake_img"
    mock_response.headers = {"Content-Type": "image/png"}
    mock_session.get.return_value = mock_response

    content, content_type = download_media_content("https://example.com/test.png", session=mock_session)
    assert content == b"fake_img"
    assert content_type == "image/png"


def test_download_media_content_failure():
    mock_session = MagicMock()
    mock_session.get.side_effect = Exception("Network timeout")

    content, content_type = download_media_content("https://example.com/test.png", session=mock_session)
    assert content is None
    assert content_type == "image/jpeg"


def test_extract_media_items_single_image():
    mock_post = MagicMock()
    mock_post.shortcode = "TEST1234"
    mock_post.typename = "GraphImage"
    mock_post.url = "https://example.com/img.jpg"
    mock_post.is_video = False

    with patch(
        "gram2email.instagram.download_media_content",
        return_value=(b"img_bytes", "image/jpeg"),
    ):
        items = extract_media_items(mock_post, download=True)

    assert len(items) == 1
    assert items[0].url == "https://example.com/img.jpg"
    assert items[0].content == b"img_bytes"
    assert items[0].cid == "TEST1234_img_0"


def test_extract_media_items_sidecar():
    mock_post = MagicMock()
    mock_post.shortcode = "CAROUSEL"
    mock_post.typename = "GraphSidecar"

    node1 = MagicMock(display_url="https://example.com/slide1.jpg", is_video=False)
    node2 = MagicMock(display_url="https://example.com/slide2.jpg", is_video=True)
    mock_post.get_sidecar_nodes.return_value = [node1, node2]

    with patch(
        "gram2email.instagram.download_media_content",
        return_value=(b"slide_bytes", "image/jpeg"),
    ):
        items = extract_media_items(mock_post, download=True)

    assert len(items) == 2
    assert items[0].url == "https://example.com/slide1.jpg"
    assert items[0].media_type == "image"
    assert items[1].url == "https://example.com/slide2.jpg"
    assert items[1].media_type == "video"


@patch("instaloader.Profile.from_username")
def test_fetch_recent_posts_private_account(mock_from_username):
    mock_profile = MagicMock()
    mock_profile.is_private = True
    mock_from_username.return_value = mock_profile

    with pytest.raises(ValueError, match="is private"):
        fetch_recent_posts("private_user")


@patch("instaloader.Profile.from_username")
def test_fetch_recent_posts_success(mock_from_username):
    mock_profile = MagicMock()
    mock_profile.is_private = False

    mock_post = MagicMock()
    mock_post.shortcode = "POST123"
    mock_post.caption = "Test caption"
    mock_post.date_utc = datetime(2026, 9, 17, 10, 0, 0, tzinfo=UTC)
    mock_post.is_video = False
    mock_post.likes = 10
    mock_post.comments = 2
    mock_post.typename = "GraphImage"
    mock_post.url = "https://example.com/image.jpg"

    mock_profile.get_posts.return_value = [mock_post]
    mock_from_username.return_value = mock_profile

    with patch(
        "gram2email.instagram.download_media_content",
        return_value=(b"data", "image/jpeg"),
    ):
        posts = fetch_recent_posts("public_user", max_posts=1)

    assert len(posts) == 1
    assert posts[0].shortcode == "POST123"
    assert posts[0].caption == "Test caption"
    assert posts[0].owner_username == "public_user"


def test_parse_cookie_string():
    from gram2email.instagram import parse_cookie_string

    assert parse_cookie_string("simple_session_id") == {"sessionid": "simple_session_id"}
    res = parse_cookie_string("sessionid=abc123xyz; ds_user_id=45678; csrftoken=tok123")
    assert res == {"sessionid": "abc123xyz", "ds_user_id": "45678", "csrftoken": "tok123"}


def test_create_loader_with_session_id():
    loader = create_loader(session_id="sessionid=abc123xyz; csrftoken=tok123", instagram_user="myuser")
    assert loader.context._session.cookies.get_dict().get("sessionid") == "abc123xyz"
    assert loader.context._session.headers.get("X-CSRFToken") == "tok123"
    assert loader.context.username == "myuser"


def test_create_loader_with_json_session_file(tmp_path):
    import json

    session_file = tmp_path / "session.json"
    session_file.write_text(json.dumps({"sessionid": "json_sess_id", "csrftoken": "json_csrf"}))

    loader = create_loader(session_file=str(session_file), instagram_user="jsonuser")
    assert loader.context._session.cookies.get_dict().get("sessionid") == "json_sess_id"
    assert loader.context._session.headers.get("X-CSRFToken") == "json_csrf"
    assert loader.context.username == "jsonuser"


def test_create_loader_with_api_key():
    loader = create_loader(api_key="secret_api_key_123")
    assert loader.context._session.headers.get("Authorization") == "Bearer secret_api_key_123"
    assert loader.context._session.headers.get("X-API-Key") == "secret_api_key_123"


@patch("instaloader.Instaloader.login")
@patch("instaloader.Instaloader.save_session_to_file")
def test_create_loader_with_credentials(mock_save, mock_login, tmp_path):
    session_file = tmp_path / "session-testuser"
    loader = create_loader(
        username="testuser",
        password="testpassword",
        session_file=str(session_file),
    )
    mock_login.assert_called_once_with("testuser", "testpassword")
    mock_save.assert_called_once()
    assert loader is not None
