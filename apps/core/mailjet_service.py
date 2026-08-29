"""
apps.core.mailjet_service — SAMS Mailjet Email API integration.

Single, dedicated seam for all outbound member-facing email. Every caller
that needs to deliver an email (apps.members.email_service's approval
email, apps.accounts.notifications' Communication Center) goes through
send_email() here rather than talking to Mailjet directly. That keeps
Mailjet-specific request/response shapes, auth, and error handling in one
place instead of scattered across signals/views/models.

Why the Mailjet Email API (HTTPS) instead of Mailjet SMTP
-----------------------------------------------------------
SMTP email works fine in local development but PythonAnywhere's Free tier
blocks outbound SMTP connections entirely, which is what made the old
django.core.mail SMTP backend unreliable in production. Mailjet's Send API
is a plain HTTPS POST (api.mailjet.com:443), which PythonAnywhere Free
does allow, so this module never opens an SMTP connection or configures
an SMTP host — it only ever calls the Mailjet REST API over HTTPS via the
official `mailjet-rest` client (a thin wrapper around `requests`).

Credentials
-----------
MAILJET_API_KEY / MAILJET_SECRET_KEY are read from Django settings (which
in turn come from the environment via django-environ — see
config/settings/base.py). Never hardcode them here and never log them.

Local development convenience
------------------------------
If MAILJET_API_KEY / MAILJET_SECRET_KEY are not configured (the common
case for a fresh clone — .env.example ships only placeholders), send_email()
does not attempt a real HTTPS call. Instead it logs the message it would
have sent, mirroring the developer experience of Django's console email
backend that development.py already uses. This means a fresh `git clone`
+ `python manage.py runserver` keeps working without anyone needing a real
Mailjet account, exactly as before this migration — only a *deployed*
environment with real MAILJET_API_KEY / MAILJET_SECRET_KEY values actually
talks to Mailjet.
"""
import logging

from django.conf import settings

logger = logging.getLogger("apps.core.mailjet_service")


class MailjetServiceError(Exception):
    """
    Raised when Mailjet Email API delivery fails for any reason: network
    failure, timeout, authentication failure, an invalid/unexpected API
    response shape, or Mailjet reporting the message itself was rejected
    (bad sender, bad recipient, etc).

    This is a controlled exception — every current caller (the approval
    email service and the Communication Center's EmailProvider) catches
    it, logs it, and continues without letting a single delivery failure
    propagate further. It intentionally carries no Mailjet request/response
    internals in a way that could leak the API key or secret; see _redact
    below.
    """


def _get_client():
    """
    Build a Mailjet REST client from settings. Imported lazily inside the
    function (rather than at module import time) so that environments
    without the `mailjet-rest` package installed — e.g. a minimal test
    environment that only imports apps.core.mailjet_service to patch
    send_email() and never actually calls this — don't fail on import.
    """
    from mailjet_rest import Client

    return Client(auth=(settings.MAILJET_API_KEY, settings.MAILJET_SECRET_KEY), version="v3.1")


def _mailjet_configured():
    return bool(settings.MAILJET_API_KEY and settings.MAILJET_SECRET_KEY)


def send_email(
    to_email,
    subject,
    html_body,
    text_body,
    to_name="",
    from_email=None,
    from_name=None,
):
    """
    Send a single email via the Mailjet Send API v3.1.

    Parameters
    ----------
    to_email : str — recipient address. Required.
    subject : str
    html_body : str — rendered HTML content.
    text_body : str — rendered plain-text content (always sent alongside
        the HTML part, matching the pre-Mailjet EmailMultiAlternatives
        behaviour of always providing a plain-text fallback).
    to_name : str, optional — recipient display name, where available.
    from_email : str, optional — defaults to settings.DEFAULT_FROM_EMAIL.
        Must be an address verified in the Mailjet account; this module
        does not and cannot bypass Mailjet's own sender verification.
    from_name : str, optional — defaults to settings.DEFAULT_FROM_NAME.

    Returns
    -------
    True on confirmed success.

    Raises
    ------
    MailjetServiceError on any failure. Callers that must not let an
    email failure interrupt their own workflow (member approval, an
    announcement's other recipients) are expected to catch this.
    """
    from_email = from_email or settings.DEFAULT_FROM_EMAIL
    from_name = from_name if from_name is not None else getattr(settings, "DEFAULT_FROM_NAME", "")

    if not _mailjet_configured():
        # Local/dev convenience — see module docstring. Not an error.
        logger.info(
            "MAILJET_API_KEY/MAILJET_SECRET_KEY not configured — printing "
            "email instead of calling the Mailjet API.\nTo: %s <%s>\nFrom: %s <%s>\nSubject: %s\n\n%s",
            to_name, to_email, from_name, from_email, subject, text_body,
        )
        return True

    message = {
        "From": {"Email": from_email, "Name": from_name},
        "To": [{"Email": to_email, "Name": to_name or ""}],
        "Subject": subject,
        "TextPart": text_body,
        "HTMLPart": html_body,
    }

    try:
        client = _get_client()
        result = client.send.create(data={"Messages": [message]})
    except MailjetServiceError:
        raise
    except Exception as exc:
        # Deliberately broad: connection errors, timeouts, DNS failures,
        # and anything else `requests` (via mailjet-rest) can raise all
        # land here as a single controlled exception type for callers.
        logger.error("Mailjet API request failed for %s: %s", to_email, exc.__class__.__name__)
        raise MailjetServiceError(f"Mailjet API request failed: {exc.__class__.__name__}") from exc

    if result.status_code != 200:
        # Non-200 covers auth failures (401), malformed payloads (400),
        # etc. Never include response body verbatim in the log/message —
        # Mailjet error payloads have never been observed to contain the
        # API secret, but we don't log full headers/body here as a matter
        # of policy rather than relying on that.
        logger.error("Mailjet API returned status %s for %s", result.status_code, to_email)
        raise MailjetServiceError(f"Mailjet API returned status {result.status_code}")

    try:
        payload = result.json()
        message_status = payload["Messages"][0]["Status"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        logger.error("Unexpected Mailjet API response shape for %s", to_email)
        raise MailjetServiceError("Unexpected Mailjet API response shape") from exc

    if message_status != "success":
        # Mailjet returned 200 but rejected the message itself — e.g. an
        # unverified sender or a malformed recipient address.
        logger.error("Mailjet rejected message to %s (status=%s)", to_email, message_status)
        raise MailjetServiceError(f"Mailjet rejected the message (status={message_status})")

    return True
