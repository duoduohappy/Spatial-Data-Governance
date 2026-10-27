"""Source release audit and source-only ZIP. Excludes runtime data and Git internals."""
from pathlib import Path
import hashlib,json,re,sys,zipfile
ROOT=Path(__file__).resolve().parents[1]
EXCLUDED={'.git','.venv','work','node_modules','__pycache__','.pytest_cache','.idea','.vscode','dist','build'}
def files():
    for p in ROOT.rglob('*'):
        rel=p.relative_to(ROOT)
        if p.is_file() and not any(x in EXCLUDED for x in rel.parts) and not (rel.parts[:2]==('eval','generated')):
            yield p,rel

def check():
    issues=[];count=0
    for p,r in files():
        count+=1
        if p.name=='.env' or p.suffix in ('.key','.pem','.pfx','.sqlite'):issues.append({'path':r.as_posix(),'issue':'credential/runtime file'})
        if p.suffix.lower() in ('.md','.py','.json','.txt','.yaml','.yml','.js','.html','.toml','.cmd','.ps1'):
            text=p.read_text(encoding='utf-8-sig',errors='strict')
            for pat in (r'sk-[A-Za-z0-9_-]{25,}',r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',r'gh[pousr]_[A-Za-z0-9]{30,}'):
                if re.search(pat,text):issues.append({'path':r.as_posix(),'issue':'possible secret pattern'})
    required=['README.md','LICENSE','THIRD_PARTY.md','docs/RELEASE_STATUS.md','acceptance/stage-5/STATUS.json']
    for name in required:
        if not (ROOT/name).exists():issues.append({'path':name,'issue':'required release file missing'})
    result={'source_files':count,'issues':issues,'status':'PASS' if not issues else 'FAIL',
            'scope':'Heuristic current source scan only. Not a guarantee; Git history is not distributed in ZIP.'}
    print(json.dumps(result,ensure_ascii=False,indent=2));return result

def main():
    r=check()
    if r['issues']:return 1
    if '--zip' in sys.argv:
        out=ROOT.parent/'GeoAcceptance-v0.5.0-rc1-source.zip'
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
            for p,rel in files():z.write(p,'GeoAcceptance/'+rel.as_posix())
        meta={'file':out.name,'bytes':out.stat().st_size,'sha256':hashlib.sha256(out.read_bytes()).hexdigest()}
        (ROOT.parent/'GeoAcceptance-source-manifest.json').write_text(json.dumps(meta,indent=2),encoding='utf-8');print(json.dumps(meta))
    return 0
if __name__=='__main__':raise SystemExit(main())
