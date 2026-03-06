# Logbook — 🌀next-ana-es

<!-- Tipos: #idea #referencia #tarea #problema #resultado #apunte #decision -->



2026-03-04 Response of Martin #apunte

2026-03-03 #apunte
  - Samuele, Pablo, Gonzalo, Josh, JA
  - Samuele has some questions:
  - [Martin-?] about the use of DBSCAN in the paper pitch, better comment use of algorithm, is there is noise in semsim?
  - Topology - Pablo:
  - 4 bar with the data has some problems as the algorithm was tuned with 13 bars. Working on the fit. MC data with detsim and sensim [Martín-?]. Where are the data [Maria-?]
  - Topology - Samuele:
  - Desarrollado el algorithm sobre datos pure MC, use of SEP and Tl single-track, trying to optimize the results. Well advances
  - Topology - María
  - María has started to train a CNN with Martin's data.
  - Kr - Gonzalo
  - Code is ready
  - MC problems: Kr MC maps then applied to HE MC (some effects, mostly in the large radius)
  - Try with the Data LPR, get the Kr map and apply to HE double scape
  - Josh - Paper of pitch
  - [?-Martin] the selection of 1-track at the level of NEXUS, what is the efficiency?
  - There is a question of the bkg in different pressures, mixtures, depends on the detector size, etc.
  - The paper address the topology with single track in e/(gamma in Bi) with mixtures and pressure.

2026-04-11 #apunte
  - Martin, Samuele, Pablo, Maria, Gonzalo, Josh, JA
  - Topology (link to pablos presentation...) - Pablo - Classical Paulina method revisited
  - 15 bar standarlone simulation with difussion of signal (bb0nu) and bkg (electrons? Bi?? - to produce signal in the SiPMs (as voxels)
  - Convert the voxels into a graph - discretice first the cloud to get the track skeleton - and find the extremes of the graph
  - Move the extremes to the closest point with the highest energy
  - Define a blob with the energy inside a radius
  - Remove events with operlaping (in radius) blobs (what is the efficiency?)
  - RoC curve and FoM are 75% eficiency 15% bkg (check) , similar to Josh results with NEW
  - Apply the method to NEXT-100 LPR DST data
  - Apply the method to NEXT-100 sensim mc data (used by María and Josh for their pitch studies)
  - Kr - María/Gonzalo
  - María has a new version of ICAROS almost ready, with most of the test, missing to check the monitoring with data, she will present it in the next software meeting
  - Polish and finalize the city
  - GALA studies - Pablo/María
  - JJ wants to study the implication of the GALA EL-structures on the topology
  - Yassid will produce the E-field of the GALA structures for different configuration
  - Produce a PDF using the E-field, as a map of the light collected by a SiPM as a function of the position where the i.e arrives in (x, y) - follow the i.e electron along the E-field lines and generate the EL light. - Pablo and Yassid
  - Use of the PDF into sensim. Is sensim modular enought to replace the curent PDF for a different one? How much we depend on the NEXT-100 geometry? - Gonzalo has some doubts- Martin/Pablo/JA
  - Produce the hits with semsim and then apply the topological algorithms, either CNN (Maria/Josh), or Paulina-revisited (Pablo/Samuele)

2026-01-12 #apunte
  - (start-26 meeting), Josh, Samuele, Gonzalo y JAngel
  - Kr code (3D maps), María working on it, maybe during Jan26 ready
  - Use for IC HPR, validate LPR, maybe for Radon paper
  - Energy coorrections, Camilo working on it, code from Samule
  - Use for background level studies
  - Use for IC
  - Topology, Gonzalo refactoring the code
  - Samuele testing variations of classical paulina algorithm
  - JA using variation of paulina algorithm in Martin's skeleton NN tracks.
  - NN, Josh and Maria has validated the bkg contamination Bi/Tl at Qbb is almost identical to e of Qbb energy
  - They are working on rephrasing the paper as 'topology' and not pich-optimization
  - NN MC production for CNN classification and application to NEXT-100 LPR double escape data, Martin and María
  - Maybe use of the new Johs' cluster at IFC soon
  - Background level, Pablo is working on it
  - Meetings every 2 weeks, Tuesdays at 15:30
