#!/usr/bin/env python3
"""Ownership-aware inventory and asynchronous, bounded container operations.

Reads stay in the panel sandbox. Every write runs this CLI in a separate root transient unit;
application lifecycle uses its package engine, other operations use the dedicated worker.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import uuid

import master_settings as settings
import master_container_config as config
from master_containers import Containers, ContainerError, epoch, listening, mask, name_of, ports_of, TAILS, update_status

ACTIONS = frozenset(('create', 'save', 'start', 'stop', 'restart', 'remove', 'adopt', 'image-pull',
                     'image-remove', 'image-update', 'volume-create', 'volume-remove', 'network-create', 'network-remove'))
JOB_RE = re.compile(r'[0-9a-f]{32}\Z')
APP_ACTIONS = {'start': 'baslat', 'stop': 'durdur', 'restart': 'yeniden-baslat', 'remove': 'kaldir'}
# DD-214: image update checks read registry manifests only and are cached; the page asks on open,
# the operator can ask again. No timer and no automatic update: an update is an explicit operation.
UPDATE_TTL = 6 * 3600
UPDATE_MIN_INTERVAL = 60


def app_specs(env):
    """Package names come from installed manifests, never browser-provided executable paths."""
    try:
        raw = settings.read_regular(env['MODULES_FILE'], 65536)[0].decode()
    except FileNotFoundError:
        return {}
    except (OSError, KeyError, ValueError, UnicodeError) as err:
        raise ContainerError(503, 'Uygulama kaydı okunamadı.') from err
    states = {}
    for line in raw.splitlines():
        bits = line.split()
        if len(bits) == 2 and bits[1] in ('calisiyor', 'durduruldu'):
            states[bits[0]] = bits[1]
    result = {}
    for mid, manifest in settings.read_manifests(env).items():
        slot = manifest.get('PAKET_KONTEYNER', '')
        if mid not in states or not re.fullmatch(r'[a-z][a-z0-9-]{1,30}\.container', slot):
            continue
        name = slot[:-10]
        result[name] = {'name': name, 'module_id': mid, 'manifest': manifest, 'module_state': states[mid],
                        'unit': name + '.service', 'image': manifest.get('PAKET_IMAJ', ''),
                        'adapter': manifest.get('PAKET_KONTEYNER_YONETIM', ''),
                        'channel': manifest.get('PAKET_IMAJ_KANAL', '')}
    return result


def app_config(env, app):
    if not app['adapter']:
        return {'config': None, 'editable': [], 'protected_mounts': [],
                'revision': hashlib.sha256((app['module_id'] + app['module_state']).encode()).hexdigest()}
    try:
        module = settings.load_package_module(env, app['module_id'], app['adapter'], 'container_config', 'Konteyner ayar aracı')
        effective = dict(env, **settings.package_env(env, app['module_id']))
        result = module.container_config(effective)
        if not isinstance(result, dict) or not isinstance(result.get('revision'), str):
            raise ValueError('adapter response')
        return result
    except (OSError, KeyError, ValueError, settings.SettingsError) as err:
        raise ContainerError(503, 'Uygulamanın konteyner ayarları okunamadı.') from err


def port_scope(ip, env):
    """DD-217: the access a published host address gives; the guard decides what passes."""
    if ip in ('127.0.0.1', '::1'):
        return 'local'
    if ip and ip in (env.get('TAILSCALE_IPV4'), env.get('TAILSCALE_IPV6')):
        return 'tailscale'
    if ip in ('', '0.0.0.0', '::') or ip in (env.get('WAN_IPV4'), env.get('WAN_IPV6')):
        return 'public'
    return 'other'


def definition_row(d):
    return {'id': '', 'name': d['name'], 'image': d['image'], 'state': 'stopped', 'status': '',
            'unit': 'konsol-' + d['name'] + '.service', 'network': d.get('network', ''),
            'ports': [], 'mounts': len(d.get('mounts', [])), 'created': None, 'started': None,
            'finished': None, 'exit_code': 0, 'restarts': 0, 'health': ''}


def memory_bytes(value):
    if isinstance(value,(int,float)) and value>=0:
        return int(value)
    match=re.match(r'^\s*([0-9]+(?:\.[0-9]+)?)\s*([KMGT]?)(i?)B(?:\s*/|\s*$)',str(value),re.I)
    if not match: return None
    power={'':0,'K':1,'M':2,'G':3,'T':4}[match[2].upper()]
    return int(float(match[1])*(1024 if match[3] else 1000)**power)


class Inventory(Containers):
    def __init__(self, service):
        super().__init__(lambda argv, timeout: service.panel.run_tool(argv, timeout=timeout))
        self.service = service
        self.env = settings.env_read(service.panel.args.state)
        self.apps = app_specs(self.env)
        try:
            self.definitions = {d['name']: d for d in config.Store(self.env).list()} if self.env.get('KONTEYNER_STATE_DIR') else {}
        except config.ContainerConfigError as err:
            raise ContainerError(err.status, str(err)) from err
        self.cache = {}

    def podman(self, *args, timeout=20):
        if args not in self.cache:
            self.cache[args] = super().podman(*args, timeout=timeout)
        return self.cache[args]

    def inspect(self, name):
        ok, raw, _ = self.podman('inspect', '--type', 'container', name)
        try:
            return json.loads(raw)[0] if ok else None
        except (ValueError, TypeError, IndexError):
            return None

    def decorate(self, row, details=False):
        name = row['name']
        app, d = self.apps.get(name), self.definitions.get(name)
        row.update(live=bool(row.get('id')), source='external', management_id='external:' + name,
                   module_id=None, revision=None, actions=[], restricted_reason='',
                   cpu_percent=None, memory_bytes=None, busy=self.service.busy(name), health=row.get('health', ''), listening=None)
        raw = self.inspect(name) if row['live'] else None
        if raw:
            row['health'] = ((raw.get('State') or {}).get('Health') or {}).get('Status') or row['health']
        running = row.get('state') == 'running'
        # DD-215: no port mappings on the host network; show the sockets the container listens on.
        if raw and running and (raw.get('HostConfig') or {}).get('NetworkMode') == 'host':
            addresses = lambda *keys: {self.env.get(k, '') for k in keys} - {''}
            row['listening'] = listening((raw.get('State') or {}).get('Pid'), wan=addresses('WAN_IPV4', 'WAN_IPV6'),
                                         tailscale=addresses('TAILSCALE_IPV4', 'TAILSCALE_IPV6'))
        lifecycle = ['stop', 'restart'] if running else ['start']
        if app:
            row.update(source='appstore', management_id='appstore:' + app['module_id'], module_id=app['module_id'], unit=app['unit'])
            if not row['live']:
                row['state'] = 'stopped' if app['module_state'] == 'durduruldu' else 'unknown'
                if details: row['mounts'] = []
            row['actions'] = (['stop', 'restart'] if running else ['start']) + ['remove']
            # DD-214: a package that names an update channel and an adapter can move its pinned image.
            if app.get('channel') and app.get('adapter'):
                row['actions'].append('image-update')
            try:
                value = app_config(self.env, app)
                row['revision'] = value['revision']
                if value.get('editable'):
                    row['actions'].append('save')
                if details:
                    row.update(value)
                    row['effective_autostart'] = app['module_state'] == 'calisiyor'
            except ContainerError as err:
                row['restricted_reason'] = str(err)
        elif d:
            row.update(source='konsol', management_id='konsol:' + name, revision=d['revision'],
                       unit='konsol-' + name + '.service', actions=lifecycle + ['save', 'remove', 'image-update'],
                       effective_autostart=bool(d.get('autostart') and not d.get('manual_stop')))
            if not row['live']:
                row['ports'] = [{'host_ip': {'local':'127.0.0.1','tailscale':self.env.get('TAILSCALE_IPV4',''),'public':'0.0.0.0'}[p['scope']],
                                 **{k:p[k] for k in ('host_port','container_port','protocol')}} for p in d.get('ports', [])]
            if details:
                row.update(config=config.redact(d), editable=['ports','mounts','environment','command','autostart','restart','cpus','memory','image','network','user'], protected_mounts=[])
                if not row['live']:
                    row['mounts'] = [{'type':m['type'], 'source':m['source'], 'destination':m['destination'],
                                      'rw':not m['read_only'], 'name':m['source'] if m['type']=='volume' else ''} for m in d.get('mounts', [])]
        else:
            if raw:
                own = config.ownership(raw, self.env)
                # Worker repeats discovery under its mutation lock; the view is not authority.
                standalone = own == 'standalone' or (isinstance(own, dict) and own.get('kind') == 'standalone')
                if standalone:
                    row['actions'] = lifecycle + ['remove','adopt']
                else:
                    row['restricted_reason'] = 'Konteyner başka bir yöneticiye ait veya desteklenmeyen seçenekler kullanıyor.'
            else:
                row['restricted_reason'] = 'Konteynerin yönetim kaynağı doğrulanamadı; listeyi yenileyin.'
        if row['live'] and (app or d):
            labels = ((raw or {}).get('Config') or {}).get('Labels') or {}
            expected = labels.get('PODMAN_SYSTEMD_UNIT') == row['unit'] if app else raw and config.ownership(raw,self.env)=='konsol'
            if not expected:
                row['actions'] = []
                row['restricted_reason'] = 'Bu adın çalışan konteyneri kayıtlı yöneticiyle eşleşmiyor; işlem yapılmadı.'
        if row['live'] and row['state'] not in ('running','stopped','exited','created','configured'):
            row['actions'] = []
            row['restricted_reason'] = 'Konteyner duraklatılmış veya geçiş durumunda; önce asıl yöneticisinden durumunu düzeltin.'
        row['update'] = self.service.update_of(name) if (app or d) else None
        for port in row.get('ports') or []:
            if isinstance(port, dict):
                port['scope'] = port_scope(port.get('host_ip', ''), self.env)
        return row

    def liste(self):
        answer = super().liste()
        rows = {r['name']: r for r in answer['containers']}
        for name, d in self.definitions.items():
            rows.setdefault(name, definition_row(d))
        for name, app in self.apps.items():
            rows.setdefault(name, dict(definition_row({'name':name,'image':app['image'],'network':'host'}),unit=app['unit']))
        answer['containers'] = [self.decorate(row) for row in rows.values()]
        answer['storage']['containers'] = len(rows)
        answer['resource_errors'] = {}
        answer['volumes'], answer['networks'] = [], []
        if not answer['runtime']['ok']:
            answer['resource_errors'] = {k:answer['runtime']['error'] for k in ('images','volumes','networks','stats')}
            return answer
        ok, stats, _ = self.podman('stats','--no-stream','--format','json',timeout=15)
        if ok and isinstance(stats,list):
            by_name = {s.get('Name') or s.get('name'):s for s in stats if isinstance(s,dict)}
            for row in answer['containers']:
                s = by_name.get(row['name'],{})
                cpu=next((s[k] for k in ('cpu_percent','CPU','CPUPerc') if k in s),None)
                try: row['cpu_percent'] = float(str(cpu).rstrip('%'))
                except (ValueError,TypeError): pass
                mem=next((s[k] for k in ('MemUsageBytes','mem_usage','MemUsage') if k in s),None)
                row['memory_bytes'] = memory_bytes(mem)
        else:
            answer['resource_errors']['stats'] = 'Kaynak kullanımı okunamadı.'
        raw_details = [self.inspect(n) for n,r in rows.items() if r.get('id')]
        uses = {'image':{},'volume':{},'network':{}}
        for r in raw_details:
            if not r: continue
            name = str(r.get('Name','')).lstrip('/')
            for image in (r.get('Image'),r.get('ImageName')):
                if image: uses['image'].setdefault(image,set()).add(name)
            for m in r.get('Mounts') or []:
                if m.get('Type') == 'volume': uses['volume'].setdefault(m.get('Name',''),set()).add(name)
            for network in (r.get('NetworkSettings') or {}).get('Networks') or {}:
                uses['network'].setdefault(network,set()).add(name)
        for d in self.definitions.values():
            uses['image'].setdefault(d['image'],set()).add(d['name'])
            network=d.get('network','')
            if network=='bridge': network=self.env.get('KONTEYNER_NETWORK','')
            uses['network'].setdefault(network,set()).add(d['name'])
            for m in d.get('mounts',[]):
                if m['type']=='volume': uses['volume'].setdefault(m['source'],set()).add(d['name'])
        ok, images, error = self.podman('images','--format','json')
        if ok and isinstance(images,list):
            answer['images'] = []
            pinned = {a['image'] for a in self.apps.values()}
            for i in images:
                refs = i.get('Names') or i.get('names') or i.get('RepoTags') or ['<adsız>']
                ident = i.get('Id') or i.get('ID') or i.get('id') or ''
                digests = set(i.get('RepoDigests') or i.get('repoDigests') or [])
                digest = i.get('Digest') or i.get('digest') or ''
                if re.fullmatch(r'sha256:[0-9a-f]{64}',digest):
                    for ref in refs:
                        repo=ref.split('@')[0]
                        if ':' in repo.rsplit('/',1)[-1]: repo=repo.rsplit(':',1)[0]
                        digests.add(repo+'@'+digest)
                users = set(uses['image'].get(ident,[]))
                for ref in set(refs)|digests: users.update(uses['image'].get(ref,[]))
                is_pinned = bool((set(refs)|digests) & pinned) or any(a['name'] in users for a in self.apps.values())
                for ref in refs:
                    answer['images'].append({'id':ident,'name':ref,'size':i.get('Size',i.get('size')),'created':epoch(i.get('Created',i.get('created'))),
                                              'used_by':sorted(users),'managed':not is_pinned,'pinned':is_pinned})
        else: answer['resource_errors']['images'] = 'İmajlar okunamadı: ' + error
        for kind, command in (('volumes','volume'),('networks','network')):
            ok, resources, error = self.podman(command,'ls','--format','json')
            if not ok or not isinstance(resources,list):
                answer['resource_errors'][kind] = ('Birimler' if kind=='volumes' else 'Ağlar') + ' okunamadı: ' + error
                continue
            for r in resources:
                name=r.get('Name') or r.get('name') or ''
                if not name: continue
                labels=r.get('Labels') or r.get('labels') or {}
                row={'name':name,'driver':r.get('Driver') or r.get('driver') or '',
                     'used_by':sorted(uses['volume' if kind=='volumes' else 'network'].get(name,[])),
                     'managed':labels.get('io.master-stack.managed') == 'konsol'}
                if kind=='volumes': row['size']=None
                else:
                    subnets=r.get('Subnets') or r.get('subnets') or []
                    row.update(id=r.get('Id') or r.get('id') or '',
                               subnets=[s.get('subnet','') if isinstance(s,dict) else str(s) for s in subnets],
                               internal=bool(r.get('Internal') or r.get('internal')))
                answer[kind].append(row)
        return answer

    def ayrinti(self,name):
        name_of(name)
        try:
            row=super().ayrinti(name)
        except ContainerError as err:
            if err.status!=404: raise
            if name in self.definitions: row=definition_row(self.definitions[name])
            elif name in self.apps: row=definition_row({'name':name,'image':self.apps[name]['image'],'network':'host'})
            else: raise
        return self.decorate(row,True)

    def gunluk(self,name,tail):
        name_of(name)
        if self.inspect(name): return super().gunluk(name,tail)
        if name in self.apps: unit=self.apps[name]['unit']
        elif name in self.definitions: unit='konsol-'+name+'.service'
        else: return super().gunluk(name,tail)
        tail=int(tail) if str(tail).isdigit() and int(tail) in TAILS else 200
        rc,text,_=self.run(['journalctl','-u',unit,'-n',str(tail),'--no-pager','-o','short-iso'],30)
        if rc: raise ContainerError(502,'Konteyner günlüğü okunamadı.')
        lines=[mask(l) for l in text.splitlines() if l.strip()]
        return {'name':name,'lines':lines[-tail:],'truncated':len(lines)>=tail,'masked':True}


class Service:
    def __init__(self,panel):
        self.panel=panel
        self.lock=threading.Lock()
        self.jobs={}
        self.update_lock=threading.Lock()
        self.update_items={}
        self.update_at=0.0

    def update_of(self,name):
        with self.lock:
            value=self.update_items.get(name)
            return dict(value,checked_at=int(self.update_at)) if value else None

    def updates(self,force=False):
        """DD-214: per-container update status, cached; registry manifests only, never a pull."""
        with self.update_lock:
            age=time.time()-self.update_at
            if self.update_at and age<UPDATE_MIN_INTERVAL or (self.update_at and age<UPDATE_TTL and not force):
                with self.lock: items=copy.deepcopy(self.update_items)
                return {'checked_at':int(self.update_at),'items':items,'cached':True}
            view=self.view()
            run=lambda argv,timeout: self.panel.run_tool(argv,timeout=timeout)
            rc,arch,_=run(['podman','info','--format','{{.Host.Arch}}'],20)
            arch=arch.strip()
            items={}
            for name,app in view.apps.items():
                if app.get('channel'):
                    items[name]=update_status(run,app['image'],app['channel'],arch) if rc==0 and arch else \
                        {'state':'denetlenemedi','channel':app['channel'],'candidate':'','error':'Podman yanıt vermedi.'}
            for name,d in view.definitions.items():
                ref=d.get('image_ref') or ''
                items[name]=update_status(run,d['image'],ref if '@' not in ref else '',arch) if rc==0 and arch else \
                    {'state':'denetlenemedi','channel':ref,'candidate':'','error':'Podman yanıt vermedi.'}
            for value in items.values(): value.pop('candidate',None)
            now=time.time()
            with self.lock:
                self.update_items,self.update_at=items,now
            return {'checked_at':int(now),'items':copy.deepcopy(items),'cached':False}

    def forget_updates(self):
        """An image change makes the cached answer stale; the next view asks the registry again."""
        with self.lock:
            self.update_items,self.update_at={},0.0

    def view(self):
        try: return Inventory(self)
        except (OSError,ValueError,KeyError,settings.SettingsError) as err:
            raise ContainerError(503,'Konteyner yönetim kayıtları okunamadı.') from err

    def busy(self,name):
        with self.lock:
            return next((j['id'] for j in self.jobs.values() if j.get('name')==name and j['state']=='running'),None)

    def operation(self,ident):
        if not isinstance(ident,str) or not JOB_RE.fullmatch(ident): raise ContainerError(400,'İşlem kimliği geçersiz.')
        env=settings.env_read(self.panel.args.state)
        value=None
        if env.get('KONTEYNER_STATE_DIR'):
            try: value=config.read_private(Path(env['KONTEYNER_STATE_DIR'])/'operations'/(ident+'.json'))
            except config.ContainerConfigError as err: raise ContainerError(err.status,str(err)) from err
        if value:
            if value.get('state')=='running':
                # The transient service is the executor. SIGKILL/timeout cannot write a final
                # JSON record; do not keep a browser spinning forever on that stale record.
                rc,_,_=self.panel.run_tool(['systemctl','is-active','--quiet','master-container-'+ident+'.service'],timeout=10)
                if rc in (3,4):
                    value=dict(value,state='failed',status=502,updated_at=int(time.time()),
                               error='İşlem son yanıtı yazmadan durdu; yeniden denemeden önce gerçek konteyner durumunu kontrol edin.')
            with self.lock: self.jobs[ident]=value
            return value
        with self.lock: value=copy.deepcopy(self.jobs.get(ident))
        if value: return value
        raise ContainerError(404,'İşlem bulunamadı; konteyner durumunu yenileyin.')

    def submit(self,data):
        if not isinstance(data,dict) or not isinstance(data.get('action'),str) or data['action'] not in ACTIONS:
            raise ContainerError(400,'Konteyner işlemi geçersiz.')
        action=data['action']; request={k:v for k,v in data.items() if k!='action'}
        if 'config' in request and not isinstance(request['config'],dict):
            raise ContainerError(400,'Konteyner ayarı bir nesne olmalı.')
        name=request.get('name') or (request.get('config') or {}).get('name') or request.get('image') or ''
        if not isinstance(name,str) or not name or len(name)>512: raise ContainerError(400,'İşlem hedefi gerekli.')
        if action in ('image-pull','image-remove'):
            try:
                if action=='image-remove' and re.fullmatch(r'[0-9a-f]{64}',name):
                    request['image']='sha256:'+name
                elif not (action=='image-remove' and re.fullmatch(r'sha256:[0-9a-f]{64}',name)):
                    config.image_of(name)
            except config.ContainerConfigError as err: raise ContainerError(err.status,str(err)) from err
        else: name_of(name)
        if action in ('save','start','stop','restart','remove','image-update','adopt'):
            row=self.view().ayrinti(name)
            if action not in row['actions']: raise ContainerError(409,row.get('restricted_reason') or 'Bu işlem konteyner için desteklenmiyor.')
            if row.get('revision') and request.get('revision')!=row['revision']:
                raise ContainerError(409,'Ayarlar değişmiş; sayfayı yenileyip değişiklikleri yeniden inceleyin.')
            if row.get('module_id') and self.panel.module_busy(row['module_id']):
                raise ContainerError(409,'Uygulamada bir işlem sürüyor.')
        ident=uuid.uuid4().hex
        with self.lock:
            if any(j['state']=='running' and j.get('name')==name for j in self.jobs.values()):
                raise ContainerError(409,'Bu hedefte bir işlem sürüyor.')
            active=sum(j['state']=='running' for j in self.jobs.values())
            if active>=4: raise ContainerError(409,'İşlem sınırına ulaşıldı; süren işlemlerin bitmesini bekleyin.')
            job={'id':ident,'action':action,'name':name,'state':'running','step':'Başlatılıyor', 'updated_at':int(time.time())}
            self.jobs[ident]=job
            # Retain a bounded in-memory dispatch cache. Durable results live in private files.
            for key in list(self.jobs):
                if len(self.jobs)<=256: break
                if self.jobs[key]['state']!='running': del self.jobs[key]
        self._launch(ident,action,request)
        return dict(job)

    def _launch(self,ident,action,data):
        threading.Thread(target=self._execute,args=(ident,action,data),daemon=True).start()

    def _execute(self,ident,action,data):
        argv=['systemd-run','--unit=master-container-'+ident,'--quiet','--wait','--pipe','--collect',
              '--property=UMask=0077','--property=RuntimeMaxSec=900','--setenv=PYTHONDONTWRITEBYTECODE=1',
              '/usr/bin/python3',str(Path(__file__).resolve()),'--state',self.panel.args.state,'--operation',ident,action]
        try:
            p=subprocess.run(argv,input=json.dumps(data),capture_output=True,text=True,timeout=910,env=self.panel.env())
            result=json.loads(p.stdout)
            if not isinstance(result,dict): raise ValueError('worker response')
            # The worker writes the terminal durable record; preserve its truth even if stderr is noisy.
            value=self.operation(ident)
            if value['state']=='running':
                value.update(state='failed' if p.returncode else 'done',result=result if not p.returncode else None,
                             error=result.get('error','İşlem başarısız.') if p.returncode else None,updated_at=int(time.time()))
        except (OSError,subprocess.TimeoutExpired,ValueError,ContainerError):
            with self.lock: value=dict(self.jobs[ident])
            value.update(state='failed',error='İşlem sonucu alınamadı; yeniden denemeden önce konteyner durumunu yenileyin.',updated_at=int(time.time()))
        with self.lock: self.jobs[ident]=value
        if action in ('image-update','save','create','remove','adopt') and value.get('state')=='done': self.forget_updates()
        self.panel.settings_cache=(0,None)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--state',required=True);parser.add_argument('--operation',required=True)
    parser.add_argument('action',choices=sorted(ACTIONS));args=parser.parse_args()
    try:
        if not JOB_RE.fullmatch(args.operation): raise ContainerError(400,'İşlem kimliği geçersiz.')
        raw=sys.stdin.read(65537)
        if len(raw)>65536: raise ContainerError(400,'İstek çok büyük.')
        request=json.loads(raw)
        if not isinstance(request,dict): raise ContainerError(400,'İstek nesne olmalı.')
        env=settings.env_read(args.state)
        app=app_specs(env).get(request.get('name')) if args.action in (*APP_ACTIONS,'save','image-update') else None
        if app:
            result=application_job(args,env,app,request)
        else:
            from master_container_worker import Manager
            result=Manager(args.state).execute(args.action,request,args.operation)
        print(json.dumps(result,ensure_ascii=False))
    except Exception as err:
        expected=isinstance(err,(ContainerError,config.ContainerConfigError,settings.SettingsError)) or hasattr(err,'status')
        print(json.dumps({'error':str(err) if expected else 'Konteyner işlemi tamamlanamadı.',
                          'status':getattr(err,'status',500)},ensure_ascii=False))
        sys.exit(1)


def application_job(args,env,app,data):
    directory=Path(env['KONTEYNER_STATE_DIR'])/'operations'
    config.private_dir(directory)
    path=directory/(args.operation+'.json')
    # Exclusive reservation prevents a repeated operation ID repeating a destructive action.
    with settings.parent_fd(path) as (fd,name):
        out=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
        os.close(out)
    job={'id':args.operation,'action':args.action,'name':app['name'],'state':'running','step':'Uygulama işlemi', 'updated_at':int(time.time())}
    def write(): settings.atomic(path,json.dumps(job,ensure_ascii=False)+'\n',0o600)
    write()
    try:
        current=app_config(env,app)
        if data.get('revision')!=current['revision']:
            raise ContainerError(409,'Uygulama ayarları değişmiş; yeniden inceleyin.')
        if args.action in ('save','image-update'):
            script=Path(env['MODULES_DIR'])/app['module_id']/app['adapter']
            verb,body,limit=(('konteyner-ayar',{'revision':data['revision'],'config':data.get('config',{})},600) if args.action=='save' else
                             ('konteyner-guncelle',{'revision':data['revision']},870))
            command=['/usr/bin/python3',str(script),'--lib',str(Path(__file__).resolve().parent),'--state',args.state,verb]
            job.update(step='İmaj denetleniyor ve indiriliyor' if args.action=='image-update' else 'Uygulama ayarı'); write()
            proc=subprocess.run(command,input=json.dumps(body),text=True,capture_output=True,timeout=limit)
            result=json.loads(proc.stdout)
            if proc.returncode: raise ContainerError(result.get('status',400),result.get('error','Uygulama ayarı uygulanamadı.'))
        else:
            command=[str(Path(__file__).resolve().parent/'master-modul'),APP_ACTIONS[args.action],app['module_id']]
            if args.action=='remove' and data.get('with_data') is True: command.append('--veri')
            proc=subprocess.run(command,capture_output=True,text=True,timeout=600,
                                env=dict(os.environ,STATE_FILE=args.state,KONSOL_KONTEYNER_REVISION=data['revision']))
            if proc.returncode==75: raise ContainerError(409,'Uygulama ayarları değişmiş; yeniden inceleyin.')
            if proc.returncode: raise ContainerError(502,'Uygulama işlemi başarısız; uygulama günlüğünü kontrol edin.')
            result={'ok':True,'module_id':app['module_id']}
        job.update(state='done',step='Tamamlandı',result=result,updated_at=int(time.time()));write()
        return result
    except Exception as err:
        job.update(state='failed',step='İşlem durdu',error=str(err) if isinstance(err,ContainerError) else 'Uygulama işlemi tamamlanamadı.',
                   status=getattr(err,'status',500),updated_at=int(time.time()));write()
        raise


if __name__=='__main__': main()
