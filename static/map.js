let candidateLocation = null;
let candidateMarker   = null;
let competitorLayer   = null;
let poiLayer          = null;   // Module 9: POI markers loaded from Azure SQL

const map = L.map("map").setView([42.2626, -71.8023], 12);

L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap contributors"
}).addTo(map);

// Load CBG boundary polygons.
// Tries the static file that was already in the repo.
fetch("/static/data/worcester_cbgs_map.geojson")
  .then(response => {
    if (!response.ok) throw new Error("GeoJSON not found");
    return response.json();
  })
  .then(data => {
    const geoLayer = L.geoJSON(data, {
      style: {
        weight:      1,
        color:       "#2563eb",
        opacity:     0.7,
        fillOpacity: 0.08
      }
    }).addTo(map);

    map.fitBounds(geoLayer.getBounds());
  })
  .catch(error => {
    console.warn("CBG boundary layer could not be loaded:", error);
  });


// -------------------------
// Candidate location pin
// -------------------------
map.on("click", function (event) {
  setCandidateLocation(event.latlng.lat, event.latlng.lng, true);
});

function setCandidateLocation(lat, lon, notifyChat = false) {
  candidateLocation = { lat: Number(lat), lon: Number(lon) };

  if (candidateMarker) {
    candidateMarker.setLatLng([candidateLocation.lat, candidateLocation.lon]);
  } else {
    candidateMarker = L.marker([candidateLocation.lat, candidateLocation.lon])
      .addTo(map)
      .bindPopup("Proposed Store Location");
  }

  candidateMarker.openPopup();

  document.getElementById("selectedLocation").innerText =
    `Selected candidate location: ${candidateLocation.lat.toFixed(6)}, ${candidateLocation.lon.toFixed(6)}`;

  map.setView([candidateLocation.lat, candidateLocation.lon], 14);

  if (notifyChat && window.onMapLocationSelected) {
    window.onMapLocationSelected(candidateLocation);
  }
}

function getCandidateLocation() {
  return candidateLocation;
}


// -------------------------
// Module 9: Load competitor POIs from Azure SQL
// Called by chat.js after each model run via window.loadCompetitorPois(naics).
// Replaces any previous POI layer with fresh data from the database.
// -------------------------
async function loadCompetitorPois(naics) {
  try {
    // Clear previous POI markers
    if (poiLayer) {
      poiLayer.remove();
      poiLayer = null;
    }

    const url = naics
      ? `/api/pois?naics=${encodeURIComponent(naics)}`
      : "/api/pois";

    const response = await fetch(url);
    const data     = await response.json();

    if (!data.ok || !Array.isArray(data.pois) || data.pois.length === 0) {
      console.log("No POI data returned from Azure SQL for NAICS:", naics);
      return;
    }

    poiLayer = L.layerGroup().addTo(map);

    data.pois.forEach(poi => {
      const lat = parseFloat(poi.latitude);
      const lon = parseFloat(poi.longitude);
      if (!isFinite(lat) || !isFinite(lon)) return;

      L.circleMarker([lat, lon], {
        radius:      5,
        weight:      1,
        color:       "#dc2626",
        fillColor:   "#dc2626",
        fillOpacity: 0.65
      })
      .addTo(poiLayer)
      .bindPopup(
        `<strong>${escapeHtml(poi.location_name || "Competitor")}</strong><br>` +
        `Category: ${escapeHtml(poi.top_category || "N/A")}<br>` +
        `NAICS: ${escapeHtml(poi.naics_code || "N/A")}`
      );
    });

    console.log(`Loaded ${data.pois.length} competitor POIs from Azure SQL`);

  } catch (error) {
    console.warn("Could not load POI data from Azure SQL:", error);
  }
}


// -------------------------
// Legacy: plotCompetitors kept for backward compatibility.
// Used when the engine returns a list of competitor objects directly.
// -------------------------
function plotCompetitors(competitors) {
  if (competitorLayer) {
    competitorLayer.remove();
  }

  competitorLayer = L.layerGroup().addTo(map);

  if (!Array.isArray(competitors)) return;

  competitors.forEach(comp => {
    if (comp.lat && comp.lon) {
      L.circleMarker([comp.lat, comp.lon], {
        radius:      6,
        weight:      1,
        color:       "#dc2626",
        fillOpacity: 0.7
      })
      .addTo(competitorLayer)
      .bindPopup(
        `<strong>${escapeHtml(comp.name || "Competitor")}</strong><br>` +
        `Size: ${comp.size ?? "N/A"}<br>` +
        `Attraction: ${comp.attraction ?? "N/A"}`
      );
    }
  });
}


// -------------------------
// Utilities
// -------------------------
function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&",  "&amp;")
    .replaceAll("<",  "&lt;")
    .replaceAll(">",  "&gt;")
    .replaceAll('"',  "&quot;")
    .replaceAll("'",  "&#039;");
}


// -------------------------
// Expose functions to chat.js
// -------------------------
window.setCandidateLocation  = setCandidateLocation;
window.getCandidateLocation  = getCandidateLocation;
window.plotCompetitors       = plotCompetitors;
window.loadCompetitorPois    = loadCompetitorPois;   // Module 9: called after each model run
