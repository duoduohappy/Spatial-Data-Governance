"""Local persistent application service, immutable runs and optimistic review versions."""
from __future__ import annotations
import csv,io,json,math,re,shutil,sqlite3,threading,uuid,hashlib,datetime,copy,os
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
import yaml
from .authoring import create_draft,normalize_proposal,outbound_preview,digest
from .llm import CompatibleClient
from .validate import validate_bundle
from .compare import compare_batches
from . import reporting

INPUTS=('delivery_spec.md','dictionary.csv','poi.csv','area.geojson','crs.json')
ROOT=Path(__file__).resolve().parent.parent
class Conflict(ValueError):pass

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def uid():return uuid.uuid4().hex

def normalize_geojson(raw):
    """Point FeatureCollection -> canonical CSV. No CRS guessing or silent point dropping."""
    obj=json.loads(raw)
    if obj.get('type')!='FeatureCollection' or not isinstance(obj.get('features'),list):raise ValueError('Expected a GeoJSON FeatureCollection')
    rows=[]
    if len(obj['features'])>100000:raise ValueError('Feature limit exceeded')
    for f in obj['features']:
        geom=f.get('geometry') or {};p=f.get('properties') or {};coords=geom.get('coordinates')
        if geom.get('type')!='Point' or not isinstance(coords,list) or len(coords)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in coords):
            raise ValueError('Only finite 2D Points supported; invalid features are never silently skipped')
        rows.append([p.get(k,'') for k in ('record_id','name','category')]+coords+[p.get('source_time','')])
    buf=io.StringIO(newline='');w=csv.writer(buf);w.writerow(['record_id','name','category','longitude','latitude','source_time']);w.writerows(rows)
    return buf.getvalue()

class Service:
    def __init__(self,root=None,workers=2):
        self.root=Path(root or ROOT/'work'/'app').resolve();self.root.mkdir(parents=True,exist_ok=True)
        self._lease=(self.root/'.owner.lock').open('a+b')
        if self._lease.seek(0,2)==0:self._lease.write(b'0');self._lease.flush()
        self._lease.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self._lease.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self._lease.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            self._lease.close();raise Conflict('Another application already owns this data directory') from None
        self.db=self.root/'state.sqlite';self.lock=threading.RLock();self.pool=ThreadPoolExecutor(max_workers=workers)
        with self.connect() as c:
            c.executescript('''CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, name TEXT, revision INTEGER, draft TEXT, approval TEXT, created TEXT);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,project TEXT,kind TEXT,revision INTEGER,status TEXT,result TEXT,error TEXT,created TEXT,idempotency TEXT UNIQUE);
            CREATE TABLE IF NOT EXISTS audit(seq INTEGER PRIMARY KEY AUTOINCREMENT,project TEXT,action TEXT,actor TEXT,at TEXT,detail TEXT);''')
            c.execute("UPDATE jobs SET status='INTERRUPTED',error='Application restarted; resubmit explicitly' WHERE status IN ('QUEUED','RUNNING')")
    def close(self):
        self.pool.shutdown(wait=True)
        self._lease.close()
    @contextmanager
    def connect(self):
        c=sqlite3.connect(self.db,timeout=15);c.row_factory=sqlite3.Row
        try:
            with c: yield c
        finally: c.close()
    def audit(self,c,p,action,actor,detail):
        c.execute('INSERT INTO audit(project,action,actor,at,detail) VALUES(?,?,?,?,?)',(p,action,actor,now(),json.dumps(detail,ensure_ascii=False)))
    def project(self,p):
        if not re.fullmatch('[a-f0-9]{32}',p):raise ValueError('Invalid project ID')
        with self.connect() as c:r=c.execute('SELECT * FROM projects WHERE id=?',(p,)).fetchone()
        if not r:raise ValueError('Project not found')
        return dict(r)
    def path(self,p):self.project(p);return self.root/'projects'/p/'input'
    def list(self):
        with self.connect() as c:return [dict(r) for r in c.execute('SELECT id,name,revision,created FROM projects ORDER BY created DESC')]
    def create(self,name,files):
        if not isinstance(name,str) or not name.strip() or len(name)>100:raise ValueError('Project name required, max 100 characters')
        if not isinstance(files,dict):raise ValueError('Files must be an object')
        files=dict(files)
        allowed=set(INPUTS)|{'poi.geojson'}
        if set(files)-allowed:raise ValueError('Unknown input filenames')
        if 'poi.geojson' in files:
            if 'poi.csv' in files:raise ValueError('Choose CSV or GeoJSON, not both')
            files['poi.csv']=normalize_geojson(files['poi.geojson'])
            side=json.loads(files.get('crs.json','{}'))
            if side.get('declared_crs')!='EPSG:4326':raise ValueError('GeoJSON adapter requires explicit EPSG:4326 sidecar; no guessed conversion')
        if set(INPUTS)-set(files):raise ValueError('Required files: '+', '.join(INPUTS))
        if any(not isinstance(v,str) or len(v.encode('utf-8'))>20*1024*1024 for v in files.values()):raise ValueError('Invalid file or 20 MiB file limit')
        if sum(len(v.encode('utf-8')) for v in files.values())>25*1024*1024:raise ValueError('Total upload exceeds 25 MiB')
        # Parse before storing; schemas and actual data correctness still belong to validation.
        for f in ('area.geojson','crs.json'):json.loads(files[f])
        p=uid();dest=self.root/'projects'/p/'input';dest.mkdir(parents=True)
        try:
            for f,v in files.items():(dest/f).write_text(v,encoding='utf-8',newline='')
            with self.connect() as c:
                c.execute('INSERT INTO projects VALUES(?,?,?,?,?,?)',(p,name.strip(),1,None,None,now()));self.audit(c,p,'CREATE','local-user',{'files':list(files)})
        except Exception:
            shutil.rmtree(dest.parent);raise
        return self.project(p)
    def example(self,name):
        if name not in ('clean','defective','corrected','ambiguous','blocked','crs_same_unit_wrong'):raise ValueError('Unknown example')
        b=ROOT/'examples'/name
        return self.create('示例 · '+name,{n:(b/n).read_text(encoding='utf-8') for n in INPUTS})
    def detail(self,p):
        r=self.project(p);b=self.path(p)
        r['draft']=json.loads(r['draft']) if r['draft'] else None
        r['approval']=json.loads(r['approval']) if r['approval'] else None
        r['preview']=outbound_preview(b);r['files']={n:hashlib.sha256((b/n).read_bytes()).hexdigest() for n in INPUTS}
        with self.connect() as c:
            r['jobs']=[dict(j) for j in c.execute('SELECT id,kind,revision,status,error,created FROM jobs WHERE project=? ORDER BY created DESC',(p,))]
            r['audit']=[{**dict(x),'detail':json.loads(x['detail'])} for x in c.execute('SELECT * FROM audit WHERE project=? ORDER BY seq DESC LIMIT 40',(p,))]
        r['points']=self.points(b);return r
    def points(self,b):
        rows=list(csv.DictReader(io.StringIO((b/'poi.csv').read_text(encoding='utf-8'))));points=[]
        for i,r in enumerate(rows[:10000],2):
            try:
                lon=float(r.get('longitude',''));lat=float(r.get('latitude',''))
                valid=math.isfinite(lon) and math.isfinite(lat) and -180<=lon<=180 and -90<=lat<=90
            except (TypeError,ValueError):valid=False;lon=lat=None
            points.append({'line':i,'record_id':r.get('record_id'),'name':r.get('name'),'longitude':lon if valid else None,'latitude':lat if valid else None})
        return {'records':len(rows),'shown':len(points),'points':points,'area':json.loads((b/'area.geojson').read_text(encoding='utf-8'))}
    def submit(self,p,kind,revision,key,mode='manual'):
        if kind not in ('draft','validate'):raise ValueError('Unknown task kind')
        if mode not in ('manual','live'):raise ValueError('Unknown mode')
        if not key or len(key)>100:raise ValueError('Idempotency key required')
        with self.lock,self.connect() as c:
            old=c.execute('SELECT * FROM jobs WHERE idempotency=?',(p+':'+key,)).fetchone()
            if old:
                if old['kind']!=kind or old['revision']!=revision:raise Conflict('Idempotency key reused for another operation')
                return dict(old)
            proj=self.project(p)
            if proj['revision']!=revision:raise Conflict('Stale project revision; refresh')
            if kind=='validate' and not proj['approval']:raise Conflict('Approve current rules before execution')
            active=c.execute("SELECT count(*) FROM jobs WHERE status IN ('QUEUED','RUNNING')").fetchone()[0]
            if active>=8:raise Conflict('Queue is full; retry later')
            j=uid();c.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?)',(j,p,kind,revision,'QUEUED',None,None,now(),p+':'+key))
            self.audit(c,p,'QUEUE','local-user',{'job':j,'kind':kind,'revision':revision,'mode':mode})
        self.pool.submit(self._execute,j,proj,kind,mode)
        return self.job(j)
    def job(self,j):
        if not re.fullmatch('[a-f0-9]{32}',j):raise ValueError('Invalid job ID')
        with self.connect() as c:r=c.execute('SELECT * FROM jobs WHERE id=?',(j,)).fetchone()
        if not r:raise ValueError('Job not found')
        d=dict(r);d['result']=json.loads(d['result']) if d['result'] else None;return d
    def _execute(self,j,proj,kind,mode):
        p=proj['id'];client=CompatibleClient() if mode=='live' else None
        with self.connect() as c:c.execute("UPDATE jobs SET status='RUNNING' WHERE id=?",(j,))
        try:
            if kind=='draft':
                result=create_draft(self.path(p),mode,client)
                with self.lock,self.connect() as c:
                    cur=self.project(p)
                    if cur['revision']!=proj['revision']:raise Conflict('Project changed while drafting; proposal discarded')
                    c.execute('UPDATE projects SET draft=?,approval=NULL,revision=revision+1 WHERE id=?',(json.dumps(result,ensure_ascii=False),p))
                    self.audit(c,p,'DRAFT','system',{'job':j,'mode':mode,'calls':result['calls'],'proposal_hash':digest(json.dumps(result,sort_keys=True,ensure_ascii=False))})
            else:
                approval=json.loads(proj['approval']);dest=self.root/'runs'/j;dest.mkdir(parents=True)
                actual={n:hashlib.sha256((self.path(p)/n).read_bytes()).hexdigest() for n in INPUTS}
                if actual!=approval['input_hashes']:raise Conflict('Input snapshot changed after approval')
                for n in INPUTS:shutil.copyfile(self.path(p)/n,dest/n)
                (dest/'requirements.yaml').write_text(yaml.safe_dump(approval['requirements_doc'],allow_unicode=True,sort_keys=False),encoding='utf-8')
                (dest/'approved-rules.yaml').write_text(yaml.safe_dump(approval['rules_doc'],allow_unicode=True,sort_keys=False),encoding='utf-8')
                result=validate_bundle(dest);(dest/'report.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
                reporting.write_html(dest/'report.json',dest/'report.html')
                manifest={'run_id':j,'project':p,'revision':proj['revision'],'approval_hash':approval['hash'],
                          'input_hashes':actual,'rules_hash':digest(json.dumps(approval['rules_doc'],sort_keys=True,ensure_ascii=False)),
                          'mode':approval['mode'],'at':now(),'report_sha256':hashlib.sha256((dest/'report.json').read_bytes()).hexdigest()}
                (dest/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
                with self.connect() as c:self.audit(c,p,'VALIDATE','system',{'job':j,'verdict':result['aggregate_verdict'],'manifest':manifest})
            with self.connect() as c:c.execute("UPDATE jobs SET status='COMPLETED',result=? WHERE id=?",(json.dumps(result,ensure_ascii=False),j))
        except Exception as e:
            # Only our own messages are surfaced; arbitrary network exception payloads are not persisted.
            message=str(e)[:800] if isinstance(e,(ValueError,Conflict)) else type(e).__name__
            if client and client.config.api_key:message=message.replace(client.config.api_key,'[redacted]')
            with self.connect() as c:
                c.execute("UPDATE jobs SET status='FAILED',error=?,result=? WHERE id=?",(message,json.dumps({'calls':client.calls if client else []}),j))
                self.audit(c,p,'TASK_FAILED','system',{'job':j,'error':message})
    def approve(self,p,revision,proposal,actor):
        if not isinstance(actor,str) or not actor.strip() or len(actor)>100:raise ValueError('Reviewer name required')
        with self.lock:
            proj=self.project(p)
            if proj['revision']!=revision:raise Conflict('Stale revision; refresh before approval')
            if not proj['draft']:raise Conflict('No draft to approve')
            base=json.loads(proj['draft']);doc=normalize_proposal(proposal,self.path(p))
            baseids={q['requirement_id'] for q in base['requirements']}
            if baseids!={q['requirement_id'] for q in doc['requirements']}:raise ValueError('Review cannot remove/add clause IDs; regenerate a draft for a changed source')
            baseq={q['requirement_id']:q for q in base['requirements']}
            for q in doc['requirements']:
                old=baseq[q['requirement_id']]
                if any(q.get(k)!=old.get(k) for k in ('source_line_start','source_line_end','source_quote')):raise ValueError('Review cannot change source evidence')
                if old['required_for_release'] and not q['required_for_release'] and not re.search('仅供参考|不作为放行依据|advisory',q['source_quote'],re.I):raise ValueError('Mandatory clause cannot be waived in this release')
            stamp=now();rdoc={'schema_version':1,'bundle':p,'reference_time':doc['reference_time'],'requirements':doc['requirements']}
            rules=doc['rules'];supported={q['requirement_id'] for q in doc['requirements'] if q['support_status']=='SUPPORTED'}
            for r in rules:
                r['status']='APPROVED' if all(c in supported for c in r['requirement_ids']) else 'DRAFT'
                r['version']=revision;r['reviewer']=actor.strip();r['approved_at']=stamp
                for s in r['parameter_sources']:s.update(reviewer=actor.strip(),approved_at=stamp)
            rulesdoc={'schema_version':1,'bundle':p,'rules':rules}
            # Validate quote/parameter lineage in an isolated staging snapshot before saving approval.
            dest=self.root/'reviews'/uid();dest.mkdir(parents=True)
            for n in INPUTS:shutil.copyfile(self.path(p)/n,dest/n)
            (dest/'requirements.yaml').write_text(yaml.safe_dump(rdoc,allow_unicode=True,sort_keys=False),encoding='utf-8')
            (dest/'approved-rules.yaml').write_text(yaml.safe_dump(rulesdoc,allow_unicode=True,sort_keys=False),encoding='utf-8')
            from tools.stage0_gate import Kernel
            k=Kernel(dest);rejections=k.collect_config_rejections();problems=k.verify_quotes()+k.verify_parameter_sources()
            if rejections or problems:raise ValueError('Approval rejected: '+json.dumps(rejections or problems,ensure_ascii=False)[:1500])
            approval={'requirements_doc':rdoc,'rules_doc':rulesdoc,'reviewer':actor.strip(),'at':stamp,'mode':base['mode'],
                      'input_hashes':{n:hashlib.sha256((self.path(p)/n).read_bytes()).hexdigest() for n in INPUTS}}
            approval['hash']=digest(json.dumps(approval,sort_keys=True,ensure_ascii=False))
            with self.connect() as c:
                c.execute('UPDATE projects SET approval=?,revision=revision+1 WHERE id=?',(json.dumps(approval,ensure_ascii=False),p))
                self.audit(c,p,'APPROVE',actor.strip(),{'revision':revision+1,'approval_hash':approval['hash'],'review_dir':dest.name})
            return self.detail(p)
    def corrected(self,p,revision,files,name):
        with self.lock:
            proj=self.project(p)
            if proj['revision']!=revision or not proj['approval']:raise Conflict('Need current approved rules')
            if set(files)-{'poi.csv','poi.geojson','crs.json'}:raise ValueError('Correction may change data and CRS declaration only; requirements need new review')
            original={n:(self.path(p)/n).read_text(encoding='utf-8') for n in INPUTS}
            if 'poi.geojson' in files:original.pop('poi.csv',None)
            original.update(files);new=self.create(name or proj['name']+' · 整改批次',original)
            approval=json.loads(proj['approval']);approval['input_hashes']={n:hashlib.sha256((self.path(new['id'])/n).read_bytes()).hexdigest() for n in INPUTS}
            approval['hash']=digest(json.dumps({k:v for k,v in approval.items() if k!='hash'},sort_keys=True,ensure_ascii=False))
            with self.connect() as c:
                c.execute('UPDATE projects SET draft=?,approval=? WHERE id=?',(proj['draft'],json.dumps(approval,ensure_ascii=False),new['id']))
                self.audit(c,new['id'],'INHERIT_APPROVED_RULER','local-user',{'parent':p,'approval_hash':approval['hash']})
            return new
    def compare(self,before,after):
        jb=self.job(before);ja=self.job(after)
        if any(j['kind']!='validate' or j['status']!='COMPLETED' for j in (jb,ja)):raise ValueError('Compare two completed validation runs')
        return compare_batches(self.root/'runs'/before,self.root/'runs'/after)



