#!/usr/bin/env python3
"""Explicit rootful container operations, run outside the panel sandbox.

CLI: --state PATH --operation UUID ACTION; JSON stdin, JSON stdout. Only this worker owns
ordinary definitions. App Store mutations belong to the module engine/package adapters.
"""
import argparse
import contextlib
import copy
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time
import uuid

import master_settings as settings
import master_container_config as cfg

ACTIONS = ('create', 'save', 'start', 'stop', 'restart', 'remove', 'adopt', 'image-pull', 'image-remove',
           'image-update', 'volume-create', 'volume-remove', 'network-create', 'network-remove')
LIMIT = 1024 * 1024


def run(argv, timeout=60, **kwargs):
    return subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout, **kwargs)


class Manager:
    def __init__(self, state, run=run, network=None, generator=None):
        self.state = str(state)
        self.env = settings.env_read(state)
        self.env['STATE_FILE'] = self.state
        self.store = cfg.Store(self.env)
        self.run = run
        self.network = network
        self.generator = generator
        self.operation = None
        self.op_path = None

    def call(self, argv, timeout=60, check=True, **kwargs):
        try:
            p = self.run(list(argv), timeout=timeout, **kwargs)
        except (OSError, subprocess.TimeoutExpired) as err:
            raise cfg.ContainerConfigError(502, 'Konteyner işlemi zamanında tamamlanamadı veya araç çalıştırılamadı.') from err
        if isinstance(p, tuple):
            p = subprocess.CompletedProcess(argv, p[0], p[1], p[2])
        if isinstance(p.stdout, bytes):
            p.stdout = p.stdout.decode('utf-8', 'replace')
        if isinstance(p.stderr, bytes):
            p.stderr = p.stderr.decode('utf-8', 'replace')
        # Never echo argv/stdout/stderr: a container's error may contain credentials.
        cfg.require(not check or p.returncode == 0, 'Konteyner aracı işlemi reddetti; önceki durum kontrol edildi.', 502)
        return p

    def json_call(self, argv, **kwargs):
        p = self.call(argv, **kwargs)
        try:
            return json.loads(p.stdout or 'null')
        except (ValueError, TypeError) as err:
            raise cfg.ContainerConfigError(502, 'Konteyner aracı geçerli yanıt vermedi.') from err

    @contextlib.contextmanager
    def locked(self):
        paths = [Path(self.env['RUNTIME_DIR']) / 'install.lock', Path(self.env['RUNTIME_DIR']) / 'modul.lock',
                 Path(self.env['KONTEYNER_LOCK'])]
        with contextlib.ExitStack() as stack:
            for path in paths:
                with settings.parent_fd(path, create=True) as (directory, name):
                    fd = os.open(name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=directory)
                f = stack.enter_context(os.fdopen(fd, 'a'))
                info = os.fstat(f.fileno())
                cfg.require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid(), 'İşlem kilidi güvenli değil.', 503)
                try:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as err:
                    raise cfg.ContainerConfigError(409, 'Kurulum veya başka bir konteyner işlemi sürüyor; biraz sonra yeniden deneyin.') from err
            pending = self.env.get('SETTINGS_PENDING_FILE')
            cfg.require(not pending or not Path(pending).exists(), 'Onay bekleyen sistem ayarını önce tamamlayın.', 409)
            yield

    def step(self, label):
        if self.operation is not None:
            self.operation.update(step=label, updated_at=int(time.time()))
            settings.atomic(self.op_path, json.dumps(self.operation, ensure_ascii=False) + '\n', 0o600)

    def begin(self, action, request, operation):
        cfg.require(isinstance(operation, str) and cfg.REV_RE.fullmatch(operation), 'İşlem kimliği geçersiz.')
        cfg.private_dir(self.store.root)
        cfg.private_dir(self.store.root / 'operations')
        self.op_path = self.store.root / 'operations' / (operation + '.json')
        # Reserve the id exclusively before any side effect; a replay never repeats an action.
        with settings.parent_fd(self.op_path) as (directory, name):
            try:
                fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            except FileExistsError as err:
                raise cfg.ContainerConfigError(409, 'Bu işlem kimliği zaten kullanıldı.') from err
            os.close(fd)
        draft = request.get('config')
        raw_name = request.get('name') or (draft.get('name') if isinstance(draft, dict) else '') or ''
        name = raw_name if isinstance(raw_name, str) and cfg.NAME_RE.fullmatch(raw_name) else ''
        self.operation = {'id': operation, 'action': action, 'name': name, 'state': 'running',
                          'step': 'Doğrulanıyor', 'created_at': int(time.time()), 'updated_at': int(time.time())}
        self.step('Doğrulanıyor')

    def execute(self, action, request, operation):
        cfg.require(action in ACTIONS and isinstance(request, dict), 'Konteyner işlemi geçersiz.')
        self.begin(action, request, operation)
        try:
            with self.locked():
                result = self.dispatch(action, request)
            self.operation.update(state='done', result=result, finished_at=int(time.time()))
            self.step('Tamamlandı')
            return result
        except Exception as err:
            if not isinstance(err, cfg.ContainerConfigError):
                err = cfg.ContainerConfigError(502, 'Konteyner işlemi tamamlanamadı; işlem kaydındaki durumu kontrol edin.')
            self.operation.update(state='failed', error=str(err), status=err.status, finished_at=int(time.time()),
                                  failed_step=getattr(err, 'failed_step', self.operation['step']))
            self.step('Başarısız')
            raise err

    def network_module(self):
        if self.network is None:
            try:
                import master_container_network
                self.network = master_container_network
            except ImportError as err:
                raise cfg.ContainerConfigError(503, 'Konteyner ağ ilkesi kurulu değil; kurulumu yeniden çalıştırın.') from err
        return self.network

    def refresh_tailnet(self):
        """Consume an address-change event; never discover or start unmanaged/stopped containers."""
        self.operation = self.op_path = None
        pending = Path(self.env['RUNTIME_DIR']) / 'containers-tailnet.pending'
        event = self.snapshot(pending)
        result = {'ok': True, 'updated': [], 'errors': []}
        with self.locked():
            for definition in self.store.list():
                if not any(p['scope'] == 'tailscale' for p in definition['ports']):
                    continue
                name = definition['name']
                try:
                    rendered = cfg.render_quadlet(definition, self.env, self.net_call('bindings', definition['ports']))
                    if self.snapshot(self.quadlet(name)) == rendered.encode():
                        continue
                    self.apply(copy.deepcopy(definition), definition)
                    result['updated'].append(name)
                except Exception as err:
                    result['ok'] = False
                    result['errors'].append({'name': name,
                                             'error': str(err) if isinstance(err, cfg.ContainerConfigError) else 'Adres yenilenemedi.',
                                             'status': err.status if isinstance(err, cfg.ContainerConfigError) else 502})
            if result['ok'] and event is not None:
                # The producer holds state.lock while replacing this marker. Compare+unlink
                # under the same lock, so a newer address event cannot be lost.
                lock = Path(self.env['RUNTIME_DIR']) / 'state.lock'
                with settings.parent_fd(lock, create=True) as (directory, filename):
                    fd = os.open(filename, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=directory)
                with os.fdopen(fd, 'a') as stream:
                    info = os.fstat(stream.fileno())
                    cfg.require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid(), 'Durum kilidi güvenli değil.', 503)
                    try:
                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        return result  # A subsequent existing timer tick will retry the marker.
                    if self.snapshot(pending) == event:
                        cfg.unlink(pending)
        return result

    def net_call(self, method, *args):
        try:
            return getattr(self.network_module(), method)(self.env, *args, run=self.run)
        except cfg.ContainerConfigError:
            raise
        except Exception as err:
            # The helper's validation errors contain no submitted secrets.
            if hasattr(err, 'status'):
                raise cfg.ContainerConfigError(err.status, str(err)) from err
            raise cfg.ContainerConfigError(502, 'Konteyner ağ ilkesi uygulanamadı.') from err

    def unit(self, name):
        return 'konsol-' + cfg.name_of(name) + '.service'

    def quadlet(self, name):
        return Path(self.env['KONTEYNER_BIRIM_DIR']) / ('konsol-' + cfg.name_of(name) + '.container')

    def running(self, name):
        return self.call(['systemctl', 'is-active', '--quiet', self.unit(name)], check=False).returncode == 0

    def inspect(self, name):
        p = self.call(['podman', 'container', 'exists', name], check=False)
        if p.returncode == 1:
            return None
        cfg.require(p.returncode == 0, 'Konteyner envanteri okunamadı.', 502)
        value = self.json_call(['podman', 'inspect', '--type', 'container', name])
        cfg.require(isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict), 'Konteyner bilgisi okunamadı.', 502)
        return value[0]

    def managed(self, request):
        name = cfg.name_of(request.get('name'))
        cfg.require(not cfg.reserved(name, self.env), 'Bu konteyneri kendi uygulama yönetiminden değiştirin.', 409)
        old = self.store.load(name)
        if old:
            cfg.require(request.get('revision') == old['revision'], 'Ayarlar değişmiş; yenileyip yeniden gözden geçirin.', 409)
        return name, old

    def ensure_managed_owner(self, name):
        found = self.inspect(name)
        cfg.require(found is None or cfg.ownership(found, self.env) == 'konsol',
                    'Bu ad başka bir yöneticinin konteynerine ait; işlem yapılmadı.', 409)
        return found

    def image(self, reference, pull=False):
        reference = cfg.image_of(reference)
        self.step('İmaj doğrulanıyor')
        if pull:
            self.call(['podman', 'pull', '--quiet', reference], timeout=600)
        p = self.call(['podman', 'image', 'inspect', reference], check=False)
        if p.returncode != 0 and not pull:
            self.step('İmaj indiriliyor')
            self.call(['podman', 'pull', '--quiet', reference], timeout=600)
            p = self.call(['podman', 'image', 'inspect', reference])
        cfg.require(p.returncode == 0, 'İmaj okunamadı.', 502)
        try:
            info = json.loads(p.stdout)[0]
            repo = reference.split('@')[0]
            if ':' in repo.rsplit('/', 1)[-1]:
                repo = repo.rsplit(':', 1)[0]
            digests = [d for d in info.get('RepoDigests', []) if isinstance(d, str) and d.startswith(repo + '@sha256:')]
            digest = next((d for d in digests if d == reference), digests[0] if digests else '')
            cfg.require('@sha256:' in digest and cfg.IMAGE_RE.fullmatch(digest), 'İmaj sabit bir özete çözümlenemedi.', 502)
            return digest
        except (ValueError, IndexError, TypeError) as err:
            raise cfg.ContainerConfigError(502, 'İmaj özeti okunamadı.') from err

    def ensure_network(self, network, create_default=True):
        if network == 'none':
            return
        name = self.env.get('KONTEYNER_NETWORK', 'konsol') if network == 'bridge' else cfg.name_of(network)
        p = self.call(['podman', 'network', 'exists', name], check=False)
        if p.returncode == 1 and create_default and name == self.env.get('KONTEYNER_NETWORK', 'konsol'):
            self.create_network({'name': name})
        else:
            cfg.require(p.returncode == 0, 'Konteyner ağı yok; önce Ağlar bölümünden oluşturun.', 409)
        info = self.json_call(['podman', 'network', 'inspect', name])
        cfg.require(isinstance(info, list) and len(info) == 1, 'Ağ bilgisi okunamadı.', 502)
        info = info[0]
        prefix = self.env.get('KONTEYNER_BRIDGE_PREFIX', 'ksl')
        interface = prefix + hashlib.sha256(name.encode()).hexdigest()[:10]
        cfg.require(info.get('driver') == 'bridge' and info.get('network_interface') == interface and
                    (info.get('labels') or {}).get(cfg.MANAGED_LABEL) == 'konsol',
                    'Bu ağın güvenlik ilkesi Konsol tarafından yönetilmiyor.', 409)

    def prepare(self, definition):
        if definition['network'] != 'none':
            self.ensure_network(definition['network'])
        definition['ports'] = self.net_call('validate_ports', definition['ports'], definition['name'])
        for mount in definition['mounts']:
            if mount['type'] == 'volume':
                cfg.require(self.call(['podman', 'volume', 'exists', mount['source']], check=False).returncode == 0,
                            'Seçilen birim yok; önce Birimler bölümünden oluşturun.', 409)
                volumes = self.json_call(['podman', 'volume', 'inspect', mount['source']])
                cfg.require(isinstance(volumes, list) and len(volumes) == 1 and isinstance(volumes[0], dict),
                            'Birim bilgisi okunamadı.', 502)
                cfg.require(volumes[0].get('Driver') == 'local' and not volumes[0].get('Options'),
                            'Özel sürücü veya bağlama seçenekli birim desteklenmiyor; standart yerel birim seçin.', 409)
        bindings = self.net_call('bindings', definition['ports'])
        rendered = cfg.render_quadlet(definition, self.env, bindings)
        self.step('Servis tanımı doğrulanıyor')
        generator = self.generator or next((p for p in ('/usr/lib/systemd/system-generators/podman-system-generator',
                                                         '/usr/libexec/podman/quadlet') if os.path.isfile(p)), None)
        cfg.require(generator, 'Podman Quadlet üreticisi bulunamadı.', 503)
        # The generator validates a temporary candidate before the existing service is stopped.
        with tempfile.TemporaryDirectory(prefix='container-validate-', dir=self.env['RUNTIME_DIR']) as temporary:
            target = Path(temporary) / self.quadlet(definition['name']).name
            settings.atomic(target, rendered, 0o600)
            environment = dict(os.environ, QUADLET_UNIT_DIRS=temporary)
            p = self.call([generator, '--dryrun'], env=environment)
            cfg.require(self.unit(definition['name']) in p.stdout and '[Service]' in p.stdout,
                        'Quadlet üreticisi servis tanımını oluşturamadı.', 409)
        return rendered

    def ready(self, name, definition=None, seconds=30):
        deadline = time.monotonic() + seconds
        while True:
            info = self.inspect(name)
            state = (info or {}).get('State') or {}
            health = state.get('Health') or {}
            if self.running(name) and state.get('Running') is True and health.get('Status') not in ('starting', 'unhealthy'):
                cfg.require(cfg.ownership(info, self.env) == 'konsol', 'Başlayan konteynerin sahibi doğrulanamadı.', 502)
                if (definition or {}).get('user') == 'downloads':
                    # DD-227: prove the account and the empty capability sets. Podman prints an empty set as
                    # null (5.4.2) or []; a missing field fails closed.
                    expected = self.env.get('DOWNLOADS_UID', '') + ':' + self.env.get('DOWNLOADS_GID', '')
                    dropped = all(key in info and info[key] in (None, []) for key in ('EffectiveCaps', 'BoundingCaps'))
                    cfg.require((info.get('Config') or {}).get('User') == expected and dropped,
                                'Konteyner Dosyalar hesabıyla yetkisiz başlamadı.', 502)
                return
            if time.monotonic() >= deadline:
                raise cfg.ContainerConfigError(502, 'Konteyner başlamadı veya sağlık denetimi başarısız oldu.')
            time.sleep(1)

    @staticmethod
    def snapshot(path):
        try:
            return settings.read_regular(path, LIMIT)[0]
        except FileNotFoundError:
            return None

    @staticmethod
    def restore(path, value, mode=0o600):
        if value is None:
            if Path(path).exists():
                cfg.unlink(path)
        else:
            settings.atomic(path, value, mode)

    def apply(self, definition, old=None, start=False):
        # Stored paths can have been renamed or replaced while the container was stopped.
        checked = cfg.validate(definition, self.env, definition)
        checked['revision'] = definition['revision']
        definition = checked
        name = definition['name']
        self.ensure_managed_owner(name)
        rendered = self.prepare(definition)
        was_running = self.running(name) if old else False
        start = bool(start or was_running)
        if start:
            definition['manual_stop'] = False
            rendered = cfg.render_quadlet(definition, self.env, self.net_call('bindings', definition['ports']))
        paths = (self.store.path(name), self.store.environment_path(name), self.quadlet(name))
        saved = {p: self.snapshot(p) for p in paths}
        stopped = False
        try:
            if was_running:
                self.step('Konteyner durduruluyor')
                self.call(['systemctl', 'stop', self.unit(name)], timeout=90)
                stopped = True
            self.step('Ayarlar uygulanıyor')
            self.store.save(definition)
            self.store.write_environment(definition)
            settings.atomic(self.quadlet(name), rendered, 0o600)
            # Policy must exist before any container can open its bridge listener.
            self.net_call('apply')
            self.call(['systemctl', 'daemon-reload'])
            if start:
                self.step('Konteyner başlatılıyor')
                self.call(['systemctl', 'start', self.unit(name)], timeout=180)
                self.ready(name, definition)
            return {'ok': True, 'name': name, 'management_id': 'konsol:' + name, 'revision': definition['revision'],
                    'running': start, 'effective_autostart': definition['autostart'] and not definition['manual_stop']}
        except Exception as original:
            failed_step = self.operation['step'] if self.operation else 'Uygulanıyor'
            self.step('Önceki yapılandırma geri uygulanıyor')
            # Stop the new service before returning its old definition; it may have started only partly.
            recovered = True
            try:
                if stopped or start:
                    self.call(['systemctl', 'stop', self.unit(name)], timeout=90)
                for path, content in saved.items():
                    self.restore(path, content)
                self.net_call('apply')
                self.call(['systemctl', 'daemon-reload'])
                if was_running:
                    self.call(['systemctl', 'start', self.unit(name)], timeout=180)
                    self.ready(name, old)
            except Exception:
                recovered = False
            error = cfg.ContainerConfigError(502, 'Uygulama başarısız; önceki yapılandırma geri yüklendi.' if recovered else
                                             'Uygulama ve geri dönüş başarısız; servis durumunu kontrol edin. Veriler geri alınmadı.')
            error.failed_step = failed_step
            raise error from original

    def managed_action(self, action, request, name, old):
        self.ensure_managed_owner(name)
        if action == 'save':
            definition = cfg.validate(request.get('config'), self.env, old)
            if definition['image'] != old['image']:
                definition['image'] = self.image(definition['image'])
            return self.apply(definition, old, request.get('start') is True)
        if action == 'image-update':
            definition = copy.deepcopy(old)
            definition['image'] = self.image(old['image_ref'], pull=True)
            if definition['image'] == old['image']:
                return {'ok': True, 'name': name, 'revision': old['revision'], 'changed': False}
            definition['revision'] = uuid.uuid4().hex
            return self.apply(definition, old)
        if action == 'start':
            definition = copy.deepcopy(old)
            definition.update(manual_stop=False, revision=uuid.uuid4().hex)
            return self.apply(definition, old, start=True)
        if action == 'restart':
            cfg.require(self.running(name), 'Durdurulmuş konteyner için Başlat seçeneğini kullanın.', 409)
            definition = copy.deepcopy(old)
            definition['revision'] = uuid.uuid4().hex
            return self.apply(definition, old, start=True)
        if action == 'stop':
            definition = copy.deepcopy(old)
            definition.update(manual_stop=True, revision=uuid.uuid4().hex)
            # A stop never needs a live Tailscale address or a writable bind source. Keep the
            # last valid rendering and remove its automatic-boot section without resolving ports.
            before = self.snapshot(self.quadlet(name))
            rendered, in_install = [], False
            for line in (before or b'').decode().splitlines():
                if line.startswith('[') and line.endswith(']'):
                    in_install = line == '[Install]'
                if not in_install:
                    rendered.append(line)
            was_running = self.running(name)
            self.call(['systemctl', 'stop', self.unit(name)], timeout=90)
            try:
                self.store.save(definition)
                if before is not None:
                    settings.atomic(self.quadlet(name), '\n'.join(rendered) + '\n', 0o600)
                self.call(['systemctl', 'daemon-reload'])
            except Exception as err:
                self.store.save(old)
                self.restore(self.quadlet(name), before)
                self.call(['systemctl', 'daemon-reload'])
                if was_running:
                    self.call(['systemctl', 'start', self.unit(name)], timeout=180)
                raise cfg.ContainerConfigError(502, 'Durdurma kaydedilemedi; önceki başlangıç ayarı geri yüklendi.') from err
            cfg.require(not self.running(name), 'Konteyner durmadı.', 502)
            return {'ok': True, 'name': name, 'revision': definition['revision'], 'running': False, 'effective_autostart': False}
        if action == 'remove':
            self.call(['systemctl', 'stop', self.unit(name)], timeout=90)
            # Never --volumes: named volumes and bind sources remain separate resources.
            if self.inspect(name) is not None:
                self.call(['podman', 'rm', name])
            cfg.unlink(self.quadlet(name))
            self.store.delete(name)
            self.restore(self.store.environment_path(name), None)
            self.call(['systemctl', 'daemon-reload'])
            self.net_call('apply')
            return {'ok': True, 'name': name, 'removed': True}
        raise cfg.ContainerConfigError(400, 'Konteyner işlemi geçersiz.')

    def dispatch(self, action, request):
        if action == 'create':
            value = request.get('config')
            definition = cfg.validate(value, self.env)
            cfg.require(not request.get('name') or request['name'] == definition['name'], 'Konteyner adı uyuşmuyor.')
            name = definition['name']
            cfg.require(self.store.load(name) is None and self.inspect(name) is None and not self.quadlet(name).exists(),
                        'Bu ad zaten kullanılıyor.', 409)
            definition['image'] = self.image(definition['image'])
            return self.apply(definition, start=request.get('start') is True)
        if action.startswith(('image-', 'volume-', 'network-')) and action != 'image-update':
            return self.resource(action, request)
        name, old = self.managed(request)
        if old:
            cfg.require(action != 'adopt', 'Bu konteyner zaten Konsol tarafından yönetiliyor.', 409)
            return self.managed_action(action, request, name, old)
        cfg.require(action in ('start', 'stop', 'restart', 'remove', 'adopt'), 'Konteyneri değiştirmek için önce Konsol yönetimine alın.', 409)
        info = self.inspect(name)
        cfg.require(info is not None, 'Konteyner bulunamadı.', 404)
        cfg.require(cfg.ownership(info, self.env) == 'standalone', 'Konteyner başka bir uygulama, servis veya yığın tarafından yönetiliyor.', 409)
        if action == 'adopt':
            return self.adopt(request, info)
        self.step('Konteyner işlemi uygulanıyor')
        if action == 'restart':
            cfg.require((info.get('State') or {}).get('Running') is True, 'Durdurulmuş konteyner için Başlat seçeneğini kullanın.', 409)
        if action == 'remove':
            if (info.get('State') or {}).get('Running'):
                self.call(['podman', 'stop', '--time', '60', name], timeout=90)
            self.call(['podman', 'rm', name])
        else:
            self.call(['podman', action, name], timeout=90)
            after = self.inspect(name)
            cfg.require(after is not None and bool((after.get('State') or {}).get('Running')) == (action != 'stop'),
                        'Konteyner istenen duruma geçmedi.', 502)
        return {'ok': True, 'name': name, 'removed': action == 'remove', 'running': action in ('start', 'restart')}

    def resource_users(self, kind, target):
        for definition in self.store.list():
            if kind == 'volume' and any(m['type'] == 'volume' and m['source'] == target for m in definition['mounts']):
                return True
            if kind == 'network' and (self.env.get('KONTEYNER_NETWORK', 'konsol') if definition['network'] == 'bridge' else definition['network']) == target:
                return True
            if kind == 'image' and target in (definition['image'], definition['image_ref']):
                return True
        rows = self.json_call(['podman', 'ps', '-a', '--filter', ('ancestor' if kind == 'image' else kind) + '=' + target, '--format', 'json'])
        cfg.require(isinstance(rows, list), 'Kaynak kullanımı okunamadı.', 502)
        return bool(rows)

    def create_network(self, request):
        name = cfg.name_of(request.get('name'))
        cfg.require(name not in ('bridge', 'host', 'none', 'podman'), 'Bu ağ adı ayrılmıştır.')
        cfg.require(type(request.get('internal', False)) is bool, 'Ağ seçeneği geçersiz.')
        prefix = self.env.get('KONTEYNER_BRIDGE_PREFIX', 'ksl')
        cfg.require(prefix.isalnum() and 1 <= len(prefix) <= 5, 'Konteyner köprü öneki geçersiz.', 503)
        interface = prefix + hashlib.sha256(name.encode()).hexdigest()[:10]
        argv = ['podman', 'network', 'create', '--driver', 'bridge', '--interface-name', interface,
                '--label', cfg.MANAGED_LABEL + '=konsol']
        if request.get('internal'):
            argv.append('--internal')
        if request.get('subnet'):
            try:
                subnet = ipaddress.ip_network(request['subnet'], strict=True)
            except (ValueError, TypeError) as err:
                raise cfg.ContainerConfigError(400, 'Ağ alt adresi geçersiz.') from err
            private_ranges = [ipaddress.ip_network(s) for s in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')]
            cfg.require(subnet.version == 4 and subnet.prefixlen >= 16 and any(subnet.subnet_of(s) for s in private_ranges),
                        'Özel bir IPv4 alt ağı seçin (/16 veya daha dar).')
            self.validate_subnet(subnet)
            argv += ['--subnet', str(subnet)]
        self.call(argv + [name])
        return {'ok': True, 'name': name}

    def validate_subnet(self, subnet):
        """A custom bridge route must not steal traffic from a host, VPN or stopped network."""
        routes = self.json_call(['ip', '-j', '-4', 'route', 'show', 'table', 'all'])
        networks = self.json_call(['podman', 'network', 'ls', '--format', 'json'])
        cfg.require(isinstance(routes, list) and isinstance(networks, list), 'Mevcut ağ adresleri okunamadı.', 502)
        candidates = [r.get('dst') for r in routes if isinstance(r, dict) and r.get('dst') not in (None, 'default')]
        names = [n.get('name') or n.get('Name') for n in networks if isinstance(n, dict)]
        cfg.require(len(names) == len(networks) and all(isinstance(n, str) and cfg.NAME_RE.fullmatch(n) for n in names),
                    'Mevcut ağ adları okunamadı.', 502)
        if names:
            details = self.json_call(['podman', 'network', 'inspect', *names])
            cfg.require(isinstance(details, list) and len(details) == len(names), 'Mevcut ağlar okunamadı.', 502)
            for network in details:
                candidates.extend(s.get('subnet') for s in network.get('subnets', []))
        for value in candidates:
            try:
                current = ipaddress.ip_network(value, strict=False)
            except (ValueError, TypeError) as err:
                raise cfg.ContainerConfigError(502, 'Mevcut ağ adresi çözümlenemedi.') from err
            cfg.require(current.version != subnet.version or not subnet.overlaps(current),
                        'Alt ağ sunucu, VPN veya başka bir konteyner ağıyla çakışıyor.', 409)

    def resource(self, action, request):
        self.step('Kaynak işlemi uygulanıyor')
        if action == 'image-pull':
            return {'ok': True, 'image': self.image(request.get('image'), pull=True)}
        if action == 'image-remove':
            target = request.get('image')
            cfg.require(isinstance(target, str) and (cfg.IMAGE_RE.fullmatch(target) or re.fullmatch(r'sha256:[0-9a-f]{64}', target)), 'İmaj kimliği geçersiz.')
            data = self.json_call(['podman', 'image', 'inspect', target])
            cfg.require(isinstance(data, list) and len(data) == 1, 'İmaj bulunamadı.', 404)
            info = data[0]
            aliases = {target, info.get('Id', ''), *(info.get('RepoDigests') or [])}
            for manifest in settings.read_manifests(self.env).values():
                pinned = manifest.get('PAKET_IMAJ')
                if pinned:
                    p = self.call(['podman', 'image', 'inspect', pinned], check=False)
                    try:
                        image_id = json.loads(p.stdout)[0]['Id'] if p.returncode == 0 else ''
                    except (ValueError, KeyError, IndexError, TypeError):
                        raise cfg.ContainerConfigError(502, 'Uygulamanın imajı doğrulanamadı.')
                    cfg.require(pinned not in aliases and not (image_id and image_id in aliases), 'Bu imaj bir App Store uygulamasına ait.', 409)
            for d in self.store.list():
                cfg.require(not aliases.intersection((d['image'], d['image_ref'])), 'İmaj kayıtlı bir konteynerde kullanılıyor.', 409)
            cfg.require(not self.resource_users('image', target), 'İmaj bir konteynerde kullanılıyor.', 409)
            self.call(['podman', 'image', 'rm', target])
            return {'ok': True, 'image': target, 'removed': True}
        name = cfg.name_of(request.get('name'))
        if action == 'volume-create':
            self.call(['podman', 'volume', 'create', '--label', cfg.MANAGED_LABEL + '=konsol', name])
        elif action in ('volume-remove', 'network-remove'):
            kind = action.split('-')[0]
            cfg.require(not self.resource_users(kind, name), 'Kaynak bir konteynerde veya kayıtlı tanımda kullanılıyor.', 409)
            if kind == 'network':
                self.ensure_network(name, create_default=False)
            self.call(['podman', kind, 'rm', name])
        elif action == 'network-create':
            return self.create_network(request)
        else:
            raise cfg.ContainerConfigError(400, 'Kaynak işlemi geçersiz.')
        return {'ok': True, 'name': name, 'removed': action.endswith('-remove')}

    def import_config(self, info):
        config, host = info.get('Config') or {}, info.get('HostConfig') or {}
        name = str(info.get('Name', '')).lstrip('/')
        image = info.get('ImageName') or config.get('Image', '')
        unsupported = []
        if not cfg.IMAGE_RE.fullmatch(str(image)):
            unsupported.append('İmajın tam kayıt adresi yok')
        for key in ('Privileged', 'Devices', 'DeviceRequests', 'CapAdd', 'CapDrop', 'SecurityOpt', 'ExtraHosts',
                    'Dns', 'DnsOptions', 'DnsSearch', 'Sysctls', 'Tmpfs', 'ReadonlyRootfs', 'VolumesFrom',
                    'GroupAdd', 'DeviceCgroupRules', 'MemoryReservation', 'OomKillDisable',
                    'CpuRealtimePeriod', 'CpuRealtimeRuntime', 'BlkioWeight', 'BlkioDeviceReadBps', 'BlkioDeviceWriteBps'):
            if host.get(key):
                unsupported.append(key)
        for key in ('Tty', 'OpenStdin', 'StdinOnce'):
            if config.get(key):
                unsupported.append(key)
        for key in ('PidMode', 'IpcMode', 'UTSMode', 'UsernsMode'):
            if host.get(key) not in (None, '', 'private', 'shareable', 'host' if key == 'UsernsMode' else 'private'):
                unsupported.append(key)
        image_data = self.json_call(['podman', 'image', 'inspect', info.get('Image') or image])
        baseline = image_data[0].get('Config') or {} if isinstance(image_data, list) and image_data else {}
        # DD-227: the Files account (uid or uid:gid) maps to Konsol's account choice; any other user is unsupported.
        files = {self.env.get('DOWNLOADS_UID', ''), self.env.get('DOWNLOADS_UID', '') + ':' + self.env.get('DOWNLOADS_GID', '')}
        user = 'downloads' if (config.get('User') or baseline.get('User') or '') in files - {'', ':'} else 'image'
        for key in ('Entrypoint', 'User', 'WorkingDir', 'Healthcheck'):
            if key == 'User' and user == 'downloads':
                continue
            if config.get(key) != baseline.get(key) and config.get(key) not in (None, '', [], {}):
                unsupported.append(key)
        labels = config.get('Labels') or {}
        if any(not k.startswith('org.opencontainers.image.') for k in labels):
            unsupported.append('Özel etiketler')
        if host.get('NetworkMode') not in ('bridge', 'default', 'podman'):
            unsupported.append('Özel ağ modu')
        if len((info.get('NetworkSettings') or {}).get('Networks') or {}) > 1:
            unsupported.append('Birden çok ağ')
        ports = []
        for key, bindings in (host.get('PortBindings') or {}).items():
            container_port, _, protocol = key.partition('/')
            for binding in bindings or []:
                ip = binding.get('HostIp', '')
                scope = 'local' if ip == '127.0.0.1' else 'tailscale' if ip == self.env.get('TAILSCALE_IPV4') else 'public'
                if ip not in ('', '0.0.0.0', '127.0.0.1', self.env.get('TAILSCALE_IPV4')):
                    unsupported.append('IPv6 veya özel adres bağlaması')
                try:
                    ports.append({'scope': scope, 'host_port': int(binding['HostPort']), 'container_port': int(container_port),
                                  'protocol': protocol, 'public_ack': False})
                except (ValueError, KeyError):
                    unsupported.append('Port aralığı')
        mounts = []
        for m in info.get('Mounts') or []:
            if m.get('Type') not in ('bind', 'volume') or m.get('Propagation') not in (None, '', 'rprivate'):
                unsupported.append('Özel birim türü veya yayılımı')
                continue
            if m.get('Options') and any(o not in ('rbind', 'rw', 'ro', 'rprivate') for o in m['Options']):
                unsupported.append('Özel birim seçenekleri')
            mounts.append({'type': m['Type'], 'source': m.get('Name') if m['Type'] == 'volume' else m.get('Source'),
                           'destination': m.get('Destination'), 'read_only': not bool(m.get('RW', True))})
        environ = []
        for entry in config.get('Env') or []:
            key, sep, value = entry.partition('=')
            if sep:
                environ.append({'name': key, 'value': value, 'secret': True})
        restart = (host.get('RestartPolicy') or {}).get('Name') or 'no'
        if restart not in ('no', 'on-failure', 'always') or (host.get('RestartPolicy') or {}).get('MaximumRetryCount'):
            unsupported.append('Özel yeniden başlatma politikası')
        command = config.get('Cmd') or []
        cpu = host.get('NanoCpus') or 0
        if host.get('CpuQuota') or host.get('CpusetCpus') or host.get('CpuShares'):
            unsupported.append('Özel CPU sınırı')
        pids = host.get('PidsLimit')
        pids_limit = ''
        if pids is not None:
            if type(pids) is int and -1 <= pids <= 9223372036854775807:
                # Inspect reports zero if OCI has no PIDs resource. Explicit -1 keeps
                # that unlimited state instead of accidentally applying the host default.
                pids_limit = str(pids) if pids > 0 else '-1'
            else:
                unsupported.append('PidsLimit')
        ulimits = []
        try:
            for limit in host.get('Ulimits') or []:
                limit_name = limit['Name'].removeprefix('RLIMIT_').lower()
                # OCI inspect uses uint64's maximum for RLIM_INFINITY; Podman CLI uses -1.
                soft, hard = limit['Soft'], limit['Hard']
                ulimits.append({'name': limit_name, 'soft': -1 if soft == 18446744073709551615 else soft,
                                'hard': -1 if hard == 18446744073709551615 else hard})
            ulimits = cfg.ulimits_of(ulimits)
        except (KeyError, TypeError, AttributeError, cfg.ContainerConfigError):
            unsupported.append('Ulimits')
            ulimits = []
        stop_signal = config.get('StopSignal') or ''
        try:
            stop_signal = cfg.stop_signal_of(str(stop_signal) if type(stop_signal) is int else stop_signal)
        except cfg.ContainerConfigError:
            unsupported.append('StopSignal')
            stop_signal = ''
        definition = {'name': name, 'image': image, 'network': 'bridge', 'ports': ports, 'mounts': mounts,
                      'environment': environ, 'command': command, 'autostart': False, 'manual_stop': False,
                      'restart': restart if restart in ('no', 'on-failure', 'always') else 'no',
                      'cpus': str(cpu / 1e9) if cpu else '', 'memory': str(host['Memory']) if host.get('Memory') else '',
                      'pids_limit': pids_limit, 'ulimits': ulimits, 'stop_signal': stop_signal, 'user': user}
        # Health logs/timestamps can change every second without changing the imported settings.
        fingerprint_data = {key: info.get(key) for key in ('Id', 'Name', 'Image', 'Config', 'HostConfig', 'Mounts')}
        fingerprint_data['running'] = (info.get('State') or {}).get('Running')
        fingerprint_data['networks'] = (info.get('NetworkSettings') or {}).get('Networks')
        fingerprint = hashlib.sha256(json.dumps(fingerprint_data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        return definition, sorted(set(unsupported)), fingerprint

    def adopt(self, request, info):
        definition, unsupported, fingerprint = self.import_config(info)
        if request.get('preview') is True:
            return {'preview': {'config': cfg.redact(definition), 'unsupported': unsupported, 'fingerprint': fingerprint,
                                'requires_scope_review': True}}
        cfg.require(request.get('confirm') is True and request.get('preview_fingerprint') == fingerprint,
                    'Konteyner değişmiş veya önizleme onaylanmamış; yeniden gözden geçirin.', 409)
        cfg.require(not unsupported, 'Bu konteynerin seçenekleri desteklenmiyor; asıl yöneticisinden değiştirin.', 409)
        submitted = request.get('config')
        cfg.require(isinstance(submitted, dict) and 'ports' in submitted and 'network' in submitted,
                    'Ağ ve port kapsamlarını önizlemede açıkça seçin.')
        candidate = cfg.validate(submitted, self.env, definition)
        candidate['image'] = self.image(candidate['image'])
        self.prepare(candidate)  # All validation before stopping or renaming the original.
        name = candidate['name']
        cfg.require(self.store.load(name) is None and not self.quadlet(name).exists(), 'Bu ad zaten yönetiliyor.', 409)
        running = (info.get('State') or {}).get('Running') is True
        hold = 'konsol-adopt-' + name + '-' + self.operation['id'][:8]
        renamed = False
        try:
            if running:
                self.call(['podman', 'stop', '--time', '60', name], timeout=90)
            self.call(['podman', 'rename', name, hold])
            renamed = True
            result = self.apply(candidate, start=request.get('start') is True)
            self.call(['podman', 'rm', hold])
            return result
        except Exception as err:
            try:
                if renamed:
                    self.call(['systemctl', 'stop', self.unit(name)], timeout=90, check=False)
                    if self.inspect(name) is not None:
                        self.call(['podman', 'rm', name])
                    self.restore(self.quadlet(name), None)
                    if self.store.load(name):
                        self.store.delete(name)
                    self.restore(self.store.environment_path(name), None)
                    self.call(['systemctl', 'daemon-reload'])
                    self.net_call('apply')
                    self.call(['podman', 'rename', hold, name])
                if running:
                    self.call(['podman', 'start', name], timeout=90)
            except Exception:
                raise cfg.ContainerConfigError(502, 'Yönetime alma ve geri dönüş başarısız; konteyner durumunu kontrol edin.') from err
            raise cfg.ContainerConfigError(502, 'Yönetime alma başarısız; önceki konteyner geri bırakıldı.') from err


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--state', default='/etc/master-stack/state.env')
    parser.add_argument('--operation')
    parser.add_argument('--refresh-tailnet', action='store_true')
    parser.add_argument('action', choices=ACTIONS, nargs='?')
    args = parser.parse_args()
    try:
        cfg.require(os.geteuid() == 0, 'Bu işlem root gerektirir.', 403)
        if args.refresh_tailnet:
            cfg.require(not args.operation and not args.action, 'Adres yenileme ayrı bir işlemdir.')
            result = Manager(args.state).refresh_tailnet()
        else:
            cfg.require(args.operation and args.action, 'İşlem kimliği ve eylem gereklidir.')
            raw = sys.stdin.read(LIMIT + 1)
            cfg.require(len(raw) <= LIMIT, 'İstek çok büyük.')
            request = json.loads(raw)
            result = Manager(args.state).execute(args.action, request, args.operation)
        print(json.dumps(result, ensure_ascii=False))
        if result.get('ok') is False:
            sys.exit(1)
    except Exception as err:
        status = err.status if isinstance(err, cfg.ContainerConfigError) else 502
        message = str(err) if isinstance(err, cfg.ContainerConfigError) else 'Konteyner işlemi tamamlanamadı.'
        print(json.dumps({'error': message, 'status': status}, ensure_ascii=False))
        sys.exit(1)


if __name__ == '__main__':
    main()
