from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class Gate20ProductionHardeningTests(SimpleTestCase):
    def setUp(self):
        self.backend = Path(settings.BASE_DIR)
        self.root = self.backend.parent

    def test_settings_have_no_permissive_production_fallbacks(self):
        text = (self.backend / 'abms_config' / 'settings.py').read_text(encoding='utf-8')
        self.assertIn("DEPLOYMENT_ENV = os.environ.get('DJANGO_ENV', 'development')", text)
        self.assertIn("if IS_PRODUCTION and not SECRET_KEY:", text)
        self.assertIn("if IS_PRODUCTION and not ALLOWED_HOSTS:", text)
        self.assertIn("if IS_PRODUCTION and not DB_PASSWORD:", text)
        self.assertNotIn("ALLOWED_HOSTS = [host.strip() for host in _allowed_hosts.split(',') if host.strip()] or ['*']", text)
        self.assertNotIn("abms-insecure-stage1-foundation-key-2026-ngl-baseline", text)

    def test_production_environment_template_contains_required_values(self):
        text = (self.backend / '.env.example').read_text(encoding='utf-8')
        for expected in (
            'DJANGO_ENV=production',
            'DJANGO_SECRET_KEY=',
            'DJANGO_DEBUG=False',
            'DJANGO_ALLOWED_HOSTS=',
            'DB_ENGINE=postgresql',
            'DB_PASSWORD=',
        ):
            self.assertIn(expected, text)

    def test_gitignore_excludes_runtime_and_database_artifacts(self):
        text = (self.root / '.gitignore').read_text(encoding='utf-8')
        for expected in (
            '*.sqlite3',
            '*_backup*.json',
            '*.abmsbackup',
            'backups/',
            'debug_*.py',
            'analyze_dups.py',
            'fix_transaction_model.py',
        ):
            self.assertIn(expected, text)

