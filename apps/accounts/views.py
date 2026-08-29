"""
A single dashboard hub at /dashboard/, rather than four separate
ad-hoc pages. Each section below is gated by a permission that already
exists (declared in apps/accounts/permissions.py, attached to groups by
setup_roles) — nothing new was added to the permission architecture for
this. Sections render purely based on `request.user.has_perm(...)`, so:

  - Registration Admin sees only the Registration section
  - Election Admin sees only the Elections section
  - Analytics Admin sees only the Analytics section
  - Super Admin (and any Django superuser, who implicitly passes every
    has_perm check) sees all four sections

No data is recomputed here that already exists elsewhere — this hub
calls into apps.analytics.services (the same functions the analytics
dashboards themselves use) and links out to the existing admin
changelists / per-election dashboard rather than re-implementing any of
them.
"""
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from apps.analytics import services as analytics_services
from apps.core.models import Association, ContactMessage
from apps.members.models import RegistrationApplication
from apps.members.services import resolve_announcement_recipients

from .forms import AnnouncementComposeForm
from .models import Announcement
from .notifications import PROVIDERS, send_announcement


def _default_association():
    return Association.objects.filter(slug=settings.DEFAULT_ASSOCIATION_SLUG).first()


@login_required
def dashboard_view(request):
    user = request.user
    association = _default_association()

    sections = {
        # Gated on review_application (not the broader view_member) so
        # this card maps to "can actually process applications", which is
        # what Registration Admin is *for* — not just read access.
        "registration": user.has_perm("members.review_application"),
        # Gated on manage_election (not view_election/view_vote, which
        # Analytics Admin also holds) so this card is specifically
        # Election Admin's management view, not duplicated into
        # Analytics Admin's screen where richer election analytics
        # already exist.
        "elections": user.has_perm("elections.manage_election"),
        "analytics": user.has_perm("analytics.view_analytics_dashboard"),
        "contact": user.has_perm("core.view_contactmessage"),
    }

    context = {"sections": sections, "association": association}

    if association is not None:
        if sections["registration"]:
            context["membership"] = analytics_services.membership_overview(association)
            context["pending_applications"] = (
                RegistrationApplication.objects.filter(status=RegistrationApplication.Status.PENDING)
                .select_related("member")
                .order_by("-submitted_at")[:5]
            )

        if sections["elections"]:
            overviews = analytics_services.all_elections_overview(association)
            context["election_overviews"] = overviews
            context["active_election_overviews"] = [o for o in overviews if o["election"].status == "active"]

        if sections["analytics"]:
            context["analytics_summary"] = analytics_services.membership_overview(association)

        if sections["contact"]:
            context["unread_contact_count"] = ContactMessage.objects.filter(
                association=association, is_read=False
            ).count()
            context["recent_contact_messages"] = ContactMessage.objects.filter(association=association)[:5]

    return render(request, "accounts/dashboard.html", context)


# ---------------------------------------------------------------------------
# v1.2 Feature 4-10: Communication Center.
#
# Gated on the new `accounts.send_announcement` permission (Feature 10:
# "Only authorized administrators may access Communication Center"),
# granted only to Super Admin in permissions.py — a brand-new capability
# gets its own narrow permission rather than being folded into an existing
# one, exactly the pattern every other module in this project already
# follows for a genuinely new authority (see ELECTION_MODULE.md's
# manage_election/publish_results, or members.review_application).
# ---------------------------------------------------------------------------
def _communication_center_required(view_func):
    @wraps(view_func)
    @login_required
    @permission_required("accounts.send_announcement", raise_exception=True)
    def wrapped(request, *args, **kwargs):
        return view_func(request, *args, **kwargs)

    return wrapped


@_communication_center_required
def communication_center_view(request):
    """Landing page: provider status (Feature 8) + a short recent-history list, with links into compose/history."""
    association = _default_association()
    recent = (
        Announcement.objects.filter(association=association).select_related("created_by")[:5]
        if association
        else []
    )
    context = {
        "association": association,
        "providers": PROVIDERS.values(),
        "recent_announcements": recent,
    }
    return render(request, "accounts/communication_center.html", context)


@_communication_center_required
def communication_compose_view(request):
    """
    Feature 5 & 6: compose + target + preview + send, all one form/view.
    GET may arrive pre-filled from the staff Members list ("Send
    Announcement to Selected" / a single member's "Send Email" quick
    action) via ?recipient_type=selected&selected_member_ids=1,2,3.
    """
    association = _default_association()
    preview = None

    if request.method == "POST":
        form = AnnouncementComposeForm(request.POST)
        action = request.POST.get("action", "preview")

        if form.is_valid() and association is not None:
            recipients = resolve_announcement_recipients(
                association,
                form.cleaned_data["recipient_type"],
                form.filters(),
                form.selected_ids(),
            )

            if action == "send":
                announcement = Announcement.objects.create(
                    association=association,
                    subject=form.cleaned_data["subject"],
                    message=form.cleaned_data["message"],
                    created_by=request.user,
                    recipient_type=form.cleaned_data["recipient_type"],
                    recipient_filters={**form.filters(), "selected_member_ids": form.selected_ids()},
                    delivery_method=form.cleaned_data["delivery_method"],
                    recipient_count=recipients.count(),
                )
                send_announcement(announcement, recipients)
                messages.success(
                    request,
                    f"Announcement \"{announcement.subject}\" sent to "
                    f"{announcement.sent_count} of {announcement.recipient_count} recipient(s).",
                )
                return redirect("accounts:communication_detail", pk=announcement.pk)

            # action == "preview" (or anything else): show the count without saving/sending
            preview = {"count": recipients.count(), "sample": list(recipients[:5])}
    else:
        initial = {
            "recipient_type": request.GET.get("recipient_type", Announcement.RecipientType.ALL),
            "selected_member_ids": request.GET.get("selected_member_ids", ""),
            "faculty": request.GET.get("faculty", ""),
            "department": request.GET.get("department", ""),
            "level": request.GET.get("level", ""),
            "gender": request.GET.get("gender", ""),
            "approval_status": request.GET.get("approval_status", ""),
        }
        # Support the bulk "Send Announcement to Selected" form, which
        # submits one selected_member_ids value per checked row.
        bulk_ids = request.GET.getlist("selected_member_ids")
        if len(bulk_ids) > 1:
            initial["selected_member_ids"] = ",".join(bulk_ids)
        form = AnnouncementComposeForm(initial=initial)

    context = {
        "association": association,
        "form": form,
        "preview": preview,
        "recipient_types": Announcement.RecipientType.choices,
    }
    return render(request, "accounts/communication_compose.html", context)


@_communication_center_required
def communication_history_view(request):
    """Feature 7: every announcement ever attempted, newest first."""
    association = _default_association()
    qs = (
        Announcement.objects.filter(association=association).select_related("created_by")
        if association
        else Announcement.objects.none()
    )
    paginator = Paginator(qs, 25)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "accounts/communication_history.html", {"association": association, "announcements": page})


@_communication_center_required
def communication_detail_view(request, pk):
    announcement = get_object_or_404(Announcement.objects.select_related("created_by", "association"), pk=pk)
    return render(request, "accounts/communication_detail.html", {"announcement": announcement})
