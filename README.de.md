# SwitchBot Keypad Manager

**Die Benutzer eines SwitchBot Keypad Vision / Vision Pro direkt aus Home Assistant verwalten** – Fingerabdrücke,
Gesichter, Handflächen, PIN-Codes und NFC-Karten anlernen und löschen, sehen *wer* *wie* entsperrt hat, und auf Wunsch
**jedes Entsperren am Keypad von Home Assistant freigeben oder ablehnen** lassen – mit Notweg, wenn Home Assistant
nicht erreichbar ist.

[English](README.md)

## Was es kann

- **Anlernen am Keypad aus Home Assistant:** Person und *Was* wählen (10 Finger, Gesicht, Handfläche, zufälliger PIN,
  NFC-Karte), *Anlernen starten*, ans Keypad gehen. Platz und Name werden automatisch gespeichert.
- **Löschen:** Der Zugang ist danach im Keypad *und* in der Liste weg.
- **Ändern:** falsche Person oder falscher Finger? Eintrag wählen (Person und Finger werden vorbelegt), umstellen, *Eintrag ändern*.
- **Befristung** für Finger, PIN und Karte (heute, 24 Stunden, 1 Woche, 1 Monat) und einmalige PINs.
- **Wer hat wie entsperrt:** „Anna (Daumen rechts) per Fingerabdruck · 08:15“ als Sensor, im Logbuch und als Ereignis
  für Automationen.
- **Freigabe mit Notweg (optional):** pro Person *Immer*, *Gesperrt*, *Nur 6–22 Uhr*, *Nur werktags 7–19 Uhr*,
  *Nur wenn jemand zu Hause ist* – und **pro Zugang** (geht vor der Person): *Immer öffnen*, *Gesperrt*,
  *Nur Automation* (öffnet nie, löst nur Automationen aus), *Zeitfenster* (Von/Bis + Alle Tage/Werktags/Wochenende),
  *Nur wenn jemand zu Hause ist*. Ist Home Assistant nicht verbunden oder antwortet nicht binnen 2 s, öffnet die
  Bridge nach deiner Wahl: alle erkannten Zugänge, nur für den Notweg erlaubte Einträge oder keiner (dann bleibt die
  Tür ohne Home Assistant zu). Die Notweg-Regel ist in der Bridge gespeichert.
- **Abgleich:** vergleicht die Anzahl im Keypad mit der Liste und zeigt Zugänge ohne Namen (z. B. aus der
  SwitchBot-App). Zuordnen: einmal damit entsperren, *Letzte Entsperrung zuordnen*.
- **Nur Auswahl:** alles über Auswahllisten und Knöpfe; Freitext nur optional (neue Person).
- Mehrere Keypads: Integration je Keypad einmal hinzufügen.

## Voraussetzungen

- Home Assistant 2026.9 oder neuer
- SwitchBot Keypad Vision oder Vision Pro in der **SwitchBot**-Integration von Home Assistant (Bluetooth, mit
  SwitchBot-Konto, damit der Schlüssel geholt wird) und ein Bluetooth-Adapter/-Proxy in Reichweite
- Für „wer hat entsperrt“ und die Freigabe: ein ESP32 mit der
  [switchbot-keypad-bridge](https://github.com/pierluigizagaria/switchbot-keypad-bridge) (nicht Teil dieses Repositorys)

## Einrichten

1. HACS → ⋮ → *Benutzerdefinierte Repositories* → `https://github.com/Aggro600/SwitchBot-Keypad-Manager` (Integration).
2. **SwitchBot Keypad Manager** installieren, Home Assistant neu starten.
3. *Einstellungen → Geräte & Dienste → Integration hinzufügen → SwitchBot Keypad Manager*: Keypad, Keypad-Bridge
   (ESPHome-Gerätename, Standard `keypad-bridge`) und Personen für die Auswahl wählen.

Die Bridge-Konfiguration (Ereignis mit `bridge`, Freigabe mit `approval:` und den Aktionen `approve_unlock` /
`deny_unlock`) steht im [englischen README](README.md#keypad-bridge-configuration). Die Freigabe ist beim Bridge-Autor als [Pull Request #56](https://github.com/pierluigizagaria/switchbot-keypad-bridge/pull/56) eingereicht; bis zur Übernahme den Zweig `feat/home-assistant-approval` aus [diesem Fork](https://github.com/Aggro600/switchbot-keypad-bridge/tree/feat/home-assistant-approval) verwenden. In den ESPHome-Optionen der Bridge
*„Dem Gerät erlauben, Home-Assistant-Aktionen auszuführen“* einschalten.

## Gut zu wissen

- **PIN-Codes** sind zufällig (6 Ziffern), werden einmal als Meldung angezeigt und **nirgends gespeichert**.
- Was hier angelernt wird, kennt die **SwitchBot-App** nicht; die Namen liegen in Home Assistant.
- **Handfläche:** Start und Status geprüft, Bestätigen/Löschen aus dem Gesichts-Schema abgeleitet.
- Nach einem Neustart der Bridge muss manches Keypad einmal stromlos gemacht werden.
- Finger so oft auflegen, bis das Keypad selbst fertig meldet; die Integration prüft danach die Zählung im Keypad.
- Zu viele Fehlversuche sperren das Keypad eine Weile (Aussperr-Alarm der SwitchBot-Integration).
- Zugänge aus der SwitchBot-App (nur zugeordnet) werden beim Löschen nur aus der Liste entfernt – im Keypad über die App löschen.
- Ein Firmware-Update von SwitchBot kann das Protokoll ändern.

**Dashboard zum Kopieren:** die ganze Benutzerverwaltung als **eine Karte** – *Dashboard → Bearbeiten → Karte hinzufügen →
Manuell*, [docs/dashboard-card.de.yaml](docs/dashboard-card.de.yaml) einfügen und das Präfix `keypad_haustur` durch das eigene
ersetzen (Anfang der Entitäts-IDs, z. B. `sensor.keypad_wohnungstur_zuletzt_entsperrt` → `keypad_wohnungstur`).

Beispiel-Automationen: [docs/examples.yaml](docs/examples.yaml) · großes Dashboard: [docs/dashboard.yaml](docs/dashboard.yaml) ·
Protokoll: [docs/PROTOCOL.md](docs/PROTOCOL.md)

Kein offizielles Produkt von SwitchBot. Nutzung auf eigene Gefahr – es geht um den Zugang zur Wohnung; einen
Schlüssel oder anderen Zugang behalten.
