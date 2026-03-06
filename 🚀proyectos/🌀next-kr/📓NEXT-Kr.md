# Logbook — 🌀next-kr

<!-- Tipos: #idea #referencia #tarea #problema #resultado #apunte #decision -->



2025-07-14 #apunte
  - E0 increases slowly with time, but has not jumps between runs
  - E0 bumps in ICARO are related the max-normalization (using average in square)

2025-06-11 #apunte
  - Josh about corrections using the hits
  - también en DEMO las correcciones con KDSTs funcionaban mucho mejor que con los Sophronia hits (era mejor con los hits no-corregidos que los hits corregidos)
  - la reconstrucción que estaba usando (con q_thr = 5 * pes) me daba muchos hits para un evento de Kr, entonces para un cierto evento se estaba cogiendo correcciones de partes del detector que no correspondía exactamente con el (x,y) del evento mismo. La corrección en que parecía que importaba esto bastante era la del lifetime. Después de corregir y mirar energía corregida vs. Z se veía un pendiente hacía arriba (se había "sobre-corregido" para lifetime). 2 cosas ayudaban a mejorar esto:
  - Subir q_thr (así los hits reconstruidos no extendían mucho más allá que el punto (x,y) principal). En general, ya que suele ser mejor el lifetime cerca del centro del detector, si un evento está más difundido se suele coger correcciones de "peor lifetime" que tiran en la dirección de sobre-corregir
  - Re-hacer el mapa con bins más grandes. El primer mapa que había hecho tenía fluctuaciones importantes en el lifetime, hasta entre un bin y sus vecinos inmediatos, y hacer los bins más grandes parece que ayudó con esto

2025-06-05 #apunte
  - Analysis meeting
  - MC LT with Kr (Rhianon), the problem that the LT with kdst is not the true LT in MC, comes from Dorothea or Irene, and not detsim. With detsim the results are fine.
  - Scatters hits (small pe signals) are correlated with energy, they are mostly physical, they need to be treated properly
  - Juan David in reproducing energy resolution from Sophronia got problems even converting the data into a "k-dst" style

2025-05-23 #apunte
  - Monitoring
  - Before cleaning
  - After cleaning

2025-05-28 #apunte
  - Gonzalo's studies about the PMT calibration with S1 using Kr
  - Use Kr selected pmaps (require in addition 1S1)
  - The poisson mean (LCE), pedestal noise, gain, std of the gain (normalized to LED calibration gain)
  - ![fig-13.png](./references/fig-13.png)
  - ![fig-07.png](./references/fig-07.png)
  - ![fig-09.png](./references/fig-09.png)
  - ![fig-04.png](./references/fig-04.png)
  - ![fig-10.png](./references/fig-10.png)

2025-05-22 #apunte
  - new version of IC at LSC: v2.3.1/20250512/
  - wfs are at the LSC (shifter's cluster) /analysis/15332/hdf5/data
  - got data from Kr pure run 15332 Irene (ldc1), Sophronia and 10 files of wfs ldc1
  - The run 15332 seems very similar in terms of the S2e per PMT
  - correlate with the gain
  - compute the S2e with normalized gain.
  - Look at Sophronia hits and compute compute the S2w, S2E, and S2E vs Z
  - Looks in the wfs selected Kr events and compare with no selected. (look for S2 signal in the trigger window)
  - Brain-storming meeting
  - ![fig-11.png](./references/fig-11.png)

2025-05-21 Tareas de la reunión del viernes en valencia #apunte

2025-05-13 #apunte
  - Samuele shows that the LT for PMTs seems to be consistent within errors (are the errors correct?) => check the fit, define a monitoring about
  - The pes in PMTs for Kr - there is no correlation with the gain
  - There is maybe a problem with the TPB deposited on the window (3-4 um reflection is maximum and 1 um is only 50%)? Can we check with the LED? =>

2025-10-12 Eric's comments on the Kr paper #apunte

2025-05-10 #apunte
  - (putting in order and clarify the tasks)
  - Data and storage [PN]
  - Store data for good runs (wfs, pmaps, Sophronia's hits) for example for good Kr and Th runs.
  - purchase 60 Tb of tape for temporally solution [JMB]
  - revisit the possibility of use the 720 Tb robust for a medium term storage [JMB]
  - task force to recude the data size while keeping most of the information (i.e trigger1 keep only relevant events etc) [JAH, GML]
  - Kr-studies [GML]
  - MC studies: we estimate the true lifetime using simulated data [GML, KM-CM]
  - MC studies: study possible sample bias introduced by the reconstruction, ie. Irene, [GML, K-Juan David]
  - trigger studies: study the Kr trigger efficiency [PN]
  - auto-trigger sample [PN, JAH->]
  - data studies: define a Kr S2 using wfs and study the reconstruction (irene) selection efficiency [GML]
  - data studies: monitor and understand the efficiencies in the different steps and filters of the reconstruction. [GML]
  - software: simplified and parallel code like Irene to find S1, S2 peaks, xcheck with irene results [S]
  - data studies: how is the impact of the PMT (SiPM) noise in the data? [S]
  - what is the effect on the S1?
  - is there any effect on the S2?
  - How we can reduce the noise?
  - take a data sample with the PMT vacuum pump off [PN, JAH->] with auto-trigger and Kr-trigger
  - take a data sample with PMT off with auto-trigger and Kr-trigger [PN, JAH->]
  - data studies: how to identify the "true" S1 with respect the spurious S1s? [GML, JAH, S]
  - data studies: Why there are less Kr events at large drift distances. Is an effect of the SiPM threshold? [GML]
  - Using pmaps, select S2 in the PMTs and check if there is signal in the SiPMs [JAH]
  - MC and data studies: effieciency an bias of the corona algorithm [GM, KM]
  - low the threshold for the corona algorithm to ensure we are not biasing specially for the transverse diffusion, check the radius.
  - use the MC to study possible bias of the SiPM selection due to diffusion
  - data studies: What is the effect of the Kr spurious hits? [JAH, PN - Pokee]
  - Can we remove the spurious hits: find a graph algoritm to identify "tracks" and "satellites" [S - John, Martin] (check for existing algorithms)
  - What we do with the spurious hits: remove for tracking! but what to do with the energy? [PN, JAH - Juan David, Pokee]
  - Can we do something more clever in Sophronia to select and remove the spurious hits? for example with a cut on the SiPM that depends on the drift time, [GMK, PN]
  - data studies: verify the energy resolution with the Sophronia hits and compare with the kdst [JAH - Miriam/Juan David]
  - data studies: check for the stability of the Kr (geometrical) maps per run. [JAH, GML - Carlos]
  - data studies: check for the time and geometrical dependeioes of the lifetime [JAH, GML - Carlos]
  - data studies: define a map with pure Kr and fix for online Sophronia reconstruction [GML, PN] [PN, JAH -> Kr pure runs]
  - data studies: compare energy resolution and performance using the general (best) Kr map and the Kr map optined run by run [JAH-Carlos]
  - online processing: Fit ICAROS and get the monitoring [GML - Carlos]
  - data studies: Do we have enough stats to generate a Kr map per run with the Th source on? [JAH, GML - Carlos]
  - data studies: check for the stability of the Kr (geometrical) maps per run. [JAH, GML - Carlos]
  - data studies: check for the time and geometrical dependeioes of the lifetime [JAH, GML - Carlos]
  - HE - studies [JAH]
  - MC studies: prepare MC Th sample with "realistic" light situation [JAH->KM]
  - trigger studies: Validate the trigger. Are we triggering efficiency on all the tracks, horizontal vs vertical?
  - auto-trigger with Th source [JAH,PN ->]
  - trigger1 with a longer buffer to find long tracks [PN - Miriam?]
  - Use of Anders' triger emulation to compute the trigger efficiency. Use MC [PN-Ander
  - MC studies: compute reconstruction efficiency and bias of the long tracks? Compare with MC. [JAH, PN - Martin, Miriam, John]
  - data studies: Monitorizar la energy scale [JAH - Martin/Miriam]
  - software: Can we get a better method to apply the calibration?, i.e, using interpolation of the signal between the SiPM positions, or using the Bersheba's hits instead of Sophronia hits: [JAH, S]
  - data studies: do we reconstruct muons? study the different angles [PN- John]
  - data studies: the DT effect [JAH - Martin/Miriam]:
  - select and separate subsamples and study as as function of different parameters [JAH - Martin]
  - study the DZ effect per PMT and main parameters [JAH-Martin]
  - data and MC studies: Track reconstruction [JAH - John]
  - data and MC studies: revisit and stimate Paulina algorithms [JAH - John]

2025-05-09 #apunte
  - Storage (hardware/software) (60 Tb)
  - keep wfs for a good Kr run and last Th run HE
  - define how to reduce the data for pmaps (for Kr and HE), create a working work
  - decide for the machine for the disk space (720 Tb)
  - We are going the use the new decoder which will allow to use more CPUs for the processing.
  - Kr -
  - Estudiar PMT energy spectrum and get the gain in ring
  - Verificar si la BLR es correcta (before and after signal, a la Samuele)
  - How the S2 vs DT behave, what we can learn?
  - Reconstruction - Kr [Juan David]
  - Compare true/reco with the LT, the study of the MC with Rhiannon
  - New run of Kr - S2 selection with the wfs and test the Irene
  - Trigger efficiency of the Kr selection (need auto-trigger)
  - Monitor and understand the different filter and steps in the reconstruction chain and why?
  - Prepare a simplified "Irene" reconstruction not IC to check that Irene is working properly
  - What is the effect of the PMT noise in the energy resolution -> Mark with Samuele supervision
  - How to separate S1s from Kr and S1s of noise?
  - CM specific runs:
  - auto-trigger run y Kr trigger
  - auto-trigger run without the PMT vacuum pump [!!] y Kr trigger
  - auto-trigger run PMT on/off y Kr trigger
  - Why we have less Kr events at large drift-time, is an effect of the SiPM threshold!
  - Using pmaps if there is a S2 in PMT check if there is in SiPM, if not why?
  - ensure the corona efficiency reconstruction: low the threshold for the corona algorithm to ensure we are not biasing specially for the transverse diffusion, check the radius.
  - use the MC to study possible bias of the SiPM selection due to diffusion
  - What is the effect of the Kr spurious hits? [Pokee]
  - What we do with the spurious hits: remove for tracking!! but what to do with the energy?
  - Get the dependence of spurious hits vs slice light
  - Can we create a graph algorithm to get connectivity maybe with the IC [Samuele]
  - Martin, John about possible existing algorithms
  - Can we do something more clever in Sophronia to select the spurius hits and remove them
  - Sanity check: verify the energy resolution with the Sophronia hits and compare with the kdst. [Miriam/Juan David]
  - The geometrical maps should be conceptually stable. How to ensure the stability? be detailed.
  - Check if there are dependencies of the lifetime with respect position and time.
  - Define a map with pure Kr and fix for online sophronia
  - Get the kr-map by run and compare with the default and use for Isaura and compare
  - Fit ICAROS and get the monitoring
  - Do we have enough stats to generate a Kr map per run with the Th source on.
  - At HE
  - Validate the trigger of HE? Are we triggering efficiency on all the tracks, horizontal vs vertical
  - we need to take auto-trigger with Th source
  - we need to take trigger1 with a longer buffer to find long tracks [CM - Miriam?]
  - Use of Anders emulation to compute the trigger efficiency. MC for Th with the light level in agreement with the data [Is Krishan working on it]. [Pau-Ander] [Kr ask?]
  - reconstruction efficiency of the long tracks? Compare with MC. [Martin]
  - main parameters.
  - Monitorizar la energy scale [Martin/Miriam]
  - Instead of correcting the hit energy SiPM per SiPM we can use the Bersheba hits? do we need interpolation? How to do at large radius [Samuele?]
  - Muon reconstruction. Do we see muons that are horizontals? Do we have tracks of more than 400 us? [John]
  - DZ effect [Martin] per PMT, per z, and others

2025-05-08 #apunte
  - The study of Kr events only
  - there is an issue related with the DT distribution, the contamination at larger radius
  - Selecting events in Kr and inside a radius
  - Nos looking at the different PMTs in rings
  - Nos the S2e vs DT per PMT for Kr only
  - Two main issues:
  - There are less Kr events at larger distance, maybe radius, is there an issue of the chamber, the reconstrucción, or the selection? (I doubt the last one)
  - Each PMT -after calibrated- and in the same ring for the full sample sees different number of pes, why? how this is affecting the performance?
  - ![fig-06.png](./references/fig-06.png)
  - ![fig-02.png](./references/fig-02.png)
  - ![fig-08.png](./references/fig-08.png)
  - ![fig-12.png](./references/fig-12.png)

2025-05-07 #apunte
  - trigger
  - ensure trigger bias does not bias the selection
  - sensor calibration
  - ensure base-line supression and BLR
  - estimation of gain, noise of PMTs
  - estimation of gain, noise of SiPMs
  - stability of PMTs
  - stability of SiPMs
  - reconstruction
  - ensure S1, S2 determination
  - ensure SiPM position
  - Kr calibration
  - estimate S1, S2 Kr light and characteristic
  - estimate lifetime
  - estimate drift-velocity
  - estimate the Kr-map
  - estimate longitudinal and transverse diffusion parameters
  - stability of S1, S2 characteristic
  - stability of lifetime
  - stability of drift-velocity and related observables
  - stability of the Kr-map
  - stability of the diffusion
  - decide when we need to update Kr-map
  - monitoring of lifetime
  - HE calibration - energy
  - define and validate energy calibration
  - estimate energy scale
  - estimate energy resolution
  - stability of the energy scale
  - stability of the energy resolution
  - study the energy dependences
  - establish and validate extra energy corrections
  - HE calibration - tracking
  - study the S2 tracking characterics
  - study the paulina performance
  - study Beersheba performance
  - PMTs - minor
  - ¿do we understand the calibration gain, can we xcheck it?
  - Is there a possible effect of the PMT base line slightly increase over time?
  - Why there are some PMTs is larger noise than other, should we treat them separately?
  - KR & Xrays - relevant
  - Why the transverse diffusion does not match the expectation? Is there an efficiency on the diffusion at larger DT and radius?
  - Do we have an issue with the reconstruction on Sophronia, should we go for different SiPM threshold cuts depending on the drift distance?
  - Why the X-Kr energy spectry is different for different PMTs?
  - Is there an effect of the lifetime values depending on looking at X, Kr? and PMTs?
  - Check that the correction by SiPM (normal procedure) is the equivalent to the barycenter.
  - How to deal with the corrections at larger radius? Should we use interpolation?
  - Is there an effect of scatted SiPM hits for Kr events?
  - Do we have enough stats to monitor and to correct the map in case of necesity?
  - HE - relevant
  - We have worse energy resolution than expected. It seems that we have serious dependencies with delta-z, and maybe z and radius.
  - Is there a problem with the correction at larger drift distance? Is this related with a diffusion issue in Kr?
  - Why the delta-z effect is not unique (there are several spots in the E vs Dz plot)
  - The effect depends on the PMTs?
  - depends on z? on the fidutial of the chamber?
  - depends on the orientation of the tracks? Compare horizontal vs vertical tracks
  - Are we having an efficiency problem detecting DE an PH of Th? Is related with the diffusion as for Kr? How we can quantify it? It depends on the trigger, reconstruction parameters, algorithms?
  - We still do not have a preliminar single, double electron separation but John may have results soon.

2025-05-03 #apunte
  - filtered kdst with 1S2, 57%
  - filtered kdst with S2 in the trigger window 0.52%
  - The selection of 1S2 in the trigger wf time window and 1 S1 in the S2width ban
  - But there is an issue related with the drift-time distribution, we are missing events at larger drift times, why [??]
  - Select Kr events and then look at S2e vs DT per PMT or rings
  - ![fig-03.png](./references/fig-03.png)
  - ![fig-05.png](./references/fig-05.png)

2025-05-01 #apunte
  - Connect to the LSC-NEXT cluster
  - Connect to Desman
  - Copy from Desman to LSC-NEXT cluster (en NEXT cluster)
  - Copy from LSC-NEXT to local (en local)

2025-04-16 #apunte
  - HE studies
  - Can we use Kr maps per run?
  - ICAROS, compare with reference map, do we need to change map?
  - Are Kr correction oks (select DS, PP regions, HE Alphas)
  - select (full and fidutial)
  - study E-corrected vs z, x, y, z average
  - study E-c vs (z-min, z-max) etc
  - study E-c vs Delta-z, Delta-x, ..., Delta-r, nhise, nslices, S1e,
  - => Do we need to improve corrections?
  - Escale of energy
  - Create the plot E-corrected vs E-espected for all the peaks in the sample!
  - Delta-z events
  - Select DS y PP
  - Study de Delta-z (Ec, Dz, Ec vs Dz) per run, in sliding z window,
  - Study de Delta-z computhe the (x, y)_PMT baricenter, vs PMT_max...
  - Different popultations
  - HE, and DS, DE populations, where they are, what is the size (mm, hits), correlation with S1, % of the total...

2025-04-09 /mnt/netapp1/Store_next_data/NEXT100/data #apunte

2025-03-11 - meeting #apunte

2025-03-10 #apunte
  - From Ander's paper
  - ![fig-01.png](./references/fig-01.png)

2025-02-07 #apunte
  - Test with MC 4 bar that the LT with MC LT of 50 ms, it is not well reproduced
  - It can be an issue related with diffusion low-dt the diffusion is smaller and at larger-dt is larger, therefore the Kr ball is spread at large difussion. That together with the effect of the dice border could result in the lower LR, but the effect is very significative
  - Is an issue with the fit?
  - Is an issue with the detsim? => compare with full MC

2025-02-04 #apunte
  - - meeting
  - reprocess 2 runs with the same conditions to see if there are bias on Zrms, S2e and DT

2025-01-14 #apunte
  - Get the Kr maps and LT
  - set the normal operation
  - monitoring
  - Get the Kr S1/S2(E, Q) caracterization and connection with the Light Collection
  - alternative peaks selection (S1/S2) and centering of the Kr.
  - Get the diffusion parameters, PDFs from Kr data
  - Understanding how unexpected features (i.e baseline stability, noise, glow, sparse SiPMTs hits) affect the Kr.
  - Compare MC/Data and tune the MC
  - (pag2) Define operation conditions (HV, P), trigger, rate, what are the porpuse
  - Yield, Light collection, vdrift, diffusion
  - (page 3) Baseline stability,
  - Noise of the baseline (noise frequencies, baseline-recovery)
  - PMT sum is correct? what is the share of the PMTs (some problematic?)
  - (page 3) scatter SiPM
  - Inspect the origin (charge, distribution, correlation with Q of the corona)
  - remove them from the processing (corona)
  - (page 5, 10) IC parameters optimization Irene/Dorothea/Sophronia
  - alternative selection of peaks and study of S1/S2
  - (page 6) S1 selection
  - Select good S1 signal, veto possible alphas, indentify the S1 (i.e S2w vs dt)
  - alternative selection of peaks and relazed IC parameters to find S1 and offline identification
  - (page 8 ) Rate of selection, monitoring in time
  - (page 10) S1 studies
  - height, width, energy, dependence within the chamber (with P)
  - (page 11) Prediction of dtime from S2 (width)
  - Kr maps without in events where the S1 is doubtful or have no S1
  - (page 12) Understanding and monitoring Kr geometrial distribution of events (dt, map, raidus)
  - Stable? What is causing the changes?
  - (page 13) Understanding the origin of the structures of the Kr map vs radius
  - What can be related to?
  - (pag 14) Clean Kr Maps
  - procedure the clean the maps (x-rays)
  - LT computations (vs xy, dependence with z)
  - (page 16) Understanding the E resolution
  - Why there is so strong z-dependence (is diffusion? noise by the baseline?)
  - (page 18) Produce the Kr map, corrected energy, E-resolution
  - Optimize the E resolution, verify energy correction, understand problems, monitor in time
  - (pag 20) Understanding Tracking energy (charge) map
  - problems with the calibration of SiPM, calibration gain estability
  - Should we equaluze the SiPM
  - is there any problems os Kr acceptance per board (due to the gain)?
  - (pag 21) SiPM distribution for Kr
  - number and distribution of SiPMs
  - obtain the PDF
  - study the distribution of the external ring
  - Are we biasing the position with the baricenter?
  - (page 23) Light collection with S1
  - Dependency of S1 in the chamber (anode, cathode, center) compare with MC
  - Compare with NEW, compute the worsened of the light collection N100/NEW
  - compare and tune the MC
  - (page 24) Understanding the S2 Light collection efficiency
  - Can we get the mesh transparency factor?
  - Compare with MC, tune the MC
  - (page 26) Understanding S2 light in SPMS
  - verify the coverage! How mutch the pes threshold/SiPM are reducing the total charge?
  - compare with MC, tune the MC
  - (page 27) What we lear from the S2 ratio energy at PMTs and SiPMs?
  - (page 28, see pag 24)
  - (page 30) Compare S1 and S2 data/MC
  - why charge is large in MC than data and the contrary for energy?
  - How to tune and tune the MC
  - (pag 31) Study diffusion, DL, DT, vdrift in different HV, P conditions
  - compare with the MC, is possible understand the differences.
  - (pag 32) map ratio data/MC vs radius
  - excellent agreement, why data is seen more light at large radius than the MC predict?
  - (pag 34) reconcile the energy resolution dependence with radius and z between data and MC
  - (page 35) Study SiPMs cluster for Kr
  - compute the PDF from data, tune the MD
  - incorporate in MC the sparse SiMPT signals?
  - Use the LT, modify till we get S1 data distrubution
  - Use data to estimate the mesh transparency and then tune the MC get the reflectivity
