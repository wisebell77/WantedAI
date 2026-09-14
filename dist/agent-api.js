(() => {
  const apiBaseUrl = window.OVERLAP_AGENT_API_BASE_URL || "";

  async function evaluateInterview(input) {
    const response = await fetch(`${apiBaseUrl}/api/v1/agent/interview-feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(input)
    });
    if (!response.ok) throw new Error(`Agent API request failed: ${response.status}`);
    const result = await response.json();
    if (!Array.isArray(result.feedback)) throw new Error("Agent API response is missing feedback.");
    return result;
  }

  window.CareerCoachAPI = { evaluateInterview };
})();
