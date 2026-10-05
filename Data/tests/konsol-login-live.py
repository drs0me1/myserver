#!/usr/bin/env python3
"""Opt-in DD-205 sign-in acceptance from a tailnet client against an authorized test host.

Requires a host WITHOUT a Konsol account; otherwise it exits 3 and touches nothing. From this
Mac (a Tailscale device) it checks that Konsol, Files and the root API open without any
sign-in and that the sign-in page goes back to Konsol, creates a temporary internet account
through the real Caddy path (no code, no session), changes its password from the tailnet
without the current one, signs in and out with it, checks the attempt limit, then resets: no
account remains. Passwords and tokens stay in memory. The internet address itself needs a
public name and is covered by panel-public-live.py.

Run on the operator Mac: python3 Data/tests/konsol-login-live.py --host nrm
"""
import argparse
import http.client
import json
import secrets
import shlex
import subprocess
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--host", required=True)
args = parser.parse_args()
ssh = ["ssh", "-o", "ClearAllForwardings=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", args.host]
CLI = "sudo -n /usr/local/sbin/master-konsol "


def run(command):
    result = subprocess.run(ssh + [command], capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise RuntimeError("Remote step failed (output withheld)")
    return result.stdout


if run(CLI + "durum").startswith("Konsol hesabı:"):
    print("SKIP: this host already has a Konsol account; the test never touches it.", file=sys.stderr)
    sys.exit(3)
meta = json.loads(run("sudo -n python3 -c " + shlex.quote(
    "import sys,json; sys.path.insert(0,'/usr/local/sbin'); from master_shares import env_read; "
    "e=env_read('/etc/master-stack/state.env'); "
    "print(json.dumps({'tail':e['TAILSCALE_IPV4'],'domain':e['LOCAL_DOMAIN'],'port':int(e['CADDY_HTTP_PORT'])}))")))


def call(method, path, body=None, cookie=None, api=True):
    conn = http.client.HTTPConnection(meta["tail"], meta["port"], timeout=30)
    headers = {"Host": "panel." + meta["domain"]}
    if api:
        headers["X-Konsol"] = "1"
    if cookie:
        headers["Cookie"] = cookie
    if body is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(body)
    try:
        conn.request(method, path, body, headers)
        response = conn.getresponse()
        return response.status, {k.lower(): v for k, v in response.getheaders()}, response.read()
    finally:
        conn.close()


user = "test-" + secrets.token_hex(4)
password, changed = secrets.token_urlsafe(18), secrets.token_urlsafe(18)
try:
    # Tailnet: no session anywhere; the sign-in page goes back to Konsol.
    for page in ("/", "/index.html", "/konsol.js"):
        status, _, body = call("GET", page, api=False)
        assert status == 200, (page, status)
    status, headers, _ = call("GET", "/giris.html", api=False)
    assert (status, headers.get("location")) == (302, "/"), (status, headers.get("location"))
    for api in ("/api/konsol/kaynaklar", "/api/state"):
        assert call("GET", api)[0] == 200, api
    assert json.loads(call("GET", "/api/konsol/oturum")[2]) == {"durum": "kurulum", "kanal": "tailscale"}
    print("PASS: a Tailscale device opens Konsol, Files and the root API without a sign-in; /giris.html goes back", flush=True)

    status, headers, body = call("POST", "/api/konsol/oturum/kur", {"kullanici": user, "parola": password})
    assert status == 200 and json.loads(body) == {"durum": "kuruldu"} and "set-cookie" not in headers, status
    assert call("POST", "/api/konsol/oturum/kur", {"kullanici": user, "parola": password})[0] == 409
    assert json.loads(call("GET", "/api/konsol/oturum")[2]) == {"durum": "giris", "kullanici": user, "kanal": "tailscale"}
    assert run(CLI + "durum").startswith("Konsol hesabı: " + user)
    print("PASS: the internet account is created from the tailnet without a code or session", flush=True)

    status, headers, _ = call("POST", "/api/konsol/oturum/giris", {"kullanici": user, "parola": password})
    assert status == 200
    attributes = [part.strip() for part in headers["set-cookie"].split(";")]
    assert attributes[1:] == ["Path=/", "HttpOnly", "SameSite=Strict", "Max-Age=604800"], attributes[1:]
    first = attributes[0]
    assert json.loads(call("GET", "/api/konsol/oturum", cookie=first)[2])["durum"] == "acik"
    # Tailnet password change: no current password, no session; every session ends.
    assert call("POST", "/api/konsol/hesap/parola", {"yeni": "short"})[0] == 400
    assert call("POST", "/api/konsol/hesap/parola", {"yeni": changed})[0] == 200
    assert json.loads(call("GET", "/api/konsol/oturum", cookie=first)[2])["durum"] == "giris"
    assert call("POST", "/api/konsol/oturum/giris", {"kullanici": user, "parola": password})[0] == 401
    status, headers, _ = call("POST", "/api/konsol/oturum/giris", {"kullanici": user, "parola": changed})
    assert status == 200
    second = headers["set-cookie"].split(";", 1)[0]
    status, headers, _ = call("POST", "/api/konsol/oturum/cikis", {}, cookie=second)
    assert status == 200 and "Max-Age=0" in headers["set-cookie"]
    assert json.loads(call("GET", "/api/konsol/oturum", cookie=second)[2])["durum"] == "giris"
    print("PASS: sign-in with the account, tailnet password change ends sessions, old password refused, sign-out", flush=True)

    # One failure so far (the old password). Five within a minute block this address.
    for _ in range(4):
        assert call("POST", "/api/konsol/oturum/giris", {"kullanici": user, "parola": "wrong-" + changed})[0] == 401
    status, headers, body = call("POST", "/api/konsol/oturum/giris", {"kullanici": user, "parola": changed})
    assert status == 429 and int(headers["retry-after"]) > 0, status
    print("PASS: five failures from one address block sign-in with Retry-After", flush=True)
finally:
    run(CLI + "sifirla")  # removes the test account and its sessions; the internet address stays closed
    # The attempt limit lives in the backend's memory; a restart frees this address.
    run("sudo -n systemctl restart master-panel.service")
    assert run(CLI + "durum").startswith("Konsol hesabı yok")
    print("CLEANUP: test account and sessions removed; the host has no Konsol account again", flush=True)
