"""
apps.core.tests.test_mailjet_service — unit tests for the Mailjet Email
API service layer.

No test in this file makes a real HTTPS call to Mailjet — the
`mailjet_rest.Client` is mocked wherever a "configured" call path is
exercised.
"""
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.core.mailjet_service import MailjetServiceError, send_email


@override_settings(
    MAILJET_API_KEY="test-key",
    MAILJET_SECRET_KEY="test-secret",
    DEFAULT_FROM_EMAIL="noreply@sams.test",
    DEFAULT_FROM_NAME="SAMS Test",
)
class SendEmailConfiguredTests(TestCase):
    """Behaviour when Mailjet credentials ARE configured — real API path."""

    def _mock_client(self, status_code=200, message_status="success"):
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.status_code = status_code
        mock_result.json.return_value = {"Messages": [{"Status": message_status}]}
        mock_client.send.create.return_value = mock_result
        return mock_client

    def test_success_returns_true(self):
        with patch("apps.core.mailjet_service._get_client", return_value=self._mock_client()):
            result = send_email(
                to_email="member@example.com",
                subject="Hi",
                html_body="<p>Hi</p>",
                text_body="Hi",
            )
        self.assertTrue(result)

    def test_sends_correct_payload_shape(self):
        client = self._mock_client()
        with patch("apps.core.mailjet_service._get_client", return_value=client):
            send_email(
                to_email="member@example.com",
                to_name="Member Name",
                subject="Hi there",
                html_body="<p>Hi</p>",
                text_body="Hi",
            )
        payload = client.send.create.call_args.kwargs["data"]
        message = payload["Messages"][0]
        self.assertEqual(message["To"], [{"Email": "member@example.com", "Name": "Member Name"}])
        self.assertEqual(message["Subject"], "Hi there")
        self.assertEqual(message["HTMLPart"], "<p>Hi</p>")
        self.assertEqual(message["TextPart"], "Hi")
        self.assertEqual(message["From"], {"Email": "noreply@sams.test", "Name": "SAMS Test"})

    def test_explicit_from_email_and_name_override_defaults(self):
        client = self._mock_client()
        with patch("apps.core.mailjet_service._get_client", return_value=client):
            send_email(
                to_email="member@example.com",
                subject="Hi",
                html_body="<p>Hi</p>",
                text_body="Hi",
                from_email="custom@sams.test",
                from_name="Custom Sender",
            )
        message = client.send.create.call_args.kwargs["data"]["Messages"][0]
        self.assertEqual(message["From"], {"Email": "custom@sams.test", "Name": "Custom Sender"})

    def test_non_200_status_raises_mailjet_service_error(self):
        with patch("apps.core.mailjet_service._get_client", return_value=self._mock_client(status_code=401)):
            with self.assertRaises(MailjetServiceError):
                send_email(to_email="member@example.com", subject="Hi", html_body="x", text_body="x")

    def test_rejected_message_status_raises_mailjet_service_error(self):
        with patch(
            "apps.core.mailjet_service._get_client",
            return_value=self._mock_client(message_status="error"),
        ):
            with self.assertRaises(MailjetServiceError):
                send_email(to_email="member@example.com", subject="Hi", html_body="x", text_body="x")

    def test_network_exception_raises_mailjet_service_error_not_propagate_raw(self):
        client = MagicMock()
        client.send.create.side_effect = ConnectionError("connection refused")
        with patch("apps.core.mailjet_service._get_client", return_value=client):
            with self.assertRaises(MailjetServiceError):
                send_email(to_email="member@example.com", subject="Hi", html_body="x", text_body="x")

    def test_failure_log_never_contains_the_api_secret(self):
        client = MagicMock()
        client.send.create.side_effect = ConnectionError("connection refused")
        with patch("apps.core.mailjet_service._get_client", return_value=client):
            with self.assertLogs("apps.core.mailjet_service", level="ERROR") as log_watcher:
                with self.assertRaises(MailjetServiceError):
                    send_email(to_email="member@example.com", subject="Hi", html_body="x", text_body="x")
        self.assertFalse(any("test-secret" in msg for msg in log_watcher.output))


@override_settings(MAILJET_API_KEY="", MAILJET_SECRET_KEY="", DEFAULT_FROM_EMAIL="noreply@sams.test")
class SendEmailUnconfiguredTests(TestCase):
    """
    Local-development convenience path: without credentials configured,
    send_email() must never attempt a real API call and must not raise.
    """

    def test_returns_true_without_calling_the_client(self):
        with patch("apps.core.mailjet_service._get_client") as mock_get_client:
            result = send_email(to_email="member@example.com", subject="Hi", html_body="x", text_body="x")
        self.assertTrue(result)
        mock_get_client.assert_not_called()

    def test_logs_the_email_instead_of_sending(self):
        with self.assertLogs("apps.core.mailjet_service", level="INFO") as log_watcher:
            send_email(to_email="member@example.com", subject="Hi there", html_body="x", text_body="x")
        self.assertTrue(any("member@example.com" in msg for msg in log_watcher.output))
