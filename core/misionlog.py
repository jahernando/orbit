from datetime import date, timedelta
from pathlib import Path
from typing import Optional

MISION_LOG_DIR = Path(__file__).parent.parent / "☀️mision-log"
TEMPLATES_DIR  = Path(__file__).parent.parent / "📐templates"

DIARIO_DIR  = MISION_LOG_DIR / "diario"
SEMANAL_DIR = MISION_LOG_DIR / "semanal"
MENSUAL_DIR = MISION_LOG_DIR / "mensual"


def _week_key(d: date) -> str:
    return d.strftime("%G-W%V")


def _week_bounds(d: date) -> tuple:
    monday = d - timedelta(days=d.weekday())
    return monday, monday + timedelta(days=6)


def _write(dest: Path, content: str, copy: Optional[str], force: bool) -> int:
    if dest.exists() and not force:
        print(f"Ya existe: {dest}  (usa --force para sobreescribir)")
        return 1
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content)
    print(f"✓ {'Copiado' if copy else 'Creado'} {dest}")
    return 0


# ── day ──────────────────────────────────────────────────────────────────────

def run_day(date_str: Optional[str], copy: Optional[str], force: bool) -> int:
    target = date.fromisoformat(date_str) if date_str else date.today()
    dest   = DIARIO_DIR / f"{target.isoformat()}.md"

    if copy:
        src = DIARIO_DIR / f"{copy}.md"
        if not src.exists():
            print(f"Error: no existe {src}")
            return 1
        lines = src.read_text().splitlines(keepends=True)
        if lines and lines[0].startswith("# Diario"):
            lines[0] = f"# Diario — {target.isoformat()}\n"
        content = "".join(lines)
    else:
        tpl = TEMPLATES_DIR / "diario.md"
        if not tpl.exists():
            print(f"Error: plantilla no encontrada en {tpl}")
            return 1
        content = tpl.read_text().replace("YYYY-MM-DD", target.isoformat())

    return _write(dest, content, copy, force)


# ── week ─────────────────────────────────────────────────────────────────────

def run_week(date_str: Optional[str], copy: Optional[str], force: bool) -> int:
    d      = date.fromisoformat(date_str) if date_str else date.today()
    wkey   = _week_key(d)
    mon, sun = _week_bounds(d)
    dest   = SEMANAL_DIR / f"{wkey}.md"

    if copy:
        src = SEMANAL_DIR / f"{copy}.md"
        if not src.exists():
            print(f"Error: no existe {src}")
            return 1
        lines = src.read_text().splitlines(keepends=True)
        if lines and lines[0].startswith("# Semana"):
            lines[0] = f"# Semana {wkey} ({mon.isoformat()} — {sun.isoformat()})\n"
        content = "".join(lines)
    else:
        tpl = TEMPLATES_DIR / "semanal.md"
        if not tpl.exists():
            print(f"Error: plantilla no encontrada en {tpl}")
            return 1
        lines = tpl.read_text().split("\n")
        lines[0] = (lines[0]
                    .replace("YYYY-Wnn", wkey)
                    .replace("YYYY-MM-DD", mon.isoformat(), 1)
                    .replace("YYYY-MM-DD", sun.isoformat(), 1))
        content = "\n".join(lines)

    return _write(dest, content, copy, force)


# ── month ─────────────────────────────────────────────────────────────────────

def run_month(date_str: Optional[str], copy: Optional[str], force: bool) -> int:
    if date_str:
        y, m = int(date_str[:4]), int(date_str[5:7])
    else:
        today = date.today()
        y, m  = today.year, today.month
    month_str = f"{y}-{m:02d}"
    dest = MENSUAL_DIR / f"{month_str}.md"

    if copy:
        src = MENSUAL_DIR / f"{copy}.md"
        if not src.exists():
            print(f"Error: no existe {src}")
            return 1
        lines = src.read_text().splitlines(keepends=True)
        if lines and lines[0].startswith("# Mes"):
            lines[0] = f"# Mes {month_str}\n"
        content = "".join(lines)
    else:
        tpl = TEMPLATES_DIR / "mensual.md"
        if not tpl.exists():
            print(f"Error: plantilla no encontrada en {tpl}")
            return 1
        prev_m = m - 1 if m > 1 else 12
        prev_y = y if m > 1 else y - 1
        prev_str = f"{prev_y}-{prev_m:02d}"
        content = (tpl.read_text()
                   .replace("← [Mes anterior](../mensual/YYYY-MM.md)",
                            f"← [Mes anterior](./{prev_str}.md)")
                   .replace("YYYY-MM", month_str))

    return _write(dest, content, copy, force)
