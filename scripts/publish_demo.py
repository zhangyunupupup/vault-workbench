"""Deploy the generated static demo ZIP to the public repository's gh-pages branch.

Requires an authenticated GitHub CLI with repository/Pages access. Only the exact
build inputs are accepted. No local service, API, model or user data is published.
"""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile

from build_release import BASE, VERSION, demo_files


def publish(archive,gh,repo):
    def api(endpoint,payload=None,method='GET',missing=False):
        args=[gh,'api',f'repos/{repo}/{endpoint}','--method',method]
        with tempfile.TemporaryDirectory(dir=BASE/'tmp') as folder:
            if payload is not None:
                path=Path(folder)/'request.json';path.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
                args+=['--input',str(path)]
            result=subprocess.run(args,capture_output=True,text=True,encoding='utf-8',timeout=90)
        if result.returncode:
            if missing and '404' in result.stderr:return None
            raise RuntimeError(result.stderr.strip())
        return json.loads(result.stdout) if result.stdout.strip() else {}

    expected={p.relative_to(BASE/'web').as_posix():p.read_bytes() for p in demo_files()}
    with zipfile.ZipFile(archive) as z:
        names=z.namelist()
        if len(names)!=len(set(names)) or set(names)!=set(expected)|{'index.html','.nojekyll','THIRD_PARTY_NOTICES.md','README.txt'}:
            raise ValueError('Static archive does not have the expected demo-only file list.')
        for name,data in expected.items():
            if z.read(name)!=data:raise ValueError('Build is stale: '+name)
        entries=[]
        for name in names:
            data=z.read(name)
            if name in ('index.html','README.txt') and (b'/api/' in data or b'http://127.' in data):
                raise ValueError('Unexpected backend dependency in deployment.')
            entries.append({'path':name,'mode':'100644','type':'blob','content':data.decode('utf-8')})
    head=api('git/ref/heads/gh-pages',missing=True)
    old=head['object']['sha'] if head else None
    tree=api('git/trees',{'tree':entries},'POST')
    if old and api('git/commits/'+old)['tree']['sha']==tree['sha']:
        sha=old
    else:
        commit=api('git/commits',{'message':f'Deploy VAULT Demo {VERSION}','tree':tree['sha'],'parents':[old] if old else []},'POST')
        sha=commit['sha']
        current=api('git/ref/heads/gh-pages',missing=True)
        if (current['object']['sha'] if current else None)!=old:raise RuntimeError('Deployment branch advanced; retry after reviewing it.')
        if old:api('git/refs/heads/gh-pages',{'sha':sha,'force':False},'PATCH')
        else:api('git/refs',{'ref':'refs/heads/gh-pages','sha':sha},'POST')
    pages=api('pages',missing=True)
    config={'build_type':'legacy','source':{'branch':'gh-pages','path':'/'}}
    if not pages:pages=api('pages',config,'POST')
    elif pages.get('source')!={'branch':'gh-pages','path':'/'} or pages.get('build_type')!='legacy':
        raise RuntimeError('Existing Pages configuration differs; review it before changing.')
    return {'commit':sha,'url':pages.get('html_url'),'files':len(entries)}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',type=Path,default=BASE/f'dist/VAULT-Demo-{VERSION}-static.zip')
    p.add_argument('--gh',default='gh')
    p.add_argument('--repo',default='zhangyunupupup/vault-workbench')
    args=p.parse_args()
    print(json.dumps(publish(args.archive,args.gh,args.repo),ensure_ascii=False,indent=2))
