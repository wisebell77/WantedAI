(() => {
  const apiBaseUrl = window.OVERLAP_JD_API_BASE_URL || "";

  function normalize(payload) {
    const required = ["postingId", "companyName", "positionTitle", "jobFamily", "responsibilities", "requiredSkills", "preferredSkills"];
    const missing = required.filter((key) => payload?.[key] === undefined || payload?.[key] === null);
    if (missing.length) throw new Error(`JD API response is missing: ${missing.join(", ")}`);
    return {
      postingId: String(payload.postingId),
      companyName: String(payload.companyName),
      positionTitle: String(payload.positionTitle),
      jobFamily: String(payload.jobFamily),
      responsibilities: payload.responsibilities.map(String),
      requiredSkills: payload.requiredSkills.map(String),
      preferredSkills: payload.preferredSkills.map(String),
      deadline: payload.deadline || null,
      sourceUpdatedAt: payload.sourceUpdatedAt || null
    };
  }

  async function get(postingId) {
    const response = await fetch(`${apiBaseUrl}/api/v1/job-contexts/${encodeURIComponent(postingId)}`, {
      headers: { Accept: "application/json" }
    });
    if (!response.ok) throw new Error(`JD API request failed: ${response.status}`);
    return normalize(await response.json());
  }

  window.JobContextAPI = { get };
})();
