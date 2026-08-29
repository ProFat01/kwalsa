"""
Root URLConf. Every app now has real views/templates: `core` is the
public website (landing/about/contact), `members` is registration,
`elections` is voting, `analytics` is the staff dashboards, and
`accounts` is the role-adaptive dashboard hub (login required, no
public views).
"""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.core.urls", namespace="core")),
    path("dashboard/", include("apps.accounts.urls", namespace="accounts")),
    path("members/", include("apps.members.urls", namespace="members")),
    path("elections/", include("apps.elections.urls", namespace="elections")),
    path("analytics/", include("apps.analytics.urls", namespace="analytics")),
]

if settings.DEBUG:
    from django.conf.urls.static import static

    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
