from email.message import EmailMessage

import aiosmtplib

from app.core.config import get_settings
from app.core.localization import translate
from app.core.templates import render_template

settings = get_settings()


async def send_email(*, to: str, subject: str, text_body: str, html_body: str) -> None:
    message = EmailMessage()
    message["From"] = f"{settings.mail_from_name} <{settings.mail_from_address}>"
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")

    await aiosmtplib.send(
        message,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_username or None,
        password=settings.smtp_password or None,
        start_tls=settings.smtp_use_tls,
    )


async def send_password_reset_email(*, name: str, email: str, reset_link: str, locale: str) -> None:
    expiry_minutes = settings.password_reset_token_expire_minutes

    context = {
        "reset_link": reset_link,
        "mail_from_name": settings.mail_from_name,
        "dir": "rtl" if locale == "ar" else "ltr",
        "locale": locale,
        "greeting": translate("email.password_reset.greeting", locale=locale, name=name),
        "intro": translate("email.password_reset.intro", locale=locale, expiry_minutes=expiry_minutes),
        "button_label": translate("email.password_reset.button", locale=locale),
        "fallback_intro": translate("email.password_reset.fallback_intro", locale=locale),
        "ignore_text": translate("email.password_reset.ignore", locale=locale),
    }
    subject = translate("email.password_reset.subject", locale=locale)

    text_body = render_template("emails/password_reset.txt", **context)
    html_body = render_template("emails/password_reset.html", **context)

    await send_email(to=email, subject=subject, text_body=text_body, html_body=html_body)
