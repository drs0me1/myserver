"""Opt-in DD-192 acceptance against an authorized disposable HTTPS host.

Creates one private test folder/account, never changes operator shares or Caddy
settings. Share saves restart WebDAV and may interrupt playback. Credentials
stay in memory/SSH stdin. Run with no concurrent operator share edits.
"""
import argparse
import base64
import http.client
import json
import secrets
import shlex
import subprocess

import konsol_session

parser = argparse.ArgumentParser()
parser.add_argument("--host", required=True)
args = parser.parse_args()
ssh = ["ssh", "-o", "ClearAllForwardings=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", args.host]
boot = """import json,sys,os,pathlib,hashlib
sys.path.insert(0,'/usr/local/sbin')
import master_shares as shares
m=shares.Manager('/etc/master-stack/state.env'); e=m.env; d=json.load(sys.stdin)
"""


def remote(code, data=None):
    result = subprocess.run(ssh + ["python3 -c " + shlex.quote(boot + code)],
                            input=json.dumps(data), text=True, capture_output=True, timeout=90)
    if result.returncode:
        raise RuntimeError("Remote fixture failed; private output withheld")
    return json.loads(result.stdout)


meta = remote("""
p=m.public(); w=p['wan']; assert w['available'] and w['mode']=='https' and p['tail_enabled']
assert m.read()['schema']==4
print(json.dumps({'tail':e['TAILSCALE_IPV4'],'port':int(e['SHARE_PORT']),
 'panel_port':int(e['CADDY_HTTP_PORT']),'host':'panel.'+e['LOCAL_DOMAIN'],
 'domain':w['domain'],'https_port':w['port'],
 'digest':hashlib.sha256(pathlib.Path(m.path).read_bytes()).hexdigest()}))
""")


# DD-194: Konsol through Caddy needs a session; a short root-issued one, closed at the end.
COOKIE = konsol_session.open_session(ssh)


def api(data=None, action="kaydet", expected=200):
    conn = http.client.HTTPConnection(meta["tail"], meta["panel_port"], timeout=160)
    try:
        headers = {"Host": meta["host"], "X-Konsol": "1", "Content-Type": "application/json", "Cookie": COOKIE}
        conn.request("GET" if data is None else "POST", "/api/konsol/paylasim" + ("/" + action if data is not None else ""),
                     json.dumps(data) if data is not None else None, headers)
        response = conn.getresponse()
        body = json.loads(response.read())
        assert response.status == expected, (response.status, body.get("error", "Unexpected API response"))
        return body
    finally:
        conn.close()


name = "connections-test-" + secrets.token_hex(5)
password = secrets.token_hex(20)
authorization = "Basic " + base64.b64encode((name + ":" + password).encode()).decode()
item = None


def dav(scope, method="GET", suffix="hello.txt", body=None, headers=None, expected=200):
    conn = (http.client.HTTPConnection(meta["tail"], meta["port"], timeout=30) if scope == "tailscale" else
            http.client.HTTPSConnection(meta["domain"], meta["https_port"], timeout=30))
    try:
        conn.request(method, "/s/" + item["id"] + "/" + suffix, body,
                     {"Authorization": authorization, **(headers or {})})
        response = conn.getresponse()
        value = response.read()
        assert response.status == expected, (scope, method, response.status, expected)
        return value
    finally:
        conn.close()


def patch(scope, values):
    global item
    result = api({"id": item["id"], "connections": {scope: values}})
    item = next(i for i in result["items"] if i["id"] == item["id"])


try:
    remote("""
root=pathlib.Path(e['SERVER_ROOT'])/d['name']
assert root.parent==pathlib.Path(e['SERVER_ROOT']) and root.name.startswith('connections-test-') and not root.exists()
root.mkdir(mode=0o775); os.chown(root,int(e['DOWNLOADS_UID']),int(e['DOWNLOADS_GID']))
(root/'hello.txt').write_bytes(b'abcdefghij')
print(json.dumps({'created':True}))
""", {"name": name})
    result = api({"path": name, "username": name, "password": password, "connections": {
        "tailscale": {"enabled": True, "permission": "rw", "days": 0, "ack_write": True},
        "wan": {"enabled": True, "permission": "ro", "days": 7}}})
    item = next(i for i in result["items"] if i["path"] == name)
    wan_expiry = item["connections"]["wan"]["expires"]
    assert item["connections"]["tailscale"]["expires"] is None
    for scope in ("tailscale", "wan"):
        assert dav(scope) == b"abcdefghij"
        dav(scope, "PROPFIND", "", headers={"Depth": "1"}, expected=207)
        assert dav(scope, headers={"Range": "bytes=2-4"}, expected=206) == b"cde"
    dav("wan", "PUT", "denied.txt", b"no", expected=403)
    dav("wan", "PUT", "spoofed.txt", b"no", headers={"X-Share-Scope": "tailscale", "X-Share-Client-IP": meta["tail"]}, expected=403)
    dav("tailscale", "PUT", "tail.txt", b"tail-write", expected=201)
    assert dav("wan", suffix="tail.txt") == b"tail-write"
    print("PASS: trusted HTTPS and Tailscale listing/ranges; same account, independent RO/RW", flush=True)

    patch("tailscale", {"days": 1})
    tail_expiry = item["connections"]["tailscale"]["expires"]
    assert item["connections"]["wan"]["expires"] == wan_expiry
    patch("wan", {"enabled": False})
    dav("wan", expected=403)
    dav("tailscale")
    patch("wan", {"enabled": True})
    assert item["connections"]["wan"]["expires"] == wan_expiry
    patch("tailscale", {"enabled": False})
    dav("tailscale", expected=403)
    dav("wan")
    patch("wan", {"enabled": False})
    assert not item["urls"]
    for scope in ("tailscale", "wan"):
        dav(scope, expected=403)
    patch("wan", {"enabled": True, "permission": "rw", "ack_write": True, "days": 0})
    dav("wan", "PUT", "wan.txt", b"wan-write", expected=201)
    patch("tailscale", {"enabled": True, "permission": "ro"})
    assert item["connections"]["tailscale"]["expires"] == tail_expiry
    assert item["connections"]["wan"]["expires"] is None
    dav("tailscale", "PUT", "denied-tail.txt", b"no", expected=403)
    assert dav("tailscale", suffix="wan.txt") == b"wan-write"
    print("PASS: both independent switches, both off, reversed permissions, unchanged peer expiry", flush=True)

    # Accelerate only our fixture's WAN expiry under the same lock ordering.
    remote("""
import contextlib,fcntl,time
with contextlib.ExitStack() as stack:
 for key in ('install.lock','modul.lock','paylasim.lock'):
  f=stack.enter_context(open(os.path.join(e['RUNTIME_DIR'],key),'a')); fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
 cfg=m.read(); row=next(i for i in cfg['items'] if i['id']==d['id'])
 assert row['path']==d['name'] and row['username']==d['name'] and row['path'].startswith('connections-test-')
 row['connections']['wan']['expires']=int(time.time())-1
 shares.atomic(m.path,cfg); m.restart(); m.publish()
print(json.dumps({'expired':True}))
""", {"id": item["id"], "name": name})
    dav("wan", expected=403)
    dav("tailscale")
    current = next(i for i in api()["items"] if i["id"] == item["id"])
    assert current["connections"]["wan"]["expired"] and not current["connections"]["wan"]["active"]
    assert current["connections"]["tailscale"]["active"]
    api({"id": item["id"], "permission": "rw", "days": 0}, expected=400)
    api({"id": item["id"], "paused": True}, action="durum", expected=400)
    print("PASS: WAN expiry leaves Tailscale active; stale global-policy API rejected", flush=True)
finally:
    for own in api()["items"]:
        if own["path"] == name and own["username"] == name:
            api({"id": own["id"]}, action="kaldir")
    remote("""
import shutil
root=pathlib.Path(e['SERVER_ROOT'])/d['name']
assert root.parent==pathlib.Path(e['SERVER_ROOT']) and root.name.startswith('connections-test-') and not root.is_symlink()
assert not any(i['path']==root.name for i in m.read()['items'])
if root.exists(): shutil.rmtree(root)
assert hashlib.sha256(pathlib.Path(m.path).read_bytes()).hexdigest()==d['digest']
print(json.dumps({'clean':True}))
""", {"name": name, "digest": meta["digest"]})
    konsol_session.close_session(ssh, COOKIE)
    print("CLEANUP: own account/files removed; operator registry byte-identical", flush=True)
