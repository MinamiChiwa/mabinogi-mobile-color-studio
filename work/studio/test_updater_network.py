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


if __name__=='__main__':unittest.main()
