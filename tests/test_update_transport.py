"""Online updates: mirror first, direct GitHub as automatic fallback, signed content only."""
import hashlib

from signing import KEYS, entry, signed
from updater.discovery import LATEST_MANIFEST, check_release
from updater.download import download_bytes
from updater.http_client import MIRROR, MIRROR_RETRY_AFTER, MirrorFirstClient

RELEASE = 'https://github.com/MinamiChiwa/mabinogi-mobile-color-studio/releases/download/v0.5.1/'


class Response:
    def __init__(self, status=200, body=b'', headers=None):
        self.status = status
        self.body = body
        self.headers = headers or {}

    def iter_bytes(self):
        yield self.body

    def close(self):
        pass


class Transport:
    """Stands in for GitHubClient: serves a URL table and records every request."""

    def __init__(self, routes):
        self.routes = routes
        self.requests = []

    def get(self, url, headers=None, timeout=(5, 15)):
        self.requests.append(url)
        route = self.routes.get(url, Response(404))
        if isinstance(route, Exception):
            raise route
        return route


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_release_files_go_through_mirror_first():
    url = RELEASE + 'update-manifest.json'
    transport = Transport({MIRROR + url: Response(body=b'via mirror')})
    response = MirrorFirstClient(transport).get(url)
    assert response.body == b'via mirror'
    assert transport.requests == [MIRROR + url]


def test_mirror_failure_falls_back_to_github_and_stays_direct_for_a_while():
    url = RELEASE + 'update-manifest.json'
    clock = Clock()
    transport = Transport({MIRROR + url: OSError('mirror down'), url: Response(body=b'direct')})
    client = MirrorFirstClient(transport, clock=clock)

    assert client.get(url).body == b'direct'
    assert client.get(url).body == b'direct'
    assert transport.requests == [MIRROR + url, url, url]

    clock.now = MIRROR_RETRY_AFTER + 1
    client.get(url)
    assert transport.requests[-2:] == [MIRROR + url, url]


def test_mirror_error_status_falls_back_to_github():
    url = RELEASE + 'update-manifest.sig'
    transport = Transport({MIRROR + url: Response(502), url: Response(body=b'sig')})
    assert MirrorFirstClient(transport).get(url).body == b'sig'


def test_github_api_is_never_mirrored():
    url = 'https://api.github.com/repos/MinamiChiwa/mabinogi-mobile-color-studio/releases/latest'
    transport = Transport({url: Response(body=b'{}')})
    MirrorFirstClient(transport).get(url)
    assert transport.requests == [url]


def test_corrupt_mirror_download_is_retried_from_github(tmp_path):
    payload = b'x' * 4096
    url = RELEASE + 'blob-test.zip'
    transport = Transport({MIRROR + url: Response(body=b'y' * 4096), url: Response(body=payload)})
    result = download_bytes(MirrorFirstClient(transport), url, tmp_path / 'blob.zip.part',
                            len(payload), hashlib.sha256(payload).hexdigest())
    assert result.read_bytes() == payload
    assert transport.requests == [MIRROR + url, url]


def test_check_finds_signed_release_through_mirror():
    raw, signature = signed([entry()], version='0.5.1', release_sequence=3)
    sig_url = LATEST_MANIFEST.removesuffix('.json') + '.sig'
    transport = Transport({MIRROR + LATEST_MANIFEST: Response(body=raw),
                           MIRROR + sig_url: Response(body=signature)})
    result = check_release('0.5.0', 'stable', {}, lambda: False,
                           client=MirrorFirstClient(transport), trusted_keys=KEYS)
    assert result.status == 'available' and result.manifest.version == '0.5.1'
    # Blob URLs stay canonical GitHub URLs; the client decides how to fetch them.
    assert all(url.startswith(RELEASE) for url in result.assets.values())


def test_tampered_manifest_from_mirror_is_rejected():
    raw, signature = signed([entry()], version='0.5.1', release_sequence=3)
    sig_url = LATEST_MANIFEST.removesuffix('.json') + '.sig'
    transport = Transport({MIRROR + LATEST_MANIFEST: Response(body=raw.replace(b'0.5.1', b'0.5.2')),
                           MIRROR + sig_url: Response(body=signature)})
    result = check_release('0.5.0', 'stable', {}, lambda: False,
                           client=MirrorFirstClient(transport), trusted_keys=KEYS)
    assert result.status == 'invalid'
