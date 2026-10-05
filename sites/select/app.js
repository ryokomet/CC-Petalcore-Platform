const API_CONFIG_TIMEOUT_MS = 5000;
const $ = (id) => document.getElementById(id);
let apiConfig = null;

function removeTrailingSlash(value) {
    return value.endsWith("/") ? value.slice(0, -1) : value;
}

async function getAPIConfig(signal) {
    if (apiConfig) return apiConfig;

    const configuredOrigin = window.PETALCORE_API_ORIGIN;
    const origin = configuredOrigin
        ? removeTrailingSlash(configuredOrigin)
        : window.location.origin;
    const controller = new AbortController();
    const cancelRequest = () => controller.abort();
    if (signal) signal.addEventListener("abort", cancelRequest, { once: true });
    const timer = setTimeout(cancelRequest, API_CONFIG_TIMEOUT_MS);

    try {
        const response = await fetch(origin + "/config/select", {
            signal: controller.signal,
            cache: "no-store"
        });
        if (!response.ok) {
            throw new Error("The Select API configuration could not be loaded.");
        }

        const config = await response.json();
        if (typeof config.api_url !== "string" || typeof config.api_key !== "string") {
            throw new Error("The Select API configuration is incomplete.");
        }

        apiConfig = {
            apiUrl: removeTrailingSlash(new URL(config.api_url, origin + "/").href),
            apiKey: config.api_key
        };
        return apiConfig;
    } catch (error) {
        if (signal && signal.aborted) {
            throw new DOMException("Request cancelled", "AbortError");
        }
        if (error.name === "AbortError") {
            throw new Error("The Select API took too long to respond. Please try again.");
        }
        if (["localhost", "127.0.0.1", "[::1]"].includes(window.location.hostname)) {
            throw new Error("Open Petalcore Select through the Platform deployment to get recommendations.");
        }
        throw error;
    } finally {
        clearTimeout(timer);
        if (signal) signal.removeEventListener("abort", cancelRequest);
    }
}

function readPreferences() {
    const setting = document.querySelector('input[name="setting"]:checked')?.value || "either";
    const light = $("lightPreference").value || "any";
    const care = $("carePreference").value || "any";
    const interests = Array.from(
        document.querySelectorAll('input[name="interest"]:checked'),
        (input) => input.value
    );
    return { setting, light, care, interests };
}

function hasPreference(preferences) {
    return preferences.setting !== "either" ||
        preferences.light !== "any" ||
        preferences.care !== "any" ||
        preferences.interests.length > 0;
}

async function requestRecommendations(preferences, signal) {
    const config = await getAPIConfig(signal);
    const response = await fetch(config.apiUrl + "/recommendations", {
        method: "POST",
        headers: {
            "x-api-key": config.apiKey,
            "Content-Type": "application/json"
        },
        body: JSON.stringify(preferences),
        signal
    });

    let data;
    try {
        data = await response.json();
    } catch {
        throw new Error("The server returned an unexpected response.");
    }

    if (!response.ok) {
        if (typeof data.detail === "string") throw new Error(data.detail);
        if (Array.isArray(data.detail)) {
            throw new Error(data.detail.map((item) => item.msg).join(" "));
        }
        throw new Error("Recommendations could not be loaded. Please try again.");
    }
    return data;
}

function makeTextElement(tag, className, text) {
    const element = document.createElement(tag);
    element.className = className;
    element.textContent = text;
    return element;
}

function createRecommendationCard(plant, index) {
    const card = document.createElement("article");
    card.className = "recommendation-card";

    const imageWrap = document.createElement("div");
    imageWrap.className = "recommendation-image";
    const image = document.createElement("img");
    image.src = "images/" + (plant.image_slug || "placeholder") + ".jpg";
    image.alt = plant.common_name ? "Photo of " + plant.common_name : "Plant";
    image.loading = "lazy";
    image.onerror = () => {
        image.onerror = null;
        image.src = "images/placeholder.jpg";
    };
    imageWrap.append(image);

    const content = document.createElement("div");
    content.className = "recommendation-content";

    const topLine = document.createElement("div");
    topLine.className = "recommendation-topline";
    topLine.append(
        makeTextElement("span", "recommendation-rank", index === 0 ? "BEST FIT" : "MATCH " + (index + 1)),
        makeTextElement("span", "recommendation-score", plant.match_score + "% match")
    );

    const title = makeTextElement("h3", "", plant.common_name || "Plant suggestion");
    const scientific = makeTextElement("p", "recommendation-scientific", plant.scientific_name || "");
    const traits = makeTextElement(
        "p",
        "recommendation-traits",
        [plant.plant_type, plant.sunlight, plant.water_requirement ? plant.water_requirement + " water" : ""]
            .filter(Boolean)
            .join(" · ")
    );
    const description = makeTextElement(
        "p",
        "recommendation-description",
        plant.description || "A possible match from the Petalcore plant collection."
    );

    const reasons = document.createElement("ul");
    reasons.className = "recommendation-reasons";
    for (const reason of plant.match_reasons || []) {
        reasons.append(makeTextElement("li", "", reason));
    }

    const scoreTrack = document.createElement("div");
    scoreTrack.className = "recommendation-score-track";
    scoreTrack.setAttribute("role", "img");
    scoreTrack.setAttribute("aria-label", plant.match_score + "% match score");
    const scoreFill = document.createElement("span");
    scoreFill.style.width = Math.max(0, Math.min(100, Number(plant.match_score) || 0)) + "%";
    scoreTrack.append(scoreFill);

    content.append(topLine, title, scientific, traits, description, reasons, scoreTrack);
    card.append(imageWrap, content);
    return card;
}

function displayRecommendations(data) {
    const results = $("recommendationResults");
    results.replaceChildren();

    const plants = Array.isArray(data.results) ? data.results : [];
    plants.forEach((plant, index) => {
        results.append(createRecommendationCard(plant, index));
    });

    const count = typeof data.count === "number" ? data.count : plants.length;
    $("matchCount").textContent = count + (count === 1 ? " match" : " matches");
    $("recommendationStatus").textContent = plants.length
        ? "Here are the closest matches based on your preferences."
        : "No matches came back for those preferences. Try adjusting one or two choices.";
    $("recommendationNotes").textContent = Array.isArray(data.notes)
        ? data.notes.join(" ")
        : "";
    $("recommendationResultsSection").hidden = false;
    $("recommendationResultsSection").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function handleRecommendationSubmit(event) {
    event.preventDefault();
    $("errorMessage").hidden = true;
    $("errorMessage").textContent = "";

    const preferences = readPreferences();
    if (!hasPreference(preferences)) {
        $("errorMessage").textContent = "Choose at least one preference, or select “Surprise me.”";
        $("errorMessage").hidden = false;
        return;
    }

    const button = $("recommendButton");
    const label = $("buttonLabel");
    const originalLabel = label.textContent;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 30_000);
    button.disabled = true;
    label.textContent = "Finding your matches…";
    $("recommendationResultsSection").hidden = false;
    $("recommendationResults").replaceChildren(
        makeTextElement("p", "loading-text", "Looking through the plant collection…")
    );
    $("recommendationStatus").textContent = "Matching your preferences with the catalog.";
    $("matchCount").textContent = "";
    $("recommendationNotes").textContent = "";

    try {
        const data = await requestRecommendations(preferences, controller.signal);
        displayRecommendations(data);
    } catch (error) {
        $("recommendationResultsSection").hidden = true;
        $("errorMessage").textContent = error.name === "AbortError"
            ? "The recommendation request took too long. Please try again."
            : error instanceof TypeError
                ? "Could not connect to Petalcore Select. Check your connection and try again."
                : error.message;
        $("errorMessage").hidden = false;
    } finally {
        clearTimeout(timeout);
        button.disabled = false;
        label.textContent = originalLabel;
    }
}

const preferenceForm = $("preferenceForm");
if (preferenceForm) {
    preferenceForm.addEventListener("submit", handleRecommendationSubmit);
    preferenceForm.addEventListener("input", () => {
        $("errorMessage").hidden = true;
    });
}
