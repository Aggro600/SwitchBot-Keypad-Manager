"""Texts built at runtime (entry labels, status, last unlock) in the Home Assistant language."""
from __future__ import annotations

TEXTS = {
    "de": {
        "kind": {"pin": "PIN-Code", "nfc": "NFC-Karte", "fingerprint": "Fingerabdruck", "face": "Gesicht",
                 "palm": "Handfläche"},
        "detail": {"thumb": "Daumen", "index": "Zeigefinger", "middle": "Mittelfinger", "ring": "Ringfinger",
                   "little": "kleiner Finger", "right": "rechts", "left": "links"},
        "until": "bis", "via": "per", "unknown": "Unbekannt", "ready": "Bereit", "none": "–",
        "starting": "Starte Anlernen: {who} – {what} …", "done": "Fertig: {entry}", "error": "Fehler: {err}",
        "deleting": "Lösche {entry} …", "deleted": "Gelöscht: {entry}", "assigned": "Zugeordnet: {entry}",
        "querying": "Frage das Keypad ab …", "sync_ok": "Abgleich: alles zugeordnet", "sync": "Abgleich: {diff}",
        "cancel": "Abbruch angefordert", "finger": "Finger mehrmals auflegen, bis das Keypad fertig meldet",
        "face": "In die Kamera schauen", "palm": "Handfläche vor das Keypad halten", "card": "Karte an das Keypad halten",
        "pin_done": "PIN angelegt", "enrolled": "Angelernt: **{entry}**",
        "pin_note": "PIN-Code: **{pin}** (wird nirgends gespeichert – jetzt notieren)",
        "deleted_note": "Gelöscht (auch im Keypad): **{entry}**", "denied": "abgelehnt",
    },
    "en": {
        "kind": {"pin": "PIN code", "nfc": "NFC card", "fingerprint": "Fingerprint", "face": "Face", "palm": "Palm"},
        "detail": {"thumb": "thumb", "index": "index finger", "middle": "middle finger", "ring": "ring finger",
                   "little": "little finger", "right": "right", "left": "left"},
        "until": "until", "via": "via", "unknown": "Unknown", "ready": "Ready", "none": "–",
        "starting": "Starting enrollment: {who} – {what} …", "done": "Done: {entry}", "error": "Error: {err}",
        "deleting": "Deleting {entry} …", "deleted": "Deleted: {entry}", "assigned": "Assigned: {entry}",
        "querying": "Querying the keypad …", "sync_ok": "Sync: everything assigned", "sync": "Sync: {diff}",
        "cancel": "Cancel requested", "finger": "Place the finger repeatedly until the keypad reports done",
        "face": "Look into the camera", "palm": "Hold your palm in front of the keypad",
        "card": "Hold the card to the keypad", "pin_done": "PIN created", "enrolled": "Enrolled: **{entry}**",
        "pin_note": "PIN code: **{pin}** (not stored anywhere – note it now)",
        "deleted_note": "Deleted (also on the keypad): **{entry}**", "denied": "denied",
    },
}


def texts(language: str) -> dict:
    return TEXTS.get((language or "en").split("-")[0], TEXTS["en"])


def detail_text(t: dict, detail: str) -> str:
    """'thumb_right' -> 'Daumen rechts' / 'right thumb'; free text stays as is."""
    if "_" in detail and all(p in t["detail"] for p in detail.split("_")):
        finger, side = detail.split("_")
        if t is TEXTS["en"]:
            return f"{t['detail'][side]} {t['detail'][finger]}"
        return f"{t['detail'][finger]} {t['detail'][side]}"
    return detail
