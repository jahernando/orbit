# Valoración Orbit v0.1.0

**Fecha:** 2026-03-09

---

## Resumen

La v0.1.0 marca una gran mejora respecto a la versión anterior. Orbit pasa de ser un conjunto de scripts acoplados al directorio de trabajo a un sistema portable, bien testeado y con una CLI coherente. Los cambios principales de esta iteración:

- **Eliminación de mision-log/** — el diario era redundante; todo vive ahora en proyectos.
- **Editor configurable** — `ORBIT_EDITOR` en vez de Typora hardcodeado.
- **Paths centralizados** — `core/config.py` con `ORBIT_HOME` como fuente única.
- **Paquete instalable** — `pyproject.toml`, cero dependencias obligatorias.
- **Dos repos** — público (orbit, código limpio) y privado (orbit-ws, workspace real).
- **410 tests** con buena cobertura de la funcionalidad core.

## Fortalezas

- Markdown plano: sin base de datos, sin lock-in, legible con cualquier editor.
- Cada proyecto es autocontenido: project + logbook + highlights + agenda + notes.
- Git como versionado — gratis, offline, sin infraestructura externa.
- CLI con shell interactivo, match parcial de proyectos, `--open` y `--log` transversales.
- Flujo natural: agenda → log → search → report.

## Debilidades conocidas

Algunas son de naturaleza (inherentes al formato markdown) y otras son mejorables:

**De naturaleza:**
- Parsing de markdown con regex — si el usuario rompe el formato al editar manualmente, el parser puede fallar silenciosamente. Es el precio de usar texto plano.
- Emojis en paths — funciona bien en macOS/Linux pero puede ser problemático en otros entornos.

**Mejorables:**
- `orbit doctor` — falta un comando de validación de integridad del workspace.
- Autocompletado de proyectos en el shell (solo autocompleta comandos, no nombres de proyecto).
- `orbit init` — para crear un workspace nuevo con templates y mission de ejemplo.
- Separar `core/log.py` — concentra demasiadas funciones (find_project, resolve_file, etc.).
- Estado global como constantes de módulo — mejor sería funciones lazy para más flexibilidad en tests.

## Próximos pasos posibles

1. `orbit init` — onboarding para nuevos usuarios.
2. `orbit doctor` — validar formato de agenda.md, logbook.md, etc.
3. Autocompletado de nombres de proyecto en el shell.
4. Refactor de `core/log.py` → separar workspace helpers.
