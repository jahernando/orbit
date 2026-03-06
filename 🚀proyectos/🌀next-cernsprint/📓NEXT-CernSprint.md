# Logbook — 🌀next-cernsprint

<!-- Tipos: #idea #referencia #tarea #problema #resultado #apunte #decision -->



2025-08-14 #apunte
  - GitHub of Samuelle:
  - GitHub de Martín: https://github.com/martinperezmaneiro/HE_ana/tree/main

2025-08-13 #apunte
  - for q>5 it is better without scatter hits
  - In general is better without scatter hits and with q>10, 12!
  - The scatter hits could be real but to get the best energy resolution is better to apply larger q threshold cut.
  - Studying the position distribution of the hits
  - Scatter hits are distributed in all (x, y) at an average radious 320 mm
  - Cluster hits are located on the top left quadrant, and the average is mostly bellow 400 mm in radius (as they are filtered)
  - The fraction of scatter hits respect the total is around 5% but depends on the energy, it decreases for HE
  - The fraction of the energy of the scatter hits is 1.5% and it is almost constant on energy
  - The fraction of energy seems that does not depend on the z-width of the event.
  - ![fig-10.png](./references/fig-10.png)
  - ![fig-11.png](./references/fig-11.png)
  - ![fig-12.png](./references/fig-12.png)
  - ![fig-13.png](./references/fig-13.png)
  - ![fig-14.png](./references/fig-14.png)
  - ![fig-09.png](./references/fig-09.png)
  - ![fig-07.png](./references/fig-07.png)
  - ![fig-08.png](./references/fig-08.png)

2025-08-12 #apunte
  - number of scatter hits and energy of the scatter hits depends linearly with energy
  - number of scatter hits and energy does not depends greatly with energy (small dependence)
  - The number of scatter hits and energy per z-unit is linear with respect the energy of the event per z-unit
  - All these indicate that the scatter hits are real and related with energy (if noise, will depend on the z-width for example). The linear dependence with the energy of the event and the energy deposit in z are indications that they are real.
  - With the qthreshold = 5, the number of hits increases slightly with z-width, maybe this is an indication that there is a emission with larger lifetime => we can study the same with empty S2 windows!
  - ![fig-06.png](./references/fig-06.png)
  - ![fig-05.png](./references/fig-05.png)

2025-08-06 #apunte
  - Conf
  - DE
  - PP
  - 15604 (Q>5)
  - Q>5, Sc=True, map
  - 1.29 Z-No, DZ-Yes
  - 1.18 Z-No, DZ-Yes
  - Q>5, Sc=True, map2
  - 1.46 Z-Some, DZ-yes
  - 1.19 Z-Some, DZ-yes
  - Q>5, Sc=False, map
  - 1.25 Z-Some, DZ-No
  - 1.05 Z-Some, DZ-Some
  - Q>7, Sc=True, map
  - 1.23 Z-Some, DZ-No
  - 1.07 Z-No, DZ-Some
  - Q>7, Sc=False, map
  - 1.25 Z-Some, DZ-No
  - 1.03 Z-Some, DZ-Some
  - 15590 (Q>7)
  - Q>7, Sc=True, map

2025-08-05 #apunte
  - run 15590 FWHM ((1.13, 0.99) (all hits, hits in range). No differences using 1 cluster or all
  - run 15604 FWHM ((1.19, 1.12 (all hits, hits in range). No differences using 1 cluster or all)
  - ![fig-01.png](./references/fig-01.png)
  - ![fig-03.png](./references/fig-03.png)
  - ![fig-02.png](./references/fig-02.png)
  - ![fig-04.png](./references/fig-04.png)

2025-07-29 #apunte
  - The internal Kr
  - 3 different Kr maps (LT unique, LT map, and 3D)
  - In the ideal world
  - L(x, y, dt, t) = L_tau(dt, t) L_xy(x, y) L_t(t)
  - tau is the lifetime: i.e, from the S2e vs dt inside a given radius
  - L is the average light:
  - i.e. either the S2e average close to the anode inside a radius.
  - i.e the S2e average after LT correction inside a radius.
  - Then we only need to monitor:
  - Evolution of lifetime (tau)
  - Evolution of the L_t respect a given L_0
  - => provide a K_t(t) = L_0/L_t
  - Constant validity of the L_xy (map does not change on time)
  - Kr calibration
  - set the internal parameters to a IC function to convert (x, y, dt, q, e) into (x, y, z, E)
  - validation of the tools and the map
  - monitoring the evolution of the main parameters -> histograms
  - Kr cities
  - ICAROS
  - input <- kdst
  - selection -> filter kdst
  - computation (update) of map -> map (map parameters)
  - evolution on time -> tuple
  - validation -> OK
  - monitoring -> histos
  - HE calibration
  - set the internal parameters to define a IC internal function that refines E (globally or locally (hit by hit?)
  - HE city
  - input <- sophronia's hits
  - selection -> filter soph. hits
  - computation (update) of scale -> scale (scale parameters)
  - validation -> OK
  - evolution on time -> tuple
  - monitoring -> histos
  - Test maps: (validate with same run and consecutive run)
  - LT unique
  - LT map
  - 3D map
  - Trigger: Understand the xy-distribution and the DT distribution (emulate the trigger) (need wfs of autotrigger)
  - Transverse diffussion (no SiPM cuts to get the PSFs for different DT ranges) (need wfs)
  - Scatter hits
  - It seems that remove them or correct them give equivalent results
  - Noise
  - Validate the effect of the noise S2 vs DT
  - Why we are having so many S1s?
  - Use different Kr maps (now using only one and with unique LT)
  - use Kr map per run
  - use Kr map with LT
  - use Kr 3D
  - Scatter
  - hits 'in range' remove them or correct them?
  - hits 'out of range' -> revisit the S2 selection by Irene
  - Corrections
  - Only z-correction (unique for DE and PP?)
  - ICAROS (selection, create map, monitor evolution)
  - recuperate the test-suite
  - Mere the open PRs
  - Move to latest Python
