"""Email message generation and SMTP delivery components.

Provides functional interfaces for creating multipart HTML emails with inline
embedded media and transmitting them through standard SMTP servers.
"""

import html
import logging
import smtplib
import ssl
from email.message import EmailMessage

from gram2email.config import SMTPSettings
from gram2email.instagram import InstagramPost

logger = logging.getLogger(__name__)


def format_plain_text(post: InstagramPost) -> str:
    """Format an Instagram post as a plain-text email body.

    Parameters
    ----------
    post : InstagramPost
        The post to format.

    Returns
    -------
    str
        Plain-text representation of the post.
    """
    timestamp_str = post.date_utc.strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        f"New post from @{post.owner_username}",
        f"Published: {timestamp_str}",
        f"Link: {post.url}",
        "",
        "--- Caption ---",
        post.caption if post.caption else "[No caption]",
        "",
        "----------------",
        f"Stats: {post.likes} likes | {post.comments} comments",
    ]
    return "\n".join(lines)


def format_html(post: InstagramPost) -> str:
    """Format an Instagram post as a responsive HTML email body.

    Uses embedded CID references for images so that media displays
    directly in the email body without external CDN image blockers.

    Parameters
    ----------
    post : InstagramPost
        The post to format.

    Returns
    -------
    str
        HTML document string for the email.
    """
    timestamp_str = post.date_utc.strftime("%B %d, %Y at %H:%M UTC")
    escaped_author = html.escape(post.owner_username)
    escaped_url = html.escape(post.url)

    # Convert caption newlines to <br> and escape HTML
    if post.caption:
        formatted_caption = html.escape(post.caption).replace("\n", "<br>\n")
    else:
        formatted_caption = "<em>No caption</em>"

    # Build image gallery cards
    media_html_parts: list[str] = []
    for item in post.media_items:
        src = f"cid:{item.cid}" if item.content and item.cid else html.escape(item.url)
        media_label = " (Video cover)" if item.media_type == "video" else ""
        img_style = (
            "max-width: 100%; height: auto; border-radius: 8px; "
            "box-shadow: 0 2px 8px rgba(0,0,0,0.1); display: inline-block;"
        )
        media_html_parts.append(
            f"""
            <div style="margin: 16px 0; text-align: center;">
                <img src="{src}" alt="Post Media{media_label}" style="{img_style}">
            </div>
            """
        )

    gallery_html = "\n".join(media_html_parts)
    btn_style = (
        "display: inline-block; padding: 10px 20px; background-color: #0095f6; "
        "color: #ffffff; text-decoration: none; font-size: 14px; "
        "font-weight: 600; border-radius: 6px;"
    )
    header_grad = "background: linear-gradient(135deg, #405DE6, #5851DB, #833AB4, #C13584, #E1306C, #FD1D1D);"
    body_style = (
        "margin: 0; padding: 24px; "
        "font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; "
        "background-color: #f7f7f9; color: #1a1a1a;"
    )
    card_style = (
        "max-width: 600px; width: 100%; background: #ffffff; border-radius: 12px; "
        "border: 1px solid #e1e4e8; overflow: hidden; "
        "box-shadow: 0 4px 12px rgba(0,0,0,0.05);"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Post by @{escaped_author}</title>
</head>
<body style="{body_style}">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
        <tr>
            <td align="center">
                <table role="presentation" style="{card_style}"
                       cellspacing="0" cellpadding="0" border="0">
                    <!-- Header -->
                    <tr>
                        <td style="padding: 20px 24px; {header_grad} color: #ffffff;">
                            <div style="font-size: 12px; text-transform: uppercase; "
                                 "letter-spacing: 1px; opacity: 0.9; margin-bottom: 4px;">
                                Instagram
                            </div>
                            <h1 style="margin: 0; font-size: 22px; font-weight: 700;">
                                @{escaped_author}
                            </h1>
                            <div style="font-size: 13px; opacity: 0.85; margin-top: 4px;">
                                {timestamp_str}
                            </div>
                        </td>
                    </tr>

                    <!-- Media Gallery -->
                    <tr>
                        <td style="padding: 16px 24px 0 24px;">
                            {gallery_html}
                        </td>
                    </tr>

                    <!-- Caption -->
                    <tr>
                        <td style="padding: 16px 24px; font-size: 15px; "
                            "line-height: 1.6; color: #2c3e50;">
                            {formatted_caption}
                        </td>
                    </tr>

                    <!-- Footer & Links -->
                    <tr>
                        <td style="padding: 20px 24px; background-color: #fafbfc; "
                            "border-top: 1px solid #eef0f2; text-align: center;">
                            <a href="{escaped_url}" style="{btn_style}"
                               target="_blank" rel="noopener noreferrer">
                                View on Instagram &rarr;
                            </a>
                            <div style="margin-top: 12px; font-size: 12px; color: #8c9ba5;">
                                {post.likes:,} likes &bull; {post.comments:,} comments &bull;
                                ID: <code>{post.shortcode}</code>
                            </div>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""


def build_post_email(
    post: InstagramPost,
    sender: str,
    recipients: list[str],
) -> EmailMessage:
    """Build a complete multipart EmailMessage for an Instagram post.

    Constructs plain text and HTML alternatives, and attaches image
    data inline with Content-ID matching the HTML `cid:` references.

    Parameters
    ----------
    post : InstagramPost
        The Instagram post data to embed.
    sender : str
        From email address.
    recipients : list of str
        List of destination email addresses.

    Returns
    -------
    EmailMessage
        Constructed email message ready for SMTP transmission.
    """
    msg = EmailMessage()

    # Subject creation (clean snippet from caption or fallback)
    caption_snippet = ""
    if post.caption:
        first_line = post.caption.strip().split("\n")[0].strip()
        caption_snippet = f": {first_line[:50]}..." if len(first_line) > 50 else f": {first_line}"

    msg["Subject"] = f"[@{post.owner_username}]{caption_snippet}"
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)

    plain_body = format_plain_text(post)
    html_body = format_html(post)

    msg.set_content(plain_body)
    msg.add_alternative(html_body, subtype="html")

    # Add inline image parts to the HTML alternative part
    html_part = msg.get_body(preferencelist=("html",))
    if html_part is not None:
        for item in post.media_items:
            if item.content and item.cid:
                subtype = "jpeg"
                if item.content_type:
                    parts = item.content_type.split("/")
                    if len(parts) == 2:
                        subtype = parts[1].lower()

                html_part.add_related(
                    item.content,
                    maintype="image",
                    subtype=subtype,
                    cid=f"<{item.cid}>",
                    filename=item.filename or f"{item.cid}.jpg",
                )

    return msg


def send_email(
    message: EmailMessage,
    smtp: SMTPSettings,
) -> None:
    """Send an EmailMessage using the configured SMTP server settings.

    Supports STARTTLS, direct SSL, or unencrypted SMTP connections.

    Parameters
    ----------
    message : EmailMessage
        The email message to transmit.
    smtp : SMTPSettings
        The SMTP connection parameters.

    Raises
    ------
    smtplib.SMTPException
        If the message fails to send through the SMTP server.
    """
    logger.debug(
        "Connecting to SMTP server %s:%d (ssl=%s, tls=%s)",
        smtp.host,
        smtp.port,
        smtp.use_ssl,
        smtp.use_tls,
    )

    if smtp.use_ssl:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp.host, smtp.port, context=context, timeout=smtp.timeout) as server:
            if smtp.username and smtp.password:
                server.login(smtp.username, smtp.password)
            server.send_message(message)
    else:
        with smtplib.SMTP(smtp.host, smtp.port, timeout=smtp.timeout) as server:
            if smtp.use_tls:
                context = ssl.create_default_context()
                server.starttls(context=context)
            if smtp.username and smtp.password:
                server.login(smtp.username, smtp.password)
            server.send_message(message)

    logger.debug("Successfully sent message to %s", message.get("To"))
