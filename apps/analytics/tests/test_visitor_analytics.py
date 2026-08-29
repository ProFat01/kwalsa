"""
Tests for v2.1 — Visitor & Usage Analytics.

Organized to match VISITOR_ANALYTICS.md / SAMS_v2.1_PROMPT.txt's testing
requirements: Tracking, Privacy, Aggregation, Permissions, Performance,
Retention. Regression coverage is the rest of the existing suite passing
unmodified alongside this file (see the final report).
"""
import datetime

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.analytics import services, tracking
from apps.analytics.models import PageVisit
from apps.core.models import Association


@override_settings(DEFAULT_ASSOCIATION_SLUG="msa")
class VisitorAnalyticsTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles", verbosity=0)
        cls.association = Association.objects.create(
            name="Malam Sidi Students Association", short_name="MSA", slug="msa"
        )

    def _login_as_analytics_admin(self):
        user = User.objects.create_user(username="analytics_admin", password="x", is_staff=True)
        user.groups.add(Group.objects.get(name="Analytics Admin"))
        self.client.login(username="analytics_admin", password="x")
        return user

    def _login_as_plain_staff(self):
        User.objects.create_user(username="plainstaff", password="x", is_staff=True)
        self.client.login(username="plainstaff", password="x")

    def _make_visit(self, **overrides):
        defaults = dict(
            association=self.association,
            visit_date=timezone.localdate(),
            page_key="core:home",
            path="/",
            visitor_hash="a" * 64,
            visitor_type=PageVisit.VisitorType.ANONYMOUS,
            device_category=PageVisit.DeviceCategory.DESKTOP,
            browser_category=PageVisit.BrowserCategory.CHROME,
            referrer_category=PageVisit.ReferrerCategory.DIRECT,
        )
        defaults.update(overrides)
        return PageVisit.objects.create(**defaults)


# ---------------------------------------------------------------------------
# Tracking
# ---------------------------------------------------------------------------
class TrackingMiddlewareTests(VisitorAnalyticsTestCase):
    def test_public_page_visit_is_recorded(self):
        self.assertEqual(PageVisit.objects.count(), 0)
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PageVisit.objects.count(), 1)
        visit = PageVisit.objects.get()
        self.assertEqual(visit.page_key, "core:home")
        self.assertEqual(visit.visitor_type, PageVisit.VisitorType.ANONYMOUS)

    def test_multiple_public_pages_each_recorded_once(self):
        self.client.get(reverse("core:home"))
        self.client.get(reverse("core:about"))
        self.client.get(reverse("elections:election_list"))
        self.assertEqual(PageVisit.objects.count(), 3)
        self.assertEqual(
            set(PageVisit.objects.values_list("page_key", flat=True)),
            {"core:home", "core:about", "elections:election_list"},
        )

    def test_admin_pages_are_not_recorded(self):
        self.client.get("/admin/login/")
        self.assertEqual(PageVisit.objects.count(), 0)

    def test_staff_dashboard_pages_are_not_recorded(self):
        self._login_as_analytics_admin()
        self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(PageVisit.objects.count(), 0)

    def test_analytics_dashboard_pages_are_not_recorded(self):
        """The analytics module must not inflate its own visitor stats."""
        self._login_as_analytics_admin()
        self.client.get(reverse("analytics:overview"))
        self.client.get(reverse("analytics:visitor_analytics_dashboard"))
        self.assertEqual(PageVisit.objects.count(), 0)

    def test_authenticated_staff_activity_excluded_even_on_public_pages(self):
        """Section 5: staff/admin activity is excluded from public visitor stats by default."""
        self._login_as_analytics_admin()
        self.client.get(reverse("core:home"))
        self.assertEqual(PageVisit.objects.count(), 0)

    def test_post_requests_are_not_recorded(self):
        self.client.post(reverse("core:contact"), data={})
        self.assertEqual(PageVisit.objects.count(), 0)

    def test_not_found_requests_are_not_recorded(self):
        self.client.get("/this-page-does-not-exist/")
        self.assertEqual(PageVisit.objects.count(), 0)

    def test_excluded_path_prefixes_helper(self):
        self.assertTrue(tracking.is_excluded_path("/admin/login/"))
        self.assertTrue(tracking.is_excluded_path("/dashboard/"))
        self.assertTrue(tracking.is_excluded_path("/analytics/"))
        self.assertTrue(tracking.is_excluded_path("/static/css/base.css"))
        self.assertTrue(tracking.is_excluded_path("/media/photo.png"))
        self.assertTrue(tracking.is_excluded_path("/favicon.ico"))
        self.assertTrue(tracking.is_excluded_path("/robots.txt"))
        self.assertFalse(tracking.is_excluded_path("/"))
        self.assertFalse(tracking.is_excluded_path("/about/"))

    def test_member_portal_session_recorded_as_member_visitor_type(self):
        session = self.client.session
        session["portal_member_id"] = 1
        session.save()
        self.client.get(reverse("core:home"))
        visit = PageVisit.objects.get()
        self.assertEqual(visit.visitor_type, PageVisit.VisitorType.MEMBER)


class ClassificationHelperTests(TestCase):
    def test_classify_device_mobile(self):
        ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
        self.assertEqual(tracking.classify_device(ua), PageVisit.DeviceCategory.MOBILE)

    def test_classify_device_tablet(self):
        ua = "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
        self.assertEqual(tracking.classify_device(ua), PageVisit.DeviceCategory.TABLET)

    def test_classify_device_desktop_default(self):
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        self.assertEqual(tracking.classify_device(ua), PageVisit.DeviceCategory.DESKTOP)

    def test_classify_device_unknown_for_empty(self):
        self.assertEqual(tracking.classify_device(""), PageVisit.DeviceCategory.UNKNOWN)

    def test_classify_browser_edge_over_chrome(self):
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36 Edg/120.0"
        self.assertEqual(tracking.classify_browser(ua), PageVisit.BrowserCategory.EDGE)

    def test_classify_browser_chrome(self):
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
        self.assertEqual(tracking.classify_browser(ua), PageVisit.BrowserCategory.CHROME)

    def test_classify_browser_firefox(self):
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0"
        self.assertEqual(tracking.classify_browser(ua), PageVisit.BrowserCategory.FIREFOX)

    def test_classify_browser_safari(self):
        ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
        self.assertEqual(tracking.classify_browser(ua), PageVisit.BrowserCategory.SAFARI)

    def test_classify_referrer_direct_when_empty(self):
        self.assertEqual(tracking.classify_referrer("", "example.com"), PageVisit.ReferrerCategory.DIRECT)

    def test_classify_referrer_internal_treated_as_direct(self):
        self.assertEqual(
            tracking.classify_referrer("https://example.com/about/", "example.com"),
            PageVisit.ReferrerCategory.DIRECT,
        )

    def test_classify_referrer_search_engine(self):
        self.assertEqual(
            tracking.classify_referrer("https://www.google.com/search?q=sams", "example.com"),
            PageVisit.ReferrerCategory.SEARCH,
        )

    def test_classify_referrer_social(self):
        self.assertEqual(
            tracking.classify_referrer("https://www.facebook.com/", "example.com"),
            PageVisit.ReferrerCategory.SOCIAL,
        )

    def test_classify_referrer_other_website(self):
        self.assertEqual(
            tracking.classify_referrer("https://some-blog.example/post", "example.com"),
            PageVisit.ReferrerCategory.OTHER_WEBSITE,
        )


# ---------------------------------------------------------------------------
# Privacy
# ---------------------------------------------------------------------------
class PrivacyTests(VisitorAnalyticsTestCase):
    def test_raw_ip_never_stored_on_model(self):
        field_names = {f.name for f in PageVisit._meta.get_fields()}
        self.assertNotIn("ip_address", field_names)
        self.assertNotIn("ip", field_names)
        self.assertNotIn("email", field_names)
        self.assertNotIn("phone_number", field_names)
        self.assertNotIn("user_agent", field_names)

    def test_visitor_hash_is_not_the_raw_ip(self):
        visit_hash = tracking.hash_visitor("203.0.113.7", "Mozilla/5.0", 1)
        self.assertNotIn("203.0.113.7", visit_hash)
        self.assertEqual(len(visit_hash), 64)  # sha256 hex digest length

    def test_visitor_hash_rotates_daily(self):
        day_one = datetime.date(2026, 1, 1)
        day_two = datetime.date(2026, 1, 2)
        hash_one = tracking.hash_visitor("203.0.113.7", "Mozilla/5.0", 1, when=day_one)
        hash_two = tracking.hash_visitor("203.0.113.7", "Mozilla/5.0", 1, when=day_two)
        self.assertNotEqual(hash_one, hash_two)

    def test_visitor_hash_stable_within_the_same_day(self):
        day = datetime.date(2026, 1, 1)
        hash_a = tracking.hash_visitor("203.0.113.7", "Mozilla/5.0", 1, when=day)
        hash_b = tracking.hash_visitor("203.0.113.7", "Mozilla/5.0", 1, when=day)
        self.assertEqual(hash_a, hash_b)

    def test_real_request_never_persists_raw_ip_string(self):
        response = self.client.get(reverse("core:home"), REMOTE_ADDR="203.0.113.99")
        self.assertEqual(response.status_code, 200)
        visit = PageVisit.objects.get()
        self.assertNotEqual(visit.visitor_hash, "203.0.113.99")
        self.assertNotIn("203.0.113.99", visit.visitor_hash)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------
class AggregationTests(VisitorAnalyticsTestCase):
    def test_visitor_overview_counts_today(self):
        self._make_visit(visitor_hash="hash-1")
        self._make_visit(visitor_hash="hash-1")  # same visitor, second pageview
        self._make_visit(visitor_hash="hash-2")
        overview = services.visitor_overview(self.association)
        self.assertEqual(overview["visits_today"], 3)
        self.assertEqual(overview["unique_today"], 2)

    def test_visitor_overview_excludes_other_days_from_today(self):
        yesterday = timezone.localdate() - datetime.timedelta(days=1)
        self._make_visit(visit_date=yesterday, visitor_hash="hash-old")
        self._make_visit(visitor_hash="hash-new")
        overview = services.visitor_overview(self.association)
        self.assertEqual(overview["visits_today"], 1)
        self.assertEqual(overview["total_visits"], 2)

    def test_traffic_trend_grouped_by_date(self):
        today = timezone.localdate()
        yesterday = today - datetime.timedelta(days=1)
        self._make_visit(visit_date=yesterday, visitor_hash="a")
        self._make_visit(visit_date=yesterday, visitor_hash="b")
        self._make_visit(visit_date=today, visitor_hash="c")
        trend = services.traffic_trend(self.association, yesterday, today)
        self.assertEqual(len(trend), 2)
        self.assertEqual(trend[0]["date"], yesterday)
        self.assertEqual(trend[0]["visits"], 2)
        self.assertEqual(trend[0]["unique_visitors"], 2)
        self.assertEqual(trend[1]["visits"], 1)

    def test_top_pages_ordering_and_percentage(self):
        for _ in range(3):
            self._make_visit(page_key="core:home")
        self._make_visit(page_key="core:about")
        today = timezone.localdate()
        pages = services.top_pages(self.association, today, today)
        self.assertEqual(pages[0]["page_key"], "core:home")
        self.assertEqual(pages[0]["visits"], 3)
        self.assertEqual(pages[0]["percentage"], 75.0)
        self.assertEqual(pages[0]["label"], "Home")
        self.assertEqual(pages[1]["percentage"], 25.0)

    def test_page_label_fallback_for_unmapped_key(self):
        self.assertEqual(services.page_label("elections:vote_success"), "Vote Success")

    def test_device_breakdown_counts_and_percentages(self):
        self._make_visit(device_category=PageVisit.DeviceCategory.MOBILE)
        self._make_visit(device_category=PageVisit.DeviceCategory.MOBILE)
        self._make_visit(device_category=PageVisit.DeviceCategory.DESKTOP)
        today = timezone.localdate()
        rows = {row["category"]: row for row in services.device_breakdown(self.association, today, today)}
        self.assertEqual(rows["mobile"]["count"], 2)
        self.assertEqual(rows["desktop"]["count"], 1)
        self.assertAlmostEqual(rows["mobile"]["percentage"], 66.7, places=1)

    def test_browser_breakdown(self):
        self._make_visit(browser_category=PageVisit.BrowserCategory.FIREFOX)
        self._make_visit(browser_category=PageVisit.BrowserCategory.CHROME)
        today = timezone.localdate()
        rows = {row["category"]: row for row in services.browser_breakdown(self.association, today, today)}
        self.assertEqual(rows["firefox"]["count"], 1)
        self.assertEqual(rows["chrome"]["count"], 1)

    def test_referrer_breakdown(self):
        self._make_visit(referrer_category=PageVisit.ReferrerCategory.SEARCH)
        self._make_visit(referrer_category=PageVisit.ReferrerCategory.DIRECT)
        self._make_visit(referrer_category=PageVisit.ReferrerCategory.DIRECT)
        today = timezone.localdate()
        rows = {row["category"]: row for row in services.referrer_breakdown(self.association, today, today)}
        self.assertEqual(rows["direct"]["count"], 2)
        self.assertEqual(rows["search"]["count"], 1)

    def test_resolve_date_range_today(self):
        today = datetime.date(2026, 8, 8)
        start, end = services.resolve_date_range("today", today=today)
        self.assertEqual((start, end), (today, today))

    def test_resolve_date_range_7d(self):
        today = datetime.date(2026, 8, 8)
        start, end = services.resolve_date_range("7d", today=today)
        self.assertEqual(start, today - datetime.timedelta(days=6))
        self.assertEqual(end, today)

    def test_resolve_date_range_custom(self):
        start_in = datetime.date(2026, 1, 1)
        end_in = datetime.date(2026, 1, 10)
        start, end = services.resolve_date_range("custom", start=start_in, end=end_in)
        self.assertEqual((start, end), (start_in, end_in))

    def test_resolve_date_range_falls_back_for_unknown_key(self):
        today = datetime.date(2026, 8, 8)
        start, end = services.resolve_date_range("nonsense", today=today)
        self.assertEqual(start, today - datetime.timedelta(days=29))


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------
class PermissionTests(VisitorAnalyticsTestCase):
    def test_anonymous_redirected_to_admin_login(self):
        response = self.client.get(reverse("analytics:visitor_analytics_dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_plain_staff_gets_403(self):
        self._login_as_plain_staff()
        response = self.client.get(reverse("analytics:visitor_analytics_dashboard"))
        self.assertEqual(response.status_code, 403)

    def test_analytics_admin_can_access_dashboard(self):
        self._login_as_analytics_admin()
        response = self.client.get(reverse("analytics:visitor_analytics_dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_superuser_can_access_without_group(self):
        User.objects.create_superuser(username="root", email="root@example.com", password="x")
        self.client.login(username="root", password="x")
        response = self.client.get(reverse("analytics:visitor_analytics_dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_json_api_gated_the_same_way(self):
        response = self.client.get(reverse("analytics:api_visitor_analytics"))
        self.assertEqual(response.status_code, 302)
        self._login_as_analytics_admin()
        response = self.client.get(reverse("analytics:api_visitor_analytics"))
        self.assertEqual(response.status_code, 200)

    def test_setup_roles_grants_visitor_analytics_to_analytics_admin(self):
        group = Group.objects.get(name="Analytics Admin")
        self.assertTrue(group.permissions.filter(codename="view_visitor_analytics").exists())

    def test_setup_roles_grants_visitor_analytics_to_super_admin(self):
        group = Group.objects.get(name="Super Admin")
        self.assertTrue(group.permissions.filter(codename="view_visitor_analytics").exists())

    def test_election_admin_does_not_get_visitor_analytics(self):
        group = Group.objects.get(name="Election Admin")
        self.assertFalse(group.permissions.filter(codename="view_visitor_analytics").exists())


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------
class PerformanceTests(VisitorAnalyticsTestCase):
    def test_dashboard_query_count_does_not_scale_with_row_count(self):
        self._login_as_analytics_admin()

        for i in range(50):
            self._make_visit(visitor_hash=f"hash-{i}", page_key="core:home" if i % 2 else "core:about")
        with CaptureQueriesContext(connection) as small_run:
            response = self.client.get(reverse("analytics:visitor_analytics_dashboard"))
        self.assertEqual(response.status_code, 200)
        small_count = len(small_run.captured_queries)

        for i in range(50, 550):
            self._make_visit(visitor_hash=f"hash-{i}", page_key="core:home" if i % 2 else "core:about")
        with CaptureQueriesContext(connection) as large_run:
            response = self.client.get(reverse("analytics:visitor_analytics_dashboard"))
        self.assertEqual(response.status_code, 200)
        large_count = len(large_run.captured_queries)

        # The whole point of the aggregation-only design: 500 more rows
        # must not mean more queries (no N+1 across pages/devices/etc.).
        self.assertEqual(small_count, large_count)
        self.assertLess(large_count, 20)

    def test_tracking_a_single_request_is_a_single_insert(self):
        with CaptureQueriesContext(connection) as captured:
            self.client.get(reverse("core:home"))
        insert_queries = [q for q in captured.captured_queries if "INSERT" in q["sql"].upper()]
        self.assertEqual(len(insert_queries), 1)


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------
class RetentionTests(VisitorAnalyticsTestCase):
    def test_cleanup_deletes_only_rows_older_than_retention(self):
        today = timezone.localdate()
        old = today - datetime.timedelta(days=100)
        recent = today - datetime.timedelta(days=10)
        self._make_visit(visit_date=old, visitor_hash="old")
        self._make_visit(visit_date=recent, visitor_hash="recent")

        deleted = services.cleanup_visitor_analytics(retention_days=90, today=today)

        self.assertEqual(deleted, 1)
        self.assertEqual(PageVisit.objects.count(), 1)
        self.assertEqual(PageVisit.objects.get().visitor_hash, "recent")

    def test_cleanup_management_command_deletes(self):
        old = timezone.localdate() - datetime.timedelta(days=200)
        self._make_visit(visit_date=old, visitor_hash="old")
        call_command("cleanup_visitor_analytics", days=90, verbosity=0)
        self.assertEqual(PageVisit.objects.count(), 0)

    def test_cleanup_management_command_dry_run_deletes_nothing(self):
        old = timezone.localdate() - datetime.timedelta(days=200)
        self._make_visit(visit_date=old, visitor_hash="old")
        call_command("cleanup_visitor_analytics", days=90, dry_run=True, verbosity=0)
        self.assertEqual(PageVisit.objects.count(), 1)

    def test_cleanup_respects_default_settings_retention(self):
        old = timezone.localdate() - datetime.timedelta(days=100)
        recent = timezone.localdate() - datetime.timedelta(days=5)
        self._make_visit(visit_date=old, visitor_hash="old")
        self._make_visit(visit_date=recent, visitor_hash="recent")
        call_command("cleanup_visitor_analytics", verbosity=0)  # uses VISITOR_ANALYTICS_RETENTION_DAYS=90
        self.assertEqual(PageVisit.objects.count(), 1)
