from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class BundledToolsReleaseTests(unittest.TestCase):
    def test_build_downloads_required_tools(self):
        build = (ROOT / 'packaging/windows/build_release.bat').read_text(encoding='utf-8')
        self.assertIn('download_tools.ps1', build)
        script = (ROOT / 'packaging/windows/download_tools.ps1').read_text(encoding='utf-8')
        for name in ('yt-dlp.exe', 'ffmpeg.exe', 'ffprobe.exe', 'ffplay.exe'):
            self.assertIn(name, script)

    def test_installer_and_portable_include_tools(self):
        installer = (ROOT / 'packaging/windows/installer.iss').read_text(encoding='utf-8')
        prepare = (ROOT / 'packaging/windows/prepare_release.ps1').read_text(encoding='utf-8')
        spec = (ROOT / 'packaging/windows/SDM.spec').read_text(encoding='utf-8')
        self.assertIn('Tools', installer)
        self.assertIn("Join-Path $Root 'Tools'", prepare)
        self.assertIn('project_root / "Tools"', spec)

    def test_runtime_prepends_bundled_tools_to_path(self):
        main = (ROOT / 'main.py').read_text(encoding='utf-8')
        self.assertIn('def _configure_bundled_tools()', main)
        self.assertIn('os.environ["PATH"] = str(tools)', main)


if __name__ == '__main__':
    unittest.main()
