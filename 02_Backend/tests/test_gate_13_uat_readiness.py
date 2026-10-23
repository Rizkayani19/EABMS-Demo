from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase
import io


class Gate13OfflineAssetTests(TestCase):
    def test_uat_preflight_command_is_registered(self):
        output = io.StringIO()
        try:
            call_command("abms_uat_preflight", stdout=output)
        except Exception:
            pass  # Preflight may fail if actual environment is not UAT ready.
        self.assertTrue(
            "ABMS UAT / RELEASE READINESS PREFLIGHT" in output.getvalue()
            or "UAT preflight" in output.getvalue().lower()
        )

    def test_shell_uses_local_assets_and_has_no_external_shell_dependencies(self):
        base_dir = Path(settings.BASE_DIR)
        base = (base_dir / "templates" / "base.html").read_text(encoding="utf-8")
        style = (base_dir / "static" / "css" / "style.css").read_text(encoding="utf-8")

        # The approved production shell uses:
        # - Compiled Tailwind CSS (built from static/css/input.css via Tailwind CLI)
        # - Locally vendored HTMX and TomSelect JS — no external CDN dependencies
        self.assertIn("css/tailwind.css", base)  # compiled production CSS
        self.assertIn("js/htmx.js", base)
        self.assertIn("js/tom-select.complete.min.js", base)
        self.assertIn("css/tom-select.css", base)

        for marker in (
            "https://cdn.tailwindcss.com",
            "https://unpkg.com/",
            "https://fonts.googleapis.com/",
            "https://fonts.gstatic.com/",
        ):
            self.assertNotIn(marker, base)
            self.assertNotIn(marker, style)

        self.assertTrue((base_dir / "static/css/tailwind.css").is_file())
        self.assertTrue((base_dir / "static/js/htmx.js").is_file())
        self.assertTrue((base_dir / "static/js/tom-select.complete.min.js").is_file())
        self.assertTrue((base_dir / "static/css/tom-select.css").is_file())

