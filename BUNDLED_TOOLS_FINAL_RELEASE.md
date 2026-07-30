# SDM v2.0.0 — Bundled Tools Final Release

The Windows release builder now downloads, verifies, packages, and installs:

- yt-dlp.exe
- ffmpeg.exe
- ffprobe.exe
- ffplay.exe

The files are stored under `Tools`, included in both Setup and Portable builds,
and prepended to the process PATH when SDM starts. Users do not need to install
these utilities separately.

The build requires an internet connection only while creating the release.
The resulting Setup and Portable packages work with the bundled executables.
