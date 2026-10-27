"""Local-only HTTP UI with durable jobs. No arbitrary filesystem paths exposed."""
from __future__ import annotations
import argparse,json,secrets,urllib.parse,sys,os
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
from .service import Service,Conflict
from .llm import ModelConfig
from .reporting import render_html

class AppServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,port=8765,root=None):
        self.service=Service(root);self.csrf=secrets.token_urlsafe(32)
        try:super().__init__((os.getenv('GA_BIND_HOST','127.0.0.1'),port),Handler)
        except Exception:
            self.service.close();raise
class Handler(BaseHTTPRequestHandler):
    server_version='GeoAcceptance/0.5'
    def log_message(self,*args):pass
    def send(self,code,data,typ='application/json; charset=utf-8',attachment=None):
        raw=json.dumps(data,ensure_ascii=False,allow_nan=False).encode('utf-8') if typ.startswith('application/json') else data.encode('utf-8')
        self.send_response(code);self.send_header('Content-Type',typ);self.send_header('Content-Length',str(len(raw)))
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        if attachment:self.send_header('Content-Disposition','attachment; filename="'+attachment+'"')
        self.end_headers();self.wfile.write(raw)
    def check_host(self):
        if self.headers.get('Host') not in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'):
            raise ValueError('Invalid Host header')
    def do_GET(self):
        try:
            self.check_host();p=urllib.parse.urlsplit(self.path).path;s=self.server.service
            if p=='/':
                page=(Path(__file__).parent/'web'/'index.html').read_text(encoding='utf-8').replace('__CSRF__',self.server.csrf)
                return self.send(200,page,'text/html; charset=utf-8')
            if p in ('/app.js','/style.css'):
                return self.send(200,(Path(__file__).parent/'web'/p[1:]).read_text(encoding='utf-8'),'text/javascript; charset=utf-8' if p.endswith('js') else 'text/css; charset=utf-8')
            if p=='/api/projects':return self.send(200,s.list())
            if p=='/api/config':return self.send(200,ModelConfig.from_env().public())
            parts=p.strip('/').split('/')
            if len(parts)==3 and parts[:2]==['api','projects']:return self.send(200,s.detail(parts[2]))
            if len(parts)>=3 and parts[:2]==['api','jobs']:
                j=s.job(parts[2])
                if len(parts)==3:return self.send(200,j)
                if len(parts)==4 and j['status']=='COMPLETED':
                    if parts[3]=='report.json':return self.send(200,j['result'],attachment='report.json')
                    if parts[3]=='report.html':return self.send(200,render_html(j['result']),'text/html; charset=utf-8',attachment='report.html')
            return self.send(404,{'error':'Not found'})
        except (ValueError,KeyError) as e:self.send(400,{'error':str(e)[:1000]})
        except Exception:self.send(500,{'error':'Internal error; inspect local diagnostics'})
    def do_POST(self):
        try:
            self.check_host()
            origin=self.headers.get('Origin')
            if origin and origin not in (f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'):
                return self.send(403,{'error':'Cross-origin request rejected'})
            if not secrets.compare_digest(self.headers.get('X-CSRF-Token',''),self.server.csrf):return self.send(403,{'error':'CSRF token required'})
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('JSON required')
            size=int(self.headers.get('Content-Length','0'))
            if size<=0 or size>30*1024*1024:raise ValueError('Request limit exceeded')
            d=json.loads(self.rfile.read(size));p=urllib.parse.urlsplit(self.path).path;s=self.server.service
            if not isinstance(d,dict):raise ValueError('Object required')
            if p=='/api/projects':return self.send(201,s.create(d.get('name'),d.get('files')))
            if p=='/api/examples':return self.send(201,s.example(d.get('name')))
            if p=='/api/compare':return self.send(200,s.compare(d['before'],d['after']))
            parts=p.strip('/').split('/')
            if len(parts)==4 and parts[:2]==['api','projects']:
                project=parts[2];op=parts[3]
                if op in ('draft','validate'):
                    if op=='draft' and d.get('mode')=='live' and d.get('confirm_outbound') is not True:raise ValueError('Confirm the displayed outbound payload before a live call')
                    return self.send(202,s.submit(project,op,d['revision'],d['key'],d.get('mode','manual')))
                if op=='approve':return self.send(200,s.approve(project,d['revision'],d['proposal'],d['reviewer']))
                if op=='corrected':return self.send(201,s.corrected(project,d['revision'],d['files'],d.get('name')))
            return self.send(404,{'error':'Not found'})
        except Conflict as e:self.send(409,{'error':str(e)})
        except (ValueError,KeyError,TypeError) as e:self.send(400,{'error':str(e)[:1500]})
        except Exception:self.send(500,{'error':'Internal error; inspect local diagnostics'})

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--port',type=int,default=8765);ap.add_argument('--data-dir');a=ap.parse_args()
    server=AppServer(a.port,a.data_dir);print(f'GeoAcceptance: http://127.0.0.1:{server.server_port}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.shutdown();server.server_close();server.service.close()
if __name__=='__main__':main()



