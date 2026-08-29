"""
apps.members.email_service — SAMS v1.1 (Mailjet migration)

Sends the post-approval welcome email to a newly-approved member.

Design constraints (all non-negotiable, per the v1.1 spec, preserved
across the Mailjet migration):

1. The approval transaction MUST complete before this is called.
   This module is called from the signal handler AFTER the member's
   approval_status and membership_id have been committed — never inside
   the atomic block that performs the approval itself.

2. Email delivery failure MUST NOT roll back the approval or raise to
   the admin. Every exception is caught here, logged, and silently
   swallowed. The member is approved either way.

3. No email → no attempt, no error. The caller checks member.email
   before calling; this module does the same as a defence-in-depth guard.

4. Delivery goes through apps.core.mailjet_service — the Mailjet Email
   API over HTTPS — not SMTP. See apps/core/mailjet_service.py for why.

5. No inline secrets. Mailjet credentials come from Django settings
   (MAILJET_API_KEY / MAILJET_SECRET_KEY) set via .env — never hardcoded
   here.
"""
import logging

from django.conf import settings
from django.template.loader import render_to_string

from apps.core import mailjet_service

logger = logging.getLogger("apps.members.email_service")

# Template paths — both live in apps/members/templates/members/
_HTML_TEMPLATE = "members/email/approval_email.html"
_TXT_TEMPLATE = "members/email/approval_email.txt"

APPROVAL_EMAIL_SUBJECT = "Welcome to Malam Sidi Students Association"


def send_approval_email(member, request=None):
    """
    Send the welcome/approval email to `member`.

    Returns True if the email was dispatched without error, False otherwise.
    False is informational only — the caller (signal handler) does NOT
    treat it as a failure; the approval stands regardless.

    Parameters
    ----------
    member : apps.members.models.Member
        The freshly-approved member. Must have approval_status == APPROVED
        and a non-empty membership_id by the time this is called.
    request : HttpRequest or None
        Passed through to the template context so absolute URLs (portal,
        card) can be built with request.build_absolute_uri().  When None
        (e.g. called from a management command or the shell) the template
        falls back to a relative URL placeholder.
    """
    if not member.email:
        # Nothing to do — not an error.
        return False

    try:
        _send(member, request)
        logger.info(
            "Approval email sent to member %s (membership_id=%s)",
            member.pk,
            member.membership_id,
        )
        return True
    except Exception:
        # Deliberately broad: Mailjet auth failure, connection timeout,
        # a rejected sender/recipient — all of these are configuration /
        # infrastructure problems that must not surface as a Django error
        # to the approving admin.
        logger.exception(
            "Failed to send approval email to member %s (membership_id=%s). "
            "Approval is unaffected.",
            member.pk,
            member.membership_id,
        )
        return False


def _send(member, request):
    """
    Internal: build the email content and dispatch it via the Mailjet
    Email API. Any exception propagates to send_approval_email() which
    catches and logs it.
    """
    # Build the portal and card URLs.  When a real request is available we
    # get proper scheme+host (e.g. https://DevProf.pythonanywhere.com/…).
    # When there's no request (management command, shell) we emit a relative
    # path — better than a broken absolute URL with a wrong host.
    if request is not None:
        from django.urls import reverse
        portal_url = request.build_absolute_uri(reverse("members:portal_login"))
        card_url = request.build_absolute_uri(reverse("members:portal_card"))
    else:
        from django.urls import reverse
        portal_url = reverse("members:portal_login")
        card_url = reverse("members:portal_card")

    # Association logo URL for the email header.  Only included if the
    # logo file actually exists — a missing logo must never break delivery.
    association = member.association
    logo_url = None
    if association.logo and request is not None:
        try:
            logo_url = request.build_absolute_uri(association.logo.url)
        except Exception:
            logo_url = None

    context = {
        "member": member,
        "association": association,
        "portal_url": portal_url,
        "card_url": card_url,
        "logo_url": logo_url,
    }

    html_body = render_to_string(_HTML_TEMPLATE, context)
    # Plain-text fallback — always sent alongside HTML for email clients
    # that prefer or require it.
    text_body = render_to_string(_TXT_TEMPLATE, context)

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com")
    from_name = getattr(settings, "DEFAULT_FROM_NAME", "")

    mailjet_service.send_email(
        to_email=member.email,
        subject=APPROVAL_EMAIL_SUBJECT,
        html_body=html_body,
        text_body=text_body,
        to_name=member.full_name,
        from_email=from_email,
        from_name=from_name,
    )
