# Logbook — 🌀next-nn

<!-- Tipos: #idea #referencia #tarea #problema #resultado #apunte #decision -->



2025-11-24 #apunte
  - Incredible images of the CNN-decov of Martín
  - From Martíns:
  - ![fig-01.png](./references/fig-01.png)

2025-11-24 #apunte
  - From the Juanjo email
  - 2 Configuration (NEXT-100 and NEXT-1000 upgrade (10 mm, 13.5bar He)
  - Roberto generará los eventos de NEXUS, pre-selecionados para que haya en ellos sólo un single track en la ventana de energía de 2300 a 2500 (computo de la eficiencia). La semana que viene comprobaremos que está todo en orden y lanzaremos la generación en Hiperión.
  - Eventos en el Cu? => script de Gonzalito usando de la actividad, qué años quería, simulaba los eventos por cada volumen.
  - Revisar las actividades Michel - DB (ultima), lanzarlos desde los volumes.
  - guardar solo eventos que solo tienen un cluster (DBSCAN ok), algunos parámetros dependiendo de la deposition de energía (distancia).
  - Roberto (2 cm)
  - Estimar la eficiencia
  - Martin tiene que pasar SEMSIN sobre esos eventos.
  - Producción de Sensim. Get values
  - Josh se ocupa de entrenar la red y sacar los resultados.
  - use of the bb that you have and the bkg CNN
  - discussion sobre b/bb separation in (NEXT100 - bb)

2025-11-20 #apunte
  - Discusión sobre la posibilidad de usar NN con dominio (para entregar con MC y datos como dominio). La idea es que la red sepa unificar dominios (datos, MC) y separar por etiquetas de un dominio (MC)
  - Uso de la red de clasificación ResNET 3D entrenada con DEP MC aplicada a los datos, funciona adecuadamente bien
  - definir cortes fiduciales, usar solamente un cluster
  - correlacionar el output de la red con variables discriminatorias (MC y datos)
  - Uso de la red del output de la red de deconvolución como feature de la red de clasificación ResNET 3D => No gain, hay mucha correlación entre la feature de la energía y la de la calsificación
  - Uso del ouput de la red de deconvolución para tolopogía, empezando por la clásica (paulina)
  - añadir columna con el output de la red y la clasificación (spine-digital) al fichero con los hits
  - Discusión sobre una zona común en el CESGA para tener IC Sería útil? => esperar hasta que haya necesidad

2024-10-08 #apunte
  - Cluster algorithm and tracking
  - Martin pre-production (100 k for bb0nu, 1eroi diffsim, and sensim),
  - not working neutrinos
  - Josh CNN-sparse
  - area 0.99, with NEXT-100 5 bar 2x2x2
  - chits from Esmeralda using Krmap-Krishan LT and now E-resolution on bb is good
  - with 2x2x2 not good results
  - chits from Esmeralda 15x15x10, NN bkg output - bkg is not 0 or 1, maybe there is a problem there
  - NEXT-White
  - Fabien working on the MC

2024-10-08 #apunte
  - Martin's detsim cities almost ready [?] Issues with the size and computing time?
  - Production of sensim Martin
  - Production with different voxels size Martin
  - Kr map and sophronia configuration of NEXT-White and NEXT-100 Gonzalo

2024-09-24 Detsim sensor production #apunte

2024-05-10 #apunte
  - Production of more stats (NEW, NEXT-100 LPR)
  - the identification of the code
  - Fabian, 3-architectures NN
  - GNN (NEW, pytorch), improvement to reduce the time (date -> hours)
  - Corey's code to produce NN (??)
  - Data/MC comparisons -presentations-
  - Documentation
  - statistics, production NEW
  - projects:
  - GNN identify double-scape peak in NEW data/MC
  - Application NN for tracking (de-convolution)
  - Energy resolution (how to train the NN with data?)
  - GNN classification LPR.
  - 500 evts in 1 min (convert to a graph): transform the hits into graphs.
  - GNN segmentation (blob)
  - CNN classification LPR
  - CNN regression - Kr maps
  - Ideas
  - Use Marias code CNN to work in the data

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
