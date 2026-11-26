"""SwitchBot Keypad Manager.

Enroll and delete credentials (fingerprint, face, palm, PIN, NFC) on a SwitchBot Keypad Vision / Vision Pro
from Home Assistant, assign them to people, show who unlocked how (events of the ESPHome keypad bridge) and,
optionally, approve or deny each keypad unlock with per-person rules.
"""
from __future__ import annotations

import asyncio
import re
from datetime import timedelta
import logging
import uuid

import voluptuous as vol

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothCallbackMatcher, BluetoothScanningMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant, ServiceCall, SupportsResponse, callback
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    BRIDGE_UNLOCK_EVENT, CONF_ADDRESS, CONF_BRIDGE, CONF_ENCRYPTION_KEY, CONF_KEY_ID, CONF_MODEL, CONF_PERSONS, DOMAIN, FACE, FINGERPRINT, PALM, KINDS, NFC, NO_ENTRY, PIN,
    RULE_OPTIONS, UNLOCKED_EVENT, VALIDITY_OPTIONS, WHAT_OPTIONS, WINDOW_DEFAULT, WINDOWS, DAY_NAMES,
)
from .keypad import DELETE as DELETE_CMD, SLOT_RANGE, Keypad, KeypadError, KeyRejected, NotStored
from .texts import detail_text, texts

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.EVENT, Platform.NUMBER, Platform.SELECT, Platform.SENSOR, Platform.SWITCH, Platform.TEXT, Platform.TIME]
LOCK_PLATFORMS = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.EVENT, Platform.NUMBER, Platform.SELECT, Platform.SWITCH, Platform.TIME]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
SIGNAL = f"{DOMAIN}_updated_{{}}"
ADV_SIGNAL = f"{DOMAIN}_advertisement_{{}}"
STORAGE_VERSION = 1


def reported_index(keypad_slot: int) -> int:
    """Slot number the keypad bridge reports on unlock for a keypad slot.

    The keypad reports credentials with a bias of 10 for some kinds (fingerprints are stored from slot 10 on);
    the bridge removes it (index = slot - 10 for slots >= 10), see switchbot-keypad-bridge lock_protocol.cpp.
    """
    return keypad_slot - 10 if keypad_slot >= 10 else keypad_slot


def keypad_slot_from_index(kind: str, index: int) -> int | None:
    """Keypad slot of a credential known only from an unlock (verified for fingerprints and faces).

    Fingerprints live in keypad slots 10+ and are reported as slot - 10; faces and palms are reported unchanged
    (verified). For PIN and NFC the slot is found on delete (NFC: only slots that really hold a card).
    """
    if kind == FINGERPRINT:
        return index + 10
    if kind in (FACE, PALM):
        return index
    return None


class Manager:
    """State and workflows of one keypad (one config entry)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.keypad = Keypad(hass, entry.data.get(CONF_ADDRESS, ""), entry.data.get(CONF_MODEL, "Keypad Vision Pro"),
                             entry.data.get(CONF_KEY_ID, ""), entry.data.get(CONF_ENCRYPTION_KEY, ""))
        self.store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self.entries: list[dict] = []
        self.extra_persons: list[str] = []
        self.counts: dict[str, int] = {}
        self.last: dict = {}
        self.rules: dict[str, str] = {}          # person -> rule
        self.unknown_rule = "always"              # rule for credentials without a person
        self.approval = False                     # approve/deny unlocks via the bridge
        self.fallback_mode = "all"                # bridge fallback without HA: all | allowed | none
        self._pushed_fallback: tuple | None = None
        self.unassigned: dict | None = None       # last unlock without a matching entry
        self.pending: dict[str, dict] = {}        # kind -> {person, detail}: assign the next unknown unlock of kind
        self.status_key, self.status_args = "ready", {}
        self.choice = {"person": None, "what": "thumb_right", "validity": "permanent", "entry": NO_ENTRY}
        self.adv: dict = {}                       # keypad state from its Bluetooth advertisements (battery, alarms)
        self.rssi: int | None = None
        self.running: asyncio.Task | None = None
        self.cancel_event = asyncio.Event()

    @property
    def bridge(self) -> str:
        """ESPHome device name of the keypad bridge (options override the setup value)."""
        return self.entry.options.get(CONF_BRIDGE) or self.entry.data[CONF_BRIDGE]

    @property
    def t(self) -> dict:
        return texts(self.hass.config.language)

    # ---------- storage ----------
    async def load(self) -> None:
        data = await self.store.async_load() or {}
        self.entries = data.get("entries", [])
        for entry in self.entries:   # 1.0.0 stored the keypad slot of enrolled entries in "slot"
            if entry.get("source") == "home_assistant" and "keypad_slot" not in entry:
                entry["keypad_slot"] = entry["slot"]
                entry["slot"] = reported_index(entry["slot"])
            if entry.get("keypad_slot") is None and entry.get("source") in ("assigned", "imported"):  # 1.6.2: derive slot
                entry["keypad_slot"] = keypad_slot_from_index(entry["kind"], entry["slot"])
        self.extra_persons = data.get("persons", [])
        self.last = data.get("last", {})
        self.counts = data.get("counts", {})
        self.rules = data.get("rules", {})
        self.unknown_rule = data.get("unknown_rule", "always")
        self.approval = data.get("approval", False)
        self.fallback_mode = data.get("fallback_mode", "all")
        self.pending = data.get("pending", {})

    async def save(self) -> None:
        await self.store.async_save({
            "entries": self.entries, "persons": self.extra_persons, "last": self.last, "counts": self.counts,
            "rules": self.rules, "unknown_rule": self.unknown_rule, "approval": self.approval,
            "fallback_mode": self.fallback_mode, "pending": self.pending})
        self.notify_entities()
        self.push_fallback()

    # ---------- fallback policy on the bridge ----------
    def fallback_policy(self) -> tuple[int, str]:
        """(mode, allow list) for the bridge: 0 all, 1 only allowed entries, 2 none."""
        mode = {"all": 0, "allowed": 1, "none": 2}.get(self.fallback_mode, 0)
        allow = ",".join(f"{e['kind']}:{e['slot']}" for e in self.entries if e.get("fallback", True))
        return mode, allow

    @callback
    def push_fallback(self, force: bool = False) -> None:
        """Send the fallback policy to the bridge (stored there in flash) when it changed."""
        policy = self.fallback_policy()
        if not force and policy == self._pushed_fallback:
            return
        service = f"{self.bridge.replace('-', '_')}_set_fallback"
        if not self.hass.services.has_service("esphome", service):
            return
        self._pushed_fallback = policy
        self.hass.async_create_task(self.hass.services.async_call(
            "esphome", service, {"mode": policy[0], "allow": policy[1]}))

    @callback
    def notify_entities(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL.format(self.entry.entry_id))

    @staticmethod
    def new_entry(kind, slot, person, detail, *, source="home_assistant", keypad_slot=None, valid_from=None,
                  valid_until=None) -> dict:
        """slot = number reported by the bridge on unlock; keypad_slot = slot on the keypad (known when enrolled
        here, needed to delete it on the keypad)."""
        return {"id": uuid.uuid4().hex[:8], "kind": kind, "slot": slot, "keypad_slot": keypad_slot,
                "person": person, "detail": detail,
                "source": source, "created": dt_util.now().isoformat(timespec="minutes"),
                "valid_from": valid_from, "valid_until": valid_until}

    # ---------- presentation ----------
    def who(self, entry: dict) -> str:
        detail = detail_text(self.t, entry.get("detail") or "")
        return f"{entry['person']} ({detail})" if detail else entry["person"]

    def label(self, entry: dict) -> str:
        until = ""
        if entry.get("valid_until"):
            until = f", {self.t['until']} {dt_util.parse_datetime(entry['valid_until']).strftime('%d.%m. %H:%M')}"
        return f"{self.who(entry)} – {self.t['kind'][entry['kind']]} {entry['slot']}{until}"

    def persons(self) -> list[str]:
        names = []
        for entity_id in self.entry.options.get(CONF_PERSONS, self.entry.data.get(CONF_PERSONS, [])):
            if (state := self.hass.states.get(entity_id)) is not None:
                names.append(state.attributes.get("friendly_name") or entity_id.split(".", 1)[1])
        for name in self.extra_persons + [e["person"] for e in self.entries]:
            if name and name not in names:
                names.append(name)
        return names or ["Guest"]

    def current_person(self) -> str:
        person = self.choice["person"]
        return person if person in self.persons() else self.persons()[0]

    def unassigned_counts(self) -> dict[str, int]:
        """Credentials on the keypad without an entry in the list (e.g. created in the SwitchBot app)."""
        result = {}
        for kind in KINDS:
            if kind in self.counts:
                diff = self.counts[kind] - sum(1 for e in self.entries if e["kind"] == kind)
                if diff:
                    result[self.t["kind"][kind]] = diff
        return result

    @property
    def status(self) -> str:
        text = self.t.get(self.status_key, self.status_key)
        try:
            return text.format(**self.status_args)
        except (KeyError, IndexError):
            return text

    async def set_status(self, key: str, **args) -> None:
        self.status_key, self.status_args = key, args
        self.notify_entities()

    # ---------- keypad state from Bluetooth advertisements ----------
    @callback
    def handle_advertisement(self, service_info, _change) -> None:
        """Battery, charging, alarms, doorbell and radar from the keypad's advertisements (PySwitchbot parser,
        no connection needed)."""
        from switchbot import SwitchbotModel, parse_advertisement_data
        try:
            adv = parse_advertisement_data(service_info.device, service_info.advertisement,
                                           SwitchbotModel(self.entry.data.get(CONF_MODEL, "Keypad Vision Pro")))
        except ValueError:
            adv = None
        data = (adv.data or {}).get("data") if adv else None
        if not data or "battery" not in data:
            return
        self.rssi = service_info.rssi
        if data != self.adv:
            self.adv = dict(data)
            async_dispatcher_send(self.hass, ADV_SIGNAL.format(self.entry.entry_id))

    # ---------- unlock events from the keypad bridge ----------
    @callback
    def handle_bridge_event(self, event: Event) -> None:
        data = event.data
        if data.get("bridge") != self.bridge:
            return
        kind = str(data.get("method", ""))
        try:
            slot = int(data.get("index"))
        except (TypeError, ValueError):
            return
        match = next((e for e in self.entries if e["kind"] == kind and e["slot"] == slot), None)
        if match is None and kind in self.pending:
            # an unknown credential was marked for a person ("Update entry" on "Unknown – …"): assign it now
            want = self.pending.pop(kind)
            was_selected = self.choice["entry"] in self.unknown_labels() or self.choice["entry"] == NO_ENTRY
            match = self.new_entry(kind, slot, want["person"], want.get("detail", ""), source="assigned",
                                   keypad_slot=keypad_slot_from_index(kind, slot))
            self.entries.append(match)
            if was_selected:
                self.choice["entry"] = self.label(match)
            self.status_key, self.status_args = "assigned", {"entry": self.label(match)}
            self._notify(self.t["pending_done"].format(entry=self.label(match)))
        decision, rule = self.decide(match)
        allowed = decision == "open"
        # Always answer a bridge with approval: with "Approve unlocks" off every unlock is approved, otherwise the
        # bridge would wait for its timeout and apply the fallback policy (possibly "nobody").
        self._answer_bridge(allowed if self.approval else True, kind, slot)
        kind_text = self.t["kind"].get(kind, kind)
        if match:
            text = self.who(match)
            self.unassigned = None
        else:
            text = f"{self.t['unknown']} ({kind_text} {slot})"
            self.unassigned = {"kind": kind, "slot": slot}
        # decision: open | denied | event_only (only meaningful with approval on; without it the bridge always opens)
        self.last = {"person": match["person"] if match else None, "detail": (match.get("detail") or "") if match else "",
                     "text": text, "kind": kind, "kind_text": kind_text, "slot": slot, "rule": rule,
                     "decision": decision if self.approval else "open",
                     "allowed": allowed if self.approval else None, "time": dt_util.now().isoformat()}
        self.hass.bus.async_fire(UNLOCKED_EVENT, {"keypad": self.entry.title, "config_entry_id": self.entry.entry_id,
                                                  "entry_id": match["id"] if match else None, **self.last})
        self.hass.async_create_task(self.save())
        if "logbook" in self.hass.config.components:
            message = f"{text} {self.t['via']} {kind_text}"
            if self.approval and decision != "open":
                message += f" ({self.t[decision]})"
            self.hass.async_create_task(self.hass.services.async_call(
                "logbook", "log", {"name": self.entry.title, "message": message}))

    # ---------- approval rules ----------
    def decide(self, entry: dict | None) -> tuple[str, str]:
        """Decision for an unlock: ('open' | 'denied' | 'event_only', effective rule)."""
        if entry is None:
            rule = self.unknown_rule
        else:
            rule = entry.get("rule") or "inherit"
            if rule == "inherit":
                rule = self.rules.get(entry["person"], "always")
        if rule == "event_only":
            return "event_only", rule
        return ("open" if self._rule_allows(rule, entry) else "denied"), rule

    def _rule_allows(self, rule: str, entry: dict | None) -> bool:
        now = dt_util.now()
        if rule == "blocked":
            return False
        if rule == "daytime":
            return 6 <= now.hour < 22
        if rule == "weekdays":
            return now.weekday() < 5 and 7 <= now.hour < 19
        if rule == "time_window":
            return any(self._window_active(w, now) for w in self.windows(entry))
        if rule == "someone_home":
            home = self.hass.states.get("zone.home")
            try:
                return home is not None and int(float(home.state)) > 0
            except ValueError:
                return False
        return True

    @staticmethod
    def windows(entry: dict | None) -> list[dict]:
        """Up to WINDOWS time windows of an entry (1.2/1.3 stored a single 'window')."""
        if entry is None:
            return []
        stored = list(entry.get("windows") or ([entry["window"]] if entry.get("window") else []))
        while len(stored) < WINDOWS:
            stored.append(dict(WINDOW_DEFAULT) if not stored else {**WINDOW_DEFAULT, "days": "off"})
        return stored[:WINDOWS]

    @staticmethod
    def _window_active(window: dict, now) -> bool:
        days = window.get("days", "all")
        weekday = now.weekday()
        if days == "off" or (days == "weekdays" and weekday >= 5) or (days == "weekend" and weekday < 5):
            return False
        if days in DAY_NAMES and DAY_NAMES.index(days) != weekday:
            return False
        start, end = window.get("from", "06:00"), window.get("until", "22:00")
        if start == end:          # e.g. 00:00–00:00 = the whole day, never "never"
            return True
        current = now.strftime("%H:%M")
        return start <= current < end if start < end else (current >= start or current < end)

    def selected_entry(self) -> dict | None:
        return next((e for e in self.entries if self.label(e) == self.choice["entry"]), None)

    async def set_entry_rule(self, **changes) -> None:
        """Change rule / time window of the entry selected in 'Entry'."""
        entry = self.selected_entry()
        if entry is None:
            raise HomeAssistantError(self.t["err_select"])
        if "rule" in changes:
            entry["rule"] = changes.pop("rule")
        if "fallback" in changes:
            entry["fallback"] = changes.pop("fallback")
        number = changes.pop("window", 1)
        if changes:
            windows = self.windows(entry)
            windows[number - 1].update(changes)
            entry["windows"] = windows
            entry.pop("window", None)
        await self.save()

    def _answer_bridge(self, allowed: bool, kind: str, slot: int) -> None:
        """Approve or deny the waiting unlock; method/index let the bridge reject a late answer."""
        service = f"{self.bridge.replace('-', '_')}_{'approve' if allowed else 'deny'}_unlock"
        if not self.hass.services.has_service("esphome", service):
            if self.approval:
                _LOGGER.warning("Approval is on, but esphome.%s does not exist – see the README (bridge approval)",
                                service)
            return
        self.hass.async_create_task(self.hass.services.async_call(
            "esphome", service, {"method": kind, "index": slot}))

    # ---------- workflows ----------
    def _period(self, validity: str):
        now = dt_util.now()
        end = {"today": now.replace(hour=23, minute=59, second=59), "24h": now + timedelta(hours=24),
               "1w": now + timedelta(days=7), "1m": now + timedelta(days=30)}.get(validity)
        return (now, end) if end else (None, None)

    async def enroll(self, person: str, what: str, validity: str = "permanent", pin: str | None = None) -> dict:
        if self.running and not self.running.done():
            raise HomeAssistantError(self.t["err_running"])
        if not person:
            raise HomeAssistantError(self.t["err_person"])
        if what not in WHAT_OPTIONS:
            raise HomeAssistantError(f"Unknown option {what}")
        kind, detail = WHAT_OPTIONS[what]
        if kind == PIN:
            pin = (pin or "").strip()
            if not re.fullmatch(r"\d{6,12}", pin):
                raise HomeAssistantError(self.t["err_pin"])
        else:
            pin = None
        start, end = self._period(validity)
        once = validity == "once"
        if once and kind != PIN:
            raise HomeAssistantError(self.t["err_once"])
        if end and kind not in (PIN, FINGERPRINT, NFC):
            raise HomeAssistantError(self.t["err_limit"])
        self.cancel_event.clear()
        self.running = asyncio.current_task()
        await self.set_status("starting", who=person, what=self.t["kind"][kind])
        try:
            result = await self.keypad.enroll(
                kind, valid_from=start.timestamp() if end else None, valid_until=end.timestamp() if end else None,
                once=once, status=lambda key: self.set_status(key), cancel=self.cancel_event, pin=pin)
        except KeypadError as err:
            await self.set_status("error", err=str(err))
            raise
        finally:
            self.running = None
        # an outdated entry for the same slot is replaced
        slot = reported_index(result["slot"])
        self.entries = [e for e in self.entries if not (e["kind"] == kind and e["slot"] == slot)]
        entry = self.new_entry(kind, slot, person, detail, keypad_slot=result["slot"],
                               valid_from=start.isoformat() if end else None, valid_until=end.isoformat() if end else None)
        self.entries.append(entry)
        if person not in self.persons():
            self.extra_persons.append(person)
        await self._refresh_counts()
        await self.set_status("done", entry=self.label(entry))
        self._notify(self.t["enrolled"].format(entry=self.label(entry)))
        return {"entry": entry}

    # ---------- unknown credentials (on the keypad, not in the list) ----------
    def unknown_labels(self) -> dict[str, str]:
        """'Unknown – Face 1' … per kind, one per credential on the keypad without an entry -> kind."""
        result = {}
        for kind in KINDS:
            n = (self.counts.get(kind) or 0) - sum(1 for e in self.entries if e["kind"] == kind)
            for i in range(1, max(n, 0) + 1):
                result[f"{self.t['unknown']} – {self.t['kind'][kind]} {i}"] = kind
        return result

    def _protected_slots(self, kind: str, skip: dict | None = None) -> set[int]:
        """Keypad slots that belong to entries in the list (never probed)."""
        slots: set[int] = set()
        for e in self.entries:
            if e["kind"] != kind or e is skip:
                continue
            if e.get("keypad_slot") is not None:
                slots.add(e["keypad_slot"])
            else:   # slot unknown: protect the likely ones
                slots.update({e["slot"], e["slot"] + 10})
        return slots

    async def _probe_delete(self, kind: str, candidates: list[int]) -> int | None:
        counts = await self.keypad.counts()
        before = counts.get(kind) or 0
        if before == 0:
            return None
        self.cancel_event.clear()

        async def progress(slot: int) -> None:
            await self.set_status("searching", kind=self.t["kind"][kind], slot=slot)

        return await self.keypad.delete_probe(kind, candidates, before, self.cancel_event, progress)

    async def delete_unknown(self, kind: str) -> None:
        """Delete one credential of `kind` that has no entry in the list – on the keypad."""
        kind_text = self.t["kind"][kind]
        protected = self._protected_slots(kind)
        candidates = [s for s in SLOT_RANGE[kind] if s not in protected]
        await self.set_status("searching", kind=kind_text, slot=candidates[0] if candidates else 0)
        try:
            slot = await self._probe_delete(kind, candidates)
        except KeypadError as err:
            await self.set_status("error", err=str(err))
            raise
        self.choice["entry"] = NO_ENTRY
        await self._refresh_counts()
        if slot is None:
            await self.set_status("unknown_not_found", kind=kind_text)
            raise HomeAssistantError(self.t["unknown_not_found"].format(kind=kind_text))
        await self.set_status("deleted_unknown", kind=kind_text, slot=slot)
        self._notify(self.t["deleted_unknown"].format(kind=kind_text, slot=slot))

    async def delete_all(self) -> None:
        """Delete every credential on the keypad and clear the list."""
        self.cancel_event.clear()
        try:
            counts = await self.keypad.counts()
            for kind in KINDS:
                left = counts.get(kind) or 0
                for slot in SLOT_RANGE[kind]:
                    if left == 0 or self.cancel_event.is_set():
                        break
                    if slot % 5 == 0:
                        await self.set_status("searching", kind=self.t["kind"][kind], slot=slot)
                    async with self.keypad.lock:
                        if kind == NFC and not await self.keypad.nfc_exists(slot):
                            continue
                        reply = await self.keypad.command(DELETE_CMD[kind] + f"{slot:02X}")
                        after = await self.keypad._count(kind, reply)  # noqa: SLF001
                    if after is not None:
                        left = after
                self.entries = [e for e in self.entries if e["kind"] != kind or left]
        except KeypadError as err:
            await self.set_status("error", err=str(err))
            raise
        finally:
            await self._refresh_counts()
            await self.keypad.release()
        left = {self.t["kind"][k]: v for k, v in self.counts.items() if k in KINDS and v}
        self.choice["entry"] = NO_ENTRY
        await self.save()
        if left:
            await self.set_status("deleted_all_partly", left=", ".join(f"{k} {v}" for k, v in left.items()))
        else:
            self.entries = []
            await self.save()
            await self.set_status("deleted_all")
            self._notify(self.t["deleted_all"])

    async def delete(self, entry_id: str) -> None:
        entry = next((e for e in self.entries if e["id"] == entry_id), None)
        if entry is None:
            raise HomeAssistantError(self.t["err_entry"])
        if entry.get("keypad_slot") is None:
            # assigned from an unlock and the slot mapping of this kind is not verified: try the likely slots and
            # check that the keypad count dropped
            protected = self._protected_slots(entry["kind"], skip=entry)
            candidates = [s for s in dict.fromkeys([entry["slot"], entry["slot"] + 10]) if s not in protected]
            await self.set_status("deleting", entry=self.label(entry))
            try:
                slot = await self._probe_delete(entry["kind"], candidates)
            except KeypadError as err:
                await self.set_status("error", err=str(err))
                raise
            if slot is None:
                await self.set_status("delete_not_found", entry=self.label(entry))
                raise HomeAssistantError(self.t["delete_not_found"].format(entry=self.label(entry)))
            self.entries.remove(entry)
            self.choice["entry"] = NO_ENTRY
            await self._refresh_counts()
            await self.set_status("deleted", entry=self.label(entry))
            self._notify(self.t["deleted_note"].format(entry=self.label(entry)))
            return
        await self.set_status("deleting", entry=self.label(entry))
        try:
            await self.keypad.delete(entry["kind"], entry["keypad_slot"])
        except NotStored:
            pass   # already gone on the keypad - just remove it from the list
        except KeypadError as err:
            await self.set_status("error", err=str(err))
            raise
        self.entries.remove(entry)
        self.choice["entry"] = NO_ENTRY
        await self._refresh_counts()
        await self.set_status("deleted", entry=self.label(entry))
        self._notify(self.t["deleted_note"].format(entry=self.label(entry)))

    def what_of(self, entry: dict) -> str:
        """'What' option that describes an entry (for pre-filling the selects when editing)."""
        if entry.get("detail") in WHAT_OPTIONS:      # finger or left/right palm
            return entry["detail"]
        return next((k for k, (kind, _) in WHAT_OPTIONS.items() if kind == entry["kind"] and kind != FINGERPRINT),
                    self.choice["what"])

    async def update_entry(self, entry_id: str, person: str | None = None, what: str | None = None) -> None:
        """Change person and/or finger of an entry (only in the list – the keypad stores no names)."""
        entry = next((e for e in self.entries if e["id"] == entry_id), None)
        if entry is None:
            raise HomeAssistantError(self.t["err_entry"])
        if what is not None:
            kind, detail = WHAT_OPTIONS[what]
            if kind != entry["kind"]:
                raise HomeAssistantError(self.t["err_kind"])
            entry["detail"] = detail
        if person:
            entry["person"] = person
            if person not in self.persons():
                self.extra_persons.append(person)
        if self.last and self.last.get("kind") == entry["kind"] and self.last.get("slot") == entry["slot"]:
            self.last.update({"person": entry["person"], "detail": entry.get("detail") or "", "text": self.who(entry)})
        self.choice["entry"] = self.label(entry)
        await self.save()
        await self.set_status("updated", entry=self.label(entry))

    async def assign_unknown(self, kind: str, person: str, what: str) -> None:
        """Mark an unknown credential for a person: the keypad does not tell its slot, so it is assigned on its
        next unlock (handle_bridge_event)."""
        if not person:
            raise HomeAssistantError(self.t["err_person"])
        what_kind, detail = WHAT_OPTIONS.get(what, (kind, ""))
        if what_kind != kind:   # the kind comes from the unknown entry; "What" only adds the finger / hand
            detail = ""
        if (self.unassigned and self.unassigned["kind"] == kind
                and not any(e["kind"] == kind and e["slot"] == self.unassigned["slot"] for e in self.entries)):
            return await self.assign_last(person, what)   # it just unlocked: assign right away
        self.pending[kind] = {"person": person, "detail": detail}
        if person not in self.persons():
            self.extra_persons.append(person)
        await self.save()
        await self.set_status("pending", who=person, kind=self.t["kind"][kind])

    async def assign_last(self, person: str, what: str) -> None:
        """Assign the last unknown unlock (e.g. a credential from the SwitchBot app) – no keypad command."""
        if not self.unassigned:
            raise HomeAssistantError(self.t["err_unassigned"])
        if not person:
            raise HomeAssistantError(self.t["err_person"])
        kind, slot = self.unassigned["kind"], self.unassigned["slot"]
        what_kind, detail = WHAT_OPTIONS.get(what, (kind, ""))
        if what_kind != kind:
            detail = ""
        entry = self.new_entry(kind, slot, person, detail, source="assigned",
                               keypad_slot=keypad_slot_from_index(kind, slot))
        self.entries.append(entry)
        self.unassigned = None
        self.last.update({"text": self.who(entry), "person": person, "detail": detail})
        await self.save()
        await self.set_status("assigned", entry=self.label(entry))

    async def sync(self) -> None:
        await self.set_status("querying")
        try:
            self.counts = await self.keypad.counts()
        except KeyRejected as err:
            self.entry.async_start_reauth(self.hass)
            await self.set_status("error", err=str(err))
            raise
        except KeypadError as err:
            await self.set_status("error", err=str(err))
            raise
        finally:
            await self.keypad.release()
        await self.save()
        diff = self.unassigned_counts()
        if diff:
            await self.set_status("sync", diff=", ".join(f"{k} {v:+d}" for k, v in diff.items()))
        else:
            await self.set_status("sync_ok")

    async def _refresh_counts(self) -> None:
        try:
            self.counts = await self.keypad.counts()
        except KeypadError:
            pass
        await self.save()

    def cancel(self) -> None:
        self.cancel_event.set()
        if self.pending:
            self.pending = {}
            self.hass.async_create_task(self.save())

    def _notify(self, message: str) -> None:
        self.hass.async_create_task(self.hass.services.async_call("persistent_notification", "create", {
            "notification_id": f"{DOMAIN}_{self.entry.entry_id}", "title": self.entry.title, "message": message}))


def _manager(hass: HomeAssistant, call: ServiceCall) -> Manager:
    """Keypad of a service call. hass.data[DOMAIN] only holds keypads (Lock Ultra settings live in runtime_data)."""
    managers: dict[str, Manager] = hass.data.get(DOMAIN, {})
    entry_id = call.data.get("config_entry_id")
    if not entry_id and (entity_id := call.data.get("entity_id")):
        # any entity of the keypad, e.g. its status sensor - readable in dashboards
        ent = er.async_get(hass).async_get(entity_id)
        if ent is None or ent.platform != DOMAIN:
            raise HomeAssistantError("Keypad not found")
        entry_id = ent.config_entry_id
    if entry_id:
        if entry_id not in managers:
            raise HomeAssistantError("Keypad not found")
        return managers[entry_id]
    if len(managers) != 1:
        raise HomeAssistantError("Several keypads – please pass config_entry_id")
    return next(iter(managers.values()))


def _selected(m: Manager, call: ServiceCall) -> tuple[str | None, str | None]:
    """(entry id, unknown kind) of a call: the given entry_id, else the entry chosen in the "Entry" select."""
    if entry_id := call.data.get("entry_id"):
        return entry_id, None
    choice = m.choice["entry"]
    if kind := m.unknown_labels().get(choice):
        return None, kind
    entry_id = next((e["id"] for e in m.entries if m.label(e) == choice), None)
    if choice == NO_ENTRY or entry_id is None:
        raise HomeAssistantError(m.t["err_select"])
    return entry_id, None


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Services that change credentials on the keypad - administrators only. Fields left out are taken from the
    selects of the keypad (person, what, validity, entry), so a dashboard can call them without data."""

    def handler(work):
        async def run(call: ServiceCall):
            m = _manager(hass, call)
            try:
                return await work(m, call)
            except HomeAssistantError as err:
                if m.status_key != "error":   # also in the status sensor - a toast is easy to miss
                    await m.set_status("error", err=str(err))
                raise
        return run

    async def enroll(m: Manager, call: ServiceCall):
        return await m.enroll(call.data.get("person") or m.current_person(), call.data.get("what") or m.choice["what"],
                              call.data.get("validity") or m.choice["validity"], call.data.get("pin"))

    async def update(m: Manager, call: ServiceCall) -> None:
        entry_id, unknown = _selected(m, call)
        person = call.data.get("person") or (None if call.data.get("entry_id") else m.current_person())
        what = call.data.get("what") or (None if call.data.get("entry_id") else m.choice["what"])
        if unknown:
            await m.assign_unknown(unknown, person or m.current_person(), what or m.choice["what"])
        else:
            await m.update_entry(entry_id, person, what)

    async def delete(m: Manager, call: ServiceCall) -> None:
        entry_id, unknown = _selected(m, call)
        if unknown:
            await m.delete_unknown(unknown)
        else:
            await m.delete(entry_id)

    async def assign_last(m: Manager, call: ServiceCall) -> None:
        await m.assign_last(call.data.get("person") or m.current_person(), call.data.get("what") or m.choice["what"])

    async def sync(m: Manager, call: ServiceCall) -> None:
        await m.sync()

    async def delete_all(m: Manager, call: ServiceCall) -> None:
        await m.delete_all()

    async def cancel(m: Manager, call: ServiceCall) -> None:
        m.cancel()
        await m.set_status("cancel")

    what = vol.All(lambda v: "palm_right" if v == "palm" else v, vol.In(list(WHAT_OPTIONS)))
    base = {vol.Optional("config_entry_id"): cv.string, vol.Optional("entity_id"): cv.entity_id}
    person = {vol.Optional("person"): cv.string, vol.Optional("what"): what}
    services = {
        "enroll": (enroll, {**person, vol.Optional("validity"): vol.In(VALIDITY_OPTIONS),
                            vol.Optional("pin"): vol.All(cv.string, vol.Match(r"^\d{6,12}$"))}),
        "update": (update, {vol.Optional("entry_id"): cv.string, **person}),
        "delete": (delete, {vol.Optional("entry_id"): cv.string}),
        "assign_last": (assign_last, person),
        "sync": (sync, {}),
        "delete_all": (delete_all, {}),
        "cancel": (cancel, {}),
    }
    for name, (work, fields) in services.items():
        async_register_admin_service(hass, DOMAIN, name, handler(work), vol.Schema({**base, **fields}),
                                     SupportsResponse.OPTIONAL if name == "enroll" else SupportsResponse.NONE)
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """1.x used the SwitchBot integration's device; 2 has its own connection - the key is asked for by reauth."""
    if entry.version == 1:
        hass.config_entries.async_update_entry(entry, version=2)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.data.get("type") == "lock":
        from .lock import LockSettings
        ls = LockSettings(hass, entry)
        entry.runtime_data = ls
        await hass.config_entries.async_forward_entry_setups(entry, LOCK_PLATFORMS)
        ls.start()
        return True
    manager = Manager(hass, entry)
    from .keypad_settings import KeypadSettings
    manager.settings = KeypadSettings(manager)
    if not (entry.data.get(CONF_ADDRESS) and entry.data.get(CONF_KEY_ID) and entry.data.get(CONF_ENCRYPTION_KEY)):
        # set up with 1.x (through the SwitchBot integration): approval and unlock events keep working, enrolling and
        # deleting need the keypad address and key once -> re-authentication
        entry.async_start_reauth(hass)
    await manager.load()
    entry.runtime_data = manager
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = manager
    entry.async_on_unload(hass.bus.async_listen(BRIDGE_UNLOCK_EVENT, manager.handle_bridge_event))
    if address := entry.data.get(CONF_ADDRESS):
        entry.async_on_unload(bluetooth.async_register_callback(
            hass, manager.handle_advertisement, BluetoothCallbackMatcher(address=address, connectable=False),
            BluetoothScanningMode.PASSIVE))
        if (last := bluetooth.async_last_service_info(hass, address, connectable=False)) is not None:
            manager.handle_advertisement(last, None)

    @callback
    def _service_registered(event: Event) -> None:
        if event.data.get("domain") == "esphome" and str(event.data.get("service", "")).endswith("_set_fallback"):
            manager.push_fallback(force=True)

    entry.async_on_unload(hass.bus.async_listen("service_registered", _service_registered))
    entry.async_on_unload(async_track_time_interval(
        hass, callback(lambda _now: manager.push_fallback(force=True)), timedelta(minutes=15)))
    manager.push_fallback(force=True)
    entry.async_on_unload(entry.add_update_listener(_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    if entry.data.get(CONF_KEY_ID):
        manager.settings.start()
    return True


async def _reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.data.get("type") == "lock":
        unloaded = await hass.config_entries.async_unload_platforms(entry, LOCK_PLATFORMS)
        if unloaded:
            entry.runtime_data.stop()
        return unloaded
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        m = hass.data[DOMAIN].pop(entry.entry_id)
        m.settings.stop()
        m.cancel()
    return unloaded


__all__ = ["ADV_SIGNAL", "Manager", "RULE_OPTIONS", "SIGNAL"]
