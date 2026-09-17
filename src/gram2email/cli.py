"""Command-line interface for gram2email using jsonargparse.

Provides functions to construct the argument parser, load and validate
configuration files and command-line options, and execute the scraping pipeline.
"""

import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from jsonargparse import ActionConfigFile, ArgumentParser

from gram2email.config import AppSettings, InstagramAuthSettings, SMTPSettings, User
from gram2email.pipeline import run_pipeline


def build_parser() -> ArgumentParser:
    """Construct and configure the command-line argument parser.

    Returns
    -------
    ArgumentParser
        Configured argument parser with support for configuration files,
        dataclasses, and CLI flag overrides.
    """
    parser = ArgumentParser(
        description="Gram2Email: Fetch Instagram posts and email their contents.",
        exit_on_error=True,
    )
    parser.add_argument(
        "-c",
        "--config",
        action=ActionConfigFile,
        help="Path to YAML or JSON configuration file.",
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Perform interactive Instagram login to generate and save a session file.",
    )
    parser.add_class_arguments(AppSettings, as_group=False)
    return parser


def parse_args_to_settings(args: Sequence[str] | None = None) -> AppSettings:
    """Parse CLI arguments and return an AppSettings instance.

    Parameters
    ----------
    args : Sequence of str or None, default None
        Command-line arguments to parse. If None, sys.argv[1:] is used.

    Returns
    -------
    AppSettings
        Instantiated application settings dataclass.
    """
    parser = build_parser()
    cfg = parser.parse_args(args=args)
    inst = parser.instantiate(cfg)

    if isinstance(inst.smtp, SMTPSettings):
        smtp_obj = inst.smtp
    else:
        smtp_dict = inst.smtp.as_dict() if hasattr(inst.smtp, "as_dict") else dict(inst.smtp)
        smtp_obj = SMTPSettings(**smtp_dict)

    if isinstance(inst.instagram, InstagramAuthSettings):
        ig_obj = inst.instagram
    else:
        ig_dict = inst.instagram.as_dict() if hasattr(inst.instagram, "as_dict") else dict(inst.instagram)
        ig_obj = InstagramAuthSettings(**ig_dict)

    user_objs: list[User] = []
    for u in inst.users:
        if isinstance(u, User):
            user_objs.append(u)
        elif isinstance(u, dict):
            user_objs.append(User(**u))
        elif hasattr(u, "as_dict"):
            user_objs.append(User(**u.as_dict()))
        elif isinstance(u, str):
            user_objs.append(User(email=u))

    state_file = inst.state_file
    session_file = ig_obj.session_file or inst.session_file
    if getattr(cfg, "config", None):
        config_entry = cfg.config[0] if isinstance(cfg.config, list) else cfg.config
        config_dir = Path(str(config_entry)).resolve().parent
        state_path_obj = Path(state_file)
        if not state_path_obj.is_absolute():
            state_file = str(config_dir / state_path_obj)
        if session_file:
            sess_path_obj = Path(session_file)
            if not sess_path_obj.is_absolute():
                session_file = str(config_dir / sess_path_obj)
                ig_obj.session_file = session_file

    return AppSettings(
        accounts=inst.accounts,
        users=user_objs,
        recipients=inst.recipients,
        smtp=smtp_obj,
        instagram=ig_obj,
        max_posts_per_account=inst.max_posts_per_account,
        state_file=state_file,
        session_id=inst.session_id,
        session_file=session_file,
        instagram_user=inst.instagram_user,
        download_media=inst.download_media,
        dry_run=inst.dry_run,
        verbose=inst.verbose,
        request_timeout=inst.request_timeout,
    )


def handle_interactive_login(settings: AppSettings) -> int:
    """Perform interactive login and save the session file.

    Parameters
    ----------
    settings : AppSettings
        Application settings containing Instagram credentials.

    Returns
    -------
    int
        Exit code (0 for success, 1 for failure).
    """
    import getpass

    from gram2email.instagram import create_loader

    auth = settings.effective_instagram_auth
    username = auth.username
    if not username:
        username = input("Enter Instagram username: ").strip()

    password = auth.password
    if not password:
        password = getpass.getpass(f"Enter Instagram password for @{username}: ").strip()

    target_session = auth.session_file or str(Path(settings.state_path).parent / f"session-{username}")

    print(f"Authenticating with Instagram as @{username}...")
    try:
        create_loader(
            username=username,
            password=password,
            session_file=target_session,
            interactive=True,
        )
        print(f"Login successful! Session saved to: {target_session}")
        return 0
    except Exception as exc:
        print(f"Login failed: {exc}", file=sys.stderr)
        return 1


def setup_logging(verbose: bool = False) -> None:
    """Configure console logging level and format.

    Parameters
    ----------
    verbose : bool, default False
        Whether to enable DEBUG-level logging.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] [%(levelname)-7s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main(args: Sequence[str] | None = None) -> int:
    """Entrypoint function for the gram2email CLI application.

    Parameters
    ----------
    args : Sequence of str or None, default None
        Command-line arguments to evaluate. If None, sys.argv[1:] is evaluated.

    Returns
    -------
    int
        Exit code (0 for success, non-zero for error).
    """
    parser = build_parser()
    try:
        cfg = parser.parse_args(args=args)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 0

    settings = parse_args_to_settings(args)
    setup_logging(verbose=settings.verbose)
    logger = logging.getLogger("gram2email")

    if getattr(cfg, "login", False):
        return handle_interactive_login(settings)

    if not settings.accounts:
        logger.error("No target accounts specified. Use --accounts or --config.")
        return 1

    try:
        total_sent = run_pipeline(settings)
        logger.info("Pipeline completed. Total posts emailed: %d", total_sent)
        return 0
    except Exception as exc:
        logger.exception("Pipeline failed with unexpected error: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
