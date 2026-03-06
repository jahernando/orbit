# Logbook — 🌀hk-ana-es

<!-- Tipos: #idea #referencia #tarea #problema #resultado #apunte #decision -->



2026-03-06 Presentacion de Alberto sobre GNN #apunte

2026-02-05 #apunte
  - Presentación de Alberto sobre GNN with neutron detection
  - Diego has found a bug in his simulation due to the units of the ball
  - Invite the japonés, Yano-san, to DIPC to discuss the production of the NiCf ball
  - discusión de como construir la bola para evitar que no tenga agujeros y puedan suportar la presión (una mezcla en vacío?, usar epoxy?, hacer los test de alta presión en alta mar?)

2026-01-30 #apunte
  - IWCTE next week - lesson learned about the sources
  - Questions about the sources (question to Lauren):
  - Is the WCTE Ni ball being used in IWCD? => Yes
  - How are we proceeding with the Cf source procurement? => KeK?
  - Changes to the umbilical and deployment (cc'd Oli here too as the CDS payout system is likely changing) => Oli?
  - Requirements for the Cf activity (less urgent point) => 10 uCu (almost)
  - Paper of sources => structure of the paper (next week)
  - Production of the sources of FD => Yano - Visita al DIPC
  - HK - simulation of data NiCf WCSIM - 10uC = 3.7e5 Bq
  - NiCf ball 6, 9, 12 cm radius and several spots
  - distribution on the nhits/pmt per 1e6 events in different spots and identify the pmts with less hits
  - Diego: WCTE - Sources - NiCf
  - discussion about the gain and the hits in the bottom of the detector, why?
  - proposal to reduce the bkg candidates using ToF
  - Alberto: GNN in WCTE for n-capture

2026-01-09 #apunte
  - WCTE and HK collaboration meetings (Helena y Elena en persona, del 1-20 de febrero)
  - Preparation of preliminary results with the sources in HK (use of WCSim with HK)
  - Maybe there is some problems with the stats with empty events. [ ] Diego starting the simulation
  - Presentation about the WCTE update of the sources analyses
  - round table:
  - HA: discussion with other collaborations about Low Energy detection in WCTE. Discussion about the nature of the bkg-sample.
  - AS: starting the software code and preparation to the reconstruction of neutron with AmBe in WCTE
  - PR: Atmospherics in HK based on SK. Excel with tasks (pag. meeting: https://hkdbweb.in2p3.fr/meetingplanner.htm). Possible tasks: systematics, relation with the neutrons (use simulation). Develop the oscillation program using also the derivative of the oscillation probability. references: https://github.com/pabloferm/CHIC, https://arxiv.org/abs/2512.16427
  - ER: increasing the stats for the single-pe calibration of the PMTs.
  - DC: revising the results of NiCf, possibility that Teresa’s results are buggy. Obtaining rasonable QE comparing with the Sim.

2025-12-28 #apunte
  - Helena y Elena van al CM de febrero
  - Helena has reserved 11k€ for the NiCf construction for IWCT, os ICTE delayed respect schedule?

2025-11-28 #apunte
  - Preparation of the source technical (writing the technical paper). Is a WCTE paper ? Does Johs want to contribute?
  - Discutir con Pablo para proponer un trabajo sobre oscilaciones para Diego
  - Discussion about
  - presentation Helena (AmBe)
  - propmt 15us and then 150 us (neutron)
  - no gain if extending the search in between readout windows
  - Alternative method to obtain the n-hits and Dt distribution of random coincidences using the AmBe run data.
  - After a pair of prompt candidate + neutron best candidate is found, generate n-virtual prompts interspaced by dt and repeat the search, for each search fill the n-hits and DT histogram
  - => consider the case there are no fake neutron candidates in the sample only the real neutron candidate in the data, what distributions you will obtain with your method? What it will be the right answer: no-entries as there are no fake candidates.
  - Alternative: select readout windows with no pair, generate a virtual prompt and do the seach.
  - Better plot: n-candidates in window, DT and n-hits, in 1D and 2D, for all pair and the best pair (the candidate with more nhits)

2025-11-28 #apunte
  - Preparation of the source technical (writing the technical paper). Is a WCTE paper ? Does Johs want to contribute?
  - Discutir con Pablo para proponer un trabajo sobre oscilaciones para Diego
  - WCTE preparation paper of the holoscope paper - contribution of Josh on the in the MC
  - Elena has results with the laser ball about the calibration of the PMT
  - CfNi finish documentation for CERN (Josh, Jorge)
  - AmBe weights
  - Do simulation of the sources (radius of CfNi for HK) and AmBe (Helena)
  - Simulate CfNi inside the WCSim (Diego)
  - Estimate the hits from CfNi and estimate trigger efficiency (Diego)
  - Estimate center seed for reconstruction using trios of hits (Diego)
  - Try Leaf for low energy reconstruction (Diego)
  - Recuperate a ResNet of CNN for reconstruction (Diego, JA)
  - Recuperate NN for gamma/electro separation (Josh, JA, Helena)

2025-10-03 #apunte
  - Código de análisis de datos de WCTE para n-tagging
  - Helena presentará los resultados de n-tagging in el meeting de WCTE

2025-09-12 #apunte
  - HK
  - Transparencias for neutrinos in Renata
  - Installation and feeds (how to pay them)
  - Talk about SHOGUN - @Fracisco
  - HK-USC
  - Construction of the sources for HK - @Francisco
  - ND280 - missing manpower
  - WCTE
  - AmBe source
  - readjunting the time to have a continuous
  - Fit the exponential with a constact
  - What are the diferencies of the 1st bin and the rest for the t-time

2025-06-13 #apunte
  - New
  - Decommissioning of the detector, what to do with the structure, give it to CERN - september
  - Send the sources before august -> Elena can do it in the mid July
  - Data
  - Light collection seems to be 0.6 respect the MC
  - Elena looking at the data with the BeamMonitor
  - Carla working with selecting the AmBe sample
  - pion scattering and production of neutrons. Study first the pion reconstruction. using MC to estimate of production of neutron and signal
  - Diego
  - He imposes a veto in the T8 (5+4 us, niths > 300 hits)

2025-08-06 #apunte
  - sobre las fuestes (Vale lo que hablamos José Ángel/Diego)
  - NiCf:
  - La bola iría para Japón (se lo habría que comentar a Mark y preguntarle a dónde exactamente)
  - El Cf se desactivaría en un par de años. Hay que preguntarle a Mark si lo quieren igualmente, en caso de que no podría venir al IGFAE y alguien de nuclear podría darle una salida (ya sabemos con quien hablar)
  - AmBe: Mark dijo que no es interesante para IWCD pero habría que preguntarle de nuevo
  - La caja y el BGO se enviarían a Japón de ser queridas o de nuevo vendrían al IGFAE e igual alguien puede sacarle provecho
  - El AmBe nos va a enterrar a todos, así que allá donde vaya puede ser útil

2025-06-02 What to do about the sources at CERN (we leave them at CERN?), the ball can be send it to WCTE #apunte

2025-02-21 #apunte
  - USC/DIPC
  - General
  - Jun 26 to deliver the covers in zona franca
  - WCTE is working. Beam time.
  - IWCTE (Spain), NiCf, AmBe
  - Sources
  - Still unclear with the DAQ, Water and electric. 26 talk is full and in operation.
  - Offline trigger for low
  - weight for the AmBe source - drawing from Oliver
  - DC at CERN f 10/3-16/3, use of the CDF
  - Go after the eastern [!]
  - Weights solution from Oliver [!!]
  - sources paper
  - simulation of the rate: NiCi (one mPMT) 250 Hz ok of data, AmBe simul (200 kHz) [!!] Check that the DAQ can support this rate
  - Reconstruction
  - Use of CF to use LEAF (maybe interesting), Xiaoem,
  - C++ is hard to take for LEAF
  - pi scattering and reconstrucction with neutrons,
  - Thorsten about for fiTQun,
  - Software workshop together
  - GNN for hits bkg/noise
  - Gonzalo Diaz presentation [!!!]
  - IWCD Facility
  - Floating system (Spain?), ardiactive sources (Spain), detector tank and support structure (Spain)
  - Assembly 4/2027 10/2027, to be ready in 2028
  - facility cost cover by Japan, but some detector components still missing
  - supermodule frame is the biggest concern, water system, trigger system

2025-01-21 #apunte
  - USC/DIPC
  - General
  - 1st test of the covers working!
  - WCTE is working. Beam time.
  - Sources
  - weight for the AmBe source - drawing from Oliver
  - DC at CERN from 24/2-1/3, or 10/3-16/3
  - Go after the eastern [!]
  - Add weight to the sources => solution from Oliver [!!]
  - sources paper
  - Reconstruction
  - data in temporal windows that overlap
  - GNN for hits bkg/noise
  - Gonzalo Diaz presentation [!!!]

2024-11-12 #apunte
  - USC/DIPC
  - General
  - WCTE is working. some PMT are dead, some are dead, 20 PMTs.
  - Sources
  - Nick: January (DAQ and mPMT), February (calibration, beam - end of match)
  - Calibration with Cf, Am (we need a weight for the Am source - Oliver)
  - Go after the eastern [!]
  - 10 ms of windows, 5 ms in each starting time
  - Cf working, increase of the rate fine
  - Add weight to the sources
  - Reconstruction
  - GNN for hits bkg/noise

2024-11-12 #apunte
  - USC/DIPC
  - General
  - WCTE is working. some PMT are dead, some are dead, 20 PMTs.
  - Sources
  - Cf working, increase of the rate fine
  - Add weight to the sources
  - Reconstruction
  - GNN for hits bkg/noise

2024-11-12 #apunte
  - USC/DIPC
  - General
  - Sources
  - Permits to move the sources
  - Can we do a test with water before putting it into the tank?
  - NB Josh for the CfNi
  - Reconstruction
  - GNN for hits bkg/noise

2024-11-12 #apunte
  - USC/DIPC
  - General
  - working with DAQ, trigger in WCTE, mPMT maybe taking care of the DAQ
  - 3-4 months in 2025
  - paper with Akira
  - check the plenaries of the HK CM
  - Sources
  - AmBe new measurement is OK - Diego Costas.
  - 49 week (1st December) - only Cf - Ball the 1st of December
  - Document of the sources (Josh)
  - CERN documentation (@Radioprotection group)
  - what is the rate or the time to calibrate (1 hour per position?)
  - Reconstruction
  - Leaf: Lorenzo (Tokio) tuning with PMT - Step of the size in detector
  - problems with the installation,
  - GNN Martin's in CESGA
  - WatchMal in GNN in the respository look

2024-11-05 #apunte
  - USC
  - General
  - working with DAQ, trigger in WCTE
  - 3-4 months in 2025
  - paper with Akira
  - CERN documentation
  - Sources
  - AmBe what happens with the intensity
  - week of the ball the 1st of December
  - what is the rate or the time to calibrate (1 hour per position?)
  - Reconstruction
  - Leaf: Lorenzo (Tokio) tuning with PMT - step of the size in detector
  - problems with the installation,
  - GNN Martin's in CESGA
  - WatchMal in GNN in the respository look

2024-10-29 #apunte
  - USC/DIPC
  - General
  - no está clara la situación de WCTE
  - WCTE taking data
  - End of May is the dismainteling.
  - excel of shifts.
  - Sources
  - AmBe status - @ waiting response
  - week of the ball the 1st of December
  - Reconstruction
  - Leaf: Lorenzo (Tokio) tuning with PMT - step of the size in detector
  - GNN Martin's in CESGA
  - WatchMal in GNN in the respository look

2024-10-15 #apunte
  - USC
  - General
  - WCTE with beam during the week
  - shifts for calibration 2-3 december
  - Sources
  - With epoxy hidro-fóbico for HK ball
  - Schedule for the use of the Ball [??] -> Do test with the ball (Oliver maybe do some tests)
  - Reconstruction
  - Leaf: Lorenzo (Tokio) tuning with PMT - step of the size in detector
  - GNN in the CESGA
  - Helena coding a general

2024-10-15 #apunte
  - USC
  - General
  - WCTE filling the water.
  - Meeting on friday
  - Sources
  - Ball at CERN (@Diego to store the sources in a save place)
  - CERN document of the sources (How to get this document?)
  - AmBe source replacement? (@Diego)
  - Schedule for the use of the Ball [??] -> Do test with the ball (Oliver maybe do some tests)
  - Reconstruction
  - NiCf (trigger?), What is the size of the bin width and the pe. width
  - Do simulation of the sources (radius of CfNi for HK) and AmBe
  - Simulate CfNi inside the WCSim
  - Estimate the hits from CfNi and estimate trigger efficiency
  - Estimate center seed for reconstruction using trios of hits
  - Try Leaf for low energy reconstruction
  - Recuperate a ResNet of CNN for reconstruction
  - Recuperate NN for gamma/electro seeparation
  - Helena has the WCSim code installed in the DIPC
  - multivertex with FitQun (Lois)

2024-09-24 #apunte
  - USC/DIP
  - General
  - WCTE filling the water.
  - Sources
  - CERN document of the sources
  - DIPC has still not send the ball to CERN
  - Reconstruction
  - NiCf (trigger?),
  - Do simulation of the sources (radius of CfNi for HK) and AmBe
  - Simulate CfNi inside the WCSim
  - Estimate the hits from CfNi and estimate trigger efficiency
  - Estimate center seed for reconstruction using trios of hits
  - Try Leaf for low energy reconstruction
  - Recuperate a ResNet of CNN for reconstruction
  - Recuperate NN for gamma/electro seeparation

2024-09-24 #apunte
  - USC/DIP
  - General
  - WCTE Installation of the WT, next beam pipe
  - Sources
  - CfNi
  - Enclosure water test done (no leaks inside the source)
  - Decision of use the ball as it is (no epoxy layer)
  - Fit of the rod inside the ball done (2 o-rings spare)
  - AmBe
  - Source intensity maybe 1/10 smaller (CERN to replace it)
  - Enclosure water leak test done
  - Enclose at CERN already
  - Sources for HK
  - Do simulations
  - Reconstruction
  - Do simulation of the sources (radious of CfNi for HK) and AmBe
  - Simulate CfNi inside the WCSim
  - Estimate the hits from CfNi and estimate trigger efficiency
  - Estimate center seed for reconstruction using trios of hits
  - Try Leaf for low energy reconstruction
  - Recuperate a ResNet of CNN for reconstruction
  - Recuperate NN for gamma/electro seeparation

2024-07-30 #apunte
  - group meeting
  - general
  - pago hotel - gerencia gestion de asuntos economicos hotel Madrid
  - Praga - comprobar las dietas
  - Septiembre 9 to 23, septiembre 30/09 Septiembre 01/10 - 14/10-21/10 CERN. Installaion T9. 1- 15 Nov. funds?
  - sources
  - Sources reference documentation at WCTE
  - Operation:
  - twice-three times neutron source
  - Ni ball (calibration of the PMTs)
  - Safety meeting, responsible person.
  - Do a list: at DIPC, at CERN
  - material sent to the water tests.
  - test-beam
  - paper status well received. almost completed. JR preparing a NB as internal note.
  - WCTE
  - reconstruction
  - n-tagging: 40% eff tagging, 75% eff of the tagging. (26% eff in SK)
  - What is the time to have the water. 370 n/s activity => 145 n/s, 5 min, 20 kevts.
  - DC simulating difference locations of the source
  - TFG
  - Mario -

2024-07-19 #apunte
  - source meeting
  - NiCf - ball
  - test the stick (close the stick), with sealing paste (JP, JR) - o-ring -
  - cover with epoxy (maybe ?) - what are the water test at UK?
  - Connection to the CDS (Oliver in charge)
  - sources - one of the sources ready, Cf-252? (Radio Protection (Sofouane RP)
  - AmBe
  - connections to the CDS done
  - test not leaks done
  - source be received in 3 weeks
  - deployment
  - October ?

2024-07-02 #apunte
  - general
  - WCTE run status
  - shifts of assembly (Josh maybe in august, Diego starting in September)
  - sources
  - Sources reference documentation at WCTE
  - Operation:
  - twice-three times neutron source
  - Ni ball (calibration of the PMTs)
  - Safety meeting, responsible person.
  - Do a list: at DIPC, at CERN
  - material sent to the water tests.
  - test-beam
  - paper status well received. almost completed. JR preparing a NB as internal note.
  - WCTE
  - reconstruction
  - n-tagging: 40% eff tagging, 75% eff of the tagging. (26% eff in SK)
  - What is the time to have the water. 370 n/s activity => 145 n/s, 5 min, 20 kevts.
  - DC simulating difference locations of the source
  - TFG
  - Mario -

2024-06-18 #apunte
  - general
  - HK meeting next week
  - Praga y Boloña.
  - extend the CERN user contract- Josh
  - WCTE: n-capture, beam, calibration?
  - Renat
  - sources
  - Bruno: send the parts for the seaks tests to Matt
  - BGO, verify that the box to put the BGO inside
  - Josh is worry about of how to set all the things together and how? (??)
  - prepare a plan of action.
  - test-beam
  - Meeting- revisiting for the next week.
  - Geant4 for lead-glass studies almost done, more?
  - making a new version of the paper. Pull into a note.
  - WCTE
  - About the logos of the presention - JAH for the presentations
  - reconstruction
  - Discuss with Gonzalo about pyfiTQun.
  - Simulation with Gd 100k kg de Gd in 4 ton Water.
  - Dark Noise simulations is the main bkg. Is the simulation right (??)
  - TFG (Mario, NN), Sebas next week.

2023-06-11 #apunte
  - general
  - curso bien, lectures from Cowen, ML - ok, symposium with busseness,
  - HK meeting next week
  - hoja de pedido
  - extend the CERN user contract
  - email WTCE - software & analysis talk
  - sources
  - Mechanical done: video.
  - Do we send it to CERN o we transport ourselves?
  - Covering the ball with epoxy, maybe not uniforme. Plan to paint next week.
  - preparing some test to send to Matt to England
  - BGO in DIPC.
  - Josh is worry about of how to set all the things together and how? (??)
  - prepare a plan of action.
  - test-beam
  - Meeting: Josh revisiting the test-beam analysis, maybe studing the gamma peak
  - Geant4 for lead-glass studies almost done, more?
  - making a new version of the paper. Pull into a note.
  - WCTE
  - About the logos of the presention JAH for the presentations
  - reconstruction
  - Discuss with Gonzalo about pyfiTQun.
  - Simulation with Gd 100k kg de Gd in 4 ton Water.
  - Dark Noise simulations is the main bkg. Is the simulation right (??)
  - TFG (Mario, NN), Sebas next week.

2023-05-30 #apunte
  - general
  - HK meeting next week
  - sources
  - Mechanical. Done (in principle).
  - Covering the ball with epoxy, maybe not uniforme. Plan to plaint next week.
  - Still not clear what to do with the extremes of the stick that holds the ball, maybe in Imperial.
  - BGO in DIPC.
  - The cage for the AmBe almost finished at Imperial. Oliver is making 3 boxes. He is sending one at DIPC.
  - Status of the sources, pending at CERN.
  - Meeting FD6 at HK!
  - test-beam
  - JR have run the new version of the analysis, no relevant changes. Allie works in several things, now how to present things in the paper. Presentation for the 10th junio.
  - Geant4 for lead-glass studies almost done, more?
  - Put information into the technical note. Add the plot of the calibration of the momenta. Discussion of the errors.
  - WCTE
  - About the logos of the presention JAH for the presentations
  - reconstruction
  - Discuss with Gonzalo about pyfiTQun.
  - Simulation with Gd 100k kg de Gd in 4 ton Water.
  - Dark Noise simulations is the main bkg. Is the simulation right (??)
  - TFG (Mario, NN), Sebas next week.

2023-05-23 #apunte
  - general
  - Moving of the office
  - sources
  - Mechanical. School working on it. End of the month.
  - Next paint with epoxy to cover the holes. Maybe better with exposy for the seak test.
  - BGO in DIPC.
  - The cage for the AmBe almost finished at Imperial, then to test
  - how the status of the sources at CERN, they will arrive before septiember. We made the end-user formulary. Niel is the chief of the HK calibration (IWCTE, WCTE).
  - What will be the size of the ball for HK. 9 cm in the Master thesis of Diego.
  - Niel for the laser diffuser, end of October, of November, 1st diffuser and then NiC. After the mechanical of the stick to graph the ball. In principle no problem with the water.
  - test-beam
  - JR have run the new version of the analysis, no relevant changes. Allie works in several things, now how to present things in the paper. Presentation for the 10th junio.
  - Geant4 for lead-glass studies almost done, but worry about Akira asking to do more work.
  - WCTE
  - Bolonia school -> DC for the school of Bologna Ask for the logos in the presentations
  - ICHEP talk, Ask for the logos in the presentations JAH
  - 2200 € budget travel Ask Sonia to pay the hotel
  - reconstruction
  - Discuss with Gonzalo about pyfiTQun.
  - Simulation with Gd 100k kg de Gd in 4 ton Water.
  - Dark Noise simulations is the main bkg. Is the simulation right (??)
  - TFG (Mario, NN), Sebas next week.

2023-05-07 #apunte
  - general
  - Moving of the office
  - sources
  - Mechanical. Francisco visiting the school! -> Francisco about the mechanical
  - BGO in DIPC. What to do with the source when we have finish the operation?
  - how the ball and the stick are, discussion with the radio-protection section of CERN
  - when to finish the ball for the WCTE deployment [??] Important!
  - test-beam
  - new version of the analysis, JR looking how to this version works in the tagged gamma paper
  - Geant4 for lead-glass, small differences, z-position of the gamma, slightly energy depositions.
  - check the material and the PMT
  - WCTE
  - Bolonia school -> DC for the school of Bologna
  - ICHEP talk,
  - reconstruction
  - Discuss with Gonzalo about pyfiTQun
  - Simulation with Gd 100k kg de Gd in 4 ton Water.
  - Dark Noise simulations is the main bkg. Is the simulation right (??)
  - TFG (Mario, NN), Sebas next week.

2023-04-24 #apunte
  - general
  - Moving of the office
  - sources
  - Mechanical. Francisco visiting the school. Francisco about the mechanical
  - Diseño del BGO (Oliver), What to do with the source when we have finish the operation?
  - WCTE office, en-user of the office JR
  - test-beam
  - JR presentation,
  - use of the lead-glass calibration, when is available?? (Manur-Cadada)
  - TOF estimated momentum with protons in the hodoscope data
  - Beam momenta calibration x-check with the field-map calculations
  - Lead Glass simulation (problems maybe with the scintillation DC)
  - Photon flux measurement, (how many particles are per spill??)
  - Extrapolation of the field map , the ToF measurement of the beam momentum.
  - WCTE
  - 11/09 date to start of the installation. We wait to help to fall
  - WCTE 2022 Lauren info. Alie presentations with the test-beam for the talk at ICHEP
  - Bolonia school, DC for the school of Bologna
  - reconstruction
  - We can run FitQun pre-fit. Some technical issues generates.
  - graphs NN for neutrinos (WatchMal), ResNet from Josh !
  - Dark Noise simulations is the main bkg. Is the simulation right (??)
  - TFG (Mario, NN), Sebas next week.

2024-04-16 #apunte
  - general
  - presentation ICHEP, DC
  - sources
  - mechanical school testing the ball (Francisco)
  - BGO status? (mid-april) JR
  - enclosure leaks, testing
  - WCTE office, en-user of the office JR
  - test-beam
  - Use of the timing analysis JR
  - x-check of the calibration with the lead glass.
  - study of the pedestal
  - study of lead-glass e/gamma
  - There is a problem with the b-field measurements and the approximations
  - Extrapolation of the field map , the ToF measurement of the beam momentum.
  - WCTE
  - 11/09 date to start of the installation. Integrations meetings Maybe DAQ.
  - reconstruction
  - selection of n-candidates, 10 us windows, consecutive candidates take the larges n-digits,
  - FitQun pre-fit, there is some technical issues
  - graphs NN for neutrinos (WatchMal)
  - Dark Noise simulations is the main bkg
  - TFG (Mario, NN) , TFM (Jaime, simulación gammas/electrons for the test-beam)

2024-02-20 #apunte
  - general
  - @DC Abstract in ICHEP or neutrinos
  - sources
  - AmBe: CERN preparing the sources, 6 months,
  - Josh is preparing the handling at CERN of the sources
  - End user documents, document => JAH signature, then @JR send to Valerie
  - Purchase of the BGO ongoing (mid-April to receive the BGO)
  - Mechanical work on the ball, but still pending with the school or Donostia lab. Francisco and Jorge.
  - test-beam
  - Is this working?
  - x-check of the calibration with the lead glass.
  - There is a problem with the b-field measurements and the approximations
  - Extrapolation of the field map , the ToF measurement of the beam momentum.
  - WCTE
  - 11/09 date to start of the installation. Integrations meetings.
  - reconstruction
  - WCsim source PR merged!
  - datatools from Gonzalo
  - FitQun pre-fit, there is some technical issues
  - graphs NN for neutrinos
  - Dark Noise simulations is the main bkg
  - @DC ask Pablo how to simulate the AmBe
  - TFG (Mario, NN) , TFM (Jaime, simulación gammas/electrons for the test-beam)

2024-02-20 #apunte
  - general
  - End abstract with ICHEP, and Neutrinos @DC with Akira
  - sources
  - AmBe: CERN invoice. Alva preparing the folla de pedido, @JSR.
  - BGO: @JR ask the budget for the BGO.
  - mechanical work on the ball, still pending with the school or Donostia lab.
  - @JR preparation of the talk
  - test-beam
  - Akira has asked for more things. @JR discussion with Akira.
  - reconstruction
  - select the relevant variables and try to reconstruct the neutrons
  - finish the PR of the source with WCSim @DC
  - @DC ask Pablo how to simulate the AmBe
  - TFG (Mario, NN) , TFM (Jaime, simulación gammas/electrons for the test-beam)
  - @JR ask Akira what he wants to simulate for, otherwise propose to Jaime to validate the N/BGO simulation

2024-02-20 #apunte
  - General
  - No beam in 2024 in principle
  - Wikipedia - done!
  - send abstract with ICHEP, and Neutrinos @DC
  - sources
  - AmBe: CERN invoice, @JSR
  - BGO: done and sent to the company @BGO
  - mechanical work in the school or Donosti lab, the possibility of making soak test at Donistia
  - Test the BGO after the CM
  - test-beam
  - some pending issues concerning the calibration, and timing.
  - reconstruction
  - finish the PR of the source with WCSim @DC

2024-02-06 #apunte
  - Bureaucracy
  - Trips for the CM 4/3 and 11/3
  - Done with the CERN documents of the DC
  - sources
  - BGO @JR ask for quotes again, AmBe @JR (ask for a quote from Stephanie)
  - Mechanical test - end of March. New plans to be sent to JR,
  - Explore if we can do it in the DIPC labs (in spring)
  - Test the BGO after the CM
  - presentation at pre-meeting CM about calibration
  - test-beam
  - paper, comments JA comments, NIM or JINST
  - reconstruction
  - Now the trigger and the dighit maching
  - JR has a NN for regression at CESGA
  - Mail to CESGA about the scentific production JR
  - Elena (Pablo's student) wants a discussion about the neutron tagging.

2024-01-30 #apunte
  - Bureaucracy
  - JR Ask Lauren about the plans for the CM (4/3-8/4) DC ask about the doctorate official time for a state
  - Most likely 2 weeks in march
  - JAH check status of the project
  - DC Do the CERN documents
  - sources:
  - JAH boy the BGO with GAES, @follow IGFAE for the AmBe
  - JR plans for the installation (tank discussion about august, maybe data in october)
  - maybe test in Donostia tests with the source
  - JR mechanical of the ball ask the status again
  - test-beam
  - meeting discussion, L at 16:00
  - other team-beam papers
  - reconstruction
  - presentation
  - problems with the triggers, but maybe if we increase the trigger window, we can get all the info. It seems 10 PMTs

2024-01-23 #apunte
  - Bureaucracy
  - JR, DC will go to the CM, (1st and maybe 2nd week of March), waiting the discussion with Lauren
  - Diego documents? JR has already extended his CERN contract as user.
  - check the status of the budget!
  - sources:
  - JR will have a meeting with the enterprise that does the mechanical of the NiBall
  - Ask the BGO (2 k€) and the AmBe (5 k€) JA ask IGFAE, JJ
  - test-beam
  - Paper committee JR, DC, JAH. Review paper
  - simulation/reconstruction
  - Number of photons per 2 MeV gamma, 0.005 probability, and 2000 PMTs, ~10 PMTs. DC to produce gamma 2 MeV.

2024-01-09 #apunte
  - CERN bureaucracy
  - Diego documents
  - sources:
  - use of the DAQ source, ToolDAQ, what is the plans?
  - define the trigger and the calibration procedures, Josh
  - NiBall has been sent to the mechanical workshop.
  - test-beam
  - paper with the tag photon paper
  - simulation/reconstruction
  - link between true with digit-hits

2023-12-12 #apunte
  - :
  - sources
  - WCTE calibration meeting, understanding how to use the DAQ, they want to know the threshold of our trigger (how many DigitHits for NiBall and AmBe?). JR computing the number of NDigitHits.
  - For the neutron, we need to buffer length and threshold, to discuss with them the DAQ software
  - test-beam
  - JR will ask Akira about what are his plans for the article
  - simulation/reconstruction
  - fix the hits creation origin. Discussion about the DigitHit.
  - issue
  - divulgation

2023-11-28 #apunte
  - :
  - divulgación
  - charga y la página del instituto
  - sources
  - Calibration of WCTE, discuss with the DAQ group, to get the calibration data, Tool-DAQ,
  - Meeting with the DAQ and mPMTs. 1st with Diffusion (Imperial). Next calibration meeting dedicated to this. (starting at CERN in feb)
  - ball sent to the school to be mechanized
  - prepare the sending of the material with epoxy to do the soak tests
  - prepare the test, we can do it at CERN. Feb/Mar/April - test, deployment of the sources.
  - simulation/reconstruction
  - fix the hits creation origin.
  - divulgation

2023-11-21 #apunte
  - :
  - sources
  - Calibrations in WCTE. Lauren
  - What about the DAQ, special events, how to precess the data? @How are in charge? @JR
  - Rate AmBe 300 Hz de neutrons with 100 muCu. How many events do we need?? What exactly we want to reconstruct? (eff rec., resolution energy and position, uniformity?)
  - prepare the sending of the material with epoxy to do the soak tests
  - prepare the test, we can do it at CERN. Feb/Mar/April - test, deployment of the sources.
  - LSC talk (end of May? ), production of the mPMTs(?).
  - simulation/reconstruction
  - 2 PRs, generator AmBe has a its seed.
  - Processes of the hit creation, some issues
  - divulgation

2023-11-14 #apunte
  - :
  - AmBe (??), 100 muCu of activity => 300 Hz,
  - How much time do we have to stay in the detector? (TFG)
  - NiCf: 1000 fotones/s (per muC), 10 muCu, 1000 s para M pes, (15'), 1 día
  - Compute for AmBe
  - Questions related with the deployment system.
  - some events on the tail may from interaction of gammas in the magnets
  - now requiring that the events pass by a collimator trigger
  - 26% there is no gamma and 40% of the events have pes from scintillation

2023-11-24 #apunte
  - :
  - AmBe (??), 100 muCu of activity,
  - How much time do we have to stay in the detector? (TFG)
  - NiCf: 1000 fotones/s (per muC), 10 muCu, 1000 s para M pes, (15'), 1 día
  - Compute for AmBe
  - Questions related with the deployment system.
  - some events on the tail may from interaction of gammas in the magnets
  - now requiring that the events pass by a collimator trigger
  - 26% there is no gamma and 40% of the events have pes from scintillation

2023-10-24 #apunte
  - :
  - @JR brain-storming for the test!!
  - @JR ask for the edition and next comments in the test-beam paper
  - @DC preparing material
  - Starting with the machining
  - preparing the epoxy layer to send to the soak tests
  - next week in WCTE (next Monday)
  - article in GitHub and presented in the beam-test meeting
  - still looking at the tail and the last section of the article
  - PR for the BGO in WCSIM, send n and gammas with the AmBe spectrum, gives access to the data
  - validation of the simulation, what is relevant,
  - recover the resources
  - talk for neutrinos.

2023-10-24 #apunte
  - :
  - @JR test-beam article into overleaf
  - @JR brain-storming for the test!!
  - @JAH follow status of the Cf purchase
  - @DC brain about the reconstruction
  - @DC brain about the outreach
  - Sources
  - The soak test may is not needed for WCTE, for HK we need to cover the ball with epoxy
  - BGO last crystal to buy next year
  - Status of the source
  - test-beam
  - Note of the test-beam almost ready => contact Akira
  - reconstruction
  - finish the simulation WCSim, prepare for a GitHub
  - how to do the reconstruction? (brain-storming)
  - outreach
  - brain structure for the

2023-10-17 #apunte
  - :
  - Ask Francisco about the status WCTE?
  - @Josh Quote BGO => HEP Saborido
  - @Akira asking about the status of the test-beam article
  - @JR, @JAH budget code and how to pay the sources!! CERN o Abraham
  - @JR brain-storming for the test!!
  - @JAH, @JR prepare the TFM and TFG (maybe requires the access to CERGA)
  - Presentations for the students!
  - notes
  - general
  - possibility on September due to the tank construction (Pablo dixit)
  - sources
  - seak tests: Matt presentation, AmBe plastic is OK, NiO (some contamination in 3 months, how is the relevance depending on the wavelengths) => text with the epoxy.
  - NEXT ball to make the 3rd ball this week.
  - Buying of the source on progress. Ask CERN to deliver in a few months. 10-100 photons per PMTs muCu, we have 10 muCu in the source.
  - reconstruction:
  - DC: Installation of WCsim, last release in the CESGA and computer, with interactive views
  - add some variables to the n-tuples.
  - test-beam:
  - The problem with the multiple-peaks in LG was due to how to selection was done, as fraction of the maximum peak, and in some events the maximum peak is weak an then it let us pass noise.

2023-10-03 #apunte
  - :
  - Ask Francisco about the status WCTE?
  - @Josh Quote BGO => HEP Saborido
  - @Akira asking about the status of the test-beam article
  - @JR, @JAH budget code and how to pay the sources!! CERN o Abraham
  - @JR brain-storming for the test!!
  - @JAH, @JR prepare the TFM and TFG (maybe requires the access to CERGA)
  - Presentations for the students!
  - notes
  - outreach
  - presentation for guide de bachelor students
  - sources
  - we try to buy in the sources purchasing
  - advancing in the Ni ball
  - Francisco to recover the plastic for the BGO
  - Oliver (imperial) has the physical connection to hold the source.
  - soak test was fine, now doing a long time test @Mattiew
  - Deadline: March - 2024
  - test-beam:
  - working on the hodoscope analysis (what are the events in the tail) How to define a veto??
  - analysis
  - discussing Thomas (responsible of GHOST)
  - add scintillation en WCSim BGO,
  - what is the particle that generates the photon that detected.
  - WCSim standard (official release) installed in CESGA!!
  - => generate events to reconstruct neutrons.

2023-09-12 #apunte
  - :
  - Ask Francisco about the status WCTE?
  - @Berta BGO IGFAE?
  - @JR structure of the paper of the test-beam
  - @JR, @JAH budget code and how to pay the sources
  - @JAH, @JR prepare the TFM and TFG (maybe requires the access to CERGA)
  - sources:
  - we should have a budget code at CERN, @JAH
  - e-mail @Stefania to buy the sources
  - BGO could be from the IGFAE @Berta-IFAE
  - test-beam:
  - comparison of the tail events on the Glass and the horoscope
  - now after selecting 1 peak the distribution of the events on the tail is heavely reduced
  - analysis:
  - installation of the tagged WCSim (CERGA), gcc8.4, change of the compiler, GEANT4,

2023-09-12 #apunte
  - :
  - @JR mail to Mark and Akira about the budget code
  - sources:
  - Cf source, Stefanía del CERN, @Stefanía, Buged code at CERN??, LHCb Code??
  - IGFAE Pay during the month of October!
  - BGO - Enero ?? Ahora
  - simulation:
  - Beam test - Akira. Study the tail of the calorimeter distributions mm

2023-09-12 #apunte
  - :
  - CM meeting - no it, Atención al test-beam
  - Viaje del CERN de Josh, dietas!
  - WCTE delays with the mPMTs de Poland
  - Josh goes to Donosti in 2 weeks
  - How to do the neutron reconstruction (?) Discuss with Pablo.
  - WCTE-sim new version in an "official" repository
  - Josh wants to move in Donosti the last ball prototype and the stick and the missing parts
  - Sources:
  - Compra del BGO, discuss with Juan or Carlos
  - Presupuesto de las fuentes, hablar con Carlos
  - @JR Josh will talk with CERN about how, when pay the sources
  - Oliver (Imperial) is looking for the stick to enter the sources in WCTE, @JR Josh asks Oliver, otherwise Donosti
  - Simulation
  - Write up about the calibration sources (deadline Q3)
  - reconstruction of the neutrons. 1st use the MC to select neutrons and first simple reconstructions 2nd use NN from Pablo. WatchMal
  - Installation of WCTEsim in CESGA?
  - Test-beam analysis
  - the tail of the Pd-Glass spectrum, events with more than 1 gamma, e+e-, loss of 1 e, and then the deposit has less energy.
  - runs with less radiation length, but without enough statistics to conclude the effect of the tail of the Pn
  - compute the sigmas of the energy of the lead-glass calorimeter with respect E.
  - Why the selection is so hard (?) ask Josh

2023-05-16 #apunte
  - :
  - JAH buy the tickets
  - @JR about the Team- Leader. @JAH Quien Firma por la Universidad
  - @DG Search for the AmBe spectrum.
  - administrative
  - 1M events (gamma/electron!
  - sources:
  - trying to make the ball, some problems with the excess of the material
  - mechanics of the bar and the ball
  - plans of the soak tests, send the material and the bar, we need to decide what mix to use, before the end of May
  - BGO purchases, contacting the company
  - simulation/reconstruction
  - work with Digit Hits.
  - 200 ns, 3 DigitHits, the window (-1, +1).
  - Simulation with the gamma/neutron at the same time
  - parameterize el spectro de AmBe
  - def selection, reconstruction, t-life of n, and the eff-selection. , Bonsai.
  - ML
  - Similar e/gamma IWCE (time and charge)
  - Simulation of the test-beam
  - new B-field, now more deflection.

2023-05-09 #apunte
  - @JAH CERN users and accounts for USC in WCTE
  - @JAH sends an email to Mark about the status of the IGFAE in the WCTE
  - @JAH with Carlos about the sources and the CERN budget code
  - @JR CERN funding account
  - @JAH about the keys to enter in the Geneva apartment!
  - @JR Pedido of the BGO
  - @JR ask for the size of the source to be sure they fit in,
  - @DC spectrum of the original neutron.
  - @DC be sure that the AmBe sources is OK
  - sources:
  - The material in DIPC!
  - when the mold will arrive, we prepare a new ball with less solid mass, and more smooth
  - soak test, different elements, at least 2 pieces, con y sin Gd in the, during this month. During this month (May)
  - BGO purchases from Santiago (Hoja de Pedido)
  - simulation/reconstruction
  - BGO in WCSim, Centelleo in WCSim, Centelleo in PMTs ok
  - the neutrons also produce scintillation but they are not treated in WCSim (2 cm of radius)
  - simulations gammas, 4.4 MeV, neutrons 1-10 MeV uniform, with DR, DR+QE, DR+QE+CE.
  - number of DigitHits [DR+QE+CE] [100 digits per gamma, 14 Ch-Hits]
  - seems ok
  - Times Digit and True seems ok
  - Migrate the production to CESGA (10k events in each configuration)
  - ML
  - Generated 100 k without the seed problems, AuC, gamma/electrons slightly worse,
  - Input: Array of Charge and Time.
  - Now with 1M now maybe there is some separations
  - Simulation Beam-Team
  - New field map in the simulation.

2023-05-05 #apunte
  - Wet test for the sources in preparation
  - By the sources requiring a CERN account, possible to use Abraham's/Diegos' [??] Open an account after the MoU signature?

2022-05-02 #apunte
  - JR, DC Ask Akira about the dates of the test-beam!
  - @JAH can we cut the stick to 30 cm?
  - @DC about the test of the sources.
  - @JR buy the two external pieces of BGO.
  - @DC will try to implement the BGO inside the WCSim
  - @JR repeating the production of 1M data for WCTE
  - sources:
  - JR: envio of the boxes to DIPC
  - Water tests:
  - prepare pieces to do the test. During this month.
  - two designs for the BGO box
  - stick of the AmBe next
  - Diego:
  - out-layers of the reconstructions.
  - simulations of the nu.
  - ML
  - with new data-set with pions!
  - Beam Line simulation
  - saving information with hits

2022-04-35 #apunte
  - @DC when to use the set-up
  - Test-beam: July-4th (DAQ, monitoring)
  - GD: fitQun, note T2K,
  - tool to get the information from WCSim
  - DC:
  - tools of Nicks, trying to understand Bonsai, time-residuals, to use the x4 hits for the 9 MeV
  - JR:
  - ML: 1 M events, with electrons/gammas, 260 keV - 1 MeV. Using WatchMal, and RestNet, maybe the problem with the timing is solved, time, charge!
  - Beam simulation: hodoscope to estimate the gamma energy
  - Magnet - simulation is crucial
  - Sources:
  - Barra metra-kilato:
  - BGO crystals.

2022-04-18 #apunte
  - JR contact Akure for the test beam. DC 19/07-31/07
  - August's discussion with CERN about the Californio source
  - What about the CM, 22/6
  - DC, JAH to talk with Hector, of the performance
  - JR test of the water for the ball.
  - @Sonia about the metra-quilato.
  - @DC runs muons with the current version of WCSim
  - @DC y @GD to fix the info of the WCSIM
  - Sources
  - what happens if we use less mass of the solid. 75% we look 1/3 of high energy gammas.
  - 1 uC is maybe too high for a Californium source.
  - possibility to cover with a poxy! Septiembre
  - test of U. Shieldfield.
  - BGO: a second quote. waiting for the response.
  - barra metra-quilato.
  - Simulations
  - Installation of the software, Geant4.10.3, problems: Scintillation has changed seriously, Root.6, problems with Root.7. Revisiting the script to convert into HDF5.
  - Docket container where to install the corresponding packages, and scripts.
  - Reconstruction, FitQun,
  - 1000 events, n, 1 - 10 MeV, origin, % of thermalization.
  - WCSim: npz + python (datatools), info of digithits and true-hits
  - Verify the script of Gonzalo and the one from Nick's (changed by Diego)
  - Now it works BONSAI
  - NN
  - time of the hits, offset,
  - RoC Run with/without the time.
  - Production of 1 M events, (e/muon/gamma/pi-) Energies (Ch-Threshold - 1500 MeV) + index/ hdf5 One Drive.
  - NN: ResNET: e/gamma with/without time information to check the results.
  - Neutron reconstruct with NN and comparisons
  - Beam simulation, Blear, discussion with Akira,

2022-04-11 #apunte
  - Contact: benjamin.quilain@llr.in2p3.fr
  - Wait for GD to ask Matiew about BONSAI
  - sources
  - JR buying the material NiO and Poliethileno for the sources
  - JR quote for the AmBe source for the box in principle USC
  - JR waiting for the quote, insisting!!
  - The ball is in a factory to machine it
  - Simulation
  - clean the code
  - NN
  - 1M events in WCTE, WCSim branch (develop)
  - Split at CESGA jobs, to production 1M in few days, mu, e, pi-, pi0, gammas,
  - Production of 100 k events to check the NN modules (Patrick)

2022-03-21 #apunte
  - @JR buys more material for the sources.
  - Sources
  - BGO quotes, responses still pending.
  - look inside the last probe (more mass) of the mixture to see the uniformity inside.
  - to try still new mixtures, try not to saturate the mixture, to be more liquid.
  - Simulation
  - WCsim in Diego's computer, he is able to display the detector simulation and display the geometry and the events
  - NN
  - IWCTE previous studies ML:
  - GitHub with the beam-simulation of WCTE

2022-03-21 #apunte
  - @JR buy more material for the sources (??)
  - HK-ES meeting:
  - Nominar for the EB
  - Budget for USC
  - meeting 11/04 Carlos with the ministry?
  - sources:
  - mechanical plans - discussion with the enterprise. Still looking for the company
  - to do a second ball with more epoxy, an epoxy saturation? More material. Maybe changing the composition respect SK.
  - Am/Be discussing with Alejandro about the crystals.
  - simulations:
  - improving the displays, using Nick's libraries
  - Bonsai and leaf, installation of bonsai, getting the tuples from the script.
  - NN
  - simulation of the beam! How does the simulation work?

2022-03-14 #apunte
  - WCTE Jul 3-7 CERN, May Ok, Jun Not
  - @JAH Josh Dietas, Donosti Jan23!
  - @JAH discuss with JJ about LL and CP and possible implications.
  - @JR to define the plan and schedule with dates.
  - @JR @JAH How is the responsible person of the WCTE to ask for a CERN team for USC
  - @JR budget for the BGO crystal and the plastic container
  - @JR get the presentation NN - with IWCTE.
  - @JR ask Akira about how to use NN and the beam simulations
  - Sources:
  - Machining of the ball to an industry. stress test. Does it break? (??)
  - Do a second ball? (??)
  - budget for the BGO crystals and the plastic container
  - simulations
  - neutron in-elastic and neutron capture, they are separated by clear times
  - how to put the times (??)
  - looking at the reconstruction
  - Difference between Bonsai & fitQun
  - NN
  - RoC curves with e/gamma separation with charge and hit info
  - similar results to previous studies with IWCTE
  - study of the beam, how to tag the gammas, work beam simulations (??)

2022-03-06 Set the preferences dates for the WCTE-CW #apunte

2023-02-28 #apunte
  - How to see the rings in the WCsim PMTs map.
  - sources:JR in Donosti next week!
  - simulation AmBe:
  - t-production of gamma from n-capture. No correlations, is it ok?
  - study the events with the rings for different topologies. Event with n-capture, 4 rings, that correspond to different segments of the election. the axes of the cone should intersept in a vertex.
  - pass these events to WCsim.
  - NN: e/gamma separation, generation uniform in the tank
  - gamma-conversion generation to set the gamma interaction uniformly in the tank
  - add time information of the hits (information: mean-hit per PMT) !!

2023-02-22 #apunte
  - @JAH check the institution of DC in HK!
  - FitQun: reconstruction - IFAE
  - sources: Alejandro and Francisco, trip to Donosti!
  - simulations
  - presentation
  - n-capture (74%), n-inelastic (5%), n-capture + n-inelastic (rest)
  - tipology of events, how to separate them? Events show clear Ch. rings.
  - NN simulations with gammas
  - Use of the time! (first ideas of use charge, and mean-time, and maybe rms!)

2023-02-07 #apunte
  - @JAH check the institution of DC in HK!
  - @JR budget for HK-USC, NN, computers, personnel, and sources.
  - @DC AmBe t-Ch photons, and correlation of t-Ch vs r-captura
  - No direct progress in the sources. @Pending of the DIPC.
  - Presentation at HK calibration meeting. Maybe there is some help to do the water test with the sources.
  - in AmBe simulation, 99% of the neutrons are captures, life-time 150 us, and 200 mm.
  - NN meeting, WatchMal, e/gamma some separation in WCTE. RoC curves
