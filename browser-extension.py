#!/usr/bin/python3
"""Install extensions at build time and load all of them in each browser."""

import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile

EXTENSION_ROOT = Path('/opt/browser-extension')
URLS_FILE = Path('/usr/local/share/browser-extensions/extensions.txt')
CHROMIUM = '/usr/bin/chromium'


def download_url(url, browser_version=None):
    """Resolve a Web Store listing to Google's CRX endpoint; keep archive URLs."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or 'REPLACE_WITH' in url:
        raise SystemExit('Use HTTPS Chrome Web Store links or ZIP/CRX download URLs in extensions.txt, one per line.')
    if parsed.hostname not in {'chromewebstore.google.com', 'chrome.google.com'}:
        return url, None
    match = re.search(r'/([a-p]{32})/?$', parsed.path)
    if not match:
        raise SystemExit('The Chrome Web Store link must contain a 32-character extension ID.')
    identifier = match.group(1)
    if browser_version is None:
        output = subprocess.check_output([CHROMIUM, '--version'], text=True)
        version_match = re.search(r'\d+\.\d+\.\d+\.\d+', output)
        if not version_match:
            raise SystemExit('Could not determine the installed Chromium version.')
        browser_version = version_match.group()
    query = urllib.parse.urlencode({
        'response': 'redirect',
        'prodversion': browser_version,
        'acceptformat': 'crx2,crx3',
        'x': f'id={identifier}&installsource=ondemand&uc',
    })
    return f'https://clients2.google.com/service/update2/crx?{query}', identifier


def protobuf_fields(message):
    """Read the length-delimited fields needed by Chromium's CRX3 header."""
    position = 0

    def varint():
        nonlocal position
        result = 0
        for shift in range(0, 70, 7):
            if position >= len(message):
                raise ValueError('Truncated CRX3 header.')
            value = message[position]
            position += 1
            result |= (value & 127) << shift
            if not value & 128:
                return result
        raise ValueError('Invalid CRX3 header integer.')

    while position < len(message):
        tag = varint()
        field, wire = tag >> 3, tag & 7
        if not field:
            raise ValueError('Invalid CRX3 header field.')
        if wire == 0:
            varint()
        elif wire in {1, 5}:
            position += 8 if wire == 1 else 4
        elif wire == 2:
            size = varint()
            end = position + size
            if end > len(message):
                raise ValueError('Truncated CRX3 header field.')
            yield field, message[position:end]
            position = end
        else:
            raise ValueError('Unsupported CRX3 header field encoding.')
        if position > len(message):
            raise ValueError('Truncated CRX3 header.')


def unpack_crx(package):
    """Return the ZIP and developer public key, preserving the extension ID.

    Packages are downloaded over HTTPS. This parses key/ID information; it does
    not implement Chrome's CRX signature-verification or Web Store trust checks.
    """
    if not package.startswith(b'Cr24'):
        return package, None
    if len(package) < 12:
        raise ValueError('Truncated CRX package.')
    version = struct.unpack_from('<I', package, 4)[0]
    if version == 2:
        if len(package) < 16:
            raise ValueError('Truncated CRX2 package.')
        key_size, signature_size = struct.unpack_from('<II', package, 8)
        offset = 16 + key_size + signature_size
        if not key_size or offset >= len(package):
            raise ValueError('Invalid CRX2 header size.')
        return package[offset:], package[16:16 + key_size]
    if version != 3:
        raise ValueError(f'Unsupported CRX format version: {version}')

    header_size = struct.unpack_from('<I', package, 8)[0]
    offset = 12 + header_size
    if header_size > 1024 * 1024 or offset >= len(package):
        raise ValueError('Invalid CRX3 header size.')
    proofs, signed_id = [], None
    for field, value in protobuf_fields(package[12:offset]):
        if field in {2, 3}:
            proofs.append(value)
        elif field == 10000:
            signed_id = dict(protobuf_fields(value)).get(1)
    if signed_id is None or len(signed_id) != 16:
        raise ValueError('The CRX3 package has no valid extension ID.')
    for proof in proofs:
        key = dict(protobuf_fields(proof)).get(1)
        if key and hashlib.sha256(key).digest()[:16] == signed_id:
            return package[offset:], key
    raise ValueError('No developer public key matches the CRX3 extension ID.')


def extension_id(manifest, extension_path):
    # Chromium uses the manifest public key when supplied; otherwise the path.
    seed = (base64.b64decode(manifest['key']) if manifest.get('key')
            else str(extension_path.resolve()).encode())
    digest = hashlib.sha256(seed).hexdigest()[:32]
    return ''.join(chr(ord('a') + int(char, 16)) for char in digest)


def configured_urls():
    try:
        raw = URLS_FILE.read_text(encoding='utf-8-sig')
    except OSError as error:
        raise SystemExit(f'Cannot read the extension list at {URLS_FILE}: {error}') from error
    urls = list(dict.fromkeys(
        line.strip() for line in raw.splitlines()
        if line.strip() and not line.lstrip().startswith('#')
    ))
    if not urls:
        raise SystemExit('Add at least one extension link to extensions.txt and rebuild the browser image.')
    return urls


def install_one(source_url, seen_ids):
    url, expected_id = download_url(source_url)
    if expected_id in seen_ids:
        print(f'Skipping duplicate extension: {expected_id}')
        return None
    request = urllib.request.Request(url, headers={'User-Agent': 'sockpuppet-extension-builder'})
    with urllib.request.urlopen(request, timeout=120) as response:
        package = response.read()
    try:
        archive_bytes, public_key = unpack_crx(package)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    if not zipfile.is_zipfile(io.BytesIO(archive_bytes)):
        raise SystemExit('The download did not return a valid ZIP/CRX. The extension may be unavailable through Google\'s download service.')

    with tempfile.TemporaryDirectory() as temp:
        staging = Path(temp)
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            for entry in archive.infolist():
                destination = (staging / entry.filename).resolve()
                if not destination.is_relative_to(staging):
                    raise SystemExit('The extension ZIP contains an invalid path.')
            archive.extractall(staging)

        if (staging / 'manifest.json').is_file():
            manifests = [staging / 'manifest.json']
        else:
            manifests = list(staging.rglob('manifest.json'))
        if len(manifests) != 1:
            raise SystemExit('Provide a ready-to-load extension ZIP containing exactly one manifest.json.')
        manifest = json.loads(manifests[0].read_text(encoding='utf-8-sig'))
        if manifest.get('manifest_version') != 3:
            raise SystemExit('This setup requires a Manifest V3 extension.')
        if manifest.get('incognito') == 'not_allowed':
            raise SystemExit('This extension disallows incognito mode, which changedetection.io uses for checks.')
        if public_key:
            manifest['key'] = base64.b64encode(public_key).decode('ascii')
        if manifest.get('key'):
            # Signed packages have a key-based ID, independent of their folder.
            folder = extension_id(manifest, EXTENSION_ROOT)
        else:
            # Keep unpacked ZIP IDs stable when the list is reordered.
            folder = hashlib.sha256(source_url.encode()).hexdigest()[:24]
        extension_path = EXTENSION_ROOT / 'unpacked' / folder
        identifier = extension_id(manifest, extension_path)
        if expected_id and identifier != expected_id:
            raise SystemExit('The downloaded extension ID does not match the Chrome Web Store link.')
        if identifier in seen_ids:
            print(f'Skipping duplicate extension: {identifier}')
            return None

        extension_path.parent.mkdir(parents=True, exist_ok=True)
        if extension_path.exists():
            shutil.rmtree(extension_path)
        shutil.copytree(manifests[0].parent, extension_path)
        (extension_path / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        # Store verification metadata is reserved by Chrome and is not part of
        # a developer-mode unpacked extension.
        metadata = extension_path / '_metadata'
        if metadata.is_dir():
            shutil.rmtree(metadata)
        elif metadata.exists():
            metadata.unlink()

    name = manifest.get('name', identifier)
    print(f'Installed extension: {name} ({identifier})')
    return {'id': identifier, 'path': str(extension_path), 'name': name}


def install():
    installed, seen_ids = [], set()
    for source_url in configured_urls():
        extension = install_one(source_url, seen_ids)
        if extension:
            installed.append(extension)
            seen_ids.add(extension['id'])
    # Write the index only after every requested extension was processed.
    # The index controls which extensions are loaded, including after removals.
    (EXTENSION_ROOT / 'extensions.json').write_text(json.dumps(installed, indent=2), encoding='utf-8')
    # The image builds as root but sockpuppet runs as the chrome user.
    for item in [EXTENSION_ROOT, *EXTENSION_ROOT.rglob('*')]:
        item.chmod(0o755 if item.is_dir() else 0o644)
    print(f'Configured {len(installed)} extension(s).')


def prepare_profile(arguments, installed):
    profile = None
    for index, argument in enumerate(arguments):
        if argument.startswith('--user-data-dir='):
            profile = Path(argument.split('=', 1)[1])
        elif argument == '--user-data-dir' and index + 1 < len(arguments):
            profile = Path(arguments[index + 1])
    if profile is None:
        raise SystemExit('Sockpuppet must supply a separate --user-data-dir for each browser process.')

    preferences = profile / 'Default' / 'Preferences'
    preferences.parent.mkdir(parents=True, exist_ok=True)
    settings = json.loads(preferences.read_text()) if preferences.exists() else {}
    extensions = settings.setdefault('extensions', {})
    extensions.setdefault('ui', {})['developer_mode'] = True
    extension_settings = extensions.setdefault('settings', {})
    for extension in installed:
        extension_settings.setdefault(extension['id'], {})['incognito'] = True
    preferences.write_text(json.dumps(settings), encoding='utf-8')
    preferences.chmod(0o600)


def launch():
    arguments = sys.argv[1:]
    if '--version' not in arguments and '--help' not in arguments:
        installed = json.loads((EXTENSION_ROOT / 'extensions.json').read_text())
        prepare_profile(arguments, installed)
        extension_paths = ','.join(extension['path'] for extension in installed)
        arguments.extend([
            f'--load-extension={extension_paths}',
            f'--disable-extensions-except={extension_paths}',
        ])
    os.execv(CHROMIUM, [CHROMIUM, *arguments])


if __name__ == '__main__':
    if sys.argv[1:] == ['--install']:
        install()
    else:
        launch()
