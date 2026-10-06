import json, platform, urllib.request, urllib.error
import xbmc, xbmcaddon, xbmcgui, xbmcvfs
from device_proof import prepare_new_pairing, signed_headers, validate_pairing_response

API='https://mkga.tv/api/kodi/agent/pair'
BASE='https://mkga.tv/api/kodi/agent'
REPO_ID='repository.stremioforkodi';ADDON_ID='script.stremioelec';CONNECTOR_ID='service.mkga.connector'
addon=xbmcaddon.Addon()
def post(url,data,token=''):
    raw=json.dumps(data).encode('utf-8'); headers={'Content-Type':'application/json','User-Agent':'MKGA-Connector/'+addon.getAddonInfo('version')}
    if token: headers['Authorization']='Bearer '+token
    if token:headers=signed_headers(addon,xbmcvfs,BASE,url[len(BASE):],'POST',raw,headers)
    req=urllib.request.Request(url,data=raw,headers=headers,method='POST')
    with urllib.request.urlopen(req,timeout=15) as r:return json.loads(r.read().decode('utf-8'))

def installed(addon_id): return xbmc.getCondVisibility('System.HasAddon(%s)'%addon_id)
def addon_version(addon_id):
    try: return xbmcaddon.Addon(addon_id).getAddonInfo('version') if installed(addon_id) else ''
    except Exception: return ''
def inventory(message=''):
    return {'message':message,'repoInstalled':installed(REPO_ID),'addonInstalled':installed(ADDON_ID),'addonVersion':addon_version(ADDON_ID),'connectorInstalled':True,'connectorVersion':addon.getAddonInfo('version')}
def refresh_existing(token):
    post(BASE+'/heartbeat',inventory('Manual inventory refresh'),token)
    xbmc.executebuiltin('RunScript(special://home/addons/service.mkga.connector/service.py)')

def main():
    current=addon.getSetting('device_token')
    if current:
        choice=xbmcgui.Dialog().select('MKGA Connector', ['Refresh connection', 'Pair again with a new code'])
        if choice<0:return
        if choice==0:
            try:
                refresh_existing(current)
                xbmcgui.Dialog().ok('MKGA Connector','Connected to MKGA.TV. Inventory refreshed and background service started.')
            except Exception as e:
                xbmcgui.Dialog().ok('MKGA Connector','Paired, but MKGA.TV could not be reached: '+str(e))
            return
    code=xbmcgui.Dialog().numeric(0,'Enter the 6-digit code shown in MKGA.TV → My Kodi or Admin → MKGA Build')
    code=''.join(c for c in str(code or '') if c.isdigit())[:6]
    if len(code)!=6:return
    default_name=xbmc.getInfoLabel('System.FriendlyName') or platform.node() or 'Kodi device'
    name=xbmcgui.Dialog().input('Device name',defaultt=default_name,type=xbmcgui.INPUT_ALPHANUM)
    if not name:return
    try:
        protected=prepare_new_pairing(xbmcvfs)
        public_key=protected['publicKey'] if protected else None
        payload={'code':code,'name':name,'platform':platform.system(),'kodiVersion':xbmc.getInfoLabel('System.BuildVersion'),'connectorVersion':addon.getAddonInfo('version')}
        if public_key:payload['devicePublicKey']=public_key
        result=post(API,payload)
        device,token=validate_pairing_response(result,protected=bool(public_key))
        if protected:
            addon.setSetting('device_install_id',protected['installId'])
            if addon.getSetting('device_install_id')!=protected['installId']:
                raise Exception('Kodi could not persist the new protected install identity')
        addon.setSetting('device_id',device);addon.setSetting('device_token',token);addon.setSetting('device_name',name)
        if not token or addon.getSetting('device_token')!=token:raise Exception('Kodi could not persist MKGA pairing settings')
        addon.setSetting('device_proof_enabled','true' if result.get('deviceProofRequired') is True else 'false')
        try:
            refresh_existing(token)
            message='Paired successfully. Inventory refreshed and background service started.'
        except Exception:
            xbmc.executebuiltin('RunScript(special://home/addons/service.mkga.connector/service.py)')
            message='Paired successfully. Inventory refresh is pending; the background service will retry.'
        xbmcgui.Dialog().ok('MKGA Connector',message)
    except urllib.error.HTTPError as e:
        try: msg=json.loads(e.read().decode()).get('error','Pairing failed')
        except Exception: msg='Pairing failed'
        xbmcgui.Dialog().ok('MKGA Connector',msg)
    except Exception as e: xbmcgui.Dialog().ok('MKGA Connector','Could not reach MKGA.TV: '+str(e))
if __name__=='__main__':main()
