# Logbook — 🌀hk-sources

<!-- Tipos: #idea #referencia #tarea #problema #resultado #apunte #decision -->



2026-02-27 #apunte
  - (Slack-Canvas)
  - Discusión with Diego sobre los pasos a seguir, como sacar el DR y el signal Rate de los candidatos, y las pdfs de tiempo, rms-tiempo y n-hits de la señal.
  - Discusión sobre los siguientes pasos para calcular la ganancia y verificar los otros métodos de calibracion
  - Discusión para verificar que Bonsai is workin

2026-02-26 Para el trabajo de Diego, sacar la comparación del spe con la laser ball y las calibraciones #apunte

2026-02-20 #apunte
  - Discusion en el Canvas sobre los spills y cómo mejorar la pureza de la muestras
  - ¿cuál es el tamaño de la readout-window? => 500 us (5e5 ns)
  - La elección de 5000 ns para buscar spill, de dónde viene
  - inspeccionando eventos en promedio 800-900 hits duraban como 5000 ns,
  - además hay after pulsing, in 3000 ns aprox, con algo menos de hits
  - Por lo tanto se quita el spill de 9000 ns
  - Definición de spill
  - spill in 5000 ns hay > 300 hits y se quita 5000 ns + 4000 ns = 9000 ns
  - Mantenemos la eliminación de los spills, con 300 hits pero añadimos la contabilidad
  - ¿Cuántos spill estoy quitando por readout-window?
  - Distribución del número de hits en el spill (en 5000 ns y en los 4000 ns posteriores)
  - Mantenemos la selección de un candidato si en 20 ns hay entre 10 y 60 hits
  - Pero eliminamos ese candidato si en la ventana extendida [200, 20 + 200] hay alguna otra acumulación de hits > 10 en 20 ns (que podemos llamar flash). Esto es en la ventana extendida solo está ese candidado con >10 hits
  - Llevamos la contabilidad de cuántos candidatos tiramos
  - Podemos jugar con el tamaño de la ventana extendida, cambiarla a 100 a ver qué pasa
  - Calculamos la pureza de la muestra a partir de la distribución de candidatos por read-out window en B y S+B
  - Hacemos los plots tc (donde tc-es el tiempo promedio del candidato), t-rms, y nhits
  - en la ventana del candidato.
  - en la ventana extensa calculamos el numero de hits en el pre-trigger y en el post-trigger, también el t-promedio de los hits pre-trigger y post-trigger
  - A partir de las distribuciones anteriores vemos si podemos poner cortes para aumentar la pureza de la muestra
  - calculamos la pureza de la muestra de la distribución de candidatos en B, y S+B
  - A partir de aquí hacemos la comparación de los candidatos seleccionadas con el MC (pero seguramnete hay tenenmos que hacer algo con la posible contaminazión), pero ya vemos en su moment

2026-02-18 #apunte
  - NiCf what we want: a very pure selection of signal events, then compute the charge distribution (or hits) per PMT and substract, if possible, the background distributions. We can obtain the geometrical distribution n-hits or charge distribution (per candidate).
  - => we can compare with MC expectacions and obtain the ratio.
  - NiCf Canvas shows that in readout window we hace 4.34 candidates in bkg+sig and 1.52 in bkg, therefore 2.81 signal candidates per readout window, the signal fraction is therefore: 0.65 (65%)
  - => we can always use this method: compute the average number of candidates per readout-window in B, B+S samples, and from there compute the expected distributions or average values of the S-sample
  - => and alternative is to compute the total number of candidates in N readout-windows for the B and B+S samples, and therefore we can substract them, and then normalizing to the N_S candidates N_S = N_B+S - N_B.
  - It shows that the t0-averafe in 20 ns time of the candidates is 4.4 ns in bkg+signal and 6.9 in bkg, that is the t0-signal is 3.3 ns
  - We can use the relation
  - that we can use for the n_hits vs PMT para estimar f_s, hace falta tener k y f_b
  - Si calculamos siempre en número de candidatos por readout window (después de la selección que apliquemos) obtenemos k a partir del número de candidatos total y en del bkg!, y a partir de ahi podemos obtener f_s
  - ![fig-01.png](./references/fig-01.png)

2026-02-11 Discussion with Xiaoé sobre la distribución temporal de candidatos, #apunte

2026-02-05 Discussion about the paper, next meeting first of march #apunte

2025-11-21 #apunte
  - data files for /mnt/lustre/scratch/nlsas/home/usc/ie/dcr/hk/nicf_data/data en el CESGA,
  - Los files se llaman: run_1766_signal_N20candidates_unfiltered.csv y run_1767_signal_N20candidates_unfiltered.csv
  - to send a job in CESGA:
  - to set the env.

2025-11-20 #apunte
  - Connect to ft3.gal.es using VS SSH
  - set the environment:
  - use the python envt:
  - Python 3.9 (shared venv)
  - Main NB:
  - restart_analsys.ipynb
  - read data is in runs and particion
  - each partition has an readout window
  - read the hits
  - finds the bkg spills and remove those hits
  - select nhits in a 20 ns windows, compute t-rms and q-nhits, make a selection
  - store the nhits into a data-frame style indexed by number of candidate
  - To show the events use EventDisplay
  - internally converts the channel ID to (x, y, z) positions
