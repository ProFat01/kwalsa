from django.urls import path

from . import views

app_name = "members"

urlpatterns = [
    path("register/", views.register_view, name="register"),
    path(
        "register/success/<str:application_number>/",
        views.registration_success_view,
        name="registration_success",
    ),
    path("status/", views.status_check_view, name="status_check"),
    path("portal/login/", views.portal_login_view, name="portal_login"),
    path("portal/", views.portal_dashboard_view, name="portal_dashboard"),
    path("portal/profile/", views.portal_profile_view, name="portal_profile"),
    path("portal/card/", views.portal_card_view, name="portal_card"),
    path("portal/card/qr/", views.portal_card_qr_view, name="portal_card_qr"),
    path("portal/logout/", views.portal_logout_view, name="portal_logout"),
    path("verify/<uuid:card_uuid>/", views.verify_member_view, name="verify_member"),
    path("<int:pk>/card/", views.staff_card_view, name="staff_card"),
    path("<int:pk>/card/qr/", views.staff_card_qr_view, name="staff_card_qr"),
    # v1.2 Feature 2 & 3: staff Members list + quick actions
    path("staff/list/", views.staff_member_list_view, name="staff_list"),
]
