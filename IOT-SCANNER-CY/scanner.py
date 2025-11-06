# iot_ids_dashboard.py
# ------------------------------------------------------------
# Real-time IoT Device Vulnerability Scanner + Web Dashboard
# ------------------------------------------------------------

import os
import time
import threading
import ipaddress
from datetime import datetime
import socket
import webbrowser

import nmap
import netifaces
from flask import (
    Flask, render_template_string, jsonify,
    request, redirect, url_for, session
)

# --------------------------- SETTINGS ---------------------------
SCAN_INTERVAL_SEC = 15       # scanner interval
COMMON_PORTS = [21, 22, 23, 80, 443, 554, 8080]
DASH_USER = os.getenv("IOT_IDS_USER", "admin")
DASH_PASS = os.getenv("IOT_IDS_PASS", "admin123")
SECRET_KEY = os.getenv("IOT_IDS_SECRET", "change-me-please")

VULN_HINTS = {
    21:  ("HIGH",   "FTP (21) — plaintext auth; disable or enforce TLS."),
    22:  ("INFO",   "SSH (22) — strong password/keys recommended."),
    23:  ("CRITICAL","Telnet (23) — unencrypted; disable immediately."),
    80:  ("MEDIUM", "HTTP (80) — no TLS; prefer HTTPS."),
    443: ("INFO",   "HTTPS (443) — verify cert/TLS settings."),
    554: ("MEDIUM", "RTSP (554) — ensure stream auth/firmware updated."),
    8080:("MEDIUM", "Alt HTTP (8080) — often admin UI; require auth.")
}

# --------------------------- GLOBAL STATE -----------------------
devices = {}
device_count_history = []
network_cidr = "0.0.0.0/0"
lock = threading.Lock()

# --------------------------- FLASK APP --------------------------
app = Flask(__name__)
app.secret_key = SECRET_KEY

def login_required(f):
    from functools import wraps
    @wraps(f)
    def _wrap(*args, **kwargs):
        if not session.get("authed"):
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return _wrap

# ------------------------ NETWORK HELPERS -----------------------
def get_local_network() -> str:
    try:
        gws = netifaces.gateways()
        if 'default' not in gws or netifaces.AF_INET not in gws['default']:
            return "192.168.1.0/24"
        iface = gws['default'][netifaces.AF_INET][1]
        addrs = netifaces.ifaddresses(iface).get(netifaces.AF_INET, [{}])[0]
        ip = addrs.get('addr')
        netmask = addrs.get('netmask')
        if not ip or not netmask:
            return "192.168.1.0/24"
        network = ipaddress.IPv4Network(f"{ip}/{netmask}", strict=False)
        return str(network)
    except Exception:
        return "192.168.1.0/24"

def scan_once():
    global devices, device_count_history, network_cidr
    nm = nmap.PortScanner()
    local_cidr = get_local_network()
    now = datetime.now()
    try:
        nm.scan(hosts=local_cidr, arguments='-sn -n')
    except Exception:
        return

    seen_ips = set()
    for host in nm.all_hosts():
        try:
            if nm[host].state() != "up":
                continue
        except KeyError:
            continue
        seen_ips.add(host)

        mac = None
        vendor = None
        try:
            mac = nm[host]['addresses'].get('mac')
            if mac:
                vendor = nm[host].get('vendor', {}).get(mac)
        except Exception:
            pass

        open_ports = []
        try:
            nm.scan(hosts=host, arguments='-Pn -n -T4 -p ' + ",".join(map(str, COMMON_PORTS)))
            for proto in nm[host].all_protocols():
                for port, meta in nm[host][proto].items():
                    if meta.get('state') == 'open':
                        open_ports.append(int(port))
        except Exception:
            pass
        open_ports = sorted(set(open_ports))

        vulns = []
        for p in open_ports:
            if p in VULN_HINTS:
                sev, msg = VULN_HINTS[p]
                vulns.append(f"[{sev}] {msg}")

        with lock:
            rec = devices.get(host, {
                "ip": host,
                "mac": mac,
                "vendor": vendor,
                "open_ports": [],
                "vulns": [],
                "last_seen": now
            })
            if mac and not rec.get("mac"):
                rec["mac"] = mac
            if vendor and not rec.get("vendor"):
                rec["vendor"] = vendor
            rec["open_ports"] = open_ports
            rec["vulns"] = vulns
            rec["last_seen"] = now
            devices[host] = rec

    with lock:
        network_cidr = local_cidr
        cutoff = now.timestamp() - (SCAN_INTERVAL_SEC * 3)
        stale_ips = [ip for ip, rec in devices.items()
                     if rec["last_seen"].timestamp() < cutoff and ip not in seen_ips]
        for ip in stale_ips:
            del devices[ip]
        device_count_history.append(len(devices))
        if len(device_count_history) > 200:
            device_count_history = device_count_history[-200:]

def background_scanner():
    while True:
        try:
            scan_once()
        except Exception:
            pass
        time.sleep(SCAN_INTERVAL_SEC)

# --------------------------- ROUTES -----------------------------
@app.route("/")
def root():
    if session.get("authed"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    err = None
    if request.method == "POST":
        u = request.form.get("username", "")
        p = request.form.get("password", "")
        if u == DASH_USER and p == DASH_PASS:
            session["authed"] = True
            nxt = request.args.get("next") or url_for("dashboard")
            return redirect(nxt)
        err = "Invalid credentials"
    return render_template_string(LOGIN_HTML, error=err, username_hint=DASH_USER)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template_string(DASHBOARD_HTML)

@app.route("/api/summary")
@login_required
def api_summary():
    with lock:
        total = len(devices)
        vulnerable = 0
        port_tally = {}
        rows = []
        for ip, rec in devices.items():
            is_vuln = 1 if rec["vulns"] else 0
            vulnerable += is_vuln
            for p in rec["open_ports"]:
                if p in VULN_HINTS:
                    port_tally[p] = port_tally.get(p, 0) + 1
            rows.append({
                "ip": ip,
                "mac": rec["mac"] or "Unknown",
                "vendor": rec["vendor"] or "Unknown",
                "open_ports": rec["open_ports"],
                "vulns": rec["vulns"],
                "last_seen": rec["last_seen"].strftime("%Y-%m-%d %H:%M:%S")
            })

        safe = total - vulnerable
        return jsonify({
            "network": network_cidr,
            "total": total,
            "safe": safe,
            "vulnerable": vulnerable,
            "history": device_count_history[-60:],
            "vuln_ports": port_tally,
            "devices": rows
        })

# --------------------------- HTML -------------------------------
LOGIN_HTML = """
<!doctype html>
<html>
<head>
  <title>Login • IoT IDS</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body{font-family:system-ui,-apple-system,Segoe UI,Roboto; background:#0f172a; color:#e2e8f0; display:flex; align-items:center; justify-content:center; height:100vh; margin:0}
    .card{background:#111827; border:1px solid #1f2937; padding:24px 28px; border-radius:16px; width:360px; box-shadow:0 6px 30px rgba(0,0,0,.35)}
    h1{margin:0 0 12px 0; font-size:22px}
    label{display:block; font-size:14px; color:#94a3b8; margin:8px 0 6px}
    input{width:100%; padding:10px 12px; border-radius:10px; border:1px solid #334155; background:#0b1220; color:#e2e8f0}
    .btn{margin-top:16px; width:100%; padding:10px 14px; border-radius:10px; border:none; background:#22c55e; color:#041; font-weight:700; cursor:pointer}
    .err{color:#f87171; margin-top:10px; font-size:14px}
    .hint{color:#64748b; font-size:12px; margin-top:10px}
  </style>
</head>
<body>
  <form class="card" method="post">
    <h1>🔐 IoT IDS Dashboard</h1>
    <label>Username</label>
    <input name="username" placeholder="Username" required>
    <label>Password</label>
    <input name="password" type="password" placeholder="Password" required>
    <button class="btn" type="submit">Sign in</button>
    {% if error %}<div class="err">{{ error }}</div>{% endif %}
    <div class="hint">Tip: default user is <b>{{ username_hint }}</b> (set IOT_IDS_USER/IOT_IDS_PASS env vars)</div>
  </form>
</body>
</html>
"""

DASHBOARD_HTML = """
<!doctype html>
<html>
<head>
  <title>IoT IDS • Dashboard</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    :root { --bg:#0f172a; --panel:#0b1220; --muted:#94a3b8; --border:#1f2937; --text:#e2e8f0; --ok:#22c55e; --warn:#f59e0b; --crit:#ef4444; }
    *{box-sizing:border-box}
    body{font-family:system-ui,-apple-system,Segoe UI,Roboto; background:var(--bg); color:var(--text); margin:0; padding:24px;}
    header{display:flex; align-items:center; justify-content:space-between; margin-bottom:16px}
    .card{background:var(--panel); border:1px solid var(--border); border-radius:16px; padding:16px; box-shadow:0 6px 30px rgba(0,0,0,.35)}
    .grid{display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:16px}
    h1{margin:0; font-size:20px}
    .pill{display:inline-flex; align-items:center; gap:8px; background:#0a0f1c; border:1px solid var(--border); padding:8px 12px; border-radius:999px; color:var(--muted)}
    a.btn{color:#041; background:var(--ok); padding:8px 12px; border-radius:10px; text-decoration:none; font-weight:700}
    table{width:100%; border-collapse:collapse; margin-top:8px}
    th,td{border-bottom:1px solid var(--border); padding:10px; text-align:left; font-size:14px}
    th{color:#9fb2ca; font-weight:600}
    .sev-CRITICAL{color:var(--crit); font-weight:700}
    .sev-HIGH{color:#f97316; font-weight:700}
    .sev-MEDIUM{color:var(--warn); font-weight:700}
    .sev-INFO{color:#60a5fa; font-weight:600}
    .charts{display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:16px}
    footer{margin-top:16px; color:var(--muted); font-size:12px}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>📡 IoT Vulnerability Scanner</h1>
      <div class="pill">Network: <span id="net">detecting…</span></div>
    </div>
    <div style="display:flex; gap:10px; align-items:center">
      <div class="pill">Total: <b id="tot">0</b></div>
      <div class="pill">Safe: <b id="safe">0</b></div>
      <div class="pill">Vulnerable: <b id="vuln">0</b></div>
      <a class="btn" href="/logout">Logout</a>
    </div>
  </header>

  <div class="grid" style="margin-bottom:16px">
    <div class="card">
      <h3 style="margin:4px 0 8px">Devices</h3>
      <div style="max-height:420px; overflow:auto">
        <table id="tbl">
          <thead>
            <tr>
              <th>IP</th><th>MAC</th><th>Vendor</th><th>Open Ports</th><th>Findings</th><th>Last Seen</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>

    <div class="card">
      <h3 style="margin:4px 0 8px">Status (Safe vs Vulnerable)</h3>
      <canvas id="pie"></canvas>
    </div>

    <div class="card">
      <h3 style="margin:4px 0 8px">Devices Online Over Time</h3>
      <canvas id="line"></canvas>
    </div>

    <div class="card">
      <h3 style="margin:4px 0 8px">Vulnerabilities by Port</h3>
      <canvas id="bar"></canvas>
    </div>
  </div>

  <footer>Only scan networks/devices you own or are authorized to test.</footer>

  <script>
    let pie, line, bar;
    function sevClass(txt){ const m = txt.match(/^\\[(.*?)\\]/); return m ? ("sev-" + m[1]) : ""; }
    function renderTable(devs){
      const tb = document.querySelector("#tbl tbody");
      tb.innerHTML = "";
      devs.forEach(d=>{
        const tr = document.createElement("tr");
        const vulnsHtml = (d.vulns && d.vulns.length)
          ? d.vulns.map(v=>`<div class="${sevClass(v)}">${v}</div>`).join("")
          : '<span class="sev-INFO">[OK] No risky ports detected</span>';
        tr.innerHTML = `
          <td>${d.ip}</td>
          <td>${d.mac}</td>
          <td>${d.vendor}</td>
          <td>${(d.open_ports||[]).join(", ") || "-"}</td>
          <td>${vulnsHtml}</td>
          <td>${d.last_seen}</td>
        `;
        tb.appendChild(tr);
      });
    }
    async function fetchSummary(){ const r = await fetch('/api/summary'); return await r.json(); }
    function ensureCharts(){
      if(!pie){ pie = new Chart(document.getElementById('pie'), { type:'pie', data:{ labels:['Safe','Vulnerable'], datasets:[{ data:[0,0] }] } }); }
      if(!line){ line = new Chart(document.getElementById('line'), { type:'line', data:{ labels:[], datasets:[{ label:'Devices Online', data:[], fill:false }] } }); }
      if(!bar){ bar = new Chart(document.getElementById('bar'), { type:'bar', data:{ labels:[], datasets:[{ label:'Devices with risky port', data:[] }] } }); }
    }
    async function tick(){
      try{
        const s = await fetchSummary();
        document.getElementById('net').textContent = s.network;
        document.getElementById('tot').textContent = s.total;
        document.getElementById('safe').textContent = s.safe;
        document.getElementById('vuln').textContent = s.vulnerable;
        renderTable(s.devices);
        ensureCharts();
        pie.data.datasets[0].data = [s.safe, s.vulnerable]; pie.update();
        line.data.labels = Array.from({length: s.history.length}, (_,i)=> String(i+1));
        line.data.datasets[0].data = s.history; line.update();
        const ports = Object.keys(s.vuln_ports);
        const counts = Object.values(s.vuln_ports);
        bar.data.labels = ports; bar.data.datasets[0].data = counts; bar.update();
      }catch(e){ }
    }
    setInterval(tick, 4000); tick();
  </script>
</body>
</html>
"""

# --------------------------- MAIN -------------------------------
if __name__ == "__main__":
    t = threading.Thread(target=background_scanner, daemon=True)
    t.start()

    host = "0.0.0.0"
    port = 5000
    while True:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind((host, port))
            s.close()
            break
        except OSError:
            print(f"Port {port} busy, trying next port...")
            port += 1

    url = f"http://localhost:{port}"
    print(f"[*] Dashboard running on {url}")
    try: webbrowser.open(url)
    except Exception: pass

    app.run(host=host, port=port, debug=False)
