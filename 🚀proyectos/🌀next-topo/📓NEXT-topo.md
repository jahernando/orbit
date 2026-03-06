# Logbook — 🌀next-topo

<!-- Tipos: #idea #referencia #tarea #problema #resultado #apunte #decision -->



2025-12-05 #apunte
  - todo:
  - Define the summary
  - Draw the event and the MC
  - Different types:
  - define the blob using the true extremes
  - define the blob using the radius of a sphere
  - define the blob using a distance along the graph
  - draw in the event display the extremes
  - Get the classical blob with a radius of 2.1 cm
  - Get the classical performance with/without deco
  - what are the best quantities to quantify the agreement with mc-blob?
  - what are the best quantities to quantify the agreement with extremes?
  - comment the functions

2025-12-04 #apunte
  - :
  - Martin has produced the NEXUS and sensim events for Tl (working in Bi) something like 50 k events with 1 track in Qbb range
  - Martin indicates that reconstruction of events, applying Kr map and fidutial selection (hits < 400 mm) implies and efficiency 50%.

2025-12-04 #apunte
  - comment
  - adding Martin's display and local display, incomplete for the moment

2025-12-02 #apunte
  - comments
  - mayor changes in the code
  - create the graph from the event voxels with energy and position information
  - create mv graphs from mc event voxels
  - add selection of the blob by distance
  - first attemps to link with the mc

2025-11-28 #apunte
  - :
  - commit with mc information
  - Comparison of blob-2 indicates that energy is discriminant (but maybe many failures in finding the 2nd blob) and the structure of the blob (nodes and edges) has discriminating power
  - Comparing MC for blob-1
  - distance between extremes is relevant to separate bkg/sign
  - spine hits and energy, blob and graph nodes and edges have some discrimination potential
  - ![fig-07.png](./references/fig-07.png)
  - ![fig-06.png](./references/fig-06.png)

2025-11-27 #apunte
  - :
  - commit zora city
  - example of an event and the blobs: the extremes are 'x' and the blobs '+', we are selecting a blob as the nodes connected with a distance of 3 respect the extremes.
  - this plot shows that the NN-spine has a goo job, there are many tracks with less number of nodes, and a sample of tracks were the spine has 1/3 of the energy, and other where the spine has all the energy.
  - commit with the selection of the blobs and some first variables
  - commit with the sharing the energy in the slice (all the energy of the slice is shared proportional to the fraction of the energy each spine hit has in the same z-slice) and energy normalization per event (to one). Test done!
  - possible variables of the summary
  - nodes, nodes in spine, energy in spine, x slices in the spline, subgraphs, length, bid (blob id), extreme energy, blob energy, blob connections, blob position
  - todo:
  - check that the share of the energy per slice is correct for the deconvoluted event
  - select the extremes
  - compute the sub-graph of the extremes as a distance
  - compute the energy in the blobs
  - compute the barycenter of the blobs
  - create a summary of the event, the graph, and the blobs
  - create a city that process and event or a list of events
  - pass the binclass to the summary ntuple
  - comment the functions
  - make a production
  - ![fig-05.png](./references/fig-05.png)
  - ![fig-04.png](./references/fig-04.png)

2025-11-26 #apunte
  - shared the energy per slice, and total energy in the event is normalized to 1.
  - Added evtfun.py and graph.py in the respository, clean the NB
  - Sometimes there is an ambiguity and a graph can have several extremes with same distance!
  - todo:
  - check that the share of the energy per slice is correct for the deconvoluted event
  - compute the energy inside a radius around the extreme (r = 20 mm)
  - refine the blob with the connected voxels till the barycenter does not move more than half the bin width (for example)
  - study the separation of e/ee vs the distance between the extremes
  - explore the correlation between extreme position and energy

2025-11-25 #apunte
  - GitHub repo NB
  - Event #22 (data), Display of the hits, the decov voxels and the longest graph with the extremes
  - ![fig-01.png](./references/fig-01.png)
  - ![fig-02.png](./references/fig-02.png)
  - ![fig-03.png](./references/fig-03.png)

2025-11-24 #apunte
  - using data from Martin's (deconv NN) located at CESGA:
  - reading the info
  - it contains the hits of the events after applying the deconv

2025-11-24 #apunte
  - Pablo y Samuele look at this during this week
  - Mapa de Kr (Carlos, mapas 3D, evolución of the light in the HE)
  - Monitoring of the low bkg with Kr
