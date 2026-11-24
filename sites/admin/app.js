const PLANT_FIELDS = [
    { name: "common_name", label: "Common name", type: "text" },
    { name: "scientific_name", label: "Scientific name", type: "text" },
    { name: "image_slug", label: "Image slug", type: "text" },
    { name: "family", label: "Family", type: "text" },
    { name: "genus", label: "Genus", type: "text" },
    { name: "plant_type", label: "Plant type", type: "text" },
    { name: "origin", label: "Origin", type: "text" },
    { name: "habitat", label: "Habitat", type: "text" },
    { name: "lifespan", label: "Lifespan", type: "text" },
    { name: "height_m", label: "Height (m)", type: "number" },
    { name: "spread_m", label: "Spread (m)", type: "number" },
    {
        name: "sunlight",
        label: "Sunlight",
        type: "select",
        options: ["Full Sun", "Partial Shade", "Full Sun to Partial Shade", "Low Light to Full Sun", "Bright Indirect Light"],
    },
    {
        name: "water_requirement",
        label: "Water requirement",
        type: "select",
        options: ["Low", "Moderate", "High", "Low to Moderate", "Moderate to High"],
    },
    { name: "soil_type", label: "Soil type", type: "text" },
    { name: "flower_color", label: "Flower color", type: "text" },
    { name: "flowering_season", label: "Flowering season", type: "text" },
    { name: "uses", label: "Uses", type: "textarea" },
    { name: "toxicity", label: "Toxicity", type: "text" },
    { name: "description", label: "Description", type: "textarea" },
];

let apiBaseUrl = "";
let readApiKey = "";
let adminApiKey = "";
let editingPlant = null;

const $ = (selector) => document.querySelector(selector);

async function loadApiConfig() {
    const response = await fetch("/config/index", { cache: "no-store" });
    if (!response.ok) throw new Error(`Could not load API settings (${response.status}).`);

    const config = await response.json();
    apiBaseUrl = new URL(config.api_url, `${window.location.origin}/`).href.replace(/\/$/, "");
    readApiKey = config.api_key;
}

function setActivity(method, endpoint, body, status, responseBody) {
    const statusPill = $("#responseStatus");
    const success = status !== null && status >= 200 && status < 300;
    statusPill.className = `status-pill ${status === null ? "status-error" : success ? "status-success" : "status-error"}`;
    statusPill.textContent = status === null ? "Network error" : `${status} ${success ? "success" : "error"}`;
    $("#requestLine").textContent = `${method}  ${apiBaseUrl}${endpoint}`;

    const requestBody = $("#requestBody");
    requestBody.textContent = body ? JSON.stringify(body, null, 2) : "No request body.";
    requestBody.classList.toggle("empty-payload", !body);

    const response = $("#responseBody");
    response.textContent = responseBody === undefined
        ? "No response received."
        : typeof responseBody === "string"
            ? responseBody
            : JSON.stringify(responseBody, null, 2);
    response.classList.toggle("empty-payload", responseBody === undefined || responseBody === null);
}

async function apiRequest(method, endpoint, body, useAdminKey = false, track = true) {
    const headers = {
        "x-api-key": useAdminKey ? adminApiKey : readApiKey,
    };
    const options = { method, headers, cache: "no-store" };
    if (body !== undefined) {
        headers["Content-Type"] = "application/json";
        options.body = JSON.stringify(body);
    }

    let responseReceived = false;
    try {
        const response = await fetch(apiBaseUrl + endpoint, options);
        responseReceived = true;
        const responseText = await response.text();
        let result = null;
        if (responseText) {
            try {
                result = JSON.parse(responseText);
            } catch {
                result = responseText;
            }
        }
        if (track) setActivity(method, endpoint, body, response.status, result);
        if (!response.ok) {
            const rawDetail = result && typeof result === "object" ? result.detail : null;
            const detail = Array.isArray(rawDetail)
                ? rawDetail.map((item) => item.msg || JSON.stringify(item)).join("; ")
                : rawDetail;
            throw new Error(detail || `The request failed with status ${response.status}.`);
        }
        return result;
    } catch (error) {
        if (track && !responseReceived) {
            setActivity(method, endpoint, body, null, { detail: error.message || "Network request failed." });
        }
        throw error;
    }
}

function setAccessMessage(message, isError = false) {
    const element = $("#accessMessage");
    element.textContent = message;
    element.classList.toggle("is-error", isError);
}

function setNotice(message, isError = false) {
    const element = $("#notice");
    element.textContent = message;
    element.classList.toggle("is-error", isError);
}

function makeCell(text, className = "") {
    const cell = document.createElement("td");
    if (className) cell.className = className;
    cell.textContent = text ?? "";
    return cell;
}

function makeAction(label, className, action) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `table-action ${className || ""}`.trim();
    button.textContent = label;
    button.addEventListener("click", action);
    return button;
}

function renderPlants(plants) {
    const body = $("#plantRows");
    body.replaceChildren();
    $("#recordCount").textContent = `${plants.length} ${plants.length === 1 ? "plant" : "plants"}`;

    if (!plants.length) {
        const row = document.createElement("tr");
        const cell = makeCell("No plants match this search.", "empty-cell");
        cell.colSpan = 4;
        row.append(cell);
        body.append(row);
        return;
    }

    for (const plant of plants) {
        const row = document.createElement("tr");
        const nameCell = document.createElement("td");
        const name = document.createElement("span");
        name.className = "plant-name";
        name.textContent = plant.common_name;
        const scientific = document.createElement("span");
        scientific.className = "plant-scientific";
        scientific.textContent = plant.scientific_name;
        nameCell.append(name, scientific);

        const actionsCell = document.createElement("td");
        const actions = document.createElement("div");
        actions.className = "row-actions";
        actions.append(
            makeAction("View", "", () => showPlantDetails(plant.id)),
            makeAction("Edit", "", () => editPlant(plant.id)),
            makeAction("Delete", "delete", () => deletePlant(plant)),
        );
        actionsCell.append(actions);

        row.append(nameCell, makeCell(plant.plant_type), makeCell(String(plant.id), "plant-id"), actionsCell);
        body.append(row);
    }
}

async function loadPlants(track = true) {
    if (track) setNotice("Loading plants…");
    const query = $("#searchInput").value.trim();
    const endpoint = query
        ? `/plants/search?q=${encodeURIComponent(query)}`
        : "/plants";

    try {
        const result = await apiRequest("GET", endpoint, undefined, false, track);
        const plants = query ? result.results : result.plants;
        renderPlants(Array.isArray(plants) ? plants : []);
        if (track) setNotice(query ? `Search complete for “${query}”.` : "Plant collection refreshed.");
    } catch (error) {
        $("#plantRows").replaceChildren();
        const row = document.createElement("tr");
        const cell = makeCell(error.message, "empty-cell");
        cell.colSpan = 4;
        row.append(cell);
        $("#plantRows").append(row);
        $("#recordCount").textContent = "Unable to load records";
        setNotice(error.message, true);
    }
}

async function unlockWorkspace(event) {
    event.preventDefault();
    const candidate = $("#adminKey").value.trim();
    if (!candidate) return;

    adminApiKey = candidate;
    $("#adminKey").value = "";
    $("#unlockForm button").disabled = true;
    setAccessMessage("Checking the admin key…");

    try {
        await loadApiConfig();
        await apiRequest("GET", "/admin/session", undefined, true);
        $("#unlockForm").hidden = true;
        $("#access-title").textContent = "Workspace unlocked";
        setAccessMessage("Workspace unlocked for this page session.");
        $("#workspace").hidden = false;
        await loadPlants();
    } catch (error) {
        adminApiKey = "";
        setAccessMessage(error.message, true);
    } finally {
        $("#unlockForm button").disabled = false;
    }
}

function addPlantField(definition) {
    const wrapper = document.createElement("div");
    wrapper.className = `field ${["uses", "description"].includes(definition.name) ? "full-width" : ""}`.trim();

    const label = document.createElement("label");
    const id = `plant-${definition.name}`;
    label.htmlFor = id;
    label.textContent = definition.label;

    let control;
    if (definition.type === "select") {
        control = document.createElement("select");
        for (const optionValue of definition.options) {
            const option = document.createElement("option");
            option.value = optionValue;
            option.textContent = optionValue;
            control.append(option);
        }
    } else if (definition.type === "textarea") {
        control = document.createElement("textarea");
        control.rows = definition.name === "description" ? 3 : 2;
    } else {
        control = document.createElement("input");
        control.type = definition.type;
        if (definition.type === "number") {
            control.min = "0.01";
            control.step = "0.01";
        }
    }

    control.id = id;
    control.name = definition.name;
    control.required = true;
    wrapper.append(label, control);
    $("#plantFields").append(wrapper);
}

function openPlantForm(plant = null) {
    editingPlant = plant;
    const form = $("#plantForm");
    form.reset();
    $("#plantDialogTitle").textContent = plant ? `Edit ${plant.common_name}` : "Add a plant";
    $("#updateMode").hidden = !plant;
    $("#savePlantButton").textContent = plant ? "Save changes" : "Create plant";

    if (plant) {
        for (const field of PLANT_FIELDS) {
            const control = form.elements.namedItem(field.name);
            control.value = plant[field.name] ?? "";
        }
    }
    $("#plantDialog").showModal();
}

function readPlantForm() {
    const formData = new FormData($("#plantForm"));
    return Object.fromEntries(PLANT_FIELDS.map((field) => {
        const value = String(formData.get(field.name) ?? "").trim();
        return [field.name, field.type === "number" ? Number(value) : value];
    }));
}

function changedFields(values, original) {
    return Object.fromEntries(Object.entries(values).filter(([key, value]) => {
        const previous = original[key];
        if (typeof value === "number") return Number(value) !== Number(previous);
        return value !== String(previous ?? "");
    }));
}

async function savePlant(event) {
    event.preventDefault();
    const saveButton = $("#savePlantButton");
    saveButton.disabled = true;
    const values = readPlantForm();
    const isEdit = Boolean(editingPlant);
    const method = isEdit ? $("#updateMethod").value : "POST";
    const endpoint = isEdit ? `/plants/${editingPlant.id}` : "/plants";
    const body = method === "PATCH" ? changedFields(values, editingPlant) : values;

    if (method === "PATCH" && !Object.keys(body).length) {
        setNotice("No fields have changed.");
        saveButton.disabled = false;
        return;
    }

    try {
        const result = await apiRequest(method, endpoint, body, true);
        $("#plantDialog").close();
        setNotice(isEdit ? `${result.common_name} was updated.` : `${result.common_name} was created with ID ${result.id}.`);
        await loadPlants(false);
    } catch (error) {
        setNotice(error.message, true);
    } finally {
        saveButton.disabled = false;
    }
}

async function showPlantDetails(plantId) {
    try {
        const plant = await apiRequest("GET", `/plants/${plantId}`);
        $("#detailsTitle").textContent = `${plant.common_name} · ID ${plant.id}`;
        $("#detailsBody").textContent = JSON.stringify(plant, null, 2);
        $("#detailsDialog").showModal();
    } catch (error) {
        setNotice(error.message, true);
    }
}

async function editPlant(plantId) {
    try {
        const plant = await apiRequest("GET", `/plants/${plantId}`);
        openPlantForm(plant);
    } catch (error) {
        setNotice(error.message, true);
    }
}

async function deletePlant(plant) {
    const confirmed = window.confirm(`Delete ${plant.common_name} (ID ${plant.id}) from the database?`);
    if (!confirmed) return;

    try {
        await apiRequest("DELETE", `/plants/${plant.id}`, undefined, true);
        setNotice(`${plant.common_name} was deleted.`);
        await loadPlants(false);
    } catch (error) {
        setNotice(error.message, true);
    }
}

function lockWorkspace() {
    adminApiKey = "";
    $("#workspace").hidden = true;
    $("#unlockForm").hidden = false;
    $("#access-title").textContent = "Unlock the workspace";
    $("#plantRows").replaceChildren();
    const row = document.createElement("tr");
    const cell = makeCell("Unlock the workspace to load plants.", "empty-cell");
    cell.colSpan = 4;
    row.append(cell);
    $("#plantRows").append(row);
    $("#recordCount").textContent = "Workspace locked";
    setAccessMessage("Locked. The admin key has been cleared from this page.");
    $("#adminKey").focus();
}

function initializeAdminPage() {
    PLANT_FIELDS.forEach(addPlantField);
    $("#unlockForm").addEventListener("submit", unlockWorkspace);
    $("#searchForm").addEventListener("submit", (event) => {
        event.preventDefault();
        loadPlants();
    });
    $("#refreshButton").addEventListener("click", () => loadPlants());
    $("#createButton").addEventListener("click", () => openPlantForm());
    $("#lockButton").addEventListener("click", lockWorkspace);
    $("#plantForm").addEventListener("submit", savePlant);
    $("#updateMethod").addEventListener("change", () => {
        $("#savePlantButton").textContent = $("#updateMethod").value === "PUT" ? "Replace plant" : "Save changes";
    });
    $("#closePlantDialog").addEventListener("click", () => $("#plantDialog").close());
    $("#cancelPlantDialog").addEventListener("click", () => $("#plantDialog").close());
    $("#closeDetailsDialog").addEventListener("click", () => $("#detailsDialog").close());
}

window.addEventListener("pagehide", () => {
    adminApiKey = "";
});

document.addEventListener("DOMContentLoaded", initializeAdminPage);
