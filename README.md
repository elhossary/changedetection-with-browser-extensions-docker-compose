# Sockpuppetbrowser with multiple Chrome extensions

Put `Dockerfile.browser`, `browser-extension.py`, and `extensions.txt` alongside your existing Compose file, and replace its contents with the supplied `docker-compose.yml`.
Keep the same Compose directory and project name so Docker continues to use your existing `changedetection-data` volume.

List the extension links in `extensions.txt`, one link per line. Your Poper Blocker example is already included. Uncomment and replace the additional placeholders to add more extensions:

```text
https://chromewebstore.google.com/detail/pop-up-blocker-for-chrome/bkkbcggnhapdmkeljlodobbkopceiche?hl=en
# https://chromewebstore.google.com/detail/REPLACE_WITH_SECOND_EXTENSION
# https://chromewebstore.google.com/detail/REPLACE_WITH_THIRD_EXTENSION
```

This is a plain text file: use one complete URL per line, without quotes or YAML list dashes. Blank lines and lines starting with `#` are ignored. Exact duplicate links and extensions with the same ID are installed once. You may mix Web Store links and direct archive links in this list.

The browser's Compose build configuration is now simply:

```yaml
build:
  context: .
  dockerfile: Dockerfile.browser
```

The Dockerfile copies `extensions.txt` into the image and the installer reads it during the build. The file is now the source of the URL list; the previous URL build arguments have been removed. Editing the file requires a rebuild followed by container recreation with the commands below. A container restart alone does not apply changes to the list.

Supported inputs are Chrome Web Store listing links and direct HTTPS ZIP/CRX downloads. For Web Store links, the installer extracts each extension ID, requests the compatible package from Google's download service using the installed Chromium version, and unpacks the CRX automatically. It preserves each developer public key in `manifest.json` so unpacked extensions keep their original Web Store IDs. Both CRX2 and CRX3 packages are supported. Parsing preserves and checks the package ID; it does not independently verify the package's cryptographic signature. Downloads use HTTPS.

The extension must use **Manifest V3**. A source archive that needs a build step is not supported. The archive may contain the extension at its root or in a single enclosing directory. When its manifest is not at the root, there must be exactly one `manifest.json` in the archive. Extensions that explicitly disallow incognito mode are rejected because changedetection.io opens isolated browser contexts. Web Store listing query parameters such as `?hl=en` do not affect extension selection.

Run these commands from your existing Compose directory:

```bash
sudo docker compose build --pull browser-sockpuppet-chrome
sudo docker compose up -d
```

In changedetection.io, use the Playwright/Chrome JavaScript fetch method for the relevant watches. Requests using a different browser URL or a non-browser fetch method do not use this extension.

The browser image is derived from `dgtlmoon/sockpuppetbrowser:latest`. It installs Debian Chromium and sets `CHROME_BIN` to a small launcher. Each extension is installed in its own folder. The launcher passes all folders together to Chromium's extension loading flags and sets incognito permission for every installed extension in each browser's separate profile. It preserves sockpuppetbrowser's separate profile per connection and the original Compose service settings.

All listed extensions are loaded for every browser connection using this service. After adding or removing links, run the build and startup commands again. Removing a link removes that extension from the set the launcher loads. Reordering the list does not change existing extension IDs. If any download or package validation fails, the build stops instead of producing an image with a partially processed list.

The switch to Chromium is deliberate: current branded Chrome restricts the command-line flags used to load unpacked extensions. The incognito preference addresses changedetection.io's use of `browser.new_context()`. This is custom integration, not a built-in sockpuppetbrowser extension-URL setting.

Limitations:

- A particular extension may require further configuration or may not function correctly in an isolated/incognito context even when permission is enabled.
- Browser profiles are temporary. Extension logins, API keys entered through its UI, and other runtime settings do not persist between checks.
- The extension is downloaded at image build time. Rebuild to update it. To re-download an extension whose URL has not changed, use `sudo docker compose build --pull --no-cache browser-sockpuppet-chrome`, then `sudo docker compose up -d`.
- An extension may be unavailable from Google's download service even when its listing exists. The build stops if it receives no valid package or the package ID does not match the requested listing.
- Poper Blocker's listing currently advertises account signup and a seven-day trial. Downloading its package does not activate a subscription or persist account state between checks.
- Configuration syntax and Python syntax were checked. The example's real CRX3 download was retrieved, its ZIP integrity checked, and its developer key matched to Web Store ID `bkkbcggnhapdmkeljlodobbkopceiche`. The retrieved package was version 8.9.3, Manifest V3, with `incognito: spanning`. Multiple extension installation was checked using that real package and a small local Manifest V3 ZIP fixture, including duplicate handling, stable IDs, and generated browser arguments. Docker was unavailable in the preparation environment, so the image build and extension behavior have not been tested end to end. Verify the selected extensions on a test watch after deployment.

Sources checked on 2026-09-10:

- [Sockpuppetbrowser configuration and CHROME_BIN](https://github.com/dgtlmoon/sockpuppetbrowser)
- [Current sockpuppetbrowser base image](https://github.com/dgtlmoon/sockpuppetbrowser/blob/master/Dockerfile)
- [Sockpuppetbrowser creates a separate browser profile per connection](https://github.com/dgtlmoon/sockpuppetbrowser/blob/master/backend/chrome.py)
- [Changedetection.io creates isolated contexts](https://github.com/dgtlmoon/changedetection.io/blob/master/changedetectionio/content_fetchers/playwright.py)
- [Playwright extension loading documentation](https://playwright.dev/docs/chrome-extensions)
- [Chromium extension incognito preference implementation](https://raw.githubusercontent.com/chromium/chromium/main/extensions/browser/extension_prefs.cc)
- [Chromium CRX3 package format](https://chromium.googlesource.com/chromium/src/+/main/components/crx_file/crx3.proto)
- [The supplied Poper Blocker listing](https://chromewebstore.google.com/detail/pop-up-blocker-for-chrome/bkkbcggnhapdmkeljlodobbkopceiche?hl=en)
- [Chromium accepts multiple extension folders in its loading flags](https://chromium.googlesource.com/chromium/src/+/main/extensions/common/switches.h)
