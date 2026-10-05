"""Opt-in HTTPS acceptance from a tailnet client; disposable host only.

--configure saves the requested domain through the actual panel API. Only this
test's folders/accounts are removed; the configured HTTPS domain stays saved.
Credentials stay in memory/SSH stdin and are never printed.
"""
import argparse
import base64
import hashlib
import http.client
import json
import secrets
import shlex
import socket
import subprocess
import time
import urllib.parse

import konsol_session

parser = argparse.ArgumentParser()
parser.add_argument("--host", required=True)
parser.add_argument("--domain", required=True)
parser.add_argument("--configure", action="store_true")
args = parser.parse_args()
ssh = ["ssh", "-o", "ClearAllForwardings=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", args.host]
boot = "import json,sys,os,pathlib,hashlib; sys.path.insert(0,'/usr/local/sbin'); import master_shares as shares; m=shares.Manager('/etc/master-stack/state.env'); e=m.env; d=json.load(sys.stdin)\n"


def remote(code, data=None):
    result = subprocess.run(ssh + ["python3 -c " + shlex.quote(boot + code)], input=json.dumps(data),
                            text=True, capture_output=True, timeout=90)
    if result.returncode:
        raise RuntimeError("Remote fixture failed; private output withheld")
    return json.loads(result.stdout)


meta = remote("print(json.dumps({'tail':e['TAILSCALE_IPV4'],'wan':e['WAN_IPV4'],'port':int(e['SHARE_PORT']),'panel_port':int(e['CADDY_HTTP_PORT']),'host':'panel.'+e['LOCAL_DOMAIN'],'digest':hashlib.sha256(pathlib.Path(m.path).read_bytes()).hexdigest()}))")


# DD-194: Konsol through Caddy needs a session; a short root-issued one, closed at the end.
COOKIE = konsol_session.open_session(ssh)


def api(path, data=None):
    conn = http.client.HTTPConnection(meta["tail"], meta["panel_port"], timeout=150)
    try:
        headers = {"Host": meta["host"], "X-Konsol": "1", "Cookie": COOKIE}
        if data is not None:
            headers["Content-Type"] = "application/json"
        conn.request("POST" if data is not None else "GET", path, json.dumps(data) if data is not None else None, headers)
        reply = conn.getresponse()
        body = json.loads(reply.read())
        assert reply.status == 200, (reply.status, body.get("error", "API failed"))
        return body
    finally:
        conn.close()


if args.configure:
    status = api("/api/konsol/ayarlar/durum")
    result = api("/api/konsol/ayarlar/uygula", {"revision": status["revision"], "https": {"domain": args.domain}})
    assert result.get("committed") is True and result.get("pending") is None
    print("PASS: real Settings API saved and verified HTTPS", flush=True)
status = api("/api/konsol/ayarlar/durum")["https"]
assert status["domain"] == args.domain and status["status"] == "ready", status


def request(method, path, item=None, password=None, headers=None, data=None, tail=False):
    conn = (http.client.HTTPConnection(meta["tail"], meta["port"], timeout=30) if tail else
            http.client.HTTPSConnection(args.domain, 443, timeout=30))
    fields = dict(headers or {})
    if item is not None:
        fields["Authorization"] = "Basic " + base64.b64encode((item["username"] + ":" + password).encode()).decode()
    try:
        conn.request(method, path, body=data, headers=fields)
        reply = conn.getresponse()
        return reply.status, reply.read()
    finally:
        conn.close()


assert request("GET", "/")[0] == 404
assert request("GET", "/api/konsol/ayarlar")[0] == 404
assert request("GET", "/api/konsol/ayarlar", headers={"Host": "panel." + meta["host"].split(".", 1)[1], "X-Konsol": "1"})[0] == 421
try:
    with socket.create_connection((meta["wan"], meta["port"]), timeout=3):
        raise AssertionError("Old HTTP WAN socket remains reachable")
except (TimeoutError, ConnectionRefusedError):
    pass
print("PASS: public TLS trust, private routes denied, old HTTP WAN closed", flush=True)

name = "https-test-" + secrets.token_hex(5)
items = []
root_created = False
try:
    fixture = remote("""
root=pathlib.Path(e['SERVER_ROOT'])/d['name']
assert root.parent==pathlib.Path(e['SERVER_ROOT']) and root.name.startswith('https-test-') and not root.exists()
root.mkdir(mode=0o755)
block=b'WebDAV HTTPS acceptance\\n'*45590
for folder in ('reader','writer','tail'):
 p=root/folder; p.mkdir(mode=0o775); os.chown(p,int(e['DOWNLOADS_UID']),int(e['DOWNLOADS_GID']))
 (p/'hello.txt').write_bytes(b'abcdefghij')
big=root/'reader'/'sample.bin'
with big.open('wb') as out:
 for _ in range(32): out.write(block)
print(json.dumps({'sha256':hashlib.sha256(big.read_bytes()).hexdigest(),'size':big.stat().st_size}))
""", {"name": name})
    root_created = True
    for folder in ("reader", "writer", "tail"):
        password = secrets.token_hex(20)
        data = {"path": name + "/" + folder, "username": name + "-" + folder, "password": password,
                "connections": {scope: {"enabled": scope == "tailscale" or folder != "tail",
                                         "permission": "rw" if folder == "writer" else "ro",
                                         "ack_write": True, "days": 1} for scope in ("tailscale", "wan")}}
        public = api("/api/konsol/paylasim/kaydet", data)
        item = next(row for row in public["items"] if row["path"] == data["path"])
        items.append((item, password))
    reader, writer, private = items
    path = "/s/" + reader[0]["id"] + "/"
    assert request("PROPFIND", path, *reader, headers={"Depth": "1"})[0] == 207
    assert request("GET", path + "hello.txt")[0] == 401
    assert request("GET", path + "hello.txt", *reader) == (200, b"abcdefghij")
    assert request("GET", path + "hello.txt", *reader, tail=True) == (200, b"abcdefghij")
    assert request("GET", path + "hello.txt", *reader, headers={"Range": "bytes=2-4"}) == (206, b"cde")
    assert request("PUT", path + "new.txt", *reader, data=b"forbidden")[0] == 403
    assert request("GET", "/s/" + private[0]["id"] + "/hello.txt", *private)[0] == 403
    start = time.monotonic()
    code, body = request("GET", path + "sample.bin", *reader)
    elapsed = time.monotonic() - start
    assert code == 200 and len(body) == fixture["size"] and hashlib.sha256(body).hexdigest() == fixture["sha256"]
    print("PASS: HTTPS/Tailscale RO, PROPFIND, ranges, WAN scope; download %.2f MB/s" % (len(body) / elapsed / 1e6), flush=True)
    wp = "/s/" + writer[0]["id"] + "/"
    target = wp + urllib.parse.quote("Türkçe.txt")
    assert request("PUT", target, *writer, data=b"tls-write")[0] == 201
    destination = "https://" + args.domain + wp + "moved.txt"
    assert request("MOVE", target, *writer, headers={"Destination": destination})[0] == 201
    assert request("GET", wp + "moved.txt", *writer) == (200, b"tls-write")
    assert request("DELETE", wp + "moved.txt", *writer)[0] == 204
    api("/api/konsol/paylasim/kaydet", {"id": reader[0]["id"], "connections": {
        "tailscale": {"enabled": False}, "wan": {"enabled": False}}})
    assert request("GET", path + "hello.txt", *reader)[0] == 403
    assert request("GET", path + "hello.txt", *reader, tail=True)[0] == 403
    print("PASS: HTTPS writes, absolute MOVE destination, deletion and both connections off", flush=True)
finally:
    for item, _ in reversed(items):
        api("/api/konsol/paylasim/kaldir", {"id": item["id"]})
    konsol_session.close_session(ssh, COOKIE)
    if root_created:
        remote("""
import shutil
root=pathlib.Path(e['SERVER_ROOT'])/d['name']
assert root.parent==pathlib.Path(e['SERVER_ROOT']) and root.name.startswith('https-test-') and not root.is_symlink()
assert not any(i['path'].startswith(root.name+'/') for i in m.read()['items'])
shutil.rmtree(root)
assert hashlib.sha256(pathlib.Path(m.path).read_bytes()).hexdigest()==d['digest']
print(json.dumps({'clean':True}))
""", {"name": name, "digest": meta["digest"]})
        print("CLEANUP: own accounts/files removed; original share registry unchanged", flush=True)
