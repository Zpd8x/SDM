# SDM GitHub Hosting Plan

## Repository model

Use one public repository named `SDM`:

- Source code and build scripts in the repository.
- Official website in `docs/`.
- Windows binaries in GitHub Releases, not in Git history.
- GitHub Pages deployed by `.github/workflows/pages.yml`.

## Before the first push

1. Open `docs/assets/js/site.js`.
2. Replace `YOUR_GITHUB_USERNAME` with the account name.
3. Review `LICENSE.txt`, `README.md`, and personal data.
4. Never commit cookies, databases, session vaults, build output or private URLs.

## Create and push the repository

```powershell
git init
git branch -M main
git add .
git commit -m "Release SDM v2.0.0 Final"
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/SDM.git
git push -u origin main
```

## Enable GitHub Pages

1. Open repository **Settings → Pages**.
2. Under **Build and deployment**, choose **GitHub Actions**.
3. Open the **Actions** tab and confirm the Pages workflow succeeds.
4. The website becomes available at:
   `https://YOUR_GITHUB_USERNAME.github.io/SDM/`

## Publish v2.0.0 binaries

Create a new GitHub Release:

- Tag: `v2.0.0`
- Title: `SDM v2.0.0 Final`
- Target: `main`

Attach exactly:

- `SDM_v2.0.0_Setup_x64.exe`
- `SDM_v2.0.0_Portable_x64.zip`
- `SDM_Browser_Extension_v2.0.0.zip`
- `SHA256SUMS.txt`
- `RELEASE_NOTES.md`

The website download buttons already target these names.

## Recommended release notes

Describe the bundled tools, Windows requirements, browser installation, upgrade behavior and checksum verification. Mention that the binary is unsigned if no code-signing certificate is used.

## Future release workflow

For each version:

1. Update `VERSION`, README and CHANGELOG.
2. Update the version and asset names in `docs/assets/js/site.js`.
3. Run all tests and build the Setup, Portable and Extension packages.
4. Generate SHA-256 checksums.
5. Commit source and documentation.
6. Create a matching Git tag and GitHub Release.
7. Test every download link from GitHub Pages.
