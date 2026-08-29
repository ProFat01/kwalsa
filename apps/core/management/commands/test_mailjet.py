"""
Safe, standalone diagnostic for the SAMS ↔ Mailjet Email API connection.

This command exists to answer one question unambiguously: can *this*
running environment (in particular, PythonAnywhere Free, which is what
motivated the whole Mailjet migration — see apps/core/mailjet_service.py's
docstring) make a real HTTPS request to Mailjet and authenticate?

It is deliberately separate from apps.core.mailjet_service.send_email()
and does not call it. send_email() intentionally collapses every failure
mode into a single MailjetServiceError so member-approval/announcement
callers don't have to care *why* delivery failed — exactly right for
that use case, and exactly wrong for this one. A diagnostic needs the
raw status code and response shape back so it can tell a DNS failure
apart from a 401 apart from a rejected sender. This command talks to
`mailjet_rest.Client` directly for that reason, using the same
MAILJET_API_KEY / MAILJET_SECRET_KEY / DEFAULT_FROM_EMAIL settings
mailjet_service.py uses — nothing about that module is changed.

Modes
-----
    python manage.py test_mailjet --check
        Safe connectivity + authentication + sender-verification check.
        Never sends an email. Two HTTPS calls are made:
          1. A plain, unauthenticated GET to https://api.mailjet.com/ —
             pure reachability, to tell "can't reach the host at all"
             apart from "reached it but auth/API failed" in one run.
          2. GET /v3/REST/sender via the authenticated Mailjet client —
             the official, documented, read-only Sender resource
             (https://dev.mailjet.com/email/reference/sender-addresses/).
             This is the least invasive authenticated endpoint available:
             it proves the API key/secret are valid AND, as a bonus,
             lists which sender addresses are verified — directly
             answering "is DEFAULT_FROM_EMAIL usable" without sending
             anything. Mailjet's REST v3 API has no dedicated
             "ping"/"health" endpoint, so this is the safest legitimate
             substitute; nothing here was invented.

    python manage.py test_mailjet --send-test --to you@example.com
        Sends one real, clearly-labelled test message via the Send API
        v3.1 (the same version/endpoint apps.core.mailjet_service uses).
        Requires --to explicitly — no address is ever hardcoded or
        defaulted. Never uses real member data.

    python manage.py test_mailjet --send-test --to you@example.com --sandbox
        Same as above but sets the Send API v3.1 "SandboxMode": true
        payload flag (documented at
        https://dev.mailjet.com/email/guides/send-api-v31/#sandbox-mode).
        Mailjet validates the request end-to-end — auth, payload shape,
        sender verification — and returns the same success/error
        reporting as a real send, but never actually delivers anything.
        This is Mailjet's real sandbox mechanism (not an invented
        parameter) and is the recommended step *before* a real
        --send-test.

Never print secrets
--------------------
The full MAILJET_SECRET_KEY is never printed, logged, or included in
any output this command produces — not even partially. MAILJET_API_KEY
is only ever shown masked (first 4 / last 4 characters). See _mask().
"""
import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

TEST_SUBJECT = "SAMS Mailjet API Test"
TEST_TEXT_BODY = (
    "This is a test of the SAMS Mailjet Email API integration.\n\n"
    "If you are reading this, the SAMS deployment was able to reach "
    "the Mailjet API over HTTPS and successfully send a message "
    "through it.\n\n"
    "This message was sent by the `test_mailjet` diagnostic management "
    "command and does not involve any real member data."
)
TEST_HTML_BODY = (
    "<p>This is a test of the <strong>SAMS Mailjet Email API</strong> "
    "integration.</p>"
    "<p>If you are reading this, the SAMS deployment was able to reach "
    "the Mailjet API over HTTPS and successfully send a message "
    "through it.</p>"
    "<p>This message was sent by the <code>test_mailjet</code> "
    "diagnostic management command and does not involve any real "
    "member data.</p>"
)

# Plain, unauthenticated reachability probe. Not a Mailjet API call —
# just establishing whether this environment can open a TLS connection
# to the host at all, so a DNS/network failure can be told apart from
# an authentication or API failure in the very next step.
_REACHABILITY_URL = "https://api.mailjet.com/"


class Command(BaseCommand):
    help = (
        "Diagnose the SAMS -> Mailjet Email API connection (config, network, "
        "auth, sender verification) without touching member-facing email. "
        "Use --check for a safe read-only connectivity test, or --send-test "
        "--to <email> to send one clearly-labelled real test message."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--check", action="store_true",
            help="Safe mode: verify config, network reachability, authentication, and "
                 "sender verification. Never sends an email.",
        )
        parser.add_argument(
            "--send-test", action="store_true",
            help="Send one real, clearly-labelled test message. Requires --to.",
        )
        parser.add_argument(
            "--to", type=str, default=None,
            help="Recipient address for --send-test. Required with --send-test; "
                 "there is no default — you must supply your own address.",
        )
        parser.add_argument(
            "--sandbox", action="store_true",
            help="With --send-test: use Mailjet's real Send API v3.1 SandboxMode "
                 "(validates the full request without delivering anything). "
                 "Recommended before a non-sandbox --send-test.",
        )

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------
    def handle(self, *args, **options):
        check = options["check"]
        send_test = options["send_test"]
        to = options["to"]
        sandbox = options["sandbox"]

        if check and send_test:
            raise CommandError("Pass --check or --send-test, not both, in a single run.")
        if not check and not send_test:
            raise CommandError(
                "Nothing to do. Pass --check for a safe connectivity test, or "
                "--send-test --to <email> to send one real test message."
            )
        if send_test and not to:
            raise CommandError(
                "--send-test requires --to <your own email address>. "
                "Refusing to guess or default a recipient."
            )
        if check and to:
            self.stdout.write(self.style.WARNING(
                "--to is ignored with --check — --check never sends an email."
            ))
        if check and sandbox:
            self.stdout.write(self.style.WARNING(
                "--sandbox is ignored with --check — --check never sends an email "
                "(sandboxed or otherwise)."
            ))

        self.stdout.write(self.style.MIGRATE_HEADING("SAMS Mailjet diagnostic"))
        self._report_config()

        if not self._mailjet_configured():
            raise CommandError(
                "CONFIGURATION PROBLEM: MAILJET_API_KEY and/or MAILJET_SECRET_KEY "
                "are not set in this environment. Set them (see .env.example) before "
                "running --check or --send-test. Nothing was contacted."
            )

        if check:
            self._run_check()
        else:
            self._run_send_test(to=to, sandbox=sandbox)

    # ------------------------------------------------------------------
    # Config reporting
    # ------------------------------------------------------------------
    def _mailjet_configured(self):
        return bool(settings.MAILJET_API_KEY and settings.MAILJET_SECRET_KEY)

    def _report_config(self):
        api_key = settings.MAILJET_API_KEY or ""
        secret = settings.MAILJET_SECRET_KEY or ""
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "") or ""

        self.stdout.write("Configuration:")
        self.stdout.write(f"  MAILJET_API_KEY:    {self._mask(api_key) if api_key else '(not set)'}")
        self.stdout.write(f"  MAILJET_SECRET_KEY: {'(configured, hidden)' if secret else '(not set)'}")
        self.stdout.write(f"  DEFAULT_FROM_EMAIL: {from_email or '(not set)'}")
        self.stdout.write("")

    @staticmethod
    def _mask(value):
        """Show only enough of a credential to eyeball-confirm which one is
        loaded — never enough to reconstruct it. Full value never appears
        anywhere in this command's output."""
        if len(value) <= 8:
            return "*" * len(value)
        return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"

    # ------------------------------------------------------------------
    # --check
    # ------------------------------------------------------------------
    def _run_check(self):
        # Step 1: raw HTTPS reachability, unauthenticated. Isolates
        # DNS/network/allowlist failures from anything Mailjet-specific.
        self.stdout.write("Step 1/2: HTTPS reachability to api.mailjet.com ...")
        try:
            requests.get(_REACHABILITY_URL, timeout=10)
        except requests.exceptions.SSLError as exc:
            raise CommandError(
                "NETWORK/TLS PROBLEM: could not establish a trusted HTTPS connection "
                f"to api.mailjet.com ({exc.__class__.__name__}). This environment can "
                "resolve the host but the TLS handshake failed. Do not disable "
                "certificate verification to work around this — investigate the "
                "underlying cause (e.g. an outdated CA bundle) instead."
            )
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            raise CommandError(
                "NETWORK PROBLEM (Case A): could not reach api.mailjet.com at all "
                f"({exc.__class__.__name__}). This is a DNS/connectivity/allowlist "
                "problem in this environment, not a Mailjet credentials problem — "
                "the authenticated check below was not attempted. On PythonAnywhere "
                "Free, see PRODUCTION_DEPLOYMENT.md and this command's own docstring "
                "for the independent requests-based reachability test to run from a "
                "plain Bash console."
            )
        except requests.exceptions.RequestException as exc:
            raise CommandError(
                f"NETWORK PROBLEM: unexpected error reaching api.mailjet.com "
                f"({exc.__class__.__name__}). The authenticated check below was not "
                "attempted."
            )
        self.stdout.write(self.style.SUCCESS("  Host is reachable over HTTPS."))
        self.stdout.write("")

        # Step 2: authenticated, read-only call — GET /v3/REST/sender.
        # Proves the API key/secret pair is valid and reports sender
        # verification status. No email is sent by this call.
        self.stdout.write("Step 2/2: authenticating and checking sender verification ...")
        from mailjet_rest import Client

        client = Client(auth=(settings.MAILJET_API_KEY, settings.MAILJET_SECRET_KEY), version="v3")
        try:
            result = client.sender.get()
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            raise CommandError(
                f"NETWORK PROBLEM (Case A): connection failed during the authenticated "
                f"call ({exc.__class__.__name__}), even though the plain reachability "
                "check above succeeded. This can happen with an intermittent or "
                "restrictive outbound allowlist — retry, and if it persists treat it "
                "as a connectivity problem, not a credentials problem."
            )
        except Exception as exc:  # noqa: BLE001 — surfaced as a generic diagnostic failure
            raise CommandError(
                f"UNEXPECTED PROBLEM: the Mailjet client raised {exc.__class__.__name__} "
                "before an HTTP response was received. This is not one of the "
                "classified failure modes below — inspect the underlying error."
            )

        self._report_status_meaning(result.status_code)

        if result.status_code == 401:
            raise CommandError(
                "AUTHENTICATION PROBLEM (Case B): Mailjet returned 401 Unauthorized. "
                "MAILJET_API_KEY / MAILJET_SECRET_KEY are being sent, but Mailjet is "
                "rejecting them — double-check they match the API Keys page in the "
                "Mailjet dashboard exactly (no extra whitespace, correct pair)."
            )
        if result.status_code == 400:
            raise CommandError(
                f"API REJECTION (Case C): Mailjet returned 400 Bad Request for a plain "
                f"GET /v3/REST/sender call. Response body: {self._safe_body(result)}"
            )
        if result.status_code != 200:
            raise CommandError(
                f"UNEXPECTED RESPONSE: Mailjet returned HTTP {result.status_code} for "
                f"GET /v3/REST/sender. Response body: {self._safe_body(result)}"
            )

        self.stdout.write(self.style.SUCCESS(
            "  Authenticated successfully — credentials are valid."
        ))
        self._report_sender_verification(result)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            "CHECK PASSED: PythonAnywhere -> Mailjet API is reachable and authenticated. "
            "No email was sent."
        ))
        self.stdout.write(
            "Next step: run `python manage.py test_mailjet --send-test --to "
            "you@example.com --sandbox` to validate a full send without delivering "
            "anything, before a real --send-test."
        )

    def _report_sender_verification(self, result):
        from_email = (getattr(settings, "DEFAULT_FROM_EMAIL", "") or "").lower()
        try:
            senders = result.json().get("Data", [])
        except ValueError:
            self.stdout.write(self.style.WARNING(
                "  Could not parse the sender list response — skipping sender-"
                "verification check."
            ))
            return

        if not senders:
            self.stdout.write(self.style.WARNING(
                "  SENDER VERIFICATION PROBLEM (Case D): this Mailjet account has no "
                "verified sender addresses at all yet. DEFAULT_FROM_EMAIL "
                f"({from_email or '(not set)'}) is not usable until at least one "
                "sender is added and verified in the Mailjet dashboard "
                "(Account > Sender addresses & domains)."
            ))
            return

        match = next((s for s in senders if (s.get("Email") or "").lower() == from_email), None)
        if match is None:
            self.stdout.write(self.style.WARNING(
                f"  SENDER VERIFICATION PROBLEM (Case D): DEFAULT_FROM_EMAIL "
                f"({from_email or '(not set)'}) does not appear in this Mailjet "
                "account's sender list at all. Add and verify it in the Mailjet "
                "dashboard before sending — Mailjet will reject any message From "
                "an unverified address."
            ))
            return

        status = match.get("Status", "unknown")
        if status.lower() == "active":
            self.stdout.write(self.style.SUCCESS(
                f"  DEFAULT_FROM_EMAIL ({from_email}) is a verified, active sender."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"  SENDER VERIFICATION PROBLEM (Case D): DEFAULT_FROM_EMAIL "
                f"({from_email}) is registered but its status is '{status}', not "
                "Active. Complete verification in the Mailjet dashboard before "
                "sending."
            ))

    # ------------------------------------------------------------------
    # --send-test
    # ------------------------------------------------------------------
    def _run_send_test(self, to, sandbox):
        mode = "SANDBOX (no delivery)" if sandbox else "REAL SEND"
        self.stdout.write(f"Mode: {mode}")
        self.stdout.write(f"Recipient: {to}")
        self.stdout.write("")

        from mailjet_rest import Client

        from_email = settings.DEFAULT_FROM_EMAIL
        from_name = getattr(settings, "DEFAULT_FROM_NAME", "") or ""

        message = {
            "From": {"Email": from_email, "Name": from_name},
            "To": [{"Email": to, "Name": ""}],
            "Subject": TEST_SUBJECT,
            "TextPart": TEST_TEXT_BODY,
            "HTMLPart": TEST_HTML_BODY,
        }
        payload = {"Messages": [message]}
        if sandbox:
            # Real, documented Send API v3.1 flag — Mailjet validates the
            # whole request (auth, payload, sender verification) but never
            # delivers anything. Not an invented parameter.
            payload["SandboxMode"] = True

        client = Client(auth=(settings.MAILJET_API_KEY, settings.MAILJET_SECRET_KEY), version="v3.1")
        try:
            result = client.send.create(data=payload)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            raise CommandError(
                f"NETWORK PROBLEM (Case A): could not reach the Mailjet Send API "
                f"({exc.__class__.__name__}). Run `python manage.py test_mailjet "
                "--check` for a fuller diagnosis; nothing was sent."
            )
        except Exception as exc:  # noqa: BLE001
            raise CommandError(
                f"UNEXPECTED PROBLEM: {exc.__class__.__name__} before an HTTP response "
                "was received. Nothing was confirmed sent."
            )

        self._report_status_meaning(result.status_code)

        if result.status_code == 401:
            raise CommandError(
                "AUTHENTICATION PROBLEM (Case B): Mailjet returned 401 Unauthorized. "
                "Nothing was sent."
            )
        if result.status_code == 400:
            raise CommandError(
                f"API REJECTION (Case C): Mailjet returned 400 Bad Request. This "
                "usually means an invalid payload, sender, or recipient. Response "
                f"body: {self._safe_body(result)}"
            )
        if result.status_code != 200:
            raise CommandError(
                f"UNEXPECTED RESPONSE: Mailjet returned HTTP {result.status_code}. "
                f"Response body: {self._safe_body(result)}"
            )

        try:
            payload_out = result.json()
            msg_status = payload_out["Messages"][0]["Status"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise CommandError(
                f"UNEXPECTED RESPONSE SHAPE: got HTTP 200 but couldn't find a "
                f"Messages[0].Status field. Raw body: {self._safe_body(result)}"
            )

        if msg_status != "success":
            raise CommandError(
                f"MAILJET REJECTION (Case E): HTTP 200 but the message itself was "
                f"not accepted (status={msg_status}). This usually means an "
                "unverified sender or invalid recipient. Full response: "
                f"{self._safe_body(result)}"
            )

        self.stdout.write("")
        if sandbox:
            self.stdout.write(self.style.SUCCESS(
                "SANDBOX SEND PASSED: Mailjet validated the full request (auth, "
                "payload, sender verification) and reported success — but this was "
                "SandboxMode, so nothing was actually delivered."
            ))
            self.stdout.write(
                "Next step: re-run without --sandbox to perform one real send."
            )
        else:
            self.stdout.write(self.style.SUCCESS(
                f"REAL SEND SUCCEEDED: Mailjet accepted and is delivering the test "
                f"message to {to}. Check that inbox (and spam folder) to confirm "
                "final delivery."
            ))

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------
    def _report_status_meaning(self, status_code):
        self.stdout.write(f"  HTTP status: {status_code}")

    @staticmethod
    def _safe_body(result):
        """
        Best-effort response body for diagnostics. Mailjet error payloads
        are not documented to ever contain the API secret (the secret is
        sent only in the outbound Authorization header, never echoed
        back), but this is still truncated and never includes request
        headers, as a matter of policy rather than relying on that alone.
        """
        try:
            return str(result.json())[:500]
        except ValueError:
            return "(non-JSON response body, not shown)"
