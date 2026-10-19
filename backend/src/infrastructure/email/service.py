"""Build and send emails over SMTP.

``send_email`` is the transport; each ``send_<name>_email`` function renders one
email's templates and hands the result to it. These run inside the taskiq worker
(see ``tasks.py``), so they use relative imports only.
"""

from email.message import EmailMessage

import aiosmtplib

from ..config import get_settings
from .renderer import render_template

settings = get_settings()


async def send_email(*, to: str, subject: str, text_body: str, html_body: str) -> None:
    """Send one multipart (plain text + HTML) email via the configured SMTP server.

    Args:
        to: Recipient address.
        subject: Message subject.
        text_body: Plain-text body, shown by clients that don't render HTML.
        html_body: HTML body.

    Raises:
        aiosmtplib.SMTPException: If the SMTP server rejects the connection or message.
    """
    message = EmailMessage()
    message["From"] = f"{settings.MAIL_FROM_NAME} <{settings.MAIL_FROM_ADDRESS}>"
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    await aiosmtplib.send(
        message,
        hostname=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        username=settings.SMTP_USERNAME or None,
        password=settings.SMTP_PASSWORD or None,
        start_tls=settings.SMTP_USE_TLS,
    )


async def send_welcome_email(*, name: str, email: str) -> None:
    """Render and send the welcome email to a newly registered user.

    Args:
        name: The user's display name.
        email: The user's email address.
    """
    context = {
        "name": name,
        "app_name": settings.APP_NAME,
    }
    subject = f"Welcome to {settings.APP_NAME}"

    text_body = render_template("emails/welcome.txt", **context)
    html_body = render_template("emails/welcome.html", **context)

    await send_email(to=email, subject=subject, text_body=text_body, html_body=html_body)
