import fs from "node:fs/promises";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Workbook } from "@oai/artifact-tool";

const here = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.basename(here) === ".qa_build" ? path.dirname(here) : here;
const python = process.env.CODEX_BUNDLED_PYTHON;
const raw = execFileSync(python, ["-c", "import json, qa_master_catalog as q; print(json.dumps({'summary':q.summary(),'cases':q.ALL_CASES[:2]}, ensure_ascii=False))"], { cwd: projectRoot, encoding: "utf8" });
const data = JSON.parse(raw);
const out = path.join(projectRoot, "outputs", "master_qa_documentation", "_xlsx_visual_qa");
await fs.mkdir(out, { recursive: true });

const wb = Workbook.create();
const navy = "#17324D", blue = "#246B8E", pale = "#EEF5F8", white = "#FFFFFF", ink = "#17212B";

function title(sheet, text, sub, endCol) {
  sheet.showGridLines = false;
  sheet.getRange(`A1:${endCol}1`).merge();
  sheet.getRange("A1").values = [[text]];
  sheet.getRange(`A1:${endCol}1`).format = { fill: navy, font: { bold: true, color: white, size: 18, name: "Aptos Display" }, verticalAlignment: "center" };
  sheet.getRange(`A1:${endCol}1`).format.rowHeight = 32;
  sheet.getRange(`A2:${endCol}2`).merge();
  sheet.getRange("A2").values = [[sub]];
  sheet.getRange(`A2:${endCol}2`).format = { fill: pale, font: { color: "#5D6B78", italic: true, size: 10 }, wrapText: true };
  sheet.getRange(`A2:${endCol}2`).format.rowHeight = 32;
}

const summary = wb.worksheets.add("00_Test_Summary");
title(summary, "Nexora RealtyOS - System Test Repository", "Formula-driven execution summary and module coverage", "J");
summary.getRange("A4:J4").values = [["Module / Feature", "Number of Test Cases", "Positive Cases", "Negative Cases", "Edge Cases", "Security Cases", "Integration Cases", "Priority", "Testing Status", "Notes"]];
summary.getRange("A4:J4").format = { fill: blue, font: { bold: true, color: white, size: 10 }, wrapText: true, horizontalAlignment: "center" };
summary.getRange("A5:J8").values = [
  ["Authentication and Access", 12, 1, 1, 2, 4, 0, "P0", "Not Run", "Registration, OTP, JWT refresh, password reset and entitlement."],
  ["Property Inventory and Lifecycle", 12, 1, 1, 1, 4, 0, "P0", "Not Run", "Tenant inventory, publication, agent restrictions and history."],
  ["Security and Permissions", 24, 0, 0, 0, 24, 0, "P0", "Not Run", "Authentication, IDOR, tenant isolation, webhooks and uploads."],
  ["TOTAL", data.summary.total_cases, data.summary.positive, data.summary.negative, 52, data.summary.security, 27, "P0", "Not Run", "401 master test cases across 31 execution sheets."],
];
summary.getRange("A5:J8").format = { font: { name: "Aptos", size: 9, color: ink }, wrapText: true, verticalAlignment: "top", borders: { insideHorizontal: { style: "thin", color: "#E4EBEF" } } };
summary.getRange("A8:J8").format = { fill: navy, font: { bold: true, color: white, size: 9 }, wrapText: true };
const sw = [30, 15, 13, 13, 13, 13, 14, 10, 14, 60];
for (let i=0;i<sw.length;i++) summary.getRange(String.fromCharCode(65+i)+":"+String.fromCharCode(65+i)).format.columnWidth = sw[i];
summary.getRange("A4:J4").format.rowHeight = 36;
summary.getRange("A5:J8").format.rowHeight = 42;
summary.freezePanes.freezeRows(4);

const headers = ["Test Case ID","Module","Feature","Sub Feature","Test Scenario","Test Case Title","Test Type","Priority","Severity","User Role","Preconditions","Required Test Data","Environment / Setup","Steps","Expected Result","Expected Database Impact","Expected API Behavior","Expected UI Behavior","Expected Side Effects","Related Features","Postconditions","Actual Result","Status","Bug / Issue ID","Automation Candidate","Notes"];
const feature = wb.worksheets.add("01_Auth_Access");
title(feature, "Authentication and Access - Master Test Cases", "Current implementation baseline | Update Actual Result, Status and Bug / Issue ID during execution", "Z");
feature.getRange("A4:Z4").values = [headers];
feature.getRange("A4:Z4").format = { fill: blue, font: { bold: true, color: white, size: 10 }, wrapText: true, horizontalAlignment: "center" };
const rows = data.cases.map(c => [c.id,c.module,c.feature,c.subfeature,c.scenario,c.title,c.type,c.priority,c.severity,c.role,c.preconditions,c.data,c.environment,c.steps,c.expected,c.db,c.api,c.ui,c.side,c.related,c.postconditions,c.actual,c.status,c.bug,c.automation,c.notes]);
feature.getRange("A5:Z6").values = rows;
feature.getRange("A5:Z6").format = { font: { name: "Aptos", size: 9, color: ink }, wrapText: true, verticalAlignment: "top", borders: { insideHorizontal: { style: "thin", color: "#E4EBEF" } } };
feature.getRange("A5:Z6").format.rowHeight = 78;
const fw = [13,22,22,30,48,34,20,9,10,24,46,44,44,58,50,48,50,44,46,42,42,28,12,14,14,44];
function colName(index){let n=index+1,o="";while(n){const r=(n-1)%26;o=String.fromCharCode(65+r)+o;n=Math.floor((n-1)/26)}return o}
fw.forEach((w,i)=>feature.getRange(`${colName(i)}:${colName(i)}`).format.columnWidth=w);
feature.freezePanes.freezeRows(4); feature.freezePanes.freezeColumns(6);

for (const [sheetName, range] of [["00_Test_Summary","A1:J8"],["01_Auth_Access","A1:Z6"]]) {
  const blob = await wb.render({ sheetName, range, scale: 0.65, format: "png" });
  await fs.writeFile(path.join(out, `${sheetName}.png`), new Uint8Array(await blob.arrayBuffer()));
}
console.log(out);

