"""
The first views/URLs apps.core has ever had. Everything here is public —
no login required — and reads other apps' data as a consumer, the same
discipline apps.analytics already follows: no new methods were added to
Election/Member for this, only to core's own views.
"""
from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render

from apps.analytics import services as analytics_services
from apps.elections.models import Election

from .forms import ContactForm
from .models import Association


def _default_association():
    return Association.objects.filter(slug=settings.DEFAULT_ASSOCIATION_SLUG).select_related("site_settings").first()


def _elections_by_status(association):
    """
    Partitions this association's elections into Upcoming / Active /
    Recently Completed using Election's own existing is_upcoming()/
    is_active()/is_closed() methods (built in the election module) —
    nothing new is added to Election for this; it's just grouped here.
    """
    elections = list(Election.objects.filter(association=association))
    return {
        "upcoming": sorted([e for e in elections if e.is_upcoming()], key=lambda e: e.start_datetime),
        "active": sorted([e for e in elections if e.is_active()], key=lambda e: e.end_datetime),
        "recently_completed": sorted(
            [e for e in elections if e.is_closed()], key=lambda e: e.end_datetime, reverse=True
        )[:3],
    }


def home_view(request):
    """
    The landing page. Every piece of dynamic content here is read from
    data that already exists elsewhere in the project — membership
    counts via apps.analytics.services (the same functions the staff
    dashboards call), elections via Election's own is_upcoming()/
    is_active()/is_closed()/results_by_position()/voters_count() methods
    (built in the election module, untouched here), and Site Settings
    content fields. The one addition below (`contact_form`) is an
    *unbound* form instance for rendering the landing page's embedded
    mini contact section (Section 8) — it changes nothing about how a
    submission is processed: that form posts straight to `core:contact`,
    handled entirely by the existing, unmodified `contact_view` below.
    """
    association = _default_association()
    context = {
        "association": association,
        "site_settings": None,
        "membership": None,
        "elections": None,
        "contact_form": ContactForm(),
    }
    if association is not None:
        context["site_settings"] = getattr(association, "site_settings", None)
        context["membership"] = analytics_services.membership_overview(association)
        context["elections"] = _elections_by_status(association)
    return render(request, "core/home.html", context)


def about_view(request):
    association = _default_association()
    site_settings = getattr(association, "site_settings", None) if association else None
    return render(request, "core/about.html", {"association": association, "site_settings": site_settings})


def contact_view(request):
    association = _default_association()
    site_settings = getattr(association, "site_settings", None) if association else None

    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid() and association is not None:
            inquiry = form.save(commit=False)
            inquiry.association = association
            inquiry.save()
            messages.success(request, "Your message has been sent. Thank you for reaching out — we'll get back to you soon.")
            return redirect("core:contact")
    else:
        form = ContactForm()

    return render(
        request,
        "core/contact.html",
        {"association": association, "site_settings": site_settings, "form": form},
    )
