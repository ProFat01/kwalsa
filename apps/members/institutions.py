"""
Seed list for the public registration "Institution" field.

Presentation-layer data only: Member.institution stays a plain
CharField (see models.py) and always stores whatever string the
registrant ends up with, whether that came from picking one of these
names or from typing a custom one via the "Other" option. Nothing here
changes what gets saved, only what's offered as a starting point.

KWALSA is a Gombe State association, so GOMBE_STATE_INSTITUTIONS is
deliberately broader than "universities" -- it covers every tertiary
institution type based in the state (universities, polytechnics,
colleges of education, health-tech/nursing colleges) since a Gombe
indigene member could plausibly attend any of them. NATIONAL_UNIVERSITIES
is a short, well-known-names-only list for members studying elsewhere in
the country; it is not meant to be exhaustive -- "Other" covers the rest.

Names/spellings checked against Wikipedia's "List of Higher Institutions
in Gombe State", each institution's own Wikipedia page, and Gombe State
Government / NUC news coverage as of 2026-09. One entry is worth a note:
the institution long known as "Gombe State University of Science and
Technology, Kumo" entered a PPP with Lincoln University College of
Malaysia in 2022 and, as of the 2025/2026 session, now admits students
as Lincoln University Kumo -- listed under its current name below.
"""

# Ordered for the UI: Gombe State institutions first (KWALSA's home
# state), then other well-known Nigerian universities. Each tuple is
# (value, label); value == label since Member.institution stores the
# plain display string either way.
GOMBE_STATE_INSTITUTIONS = [
    "Federal College of Education (Technical), Gombe",
    "Federal College of Horticultural Technology, Dadin Kowa",
    "Federal Polytechnic, Kaltungo",
    "Federal University Kashere (FUK)",
    "Gombe State College of Education, Billiri",
    "Gombe State College of Health Sciences and Technology, Kaltungo",
    "Gombe State College of Legal Studies, Nafada",
    "Gombe State College of Nursing and Midwifery, Gombe",
    "Gombe State Polytechnic, Bajoga",
    "Gombe State University (GSU), Tudun Wada",
    "JIBWIS College of Education, Gombe",
    "Lincoln University Kumo (formerly Gombe State University of Science & Technology)",
    "National Open University of Nigeria (NOUN), Gombe Study Centre",
    "Umma College of Health Sciences and Technology, Gombe",
]

NATIONAL_UNIVERSITIES = [
    "Ahmadu Bello University (ABU), Zaria",
    "Bayero University Kano (BUK)",
    "Delta State University, Abraka",
    "Ekiti State University",
    "Federal University of Technology, Akure (FUTA)",
    "Federal University of Technology, Minna (FUTMINNA)",
    "Lagos State University (LASU)",
    "Nnamdi Azikiwe University, Awka (UNIZIK)",
    "Obafemi Awolowo University (OAU), Ile-Ife",
    "University of Abuja",
    "University of Benin (UNIBEN)",
    "University of Calabar (UNICAL)",
    "University of Ibadan (UI)",
    "University of Ilorin (UNILORIN)",
    "University of Jos (UNIJOS)",
    "University of Lagos (UNILAG)",
    "University of Maiduguri (UNIMAID)",
    "University of Nigeria, Nsukka (UNN)",
    "University of Port Harcourt (UNIPORT)",
    "University of Uyo (UNIUYO)",
]

# Sentinel posted when the registrant picks "Other" instead of a listed
# institution -- never a real institution name, so it can't collide with
# one. The visible label is what actually renders in the <option>.
OTHER_INSTITUTION_VALUE = "other"
OTHER_INSTITUTION_LABEL = "Other (type your institution)"

# Grouped-choices shape a Django Select widget renders as <optgroup>s
# automatically: [(group_label, [(value, label), ...]), ...]. The
# trailing plain tuple (not wrapped in a group) renders as a top-level
# <option>, which is exactly what we want for "Other".
INSTITUTION_CHOICES = [
    ("", "Select your institution\u2026"),
    ("Gombe State Institutions", [(name, name) for name in GOMBE_STATE_INSTITUTIONS]),
    ("Other Nigerian Universities", [(name, name) for name in NATIONAL_UNIVERSITIES]),
    (OTHER_INSTITUTION_VALUE, OTHER_INSTITUTION_LABEL),
]
