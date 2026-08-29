"""
Small template-filter home for apps.core.

`split_lines` exists for one reason: SiteSettings.aims/objectives are
stored as plain newline-separated text (simplest possible admin editing
experience — one line per aim/objective, no nested formset), and the
About page renders each as a <li>. Django ships no built-in filter for
"split this on newlines", so this is the minimal custom filter needed
to turn that stored text into a bulleted list without a JS/markdown
dependency for what is otherwise a one-line problem.
"""
from django import template

register = template.Library()


@register.filter
def split_lines(value):
    """Return a list of non-empty, stripped lines from a text field."""
    if not value:
        return []
    return [line.strip() for line in value.splitlines() if line.strip()]
