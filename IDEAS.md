# Ideas de mejora — pendientes de evaluar

Ideas que requieren reflexión antes de decidir si implementarlas.

---

### 1. Sincronización de reminders con Google

Los reminders de Orbit se programan en Reminders.app de macOS, pero si no estás delante del Mac se pierden. Sincronizarlos con Google permitiría recibirlos en el móvil.

**Opciones:**
- Google Calendar: eventos de 0 duración con alarma (visibles en el calendario)
- Google Tasks: tarea con fecha/hora (más discreto, sin ocupar espacio en calendario)
- Ambos: Calendar para los que tienen hora fija, Tasks para los genéricos

**Consideraciones:**
- Los tasks/ms/ev con `--ring` ya se sincronizan con Google y Google lanza sus propias notificaciones — no hay duplicación problemática
- Para reminders sería redundante (Mac + Google), pero la redundancia es una feature si estás fuera del ordenador
- ¿Deberían aparecer como un tipo separado en Google (lista "💬 Recordatorios") o mezclados con las tareas?

### 2. Vista agenda con recordatorios del día

La vista `agenda` muestra tareas, hitos y eventos del día, pero no los recordatorios. ¿Deberían aparecer en la agenda del día con su hora?

### 3. Recordatorios inteligentes basados en contexto

Algunos recordatorios son "si tienes tiempo y ganas" (baja prioridad). ¿Tendría sentido un campo `--priority` para reminders que controle si se programa la notificación o solo aparece en la agenda?

### 4. Historial de recordatorios atendidos

Cuando haces `reminder log`, podrías marcar automáticamente el recordatorio como "atendido" (sin eliminarlo). Así tendrías un registro de cuáles se atendieron y cuáles se ignoraron.

### 5. Notificaciones de ring en el móvil para tareas/hitos

Los `--ring` de tasks/ms/ev se sincronizan con Google, que tiene sus propias notificaciones. ¿Son suficientes las de Google o hay que añadir un recordatorio explícito en Google Calendar para que funcione bien en el móvil?
