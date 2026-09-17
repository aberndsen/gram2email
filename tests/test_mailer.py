"""Tests for email message generation and delivery functions."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from gram2email.config import SMTPSettings
from gram2email.instagram import InstagramPost, MediaItem
from gram2email.mailer import (
    build_post_email,
    format_html,
    format_plain_text,
    send_email,
)


def sample_post() -> InstagramPost:
    return InstagramPost(
        shortcode="ABC123xyz",
        url="https://www.instagram.com/p/ABC123xyz/",
        owner_username="nasa",
        caption="Exploring the cosmos.\nJourney to Mars.",
        date_utc=datetime(2026, 9, 17, 12, 0, 0, tzinfo=UTC),
        media_items=[
            MediaItem(
                url="https://instagram.example.com/img1.jpg",
                media_type="image",
                content=b"fake_jpeg_data",
                filename="nasa_0.jpg",
                content_type="image/jpeg",
                cid="ABC123xyz_img_0",
            )
        ],
        likes=12345,
        comments=678,
    )


def test_format_plain_text():
    post = sample_post()
    text = format_plain_text(post)
    assert "@nasa" in text
    assert "https://www.instagram.com/p/ABC123xyz/" in text
    assert "Exploring the cosmos." in text
    assert "12345 likes" in text


def test_format_html():
    post = sample_post()
    html_content = format_html(post)
    assert "@nasa" in html_content
    assert "cid:ABC123xyz_img_0" in html_content
    assert "Exploring the cosmos.<br>\nJourney to Mars." in html_content
    assert "https://www.instagram.com/p/ABC123xyz/" in html_content


def test_build_post_email():
    post = sample_post()
    msg = build_post_email(
        post=post,
        sender="bot@example.com",
        recipients=["reader@example.com"],
    )

    assert msg["From"] == "bot@example.com"
    assert msg["To"] == "reader@example.com"
    assert "[@nasa]" in msg["Subject"]
    assert "Exploring the cosmos." in msg["Subject"]

    # Verify MIME structure
    assert msg.is_multipart()
    parts = list(msg.walk())
    content_types = [p.get_content_type() for p in parts]
    assert "text/plain" in content_types
    assert "text/html" in content_types
    assert "image/jpeg" in content_types


@patch("smtplib.SMTP")
def test_send_email_starttls(mock_smtp_class):
    mock_server = MagicMock()
    mock_smtp_class.return_value.__enter__.return_value = mock_server

    smtp_settings = SMTPSettings(
        host="smtp.example.com",
        port=587,
        username="user",
        password="password",
        use_tls=True,
        use_ssl=False,
    )

    msg = build_post_email(sample_post(), "bot@example.com", ["user@example.com"])
    send_email(msg, smtp_settings)

    mock_smtp_class.assert_called_once_with("smtp.example.com", 587, timeout=30)
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once_with("user", "password")
    mock_server.send_message.assert_called_once_with(msg)


@patch("smtplib.SMTP_SSL")
def test_send_email_ssl(mock_smtp_ssl_class):
    mock_server = MagicMock()
    mock_smtp_ssl_class.return_value.__enter__.return_value = mock_server

    smtp_settings = SMTPSettings(
        host="smtp.example.com",
        port=465,
        username="user",
        password="password",
        use_tls=False,
        use_ssl=True,
    )

    msg = build_post_email(sample_post(), "bot@example.com", ["user@example.com"])
    send_email(msg, smtp_settings)

    mock_server.login.assert_called_once_with("user", "password")
    mock_server.send_message.assert_called_once_with(msg)
