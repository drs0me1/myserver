"""Container manager public read/write contract; no host/container mutations."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

PANEL = Path(__file__).resolve().parents[1] / 'panel'
sys.path.insert(0, str(PANEL))
import master_container_config as config
try:
    import master_container_manager as manager
except ImportError:
    manager = None


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(manager, 'The public container manager is not implemented')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.env = {'KONTEYNER_STATE_DIR': str(self.root / 'containers'), 'MODULES_FILE': str(self.root / 'modules'),
                    'MODULES_DIR': str(self.root / 'packages'), 'RUNTIME_DIR': str(self.root / 'run'),
                    'KONTEYNER_NETWORK': 'konsol', 'TAILSCALE_IPV4': '100.64.0.2'}
        (self.root / 'modules').write_text('')
        (self.root / 'state').write_text(''.join(k+'='+v+'\n' for k,v in self.env.items()))
        self.rows = []
        self.fail_commands = set()
        self.calls = []
        self.p = types.SimpleNamespace(args=types.SimpleNamespace(state=str(self.root / 'state'), master_modul='/fixture/master-modul'),
                                       run_tool=self.fake_run, env=lambda:{}, module_busy=lambda _:False)
        self.s = manager.Service(self.p)

    def fake_run(self, argv, timeout=30, binary=False):
        self.calls.append(argv)
        key = tuple(argv[:2])
        if key in self.fail_commands:
            return 1, '', 'fixture unavailable'
        if argv[:2] == ['podman','version']:
            return 0,'5.4.2',''
        if argv[:2] == ['podman','ps']:
            return 0,json.dumps(self.rows),''
        if argv[:2] == ['podman','inspect']:
            return 1,'','no such container'
        if argv[:2] == ['podman','volume']:
            return 0,'[]',''
        if argv[:2] == ['podman','network']:
            return 0,'[]',''
        if argv[:2] in (['podman','images'], ['podman','system'], ['podman','stats']):
            return 0,'[]',''
        if argv[0] == 'journalctl':
            return 0,'token=secret\nclean log\n',''
        raise AssertionError(argv)

    def save(self):
        value = {'schema':1,'name':'web','revision':'a'*32,'image':'docker.io/library/nginx@sha256:'+'b'*64,
                 'image_ref':'docker.io/library/nginx:alpine','network':'konsol','ports':[],
                 'mounts':[{'type':'volume','source':'web-data','destination':'/data','read_only':False}],
                 'environment':[{'name':'API_TOKEN','value':'secret-token','secret':True}],
                 'command':[],'autostart':True,'manual_stop':True,'restart':'on-failure','cpus':'','memory':''}
        config.Store(self.env).save(value)
        return value

    def test_stopped_definition_remains_visible_and_secret_never_leaves_read_view(self):
        self.save()
        answer = self.s.view().liste()
        self.assertEqual([c['name'] for c in answer['containers']], ['web'])
        row = answer['containers'][0]
        self.assertEqual((row['source'],row['state'],row['live']), ('konsol','stopped',False))
        self.assertEqual(row['management_id'], 'konsol:web')
        self.assertIn('start',row['actions'])
        detail = self.s.view().ayrinti('web')
        self.assertFalse(detail['effective_autostart'])
        self.assertEqual(detail['config']['environment'],[{'name':'API_TOKEN','secret':True,'present':True}])
        self.assertNotIn('secret-token',json.dumps(detail))

    def test_unknown_systemd_owner_does_not_receive_destructive_controls(self):
        self.rows = [{'Id':'abc','Names':['external'],'Image':'image','State':'running','Labels':{'PODMAN_SYSTEMD_UNIT':'foreign.service'}}]
        row = self.s.view().liste()['containers'][0]
        self.assertEqual(row['source'],'external')
        self.assertEqual(row['actions'],[])
        self.assertTrue(row['restricted_reason'])

    def test_resource_read_failure_is_explicit_and_saved_definition_survives(self):
        self.save()
        self.fail_commands.add(('podman','volume'))
        answer = self.s.view().liste()
        self.assertTrue(answer['resource_errors']['volumes'])
        self.assertEqual(answer['containers'][0]['name'],'web')

    def test_missing_live_container_uses_managed_journal_and_masks_it(self):
        self.save()
        log = self.s.view().gunluk('web',200)
        self.assertEqual(log['lines'],['token=••••','clean log'])
        self.assertIn(['journalctl','-u','konsol-web.service','-n','200','--no-pager','-o','short-iso'],self.calls)

    def test_unknown_action_and_stale_save_never_launch_worker(self):
        self.save()
        with patch.object(self.s, '_launch') as launch:
            for data in ({'action':'exec','name':'web'}, {'action':'save','name':'web','revision':'b'*32,'config':{}}):
                with self.assertRaises(manager.ContainerError):
                    self.s.submit(data)
            launch.assert_not_called()

    def test_async_acceptance_is_not_reported_as_success_and_duplicate_is_busy(self):
        self.save()
        with patch.object(self.s,'_launch') as launch:
            result = self.s.submit({'action':'start','name':'web','revision':'a'*32})
            self.assertEqual(result['state'],'running')
            self.assertEqual(self.s.operation(result['id'])['state'],'running')
            with self.assertRaises(manager.ContainerError) as e:
                self.s.submit({'action':'start','name':'web','revision':'a'*32})
            self.assertEqual(e.exception.status,409)
            launch.assert_called_once()

    def test_podman_json_stats_use_lowercase_fields_and_decimal_memory_units(self):
        self.rows=[{'Id':'abc','Names':['web'],'Image':'image','State':'running','Labels':{}}]
        original=self.fake_run
        def run(argv,**kw):
            if argv[:2]==['podman','stats']:
                return 0,json.dumps([{'name':'web','cpu_percent':'0.00%','mem_usage':'3.092MB / 16.7GB'}]),''
            return original(argv,**kw)
        self.p.run_tool=run
        row=self.s.view().liste()['containers'][0]
        self.assertEqual(row['cpu_percent'],0.0)
        self.assertEqual(row['memory_bytes'],3092000)

    def test_job_lookup_rejects_paths_and_returns_durable_completed_result(self):
        directory=Path(self.env['KONTEYNER_STATE_DIR'])/'operations';directory.mkdir(parents=True)
        value={'id':'c'*32,'action':'start','name':'web','state':'done','step':'Tamamlandı','updated_at':1}
        path=directory/('c'*32+'.json');path.write_text(json.dumps(value));path.chmod(0o600)
        self.assertEqual(self.s.operation('c'*32),value)
        with self.assertRaises(manager.ContainerError):self.s.operation('../state')

    def test_real_image_json_links_stopped_definition_by_digest(self):
        definition=self.save()
        original=self.fake_run
        def run(argv,**kw):
            if argv[:2]==['podman','images']:
                return 0,json.dumps([{'id':'c'*64,'names':['docker.io/library/nginx:alpine'],
                    'digest':'sha256:'+'b'*64,'created':'2026-10-03T09:00:00Z','size':12345}]),''
            return original(argv,**kw)
        self.p.run_tool=run
        row=self.s.view().liste()['images'][0]
        self.assertEqual((row['id'],row['name'],row['size']),('c'*64,'docker.io/library/nginx:alpine',12345))
        self.assertEqual(row['used_by'],[definition['name']])

    def test_absent_package_runtime_detail_has_mount_array(self):
        app={'name':'example','image':'docker.io/library/nginx:alpine','unit':'example.service',
             'module_id':'example','module_state':'durduruldu','adapter':'adapter.py'}
        with patch.object(manager,'app_specs',return_value={'example':app}), \
             patch.object(manager,'app_config',return_value={'revision':'d'*64,'config':{'listener_port':8080},
                          'editable':['listener_port'],'protected_mounts':[]}):
            row=self.s.view().ayrinti('example')
        self.assertEqual(row['mounts'],[])
        self.assertEqual(row['state'],'stopped')

    def test_image_delete_normalizes_real_podman_id_for_worker(self):
        with patch.object(self.s,'_launch') as launch:
            self.s.submit({'action':'image-remove','image':'c'*64})
        self.assertEqual(launch.call_args.args[2]['image'],'sha256:'+'c'*64)



class RouteTests(unittest.TestCase):
    def test_real_handler_requires_gates_and_returns_operation_identity(self):
        from test_resources import panel, start_unix, unix_get
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        root=Path(tmp.name).resolve();(root/'modules').write_text('')
        (root/'state').write_text(f'SERVER_ROOT={root}\nLOCAL_DOMAIN=test\nMODULES_FILE={root}/modules\nKONTEYNER_STATE_DIR={root}/containers\n')
        p=panel.Panel(types.SimpleNamespace(state=str(root/'state'),allow_host=[],master_modul='/fixture/master-modul'))
        class Handler(panel.Handler):
            def log_message(self,*_):pass
        Handler.panel=p
        _server,sock=start_unix(self,Handler)
        body=json.dumps({'action':'create','config':{'name':'web','image':'docker.io/library/nginx:alpine'}}).encode()
        headers={'X-Konsol':'1','Content-Type':'application/json'}
        with patch.object(manager.Service,'_launch'):
            self.assertEqual(unix_get(sock,'/api/konsol/konteynerler/islem',{'Content-Type':'application/json'},'POST',body)[0],403)
            self.assertEqual(unix_get(sock,'/api/konsol/konteynerler/islem',dict(headers,Host='evil.test'),'POST',body)[0],403)
            code,_,raw=unix_get(sock,'/api/konsol/konteynerler/islem',headers,'POST',body)
            self.assertEqual(code,202,raw)
            job=json.loads(raw)
            code,_,raw=unix_get(sock,'/api/konsol/konteynerler/islem?id='+job['id'],headers)
            self.assertEqual((code,json.loads(raw)['state']),(200,'running'))

class PublicationIntegrationTests(unittest.TestCase):
    def test_declared_port_key_updates_both_catalogue_and_private_proxy(self):
        import master_publications as pubs
        manifest={'PAKET_YAYIN':'1','PAKET_YAYIN_AD':'Example','PAKET_YAYIN_YEREL':'example',
                  'PAKET_YAYIN_UPSTREAM':'127.0.0.1:61006','PAKET_YAYIN_PORT_ANAHTARI':'EXAMPLE_PORT'}
        with patch.object(pubs,'read_manifests',return_value={'example':manifest}), \
             patch.object(pubs,'package_env',return_value={'EXAMPLE_PORT':'61016'},create=True), \
             patch.object(pubs,'config',return_value={'example':{'tail':True}}):
            self.assertEqual(pubs.packages({})['example']['upstream'],'127.0.0.1:61016')
            source='http://example.test {\n reverse_proxy 127.0.0.1:61006 {\n }\n}\n'
            self.assertIn('reverse_proxy 127.0.0.1:61016',pubs.private_site({},'example',source))
            self.assertNotIn(':61006',pubs.private_site({},'example',source))

if __name__ == '__main__':unittest.main()
