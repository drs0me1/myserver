"""Container manager persistence and failure contracts; all services and Podman are fakes."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'panel'))
import master_container_binds as binds
import master_container_config as cfg
import master_container_worker as worker

DIGEST = 'registry.example/app@sha256:' + 'a' * 64


class FakeRun:
    def __init__(self):
        self.calls = []
        self.containers = {}
        self.active = set()
        self.fail = None
        self.image = DIGEST
        self.images = {}
        self.volumes = set()
        self.volume_options = {}
        self.routes = []
        self.quadlets = None
        self.ignore_user = False
        self.dropped = None  # Podman 5.4.2 reports a fully dropped capability set as null (nrm, 2026-10-05)
        self.omit = ()

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        if self.fail and self.fail in ' '.join(argv):
            self.fail = None
            return subprocess.CompletedProcess(argv, 1, '', 'sensitive failure password=never-print')
        out, code = '', 0
        if argv[:3] == ['podman', 'container', 'exists']:
            code = 0 if argv[-1] in self.containers else 1
        elif argv[:3] == ['podman', 'inspect', '--type']:
            if argv[-1] in self.containers:
                out = json.dumps([self.containers[argv[-1]]])
            else:
                code = 1
        elif argv[:3] == ['podman', 'image', 'inspect']:
            out = json.dumps([self.images.get(argv[-1], {'Id': 'sha256:' + 'a' * 64, 'RepoDigests': [self.image], 'Config': {}})])
        elif argv[:3] == ['podman', 'ps', '-a']:
            out = json.dumps([] if '--filter' in argv else list(self.containers.values()))
        elif argv[:2] == ['podman', 'rename']:
            self.containers[argv[-1]] = self.containers.pop(argv[-2])
            self.containers[argv[-1]]['Name'] = argv[-1]
        elif argv[:2] == ['podman', 'rm']:
            self.containers.pop(argv[-1], None)
        elif argv[:2] in (['podman', 'start'], ['podman', 'stop'], ['podman', 'restart']):
            self.containers[argv[-1]]['State']['Running'] = argv[1] != 'stop'
        elif argv[:3] == ['podman', 'network', 'inspect']:
            out = json.dumps([{'name': argv[-1], 'driver': 'bridge', 'network_interface': 'ksl' + hashlib.sha256(argv[-1].encode()).hexdigest()[:10],
                               'labels': {cfg.MANAGED_LABEL: 'konsol'}}])
        elif argv[:3] == ['podman', 'volume', 'inspect']:
            out = json.dumps([{'Name': argv[-1], 'Driver': 'local', 'Options': self.volume_options}])
        elif argv[:3] == ['podman', 'network', 'ls']:
            out = '[]'
        elif argv[:4] == ['ip', '-j', '-4', 'route']:
            out = json.dumps(self.routes)
        elif argv[:2] == ['systemctl', 'is-active']:
            code = 0 if argv[-1] in self.active else 3
        elif argv[:2] == ['systemctl', 'start']:
            self.active.add(argv[-1])
            name = argv[-1][len('konsol-'):-len('.service')]
            lines = (self.quadlets / ('konsol-' + name + '.container')).read_text().splitlines() if self.quadlets else []
            value = lambda key: next((l.split('=', 1)[1] for l in lines if l.startswith(key + '=')), '')
            user = '' if self.ignore_user or not value('User') else value('User') + ':' + value('Group')
            caps = self.dropped if 'DropCapability=all' in lines and not self.ignore_user else ['CAP_CHOWN', 'CAP_DAC_OVERRIDE']
            self.containers[name] = {'Name': name, 'State': {'Running': True}, 'EffectiveCaps': caps, 'BoundingCaps': caps,
                                     'Config': {'Labels': {cfg.MANAGED_LABEL: 'konsol', 'PODMAN_SYSTEMD_UNIT': argv[-1]}, 'User': user}}
            for key in self.omit:
                self.containers[name].pop(key)
        elif argv[:2] == ['systemctl', 'stop']:
            self.active.discard(argv[-1])
            self.containers.pop(argv[-1][len('konsol-'):-len('.service')], None)
        elif argv[:2] == ['systemctl', 'show']:
            out = 'loaded\n'
        elif argv[:3] in (['podman', 'volume', 'exists'], ['podman', 'network', 'exists']):
            code = 0
        elif argv[0] == '/fixture/quadlet':
            name = next(Path(kwargs['env']['QUADLET_UNIT_DIRS']).glob('*.container')).stem
            out = '# ' + name + '.service\n[Service]\nExecStart=/usr/bin/podman\n'
        return subprocess.CompletedProcess(argv, code, out, '')


class FakeNetwork:
    tail_ip = '100.64.0.7'

    @staticmethod
    def validate_ports(env, ports, name, run):
        return ports

    def bindings(self, env, ports, run):
        return [('%s:%s:%s/%s' % (self.tail_ip if p['scope'] == 'tailscale' else '127.0.0.1',
                                 p['host_port'], p['container_port'], p['protocol'])) for p in ports]

    @staticmethod
    def apply(env, run):
        return None


class ContainerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='container-manager-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        for name in ('srv/data', 'srv/.pay', 'srv/media', 'state', 'run', 'quadlet', 'mods'):
            (self.root / name).mkdir(parents=True)
        self.env = {'KONTEYNER_STATE_DIR': str(self.root / 'state'), 'KONTEYNER_BIRIM_DIR': str(self.root / 'quadlet'),
                    'KONTEYNER_LOCK': str(self.root / 'run/container.lock'), 'RUNTIME_DIR': str(self.root / 'run'),
                    'SBIN_DIR': str(self.root / 'sbin'),
                    'SERVER_ROOT': str(self.root / 'srv'), 'FILES_PANEL_TRASH': '.cop', 'SHARE_DIR': '.pay',
                    'MODULES_DIR': str(self.root / 'mods'), 'TAILSCALE_IPV4': '100.64.0.7',
                    'KONTEYNER_BAGLAMA_DIR': str(self.root / 'run/konteyner-baglama'),
                    'DOWNLOADS_UID': '1000', 'DOWNLOADS_GID': '1000'}
        self.state = self.root / 'state.env'
        self.state.write_text(''.join(k + '=' + v + '\n' for k, v in self.env.items()))
        self.runner = FakeRun()
        self.runner.quadlets = self.root / 'quadlet'
        self.store = cfg.Store(self.env)
        self.manager = worker.Manager(str(self.state), run=self.runner, network=FakeNetwork(), generator='/fixture/quadlet')
        self.config = {'name': 'demo', 'image': 'registry.example/app:1', 'network': 'bridge', 'ports': [],
                       'mounts': [{'type': 'bind', 'source': str(self.root / 'srv/data'), 'destination': '/data', 'read_only': False}],
                       'environment': [{'name': 'TOKEN', 'value': 'test-secret', 'secret': True}],
                       'command': ['serve', 'literal $HOME', '100%'], 'autostart': True, 'restart': 'on-failure', 'cpus': '1.5', 'memory': '256M'}

    def execute(self, action, data):
        return self.manager.execute(action, data, uuid.uuid4().hex)

    def create(self, start=False):
        self.execute('create', {'name': 'demo', 'config': self.config, 'start': start})
        return self.store.load('demo')

    def test_config_validates_before_writing_and_refuses_unsafe_bind_and_ports(self):
        for change in ({'name': '../bad'}, {'image': 'ubuntu'}, {'ports': [{'scope': 'public', 'host_port': 8080, 'container_port': 80, 'protocol': 'tcp', 'public_ack': False}]},
                       {'environment': [{'name': 'BAD\nX', 'value': 'secret', 'secret': True}]},
                       {'mounts': [{'type': 'bind', 'source': '/etc', 'destination': '/etc', 'read_only': False}]},
                       {'mounts': [{'type': 'bind', 'source': str(self.root / 'srv'), 'destination': '/all', 'read_only': True}]},
                       {'privileged': True}):
            with self.subTest(change=change), self.assertRaises(cfg.ContainerConfigError):
                cfg.validate(dict(self.config, **change), self.env)
        self.assertEqual(self.runner.calls, [])
        self.assertEqual(self.store.list(), [])

    def test_bind_symlinks_and_package_protected_ancestors_are_refused(self):
        (self.root / 'srv/link').symlink_to(self.root / 'srv/data', target_is_directory=True)
        (self.root / 'mods/example').mkdir()
        (self.root / 'mods/example/paket.env').write_text('PAKET_KLASORLER="' + str(self.root / 'srv/data/private') + '"\n')
        for source in ('srv/link', 'srv/data', 'srv/.pay'):
            c = dict(self.config, mounts=[{'type': 'bind', 'source': str(self.root / source), 'destination': '/data', 'read_only': True}])
            with self.assertRaises(cfg.ContainerConfigError):
                cfg.validate(c, self.env)

    def test_create_pins_image_and_persists_private_definition_without_secrets_in_unit_or_result(self):
        result = self.execute('create', {'name': 'demo', 'config': self.config, 'start': False})
        d = self.store.load('demo')
        self.assertEqual(d['image'], DIGEST)
        self.assertEqual(d['image_ref'], self.config['image'])
        self.assertEqual(d['schema'], 1)
        self.assertEqual((self.root / 'state/definitions/demo.json').stat().st_mode & 0o777, 0o600)
        self.assertNotIn('test-secret', json.dumps(result))
        self.assertNotIn('test-secret', (self.root / 'quadlet/konsol-demo.container').read_text())
        self.assertNotIn('test-secret', json.dumps(self.runner.calls))
        self.assertEqual(d['environment'][0]['value'], 'test-secret')

    def test_quadlet_volume_is_raw_scalar_while_exec_and_environment_file_use_argument_syntax(self):
        source = self.root / 'srv/proof space'
        source.mkdir()
        self.config['mounts'] = [{'type': 'bind', 'source': str(source), 'destination': '/proof space', 'read_only': False},
                                 {'type': 'volume', 'source': 'data-volume', 'destination': '/cache', 'read_only': True}]
        self.create()
        lines = self.manager.quadlet('demo').read_text().splitlines()
        # Quadlet 5.4 addVolumes uses LookupAll + SplitN, not its argument/unquote parser.
        # A wrapping quote reaches Podman as part of the rw/ro option, including paths with spaces.
        # DD-226: a bind mounts its pinned anchor, never the path; the real path stays a mount dependency.
        anchor = binds.anchor_path(self.manager.env, 'demo', 0, str(source))
        self.assertEqual([line for line in lines if line.startswith('Volume=')],
                         ['Volume=' + str(anchor) + ':/proof space:rw', 'Volume=data-volume:/cache:ro'])
        self.assertIn('RequiresMountsFor="' + str(source) + '"', lines)
        self.assertIn('EnvironmentFile="' + str(self.store.environment_path('demo')) + '"', lines)
        self.assertIn('Exec="serve" "literal $$HOME" "100%%"', lines)

    def test_quadlet_waits_for_the_firewall_but_never_restarts_with_it(self):
        # DD-223: Wants/After instead of Requires= (a firewall restart no longer restarts the
        # container); the unit only checks the guard a locked writer applied, and retries.
        d = self.create()
        lines = self.manager.quadlet('demo').read_text().splitlines()
        self.assertIn('After=network-online.target master-firewall.service', lines)
        self.assertIn('Wants=network-online.target master-firewall.service', lines)
        self.assertEqual([l for l in lines if l.split('=', 1)[0] in ('Requires', 'Requisite', 'BindsTo', 'PartOf')], [])
        pre = [l for l in lines if l.startswith('ExecStartPre=')]
        guard = [l for l in pre if 'master_container_network.py' in l]
        self.assertEqual(len(guard), 1)
        self.assertEqual(pre[0], guard[0], 'the guard is checked before anything else')
        self.assertTrue(guard[0].endswith(' --check'), guard[0])
        self.assertIn('RestartSec=10s', lines)
        # Without a network there is no publication and nothing to wait for.
        self.assertNotIn('master_container_network.py', cfg.render_quadlet(dict(d, network='none', ports=[]), self.manager.env, []))

    def test_bind_sources_are_pinned_after_the_guard_check_and_released_on_stop(self):
        # DD-226: ExecStartPre checks the guard, then pins every bind source; ExecStopPost releases.
        self.config['mounts'].append({'type': 'volume', 'source': 'cache-volume', 'destination': '/cache', 'read_only': False})
        self.create()
        lines = self.manager.quadlet('demo').read_text().splitlines()
        helper = '"' + str(Path(self.env['SBIN_DIR']) / 'master_container_binds.py') + '"'
        state = '"' + str(self.state) + '"'
        pre = [l for l in lines if l.startswith('ExecStartPre=')]
        self.assertEqual(len(pre), 2)
        self.assertTrue(pre[0].endswith(' --check'), pre[0])
        self.assertEqual(pre[1], 'ExecStartPre=/usr/bin/python3 ' + helper + ' --state ' + state + ' bagla "demo" "' + str(self.root / 'srv/data') + '"')
        self.assertIn('ExecStopPost=-/usr/bin/python3 ' + helper + ' --state ' + state + ' birak "demo"', lines)
        self.assertIn('Volume=' + str(binds.anchor_path(self.manager.env, 'demo', 0, str(self.root / 'srv/data'))) + ':/data:rw', lines)
        self.assertIn('Volume=cache-volume:/cache:rw', lines)
        # Without a bind there is nothing to pin or release.
        d = self.store.load('demo')
        plain = cfg.render_quadlet(dict(d, mounts=[m for m in d['mounts'] if m['type'] == 'volume']), self.manager.env, [])
        self.assertNotIn('master_container_binds.py', plain)
        self.assertNotIn('RequiresMountsFor=', plain)

    def test_files_account_runs_without_capabilities_and_writes_group_writable(self):
        # DD-227: User/Group from the state, DropCapability=all and a group-writable umask; ready() proves them.
        self.config['user'] = 'downloads'
        d = self.create(start=True)
        lines = self.manager.quadlet('demo').read_text().splitlines()
        for line in ('User=1000', 'Group=1000', 'DropCapability=all', 'NoNewPrivileges=true',
                     'PodmanArgs=--cpus=1.5 --memory=256M --umask=0002'):
            self.assertIn(line, lines)
        self.assertEqual(d['user'], 'downloads')
        self.assertEqual(self.runner.containers['demo']['Config']['User'], '1000:1000')

    def test_image_account_cannot_write_server_folders(self):
        self.config['user'] = 'image'
        with self.assertRaises(cfg.ContainerConfigError) as err:
            self.create()
        self.assertIn('Dosyalar hesabıyla', str(err.exception))
        self.assertFalse(any(c[0] == 'podman' for c in self.runner.calls), 'refused before any pull or stop')
        self.assertEqual(self.store.list(), [])
        for mounts in ([dict(self.config['mounts'][0], read_only=True)],
                       [{'type': 'volume', 'source': 'cache-volume', 'destination': '/cache', 'read_only': False}]):
            with self.subTest(mounts=mounts):
                self.assertEqual(cfg.validate(dict(self.config, mounts=mounts), self.env)['user'], 'image')
        with self.assertRaises(cfg.ContainerConfigError):
            cfg.validate(dict(self.config, user='root'), self.env)

    def test_account_defaults_new_definitions_to_files_and_keeps_older_ones_as_they_ran(self):
        d = self.create()
        self.assertEqual(d['user'], 'downloads', 'an omitted account means least privilege for a new definition')
        self.assertEqual(cfg.validate(self.config, self.env, d)['user'], 'downloads', 'preserved when omitted')
        older = {k: v for k, v in d.items() if k != 'user'}  # stored before DD-227: it ran as the image's account
        rendered = cfg.render_quadlet(older, self.manager.env, [])
        self.assertNotIn('User=', rendered)
        self.assertNotIn('--umask', rendered)
        with self.assertRaises(cfg.ContainerConfigError):  # saving it with a writable folder needs the switch
            cfg.validate(self.config, self.env, older)

    def test_files_account_ids_must_be_valid(self):
        d = dict(self.create(), user='downloads')
        for uid in ('0', 'abc', ''):
            with self.subTest(uid=uid), self.assertRaises(cfg.ContainerConfigError) as err:
                cfg.render_quadlet(d, dict(self.manager.env, DOWNLOADS_UID=uid), [])
            self.assertEqual(err.exception.status, 503)

    def test_ready_proves_the_files_account_and_dropped_capabilities(self):
        self.config['user'] = 'downloads'
        self.runner.ignore_user = True  # Podman did not apply the account
        with self.assertRaises(cfg.ContainerConfigError):
            self.create(start=True)
        self.assertNotIn('konsol-demo.service', self.runner.active)
        self.runner.ignore_user = False
        for omit in (('EffectiveCaps',), ('BoundingCaps',)):  # an inspect without the field proves nothing
            self.runner.omit = omit
            with self.subTest(omit=omit), self.assertRaises(cfg.ContainerConfigError) as err:
                self.create(start=True)
            self.assertEqual(err.exception.status, 502)
            self.assertNotIn('konsol-demo.service', self.runner.active)
        self.runner.omit = ()
        self.runner.dropped = []  # another Podman may print the empty set as a list
        self.assertEqual(self.create(start=True)['user'], 'downloads')
        self.assertIn('konsol-demo.service', self.runner.active)

    def test_adoption_maps_the_downloads_account_and_refuses_other_users(self):
        info = self.external()
        for user, expected in (('1000:1000', 'downloads'), ('1000', 'downloads'), ('', 'image')):
            info['Config']['User'] = user
            preview = self.execute('adopt', {'name': 'foreign', 'preview': True})['preview']
            self.assertEqual((preview['unsupported'], preview['config']['user']), ([], expected), user)
        info['Config']['User'] = '33'
        self.assertIn('User', self.execute('adopt', {'name': 'foreign', 'preview': True})['preview']['unsupported'])

    def test_stale_revision_refuses_before_any_mutation(self):
        d = self.create()
        before = len(self.runner.calls)
        for action in ('save', 'start', 'stop', 'restart', 'remove'):
            with self.subTest(action=action), self.assertRaises(cfg.ContainerConfigError) as err:
                self.execute(action, {'name': 'demo', 'revision': '0'*32, 'config': self.config})
            self.assertEqual(err.exception.status, 409)
        self.assertEqual(len(self.runner.calls), before)
        self.assertEqual(self.store.load('demo'), d)

    def test_stop_latch_survives_edit_and_start_clears_it(self):
        d = self.create(start=True)
        self.execute('stop', {'name': 'demo', 'revision': d['revision']})
        d = self.store.load('demo')
        self.assertTrue(d['manual_stop'])
        self.assertTrue(d['autostart'])
        self.assertNotIn('WantedBy=', (self.root / 'quadlet/konsol-demo.container').read_text())
        modified = copy.deepcopy(self.config)
        modified['environment'][0].pop('value')
        modified['memory'] = '512M'
        self.execute('save', {'name': 'demo', 'revision': d['revision'], 'config': modified})
        d = self.store.load('demo')
        self.assertTrue(d['manual_stop'])
        self.assertEqual(d['environment'][0]['value'], 'test-secret')
        self.assertNotIn('konsol-demo.service', self.runner.active)
        self.execute('start', {'name': 'demo', 'revision': d['revision']})
        self.assertFalse(self.store.load('demo')['manual_stop'])
        self.assertIn('konsol-demo.service', self.runner.active)

    def test_bad_validation_does_not_stop_running_service(self):
        d = self.create(start=True)
        before = len(self.runner.calls)
        with self.assertRaises(cfg.ContainerConfigError):
            self.execute('save', {'name': 'demo', 'revision': d['revision'], 'config': dict(self.config, memory='1M\nExecStart=/bad')})
        self.assertFalse(any(c[:2] == ['systemctl', 'stop'] for c in self.runner.calls[before:]))
        self.assertIn('konsol-demo.service', self.runner.active)

    def test_failed_recreation_restores_definition_and_running_state(self):
        d = self.create(start=True)
        old = (self.root / 'quadlet/konsol-demo.container').read_bytes()
        self.runner.fail = 'systemctl start konsol-demo.service'
        with self.assertRaises(cfg.ContainerConfigError):
            self.execute('save', {'name': 'demo', 'revision': d['revision'], 'config': dict(self.config, memory='512M')})
        self.assertEqual(self.store.load('demo'), d)
        self.assertEqual((self.root / 'quadlet/konsol-demo.container').read_bytes(), old)
        self.assertIn('konsol-demo.service', self.runner.active)

    def test_remove_retains_mounts_named_volumes_and_image(self):
        self.config['mounts'].append({'type': 'volume', 'source': 'data-volume', 'destination': '/cache', 'read_only': False})
        d = self.create(start=True)
        before = len(self.runner.calls)
        self.execute('remove', {'name': 'demo', 'revision': d['revision']})
        self.assertIsNone(self.store.load('demo'))
        self.assertFalse((self.root / 'quadlet/konsol-demo.container').exists())
        self.assertTrue((self.root / 'srv/data').exists())
        self.assertFalse(any(c[:3] in (['podman', 'volume', 'rm'], ['podman', 'image', 'rm']) for c in self.runner.calls[before:]))

    def test_operations_are_redacted_and_duplicate_ids_cannot_repeat_actions(self):
        op = uuid.uuid4().hex
        self.manager.execute('create', {'name': 'demo', 'config': self.config}, op)
        record = json.loads((self.root / ('state/operations/' + op + '.json')).read_text())
        self.assertEqual(record['state'], 'done')
        self.assertNotIn('test-secret', json.dumps(record))
        count = len(self.runner.calls)
        with self.assertRaises(cfg.ContainerConfigError):
            self.manager.execute('create', {'name': 'demo', 'config': self.config}, op)
        self.assertEqual(len(self.runner.calls), count)

    def test_foreign_controllers_and_reserved_app_names_refuse_mutation(self):
        for attrs in ({'Config': {'Labels': {'PODMAN_SYSTEMD_UNIT': 'foreign.service'}}},
                      {'Pod': 'somepod'}, {'Config': {'Labels': {'com.docker.compose.project': 'p'}}}):
            self.runner.containers['foreign'] = dict({'Name': 'foreign', 'State': {'Running': False}}, **attrs)
            with self.assertRaises(cfg.ContainerConfigError):
                self.execute('remove', {'name': 'foreign'})
        self.assertFalse(any(c[:2] == ['podman', 'rm'] for c in self.runner.calls))
        (self.root / 'mods/torrent').mkdir()
        (self.root / 'mods/torrent/paket.env').write_text('PAKET_KONTEYNER="qbittorrent.container"\n')
        with self.assertRaises(cfg.ContainerConfigError):
            self.execute('create', {'name': 'qbittorrent', 'config': dict(self.config, name='qbittorrent')})

    def test_redact_never_modifies_stored_values(self):
        d = self.create()
        redacted = cfg.redact(d)
        self.assertNotIn('value', redacted['environment'][0])
        self.assertTrue(redacted['environment'][0]['present'])
        self.assertEqual(d['environment'][0]['value'], 'test-secret')

    def external(self, name='foreign'):
        info = {'Id': 'b'*64, 'Name': name, 'ImageName': 'registry.example/app:1', 'Image': 'sha256:' + 'a'*64,
                'State': {'Running': True}, 'Config': {'Labels': {}, 'Cmd': ['serve'], 'Env': ['TOKEN=import-secret']},
                'HostConfig': {'NetworkMode': 'bridge', 'PortBindings': {}, 'RestartPolicy': {'Name': 'no'}}, 'Mounts': []}
        self.runner.containers[name] = info
        return info

    def test_standalone_lifecycle_and_adoption_preview_are_non_destructive(self):
        self.external()
        preview = self.execute('adopt', {'name': 'foreign', 'preview': True})['preview']
        self.assertEqual(preview['unsupported'], [])
        self.assertNotIn('import-secret', json.dumps(preview))
        self.assertEqual(self.store.list(), [])
        self.assertFalse(any(c[:2] in (['podman', 'stop'], ['podman', 'rename']) for c in self.runner.calls))
        self.execute('stop', {'name': 'foreign'})
        self.assertFalse(self.runner.containers['foreign']['State']['Running'])
        self.execute('start', {'name': 'foreign'})
        self.assertTrue(self.runner.containers['foreign']['State']['Running'])

    def test_adoption_preserves_imported_secrets_and_stale_preview_is_refused(self):
        info = self.external()
        preview = self.execute('adopt', {'name': 'foreign', 'preview': True})['preview']
        with self.assertRaises(cfg.ContainerConfigError):
            self.execute('adopt', {'name': 'foreign', 'confirm': True, 'preview_fingerprint': 'wrong', 'config': preview['config']})
        self.assertTrue(info['State']['Running'])
        self.execute('adopt', {'name': 'foreign', 'confirm': True, 'preview_fingerprint': preview['fingerprint'],
                               'config': preview['config'], 'start': False})
        self.assertEqual(self.store.load('foreign')['environment'][0]['value'], 'import-secret')
        self.assertNotIn('konsol-foreign.service', self.runner.active)
        self.assertFalse(any(name.startswith('konsol-adopt-') for name in self.runner.containers))

    def test_unsupported_adoption_options_block_before_stop(self):
        info = self.external()
        info['HostConfig']['Privileged'] = True
        preview = self.execute('adopt', {'name': 'foreign', 'preview': True})['preview']
        self.assertIn('Privileged', preview['unsupported'])
        with self.assertRaises(cfg.ContainerConfigError):
            self.execute('adopt', {'name': 'foreign', 'confirm': True, 'preview_fingerprint': preview['fingerprint'], 'config': preview['config']})
        self.assertFalse(any(c[:2] == ['podman', 'stop'] for c in self.runner.calls))

    def test_adoption_preserves_observed_pid_limit_including_stock_podman_default(self):
        for observed, expected in ((2048, '2048'), (512, '512'), (-1, '-1'), (0, '-1')):
            with self.subTest(observed=observed):
                info = self.external()
                info['HostConfig'].update(PidsLimit=observed, IpcMode='shareable', PidMode='private', UTSMode='private', UsernsMode='')
                preview = self.execute('adopt', {'name': 'foreign', 'preview': True})['preview']
                self.assertEqual(preview['unsupported'], [])
                self.assertEqual(preview['config']['pids_limit'], expected)
                self.execute('adopt', {'name': 'foreign', 'confirm': True, 'preview_fingerprint': preview['fingerprint'],
                                       'config': preview['config'], 'start': False})
                saved = self.store.load('foreign')
                self.assertEqual(saved['pids_limit'], expected)
                self.assertIn('PidsLimit=' + expected, self.manager.quadlet('foreign').read_text())
                edited = self.store.redact(saved)
                edited.pop('pids_limit')  # Existing UI versions do not send the hidden supported field.
                edited['memory'] = '256M'
                self.execute('save', {'name': 'foreign', 'revision': saved['revision'], 'config': edited})
                saved = self.store.load('foreign')
                self.assertEqual(saved['pids_limit'], expected)
                self.execute('remove', {'name': 'foreign', 'revision': saved['revision']})

    def test_pid_limit_validation_is_structured_and_never_a_raw_podman_argument(self):
        self.assertEqual(cfg.validate(dict(self.config, pids_limit='4096'), self.env)['pids_limit'], '4096')
        for value in ('0', '-2', '10 --privileged', '9223372036854775808', True, 2048):
            with self.subTest(value=value), self.assertRaises(cfg.ContainerConfigError):
                cfg.validate(dict(self.config, pids_limit=value), self.env)

    def test_running_adoption_preserves_ulimits_and_stop_signal_when_editor_omits_them(self):
        info = self.external()
        info['Config']['StopSignal'] = 'SIGTERM'  # Runtime default, absent from the image config.
        info['HostConfig'].update(PidsLimit=2048, Ulimits=[
            {'Name': 'RLIMIT_NOFILE', 'Soft': 1048576, 'Hard': 1048576},
            {'Name': 'RLIMIT_NPROC', 'Soft': 1048576, 'Hard': 1048576},
            {'Name': 'RLIMIT_CORE', 'Soft': 0, 'Hard': 18446744073709551615}])
        expected = [{'name': 'nofile', 'soft': 1048576, 'hard': 1048576},
                    {'name': 'nproc', 'soft': 1048576, 'hard': 1048576},
                    {'name': 'core', 'soft': 0, 'hard': -1}]
        preview = self.execute('adopt', {'name': 'foreign', 'preview': True})['preview']
        self.assertEqual(preview['unsupported'], [])
        self.assertEqual(preview['config']['ulimits'], expected)
        self.assertEqual(preview['config']['stop_signal'], 'SIGTERM')
        self.execute('adopt', {'name': 'foreign', 'confirm': True, 'preview_fingerprint': preview['fingerprint'],
                               'config': preview['config'], 'start': True})
        saved = self.store.load('foreign')
        edited = self.store.redact(saved)
        for key in ('ulimits', 'stop_signal', 'pids_limit'):
            edited.pop(key)
        edited['memory'] = '128M'
        self.execute('save', {'name': 'foreign', 'revision': saved['revision'], 'config': edited})
        saved = self.store.load('foreign')
        self.assertEqual(saved['ulimits'], expected)
        self.assertEqual(saved['stop_signal'], 'SIGTERM')
        lines = self.manager.quadlet('foreign').read_text().splitlines()
        self.assertIn('StopSignal=SIGTERM', lines)
        self.assertIn('Ulimit=nofile=1048576:1048576', lines)
        self.assertIn('Ulimit=core=0:-1', lines)

    def test_ulimit_and_signal_validation_rejects_malformed_values_before_any_stop(self):
        expected = [{'name': 'nofile', 'soft': 512, 'hard': 2048}]
        valid = cfg.validate(dict(self.config, ulimits=expected, stop_signal='SIGUSR1'), self.env)
        self.assertEqual(valid['ulimits'], expected)
        self.assertEqual(valid['stop_signal'], 'SIGUSR1')
        for changed in ({'ulimits': [{'name': 'nofile --privileged', 'soft': 1, 'hard': 2}]},
                        {'ulimits': [{'name': 'nofile', 'soft': -1, 'hard': 10}]},
                        {'ulimits': [{'name': 'nofile', 'soft': True, 'hard': 10}]},
                        {'ulimits': expected + expected}, {'stop_signal': 'SIGTERM\nExecStart=/bad'},
                        {'stop_signal': '65'}, {'stop_signal': True}):
            with self.subTest(changed=changed), self.assertRaises(cfg.ContainerConfigError):
                cfg.validate(dict(self.config, **changed), self.env)
        self.assertEqual(self.runner.calls, [])

    def test_failed_adoption_returns_original_container(self):
        self.external()
        preview = self.execute('adopt', {'name': 'foreign', 'preview': True})['preview']
        self.runner.fail = 'systemctl start konsol-foreign.service'
        with self.assertRaises(cfg.ContainerConfigError):
            self.execute('adopt', {'name': 'foreign', 'confirm': True, 'preview_fingerprint': preview['fingerprint'],
                                   'config': preview['config'], 'start': True})
        self.assertIsNone(self.store.load('foreign'))
        self.assertTrue(self.runner.containers['foreign']['State']['Running'])
        self.assertEqual(self.runner.containers['foreign']['Config']['Env'], ['TOKEN=import-secret'])

    def test_volume_and_network_deletion_checks_stopped_definition_references(self):
        self.config['mounts'] = [{'type': 'volume', 'source': 'my-volume', 'destination': '/data', 'read_only': False}]
        self.create()
        for action, name in (('volume-remove', 'my-volume'), ('network-remove', 'konsol')):
            with self.assertRaises(cfg.ContainerConfigError) as caught:
                self.execute(action, {'name': name})
            self.assertEqual(caught.exception.status, 409)
        self.execute('volume-create', {'name': 'unused'})
        self.execute('volume-remove', {'name': 'unused'})
        self.assertIn(['podman', 'volume', 'rm', 'unused'], self.runner.calls)

    def test_image_delete_protects_package_and_saved_definition_pins(self):
        self.create()
        with self.assertRaises(cfg.ContainerConfigError):
            self.execute('image-remove', {'image': 'sha256:' + 'a'*64})
        self.store.delete('demo')
        (self.root / 'mods/app').mkdir()
        (self.root / 'mods/app/paket.env').write_text('PAKET_IMAJ="' + DIGEST + '"\n')
        with self.assertRaises(cfg.ContainerConfigError):
            self.execute('image-remove', {'image': 'sha256:' + 'a'*64})
        self.assertFalse(any(c[:3] == ['podman', 'image', 'rm'] for c in self.runner.calls))

    def test_image_update_is_explicit_and_preserves_stopped_state(self):
        d = self.create()
        self.runner.image = 'registry.example/app@sha256:' + 'c'*64
        self.execute('image-update', {'name': 'demo', 'revision': d['revision']})
        self.assertEqual(self.store.load('demo')['image'], self.runner.image)
        self.assertNotIn('konsol-demo.service', self.runner.active)
        self.assertIn(['podman', 'pull', '--quiet', 'registry.example/app:1'], self.runner.calls)

    def test_stop_works_without_available_tailnet_address(self):
        d = self.create(start=True)
        with patch.object(self.manager.network, 'bindings', side_effect=ValueError('tailnet unavailable')):
            self.execute('stop', {'name': 'demo', 'revision': d['revision']})
        self.assertTrue(self.store.load('demo')['manual_stop'])

    def test_start_revalidates_bind_paths_after_they_are_replaced_by_symlinks(self):
        d = self.create()
        (self.root / 'srv/data').rmdir()
        (self.root / 'srv/data').symlink_to(self.root / 'srv/media', target_is_directory=True)
        with self.assertRaises(cfg.ContainerConfigError):
            self.execute('start', {'name': 'demo', 'revision': d['revision']})
        self.assertNotIn('konsol-demo.service', self.runner.active)

    def test_failed_operation_keeps_step_and_never_echoes_subprocess_secrets(self):
        d = self.create(start=True)
        op = uuid.uuid4().hex
        self.runner.fail = 'systemctl start konsol-demo.service'
        with self.assertRaises(cfg.ContainerConfigError):
            self.manager.execute('restart', {'name': 'demo', 'revision': d['revision']}, op)
        record = json.loads((self.root / ('state/operations/' + op + '.json')).read_text())
        self.assertEqual(record['state'], 'failed')
        self.assertIn('failed_step', record)
        self.assertNotIn('never-print', json.dumps(record))

    def test_tailnet_refresh_preserves_stop_latch_revision_and_skips_unchanged_units(self):
        self.config['ports'] = [{'scope': 'tailscale', 'host_port': 18080, 'container_port': 80,
                                 'protocol': 'tcp', 'public_ack': False}]
        d = self.create(start=True)
        self.execute('stop', {'name': 'demo', 'revision': d['revision']})
        old = self.store.load('demo')
        pending = self.root / 'run/containers-tailnet.pending'
        pending.write_text('100.64.0.9\n\n')
        self.manager.network.tail_ip = '100.64.0.9'
        before = len(self.runner.calls)
        result = self.manager.refresh_tailnet()
        self.assertEqual(result['updated'], ['demo'])
        self.assertFalse(pending.exists())
        self.assertEqual(self.store.load('demo'), old)
        self.assertNotIn('konsol-demo.service', self.runner.active)
        self.assertIn('PublishPort=100.64.0.9:18080:80/tcp', self.manager.quadlet('demo').read_text())
        self.assertFalse(any(c[:2] == ['systemctl', 'start'] for c in self.runner.calls[before:]))
        before = len(self.runner.calls)
        result = self.manager.refresh_tailnet()
        self.assertEqual(result['updated'], [])
        self.assertEqual(self.runner.calls[before:], [])

    def test_tailnet_refresh_running_target_and_newer_pending_event_is_preserved(self):
        self.config['ports'] = [{'scope': 'tailscale', 'host_port': 18080, 'container_port': 80,
                                 'protocol': 'tcp', 'public_ack': False}]
        old = self.create(start=True)
        pending = self.root / 'run/containers-tailnet.pending'
        pending.write_text('100.64.0.9\n\n')
        self.manager.network.tail_ip = '100.64.0.9'
        with patch.object(self.manager.network, 'apply', side_effect=lambda *a, **kw: pending.write_text('100.64.0.10\n\n')):
            result = self.manager.refresh_tailnet()
        self.assertTrue(result['ok'])
        self.assertEqual(pending.read_text(), '100.64.0.10\n\n')
        self.assertEqual(self.store.load('demo'), old)
        self.assertIn('konsol-demo.service', self.runner.active)

    def test_tailnet_refresh_failure_retains_pending_event(self):
        self.config['ports'] = [{'scope': 'tailscale', 'host_port': 18080, 'container_port': 80,
                                 'protocol': 'tcp', 'public_ack': False}]
        self.create()
        pending = self.root / 'run/containers-tailnet.pending'
        pending.write_text('100.64.0.9\n\n')
        with patch.object(self.manager.network, 'bindings', side_effect=ValueError('unavailable')):
            result = self.manager.refresh_tailnet()
        self.assertFalse(result['ok'])
        self.assertEqual(result['errors'][0]['name'], 'demo')
        self.assertTrue(pending.exists())

    def test_named_volume_cannot_bypass_bind_policy_with_driver_options(self):
        self.config['mounts'] = [{'type': 'volume', 'source': 'foreign-volume', 'destination': '/data', 'read_only': False}]
        self.runner.volume_options = {'type': 'none', 'o': 'bind', 'device': '/etc'}
        with self.assertRaises(cfg.ContainerConfigError):
            self.create()
        self.assertIsNone(self.store.load('demo'))
        self.assertFalse(any(c[:2] == ['systemctl', 'start'] for c in self.runner.calls))

    def test_unsafe_definition_file_is_a_structured_failure(self):
        d = self.create()
        path = self.store.path('demo')
        path.unlink()
        path.symlink_to(self.state)
        with self.assertRaises(cfg.ContainerConfigError) as caught:
            self.store.list()
        self.assertEqual(caught.exception.status, 503)

    def test_explicit_network_subnet_cannot_shadow_host_or_vpn_routes(self):
        self.runner.routes = [{'dst': 'default', 'gateway': '192.168.1.1'}, {'dst': '10.42.0.0/24', 'dev': 'wg0'}]
        for subnet in ('10.42.0.0/24', '169.254.0.0/16', '0.0.0.0/16'):
            with self.subTest(subnet=subnet), self.assertRaises(cfg.ContainerConfigError):
                self.execute('network-create', {'name': 'custom', 'subnet': subnet})
        self.assertFalse(any(c[:3] == ['podman', 'network', 'create'] for c in self.runner.calls))
        self.execute('network-create', {'name': 'custom', 'subnet': '172.29.1.0/24'})
        self.assertTrue(any(c[:3] == ['podman', 'network', 'create'] for c in self.runner.calls))


if __name__ == '__main__':
    unittest.main()
