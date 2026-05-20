from __future__ import annotations

import email.message
import smtplib
import ssl


def send_html_email(
    host: str,
    port: int,
    user: str,
    password: str,
    from_addr: str,
    to_addrs: list[str],
    subject: str,
    html_body: str,
) -> None:
    message = email.message.EmailMessage()
    message["From"] = from_addr
    message["To"] = ", ".join(to_addrs)
    message["Subject"] = subject
    message.set_content("This email requires HTML support.")
    message.add_alternative(html_body, subtype="html")

    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=30) as server:
            if user and password:
                server.login(user, password)
            server.send_message(message)
        return

    with smtplib.SMTP(host, port, timeout=30) as server:
        server.ehlo()
        server.starttls(context=ssl.create_default_context())
        server.ehlo()
        if user and password:
            server.login(user, password)
        server.send_message(message)
