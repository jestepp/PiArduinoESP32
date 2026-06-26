#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <Preferences.h>
#include <WebServer.h>
#include <WiFi.h>
#include "esp_camera.h"
#include "esp_timer.h"

namespace {

constexpr char kDefaultApSsid[] = "XIAO-S3-Camera";
constexpr char kDefaultApPass[] = "camera1234";
constexpr char kPrefsNamespace[] = "cam";
constexpr char kBleServiceUuid[] = "b2b7f440-1c2a-45a8-a7c7-8fd6f7d90201";
constexpr char kBleConfigUuid[] = "b2b7f441-1c2a-45a8-a7c7-8fd6f7d90201";

// Seeed XIAO ESP32-S3 Sense camera connector pin map.
constexpr int PWDN_GPIO_NUM = 21;
constexpr int RESET_GPIO_NUM = 1;
constexpr int XCLK_GPIO_NUM = 10;
constexpr int SIOD_GPIO_NUM = 40;
constexpr int SIOC_GPIO_NUM = 39;
constexpr int Y9_GPIO_NUM = 48;
constexpr int Y8_GPIO_NUM = 11;
constexpr int Y7_GPIO_NUM = 12;
constexpr int Y6_GPIO_NUM = 14;
constexpr int Y5_GPIO_NUM = 16;
constexpr int Y4_GPIO_NUM = 18;
constexpr int Y3_GPIO_NUM = 17;
constexpr int Y2_GPIO_NUM = 15;
constexpr int VSYNC_GPIO_NUM = 38;
constexpr int HREF_GPIO_NUM = 47;
constexpr int PCLK_GPIO_NUM = 13;

const int kCameraPins[] = {
    PWDN_GPIO_NUM, RESET_GPIO_NUM, XCLK_GPIO_NUM, SIOD_GPIO_NUM, SIOC_GPIO_NUM,
    Y9_GPIO_NUM, Y8_GPIO_NUM, Y7_GPIO_NUM, Y6_GPIO_NUM, Y5_GPIO_NUM,
    Y4_GPIO_NUM, Y3_GPIO_NUM, Y2_GPIO_NUM, VSYNC_GPIO_NUM, HREF_GPIO_NUM,
    PCLK_GPIO_NUM};

const int kUserPins[] = {2, 3, 4, 5, 6, 7, 8, 9, 41, 42, 43, 44};

Preferences prefs;
WebServer server(80);
BLECharacteristic *configCharacteristic = nullptr;

String wifiSsid;
String wifiPass;
String apSsid;
String apPass;
framesize_t frameSize = FRAMESIZE_SVGA;
int jpegQuality = 10;
int xclkMhz = 20;
bool stationConnected = false;

struct PinState {
  int pin;
  String mode;
  int value;
};

bool isCameraPin(int pin) {
  for (int cameraPin : kCameraPins) {
    if (cameraPin == pin) {
      return true;
    }
  }
  return false;
}

String htmlEscape(const String &value) {
  String escaped = value;
  escaped.replace("&", "&amp;");
  escaped.replace("<", "&lt;");
  escaped.replace(">", "&gt;");
  escaped.replace("\"", "&quot;");
  return escaped;
}

String jsonEscape(const String &value) {
  String escaped = value;
  escaped.replace("\\", "\\\\");
  escaped.replace("\"", "\\\"");
  escaped.replace("\r", "\\r");
  escaped.replace("\n", "\\n");
  return escaped;
}

framesize_t parseFrameSize(const String &value) {
  if (value == "UXGA") return FRAMESIZE_UXGA;
  if (value == "SXGA") return FRAMESIZE_SXGA;
  if (value == "XGA") return FRAMESIZE_XGA;
  if (value == "SVGA") return FRAMESIZE_SVGA;
  if (value == "VGA") return FRAMESIZE_VGA;
  if (value == "CIF") return FRAMESIZE_CIF;
  if (value == "QVGA") return FRAMESIZE_QVGA;
  return FRAMESIZE_SVGA;
}

String frameSizeName(framesize_t value) {
  switch (value) {
    case FRAMESIZE_UXGA: return "UXGA";
    case FRAMESIZE_SXGA: return "SXGA";
    case FRAMESIZE_XGA: return "XGA";
    case FRAMESIZE_SVGA: return "SVGA";
    case FRAMESIZE_VGA: return "VGA";
    case FRAMESIZE_CIF: return "CIF";
    case FRAMESIZE_QVGA: return "QVGA";
    default: return "SVGA";
  }
}

String localUrl() {
  IPAddress ip = stationConnected ? WiFi.localIP() : WiFi.softAPIP();
  return "http://" + ip.toString();
}

String jsonStatus() {
  String json = "{";
  json += "\"stationConnected\":" + String(stationConnected ? "true" : "false") + ",";
  json += "\"ssid\":\"" + jsonEscape(stationConnected ? WiFi.SSID() : apSsid) + "\",";
  json += "\"ip\":\"" + (stationConnected ? WiFi.localIP().toString() : WiFi.softAPIP().toString()) + "\",";
  json += "\"streamUrl\":\"" + localUrl() + "/stream\",";
  json += "\"frameSize\":\"" + frameSizeName(frameSize) + "\",";
  json += "\"jpegQuality\":" + String(jpegQuality) + ",";
  json += "\"xclkMhz\":" + String(xclkMhz) + ",";
  json += "\"psram\":" + String(psramFound() ? "true" : "false");
  json += "}";
  return json;
}

String getArg(const String &name, const String &fallback = "") {
  return server.hasArg(name) ? server.arg(name) : fallback;
}

void saveCameraSettings() {
  prefs.putString("framesize", frameSizeName(frameSize));
  prefs.putInt("quality", jpegQuality);
  prefs.putInt("xclk", xclkMhz);
}

void loadSettings() {
  prefs.begin(kPrefsNamespace, false);
  wifiSsid = prefs.getString("ssid", "");
  wifiPass = prefs.getString("pass", "");
  apSsid = prefs.getString("ap_ssid", kDefaultApSsid);
  apPass = prefs.getString("ap_pass", kDefaultApPass);
  frameSize = parseFrameSize(prefs.getString("framesize", "SVGA"));
  jpegQuality = prefs.getInt("quality", 10);
  xclkMhz = prefs.getInt("xclk", 20);
}

void connectWifi() {
  WiFi.mode(WIFI_AP_STA);
  WiFi.setSleep(false);
  WiFi.softAP(apSsid.c_str(), apPass.c_str());

  if (wifiSsid.length() > 0) {
    WiFi.begin(wifiSsid.c_str(), wifiPass.c_str());
    Serial.printf("Connecting to WiFi SSID %s", wifiSsid.c_str());
    const uint32_t started = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - started < 12000) {
      delay(300);
      Serial.print(".");
    }
    Serial.println();
  }

  stationConnected = WiFi.status() == WL_CONNECTED;
  Serial.printf("AP URL: http://%s\n", WiFi.softAPIP().toString().c_str());
  if (stationConnected) {
    Serial.printf("LAN URL: http://%s\n", WiFi.localIP().toString().c_str());
  }
}

bool startCamera() {
  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = xclkMhz * 1000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = psramFound() ? frameSize : FRAMESIZE_VGA;
  config.jpeg_quality = jpegQuality;
  config.fb_count = psramFound() ? 2 : 1;
  config.fb_location = psramFound() ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;
  config.grab_mode = CAMERA_GRAB_LATEST;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\n", err);
    return false;
  }

  sensor_t *sensor = esp_camera_sensor_get();
  if (sensor) {
    sensor->set_framesize(sensor, config.frame_size);
    sensor->set_quality(sensor, jpegQuality);
  }
  return true;
}

void restartCamera() {
  esp_camera_deinit();
  delay(100);
  startCamera();
}

void handleRoot() {
  String page = R"HTML(
<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>XIAO ESP32-S3 Sense Camera</title>
<style>
body{margin:0;font-family:Arial,sans-serif;background:#101418;color:#edf2f7}
header,main{max-width:1120px;margin:auto;padding:16px}
header{display:flex;gap:12px;align-items:center;justify-content:space-between}
.grid{display:grid;grid-template-columns:2fr 1fr;gap:14px}
section{background:#1a2129;border:1px solid #2d3744;border-radius:8px;padding:14px}
img{width:100%;height:auto;background:#050607;border-radius:6px}
label{display:block;margin:10px 0 4px;color:#b6c2cf}
input,select,button{font:inherit;border-radius:6px;border:1px solid #3a4654;background:#111820;color:#edf2f7;padding:9px}
button{cursor:pointer;background:#2563eb;border-color:#2563eb}
.row{display:flex;gap:8px;flex-wrap:wrap}.row>*{flex:1}
table{width:100%;border-collapse:collapse}td,th{border-bottom:1px solid #2d3744;padding:7px;text-align:left}
.muted{color:#9aa7b5;font-size:13px}
@media(max-width:820px){.grid{grid-template-columns:1fr}header{display:block}}
</style></head><body>
<header><div><h2>XIAO ESP32-S3 Sense Camera</h2><div id="status" class="muted"></div></div><button onclick="location.reload()">Refresh</button></header>
<main class="grid">
<section><img id="stream" src="/stream"><div class="row"><button onclick="snap()">Capture JPEG</button><button onclick="restart()">Restart Camera</button></div></section>
<section>
<h3>Camera</h3>
<label>Resolution</label><select id="framesize"><option>UXGA</option><option>SXGA</option><option>XGA</option><option>SVGA</option><option>VGA</option><option>CIF</option><option>QVGA</option></select>
<label>JPEG quality, lower is sharper</label><input id="quality" type="number" min="4" max="63">
<label>XCLK MHz</label><select id="xclk"><option>20</option><option>16</option><option>10</option></select>
<button onclick="saveCamera()">Apply Camera Settings</button>
<h3>Wi-Fi</h3>
<label>Router SSID</label><input id="ssid">
<label>Router password</label><input id="pass" type="password">
<button onclick="saveWifi()">Save Wi-Fi and Reboot</button>
</section>
<section>
<h3>GPIO Assignment</h3>
<div class="row"><select id="pin"></select><select id="mode"><option>input</option><option>input_pullup</option><option>output</option></select><select id="value"><option>0</option><option>1</option></select><button onclick="setPin()">Set</button></div>
<table><thead><tr><th>GPIO</th><th>Mode</th><th>Value</th></tr></thead><tbody id="pins"></tbody></table>
</section>
<section>
<h3>Links</h3>
<p><a style="color:#7db3ff" href="/capture">/capture</a></p>
<p><a style="color:#7db3ff" href="/status">/status</a></p>
<p class="muted">BLE service: b2b7f440-1c2a-45a8-a7c7-8fd6f7d90201. Write lines like ssid=Name, pass=Password, framesize=VGA, quality=10, reboot=1.</p>
</section>
</main>
<script>
async function refresh(){
 const s=await (await fetch('/status')).json();
 status.textContent=(s.stationConnected?'LAN ':'AP ')+s.ip+' | '+s.frameSize+' quality '+s.jpegQuality+' | stream '+s.streamUrl;
 framesize.value=s.frameSize; quality.value=s.jpegQuality; xclk.value=s.xclkMhz;
 const p=await (await fetch('/gpio')).json();
 pin.innerHTML=p.pins.map(x=>`<option>${x.pin}</option>`).join('');
 pins.innerHTML=p.pins.map(x=>`<tr><td>${x.pin}</td><td>${x.mode}</td><td>${x.value}</td></tr>`).join('');
}
async function saveCamera(){await fetch('/config',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({framesize:framesize.value,quality:quality.value,xclk:xclk.value})}); location.reload();}
async function saveWifi(){await fetch('/wifi',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({ssid:ssid.value,pass:pass.value})}); alert('Saved. Device is rebooting.');}
async function setPin(){await fetch('/gpio',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({pin:pin.value,mode:mode.value,value:value.value})}); refresh();}
async function restart(){await fetch('/restart-camera',{method:'POST'}); setTimeout(()=>location.reload(),1500);}
function snap(){window.open('/capture','_blank')}
refresh();
</script></body></html>
)HTML";
  server.send(200, "text/html", page);
}

void handleStatus() {
  server.send(200, "application/json", jsonStatus());
}

void handleCapture() {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    server.send(503, "text/plain", "Camera capture failed");
    return;
  }
  server.sendHeader("Content-Disposition", "inline; filename=capture.jpg");
  server.send_P(200, "image/jpeg", reinterpret_cast<const char *>(fb->buf), fb->len);
  esp_camera_fb_return(fb);
}

void handleStream() {
  WiFiClient client = server.client();
  client.print("HTTP/1.1 200 OK\r\n"
               "Content-Type: multipart/x-mixed-replace; boundary=frame\r\n"
               "Cache-Control: no-cache\r\n"
               "Connection: close\r\n\r\n");

  uint32_t frames = 0;
  int64_t started = esp_timer_get_time();
  while (client.connected()) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
      break;
    }
    client.printf("--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n", fb->len);
    client.write(fb->buf, fb->len);
    client.print("\r\n");
    esp_camera_fb_return(fb);
    frames++;
    if (frames % 120 == 0) {
      const float seconds = (esp_timer_get_time() - started) / 1000000.0f;
      Serial.printf("Stream %.1f FPS\n", frames / seconds);
    }
    delay(1);
  }
}

void handleConfig() {
  if (server.method() == HTTP_POST) {
    frameSize = parseFrameSize(getArg("framesize", frameSizeName(frameSize)));
    jpegQuality = constrain(getArg("quality", String(jpegQuality)).toInt(), 4, 63);
    xclkMhz = constrain(getArg("xclk", String(xclkMhz)).toInt(), 10, 20);
    saveCameraSettings();
    restartCamera();
  }
  server.send(200, "application/json", jsonStatus());
}

void handleWifi() {
  if (server.method() != HTTP_POST) {
    server.send(405, "text/plain", "POST required");
    return;
  }
  wifiSsid = getArg("ssid");
  wifiPass = getArg("pass");
  prefs.putString("ssid", wifiSsid);
  prefs.putString("pass", wifiPass);
  server.send(200, "text/plain", "saved; rebooting");
  delay(500);
  ESP.restart();
}

String gpioJson() {
  String json = "{\"pins\":[";
  for (size_t i = 0; i < sizeof(kUserPins) / sizeof(kUserPins[0]); ++i) {
    int pin = kUserPins[i];
    if (i) json += ",";
    String mode = prefs.getString(("p" + String(pin) + "m").c_str(), "input");
    json += "{\"pin\":" + String(pin) + ",\"mode\":\"" + mode + "\",\"value\":" + String(digitalRead(pin)) + "}";
  }
  json += "]}";
  return json;
}

void applyPinMode(int pin, const String &mode, int value) {
  if (isCameraPin(pin)) {
    return;
  }
  if (mode == "output") {
    pinMode(pin, OUTPUT);
    digitalWrite(pin, value ? HIGH : LOW);
  } else if (mode == "input_pullup") {
    pinMode(pin, INPUT_PULLUP);
  } else {
    pinMode(pin, INPUT);
  }
  prefs.putString(("p" + String(pin) + "m").c_str(), mode);
  prefs.putInt(("p" + String(pin) + "v").c_str(), value ? 1 : 0);
}

void restorePins() {
  for (int pin : kUserPins) {
    String mode = prefs.getString(("p" + String(pin) + "m").c_str(), "input");
    int value = prefs.getInt(("p" + String(pin) + "v").c_str(), 0);
    applyPinMode(pin, mode, value);
  }
}

void handleGpio() {
  if (server.method() == HTTP_POST) {
    int pin = getArg("pin").toInt();
    String mode = getArg("mode", "input");
    int value = getArg("value", "0").toInt();
    applyPinMode(pin, mode, value);
  }
  server.send(200, "application/json", gpioJson());
}

void routeWeb() {
  server.on("/", HTTP_GET, handleRoot);
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/capture", HTTP_GET, handleCapture);
  server.on("/stream", HTTP_GET, handleStream);
  server.on("/config", HTTP_POST, handleConfig);
  server.on("/wifi", HTTP_POST, handleWifi);
  server.on("/gpio", HTTP_GET, handleGpio);
  server.on("/gpio", HTTP_POST, handleGpio);
  server.on("/restart-camera", HTTP_POST, []() {
    restartCamera();
    server.send(200, "text/plain", "restarted");
  });
  server.begin();
}

void applyBleLine(String line) {
  line.trim();
  int equals = line.indexOf('=');
  if (equals < 1) {
    return;
  }
  String key = line.substring(0, equals);
  String value = line.substring(equals + 1);
  key.toLowerCase();
  if (key == "ssid") {
    prefs.putString("ssid", value);
  } else if (key == "pass") {
    prefs.putString("pass", value);
  } else if (key == "framesize") {
    frameSize = parseFrameSize(value);
    saveCameraSettings();
    restartCamera();
  } else if (key == "quality") {
    jpegQuality = constrain(value.toInt(), 4, 63);
    saveCameraSettings();
    restartCamera();
  } else if (key == "xclk") {
    xclkMhz = constrain(value.toInt(), 10, 20);
    saveCameraSettings();
    restartCamera();
  } else if (key == "reboot" && value == "1") {
    ESP.restart();
  }
  if (configCharacteristic) {
    configCharacteristic->setValue(jsonStatus().c_str());
    configCharacteristic->notify();
  }
}

class ConfigCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *characteristic) override {
    applyBleLine(String(characteristic->getValue().c_str()));
  }

  void onRead(BLECharacteristic *characteristic) override {
    characteristic->setValue(jsonStatus().c_str());
  }
};

void startBle() {
  BLEDevice::init("XIAO-S3-Camera");
  BLEServer *bleServer = BLEDevice::createServer();
  BLEService *service = bleServer->createService(kBleServiceUuid);
  configCharacteristic = service->createCharacteristic(
      kBleConfigUuid,
      BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_WRITE |
          BLECharacteristic::PROPERTY_NOTIFY);
  configCharacteristic->setCallbacks(new ConfigCallbacks());
  configCharacteristic->setValue(jsonStatus().c_str());
  service->start();
  BLEAdvertising *advertising = BLEDevice::getAdvertising();
  advertising->addServiceUUID(kBleServiceUuid);
  advertising->setScanResponse(true);
  BLEDevice::startAdvertising();
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("XIAO ESP32-S3 Sense Camera Server starting");
  loadSettings();
  restorePins();
  connectWifi();
  if (!startCamera()) {
    Serial.println("Camera unavailable; check Sense board seating and power.");
  }
  routeWeb();
  startBle();
  Serial.printf("Open %s\n", localUrl().c_str());
}

void loop() {
  server.handleClient();
  delay(1);
}
