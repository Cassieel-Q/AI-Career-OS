const fs = require("node:fs/promises");
const path = require("node:path");
const { chromium } = require(path.resolve(__dirname, "../../../../apps/web/node_modules/playwright"));

const web = process.env.TOUR_WEB_URL || "http://127.0.0.1:3001";
const outputDir = path.resolve(__dirname, "../../../screenshots/project-tour-2026-10-10");
const missionId = process.env.TOUR_MISSION_ID || "48b6772e-17c7-42c4-a18f-a0dda61a1508";
const profileId = process.env.TOUR_PROFILE_ID || "45995c1bdbe84c5991fa9782fff16cde";
const routes = [
  ["01-missions.png", `/missions?profile_id=${profileId}`],
  ["02-role.png", `/missions/${missionId}/role`],
  ["03-resume-source.png", `/missions/${missionId}/resume`],
  ["04-resume-studio.png", `/missions/${missionId}/resume/studio`],
  ["05-interview.png", `/missions/${missionId}/interview`],
  ["06-interview-records.png", `/interview-records?profile_id=${profileId}`],
];

async function main() {
  await fs.mkdir(outputDir, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 });
  const report = [];
  for (const [file, route] of routes) {
    const url = `${web}${route}`;
    const response = await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 }).catch((error) => ({ status: () => 0, error: String(error) }));
    await page.waitForTimeout(1400);
    const screenshotPath = path.join(outputDir, file);
    await page.screenshot({ path: screenshotPath, fullPage: true, timeout: 60000 });
    report.push({
      file,
      route,
      url: page.url(),
      status: typeof response?.status === "function" ? response.status() : 0,
      title: await page.title(),
      headings: await page.locator("h1,h2,h3").allTextContents(),
      body_excerpt: (await page.locator("body").innerText()).slice(0, 500),
    });
  }
  await fs.writeFile(path.join(outputDir, "report.json"), JSON.stringify({ web, missionId, profileId, captured_at: new Date().toISOString(), routes: report }, null, 2));
  await browser.close();
  console.log(JSON.stringify(report, null, 2));
}

main().catch((error) => { console.error(error); process.exitCode = 1; });
