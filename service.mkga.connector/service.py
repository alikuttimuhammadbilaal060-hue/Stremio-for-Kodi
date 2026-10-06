import hashlib, json, os, platform, re, shutil, subprocess, time, urllib.parse, urllib.request, uuid, zipfile
import xbmc, xbmcaddon, xbmcgui, xbmcvfs
from runtime_inventory import collect as collect_runtime_inventory
from command_results import ResultOutbox,MAX_PENDING
from device_proof import signed_headers
from discovery_settings import apply_settings as apply_discovery_settings

BASE='https://mkga.tv/api/kodi/agent'
REPO_ZIP='https://raw.githubusercontent.com/0eroiQ/Stremio-for-Kodi/kodi-repository/repository.stremioforkodi/repository.stremioforkodi-1.1.0.zip'
ADDON_ID='script.stremioelec';REPO_ID='repository.stremioforkodi';CONNECTOR_ID='service.mkga.connector'
addon=xbmcaddon.Addon(CONNECTOR_ID); monitor=xbmc.Monitor(); home=xbmcgui.Window(10000)
def request(path,method='GET',data=None):
    token=addon.getSetting('device_token')
    if not token:return None
    headers={'Authorization':'Bearer '+token,'User-Agent':'MKGA-Connector/'+addon.getAddonInfo('version')}; raw=None
    if data is not None:raw=json.dumps(data).encode();headers['Content-Type']='application/json'
    headers=signed_headers(addon,xbmcvfs,BASE,path,method,raw,headers)
    req=urllib.request.Request(BASE+path,data=raw,headers=headers,method=method)
    with urllib.request.urlopen(req,timeout=20) as r:return json.loads(r.read().decode())
def binary_request(path,method='GET',data=None):
    token=addon.getSetting('device_token')
    if not token:raise Exception('Device is not paired')
    headers={'Authorization':'Bearer '+token,'User-Agent':'MKGA-Connector/'+addon.getAddonInfo('version')}; raw=data
    if data is not None:
        headers['Content-Type']='application/octet-stream';headers['Content-Length']=str(len(data))
    headers=signed_headers(addon,xbmcvfs,BASE,path,method,raw,headers)
    req=urllib.request.Request(BASE+path,data=raw,headers=headers,method=method)
    with urllib.request.urlopen(req,timeout=90) as r:
        body=r.read()
        return json.loads(body.decode()) if body else {}
def backup_skip(rel):
    rel=rel.replace('\\','/').strip('/');low=rel.lower()
    if not rel:return False
    if low=='addons/service.mkga.connector' or low.startswith('addons/service.mkga.connector/'):return True
    if low=='userdata/addon_data/service.mkga.connector' or low.startswith('userdata/addon_data/service.mkga.connector/'):return True
    if low=='addons/packages' or low.startswith('addons/packages/'):return True
    if low=='userdata/thumbnails' or low.startswith('userdata/thumbnails/'):return True
    if low.startswith('userdata/database/textures') and low.endswith('.db'):return True
    if low.endswith('/kodi.log') or low.endswith('/kodi.old.log'):return True
    parts=[x.lower() for x in rel.split('/')]
    return any(x in ('cache','temp','logs') for x in parts)
def backup_files(home_path):
    for root_name in ('addons','userdata','media'):
        root=os.path.join(home_path,root_name)
        if not os.path.isdir(root):continue
        for base,dirs,files in os.walk(root):
            rel_base=os.path.relpath(base,home_path).replace('\\','/')
            dirs[:]=[d for d in dirs if not backup_skip((rel_base+'/'+d).replace('./','',1))]
            for name in files:
                src=os.path.join(base,name);rel=os.path.relpath(src,home_path).replace('\\','/')
                if backup_skip(rel) or os.path.islink(src):continue
                yield src,rel
def sha256_file(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        while True:
            chunk=f.read(1024*1024)
            if not chunk:break
            h.update(chunk)
    return h.hexdigest()
def create_backup(name):
    home_path=xbmcvfs.translatePath('special://home');temp=xbmcvfs.translatePath('special://temp/mkga-kodi-build-%d.zip'%int(time.time()))
    manifest={'format':1,'createdAt':int(time.time()),'kodiVersion':xbmc.getInfoLabel('System.BuildVersion'),'platform':platform.system(),'deviceName':addon.getSetting('device_name'),'connectorVersion':addon.getAddonInfo('version'),'roots':['addons','userdata','media'],'excluded':['cache/temp/logs','Thumbnails','addons/packages','service.mkga.connector device identity']}
    count=0
    try:
        with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED,compresslevel=4) as z:
            for src,rel in backup_files(home_path):
                try:z.write(src,rel);count+=1
                except (OSError,IOError):pass
            manifest['fileCount']=count;z.writestr('_mkga_backup.json',json.dumps(manifest,separators=(',',':')))
        size=os.path.getsize(temp);digest=sha256_file(temp)
        start=request('/backups/start','POST',{'name':name,'kodiVersion':manifest['kodiVersion'],'platform':manifest['platform'],'manifest':manifest}) or {}
        backup_id=str(start.get('backupId',''));part_size=int(start.get('partSize') or 8388608)
        if not backup_id:raise Exception('Backup upload could not start')
        part=1
        with open(temp,'rb') as f:
            while True:
                chunk=f.read(part_size)
                if not chunk:break
                binary_request('/backups/'+backup_id+'/parts/'+str(part),'PUT',chunk);part+=1
        request('/backups/'+backup_id+'/complete','POST',{'sizeBytes':size,'sha256':digest,'fileCount':count})
        return True,'Kodi build backed up to MKGA cloud',{'backupId':backup_id,'backupName':name,'backupSizeBytes':size}
    finally:
        try:os.remove(temp)
        except Exception:pass
def download_backup(backup_id):
    token=addon.getSetting('device_token');target=xbmcvfs.translatePath('special://temp/mkga-restore-'+backup_id+'.zip')
    path='/backups/'+backup_id+'/download'
    headers=signed_headers(addon,xbmcvfs,BASE,path,'GET',None,{'Authorization':'Bearer '+token,'User-Agent':'MKGA-Connector/'+addon.getAddonInfo('version')})
    req=urllib.request.Request(BASE+path,headers=headers,method='GET')
    with urllib.request.urlopen(req,timeout=120) as r,open(target,'wb') as out:
        expected=str(r.headers.get('x-backup-sha256') or '').lower();shutil.copyfileobj(r,out,1024*1024)
    if expected and sha256_file(target)!=expected:
        try:os.remove(target)
        except Exception:pass
        raise Exception('Backup checksum verification failed')
    return target
MAX_BUILD_DOWNLOAD=4*1024*1024*1024
MAX_BUILD_UNCOMPRESSED=20*1024*1024*1024
MAX_BUILD_FILES=100000

def validate_build_url(value):
    value=str(value or '').strip()
    parsed=urllib.parse.urlparse(value)
    if parsed.scheme.lower() not in ('http','https') or not parsed.netloc or parsed.username or parsed.password:
        raise Exception('Build URL must be a normal HTTP or HTTPS URL')
    return value

def download_build_url(url):
    url=validate_build_url(url)
    target=xbmcvfs.translatePath('special://temp/mkga-url-build-%d.zip'%int(time.time()))
    req=urllib.request.Request(url,headers={'User-Agent':'MKGA-Connector/'+addon.getAddonInfo('version')},method='GET')
    total=0
    try:
        with urllib.request.urlopen(req,timeout=60) as response,open(target,'wb') as out:
            validate_build_url(response.geturl())
            declared=int(response.headers.get('Content-Length') or 0)
            if declared>MAX_BUILD_DOWNLOAD:raise Exception('Kodi build is larger than the 4 GB safety limit')
            while True:
                chunk=response.read(1024*1024)
                if not chunk:break
                total+=len(chunk)
                if total>MAX_BUILD_DOWNLOAD:raise Exception('Kodi build is larger than the 4 GB safety limit')
                out.write(chunk)
                if monitor.abortRequested():raise Exception('Kodi is shutting down; build install cancelled')
        if total<22 or not zipfile.is_zipfile(target):raise Exception('The URL did not return a valid Kodi ZIP build')
        return target,total
    except Exception:
        try:os.remove(target)
        except Exception:pass
        raise

def build_member_rel(name):
    rel=str(name or '').replace('\\','/').lstrip('/')
    parts=[p for p in rel.split('/') if p not in ('','.')]
    if not parts or '..' in parts:return ''
    roots={'addons':'addons','userdata':'userdata','media':'media'}
    for index,part in enumerate(parts):
        key=part.lower()
        if key not in roots:continue
        prefix=parts[:index]
        if len(prefix)>2:continue
        if len(prefix)==2 and prefix[-1].lower() not in ('.kodi','kodi'):continue
        return '/'.join([roots[key],*parts[index+1:]])
    return ''

def safe_install_url_build(zip_path):
    home_path=os.path.realpath(xbmcvfs.translatePath('special://home'));restored=0;total=0;selected=[]
    with zipfile.ZipFile(zip_path,'r') as z:
        infos=z.infolist()
        if len(infos)>MAX_BUILD_FILES:raise Exception('Kodi build contains too many files')
        for member in infos:
            rel=build_member_rel(member.filename)
            if not rel or backup_skip(rel):continue
            mode=(member.external_attr>>16)&0o170000
            if mode==0o120000:continue
            total+=max(0,int(member.file_size or 0))
            if total>MAX_BUILD_UNCOMPRESSED:raise Exception('Kodi build expands beyond the 20 GB safety limit')
            selected.append((member,rel))
        if not any(rel.split('/')[0] in ('addons','userdata') for _,rel in selected):raise Exception('ZIP does not contain a supported Kodi build structure')
        for member,rel in selected:
            parts=[p for p in rel.split('/') if p]
            out=os.path.realpath(os.path.join(home_path,*parts))
            if not (out==home_path or out.startswith(home_path+os.sep)):continue
            if member.is_dir():os.makedirs(out,exist_ok=True);continue
            os.makedirs(os.path.dirname(out),exist_ok=True)
            with z.open(member) as src,open(out,'wb') as dst:shutil.copyfileobj(src,dst,1024*1024)
            restored+=1
    xbmc.executebuiltin('UpdateLocalAddons');xbmc.executebuiltin('ReloadSkin()')
    return restored

def install_build_url(url):
    url=validate_build_url(url)
    safety_name='Before URL build · '+time.strftime('%Y-%m-%d %H:%M')
    safety_ok,_,safety=create_backup(safety_name)
    if not safety_ok:raise Exception('Safety backup failed; URL build install cancelled')
    path,size=download_build_url(url)
    try:count=safe_install_url_build(path)
    finally:
        try:os.remove(path)
        except Exception:pass
    return True,'Kodi build installed from URL. Restart Kodi to fully apply it.',{'restartRequired':True,'safetyBackupId':safety.get('backupId',''),'restoredFiles':count,'downloadedBytes':size}

def safe_restore(zip_path):
    home_path=os.path.realpath(xbmcvfs.translatePath('special://home'));restored=0
    with zipfile.ZipFile(zip_path,'r') as z:
        names=z.infolist()
        for m in names:
            rel=m.filename.replace('\\','/').lstrip('/');parts=[p for p in rel.split('/') if p]
            if not parts or rel=='_mkga_backup.json':continue
            if parts[0] not in ('addons','userdata','media') or '..' in parts or backup_skip(rel):continue
            out=os.path.realpath(os.path.join(home_path,*parts))
            if not (out==home_path or out.startswith(home_path+os.sep)):continue
            if m.is_dir():os.makedirs(out,exist_ok=True);continue
            os.makedirs(os.path.dirname(out),exist_ok=True)
            with z.open(m) as src,open(out,'wb') as dst:shutil.copyfileobj(src,dst)
            restored+=1
    xbmc.executebuiltin('UpdateLocalAddons');xbmc.executebuiltin('ReloadSkin()')
    return restored
def restore_backup(backup_id):
    safety_name='Before restore · '+time.strftime('%Y-%m-%d %H:%M')
    safety_ok,_,safety=create_backup(safety_name)
    if not safety_ok:raise Exception('Safety backup failed; restore cancelled')
    path=download_backup(backup_id)
    try:count=safe_restore(path)
    finally:
        try:os.remove(path)
        except Exception:pass
    return True,'Kodi build restored. Restart Kodi to fully apply it.',{'backupId':backup_id,'backupName':'Restored build','restartRequired':True,'safetyBackupId':safety.get('backupId',''),'restoredFiles':count}
def installed(addon_id):return xbmc.getCondVisibility('System.HasAddon(%s)'%addon_id)
def version():
    try:return xbmcaddon.Addon(ADDON_ID).getAddonInfo('version') if installed(ADDON_ID) else ''
    except Exception:return ''
def install_repo():
    home=xbmcvfs.translatePath('special://home/addons'); temp=xbmcvfs.translatePath('special://temp/mkga-repo.zip')
    urllib.request.urlretrieve(REPO_ZIP,temp)
    with zipfile.ZipFile(temp,'r') as z:
        roots={n.split('/')[0] for n in z.namelist() if n and not n.startswith('/')}
        if REPO_ID not in roots: raise Exception('Invalid repository package')
        for m in z.infolist():
            n=m.filename.replace('\\','/');parts=[p for p in n.split('/') if p]
            if not parts or parts[0]!=REPO_ID or '..' in parts:continue
            out=os.path.realpath(os.path.join(home,*parts));root=os.path.realpath(os.path.join(home,REPO_ID))
            if not (out==root or out.startswith(root+os.sep)):continue
            if m.is_dir():os.makedirs(out,exist_ok=True)
            else:
                os.makedirs(os.path.dirname(out),exist_ok=True)
                with z.open(m) as src,open(out,'wb') as dst:shutil.copyfileobj(src,dst)
    try:os.remove(temp)
    except Exception:pass
    xbmc.executebuiltin('UpdateLocalAddons');time.sleep(2);xbmc.executebuiltin('UpdateAddonRepos');time.sleep(4)
    return installed(REPO_ID)
def install_stremio():
    if not installed(REPO_ID) and not install_repo():raise Exception('Repository install failed')
    xbmc.executebuiltin('UpdateAddonRepos');time.sleep(4);xbmc.executebuiltin('InstallAddon(%s)'%ADDON_ID);time.sleep(6);xbmc.executebuiltin('UpdateLocalAddons');time.sleep(2)
    return installed(ADDON_ID)
def prepare_mkga_build(payload):
    # Trust and interpreter configuration are local, never supplied by a command.
    home_path=xbmcvfs.translatePath('special://home')
    root=os.path.join(home_path,'mkga-installer')
    config=os.path.join(root,'runtime.json');helper=os.path.join(root,'remote_prepare.py')
    trusted=os.path.join(root,'trusted-public.pem')
    if platform.system() not in ('Darwin','Linux'):
        return False,'Signed Build preparation is unavailable on this platform',{}
    try:
        if set(payload)!={'packageUrl','signatureUrl'}:raise ValueError('Invalid request')
        if os.path.islink(root) or os.path.islink(config) or not os.path.isfile(config):
            raise ValueError('Local helper unavailable')
        with open(config,'rb') as source:raw=source.read(4097)
        if len(raw)>4096:raise ValueError('Invalid local runtime')
        runtime=json.loads(raw)
        if runtime.get('mode')=='clean-macos-app':
            from whole_app_install import prepare as prepare_whole_app
            stage=prepare_whole_app(runtime,xbmcvfs.translatePath('special://xbmc'),payload)
            return True,'Signed Mac application prepared. Quit Kodi before applying.',{'buildStage':stage}
        if any(os.path.islink(p) or not os.path.isfile(p) for p in (helper,trusted)):raise ValueError('Local helper unavailable')
        python=runtime.get('python','')
        if not isinstance(python,str) or not os.path.isabs(python) or not os.path.isfile(python):
            raise ValueError('Invalid local interpreter')
        result=subprocess.run([python,'-I',helper,'--home',home_path,'--public-key',trusted],
            input=json.dumps(payload),text=True,capture_output=True,timeout=120)
        if result.returncode or len(result.stdout)>4096:raise ValueError('Preparation failed')
        stage=json.loads(result.stdout).get('stage',{})
        if stage.get('status')!='prepared' or not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',str(stage.get('id',''))):
            raise ValueError('Invalid stage result')
        return True,'Signed Build prepared. Quit Kodi before applying the package.',{'buildStage':{'id':stage['id'],'status':'prepared'}}
    except Exception:
        return False,'Signed Build preparation failed; check the local installer and trust configuration',{}

def apply_mkga_build(payload):
    try:
        if set(payload)!={'stageId'} or not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',str(payload['stageId'])):
            raise ValueError('Invalid stage request')
        if not build_prepare_ready():raise ValueError('Local installer unavailable')
        home_path=xbmcvfs.translatePath('special://home')
        with open(os.path.join(home_path,'mkga-installer','runtime.json'),'rb') as source:runtime_raw=source.read(4097)
        if len(runtime_raw)>4096:raise ValueError('Invalid local runtime')
        runtime=json.loads(runtime_raw)
        if runtime.get('mode')=='clean-macos-app':
            from whole_app_install import apply as apply_whole_app
            apply_whole_app(runtime,xbmcvfs.translatePath('special://xbmc'),payload,os.getpid(),home_path)
            return True,'Whole Mac application requested. Quit Kodi within ten minutes before reopening.',{}
        root=os.path.join(home_path,'mkga-staged-installs')
        stage=os.path.join(root,payload['stageId']);receipt_path=os.path.join(stage,'receipt.json')
        if os.path.islink(root) or os.path.islink(stage) or os.path.islink(receipt_path):raise ValueError('Invalid stage location')
        with open(receipt_path,'rb') as source:raw=source.read(4097)
        if len(raw)>4096:raise ValueError('Invalid stage receipt')
        receipt=json.loads(raw)
        if receipt.get('schema')!=1 or receipt.get('id')!=payload['stageId'] or receipt.get('status')!='prepared':
            raise ValueError('Stage is not prepared')
        installer=os.path.join(home_path,'mkga-installer')
        with open(os.path.join(installer,'runtime.json'),'rb') as source:runtime=json.loads(source.read(4096))
        subprocess.Popen([runtime['python'],'-I',os.path.join(installer,'wait_apply.py'),
            '--home',home_path,'--stage',stage,'--public-key',os.path.join(installer,'trusted-public.pem'),'--kodi-pid',str(os.getpid())],
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        return True,'Application requested. Quit Kodi within ten minutes, then reopen it after application completes.',{}
    except Exception:
        return False,'Build application could not be requested; check the prepared package and local installer',{}

def execute(action,payload=None):
    payload=payload or {}
    if action=='refresh_inventory':return True,'Inventory refreshed',{}
    if action=='install_repo':
        ok=install_repo();return ok,'Repository installed' if ok else 'Repository installation failed',{}
    if action in ('install_stremio','update_stremio'):
        ok=install_stremio();return ok,(('Stremio for Kodi installed' if action=='install_stremio' else 'Stremio for Kodi update requested') if ok else 'Stremio for Kodi installation failed'),{}
    if action=='repair_stremio':
        ok=install_repo() and install_stremio();return ok,'Repository and Stremio for Kodi repaired' if ok else 'Repair failed',{}
    if action=='create_backup':return create_backup(str(payload.get('name') or ('Kodi backup · '+time.strftime('%Y-%m-%d %H:%M'))))
    if action=='install_build_url':return install_build_url(str(payload.get('url') or ''))
    if action=='prepare_mkga_build':return prepare_mkga_build(payload)
    if action=='apply_mkga_build':return apply_mkga_build(payload)
    if action=='restore_backup':
        backup_id=str(payload.get('backupId') or '')
        if not backup_id:return False,'Backup ID is missing',{}
        return restore_backup(backup_id)
    return False,'Unknown command',{}
def build_stage(home_path):
    root=os.path.join(home_path,'mkga-staged-installs');latest=None
    config=os.path.join(home_path,'mkga-installer','runtime.json')
    if os.path.isfile(config):
        try:
            if os.path.islink(config):return None
            with open(config,'rb') as source:raw=source.read(4097)
            if len(raw)>4096:return None
            runtime=json.loads(raw)
            if runtime.get('mode')=='clean-macos-app':
                from whole_app_install import configuration
                root=str(configuration(runtime,xbmcvfs.translatePath('special://xbmc'))['stagingRoot'])
        except Exception:return None
    if not os.path.isdir(root) or os.path.islink(root):return None
    for identity in os.listdir(root):
        if not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',identity):continue
        directory=os.path.join(root,identity);path=os.path.join(directory,'receipt.json')
        if os.path.islink(directory) or os.path.islink(path):continue
        try:
            with open(path,'rb') as source:raw=source.read(4097)
            if len(raw)>4096:continue
            receipt=json.loads(raw)
            if receipt.get('schema')!=1 or receipt.get('id')!=identity or receipt.get('status') not in ('prepared','applying','recovering','installed'):continue
            public={'id':identity,'status':receipt['status']}
            job_path=os.path.join(directory,'application-job.json')
            try:
                if not os.path.islink(job_path):
                    with open(job_path,'rb') as source:job_raw=source.read(4097)
                    if len(job_raw)<=4096:
                        job=json.loads(job_raw);updated=job.get('updatedAt')
                        if job.get('schema')==1 and job.get('stageId')==identity and job.get('status') in ('waiting','installed','failed') and type(updated)==int and 0<=updated<=4102444800:
                            public['application']={'status':job['status'],'updatedAt':updated}
            except (OSError,ValueError,AttributeError):pass
            entry=(os.path.getmtime(path),public)
            if latest is None or entry[0]>latest[0]:latest=entry
        except (OSError,ValueError,AttributeError):continue
    return latest[1] if latest else None

def build_prepare_ready():
    if platform.system() not in ('Darwin','Linux'):return False
    root=os.path.join(xbmcvfs.translatePath('special://home'),'mkga-installer')
    try:
        config=os.path.join(root,'runtime.json')
        if not os.path.islink(root) and not os.path.islink(config):
            with open(config,'rb') as source:raw=source.read(4097)
            if len(raw)>4096:return False
            runtime=json.loads(raw)
            if runtime.get('mode')=='clean-macos-app':
                from whole_app_install import configuration
                configuration(runtime,xbmcvfs.translatePath('special://xbmc'))
                return platform.system()=='Darwin' and bool(shutil.which('openssl'))
    except Exception:return False
    names=('remote_prepare.py','wait_apply.py','staged_install.py','dev_lifecycle.py','build_package.py','package_signature.py','assemble_nimbus.py','trusted-public.pem','runtime.json')
    try:
        if os.path.islink(root) or any(os.path.islink(os.path.join(root,name)) or not os.path.isfile(os.path.join(root,name)) for name in names):return False
        with open(os.path.join(root,'runtime.json'),'rb') as source:raw=source.read(4097)
        if len(raw)>4096:return False
        python=json.loads(raw).get('python','')
        return isinstance(python,str) and os.path.isabs(python) and os.path.isfile(python) and bool(shutil.which('openssl'))
    except Exception:return False

def build_inventory():
    result={'runtime':collect_runtime_inventory(xbmc)}
    for prefix,identity in (('skin','skin.mkga'),('service','service.mkga.build')):
        present=installed(identity);result[prefix+'Installed']=present
        try:result[prefix+'Version']=xbmcaddon.Addon(identity).getAddonInfo('version') if present else ''
        except Exception:result[prefix+'Version']=''
    stage=build_stage(xbmcvfs.translatePath('special://home'))
    if stage:result['stage']=stage
    result['signedPrepareReady']=build_prepare_ready()
    return result
def state_payload(message=''):
    return {'buildInventory':build_inventory(),'message':message,'repoInstalled':installed(REPO_ID),'addonInstalled':installed(ADDON_ID),'addonVersion':version(),'connectorInstalled':installed(CONNECTOR_ID),'connectorVersion':addon.getAddonInfo('version')}
def result_outbox():
    # Re-pairing must not report another device's old command results.
    identity=hashlib.sha256(addon.getSetting('device_id').encode()).hexdigest()
    return ResultOutbox(os.path.join(xbmcvfs.translatePath(addon.getAddonInfo('profile')),'command-results-'+identity+'.json'))
def send_result(cid,payload):return request('/commands/'+cid+'/result','POST',payload)
def report(cid,ok,message,extra=None):
    outbox=result_outbox()
    outbox.enqueue(cid,dict(state_payload(str(message)[:500]),**(extra or {}),ok=ok))
    outbox.flush(send_result)
def heartbeat():
    try:request('/heartbeat','POST',state_payload())
    except Exception:pass
def sync_discovery_settings():
    try:
        if not installed(ADDON_ID):return
        payload=request('/discovery-settings')
        profile=xbmcvfs.translatePath(addon.getAddonInfo('profile'))
        apply_discovery_settings(payload,addon.getSetting('device_id'),xbmcaddon.Addon(ADDON_ID),os.path.join(profile,'discovery-settings.json'))
    except Exception:pass
def settle_apply_commands():
    path=os.path.join(xbmcvfs.translatePath('special://home'),'mkga-installer','runtime.json')
    if not os.path.isfile(path):return
    if os.path.islink(path):raise ValueError('Invalid local runtime')
    with open(path,'rb') as source:raw=source.read(4097)
    if len(raw)>4096:raise ValueError('Invalid local runtime')
    runtime=json.loads(raw)
    if runtime.get('mode')!='clean-macos-app':return
    from whole_app_install import terminal_commands,mark_reported
    for stage,cid,ok,message in terminal_commands(runtime,xbmcvfs.translatePath('special://xbmc'),addon.getSetting('device_id')):
        # report() durably enqueues before attempting network delivery.
        report(cid,ok,message)
        mark_reported(stage,cid)

def bind_apply_command(cmd):
    home_path=xbmcvfs.translatePath('special://home')
    path=os.path.join(home_path,'mkga-installer','runtime.json')
    if not os.path.isfile(path):return
    if os.path.islink(path):raise ValueError('Invalid local runtime')
    with open(path,'rb') as source:raw=source.read(4097)
    if len(raw)>4096:raise ValueError('Invalid local runtime')
    runtime=json.loads(raw)
    if runtime.get('mode')!='clean-macos-app':return
    from whole_app_install import bind_command
    bind_command(runtime,xbmcvfs.translatePath('special://xbmc'),cmd.get('payload') or {},
                 str(cmd.get('id','')),addon.getSetting('device_id'))

def execute_command(cmd):
    cid=str(cmd.get('id',''));action=str(cmd.get('action',''))
    result_outbox().begin(cid,action)
    try:
        # A batch may have been fetched before supporter expiry or revocation.
        # Recheck the protected backend immediately before each local operation.
        authorized=request('/heartbeat','POST',state_payload())
        if not isinstance(authorized,dict) or authorized.get('ok') is not True:
            raise RuntimeError('Device authorization could not be confirmed')
        if action=='apply_mkga_build':bind_apply_command(cmd)
        ok,msg,extra=execute(action,cmd.get('payload') or {})
    except Exception as e:ok,msg,extra=False,str(e),{}
    report(cid,ok,msg,extra)
if home.getProperty('MKGA.Connector.ServiceRunning')=='true':
    raise SystemExit
home.setProperty('MKGA.Connector.ServiceRunning','true')
try:
    next_heartbeat=0;session_id=str(uuid.uuid4());session_device=None
    while not monitor.abortRequested():
        if addon.getSetting('device_token'):
            try:
                device=addon.getSetting('device_id')
                if session_device!=device:
                    response=request('/session/start','POST',{'sessionId':session_id})
                    if not isinstance(response,dict) or response.get('ok') is not True:
                        raise RuntimeError('Connector session could not be registered')
                    session_device=device
                if time.time()>=next_heartbeat:
                    heartbeat();sync_discovery_settings();next_heartbeat=time.time()+30
                settle_apply_commands()
                outbox=result_outbox()
                for cid,action in list(outbox.interrupted().items()):
                    report(cid,False,'Connector stopped during '+action+'. Outcome is unconfirmed; check this device before retrying.')
                outbox.flush(send_result)
                # Reserve room for the server's next batch of at most five.
                if len(outbox.read())>MAX_PENDING-5:
                    if monitor.waitForAbort(10):break
                    continue
                data=request('/commands') or {}
                for cmd in data.get('commands',[]):
                    execute_command(cmd)
            except Exception:pass
        if monitor.waitForAbort(10):break
finally:
    home.clearProperty('MKGA.Connector.ServiceRunning')
