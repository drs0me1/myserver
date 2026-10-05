#!/usr/bin/env python3
"""Opt-in DD-195 acceptance: Konsol over public HTTPS on an authorized test host.

Requires the operator's existing Konsol account (never changed) and a --domain that
already has a DNS-only A record to the host's WAN IPv4 and no AAAA record. The test
publishes Panel on that name through the real Settings API, checks the public door
from this machine, then restores the Panel row exactly. It uses only a short
root-issued automation session (never a password) and makes one deliberately wrong
sign-in, which counts once against this machine's address. Tokens stay in memory.

Run on the operator Mac: python3 Data/tests/panel-public-live.py --host nrm --domain konsol.example.com
"""
import argparse
import http.client
import json
import shlex
import ssl
import subprocess
import sys
import time

import konsol_session

parser = argparse.ArgumentParser()
parser.add_argument("--host", required=True)
parser.add_argument("--domain", required=True)
args = parser.parse_args()
ssh = ["ssh", "-o", "ClearAllForwardings=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", args.host]
boot = ("import json,sys; sys.path.insert(0,'/usr/local/sbin'); import master_settings as settings; "
        "e=settings.env_read('/etc/master-stack/state.env'); ")


def remote(code, sudo=False):
    command = ("sudo -n " if sudo else "") + "python3 -c " + shlex.quote(boot + code)
    proc = subprocess.run(ssh + [command], capture_output=True, text=True, timeout=90)
    if proc.returncode:
        raise RuntimeError("Remote test step failed; private output withheld")
    return json.loads(proc.stdout)


meta = remote("print(json.dumps({k:e[k] for k in ('TAILSCALE_IPV4','LOCAL_DOMAIN','CADDY_HTTP_PORT','SHARE_HTTPS_PORT')}))")
if not subprocess.run(ssh + ["sudo -n /usr/local/sbin/master-konsol durum"], capture_output=True, text=True,
                      timeout=60).stdout.startswith("Konsol hesabı:"):
    print("SKIP: no Konsol account; the public address needs the operator's account.", file=sys.stderr)
    sys.exit(3)
COOKIE = konsol_session.open_session(ssh)


def tail(path, data=None):
    conn = http.client.HTTPConnection(meta["TAILSCALE_IPV4"], int(meta["CADDY_HTTP_PORT"]), timeout=145)
    try:
        conn.request("POST" if data is not None else "GET", path, json.dumps(data) if data is not None else None,
                     {"Host": "panel." + meta["LOCAL_DOMAIN"], "X-Konsol": "1", "Content-Type": "application/json",
                      "Cookie": COOKIE})
        response = conn.getresponse()
        return response.status, response.read()
    finally:
        conn.close()


def public(path, data=None, cookie=None, api=True):
    port = int(meta["SHARE_HTTPS_PORT"])
    conn = http.client.HTTPSConnection(args.domain, port, timeout=20, context=ssl.create_default_context())
    headers = {"X-Konsol": "1"} if api else {}
    if cookie:
        headers["Cookie"] = cookie
    if data is not None:
        headers["Content-Type"] = "application/json"
    try:
        conn.request("POST" if data is not None else "GET", path, json.dumps(data) if data is not None else None, headers)
        response = conn.getresponse()
        return response.status, {k.lower(): v for k, v in response.getheaders()}, response.read()
    finally:
        conn.close()


def status():
    code, body = tail("/api/konsol/ayarlar/durum")
    assert code == 200, code
    return json.loads(body)


def save(**item):
    item = dict(service="panel", **item)
    for attempt in range(10):
        code, body = tail("/api/konsol/ayarlar/uygula", {"revision": status()["revision"], "web": item})
        if code == 400 and "sürüyor" in body.decode(errors="replace") and attempt < 9:
            time.sleep(3)
            continue
        break
    assert code == 200, (code, body.decode()[:300])
    assert json.loads(body) == {"committed": True, "pending": None}


def panel_row():
    return next(r for r in status()["publications"] if r["service"] == "panel")


before = {k: panel_row()[k] for k in ("tail", "enabled", "domain")}
if before["enabled"]:
    print("SKIP: Panel is already public; the test changes nothing.", file=sys.stderr)
    konsol_session.close_session(ssh, COOKIE)
    sys.exit(3)
try:
    save(tail=True, enabled=True, domain=args.domain, confirm="onayla")
    row = panel_row()
    assert (row["enabled"], row["status"], row["domain"]) == (True, "ready", args.domain), row["status"]
    assert remote("import master_publications as p; print(json.dumps(p.panel_active(e)))", sudo=True) is True
    firewall = subprocess.run(ssh + ["sudo -n python3 /usr/local/sbin/master_shares.py wan-firewall"],
                              capture_output=True, text=True, timeout=60).stdout.split()
    assert firewall[0] == "1" and firewall[3] == meta["SHARE_HTTPS_PORT"], firewall
    print("PASS: Panel published through the real Settings API; certificate verified; firewall opens HTTPS", flush=True)

    status_code, headers, _ = public("/giris.html", api=False)
    assert status_code == 200 and headers.get("strict-transport-security") == "max-age=31536000", status_code
    for page in ("/", "/konsol.js", "/index.html"):
        status_code, headers, _ = public(page, api=False)
        assert (status_code, headers.get("location")) == (302, "/giris.html"), (page, status_code)
    for api in ("/api/konsol/kaynaklar", "/api/state", "/api/uygulama/wireguard/state"):
        status_code, _, body = public(api)
        assert status_code == 401 and json.loads(body)["giris"] is True, (api, status_code)
    assert json.loads(public("/api/konsol/oturum")[2]) == {"durum": "giris", "kanal": "internet"}
    status_code, _, body = public("/api/konsol/oturum/kur", {"kullanici": "x-test", "parola": "x" * 12})
    assert status_code == 403 and "Tailscale" in json.loads(body)["error"], status_code
    status_code, _, _ = public("/api/konsol/oturum/giris", {"kullanici": "x-test-wrong", "parola": "wrong-password-x"})
    assert status_code == 401, status_code
    print("PASS: public sign-in page with HSTS; pages, Files and root APIs need a session; no account creation over the internet", flush=True)

    status_code, _, body = public("/", cookie=COOKIE, api=False)
    assert status_code == 200 and b'id="panel-sidebar"' in body, status_code
    for api in ("/api/konsol/kaynaklar", "/api/state", "/api/konsol/ayarlar/durum"):
        assert public(api, cookie=COOKIE)[0] == 200, api
    assert json.loads(public("/api/konsol/oturum", cookie=COOKIE)[2])["kanal"] == "internet"
    # A request without the session-gated API header is still refused (CSRF gate).
    assert public("/api/konsol/kaynaklar", cookie=COOKIE, api=False)[0] == 403
    print("PASS: a session opens Konsol, Files and root APIs over the public address; CSRF gate unchanged", flush=True)
finally:
    failures = []
    try:
        save(**before)
    except AssertionError as err:
        failures.append(str(err)[:200])
    assert not failures, failures
    after = panel_row()
    assert {k: after[k] for k in ("tail", "enabled", "domain")} == before
    assert remote("import master_publications as p; print(json.dumps(p.panel_active(e)))", sudo=True) is False
    konsol_session.close_session(ssh, COOKIE)
print("CLEANUP: Panel row restored; its public site is gone", flush=True)
# Without the site the name gets no certificate, or Caddy's empty answer; never Konsol.
try:
    reached = b'id="form-login"' in public("/giris.html", api=False)[2]
except (ssl.SSLError, OSError):
    reached = False
assert not reached, "public Konsol still answers after cleanup"
print("PASS: the public name no longer reaches Konsol after cleanup", flush=True)
