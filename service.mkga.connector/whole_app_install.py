"""Locally configured whole-app lifecycle; commands never select installation paths."""
import json
import os
from pathlib import Path
import subprocess
import uuid
import re

MODULES=('remote_clean_app.py','wait_clean_app.py','clean_app_stage.py','clean_app_apply.py',
         'clean_app_package.py','remote_prepare.py','wait_apply.py','staged_install.py',
         'fresh_install.py','connector_handoff.py','dev_lifecycle.py','build_package.py','package_signature.py')


def configuration(runtime,xbmc_root):
    if runtime.get('mode')!='clean-macos-app':raise ValueError('Whole-app mode required')
    result={}
    for name in ('python','installer','stagingRoot','app','home'):
        value=runtime.get(name)
        if not isinstance(value,str) or not os.path.isabs(value):raise ValueError('Invalid local path')
        raw=Path(value)
        if name!='python' and raw.is_symlink():raise ValueError('Local paths cannot be links')
        result[name]=raw.resolve(strict=True)
    if result['app'].suffix!='.app' or not result['app'].is_dir():raise ValueError('Invalid application')
    # Bind the configured app to the application actually executing this Connector.
    expected=result['app']/'Contents/Resources/Kodi'
    if Path(xbmc_root).resolve()!=expected.resolve():raise ValueError('Application mismatch')
    if not (result['home']/'userdata').is_dir():raise ValueError('Existing profile required')
    roots=[result[name] for name in ('installer','stagingRoot','app','home')]
    for i,left in enumerate(roots):
        if left in (Path('/'),Path.home().resolve()) or left.parent==Path('/'):
            raise ValueError('Broad lifecycle root')
        for right in roots[i+1:]:
            if left==right or left in right.parents or right in left.parents:
                raise ValueError('Lifecycle roots must be separate')
    if not result['python'].is_file() or not os.access(result['python'],os.X_OK):
        raise ValueError('Executable interpreter unavailable')
    for name in MODULES+('trusted-public.pem',):
        path=result['installer']/name
        if path.is_symlink() or not path.is_file():raise ValueError('Lifecycle helper unavailable')
    return result


def prepare(runtime,xbmc_root,payload):
    if not isinstance(payload,dict) or set(payload)!={'packageUrl','signatureUrl'}:raise ValueError('Invalid request')
    config=configuration(runtime,xbmc_root);root=config['installer']
    completed=subprocess.run([str(config['python']),'-I',str(root/'remote_clean_app.py'),
        '--staging-root',str(config['stagingRoot']),'--public-key',str(root/'trusted-public.pem')],
        input=json.dumps(payload),text=True,capture_output=True,timeout=300)
    if completed.returncode or len(completed.stdout)>4096:raise ValueError('Preparation failed')
    stage=json.loads(completed.stdout).get('stage',{})
    identity=stage.get('id','')
    if str(uuid.UUID(identity))!=identity or stage.get('status')!='prepared' or stage.get('kind')!='clean-macos-app':
        raise ValueError('Invalid prepared stage')
    return {'id':identity,'status':'prepared','kind':'clean-macos-app'}


def apply(runtime,xbmc_root,payload,kodi_pid,connector_profile=None):
    if not isinstance(payload,dict) or set(payload)!={'stageId'}:raise ValueError('Invalid request')
    identity=payload['stageId']
    if not isinstance(identity,str) or str(uuid.UUID(identity))!=identity:raise ValueError('Invalid stage')
    config=configuration(runtime,xbmc_root);root=config['installer'];stage=config['stagingRoot']/identity
    receipt_path=stage/'receipt.json'
    if stage.is_symlink() or receipt_path.is_symlink() or receipt_path.stat().st_size>4096:raise ValueError('Invalid receipt')
    receipt=json.loads(receipt_path.read_text())
    if any(receipt.get(k)!=v for k,v in {'schema':1,'id':identity,'status':'prepared','kind':'clean-macos-app'}.items()):
        raise ValueError('Stage is not prepared')
    profile=Path(connector_profile) if connector_profile is not None else config['home']
    if profile.is_symlink() or profile.resolve() not in (config['home'],config['app']/'Contents/Resources/Kodi/portable_data'):
        raise ValueError('Connector profile does not belong to this installation')
    subprocess.Popen([str(config['python']),'-I',str(root/'wait_clean_app.py'),
        '--stage',str(stage),'--app',str(config['app']),'--home',str(config['home']),
        '--public-key',str(root/'trusted-public.pem'),'--kodi-pid',str(kodi_pid),
        '--connector-profile',str(profile)],
        stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)


def bind_command(runtime,xbmc_root,payload,command_id,device_id):
    """Persist the device/command association outside the replaced profiles."""
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',command_id):raise ValueError('Invalid command identity')
    if str(uuid.UUID(device_id))!=device_id:raise ValueError('Invalid device identity')
    if not isinstance(payload,dict) or set(payload)!={'stageId'}:raise ValueError('Invalid stage request')
    identity=payload['stageId']
    if not isinstance(identity,str) or str(uuid.UUID(identity))!=identity:raise ValueError('Invalid stage identity')
    config=configuration(runtime,xbmc_root);stage=config['stagingRoot']/identity
    receipt_path=stage/'receipt.json'
    if stage.is_symlink() or receipt_path.is_symlink() or receipt_path.stat().st_size>4096:raise ValueError('Invalid stage receipt')
    receipt=json.loads(receipt_path.read_text())
    if any(receipt.get(k)!=v for k,v in {'schema':1,'id':identity,'status':'prepared','kind':'clean-macos-app'}.items()):
        raise ValueError('Prepared stage required')
    descriptor=os.open(stage/'command.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(descriptor,'w') as output:
        json.dump({'schema':1,'stageId':identity,'commandId':command_id,'deviceId':device_id},output)
        output.flush();os.fsync(output.fileno())
    descriptor=os.open(stage,os.O_RDONLY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)


def read_record(path):
    import stat
    descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(descriptor,'rb') as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):raise ValueError('Invalid stage record')
        raw=source.read(4097)
    if len(raw)>4096:raise ValueError('Stage record exceeds limit')
    value=json.loads(raw)
    if not isinstance(value,dict):raise ValueError('Invalid stage record')
    return value


def terminal_commands(runtime,xbmc_root,device_id):
    config=configuration(runtime,xbmc_root);root=config['stagingRoot'];results=[]
    for stage in root.iterdir():
        if len(results)>=100:break
        try:
            if stage.is_symlink() or not stage.is_dir() or str(uuid.UUID(stage.name))!=stage.name:continue
            if (stage/'command-reported.json').exists():continue
            if (stage/'takeover.json').exists():continue
            command=read_record(stage/'command.json')
            if (set(command)!={'schema','stageId','commandId','deviceId'} or command.get('schema')!=1
                    or command.get('stageId')!=stage.name or command.get('deviceId')!=device_id
                    or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',str(command.get('commandId','')))):continue
            receipt=read_record(stage/'receipt.json');job=read_record(stage/'application-job.json')
            if receipt.get('schema')!=1 or receipt.get('id')!=stage.name or receipt.get('kind')!='clean-macos-app':continue
            if job.get('schema')!=1 or job.get('stageId')!=stage.name:continue
            if receipt.get('status')=='installed' and job.get('status')=='installed':
                results.append((stage,command['commandId'],True,'MKGA whole-app installation completed.'))
            elif job.get('status')=='failed' and receipt.get('status')=='prepared':
                results.append((stage,command['commandId'],False,'MKGA whole-app installation failed; previous installation retained or recovered.'))
        except (OSError,ValueError,TypeError):continue
    return results


def mark_reported(stage,command_id):
    descriptor=os.open(Path(stage)/'command-reported.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(descriptor,'w') as output:
        json.dump({'schema':1,'commandId':command_id},output);output.flush();os.fsync(output.fileno())
    descriptor=os.open(stage,os.O_RDONLY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)
