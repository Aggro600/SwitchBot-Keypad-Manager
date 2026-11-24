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
        "deleting": "Lösche {entry} …", "deleted": "Gelöscht: {entry}", "assigned": "Zugeordnet: {entry}", "updated": "Geändert: {entry}",
        "querying": "Frage das Keypad ab …", "sync_ok": "Abgleich: alles zugeordnet", "sync": "Abgleich: {diff}",
        "cancel": "Abbruch angefordert", "finger": "Finger mehrmals auflegen, bis das Keypad fertig meldet",
        "face": "In die Kamera schauen", "palm": "Handfläche vor das Keypad halten", "card": "Karte an das Keypad halten",
        "pin_done": "PIN angelegt", "enrolled": "Angelernt: **{entry}**",
        "pin_note": "PIN-Code: **{pin}** (wird nirgends gespeichert – jetzt notieren)",
        "deleted_note": "Gelöscht (auch im Keypad): **{entry}**",
        "deleted_list_only": "Aus der Liste entfernt: {entry} – im Keypad bitte über die SwitchBot-App löschen",
        "deleted_list_only_note": "Aus der Liste entfernt: **{entry}**. Dieser Zugang wurde nicht hier angelernt, sein Platz im Keypad ist unbekannt – bitte in der SwitchBot-App löschen.", "denied": "abgelehnt", "event_only": "nur Automation",
        "err_running": "Es läuft schon ein Anlernen",
        "err_person": "Bitte zuerst eine Person wählen",
        "err_once": "'Einmalig' gibt es nur für PIN-Codes",
        "err_limit": "Befristung geht nur für PIN, Finger und NFC-Karte",
        "err_entry": "Eintrag nicht gefunden",
        "err_kind": "Die Art lässt sich nicht ändern (ein Gesicht bleibt ein Gesicht) – bitte neu anlernen",
        "err_unassigned": "Keine unbekannte Entsperrung – erst damit am Keypad entsperren",
        "searching": "Suche {kind} im Keypad … (Platz {slot})",
        "deleted_unknown": "Gelöscht (im Keypad): unbekannt – {kind}, Platz {slot}",
        "unknown_not_found": "Kein unbekannter Zugang ({kind}) im Keypad gefunden",
        "delete_not_found": "{entry}: im Keypad nicht gefunden – nicht gelöscht",
        "delete_all_confirm": "ALLES löschen? Zum Bestätigen innerhalb von 15 s nochmal drücken",
        "deleted_all": "Alle Zugänge im Keypad und in der Liste gelöscht",
        "deleted_all_partly": "Gelöscht, aber im Keypad sind noch übrig: {left}",
        "err_select": "Bitte zuerst einen Eintrag wählen",
    },
    "en": {
        "kind": {"pin": "PIN code", "nfc": "NFC card", "fingerprint": "Fingerprint", "face": "Face", "palm": "Palm"},
        "detail": {"thumb": "thumb", "index": "index finger", "middle": "middle finger", "ring": "ring finger",
                   "little": "little finger", "right": "right", "left": "left"},
        "until": "until", "via": "via", "unknown": "Unknown", "ready": "Ready", "none": "–",
        "starting": "Starting enrollment: {who} – {what} …", "done": "Done: {entry}", "error": "Error: {err}",
        "deleting": "Deleting {entry} …", "deleted": "Deleted: {entry}", "assigned": "Assigned: {entry}", "updated": "Updated: {entry}",
        "querying": "Querying the keypad …", "sync_ok": "Sync: everything assigned", "sync": "Sync: {diff}",
        "cancel": "Cancel requested", "finger": "Place the finger repeatedly until the keypad reports done",
        "face": "Look into the camera", "palm": "Hold your palm in front of the keypad",
        "card": "Hold the card to the keypad", "pin_done": "PIN created", "enrolled": "Enrolled: **{entry}**",
        "pin_note": "PIN code: **{pin}** (not stored anywhere – note it now)",
        "deleted_note": "Deleted (also on the keypad): **{entry}**",
        "deleted_list_only": "Removed from the list: {entry} – delete it on the keypad with the SwitchBot app",
        "deleted_list_only_note": "Removed from the list: **{entry}**. It was not enrolled here, so its keypad slot is unknown – please delete it in the SwitchBot app.", "denied": "denied", "event_only": "automation only",
        "err_running": "An enrollment is already running",
        "err_person": "Select a person first",
        "err_once": "'Once' is only available for PIN codes",
        "err_limit": "Time limits are only available for PIN, fingerprint and NFC card",
        "err_entry": "Entry not found",
        "err_kind": "The kind cannot be changed (a face stays a face) – enroll it again instead",
        "err_unassigned": "No unknown unlock – unlock with the credential first",
        "searching": "Searching {kind} on the keypad … (slot {slot})",
        "deleted_unknown": "Deleted (on the keypad): unknown – {kind}, slot {slot}",
        "unknown_not_found": "No unknown credential ({kind}) found on the keypad",
        "delete_not_found": "{entry}: not found on the keypad – not deleted",
        "delete_all_confirm": "Delete EVERYTHING? Press again within 15 s to confirm",
        "deleted_all": "All credentials deleted on the keypad and in the list",
        "deleted_all_partly": "Deleted, but still on the keypad: {left}",
        "err_select": "Select an entry first",
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
