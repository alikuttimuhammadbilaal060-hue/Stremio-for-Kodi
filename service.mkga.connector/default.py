import json, platform, urllib.request, urllib.error
import xbmc, xbmcaddon, xbmcgui

API='https://mkga.tv/api/kodi/agent/pair'
BASE='https://mkga.tv/api/kodi/agent'
REPO_ID='repository.stremioforkodi';ADDON_ID='script.stremioelec';CONNECTOR_ID='service.mkga.connector'
addon=xbmcaddon.Addon()
def post(url,data,token=''):
    raw=json.dumps(data).encode('utf-8'); headers={'Content-Type':'application/json','User-Agent':'MKGA-Connector/'+addon.getAddonInfo('version')}
    if token: headers['Authorization']='Bearer '+token
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
        try:
            refresh_existing(current)
            xbmcgui.Dialog().ok('MKGA Connector','Connected to MKGA.TV. Inventory refreshed and background service started.')
        except Exception as e:
            xbmcgui.Dialog().ok('MKGA Connector','Paired, but MKGA.TV could not be reached: '+str(e))
        return
    code=xbmcgui.Dialog().numeric(0,'Enter the 6-digit code shown in MKGA.TV → Account → My Kodi')
    code=''.join(c for c in str(code or '') if c.isdigit())[:6]
    if len(code)!=6:return
    default_name=xbmc.getInfoLabel('System.FriendlyName') or platform.node() or 'Kodi device'
    name=xbmcgui.Dialog().input('Device name',defaultt=default_name,type=xbmcgui.INPUT_ALPHANUM)
    if not name:return
    try:
        result=post(API,{'code':code,'name':name,'platform':platform.system(),'kodiVersion':xbmc.getInfoLabel('System.BuildVersion'),'connectorVersion':addon.getAddonInfo('version')})
        addon.setSetting('device_id',str(result.get('deviceId','')));addon.setSetting('device_token',str(result.get('deviceToken','')));addon.setSetting('device_name',name)
        refresh_existing(str(result.get('deviceToken','')))
        xbmcgui.Dialog().ok('MKGA Connector','Paired successfully. Inventory refreshed and background service started.')
    except urllib.error.HTTPError as e:
        try: msg=json.loads(e.read().decode()).get('error','Pairing failed')
        except Exception: msg='Pairing failed'
        xbmcgui.Dialog().ok('MKGA Connector',msg)
    except Exception as e: xbmcgui.Dialog().ok('MKGA Connector','Could not reach MKGA.TV: '+str(e))
if __name__=='__main__':main()
