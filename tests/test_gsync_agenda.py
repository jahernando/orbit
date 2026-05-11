"""Tests for the agenda-calendar backend (tasks/ms/reminders → Calendar.app)
in core/gsync.py — see _agenda_backend / _sync_one_agenda_event.
"""

from core import gsync


# ── Backend selection ─────────────────────────────────────────────────────────

class TestAgendaBackend:
    def test_default_is_calendar(self):
        assert gsync._agenda_backend({}) == "calendar"

    def test_explicit_calendar(self):
        assert gsync._agenda_backend({"reminders_backend": "calendar"}) == "calendar"

    def test_explicit_reminders(self):
        assert gsync._agenda_backend({"reminders_backend": "reminders"}) == "reminders"

    def test_unknown_value_defaults_to_calendar(self):
        assert gsync._agenda_backend({"reminders_backend": "weird"}) == "calendar"

    def test_case_insensitive(self):
        assert gsync._agenda_backend({"reminders_backend": "REMINDERS"}) == "reminders"


class TestAgendaCalendarName:
    def test_explicit_value_wins(self):
        assert gsync._agenda_calendar_name(
            {"agenda_calendar": "my-cal"}) == "my-cal"

    def test_falls_back_to_workspace_dir_name(self):
        # ORBIT_HOME.name in the test env is whatever directory pytest runs from;
        # the suffix is what we care about.
        assert gsync._agenda_calendar_name({}).endswith("-rem")


class TestAgendaStorageKey:
    def test_prefixes_with_kind(self):
        item = {"desc": "X", "date": "2030-01-01"}
        assert gsync._agenda_storage_key(item, "task") == "task::X::2030-01-01"
        assert gsync._agenda_storage_key(item, "milestone") == "milestone::X::2030-01-01"
        assert gsync._agenda_storage_key(item, "reminder") == "reminder::X::2030-01-01"

    def test_recurring_keeps_recur_part(self):
        item = {"desc": "X", "date": "2030-01-01", "recur": "weekly"}
        assert gsync._agenda_storage_key(item, "task") == "task::X::🔄weekly::2030-01-01"

    def test_different_kinds_different_keys(self):
        item = {"desc": "Reunión", "date": "2030-05-15"}
        assert (gsync._agenda_storage_key(item, "task")
                != gsync._agenda_storage_key(item, "reminder"))


# ── Props builder ─────────────────────────────────────────────────────────────

class TestAgendaPropsForCalendarApp:
    def _item(self, **over):
        base = {"desc": "Test", "date": "2030-05-15", "time": "10:00"}
        base.update(over)
        return base

    def test_zero_minute_event(self):
        props = gsync._agenda_props_for_calendar_app(
            self._item(), "proj", "Proyecto: proj", "task")
        assert props["start_iso"] == props["end_iso"] == "2030-05-15T10:00"

    def test_default_start_time_when_no_time(self):
        props = gsync._agenda_props_for_calendar_app(
            self._item(time=None), "proj", "Proyecto: proj", "task")
        assert props["start_iso"].endswith("T09:00")

    def test_summary_carries_kind_emoji(self):
        for kind, emoji in (("task", "✅"), ("milestone", "🏁"),
                             ("reminder", "💬")):
            props = gsync._agenda_props_for_calendar_app(
                self._item(), "proj", "Proyecto: proj", kind)
            assert emoji in props["summary"]
            assert "[proj]" in props["summary"]
            assert props["summary"].endswith("Test")

    def test_alarm_zero_by_default(self):
        props = gsync._agenda_props_for_calendar_app(
            self._item(), "proj", "Proyecto: proj", "task")
        assert props["alarm_minutes"] == 0

    def test_alarm_honors_ring_minutes(self):
        # ring=15m → alarm fires 15 minutes before start
        props = gsync._agenda_props_for_calendar_app(
            self._item(ring="15m"), "proj", "Proyecto: proj", "task")
        assert props["alarm_minutes"] == 15

    def test_no_rrule_for_recurring(self):
        # orbit avanza recurrencias localmente; el evento subido no lleva RRULE.
        props = gsync._agenda_props_for_calendar_app(
            self._item(recur="weekly"), "proj", "Proyecto: proj", "task")
        assert props["rrule"] == ""

    def test_orbit_tag_embedded_in_description(self):
        item = self._item()
        item["_orbit_id"] = "deadbeef"
        props = gsync._agenda_props_for_calendar_app(
            item, "proj", "Proyecto: proj", "task")
        assert "[orbit:deadbeef]" in props["description"]

    def test_notes_prepended_to_description(self):
        item = self._item(notes=["nota A", "nota B"])
        props = gsync._agenda_props_for_calendar_app(
            item, "proj", "Proyecto: proj", "task")
        assert "nota A" in props["description"]
        assert "nota B" in props["description"]
        # Project description still present.
        assert "proj" in props["description"]

    def test_strips_time_range_to_start(self):
        # time "10:00-11:00" → only start is used (events are 0-min markers).
        props = gsync._agenda_props_for_calendar_app(
            self._item(time="10:00-11:00"), "proj", "Proyecto: proj", "task")
        assert props["start_iso"] == "2030-05-15T10:00"
        assert props["end_iso"]   == "2030-05-15T10:00"


# ── _sync_one_agenda_event ────────────────────────────────────────────────────

class TestSyncOneAgendaEvent:
    def _item(self, **over):
        base = {"desc": "X", "date": "2030-05-15", "time": "10:00"}
        base.update(over)
        return base

    def test_orbit_id_match_short_circuits_to_update(self, monkeypatch):
        called = {"find": False, "update": False, "create": False}

        def fake_find(cal, oid):
            called["find"] = True
            return "uid-by-orbit"

        def fake_update(uid, cal, props):
            called["update"] = True
            assert uid == "uid-by-orbit"
            return True

        def fake_create(cal, props):
            called["create"] = True
            return "wrong"

        monkeypatch.setattr(gsync, "_find_calendar_event_by_orbit_id", fake_find)
        monkeypatch.setattr(gsync, "_update_calendar_event", fake_update)
        monkeypatch.setattr(gsync, "_create_calendar_event", fake_create)

        item = self._item()
        item["_orbit_id"] = "abcd1234"
        uid = gsync._sync_one_agenda_event("orbit-rem", item, "proj",
                                            "Proyecto: proj", "task")
        assert uid == "uid-by-orbit"
        assert called == {"find": True, "update": True, "create": False}

    def test_create_path_when_no_match(self, monkeypatch):
        monkeypatch.setattr(gsync, "_find_calendar_event_by_orbit_id",
                             lambda c, o: None)
        monkeypatch.setattr(gsync, "_find_calendar_event_by_title_date",
                             lambda c, s, t: None)
        monkeypatch.setattr(gsync, "_create_calendar_event",
                             lambda c, p: "new-uid")
        uid = gsync._sync_one_agenda_event("orbit-rem", self._item(),
                                            "proj", "Proyecto: proj", "task")
        assert uid == "new-uid"

    def test_dry_run_does_not_call_applescript(self, monkeypatch):
        called = {"any": False}
        for name in ("_find_calendar_event_by_orbit_id",
                     "_find_calendar_event_by_title_date",
                     "_update_calendar_event",
                     "_create_calendar_event"):
            monkeypatch.setattr(
                gsync, name,
                lambda *a, **k: called.__setitem__("any", True) or "x")
        gsync._sync_one_agenda_event("orbit-rem", self._item(),
                                      "proj", "Proyecto: proj", "task",
                                      dry_run=True)
        assert called["any"] is False


# ── sync_item branching by backend ────────────────────────────────────────────

class TestSyncItemBranching:
    """Verify sync_item picks the calendar route when backend=calendar."""

    def _setup_project(self, tmp_path, monkeypatch):
        proj = tmp_path / "🌀test-proj"
        proj.mkdir()
        (proj / "agenda.md").write_text(
            "# Agenda\n\n## ✅ Tareas\n\n- [ ] X (2030-05-15) ⏰10:00\n")
        # Stub config so neither path tries to write to a real fs.
        monkeypatch.setattr(gsync, "_load_config",
                             lambda: {"reminders_backend": "calendar",
                                      "agenda_calendar": "test-cal"})
        monkeypatch.setattr(gsync, "_get_project_tipo",
                             lambda p: "investigacion")
        monkeypatch.setattr(gsync, "_is_gsync_configured", lambda: True)
        monkeypatch.setattr(gsync, "_calendar_app_running", lambda: True)
        monkeypatch.setattr(gsync, "_ensure_agenda_calendar", lambda n: True)
        monkeypatch.setattr(gsync, "_load_ids", lambda p: {})
        monkeypatch.setattr(gsync, "_save_ids", lambda p, ids: None)
        return proj

    def test_calendar_backend_routes_to_agenda_event(self, tmp_path, monkeypatch):
        called = {"agenda": 0, "reminders": 0}

        def fake_agenda(cal, item, proj, desc, kind, dry_run=False):
            called["agenda"] += 1
            return "uid-x"

        def fake_reminders(*a, **k):
            called["reminders"] += 1
            return "should-not-run"

        monkeypatch.setattr(gsync, "_sync_one_agenda_event", fake_agenda)
        monkeypatch.setattr(gsync, "_sync_one_to_reminders", fake_reminders)
        monkeypatch.setattr(gsync, "_SYNC_TIMEOUT", 5)  # wait long enough

        proj = self._setup_project(tmp_path, monkeypatch)
        item = {"desc": "X", "date": "2030-05-15", "time": "10:00",
                "status": "pending", "notes": []}
        gsync.sync_item(proj, item, kind="task")
        assert called == {"agenda": 1, "reminders": 0}

    def test_done_task_deletes_event_and_drops_id(self, tmp_path, monkeypatch):
        deleted = {"calls": []}

        monkeypatch.setattr(gsync, "_sync_one_agenda_event",
                             lambda *a, **k: "should-not-run")
        monkeypatch.setattr(gsync, "_delete_calendar_event",
                             lambda uid, cal: deleted["calls"].append((uid, cal)) or True)
        monkeypatch.setattr(gsync, "_load_ids",
                             lambda p: {"task::X::2030-05-15": {"gcal_id": "old-uid"}})
        monkeypatch.setattr(gsync, "_save_ids", lambda p, ids: None)
        monkeypatch.setattr(gsync, "_SYNC_TIMEOUT", 5)

        proj = self._setup_project(tmp_path, monkeypatch)
        # Re-stub _load_ids after _setup_project to override its lambda
        monkeypatch.setattr(gsync, "_load_ids",
                             lambda p: {"task::X::2030-05-15": {"gcal_id": "old-uid"}})

        item = {"desc": "X", "date": "2030-05-15", "time": "10:00",
                "status": "done", "notes": []}
        gsync.sync_item(proj, item, kind="task")
        assert deleted["calls"] == [("old-uid", "test-cal")]


# ── Milestone routing to per-tipo events calendar (v0.29.2) ───────────────────

class TestMilestoneRoutesToEventsCalendar:
    """Milestones now live in the per-tipo events calendar instead of the
    workspace agenda calendar — keeps them visible alongside events."""

    def _setup_project(self, tmp_path, monkeypatch, ids=None):
        proj = tmp_path / "🌀test-proj"
        proj.mkdir()
        (proj / "agenda.md").write_text(
            "# Agenda\n\n## 🏁 Hitos\n\n- [ ] Submit paper (2030-05-15)\n")
        monkeypatch.setattr(gsync, "_load_config",
                             lambda: {"reminders_backend": "calendar",
                                      "agenda_calendar": "agenda-cal",
                                      "calendars": {"investigacion":
                                                    "events-cal"}})
        monkeypatch.setattr(gsync, "_get_project_tipo",
                             lambda p: "investigacion")
        monkeypatch.setattr(gsync, "_is_gsync_configured", lambda: True)
        monkeypatch.setattr(gsync, "_calendar_app_running", lambda: True)
        monkeypatch.setattr(gsync, "_ensure_agenda_calendar", lambda n: True)
        monkeypatch.setattr(gsync, "_load_ids", lambda p: dict(ids or {}))
        monkeypatch.setattr(gsync, "_save_ids", lambda p, ids: None)
        monkeypatch.setattr(gsync, "_SYNC_TIMEOUT", 5)
        return proj

    def test_pending_milestone_goes_to_events_calendar(
            self, tmp_path, monkeypatch):
        seen = {"cal_name": None}

        def fake_agenda(cal, item, proj, desc, kind, dry_run=False):
            seen["cal_name"] = cal
            return "new-uid"

        monkeypatch.setattr(gsync, "_sync_one_agenda_event", fake_agenda)
        proj = self._setup_project(tmp_path, monkeypatch)

        item = {"desc": "Submit paper", "date": "2030-05-15",
                "status": "pending", "notes": []}
        gsync.sync_item(proj, item, kind="milestone")

        assert seen["cal_name"] == "events-cal"

    def test_task_still_goes_to_agenda_calendar(
            self, tmp_path, monkeypatch):
        seen = {"cal_name": None}

        def fake_agenda(cal, item, proj, desc, kind, dry_run=False):
            seen["cal_name"] = cal
            return "new-uid"

        monkeypatch.setattr(gsync, "_sync_one_agenda_event", fake_agenda)
        proj = self._setup_project(tmp_path, monkeypatch)

        item = {"desc": "Do thing", "date": "2030-05-15",
                "status": "pending", "notes": []}
        gsync.sync_item(proj, item, kind="task")

        assert seen["cal_name"] == "agenda-cal"

    def test_done_milestone_deletes_from_events_and_legacy_agenda(
            self, tmp_path, monkeypatch):
        """Terminal status removes the event from the events calendar AND
        best-effort from the legacy agenda calendar so a pre-v0.29.2
        leftover gets cleaned up on the way out."""
        deleted = []
        monkeypatch.setattr(gsync, "_delete_calendar_event",
                             lambda uid, cal: deleted.append((uid, cal)) or True)
        monkeypatch.setattr(gsync, "_sync_one_agenda_event",
                             lambda *a, **k: "should-not-run")

        ids = {"milestone::Submit paper::2030-05-15": {"gcal_id": "stale-uid"}}
        proj = self._setup_project(tmp_path, monkeypatch, ids=ids)

        item = {"desc": "Submit paper", "date": "2030-05-15",
                "status": "done", "notes": []}
        gsync.sync_item(proj, item, kind="milestone")

        # First delete on events-cal (current location), then on agenda-cal
        # (legacy location). Both are best-effort but both must be attempted.
        assert deleted == [("stale-uid", "events-cal"),
                           ("stale-uid", "agenda-cal")]

    def test_migration_cleans_up_old_agenda_event(
            self, tmp_path, monkeypatch):
        """When sync_one_agenda_event returns a NEW uid (i.e. it created the
        event in the events calendar because the stored uid pointed to a
        different calendar), the stale uid in the agenda calendar must be
        deleted."""
        deleted = []
        monkeypatch.setattr(gsync, "_delete_calendar_event",
                             lambda uid, cal: deleted.append((uid, cal)) or True)
        monkeypatch.setattr(gsync, "_sync_one_agenda_event",
                             lambda *a, **k: "fresh-uid")  # ≠ "legacy-uid"

        ids = {"milestone::Submit paper::2030-05-15":
               {"gcal_id": "legacy-uid", "orbit_id": "abc12345"}}
        proj = self._setup_project(tmp_path, monkeypatch, ids=ids)

        item = {"desc": "Submit paper", "date": "2030-05-15",
                "status": "pending", "notes": []}
        gsync.sync_item(proj, item, kind="milestone")

        assert deleted == [("legacy-uid", "agenda-cal")]

    def test_no_migration_when_uid_unchanged(
            self, tmp_path, monkeypatch):
        """Updating an existing ms (uid stays the same) must NOT trigger the
        agenda-calendar cleanup — there's nothing legacy to delete."""
        deleted = []
        monkeypatch.setattr(gsync, "_delete_calendar_event",
                             lambda uid, cal: deleted.append((uid, cal)) or True)
        monkeypatch.setattr(gsync, "_sync_one_agenda_event",
                             lambda *a, **k: "same-uid")

        ids = {"milestone::Submit paper::2030-05-15":
               {"gcal_id": "same-uid", "orbit_id": "abc12345"}}
        proj = self._setup_project(tmp_path, monkeypatch, ids=ids)

        item = {"desc": "Submit paper", "date": "2030-05-15",
                "status": "pending", "notes": []}
        gsync.sync_item(proj, item, kind="milestone")

        assert deleted == []

    def test_no_events_calendar_skips_sync(
            self, tmp_path, monkeypatch):
        """If no calendar is configured for the project's tipo and no default
        is set, milestones silently skip (same posture as events)."""
        monkeypatch.setattr(gsync, "_load_config",
                             lambda: {"reminders_backend": "calendar",
                                      "agenda_calendar": "agenda-cal",
                                      "calendars": {}})  # no per-tipo, no default
        monkeypatch.setattr(gsync, "_get_project_tipo",
                             lambda p: "investigacion")
        monkeypatch.setattr(gsync, "_is_gsync_configured", lambda: True)
        monkeypatch.setattr(gsync, "_calendar_app_running", lambda: True)
        monkeypatch.setattr(gsync, "_load_ids", lambda p: {})
        monkeypatch.setattr(gsync, "_save_ids", lambda p, ids: None)
        monkeypatch.setattr(gsync, "_SYNC_TIMEOUT", 5)

        called = {"n": 0}
        monkeypatch.setattr(gsync, "_sync_one_agenda_event",
                             lambda *a, **k: called.__setitem__("n", called["n"] + 1) or "uid")

        proj = tmp_path / "🌀test-proj"
        proj.mkdir()
        item = {"desc": "Submit paper", "date": "2030-05-15",
                "status": "pending", "notes": []}
        gsync.sync_item(proj, item, kind="milestone")

        assert called["n"] == 0
