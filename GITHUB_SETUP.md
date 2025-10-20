# GitHub Setup for HACS Compatibility

This guide shows you how to push your integration to GitHub and make it installable via HACS.

## Prerequisites

1. GitHub account
2. Git installed locally
3. GitHub Personal Access Token (classic) with `repo` scope

## Step 1: Create GitHub Personal Access Token

1. Go to https://github.com/settings/tokens
2. Click "Generate new token" → "Generate new token (classic)"
3. Name: `HA Integration Upload`
4. Select scope: ✅ `repo` (Full control of private repositories)
5. Click "Generate token"
6. **Copy the token** (you won't see it again!)

## Step 2: Initialize Git Repository

```bash
cd /path/to/ha-z2m-irrigation

# Initialize repository
git init

# Add all files
git add .

# Create initial commit
git commit -m "Initial release v0.3.0 - Z2M Irrigation Integration"
```

## Step 3: Create GitHub Repository

### Option A: Via GitHub Website

1. Go to https://github.com/new
2. Repository name: `ha-z2m-irrigation`
3. Description: `Home Assistant integration for Sonoff Zigbee water valves via Zigbee2MQTT with GUI session logging`
4. Visibility: **Public** (required for HACS)
5. **DO NOT** initialize with README, .gitignore, or license (we already have these)
6. Click "Create repository"

### Option B: Via GitHub CLI (if installed)

```bash
gh repo create ha-z2m-irrigation --public --source=. --remote=origin --push
```

## Step 4: Push to GitHub

Replace `YOUR_USERNAME` and `YOUR_TOKEN`:

```bash
# Add remote (use token in URL for authentication)
git remote add origin https://YOUR_TOKEN@github.com/YOUR_USERNAME/ha-z2m-irrigation.git

# Push to main branch
git branch -M main
git push -u origin main
```

**Example:**
```bash
git remote add origin https://ghp_xxxxxxxxxxxx@github.com/johndoe/ha-z2m-irrigation.git
git branch -M main
git push -u origin main
```

## Step 5: Create Release Tag

```bash
# Create annotated tag
git tag -a v0.3.0 -m "Release v0.3.0 - Initial release with GUI session logging"

# Push tag
git push origin v0.3.0
```

## Step 6: Create GitHub Release

1. Go to your repository on GitHub
2. Click "Releases" → "Create a new release"
3. Tag: Select `v0.3.0`
4. Release title: `v0.3.0 - Initial Release`
5. Description:
   ```markdown
   ## Z2M Irrigation Integration v0.3.0

   Initial release of the Zigbee2MQTT Irrigation integration for Home Assistant.

   ### Features
   - UI-only configuration (no YAML)
   - Multi-valve support
   - Real-time flow monitoring
   - Volume tracking with persistent totals
   - GUI session history panel
   - Automation services (timed, litres, manual)
   - Failsafe protection
   - HACS compatible

   ### Installation via HACS
   1. HACS → Integrations → ⋮ → Custom repositories
   2. Add: `https://github.com/YOUR_USERNAME/ha-z2m-irrigation`
   3. Category: Integration
   4. Install and restart Home Assistant

   See [README](https://github.com/YOUR_USERNAME/ha-z2m-irrigation#readme) for full documentation.
   ```
6. Click "Publish release"

## Step 7: Update manifest.json

Update the URLs in `manifest.json` with your actual GitHub username:

```json
{
  "domain": "z2m_irrigation",
  "name": "Z2M Irrigation (Sonoff Valves)",
  "codeowners": ["@YOUR_GITHUB_USERNAME"],
  "config_flow": true,
  "dependencies": ["mqtt"],
  "documentation": "https://github.com/YOUR_USERNAME/ha-z2m-irrigation",
  "iot_class": "local_push",
  "issue_tracker": "https://github.com/YOUR_USERNAME/ha-z2m-irrigation/issues",
  "requirements": [],
  "version": "0.3.0"
}
```

Then commit and push:

```bash
git add manifest.json
git commit -m "Update manifest URLs"
git push
```

## Step 8: Verify HACS Compatibility

Your repository structure should look like this:

```
ha-z2m-irrigation/
├── .gitignore
├── README.md
├── LICENSE
├── hacs.json                  ← Important for HACS
├── info.md                    ← Shows in HACS UI
├── manifest.json              ← Integration metadata
├── __init__.py                ← Integration files at root
├── config_flow.py
├── const.py
├── sensor.py
├── switch.py
├── websocket.py
├── logbook.py
├── services.yaml
├── strings.json
├── panel/
│   └── panel.js
└── translations/
    └── en.json
```

**Key points for HACS:**
- ✅ Integration files are in **repository root**
- ✅ `hacs.json` with `"content_in_root": true`
- ✅ `manifest.json` with proper metadata
- ✅ `info.md` for HACS description
- ✅ `README.md` for documentation
- ✅ Repository is **public**

## Step 9: Test HACS Installation

1. In Home Assistant, go to HACS → Integrations
2. Click ⋮ (three dots) → Custom repositories
3. Add your repository: `https://github.com/YOUR_USERNAME/ha-z2m-irrigation`
4. Category: Integration
5. Click "Add"
6. Search for "Z2M Irrigation"
7. Click "Download"
8. Restart Home Assistant
9. Add integration via Settings → Devices & Services

## Troubleshooting

### Authentication Failed

If you get authentication errors:

```bash
# Update remote URL with token
git remote set-url origin https://YOUR_TOKEN@github.com/YOUR_USERNAME/ha-z2m-irrigation.git
```

### HACS Can't Find Integration

Check:
- Repository is public
- `hacs.json` exists with correct settings
- `manifest.json` has correct `domain`
- All Python files are in root (not in subdirectory)

### Token Security

**Never commit your token!** It's only used in the remote URL locally. Your `.gitignore` protects against accidentally committing sensitive files.

To remove token from git history (if accidentally committed):

```bash
# Change remote to use HTTPS without token
git remote set-url origin https://github.com/YOUR_USERNAME/ha-z2m-irrigation.git

# Use credential helper instead
git config credential.helper store
```

## Future Updates

When you make updates:

```bash
# Make changes to code
git add .
git commit -m "Fix: description of changes"
git push

# Update version in manifest.json
# Create new tag
git tag -a v0.3.1 -m "Release v0.3.1 - Bug fixes"
git push origin v0.3.1

# Create new GitHub release
```

## Alternative: Can't Push to GitHub?

If you can't push to GitHub yourself:

1. Create repository via GitHub web interface
2. Use GitHub's web UI to upload files
3. Create release manually through web UI
4. Users can still install via HACS custom repository

## Need More Help?

If you provide your GitHub username, I can give you exact commands with your username filled in.

---

**Once published, users install with:**

```
HACS → Integrations → ⋮ → Custom repositories
Add: https://github.com/YOUR_USERNAME/ha-z2m-irrigation
Category: Integration
```

🎉 Your integration is now HACS-compatible!
