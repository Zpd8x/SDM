from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

try:
    from browser_host.install_host import REGISTRY_KEYS
except ImportError:
    from install_host import REGISTRY_KEYS


def main() -> int:
    if os.name != "nt":
        print("[ERROR] Browser integration removal requires Windows.")
        return 1

    for registry_key in REGISTRY_KEYS:
        subprocess.run(
            ["reg", "delete", registry_key, "/f"],
            check=False,
            capture_output=True,
            text=True,
        )

    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    install_directory = local_app_data / "SDM" / "NativeHost"
    if install_directory.exists():
        shutil.rmtree(install_directory)
    print("[SUCCESS] SDM Native Messaging host removed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
