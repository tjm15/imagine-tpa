import http from "node:http";
import { URL } from "node:url";

const port = Number(process.env.PORT || "8085");
const maxHtmlBytes = Number(process.env.MAX_HTML_BYTES || "4000000");
const maxScreenshotBytes = Number(process.env.MAX_SCREENSHOT_BYTES || "6000000");
const defaultTimeoutMs = Number(process.env.DEFAULT_TIMEOUT_MS || "30000");

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

async function handleRender(body) {
  const url = body?.url;
  if (!url || typeof url !== "string") {
    return { status: 400, json: { error: "Missing required field: url" } };
  }

  let playwright;
  try {
    playwright = await import("playwright");
  } catch (e) {
    return {
      status: 500,
      json: {
        error: "Playwright not available in this image. Use a Playwright base image or install playwright.",
        detail: String(e?.message || e),
      },
    };
  }

  const waitUntil = body?.wait_until || "load";
  const timeoutMs = Number(body?.timeout_ms || defaultTimeoutMs);
  const screenshot = body?.screenshot !== false;
  const viewport = body?.viewport || { width: 1280, height: 720 };

  const browser = await playwright.chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport });
    const resp = await page.goto(url, { waitUntil, timeout: timeoutMs });

    const finalUrl = page.url();
    const status = resp?.status() ?? null;

    const html = await page.content();
    const htmlBytes = Buffer.byteLength(html, "utf-8");
    if (htmlBytes > maxHtmlBytes) {
      return {
        status: 413,
        json: {
          error: "Rendered HTML too large",
          html_bytes: htmlBytes,
          max_html_bytes: maxHtmlBytes,
          final_url: finalUrl,
        },
      };
    }

    let screenshotBase64 = null;
    if (screenshot) {
      const shot = await page.screenshot({ type: "png", fullPage: true });
      if (shot.length > maxScreenshotBytes) {
        return {
          status: 413,
          json: {
            error: "Screenshot too large",
            screenshot_bytes: shot.length,
            max_screenshot_bytes: maxScreenshotBytes,
            final_url: finalUrl,
          },
        };
      }
      screenshotBase64 = shot.toString("base64");
    }

    return {
      status: 200,
      json: {
        requested_url: url,
        final_url: finalUrl,
        http_status: status,
        html,
        screenshot_png_base64: screenshotBase64,
        limitations_text:
          "Automated web capture; content may differ by time, geo, cookies, or bot mitigations. Treat as evidence artefact and record limitations/terms.",
      },
    };
  } finally {
    await browser.close();
  }
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

    return sendText(res, 404, "not found");
  } catch (e) {
    return sendJson(res, 500, { error: "internal error", detail: String(e?.message || e) });
  }
});

server.listen(port, "0.0.0.0", () => {
  // eslint-disable-next-line no-console
  console.log(`tpa-web-automation listening on :${port}`);
});

