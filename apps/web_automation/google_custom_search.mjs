const DEFAULT_ENDPOINT = "https://www.googleapis.com/customsearch/v1";

function normalizeNum(value) {
  const parsed = Number(value);
  if (Number.isNaN(parsed)) return 10;
  return Math.min(10, Math.max(1, Math.floor(parsed)));
}

function normalizeStart(value) {
  const parsed = Number(value);
  if (Number.isNaN(parsed)) return 1;
  return Math.max(1, Math.floor(parsed));
}

function normalizeStringList(value, limit = 8) {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => (typeof item === "string" ? item.trim() : ""))
    .filter((item) => item)
    .slice(0, limit);
}

function resolveConfig(overrides = {}) {
  const apiKey = overrides.apiKey || process.env.GOOGLE_CSE_API_KEY;
  const cx = overrides.cx || process.env.GOOGLE_CSE_CX;
  const endpoint = overrides.endpoint || process.env.GOOGLE_CSE_ENDPOINT || DEFAULT_ENDPOINT;
  return { apiKey, cx, endpoint };
}

export function buildAuthorityDocumentQuery({
  authorityName,
  documentHints = [],
  extraTerms = [],
} = {}) {
  const authority = typeof authorityName === "string" ? authorityName.trim() : "";
  const hints = normalizeStringList(documentHints, 12);
  const extras = normalizeStringList(extraTerms, 12);
  const parts = [authority, ...hints, ...extras].filter((item) => item);
  return parts.join(" ").trim();
}

export async function googleCustomSearch(options = {}) {
  const query = typeof options.query === "string" ? options.query.trim() : "";
  if (!query) {
    return { ok: false, error: "missing_query" };
  }

  const { apiKey, cx, endpoint } = resolveConfig(options);
  if (!apiKey || !cx) {
    return { ok: false, error: "google_cse_unconfigured" };
  }

  const num = normalizeNum(options.num);
  const start = normalizeStart(options.start);
  const params = new URLSearchParams({
    q: query,
    key: apiKey,
    cx,
    num: String(num),
    start: String(start),
  });

  const safe = typeof options.safe === "string" ? options.safe : null;
  if (safe) params.set("safe", safe);

  const gl = typeof options.gl === "string" ? options.gl : null;
  if (gl) params.set("gl", gl);

  const lr = typeof options.lr === "string" ? options.lr : null;
  if (lr) params.set("lr", lr);

  const siteSearch = typeof options.siteSearch === "string" ? options.siteSearch.trim() : "";
  if (siteSearch) params.set("siteSearch", siteSearch);

  const fileType = typeof options.fileType === "string" ? options.fileType.trim() : "";
  if (fileType) params.set("fileType", fileType);

  const exactTerms = typeof options.exactTerms === "string" ? options.exactTerms.trim() : "";
  if (exactTerms) params.set("exactTerms", exactTerms);

  const orTerms = typeof options.orTerms === "string" ? options.orTerms.trim() : "";
  if (orTerms) params.set("orTerms", orTerms);

  const excludeTerms = typeof options.excludeTerms === "string" ? options.excludeTerms.trim() : "";
  if (excludeTerms) params.set("excludeTerms", excludeTerms);

  const requestUrl = `${endpoint}?${params.toString()}`;
  const timeoutMs = Number(options.timeoutMs || options.timeout_ms || 15000);

  try {
    const resp = await fetch(requestUrl, {
      signal: AbortSignal.timeout(timeoutMs),
    });
    const data = await resp.json();
    if (!resp.ok || data.error) {
      return {
        ok: false,
        status: resp.status,
        error: "google_cse_error",
        detail: data.error || data,
      };
    }

    const items = Array.isArray(data.items)
      ? data.items.map((item) => ({
          title: item.title || "",
          link: item.link || "",
          snippet: item.snippet || "",
          mime: item.mime || "",
          file_format: item.fileFormat || "",
          display_link: item.displayLink || "",
        }))
      : [];

    return {
      ok: true,
      query,
      request: {
        endpoint,
        cx,
        num,
        start,
        site_search: siteSearch || null,
        file_type: fileType || null,
      },
      search_information: data.searchInformation || {},
      items,
    };
  } catch (e) {
    return { ok: false, error: "google_cse_fetch_failed", detail: String(e?.message || e) };
  }
}
