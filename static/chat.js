// ============================================================
// chat.js — Module 9 Final Version
// ============================================================

const chatMessages = document.getElementById("chatMessages");
const chatInput    = document.getElementById("chatInput");
const sendBtn      = document.getElementById("sendBtn");

// -------------------------
// NAICS Lookup
// -------------------------
const NAICS_LOOKUP = {
    "hardware store":        "4441",
    "hardware":              "4441",
    "home improvement":      "4441",
    "building materials":    "4441",
    "lumber store":          "4441",
    "lumber":                "4441",
    "home depot":            "4441",
    "lowes":                 "4441",
    "lowe's":                "4441",
    "liquor store":          "445310",
    "wine store":            "445310",
    "beer store":            "445310",
    "alcohol store":         "445310",
    "liquor":                "445310",
    "auto parts":            "441310",
    "car parts":             "441310",
    "tire store":            "441310",
    "automotive parts":      "441310",
    "auto":                  "441310",
    "gas station":           "447110",
    "petrol station":        "447110",
    "fuel station":          "447110",
    "gas":                   "447110",
    "jewelry store":         "448310",
    "jewelry":               "448310",
    "luggage store":         "448310",
    "jewellery":             "448310",
    "general store":         "452319",
    "warehouse store":       "452319",
    "department store":      "452319",
    "superstore":            "452319",
    "walmart":               "452319",
    "costco":                "452319",
    "target":                "452319",
    "bakery":                "311811",
    "bread store":           "311811",
    "pastry shop":           "311811",
    "cake shop":             "311811",
    "bank":                  "522110",
    "credit union":          "522110",
    "financial services":    "522310",
    "investment office":     "523930",
    "insurance office":      "524113",
    "insurance":             "524113",
    "real estate office":    "531210",
    "real estate agent":     "531210",
    "real estate":           "531210",
    "property rental":       "531120",
    "rental office":         "531120",
    "college":               "611310",
    "university":            "611310",
    "school":                "611310",
    "training center":       "611310",
    "dentist":               "621210",
    "dental office":         "621210",
    "dental":                "621210",
    "clinic":                "6214",
    "urgent care":           "6214",
    "outpatient clinic":     "6214",
    "medical clinic":        "6214",
    "medical lab":           "621511",
    "diagnostic lab":        "621511",
    "salon":                 "812910",
    "spa":                   "812910",
    "nail salon":            "812910",
    "barber":                "812910",
    "barbershop":            "812910",
    "personal services":     "812910",
    "phone store":           "517312",
    "telecom store":         "517312",
    "wireless store":        "517312",
    "mobile store":          "517312",
    "cell phone store":      "517312",
};

const NAICS_NAMES = {
    "4441":   "Building Material and Supplies Dealers",
    "445310": "Beer, Wine, and Liquor Stores",
    "441310": "Automotive Parts, Accessories, and Tire Stores",
    "447110": "Gasoline Stations",
    "448310": "Jewelry, Luggage, and Leather Goods Stores",
    "452319": "General Merchandise Stores",
    "311811": "Bakeries",
    "522110": "Bank / Credit Institution",
    "522310": "Financial Services",
    "523930": "Investment Office",
    "524113": "Insurance Office",
    "531120": "Property Rental",
    "531210": "Real Estate Office",
    "611310": "College / University",
    "621210": "Dental Office",
    "6214":   "Outpatient Clinic",
    "621511": "Medical / Diagnostic Laboratory",
    "812910": "Personal Services (Salon / Spa)",
    "517312": "Telecom / Phone Store",
    "3399":   "Miscellaneous Manufacturing",
    "512240": "Sound Recording Studio",
    "453991": "Miscellaneous Retail Store",
    "922110": "Justice / Public Safety",
};

// -------------------------
// Ambiguous Category Detection
// -------------------------
const AMBIGUOUS_CATEGORIES = {
    "food":           "Food business could mean several things. Did you mean a bakery? That is the food category we have in our database. Type 'bakery' to proceed.",
    "food business":  "Food business could mean several types. Did you mean a bakery? That is the food category we have in our database. Type 'bakery' to proceed.",
    "food store":     "Food store could mean a bakery or a specialty food store. We have data for bakeries in our database. Type 'bakery' to proceed.",
    "health":         "Health business could mean a dental office, outpatient clinic, or medical lab. Which one did you have in mind?",
    "healthcare":     "Healthcare could mean a dental office, outpatient clinic, or medical lab. Which one did you have in mind?",
    "medical":        "Medical could mean a dental office, outpatient clinic, or medical lab. Could you be more specific?",
    "financial":      "Financial services could mean a bank, insurance office, or investment office. Which one did you have in mind?",
    "finance":        "Financial services could mean a bank, insurance office, or investment office. Which one did you have in mind?",
    "money":          "That could mean a bank or an insurance office. Which one did you mean?",
    "real estate":    "Real estate could mean a real estate agent office or a property rental business. Which one did you mean?",
    "property":       "Property could mean a real estate agent office or a property rental business. Which one did you mean?",
    "store":          "That is a bit broad. Could you be more specific? For example: hardware store, gas station, jewelry store, or bakery.",
    "shop":           "That is a bit broad. Could you be more specific? For example: hardware store, gas station, jewelry store, or bakery.",
    "business":       "Could you describe your business type more specifically? For example: hardware store, bakery, dental office, or gas station.",
    "retail":         "Could you describe your retail type more specifically? For example: hardware store, gas station, jewelry store, or general merchandise store.",
    "service":        "Could you describe your service type more specifically? For example: dental office, salon, insurance office, or real estate agent.",
    "services":       "Could you describe your service type more specifically? For example: dental office, salon, insurance office, or real estate agent.",
};

function getAmbiguousMessage(text) {
    const lower = text.toLowerCase().trim();
    if (AMBIGUOUS_CATEGORIES[lower]) return AMBIGUOUS_CATEGORIES[lower];
    const singleWord = ["store", "shop", "business", "retail", "service", "services",
                        "health", "medical", "financial", "finance", "food", "property"];
    if (singleWord.includes(lower)) return AMBIGUOUS_CATEGORIES[lower] || null;
    return null;
}

// -------------------------
// Scenario History
// -------------------------
let scenarioHistory = [];
let scenarioChart   = null;

function getScenarioLabel(index) {
    const letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
    return "Location " + (letters[index] || (index + 1));
}

// -------------------------
// State
// -------------------------
const state = {
    step:              "category",
    business_category: null,
    business_name:     null,
    candidate_lat:     null,
    candidate_lon:     null,
    floor_area:        null,
    last_result:       null
};

// -------------------------
// Welcome message
// -------------------------
addBotMessage(
    "Welcome. I will guide you through a store-location scenario for Worcester, MA. " +
    "You can enter a NAICS code (e.g., 4441) or describe your business type " +
    "(e.g., 'hardware store', 'bakery', 'dental office')."
);

// -------------------------
// Event listeners
// -------------------------
sendBtn.addEventListener("click", handleSend);
chatInput.addEventListener("keydown", function (event) {
    if (event.key === "Enter") handleSend();
});

window.onMapLocationSelected = function (location) {
    state.candidate_lat = location.lat;
    state.candidate_lon = location.lon;
    if (state.step === "location") {
        addBotMessage(
            `Great, I captured the candidate location: ${location.lat.toFixed(6)}, ${location.lon.toFixed(6)}. ` +
            "Now enter the proposed store floor area in square meters."
        );
        state.step = "floor_area";
    }
};


// -------------------------
// Main message handler
// -------------------------
async function handleSend() {
    const text = chatInput.value.trim();
    if (!text) return;

    addUserMessage(text);
    chatInput.value = "";

    try {
        const rerunInputs = extractRerunInputs(text);
        if (rerunInputs) {
            await rerunModelFromMessage(rerunInputs);
            return;
        }

        if (state.step === "category") {
            await handleCategoryStep(text);
            return;
        }
        if (state.step === "location") {
            handleLocationStep(text);
            return;
        }
        if (state.step === "floor_area") {
            await handleFloorAreaStep(text);
            return;
        }
        if (state.step === "ready") {
            if (isComparisonRequest(text) && scenarioHistory.length >= 2) {
                renderComparison();
                await explainComparison(text);
                return;
            }
            const coords = parseCoordinates(text);
            if (coords && state.business_category && state.floor_area && !extractFullRerunInputs(text)) {
                addBotMessage(
                    `I will rerun the model with the same business (${state.business_name || "NAICS " + state.business_category}) ` +
                    `and floor area (${state.floor_area} sqm) at the new location ` +
                    `${coords.lat.toFixed(6)}, ${coords.lon.toFixed(6)}.`
                );
                await rerunModelFromMessage({
                    business_category: state.business_category,
                    business_name:     state.business_name,
                    candidate_lat:     coords.lat,
                    candidate_lon:     coords.lon,
                    floor_area:        state.floor_area
                });
                return;
            }
            await askQuestion(text);
            return;
        }
    } catch (error) {
        addErrorMessage(error.message || String(error));
    }
}


// -------------------------
// Step handlers
// -------------------------
async function handleCategoryStep(text) {
    if (/^\d+$/.test(text.trim())) {
        const naics = text.trim();
        state.business_category = naics;
        state.business_name     = NAICS_NAMES[naics] || `NAICS ${naics}`;
        state.step = "location";
        addBotMessage(
            `Got it — NAICS code ${naics} (${state.business_name}). ` +
            "Now click the proposed store location on the map. " +
            "You can also type coordinates as: 42.24, -71.78"
        );
        return;
    }

    const ambiguousMsg = getAmbiguousMessage(text);
    if (ambiguousMsg) {
        addBotMessage(ambiguousMsg);
        return;
    }

    const resolved = resolveBusinessName(text);
    if (resolved) {
        state.business_category = resolved.naics;
        state.business_name     = text.trim();
        state.step = "location";
        addBotMessage(
            `I mapped "${text.trim()}" to NAICS ${resolved.naics} (${resolved.name}). ` +
            "Now click the proposed store location on the map. " +
            "You can also type coordinates as: 42.24, -71.78"
        );
        return;
    }

    try {
        const resp = await fetch("/api/resolve_category", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: text.trim() })
        });
        const data = await resp.json();
        if (data.ok && data.matched) {
            state.business_category = data.naics_code;
            state.business_name     = text.trim();
            state.step = "location";
            addBotMessage(
                `I mapped "${text.trim()}" to NAICS ${data.naics_code} (${data.category_name}). ` +
                "Now click the proposed store location on the map, " +
                "or type coordinates as: 42.24, -71.78"
            );
            return;
        }
    } catch (_) { }

    addBotMessage(
        `I could not identify "${text.trim()}" as a business category. ` +
        "Please enter a numeric NAICS code (e.g., 4441 for hardware stores) " +
        "or try a more specific description like 'hardware store', 'bakery', or 'dental office'."
    );
}

function handleLocationStep(text) {
    const coords = parseCoordinates(text);
    if (!coords) {
        addBotMessage("Please click the map or type coordinates in this format: 42.24, -71.78");
        return;
    }
    state.candidate_lat = coords.lat;
    state.candidate_lon = coords.lon;
    if (window.setCandidateLocation) {
        window.setCandidateLocation(coords.lat, coords.lon, false);
    }
    state.step = "floor_area";
    addBotMessage("Great. Now enter the proposed store floor area in square meters.");
}

async function handleFloorAreaStep(text) {
    const area = Number(text.replace(/,/g, ""));
    if (!Number.isFinite(area) || area <= 0) {
        addBotMessage("Please enter a positive numeric floor area, such as 1000.");
        return;
    }
    state.floor_area = area;
    state.step = "ready";
    addBotMessage(
        `Thanks. I will run the Huff model for ${state.business_name || "NAICS " + state.business_category}, ` +
        `location (${state.candidate_lat.toFixed(6)}, ${state.candidate_lon.toFixed(6)}), ` +
        `and floor area ${state.floor_area} square meters.`
    );
    await runModel();
}


// -------------------------
// Model execution
// -------------------------
async function rerunModelFromMessage(inputs) {
    state.business_category = inputs.business_category;
    state.business_name     = inputs.business_name || NAICS_NAMES[inputs.business_category] || `NAICS ${inputs.business_category}`;
    state.candidate_lat     = inputs.candidate_lat;
    state.candidate_lon     = inputs.candidate_lon;
    state.floor_area        = inputs.floor_area;
    state.step              = "ready";
    addBotMessage(
        `Running the model for ${state.business_name}, ` +
        `location (${state.candidate_lat.toFixed(6)}, ${state.candidate_lon.toFixed(6)}), ` +
        `floor area ${state.floor_area} sqm.`
    );
    if (window.setCandidateLocation) {
        window.setCandidateLocation(state.candidate_lat, state.candidate_lon, false);
    }
    await runModel();
}

async function runModel() {
    addBotMessage("Running the model now...");

    const response = await fetch("/api/run_huff", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            candidate_lat:     state.candidate_lat,
            candidate_lon:     state.candidate_lon,
            business_category: state.business_category,
            floor_area:        state.floor_area,
            naics_code:        state.business_category,
            floor_area_sqm:    state.floor_area
        })
    });

    const data = await response.json();
    if (!response.ok || !data.ok) {
        throw new Error(data.error || "Model failed.");
    }

    state.last_result = data.result;

    // Load competitor POIs on map and get nearest distance
    let nearestKm = null;
    if (window.loadCompetitorPois) {
        nearestKm = await window.loadCompetitorPois(
            state.business_category,
            state.candidate_lat,
            state.candidate_lon
        );
    } else if (window.plotCompetitors) {
        window.plotCompetitors(data.result.competitors);
    }

    // Load top 5 nearest competitors into results panel
    await loadNearestCompetitors(
        state.business_category,
        state.candidate_lat,
        state.candidate_lon
    );

    // Store in scenario history
    const label = getScenarioLabel(scenarioHistory.length);
    scenarioHistory.push({
        label,
        inputs: {
            business_category: state.business_category,
            business_name:     state.business_name,
            lat:               state.candidate_lat,
            lon:               state.candidate_lon,
            floor_area:        state.floor_area
        },
        result:    data.result,
        nearestKm: nearestKm
    });

    renderResult(data.result, label);
    updateScenarioChart();

    addBotMessage(
        data.explanation ||
        `${label} result is ready. You can ask follow-up questions, ` +
        "provide new coordinates for another scenario, or type 'compare' to compare locations."
    );

    if (scenarioHistory.length === 2) {
        addBotMessage(
            "You now have two scenarios. Type 'compare locations' or 'which is better' to see a side-by-side comparison."
        );
    }
}


// -------------------------
// Nearest Competitors (Module 9 - Item 1 fix)
// Calls /api/nearest_competitors and populates the competitor table
// with real names, categories, and distances from Azure SQL.
// -------------------------
async function loadNearestCompetitors(naics, lat, lon) {
    try {
        const url = `/api/nearest_competitors?naics=${encodeURIComponent(naics)}&lat=${lat}&lon=${lon}&n=5`;
        const response = await fetch(url);
        const data     = await response.json();

        if (!data.ok || !Array.isArray(data.competitors) || data.competitors.length === 0) {
            return;
        }

        renderNearestCompetitors(data.competitors, data.total_found);

    } catch (error) {
        console.warn("Could not load nearest competitors:", error);
    }
}

function renderNearestCompetitors(competitors, totalFound) {
    const tableWrap = document.getElementById("competitorTable");

    const note = totalFound > competitors.length
        ? `<p style="font-size:0.85em;color:#666;">Showing 5 nearest of ${totalFound} total competitors in this category.</p>`
        : `<p style="font-size:0.85em;color:#666;">${totalFound} competitor(s) found in this category.</p>`;

    tableWrap.innerHTML = note + `
        <table>
            <thead>
                <tr>
                    <th>Name</th>
                    <th>Category</th>
                    <th>Distance</th>
                </tr>
            </thead>
            <tbody>
                ${competitors.map(c => `
                    <tr>
                        <td>${escapeHtml(c.location_name || "Unknown")}</td>
                        <td>${escapeHtml(c.top_category  || "N/A")}</td>
                        <td>${c.distance_km !== null ? c.distance_km + " km" : "N/A"}</td>
                    </tr>
                `).join("")}
            </tbody>
        </table>
    `;
}


// -------------------------
// Follow-up questions
// -------------------------
async function askQuestion(question) {
    if (!state.last_result) {
        addBotMessage("Please complete a model run first.");
        return;
    }
    const response = await fetch("/api/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, result: state.last_result })
    });
    const data = await response.json();
    if (!response.ok || !data.ok) {
        throw new Error(data.error || "The assistant could not answer.");
    }
    addBotMessage(data.answer);
}


// -------------------------
// Comparison
// -------------------------
function isComparisonRequest(text) {
    const lower = text.toLowerCase();
    return lower.includes("compare") ||
           lower.includes("which is better") ||
           lower.includes("which location") ||
           lower.includes("best location") ||
           lower.includes("versus") ||
           lower.includes(" vs ") ||
           lower.includes("difference between") ||
           lower.includes("side by side") ||
           lower.includes("side-by-side");
}

function renderComparison() {
    const section = document.getElementById("comparisonSection");
    if (!section || scenarioHistory.length < 2) return;

    const headers  = scenarioHistory.map(s => `<th>${escapeHtml(s.label)}</th>`).join("");
    let tableRows  = "";

    const visits   = scenarioHistory.map(s => s.result.predicted_visits || 0);
    const maxVisit = Math.max(...visits);
    tableRows += `<tr><td><strong>Predicted Visits</strong></td>
        ${scenarioHistory.map((s, i) =>
            `<td class="${visits[i] === maxVisit ? "better" : ""}">${escapeHtml(s.result.predicted_visits)}</td>`
        ).join("")}</tr>`;

    const shares   = scenarioHistory.map(s => s.result.market_share || 0);
    const maxShare = Math.max(...shares);
    tableRows += `<tr><td><strong>Market Share</strong></td>
        ${scenarioHistory.map((s, i) =>
            `<td class="${shares[i] === maxShare ? "better" : ""}">${(s.result.market_share * 100).toFixed(2)}%</td>`
        ).join("")}</tr>`;

    const comps   = scenarioHistory.map(s => typeof s.result.competitors === "number" ? s.result.competitors : 0);
    const minComp = Math.min(...comps);
    tableRows += `<tr><td><strong>Competitors</strong></td>
        ${scenarioHistory.map((s, i) => {
            const val = typeof s.result.competitors === "number" ? s.result.competitors : "N/A";
            return `<td class="${comps[i] === minComp ? "better" : ""}">${escapeHtml(val)}</td>`;
        }).join("")}</tr>`;

    const dists   = scenarioHistory.map(s => s.nearestKm);
    const hasData = dists.some(d => d !== null && d !== undefined);
    if (hasData) {
        const maxDist = Math.max(...dists.filter(d => d !== null && d !== undefined));
        tableRows += `<tr><td><strong>Nearest Competitor</strong></td>
            ${scenarioHistory.map((s, i) => {
                const d = dists[i];
                if (d === null || d === undefined) return `<td>N/A</td>`;
                return `<td class="${d === maxDist ? "better" : ""}">${d.toFixed(2)} km away</td>`;
            }).join("")}</tr>`;
    }

    tableRows += `<tr><td><strong>Runtime (ms)</strong></td>
        ${scenarioHistory.map(s => `<td>${escapeHtml(s.result.runtime_ms)}</td>`).join("")}</tr>`;

    tableRows += `<tr><td><strong>Business</strong></td>
        ${scenarioHistory.map(s => `<td>${escapeHtml(s.inputs.business_name || s.inputs.business_category)}</td>`).join("")}</tr>`;

    tableRows += `<tr><td><strong>Floor Area (sqm)</strong></td>
        ${scenarioHistory.map(s => `<td>${escapeHtml(s.inputs.floor_area)}</td>`).join("")}</tr>`;

    tableRows += `<tr><td><strong>Coordinates</strong></td>
        ${scenarioHistory.map(s =>
            `<td>${s.inputs.lat.toFixed(4)}, ${s.inputs.lon.toFixed(4)}</td>`
        ).join("")}</tr>`;

    section.innerHTML = `
        <h3>Location Comparison</h3>
        <p style="font-size:0.85em;color:#666;">
            Green cells indicate the stronger result for that metric.
            For competitors and nearest competitor distance, fewer competitors
            and farther distance are better.
            Note: this model does not account for rent, zoning, or parking.
        </p>
        <div class="table-wrap">
            <table>
                <thead><tr><th>Metric</th>${headers}</tr></thead>
                <tbody>${tableRows}</tbody>
            </table>
        </div>
    `;

    section.scrollIntoView({ behavior: "smooth" });
}

async function explainComparison(userQuestion) {
    if (scenarioHistory.length < 2) return;
    try {
        const response = await fetch("/api/ask", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                question: userQuestion || "Compare these locations and explain which performs better and why.",
                result:   {
                    type:      "location_comparison",
                    scenarios: scenarioHistory.map(s => ({
                        label: s.label, inputs: s.inputs,
                        result: s.result, nearestKm: s.nearestKm
                    }))
                }
            })
        });
        const data = await response.json();
        if (data.ok) addBotMessage(data.answer);
    } catch (e) {
        addBotMessage("I could not generate a comparison explanation. Please check the comparison table above.");
    }
}


// -------------------------
// Chart
// -------------------------
function updateScenarioChart() {
    const canvas = document.getElementById("scenarioChart");
    if (!canvas || scenarioHistory.length === 0) return;

    const labels = scenarioHistory.map(s => s.label);
    const visits = scenarioHistory.map(s => s.result.predicted_visits || 0);
    const shares = scenarioHistory.map(s => parseFloat((s.result.market_share * 100).toFixed(2)));

    if (scenarioChart) {
        scenarioChart.data.labels           = labels;
        scenarioChart.data.datasets[0].data = visits;
        scenarioChart.data.datasets[1].data = shares;
        scenarioChart.update();
    } else {
        const ctx = canvas.getContext("2d");
        scenarioChart = new Chart(ctx, {
            type: "bar",
            data: {
                labels,
                datasets: [
                    { label: "Predicted Visits",  data: visits, backgroundColor: "rgba(54, 162, 235, 0.75)", borderColor: "rgba(54, 162, 235, 1)", borderWidth: 1, yAxisID: "y"  },
                    { label: "Market Share (%)",  data: shares, backgroundColor: "rgba(255, 99, 132, 0.75)", borderColor: "rgba(255, 99, 132, 1)", borderWidth: 1, yAxisID: "y1" }
                ]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: {
                    title:  { display: true, text: "Scenario Comparison: Visits and Market Share" },
                    legend: { position: "top" }
                },
                scales: {
                    y:  { type: "linear", position: "left",  title: { display: true, text: "Predicted Visits"  }, beginAtZero: true },
                    y1: { type: "linear", position: "right", title: { display: true, text: "Market Share (%)"  }, beginAtZero: true, grid: { drawOnChartArea: false } }
                }
            }
        });
    }
    canvas.parentElement.style.display = "block";
}


// -------------------------
// Input extraction helpers
// -------------------------
function resolveBusinessName(text) {
    const lower = text.toLowerCase().trim();
    if (NAICS_LOOKUP[lower]) return { naics: NAICS_LOOKUP[lower], name: NAICS_NAMES[NAICS_LOOKUP[lower]] || lower };
    const keys = Object.keys(NAICS_LOOKUP).sort((a, b) => b.length - a.length);
    for (const key of keys) {
        if (lower.includes(key)) {
            const code = NAICS_LOOKUP[key];
            return { naics: code, name: NAICS_NAMES[code] || key };
        }
    }
    return null;
}

function extractBusinessCategoryFromText(text) {
    // Only treat a number as NAICS if explicitly prefixed with "naics"
    // This prevents "1000 square meters" from being mistaken for a NAICS code.
    const explicitNaics = text.match(/naics\s*(?:code)?\s*(?:is|=|:|of|for)?\s*(\b\d{4,6}\b)/i);
    if (explicitNaics && NAICS_NAMES[explicitNaics[1]]) {
        return { code: explicitNaics[1], name: NAICS_NAMES[explicitNaics[1]] };
    }
    // Try business name lookup first (most reliable for plain-language input)
    const resolved = resolveBusinessName(text);
    if (resolved) return { code: resolved.naics, name: resolved.name };
    // Fall back: a bare standalone number that exists in our known NAICS list
    const bareNumber = text.match(/\b(\d{4,6})\b/);
    if (bareNumber && NAICS_NAMES[bareNumber[1]]) {
        return { code: bareNumber[1], name: NAICS_NAMES[bareNumber[1]] };
    }
    return null;
}

function extractRerunInputs(message) {
    const coords = parseCoordinates(message);
    if (!coords) return null;
    const businessInfo = extractBusinessCategoryFromText(message);
    if (!businessInfo) return null;
    const areaMatch =
        message.match(/area\s*(?:of|is|=|:)?\s*([\d,]+(?:\.\d+)?)/i) ||
        message.match(/floor\s+area\s*(?:of|is|=|:)?\s*([\d,]+(?:\.\d+)?)/i) ||
        message.match(/([\d,]+(?:\.\d+)?)\s*(?:square\s+meters|square\s+metres|sqm|sq\.?\s*m|m2|m²)/i);
    if (!areaMatch) return null;
    const floorArea = Number(areaMatch[1].replace(/,/g, ""));
    if (!Number.isFinite(floorArea) || floorArea <= 0) return null;
    return { business_category: businessInfo.code, business_name: businessInfo.name, candidate_lat: coords.lat, candidate_lon: coords.lon, floor_area: floorArea };
}

function extractFullRerunInputs(text) {
    const coords   = parseCoordinates(text);
    const business = extractBusinessCategoryFromText(text);
    const area     = text.match(/([\d,]+(?:\.\d+)?)\s*(?:square\s+meters|sqm|m2)/i);
    return (coords && business && area) ? true : null;
}


// -------------------------
// Result rendering
// -------------------------
function renderResult(result, label) {
    const summary   = document.getElementById("resultSummary");
    const tableWrap = document.getElementById("competitorTable");

    const predictedVisits = result.predicted_visits ?? "N/A";
    const marketShare     = Number(result.market_share);
    const runtime         = result.runtime_ms ?? "N/A";
    const notes           = result.notes ?? "";

    // Module 8: populate KPI cards with the two key decision numbers
    const kpiCards = document.getElementById("kpiCards");
    if (kpiCards) {
        const shareDisplay = Number.isFinite(marketShare) ? (marketShare * 100).toFixed(2) + "%" : "N/A";
        const visitsDisplay = Number.isFinite(Number(predictedVisits)) ? Number(predictedVisits).toFixed(1) : String(predictedVisits);
        kpiCards.style.display = "grid";
        kpiCards.innerHTML = `
            <div class="kpi-card">
                <div class="kpi-value">${escapeHtml(shareDisplay)}</div>
                <div class="kpi-label">Market Share</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-value">${escapeHtml(visitsDisplay)}</div>
                <div class="kpi-label">Predicted Visits</div>
            </div>
        `;
    }

    summary.innerHTML = `
        ${label ? `<div style="font-weight:bold;margin-bottom:6px;color:#2c5282;">${escapeHtml(label)}</div>` : ""}
        <strong>Predicted Visits:</strong> ${escapeHtml(predictedVisits)}<br>
        <strong>Estimated Market Share:</strong> ${Number.isFinite(marketShare) ? (marketShare * 100).toFixed(2) + "%" : "N/A"}<br>
        <strong>Runtime:</strong> ${escapeHtml(runtime)} ms<br>
        <strong>Notes:</strong> ${escapeHtml(notes)}
    `;

    // Competitor table is populated by loadNearestCompetitors()
    // Only show placeholder if it hasn't been populated yet
    if (tableWrap.innerHTML.trim() === "" || tableWrap.innerHTML === "No competitor records returned.") {
        tableWrap.innerHTML = "Loading nearby competitors...";
    }
}


// -------------------------
// Coordinate parser
// -------------------------
function parseCoordinates(text) {
    const match = text.match(/(-?\d{1,3}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)/);
    if (!match) return null;
    const lat = Number(match[1]);
    const lon = Number(match[2]);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
    if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return null;
    return { lat, lon };
}


// -------------------------
// Message helpers
// -------------------------
function addBotMessage(text)   { addMessage(text, "bot");   }
function addUserMessage(text)  { addMessage(text, "user");  }
function addErrorMessage(text) { addMessage(text, "error"); }

function addMessage(text, type) {
    const div     = document.createElement("div");
    div.className = `message ${type}`;
    div.innerText = text;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&",  "&amp;")
        .replaceAll("<",  "&lt;")
        .replaceAll(">",  "&gt;")
        .replaceAll('"',  "&quot;")
        .replaceAll("'",  "&#039;");
}
