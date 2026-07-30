from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QWidget


def configure_attention_window(
    window: QWidget,
    *,
    application_modal: bool = False,
) -> None:
    """Make a standalone SDM window visible in the taskbar and above apps."""
    flags = (
        Qt.WindowType.Window
        | Qt.WindowType.WindowTitleHint
        | Qt.WindowType.WindowSystemMenuHint
        | Qt.WindowType.WindowMinimizeButtonHint
        | Qt.WindowType.WindowCloseButtonHint
        | Qt.WindowType.WindowStaysOnTopHint
    )
    window.setWindowFlags(flags)
    window.setAttribute(
        Qt.WidgetAttribute.WA_ShowWithoutActivating,
        False,
    )
    if application_modal:
        window.setWindowModality(Qt.WindowModality.ApplicationModal)


def schedule_window_activation(window: QWidget) -> None:
    """Activate after Qt creates the native HWND and starts its event loop."""
    QTimer.singleShot(0, lambda: bring_window_to_front(window))
    QTimer.singleShot(180, lambda: bring_window_to_front(window))


def bring_window_to_front(window: QWidget) -> None:
    if window.isMinimized():
        window.showNormal()
    else:
        window.show()
    window.setWindowState(
        (window.windowState() & ~Qt.WindowState.WindowMinimized)
        | Qt.WindowState.WindowActive
    )
    window.raise_()
    window.activateWindow()
    _activate_windows_hwnd(window)


def _activate_windows_hwnd(window: QWidget) -> None:
    if sys.platform != "win32":
        return
    try:
        hwnd_value = int(window.winId())
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
    except (AttributeError, TypeError, ValueError):
        return
    if not hwnd_value:
        return
    hwnd = wintypes.HWND(hwnd_value)

    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.AttachThreadInput.argtypes = [
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.BOOL,
    ]
    user32.AttachThreadInput.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user32.BringWindowToTop.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetFocus.argtypes = [wintypes.HWND]
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD

    foreground = user32.GetForegroundWindow()
    current_thread = kernel32.GetCurrentThreadId()
    foreground_thread = (
        user32.GetWindowThreadProcessId(foreground, None)
        if foreground
        else 0
    )
    attached = False
    if foreground_thread and foreground_thread != current_thread:
        attached = bool(
            user32.AttachThreadInput(
                current_thread,
                foreground_thread,
                True,
            )
        )
    try:
        sw_restore = 9
        hwnd_topmost = wintypes.HWND(-1)
        swp_nosize = 0x0001
        swp_nomove = 0x0002
        swp_showwindow = 0x0040
        user32.ShowWindow(hwnd, sw_restore)
        user32.SetWindowPos(
            hwnd,
            hwnd_topmost,
            0,
            0,
            0,
            0,
            swp_nosize | swp_nomove | swp_showwindow,
        )
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetFocus(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(
                current_thread,
                foreground_thread,
                False,
            )
