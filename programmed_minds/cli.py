"""User-facing CLI. Inputs are local trusted JSON, never executable model text."""
import argparse
import json
import sys
from pathlib import Path
from .pipeline import run_pipeline,run_audit,PipelineError
from .provider import LiveProvider,ReplayProvider,ProviderError
from .models import Review

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
    critique=subs.add_parser('critique',help='Run one free API critic on a Codex-authored draft')
    critique.add_argument('--role',required=True,choices=('research_critic','improvement_critic','plan_critic'))
    critique.add_argument('--brief',required=True); critique.add_argument('--draft',required=True)
    critique.add_argument('--config',default='examples/free-critics.json'); critique.add_argument('--out',required=True)
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
        elif args.command=='critique':
            from .pipeline import new_directory,write_json,digest
            brief=read_json(args.brief); draft=read_json(args.draft)
            config=read_json(args.config)
            role_cfg=dict(config.get('default',{}));role_cfg.update(config.get('roles',{}).get(args.role,{}))
            allowed={'GROQ_API_KEY':'https://api.groq.com/openai/v1','OPENROUTER_API_KEY':'https://openrouter.ai/api/v1'}
            key_env=role_cfg.get('api_key_env')
            if (role_cfg.get('api_style')!='chat_completions' or key_env not in allowed
                or role_cfg.get('base_url')!=allowed.get(key_env)
                or (key_env=='OPENROUTER_API_KEY' and not role_cfg.get('model','').endswith(':free'))):
                raise ProviderError('Critique requires a configured Groq/OpenRouter chat model')
            output=new_directory(args.out)
            context={'brief':brief,'draft':draft,'approved':{},'tool_registry':[]}
            try:
                reply=LiveProvider(config).generate(args.role,Review,context)
                artifact={'role':args.role,'data':reply['data'],'identity':reply['identity'],
                          'usage':reply['usage'],'input_hash':digest(context),'output_hash':digest(reply['data'])}
                write_json(output/'review.json',artifact)
                status='reviewed'
                if reply['data']['verdict']!='approve' or any(i['severity'] in ('critical','high','medium') for i in reply['data']['issues']): status='blocked'
                result={'status':status,'mode':'live','review':str(output/'review.json')}
            except Exception:
                # Do not leak any provider response or key in a local report.
                raise
        else:
            from .dashboard import serve
            print(f'عرض التقارير: http://127.0.0.1:{args.port}',flush=True)
            serve(Path(args.run),port=args.port,audit_dir=Path(args.audit) if args.audit else None,checks_dir=Path(args.checks) if args.checks else None); return 0
        print(json.dumps({'status':result['status'],'mode':result.get('mode'),
                          'output':str(Path(args.out).resolve()),'error':result.get('error'),
                          'reasons':result.get('reasons',[])},ensure_ascii=False))
        return 0 if result['status'] in ('planned','passed','verified','reviewed') else 1
    except (OSError,ValueError,KeyError,PipelineError,ProviderError) as exc:
        # Invalid JSON could contain secrets; do not print content or traceback.
        message=str(exc) if isinstance(exc,(PipelineError,ProviderError)) or str(exc)=='External checks require Linux/macOS or WSL on Windows' else type(exc).__name__+'; verify input paths and JSON configuration'
        print('Error: '+message,file=sys.stderr); return 2
    except KeyboardInterrupt: return 130
