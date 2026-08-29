"""
Single source of truth for "what can each role do".

Format: {role_name: ["app_label.codename", ...]}. Using Django's built-in
Permission objects (default add/change/delete/view per model, plus the
custom ones declared in each model's Meta.permissions) instead of a
hand-rolled permissions system means:

  - every ModelAdmin's has_*_permission already understands these for free
  - `user.has_perm(...)` works everywhere, including any future API/views
  - Django's own permission UI (on the Group admin) stays usable for
    fine-tuning without code changes

This module only *declares* the mapping; `setup_roles` (the management
command in management/commands/setup_roles.py) is what actually creates
the Groups and attaches these permissions, and is meant to be re-run
after any change here.

Note: `auth.Group` and `auth.Permission` themselves are deliberately left
out of every role below, including Super Admin. Granting change
permission on Group/Permission to a non-superuser account would let that
account add itself (or anyone) to a more privileged group — i.e. a
privilege-escalation path. Day-to-day "Super Admin" work should be done
through a Django superuser account; the Super Admin *group* exists for
staff who need broad app access without being a true superuser (no
access to Django's own user/permission machinery).
"""
from .models import (
    ROLE_ANALYTICS_ADMIN,
    ROLE_ELECTION_ADMIN,
    ROLE_REGISTRATION_ADMIN,
    ROLE_SUPER_ADMIN,
)

ROLE_PERMISSIONS = {
    ROLE_SUPER_ADMIN: [
        # core
        "core.view_association", "core.change_association", "core.add_association",
        "core.view_sitesettings", "core.change_sitesettings",
        "core.view_contactmessage", "core.change_contactmessage", "core.delete_contactmessage",
        # members
        "members.view_member", "members.add_member", "members.change_member", "members.delete_member",
        "members.approve_member", "members.manage_alumni_status",
        "members.view_registrationapplication", "members.change_registrationapplication",
        "members.review_application",
        "members.view_alumnirecord", "members.add_alumnirecord", "members.change_alumnirecord",
        # elections
        "elections.view_position", "elections.add_position", "elections.change_position", "elections.delete_position",
        "elections.view_election", "elections.add_election", "elections.change_election", "elections.delete_election",
        "elections.manage_election", "elections.publish_results",
        "elections.view_candidate", "elections.add_candidate", "elections.change_candidate", "elections.delete_candidate",
        "elections.view_vote",
        # analytics
        "analytics.view_membershipsnapshot", "analytics.view_agedistributionsnapshot",
        "analytics.view_electionresultsnapshot", "analytics.change_electionresultsnapshot",
        "analytics.view_analytics_dashboard",
        # v2.1: Visitor & Usage Analytics
        "analytics.view_pagevisit", "analytics.view_visitor_analytics",
        # accounts — v1.2 Communication Center (new capability, Super Admin only)
        "accounts.view_announcement", "accounts.send_announcement",
    ],
    ROLE_REGISTRATION_ADMIN: [
        "core.view_association", "core.view_sitesettings",
        "members.view_member", "members.change_member", "members.approve_member", "members.manage_alumni_status",
        "members.view_registrationapplication", "members.change_registrationapplication", "members.review_application",
        "members.view_alumnirecord", "members.add_alumnirecord", "members.change_alumnirecord",
    ],
    ROLE_ELECTION_ADMIN: [
        "core.view_association",
        "elections.view_position", "elections.add_position", "elections.change_position", "elections.delete_position",
        "elections.view_election", "elections.add_election", "elections.change_election", "elections.manage_election",
        "elections.view_candidate", "elections.add_candidate", "elections.change_candidate", "elections.delete_candidate",
        "elections.view_vote",
        "elections.publish_results",
        "analytics.view_electionresultsnapshot", "analytics.change_electionresultsnapshot",
    ],
    ROLE_ANALYTICS_ADMIN: [
        "core.view_association",
        "members.view_member",
        "elections.view_election", "elections.view_vote",
        "analytics.view_membershipsnapshot", "analytics.view_agedistributionsnapshot",
        "analytics.view_electionresultsnapshot", "analytics.view_analytics_dashboard",
        # v2.1: Visitor & Usage Analytics
        "analytics.view_pagevisit", "analytics.view_visitor_analytics",
    ],
}
