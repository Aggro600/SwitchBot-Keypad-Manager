# SwitchBot Keypad Manager

**Die Benutzer eines SwitchBot Keypad Vision / Vision Pro direkt aus Home Assistant verwalten** – Fingerabdrücke,
Gesichter, Handflächen, PIN-Codes und NFC-Karten anlernen und löschen, sehen *wer* *wie* entsperrt hat, und auf Wunsch
**jedes Entsperren am Keypad von Home Assistant freigeben oder ablehnen** lassen – mit Notweg, wenn Home Assistant
nicht erreichbar ist.

[English](README.md)

## Was es kann

- **Anlernen am Keypad aus Home Assistant:** Person und *Was* wählen (10 Finger, Gesicht, Handfläche rechts/links, eigener oder zufälliger PIN,
  NFC-Karte), *Anlernen starten*, ans Keypad gehen. Platz und Name werden automatisch gespeichert.
- **Löschen – immer im Keypad *und* in der Liste:** auch Zugänge, die nicht hier angelernt wurden. Unbekannte stehen in
  der Auswahl als *Unbekannt – Gesicht 1*, *Unbekannt – PIN-Code 1* …; die Integration sucht den Platz im Keypad
  selbst (das Keypad meldet beim Löschen die Restanzahl). **Alles löschen** (zweimal drücken) leert Keypad und Liste.
- **Ändern:** falsche Person oder falscher Finger? Eintrag wählen (Person und Finger werden vorbelegt), umstellen, *Eintrag ändern*.
- **Befristung** für Finger, PIN und Karte (heute, 24 Stunden, 1 Woche, 1 Monat) und einmalige PINs.
- **Wer hat wie entsperrt:** „Anna (Daumen rechts) per Fingerabdruck · 08:15“ als Sensor, im Logbuch und als Ereignis
  für Automationen.
- **Freigabe mit Notweg (optional):** pro Person *Immer*, *Gesperrt*, *Nur Automation*, *Nur 6–22 Uhr*, *Nur werktags 7–19 Uhr*,
  *Nur wenn jemand zu Hause ist* – und **pro Zugang** (geht vor der Person): *Immer öffnen*, *Gesperrt*,
  *Nur Automation* (öffnet nie, löst nur Automationen aus), *Zeitfenster* (bis zu 3 pro Zugang, je Von/Bis + Alle Tage/Werktags/Wochenende/einzelner Tag; geöffnet wird, wenn eines passt),
  *Nur wenn jemand zu Hause ist*. Ist Home Assistant nicht verbunden oder antwortet nicht binnen 2 s, öffnet die
  Bridge nach deiner Wahl: alle erkannten Zugänge, nur für den Notweg erlaubte Einträge oder keiner (dann bleibt die
  Tür ohne Home Assistant zu). Die Notweg-Regel ist in der Bridge gespeichert.
- **Abgleich:** vergleicht die Anzahl im Keypad mit der Liste und zeigt Zugänge ohne Namen (z. B. aus der
  SwitchBot-App). Zuordnen: einmal damit entsperren, *Letzte Entsperrung zuordnen*. Für unbekannte Zugänge gibt es
  eine eigene Regel (auch *Nur Automation*) – z. B. „jedes Entsperren startet nur mein Tür-Skript“.
- **Keypad-Einstellungen:** Erkennungsauslöser und -empfindlichkeit, bis zu 3 Zeitpläne (an/aus, Tage, von/bis), Deaktivierungsintervall, Fast Unlock,
  Lautstärke Sprachansage und Signaltöne, Sprache der Ansage, Demontagealarm, Tastenton, Hintergrundbeleuchtung und Helligkeit, Verriegelungstaste,
  Keypad deaktivieren – wie in der SwitchBot-App.
- **Lock-Ultra-Einstellungen** (Schloss als zweiten Eintrag hinzufügen): Motorgeschwindigkeit (schnell/normal/leise),
  LED, Ton, automatisch verriegeln + Zeit, pausieren, halb verriegeln, Taste am Schloss (Drücken, Aktion), iBeacon und
  der komplette **Nachtmodus** (von/bis, Geschwindigkeit, Ton, bei Beginn verriegeln, ganz/halb, Auto-Verriegeln,
  Auto-Entriegeln). Die Schlosskraft fehlt absichtlich (danach müsste neu kalibriert werden). Gelesen wird beim Start,
  alle 12 h, nach jeder Änderung und per Knopf; alles an echter Hardware geprüft. Fertige Ansicht zum Kopieren:
  [docs/settings-view.de.yaml](docs/settings-view.de.yaml) (Keypad-Einstellungen mit Zeitplänen + Schloss-Einstellungen).
- **Nur Auswahl:** alles über Auswahllisten und Knöpfe; Freitext nur optional (neue Person).
- Mehrere Keypads: Integration je Keypad einmal hinzufügen.

## Voraussetzungen

- Home Assistant 2026.9 oder neuer
- SwitchBot Keypad Vision oder Vision Pro (in der SwitchBot-App eingerichtet) und ein Bluetooth-Adapter oder
  ESPHome-Bluetooth-Proxy in Reichweite. Die Integration hat eine **eigene Verbindung** (PySwitchbot über das Bluetooth
  von Home Assistant); der Schlüssel wird bei der Einrichtung einmal mit dem SwitchBot-Konto geholt (nicht gespeichert)
  oder von Hand eingegeben. Die SwitchBot-Integration wird **nicht** gebraucht.
- Für „wer hat entsperrt“ und die Freigabe: ein ESP32 mit der
  [switchbot-keypad-bridge](https://github.com/pierluigizagaria/switchbot-keypad-bridge) (nicht Teil dieses Repositorys)

## Einrichten

1. HACS → ⋮ → *Benutzerdefinierte Repositories* → `https://github.com/Aggro600/SwitchBot-Keypad-Manager` (Integration).
2. **SwitchBot Keypad Manager** installieren, Home Assistant neu starten.
3. *Einstellungen → Geräte & Dienste → Integration hinzufügen → SwitchBot Keypad Manager*: Keypad (aus der
   Bluetooth-Liste – Keypad antippen, damit es sendet), Keypad-Bridge (ESPHome-Gerätename) und Personen wählen,
   danach den Schlüssel *mit SwitchBot-Konto* holen oder von Hand eingeben.

Die Bridge-Konfiguration (Ereignis mit `bridge`, Freigabe mit `approval:` und den Aktionen `approve_unlock` /
`deny_unlock`) steht im [englischen README](README.md#keypad-bridge-configuration). Die Freigabe ist beim Bridge-Autor als [Pull Request #56](https://github.com/pierluigizagaria/switchbot-keypad-bridge/pull/56) eingereicht; bis zur Übernahme den Zweig `feat/home-assistant-approval` aus [diesem Fork](https://github.com/Aggro600/switchbot-keypad-bridge/tree/feat/home-assistant-approval) verwenden. In den ESPHome-Optionen der Bridge
*„Dem Gerät erlauben, Home-Assistant-Aktionen auszuführen“* einschalten.

## Gut zu wissen

- **PIN-Codes:** *PIN-Code (eigener)* nimmt die 6–12 Ziffern aus dem Feld *PIN-Code (6–12 Ziffern)* (nur als
  Sternchen sichtbar, nur im Arbeitsspeicher, nach dem Anlernen gelöscht). *PIN-Code (zufällig)* erzeugt 6 Ziffern und
  zeigt sie **einmal** an: im Statusfeld (`state_content: [state, pin]` an der Status-Kachel), als Attribut `pin` des
  Status-Sensors und als Meldung – bis *Neuen PIN notiert – ausblenden*, zur nächsten Aktion oder nach 10 Minuten.
  PINs werden **nirgends gespeichert** und nicht im Verlauf aufgezeichnet.
- Was hier angelernt wird, kennt die **SwitchBot-App** nicht; die Namen liegen in Home Assistant.
- **An echter Hardware geprüft** (Keypad Vision Pro): Anlernen, Entsperr-Meldung und Löschen für PIN, NFC-Karte,
  Finger, Gesicht und Handfläche rechts/links – jeweils mit der Zählung im Keypad.
- **NFC-Karte:** nach *Anlernen* die Karte **innerhalb von ca. 5 s** ans Keypad halten – länger wartet es nicht.
- **Nie einen leeren NFC-Platz selbst löschen** (z. B. mit eigenen Roh-Befehlen): das Keypad zählt seinen Kartenzähler
  trotzdem herunter; unter 0 meldet es 255 Karten und nimmt keine neue mehr an, bis es in der SwitchBot-App entfernt und
  neu hinzugefügt wird. Die Integration prüft vor jedem Löschen, ob auf dem Platz wirklich eine Karte liegt.
- **Update von 1.x:** einmal neu authentifizieren (Keypad wählen, Schlüssel holen) – Freigabe und Meldungen laufen
  währenddessen weiter. Nach Entfernen/Neu-Hinzufügen in der SwitchBot-App hat das Keypad einen neuen Schlüssel; dann
  fragt die Integration erneut.
- **Schlüssel oder anderen Zugang behalten** – es ist eine Zutrittsanlage.
- In der Bridge-YAML bei `api:` und `wifi:` `reboot_timeout: 0s` setzen: ESPHome startet sonst nach 15 Minuten ohne
  Home Assistant oder WLAN neu – der Notweg soll aber weiterlaufen.
- Das Keypad verbindet sich nur beim Benutzen und trennt nach ein paar Sekunden wieder; „nicht verbunden“ ist normal.
- Nach dem Neukoppeln das Keypad einmal stromlos machen.
- Finger so oft auflegen, bis das Keypad selbst fertig meldet; die Integration prüft danach die Zählung im Keypad.
- Zu viele Fehlversuche sperren das Keypad eine Weile (Aussperr-Alarm der SwitchBot-Integration).
- Das Keypad kann seine Zugänge nicht auflisten (die Liste der SwitchBot-App liegt in der SwitchBot-Cloud). Unbekannte
  Zugänge sieht man daher nur als Anzahl; beim Löschen werden die Plätze der Reihe nach probiert (PIN/Karte bis ca. 1 Minute).
  Plätze bekannter Einträge werden dabei nie angefasst. Die SwitchBot-App zeigt gelöschte Zugänge evtl. noch an.
- Die Keypad-Bridge lässt sich nachträglich in den Optionen der Integration ändern (z. B. nach dem Umbenennen).
- Ein Firmware-Update von SwitchBot kann das Protokoll ändern.

**Automationen ohne Tippen:** *Auslöser hinzufügen → Gerät → (dein Keypad)* → *Entsperrt (beliebiger Zugang)* oder
*Entsperrt mit bestimmtem Zugang* (Person + Finger/Gesicht/… aus einer Liste), jeweils mit *Ergebnis* (beliebig /
geöffnet / abgelehnt / nur Automation).

**Dashboard zum Kopieren:** die ganze Benutzerverwaltung als **eine Karte** (mit Live-Erklärung *„Was passiert bei diesem Zugang?“* für den gewählten Eintrag und Regel-Tabelle) – *Dashboard → Bearbeiten → Karte hinzufügen →
Manuell*, [docs/dashboard-card.de.yaml](docs/dashboard-card.de.yaml) einfügen und das Präfix `keypad_haustur` durch das eigene
ersetzen (Anfang der Entitäts-IDs, z. B. `sensor.keypad_wohnungstur_zuletzt_entsperrt` → `keypad_wohnungstur`).

Beispiel-Automationen: [docs/examples.yaml](docs/examples.yaml) · großes Dashboard: [docs/dashboard.yaml](docs/dashboard.yaml) ·
Protokoll: [docs/PROTOCOL.md](docs/PROTOCOL.md)

Kein offizielles Produkt von SwitchBot. Nutzung auf eigene Gefahr – es geht um den Zugang zur Wohnung; einen
Schlüssel oder anderen Zugang behalten.
