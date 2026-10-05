"""Opt-in disposable-host acceptance; secrets stay in memory and SSH stdin.

Creates/removes one RO WAN+Tailscale share and two 256 MiB test files. Existing
shares remain configured, but WebDAV restarts during fixture setup/cleanup.
Run from an external tailnet client, never against an unauthorized host.
WAN uses the host's mode: legacy HTTP on SHARE_PORT or HTTPS on its public name.
"""
import argparse
import base64
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import hashlib
import http.client
import json
import secrets
import shlex
import subprocess
import time

import konsol_session

parser = argparse.ArgumentParser()
parser.add_argument('--host', required=True)
args = parser.parse_args()
SSH = ['ssh', '-o', 'ClearAllForwardings=yes', '-o', 'BatchMode=yes',
       '-o', 'ConnectTimeout=15', args.host]
BOOT = '''import sys, json, os, pathlib, hashlib, subprocess, time
sys.path.insert(0, '/usr/local/sbin')
import master_shares as shares
m = shares.Manager('/etc/master-stack/state.env'); e = m.env
d = json.load(sys.stdin)
'''


def remote(code, data=None):
    p = subprocess.run(SSH + ['python3 -c ' + shlex.quote(BOOT + code)],
                       input=json.dumps(data), text=True, capture_output=True, timeout=120)
    if p.returncode:
        # A traceback could contain submitted test credentials; do not echo it.
        raise RuntimeError('Remote fixture failed; output withheld')
    return json.loads(p.stdout)


meta = remote('''w = m.wan_info()
print(json.dumps({
 'tail': e['TAILSCALE_IPV4'], 'wan': e['WAN_IPV4'], 'port': int(e['SHARE_PORT']),
 'wan_mode': w['mode'], 'wan_domain': w['domain'], 'wan_port': int(w['port'] or 0),
 'wan_available': w['available'],
 'panel_port': int(e['CADDY_HTTP_PORT']), 'host': 'panel.'+e['LOCAL_DOMAIN'],
 'before': hashlib.sha256(pathlib.Path(m.path).read_bytes()).hexdigest()}))''')
assert meta['wan_available'] and meta['wan_mode'] in ('http', 'https'), 'Requires an available WAN share transport'


# DD-194: Konsol through Caddy needs a session; a short root-issued one, closed at the end.
COOKIE = konsol_session.open_session(SSH)


def panel_get(path):
    c = http.client.HTTPConnection(meta['tail'], meta['panel_port'], timeout=20)
    try:
        c.request('GET', path, headers={'Host': meta['host'], 'X-Konsol': '1', 'Cookie': COOKIE,
                                       'Connection': 'close'})
        r = c.getresponse(); body = r.read()
        if r.status == 200:
            json.loads(body)
        return r.status
    finally:
        c.close()


for name, paths in (
    ('Konsol', ['/api/konsol/kaynaklar', '/api/konsol/ayarlar', '/api/konsol/moduller']),
    ('Files', ['/api/state', '/api/list?path=downloads'])):
    with ThreadPoolExecutor(max_workers=20) as pool:
        codes = list(pool.map(panel_get, [paths[i % len(paths)] for i in range(100)]))
    print(name, '20 parallel / 100 fresh client connections:', dict(Counter(codes)), flush=True)
    assert codes == [200] * 100

print('Unix cold connections:', remote('''
import http.client, socket
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
class U(http.client.HTTPConnection):
 def connect(self):
  self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
  self.sock.settimeout(10); self.sock.connect(e['PANEL_SOCKET'])
def check(_):
 c=U('localhost',timeout=10)
 try:
  c.request('GET','/api/konsol/kaynaklar',headers={'Host':'panel.'+e['LOCAL_DOMAIN'],
   'X-Konsol':'1','Connection':'close'})
  r=c.getresponse(); r.read(); return r.status
 finally: c.close()
with ThreadPoolExecutor(max_workers=24) as pool: codes=list(pool.map(check,range(120)))
assert codes==[200]*120
print(json.dumps(dict(Counter(codes))))
'''), flush=True)

name = 'audit-' + secrets.token_hex(5)
password = secrets.token_hex(20)
item = None


def memory():
    return remote('''
cg=subprocess.check_output(['systemctl','show','master-paylasim.service','-p','ControlGroup','--value'],text=True).strip()
p=pathlib.Path('/sys/fs/cgroup')/cg.lstrip('/')
stat=dict(line.split() for line in (p/'memory.stat').read_text().splitlines())
out={k:int(stat[k]) for k in ('anon','file','sock','kernel')}
out.update(current=int((p/'memory.current').read_text()),peak=int((p/'memory.peak').read_text()))
events=dict(line.split() for line in (p/'memory.events').read_text().splitlines())
out.update(oom=int(events['oom']),oom_kill=int(events['oom_kill']))
assert out['oom']==0 and out['oom_kill']==0, 'WebDAV memory limit reached OOM'
print(json.dumps(out))
''')


def dav(network, method='GET', leaf='', headers=None, expected=200):
    if network == 'tail':
        c = http.client.HTTPConnection(meta['tail'], meta['port'], timeout=20)
    elif meta['wan_mode'] == 'https':
        c = http.client.HTTPSConnection(meta['wan_domain'], meta['wan_port'], timeout=20)
    else:
        c = http.client.HTTPConnection(meta['wan'], meta['wan_port'], timeout=20)
    start = time.monotonic()
    auth = base64.b64encode((name + ':' + password).encode()).decode()
    h = {'Authorization': 'Basic ' + auth, 'Connection': 'close'}
    h.update(headers or {})
    count = 0
    digest = hashlib.sha256()
    try:
        c.request(method, '/s/' + item['id'] + '/' + leaf, headers=h)
        r = c.getresponse()
        assert r.status == expected, (network, method, r.status)
        while True:
            block = r.read(1024 * 1024)
            if not block:
                break
            count += len(block); digest.update(block)
    finally:
        c.close()
    return count, digest.hexdigest(), time.monotonic() - start


try:
    fixture = remote('''
assert d['name'].startswith('audit-') and '/' not in d['name']
root=pathlib.Path(e['DOWNLOADS_PATH'])/d['name']; root.mkdir(mode=0o775)
os.chown(root,int(e['DOWNLOADS_UID']),int(e['DOWNLOADS_GID'])); root.chmod(0o775)
block=os.urandom(1024*1024); digest=hashlib.sha256()
for _ in range(256): digest.update(block)
for name in ('wan.bin','tail.bin'):
 with (root/name).open('xb') as f:
  for _ in range(256): f.write(block)
  f.flush(); os.fsync(f.fileno())
  # Evict only the test file's clean pages; never drop the host's global cache.
  os.posix_fadvise(f.fileno(),0,0,os.POSIX_FADV_DONTNEED)
 os.chown(root/name,int(e['DOWNLOADS_UID']),int(e['DOWNLOADS_GID']))
result=m.change('save',{'path':str(root.relative_to(e['SERVER_ROOT'])),
 'username':d['name'],'password':d['password'],
 'connections':{scope:{'enabled':True,'permission':'ro','days':1} for scope in ('tailscale','wan')},
 'ack_wan_http':True})
item=next(i for i in result['items'] if i['username']==d['name'])
print(json.dumps({'item':{'id':item['id']},'sha256':digest.hexdigest()}))
''', dict(name=name, password=password))
    item = fixture['item']
    print('Memory baseline (bytes):', memory(), flush=True)
    for network in ('wan', 'tail'):
        size, digest, elapsed = dav(network, leaf=network + '.bin')
        assert size == 256 * 1024 * 1024 and digest == fixture['sha256']
        print(network, '256 MiB verified:', round(size / elapsed / 1e6, 2), 'MB/s;',
              'memory (bytes):', memory(), flush=True)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: dav(network, 'PROPFIND', headers={'Depth': '1'},
                                                 expected=207), range(40)))
        print(network, '4 parallel PROPFIND: 40/40 HTTP 207', flush=True)
        assert dav(network, leaf=network+'.bin', headers={'Range':'bytes=0-99'}, expected=206)[0] == 100
    print('PASS: RO share, WAN/Tailscale GET, Range and directory scans', flush=True)
finally:
    result = remote('''
import shutil
assert d['name'].startswith('audit-') and '/' not in d['name']
root=pathlib.Path(e['DOWNLOADS_PATH'])/d['name']
relative=str(root.relative_to(e['SERVER_ROOT']))
for item in list(m.read()['items']):
 if item['path']==relative and item['username']==d['name']:
  for attempt in range(10):
   try:
    m.change('remove',{'id':item['id']}); break
   except shares.ShareError:
    if attempt==9: raise
    time.sleep(.5)
assert not root.is_symlink() and root.parent==pathlib.Path(e['DOWNLOADS_PATH'])
if root.exists(): shutil.rmtree(root)
print(json.dumps({'fixture_removed':not root.exists(),
 'existing_registry_unchanged':hashlib.sha256(pathlib.Path(m.path).read_bytes()).hexdigest()==d['before']}))
''', dict(name=name, before=meta['before']))
    konsol_session.close_session(SSH, COOKIE)
    print('Cleanup:', result, flush=True)
    assert all(result.values())
