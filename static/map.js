let candidateLocation = null;
let candidateMarker   = null;
let competitorLayer   = null;
let poiLayer          = null;

const map = L.map("map").setView([42.2626, -71.8023], 12);

L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap contributors"
}).addTo(map);

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
// Haversine distance (km)
// -------------------------
function haversineKm(lat1, lon1, lat2, lon2) {
  const R    = 6371;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a    = Math.sin(dLat / 2) ** 2 +
               Math.cos(lat1 * Math.PI / 180) *
               Math.cos(lat2 * Math.PI / 180) *
               Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}


// -------------------------
// Module 9: Load competitor POIs from Azure SQL
// Called by chat.js after each model run.
// Returns the nearest competitor distance in km (or null if unavailable).
// chat.js stores this in scenario history and shows it in the comparison table.
// -------------------------
async function loadCompetitorPois(naics, candidateLat, candidateLon) {
  try {
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
      return null;
    }

    poiLayer = L.layerGroup().addTo(map);

    let nearestKm = null;

    data.pois.forEach(poi => {
      const lat = parseFloat(poi.latitude);
      const lon = parseFloat(poi.longitude);
      if (!isFinite(lat) || !isFinite(lon)) return;

      // Calculate distance from candidate location to this POI
      if (candidateLat !== null && candidateLon !== null) {
        const dist = haversineKm(candidateLat, candidateLon, lat, lon);
        if (nearestKm === null || dist < nearestKm) {
          nearestKm = dist;
        }
      }

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

    console.log(`Loaded ${data.pois.length} competitor POIs. Nearest: ${nearestKm ? nearestKm.toFixed(2) + " km" : "N/A"}`);

    return nearestKm !== null ? parseFloat(nearestKm.toFixed(3)) : null;

  } catch (error) {
    console.warn("Could not load POI data from Azure SQL:", error);
    return null;
  }
}


// -------------------------
// Legacy plotCompetitors (kept for backward compatibility)
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
// Expose to chat.js
// -------------------------
window.setCandidateLocation = setCandidateLocation;
window.getCandidateLocation = getCandidateLocation;
window.plotCompetitors      = plotCompetitors;
window.loadCompetitorPois   = loadCompetitorPois;
