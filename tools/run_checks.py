"""Run the candidate's main checks, persist commands/exit codes, never infer success."""
import json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    out=ROOT/'acceptance'/'stage-5';out.mkdir(parents=True,exist_ok=True)
    commands=[['tools/stage0_gate.py'],['tools/recheck_probes.py','--out','acceptance/stage-5/core-probes.json'],
              ['tools/compare_probes.py'],['tools/check_schema_consistency.py'],['tests/test_application.py']]
    names=['core-regression','core-probes','compare-probes','schema-check','application-tests']
    rows=[]
    for name,args in zip(names,commands):
        command=[sys.executable,'-X','utf8',*args];start=time.perf_counter()
        p=subprocess.run(command,cwd=ROOT,capture_output=True,encoding='utf-8',errors='strict',env={**os.environ,'PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8','PYTHONDONTWRITEBYTECODE':'1'})
        (out/(name+'.txt')).write_text(p.stdout+p.stderr,encoding='utf-8')
        if name=='application-tests':(ROOT/'acceptance'/'stage-2'/'application-tests.txt').write_text(p.stdout+p.stderr,encoding='utf-8')
        rows.append({'name':name,'command':command,'exit_code':p.returncode,'seconds':round(time.perf_counter()-start,3)});print(name,p.returncode,flush=True)
    result={'python':sys.version,'checks':rows,'all_ok':all(r['exit_code']==0 for r in rows)}
    (out/'check-summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if result['all_ok'] else 1
if __name__=='__main__':raise SystemExit(main())
