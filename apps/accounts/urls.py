from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("", views.dashboard_view, name="dashboard"),
    # v1.2 Feature 4-7: Communication Center
    path("communications/", views.communication_center_view, name="communication_center"),
    path("communications/compose/", views.communication_compose_view, name="communication_compose"),
    path("communications/history/", views.communication_history_view, name="communication_history"),
    path("communications/history/<int:pk>/", views.communication_detail_view, name="communication_detail"),
]
