# draft_structura

*2026-03-09 — 💻orbit*

---

Ideas sobre la structura de Orbit

Sobre gestión de un proyecto:

* orbit debe usar sistemas facilmente editables (preferentemente md) y trazables (git). 
* orbit tiene dos contribuidores: el usuario y Orbit (el sistema en si, que denotaremos con la primera letra en mayúsculas)
* orbit es un sistema para anotar  en un diario entradas (un apunte en una fecha) con el fin de poder facilitar la búsqueda y trazabilidad del proyecto. Cada entrada tiene un tipo: idea, apunte, referencia, problema, decision, resultado, evaluación. ¿Las entradas deberían ser permanentes?
* orbit es un sistema para poder anotar reseñas (elementos más relevantes de un proyecto) mediante etiquetas, de tal forma que sean fácilmente accesibles y trazables. Cada reseña tiene un tipo: idea, apunte, referencia, problema, decisión,  resultado, evaluación. Las reseñas podrían eliminarse.
* orbit permite un sistema de citas para organizar el desarrollo temporal del proyecto. Deben ser trazables y verficiar su conclusión. Cada cita tiene un tipo: recordatorio, evento, tarea, objetivo. Las citas podrían eliminarse.
* El usuario y Orbit pueden añadir, editar las entradas del diario del proyecto
* El usuario y Orbit pueden añadir, editar y eliminar las reseñas del proyecto
* El usuario y Orbit puede añadir, editar y eliminar las citas del proyecto
* El usuario puede pedir la vision del proyecto (eventos, citas) y su diario (entradas)

Sobre gestión de varios proyectos

* orbit permite manejar varios proyectos y hacer búsqueda de entradas, reseñas o citas.
* orbir permite revisar la actividad de los proyectos en un periodo, entradas, reseñas  y citas.

-----




---
  Tres entidades, dos autores                                                                                             
                                                                                                                          
  La distinción clave que propones es:                                                                                    
                                                                                                                          

  │     Entidad      │ Permanente │     Autores     │               Función               │
  │ Entrada (diario) │ Sí         │ Usuario + Orbit │ Trazabilidad cronológica            │
  │ Reseña           │ No         │ Usuario + Orbit │ Conocimiento destilado del proyecto │  
 │ Cita             │ No         │ Usuario + Orbit │ Compromiso temporal                 │

  Esto es conceptualmente más limpio que el modelo actual, donde el logbook.md mezcla los tres roles con hashtags.

---
  Mapeo con el sistema actual

  Propuesta          →  Actual
  ─────────────────────────────────────────────────────
  Entradas (diario)  →  logbook.md          ✓ bien mapeado
  Reseñas            →  logbook.md (tags)   ✗ mezclado con entradas
  Citas              →  proyecto.md#tareas  ✗ incompleto (solo tareas)

  El problema actual: las reseñas no tienen identidad propia — son entradas del logbook filtradas por tipo. Esto funciona
  para buscar, pero no para editar ni eliminar de forma controlada.

---
  Preguntas que me genera el modelo

  Sobre entradas:
  - Si son permanentes, ¿puede Orbit añadir entradas automáticas? (ahora lo hace con eventos de calendario, por ejemplo). ¿Esas también son permanentes? => sí
  - ¿La "evaluación" como tipo de entrada tiene sentido en el diario, o es más una reseña? => Sí, puede ser una evaluación parcial

  Sobre reseñas:
  - ¿Una reseña es una destilación de una o varias entradas, o es independiente? => las dos, a veces es la destilacion de varias entradas otras es una reseña externa que no estaba en el diario (aunque se puede añadir a él)
  - ¿Tiene sentido que una reseña tenga fecha (origen) aunque sea editable? => No, son destilaciónes y no veo necesidad de que tengan fecha. ¿ventajas e inconvenientes? Suguerencia.
  - Los tipos propuestos (idea, apunte, referencia, problema, decisión, resultado, evaluación) son los mismos que las entradas — ¿es intencional? Si no, ¿en qué difieren? => las entradas son destilaciónes de varias entradas, un input externo al proyectos, o entradas del diario que se consideran esenciales.

  Sobre citas:
  - "Objetivo" como tipo de cita es interesante — diferente de tarea en que no tiene fecha concreta sino un horizonte. ¿Cómo se verifica su conclusión? => Cambiemosle por "hito", serían objetivos parciales del proyecto. Por ejemplo, el focus actual (trabajar en un proyecto esta semana podría ser un hito del proyecto mission)
  - ¿Un evento es algo que ocurre (pasado/futuro) y un recordatorio es una alerta? ¿Se solapan? => Un evento es una reunión, un congreso, algo que tienen su periodo de tiempo. Todas las citas pueden tener ring, el recordatorio sería simplemente una nota de atención al usuario sobre ese asunto del proyecto, podría convertirse en una tarea, (i.e: evalua el estado del proyecto). ¿pros y cons de solo haya tareas? Sugerencia.

---
  Una posible estructura de ficheros

  proyecto/
  ├── diario.md       ← entradas cronológicas (append-only)
  ├── reseñas.md      ← secciones por tipo, editables
  ├── citas.md        ← lista de citas con estado, editables
  └── proyecto.md     ← índice: tipo, estado, prioridad, objetivo

  Esto es más explícito que el logbook.md actual, donde todo convive.

-----

---
  Puntos débiles conceptuales a resolver antes de implementar

  1. Frontera diario ↔ reseña
       ¿Cómo se promueve una entrada a reseña? ¿Manual siempre? ¿Puede Orbit sugerir? Sin esto, las reseñas quedarán vacías en  la práctica — el usuario siempre irá al diario. => No. Mi experiencia es que anoto sobretodo referencias en el diario y tambien resultados (por ejemplo links a presentaciones)

  2. Ciclo de vida del hito
       Un hito no es binario. ¿Tiene estados? (pendiente / en curso / alcanzado / cancelado). ¿Cómo se evalúa su conclusión?  ¿Hay sub-tareas asociadas o es solo narrativo? => Idealmente sí a las dos, pero por simplicidad podemos dejar al hito sencillo como binario (si/no completado), pero si tiene una fecha límite.

  3. Trazabilidad de eliminaciones
       Si las citas y reseñas se pueden eliminar, ¿queda rastro en el diario? Para que el sistema sea realmente trazable, una reseña eliminada o un hito cancelado debería generar una entrada automática en el diario. Si no, hay agujeros en la historia del proyecto. => No se cómo manejar el borrado de reseñas y citas. Si la reseña o cita la añade o modifica Orbit hay una marca [0] y [emoji-cohete], pero, ¿cómo manejamos  el borrado?

  4. Autoría de Orbit
       Cuando Orbit genera entradas automáticas (eventos de calendario, reportes), ¿cómo las distingue el usuario de las suyas?   Sin marcado, la autoría se pierde => una marca con [0] u el emoji para visibilidad del usuario.

  5. Granularidad del fichero
       Con diario.md, reseñas.md y citas.md por proyecto, la búsqueda cross-proyecto sigue siendo la misma. Pero ¿el formato interno de cada fichero está claro? Por ejemplo, ¿reseñas.md es una lista plana por tipo, o tiene secciones? Esto afecta a lo que Orbit puede leer y escribir de forma fiable. => Aquí es importante que Orbit pueda leerlo de forma fiable y el humano de forma visible. Yo como humano prefiero separción por seccion del tipo de reseña y tipo de cita. Pero espero tus sugerencias

       -----

        Las reglas quedan así:                                                                                                  
                                                                                                                                 
                                            
         │        Evento         │  Fichero de trabajo  │             Diario              │
           │ Añadir reseña o cita  │ Se añade             │ —                               │
           │ Editar reseña o cita  │ Se modifica          │ —                               │
         │ Borrar reseña         │ Se elimina           │ Entrada [borrada] automática    │
         │ Completar tarea [x]   │ Se marca y permanece │ Entrada [completada] automática │
         │ Alcanzar hito [x]     │ Se marca y permanece │ Entrada [alcanzado] automática  │
         │ Cancelar tarea o hito │ Se elimina           │ Entrada [cancelada] automática  │

       

       ----

       Conclusión de la estructura del proyecto:

         # Mission
         - Tipo: 🌀 Investigación
         - Estado: activo
         - Prioridad: alta
         - Objetivo: desarrollar método de calibración relativa para detectores

         ## Estado actual
         Resumen breve del momento del proyecto — escrito y mantenido por el usuario.
         Actualización libre, no parseada por Orbit.

       ---
         [diario](./diario.md) · [reseñas](./reseñas.md) · [citas](./citas.md) · [notas](./notas.md)

       -------

       Conclusión del estado y la prioridad:

         ┌───────────────┬────────────────────────────────────┬───────────────────────────────────────────┐
         │     Campo     │         Quién lo gestiona          │                  Cuándo                   │
         ├───────────────┼────────────────────────────────────┼───────────────────────────────────────────┤
         │ Estado        │ Orbit (auto) o usuario (declarado) │ Continuo / cuando el usuario quiere fijar │
         ├───────────────┼────────────────────────────────────┼───────────────────────────────────────────┤
         │ Prioridad     │ Usuario                            │ En revisión periódica (mensual)           │
         ├───────────────┼────────────────────────────────────┼───────────────────────────────────────────┤
         │ Foco reciente │ Orbit (derivado del mission log)   │ Automático, solo en reportes              │
         └───────────────┴────────────────────────────────────┴───────────────────────────────────────────┘
