const $ = (id) => document.getElementById(id);
let supabaseClient = null;
let mode = "login";

function showNotice(element, message, isError = false) {
  element.textContent = message || "";
  element.classList.toggle("error", isError);
}

function setMode(nextMode) {
  mode = nextMode;
  const signup = mode === "signup";
  $("loginTab").classList.toggle("active", !signup);
  $("signupTab").classList.toggle("active", signup);
  $("loginTab").setAttribute("aria-selected", String(!signup));
  $("signupTab").setAttribute("aria-selected", String(signup));
  $("nameField").hidden = !signup;
  $("displayName").required = signup;
  $("password").autocomplete = signup ? "new-password" : "current-password";
  $("submitButton").textContent = signup ? "Create account" : "Sign in";
  $("forgotButton").hidden = signup;
  showNotice($("notice"), "");
}

async function loadClient() {
  const response = await fetch("/auth-config", { cache: "no-store" });
  if (!response.ok) throw new Error("Account services are not configured yet. Please try again later.");
  const config = await response.json();
  if (!config.supabase_url || !config.supabase_anon_key) throw new Error("Account services are not configured yet.");
  if (!window.supabase?.createClient) throw new Error("The account service could not be loaded. Refresh and try again.");
  supabaseClient = window.supabase.createClient(config.supabase_url, config.supabase_anon_key);
}

async function showCurrentSession() {
  const { data: { session }, error } = await supabaseClient.auth.getSession();
  if (error) throw error;
  if (!session) return;
  const { data: profile } = await supabaseClient.from("profiles").select("display_name").eq("id", session.user.id).maybeSingle();
  $("authPanel").hidden = true;
  $("profilePanel").hidden = false;
  $("accountEmail").textContent = session.user.email || "";
  $("profileName").value = profile?.display_name || session.user.user_metadata?.display_name || "";
  $("welcomeTitle").textContent = profile?.display_name ? "Welcome, " + profile.display_name + "." : "Welcome to Petalcore.";
}

$("loginTab").addEventListener("click", () => setMode("login"));
$("signupTab").addEventListener("click", () => setMode("signup"));

$("authForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("submitButton");
  button.disabled = true;
  showNotice($("notice"), mode === "signup" ? "Creating your account…" : "Signing you in…");
  try {
    const email = $("email").value.trim();
    const password = $("password").value;
    let result;
    if (mode === "signup") {
      result = await supabaseClient.auth.signUp({
        email, password,
        options: { data: { display_name: $("displayName").value.trim() } }
      });
    } else {
      result = await supabaseClient.auth.signInWithPassword({ email, password });
    }
    if (result.error) throw result.error;
    if (mode === "signup" && !result.data.session) {
      showNotice($("notice"), "Account created. Check your email to confirm your address, then sign in.");
      return;
    }
    await showCurrentSession();
  } catch (error) {
    showNotice($("notice"), error.message || "We couldn't complete that request.", true);
  } finally {
    button.disabled = false;
  }
});

$("forgotButton").addEventListener("click", async () => {
  const email = $("email").value.trim();
  if (!email) {
    showNotice($("notice"), "Enter your email address first.", true);
    $("email").focus();
    return;
  }
  try {
    const { error } = await supabaseClient.auth.resetPasswordForEmail(email, {
      redirectTo: window.location.origin + "/account/"
    });
    if (error) throw error;
    showNotice($("notice"), "If an account exists for that email, a password reset link has been sent.");
  } catch (error) {
    showNotice($("notice"), error.message || "Password reset could not be requested.", true);
  }
});

$("profileForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const { data: { user } } = await supabaseClient.auth.getUser();
  if (!user) return;
  const displayName = $("profileName").value.trim();
  try {
    const { error } = await supabaseClient.from("profiles").update({ display_name: displayName }).eq("id", user.id);
    if (error) throw error;
    await supabaseClient.auth.updateUser({ data: { display_name: displayName } });
    $("welcomeTitle").textContent = displayName ? "Welcome, " + displayName + "." : "Welcome to Petalcore.";
    showNotice($("profileNotice"), "Profile saved.");
  } catch (error) {
    showNotice($("profileNotice"), error.message || "Your profile could not be saved.", true);
  }
});

$("logoutButton").addEventListener("click", async () => {
  const { error } = await supabaseClient.auth.signOut();
  if (error) {
    showNotice($("profileNotice"), error.message, true);
    return;
  }
  $("profilePanel").hidden = true;
  $("authPanel").hidden = false;
  $("authForm").reset();
  showNotice($("notice"), "You have been signed out.");
});

(async function initialize() {
  try {
    await loadClient();
    await showCurrentSession();
  } catch (error) {
    showNotice($("notice"), error.message || "Account services are unavailable.", true);
  }
})();