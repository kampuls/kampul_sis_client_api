"""Uploaded filenames must never escape their folder or pick their own type.

``StorageService._upload_to_local`` does ``os.path.join(target_dir, filename)``.
That does not contain an attacker-controlled name: a leading ``/`` makes the
result absolute and ``..`` walks out of the folder, so an unsanitised filename
is an arbitrary file write. ``/uploads`` is also served by StaticFiles, so an
attacker-chosen extension like ``.html`` or ``.svg`` becomes stored XSS on the
API's own origin.
"""

import os
import unittest

from app.services.storage_service import StorageService


class UploadFilenameSafetyTests(unittest.TestCase):
    FOLDER = "uploads/forms"

    def _resolved(self, filename, content_type="image/png"):
        safe = StorageService.safe_filename(filename, content_type)
        return safe, os.path.abspath(os.path.join(self.FOLDER, safe))

    def _assert_contained(self, filename):
        safe, resolved = self._resolved(filename)
        root = os.path.abspath(self.FOLDER)
        self.assertTrue(
            resolved.startswith(root + os.sep),
            f"{filename!r} escaped to {resolved}",
        )
        self.assertNotIn("..", safe)
        self.assertNotIn("/", safe)
        self.assertNotIn("\\", safe)

    def test_relative_traversal_is_contained(self):
        for name in (
            "../../app/main.py",
            "../../../etc/cron.d/x",
            "a/../../../x.py",
            "./../../y.png",
        ):
            with self.subTest(name=name):
                self._assert_contained(name)

    def test_absolute_paths_are_contained(self):
        """os.path.join discards the folder entirely for an absolute name."""
        for name in ("/etc/passwd", "/tmp/evil.py", "/app/app/main.py"):
            with self.subTest(name=name):
                self._assert_contained(name)

    def test_windows_separators_are_contained(self):
        for name in ("..\\..\\win.py", "C:\\evil.png", "dir\\sub\\x.png"):
            with self.subTest(name=name):
                self._assert_contained(name)

    def test_executable_and_markup_extensions_are_replaced(self):
        for name in (
            "evil.html", "evil.htm", "x.svg", "a.js", "shell.php",
            "code.py", "run.sh", "app.jsp", "x.aspx", "t.exe",
        ):
            with self.subTest(name=name):
                safe = StorageService.safe_filename(name, "image/png")
                self.assertTrue(
                    safe.endswith(".png"), f"{name} -> {safe} kept a live extension"
                )

    def test_unknown_extension_without_a_usable_content_type_becomes_bin(self):
        self.assertTrue(
            StorageService.safe_filename("mystery.xyz", None).endswith(".bin")
        )

    def test_ordinary_filenames_survive(self):
        self.assertEqual(
            StorageService.safe_filename("photo.png", "image/png"), "photo.png"
        )
        self.assertEqual(
            StorageService.safe_filename("ok.jpeg", "image/jpeg"), "ok.jpeg"
        )
        self.assertEqual(
            StorageService.safe_filename("my report.pdf", "application/pdf"),
            "my_report.pdf",
        )

    def test_empty_and_control_characters_get_a_generated_name(self):
        for name in ("", "   ", None, "\x00\x01", "..."):
            with self.subTest(name=name):
                safe = StorageService.safe_filename(name, "image/png")
                self.assertTrue(safe.endswith(".png"))
                self.assertGreater(len(os.path.splitext(safe)[0]), 0)

    def test_very_long_name_is_truncated(self):
        safe = StorageService.safe_filename("a" * 5000 + ".png", "image/png")
        self.assertLessEqual(len(safe), 90)
        self.assertTrue(safe.endswith(".png"))

    def test_dotfiles_do_not_become_hidden_config(self):
        safe = StorageService.safe_filename(".htaccess", "image/png")
        self.assertFalse(safe.startswith("."))


if __name__ == "__main__":
    unittest.main()
