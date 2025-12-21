import http from "node:http";
import { URL } from "node:url";
import { buildAuthorityDocumentQuery, googleCustomSearch } from "./google_custom_search.mjs";

const port = Number(process.env.PORT || "8085");
const maxHtmlBytes = process.env.MAX_HTML_BYTES ? Number(process.env.MAX_HTML_BYTES) : null;
const maxScreenshotBytes = process.env.MAX_SCREENSHOT_BYTES ? Number(process.env.MAX_SCREENSHOT_BYTES) : null;
const maxFetchBytes = process.env.MAX_FETCH_BYTES ? Number(process.env.MAX_FETCH_BYTES) : null;
const defaultTimeoutMs = process.env.DEFAULT_TIMEOUT_MS ? Number(process.env.DEFAULT_TIMEOUT_MS) : null;
const defaultUserAgent =
  "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

async function readJson(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  const body = Buffer.concat(chunks).toString("utf-8");
  if (!body) return null;
  return JSON.parse(body);
}

function sendJson(res, status, obj) {
  const body = Buffer.from(JSON.stringify(obj));
  res.writeHead(status, { "content-type": "application/json", "content-length": body.length });
  res.end(body);
}

function sendText(res, status, text) {
  const body = Buffer.from(text, "utf-8");
  res.writeHead(status, { "content-type": "text/plain; charset=utf-8", "content-length": body.length });
  res.end(body);
}

function normalizeAuthoritySlug(name) {
  return String(name || "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "-");
}

function filenameFromUrl(value, fallback) {
  try {
    const parsed = new URL(value);
    const name = parsed.pathname.split("/").filter(Boolean).pop();
    if (name) return name;
  } catch {
    // ignore invalid URL
  }
  return fallback || "document";
}

async function headUrl(url, timeoutMs) {
  try {
    const options = { method: "HEAD", redirect: "follow" };
    if (typeof timeoutMs === "number") {
      options.signal = AbortSignal.timeout(timeoutMs);
    }
    const res = await fetch(url, {
      ...options,
    });
    return {
      ok: true,
      status: res.status,
      final_url: res.url,
      content_type: res.headers.get("content-type") || "",
    };
  } catch (e) {
    return { ok: false, error: String(e?.message || e) };
  }
}

async function fetchBytesWithLimit(url, timeoutMs, maxBytes) {
  try {
    const options = { method: "GET", redirect: "follow" };
    if (typeof timeoutMs === "number") {
      options.signal = AbortSignal.timeout(timeoutMs);
    }
    const res = await fetch(url, {
      ...options,
    });
    const contentType = res.headers.get("content-type") || "";
    const contentLength = Number(res.headers.get("content-length") || "0");
    if (typeof maxBytes === "number" && contentLength && contentLength > maxBytes) {
      return {
        status: 413,
        error: "Body too large",
        content_length: contentLength,
        max_bytes: maxBytes,
        final_url: res.url,
        content_type: contentType,
      };
    }
    if (!res.body) {
      return { status: 502, error: "Empty response body", final_url: res.url, content_type: contentType };
    }
    let size = 0;
    const chunks = [];
    for await (const chunk of res.body) {
      size += chunk.length;
      if (typeof maxBytes === "number" && size > maxBytes) {
        return {
          status: 413,
          error: "Body too large",
          body_bytes: size,
          max_bytes: maxBytes,
          final_url: res.url,
          content_type: contentType,
        };
      }
      chunks.push(Buffer.from(chunk));
    }
    const body = Buffer.concat(chunks);
    return {
      status: res.status,
      final_url: res.url,
      content_type: contentType,
      body,
      body_bytes: body.length,
    };
  } catch (e) {
    return { status: 502, error: "Fetch failed", detail: String(e?.message || e) };
  }
}

async function dismissCookieBanners(page) {
  const selectors = [
    "text=Accept All",
    "text=Accept Cookies",
    "text=I Agree",
    "button[id*='cookie']",
    "button[class*='cookie']",
  ];
  for (const sel of selectors) {
    try {
      const loc = page.locator(sel).first();
      if (await loc.isVisible()) {
        await loc.click({ timeout: 1000 });
        await page.waitForTimeout(1000);
        break;
      }
    } catch {
      continue;
    }
  }
}

async function renderPage({
  url,
  waitUntil,
  timeoutMs,
  screenshot,
  viewport,
  dismissCookies,
  userAgent,
}) {
  let playwright;
  try {
    playwright = await import("playwright");
  } catch (e) {
    return {
      status: 500,
      error: "Playwright not available in this image. Use a Playwright base image or install playwright.",
      detail: String(e?.message || e),
    };
  }

  const browser = await playwright.chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({
      viewport,
      userAgent,
      acceptDownloads: true,
    });
    const page = await context.newPage();
    let resp;
    try {
      resp = await page.goto(url, { waitUntil, ...(typeof timeoutMs === "number" ? { timeout: timeoutMs } : {}) });
    } catch (e) {
      return { status: 502, error: "Navigation failed", detail: String(e?.message || e) };
    }

    if (dismissCookies) {
      await dismissCookieBanners(page);
    }

    const html = await page.content();
    const htmlBytes = Buffer.byteLength(html, "utf-8");
    if (typeof maxHtmlBytes === "number" && htmlBytes > maxHtmlBytes) {
      return {
        status: 413,
        error: "Rendered HTML too large",
        html_bytes: htmlBytes,
        max_html_bytes: maxHtmlBytes,
        final_url: page.url(),
      };
    }

    let screenshotBase64 = null;
    if (screenshot) {
      const shot = await page.screenshot({ type: "png", fullPage: true });
      if (typeof maxScreenshotBytes === "number" && shot.length > maxScreenshotBytes) {
        return {
          status: 413,
          error: "Screenshot too large",
          screenshot_bytes: shot.length,
          max_screenshot_bytes: maxScreenshotBytes,
          final_url: page.url(),
        };
      }
      screenshotBase64 = shot.toString("base64");
    }

    return {
      status: 200,
      requested_url: url,
      final_url: page.url(),
      http_status: resp?.status() ?? null,
      title: await page.title(),
      html,
      screenshot_png_base64: screenshotBase64,
    };
  } finally {
    await browser.close();
  }
}

async function handleRender(body) {
  const url = body?.url;
  if (!url || typeof url !== "string") {
    return { status: 400, json: { error: "Missing required field: url" } };
  }

  const waitUntil = body?.wait_until || "load";
  const timeoutMsRaw = body?.timeout_ms ?? defaultTimeoutMs;
  const timeoutMs = timeoutMsRaw == null ? null : Number(timeoutMsRaw);
  const screenshot = body?.screenshot !== false;
  const viewport = body?.viewport || { width: 1280, height: 720 };
  const dismissCookies = body?.dismiss_cookies !== false;
  const userAgent = body?.user_agent || defaultUserAgent;

  const out = await renderPage({
    url,
    waitUntil,
    timeoutMs,
    screenshot,
    viewport,
    dismissCookies,
    userAgent,
  });

  if (out.status !== 200) {
    return { status: out.status, json: out };
  }

  return {
    status: 200,
    json: {
      requested_url: out.requested_url,
      final_url: out.final_url,
      http_status: out.http_status,
      title: out.title,
      html: out.html,
      screenshot_png_base64: out.screenshot_png_base64,
      limitations_text:
        "Automated web capture; content may differ by time, geo, cookies, or bot mitigations. Treat as evidence artefact and record limitations/terms.",
    },
  };
}

async function handleFetch(body) {
  const url = body?.url;
  if (!url || typeof url !== "string") {
    return { status: 400, json: { error: "Missing required field: url" } };
  }

  const timeoutMsRaw = body?.timeout_ms ?? defaultTimeoutMs;
  const timeoutMs = timeoutMsRaw == null ? null : Number(timeoutMsRaw);
  const maxBytesRaw = body?.max_bytes ?? maxFetchBytes;
  const maxBytes = maxBytesRaw == null ? null : Number(maxBytesRaw);
  const out = await fetchBytesWithLimit(url, timeoutMs, maxBytes);

  if (out.error) {
    return {
      status: out.status || 500,
      json: { ...out, requested_url: url },
    };
  }

  return {
    status: 200,
    json: {
      requested_url: url,
      final_url: out.final_url,
      http_status: out.status,
      content_type: out.content_type,
      body_bytes: out.body_bytes,
      body_base64: out.body.toString("base64"),
      limitations_text:
        "Direct fetch without full browser rendering; JS-generated content may be missing or incomplete.",
    },
  };
}

async function handleDiscover(body) {
  const authorityName = body?.authority_name;
  if (!authorityName || typeof authorityName !== "string") {
    return { status: 400, json: { error: "Missing required field: authority_name" } };
  }
  const slug = normalizeAuthoritySlug(authorityName);
  const candidates = [
    `https://www.${slug}.gov.uk/planning-and-building-control/planning-policy/local-plan`,
    `https://www.${slug}.gov.uk/planning/planning-policy`,
  ];
  const checks = [];
  let portalUrl = null;
  for (const candidate of candidates) {
    const head = await headUrl(candidate, defaultTimeoutMs);
    checks.push({
      url: candidate,
      status: head.ok ? head.status : null,
      error: head.ok ? null : head.error,
    });
    if (head.ok && head.status === 200) {
      portalUrl = candidate;
      break;
    }
  }

  let googleSearch = null;
  if (body?.use_google === true) {
    const documentHints =
      Array.isArray(body?.document_hints) && body.document_hints.length
        ? body.document_hints
        : ["local plan", "planning policy", "supplementary planning document"];
    const extraTerms = Array.isArray(body?.extra_terms) ? body.extra_terms : [];
    const query =
      typeof body?.query === "string" && body.query.trim()
        ? body.query.trim()
        : buildAuthorityDocumentQuery({ authorityName, documentHints, extraTerms });
    const fileTypeRaw = typeof body?.file_type === "string" ? body.file_type.trim() : "";
    const fileType = fileTypeRaw || "pdf";
    const siteSearch = typeof body?.site_search === "string" ? body.site_search.trim() : "";
    googleSearch = await googleCustomSearch({
      query,
      num: body?.num,
      start: body?.start,
      timeout_ms: body?.timeout_ms,
      safe: body?.safe,
      gl: body?.gl,
      lr: body?.lr,
      siteSearch,
      fileType,
    });
  }

  return {
    status: 200,
    json: {
      authority_name: authorityName,
      portal_url: portalUrl,
      candidates_checked: checks,
      google_search: googleSearch,
    },
  };
}

async function handleGoogleSearch(body) {
  const query =
    typeof body?.query === "string" && body.query.trim()
      ? body.query.trim()
      : buildAuthorityDocumentQuery({
          authorityName: body?.authority_name,
          documentHints: Array.isArray(body?.document_hints) ? body.document_hints : [],
          extraTerms: Array.isArray(body?.extra_terms) ? body.extra_terms : [],
        });

  if (!query) {
    return { status: 400, json: { error: "Missing required field: query or authority_name" } };
  }

  const result = await googleCustomSearch({
    query,
    num: body?.num,
    start: body?.start,
    timeout_ms: body?.timeout_ms,
    safe: body?.safe,
    gl: body?.gl,
    lr: body?.lr,
    siteSearch: body?.site_search,
    fileType: body?.file_type,
    exactTerms: body?.exact_terms,
    orTerms: body?.or_terms,
    excludeTerms: body?.exclude_terms,
  });

  return { status: result.ok ? 200 : result.status || 502, json: result };
}

async function handleIngest(body) {
  const url = body?.url;
  if (!url || typeof url !== "string") {
    return { status: 400, json: { error: "Missing required field: url" } };
  }

  const timeoutMsRaw = body?.timeout_ms ?? defaultTimeoutMs;
  const timeoutMs = timeoutMsRaw == null ? null : Number(timeoutMsRaw);
  const head = await headUrl(url, timeoutMs);
  const contentType = head.ok ? String(head.content_type || "").toLowerCase() : "";
  const urlLower = url.toLowerCase();
  const isPdf = contentType.includes("application/pdf") || urlLower.endsWith(".pdf");

  if (isPdf) {
    const maxBytesRaw = body?.max_bytes ?? maxFetchBytes;
    const maxBytes = maxBytesRaw == null ? null : Number(maxBytesRaw);
    const fetched = await fetchBytesWithLimit(url, timeoutMs, maxBytes);
    if (fetched.error) {
      return { status: fetched.status || 500, json: { ...fetched, requested_url: url } };
    }
    const finalName = filenameFromUrl(fetched.final_url || url, "document.pdf");
    return {
      status: 200,
      json: {
        requested_url: url,
        final_url: fetched.final_url,
        http_status: fetched.status,
        content_type: "application/pdf",
        content_bytes: fetched.body_bytes,
        content_base64: fetched.body.toString("base64"),
        filename: finalName,
        limitations_text:
          "Direct PDF fetch; metadata and cross-links are not parsed. Treat as evidence artefact and record limitations.",
      },
    };
  }

  const render = await renderPage({
    url,
    waitUntil: body?.wait_until || "domcontentloaded",
    timeoutMs,
    screenshot: body?.screenshot === true,
    viewport: body?.viewport || { width: 1280, height: 720 },
    dismissCookies: body?.dismiss_cookies !== false,
    userAgent: body?.user_agent || defaultUserAgent,
  });

  if (render.status !== 200) {
    return { status: render.status, json: render };
  }

  return {
    status: 200,
    json: {
      requested_url: render.requested_url,
      final_url: render.final_url,
      http_status: render.http_status,
      content_type: "text/html",
      title: render.title,
      html: render.html,
      screenshot_png_base64: render.screenshot_png_base64,
      filename: filenameFromUrl(render.final_url || url, "document.html"),
      limitations_text:
        "Automated web capture; content may differ by time, geo, cookies, or bot mitigations. Treat as evidence artefact and record limitations/terms.",
    },
  };
}

const server = http.createServer(async (req, res) => {
  try {
    const u = new URL(req.url || "/", `http://${req.headers.host || "localhost"}`);
    if (req.method === "GET" && u.pathname === "/healthz") {
      return sendJson(res, 200, { status: "ok" });
    }

    if (req.method === "POST" && u.pathname === "/render") {
      const body = await readJson(req);
      const out = await handleRender(body);
      return sendJson(res, out.status, out.json);
    }

    if (req.method === "POST" && u.pathname === "/fetch") {
      const body = await readJson(req);
      const out = await handleFetch(body);
      return sendJson(res, out.status, out.json);
    }

    if (req.method === "POST" && u.pathname === "/discover") {
      const body = await readJson(req);
      const out = await handleDiscover(body);
      return sendJson(res, out.status, out.json);
    }

    if (req.method === "POST" && u.pathname === "/search/google") {
      const body = await readJson(req);
      const out = await handleGoogleSearch(body);
      return sendJson(res, out.status, out.json);
    }

    if (req.method === "POST" && u.pathname === "/ingest") {
      const body = await readJson(req);
      const out = await handleIngest(body);
      return sendJson(res, out.status, out.json);
    }

    return sendText(res, 404, "not found");
  } catch (e) {
    return sendJson(res, 500, { error: "internal error", detail: String(e?.message || e) });
  }
});

server.listen(port, "0.0.0.0", () => {
  // eslint-disable-next-line no-console
  console.log(`tpa-web-automation listening on :${port}`);
});
