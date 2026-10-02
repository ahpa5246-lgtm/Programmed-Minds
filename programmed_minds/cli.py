"""User-facing CLI. Inputs are local trusted JSON, never executable model text."""
import argparse
import json
import sys
from pathlib import Path
from .pipeline import run_pipeline,run_audit,PipelineError
from .provider import LiveProvider,ReplayProvider,ProviderError

def read_json(path):
    path=Path(path)
    if path.stat().st_size>2_000_000: raise ValueError('JSON input exceeds 2 MB')
    return json.loads(path.read_text(encoding='utf-8'))

def provider(args):
    if args.replay: return ReplayProvider(read_json(args.replay))
    if not args.config: raise ValueError('Live runs need --config with model and credential environment variable names')
    return LiveProvider(read_json(args.config))

def main(argv=None):
    parser=argparse.ArgumentParser(prog='pminds',description='Eight agents with evidence-driven project handoffs and real tool checks')
    subs=parser.add_subparsers(dest='command',required=True)
    plan=subs.add_parser('plan',help='Research, critique, improve, plan and design')
    plan.add_argument('--brief',required=True); plan.add_argument('--config'); plan.add_argument('--replay')
    plan.add_argument('--out',required=True)
    check=subs.add_parser('check',help='Run original tool CLIs against a trusted implemented target')
    check.add_argument('--target',required=True); check.add_argument('--config',required=True); check.add_argument('--out',required=True)
    audit=subs.add_parser('audit',help='Run tester against the approved plan and actual check report')
    audit.add_argument('--run',required=True); audit.add_argument('--checks',required=True); audit.add_argument('--config'); audit.add_argument('--replay'); audit.add_argument('--out',required=True)
    view=subs.add_parser('view',help='Read-only Arabic dashboard, localhost only')
    view.add_argument('--run',required=True); view.add_argument('--audit'); view.add_argument('--checks'); view.add_argument('--port',type=int,default=8765)
    args=parser.parse_args(argv)
    try:
        if args.command=='plan':
            cfg=read_json(args.config) if args.config else {}
            result=run_pipeline(read_json(args.brief),provider(args),args.out,
                                max_revisions=cfg.get('max_revisions',2),strict_diversity=cfg.get('strict_diversity',False))
        elif args.command=='check':
            import os
            if os.name!='posix': raise ValueError('External checks require Linux/macOS or WSL on Windows')
            from .checks import run_checks
            result=run_checks(Path(args.target),read_json(args.config),Path(args.out))
        elif args.command=='audit':
            result=run_audit(args.run,read_json(args.checks),provider(args),args.out,report_dir=Path(args.checks).parent)
        else:
            from .dashboard import serve
            print(f'عرض التقارير: http://127.0.0.1:{args.port}',flush=True)
            serve(Path(args.run),port=args.port,audit_dir=Path(args.audit) if args.audit else None,checks_dir=Path(args.checks) if args.checks else None); return 0
        print(json.dumps({'status':result['status'],'mode':result.get('mode'),
                          'output':str(Path(args.out).resolve()),'error':result.get('error'),
                          'reasons':result.get('reasons',[])},ensure_ascii=False))
        return 0 if result['status'] in ('planned','passed','verified') else 1
    except (OSError,ValueError,KeyError,PipelineError,ProviderError) as exc:
        # Invalid JSON could contain secrets; do not print content or traceback.
        message=str(exc) if isinstance(exc,(PipelineError,ProviderError)) or str(exc)=='External checks require Linux/macOS or WSL on Windows' else type(exc).__name__+'; verify input paths and JSON configuration'
        print('Error: '+message,file=sys.stderr); return 2
    except KeyboardInterrupt: return 130
