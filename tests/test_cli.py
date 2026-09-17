"""Tests for command-line interface and configuration parser."""

from unittest.mock import patch

from gram2email.cli import build_parser, main, parse_args_to_settings


def test_build_parser():
    parser = build_parser()
    assert parser is not None


def test_parse_args_with_yaml_config(tmp_path):
    config_file = tmp_path / "test_config.yaml"
    config_content = """
accounts:
  - natgeo
  - nasa
recipients:
  - reader@example.com
smtp:
  host: smtp.custom.com
  port: 2525
  username: testuser
  password: secretpassword
  use_tls: false
  use_ssl: false
max_posts_per_account: 3
dry_run: true
"""
    config_file.write_text(config_content, encoding="utf-8")

    settings = parse_args_to_settings(["--config", str(config_file)])
    assert settings.accounts == ["natgeo", "nasa"]
    assert settings.recipients == ["reader@example.com"]
    assert settings.smtp.host == "smtp.custom.com"
    assert settings.smtp.port == 2525
    assert settings.smtp.username == "testuser"
    assert settings.smtp.use_tls is False
    assert settings.max_posts_per_account == 3
    assert settings.dry_run is True
    assert settings.state_file == str(tmp_path / "seen_posts.json")


def test_parse_args_with_users_list(tmp_path):
    config_file = tmp_path / "test_users_config.yaml"
    config_content = """
accounts:
  - natgeo
users:
  - email: alice@example.com
    name: Alice Smith
  - email: bob@example.com
"""
    config_file.write_text(config_content, encoding="utf-8")
    settings = parse_args_to_settings(["--config", str(config_file)])
    assert len(settings.users) == 2
    assert settings.users[0].email == "alice@example.com"
    assert settings.users[0].name == "Alice Smith"
    assert settings.users[1].email == "bob@example.com"
    assert settings.effective_recipients == [
        "Alice Smith <alice@example.com>",
        "bob@example.com",
    ]


def test_cli_flags_override_config(tmp_path):
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(
        """
accounts:
  - natgeo
recipients:
  - reader@example.com
dry_run: false
""",
        encoding="utf-8",
    )

    settings = parse_args_to_settings(["--config", str(config_file), "--dry_run", "true"])
    assert settings.dry_run is True


@patch("gram2email.cli.run_pipeline")
def test_main_success(mock_pipeline, tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        """
accounts:
  - testaccount
recipients:
  - recipient@example.com
dry_run: true
""",
        encoding="utf-8",
    )

    mock_pipeline.return_value = 1
    exit_code = main(["--config", str(config_file)])
    assert exit_code == 0
    mock_pipeline.assert_called_once()


def test_main_no_accounts():
    exit_code = main(["--accounts", "[]"])
    assert exit_code == 1
