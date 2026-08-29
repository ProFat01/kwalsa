"""
Shared helpers for the members app test suite.
"""
import io
import shutil
import tempfile

from PIL import Image

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings


def make_image(name="upload.png", size=(10, 10)):
    """
    A real, tiny, valid PNG — ImageField validation (via Pillow) actually
    opens the uploaded file to confirm it's a real image, so a fake
    byte string wouldn't pass; a 10x10 in-memory PNG is the cheapest
    thing that will.
    """
    buf = io.BytesIO()
    Image.new("RGB", size, color="white").save(buf, format="PNG")
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type="image/png")


class MediaIsolatedTestCase(TestCase):
    """
    Base class for any test that uploads a file. Points MEDIA_ROOT at a
    fresh temp directory for the duration of the test class and removes
    it afterwards, so test runs never leave passport/receipt files behind
    in the project's real media/ folder.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._temp_media_root = tempfile.mkdtemp(prefix="sams_test_media_")
        cls._media_override = override_settings(MEDIA_ROOT=cls._temp_media_root)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._temp_media_root, ignore_errors=True)
        super().tearDownClass()
