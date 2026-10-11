"""Release trust must be provisioned before a public bootstrap build.

No test key is trusted by a production client. The release task supplies a
public key here; the private key remains outside source and portable packages.
"""
import json,sys
from pathlib import Path

TRUSTED_KEYS={}
if getattr(sys,'frozen',False):
    public=Path(sys._MEIPASS)/'update-trust.json'
    if public.is_file():
        value=json.loads(public.read_text(encoding='utf-8'))
        if not isinstance(value,dict) or any(not isinstance(k,str) or not isinstance(v,str) or len(v)!=64 for k,v in value.items()):
            raise RuntimeError('Invalid embedded update trust')
        TRUSTED_KEYS={k:bytes.fromhex(v) for k,v in value.items()}
UPDATER_VERSION=1
