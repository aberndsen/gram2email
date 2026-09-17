"""Instagram scraping components and data models.

Provides functional interfaces for querying public Instagram profiles,
extracting post details and media, and downloading images for email inclusion.
"""

import logging
import mimetypes
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import instaloader
import requests

logger = logging.getLogger(__name__)


@dataclass
class MediaItem:
    """Represents a single media asset associated with an Instagram post.

    Parameters
    ----------
    url : str
        URL of the media asset.
    media_type : str
        Type of the media ("image" or "video").
    content : bytes or None, default None
        Raw byte payload of the downloaded media file.
    filename : str or None, default None
        Filename associated with the media asset.
    content_type : str, default "image/jpeg"
        MIME type of the media asset.
    cid : str, default ""
        Unique Content-ID string used for inline email embedding.
    """

    url: str
    media_type: str = "image"
    content: bytes | None = None
    filename: str | None = None
    content_type: str = "image/jpeg"
    cid: str = ""


@dataclass
class InstagramPost:
    """Normalized data representation of an Instagram post.

    Parameters
    ----------
    shortcode : str
        Unique shortcode identifying the post.
    url : str
        Full web URL to the post.
    owner_username : str
        Instagram username of the author.
    caption : str
        Text caption accompanying the post.
    date_utc : datetime
        UTC timestamp of post publication.
    media_items : list of MediaItem, default empty list
        Collection of images and video thumbnails for the post.
    is_video : bool, default False
        Whether the post is or contains a primary video.
    likes : int, default 0
        Number of likes recorded on the post.
    comments : int, default 0
        Number of comments recorded on the post.
    """

    shortcode: str
    url: str
    owner_username: str
    caption: str
    date_utc: datetime
    media_items: list[MediaItem] = field(default_factory=list)
    is_video: bool = False
    likes: int = 0
    comments: int = 0


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
DEFAULT_IG_APP_ID = "936619743392459"
DEFAULT_ASBD_ID = "129477"
KNOWN_USER_IDS: dict[str, str] = {
    "ruralraiders": "2176213596",
}


def parse_cookie_string(cookie_input: str) -> dict[str, str]:
    """Parse cookie string or raw sessionid into a dictionary of cookie key-values.

    Parameters
    ----------
    cookie_input : str
        Cookie string (e.g., 'sessionid=xxx; ds_user_id=yyy') or standalone sessionid.

    Returns
    -------
    dict of str to str
        Parsed cookies dictionary.
    """
    clean = cookie_input.strip()
    cookies: dict[str, str] = {}
    if "=" in clean:
        for part in clean.split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                cookies[k.strip()] = v.strip().strip('"').strip("'")
    elif clean:
        cookies["sessionid"] = clean
    return cookies


def create_loader(
    user_agent: str | None = None,
    max_connection_attempts: int = 1,
    request_timeout: float = 30.0,
    session_file: str | None = None,
    session_id: str | None = None,
    username: str | None = None,
    password: str | None = None,
    api_key: str | None = None,
    instagram_user: str | None = None,
    interactive: bool = False,
) -> instaloader.Instaloader:
    """Create and configure an Instaloader instance.

    Parameters
    ----------
    user_agent : str or None, default None
        Custom HTTP User-Agent string. If None, a modern browser user-agent is used.
    max_connection_attempts : int, default 1
        Maximum retry attempts for requests.
    request_timeout : float, default 30.0
        Request timeout in seconds.
    session_file : str or None, default None
        Optional path to an existing Instaloader session file or cookie JSON file.
    session_id : str or None, default None
        Optional Instagram session ID cookie or full cookie header string.
    username : str or None, default None
        Instagram account username for direct login or session identification.
    password : str or None, default None
        Instagram account password for login.
    api_key : str or None, default None
        Optional third-party or developer API key.
    instagram_user : str or None, default None
        Optional Instagram username alias (shortcut for username).
    interactive : bool, default False
        Whether to prompt interactively for 2FA codes if required.

    Returns
    -------
    instaloader.Instaloader
        Configured Instaloader instance.
    """
    from pathlib import Path

    effective_ua = user_agent or DEFAULT_USER_AGENT
    effective_user = username or instagram_user

    loader = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        max_connection_attempts=max_connection_attempts,
        request_timeout=request_timeout,
        fatal_status_codes=None,
        sleep=False,
        user_agent=effective_ua,
    )

    # Ensure Instagram Web App ID and ASBD ID are present for API queries
    loader.context._session.headers["x-ig-app-id"] = DEFAULT_IG_APP_ID
    loader.context._session.headers["x-asbd-id"] = DEFAULT_ASBD_ID

    if api_key and api_key.strip():
        loader.context._session.headers["Authorization"] = f"Bearer {api_key.strip()}"
        loader.context._session.headers["X-API-Key"] = api_key.strip()

    # 1. Apply session_id if provided directly (highest priority)
    if session_id and session_id.strip():
        cookies = parse_cookie_string(session_id)
        if "ds_user_id" not in cookies and "sessionid" in cookies:
            raw_sid = cookies["sessionid"]
            prefix = raw_sid.split("%3A")[0].split(":")[0]
            if prefix.isdigit():
                cookies["ds_user_id"] = prefix
        for k, v in cookies.items():
            loader.context._session.cookies.set(k, v)
        if "csrftoken" in cookies:
            loader.context._session.headers["X-CSRFToken"] = cookies["csrftoken"]
        try:
            loader.context._session.get("https://www.instagram.com/", timeout=10)
            csrf = loader.context._session.cookies.get_dict().get("csrftoken", "")
            if csrf:
                loader.context._session.headers["X-CSRFToken"] = csrf
        except Exception as exc:
            logger.debug("Initial session ping to instagram.com failed: %s", exc)

        loader.context.username = effective_user or (loader.test_login() or "authenticated_user")
        logger.debug(
            "Configured Instagram session from session_id cookie (user: %s)", loader.context.username
        )

        # Cache session_id to session_file if requested
        if session_file:
            try:
                target_path = Path(session_file).expanduser().resolve()
                target_path.parent.mkdir(parents=True, exist_ok=True)
                loader.save_session_to_file(str(target_path))
                logger.debug("Cached session_id to session file %s", target_path)
            except Exception as save_exc:
                logger.debug("Could not cache session to %s: %s", session_file, save_exc)

    # 2. Apply session_file if provided and session_id was not supplied
    elif session_file:
        session_path = Path(session_file).expanduser().resolve()
        if session_path.is_file():
            try:
                content = session_path.read_text(encoding="utf-8").strip()
                if content.startswith("{"):
                    import json

                    cookie_data = json.loads(content)
                    if isinstance(cookie_data, dict):
                        loader.context._session.cookies.update(cookie_data)
                        if "csrftoken" in cookie_data:
                            loader.context._session.headers["X-CSRFToken"] = cookie_data["csrftoken"]
                        loader.context.username = effective_user or "authenticated_user"
                        logger.debug("Loaded JSON session cookies from %s", session_path)
                elif "=" in content:
                    cookie_data = parse_cookie_string(content)
                    loader.context._session.cookies.update(cookie_data)
                    loader.context.username = effective_user or "authenticated_user"
                    logger.debug("Loaded text session cookies from %s", session_path)
                else:
                    uname = effective_user or (
                        session_path.name.removeprefix("session-")
                        if session_path.name.startswith("session-")
                        else session_path.stem
                    )
                    loader.load_session_from_file(uname, filename=str(session_path))
                    logger.debug("Loaded Instaloader pickle session from %s", session_path)
            except Exception:
                try:
                    uname = effective_user or (
                        session_path.name.removeprefix("session-")
                        if session_path.name.startswith("session-")
                        else session_path.stem
                    )
                    loader.load_session_from_file(uname, filename=str(session_path))
                    logger.debug("Loaded Instaloader pickle session from %s", session_path)
                except Exception as exc:
                    logger.warning("Failed to load session file %s: %s", session_path, exc)
            # Ensure critical web headers are present after loading session
            loader.context._session.headers["x-ig-app-id"] = DEFAULT_IG_APP_ID
            loader.context._session.headers["x-asbd-id"] = DEFAULT_ASBD_ID
            csrf = loader.context._session.cookies.get_dict().get("csrftoken", "")
            if csrf:
                loader.context._session.headers["X-CSRFToken"] = csrf
        else:
            logger.warning("Session file does not exist: %s", session_path)

    # 3. Direct login with username & password if not already authenticated
    if not loader.context.is_logged_in and effective_user and password:
        target_path = (
            Path(session_file).expanduser().resolve()
            if session_file
            else Path(instaloader.instaloader.get_default_session_filename(effective_user))
        )
        if target_path.is_file():
            try:
                loader.load_session_from_file(effective_user, filename=str(target_path))
                logger.debug("Loaded existing cached session from %s", target_path)
            except Exception as exc:
                logger.warning("Cached session %s failed to load (%s); logging in...", target_path, exc)

        if not loader.context.is_logged_in:
            try:
                logger.info("Logging into Instagram as @%s", effective_user)
                loader.login(effective_user, password)
                target_path.parent.mkdir(parents=True, exist_ok=True)
                loader.save_session_to_file(str(target_path))
                logger.info("Successfully logged in and saved session to %s", target_path)
            except instaloader.TwoFactorAuthRequiredException as exc:
                if interactive:
                    code = input(f"Enter Instagram 2FA security code for @{effective_user}: ").strip()
                    loader.two_factor_login(code)
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    loader.save_session_to_file(str(target_path))
                    logger.info("Successfully completed 2FA login and saved session to %s", target_path)
                else:
                    raise RuntimeError(
                        f"Instagram 2FA is required for account @{effective_user}. "
                        "Run `gram2email --login` interactively once to authenticate."
                    ) from exc
            except instaloader.BadCredentialsException as exc:
                raise ValueError(f"Invalid Instagram credentials for @{effective_user}.") from exc
            except Exception as exc:
                logger.error("Instagram login failed for @{effective_user}: %s", exc)
                raise

    return loader


def download_media_content(
    url: str,
    session: requests.Session | None = None,
    timeout: int = 20,
) -> tuple[bytes | None, str]:
    """Download binary content of a media URL.

    Parameters
    ----------
    url : str
        Web URL pointing to an image or media asset.
    session : requests.Session or None, default None
        HTTP session to use for downloading. If None, requests.get is used.
    timeout : int, default 20
        Request timeout in seconds.

    Returns
    -------
    tuple of (bytes or None, str)
        Downloaded bytes (or None on failure) and the detected MIME content type.
    """
    try:
        req = session.get if session else requests.get
        response = req(url, timeout=timeout)
        response.raise_for_status()
        content = response.content

        content_type = response.headers.get("Content-Type", "").split(";")[0].strip()
        if not content_type or content_type == "application/octet-stream":
            guess, _ = mimetypes.guess_type(url)
            content_type = guess or "image/jpeg"

        return content, content_type
    except Exception as exc:
        logger.warning("Failed to download media from %s: %s", url, exc)
        return None, "image/jpeg"


def extract_media_items(
    post: Any,
    session: requests.Session | None = None,
    download: bool = True,
) -> list[MediaItem]:
    """Extract media assets from an Instaloader Post object.

    Handles single images, carousel/sidecar posts, and video thumbnails.

    Parameters
    ----------
    post : instaloader.Post
        Instaloader post object.
    session : requests.Session or None, default None
        Session used to download binary assets.
    download : bool, default True
        Whether to download the binary media content into memory.

    Returns
    -------
    list of MediaItem
        Extracted media items with URLs, metadata, and optional bytes.
    """
    items: list[MediaItem] = []
    shortcode = getattr(post, "shortcode", "post")

    # Check for carousel / sidecar nodes
    typename = getattr(post, "typename", "")
    if typename == "GraphSidecar":
        try:
            for idx, node in enumerate(post.get_sidecar_nodes()):
                display_url = getattr(node, "display_url", None)
                if not display_url:
                    continue
                is_node_video = getattr(node, "is_video", False)
                cid = f"{shortcode}_img_{idx}"
                filename = f"{shortcode}_{idx}.jpg"
                content = None
                content_type = "image/jpeg"

                if download:
                    content, content_type = download_media_content(display_url, session=session)

                items.append(
                    MediaItem(
                        url=display_url,
                        media_type="video" if is_node_video else "image",
                        content=content,
                        filename=filename,
                        content_type=content_type,
                        cid=cid,
                    )
                )
        except Exception as exc:
            logger.warning(
                "Failed to parse sidecar nodes for post %s: %s",
                shortcode,
                exc,
            )

    # Fallback to single primary image/thumbnail if sidecar extraction didn't yield items
    if not items:
        primary_url = getattr(post, "url", None)
        if primary_url:
            cid = f"{shortcode}_img_0"
            filename = f"{shortcode}_0.jpg"
            content = None
            content_type = "image/jpeg"

            if download:
                content, content_type = download_media_content(primary_url, session=session)

            items.append(
                MediaItem(
                    url=primary_url,
                    media_type="video" if getattr(post, "is_video", False) else "image",
                    content=content,
                    filename=filename,
                    content_type=content_type,
                    cid=cid,
                )
            )

    return items


def resolve_user_id(account: str, session: requests.Session | None = None) -> str | None:
    """Resolve an Instagram account username to its numeric profile ID.

    Parameters
    ----------
    account : str
        Instagram username handle.
    session : requests.Session or None, default None
        HTTP session to use for requests.

    Returns
    -------
    str or None
        Numeric profile ID if resolved, otherwise None.
    """
    clean_account = account.lstrip("@").strip().lower()
    if clean_account in KNOWN_USER_IDS:
        return KNOWN_USER_IDS[clean_account]

    s = session or requests.Session()

    # 1. HTML profile scrape
    try:
        url = f"https://www.instagram.com/{clean_account}/"
        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
        }
        resp = s.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            for pattern in (
                r'"profile_id":"(\d+)"',
                r'"props":.*?"id":"(\d+)"',
                r'"target_id":"(\d+)"',
                r'"user_id":"(\d+)"',
            ):
                match = re.search(pattern, resp.text)
                if match:
                    uid = match.group(1)
                    KNOWN_USER_IDS[clean_account] = uid
                    return uid
    except Exception as exc:
        logger.debug("HTML profile ID resolution failed for @%s: %s", clean_account, exc)

    # 2. Modern search endpoint
    try:
        search_url = "https://www.instagram.com/api/v1/web/search/topsearch/"
        headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "x-ig-app-id": DEFAULT_IG_APP_ID,
            "x-asbd-id": DEFAULT_ASBD_ID,
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"https://www.instagram.com/{clean_account}/",
        }
        csrf = s.cookies.get_dict().get("csrftoken", "")
        if csrf:
            headers["X-CSRFToken"] = csrf
        resp = s.get(
            search_url,
            headers=headers,
            params={"context": "blended", "query": clean_account},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            for user_entry in data.get("users", []):
                user = user_entry.get("user", {})
                if user.get("username", "").lower() == clean_account:
                    uid = str(user.get("pk") or user.get("id"))
                    if uid:
                        KNOWN_USER_IDS[clean_account] = uid
                        return uid
    except Exception as exc:
        logger.debug("Search API ID resolution failed for @%s: %s", clean_account, exc)

    return None


def fetch_posts_via_user_feed(
    user_id: str,
    username: str,
    context: instaloader.InstaloaderContext,
    max_posts: int = 5,
    download_media: bool = True,
) -> list[InstagramPost]:
    """Fetch recent posts for a user via Instagram REST feed endpoint.

    Parameters
    ----------
    user_id : str
        Numeric profile user ID.
    username : str
        Username handle for the profile.
    context : instaloader.InstaloaderContext
        Active Instaloader context.
    max_posts : int, default 5
        Maximum posts to retrieve.
    download_media : bool, default True
        Whether to download media bytes.

    Returns
    -------
    list of InstagramPost
        Parsed post objects.
    """
    session = getattr(context, "_session", None)
    if not session:
        return []

    url = f"https://www.instagram.com/api/v1/feed/user/{user_id}/"
    headers = {
        "User-Agent": context.user_agent or DEFAULT_USER_AGENT,
        "x-ig-app-id": DEFAULT_IG_APP_ID,
        "x-asbd-id": DEFAULT_ASBD_ID,
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"https://www.instagram.com/{username}/",
    }
    csrf = session.cookies.get_dict().get("csrftoken", "")
    if csrf:
        headers["X-CSRFToken"] = csrf

    resp = session.get(
        url,
        headers=headers,
        params={"count": max_posts},
        timeout=context.request_timeout,
    )
    if resp.status_code != 200:
        logger.debug(
            "Feed endpoint returned HTTP %d for @%s: %s",
            resp.status_code,
            username,
            resp.text[:200],
        )
        return []

    data = resp.json()
    items = data.get("items", [])
    posts: list[InstagramPost] = []
    for item in items[:max_posts]:
        try:
            post = instaloader.Post.from_iphone_struct(context, item)
            if hasattr(post, "_node") and isinstance(post._node, dict):
                post._node["edge_media_to_parent_comment"] = {"count": item.get("comment_count", 0)}
            posts.append(_convert_post(post, username, session=session, download_media=download_media))
        except Exception as exc:
            logger.debug("Failed to convert feed item for @%s: %s", username, exc)

    return posts


def _convert_post(
    post: Any,
    owner_username: str,
    session: requests.Session | None = None,
    download_media: bool = True,
) -> InstagramPost:
    """Convert an Instaloader Post object into a normalized InstagramPost dataclass.

    Parameters
    ----------
    post : Any
        Instaloader Post object.
    owner_username : str
        Account username for post ownership.
    session : requests.Session or None, default None
        Session used to download media files.
    download_media : bool, default True
        Whether to fetch image payload bytes.

    Returns
    -------
    InstagramPost
        Normalized post representation.
    """
    shortcode = getattr(post, "shortcode", "")
    caption = getattr(post, "caption", "") or ""
    date_utc = getattr(post, "date_utc", datetime.now())
    post_url = f"https://www.instagram.com/p/{shortcode}/"
    is_video = getattr(post, "is_video", False)
    media_items = extract_media_items(post, session=session, download=download_media)

    likes = 0
    try:
        likes = post.likes
    except Exception:
        likes = getattr(post, "_node", {}).get("like_count", 0)

    comments = 0
    try:
        comments = post.comments
    except Exception:
        node = getattr(post, "_node", {})
        comments_val = node.get("comments") or node.get("comment_count", 0)
        comments = comments_val.get("count", 0) if isinstance(comments_val, dict) else (comments_val or 0)

    return InstagramPost(
        shortcode=shortcode,
        url=post_url,
        owner_username=owner_username,
        caption=caption,
        date_utc=date_utc,
        media_items=media_items,
        is_video=is_video,
        likes=likes,
        comments=comments,
    )


def fetch_recent_posts(
    account: str,
    max_posts: int = 5,
    loader: instaloader.Instaloader | None = None,
    download_media: bool = True,
) -> list[InstagramPost]:
    """Fetch the most recent posts from a public Instagram account.

    Employs a tiered retrieval strategy:
    1. Standard Instaloader Profile.from_username query.
    2. Direct GraphQL timeline query via lightweight Profile node (bypassing
       web_profile_info 429 throttling when logged in).
    3. Authenticated REST feed endpoint (/api/v1/feed/user/{user_id}/).

    Parameters
    ----------
    account : str
        Public Instagram handle / username without leading '@'.
    max_posts : int, default 5
        Maximum number of recent posts to retrieve.
    loader : instaloader.Instaloader or None, default None
        Instaloader instance to use. If None, a new anonymous loader is created.
    download_media : bool, default True
        Whether to download image assets into memory.

    Returns
    -------
    list of InstagramPost
        Normalized post objects ordered from newest to oldest.

    Raises
    ------
    ValueError
        If the profile does not exist, is private, or access is blocked.
    """
    clean_account = account.lstrip("@").strip()
    inst = loader or create_loader()
    session = getattr(inst.context, "_session", None)

    logger.debug("Querying posts for @%s", clean_account)

    # Attempt 1: Standard Instaloader Profile.from_username
    try:
        profile = instaloader.Profile.from_username(inst.context, clean_account)
        if profile.is_private:
            raise ValueError(f"Instagram account @{clean_account} is private.")
        posts: list[InstagramPost] = []
        for idx, post in enumerate(profile.get_posts()):
            if idx >= max_posts:
                break
            posts.append(_convert_post(post, clean_account, session=session, download_media=download_media))
        if posts:
            return posts
    except ValueError:
        raise
    except Exception as exc:
        logger.debug(
            "Standard profile query for @%s failed (%s); trying fallback strategies...",
            clean_account,
            exc,
        )

    # Attempt 2: If logged in, query GraphQL timeline directly via lightweight Profile node
    # This bypasses web_profile_info completely and avoids HTTP 429
    if inst.context.is_logged_in:
        try:
            logger.debug("Attempting direct GraphQL timeline fetch for @%s", clean_account)
            user_id = resolve_user_id(clean_account, session=session) or "0"
            profile_direct = instaloader.Profile(
                inst.context,
                {
                    "username": clean_account,
                    "id": user_id,
                    "is_private": False,
                },
            )
            profile_direct._has_full_metadata = True
            posts = []
            for idx, post in enumerate(profile_direct.get_posts()):
                if idx >= max_posts:
                    break
                posts.append(
                    _convert_post(post, clean_account, session=session, download_media=download_media)
                )
            if posts:
                logger.debug(
                    "Retrieved %d posts via direct GraphQL timeline for @%s",
                    len(posts),
                    clean_account,
                )
                return posts
        except Exception as gql_exc:
            logger.debug("Direct GraphQL timeline fetch failed for @%s: %s", clean_account, gql_exc)

    # Attempt 3: User feed REST API fallback (/api/v1/feed/user/{user_id}/)
    try:
        user_id = resolve_user_id(clean_account, session=session)
        if user_id:
            logger.debug("Attempting user feed endpoint for @%s (id: %s)...", clean_account, user_id)
            feed_posts = fetch_posts_via_user_feed(
                user_id=user_id,
                username=clean_account,
                context=inst.context,
                max_posts=max_posts,
                download_media=download_media,
            )
            if feed_posts:
                logger.debug(
                    "Retrieved %d posts via user feed endpoint for @%s",
                    len(feed_posts),
                    clean_account,
                )
                return feed_posts
    except Exception as feed_exc:
        logger.debug("User feed fallback failed for @%s: %s", clean_account, feed_exc)

    # All attempts failed: provide actionable diagnostics
    if not inst.context.is_logged_in:
        raise ValueError(
            f"Instagram blocked unauthenticated access to @{clean_account} (HTTP 429/401). "
            "Meta requires an authenticated session to view profile posts. "
            "Configure an Instagram session ('session_file' or 'session_id') in settings."
        )
    raise ValueError(
        f"Failed to retrieve posts for @{clean_account} using authenticated session. "
        "The burner account may need to be verified in a browser (e.g. log into https://instagram.com "
        "with @kneedme2026 once to dismiss onboarding/challenge), or the profile may be temporarily "
        "restricted by Meta."
    )
