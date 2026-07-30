from __future__ import annotations

import sys
import traceback
import ctypes
import os
from pathlib import Path


def _show_missing_dependency() -> int:
    message = (
        "\nSDM could not start because PySide6 is not installed.\n\n"
        "Windows users: close this window and run START_SDM.bat.\n"
        "Manual install: python -m pip install -r requirements.txt\n"
    )
    print(message)
    return 1


def _configure_bundled_tools() -> Path:
    if getattr(sys, "frozen", False):
        root = Path(sys.executable).resolve().parent
    else:
        root = Path(__file__).resolve().parent
    tools = root / "Tools"
    if tools.is_dir():
        current = os.environ.get("PATH", "")
        parts = [part for part in current.split(os.pathsep) if part]
        if str(tools) not in parts:
            os.environ["PATH"] = str(tools) + os.pathsep + current
        os.environ.setdefault("FFMPEG_BINARY", str(tools / "ffmpeg.exe"))
    return root


def _set_windows_app_user_model_id() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "ZPD8X.SDM.SmartDownloadManager"
        )
    except (AttributeError, OSError):
        pass


def _run_browser_host_action(action: str) -> int:
    if sys.platform != "win32":
        print("[ERROR] Browser integration actions require Windows.")
        return 1
    if getattr(sys, "frozen", False):
        executable_root = Path(sys.executable).resolve().parent
    else:
        executable_root = Path(__file__).resolve().parent
    host_executable = executable_root / "browser_host" / "SDMNativeHost.exe"
    extension_manifest = executable_root / "browser_extension" / "manifest.json"
    from browser_host.install_host import install_packaged_host, uninstall_packaged_host
    if action == "install":
        return install_packaged_host(host_executable, extension_manifest, executable_root)
    return uninstall_packaged_host()


def main() -> int:
    _configure_bundled_tools()
    if "--install-browser-host" in sys.argv:
        return _run_browser_host_action("install")
    if "--uninstall-browser-host" in sys.argv:
        return _run_browser_host_action("uninstall")
    capture_only = "--capture-only" in sys.argv
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
    except ImportError:
        return _show_missing_dependency()

    from sdm.config import APP_NAME, APP_VERSION, ensure_app_directories
    from sdm.browser_bridge import is_application_running
    from sdm.database import DownloadRepository
    from sdm.ui.main_window import MainWindow
    from sdm.ui.icons import application_icon
    from sdm.ui.theme import DARK_STYLESHEET

    paths = ensure_app_directories()
    if not capture_only and is_application_running(paths.heartbeat):
        try:
            paths.show_manager_request.touch(exist_ok=True)
        except OSError:
            pass
        return 0

    repository = DownloadRepository(paths.database)

    # Plugins are fault-isolated: a broken third-party plugin can never block SDM startup.
    from sdm.plugins import PluginManager
    plugin_manager = PluginManager(paths.plugins)
    plugin_manager.discover()
    plugin_manager.load_enabled({"repository": repository, "paths": paths})
    _set_windows_app_user_model_id()

    qt_arguments = [
        argument
        for argument in sys.argv
        if argument != "--capture-only"
    ]
    app = QApplication(qt_arguments)
    app.setQuitOnLastWindowClosed(not capture_only)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("SDM")
    app.setWindowIcon(application_icon())
    app.setStyleSheet(DARK_STYLESHEET)

    def handle_exception(exc_type, exc_value, exc_traceback) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        details = "".join(
            traceback.format_exception(exc_type, exc_value, exc_traceback)
        )
        try:
            paths.logs.mkdir(parents=True, exist_ok=True)
            (paths.logs / "crash.log").write_text(details, encoding="utf-8")
        except OSError:
            pass

        QMessageBox.critical(
            None,
            "SDM Error",
            "An unexpected error occurred.\n\n"
            f"Details were written to:\n{paths.logs / 'crash.log'}",
        )

    sys.excepthook = handle_exception
    window = MainWindow(
        repository,
        heartbeat_path=paths.heartbeat,
        show_manager_request_path=paths.show_manager_request,
        capture_only=capture_only,
    )
    if not capture_only:
        window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
