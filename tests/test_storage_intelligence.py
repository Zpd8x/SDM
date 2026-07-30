from __future__ import annotations
import os
import tempfile
import unittest
from pathlib import Path
from sdm.database import DownloadRepository
from sdm.models import DownloadStatus
from sdm.storage_intelligence import build_storage_report, duplicate_groups, replace_with_hardlink, scan_completed_records

class StorageIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = DownloadRepository(self.root / 'downloads.db')
    def tearDown(self): self.temp.cleanup()
    def add_completed(self, name, data, folder=None):
        folder = folder or self.root
        Path(folder).mkdir(parents=True, exist_ok=True)
        (Path(folder)/name).write_bytes(data)
        r=self.repo.create_download(url='https://example.test/'+name,filename=name,folder=str(folder))
        self.repo.update(r.id,status=DownloadStatus.COMPLETED,total_bytes=len(data),downloaded_bytes=len(data))
        return r
    def test_scan_detects_identical_content_with_different_names(self):
        self.add_completed('a.bin',b'same')
        self.add_completed('renamed.dat',b'same',self.root/'other')
        report=scan_completed_records(self.repo)
        self.assertEqual(report.duplicate_groups,1)
        self.assertEqual(report.duplicate_files,1)
        self.assertEqual(len(duplicate_groups(self.repo.list_all())),1)
    def test_same_name_different_content_is_not_duplicate(self):
        self.add_completed('same.bin',b'one',self.root/'one')
        self.add_completed('same.bin',b'two',self.root/'two')
        report=scan_completed_records(self.repo)
        self.assertEqual(report.duplicate_groups,0)
    def test_missing_file_is_reported(self):
        r=self.repo.create_download(url='https://example.test/missing',filename='missing.bin',folder=str(self.root))
        self.repo.update(r.id,status=DownloadStatus.COMPLETED)
        scan_completed_records(self.repo)
        saved=self.repo.get(r.id)
        self.assertEqual(saved.content_fingerprint_status,'Missing')
        self.assertEqual(build_storage_report(self.repo.list_all()).missing_files,1)
    def test_hardlink_replacement_preserves_paths_and_content(self):
        source=self.root/'source.bin'; target=self.root/'target.bin'
        source.write_bytes(b'payload'); target.write_bytes(b'payload')
        replace_with_hardlink(source,target)
        self.assertEqual(target.read_bytes(),b'payload')
        self.assertEqual(os.stat(source).st_ino,os.stat(target).st_ino)

if __name__=='__main__': unittest.main()
