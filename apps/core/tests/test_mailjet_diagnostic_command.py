"""
apps.core.tests.test_mailjet_diagnostic_command — regression tests for
the `test_mailjet` diagnostic management command.

These guard against a specific class of bug: `_REACHABILITY_URL` (and any
other value fed to `requests.get/post/request` in this command) being a
Markdown-style link — e.g. "[https://api.mailjet.com/](https://api.mailjet.com/)"
— instead of a plain URL string. `requests` does not raise on such a
string at call time in a way that's obviously connected to this cause,
so this is cheap insurance against it silently coming back.

No test here makes a real HTTPS call to Mailjet.
"""
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.core.management.commands.test_mailjet import _REACHABILITY_URL, Command


class ReachabilityUrlTests(TestCase):
    """`_REACHABILITY_URL` must be a plain URL, never Markdown link syntax."""

    def test_reachability_url_is_exactly_the_plain_mailjet_url(self):
        self.assertEqual(_REACHABILITY_URL, "https://api.mailjet.com/")

    def test_reachability_url_contains_no_markdown_link_syntax(self):
        # Catches "[https://...](https://...)" and similar constructs
        # regardless of the exact URL, in case the host ever changes.
        self.assertNotIn("[", _REACHABILITY_URL)
        self.assertNotIn("](", _REACHABILITY_URL)
        self.assertTrue(_REACHABILITY_URL.startswith("https://"))


@override_settings(
    MAILJET_API_KEY="test-key",
    MAILJET_SECRET_KEY="test-secret",
    DEFAULT_FROM_EMAIL="noreply@sams.test",
)
class RunCheckReachabilityCallTests(TestCase):
    """`--check` must pass the plain URL string to `requests.get`, not a
    Markdown-wrapped value — this would still be true even if
    `_REACHABILITY_URL` itself were correct but got mangled before use."""

    def test_requests_get_is_called_with_the_plain_url(self):
        command = Command()
        mock_response = MagicMock(status_code=200)
        mock_response.json.return_value = {"Data": []}

        mock_client = MagicMock()
        mock_client.sender.get.return_value = mock_response

        with patch(
            "apps.core.management.commands.test_mailjet.requests.get",
            return_value=MagicMock(),
        ) as mock_get, patch(
            "mailjet_rest.Client", return_value=mock_client
        ):
            command.stdout = MagicMock()
            command.style = MagicMock()
            command._run_check()

        mock_get.assert_called_once()
        called_url = mock_get.call_args[0][0]
        self.assertEqual(called_url, "https://api.mailjet.com/")
        self.assertNotIn("[", called_url)
        self.assertNotIn("](", called_url)
