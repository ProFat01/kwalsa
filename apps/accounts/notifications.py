"""
apps.accounts.notifications — SAMS v1.2 Communication Center (Mailjet migration).

v1.2 Feature 8 asks for the architecture to be built "around a Notification
Service" so that email is just one delivery provider today, and SMS can
become a second provider later "without redesigning anything." This module
is that seam:

  - NotificationProvider is the interface every delivery method implements.
  - EmailProvider is the only *enabled* one right now. It delivers through
    apps.core.mailjet_service — the Mailjet Email API over HTTPS — the
    same service apps.members.email_service now uses for the v1.1
    approval email, so there is exactly one place in SAMS that knows how
    to talk to Mailjet.
  - SMSProvider / PushProvider exist as disabled placeholders per Feature 8
    ("the UI must already include Email / SMS (Coming Soon) / Push
    Notification (Coming Soon)") — calling either raises before anything
    is sent. A future SMS integration means writing one real provider
    class and enabling it here; no view, form, model, or template in this
    module needs to change for that.

This module never touches apps.members.email_service (the approval email)
or its templates — that is a separate, already-approved v1.1 feature this
task is not allowed to modify. Announcements are a distinct kind of email
with their own subject/body, sent through the same Mailjet service.

Note on the old SMTP connection-reuse optimisation
----------------------------------------------------
The pre-Mailjet version of send_announcement() opened a single SMTP
connection (get_connection()) and reused it across every recipient in the
batch — a meaningful win for SMTP, where each new connection is a real
handshake. That optimisation is SMTP-specific and doesn't apply to an
HTTPS API: each Mailjet Send call is already an independent, stateless
HTTPS request, so there is nothing to keep open or reuse between
recipients. That connection-reuse code has been removed accordingly (see
PRODUCTION_DEPLOYMENT_2.md "Communication Center: synchronous bulk-send
limit" for the still-applicable note on very large recipient sets).
"""
import logging

from django.conf import settings

from apps.core import mailjet_service

from .models import Announcement

logger = logging.getLogger("apps.accounts.notifications")


class NotificationProvider:
    key = None
    label = None
    enabled = False

    def send(self, member, subject, message):
        raise NotImplementedError


class EmailProvider(NotificationProvider):
    key = "email"
    label = "Email"
    enabled = True

    def send(self, member, subject, message):
        """
        Returns (True, None) on a dispatched email, (False, reason) on
        anything else — never raises, matching email_service.py's "a
        delivery failure must not blow up the caller" rule, extended here
        to cover an announcement being sent to hundreds/thousands of
        members in one request: one bad address must not abort the rest
        of the batch.
        """
        if not member.email:
            return False, "no email on file"
        try:
            mailjet_service.send_email(
                to_email=member.email,
                subject=subject,
                html_body=message,
                text_body=message,
                to_name=getattr(member, "full_name", ""),
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com"),
                from_name=getattr(settings, "DEFAULT_FROM_NAME", ""),
            )
            return True, None
        except mailjet_service.MailjetServiceError as exc:
            logger.exception("Failed to send announcement email to member %s", member.pk)
            return False, str(exc)
        except Exception as exc:  # noqa: BLE001 — deliberately broad, see email_service.py's identical reasoning
            logger.exception("Failed to send announcement email to member %s", member.pk)
            return False, str(exc)


class SMSProvider(NotificationProvider):
    key = "sms"
    label = "SMS (Coming Soon)"
    enabled = False

    def send(self, member, subject, message):
        raise NotImplementedError("SMS delivery is not implemented yet.")


class PushProvider(NotificationProvider):
    key = "push"
    label = "Push Notification (Coming Soon)"
    enabled = False

    def send(self, member, subject, message):
        raise NotImplementedError("Push notification delivery is not implemented yet.")


PROVIDERS = {
    EmailProvider.key: EmailProvider(),
    SMSProvider.key: SMSProvider(),
    PushProvider.key: PushProvider(),
}


def send_announcement(announcement, recipients):
    """
    Sends `announcement` to every Member in `recipients` (an iterable —
    typically the queryset apps.members.services.resolve_announcement_recipients
    returned) via the provider named by announcement.delivery_method, then
    updates and saves the announcement's own sent/failed counts and status.

    Synchronous, in-request send — each recipient is one independent
    Mailjet API call. No Celery/Redis/queue infrastructure is introduced
    here (explicitly out of scope); for very large recipient sets on
    PythonAnywhere Free, see PRODUCTION_DEPLOYMENT_2.md "Communication
    Center: synchronous bulk-send limit".
    """
    provider = PROVIDERS.get(announcement.delivery_method)

    if provider is None or not provider.enabled:
        # Feature 8: SMS/Push are UI placeholders only. Defence in depth —
        # the form already rejects anything but "email" (see
        # AnnouncementComposeForm.clean_delivery_method) — this is the
        # second, model-adjacent check in case this function is ever
        # called from somewhere that skipped form validation.
        announcement.status = Announcement.Status.FAILED
        announcement.save(update_fields=["status"])
        return announcement

    sent = 0
    failed = 0
    for member in recipients:
        ok, _reason = provider.send(member, announcement.subject, announcement.message)
        if ok:
            sent += 1
        else:
            failed += 1

    announcement.sent_count = sent
    announcement.failed_count = failed
    if sent and not failed:
        announcement.status = Announcement.Status.SENT
    elif sent and failed:
        announcement.status = Announcement.Status.PARTIAL
    else:
        announcement.status = Announcement.Status.FAILED
    announcement.save(update_fields=["sent_count", "failed_count", "status"])
    return announcement
