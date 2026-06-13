import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const cwd = process.cwd();
const outputDir = path.join(cwd, "outputs", "lottery_ocr_20260613");
const sourceImage = path.join(cwd, "2026-06", "671dac68-4b46-4aad-9d51-2f1a8ceeb92c.jpg");
const row02Crop = path.join(outputDir, "row02_crop.png");
const row04Crop = path.join(outputDir, "row04_crop.png");
const row12Crop = path.join(outputDir, "row12_crop.png");
const outputFile = path.join(outputDir, "投注识别统计_20260613_核对版_全部核查截图.xlsx");

const detailRows = [
  [1, "胆0 — 200", "胆码", "福胆0各200元", 200, "否", "单独数字0，按规则默认胆码；左侧有涂写但不影响数字与金额"],
  [2, "疑似胆24 — 200", "胆码", "福胆24各200元", 200, "是", "前缀被涂写，24按“胆24”处理；需核对是否为胆码"],
  [3, "0459组三 — 100", "组三", "福0459组三各100元", 100, "否", ""],
  [4, "1369组三 — 100", "组三", "福1369组三各100元", 100, "是", "玩法字样局部有涂写，按可见“三/组三”处理"],
  [5, "01569组三 — 200", "组三", "福01569组三各200元", 200, "否", ""],
  [6, "2X6 — 200", "定位", "福2*6定各200元", 200, "否", "X按规则转换为*"],
  [7, "胆3 — 500", "胆码", "福胆3各500元", 500, "否", "单独数字3，按规则默认胆码；红圈忽略"],
  [8, "胆6 — 500", "胆码", "福胆6各500元", 500, "否", "单独数字6，按规则默认胆码；红圈忽略"],
  [9, "0456组选 — 200", "组六", "福0456组六各200元", 200, "否", "组选未标三/六，数字串≥3位，按规则默认组六"],
  [10, "1457组选 — 100", "组六", "福1457组六各100元", 100, "否", "同上"],
  [11, "05679组选 — 300", "组六", "福05679组六各300元", 300, "否", "同上"],
  [12, "疑似511 — 200", "组六", "福511组六各200元", 200, "是", "见本列截图；重新识别为疑似数字511，不按定位"],
];

const headers = ["序号", "原图识别内容", "玩法判定", "标准化结果", "金额(元)", "需人工核查", "核查原因/备注"];
const workbook = Workbook.create();
const summary = workbook.worksheets.add("统计总览");
const detail = workbook.worksheets.add("识别明细");
const images = workbook.worksheets.add("截图核对");

for (const sheet of [summary, detail, images]) {
  sheet.showGridLines = false;
}

// 识别明细
detail.getRange("A1:G1").values = [headers];
detail.getRange(`A2:G${detailRows.length + 1}`).values = detailRows;
detail.getRange("A1:G1").format = {
  fill: "#1F4E78",
  font: { bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
detail.getRange("A1:A20").format.columnWidthPx = 58;
detail.getRange("B1:B20").format.columnWidthPx = 155;
detail.getRange("C1:C20").format.columnWidthPx = 90;
detail.getRange("D1:D20").format.columnWidthPx = 205;
detail.getRange("E1:E20").format.columnWidthPx = 85;
detail.getRange("F1:F20").format.columnWidthPx = 100;
detail.getRange("G1:G20").format.columnWidthPx = 460;
detail.getRange(`A1:G${detailRows.length + 1}`).format.wrapText = true;
detail.getRange(`A1:G${detailRows.length + 1}`).format.verticalAlignment = "center";
detail.getRange(`E2:E${detailRows.length + 1}`).format.numberFormat = "0";
detail.getRange("G13").values = [[""]];
detail.getRange("G3").values = [[""]];
detail.getRange("G5").values = [[""]];
detail.getRange("A3:G3").format.rowHeightPx = 155;
detail.getRange("A5:G5").format.rowHeightPx = 180;
detail.getRange("A13:G13").format.rowHeightPx = 235;
detail.freezePanes.freezeRows(1);
const detailTable = detail.tables.add(`A1:G${detailRows.length + 1}`, true, "LotteryOcrDetail");
detailTable.style = "TableStyleMedium2";

// 人工核查行高亮
for (let i = 0; i < detailRows.length; i++) {
  if (detailRows[i][5] === "是") {
    const row = i + 2;
    detail.getRange(`A${row}:G${row}`).format.fill = "#FFF2CC";
    detail.getRange(`F${row}`).format.font = { bold: true, color: "#C00000" };
  }
}

// 统计总览
summary.getRange("A1:G1").merge();
summary.getRange("A1").values = [["投注识别统计核对表"]];
summary.getRange("A1").format = {
  fill: "#1F4E78",
  font: { bold: true, color: "#FFFFFF", size: 16 },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  rowHeightPx: 34,
};
summary.getRange("A3:B7").values = [
  ["来源图片", "671dac68-4b46-4aad-9d51-2f1a8ceeb92c.jpg"],
  ["识别条数", detailRows.length],
  ["合计金额(含待核)", null],
  ["需人工核查条数", null],
  ["需人工核查金额", null],
];
summary.getRange("B5").formulas = [[`=SUM('识别明细'!E2:E${detailRows.length + 1})`]];
summary.getRange("B6").formulas = [[`=COUNTIF('识别明细'!F2:F${detailRows.length + 1},"是")`]];
summary.getRange("B7").formulas = [[`=SUMIF('识别明细'!F2:F${detailRows.length + 1},"是",'识别明细'!E2:E${detailRows.length + 1})`]];
summary.getRange("A3:A7").format = {
  fill: "#D9EAF7",
  font: { bold: true },
  horizontalAlignment: "right",
};
summary.getRange("B3:B7").format = { fill: "#F7FBFF", horizontalAlignment: "left" };
summary.getRange("B5:B7").format.numberFormat = "0";
summary.getRange("A9:C9").values = [["玩法判定", "条数", "金额(元)"]];
summary.getRange("A10:A13").values = [["胆码"], ["组三"], ["组六"], ["定位"]];
for (let r = 10; r <= 13; r++) {
  summary.getRange(`B${r}`).formulas = [[`=COUNTIF('识别明细'!C2:C${detailRows.length + 1},A${r})`]];
  summary.getRange(`C${r}`).formulas = [[`=SUMIF('识别明细'!C2:C${detailRows.length + 1},A${r},'识别明细'!E2:E${detailRows.length + 1})`]];
}
summary.getRange("A9:C9").format = {
  fill: "#70AD47",
  font: { bold: true, color: "#FFFFFF" },
  horizontalAlignment: "center",
};
summary.getRange("A9:C13").format.wrapText = true;
summary.getRange("C10:C13").format.numberFormat = "0";
summary.getRange("A15:G19").values = [
  ["核对说明", "", "", "", "", "", ""],
  ["1. 红色圈注不计入识别，仅保留在截图中方便核对。", "", "", "", "", "", ""],
  ["2. 第12行已由原先错误的“5**”修正为疑似数字“511”，不再按定位处理。", "", "", "", "", "", ""],
  ["3. 凡不确定项均在“需人工核查”列标注为“是”，合计金额暂按识别金额计入。", "", "", "", "", "", ""],
  ["4. 请重点核对第2、4、12行，尤其第12行局部截图。", "", "", "", "", "", ""],
];
summary.getRange("A15:G15").merge();
summary.getRange("A16:G16").merge();
summary.getRange("A17:G17").merge();
summary.getRange("A18:G18").merge();
summary.getRange("A19:G19").merge();
summary.getRange("A15").format = {
  fill: "#F4B183",
  font: { bold: true },
};
summary.getRange("A16:A19").format.wrapText = true;
summary.getRange("A1:A25").format.columnWidthPx = 150;
summary.getRange("B1:B25").format.columnWidthPx = 260;
summary.getRange("C1:C25").format.columnWidthPx = 120;
summary.getRange("D1:G25").format.columnWidthPx = 110;

// 截图核对
images.getRange("A1:H1").merge();
images.getRange("A1").values = [["截图核对（红色圈注忽略，仅用于人工核对原图）"]];
images.getRange("A1").format = {
  fill: "#1F4E78",
  font: { bold: true, color: "#FFFFFF", size: 14 },
  horizontalAlignment: "center",
  verticalAlignment: "center",
  rowHeightPx: 30,
};
images.getRange("A3").values = [["原图整页"]];
images.getRange("J3").values = [["第12行局部截图（疑似511 — 200）"]];
images.getRange("A3:J3").format = { font: { bold: true }, fill: "#D9EAD3" };
images.getRange("A1:A45").format.columnWidthPx = 90;
images.getRange("B1:I45").format.columnWidthPx = 75;
images.getRange("J1:J45").format.columnWidthPx = 155;
images.getRange("K1:N45").format.columnWidthPx = 80;

const addImageIfExists = async (sheet, filePath, anchor, widthPx, heightPx, mime = "image/jpeg") => {
  const data = await fs.readFile(filePath);
  const dataUrl = `data:${mime};base64,${data.toString("base64")}`;
  sheet.images.add({
    dataUrl,
    anchor: { from: anchor, extent: { widthPx, heightPx } },
  });
};

await fs.mkdir(outputDir, { recursive: true });
await addImageIfExists(detail, row02Crop, { row: 2, col: 6 }, 430, 150, "image/png");
await addImageIfExists(detail, row04Crop, { row: 4, col: 6 }, 430, 175, "image/png");
await addImageIfExists(detail, row12Crop, { row: 12, col: 6 }, 430, 265, "image/png");
await addImageIfExists(images, sourceImage, { row: 4, col: 0 }, 425, 640, "image/jpeg");
await addImageIfExists(images, row12Crop, { row: 4, col: 9 }, 390, 240, "image/png");

// Compact verification output.
const detailInspect = await workbook.inspect({
  kind: "table",
  range: `识别明细!A1:G${detailRows.length + 1}`,
  include: "values,formulas",
  tableMaxRows: 14,
  tableMaxCols: 7,
});
console.log(detailInspect.ndjson);
const errorScan = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 50 },
  summary: "final formula error scan",
});
console.log(errorScan.ndjson);

// Render one pass for visual sanity.
const preview = await workbook.render({ sheetName: "识别明细", range: "A1:G13", scale: 1, format: "png" });
await fs.writeFile(path.join(outputDir, "识别明细预览.png"), new Uint8Array(await preview.arrayBuffer()));

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputFile);
console.log(outputFile);
