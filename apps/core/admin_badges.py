"""
Shared admin-only presentation helper for Version 1.2's "SaaS dashboard"
admin polish pass.

This module renders nothing but a `<span>` with a CSS class — it has no
opinion on *when* something counts as approved/pending/rejected, that
decision is still made entirely by each admin.py's own field value. This
file only turns a value Django already computed into a colour-coded pill
instead of plain text, matching the badge styling in static/css/admin.css.

Deliberately its own tiny module (rather than duplicated `format_html`
calls in members/elections/core admin.py) so the four admin.py files
that use it don't each reinvent the same markup, and so the visual
vocabulary (which variant = which colour) stays in exactly one place.
"""
from django.utils.html import format_html

# variant -> CSS class suffix consumed by static/css/admin.css
# (.sams-badge--success / --warning / --error / --neutral / --info)
_VARIANTS = {"success", "warning", "error", "neutral", "info"}


def status_badge(label, variant="neutral"):
    """
    Returns a safe HTML span for use inside an @admin.display method,
    e.g.:

        @admin.display(description="Status")
        def status_badge_display(self, obj):
            return status_badge(obj.get_status_display(), STATUS_VARIANTS[obj.status])

    `label` is escaped by format_html automatically. Falls back to
    "neutral" for any variant not in _VARIANTS, so a typo styles as a
    plain grey pill instead of silently rendering unstyled/broken markup.
    """
    if variant not in _VARIANTS:
        variant = "neutral"
    return format_html('<span class="sams-badge sams-badge--{}">{}</span>', variant, label)
