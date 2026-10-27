"""CLI for the application lifecycle; no web UI required."""
import argparse,json,time
from pathlib import Path
from .service import Service

def main():
    p=argparse.ArgumentParser();p.add_argument('--data-dir');sub=p.add_subparsers(dest='command',required=True)
    e=sub.add_parser('example');e.add_argument('name',choices=['clean','defective','corrected','ambiguous','blocked'])
    d=sub.add_parser('draft');d.add_argument('project');d.add_argument('--mode',choices=['manual','live'],default='manual');d.add_argument('--confirm-outbound',action='store_true')
    a=sub.add_parser('approve');a.add_argument('project');a.add_argument('--proposal',required=True);a.add_argument('--revision',type=int,required=True);a.add_argument('--reviewer',required=True)
    r=sub.add_parser('execute');r.add_argument('project')
    s=sub.add_parser('show');s.add_argument('project')
    args=p.parse_args();service=Service(args.data_dir)
    try:
        if args.command=='example':result=service.example(args.name)
        elif args.command=='show':result=service.detail(args.project)
        elif args.command=='approve':result=service.approve(args.project,args.revision,json.loads(Path(args.proposal).read_text(encoding='utf-8')),args.reviewer)
        else:
            if args.command=='draft' and args.mode=='live' and not args.confirm_outbound:raise ValueError('Use show to inspect preview, then explicitly pass --confirm-outbound')
            proj=service.project(args.project);j=service.submit(args.project,'draft' if args.command=='draft' else 'validate',proj['revision'],__import__('uuid').uuid4().hex,getattr(args,'mode','manual'))
            service.pool.shutdown(wait=True);result=service.job(j['id'])
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    finally:service.close()
if __name__=='__main__':raise SystemExit(main())

