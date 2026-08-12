import fs from "node:fs/promises";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const here = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.basename(here) === ".qa_build" ? path.dirname(here) : here;
const python = process.env.CODEX_BUNDLED_PYTHON;
if (!python) throw new Error("CODEX_BUNDLED_PYTHON is required");

const raw = execFileSync(
  python,
  [
    "-c",
    "import json, qa_master_catalog as q; print(json.dumps({'features': q.FEATURES, 'cases': q.ALL_CASES, 'summary': q.summary(), 'unknowns': q.UNKNOWNS}, ensure_ascii=False))",
  ],
  { cwd: projectRoot, encoding: "utf8", maxBuffer: 64 * 1024 * 1024 },
);
const catalog = JSON.parse(raw);

const outputDir = path.join(projectRoot, "outputs", "master_qa_documentation");
const previewDir = path.join(outputDir, "_xlsx_previews");
await fs.mkdir(previewDir, { recursive: true });

const workbook = Workbook.create();
const columns = [
  "Test Case ID", "Module", "Feature", "Sub Feature", "Test Scenario",
  "Test Case Title", "Test Type", "Priority", "Severity", "User Role",
  "Preconditions", "Required Test Data", "Environment / Setup", "Steps",
  "Expected Result", "Expected Database Impact", "Expected API Behavior",
  "Expected UI Behavior", "Expected Side Effects", "Related Features",
  "Postconditions", "Actual Result", "Status", "Bug / Issue ID",
  "Automation Candidate", "Notes",
];

const colors = {
  navy: "#17324D", blue: "#246B8E", cyan: "#D9EEF5", pale: "#EEF5F8",
  ink: "#17212B", muted: "#5D6B78", white: "#FFFFFF", line: "#CCD8E0",
  p0: "#F8D7DA", p1: "#FCE8CC", p2: "#FFF4CC", p3: "#DFF1E3",
  pass: "#DFF1E3", fail: "#F8D7DA", block: "#FCE8CC", skip: "#E5E7EB",
};

function colName(index) {
  let n = index + 1;
  let out = "";
  while (n) {
    const r = (n - 1) % 26;
    out = String.fromCharCode(65 + r) + out;
    n = Math.floor((n - 1) / 26);
  }
  return out;
}

function styleTitle(sheet, title, subtitle) {
  sheet.showGridLines = false;
  sheet.getRange("A1:Z1").merge();
  sheet.getRange("A1").values = [[title]];
  sheet.getRange("A1:Z1").format = {
    fill: colors.navy,
    font: { bold: true, color: colors.white, size: 18, name: "Aptos Display" },
    verticalAlignment: "center", horizontalAlignment: "left",
  };
  sheet.getRange("A1:Z1").format.rowHeight = 32;
  sheet.getRange("A2:Z2").merge();
  sheet.getRange("A2").values = [[subtitle]];
  sheet.getRange("A2:Z2").format = {
    fill: colors.pale,
    font: { color: colors.muted, italic: true, size: 10, name: "Aptos" },
    wrapText: true, verticalAlignment: "center",
  };
  sheet.getRange("A2:Z2").format.rowHeight = 34;
}

function addConditionalFormatting(sheet, firstRow, lastRow) {
  const priority = sheet.getRange(`H${firstRow}:H${lastRow}`);
  priority.conditionalFormats.add("expression", { formula: `=H${firstRow}="P0"`, format: { fill: colors.p0, font: { color: "#8A1C25", bold: true } } });
  priority.conditionalFormats.add("expression", { formula: `=H${firstRow}="P1"`, format: { fill: colors.p1, font: { color: "#8A4B08", bold: true } } });
  priority.conditionalFormats.add("expression", { formula: `=H${firstRow}="P2"`, format: { fill: colors.p2, font: { color: "#665200" } } });
  priority.conditionalFormats.add("expression", { formula: `=H${firstRow}="P3"`, format: { fill: colors.p3, font: { color: "#235C34" } } });

  const status = sheet.getRange(`W${firstRow}:W${lastRow}`);
  status.conditionalFormats.add("expression", { formula: `=W${firstRow}="Passed"`, format: { fill: colors.pass, font: { color: "#235C34", bold: true } } });
  status.conditionalFormats.add("expression", { formula: `=W${firstRow}="Failed"`, format: { fill: colors.fail, font: { color: "#8A1C25", bold: true } } });
  status.conditionalFormats.add("expression", { formula: `=W${firstRow}="Blocked"`, format: { fill: colors.block, font: { color: "#8A4B08", bold: true } } });
  status.conditionalFormats.add("expression", { formula: `=W${firstRow}="Skipped"`, format: { fill: colors.skip, font: { color: "#4B5563" } } });
}

function addFeatureSheet(sheetName, cases, feature) {
  const sheet = workbook.worksheets.add(sheetName);
  styleTitle(
    sheet,
    `${feature ? feature.name : cases[0].module} - Master Test Cases`,
    `Current implementation baseline | ${cases.length} cases | Update Actual Result, Status and Bug / Issue ID during execution. Requires clarification items are called out in Notes or the testing guide.`,
  );
  sheet.getRange("A4:Z4").values = [columns];
  sheet.getRange("A4:Z4").format = {
    fill: colors.blue,
    font: { bold: true, color: colors.white, size: 10, name: "Aptos" },
    wrapText: true, verticalAlignment: "center", horizontalAlignment: "center",
    borders: { preset: "outside", style: "thin", color: colors.navy },
  };
  sheet.getRange("A4:Z4").format.rowHeight = 38;

  const matrix = cases.map((c) => [
    c.id, c.module, c.feature, c.subfeature, c.scenario, c.title, c.type,
    c.priority, c.severity, c.role, c.preconditions, c.data, c.environment,
    c.steps, c.expected, c.db, c.api, c.ui, c.side, c.related, c.postconditions,
    c.actual, c.status, c.bug, c.automation, c.notes,
  ]);
  const first = 5;
  const last = first + matrix.length - 1;
  sheet.getRange(`A${first}:Z${last}`).values = matrix;
  sheet.getRange(`A${first}:Z${last}`).format = {
    font: { name: "Aptos", size: 9, color: colors.ink },
    verticalAlignment: "top", wrapText: true,
    borders: { insideHorizontal: { style: "thin", color: "#E4EBEF" } },
  };
  sheet.getRange(`A${first}:A${last}`).format.font = { name: "Aptos", size: 9, bold: true, color: colors.blue };
  sheet.getRange(`H${first}:I${last}`).format.horizontalAlignment = "center";
  sheet.getRange(`W${first}:Y${last}`).format.horizontalAlignment = "center";
  sheet.getRange(`A${first}:Z${last}`).format.rowHeight = 78;

  const widths = [13, 22, 22, 30, 48, 34, 20, 9, 10, 24, 46, 44, 44, 58, 50, 48, 50, 44, 46, 42, 42, 28, 12, 14, 14, 44];
  widths.forEach((w, i) => { sheet.getRange(`${colName(i)}:${colName(i)}`).format.columnWidth = w; });
  sheet.freezePanes.freezeRows(4);
  sheet.freezePanes.freezeColumns(6);

  const tableName = `T_${sheetName.replace(/[^A-Za-z0-9_]/g, "_")}`;
  const table = sheet.tables.add(`A4:Z${last}`, true, tableName);
  table.style = "TableStyleMedium2";

  sheet.getRange(`H${first}:H${last}`).dataValidation = { rule: { type: "list", values: ["P0", "P1", "P2", "P3"] } };
  sheet.getRange(`I${first}:I${last}`).dataValidation = { rule: { type: "list", values: ["Critical", "High", "Medium", "Low"] } };
  sheet.getRange(`W${first}:W${last}`).dataValidation = { rule: { type: "list", values: ["Not Run", "Passed", "Failed", "Blocked", "Skipped"] } };
  sheet.getRange(`Y${first}:Y${last}`).dataValidation = { rule: { type: "list", values: ["Yes", "No", "Maybe"] } };
  addConditionalFormatting(sheet, first, last);
  return sheet;
}

const summarySheet = workbook.worksheets.add("00_Test_Summary");
styleTitle(
  summarySheet,
  "Nexora RealtyOS - System Test Repository",
  `Generated ${catalog.summary.generated} from the Django backend, React agency dashboard and Next.js public storefront. Property transaction payments are out of scope; Stripe coverage is SaaS agency subscription billing only.`,
);

summarySheet.getRange("A4:J4").merge();
summarySheet.getRange("A4").values = [["Execution Overview"]];
summarySheet.getRange("A4:J4").format = { fill: colors.blue, font: { bold: true, color: colors.white, size: 11 }, verticalAlignment: "center" };
summarySheet.getRange("A5:J5").values = [["Total Cases", catalog.summary.total_cases, "P0", catalog.summary.p0, "P1", catalog.summary.p1, "Feature Areas", catalog.summary.feature_areas, "E2E Journeys", catalog.summary.e2e]];
summarySheet.getRange("A5:J5").format = { fill: colors.pale, font: { bold: true, color: colors.ink, size: 11 }, horizontalAlignment: "center", verticalAlignment: "center", borders: { preset: "outside", style: "thin", color: colors.line } };
summarySheet.getRange("A5:J5").format.rowHeight = 28;

const summaryHeaders = ["Module / Feature", "Number of Test Cases", "Positive Cases", "Negative Cases", "Edge Cases", "Security Cases", "Integration Cases", "Priority", "Testing Status", "Notes"];
summarySheet.getRange("A7:J7").values = [summaryHeaders];
summarySheet.getRange("A7:J7").format = { fill: colors.navy, font: { bold: true, color: colors.white, size: 10 }, wrapText: true, horizontalAlignment: "center", verticalAlignment: "center" };
summarySheet.getRange("A7:J7").format.rowHeight = 36;

const grouped = new Map();
for (const c of catalog.cases) {
  if (!grouped.has(c.sheet)) grouped.set(c.sheet, []);
  grouped.get(c.sheet).push(c);
}
const featureBySheet = new Map(catalog.features.map((f) => [f.sheet, f]));
const sheetNames = [...grouped.keys()].sort();
sheetNames.forEach((name) => addFeatureSheet(name, grouped.get(name), featureBySheet.get(name)));

const summaryStart = 8;
sheetNames.forEach((sheetName, idx) => {
  const row = summaryStart + idx;
  const name = grouped.get(sheetName)[0].module;
  const note = featureBySheet.get(sheetName)?.purpose || "Dedicated cross-system QA suite.";
  summarySheet.getRange(`A${row}`).values = [[name]];
  summarySheet.getRange(`B${row}`).formulas = [[`=COUNTA('${sheetName}'!$A$5:$A$1000)`]];
  summarySheet.getRange(`C${row}`).formulas = [[`=COUNTIF('${sheetName}'!$G$5:$G$1000,"Functional / Positive")+COUNTIF('${sheetName}'!$G$5:$G$1000,"Functional")`]];
  summarySheet.getRange(`D${row}`).formulas = [[`=COUNTIF('${sheetName}'!$G$5:$G$1000,"Negative / Validation")+COUNTIF('${sheetName}'!$G$5:$G$1000,"Validation")`]];
  summarySheet.getRange(`E${row}`).formulas = [[`=COUNTIF('${sheetName}'!$G$5:$G$1000,"Edge Case")+COUNTIF('${sheetName}'!$G$5:$G$1000,"Boundary")+COUNTIF('${sheetName}'!$G$5:$G$1000,"Concurrency")+COUNTIF('${sheetName}'!$G$5:$G$1000,"Idempotency / Concurrency")`]];
  summarySheet.getRange(`F${row}`).formulas = [[`=COUNTIF('${sheetName}'!$G$5:$G$1000,"Security")+COUNTIF('${sheetName}'!$G$5:$G$1000,"Permission / Security")+COUNTIF('${sheetName}'!$G$5:$G$1000,"Security / IDOR")+COUNTIF('${sheetName}'!$G$5:$G$1000,"Permission")`]];
  summarySheet.getRange(`G${row}`).formulas = [[`=COUNTIF('${sheetName}'!$G$5:$G$1000,"Integration")+COUNTIF('${sheetName}'!$G$5:$G$1000,"End-to-End")+COUNTIF('${sheetName}'!$G$5:$G$1000,"External Integration")`]];
  summarySheet.getRange(`H${row}`).formulas = [[`=IF(COUNTIF('${sheetName}'!$H$5:$H$1000,"P0")>0,"P0",IF(COUNTIF('${sheetName}'!$H$5:$H$1000,"P1")>0,"P1","P2"))`]];
  summarySheet.getRange(`I${row}`).formulas = [[`=IF(COUNTIF('${sheetName}'!$W$5:$W$1000,"Failed")>0,"Failed",IF(COUNTIF('${sheetName}'!$W$5:$W$1000,"Blocked")>0,"Blocked",IF(COUNTIF('${sheetName}'!$W$5:$W$1000,"Passed")=B${row},"Passed","Not Run")))`]];
  summarySheet.getRange(`J${row}`).values = [[note]];
});

const totalRow = summaryStart + sheetNames.length;
summarySheet.getRange(`A${totalRow}`).values = [["TOTAL"]];
for (const col of ["B", "C", "D", "E", "F", "G"]) {
  summarySheet.getRange(`${col}${totalRow}`).formulas = [[`=SUM(${col}${summaryStart}:${col}${totalRow - 1})`]];
}
summarySheet.getRange(`H${totalRow}`).values = [["P0"]];
summarySheet.getRange(`I${totalRow}`).formulas = [[`=IF(COUNTIF(I${summaryStart}:I${totalRow - 1},"Failed")>0,"Failed",IF(COUNTIF(I${summaryStart}:I${totalRow - 1},"Blocked")>0,"Blocked",IF(COUNTIF(I${summaryStart}:I${totalRow - 1},"Passed")=${sheetNames.length},"Passed","Not Run")))`]];
summarySheet.getRange(`J${totalRow}`).values = [["Formula-driven totals across all execution sheets."]];
summarySheet.getRange(`A${totalRow}:J${totalRow}`).format = { fill: colors.navy, font: { bold: true, color: colors.white }, borders: { preset: "outside", style: "medium", color: colors.navy } };

const unknownStart = totalRow + 3;
summarySheet.getRange(`A${unknownStart}:J${unknownStart}`).merge();
summarySheet.getRange(`A${unknownStart}`).values = [["Requires clarification / not determined from current implementation"]];
summarySheet.getRange(`A${unknownStart}:J${unknownStart}`).format = { fill: colors.p1, font: { bold: true, color: "#6B4100" } };
catalog.unknowns.forEach((item, i) => {
  const row = unknownStart + 1 + i;
  summarySheet.getRange(`A${row}:J${row}`).merge();
  summarySheet.getRange(`A${row}`).values = [[`• ${item}`]];
  summarySheet.getRange(`A${row}:J${row}`).format = { fill: "#FFF9ED", font: { color: colors.ink, size: 10 }, wrapText: true };
  summarySheet.getRange(`A${row}:J${row}`).format.rowHeight = 30;
});

summarySheet.getRange(`A8:J${totalRow - 1}`).format = { font: { name: "Aptos", size: 9, color: colors.ink }, verticalAlignment: "top", wrapText: true, borders: { insideHorizontal: { style: "thin", color: "#E4EBEF" } } };
summarySheet.getRange(`A8:J${totalRow - 1}`).format.rowHeight = 38;
summarySheet.getRange(`B8:I${totalRow}`).format.horizontalAlignment = "center";
const summaryWidths = [30, 15, 13, 13, 13, 13, 14, 10, 14, 78];
summaryWidths.forEach((w, i) => { summarySheet.getRange(`${colName(i)}:${colName(i)}`).format.columnWidth = w; });
summarySheet.freezePanes.freezeRows(7);
summarySheet.freezePanes.freezeColumns(1);
summarySheet.tables.add(`A7:J${totalRow - 1}`, true, "T_Test_Summary").style = "TableStyleMedium2";
summarySheet.getRange(`H${summaryStart}:H${totalRow}`).conditionalFormats.add("expression", { formula: `=H${summaryStart}="P0"`, format: { fill: colors.p0, font: { color: "#8A1C25", bold: true } } });
summarySheet.getRange(`H${summaryStart}:H${totalRow}`).conditionalFormats.add("expression", { formula: `=H${summaryStart}="P1"`, format: { fill: colors.p1, font: { color: "#8A4B08", bold: true } } });
summarySheet.getRange(`I${summaryStart}:I${totalRow}`).conditionalFormats.add("expression", { formula: `=I${summaryStart}="Passed"`, format: { fill: colors.pass, font: { color: "#235C34", bold: true } } });
summarySheet.getRange(`I${summaryStart}:I${totalRow}`).conditionalFormats.add("expression", { formula: `=I${summaryStart}="Failed"`, format: { fill: colors.fail, font: { color: "#8A1C25", bold: true } } });
summarySheet.getRange(`I${summaryStart}:I${totalRow}`).conditionalFormats.add("expression", { formula: `=I${summaryStart}="Blocked"`, format: { fill: colors.block, font: { color: "#8A4B08", bold: true } } });

const inspect = await workbook.inspect({ kind: "table", range: `00_Test_Summary!A1:J${Math.min(totalRow + 8, 50)}`, include: "values,formulas", tableMaxRows: 50, tableMaxCols: 10, maxChars: 12000 });
console.log(inspect.ndjson);
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 300 }, summary: "final formula error scan", maxChars: 4000 });
console.log(errors.ndjson);

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(path.join(outputDir, "System_Test_Cases.xlsx"));

if (process.env.QA_SKIP_RENDER !== "1") {
  for (const [index, sheetName] of ["00_Test_Summary", ...sheetNames].entries()) {
    const range = sheetName === "00_Test_Summary"
      ? `A1:J${Math.min(totalRow + 8, 50)}`
      : index <= 2 ? "A1:Z8" : "A1:F6";
    const blob = await workbook.render({ sheetName, range, scale: 0.55, format: "png" });
    const bytes = new Uint8Array(await blob.arrayBuffer());
    await fs.writeFile(path.join(previewDir, `${sheetName}.png`), bytes);
  }
}

console.log(JSON.stringify({ output: path.join(outputDir, "System_Test_Cases.xlsx"), previews: sheetNames.length + 1, summary: catalog.summary }));
