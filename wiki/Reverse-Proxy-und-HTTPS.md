# Reverse Proxy und HTTPS

Der Container lauscht auf Port **8000**. Für den Zugriff von außen empfiehlt die Dokumentation einen Reverse Proxy mit HTTPS (Nginx Proxy Manager, Traefik oder Caddy). **Noch sicherer** ist ein VPN (z. B. WireGuard), statt den Hub öffentlich ins Netz zu stellen. Port 8000 nie ohne HTTPS ins Internet freigeben.

> Das Projekt liefert **keine fertigen Proxy-Konfigurationen** mit. Die Beispiele unten sind gewöhnliche Minimal-Konfigurationen dieser Programme, nur auf den Familienhub-Port gemünzt. Sie sind hier **nicht** gegen jede Proxy-Version getestet. Verbessert sie gern im Wiki.

## Was der Hub vom Proxy braucht

Aus der Dokumentation und der `.env.example`:

- **`SECURE_COOKIES=true`**, wenn der Hub nur über HTTPS erreichbar ist (Add-on: Option `secure_cookies`). Bei reinem HTTP im Heimnetz muss es `false` bleiben.
- **`HUB_PUBLIC_URL=https://familienhub.example.org`**: die Adresse, die Handys erreichen. Damit funktionieren Klick-Links und die Erinnerungs-Knöpfe in Mitteilungen.
- **Lange Anfragen erlauben.** Ein Plugin zu installieren kann eine Minute oder länger dauern. Erlaubt für `/api/` lange Anfragen, z. B. bei nginx `proxy_read_timeout 300s`, bei Nginx Proxy Manager im Reiter *Advanced*. Wird die Verbindung getrennt, kann die Installation trotzdem fertig werden: Schaut in die Plugin-Liste.
- **`CORS_ORIGINS`** leer lassen, solange App und Web-App dieselbe Adresse nutzen.
- Bei OIDC müssen die Weiterleitungs-Adressen (`OIDC_REDIRECT_URI_*`) mit eurer öffentlichen HTTPS-Adresse übereinstimmen.

## Beispiel Caddy

Caddy holt und erneuert das HTTPS-Zertifikat selbst (die Domain muss auf euren Server zeigen).

```
familienhub.example.org {
    reverse_proxy localhost:8000
}
```

## Beispiel nginx

```nginx
server {
    listen 443 ssl;
    server_name familienhub.example.org;
    # ssl_certificate / ssl_certificate_key: z. B. von certbot

    client_max_body_size 5m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }
}
```

(Der Hub begrenzt Anfragen selbst auf 2 MB; `client_max_body_size` ist nur eine großzügige Obergrenze.)

## Traefik und Nginx Proxy Manager

Beide werden in der Projekt-Dokumentation nur namentlich genannt. Zeigt den Router/Proxy-Host auf den Container bzw. `<server>:8000`, aktiviert HTTPS (Let's Encrypt) und setzt die Einstellungen oben. Mit Nginx Proxy Manager: Proxy Host anlegen, Ziel `http`, Host/IP des Servers, Port 8000, im Reiter *SSL* ein Zertifikat anfordern, im Reiter *Advanced* das lange Zeitlimit eintragen.

## Prüfen

- `https://familienhub.example.org/api/health` muss ohne Anmeldung antworten.
- Danach in der App die HTTPS-Adresse als Server eintragen.
- Funktioniert der Login im Browser nicht: `SECURE_COOKIES` passt nicht zu eurer Adresse, siehe [Fehlerbehebung](Fehlerbehebung).

Referenz (Englisch): [Getting started, Abschnitt 2](https://github.com/Brottuetchen/familienhub/blob/main/docs/getting-started.md#2-make-it-reachable) · [Security](https://github.com/Brottuetchen/familienhub/blob/main/docs/security.md)
