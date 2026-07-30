from __future__ import annotations

import unittest
from pathlib import Path


class WindowsReleaseBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = (
            Path(__file__).resolve().parents[1]
            / "packaging"
            / "windows"
            / "build_release.bat"
        ).read_text(encoding="utf-8")

    def test_missing_inno_setup_is_a_hard_failure(self) -> None:
        self.assertIn('call :fatal "Inno Setup 6 was not found."', self.script)
        self.assertNotIn("Setup EXE was skipped", self.script)

    def test_inno_setup_is_searched_in_common_locations_and_path(self) -> None:
        self.assertIn("where %%I", self.script)
        self.assertIn(r"%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe", self.script)
        self.assertIn(r"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe", self.script)

    def test_setup_output_is_verified(self) -> None:
        self.assertIn('if not exist "%SETUP_EXE%"', self.script)
        self.assertIn('"Windows Setup file was not created."', self.script)

    def test_failure_displays_windows_message_box(self) -> None:
        self.assertIn("[System.Windows.MessageBox]::Show", self.script)
        self.assertIn("'Error'", self.script)


    def test_fatal_path_terminates_the_entire_build(self) -> None:
        self.assertIn(":fatal", self.script)
        self.assertIn("endlocal", self.script)
        self.assertIn("exit 1", self.script)
        self.assertNotIn("goto :abort_build", self.script)

    def test_installer_registry_command_uses_inno_quote_escaping(self) -> None:
        installer = (
            Path(__file__).resolve().parents[1]
            / "packaging"
            / "windows"
            / "installer.iss"
        ).read_text(encoding="utf-8")
        self.assertIn('ValueData: """{app}\\SDM.exe"" --capture-only"', installer)
        self.assertNotIn('ValueData: "\\"{app}', installer)


if __name__ == "__main__":
    unittest.main()
