#!/usr/bin/env python3
"""Persistent, private definitions for Konsol-managed rootful Podman containers.

Only explicit operations render definitions; no reconciliation or runtime socket. The module is
also imported by read views, which must call redact() before returning a definition.
"""
import copy
import json
import os
from pathlib import Path
import re
import stat
import uuid

import master_container_binds
import master_settings as settings

SCHEMA = 1
LIMIT = 1024 * 1024
NAME_RE = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z')
ENV_RE = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,127}\Z')
REV_RE = re.compile(r'[0-9a-f]{32}\Z')
IMAGE_RE = re.compile(r'(?:[a-z0-9][a-z0-9.-]*\.[a-z0-9.-]+|localhost)(?::[0-9]{1,5})?/(?:[a-z0-9]+(?:[._-][a-z0-9]+)*/)*[a-z0-9]+(?:[._-][a-z0-9]+)*(?::[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}|@sha256:[0-9a-f]{64})?\Z')
MANAGED_LABEL = 'io.master-stack.managed'
FIELDS = {'schema', 'name', 'image', 'image_ref', 'network', 'ports', 'mounts', 'environment', 'command',
          'autostart', 'manual_stop', 'restart', 'cpus', 'memory', 'pids_limit', 'ulimits', 'stop_signal', 'revision',
          'user'}
ULIMIT_NAMES = frozenset('as core cpu data fsize locks memlock msgqueue nice nofile nproc rss rtprio rttime sigpending stack'.split())
SIGNAL_NAMES = frozenset(('SIG' + name) for name in
                        'ABRT ALRM BUS CHLD CLD CONT FPE HUP ILL INT IO IOT KILL PIPE POLL PROF PWR QUIT SEGV STKFLT STOP SYS TERM TRAP TSTP TTIN TTOU URG USR1 USR2 VTALRM WINCH XCPU XFSZ'.split())


class ContainerConfigError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def require(ok, message, status=400):
    if not ok:
        raise ContainerConfigError(status, message)


def name_of(value):
    require(isinstance(value, str) and NAME_RE.fullmatch(value), 'Ad 1–64 harf/rakam, . _ veya - içermeli; harf/rakamla başlamalı.')
    return value


def image_of(value):
    require(isinstance(value, str) and len(value) <= 512 and IMAGE_RE.fullmatch(value),
            'İmajın tam kayıt adresini yazın (ör. docker.io/library/nginx:alpine).')
    return value


def ulimits_of(value):
    require(isinstance(value, list) and len(value) <= len(ULIMIT_NAMES), 'İşlem kaynak sınırları geçersiz.')
    result, seen = [], set()
    for row in value:
        require(isinstance(row, dict) and set(row) == {'name', 'soft', 'hard'} and
                isinstance(row['name'], str) and row['name'] in ULIMIT_NAMES and row['name'] not in seen and
                all(type(row[k]) is int and -1 <= row[k] <= 9223372036854775807 for k in ('soft', 'hard')),
                'İşlem kaynak sınırı geçersiz.')
        require(row['hard'] == -1 or 0 <= row['soft'] <= row['hard'], 'Yumuşak sınır sert sınırı aşamaz.')
        seen.add(row['name'])
        result.append(dict(row))
    return result


def stop_signal_of(value):
    require(isinstance(value, str), 'Durdurma sinyali geçersiz.')
    realtime = re.fullmatch(r'SIGRT(?:MIN(?:\+([0-9]{1,2}))?|MAX(?:-([0-9]{1,2}))?)', value)
    require(value == '' or value in SIGNAL_NAMES or re.fullmatch(r'[1-9][0-9]?', value) and int(value) <= 64 or
            realtime and all(int(offset) <= 30 for offset in realtime.groups() if offset is not None),
            'Durdurma sinyali geçersiz.')
    return value


def package_names(env):
    result = {}
    for mid, manifest in settings.read_manifests(env).items():
        quadlet = manifest.get('PAKET_KONTEYNER', '')
        if quadlet.endswith('.container'):
            result[quadlet[:-10]] = mid
    return result


def reserved(name, env):
    return name.startswith(('konsol-', 'master-', 'libpod-')) or name in package_names(env)


def text(value, limit, message):
    require(isinstance(value, str) and len(value) <= limit and all(ord(c) >= 32 and ord(c) != 127 for c in value), message)
    return value


def private_dir(path):
    """No-follow directory creation; never chmod through a user-controlled symlink."""
    with settings.parent_fd(Path(path) / '.directory', create=True) as (fd, _):
        info = os.fstat(fd)
        require(info.st_uid == os.geteuid(), 'Konteyner kayıt klasörünün sahibi geçersiz.', 503)
        os.fchmod(fd, 0o700)


def unlink(path):
    with settings.parent_fd(path) as (directory, name):
        try:
            info = os.stat(name, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            return
        require(stat.S_ISREG(info.st_mode), 'Konteyner kayıt dosyası güvenli değil.', 503)
        os.unlink(name, dir_fd=directory)
        os.fsync(directory)


def read_private(path):
    try:
        raw, info = settings.read_regular(path, LIMIT)
    except FileNotFoundError:
        return None
    except (OSError, settings.SettingsError) as err:
        raise ContainerConfigError(503, 'Konteyner kayıt dosyası güvenli biçimde okunamadı.') from err
    require(info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) & 0o077 == 0,
            'Konteyner kaydı özel değil; işlem yapılmadı.', 503)
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError) as err:
        raise ContainerConfigError(503, 'Konteyner kaydı okunamadı; üzerine yazılmadı.') from err
    require(isinstance(value, dict), 'Konteyner kaydı geçersiz.', 503)
    return value


def redact(definition):
    value = copy.deepcopy(definition)
    value['environment'] = [({'name': e['name'], 'secret': True, 'present': bool(e.get('value'))}
                             if e.get('secret') else dict(e)) for e in value.get('environment', [])]
    return value


class Store:
    redact = staticmethod(redact)

    def __init__(self, env):
        value = env.get('KONTEYNER_STATE_DIR', '')
        require(isinstance(value, str) and value.startswith('/') and '..' not in Path(value).parts,
                'Konteyner kayıt yolu eksik; kurulumu yeniden çalıştırın.', 503)
        self.root = Path(value)

    def path(self, name):
        return self.root / 'definitions' / (name_of(name) + '.json')

    def load(self, name):
        value = read_private(self.path(name))
        if value is not None:
            require(value.get('schema') == SCHEMA and value.get('name') == name and
                    isinstance(value.get('revision'), str) and REV_RE.fullmatch(value['revision']),
                    'Konteyner kaydı geçersiz; üzerine yazılmadı.', 503)
        return value

    def list(self):
        directory = self.root / 'definitions'
        if not directory.exists():
            return []
        require(not directory.is_symlink(), 'Konteyner kayıt yolu güvenli değil.', 503)
        return [value for p in sorted(directory.glob('*.json')) if (value := self.load(p.stem)) is not None]

    def save(self, definition):
        private_dir(self.root)
        private_dir(self.root / 'definitions')
        require(definition.get('schema') == SCHEMA and REV_RE.fullmatch(definition.get('revision', '')),
                'Konteyner kaydı geçersiz.', 503)
        settings.atomic(self.path(definition['name']), json.dumps(definition, ensure_ascii=False, sort_keys=True) + '\n', 0o600)

    def delete(self, name):
        unlink(self.path(name))

    def environment_path(self, name):
        return self.root / 'environment' / (name_of(name) + '.env')

    def write_environment(self, definition):
        private_dir(self.root)
        private_dir(self.root / 'environment')
        settings.atomic(self.environment_path(definition['name']),
                        ''.join(e['name'] + '=' + e['value'] + '\n' for e in definition['environment']), 0o600)


def protected_paths(env):
    root = Path(env['SERVER_ROOT'])
    paths = [root / env.get('FILES_PANEL_TRASH', '.cop'), root / env.get('SHARE_DIR', '.pay')]
    for mid, manifest in settings.read_manifests(env).items():
        paths.extend(Path(p) for p in manifest.get('PAKET_KLASORLER', '').split())
        report = manifest.get('PAKET_KLASOR_MODUL')
        if report:
            module = settings.load_package_module(env, mid, report, 'yazilan', 'Konteyner korunan klasör bildirimi')
            declared = module.yazilan(dict(env))
            require(isinstance(declared, list) and all(isinstance(p, str) and p.startswith('/') for p in declared),
                    'Uygulamanın korunan klasörleri okunamadı.', 503)
            paths.extend(Path(p) for p in declared)
    return paths


def bind_path(value, env):
    value = text(value, 1024, 'Sunucu klasörü geçersiz.')
    require(re.fullmatch(r'/[A-Za-z0-9_./ -]+', value) is not None, 'Sunucu klasörü geçersiz.')
    path, root = Path(value), Path(env['SERVER_ROOT'])
    require(path.is_absolute() and '..' not in path.parts and path.is_dir() and path.resolve() == path,
            'Sunucu klasörü mevcut ve gerçek bir klasör olmalı; sembolik bağlantı kullanılamaz.')
    require(root in path.parents and not any(p.startswith('.') for p in path.relative_to(root).parts),
            'Yalnız kullanıcı alanının gizli olmayan alt klasörleri bağlanabilir.')
    for blocked in protected_paths(env):
        require(path != blocked and path not in blocked.parents and blocked not in path.parents,
                'Uygulama, paylaşım veya çöp klasörü konteynere bağlanamaz.')
    return str(path)


def validate(value, env, previous=None):
    require(isinstance(value, dict) and not (set(value) - FIELDS), 'Konteyner ayar alanları geçersiz.')
    name = name_of(value.get('name', previous.get('name') if previous else None))
    require(not reserved(name, env), 'Bu ad bir uygulamaya veya sistem hizmetine ait.', 409)
    require(not previous or name == previous['name'], 'Konteyner adı değiştirilemez.')
    image = image_of(value.get('image', previous.get('image') if previous else None))
    original = value.get('image_ref', image)
    image_of(original)
    if previous and image == previous['image'] and original == previous.get('image_ref'):
        pass
    elif previous and image == previous['image'] and original != previous.get('image_ref'):
        image = original
    else:
        original = image
    network = value.get('network', 'bridge')
    require(network in ('bridge', 'none') or isinstance(network, str) and NAME_RE.fullmatch(network), 'Konteyner ağı geçersiz.')
    require(network not in ('host', 'podman'), 'Bu ağ Konsol tarafından yönetilmiyor.', 409)
    result = {'schema': SCHEMA, 'name': name, 'image': image, 'image_ref': original, 'network': network,
              'ports': [], 'mounts': [], 'environment': [], 'command': [],
              'manual_stop': bool(previous.get('manual_stop', False)) if previous else False,
              'revision': uuid.uuid4().hex}
    for key, default in (('autostart', True),):
        require(type(value.get(key, default)) is bool, 'Başlangıç ayarı geçersiz.')
        result[key] = value.get(key, default)
    restart = value.get('restart', 'on-failure')
    require(restart in ('no', 'on-failure', 'always'), 'Yeniden başlatma politikası geçersiz.')
    result['restart'] = restart
    cpus, memory = value.get('cpus', ''), value.get('memory', '')
    require(isinstance(cpus, str) and (not cpus or re.fullmatch(r'[0-9]{1,3}(?:\.[0-9]{1,3})?', cpus) and 0 < float(cpus) <= 256), 'CPU sınırı geçersiz.')
    require(isinstance(memory, str) and (not memory or re.fullmatch(r'[1-9][0-9]{0,8}[kKmMgG]?', memory)), 'Bellek sınırı geçersiz.')
    result.update(cpus=cpus, memory=memory)
    # Adoption preserves an observed limit even when an older editor omits this field.
    pids = value.get('pids_limit', (previous or {}).get('pids_limit', ''))
    require(isinstance(pids, str) and (pids in ('', '-1') or re.fullmatch(r'[1-9][0-9]{0,18}', pids) and
                                     int(pids) <= 9223372036854775807), 'Süreç sınırı geçersiz.')
    result['pids_limit'] = pids
    # DD-227: 'downloads' runs as the Files account without capabilities; 'image' keeps the image's own
    # (often root). Omitted: a new definition gets the least privilege, a stored one keeps how it ran.
    user = value.get('user', previous.get('user', 'image') if previous else 'downloads')
    require(user in ('image', 'downloads'), 'Çalıştıran hesap geçersiz.')
    result['user'] = user
    result['ulimits'] = ulimits_of(value.get('ulimits', (previous or {}).get('ulimits', [])))
    result['stop_signal'] = stop_signal_of(value.get('stop_signal', (previous or {}).get('stop_signal', '')))
    ports = value.get('ports', [])
    require(isinstance(ports, list) and len(ports) <= 32, 'Port listesi geçersiz.')
    seen = set()
    for port in ports:
        require(isinstance(port, dict) and set(port) <= {'scope', 'host_port', 'container_port', 'protocol', 'public_ack'}, 'Port alanları geçersiz.')
        require(port.get('scope') in ('local', 'tailscale', 'public') and port.get('protocol') in ('tcp', 'udp') and
                all(type(port.get(k)) is int and 1 <= port[k] <= 65535 for k in ('host_port', 'container_port')), 'Port geçersiz.')
        require(port['scope'] != 'public' or port.get('public_ack') is True, 'İnternet portu için açık onay gerekli.')
        key = (port['host_port'], port['protocol'])
        require(key not in seen, 'Aynı sunucu portu birden çok kez kullanılamaz.')
        seen.add(key)
        result['ports'].append(dict(port, public_ack=port.get('public_ack') is True))
    require(network != 'none' or not ports, 'Ağsız konteyner port yayımlayamaz.')
    mounts = value.get('mounts', [])
    require(isinstance(mounts, list) and len(mounts) <= 64, 'Birim listesi geçersiz.')
    destinations = set()
    for mount in mounts:
        require(isinstance(mount, dict) and set(mount) == {'type', 'source', 'destination', 'read_only'} and
                mount['type'] in ('bind', 'volume') and type(mount['read_only']) is bool, 'Birim alanları geçersiz.')
        dest = text(mount['destination'], 1024, 'Konteyner yolu geçersiz.')
        require(re.fullmatch(r'/[A-Za-z0-9_./ -]+', dest) and '..' not in Path(dest).parts and dest != '/' and
                dest not in destinations, 'Konteyner yolu mutlak, benzersiz ve güvenli olmalı.')
        destinations.add(dest)
        source = bind_path(mount['source'], env) if mount['type'] == 'bind' else name_of(mount['source'])
        result['mounts'].append(dict(mount, source=source, destination=dest))
    require(user == 'downloads' or not any(m['type'] == 'bind' and not m['read_only'] for m in result['mounts']),
            'Sunucu klasörüne yalnız Dosyalar hesabıyla yazılabilir; root gerektiren imajlar için birim veya salt okunur klasör kullanın.')
    environ = value.get('environment', [])
    require(isinstance(environ, list) and len(environ) <= 256, 'Ortam değişkeni listesi geçersiz.')
    old = {e['name']: e for e in (previous or {}).get('environment', [])}
    seen = set()
    for item in environ:
        require(isinstance(item, dict) and not (set(item) - {'name', 'value', 'secret', 'present'}) and
                isinstance(item.get('name'), str) and ENV_RE.fullmatch(item['name']) and type(item.get('secret', False)) is bool,
                'Ortam değişkeni geçersiz.')
        key, secret = item['name'], item.get('secret', False)
        require(key not in seen, 'Ortam değişkeni adı tekrar ediyor.')
        seen.add(key)
        val = item.get('value', '')
        if secret and not val and old.get(key, {}).get('secret'):
            val = old[key]['value']
        result['environment'].append({'name': key, 'value': text(val, 16384, 'Ortam değişkeni değeri geçersiz.'), 'secret': secret})
    command = value.get('command', [])
    require(isinstance(command, list) and len(command) <= 128, 'Komut ayrı argümanlardan oluşan bir liste olmalı.')
    result['command'] = [text(arg, 4096, 'Komut argümanı geçersiz.') for arg in command]
    return result


def quote(value, command=False):
    """Systemd words: percent specifiers everywhere, dollar expansion only in Exec directives."""
    result = str(value).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
    return '"' + (result.replace('$', '$$') if command else result) + '"'


def render_quadlet(definition, env, bindings=None):
    d = definition
    network = env.get('KONTEYNER_NETWORK', 'konsol') if d['network'] == 'bridge' else d['network']
    binds = [m['source'] for m in d['mounts'] if m['type'] == 'bind']
    lines = ['# Konsol tarafından oluşturuldu; kalıcı kaynak: konteyner tanımı.', '[Unit]',
             'Description=Konsol container ' + d['name'], 'After=network-online.target master-firewall.service',
             # DD-223: no Requires=, so a firewall restart does not restart the container.
             'Wants=network-online.target master-firewall.service']
    # DD-226: the Volume source is a pinned anchor, so the real folder stays a mount dependency here.
    lines.extend('RequiresMountsFor=' + quote(source) for source in binds)
    lines.extend(['', '[Container]',
             'ContainerName=' + d['name'], 'Image=' + d['image'], 'Pull=never', 'Network=' + network,
             'Label=' + MANAGED_LABEL + '=konsol', 'LogDriver=journald', 'NoNewPrivileges=true',
             'EnvironmentFile=' + quote(Store(env).environment_path(d['name']))])
    files_account = d.get('user', 'image') == 'downloads'
    if files_account:
        # DD-227: the Files account (DOWNLOADS_UID/GID), no capabilities; files stay group-writable like /srv.
        ids = [env.get('DOWNLOADS_UID', ''), env.get('DOWNLOADS_GID', '')]
        if not all(re.fullmatch(r'[1-9][0-9]{0,9}', i) for i in ids):
            raise ContainerConfigError(503, 'Dosyalar hesabı kimliği geçersiz; kurulumu yeniden çalıştırın.')
        lines.extend(['User=' + ids[0], 'Group=' + ids[1], 'DropCapability=all'])
    for binding in bindings or []:
        lines.append('PublishPort=' + binding)
    pinned = 0
    for mount in d['mounts']:
        # Quadlet reads Volume as a raw scalar (LookupAll), unlike EnvironmentFile/Exec.
        # Its generator quotes the resulting -v argument, including spaces. Outer quotes
        # here survive as literal characters in Podman's mount options. Paths were validated.
        source = mount['source']
        if mount['type'] == 'bind':
            # DD-226: Podman would resolve the path again at every start; it mounts the anchor that
            # ExecStartPre pinned through a descriptor instead.
            source = str(master_container_binds.anchor_path(env, d['name'], pinned, source))
            pinned += 1
        lines.append('Volume=' + source + ':' + mount['destination'] + (':ro' if mount['read_only'] else ':rw'))
    if d['command']:
        lines.append('Exec=' + ' '.join(quote(arg, command=True) for arg in d['command']))
    # Resource flags are numeric/size-validated, never a user-provided raw PodmanArgs field.
    limits = (['--cpus=' + d['cpus']] if d['cpus'] else []) + (['--memory=' + d['memory']] if d['memory'] else [])
    if files_account:
        limits.append('--umask=0002')
    if limits:
        lines.append('PodmanArgs=' + ' '.join(limits))
    if d.get('pids_limit'):
        lines.append('PidsLimit=' + d['pids_limit'])
    for limit in d.get('ulimits', []):
        lines.append('Ulimit=%s=%s:%s' % (limit['name'], limit['soft'], limit['hard']))
    if d.get('stop_signal'):
        lines.append('StopSignal=' + d['stop_signal'])
    helper = str(Path(env['SBIN_DIR']) / 'master_container_network.py')
    lines.extend(['', '[Service]', 'Restart=' + d['restart'], 'RestartSec=10s', 'TimeoutStartSec=180', 'TimeoutStopSec=75',
                  'UMask=0077'])
    if d['network'] != 'none':
        # DD-223: only the locked writers (firewall, worker, engine) apply the guard; the unit checks it,
        # so an automatic restart can never re-open a publication that was just revoked.
        lines.append('ExecStartPre=/usr/bin/python3 ' + quote(helper, command=True) + ' --state ' +
                     quote(env['STATE_FILE'], command=True) + ' --check')
    if binds:
        pin = '/usr/bin/python3 ' + quote(str(Path(env['SBIN_DIR']) / 'master_container_binds.py'), command=True) + \
            ' --state ' + quote(env['STATE_FILE'], command=True)
        lines.append('ExecStartPre=' + pin + ' bagla ' + ' '.join(quote(v, command=True) for v in [d['name']] + binds))
        lines.append('ExecStopPost=-' + pin + ' birak ' + quote(d['name'], command=True))
    if d['autostart'] and not d['manual_stop']:
        lines.extend(['', '[Install]', 'WantedBy=multi-user.target'])
    return '\n'.join(lines) + '\n'


def ownership(inspect, env):
    name = str(inspect.get('Name', '')).lstrip('/')
    if name in package_names(env):
        return 'appstore'
    labels = (inspect.get('Config') or {}).get('Labels') or inspect.get('Labels') or {}
    if inspect.get('Pod') or inspect.get('PodName') or any(k.startswith(('com.docker.compose.', 'io.podman.compose.', 'io.kubernetes.')) for k in labels):
        return 'controlled'
    unit = labels.get('PODMAN_SYSTEMD_UNIT')
    if labels.get(MANAGED_LABEL) == 'konsol' and unit == 'konsol-' + name + '.service':
        return 'konsol'
    if unit or labels.get('io.containers.autoupdate') or name.startswith(('master-', 'konsol-')):
        return 'controlled'
    cgroup = str((inspect.get('State') or {}).get('CgroupPath', ''))
    if any(part.endswith('.service') and not part.startswith('user@') for part in cgroup.split('/')):
        return 'controlled'
    return 'standalone'
