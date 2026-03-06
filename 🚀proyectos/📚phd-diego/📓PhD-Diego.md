# Logbook — 📚phd-diego

<!-- Tipos: #idea #referencia #tarea #problema #resultado #apunte #decision -->



2026-03-04 #apunte
  - With candidates [5-60] hits in 20 ns
  - Distribution of the S = S+B - B, properly weighted by the purity
  - Xiaoyue plot:
  - Calibration plot:
  - ![fig-03.png](./references/fig-03.png)
  - ![fig-04.png](./references/fig-04.png)

2026-03-03 #apunte
  - Diego has computed the pdf for the tc, trms, nhits, of the signal, after the bkg substraction, they look quite good (3.5 ns for time)
  - The hit time distribution seems to be ok
  - Still revisiting the DR in the pre and post-trigger, it seems there is more DN in the post-trigger
  - The distribution of the charge of the PMTs with S seems to be quite good. He will fit to a gaussian to get the calibration and x-check with Helenas' results.
  - Discussion about the quantum efficiency, we can compute the relative respect one PMT
  - Discussion about the MC, consider only hits in 60 ns after the interaction to avoid reflexions.

2026-02-05 Diego has found a bug in the simulation code of the ball, -a problem with the units-, now redoing the simulation #apunte

2026-02-04 #apunte
  - - I included a pre and post trigger window in my trigger.
  - - I then compute t0 as the time difference between the first hit in the triggered candidate and the original hit time that made the trigger fire.
  - - I, as in the paper, compute t - TOF - t0, in order to find the on-time and off-time zones that represent physical signal and random noise, respectively.
  - ![fig-01.png](./references/fig-01.png)
  - ![fig-02.png](./references/fig-02.png)

2026-01-22 #apunte
  - Mapa the la QBS y QB para CfNi con la carga arriba tiene sentido
  - El cálculo de NS = NBS - NB de número de hits data y MC y su razón parece tener sentido y nos cuantifica principalmente la Qefficiency

2025-12-17 #apunte
  - Ph.D thesis about NiCf calibration in SK (pdf)
  - From data for N-samples, we can compute, Nb and Nsb, and the N(n|B+S) - N(n|B) nos da la distribución de la señal N(n|S)

2025-12-15 #apunte
  - The link for uploading the letter is the following :
  - https://reclutamento.dsi.infn.it/#!uploadLetter/20369/36731/hdKBd6Yt2dt0Eb5MGreFZ6F1WOeOXAxL
  - If the should not work you can access the page
  - https://reclutamento.dsi.infn.it/#!uploadLetter/
  - hdKBd6Yt2dt0Eb5MGreFZ6F1WOeOXAxL
  - The expiration date for uploading the letters is 18/12/2025 11:59 PM CET

2025-11-20 #apunte
  - Presentations about the NiCf source calibration (ana coordinates -local-)
  - Diegos GitHub repository for NiCf analysis

2025-06-10 Range de energías del BG0 375 nm- 650 nm (in the range of SiPM and PMTs) #apunte

2025-06-02 #apunte
  - WCTE talk about the neutrons
  - first look at the n-data (local file)
  - 100 uCi = 2.7 MBq source, expected 260 n/s and 155 trigger gammas/s, from simulation expected 80 Hz of 4.4 MeV gamma + n events
  - Concentration of Gd: 0.03% (75% capture), 0.2% (90% capture. n-time in UPureWater (250 us), in GD (20 us and 4 cm) :
  - pag5 : why the distance does not change with the concentration of Gd? Because first the neutron must thermalize and then get cpatured
  - trigger: 1800 readout window of 270 us separated 7 us and then 20 s of waiting time to recuperate the RDU (the DAQ)
  - The expected rate is 20 Hz per PMT but the measured is 1500 Hz per PMT!!
  - scintillation window 2000 ns aprox, and with 200 hits in average
  - cherenkov ling in 50 ns, and with 9.6, 37, 45 nhits per (UPW, 0.03%, 0.2%)
  - ?? Expected/Measured rate (does it make sense)
  - removing T8 spills
  - search for scintillation (1500 ns sliding window, 2500 whole window), is fins!! ( plot of the nhits in 1500 ns time-window for on/off source data)
  - ?? (what does mean after the last scintillation signal?) neutron search in 150 us ok!
  - search of n-candidatos is fine, 100 ns sliding window, 500 ns whole window. Distribution of the rate in 100 ns time-window, and the distribution of candidates / trigger (on, off)

2025-05-23 #apunte
  - 500 us trigger , 5 us bin
  - There is bkg from spills of T8 (most likely) seems to be 5 us width => veto this read window
  - in the read-window make bins of 200 ns y get the distribution of nhits and charge, get an idea of the size of the number of hits in that bines.

2025-05-12 #apunte
  - Presentation at WCTE [First look at the CfNi data]
  - MC predicts less nhits than data
  - Still the main questions remains: are we seeing the source?
