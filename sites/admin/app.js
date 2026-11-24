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
    requestBody.textContent = body ? previewRequestBody(body) : "No request body.";
    requestBody.classList.toggle("empty-payload", !body);

    const response = $("#responseBody");
    response.textContent = responseBody === undefined
        ? "No response received."
        : typeof responseBody === "string"
            ? responseBody
            : JSON.stringify(responseBody, null, 2);
    response.classList.toggle("empty-payload", responseBody === undefined || responseBody === null);
}

function previewRequestBody(body) {
    if (!(body instanceof FormData)) return JSON.stringify(body, null, 2);

    const preview = {};
    for (const [name, value] of body.entries()) {
        if (value instanceof File) {
            preview[name] ??= [];
            preview[name].push({ name: value.name, type: value.type, size_bytes: value.size });
        } else if (name === "plant" || name === "plants") {
            try {
                preview[name] = JSON.parse(value);
            } catch {
                preview[name] = value;
            }
        } else {
            preview[name] = value;
        }
    }
    return JSON.stringify(preview, null, 2);
}

async function apiRequest(method, endpoint, body, useAdminKey = false, track = true) {
    const headers = {
        "x-api-key": useAdminKey ? adminApiKey : readApiKey,
    };
    const options = { method, headers, cache: "no-store" };
    if (body !== undefined) {
        if (body instanceof FormData) {
            options.body = body;
        } else {
            headers["Content-Type"] = "application/json";
            options.body = JSON.stringify(body);
        }
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

function addPlantField(definition, container = $("#plantFields"), prefix = "plant-") {
    const wrapper = document.createElement("div");
    wrapper.className = `field ${["uses", "description"].includes(definition.name) ? "full-width" : ""}`.trim();

    const label = document.createElement("label");
    const id = `${prefix}${definition.name}`;
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
    container.append(wrapper);
}

function openPlantForm(plant = null) {
    editingPlant = plant;
    const form = $("#plantForm");
    form.reset();
    $("#plantDialogTitle").textContent = plant ? `Edit ${plant.common_name}` : "Add a plant";
    $("#updateMode").hidden = !plant;
    $("#savePlantButton").textContent = plant ? "Save changes" : "Create plant";
    $("#plantImage").value = "";
    $("#plantImage").required = !plant;
    $("#imageRequirement").textContent = plant ? "(optional replacement)" : "(required)";

    if (plant) {
        for (const field of PLANT_FIELDS) {
            const control = form.elements.namedItem(field.name);
            control.value = plant[field.name] ?? "";
        }
    }
    $("#plantDialog").showModal();
}

function readPlantFields(container) {
    return Object.fromEntries(PLANT_FIELDS.map((field) => {
        const control = container.querySelector(`[name="${field.name}"]`);
        const value = String(control?.value ?? "").trim();
        return [field.name, field.type === "number" ? Number(value) : value];
    }));
}

function readPlantForm() {
    return readPlantFields($("#plantForm"));
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
    const imageFile = $("#plantImage").files[0];
    const body = method === "PATCH" ? changedFields(values, editingPlant) : values;

    if (method === "PATCH" && !Object.keys(body).length && !imageFile) {
        setNotice("No fields have changed.");
        saveButton.disabled = false;
        return;
    }

    try {
        let result;
        if (!isEdit) {
            const upload = new FormData();
            upload.append("plant", JSON.stringify(values));
            upload.append("image", await optimizeImageFile(imageFile));
            result = await apiRequest("POST", "/plants", upload, true);
        } else {
            if (method === "PUT" || Object.keys(body).length) {
                result = await apiRequest(method, endpoint, body, true);
            }
            if (imageFile) {
                const upload = new FormData();
                upload.append("image", await optimizeImageFile(imageFile));
                result = await apiRequest("PUT", `${endpoint}/image`, upload, true);
            }
        }
        $("#plantDialog").close();
        setNotice(isEdit
            ? `${editingPlant.common_name} was updated.`
            : `${result.common_name} was created with ID ${result.id}.`);
        await loadPlants(false);
    } catch (error) {
        setNotice(error.message, true);
    } finally {
        saveButton.disabled = false;
    }
}

async function optimizeImageFile(file) {
    if (!file) throw new Error("Choose an image for every plant.");
    if (!file.type.startsWith("image/")) throw new Error("Choose a JPG or PNG image.");
    if (file.type === "image/jpeg" && file.size <= 300_000) return file;

    let bitmap;
    try {
        bitmap = await createImageBitmap(file);
    } catch {
        throw new Error(`Could not read ${file.name}. Choose a valid JPG or PNG image.`);
    }

    try {
        const maxDimension = 1400;
        let scale = Math.min(1, maxDimension / Math.max(bitmap.width, bitmap.height));
        const qualities = [0.84, 0.76, 0.68, 0.6];
        let blob = null;

        for (let attempt = 0; attempt < 12; attempt += 1) {
            const canvas = document.createElement("canvas");
            canvas.width = Math.max(1, Math.round(bitmap.width * scale));
            canvas.height = Math.max(1, Math.round(bitmap.height * scale));
            const context = canvas.getContext("2d");
            context.fillStyle = "#fff";
            context.fillRect(0, 0, canvas.width, canvas.height);
            context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
            const quality = qualities[Math.min(attempt % qualities.length, qualities.length - 1)];
            blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", quality));
            if (!blob) throw new Error("The selected image could not be prepared.");
            if (blob.size <= 300_000) break;
            if (attempt > 0 && attempt % qualities.length === qualities.length - 1) scale *= 0.82;
        }

        if (!blob) throw new Error("The selected image could not be prepared.");
        if (blob.size > 300_000) {
            throw new Error(`Could not reduce ${file.name} enough for upload. Choose a smaller image.`);
        }
        const fileName = file.name.replace(/\.[^.]+$/, "") || "plant-image";
        return new File([blob], `${fileName}.jpg`, {
            type: "image/jpeg",
            lastModified: Date.now(),
        });
    } finally {
        bitmap.close?.();
    }
}

let bulkEntryNumber = 0;

function updateBulkEntryControls() {
    const entries = [...document.querySelectorAll("#bulkEntries .bulk-entry")];
    entries.forEach((entry, index) => {
        entry.querySelector("legend").textContent = `Entry ${index + 1}`;
        const removeButton = entry.querySelector(".entry-remove");
        removeButton.hidden = entries.length === 1;
    });
    $("#addBulkEntry").disabled = entries.length >= 10;
}

function addBulkPlantEntry() {
    const entries = $("#bulkEntries");
    if (entries.children.length >= 10) return;

    bulkEntryNumber += 1;
    const entry = document.createElement("fieldset");
    entry.className = "bulk-entry";
    const legend = document.createElement("legend");
    legend.textContent = `Entry ${entries.children.length + 1}`;
    const fields = document.createElement("div");
    fields.className = "field-grid";
    PLANT_FIELDS.forEach((definition) => {
        addPlantField(definition, fields, `bulk-${bulkEntryNumber}-`);
    });

    const imageField = document.createElement("div");
    imageField.className = "field image-field";
    const imageLabel = document.createElement("label");
    const imageId = `bulk-${bulkEntryNumber}-image`;
    imageLabel.htmlFor = imageId;
    imageLabel.textContent = "Plant image (required)";
    const imageInput = document.createElement("input");
    imageInput.id = imageId;
    imageInput.type = "file";
    imageInput.accept = "image/jpeg,image/png";
    imageInput.required = true;
    imageInput.dataset.plantImage = "true";
    const imageHelp = document.createElement("small");
    imageHelp.textContent = "Choose a JPG or PNG image.";
    imageField.append(imageLabel, imageInput, imageHelp);

    const removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.className = "entry-remove";
    removeButton.textContent = "Remove entry";
    removeButton.addEventListener("click", () => {
        entry.remove();
        updateBulkEntryControls();
    });

    entry.append(legend, fields, imageField, removeButton);
    entries.append(entry);
    updateBulkEntryControls();
}

function openBulkForm() {
    $("#bulkForm").reset();
    $("#bulkEntries").replaceChildren();
    addBulkPlantEntry();
    addBulkPlantEntry();
    $("#bulkDialog").showModal();
}

async function saveBulkPlants(event) {
    event.preventDefault();
    const entries = [...document.querySelectorAll("#bulkEntries .bulk-entry")];
    if (entries.length < 1 || entries.length > 10) return;
    const button = $("#saveBulkButton");
    button.disabled = true;
    button.textContent = "Saving…";

    try {
        const plants = entries.map((entry) => readPlantFields(entry));
        const images = await Promise.all(entries.map((entry) =>
            optimizeImageFile(entry.querySelector("[data-plant-image]").files[0])
        ));
        const upload = new FormData();
        upload.append("plants", JSON.stringify(plants));
        images.forEach((image) => upload.append("images", image));

        const result = await apiRequest("POST", "/plants/bulk", upload, true);
        $("#bulkDialog").close();
        const names = result.plants.map((plant) => plant.common_name).join(", ");
        setNotice(`${result.count} plants were created: ${names}.`);
        await loadPlants(false);
    } catch (error) {
        setNotice(error.message, true);
    } finally {
        button.disabled = false;
        button.textContent = "Save all plants";
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
    PLANT_FIELDS.forEach((definition) => addPlantField(definition));
    $("#unlockForm").addEventListener("submit", unlockWorkspace);
    $("#searchForm").addEventListener("submit", (event) => {
        event.preventDefault();
        loadPlants();
    });
    $("#refreshButton").addEventListener("click", () => loadPlants());
    $("#createButton").addEventListener("click", () => openPlantForm());
    $("#bulkButton").addEventListener("click", openBulkForm);
    $("#addBulkEntry").addEventListener("click", addBulkPlantEntry);
    $("#bulkForm").addEventListener("submit", saveBulkPlants);
    $("#lockButton").addEventListener("click", lockWorkspace);
    $("#plantForm").addEventListener("submit", savePlant);
    $("#updateMethod").addEventListener("change", () => {
        $("#savePlantButton").textContent = $("#updateMethod").value === "PUT" ? "Replace plant" : "Save changes";
    });
    $("#closePlantDialog").addEventListener("click", () => $("#plantDialog").close());
    $("#cancelPlantDialog").addEventListener("click", () => $("#plantDialog").close());
    $("#closeBulkDialog").addEventListener("click", () => $("#bulkDialog").close());
    $("#cancelBulkDialog").addEventListener("click", () => $("#bulkDialog").close());
    $("#closeDetailsDialog").addEventListener("click", () => $("#detailsDialog").close());
}

window.addEventListener("pagehide", () => {
    adminApiKey = "";
});

document.addEventListener("DOMContentLoaded", initializeAdminPage);
