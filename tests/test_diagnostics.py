import tempfile
import unittest
from pathlib import Path

from sdm.database import DownloadRepository
from sdm.diagnostics import DiagnosticsService


class DiagnosticsTests(unittest.TestCase):
    def test_database_health_and_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = root / "downloads.db"
            repository = DownloadRepository(db)
            service = DiagnosticsService(db, root)
            items = service.collect()
            database = next(item for item in items if item.name == "Database")
            self.assertEqual(database.status, "OK")
            report = service.export(root / "report.json")
            self.assertTrue(report.exists())
            self.assertIn('"sdm_version": "2.0.0"', report.read_text())
            del repository
