from django.urls import path

from . import views

app_name = "elections"

urlpatterns = [
    path("", views.election_list_view, name="election_list"),
    path("<int:pk>/", views.election_detail_view, name="election_detail"),
    path("<int:pk>/login/", views.voting_login_view, name="voting_login"),
    path("<int:pk>/vote/", views.ballot_view, name="ballot"),
    path("<int:pk>/vote/success/", views.vote_success_view, name="vote_success"),
    path("<int:pk>/results/", views.results_view, name="results"),
    path("<int:pk>/dashboard/", views.admin_dashboard_view, name="admin_dashboard"),
]
