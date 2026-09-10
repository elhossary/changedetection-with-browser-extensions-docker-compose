# Chrome extensions for SockpuppetBrowser

Run [changedetection.io](https://github.com/dgtlmoon/changedetection.io) with a
[SockpuppetBrowser](https://github.com/dgtlmoon/sockpuppetbrowser) image that has your own Chrome
extensions loaded — ad/consent blockers, fingerprint tools, captcha solvers, or anything else you
need a watch to see the page through.

Extensions are listed one URL per line in `extensions.txt`, downloaded and unpacked at image build
time, and loaded into every browser context changedetection.io opens, including incognito ones.

## Requirements

- Docker with the Compose plugin
- An extension that ships as Manifest V3

## Quick start

```bash
git clone https://github.com/<you>/sockpuppet-extension-config.git
cd sockpuppet-extension-config
sudo docker compose build --pull browser-sockpuppet-chrome
sudo docker compose up -d
```

changedetection.io is then on `http://127.0.0.1:5000`. In a watch, set the fetch method to
**Playwright/Chrome** — extensions apply only to that method, and only to watches using this
browser URL.

If you already run changedetection.io, copy `Dockerfile.browser`, `browser-extension.py`, and
`extensions.txt` next to your existing Compose file and merge the `build:` block from
`docker-compose.yml` into your browser service:

```yaml
build:
  context: .
  dockerfile: Dockerfile.browser
```

Keep the same Compose directory and project name so Docker keeps using your existing
`changedetection-data` volume.

## Choosing extensions

`extensions.txt` is plain text — one complete URL per line, no quotes, no YAML dashes. Blank lines
and lines starting with `#` are ignored.

```text
https://chromewebstore.google.com/detail/consent-o-matic/mdjildafknihdffpkfmmpnpoiajfjnjd
# https://example.com/my-extension.zip
```

Both Chrome Web Store listing links and direct HTTPS ZIP/CRX downloads work, and the two may be
mixed. Listing query parameters such as `?hl=en` are ignored. Duplicate links, and different links
resolving to the same extension ID, are installed once.

Each extension must:

- be Manifest V3 (a source archive needing a build step will not work);
- contain exactly one `manifest.json`, at the archive root or in a single enclosing directory;
- not set `incognito: not_allowed` — changedetection.io checks pages in isolated contexts.

The build fails on the first extension that cannot be downloaded or validated, rather than
producing an image with a partial list.

## Applying changes

The list is baked into the image, so editing `extensions.txt` needs a rebuild and container
recreation. A restart alone changes nothing.

```bash
sudo docker compose build --pull browser-sockpuppet-chrome
sudo docker compose up -d
```

To re-download an extension whose URL has not changed, add `--no-cache` to the build.

## How it works

The image is built from `dgtlmoon/sockpuppetbrowser:latest` and installs Debian Chromium.
Branded Chrome restricts the command-line flags used to load unpacked extensions; Chromium does
not, which is why it is swapped in.

At build time, `browser-extension.py` reads `extensions.txt`. For a Web Store link it extracts the
extension ID, asks Google's update service for the package matching the installed Chromium
version, and unpacks the CRX (CRX2 and CRX3 both supported). The developer public key is written
into `manifest.json` so the unpacked extension keeps its original Web Store ID, which is then
checked against the ID in the link. Each extension lands in its own folder under
`/opt/browser-extension/unpacked`.

`CHROME_BIN` points at the same script, which SockpuppetBrowser invokes for every browser process.
On each launch it writes `incognito: true` for every installed extension into that process's own
profile, appends `--load-extension` and `--disable-extensions-except` for all installed folders,
and execs Chromium. SockpuppetBrowser's separate-profile-per-connection behaviour is preserved.

Downloads are over HTTPS and package IDs are checked, but the CRX signature itself is not
cryptographically verified. Install extensions you trust.

## Limitations

- Browser profiles are temporary. Extension logins, API keys, and settings entered through an
  extension's UI do not persist between checks — extensions requiring an account or in-UI
  configuration are largely unusable here.
- An extension may still misbehave in an isolated/incognito context even with permission granted.
- An extension may be unavailable from Google's download service even when its listing page
  exists.
- This is a custom integration, not a built-in SockpuppetBrowser setting; nothing here is
  supported by the upstream projects.

Verify your selected extensions against a test watch after deploying.

## License

MIT — see [LICENSE](LICENSE).
