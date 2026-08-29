from django.contrib import admin

from . import services
from .models import AgeDistributionSnapshot, ElectionResultSnapshot, MembershipSnapshot, PageVisit


class GeneratedSnapshotAdminMixin:
    """
    Shared "this table is written by a management command/signal, not by
    hand" admin behaviour: visible and filterable, but not creatable
    through the admin UI, so nobody accidentally hand-enters a snapshot
    that then silently disagrees with the real underlying data.
    """

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(MembershipSnapshot)
class MembershipSnapshotAdmin(GeneratedSnapshotAdminMixin, admin.ModelAdmin):
    list_display = (
        "association", "snapshot_date", "total_members", "total_approved",
        "total_pending", "total_rejected", "total_alumni",
    )
    list_filter = ("association",)
    date_hierarchy = "snapshot_date"
    list_select_related = ("association",)
    actions = ["regenerate_for_today"]

    @admin.action(
        description="Regenerate today's snapshot (membership + age) for the selected row(s)' association",
        permissions=["view"],  # has_change_permission is False here; default action gating requires
                               # change permission, which would hide this action from exactly the
                               # Analytics Admin/Super Admin users who are supposed to be able to use it
    )
    def regenerate_for_today(self, request, queryset):
        associations = {snapshot.association for snapshot in queryset}
        for association in associations:
            services.generate_membership_snapshot(association)
            services.generate_age_distribution_snapshot(association)
        self.message_user(request, f"Regenerated today's snapshot for {len(associations)} association(s).")


@admin.register(AgeDistributionSnapshot)
class AgeDistributionSnapshotAdmin(GeneratedSnapshotAdminMixin, admin.ModelAdmin):
    list_display = ("association", "snapshot_date", "age_bracket", "count")
    list_filter = ("association", "age_bracket")
    date_hierarchy = "snapshot_date"
    list_select_related = ("association",)


@admin.register(ElectionResultSnapshot)
class ElectionResultSnapshotAdmin(admin.ModelAdmin):
    """
    Unlike the two snapshots above, this one IS editable in the admin —
    but only for the publish workflow (is_published, winner_candidate).
    The vote-derived numbers stay readonly because they should only ever
    come from the aggregation that generates this row in the first place.
    """

    list_display = (
        "election", "position", "total_votes_cast", "total_eligible_voters",
        "turnout_percentage", "winner_candidate", "is_published",
    )
    list_filter = ("is_published", "election__association", "position")
    autocomplete_fields = ("election", "position", "winner_candidate")
    readonly_fields = ("total_votes_cast", "total_eligible_voters", "turnout_percentage", "generated_at")
    list_select_related = ("election", "position", "winner_candidate")
    actions = ["refresh_vote_counts"]

    def has_add_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        if "is_published" in form.changed_data and obj.is_published:
            obj.published_by = request.user
        super().save_model(request, obj, form, change)

    @admin.action(
        description="Refresh vote counts/winner for the selected row(s)' election",
        permissions=["view"],  # so Analytics Admins (view-only on this model) can trigger a refresh too
    )
    def refresh_vote_counts(self, request, queryset):
        elections = {snapshot.election for snapshot in queryset}
        for election in elections:
            services.generate_election_result_snapshots(election)
        self.message_user(request, f"Refreshed results for {len(elections)} election(s).")


@admin.register(PageVisit)
class PageVisitAdmin(admin.ModelAdmin):
    """
    Read-only in the admin — rows are written exclusively by
    VisitorTrackingMiddleware, and hand-editing/creating a visit record
    would just corrupt the aggregates. Kept registered purely so staff
    with the right permission can spot-check raw rows during
    troubleshooting; day-to-day use is the Visitor Analytics dashboard.
    """

    list_display = ("visit_date", "page_key", "association", "visitor_type", "device_category", "browser_category", "referrer_category")
    list_filter = ("visit_date", "visitor_type", "device_category", "browser_category", "referrer_category", "association")
    date_hierarchy = "visit_date"
    list_select_related = ("association",)
    search_fields = ("page_key", "path")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
