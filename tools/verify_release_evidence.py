"""Verify byte-sensitive release evidence after a fresh cross-platform Git checkout."""
from pathlib import Path
import hashlib,json
from restore_recording import restore,VIDEO
ROOT=Path(__file__).resolve().parents[1]
def read(name): return json.loads((ROOT/name).read_text(encoding='utf-8'))
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    manifest_path=ROOT/'eval/heldout-v1/manifest.json'
    manifest=read('eval/heldout-v1/manifest.json')
    results=read('acceptance/stage-4/local-model/heldout-v1/results.json')
    assert digest(manifest_path)==results['manifest_sha256'], 'Frozen manifest bytes changed'
    for case in manifest['cases']:
        assert digest(ROOT/'eval/heldout-v1'/case['id']/'delivery_spec.md')==case['document_sha256'], case['id']
    for entry in read('acceptance/stage-3/iab-downloads/results.json')['files']:
        assert digest(ROOT/'acceptance/stage-3/iab-downloads'/('report.'+entry['type']))==entry['sha256'], entry['type']
    restore()
    media=read('acceptance/stage-3/browser/recording-metadata.json')
    assert digest(VIDEO)==media['sha256'], 'Recording bytes changed'
    print(json.dumps({'status':'PASS','frozen_documents':len(manifest['cases']),'browser_attachments':2,'recording_sha256_verified':True}))
if __name__=='__main__': main()
