"""
Membership Card System v1 — QR + verification helpers.

Kept separate from services.py (which owns the credential-lookup
concern) because this is a different responsibility: turning a
MembershipCard into (a) the URL its QR code should point at and (b) the
actual QR image bytes. Nothing here touches Member, RegistrationApplication,
voting, or credential lookup.
"""
import io

import qrcode
from django.urls import reverse


def build_verification_url(request, card):
    """
    Absolute URL the QR code encodes, e.g.
    https://your-domain/members/verify/<uuid>/ — absolute (not relative)
    because the QR is meant to be scanned by a phone camera off the
    physical/printed card, not opened from within the site itself.
    """
    path = reverse("members:verify_member", kwargs={"card_uuid": card.card_uuid})
    return request.build_absolute_uri(path)


def generate_qr_png(data):
    """
    Renders `data` (a URL string) as a QR code PNG, entirely offline via
    the `qrcode` package (+ Pillow, already a project dependency) — no
    network call, no third-party QR API. Returns raw PNG bytes.

    box_size/border kept small-ish (still well within scannable range)
    since this is embedded inline on a card template, not served as a
    giant standalone image — keeps the response small and fast even on
    PythonAnywhere Free's shared, rate-limited CPU.
    """
    qr = qrcode.QRCode(
        version=None,  # auto-sized to fit the data
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    image = qr.make_image(fill_color="#16212c", back_color="#ffffff")

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
