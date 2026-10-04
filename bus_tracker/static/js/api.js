window.SchoolRunAPI = {
  async request(url, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(url, {
        credentials: "same-origin", cache: "no-store", ...options, signal: controller.signal,
      });
      if (response.redirected) throw Object.assign(new Error("Your session expired. Sign in again."), {status:401});
      let payload;
      try { payload = await response.json(); }
      catch { throw Object.assign(new Error("Unable to read this update. Refresh the page."), {status:response.status}); }
      if (!response.ok) {
        const messages = {
          403:"You no longer have permission for this action.",
          404:"This journey or child is no longer available to your account.",
          409:"The trip state changed. Refresh before editing.",
        };
        throw Object.assign(new Error(messages[response.status] || payload.detail || "Unable to save or load this update."), {status:response.status});
      }
      return payload;
    } catch (error) {
      if (error.name === "AbortError") throw new Error("The request timed out. Try refreshing.");
      throw error;
    } finally { clearTimeout(timer); }
  },
  date(value) {
    if (!value) return "Not available";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "Not available" : date.toLocaleString();
  },
};
