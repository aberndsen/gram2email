"""Tests for configuration dataclasses."""

from pathlib import Path

from gram2email.config import AppSettings, SMTPSettings, User


def test_smtp_settings_defaults():
    smtp = SMTPSettings()
    assert smtp.host == "smtp.gmail.com"
    assert smtp.port == 587
    assert smtp.use_tls is True
    assert smtp.use_ssl is False
    assert smtp.effective_sender == ""


def test_smtp_settings_effective_sender():
    smtp1 = SMTPSettings(username="user@example.com", sender="")
    assert smtp1.effective_sender == "user@example.com"

    smtp2 = SMTPSettings(username="user@example.com", sender="custom@example.com")
    assert smtp2.effective_sender == "custom@example.com"


def test_user_dataclass():
    u1 = User(email="alice@example.com", name="Alice")
    assert u1.formatted_address == "Alice <alice@example.com>"

    u2 = User(email="bob@example.com")
    assert u2.formatted_address == "bob@example.com"


def test_effective_recipients():
    settings = AppSettings(
        users=[
            User(email="alice@example.com", name="Alice"),
            User(email="bob@example.com"),
        ],
        recipients=["charlie@example.com"],
    )
    expected = [
        "Alice <alice@example.com>",
        "bob@example.com",
        "charlie@example.com",
    ]
    assert settings.effective_recipients == expected


def test_app_settings_defaults():
    settings = AppSettings()
    assert settings.accounts == []
    assert settings.users == []
    assert settings.recipients == []
    assert settings.effective_recipients == []
    assert settings.max_posts_per_account == 5
    assert settings.state_file == "seen_posts.json"
    assert settings.session_file is None
    assert settings.request_timeout == 30
    assert isinstance(settings.state_path, Path)
    assert settings.download_media is True
    assert settings.dry_run is False
    assert settings.verbose is False


def test_instagram_auth_settings():
    from gram2email.config import InstagramAuthSettings

    auth = InstagramAuthSettings(username="myuser", password="mypassword", session_id="sess123")
    assert auth.username == "myuser"
    assert auth.password == "mypassword"
    assert auth.session_id == "sess123"

    settings = AppSettings(
        instagram=auth,
        session_file="custom_session.json",
    )
    effective = settings.effective_instagram_auth
    assert effective.username == "myuser"
    assert effective.password == "mypassword"
    assert effective.session_id == "sess123"
    assert effective.session_file == "custom_session.json"
