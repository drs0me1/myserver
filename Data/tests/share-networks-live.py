#!/usr/bin/env python3
"""Opt-in disposable-host tests from an external client. No real share is exposed.

Run on the operator Mac: python3 Data/tests/share-networks-live.py --host nrm
Uses SSH only for fixture/API management; DAV requests use the actual WAN/tail IP.
Secrets remain in process memory and SSH stdin, never argv/output.
Legacy HTTP WAN mode only (no HTTPS setting); other hosts exit 3 before any change.
"""
import argparse
import base64
import http.client
import json
import secrets
import shlex
import socket
import subprocess
import sys
import time

parser=argparse.ArgumentParser()
parser.add_argument("--host",required=True)
args=parser.parse_args()

def remote(code, data=None):
    p=subprocess.run(["ssh","-o","ClearAllForwardings=yes","-o","BatchMode=yes","-o","ConnectTimeout=15",args.host,
                      "python3 -c "+shlex.quote(code)],input=json.dumps(data),text=True,capture_output=True,timeout=120)
    if p.returncode:
        raise RuntimeError("Remote fixture/worker failed (details withheld to protect test credentials)")
    return json.loads(p.stdout) if p.stdout.strip() else None

BOOT="""import sys,json,os,pathlib,shutil,time
sys.path.insert(0,'/usr/local/sbin')
import master_shares as s
m=s.Manager('/etc/master-stack/state.env'); e=m.env
d=json.load(sys.stdin)
"""
mode=remote(BOOT+"print(json.dumps(m.wan_info()['mode']))",{})
if mode!="http":
    print("SKIP: legacy HTTP WAN mode required; this host's WAN mode is %r. "
          "Use share-connections-live.py or https-live.py instead." % mode, file=sys.stderr)
    sys.exit(3)
root="wan-test-"+secrets.token_hex(5)
metadata=remote(BOOT+"""
root=pathlib.Path(e['DOWNLOADS_PATH'])/d['root']; root.mkdir()
os.chown(root,int(e['DOWNLOADS_UID']),int(e['DOWNLOADS_GID'])); root.chmod(0o775)
for name in ('tail','wan','both'):
 p=root/name; p.mkdir(); os.chown(p,int(e['DOWNLOADS_UID']),int(e['DOWNLOADS_GID'])); p.chmod(0o775)
 (p/'sample.txt').write_bytes(b'abcdefghij')
 os.chown(p/'sample.txt',int(e['DOWNLOADS_UID']),int(e['DOWNLOADS_GID']))
print(json.dumps({'tail':e['TAILSCALE_IPV4'],'wan':e['WAN_IPV4'],'port':int(e['SHARE_PORT']),
 'relative':str(root.relative_to(e['SERVER_ROOT'])),'before':[i['id'] for i in m.read()['items']]}))
""",dict(root=root))

# DD-180: root backend and Caddy admin are Unix sockets; Konsol refuses requests Caddy relays from the host itself.
UNIX = """
import http.client,socket
class U(http.client.HTTPConnection):
 def __init__(self,path,timeout): super().__init__('localhost',timeout=timeout); self.p=path
 def connect(self):
  self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); self.sock.settimeout(self.timeout); self.sock.connect(self.p)
"""

def api(action, data):
    return remote(BOOT+UNIX+"""
c=U(e['PANEL_SOCKET'],100)
c.request('POST','/api/konsol/paylasim/'+d['action'],json.dumps(d['data']),
 {'Host':'panel.'+e['LOCAL_DOMAIN'],'X-Konsol':'1','Origin':'http://panel.'+e['LOCAL_DOMAIN'],'Content-Type':'application/json'})
r=c.getresponse(); data=json.loads(r.read()); c.close()
if r.status!=200: raise RuntimeError('API rejected test operation')
print(json.dumps(data))
""",dict(action=action,data=data))

items={}; passwords={name:secrets.token_hex(20) for name in ('tail','wan','both')}
def request(network, name, method="GET", leaf="sample.txt", extra=None, password=None, body=None, expected=200):
    item=items[name]
    auth=base64.b64encode((item['username']+":"+(password if password is not None else passwords[name])).encode()).decode()
    headers={'Authorization':'Basic '+auth}; headers.update(extra or {})
    c=http.client.HTTPConnection(metadata[network],metadata['port'],timeout=8)
    try:
        c.request(method,'/s/'+item['id']+'/'+leaf,body,headers)
        r=c.getresponse(); payload=r.read(); result=(r.status,payload,dict(r.getheaders()))
    finally: c.close()
    assert result[0]==expected,(network,name,method,result[0],expected)
    return result

def check_rules():
    return remote(BOOT+UNIX+"""
import subprocess,http.client
p=subprocess.run([e['SBIN_DIR']+'/master-firewall','--check'],capture_output=True)
assert p.returncode==0
r=subprocess.run(['iptables','-S',e['CHAIN_SETTINGS']],capture_output=True,text=True,check=True).stdout
counts=subprocess.run(['iptables','-nvxL',e['CHAIN_INPUT']],capture_output=True,text=True,check=True).stdout
packets=sum(int(line.split()[0]) for line in counts.splitlines() if 'dpt:'+e['SHARE_PORT'] in line)
c=U(e['CADDY_ADMIN_SOCKET'],3)
c.request('GET','/config/apps/http/servers'); servers=json.loads(c.getresponse().read()); c.close()
public=[v for v in servers.values() if e['WAN_IPV4']+':'+e['SHARE_PORT'] in v.get('listen',[])]
bounded=bool(public) and all(v.get('read_header_timeout')==10000000000 and v.get('idle_timeout')==30000000000 for v in public)
print(json.dumps({'ip_limit':'share-ip' in r,'total_limit':'share-total' in r,
 'active':m.wan_active(),'site':os.path.exists(e['CADDY_MODULES_DIR']+'/paylasim-wan.caddy'),'wan_packets':packets,'edge_timeouts':bounded}))
""",{})

try:
    for name,nets in (('tail',['tailscale']),('wan',['wan']),('both',['tailscale','wan'])):
        d=dict(path=metadata['relative']+'/'+name,username=root+'-'+name,password=passwords[name],
               connections={scope:dict(enabled=scope in nets,permission='rw' if name=='both' else 'ro',
                                       ack_write=True,days=1) for scope in ('tailscale','wan')},ack_wan_http=True)
        result=api('kaydet',d)
        items[name]=next(i for i in result['items'] if i['username']==d['username'])
    rules=check_rules()
    assert all(rules[k] for k in ('ip_limit','total_limit','active','site','edge_timeouts')),rules
    initial_wan_packets=rules['wan_packets']
    print('PASS: public listener and managed firewall/TCP limits created only for opted-in test shares',flush=True)
    for name,nets in (('tail',['tail']),('wan',['wan']),('both',['tail','wan'])):
        for net in ('tail','wan'):
            if net in nets:
                assert request(net,name)[1]==b'abcdefghij'
                request(net,name,'PROPFIND','',extra={'Depth':'1'},expected=207)
                assert request(net,name,extra={'Range':'bytes=2-4'},expected=206)[1]==b'cde'
            else:
                for method in ('GET','OPTIONS','PROPFIND'):
                    request(net,name,method,expected=403)
    request('wan','tail',extra={'X-Share-Client-IP':'100.64.0.8','X-Forwarded-For':'100.64.0.8'},expected=403)
    request('wan','wan','PUT','sample.txt',body=b'no',expected=403)
    request('wan','both','PUT','new.txt',body=b'test',expected=201)
    assert request('tail','both',leaf='new.txt')[1]==b'test'
    request('wan','both','DELETE','new.txt',expected=204)
    print('PASS: Tailscale-only / WAN-only / both, PROPFIND, ranges, RO/RW and forged-header isolation',flush=True)
    for path in ('/','/api/state','/api/konsol/paylasim','/api/v2/app/preferences'):
        for host in (metadata['wan'],'panel.ayc','torrent.ayc','paylas.ayc'):
            c=http.client.HTTPConnection(metadata['wan'],metadata['port'],timeout=5)
            try:
                c.request('GET',path,headers={'Host':host}); r=c.getresponse(); r.read()
                assert r.status in (404,421),(path,host,r.status)
            finally:c.close()
    print('PASS: public port cannot route console, Files API or qBittorrent even with forged Host',flush=True)
    idle=[]; rejected=0
    try:
        for _ in range(20):
            try: idle.append(socket.create_connection((metadata['wan'],metadata['port']),timeout=.7))
            except OSError: rejected+=1
        assert 0<len(idle)<=16 and rejected>0,(len(idle),rejected)
        request('tail','tail')
        print('PASS: WAN TCP admission rejects excess idle sockets before HTTP; tailnet stays available',flush=True)
    finally:
        for conn in idle: conn.close()
    time.sleep(1)
    sockets=[]
    try:
        auth=base64.b64encode((items['both']['username']+':'+passwords['both']).encode()).decode()
        for index in range(4):
            conn=socket.create_connection((metadata['wan'],metadata['port']),timeout=5)
            conn.sendall(('PUT /s/%s/hold-%d HTTP/1.1\r\nHost: %s:%d\r\nAuthorization: Basic %s\r\nContent-Length: 1000000\r\nExpect: 100-continue\r\n\r\n'
                %(items['both']['id'],index,metadata['wan'],metadata['port'],auth)).encode())
            sockets.append(conn)
        time.sleep(1)
        request('wan','wan',expected=503)
        request('tail','tail')
        print('PASS: four simultaneous WAN requests cap this client; tailnet remains available',flush=True)
    finally:
        for conn in sockets: conn.close()
    time.sleep(1)
    for i in range(5):
        result=request('wan','wan',password='intentionally-wrong',extra={'X-Share-Client-IP':'198.51.100.'+str(i+1)},expected=401 if i<4 else 429)
    assert 1<=int(result[2]['Retry-After'])<=300
    request('wan','wan',expected=429)
    request('tail','tail')
    print('PASS: five failures block even the correct WAN password with Retry-After; spoofed IP cannot evade; tailnet unaffected',flush=True)
    assert check_rules()['wan_packets']>initial_wan_packets,'Public requests did not traverse the WAN ingress rule'
    print('PASS: WAN ingress packet counter confirms requests came through the actual external interface',flush=True)
    for name in ('wan','both'):
        api('kaydet',dict(id=items[name]['id'],connections={'wan':{'enabled':False}}))
    rules=check_rules(); assert not any(rules.values()),rules
    try:
        c=socket.create_connection((metadata['wan'],metadata['port']),timeout=2)
    except (OSError,socket.timeout): pass
    else:
        c.close(); raise AssertionError('Public listener still reachable after last share paused')
    request('tail','tail')
    print('PASS: last WAN pause removes public listener, permission and TCP limit rules; tailnet share survives',flush=True)
    request('tail','both')
    # Only this test-owned share gets a short expiry; production API keeps day presets.
    api('kaydet',dict(id=items['both']['id'],connections={'wan':{'enabled':True}},ack_wan_http=True))
    remote(BOOT+"""
data=m.read(); item=next(i for i in data['items'] if i['id']==d['id'])
assert item['path'].startswith(d['relative']+'/')
item['connections']['wan']['expires']=int(time.time())+3
s.atomic(m.path,data); m.restart(); m.publish()
print('{}')
""",dict(id=items['both']['id'],relative=metadata['relative']))
    time.sleep(4)
    request('tail','both')
    try:
        request('wan','both',expected=403)
    except OSError: pass  # Timer may already have removed the listener.
    deadline=time.monotonic()+40
    while True:
        closed=remote(BOOT+"print(json.dumps(not os.path.exists(e['CADDY_MODULES_DIR']+'/paylasim-wan.caddy')))",{})
        if closed:
            try:
                expired=check_rules()
                if not expired['site']: break
            except RuntimeError: pass  # The guarded firewall update may still be in flight.
        assert time.monotonic()<deadline,'Expiry timer did not close WAN publication'
        time.sleep(2)
    print('PASS: expiry rejects access and the scheduled guard removes the last WAN listener/permission',flush=True)
finally:
    # Exact, test-owned prefix. No existing user account or folder is removed.
    remote(BOOT+"""
root=pathlib.Path(e['DOWNLOADS_PATH'])/d['root']
assert root.name.startswith('wan-test-') and root.parent==pathlib.Path(e['DOWNLOADS_PATH'])
for item in list(m.read()['items']):
 if item['path'].startswith(d['relative']+'/') and item['id'] not in d['before']:
  deadline=time.monotonic()+15
  while True:
   try:
    m.change('remove',{'id':item['id']}); break
   except s.ShareError:
    if time.monotonic()>=deadline: raise
    time.sleep(.5)
shutil.rmtree(root)
print(json.dumps({'clean':not root.exists(),'remaining_ids':[i['id'] for i in m.read()['items']]}))
""",dict(root=root,relative=metadata['relative'],before=metadata['before']))
    print('CLEANUP: temporary test shares and fixture files removed; existing accounts retained',flush=True)
