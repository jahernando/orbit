# Logbook — 📚phd-martin

<!-- Tipos: #idea #referencia #tarea #problema #resultado #apunte #decision -->



2026-03-04 Discussion about the Ph.D thesis chapter on segmentation and CNN implementation, some problems with the names #apunte

2026-02-29 #apunte
  - Tasks
  - Apply first data classifier, select MC events similar to data, and then create the FE
  - No funciona tampoco el Feature Extractor casi sin entrenar y luego el data classifier.

2026-02-02 #apunte
  - Use of the UMap to study the features. The U has two clusters with signal/bkg both degradated in a region. ¿Why this separation? Looking at the correlation with the variables it seems that the NN classifies using the z-position, no other variables.
  - There is a problem using as weight p/(1-p) with p the probability of being signal [??]

2026-01-22 #apunte
  - Tesis: capítulo de introducción casi acabado
  - El esquema de peso por dominain class no parece mejorar porque la separacion de FT es ya muy buena, y simplemente da más pesos a unos eventos de MC que otros pero la NN ya sabe cómo separarlos.
  - Para estudiar cómo se agrupan las features se utiliza el método t-SNE, que coloca los eventos de forma no supervisada en un espacio 2D.
  - Existe la posibilidad de hacer un encodificador que minimiza la diferencia entre la imagen decodificada y el original, esto es, comprime la información en una imagen de dimensión inferior
  - Los métodos de pesado de la etiqueta de eventos se llaman: noise labels
  - ¿Existe una posibilidad de clasificar los eventos solo como electron? Se llama normalizing flow.
  - ![fig-02.png](./references/fig-02.png)
  - ![fig-03.png](./references/fig-03.png)

2026-01-13 #apunte
  - Ph.D tesis chapter 3 (NN) ready for next week
  - MC production of 400 k events, if selection hits inside 400 mm, reduce ro 200 k events
  - check efficiency vs z => there is no significan efect
  - removed augmentation in z
  - DS peak has a tail on the right, why? there is maybe a problem with the energy correction? This affects the fit of the DS peak as it is not gaussian anymore.
  - In the domain adversarial NN, it seems that the problems is that data/MC differs more than 80%
  - How we can compare data/MC using a list of physical and NN variables (the pre-output to the last leayer)
  - Prepare a MC/Data label classification.
  - Brainstorming of how to identify a sample (for examen un e-), of a inferred label classification (given them a weight depending on a given variable, i.e, energy)
  - ![fig-01.png](./references/fig-01.png)

2025-11-20 #apunte
  - Discusión sobre los temas y secciones de su tesis
  - tema de introducción de NN
  - tema de hipótesis en metodología para describir teóricamente los objetivos de la tesis (NN)
  - Discusión sobre la posibilidad de usar NN con dominio (para entregar con MC y datos como dominio). La idea es que la red sepa unificar dominios (datos, MC) y separar por etiquetas de un dominio (MC)
  - Uso de la red de clasificación ResNET 3D entrenada con DEP MC aplicada a los datos, funciona adecuadamente bien
  - definir cortes fiduciales, usar solamente un cluster
  - correlacionar el output de la red con variables discriminatorias (MC y datos)
  - Uso de la red del output de la red de deconvolución como feature de la red de clasificación ResNET 3D => No gain, hay mucha correlación entre la feature de la energía y la de la calsificación
  - Uso del ouput de la red de deconvolución para tolopogía, empezando por la clásica (paulina)
  - añadir columna con el output de la red y la clasificación (spine-digital) al fichero con los hits
  - Discusión sobre una zona común en el CESGA para tener IC Sería útil? => esperar hasta que haya necesidad
