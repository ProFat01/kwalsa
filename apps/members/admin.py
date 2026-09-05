from django.contrib import admin
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from apps.core.admin_badges import status_badge

from .models import AlumniRecord, Member, MembershipCard, RegistrationApplication

# Version 1.2 "Admin Experience" polish: display-only badge colour maps.
# Purely cosmetic -- the underlying choice values/workflow are unchanged.
_MEMBER_STATUS_VARIANT = {
    Member.ApprovalStatus.APPROVED: "success",
    Member.ApprovalStatus.PENDING: "warning",
    Member.ApprovalStatus.REJECTED: "error",
}
_APPLICATION_STATUS_VARIANT = {
    RegistrationApplication.Status.APPROVED: "success",
    RegistrationApplication.Status.PENDING: "warning",
    RegistrationApplication.Status.REJECTED: "error",
}


class RegistrationApplicationInline(admin.TabularInline):
    """Read-mostly history of every application this member has ever filed."""

    model = RegistrationApplication
    extra = 0
    fields = ("application_number", "status", "submitted_at", "reviewed_at", "reviewed_by")
    readonly_fields = fields
    can_delete = False
    show_change_link = True


class AlumniRecordInline(admin.StackedInline):
    model = AlumniRecord
    extra = 0
    max_num = 1
    readonly_fields = ("converted_at",)
    autocomplete_fields = ("converted_by",)


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "membership_id",
        "association",
        "category",
        "approval_status_badge",
        "alumni_status",
        "voting_status",
        "registration_date",
    )
    list_filter = ("association", "approval_status", "category", "alumni_status", "voting_status")
    search_fields = ("full_name", "phone_number", "nin_number", "membership_id", "email")
    readonly_fields = ("membership_id", "registration_date", "voting_status", "card_link")
    autocomplete_fields = ("association", "user")
    date_hierarchy = "registration_date"
    inlines = [RegistrationApplicationInline, AlumniRecordInline]
    actions = ["convert_selected_to_alumni"]

    # Member is read frequently with its association joined (list_display,
    # filters) — select_related avoids one extra query per row, the same
    # ORM-optimisation discipline used throughout the project.
    list_select_related = ("association",)

    # Section names/order match the v1.2 admin-experience brief's
    # "Application Detail Page" grouping (Personal / Identity Verification /
    # Academic / Registration Status / Membership Details). Field lists
    # are byte-for-byte unchanged from before this task -- only the
    # fieldset titles moved, so admin.css's per-section icon selectors
    # (keyed to this exact order) line up correctly.
    fieldsets = (
        (
            "Personal Information",
            {"fields": ("association", "user", "full_name", "date_of_birth", "gender", "email", "passport_photo")},
        ),
        ("Identity Verification", {"fields": ("phone_number", "nin_number")}),
        ("Academic Information", {"fields": ("institution", "course", "faculty", "department", "level", "category")}),
        (
            "Registration Status",
            {"fields": ("approval_status", "membership_id", "voting_status", "alumni_status", "registration_date")},
        ),
        ("Membership Details", {"fields": ("card_link",)}),
    )

    @admin.display(description="Status", ordering="approval_status")
    def approval_status_badge(self, obj):
        return status_badge(obj.get_approval_status_display(), _MEMBER_STATUS_VARIANT.get(obj.approval_status))

    @admin.display(description="Membership card")
    def card_link(self, obj):
        if not obj.pk:
            return "Save the member first."
        url = reverse("members:staff_card", args=[obj.pk])
        return format_html('<a class="button" href="{}" target="_blank">View / Print Card</a>', url)

    @admin.action(description="Convert selected members to alumni")
    def convert_selected_to_alumni(self, request, queryset):
        updated = 0
        for member in queryset:
            member.convert_to_alumni(converted_by=request.user)
            updated += 1
        self.message_user(request, f"{updated} member(s) converted to alumni.")


@admin.register(RegistrationApplication)
class RegistrationApplicationAdmin(admin.ModelAdmin):
    list_display = (
        "application_number", "member", "application_status_badge", "submitted_at", "reviewed_at", "reviewed_by",
    )
    list_filter = ("status", "member__association")
    search_fields = ("application_number", "member__full_name", "member__phone_number")
    autocomplete_fields = ("member",)
    readonly_fields = (
        "application_number", "submitted_at", "reviewed_at", "reviewed_by",
        "receipt_preview", "indigene_image_preview",
    )
    list_select_related = ("member", "member__association", "reviewed_by")
    actions = ["approve_applications", "clear_receipt_images"]

    # Section names/order match the v1.2 brief's "Application Detail
    # Page" grouping (Application Details / Payment Information /
    # Registration Status), plus an "Indigene Verification" section for
    # the staff-only verification image. Fields inside the pre-existing
    # sections are unchanged.
    fieldsets = (
        ("Application Details", {"fields": ("application_number", "member", "submitted_at")}),
        # PART 5: receipt is shown here for review. PART 6: it's only
        # visible while a decision is still Pending — the receipt file is
        # deleted automatically the moment status leaves Pending (see
        # members/signals.py), so this preview naturally disappears once
        # a decision has been made.
        ("Payment Information", {"fields": ("receipt_image", "receipt_preview")}),
        # Staff-only, not publicly exposed anywhere else. Visible for as
        # long as the application is pending; deleted automatically (see
        # RegistrationApplication.clear_indigene_image()) the moment this
        # application is *approved* — a rejection leaves it in place, so
        # this preview only disappears after approval, unlike the receipt
        # above which disappears after either decision.
        ("Indigene Verification", {"fields": ("indigene_image", "indigene_image_preview")}),
        ("Registration Status", {"fields": ("status", "rejection_reason", "reviewed_at", "reviewed_by")}),
    )

    @admin.display(description="Status", ordering="status")
    def application_status_badge(self, obj):
        return status_badge(obj.get_status_display(), _APPLICATION_STATUS_VARIANT.get(obj.status))

    @admin.display(description="Receipt preview")
    def receipt_preview(self, obj):
        if not obj.receipt_image:
            return "— (no receipt on file; already cleared if this application has been reviewed)"
        return format_html(
            '<a href="{0}" target="_blank" rel="noopener">'
            '<img src="{0}" style="max-height: 220px; max-width: 100%; border: 1px solid #ddd; border-radius: 4px;">'
            "</a>",
            obj.receipt_image.url,
        )

    @admin.display(description="Indigene verification image")
    def indigene_image_preview(self, obj):
        if not obj.indigene_image:
            return "— (no image on file; already cleared if this application has been approved)"
        return format_html(
            '<a href="{0}" target="_blank" rel="noopener">'
            '<img src="{0}" style="max-height: 220px; max-width: 100%; border: 1px solid #ddd; border-radius: 4px;">'
            "</a>",
            obj.indigene_image.url,
        )

    def save_model(self, request, obj, form, change):
        # reviewed_by is set here (server-side, from the logged-in admin)
        # rather than exposed as an editable field, so it can't be
        # mis-attributed to the wrong reviewer through the form.
        if change and "status" in form.changed_data and obj.status != RegistrationApplication.Status.PENDING:
            obj.reviewed_by = request.user
        super().save_model(request, obj, form, change)

    @admin.action(description="Approve selected applications")
    def approve_applications(self, request, queryset):
        # Bulk action intentionally covers approval only: rejection
        # requires a rejection_reason (enforced in Model.clean()), which
        # only makes sense to capture per-application through the form.
        count = 0
        for application in queryset.filter(status=RegistrationApplication.Status.PENDING):
            application.status = RegistrationApplication.Status.APPROVED
            application.reviewed_by = request.user
            application.save()
            count += 1
        self.message_user(request, f"{count} application(s) approved.")

    @admin.action(description="Delete receipt images (manual fallback)")
    def clear_receipt_images(self, request, queryset):
        """
        Receipt deletion now happens automatically the instant a review
        decision is recorded (members/signals.py::_sync_member_on_review,
        PART 6 of the registration module spec) — this action exists only
        as a manual fallback (e.g. a receipt that somehow survived an
        out-of-band status change) and will typically find nothing left
        to clear.
        """
        count = 0
        for application in queryset.exclude(status=RegistrationApplication.Status.PENDING):
            if application.receipt_image:
                application.clear_receipt()
                count += 1
        self.message_user(request, f"Receipt image cleared for {count} application(s).")


@admin.register(AlumniRecord)
class AlumniRecordAdmin(admin.ModelAdmin):
    list_display = ("member", "graduation_year", "current_employer", "converted_at")
    list_filter = ("graduation_year",)
    search_fields = ("member__full_name", "current_employer")
    autocomplete_fields = ("member", "converted_by")
    list_select_related = ("member",)
