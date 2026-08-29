from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Announcement, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """
    Extends Django's battle-tested UserAdmin (password hashing widget,
    permission/group management UI, etc.) rather than rebuilding it, and
    only adds what's actually new on this model: `association` (tenant
    scoping) and `phone_number`.
    """

    fieldsets = DjangoUserAdmin.fieldsets + (
        ("SAMS", {"fields": ("association", "phone_number")}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("SAMS", {"fields": ("association", "phone_number")}),
    )
    list_display = DjangoUserAdmin.list_display + ("association", "role_list")
    list_filter = DjangoUserAdmin.list_filter + ("association", "groups")
    autocomplete_fields = ("association",)

    @admin.display(description="Roles")
    def role_list(self, obj):
        return ", ".join(obj.role_names) or "—"


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    """
    Read-only audit trail in the admin, same pattern already used for
    SequenceCounter/MembershipSnapshot/AgeDistributionSnapshot
    (ARCHITECTURE.md §6: "generated tables are view-only in the admin").
    Announcements are only ever created through the Communication Center's
    send flow, which is what actually dispatches the emails — creating or
    editing one here would produce a row that claims to have been sent
    without anything having sent it.
    """

    list_display = (
        "subject",
        "association",
        "recipient_type",
        "delivery_method",
        "status",
        "recipient_count",
        "sent_count",
        "failed_count",
        "created_by",
        "created_at",
    )
    list_filter = ("association", "recipient_type", "delivery_method", "status")
    search_fields = ("subject", "message")
    readonly_fields = [f.name for f in Announcement._meta.fields]
    list_select_related = ("association", "created_by")
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
