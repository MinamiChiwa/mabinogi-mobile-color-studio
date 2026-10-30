"""System proxy/certificates with separate connect/read timeouts and HTTPS redirects."""
from urllib.parse import urlparse
import httpx,ssl,os,time

# Release files are fetched through this mirror first. The mirror is only a
# transport: manifests are Ed25519-verified and every blob is SHA-256 checked,
# so a mirror cannot change what gets installed.
MIRROR='https://v6.gh-proxy.org/'
MIRROR_RETRY_AFTER=600

ALLOWED_HOSTS={'api.github.com','github.com','objects.githubusercontent.com','release-assets.githubusercontent.com',
    'github-releases.githubusercontent.com',urlparse(MIRROR).hostname}

class Response:
    def __init__(self,response):self.response=response;self.status=response.status_code;self.headers=response.headers
    def iter_bytes(self):
        try:yield from self.response.iter_bytes(65536)
        finally:self.close()
    def close(self):self.response.close()

class GitHubClient:
    def get(self,url,headers=None,timeout=(5,15)):
        certificate_file=os.environ.get('SSL_CERT_FILE')
        certificates=ssl.create_default_context(cafile=certificate_file) if certificate_file else ssl.create_default_context()
        client=httpx.Client(timeout=httpx.Timeout(timeout[1],connect=timeout[0]),verify=certificates,trust_env=True,follow_redirects=False,
            headers={'User-Agent':'ColorStudio-Updater/1','Accept':'application/vnd.github+json'})
        try:
            for _ in range(6):
                parsed=urlparse(url)
                if parsed.scheme!='https' or parsed.hostname not in ALLOWED_HOSTS or parsed.port not in (None,443) or parsed.username:
                    raise ValueError('Untrusted update download URL')
                response=client.send(client.build_request('GET',url,headers=headers or {}),stream=True)
                if response.status_code not in (301,302,303,307,308):
                    wrapped=Response(response);original=wrapped.close
                    def close(original=original,client=client):original();client.close()
                    wrapped.close=close;return wrapped
                target=response.headers.get('Location','');response.close();url=__import__('urllib.parse',fromlist=['urljoin']).urljoin(url,target)
            raise ValueError('Too many redirects')
        except BaseException:client.close();raise

class MirrorFirstClient:
    """github.com release URLs try the mirror first and fall back to GitHub directly.

    A mirror failure (connection error, unexpected status, or a broken body the
    downloader reports) switches to direct GitHub for MIRROR_RETRY_AFTER seconds.
    The GitHub API is never mirrored.
    """
    def __init__(self,direct=None,mirror=MIRROR,clock=time.monotonic):
        self.direct=direct or GitHubClient();self.mirror=mirror;self.clock=clock;self._mirror_down_until=0.
    def mirrored(self,url):
        return url.startswith('https://github.com/') and self.clock()>=self._mirror_down_until
    def report_failure(self,url):
        if url.startswith('https://github.com/'):self._mirror_down_until=self.clock()+MIRROR_RETRY_AFTER
    def get(self,url,headers=None,timeout=(5,15)):
        if self.mirrored(url):
            try:
                response=self.direct.get(self.mirror+url,headers,timeout=(min(timeout[0],4),min(timeout[1],8)))
                if int(response.status) in (200,206,304,416):return response
                response.close()
            except Exception:pass
            self.report_failure(url)
        return self.direct.get(url,headers,timeout)
