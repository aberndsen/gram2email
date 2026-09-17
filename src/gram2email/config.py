"""Configuration models for gram2email.

Defines typed dataclasses for application settings, SMTP configuration,
and runtime parameters.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SMTPSettings:
    """Settings for the outgoing SMTP email server.

    Parameters
    ----------
    host : str, default "smtp.gmail.com"
        SMTP server hostname. Defaults to "smtp.gmail.com" or `SMTP_HOST` env var.
    port : int, default 587
        SMTP server port (e.g., 587 for STARTTLS, 465 for SSL).
    username : str, default ""
        Username or email address for SMTP authentication.
    password : str, default ""
        Password or app-specific password for SMTP authentication.
    sender : str, default ""
        Email address to appear in the 'From' header. If empty, `username` is used.
    use_tls : bool, default True
        Whether to upgrade connection using STARTTLS.
    use_ssl : bool, default False
        Whether to initiate an SSL/TLS connection directly (typically port 465).
    timeout : int, default 30
        Connection timeout in seconds.
    """

    host: str = field(default_factory=lambda: os.getenv("SMTP_HOST", "smtp.gmail.com"))
    port: int = field(default_factory=lambda: int(os.getenv("SMTP_PORT", "587")))
    username: str = field(default_factory=lambda: os.getenv("SMTP_USER", os.getenv("SMTP_USERNAME", "")))
    password: str = field(default_factory=lambda: os.getenv("SMTP_PASSWORD", ""))
    sender: str = field(default_factory=lambda: os.getenv("SMTP_SENDER", ""))
    use_tls: bool = field(
        default_factory=lambda: os.getenv("SMTP_USE_TLS", "true").lower() in ("true", "1", "yes")
    )
    use_ssl: bool = field(
        default_factory=lambda: os.getenv("SMTP_USE_SSL", "false").lower() in ("true", "1", "yes")
    )
    timeout: int = 30

    @property
    def effective_sender(self) -> str:
        """Return the effective sender address.

        Returns
        -------
        str
            The configured sender or fallback to username.
        """
        return self.sender if self.sender else self.username


@dataclass
class User:
    """User recipient configuration.

    Parameters
    ----------
    email : str
        Email address of the user.
    name : str, default ""
        Optional display name of the user.
    """

    email: str
    name: str = ""

    @property
    def formatted_address(self) -> str:
        """Return the formatted email address with name if available.

        Returns
        -------
        str
            Formatted address, e.g. "Alice <alice@example.com>" or "alice@example.com".
        """
        return f"{self.name} <{self.email}>" if self.name else self.email


@dataclass
class AppSettings:
    """Top-level configuration settings for gram2email.

    Parameters
    ----------
    accounts : list of str
        List of public Instagram usernames to monitor.
    users : list of User, default empty list
        List of users receiving the emails.
    recipients : list of str, default empty list
        Optional list of email addresses to receive post notifications.
    smtp : SMTPSettings
        SMTP server connection details.
    max_posts_per_account : int, default 5
        Maximum number of recent posts to inspect per account per run.
    state_file : str, default "seen_posts.json"
        Path to the JSON file tracking already seen post shortcodes.
    session_file : str or None, default None
        Optional path to an Instaloader session file for authenticated requests.
    download_media : bool, default True
        Whether to download and embed media directly into the email body.
    dry_run : bool, default False
        If True, runs the scraper without sending emails or updating state.
    verbose : bool, default False
        Enable verbose logging output.
    request_timeout : int, default 30
        Network timeout in seconds for scraper requests.
    """

    accounts: list[str] = field(default_factory=list)
    users: list[User] = field(default_factory=list)
    recipients: list[str] = field(default_factory=list)
    smtp: SMTPSettings = field(default_factory=SMTPSettings)
    max_posts_per_account: int = 5
    state_file: str = "seen_posts.json"
    session_id: str = field(default_factory=lambda: os.getenv("INSTAGRAM_SESSION_ID", ""))
    session_file: str | None = field(default_factory=lambda: os.getenv("INSTAGRAM_SESSION_FILE", None))
    instagram_user: str = field(default_factory=lambda: os.getenv("INSTAGRAM_USER", ""))
    download_media: bool = True
    dry_run: bool = False
    verbose: bool = False
    request_timeout: int = 30

    @property
    def effective_recipients(self) -> list[str]:
        """Return the aggregated list of recipient email addresses.

        Returns
        -------
        list of str
            Combined list of recipient addresses from users and recipients.
        """
        user_addrs = [u.formatted_address for u in self.users]
        seen = set(user_addrs)
        extras = [r for r in self.recipients if r not in seen]
        return user_addrs + extras

    @property
    def state_path(self) -> Path:
        """Return the resolved Path object for the state file.

        Returns
        -------
        Path
            Path to the state persistence file.
        """
        return Path(self.state_file).expanduser().resolve()
