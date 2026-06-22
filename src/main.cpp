#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <vector>
#include <algorithm>

// =========================
// User configuration
// =========================
static const char* WIFI_SSID = "YOUR_WIFI_SSID";
static const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";

// Pico W UART pins to DROK 200310
static const uint8_t UART_TX_PIN = 4;  // Pico TX -> DROK RX
static const uint8_t UART_RX_PIN = 5;  // Pico RX <- DROK TX
static const uint32_t UART_BAUD = 4800;

static const uint32_t POLL_INTERVAL_MS = 250;
static const size_t GRAPH_POINTS = 180;

// =========================
// DROK UART helper
// =========================
class Drok200310 {
 public:
  explicit Drok200310(HardwareSerial& serial) : serial_(serial) {}

  void begin(uint8_t txPin, uint8_t rxPin, uint32_t baud) {
    serial_.setTX(txPin);
    serial_.setRX(rxPin);
    serial_.begin(baud);
    while (serial_.available()) serial_.read();
  }

  String sendCommand(const String& cmd, uint32_t waitMs = 90) {
    while (serial_.available()) serial_.read();
    serial_.print(cmd);
    serial_.print("\r\n");
    serial_.flush();

    uint32_t start = millis();
    String resp;
    while ((millis() - start) < waitMs) {
      while (serial_.available()) {
        char c = static_cast<char>(serial_.read());
        resp += c;
      }
      delay(2);
    }
    resp.trim();
    return resp;
  }

  static float parseHundredthsValue(const String& response) {
    String digits;
    for (size_t i = 0; i < response.length(); ++i) {
      char c = response.charAt(i);
      if (isDigit(c)) digits += c;
    }
    if (digits.length() == 0) return NAN;
    return digits.toInt() / 100.0f;
  }

  bool readActualVoltage(float& volts, String& raw) {
    raw = sendCommand("aru");
    volts = parseHundredthsValue(raw);
    return !isnan(volts);
  }

  bool readActualCurrent(float& amps, String& raw) {
    raw = sendCommand("ari");
    amps = parseHundredthsValue(raw);
    return !isnan(amps);
  }

  bool setVoltage(float volts, String& raw) {
    int value = static_cast<int>(roundf(volts * 100.0f));
    char cmd[16];
    snprintf(cmd, sizeof(cmd), "awu%04d", value);
    raw = sendCommand(cmd);
    return raw.length() > 0;
  }

  bool setCurrent(float amps, String& raw) {
    int value = static_cast<int>(roundf(amps * 100.0f));
    char cmd[16];
    snprintf(cmd, sizeof(cmd), "awi%04d", value);
    raw = sendCommand(cmd);
    return raw.length() > 0;
  }

  bool setOutput(bool enabled, String& raw) {
    raw = sendCommand(enabled ? "awo1" : "awo0");
    return raw.length() > 0;
  }

  bool recallMemory(uint8_t slot, String& raw) {
    if (slot > 9) return false;
    char cmd[8];
    snprintf(cmd, sizeof(cmd), "awm%u", slot);
    raw = sendCommand(cmd);
    return raw.length() > 0;
  }

 private:
  HardwareSerial& serial_;
};

struct Sample {
  uint32_t tMs;
  float volts;
  float amps;
  float watts;
};

WebServer server(80);
Drok200310 psu(Serial1);
std::vector<Sample> samples;

float gVolts = NAN;
float gAmps = NAN;
float gWatts = NAN;
bool gOutputEnabled = false;
String gLastVRaw;
String gLastIRaw;
String gLastCmdRaw;
uint32_t lastPollMs = 0;

static String htmlEscape(String s) {
  s.replace("&", "&amp;");
  s.replace("<", "&lt;");
  s.replace(">", "&gt;");
  s.replace("\"", "&quot;");
  return s;
}

void addSample(float volts, float amps) {
  Sample s;
  s.tMs = millis();
  s.volts = volts;
  s.amps = amps;
  s.watts = volts * amps;
  samples.push_back(s);
  if (samples.size() > GRAPH_POINTS) {
    samples.erase(samples.begin());
  }
}

String jsonMetrics() {
  String out = "{";
  out += "\"volts\":" + String(isnan(gVolts) ? 0.0f : gVolts, 2) + ",";
  out += "\"amps\":" + String(isnan(gAmps) ? 0.0f : gAmps, 2) + ",";
  out += "\"watts\":" + String(isnan(gWatts) ? 0.0f : gWatts, 2) + ",";
  out += "\"output\":" + String(gOutputEnabled ? "true" : "false") + ",";
  out += "\"rawV\":\"" + htmlEscape(gLastVRaw) + "\",";
  out += "\"rawI\":\"" + htmlEscape(gLastIRaw) + "\",";
  out += "\"lastCmd\":\"" + htmlEscape(gLastCmdRaw) + "\",";
  out += "\"samples\":[";
  for (size_t i = 0; i < samples.size(); ++i) {
    if (i) out += ",";
    out += "{";
    out += "\"t\":" + String(samples[i].tMs) + ",";
    out += "\"v\":" + String(samples[i].volts, 2) + ",";
    out += "\"a\":" + String(samples[i].amps, 2) + ",";
    out += "\"w\":" + String(samples[i].watts, 2);
    out += "}";
  }
  out += "]}";
  return out;
}

String pageHtml() {
  return R"HTML(
<!doctype html>
<html>
<head>
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>DROK 200310 Monitor</title>
  <style>
    body{font-family:Arial,sans-serif;background:#0d1117;color:#e6edf3;margin:0;padding:16px}
    .wrap{max-width:980px;margin:0 auto}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}
    .card{background:#161b22;border:1px solid #30363d;border-radius:14px;padding:14px;box-shadow:0 3px 10px rgba(0,0,0,.25)}
    .value{font-size:2rem;font-weight:700}
    .muted{color:#9da7b3;font-size:.92rem}
    input,button,select{font-size:1rem;padding:10px;border-radius:10px;border:1px solid #3d444d;background:#0d1117;color:#e6edf3}
    button{cursor:pointer}
    .row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
    svg{width:100%;height:320px;background:#0b0f14;border-radius:12px;border:1px solid #30363d}
    .small{font-size:.85rem;white-space:pre-wrap;word-break:break-word}
    .on{color:#3fb950}.off{color:#f85149}
  </style>
</head>
<body>
<div class="wrap">
  <h2>DROK 200310 UART Dashboard</h2>
  <div class="grid">
    <div class="card"><div class="muted">Voltage</div><div class="value" id="v">0.00 V</div></div>
    <div class="card"><div class="muted">Current</div><div class="value" id="a">0.00 A</div></div>
    <div class="card"><div class="muted">Power</div><div class="value" id="w">0.00 W</div></div>
    <div class="card"><div class="muted">Output</div><div class="value" id="o">UNKNOWN</div></div>
  </div>

  <div class="grid" style="margin-top:12px">
    <div class="card">
      <div class="muted">Set Voltage / Current</div>
      <div class="row" style="margin-top:10px">
        <input id="setv" type="number" step="0.01" placeholder="Volts">
        <button onclick="setVoltage()">Set V</button>
      </div>
      <div class="row" style="margin-top:10px">
        <input id="seta" type="number" step="0.01" placeholder="Amps">
        <button onclick="setCurrent()">Set A</button>
      </div>
      <div class="row" style="margin-top:10px">
        <button onclick="setOutput(1)">Output ON</button>
        <button onclick="setOutput(0)">Output OFF</button>
      </div>
    </div>

    <div class="card">
      <div class="muted">Presets</div>
      <div class="row" style="margin-top:10px">
        <select id="mem">
          <option value="0">M0</option><option value="1">M1</option><option value="2">M2</option>
          <option value="3">M3</option><option value="4">M4</option><option value="5">M5</option>
          <option value="6">M6</option><option value="7">M7</option><option value="8">M8</option>
          <option value="9">M9</option>
        </select>
        <button onclick="recallMemory()">Recall</button>
      </div>
      <div class="small" id="status" style="margin-top:12px">Ready</div>
    </div>
  </div>

  <div class="card" style="margin-top:12px">
    <div class="muted">Trend Scope (UART sample history)</div>
    <svg id="chart" viewBox="0 0 900 320"></svg>
  </div>

  <div class="grid" style="margin-top:12px">
    <div class="card"><div class="muted">Raw Voltage Reply</div><div class="small" id="rawv"></div></div>
    <div class="card"><div class="muted">Raw Current Reply</div><div class="small" id="rawi"></div></div>
    <div class="card"><div class="muted">Last Command Reply</div><div class="small" id="lastcmd"></div></div>
  </div>
</div>

<script>
async function post(path, body){
  const r = await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  return await r.json();
}
function linePath(points, key, maxY, h, w, pad){
  if(!points.length) return '';
  return points.map((p,i)=>{
    const x = pad + (i * (w - pad*2) / Math.max(1, points.length - 1));
    const y = h - pad - ((p[key] / Math.max(0.0001, maxY)) * (h - pad*2));
    return (i===0?'M':'L') + x.toFixed(1) + ' ' + y.toFixed(1);
  }).join(' ');
}
function renderChart(data){
  const svg = document.getElementById('chart');
  const w=900,h=320,pad=24;
  const maxV = Math.max(1,...data.samples.map(s=>s.v));
  const maxA = Math.max(1,...data.samples.map(s=>s.a));
  const maxW = Math.max(1,...data.samples.map(s=>s.w));
  const pv = linePath(data.samples,'v',maxV,h,w,pad);
  const pa = linePath(data.samples,'a',maxA,h,w,pad);
  const pw = linePath(data.samples,'w',maxW,h,w,pad);
  let grid='';
  for(let i=0;i<5;i++){
    const y=pad + i*((h-pad*2)/4);
    grid += `<line x1="${pad}" y1="${y}" x2="${w-pad}" y2="${y}" stroke="#263040" stroke-width="1"/>`;
  }
  svg.innerHTML = `
    <rect x="0" y="0" width="${w}" height="${h}" fill="#0b0f14" rx="12"/>
    ${grid}
    <path d="${pv}" fill="none" stroke="#58a6ff" stroke-width="2"/>
    <path d="${pa}" fill="none" stroke="#3fb950" stroke-width="2"/>
    <path d="${pw}" fill="none" stroke="#f2cc60" stroke-width="2"/>
    <text x="${pad}" y="18" fill="#58a6ff" font-size="13">Voltage</text>
    <text x="${pad+80}" y="18" fill="#3fb950" font-size="13">Current</text>
    <text x="${pad+160}" y="18" fill="#f2cc60" font-size="13">Power</text>`;
}
async function refresh(){
  const r = await fetch('/api/metrics');
  const data = await r.json();
  document.getElementById('v').textContent = data.volts.toFixed(2)+' V';
  document.getElementById('a').textContent = data.amps.toFixed(2)+' A';
  document.getElementById('w').textContent = data.watts.toFixed(2)+' W';
  const o = document.getElementById('o');
  o.textContent = data.output ? 'ON' : 'OFF';
  o.className = 'value ' + (data.output ? 'on':'off');
  document.getElementById('rawv').textContent = data.rawV;
  document.getElementById('rawi').textContent = data.rawI;
  document.getElementById('lastcmd').textContent = data.lastCmd;
  renderChart(data);
}
async function setVoltage(){
  const v = parseFloat(document.getElementById('setv').value);
  const r = await post('/api/set_voltage',{value:v});
  document.getElementById('status').textContent = JSON.stringify(r);
  refresh();
}
async function setCurrent(){
  const a = parseFloat(document.getElementById('seta').value);
  const r = await post('/api/set_current',{value:a});
  document.getElementById('status').textContent = JSON.stringify(r);
  refresh();
}
async function setOutput(on){
  const r = await post('/api/set_output',{enabled:!!on});
  document.getElementById('status').textContent = JSON.stringify(r);
  refresh();
}
async function recallMemory(){
  const m = parseInt(document.getElementById('mem').value,10);
  const r = await post('/api/recall_memory',{slot:m});
  document.getElementById('status').textContent = JSON.stringify(r);
  refresh();
}
setInterval(refresh, 1000);
refresh();
</script>
</body>
</html>
)HTML";
}

String readRequestBody() {
  if (!server.hasArg("plain")) return "";
  return server.arg("plain");
}

bool extractNumberValue(const String& body, const char* key, float& outValue) {
  String token = String("\"") + key + "\":";
  int idx = body.indexOf(token);
  if (idx < 0) return false;
  idx += token.length();
  int end = idx;
  while (end < body.length() && (isDigit(body[end]) || body[end] == '.' || body[end] == '-')) end++;
  outValue = body.substring(idx, end).toFloat();
  return true;
}

bool extractBoolValue(const String& body, const char* key, bool& outValue) {
  String token = String("\"") + key + "\":";
  int idx = body.indexOf(token);
  if (idx < 0) return false;
  idx += token.length();
  String rem = body.substring(idx);
  rem.trim();
  outValue = rem.startsWith("true") || rem.startsWith("1");
  return true;
}

void sendJsonOk(const String& extra) {
  server.send(200, "application/json", String("{\"ok\":true") + extra + "}");
}

void sendJsonError(const String& message) {
  server.send(400, "application/json", String("{\"ok\":false,\"error\":\"") + htmlEscape(message) + "\"}");
}

void handleRoot() { server.send(200, "text/html", pageHtml()); }
void handleMetrics() { server.send(200, "application/json", jsonMetrics()); }

void handleSetVoltage() {
  float v;
  String body = readRequestBody();
  if (!extractNumberValue(body, "value", v)) return sendJsonError("Missing value");
  if (v < 0.0f || v > 60.0f) return sendJsonError("Voltage out of range");
  bool ok = psu.setVoltage(v, gLastCmdRaw);
  server.send(200, "application/json", String("{\"ok\":") + (ok ? "true" : "false") + ",\"reply\":\"" + htmlEscape(gLastCmdRaw) + "\"}");
}

void handleSetCurrent() {
  float a;
  String body = readRequestBody();
  if (!extractNumberValue(body, "value", a)) return sendJsonError("Missing value");
  if (a < 0.0f || a > 12.0f) return sendJsonError("Current out of range");
  bool ok = psu.setCurrent(a, gLastCmdRaw);
  server.send(200, "application/json", String("{\"ok\":") + (ok ? "true" : "false") + ",\"reply\":\"" + htmlEscape(gLastCmdRaw) + "\"}");
}

void handleSetOutput() {
  bool enabled = false;
  String body = readRequestBody();
  if (!extractBoolValue(body, "enabled", enabled)) return sendJsonError("Missing enabled");
  bool ok = psu.setOutput(enabled, gLastCmdRaw);
  if (ok) gOutputEnabled = enabled;
  server.send(200, "application/json", String("{\"ok\":") + (ok ? "true" : "false") + ",\"reply\":\"" + htmlEscape(gLastCmdRaw) + "\",\"output\":" + (gOutputEnabled ? "true" : "false") + "}");
}

void handleRecallMemory() {
  float slotFloat;
  String body = readRequestBody();
  if (!extractNumberValue(body, "slot", slotFloat)) return sendJsonError("Missing slot");
  int slot = static_cast<int>(slotFloat);
  if (slot < 0 || slot > 9) return sendJsonError("Slot out of range");
  bool ok = psu.recallMemory(static_cast<uint8_t>(slot), gLastCmdRaw);
  server.send(200, "application/json", String("{\"ok\":") + (ok ? "true" : "false") + ",\"reply\":\"" + htmlEscape(gLastCmdRaw) + "\"}");
}

void pollPsu() {
  if (millis() - lastPollMs < POLL_INTERVAL_MS) return;
  lastPollMs = millis();

  float volts = NAN, amps = NAN;
  bool okV = psu.readActualVoltage(volts, gLastVRaw);
  bool okA = psu.readActualCurrent(amps, gLastIRaw);

  if (okV) gVolts = volts;
  if (okA) gAmps = amps;
  if (!isnan(gVolts) && !isnan(gAmps)) {
    gWatts = gVolts * gAmps;
    addSample(gVolts, gAmps);
  }
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("Booting DROK 200310 Pico W dashboard...");

  psu.begin(UART_TX_PIN, UART_RX_PIN, UART_BAUD);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Connecting to WiFi");
  uint32_t wifiStart = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - wifiStart < 20000) {
    delay(400);
    Serial.print('.');
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("WiFi connected. IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("WiFi failed. Web UI unavailable until reconnect.");
  }

  server.on("/", HTTP_GET, handleRoot);
  server.on("/api/metrics", HTTP_GET, handleMetrics);
  server.on("/api/set_voltage", HTTP_POST, handleSetVoltage);
  server.on("/api/set_current", HTTP_POST, handleSetCurrent);
  server.on("/api/set_output", HTTP_POST, handleSetOutput);
  server.on("/api/recall_memory", HTTP_POST, handleRecallMemory);
  server.begin();
  Serial.println("HTTP server started.");
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    static uint32_t lastRetry = 0;
    if (millis() - lastRetry > 10000) {
      lastRetry = millis();
      WiFi.disconnect();
      WiFi.begin(WIFI_SSID, WIFI_PASS);
    }
  }

  server.handleClient();
  pollPsu();
}
