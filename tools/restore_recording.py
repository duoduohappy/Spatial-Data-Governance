"""Restore the large evidence recording from GitHub transport parts; verify exact bytes."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
VIDEO=ROOT/'acceptance/stage-3/browser/2026-10-27T00-19-03-715Z/video/page@6d515e1b53cbdcdf256ee723cfa22cae.webm'
def restore():
    manifest=VIDEO.with_suffix(VIDEO.suffix+'.parts.json')
    if VIDEO.exists():
        return False
    if not manifest.exists():
        raise FileNotFoundError('Recording and transport manifest are both absent')
    spec=json.loads(manifest.read_text(encoding='utf-8'))
    parts=[]
    for i,entry in enumerate(spec['parts']):
        name=VIDEO.name+'.part%03d'%i
        if entry['name']!=name: raise ValueError('Invalid recording part path')
        data=(VIDEO.parent/name).read_bytes()
        if hashlib.sha256(data).hexdigest()!=entry['sha256']: raise ValueError('Recording part hash mismatch')
        parts.append(data)
    data=b''.join(parts)
    if len(data)!=spec['bytes'] or hashlib.sha256(data).hexdigest()!=spec['sha256']:
        raise ValueError('Recording hash mismatch')
    with VIDEO.open('xb') as stream: stream.write(data)
    return True
if __name__=='__main__':
    print('Recording restored and verified' if restore() else 'Original recording already present')
