/**
 * Nick's Edge Dashboard - optional helper for the Google Sheet.
 * Research screen, not a trade signal.
 *
 * Adds a menu "Nick's Edge" with:
 *   1. Set up data tabs      - makes one tab per data file, each filled by IMPORTDATA from GitHub
 *   2. Refresh data now      - re-pulls every tab right away (Sheets also refreshes by itself about every hour)
 *   3. Make Looker Studio link - opens Looker Studio with the Top Setups tab already connected
 * Nothing here needs a password or a key. It only reads public files from your GitHub repo.
 */
var TABS = ["top_setups", "scorecard_details", "news_risk", "upcoming_events", "econ_data", "econ_strength",
            "cot_report", "cot_history", "retail_sentiment", "put_call", "seasonality", "momentum", "volatility",
            "market_heatmap", "carry", "rates", "spreads", "calendar", "news", "score_history", "backtest",
            "updates_log", "help", "settings"];

function onOpen() {
  SpreadsheetApp.getUi().createMenu("Nick's Edge")
    .addItem("1. Set up data tabs", "setupTabs")
    .addItem("2. Refresh data now", "refreshNow")
    .addItem("3. Make Looker Studio link", "showLookerLink")
    .addToUi();
}

function baseUrl_() {
  var setup = SpreadsheetApp.getActive().getSheetByName("Setup");
  if (!setup) throw new Error("Please add a tab called Setup first (it comes with the starter file).");
  var user = String(setup.getRange("B2").getValue()).trim();
  var repo = String(setup.getRange("B3").getValue()).trim() || "nicks-edge-dashboard";
  var branch = String(setup.getRange("B4").getValue()).trim() || "main";
  if (!user) throw new Error("Type your GitHub username in Setup!B2 first.");
  return "https://raw.githubusercontent.com/" + user + "/" + repo + "/" + branch + "/output/";
}

function setupTabs() {
  var ss = SpreadsheetApp.getActive();
  baseUrl_();  // checks the Setup tab
  TABS.forEach(function (t) {
    var sh = ss.getSheetByName(t) || ss.insertSheet(t);
    sh.getRange("A1").setFormula('=IMPORTDATA(Setup!$B$5&"' + t + '.csv"&Setup!$B$6)');
  });
  SpreadsheetApp.getUi().alert("Done. " + TABS.length + " data tabs are linked to your GitHub files.");
}

function refreshNow() {
  // changing the cache-buster cell makes every IMPORTDATA formula fetch again
  SpreadsheetApp.getActive().getSheetByName("Setup").getRange("B6").setValue("?v=" + new Date().getTime());
}

function lookerLink_() {
  var ss = SpreadsheetApp.getActive();
  var sh = ss.getSheetByName("top_setups");
  if (!sh) throw new Error("Run '1. Set up data tabs' first.");
  var p = ["r.reportName=" + encodeURIComponent("Nick's Edge Dashboard"),
           "ds.connector=googleSheets",
           "ds.spreadsheetId=" + ss.getId(),
           "ds.worksheetId=" + sh.getSheetId(),
           "ds.datasourceName=" + encodeURIComponent("Edge - top_setups"),
           "ds.hasHeader=true"];
  return "https://lookerstudio.google.com/reporting/create?" + p.join("&");
}

/** Lists every tab with its id, so each one can be added in Looker Studio with Add data > Google Sheets. */
function tabIds_() {
  return TABS.map(function (t) {
    var sh = SpreadsheetApp.getActive().getSheetByName(t);
    return t + " = " + (sh ? sh.getSheetId() : "missing");
  }).join("<br>");
}

function showLookerLink() {
  var url = lookerLink_();
  var html = HtmlService.createHtmlOutput(
      '<p style="font-family:Arial">Click to open Looker Studio with your Top Setups data connected:</p>' +
      '<p><a target="_blank" href="' + url + '">Open Nick\'s Edge Dashboard in Looker Studio</a></p>' +
      '<p style="font-family:Arial;font-size:12px;color:#555">Tab ids (for adding the other tabs):<br>' + tabIds_() + '</p>')
    .setWidth(520).setHeight(420);
  SpreadsheetApp.getUi().showModalDialog(html, "Looker Studio link");
}
