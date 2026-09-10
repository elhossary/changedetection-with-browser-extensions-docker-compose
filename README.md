# Changedetection.io instance with SockpuppetBrowser bundled with Chrome extensions (Docker Compose)

Run [changedetection.io](https://github.com/dgtlmoon/changedetection.io) with a
[SockpuppetBrowser](https://github.com/dgtlmoon/sockpuppetbrowser) image that has your own Chrome
extensions loaded, such as ad/consent blockers, fingerprint tools, captcha solvers, or anything else you need a watch to see the page through.

**This repo exists for one extension: [NopeCHA](https://chromewebstore.google.com/detail/nopecha-captcha-solver/dknlfmjaanfblgfdfebhijalfmhmjjjo).**
Watches that hit a captcha or an anti-bot interstitial return the challenge page instead of the
content you are watching, and there is no way to load a solver into SockpuppetBrowser out of the
box. NopeCHA is first in `extensions.txt`; the fingerprint and consent extensions alongside it are
there to keep the browser from being flagged in the first place, so the solver is needed less
often.

Extensions are listed one URL per line in `extensions.txt`, downloaded and unpacked at image build
time, and loaded into every browser context changedetection.io opens, including incognito ones.

## Requirements

- Docker with the Compose plugin
- An extension that ships as Manifest V3

## Quick start

```bash
https://github.com/elhossary/changedetection-with-browser-extensions-docker-compose.git
cd changedetection-with-browser-extensions-docker-compose
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
https://chromewebstore.google.com/detail/nopecha-captcha-solver/dknlfmjaanfblgfdfebhijalfmhmjjjo
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
  configuration are largely unusable here. This applies to NopeCHA too: only what it does without
  configuration is available, since a key entered on its options page is gone by the next check.
- An extension may still misbehave in an isolated/incognito context even with permission granted.
- An extension may be unavailable from Google's download service even when its listing page
  exists.
- This is a custom integration, not a built-in SockpuppetBrowser setting; nothing here is
  supported by the upstream projects.

Verify your selected extensions against a test watch after deploying.

## Disclaimer

This project is provided for lawful use only, and is used entirely at your own risk.

**No affiliation.** This repository is an independent, unofficial integration. It is not
affiliated with, endorsed by, or supported by changedetection.io, SockpuppetBrowser, NopeCHA,
Google, or the authors of any extension listed in `extensions.txt`. All trademarks and product
names are the property of their respective owners. Each extension is distributed by its own
publisher under its own terms and privacy policy; this repository merely downloads and unpacks
what you point it at, and does not redistribute, modify, or vouch for any extension's code.

**Your responsibility to comply.** You alone are responsible for how you use this software and for
determining whether that use is lawful in your jurisdiction. Automated access, captcha or
anti-bot circumvention, and scraping may be restricted by a site's terms of service, by
robots.txt, by applicable computer-misuse, contract, copyright, or data-protection law, or by all
of these. Obtain any authorisation you need before pointing a watch at a site you do not control,
and respect the operator's stated access policies.

**Security.** Extensions run with broad access to every page the browser loads. Downloads are made
over HTTPS and package identifiers are checked, but CRX signatures are not cryptographically
verified and no review of extension code is performed. Install only extensions you have
independently assessed and trust.

**No warranty and no liability.** As stated in Sections 7 and 8 of the [LICENSE](LICENSE), the
software is provided on an "as is" basis, without warranties or conditions of any kind, express or
implied, and no contributor is liable for any damages arising from its use. Nothing in this
repository constitutes legal advice.

## Third-party components

This repository contains no third-party code. It ships one Python script (standard library only),
a Dockerfile, a Compose file, and a list of URLs. Everything else is fetched on your machine at
build time and carries its own licence and terms:

| Component | Pulled from |
| --- | --- |
| changedetection.io | `ghcr.io/dgtlmoon/changedetection.io:latest` |
| SockpuppetBrowser | `dgtlmoon/sockpuppetbrowser:latest` (base image) |
| Chromium and `ca-certificates` | Debian package repositories |
| Each extension in `extensions.txt` | its publisher, via the Chrome Web Store or the URL you supply |

Note that a container image you build from this repository *does* contain those components. If
you publish such an image, their licences and terms travel with it, and this repository's licence
does not cover them.

## License

Apache License 2.0 — see [LICENSE](LICENSE).

Copyright 2026 Muhammad Elhossary.
