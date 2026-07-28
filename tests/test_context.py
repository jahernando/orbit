"""Tests del proyecto fijado (core/context.py) — panel de proyecto, ADR-049."""

import pytest

from core import context


@pytest.fixture
def pinnable(tmp_path, monkeypatch):
    """Workspace con tres proyectos en dos tipos, listo para fijar."""
    for type_dir, names in (("💻software", ["orbit", "echo"]),
                            ("🌀investigacion", ["next-pn24"])):
        td = tmp_path / type_dir
        td.mkdir(exist_ok=True)
        for n in names:
            pd = td / f"{type_dir[0]}{n}"
            pd.mkdir()
            (pd / "project.md").write_text(f"# {n}\n")
            (pd / "logbook.md").write_text("# Logbook\n")
    monkeypatch.setattr("core.config.ORBIT_HOME", tmp_path)
    monkeypatch.setattr("core.log.PROJECTS_DIR", tmp_path)
    monkeypatch.setattr("core.config._load_types",
                        lambda: {"software": "💻", "investigacion": "🌀"})
    yield tmp_path
    context.clear()


# ── Resolución y fijado ──────────────────────────────────────────────────────

def test_pin_exact_name(pinnable):
    ok, name = context.pin("orbit")
    assert ok and name == "orbit"
    assert context.pinned() == "orbit"
    assert context.pinned_dir().name == "💻orbit"


def test_pin_accepts_name_with_type_emoji(pinnable):
    ok, name = context.pin("💻orbit")
    assert ok and name == "orbit"


def test_pin_partial_unambiguous(pinnable):
    ok, name = context.pin("pn24")
    assert ok and name == "next-pn24"


def test_pin_unknown_project_fails_with_hint(pinnable):
    ok, msg = context.pin("orbti")
    assert not ok
    assert "no encontrado" in msg
    assert "orbit" in msg          # sugerencia por cercanía
    assert context.pinned() is None


def test_pin_ambiguous_partial_fails(pinnable):
    # "o" aparece en orbit y echo → ambiguo, no se elige a ciegas
    ok, _ = context.pin("o")
    assert not ok
    assert context.pinned() is None


def test_pin_from_env_absent_is_not_an_error(pinnable, monkeypatch):
    monkeypatch.delenv("ORBIT_PROJECT", raising=False)
    ok, msg = context.pin_from_env()
    assert ok and msg == ""
    assert context.pinned() is None


def test_pin_from_env(pinnable, monkeypatch):
    monkeypatch.setenv("ORBIT_PROJECT", "echo")
    ok, name = context.pin_from_env()
    assert ok and name == "echo"


# ── Comandos transversales ───────────────────────────────────────────────────

def test_blocked_commands_only_when_pinned(pinnable):
    assert context.check_blocked(["dash"]) is None      # panel general: pasa
    context.pin("orbit")
    msg = context.check_blocked(["dash"])
    assert msg and "workspace" in msg and "orbit" in msg


def test_blocked_subcommand(pinnable):
    context.pin("orbit")
    assert context.check_blocked(["project", "create", "x"]) is not None
    assert context.check_blocked(["cloud", "sync"]) is not None
    # el mismo comando con otro subcomando sigue permitido
    assert context.check_blocked(["cloud", "deliver", "f.pdf"]) is None
    assert context.check_blocked(["project", "status"]) is None


def test_allowed_commands_when_pinned(pinnable):
    context.pin("orbit")
    for cmd in (["log", "hola"], ["save"], ["commit"], ["agenda"],
                ["search", "algo"], ["undo"], ["history"], ["doctor"]):
        assert context.check_blocked(cmd) is None, cmd


# ── Guardia contra proyectos ajenos ──────────────────────────────────────────

def test_foreign_project_is_refused(pinnable):
    context.pin("orbit")
    msg = context.check_foreign(["log", "echo", "un apunte"])
    assert msg and "echo" in msg and "orbit" in msg


def test_own_project_name_is_not_foreign(pinnable):
    context.pin("orbit")
    assert context.check_foreign(["log", "orbit", "un apunte"]) is None


def test_quoted_text_never_trips_the_guard(pinnable):
    """Un mensaje entrecomillado es UN token: no coincide exacto con nada."""
    context.pin("orbit")
    assert context.check_foreign(["log", "echo ya soporta esto"]) is None


def test_guard_is_off_in_general_panel(pinnable):
    assert context.check_foreign(["log", "echo", "texto"]) is None


def test_flag_values_are_checked_too(pinnable):
    context.pin("orbit")
    assert context.check_foreign(["ls", "tasks", "--log", "echo"]) is not None


# ── Relleno de argumentos ────────────────────────────────────────────────────

class _Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_apply_fills_empty_projects_list(pinnable):
    context.pin("orbit")
    a = _Args(command="agenda", projects=[])
    context.apply_to_args(a)
    assert a.projects == ["orbit"]


def test_apply_respects_explicit_projects(pinnable):
    context.pin("orbit")
    a = _Args(command="agenda", projects=["orbit"])
    context.apply_to_args(a)
    assert a.projects == ["orbit"]


def test_apply_fills_search_project_as_list(pinnable):
    context.pin("orbit")
    a = _Args(command="search", project=None)
    context.apply_to_args(a)
    assert a.project == ["orbit"]


def test_apply_fills_scalar_project(pinnable):
    context.pin("orbit")
    a = _Args(command="doctor", project=None)
    context.apply_to_args(a)
    assert a.project == "orbit"


def test_apply_disables_federation(pinnable):
    context.pin("orbit")
    a = _Args(command="agenda", projects=[], no_fed=False)
    context.apply_to_args(a)
    assert a.no_fed is True


def test_apply_is_noop_in_general_panel(pinnable):
    a = _Args(command="agenda", projects=[], no_fed=False)
    context.apply_to_args(a)
    assert a.projects == [] and a.no_fed is False


# ── Gramática: el posicional desaparece al fijar ─────────────────────────────

def test_pinned_parser_drops_the_project_positional(pinnable):
    import orbit
    context.pin("orbit")
    args = orbit._build_parser().parse_args(["log", "un apunte suelto"])
    assert args.project == "orbit"
    assert args.message == "un apunte suelto"


def test_unpinned_parser_still_requires_the_project(pinnable):
    import orbit
    args = orbit._build_parser().parse_args(["log", "echo", "un apunte"])
    assert args.project == "echo"
    assert args.message == "un apunte"


def test_pinned_parser_on_optional_positional(pinnable):
    import orbit
    context.pin("orbit")
    args = orbit._build_parser().parse_args(["ls", "hl"])
    assert args.project == "orbit"


def test_pinned_parser_typed_verb(pinnable):
    import orbit
    context.pin("orbit")
    args = orbit._build_parser().parse_args(["task", "add", "escribir el ADR"])
    assert args.project == "orbit"
    assert args.text == "escribir el ADR"


# ── Cableado en el shell y en run_command ────────────────────────────────────

def test_run_command_refuses_workspace_command(pinnable, capsys):
    import orbit
    context.pin("orbit")
    assert orbit.run_command(["dash"]) == 1
    assert "panel general" in capsys.readouterr().out


def test_run_command_refuses_foreign_project(pinnable, capsys):
    import orbit
    context.pin("orbit")
    assert orbit.run_command(["log", "echo", "un apunte"]) == 1
    out = capsys.readouterr().out
    assert "echo" in out and "orbit" in out


def test_run_command_blocks_after_verb_entity_swap(pinnable, capsys):
    """`add project` se normaliza a `project add`; el bloqueo va después."""
    import orbit
    context.pin("orbit")
    assert orbit.run_command(["create", "project", "nuevo"]) == 1
    assert "panel general" in capsys.readouterr().out


def test_light_startup_fires_nothing(pinnable, monkeypatch):
    from core import shell
    called = []
    monkeypatch.setattr(shell._hooks, "fire", lambda *a, **k: called.append(a))
    shell._run_startup(light=True)
    assert called == []
    shell._run_startup(light=False)
    assert called != []


def test_history_file_is_per_panel(pinnable):
    from core import shell
    general = shell._history_path(None)
    project = shell._history_path("orbit")
    assert general != project
    assert project.name.endswith("-orbit")


def test_env_pins_one_shot_invocations_too(pinnable, monkeypatch, capsys):
    """ORBIT_PROJECT vale para `orbit <cmd>`, no sólo para `orbit shell`."""
    import orbit
    monkeypatch.setenv("ORBIT_PROJECT", "orbit")
    assert orbit.run_command(["dash"]) == 1
    assert "panel general" in capsys.readouterr().out


def test_invalid_env_aborts_the_command(pinnable, monkeypatch, capsys):
    import orbit
    monkeypatch.setenv("ORBIT_PROJECT", "no-existe")
    assert orbit.run_command(["agenda"]) == 1
    assert "ORBIT_PROJECT" in capsys.readouterr().out
