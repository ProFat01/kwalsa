"""
Seed list for the public registration "Course" field.

Same design philosophy as institutions.py: presentation-layer data only.
Member.course stays a plain CharField (see models.py) and always stores
whatever string the registrant ends up with, whether that came from
picking one of these names or from typing a custom one via the "Other"
option. Nothing here changes what gets saved, only what's offered as a
starting point.

Grouped by broad Nigerian tertiary-education subject area rather than by
institution (courses aren't state-specific the way institutions.py's
Gombe-first grouping is) so the dropdown reads like a course catalogue:
Sciences, Engineering and Technology, Computing and ICT, Medicine and
Health Sciences, Education, Arts and Humanities, Social and Management
Sciences, Agriculture, Law, and Professional and Vocational Programmes.
Each list is a representative, well-known-names-only sample -- it is not
meant to be exhaustive, exactly like institutions.py's NATIONAL_UNIVERSITIES
-- "Other" covers the rest.
"""

SCIENCES = [
    "Biochemistry",
    "Biology",
    "Chemistry",
    "Geology",
    "Microbiology",
    "Mathematics",
    "Physics",
    "Statistics",
]

ENGINEERING_AND_TECHNOLOGY = [
    "Agricultural Engineering",
    "Chemical Engineering",
    "Civil Engineering",
    "Electrical Engineering",
    "Electronic Engineering",
    "Mechanical Engineering",
    "Petroleum Engineering",
    "Telecommunications Engineering",
]

COMPUTING_AND_ICT = [
    "Computer Engineering",
    "Computer Science",
    "Cyber Security",
    "Information and Communication Technology",
    "Information Technology",
    "Software Engineering",
]

MEDICINE_AND_HEALTH_SCIENCES = [
    "Anatomy",
    "Dentistry",
    "Medical Laboratory Science",
    "Medicine and Surgery (MBBS)",
    "Nursing Science",
    "Pharmacy",
    "Physiology",
    "Physiotherapy",
    "Public Health",
    "Radiography",
]

EDUCATION = [
    "Adult and Non-Formal Education",
    "Early Childhood Education",
    "Education and English Language",
    "Education and Mathematics",
    "Educational Administration and Planning",
    "Guidance and Counselling",
    "Science Education",
]

ARTS_AND_HUMANITIES = [
    "Arabic",
    "Christian Religious Studies",
    "English Language",
    "History and International Studies",
    "Islamic Studies",
    "Linguistics",
    "Philosophy",
    "Theatre and Performing Arts",
]

SOCIAL_AND_MANAGEMENT_SCIENCES = [
    "Accounting",
    "Banking and Finance",
    "Business Administration",
    "Economics",
    "Mass Communication",
    "Political Science",
    "Public Administration",
    "Sociology",
]

AGRICULTURE = [
    "Agricultural Economics and Extension",
    "Agricultural Science",
    "Animal Science",
    "Crop Science",
    "Fisheries and Aquaculture",
    "Forestry and Wildlife Management",
    "Soil Science",
]

LAW = [
    "Law (LL.B)",
    "Sharia Law",
]

PROFESSIONAL_AND_VOCATIONAL_PROGRAMMES = [
    "Automobile Technology",
    "Catering and Hotel Management",
    "Cosmetology",
    "Fashion Design and Clothing Technology",
    "Secretarial Studies",
    "Welding and Fabrication Engineering",
]

# Sentinel posted when the registrant picks "Other" instead of a listed
# course -- never a real course name, so it can't collide with one. The
# visible label is what actually renders in the <option>. Deliberately
# the same literal string as institutions.OTHER_INSTITUTION_VALUE ("other")
# since each ChoiceField is validated and resolved independently in
# forms.py's clean() -- the two "other" sentinels never appear in the
# same POST field, so there's no risk of them being confused for each
# other.
OTHER_COURSE_VALUE = "other"
OTHER_COURSE_LABEL = "Other (type your course)"

# Grouped-choices shape a Django Select widget renders as <optgroup>s
# automatically: [(group_label, [(value, label), ...]), ...]. The
# trailing plain tuple (not wrapped in a group) renders as a top-level
# <option>, which is exactly what we want for "Other" -- same pattern
# institutions.py's INSTITUTION_CHOICES uses.
COURSE_CHOICES = [
    ("", "Select your course\u2026"),
    ("Sciences", [(name, name) for name in SCIENCES]),
    ("Engineering and Technology", [(name, name) for name in ENGINEERING_AND_TECHNOLOGY]),
    ("Computing and ICT", [(name, name) for name in COMPUTING_AND_ICT]),
    ("Medicine and Health Sciences", [(name, name) for name in MEDICINE_AND_HEALTH_SCIENCES]),
    ("Education", [(name, name) for name in EDUCATION]),
    ("Arts and Humanities", [(name, name) for name in ARTS_AND_HUMANITIES]),
    ("Social and Management Sciences", [(name, name) for name in SOCIAL_AND_MANAGEMENT_SCIENCES]),
    ("Agriculture", [(name, name) for name in AGRICULTURE]),
    ("Law", [(name, name) for name in LAW]),
    ("Professional and Vocational Programmes", [(name, name) for name in PROFESSIONAL_AND_VOCATIONAL_PROGRAMMES]),
    (OTHER_COURSE_VALUE, OTHER_COURSE_LABEL),
]
