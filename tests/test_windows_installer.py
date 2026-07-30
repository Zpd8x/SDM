from __future__ import annotations

import unittest
from pathlib import Path


class WindowsInstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.installer = (
            Path(__file__).resolve().parents[1]
            / "INSTALL_BROWSER_INTEGRATION.bat"
        ).read_text(encoding="utf-8")

    def test_pyinstaller_receives_native_host_script(self) -> None:
        self.assertIn('"%SDM_HOST_SCRIPT%"', self.installer)
        self.assertIn(
            r"\browser_host\native_host.py",
            self.installer,
        )

    def test_pyinstaller_search_path_does_not_end_in_backslash(self) -> None:
        self.assertIn(
            '--paths "%SDM_PROJECT_ROOT%\\."',
            self.installer,
        )
        self.assertNotIn('--paths "%~dp0"', self.installer)

    def test_installer_uses_the_project_virtual_environment(self) -> None:
        self.assertIn(
            r'set "SDM_PYTHON=%SDM_PROJECT_ROOT%\.venv\Scripts\python.exe"',
            self.installer,
        )
        self.assertIn('"%SDM_PYTHON%" -m PyInstaller', self.installer)


if __name__ == "__main__":
    unittest.main()
