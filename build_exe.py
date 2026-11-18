"""
Build standalone Windows executable (dist/AuraTime.exe) using PyInstaller.
Embeds the multi-resolution AuraTime icon and bundles the assets folder.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from logo import ensure_brand_assets


def build() -> int:
    root_dir = Path(__file__).resolve().parent
    assets_dir = root_dir / "assets"
    assets = ensure_brand_assets(assets_dir)
    ico_path = assets["ico"]

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        "AuraTime",
        "--icon",
        str(ico_path),
        "--add-data",
        f"{assets_dir};assets",
        str(root_dir / "main.py"),
    ]

    print("Running PyInstaller:", " ".join(cmd))
    res = subprocess.run(cmd, cwd=str(root_dir), check=False)
    if res.returncode == 0:
        exe_out = root_dir / "dist" / "AuraTime.exe"
        if exe_out.exists():
            size_mb = exe_out.stat().st_size / (1024 * 1024)
            print(f"\n[OK] Built standalone executable: {exe_out} ({size_mb:.2f} MB)")
    return res.returncode


if __name__ == "__main__":
    sys.exit(build())
