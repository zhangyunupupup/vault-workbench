"""Build explicit-file releases; never include user state or licensed model files.

python scripts/build_release.py --python-zip tmp/python-embed/python-3.14.10-embed-amd64.zip
The input is the official python.org Windows x64 embeddable distribution.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

BASE=Path(__file__).resolve().parents[1]
VERSION='2.4.0'
PYTHON_VERSION='3.14.10'
PYTHON_URL='https://www.python.org/ftp/python/3.14.10/python-3.14.10-embed-amd64.zip'
PYTHON_SHA256='90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159'
ROOT_FILES=('server.py','launch.ps1','启动VAULT工作台.cmd','README.md','使用说明.md','CHANGELOG.md','THIRD_PARTY_NOTICES.md')
FORBIDDEN={'.stl','.3mf','.pdf','.pyc'}

def source_files():
    files=[BASE/p for p in ROOT_FILES]
    files += [p for folder in ('vault','web') for p in (BASE/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    files += [p for p in (BASE/'docs').rglob('*') if p.suffix in ('.md','.json')]
    files += list((BASE/'output').glob('*.png'))
    for p in files:
        if p.suffix.lower() in FORBIDDEN or not p.resolve().is_relative_to(BASE):
            raise ValueError('Unexpected source artifact: '+str(p))
    return sorted(files)

def demo_files():
    files=list((BASE/'web/assets/demo').glob('*'))
    files += [BASE/'web/assets'/p for p in ('builder-stage.js','palette.json','vendor/three.module.js','vendor/OrbitControls.js','vendor/THREE-LICENSE.txt')]
    return sorted(p for p in files if p.is_file())

def verified_python(path):
    if hashlib.sha256(path.read_bytes()).hexdigest()!=PYTHON_SHA256:
        raise ValueError('Python ZIP SHA-256 differs from the official pinned release.')
    with zipfile.ZipFile(path) as archive:
        result={}
        for name in archive.namelist():
            p=PurePosixPath(name)
            if p.is_absolute() or '..' in p.parts or '\\' in name:
                raise ValueError('Invalid runtime archive member.')
            if not name.endswith('/'):
                result[name]=archive.read(name)
        if not {'python.exe','python314._pth','python314.zip','LICENSE.txt'}.issubset(result):
            raise ValueError('Not the expected official Python distribution.')
        # Keep isolated mode; explicitly allow the containing application only.
        result['python314._pth']=b'python314.zip\n.\n..\n'
        return result

def write_archive(path,entries):
    temporary=path.with_suffix('.tmp')
    with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for name,data in sorted(entries.items()):
            info=zipfile.ZipInfo(name,date_time=(2026,10,28,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,data)
    temporary.replace(path)

def build(output,python_zip):
    runtime=verified_python(python_zip)
    output.mkdir(parents=True,exist_ok=True)
    prefix=f'VAULT-Workbench-{VERSION}/'
    entries={prefix+p.relative_to(BASE).as_posix():p.read_bytes() for p in source_files()}
    # Windows PowerShell 5.1 requires a BOM when reading a UTF-8 script.
    entries[prefix+'launch.ps1']=(BASE/'launch.ps1').read_text(encoding='utf-8-sig').encode('utf-8-sig')
    entries.update({prefix+'python/'+n:data for n,data in runtime.items()})
    entries[prefix+'发行说明.txt']=('VAULT 中文打印工作台 '+VERSION+'\nWindows 10/11 x64便携版\n\n解压整个目录后双击「启动VAULT工作台.cmd」。无需安装Python，无需管理员权限。\n首次使用请选择自己的VAULT资料库。模型、官方PDF和个人设置不包含在发行包中。\n\n手机体验：打开项目README中的「随手搭」在线入口，首次缓存完成后可离线再访。\n运行数据保存在当前解压目录runtime/和exports/，请解压到可写位置，不要直接在ZIP内运行。\n更新时保留旧目录，先在新目录测试；需要迁移时手动复制runtime/settings.json与exports/。\n').encode('utf-8-sig')
    entries[prefix+'release.json']=json.dumps({'version':VERSION,'platform':'windows-x64','python':{'version':PYTHON_VERSION,'url':PYTHON_URL,'sha256':PYTHON_SHA256},'models_included':False},indent=2).encode()
    portable=output/f'VAULT-Workbench-{VERSION}-windows-x64.zip'
    write_archive(portable,entries)
    demo={p.relative_to(BASE/'web').as_posix():p.read_bytes() for p in demo_files()}
    demo['index.html']=b'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=assets/demo/index.html"><a href="assets/demo/index.html">VAULT Demo</a>'
    demo['.nojekyll']=b''
    demo['THIRD_PARTY_NOTICES.md']=(BASE/'THIRD_PARTY_NOTICES.md').read_bytes()
    demo['README.txt']='VAULT随手搭：将全部文件部署至HTTPS静态站点，打开index.html。首次离线缓存成功后可离线再访。直接双击file://不支持模块与离线安装。无API、无官方模型；方案JSON在桌面工作台导入。\n'.encode('utf-8')
    demo_zip=output/f'VAULT-Demo-{VERSION}-static.zip'
    write_archive(demo_zip,demo)
    checksums={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (portable,demo_zip)}
    (output/'SHA256SUMS.txt').write_text(''.join(f'{sha}  {name}\n' for name,sha in checksums.items()),encoding='utf-8')
    return {'version':VERSION,'files':checksums,'portable_files':len(entries),'demo_files':len(demo)}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python-zip',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=BASE/'dist')
    args=parser.parse_args()
    print(json.dumps(build(args.output,args.python_zip),ensure_ascii=False,indent=2))
