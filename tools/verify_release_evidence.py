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
    review_set=ROOT/'eval/review-dev-v1/manifest.json'
    if review_set.exists():
        review=json.loads(review_set.read_text(encoding='utf-8'))
        for case in review['cases']:
            assert digest(ROOT/'eval/review-dev-v1'/case['id']/'delivery_spec.md')==case['document_sha256'],case['id']
        for version in ('v1','v2'):
            record=read('acceptance/v06/review-ablation-'+version+'/results.json')
            assert digest(review_set)==record['manifest_sha256'],'Review dataset manifest changed'
    restore()
    media=read('acceptance/stage-3/browser/recording-metadata.json')
    assert digest(VIDEO)==media['sha256'], 'Recording bytes changed'
    print(json.dumps({'status':'PASS','frozen_documents':len(manifest['cases']),'browser_attachments':2,'recording_sha256_verified':True}))
if __name__=='__main__': main()
