from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home_view, name="home"),
    path("about/", views.about_view, name="about"),
    path("leadership/", views.leadership_view, name="leadership"),
    path("contact/", views.contact_view, name="contact"),
]
