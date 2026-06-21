# AI-Assisted Location Decision Support System
### Team H2 | ITC6040 Informatics Capstone | Northeastern University

**Team Members:** Hatim & Han

**Live App:** https://alsds-team5-app-d6b9abc4bdbdabhw.eastus-01.azurewebsites.net

---

## What This System Does

This is a location decision support system (DSS) that helps business owners and analysts evaluate retail store locations in Worcester, MA. The system uses the Huff Gravity Model to estimate how likely customers from each neighborhood are to visit a proposed store compared to nearby competitors, based on store size and travel distance.

A user can describe their business, pick a spot on the map, and get a predicted market share and estimated customer visits through a guided chatbot.

---

## What Our Team Built

Starting from the instructor baseline, Team H2 built a fully working and deployed DSS with the following improvements:

- **Plain-language input** - Users type a business name like "hardware store" and the system maps it to the right NAICS code automatically
- **Single-message model runs** - The chatbot can pull the business type, floor area, and coordinates from one sentence and run the model right away
- **Scenario memory and follow-up** - The system remembers previous inputs so users can test a new location without re-entering everything
- **Side-by-side location comparison** - After two runs, users can type "compare locations" to see a comparison table with green-highlighted winners
- **Live Azure SQL data** - Competitor markers on the map and the competitor table are loaded directly from Azure SQL after each model run
- **KPI cards** - Market share and predicted visits are shown as large bold numbers at the top of the results panel
- **Scenario comparison chart** - A bar chart updates after each run showing all scenarios side by side
- **Responsible NAICS handling** - The system checks whether a NAICS code exists in the data before running the model, and gives a clear message if no data is available
- **Topic-focused chatbot** - The chatbot stays on DSS topics and politely declines unrelated requests

---

## How to Use It

1. **Choose a location** - Click anywhere on the Worcester map to set your candidate store location
2. **Describe your store** - Type your business type (e.g., "hardware store") or NAICS code in the chatbot
3. **Enter floor area** - Type the proposed store size in square meters
4. **Read the result** - The results panel shows predicted market share, estimated visits, a competitor table, and a chart
5. **Compare locations** - Run a second scenario and type "compare locations" for a side-by-side comparison

---

## Tech Stack

- **Backend:** Python / Flask, deployed on Azure App Service
- **Database:** Azure SQL (POI data, Census Block Groups, Huff model parameters)
- **Model:** Huff Gravity Model (huff_engine.py)
- **Frontend:** HTML, CSS, JavaScript, Leaflet.js (map), Chart.js (charts)
- **AI:** Azure OpenAI (chatbot responses and explanations)
