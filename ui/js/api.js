let sessionToken = "";

export function setSessionToken(token) {
  sessionToken = token;
}

export function request(service, path, options = {}) {
  const baseUrl = window.SCHOOLRUN_CONFIG?.[service];
  if (!baseUrl || !path.startsWith("/") || path.startsWith("//")) {
    throw new Error("The SchoolRun API address is missing or invalid.");
  }
  const headers = new Headers(options.headers);
  if (sessionToken) headers.set("Authorization", `Bearer ${sessionToken}`);
  return fetch(`${baseUrl.replace(/\/$/, "")}${path}`, {
    ...options,
    headers,
    credentials: "omit",
    cache: "no-store",
    redirect: "error",
    signal: options.signal || AbortSignal.timeout(12000),
  });
}

export async function call(service, path, options) {
  let response;
  try {
    response = await request(service, path, options);
  } catch (error) {
    if (options?.signal?.aborted) throw error;
    throw new Error("Could not reach the service. It may be starting up. Try again shortly.");
  }
  const data = await response.json().catch(() => ({}));
  if (response.ok) return data;

  const formErrors = Object.values(data.errors || {}).flat().map(error => error.message).join(" ");
  const messages = {
    401: "Sign-in required or credentials invalid.",
    403: "You do not have permission for this action.",
    404: "This record is unavailable.",
    409: "The current state does not allow this action. Refresh and try again.",
    503: "The service is unavailable or starting up. Try again shortly.",
  };
  throw Object.assign(new Error(formErrors || data.detail || messages[response.status] || "The request failed."), {
    status: response.status,
  });
}

export function jsonPost(data) {
  return {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data)};
}

export function dateLabel(value) {
  const date = value && new Date(value);
  return date && Number.isFinite(date.getTime()) ? date.toLocaleString() : "Not available";
}
