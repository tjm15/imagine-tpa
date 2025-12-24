import fs from 'fs';
import yaml from 'js-yaml';
import { chromium } from 'playwright';

const SPEC_FILE = process.argv[2];
const VLM_BASE_URL = process.env.TPA_VLM_BASE_URL || 'http://tpa-vlm:8000/v1'; 
const TARGET_BASE_URL = process.env.TARGET_BASE_URL || 'http://tpa-ui:80'; 
const SUPERVISOR_URL = process.env.TPA_MODEL_SUPERVISOR_URL || 'http://tpa-model-supervisor:8091';

if (!SPEC_FILE) {
    console.error("Usage: node runner.mjs <spec_file>");
    process.exit(1);
}

async function ensureVLM() {
    try {
        console.log(`[UAT] Ensuring VLM via supervisor: ${SUPERVISOR_URL}`);
        const response = await fetch(`${SUPERVISOR_URL}/ensure`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ role: 'vlm' })
        });
        if (!response.ok) {
            console.warn(`[UAT] Supervisor ensure failed: ${response.status} (might be unavailable, proceeding anyway)`);
        } else {
            console.log(`[UAT] VLM Ensure: OK`);
        }
    } catch (e) {
        console.warn(`[UAT] Supervisor unreachable: ${e.message}`);
    }
}

async function callVLM(prompt, imageBuffer) {
    // Ensure VLM is up before calling
    await ensureVLM();

    const base64Image = imageBuffer.toString('base64');
    const payload = {
        model: "nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-FP8", // Default, can be overridden
        messages: [
            {
                role: "user",
                content: [
                    { type: "text", text: prompt },
                    { type: "image_url", image_url: { url: `data:image/png;base64,${base64Image}` } }
                ]
            }
        ],
        max_tokens: 100
    };

    try {
        const response = await fetch(`${VLM_BASE_URL}/chat/completions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        if (!response.ok) {
            const txt = await response.text();
            throw new Error(`VLM Error ${response.status}: ${txt}`);
        }
        
        const data = await response.json();
        return data.choices[0].message.content;
    } catch (e) {
        console.error("VLM Call Failed:", e);
        return "ERROR";
    }
}

async function run() {
    console.log(`[UAT] Running spec: ${SPEC_FILE}`);
    const specContent = fs.readFileSync(SPEC_FILE, 'utf8');
    const spec = yaml.load(specContent);

    const browser = await chromium.launch();
    const page = await browser.newPage();
    
    // Set viewport
    await page.setViewportSize({ width: 1280, height: 720 });

    let failed = false;

    try {
        for (const step of spec.steps) {
            console.log(`[Step] ${step.action} ...`);
            
            if (step.action === 'goto') {
                const url = step.url.startsWith('http') ? step.url : `${TARGET_BASE_URL}${step.url}`;
                await page.goto(url);
            }
            else if (step.action === 'wait_for_text') {
                await page.waitForSelector(`text=${step.text}`, { timeout: 10000 });
            }
            else if (step.action === 'click') {
                await page.click(step.selector);
            }
            else if (step.action === 'type') {
                await page.fill(step.selector, step.text);
            }
            else if (step.action === 'screenshot') {
                const path = `agents/mdk/uat/scenarios/${step.id}.png`;
                await page.screenshot({ path: path });
                console.log(`  -> Saved ${path}`);
            }
            else if (step.action === 'judge') {
                // Take screenshot for judgement
                const screenshot = await page.screenshot();
                console.log(`  -> Asking Judge: "${step.prompt}"`);
                
                // MOCK JUDGE IF ENV SET (for speed/dev)
                let verdict;
                if (process.env.MOCK_JUDGE) {
                    verdict = "YES";
                    console.log(`  -> [Mock Judge] Verdict: ${verdict}`);
                } else {
                    verdict = await callVLM(`Answer strictly YES or NO. ${step.prompt}`, screenshot);
                    console.log(`  -> [Real Judge] Verdict: ${verdict}`);
                }
                
                if (!verdict.toUpperCase().includes("YES")) {
                    console.error(`❌ Judgement Failed!`);
                    failed = true;
                    // break; // Optional: stop on failure
                } else {
                    console.log(`✅ Judgement Passed`);
                }
            }
        }
    } catch (e) {
        console.error("❌ Scenario Error:", e);
        failed = true;
    } finally {
        await browser.close();
    }
    
    if (failed) process.exit(1);
    console.log("🎉 Scenario Completed");
}

run();