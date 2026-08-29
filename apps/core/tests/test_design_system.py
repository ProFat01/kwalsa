"""
Regression tests for the Module 1 global design-system polish.

This module changed exactly three files -- static/css/base.css,
static/css/components.css, static/js/site.js -- and zero templates, so
there is very little new *server-side* behavior to test with Django's
test client (which never executes CSS or JS). What these tests lock in
instead:

  1. The CSP-safety invariant established in the earlier production
     audit (zero inline style="" attributes, zero inline <script>
     blocks) still holds across every major page -- this is the
     concrete risk this kind of styling pass could have reintroduced,
     so it's asserted automatically rather than left to another manual
     grep next time someone edits a template.
  2. The static asset files this task shipped are actually served.
  3. The two small pieces of *template* logic this design system relies
     on -- the active-page nav indicator and the warning-alert tag
     mapping -- were already present in base.html and continue to work
     correctly with the new CSS.

Visual details (colors, shadows, hover-lift, spinner animation, the
:has() error-field auto-highlight, the mobile-menu smooth transition)
were verified with a real headless-browser session during development
and are documented in FRONTEND_DESIGN_SYSTEM.md; they aren't
re-asserted here since Django's test client has no rendering engine to
check computed CSS against.
"""
import os

from django.contrib.staticfiles import finders
from django.test import SimpleTestCase, override_settings
from django.urls import reverse

from apps.core.models import Association
from apps.members.tests.helpers import MediaIsolatedTestCase

PAGES_TO_AUDIT = [
    "core:home",
    "core:about",
    "core:contact",
    "members:register",
    "members:status_check",
    "elections:election_list",
]


@override_settings(DEFAULT_ASSOCIATION_SLUG="msa")
class CspSafetyInvariantTests(MediaIsolatedTestCase):
    """
    The production CSP is script-src 'self'; style-src 'self' plus the
    Google Fonts stylesheet -- no 'unsafe-inline' for either. Any
    style="" attribute or inline <script> block introduced by a future
    template edit would silently break in production while looking
    fine in development (where no CSP header is sent at all). This is
    asserted here so it fails loudly, in CI, instead.
    """

    def setUp(self):
        Association.objects.create(name="Malam Sidi Students Association", short_name="MSA", slug="msa")

    def test_no_inline_style_attributes_on_any_major_page(self):
        for url_name in PAGES_TO_AUDIT:
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertNotIn(b'style="', response.content)

    def test_no_inline_script_blocks_on_any_major_page(self):
        for url_name in PAGES_TO_AUDIT:
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertNotIn(b"<script>", response.content)

    def test_site_js_loaded_as_external_file_not_inline(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, '<script src="/static/js/site.js"')


class StaticAssetAvailabilityTests(SimpleTestCase):
    """
    The three files this module shipped actually exist on disk, in the
    project's static directory, and are non-trivial in size.

    Deliberately checked on the filesystem (via Django's staticfiles
    finders) rather than via an HTTP request through self.client: static
    file serving through a URL is runserver's own special-cased behavior
    (when DEBUG=True) or WhiteNoise's job in production -- neither path
    is wired into config/urls.py itself, so the Django test client
    (which only ever dispatches through the real URLconf) correctly has
    no route for /static/... at all. Asserting against the URL would be
    testing Django/WhiteNoise's infrastructure, not this project's code;
    asserting the files exist and aren't empty is the right scope here.
    """

    def test_base_css_exists_and_is_not_empty(self):
        path = finders.find("css/base.css")
        self.assertIsNotNone(path, "static/css/base.css not found by Django's staticfiles finders")
        self.assertGreater(os.path.getsize(path), 1000)

    def test_components_css_exists_and_is_not_empty(self):
        path = finders.find("css/components.css")
        self.assertIsNotNone(path, "static/css/components.css not found by Django's staticfiles finders")
        self.assertGreater(os.path.getsize(path), 1000)

    def test_site_js_exists_and_is_not_empty(self):
        path = finders.find("js/site.js")
        self.assertIsNotNone(path, "static/js/site.js not found by Django's staticfiles finders")
        self.assertGreater(os.path.getsize(path), 100)


@override_settings(DEFAULT_ASSOCIATION_SLUG="msa")
class NavigationAndAlertTemplateLogicTests(MediaIsolatedTestCase):
    """
    These two behaviors live in base.html's template logic (not this
    module's CSS/JS), but the new CSS classes (.is-active, .alert-warning)
    only mean anything if the template actually applies them -- so both
    ends of the contract are checked together here.
    """

    def setUp(self):
        self.association = Association.objects.create(
            name="Malam Sidi Students Association", short_name="MSA", slug="msa"
        )

    def test_active_page_gets_is_active_class_on_its_own_nav_link(self):
        response = self.client.get(reverse("core:about"))
        self.assertContains(response, 'href="' + reverse("core:about") + '" class="is-active"')

    def test_inactive_pages_do_not_get_is_active_class(self):
        response = self.client.get(reverse("core:about"))
        self.assertContains(response, 'href="' + reverse("core:home") + '" class="">')

    def test_warning_level_message_renders_with_alert_warning_class(self):
        """
        No view in the codebase currently calls messages.warning() (only
        messages.success(), in the contact view), but base.html's tag
        mapping supports it and the new CSS ships an .alert-warning
        variant -- this proves the two actually connect correctly for
        whenever a future view does use it, without adding a new view
        just to test one.

        Rendered directly via render_to_string with a duck-typed fake
        message object (matching what Django's messages framework
        actually provides in the template: a .tags attribute and a
        __str__), rather than round-tripping through the real cookie/
        session message storage backend -- which is Django's own
        machinery, not something this project's code controls, and is
        awkward to drive correctly through the test client's cookie
        jar. This isolates the test to exactly the piece of logic this
        project owns: base.html's tags -> CSS class mapping.
        """
        from django.template.loader import render_to_string

        class FakeMessage:
            tags = "warning"

            def __str__(self):
                return "This is a test warning message."

        html = render_to_string(
            "base.html",
            {"messages": [FakeMessage()], "association": self.association, "site_settings": None},
        )
        self.assertIn("alert-warning", html)
        self.assertIn("This is a test warning message.", html)
