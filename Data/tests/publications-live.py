"""Opt-in nrm/publication acceptance. Restores effective network choices.

Runs real Settings writes and module reapply; transfers/services can interrupt.
Never changes app credentials or enables a new public hostname. Works with a
private or an already public qBittorrent; the operator's names are read from
the host, never written here.
"""
import argparse
import hashlib
import http.client
import json
import secrets
import shlex
import subprocess
import time

import konsol_session

parser = argparse.ArgumentParser()
parser.add_argument("--host", required=True)
args = parser.parse_args()
ssh = ["ssh", "-o", "ClearAllForwardings=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", args.host]
boot = "import json,sys,pathlib,hashlib; sys.path.insert(0,'/usr/local/sbin'); import master_settings as settings; e=settings.env_read('/etc/master-stack/state.env'); "


def remote(code):
    proc = subprocess.run(ssh + ["python3 -c " + shlex.quote(boot + code)], capture_output=True, text=True, timeout=90)
    if proc.returncode:
        raise RuntimeError("Remote test step failed; private output withheld")
    return json.loads(proc.stdout)


meta = remote("print(json.dumps({k:e[k] for k in ('TAILSCALE_IPV4','LOCAL_DOMAIN','CADDY_HTTP_PORT','SHARE_PORT','SHARE_HTTPS_PORT')}))")


# DD-194: Konsol through Caddy needs a session; a short root-issued one, closed at the end.
COOKIE = konsol_session.open_session(ssh)


def request(path, data=None, host=None, port=None):
    conn = http.client.HTTPConnection(meta["TAILSCALE_IPV4"], port or int(meta["CADDY_HTTP_PORT"]), timeout=145)
    try:
        conn.request("POST" if data is not None else "GET", path,
                     json.dumps(data) if data is not None else None,
                     {"Host": host or "panel." + meta["LOCAL_DOMAIN"], "X-Konsol": "1", "Content-Type": "application/json",
                      **({} if host else {"Cookie": COOKIE})})
        response = conn.getresponse()
        return response.status, response.read()
    finally:
        conn.close()


def status():
    code, body = request("/api/konsol/ayarlar/durum")
    assert code == 200, code
    return json.loads(body)


def save(row, **updates):
    item = {k: row[k] for k in ("service", "tail", "enabled", "domain")}
    item.update(updates)
    for attempt in range(10):
        code, body = request("/api/konsol/ayarlar/uygula", {"revision": status()["revision"], "web": item})
        # The share/settings guard timers hold the operation locks briefly; retry only that answer.
        if code == 400 and "sürüyor" in body.decode(errors="replace") and attempt < 9:
            time.sleep(3)
            continue
        break
    assert code == 200, (code, body.decode()[:300])
    assert json.loads(body) == {"committed": True, "pending": None}


before = status()
rows = {r["service"]: r for r in before["publications"]}
# DD-195: Panel may be public, but its tailnet address never closes; this test never changes it.
assert rows["panel"]["tail"] and rows["panel"]["status"] in ("disabled", "ready", "error")
panel_before = {k: rows["panel"][k] for k in ("tail", "enabled", "domain")}
assert rows["paylasim"]["enabled"] and rows["paylasim"]["status"] == "ready", "Requires existing verified DAV HTTPS"
assert rows["torrent"]["installed"], "Requires installed qBittorrent"
torrent_public = rows["torrent"]["enabled"]
# Names come from the host. example.net is reserved and never resolves below its apex.
probe_name = rows["torrent"]["domain"] or rows["paylasim"]["domain"]
digest = remote("print(json.dumps(hashlib.sha256(pathlib.Path(e['SHARE_STATE_FILE']).read_bytes()).hexdigest()))")
try:
    # Each refusal names its real cause (DD-195: the typed word and the account come before DNS).
    missing = "panel-" + secrets.token_hex(5) + ".example.net"
    for item, expected in ((dict(service="panel", tail=False, enabled=False, domain=""), "Tailscale erişimi kapatılamaz"),
                           (dict(service="panel", tail=True, enabled=True, domain=missing), "onayla yazın"),
                           (dict(service="panel", tail=True, enabled=True, domain=missing, confirm="onayla"),
                            "DNS" if rows["panel"]["account"] else "Konsol hesabını"),
                           (dict(service="torrent", tail=True, enabled=True, domain=rows["paylasim"]["domain"]), "aynı HTTPS alan adını"),
                           (dict(service="paylasim", tail=True, enabled=True, domain="missing-" + secrets.token_hex(5) + ".example.net"), "DNS")):
        code, body = request("/api/konsol/ayarlar/uygula", {"revision": status()["revision"], "web": item})
        assert code == 400 and expected in json.loads(body)["error"], (code, body.decode()[:200])
        assert status()["pending"] is None
    print("PASS: Panel tailnet-off/word/account-or-DNS, duplicate domain and DAV missing DNS rejected with their real causes", flush=True)
    result = remote("import master_publications as pubs; pubs.security_check(e,'torrent',%s,probe=True); print(json.dumps(True))" % json.dumps(probe_name))
    assert result is True
    print("PASS: native qBittorrent permanent-auth checks and anonymous API refusal", flush=True)
    # Every address of the module template must answer 403 when Tailscale is off (DD-193).
    for service, targets in (("torrent", [("torrent." + meta["LOCAL_DOMAIN"], None)]),
                             ("paylasim", [(meta["TAILSCALE_IPV4"], int(meta["SHARE_PORT"])),
                                           ("paylas." + meta["LOCAL_DOMAIN"], None)])):
        save(rows[service], tail=False)
        assert all(request("/", host=h, port=p)[0] == 403 for h, p in targets)
        # Real lifecycle consumes the choice, not the original always-on template.
        command = "master-modul uygula torrent" if service == "torrent" else "master-modul yerlesik"
        proc = subprocess.run(ssh + [command], capture_output=True, timeout=90)
        assert proc.returncode == 0, "Module reapply failed (private output withheld)"
        assert all(request("/", host=h, port=p)[0] == 403 for h, p in targets)
        assert status()["publications"][0]["tail"] is True
        if service == "paylasim":
            conn = http.client.HTTPSConnection(rows[service]["domain"], int(meta["SHARE_HTTPS_PORT"]), timeout=15)
            try:
                conn.request("GET", "/s/" + "a"*24 + "/")
                response = conn.getresponse(); response.read()
                assert response.status == 401, response.status
            finally:
                conn.close()
        save(rows[service])
        assert all(request("/", host=h, port=p)[0] == (200 if service == "torrent" else 401) for h, p in targets)
        print("PASS: %s private off/403, real module reapply, on/restore; Panel preserved" % service, flush=True)
    save(rows["paylasim"], enabled=False)
    current = next(r for r in status()["publications"] if r["service"] == "paylasim")
    assert not current["enabled"] and current["domain"] == rows["paylasim"]["domain"]
    assert request("/", host=meta["TAILSCALE_IPV4"], port=int(meta["SHARE_PORT"]))[0] == 401
    saved = remote("import master_publications as pubs; print(json.dumps([pubs.extra_sites(e).get('torrent-wan.caddy')!='', (pathlib.Path(e['CADDY_MODULES_DIR'])/'paylasim-wan.caddy').exists()]))")
    assert saved == [torrent_public, False], saved
    if torrent_public:
        # A public qBittorrent keeps its own HTTPS site on the shared port.
        conn = http.client.HTTPSConnection(rows["torrent"]["domain"], int(meta["SHARE_HTTPS_PORT"]), timeout=15)
        try:
            conn.request("GET", "/")
            response = conn.getresponse(); response.read()
            assert response.status == 200, response.status
        finally:
            conn.close()
    print("PASS: public DAV off remembers domain, removes only its WAN site and preserves private DAV", flush=True)
finally:
    # Restore every row even if one fails, so the operator's choices never stay changed.
    failures = []
    for service in ("torrent", "paylasim"):
        try:
            save(rows[service])
        except AssertionError as err:
            failures.append((service, str(err)[:200]))
    assert not failures, failures
    assert status()["pending"] is None
    after = {r["service"]: r for r in status()["publications"]}["panel"]
    assert {k: after[k] for k in ("tail", "enabled", "domain")} == panel_before, "Panel row changed"
    assert remote("print(json.dumps(hashlib.sha256(pathlib.Path(e['SHARE_STATE_FILE']).read_bytes()).hexdigest()))") == digest
    konsol_session.close_session(ssh, COOKIE)
    print("CLEANUP: original effective network choices restored; folder accounts unchanged", flush=True)
