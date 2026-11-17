"""
Scharfsinn - absichtlich verwundbarer Demo-Shop fuer eine Hacking-Praesentation.

Nur Standardbibliothek: http.server + sqlite3. Starten mit `python3 app.py`.

WARNUNG: Dieser Server ist mit Absicht unsicher (SQL-Injection, ratbare
Passwoerter ohne Rate-Limit, kaputte Zugriffskontrolle). Niemals ins oeffentliche
Netz stellen. Gedacht fuer eine lokale CTF-/Lehr-Umgebung hinter Port-Forwarding.
"""

import hashlib
import html
import os
import secrets
import sqlite3
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "shop.db")

# In-Memory-Sessions: token -> {"username": ..., "role": ...}
SESSIONS = {}


# --------------------------------------------------------------------------- #
# Konfiguration / .env
# --------------------------------------------------------------------------- #
def load_env():
    cfg = {}
    env_path = os.path.join(BASE_DIR, ".env")
    with open(env_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            cfg[key.strip()] = value.strip()
    return cfg


CFG = load_env()


# --------------------------------------------------------------------------- #
# Produkte (reiner Shop-Inhalt, keine Angriffsflaeche)
# Tuple: (Name, Untertitel, Preis, Schaerfe 1-5, Beschreibung)
# --------------------------------------------------------------------------- #
PRODUCTS = [
    ("Dorfbrand", "Habanero, Mango, zu viel Mut", "8,90", 3,
     "Faengt harmlos an, bleibt dann aber. Auf Ruehrei getestet, Nachbarn haben geklopft."),
    ("Nachbars Rache", "Jalapeno & geroesteter Knoblauch", "7,50", 2,
     "Die milde unter den scharfen. Geht auf alles, sogar auf Leute die 'eigentlich nichts Scharfes' essen."),
    ("Stiller Reflux", "Ghost Pepper, Limette, Reue", "11,20", 4,
     "Kleiner Loeffel reicht. Grosser Loeffel ist eine Lebensentscheidung."),
    ("Oma's Geheimnis", "geraeucherte Paprika, mild", "6,40", 1,
     "Null Schaerfe, viel Geschmack. Fuer die Tischhaelfte die sonst nur meckert."),
    ("Betriebsausflug", "Chipotle, Tomate, dunkles Bier", "9,10", 3,
     "Rauchig und breit. Passt zu Burgern und zu schlechten Entscheidungen am Grill."),
    ("Letzte Mahnung", "Carolina Reaper, pur", "14,00", 5,
     "Wir haben dich gewarnt. Es steht sogar auf dem Etikett. Zweimal."),
]


# --------------------------------------------------------------------------- #
# Datenbank
# --------------------------------------------------------------------------- #
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Legt die DB beim ersten Start an und befuellt Nutzer + Tresor."""
    if os.path.exists(DB_PATH):
        return
    conn = db()
    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE users ("
        "  id INTEGER PRIMARY KEY, username TEXT, password TEXT, role TEXT)"
    )
    cur.execute("CREATE TABLE vault (id INTEGER PRIMARY KEY, secret TEXT)")

    users = [
        (CFG["ADMIN_USERNAME"], CFG["ADMIN_PASSWORD"], "admin"),
        ("kevin", "pizza123", "user"),
        ("hartmann", "letmein", "user"),      # Ziel fuer das Hash-Cracking
        ("swetlana", "sunshine", "user"),
        ("buchhaltung", "qwertz", "user"),
    ]
    cur.executemany(
        "INSERT INTO users (username, password, role) VALUES (?, ?, ?)", users
    )
    cur.execute("INSERT INTO vault (secret) VALUES (?)", (CFG["FLAG_SQLI"],))
    conn.commit()
    conn.close()


# --------------------------------------------------------------------------- #
# HTML-Layout (Catppuccin Mocha, Dark Mode als Standard)
# --------------------------------------------------------------------------- #
STYLE = """
:root{
  --base:#1e1e2e; --mantle:#181825; --crust:#11111b;
  --surface0:#313244; --surface1:#45475a; --overlay0:#6c7086;
  --text:#cdd6f4; --subtext0:#a6adc8;
  --mauve:#cba6f7; --red:#f38ba8; --green:#a6e3a1;
  --yellow:#f9e2af; --blue:#89b4fa;
  --maxw:1040px;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--base);color:var(--text);
  font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  line-height:1.6;-webkit-font-smoothing:antialiased}
a{color:var(--mauve);text-decoration:none}
a:hover{text-decoration:underline}

/* Ankuendigungsstreifen */
.ribbon{background:var(--crust);color:var(--subtext0);font-size:12.5px;
  letter-spacing:.3px;text-align:center;padding:7px 16px;
  border-bottom:1px solid var(--surface0)}

/* Kopf / Navigation */
header{position:sticky;top:0;z-index:20;background:rgba(24,24,37,.85);
  backdrop-filter:blur(10px);border-bottom:1px solid var(--surface0)}
.bar{max-width:var(--maxw);margin:0 auto;padding:14px 20px;display:flex;
  align-items:center;gap:22px}
.brand{font-size:22px;font-weight:800;color:var(--text);letter-spacing:-.4px;
  display:flex;align-items:baseline;gap:9px}
.brand b{color:var(--mauve);font-weight:800}
.brand small{font-size:11px;font-weight:600;color:var(--overlay0);
  text-transform:uppercase;letter-spacing:1.2px}
nav{margin-left:auto;display:flex;align-items:center;gap:6px}
nav a.navlink{color:var(--subtext0);font-size:14.5px;font-weight:500;
  padding:8px 12px;border-radius:8px}
nav a.navlink:hover{color:var(--text);background:var(--surface0);text-decoration:none}
.cart{display:inline-flex;align-items:center;gap:7px;font-size:13.5px;
  color:var(--subtext0);padding:7px 12px;border:1px solid var(--surface0);
  border-radius:999px;margin-left:4px}
.cart b{color:var(--text);font-variant-numeric:tabular-nums}
.loginbtn{background:var(--mauve);color:var(--crust);font-weight:700;font-size:14px;
  padding:8px 15px;border-radius:8px;margin-left:4px}
.loginbtn:hover{text-decoration:none;filter:brightness(1.07)}

main{max-width:var(--maxw);margin:0 auto;padding:0 20px 72px}

/* Hero */
.hero{padding:62px 0 40px;border-bottom:1px solid var(--surface0);margin-bottom:40px;
  position:relative}
.hero::after{content:"";position:absolute;inset:0;z-index:-1;
  background:radial-gradient(70% 120% at 85% -10%,rgba(203,166,247,.14),transparent 60%)}
.kicker{display:inline-block;font-size:12px;font-weight:700;letter-spacing:2px;
  text-transform:uppercase;color:var(--mauve);margin:0 0 14px}
.hero h1{font-size:clamp(32px,5vw,50px);line-height:1.08;margin:0 0 18px;
  letter-spacing:-1px;max-width:16ch;font-weight:800}
.hero h1 em{font-style:normal;color:var(--mauve)}
.lead{color:var(--subtext0);font-size:17px;margin:0;max-width:56ch}
.lead a{font-weight:600}
.hero-meta{display:flex;flex-wrap:wrap;gap:10px 16px;margin-top:26px;
  color:var(--overlay0);font-size:13.5px}
.hero-meta span.dot{color:var(--surface1)}

/* Abschnittskopf */
.section-head{display:flex;align-items:baseline;gap:14px;margin:0 0 22px;
  scroll-margin-top:84px}
.section-head h2{font-size:24px;margin:0;font-weight:800;letter-spacing:-.4px}
.section-head .count{margin-left:auto;color:var(--overlay0);font-size:13px}

/* Produktgitter */
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:18px}
.card{background:var(--mantle);border:1px solid var(--surface0);border-radius:14px;
  padding:20px;display:flex;flex-direction:column;gap:10px;
  transition:transform .14s ease,border-color .14s ease}
.card:hover{transform:translateY(-3px);border-color:var(--surface1)}
.card-top{display:flex;align-items:baseline;justify-content:space-between;gap:12px}
.card-top h3{margin:0;font-size:18.5px;font-weight:700}
.price{font-weight:800;color:var(--green);font-size:16px;white-space:nowrap;
  font-variant-numeric:tabular-nums}
.card .sub{color:var(--mauve);font-size:13px;font-weight:600}
.card p{margin:2px 0 0;font-size:14px;color:var(--subtext0);flex:1}
.card-bottom{display:flex;align-items:center;justify-content:space-between;gap:12px;
  margin-top:8px;padding-top:14px;border-top:1px solid var(--surface0)}
.heat{display:flex;align-items:center;gap:9px}
.heat-label{font-size:11px;text-transform:uppercase;letter-spacing:.8px;
  color:var(--overlay0)}
.pips{display:inline-flex;gap:4px}
.pip{width:8px;height:8px;border-radius:2px;background:var(--surface1);transform:rotate(45deg)}
.pip.on{background:var(--red)}
.add{background:var(--surface0);color:var(--text);border:1px solid var(--surface1);
  font-weight:600;font-size:13.5px;padding:8px 14px;border-radius:9px;cursor:pointer;
  font-family:inherit;transition:background .12s ease}
.add:hover{background:var(--mauve);color:var(--crust);border-color:var(--mauve)}
.add:active{transform:translateY(1px)}

/* Formulare / Login */
h1{font-size:28px;margin:34px 0 6px;letter-spacing:-.4px}
h1.denied{color:var(--red)}
.page-lead{color:var(--subtext0);margin:0 0 24px;max-width:60ch}
form.auth{max-width:380px;background:var(--mantle);border:1px solid var(--surface0);
  border-radius:14px;padding:26px}
label{display:block;font-size:13.5px;margin:14px 0 6px;color:var(--subtext0);font-weight:600}
input[type=text],input[type=password]{width:100%;padding:11px 13px;border-radius:9px;
  border:1px solid var(--surface1);background:var(--crust);color:var(--text);
  font-size:15px;font-family:inherit}
input:focus{outline:2px solid var(--mauve);outline-offset:0;border-color:var(--mauve)}
.btn{display:inline-block;background:var(--mauve);color:var(--crust);
  padding:11px 20px;border-radius:9px;font-weight:700;border:none;cursor:pointer;
  font-size:15px;font-family:inherit}
.btn:hover{text-decoration:none;filter:brightness(1.07)}

/* Hinweise, Flags, Tabellen, Admin */
.note{background:var(--surface0);border-left:3px solid var(--blue);padding:11px 15px;
  border-radius:0 9px 9px 0;margin:16px 0;font-size:14.5px}
.note.err{border-left-color:var(--red)}
.note.err code{color:var(--red)}
.flag{background:var(--surface0);border:1px dashed var(--green);border-radius:9px;
  padding:14px 16px;margin:18px 0;color:var(--green);font-family:ui-monospace,monospace;
  font-size:15px;word-break:break-all}
table{width:100%;border-collapse:collapse;margin-top:14px;font-size:14px;
  background:var(--mantle);border:1px solid var(--surface0);border-radius:12px;overflow:hidden}
th,td{text-align:left;padding:11px 14px;border-bottom:1px solid var(--surface0)}
tr:last-child td{border-bottom:none}
th{color:var(--subtext0);font-weight:600;background:var(--crust)}
td code{font-family:ui-monospace,monospace;color:var(--yellow)}
.pill{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;
  background:var(--surface0);color:var(--subtext0)}
.pill.admin{background:var(--mauve);color:var(--crust);font-weight:700}
.dash{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:16px;
  margin-top:18px}
.dash a.card{display:flex;flex-direction:column;gap:4px}
.dash a.card:hover{text-decoration:none}
.dash h3{margin:0;font-size:17px}
.dash .sub{color:var(--overlay0)}

footer{max-width:var(--maxw);margin:0 auto;padding:26px 20px;color:var(--overlay0);
  font-size:13px;border-top:1px solid var(--surface0)}

/* Toast */
.toast{position:fixed;left:50%;bottom:26px;transform:translateX(-50%) translateY(14px);
  background:var(--surface0);color:var(--text);border:1px solid var(--surface1);
  padding:11px 18px;border-radius:10px;font-size:14px;font-weight:600;
  opacity:0;pointer-events:none;transition:opacity .2s ease,transform .2s ease;z-index:50}
.toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
"""

CART_JS = """
(function(){
  function get(){try{return parseInt(localStorage.getItem('korb')||'0',10)||0}catch(e){return 0}}
  function set(n){try{localStorage.setItem('korb',String(n))}catch(e){}}
  function render(){var b=document.getElementById('korb');if(b)b.textContent=get();}
  var tid;
  function toast(msg){var el=document.getElementById('toast');if(!el)return;
    el.textContent=msg;el.classList.add('show');clearTimeout(tid);
    tid=setTimeout(function(){el.classList.remove('show')},1700);}
  document.addEventListener('click',function(e){
    var b=e.target.closest('.add');if(!b)return;
    set(get()+1);render();toast(b.dataset.name+' liegt im Korb');});
  document.addEventListener('DOMContentLoaded',render);
})();
"""


def layout(title, body, session=None):
    if session:
        acct = (f'<a class=navlink href="/account">{html.escape(session["username"])}</a>'
                f'<a class=navlink href="/logout">abmelden</a>')
    else:
        acct = '<a class=loginbtn href="/login">Anmelden</a>'
    return (
        "<!doctype html><html lang=de data-theme=dark><head>"
        "<meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(title)} &ndash; Scharfsinn</title>"
        f"<style>{STYLE}</style></head><body>"
        "<div class=ribbon>Kleine Manufaktur &middot; Versand Mo&ndash;Mi, wenn das "
        "Wetter passt &middot; zahl bar oder per Ueberweisung</div>"
        "<header><div class=bar>"
        "<a class=brand href='/'>Scharf<b>sinn</b> <small>Soßenlager</small></a>"
        "<nav>"
        "<a class=navlink href='/'>Start</a>"
        "<a class=navlink href='/#sortiment'>Sortiment</a>"
        "<span class=cart>Korb <b id=korb>0</b></span>"
        f"{acct}"
        "</nav>"
        "</div></header><main>"
        + body +
        "</main><footer>Scharfsinn GbR &middot; Lager hinterm Bahndamm &middot; "
        "Rueckgabe sinnlos, ist ja aufgegessen. "
        "Demo-Shop fuer Lehrzwecke.</footer>"
        "<div id=toast class=toast></div>"
        f"<script>{CART_JS}</script>"
        "</body></html>"
    )


# --------------------------------------------------------------------------- #
# Seiten
# --------------------------------------------------------------------------- #
def heat_pips(level):
    pips = "".join(
        f"<span class='pip{' on' if i < level else ''}'></span>" for i in range(5)
    )
    return f"<span class=pips>{pips}</span>"


def page_home(session):
    cards = ""
    for name, sub, price, heat, desc in PRODUCTS:
        cards += (
            "<article class=card>"
            "<div class=card-top>"
            f"<h3>{html.escape(name)}</h3>"
            f"<span class=price>{html.escape(price)}&nbsp;&euro;</span>"
            "</div>"
            f"<div class=sub>{html.escape(sub)}</div>"
            f"<p>{html.escape(desc)}</p>"
            "<div class=card-bottom>"
            f"<span class=heat><span class=heat-label>Schärfe</span>{heat_pips(heat)}</span>"
            f"<button class=add data-name=\"{html.escape(name)}\">In den Korb</button>"
            "</div>"
            "</article>"
        )
    body = (
        "<section class=hero>"
        "<span class=kicker>Manufaktur seit 2019 &middot; Charge Nr. 47</span>"
        "<h1>Sechs Soßen, <em>handgebrannt</em>, schief etikettiert.</h1>"
        "<p class=lead>Wir kochen in kleinen Chargen, fuellen von Hand ab und "
        "schreiben die Schaerfe ehrlich aufs Glas. Kein Abo, keine App, kein "
        "Firlefanz &ndash; nur Soße. Stammkunden <a href='/login'>melden sich an</a> "
        "und finden ihre Bestellungen wieder.</p>"
        "<div class=hero-meta>"
        "<span>frisch gebrannt</span><span class=dot>&bull;</span>"
        "<span>ohne Konservierungszeug</span><span class=dot>&bull;</span>"
        "<span>Glas, kein Plastik</span><span class=dot>&bull;</span>"
        "<span>Schaerfe 1&ndash;5 ehrlich deklariert</span>"
        "</div>"
        "</section>"
        "<div class=section-head id=sortiment>"
        "<h2>Was gerade im Regal steht</h2>"
        f"<span class=count>{len(PRODUCTS)} Sorten</span>"
        "</div>"
        f"<div class=grid>{cards}</div>"
    )
    return layout("Start", body, session)


def page_login(session, error=None, prefill=""):
    note = f"<div class='note err'>{error}</div>" if error else ""
    body = (
        "<h1>Anmelden</h1>"
        "<p class=page-lead>Mit deinem Kundenkonto anmelden, um Bestellungen und "
        "Gutscheine zu sehen.</p>"
        f"{note}"
        "<form class=auth method=post action='/login'>"
        "<label for=u>Benutzername</label>"
        f"<input id=u name=username type=text autocomplete=off value='{html.escape(prefill)}'>"
        "<label for=p>Passwort</label>"
        "<input id=p name=password type=password autocomplete=off>"
        "<div style='margin-top:20px'><button class=btn type=submit>Einloggen</button></div>"
        "</form>"
    )
    return layout("Anmelden", body, session)


def page_account(session):
    uname = session["username"]
    role = session["role"]
    pill = ("<span class='pill admin'>admin</span>" if role == "admin"
            else "<span class=pill>Kunde</span>")
    body = (
        f"<h1>Hallo, {html.escape(uname)} {pill}</h1>"
        "<p class=page-lead>Schoen dass du da bist. Hier siehst du deinen Kontostatus.</p>"
    )
    if uname == "hartmann":
        body += (
            "<div class=note>Treue-Gutschein auf deinem Konto gefunden:</div>"
            f"<div class=flag>{html.escape(CFG['FLAG_CRACK'])}</div>"
        )
    if role == "admin":
        body += ("<div class=note>Du bist als Mitarbeiter angemeldet. "
                 "Zum <a href='/admin'>Admin-Bereich</a>.</div>")
    else:
        body += ("<div class=note>Noch keine Bestellungen. "
                 "Trau dich an die <a href='/#sortiment'>Letzte Mahnung</a>.</div>")
    return layout("Mein Konto", body, session)


def page_admin_index(session):
    body = (
        "<h1>Admin-Bereich</h1>"
        "<p class=page-lead>Interne Verwaltung. Nur fuer Mitarbeiter.</p>"
        "<div class=dash>"
        "<a class=card href='/admin/orders'><h3>Bestellungen</h3>"
        "<div class=sub>offene Lieferungen &amp; Gutscheine</div></a>"
        "<a class=card href='/admin/users'><h3>Benutzerliste</h3>"
        "<div class=sub>Kundenkonten</div></a>"
        "<a class=card href='/admin/config'><h3>Systemkonfiguration</h3>"
        "<div class=sub>gesperrt &ndash; Leitung</div></a>"
        "</div>"
    )
    return layout("Admin", body, session)


def page_admin_orders(session):
    rows = (
        ("#1041", "Dorfbrand x2", "versandfertig"),
        ("#1042", "Letzte Mahnung x1", "Kunde kontaktiert"),
        ("#1043", "Oma's Geheimnis x6", "bezahlt"),
    )
    trs = "".join(
        f"<tr><td><code>{o}</code></td><td>{html.escape(item)}</td>"
        f"<td>{html.escape(st)}</td></tr>"
        for o, item, st in rows
    )
    body = (
        "<h1>Bestellungen</h1>"
        "<p class=page-lead>Interne Lieferliste.</p>"
        f"<table><tr><th>Nr.</th><th>Artikel</th><th>Status</th></tr>{trs}</table>"
        "<div class=note>Interner Aktions-Gutschein fuer Reklamationen:</div>"
        f"<div class=flag>{html.escape(CFG['FLAG_BAC'])}</div>"
    )
    return layout("Bestellungen", body, session)


def page_admin_users(session):
    conn = db()
    rows = conn.execute("SELECT username, password, role FROM users").fetchall()
    conn.close()
    trs = ""
    for r in rows:
        md5 = hashlib.md5(r["password"].encode()).hexdigest()
        trs += (
            f"<tr><td>{html.escape(r['username'])}</td>"
            f"<td><code>{md5}</code></td>"
            f"<td>{html.escape(r['role'])}</td></tr>"
        )
    body = (
        "<h1>Benutzerliste</h1>"
        "<p class=page-lead>Alle Kundenkonten. Passwoerter liegen (natuerlich) nur "
        "als Hash vor.</p>"
        "<table><tr><th>Benutzer</th><th>Passwort (MD5)</th><th>Rolle</th></tr>"
        f"{trs}</table>"
    )
    return layout("Benutzerliste", body, session)


def page_admin_config(session):
    body = (
        "<h1>Systemkonfiguration</h1>"
        "<p class=page-lead>Zugangsdaten der Kasse, Schnittstellen, der ganze heikle Kram.</p>"
        "<div class=note>Master-Zugang:</div>"
        f"<div class=flag>{html.escape(CFG['FLAG_BRUTE'])}</div>"
    )
    return layout("Systemkonfiguration", body, session)


def page_denied(session):
    body = (
        "<h1 class=denied>Zugriff verweigert</h1>"
        "<p class=page-lead>Diese Seite ist der Leitung vorbehalten. "
        "Du bist nicht berechtigt.</p>"
        "<p><a href='/admin'>Zurueck zum Admin-Bereich</a></p>"
    )
    return layout("Zugriff verweigert", body, session)


def page_404(session):
    body = ("<h1>404</h1><p class=page-lead>Die Seite gibt es nicht. "
            "Wie die Sorte 'mittelscharf'.</p>")
    return layout("404", body, session)


# --------------------------------------------------------------------------- #
# HTTP-Handler
# --------------------------------------------------------------------------- #
class Handler(BaseHTTPRequestHandler):
    server_version = "Scharfsinn/1.0"

    def log_message(self, fmt, *args):
        # Zugriffe loggen (hilfreich um Brute-Force live zu zeigen).
        print("%s - %s" % (self.address_string(), fmt % args))

    # --- Hilfen ---------------------------------------------------------- #
    def get_session(self):
        cookie = self.headers.get("Cookie", "")
        for part in cookie.split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                if k == "sid" and v in SESSIONS:
                    return SESSIONS[v]
        return None

    def send_html(self, body, code=200, cookie=None):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(data)

    def redirect(self, location, cookie=None):
        self.send_response(303)
        self.send_header("Location", location)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()

    # --- GET ------------------------------------------------------------- #
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        session = self.get_session()

        if path == "/":
            self.send_html(page_home(session))
        elif path == "/login":
            self.send_html(page_login(session))
        elif path == "/logout":
            self.do_logout()
        elif path == "/account":
            if not session:
                self.redirect("/login")
            else:
                self.send_html(page_account(session))

        # --- Admin-Bereich ---
        elif path == "/admin":
            # Korrekt geschuetzt: nur Admin sieht die Uebersicht.
            if session and session["role"] == "admin":
                self.send_html(page_admin_index(session))
            else:
                self.send_html(page_denied(session), code=403)
        elif path == "/admin/orders":
            # BROKEN ACCESS CONTROL: keinerlei Pruefung.
            self.send_html(page_admin_orders(session))
        elif path == "/admin/users":
            # BROKEN ACCESS CONTROL: keinerlei Pruefung.
            self.send_html(page_admin_users(session))
        elif path == "/admin/config":
            # Korrekt geschuetzt: nur echter Admin.
            if session and session["role"] == "admin":
                self.send_html(page_admin_config(session))
            else:
                self.send_html(page_denied(session), code=403)
        else:
            self.send_html(page_404(session), code=404)

    # --- POST ------------------------------------------------------------ #
    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/login":
            self.do_login()
        else:
            self.send_html(page_404(self.get_session()), code=404)

    def read_form(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8", "replace")
        form = urllib.parse.parse_qs(raw, keep_blank_values=True)
        return {k: v[0] for k, v in form.items()}

    def do_login(self):
        form = self.read_form()
        username = form.get("username", "")
        password = form.get("password", "")

        # ---- ABSICHTLICHE SQL-INJECTION ---------------------------------- #
        # Eingaben werden ungeprueft in den Query-String gebaut.
        query = (
            "SELECT id, username, role FROM users "
            "WHERE username = '%s' AND password = '%s'"
            % (username, password)
        )
        conn = db()
        try:
            row = conn.execute(query).fetchone()
        except sqlite3.Error as exc:
            conn.close()
            # SQL-Fehler bewusst anzeigen -> error-based SQLi lernbar.
            msg = ("SQL-Fehler: <code>%s</code><br><small>Query: %s</small>"
                   % (html.escape(str(exc)), html.escape(query)))
            self.send_html(page_login(None, error=msg, prefill=username))
            return
        conn.close()

        if row is None:
            self.send_html(page_login(
                None,
                error="Benutzername oder Passwort falsch.",
                prefill=username))
            return

        token = secrets.token_hex(16)
        SESSIONS[token] = {"username": row["username"], "role": row["role"]}
        cookie = "sid=%s; Path=/; HttpOnly" % token
        self.redirect("/account", cookie=cookie)

    def do_logout(self):
        cookie = self.headers.get("Cookie", "")
        for part in cookie.split(";"):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                if k == "sid":
                    SESSIONS.pop(v, None)
        self.redirect("/", cookie="sid=; Path=/; Max-Age=0")


# --------------------------------------------------------------------------- #
# Start
# --------------------------------------------------------------------------- #
def main():
    init_db()
    port = int(CFG.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print("Scharfsinn laeuft auf http://0.0.0.0:%d  (Strg+C zum Stoppen)" % port)
    print("DB: %s" % DB_PATH)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nTschuess.")
        server.shutdown()


if __name__ == "__main__":
    main()
