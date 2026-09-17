"""Tests for pipeline orchestrator."""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from gram2email.config import AppSettings, SMTPSettings
from gram2email.instagram import InstagramPost
from gram2email.pipeline import run_pipeline
from gram2email.storage import load_seen_posts


def sample_post(shortcode: str) -> InstagramPost:
    return InstagramPost(
        shortcode=shortcode,
        url=f"https://www.instagram.com/p/{shortcode}/",
        owner_username="testuser",
        caption=f"Caption for {shortcode}",
        date_utc=datetime(2026, 9, 17, 10, 0, 0, tzinfo=UTC),
    )


def test_run_pipeline_no_accounts(tmp_path):
    settings = AppSettings(accounts=[], state_file=str(tmp_path / "state.json"))
    assert run_pipeline(settings) == 0


def test_run_pipeline_no_recipients(tmp_path):
    settings = AppSettings(
        accounts=["testuser"],
        recipients=[],
        state_file=str(tmp_path / "state.json"),
        dry_run=False,
    )
    with pytest.raises(ValueError, match="No email recipients configured"):
        run_pipeline(settings)


@patch("gram2email.pipeline.fetch_recent_posts")
@patch("gram2email.pipeline.send_email")
def test_run_pipeline_success(mock_send, mock_fetch, tmp_path):
    state_file = tmp_path / "state.json"
    settings = AppSettings(
        accounts=["testuser"],
        recipients=["user@example.com"],
        state_file=str(state_file),
        smtp=SMTPSettings(username="bot@example.com"),
    )

    mock_fetch.return_value = [sample_post("p1"), sample_post("p2")]

    sent_count = run_pipeline(settings)
    assert sent_count == 2
    assert mock_send.call_count == 2

    # State file should have saved both posts
    seen = load_seen_posts(state_file)
    assert seen == {"p1", "p2"}

    # Run again with one new post
    mock_fetch.return_value = [sample_post("p1"), sample_post("p2"), sample_post("p3")]
    sent_count_2 = run_pipeline(settings)
    assert sent_count_2 == 1
    assert mock_send.call_count == 3
    assert load_seen_posts(state_file) == {"p1", "p2", "p3"}


@patch("gram2email.pipeline.fetch_recent_posts")
@patch("gram2email.pipeline.send_email")
def test_run_pipeline_with_users(mock_send, mock_fetch, tmp_path):
    from gram2email.config import User

    state_file = tmp_path / "state.json"
    settings = AppSettings(
        accounts=["testuser"],
        users=[User(email="alice@example.com", name="Alice")],
        state_file=str(state_file),
    )
    mock_fetch.return_value = [sample_post("p1")]
    sent_count = run_pipeline(settings)
    assert sent_count == 1
    assert mock_send.call_count == 1
    sent_msg = mock_send.call_args[0][0]
    assert sent_msg["To"] == "Alice <alice@example.com>"


@patch("gram2email.pipeline.fetch_recent_posts")
@patch("gram2email.pipeline.send_email")
def test_run_pipeline_dry_run(mock_send, mock_fetch, tmp_path):
    state_file = tmp_path / "state.json"
    settings = AppSettings(
        accounts=["testuser"],
        recipients=["user@example.com"],
        state_file=str(state_file),
        dry_run=True,
    )

    mock_fetch.return_value = [sample_post("p1")]
    sent_count = run_pipeline(settings)

    assert sent_count == 1
    mock_send.assert_not_called()
    # State file must not be modified in dry run
    assert load_seen_posts(state_file) == set()


@patch("gram2email.pipeline.fetch_recent_posts")
@patch("gram2email.pipeline.send_email")
def test_cron_10_minute_stateful_deduplication(mock_send, mock_fetch, tmp_path):
    state_file = tmp_path / "cron_state.json"
    settings = AppSettings(
        accounts=["natgeo"],
        recipients=["user@example.com"],
        state_file=str(state_file),
        max_posts_per_account=5,
    )

    # 1. First run at T=00:00: Account has 5 posts (P1..P5).
    # All 5 are unseen, so all 5 are emailed and saved to seen_posts.json.
    initial_posts = [sample_post(f"P{i}") for i in range(1, 6)]
    mock_fetch.return_value = initial_posts
    sent_t0 = run_pipeline(settings)
    assert sent_t0 == 5
    assert mock_send.call_count == 5
    assert load_seen_posts(state_file) == {"P1", "P2", "P3", "P4", "P5"}

    # 2. Second cron run at T=00:10: Same 5 posts inspected.
    # All are already in seen_posts.json -> 0 emails sent!
    mock_send.reset_mock()
    mock_fetch.return_value = initial_posts
    sent_t10 = run_pipeline(settings)
    assert sent_t10 == 0
    assert mock_send.call_count == 0

    # 3. Third cron run at T=00:20: Still the same 5 posts.
    mock_send.reset_mock()
    mock_fetch.return_value = initial_posts
    sent_t20 = run_pipeline(settings)
    assert sent_t20 == 0
    assert mock_send.call_count == 0

    # 4. Fourth cron run at T=00:30: 2 new posts published (P6, P7)!
    # Last 5 posts are now [P3, P4, P5, P6, P7].
    # P3, P4, P5 are already seen, so ONLY P6 and P7 are emailed!
    mock_send.reset_mock()
    updated_posts = [sample_post(f"P{i}") for i in range(3, 8)]
    mock_fetch.return_value = updated_posts
    sent_t30 = run_pipeline(settings)
    assert sent_t30 == 2
    assert mock_send.call_count == 2
    assert load_seen_posts(state_file) == {"P1", "P2", "P3", "P4", "P5", "P6", "P7"}

    # 5. Fifth cron run at T=00:40: Same [P3..P7] posts inspected.
    # All are already in seen_posts.json -> 0 emails sent!
    mock_send.reset_mock()
    mock_fetch.return_value = updated_posts
    sent_t40 = run_pipeline(settings)
    assert sent_t40 == 0
    assert mock_send.call_count == 0
