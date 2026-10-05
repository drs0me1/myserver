#!/usr/bin/env python3
"""Disposable, actual rootful Podman + Quadlet worker acceptance (Linux/systemd).

Run on the explicitly disposable test host, with no other live fixture running:
  sudo python3 Data/tests/containers-worker-linux.py --source-root /path/to/repository
  IMAGE=docker.io/library/alpine:3.22 sudo -E python3 ... --source-root /path/to/repository

The source root may instead be Data/ or an installed runtime helper directory. Only four
named Python helpers are copied. State/locks/bind data are private scratch files; generated
Quadlets live under /run/containers/systemd with unique names. The existing, already-active
master-firewall.service is a prerequisite, never restarted by the fixture. A unique bridge
and nft table isolate fixture policy. Only an ephemeral loopback TCP/UDP port is published; no account/profile is
read, and cached images are retained. Exact fixture resources are cleaned even after failure.

Stdout is NDJSON. A final status=pass includes cleanup success; partial pass records do not
mean acceptance passed. Inspect Env values, raw command errors and journals are never printed.
SIGINT/SIGTERM run cleanup; SIGKILL/power loss cannot. Reboot/install persistence is separate.
"""
import argparse
import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import uuid


HELPERS = ('master_container_config.py', 'master_container_worker.py',
           'master_container_network.py', 'master_settings.py', 'master_container_binds.py')


def downloads_ids():
    """DD-227: new Konsol definitions run as the Files account; the fixture's writable bind is owned by it, as /srv is."""
    ids = {'DOWNLOADS_UID': '1000', 'DOWNLOADS_GID': '1000'}
    state = Path('/etc/master-stack/state.env')
    if state.is_file():
        for line in state.read_text(encoding='utf-8').splitlines():
            key, _, value = line.partition('=')
            if key in ids and value.strip().strip('"').isdigit():
                ids[key] = value.strip().strip('"')
    return ids


def block_list(source):
    """DD-224: the guard's single-source egress block list: Data/config or the installed state."""
    for path in (source.parent / 'config/defaults.env', Path('/etc/master-stack/state.env')):
        if path.is_file():
            for line in path.read_text(encoding='utf-8').splitlines():
                if line.startswith('VPN_BLOCK_DEST4='):
                    return line.split('=', 1)[1].strip().strip('"')
    raise SystemExit('VPN_BLOCK_DEST4 not found in Data/config/defaults.env or /etc/master-stack/state.env')


class FixtureFailure(Exception):
    pass


def require(condition, message):
    if not condition:
        raise FixtureFailure(message)


def emit(event, **fields):
    print(json.dumps(dict(event=event, **fields), sort_keys=True), flush=True)


def run(argv, timeout=90, check=True):
    try:
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise FixtureFailure('tool unavailable or timed out: ' + Path(argv[0]).name) from error
    # Do not forward tool output: both image tools and inspect can contain credentials.
    if check and result.returncode:
        raise FixtureFailure('tool failed: ' + Path(argv[0]).name + ', exit=' + str(result.returncode))
    return result


def data(argv):
    try:
        return json.loads(run(argv).stdout)
    except ValueError as error:
        raise FixtureFailure('invalid JSON from ' + Path(argv[0]).name) from error


def source_directory(root):
    root = Path(root).resolve()
    for directory in (root / 'Data/panel', root / 'panel', root):
        if all((directory / filename).is_file() and not (directory / filename).is_symlink() for filename in HELPERS):
            return directory
    raise FixtureFailure('source root lacks the four allowlisted regular helper files')


class Acceptance:
    def __init__(self, source, image):
        self.source, self.image = source, image
        self.token = uuid.uuid4().hex[:12]
        self.name = 'cw' + self.token + '-main'
        self.external = 'cw' + self.token + '-external'
        self.network = 'cw' + self.token + '-network'
        self.volume = 'cw' + self.token + '-data'
        self.table = 'worker_' + self.token
        self.prefix = 'cw' + self.token[:3]
        self.root = None
        self.armed = False
        self.claims = []
        self.step = 'preflight'
        self.hold = None
        self.external_info = None
        self.units = ['konsol-' + n + '.service' for n in (self.name, self.external)]
        self.quadlets = [Path('/run/containers/systemd') / ('konsol-' + n + '.container') for n in (self.name, self.external)]

    def claim(self, name, **details):
        self.claims.append(name)
        emit('check', name=name, status='pass', **details)

    def setup(self):
        require(os.geteuid() == 0 and sys.platform.startswith('linux'), 'requires root on Linux')
        require(Path('/run/systemd/system').is_dir(), 'requires real systemd')
        for tool in ('podman', 'systemctl', 'ip', 'nft'):
            require(shutil.which(tool), 'missing executable: ' + tool)
        require(run(['systemctl', 'is-active', '--quiet', 'master-firewall.service'], check=False).returncode == 0,
                'master-firewall.service must already be active; fixture will not start it')
        for kind, names in (('container', (self.name, self.external)), ('network', (self.network,)), ('volume', (self.volume,))):
            for name in names:
                require(run(['podman', kind, 'exists', name], check=False).returncode == 1, 'fixture resource name is unavailable')
        require(run(['podman', 'network', 'exists', 'podman'], check=False).returncode == 0,
                'plain adoption requires the existing default podman network')
        interfaces = data(['ip', '-j', 'link', 'show'])
        require(isinstance(interfaces, list) and not any(row.get('ifname', '').startswith(self.prefix) for row in interfaces),
                'random bridge prefix collides with an existing interface; rerun fixture')
        table = run(['nft', '-j', 'list', 'table', 'inet', self.table], check=False)
        require(table.returncode != 0 and ('No such file' in table.stderr or 'does not exist' in table.stderr),
                'unique fixture nft table is unavailable')
        require(not any(path.exists() or path.is_symlink() for path in self.quadlets), 'fixture Quadlet name already exists')
        for unit in self.units:
            require(run(['systemctl', 'show', '--property=LoadState', '--value', unit], check=False).stdout.strip() == 'not-found',
                    'fixture service name already exists')
        quadlet_root = self.quadlets[0].parent
        require(not quadlet_root.is_symlink(), 'runtime Quadlet directory must not be a symlink')
        quadlet_root.mkdir(parents=True, exist_ok=True)
        self.root = Path(tempfile.mkdtemp(prefix='containers-worker-', dir='/var/tmp')).resolve()
        os.chmod(self.root, 0o700)
        for name in ('helpers', 'run', 'state', 'mods', 'srv/proof space'):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        ids = downloads_ids()
        for name in ('srv', 'srv/proof space'):
            os.chown(self.root / name, int(ids['DOWNLOADS_UID']), int(ids['DOWNLOADS_GID']))
            os.chmod(self.root / name, 0o775)
        hashes = {}
        for filename in HELPERS:
            content = (self.source / filename).read_bytes()
            target = self.root / 'helpers' / filename
            target.write_bytes(content)
            target.chmod(0o600)
            hashes[filename] = hashlib.sha256(content).hexdigest()
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(self.root / 'helpers'))
        self.worker = importlib.import_module('master_container_worker')
        self.cfg = importlib.import_module('master_container_config')
        self.cfg.image_of(self.image)
        env = dict(KONTEYNER_STATE_DIR=str(self.root / 'state'), KONTEYNER_BIRIM_DIR=str(quadlet_root),
                   KONTEYNER_LOCK=str(self.root / 'run/containers.lock'), RUNTIME_DIR=str(self.root / 'run'),
                   SBIN_DIR=str(self.root / 'helpers'), MODULES_DIR=str(self.root / 'mods'),
                   SERVER_ROOT=str(self.root / 'srv'), FILES_PANEL_TRASH='.cop', SHARE_DIR='.pay',
                   KONTEYNER_NETWORK=self.network, KONTEYNER_BRIDGE_PREFIX=self.prefix,
                   KONTEYNER_NFT_TABLE=self.table, TAILSCALE_IF='tailscale0', VPN_BLOCK_DEST4=block_list(self.source),
                   KONTEYNER_BAGLAMA_DIR=str(self.root / 'run/konteyner-baglama'), **ids)
        self.state = self.root / 'state.env'
        self.state.write_text(''.join(k + '=' + ('"%s"' % v if ' ' in v else v) + '\n' for k, v in env.items()))
        self.state.chmod(0o600)
        self.store = self.cfg.Store(env)
        self.secret = 'synthetic-' + uuid.uuid4().hex
        self.proof = self.root / 'srv/proof space'
        self.armed = True
        emit('fixture', id=self.token, helpers=hashes, network=self.network, nft_table=self.table,
             bridge_prefix=self.prefix, units=self.units)

    def execute(self, action, payload, operation=None):
        return self.worker.Manager(self.state).execute(action, payload, operation or uuid.uuid4().hex)

    def inspect(self, name):
        return data(['podman', 'inspect', '--type', 'container', name])[0]

    def active(self, name):
        return run(['systemctl', 'is-active', '--quiet', 'konsol-' + name + '.service'], check=False).returncode == 0

    def reject(self, action, payload):
        try:
            self.execute(action, payload)
        except self.cfg.ContainerConfigError as error:
            require(error.status == 409, action + ' returned an unexpected rejection status')
        else:
            raise FixtureFailure(action + ' unexpectedly succeeded')

    def wait_proof(self):
        deadline = time.monotonic() + 10
        while not (self.proof / 'args').exists() or not (self.proof / 'secret').exists():
            require(time.monotonic() < deadline, 'container did not write bind-mount proof')
            time.sleep(0.1)
        require((self.proof / 'args').read_text().splitlines() == ['literal $HOME', '100%'],
                'Quadlet did not preserve literal dollar/percent command arguments')
        require((self.proof / 'secret').read_text() == self.secret, 'private environment value was not preserved')

    def lifecycle(self):
        self.step = 'create and literal arguments'
        self.execute('volume-create', {'name': self.volume})
        # Reserve a TCP/UDP pair only while choosing it; worker validation checks again before start.
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
            tcp.bind(('127.0.0.1', 0))
            host_port = tcp.getsockname()[1]
            udp.bind(('127.0.0.1', host_port))
        command = ['sh', '-c', 'printf "%s\\n" "$@" > /proof/args; printf "%s" "$FIXTURE_SECRET" > /proof/secret; '
                   'printf "%s" retained > /cache/marker; exec sleep 600', 'fixture', 'literal $HOME', '100%']
        config = dict(name=self.name, image=self.image, network='bridge',
                      ports=[dict(scope='local', host_port=host_port, container_port=8080, protocol=protocol, public_ack=False)
                             for protocol in ('tcp', 'udp')],
                      mounts=[dict(type='bind', source=str(self.proof), destination='/proof', read_only=False),
                              dict(type='volume', source=self.volume, destination='/cache', read_only=False)],
                      environment=[dict(name='FIXTURE_SECRET', value=self.secret, secret=True)],
                      command=command, autostart=True, restart='on-failure', cpus='', memory='')
        self.execute('create', {'config': config, 'start': True})
        saved = self.store.load(self.name)
        require(self.active(self.name), 'created service is not active')
        require('@sha256:' in saved['image'], 'image was not digest pinned')
        self.wait_proof()
        for path in (self.store.path(self.name), self.store.environment_path(self.name)):
            require(stat.S_IMODE(path.stat().st_mode) == 0o600, 'private file mode is not 0600')
        for path in (self.root / 'state/operations').glob('*.json'):
            require(self.secret not in path.read_text(), 'secret leaked to operation record')
        require(self.secret not in self.quadlets[0].read_text(), 'secret leaked to Quadlet')
        self.claim('actual_create_start_and_digest_pin')
        self.claim('literal_dollar_percent_arguments_and_bind_path_with_space')
        self.claim('private_environment_transport')

        self.step = 'stale revision and in-use resources'
        original_id = self.inspect(self.name)['Id']
        self.reject('save', {'name': self.name, 'revision': '0' * 32, 'config': dict(config, memory='128M')})
        self.reject('volume-remove', {'name': self.volume})
        self.reject('network-remove', {'name': self.network})
        self.reject('image-remove', {'image': saved['image']})
        require(self.inspect(self.name)['Id'] == original_id and self.active(self.name), 'rejected operation changed the container')
        self.claim('stale_revision_and_in_use_resource_refusals')

        self.step = 'running save with owned published ports'
        edited = self.store.redact(saved)
        edited['memory'] = '96M'
        self.execute('save', {'name': self.name, 'revision': saved['revision'], 'config': edited})
        saved = self.store.load(self.name)
        require(self.active(self.name) and self.inspect(self.name)['Id'] != original_id,
                'running save with owned published ports did not recreate successfully')

        self.step = 'stop and stopped save'
        self.execute('stop', {'name': self.name, 'revision': saved['revision']})
        saved = self.store.load(self.name)
        require(saved['manual_stop'] and saved['autostart'] and not self.active(self.name), 'stop latch was not persisted')
        require(run(['podman', 'container', 'exists', self.name], check=False).returncode == 1,
                'stopped Quadlet retained its runtime container unexpectedly')
        edited = self.store.redact(saved)
        edited['memory'] = '128M'
        self.execute('save', {'name': self.name, 'revision': saved['revision'], 'config': edited})
        saved = self.store.load(self.name)
        require(saved['memory'] == '128M' and saved['manual_stop'] and not self.active(self.name), 'stopped save changed running state')
        require(saved['environment'][0]['value'] == self.secret, 'stopped save lost the retained secret')
        require('WantedBy=' not in self.quadlets[0].read_text(), 'manually stopped service remains enabled for boot')
        self.reject('volume-remove', {'name': self.volume})
        self.claim('stop_absent_runtime_and_stopped_save_remains_stopped')
        self.claim('stopped_definition_keeps_volume_in_use')

        self.step = 'start and restart'
        self.execute('start', {'name': self.name, 'revision': saved['revision']})
        saved = self.store.load(self.name)
        require(not saved['manual_stop'] and self.active(self.name), 'start did not clear manual stop')
        before_restart = self.inspect(self.name)['Id']
        self.execute('restart', {'name': self.name, 'revision': saved['revision']})
        require(self.active(self.name) and self.inspect(self.name)['Id'] != before_restart, 'restart did not recreate a running container')
        self.wait_proof()
        self.claim('explicit_start_and_actual_restart')
        self.claim('running_save_and_restart_with_owned_loopback_tcp_udp_ports')

        self.step = 'remove retains data'
        saved = self.store.load(self.name)
        self.execute('remove', {'name': self.name, 'revision': saved['revision']})
        require(self.store.load(self.name) is None and not self.quadlets[0].exists(), 'remove left its managed definition')
        require(run(['podman', 'container', 'exists', self.name], check=False).returncode == 1, 'remove left a runtime container')
        require(run(['podman', 'volume', 'exists', self.volume], check=False).returncode == 0, 'remove deleted a named volume')
        volume = data(['podman', 'volume', 'inspect', self.volume])[0]
        require((Path(volume['Mountpoint']) / 'marker').read_text() == 'retained', 'named-volume data did not survive removal')
        require((self.proof / 'args').exists(), 'remove deleted host bind data')
        self.execute('volume-remove', {'name': self.volume})
        require(run(['podman', 'volume', 'exists', self.volume], check=False).returncode == 1, 'explicit unused-volume removal failed')
        self.claim('container_removal_retains_volume_and_bind_data')
        self.claim('explicit_unused_volume_removal')

    def adoption(self):
        self.step = 'plain external adoption preview'
        # Deliberately ordinary Podman defaults: no host-config overrides to make adoption pass.
        run(['podman', 'run', '--detach', '--name', self.external, '--network', 'bridge', self.image, 'sleep', '600'], timeout=600)
        self.external_info = self.inspect(self.external)
        preview = self.execute('adopt', {'name': self.external, 'preview': True})['preview']
        if preview['unsupported']:
            emit('adoption_diagnostic', unsupported=preview['unsupported'], defaults=self.scrubbed_defaults())
            raise FixtureFailure('plain external Podman defaults are rejected by adoption')
        require(self.store.load(self.external) is None and self.inspect(self.external)['Id'] == self.external_info['Id'],
                'adoption preview mutated the original container')
        require(all('value' not in e for e in preview['config']['environment']), 'adoption preview exposed environment values')
        self.claim('plain_external_adoption_preview_is_non_destructive')
        self.step = 'plain external adoption apply'
        operation = uuid.uuid4().hex
        self.hold = 'konsol-adopt-' + self.external + '-' + operation[:8]
        self.execute('adopt', dict(name=self.external, config=preview['config'], confirm=True, start=True,
                                   preview_fingerprint=preview['fingerprint']), operation)
        saved = self.store.load(self.external)
        require(saved is not None and self.active(self.external), 'adopted container is not managed and running')
        adopted = self.inspect(self.external)
        require(adopted['Id'] != self.external_info['Id'], 'adoption did not recreate the container')
        before_host, after_host = self.external_info.get('HostConfig') or {}, adopted.get('HostConfig') or {}
        require(before_host.get('PidsLimit') == after_host.get('PidsLimit'), 'adoption changed the actual PIDs limit')
        def limits(host):
            return {row['Name'].removeprefix('RLIMIT_').lower(): (row['Soft'], row['Hard']) for row in host.get('Ulimits') or []}
        require(limits(before_host) == limits(after_host), 'adoption changed the actual process ulimits')
        require((self.external_info.get('Config') or {}).get('StopSignal') == (adopted.get('Config') or {}).get('StopSignal'),
                'adoption changed the actual stop signal')
        self.claim('adoption_preserves_actual_pids_ulimits_and_stop_signal')
        imported = dict(e.split('=', 1) for e in (self.external_info.get('Config') or {}).get('Env', []) if '=' in e)
        require({e['name']: e['value'] for e in saved['environment']} == imported, 'adoption changed imported environment values')
        require(run(['podman', 'container', 'exists', self.hold], check=False).returncode == 1, 'adoption left its retained original')
        self.execute('remove', {'name': self.external, 'revision': saved['revision']})
        self.execute('network-remove', {'name': self.network})
        self.claim('plain_external_adoption_apply_and_remove')
        self.claim('explicit_unused_network_removal')

    def scrubbed_defaults(self):
        info = self.external_info or {}
        host = info.get('HostConfig') or {}
        config = info.get('Config') or {}
        # No Env, CreateCommand, Args, mounts, paths, health command, or label values.
        scalar_keys = ('PidsLimit', 'Memory', 'MemoryReservation', 'NanoCpus', 'CpuQuota', 'CpuPeriod', 'CpuShares',
                       'OomKillDisable', 'Privileged', 'ReadonlyRootfs', 'NetworkMode', 'IpcMode', 'PidMode', 'UTSMode', 'UsernsMode')
        safe = {key: host[key] for key in scalar_keys if isinstance(host.get(key), (int, float, bool, str))}
        safe['Ulimits'] = [{k: row.get(k) for k in ('Name', 'Soft', 'Hard')} for row in host.get('Ulimits') or []]
        safe['nonempty_option_keys'] = sorted(k for k in ('SecurityOpt', 'CapAdd', 'CapDrop', 'GroupAdd', 'Devices',
                                                         'DeviceRequests', 'Sysctls', 'Dns', 'DnsOptions', 'DnsSearch', 'ExtraHosts') if host.get(k))
        safe['interactive'] = {key: bool(config.get(key)) for key in ('Tty', 'OpenStdin', 'StdinOnce')}
        return safe

    def cleanup(self):
        errors = []
        def attempt(label, argv, absent=None):
            try:
                if absent and run(absent, check=False).returncode == 1:
                    return
                result = run(argv, check=False)
                if result.returncode:
                    errors.append(label)
            except Exception:
                errors.append(label)
        if self.armed:
            # Exact random fixture names only. No prune, global reset, image removal or wildcard.
            for unit in self.units:
                try:
                    state = run(['systemctl', 'show', '--property=LoadState', '--value', unit], check=False).stdout.strip()
                except Exception:
                    state = 'unknown'
                if state != 'not-found':
                    attempt('stop ' + unit, ['systemctl', 'stop', unit])
            for name in (self.name, self.external, self.hold):
                if name:
                    attempt('remove fixture container', ['podman', 'rm', '--force', name], ['podman', 'container', 'exists', name])
            for path in self.quadlets:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    errors.append('remove fixture Quadlet')
            attempt('daemon reload', ['systemctl', 'daemon-reload'])
            # reset-failed on a vanished unit may return nonzero; it carries no persistent resource.
            for unit in self.units:
                try:
                    run(['systemctl', 'reset-failed', unit], check=False)
                except Exception:
                    errors.append('reset fixture failed state')
            attempt('remove fixture volume', ['podman', 'volume', 'rm', self.volume], ['podman', 'volume', 'exists', self.volume])
            attempt('remove fixture network', ['podman', 'network', 'rm', self.network], ['podman', 'network', 'exists', self.network])
            try:
                table = run(['nft', '-j', 'list', 'table', 'inet', self.table], check=False)
                if table.returncode == 0:
                    attempt('remove fixture nft table', ['nft', 'delete', 'table', 'inet', self.table])
                elif 'No such file' not in table.stderr and 'does not exist' not in table.stderr:
                    errors.append('read fixture nft table during cleanup')
            except Exception:
                errors.append('read fixture nft table during cleanup')
        if self.root is not None:
            # DD-226: an anchor still mounted under the scratch tree would let rmtree reach the bound data.
            try:
                with open('/proc/self/mountinfo', encoding='utf-8') as stream:
                    if any(line.split()[4].startswith(str(self.root) + '/') for line in stream if len(line.split()) > 4):
                        errors.append('fixture bind anchor still mounted')
            except OSError:
                errors.append('read mount table during cleanup')
            # If a stop failed, do not erase bind data under a potentially live fixture container.
            if not errors:
                shutil.rmtree(self.root)
            else:
                emit('cleanup_retained', scratch=str(self.root), reason='cleanup failed; exact scratch retained for repair')
        emit('cleanup', status='pass' if not errors else 'fail', errors=errors)
        return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--image', default=os.environ.get('IMAGE', 'docker.io/library/alpine:3.22'))
    args = parser.parse_args()
    fixture = None
    error = None
    cleanup_errors = []
    def interrupted(signum, frame):
        raise FixtureFailure('interrupted by signal ' + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        fixture = Acceptance(source_directory(args.source_root), args.image)
        fixture.setup()
        fixture.lifecycle()
        fixture.adoption()
    except BaseException as caught:
        # No traceback/subprocess output: helper failure messages are designed for the public API.
        permitted = isinstance(caught, FixtureFailure) or fixture is not None and hasattr(fixture, 'cfg') and isinstance(caught, fixture.cfg.ContainerConfigError)
        error = str(caught) if permitted else type(caught).__name__
        emit('failure', stage=fixture.step if fixture else 'source preflight', error=error)
        if fixture and fixture.external_info:
            emit('adoption_diagnostic', defaults=fixture.scrubbed_defaults())
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        if fixture:
            try:
                cleanup_errors = fixture.cleanup()
            except BaseException as caught:
                cleanup_errors = ['cleanup interrupted: ' + type(caught).__name__]
                emit('cleanup', status='fail', errors=cleanup_errors, scratch=str(fixture.root))
    emit('result', status='pass' if not error and not cleanup_errors else 'fail',
         passed=fixture.claims if fixture else [], error=error, cleanup_errors=cleanup_errors)
    return 1 if error or cleanup_errors else 0


if __name__ == '__main__':
    sys.exit(main())
