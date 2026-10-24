import hashlib
import tempfile
import unittest
from pathlib import Path

from updater.download import download_bytes


class Response:
    def __init__(self,status,body,headers=None):self.status=status;self.body=body;self.headers=headers or {}
    def iter_bytes(self,chunk=65536):yield self.body


class Client:
    def __init__(self,response):self.response=response;self.calls=[]
    def get(self,url,headers=None,timeout=None):self.calls.append((url,headers or {}));return self.response


class NetworkTests(unittest.TestCase):
    def test_prerelease_channel_finds_highest_compatible_signed_release(self):
        from updater.discovery import check_release,API,BASE
        from _updater_test_support import signed,KEYS
        import json
        releases=[];payloads={}
        for version,minimum in (('0.5.0rc1',2),('0.4.3rc1',1)):
            tag='v'+version;url=BASE+'/releases/download/'+tag+'/'
            releases.append(dict(tag_name=tag,prerelease=True,draft=False,assets=[dict(name=n,browser_download_url=url+n) for n in ('update-manifest.json','update-manifest.sig')]))
            raw,sig=signed(version=version,channel='prerelease',minimum_updater=minimum)
            payloads[url+'update-manifest.json']=raw;payloads[url+'update-manifest.sig']=sig
        class GitHubFixture:
            def get(self,url,headers=None,timeout=None):return Response(200,json.dumps(releases).encode() if url.startswith(API) else payloads[url])
        result=check_release('0.4.2','prerelease',{},lambda:False,client=GitHubFixture(),trusted_keys=KEYS)
        self.assertEqual(result.status,'available');self.assertEqual(result.manifest.version,'0.4.3rc1')
    def test_cancelled_stream_keeps_hash_bound_partial_and_can_resume(self):
        from updater.download import DownloadCancelled
        with tempfile.TemporaryDirectory() as temp:
            partial=Path(temp)/'blob.zip.part';payload=b'abcdef';stopped=[False]
            class Chunks(Response):
                def iter_bytes(self,chunk=65536):
                    yield b'abc';stopped[0]=True;yield b'def'
            with self.assertRaises(DownloadCancelled):
                download_bytes(Client(Chunks(200,b'',{'ETag':'same'})),'url',partial,6,
                    hashlib.sha256(payload).hexdigest(),cancel=lambda:stopped[0])
            self.assertEqual(partial.read_bytes(),b'abc')
            client=Client(Response(206,b'def',{'Content-Range':'bytes 3-5/6','ETag':'same'}))
            path=download_bytes(client,'url',partial,6,hashlib.sha256(payload).hexdigest())
            self.assertEqual(path.read_bytes(),payload)
            self.assertEqual(client.calls[0][1]['If-Range'],'same')

    def test_stale_complete_partial_with_416_is_replaced(self):
        with tempfile.TemporaryDirectory() as temp:
            partial=Path(temp)/'blob.part';partial.write_bytes(b'bad');calls=[]
            class RetryClient:
                def get(self,*args,**kw):
                    calls.append(kw);return Response(416,b'') if len(calls)==1 else Response(200,b'new')
            result=download_bytes(RetryClient(),'url',partial,3,hashlib.sha256(b'new').hexdigest())
            self.assertEqual(result.read_bytes(),b'new')

    def test_304_without_signed_cache_refetches_manifest(self):
        from updater.discovery import check_release
        from _updater_test_support import signed,KEYS
        raw,sig=signed();calls=[]
        class CacheClient:
            def get(self,url,headers=None,timeout=None):
                calls.append(url)
                return Response(304,b'') if len(calls)==1 else Response(200,sig if url.endswith('.sig') else raw)
        result=check_release('0.4.2','stable',{'etag':'old'},lambda:False,client=CacheClient(),
            trusted_keys=KEYS,manifest_url='https://example.test/update-manifest.json')
        self.assertEqual(result.status,'available');self.assertEqual(len(calls),3)

    def test_416_complete_partial_is_verified_without_truncation(self):
        with tempfile.TemporaryDirectory() as temp:
            partial=Path(temp)/'blob.part';payload=b'complete';partial.write_bytes(payload)
            client=Client(Response(416,b''))
            result=download_bytes(client,'url',partial,len(payload),hashlib.sha256(payload).hexdigest())
            self.assertEqual(result.read_bytes(),payload)

    def test_206_wrong_total_and_oversize_body_never_complete(self):
        from updater.download import DownloadError
        for response in (Response(206,b'abc',{'Content-Range':'bytes 0-2/99'}),Response(200,b'too large')):
            with self.subTest(status=response.status),tempfile.TemporaryDirectory() as temp:
                with self.assertRaises(DownloadError):
                    download_bytes(Client(response),'url',Path(temp)/'b.part',3,hashlib.sha256(b'abc').hexdigest())

    def test_discovery_fetches_detached_signature_and_rejects_replay(self):
        from updater.discovery import check_release
        from _updater_test_support import signed,KEYS
        raw,sig=signed()
        class DiscoveryClient:
            def get(self,url,headers=None,timeout=None):
                return Response(200,sig if url.endswith('.sig') else raw,{'ETag':'release2'})
        result=check_release('0.4.2','stable',{},lambda:False,client=DiscoveryClient(),
            trusted_keys=KEYS,manifest_url='https://example.test/update-manifest.json')
        self.assertEqual(result.status,'available')
        stale=check_release('0.4.2','stable',{'sequence':3},lambda:False,client=DiscoveryClient(),
            trusted_keys=KEYS,manifest_url='https://example.test/update-manifest.json')
        self.assertEqual(stale.reason_code,'replay')
    def test_range_ignored_restarts_instead_of_appending(self):
        with tempfile.TemporaryDirectory() as temp:
            partial=Path(temp)/'blob.part';partial.write_bytes(b'old-prefix');payload=b'new-complete'
            client=Client(Response(200,payload,{'ETag':'new'}))
            result=download_bytes(client,'https://example.test/blob',partial,len(payload),hashlib.sha256(payload).hexdigest())
            self.assertEqual(result.read_bytes(),payload);self.assertFalse(partial.exists());self.assertEqual(len(client.calls),1)

    def test_matching_206_range_appends(self):
        with tempfile.TemporaryDirectory() as temp:
            partial=Path(temp)/'blob.part';partial.write_bytes(b'old-');payload=b'old-complete'
            client=Client(Response(206,b'complete',{'Content-Range':'bytes 4-11/12'}))
            result=download_bytes(client,'url',partial,len(payload),hashlib.sha256(payload).hexdigest())
            self.assertEqual(result.read_bytes(),payload)


class RateLimitDiscoveryTests(unittest.TestCase):
    def test_stable_default_checks_direct_download_without_using_api(self):
        from updater.discovery import check_release,API
        from _updater_test_support import KEYS
        client,latest=self.fixture()
        result=check_release('0.4.2','stable',{},lambda:False,client=client,trusted_keys=KEYS)
        self.assertEqual(result.status,'available')
        self.assertEqual(client.calls,[latest,latest.removesuffix('.json')+'.sig'])

    def test_direct_http_failure_uses_api_and_pinned_signed_assets(self):
        from updater.discovery import check_release,API,BASE
        from _updater_test_support import KEYS,signed,entry
        import json
        raw,sig=signed([entry()]);calls=[]
        prefix=BASE+'/releases/download/v0.4.3/'
        names=('update-manifest.json','update-manifest.sig',entry()['blob'])
        release=dict(tag_name='v0.4.3',draft=False,prerelease=False,
            assets=[dict(name=n,browser_download_url=prefix+n) for n in names])
        class Fixture:
            def get(self,url,headers=None,timeout=None):
                calls.append(url)
                if '/latest/download/' in url:return Response(503,b'')
                if url==API+'/latest':return Response(200,json.dumps(release).encode())
                return Response(200,sig if url.endswith('.sig') else raw)
        result=check_release('0.4.2','stable',{},lambda:False,client=Fixture(),trusted_keys=KEYS)
        self.assertEqual(result.status,'available')
        self.assertEqual(calls[1],API+'/latest')
        self.assertTrue(all(url.startswith(prefix) for url in result.assets.values()))

    def test_invalid_direct_signature_never_falls_back_to_api(self):
        from updater.discovery import check_release,API
        from _updater_test_support import KEYS
        client,_=self.fixture(signature_valid=False)
        result=check_release('0.4.2','stable',{},lambda:False,client=client,trusted_keys=KEYS)
        self.assertEqual((result.status,result.reason_code),('invalid','signature'))
        self.assertNotIn(API+'/latest',client.calls)

    def test_rate_limited_api_is_not_retried_when_direct_is_down(self):
        from updater.discovery import check_release,API
        from _updater_test_support import KEYS
        from unittest.mock import patch
        calls=[]
        class Fixture:
            def get(self,url,headers=None,timeout=None):
                calls.append(url)
                return Response(429,b'{}',{'Retry-After':'30'}) if url==API+'/latest' else Response(503,b'')
        cache={}
        with patch('updater.discovery.time.time',return_value=1000):
            result=check_release('0.4.2','stable',cache,lambda:False,client=Fixture(),trusted_keys=KEYS)
        self.assertEqual(result.reason_code,'rate_limit')
        with patch('updater.discovery.time.time',return_value=1001):
            check_release('0.4.2','stable',cache,lambda:False,client=Fixture(),trusted_keys=KEYS)
        self.assertEqual(calls.count(API+'/latest'),1)
        with patch('updater.discovery.time.time',return_value=1031):
            check_release('0.4.2','stable',cache,lambda:False,client=Fixture(),trusted_keys=KEYS)
        self.assertEqual(calls.count(API+'/latest'),2)

    def fixture(self,status=403,headers=None,signature_valid=True):
        from updater.discovery import API,BASE
        from _updater_test_support import signed,entry
        raw,sig=signed([entry()])
        latest=BASE+'/releases/latest/download/update-manifest.json'
        responses={API+'/latest':Response(status,b'{"message":"API rate limit exceeded"}',
            headers or {'X-RateLimit-Reset':'2000'}),
            latest:Response(200,raw),latest.removesuffix('.json')+'.sig':Response(200,sig if signature_valid else b'x'*64)}
        class Fixture:
            def __init__(self):self.calls=[]
            def get(self,url,headers=None,timeout=None):
                self.calls.append(url)
                return responses[url]
        return Fixture(),latest

    def test_stable_rate_limit_uses_signed_official_fallback_and_pinned_blob_urls(self):
        from updater.discovery import check_release,BASE
        from _updater_test_support import KEYS
        for status in (403,429):
            with self.subTest(status=status):
                client,latest=self.fixture(status);cache={}
                result=check_release('0.4.2','stable',cache,lambda:False,client=client,trusted_keys=KEYS)
                self.assertEqual(result.status,'available')
                self.assertEqual(result.manifest.version,'0.4.3')
                self.assertIn(latest,client.calls)
                self.assertTrue(result.assets)
                self.assertTrue(all(url.startswith(BASE+'/releases/download/v0.4.3/')
                                    for url in result.assets.values()))

    def test_active_api_cooldown_checks_directly_and_still_detects_update(self):
        from updater.discovery import check_release,API
        from _updater_test_support import KEYS
        from unittest.mock import patch
        client,latest=self.fixture();cache={}
        with patch('updater.discovery.time.time',return_value=1000):
            check_release('0.4.2','stable',cache,lambda:False,client=client,trusted_keys=KEYS)
            client.calls.clear()
            result=check_release('0.4.2','stable',cache,lambda:False,client=client,trusted_keys=KEYS)
        self.assertEqual(result.status,'available')
        self.assertNotIn(API+'/latest',client.calls)
        self.assertIn(latest,client.calls)

    def test_direct_success_does_not_need_api_after_cooldown_expires(self):
        from updater.discovery import check_release,API
        from _updater_test_support import KEYS
        from unittest.mock import patch
        client,_=self.fixture(429,{'Retry-After':'30'});cache={}
        with patch('updater.discovery.time.time',return_value=1000):
            check_release('0.4.2','stable',cache,lambda:False,client=client,trusted_keys=KEYS)
        client.calls.clear()
        with patch('updater.discovery.time.time',return_value=1031):
            result=check_release('0.4.2','stable',cache,lambda:False,client=client,trusted_keys=KEYS)
        self.assertEqual(result.status,'available')
        self.assertNotIn(API+'/latest',client.calls)

    def test_fallback_still_rejects_bad_signature_and_signed_replay(self):
        from updater.discovery import check_release
        from _updater_test_support import KEYS
        for cache,valid,want in (({},False,'signature'),({'sequence':3},True,'replay')):
            with self.subTest(reason=want):
                client,_=self.fixture(signature_valid=valid)
                result=check_release('0.4.2','stable',cache,lambda:False,client=client,trusted_keys=KEYS)
                self.assertEqual((result.status,result.reason_code),('invalid',want))

    def test_prerelease_rate_limit_never_switches_to_stable(self):
        from updater.discovery import check_release,API
        from _updater_test_support import KEYS
        calls=[]
        class Fixture:
            def get(self,url,headers=None,timeout=None):
                calls.append(url)
                return Response(429,b'{}',{'Retry-After':'30'})
        result=check_release('0.4.2','prerelease',{},lambda:False,client=Fixture(),trusted_keys=KEYS)
        self.assertEqual((result.status,result.reason_code),('unavailable','rate_limit'))
        self.assertEqual(calls,[API+'?per_page=100'])

    def test_cancellation_after_direct_response_never_requests_api(self):
        from updater.discovery import check_release,API
        from _updater_test_support import KEYS
        stopped=[False];calls=[]
        class CancelResponse(Response):
            def iter_bytes(self):
                yield b'{}'
                stopped[0]=True
        class Fixture:
            def get(self,url,headers=None,timeout=None):
                calls.append(url)
                return CancelResponse(403,b'')
        result=check_release('0.4.2','stable',{},lambda:stopped[0],client=Fixture(),trusted_keys=KEYS)
        self.assertEqual(result.status,'cancelled')
        from updater.discovery import LATEST_MANIFEST
        self.assertEqual(calls,[LATEST_MANIFEST])

    def test_direct_304_without_signed_cache_refetches_directly(self):
        from updater.discovery import check_release,API
        from _updater_test_support import KEYS
        delegate,latest=self.fixture();calls=[]
        class Fixture:
            def get(self,url,headers=None,timeout=None):
                calls.append(url)
                return Response(304,b'') if len(calls)==1 else delegate.get(url,headers,timeout)
        result=check_release('0.4.2','stable',{'api_etag':'old'},lambda:False,client=Fixture(),trusted_keys=KEYS)
        self.assertEqual(result.status,'available')
        self.assertEqual(calls[:2],[latest]*2)
        self.assertIn(latest,calls)

    def test_stale_api_release_does_not_override_new_signed_fallback_version(self):
        from updater.discovery import check_release,BASE
        from _updater_test_support import KEYS
        cache={'release':{'tag_name':'v0.4.1','assets':[]},'api_etag':'old'}
        client,_=self.fixture()
        result=check_release('0.4.2','stable',cache,lambda:False,client=client,trusted_keys=KEYS)
        self.assertEqual(result.status,'available')
        self.assertEqual(result.manifest.version,'0.4.3')
        self.assertTrue(all('/v0.4.3/' in url for url in result.assets.values()))


if __name__=='__main__':unittest.main()
