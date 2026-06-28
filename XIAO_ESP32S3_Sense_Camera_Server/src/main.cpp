#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <FS.h>
#include <Preferences.h>
#include <SD.h>
#include <SPI.h>
#include <WebServer.h>
#include <WiFi.h>
#include "esp_camera.h"
#include "esp_timer.h"

namespace {

constexpr char kDefaultApSsid[] = "XIAO-S3-Camera";
constexpr char kDefaultApPass[] = "camera1234";
constexpr char kWifiHostname[] = "xiao-s3-camera";
constexpr uint8_t kApChannel = 6;
constexpr uint8_t kApMaxClients = 4;
constexpr bool kApHidden = false;
constexpr uint32_t kStationConnectTimeoutMs = 12000;
constexpr uint32_t kStationReconnectIntervalMs = 30000;
constexpr char kPrefsNamespace[] = "cam";
constexpr char kBleServiceUuid[] = "b2b7f440-1c2a-45a8-a7c7-8fd6f7d90201";
constexpr char kBleConfigUuid[] = "b2b7f441-1c2a-45a8-a7c7-8fd6f7d90201";
constexpr char kStorageDir[] = "/camera";
constexpr char kPhotoDir[] = "/camera/photos";
constexpr char kVideoDir[] = "/camera/videos";
constexpr char kAssetsDir[] = "/camera/assets";
constexpr char kModulesDir[] = "/camera/modules";
constexpr uint32_t kThermalSampleIntervalMs = 30000;
constexpr float kThermalWarmC = 55.0f;
constexpr float kThermalHotC = 70.0f;
constexpr float kThermalCriticalC = 80.0f;

// Seeed XIAO ESP32-S3 Sense camera connector pin map.
constexpr int PWDN_GPIO_NUM = -1;
constexpr int RESET_GPIO_NUM = -1;
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
constexpr int SD_CS_GPIO_NUM = 21;
constexpr int SD_SCK_GPIO_NUM = 7;
constexpr int SD_MISO_GPIO_NUM = 8;
constexpr int SD_MOSI_GPIO_NUM = 9;

const int kCameraPins[] = {
    PWDN_GPIO_NUM, RESET_GPIO_NUM, XCLK_GPIO_NUM, SIOD_GPIO_NUM, SIOC_GPIO_NUM,
    Y9_GPIO_NUM, Y8_GPIO_NUM, Y7_GPIO_NUM, Y6_GPIO_NUM, Y5_GPIO_NUM,
    Y4_GPIO_NUM, Y3_GPIO_NUM, Y2_GPIO_NUM, VSYNC_GPIO_NUM, HREF_GPIO_NUM,
    PCLK_GPIO_NUM};

const int kStoragePins[] = {SD_CS_GPIO_NUM, SD_SCK_GPIO_NUM, SD_MISO_GPIO_NUM, SD_MOSI_GPIO_NUM};
const int kUserPins[] = {2, 3, 4, 5, 6, 41, 42, 43, 44};

Preferences prefs;
WebServer server(80);
WebServer streamServer(81);
BLECharacteristic *configCharacteristic = nullptr;
BLEServer *bleServer = nullptr;
TaskHandle_t streamTaskHandle = nullptr;
SemaphoreHandle_t cameraMutex = nullptr;
File recordingFile;
File uploadFile;
String uploadPath;

String wifiSsid;
String wifiPass;
String apSsid;
String apPass;
framesize_t frameSize = FRAMESIZE_SVGA;
framesize_t streamFrameSize = FRAMESIZE_QVGA;
framesize_t activeFrameSize = FRAMESIZE_SVGA;
int jpegQuality = 10;
constexpr int xclkMhz = 20;
bool stationConnected = false;
bool bleStarted = false;
bool lowPowerMode = true;
bool streamEnabled = false;
bool streamPreviewEnabled = false;
bool sdReady = false;
bool recording = false;
bool thermalAutoStop = true;
bool thermalStoppedStream = false;
float chipTempC = -1000.0f;
uint32_t lastStationReconnectMs = 0;
uint32_t lastThermalSampleMs = 0;
uint32_t recordingFrameIntervalMs = 200;
uint32_t lastRecordingFrameMs = 0;
uint32_t recordingFrameCount = 0;
uint32_t recordingTargetFps = 5;
uint32_t recordingStartedMs = 0;
String recordingPath;
String moduleInventoryJson = "[]";
uint16_t moduleCount = 0;

struct PinState {
  int pin;
  String mode;
  int value;
};

void startBle();
void stopBle();
void stopRecording();

bool isCameraPin(int pin) {
  for (int cameraPin : kCameraPins) {
    if (cameraPin == pin) {
      return true;
    }
  }
  return false;
}

bool isStoragePin(int pin) {
  for (int storagePin : kStoragePins) {
    if (storagePin == pin) {
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

framesize_t limitFrameSizeForMemory(framesize_t value) {
  if (psramFound()) {
    return value;
  }
  switch (value) {
    case FRAMESIZE_UXGA:
    case FRAMESIZE_SXGA:
    case FRAMESIZE_XGA:
    case FRAMESIZE_SVGA:
      return FRAMESIZE_VGA;
    default:
      return value;
  }
}

framesize_t desiredStreamFrameSize() {
  return limitFrameSizeForMemory(streamPreviewEnabled ? streamFrameSize : frameSize);
}

framesize_t desiredIdleFrameSize() {
  return limitFrameSizeForMemory(frameSize);
}

bool isLowPowerFrameSize(framesize_t value) {
  return value == FRAMESIZE_QVGA;
}

uint32_t maxRecordFpsForFrameSize(framesize_t value) {
  switch (limitFrameSizeForMemory(value)) {
    case FRAMESIZE_QVGA: return 25;
    case FRAMESIZE_CIF: return 20;
    case FRAMESIZE_VGA: return 15;
    case FRAMESIZE_SVGA: return 10;
    case FRAMESIZE_XGA: return 6;
    case FRAMESIZE_SXGA: return 4;
    case FRAMESIZE_UXGA: return 2;
    default: return 10;
  }
}

bool setSensorFrameSize(framesize_t value, bool takeMutex = true) {
  value = limitFrameSizeForMemory(value);
  if (takeMutex && cameraMutex && xSemaphoreTake(cameraMutex, pdMS_TO_TICKS(2000)) != pdTRUE) {
    return false;
  }
  sensor_t *sensor = esp_camera_sensor_get();
  bool ok = sensor && sensor->set_framesize(sensor, value) == 0;
  if (ok) {
    sensor->set_quality(sensor, jpegQuality);
    activeFrameSize = value;
  }
  if (takeMutex && cameraMutex) {
    xSemaphoreGive(cameraMutex);
  }
  return ok;
}

String localUrl() {
  IPAddress ip = stationConnected ? WiFi.localIP() : WiFi.softAPIP();
  return "http://" + ip.toString();
}

String streamUrl() {
  IPAddress ip = stationConnected ? WiFi.localIP() : WiFi.softAPIP();
  return "http://" + ip.toString() + ":81/stream";
}

String wifiPowerName() {
  return lowPowerMode ? "eco" : "normal";
}

String wifiModeName() {
  wl_status_t status = WiFi.status();
  if (wifiSsid.length() > 0 && status == WL_CONNECTED) {
    return "ap_sta_connected";
  }
  if (wifiSsid.length() > 0) {
    return "ap_sta";
  }
  return "ap_only";
}

String storageJson() {
  String json = "\"sdReady\":" + String(sdReady ? "true" : "false") + ",";
  json += "\"recording\":" + String(recording ? "true" : "false") + ",";
  json += "\"recordingPath\":\"" + jsonEscape(recordingPath) + "\",";
  json += "\"recordingFrames\":" + String(recordingFrameCount) + ",";
  json += "\"recordingTargetFps\":" + String(recordingTargetFps) + ",";
  json += "\"recordingMaxFps\":" + String(maxRecordFpsForFrameSize(desiredIdleFrameSize())) + ",";
  float actualFps = 0.0f;
  if (recording && recordingStartedMs != 0) {
    const float seconds = (millis() - recordingStartedMs) / 1000.0f;
    if (seconds > 0.0f) {
      actualFps = recordingFrameCount / seconds;
    }
  }
  json += "\"recordingActualFps\":" + String(actualFps, 1);
  return json;
}

float readChipTempC() {
  const float reading = temperatureRead();
  return reading == reading ? reading : -1000.0f;
}

String thermalStateName() {
  if (chipTempC < -200.0f) return "unknown";
  if (chipTempC >= kThermalCriticalC) return "critical";
  if (chipTempC >= kThermalHotC) return "hot";
  if (chipTempC >= kThermalWarmC) return "warm";
  return "normal";
}

void sampleThermals(bool force = false) {
  const uint32_t now = millis();
  if (!force && lastThermalSampleMs != 0 && now - lastThermalSampleMs < kThermalSampleIntervalMs) {
    return;
  }
  chipTempC = readChipTempC();
  lastThermalSampleMs = now;
  if (thermalAutoStop && chipTempC >= kThermalCriticalC) {
    if (streamEnabled || recording) {
      Serial.printf("Thermal critical %.1f C: stopping stream/recording\n", chipTempC);
    }
    streamEnabled = false;
    if (recording) {
      stopRecording();
    }
    thermalStoppedStream = true;
  }
}

String extractJsonString(const String &json, const String &key, const String &fallback = "") {
  String needle = "\"" + key + "\"";
  int keyIndex = json.indexOf(needle);
  if (keyIndex < 0) return fallback;
  int colon = json.indexOf(':', keyIndex + needle.length());
  if (colon < 0) return fallback;
  int firstQuote = json.indexOf('"', colon + 1);
  if (firstQuote < 0) return fallback;
  int secondQuote = json.indexOf('"', firstQuote + 1);
  if (secondQuote < 0) return fallback;
  return json.substring(firstQuote + 1, secondQuote);
}

String jsonStatus() {
  String json = "{";
  json += "\"stationConnected\":" + String(stationConnected ? "true" : "false") + ",";
  json += "\"ssid\":\"" + jsonEscape(stationConnected ? WiFi.SSID() : apSsid) + "\",";
  json += "\"ip\":\"" + (stationConnected ? WiFi.localIP().toString() : WiFi.softAPIP().toString()) + "\",";
  json += "\"streamUrl\":\"" + streamUrl() + "\",";
  json += "\"apIp\":\"" + WiFi.softAPIP().toString() + "\",";
  json += "\"apClients\":" + String(WiFi.softAPgetStationNum()) + ",";
  json += "\"wifiMode\":\"" + wifiModeName() + "\",";
  json += "\"wifiPower\":\"" + wifiPowerName() + "\",";
  json += "\"wifiSleep\":" + String((lowPowerMode || bleStarted) ? "true" : "false") + ",";
  json += "\"stationRssi\":" + String(stationConnected ? WiFi.RSSI() : 0) + ",";
  json += "\"frameSize\":\"" + frameSizeName(frameSize) + "\",";
  json += "\"streamFrameSize\":\"" + frameSizeName(streamFrameSize) + "\",";
  json += "\"activeFrameSize\":\"" + frameSizeName(activeFrameSize) + "\",";
  json += "\"streamPreviewEnabled\":" + String(streamPreviewEnabled ? "true" : "false") + ",";
  json += "\"jpegQuality\":" + String(jpegQuality) + ",";
  json += "\"xclkMhz\":" + String(xclkMhz) + ",";
  json += "\"psram\":" + String(psramFound() ? "true" : "false") + ",";
  json += "\"bleStarted\":" + String(bleStarted ? "true" : "false") + ",";
  json += "\"lowPowerMode\":" + String(lowPowerMode ? "true" : "false") + ",";
  json += "\"streamEnabled\":" + String(streamEnabled ? "true" : "false") + ",";
  json += "\"chipTempValid\":" + String(chipTempC > -200.0f ? "true" : "false") + ",";
  json += "\"chipTempC\":" + String(chipTempC < -200.0f ? 0.0f : chipTempC, 1) + ",";
  json += "\"thermalState\":\"" + thermalStateName() + "\",";
  json += "\"thermalAutoStop\":" + String(thermalAutoStop ? "true" : "false") + ",";
  json += "\"thermalStoppedStream\":" + String(thermalStoppedStream ? "true" : "false") + ",";
  json += "\"thermalSampleIntervalMs\":" + String(kThermalSampleIntervalMs) + ",";
  json += "\"thermalSampleAgeMs\":" + String(lastThermalSampleMs == 0 ? 0 : millis() - lastThermalSampleMs) + ",";
  json += "\"thermalWarmC\":" + String(kThermalWarmC, 0) + ",";
  json += "\"thermalHotC\":" + String(kThermalHotC, 0) + ",";
  json += "\"thermalCriticalC\":" + String(kThermalCriticalC, 0) + ",";
  json += "\"moduleCount\":" + String(moduleCount) + ",";
  json += storageJson();
  json += "}";
  return json;
}

String getArg(const String &name, const String &fallback = "") {
  return server.hasArg(name) ? server.arg(name) : fallback;
}

String basenameOf(const String &path) {
  int slash = path.lastIndexOf('/');
  return slash >= 0 ? path.substring(slash + 1) : path;
}

String parentOf(const String &path) {
  if (path == "/" || path.length() == 0) {
    return "/";
  }
  int slash = path.lastIndexOf('/');
  if (slash <= 0) {
    return "/";
  }
  return path.substring(0, slash);
}

String cleanStoragePath(String path) {
  path.trim();
  path.replace("\\", "/");
  if (path.length() == 0) {
    path = "/";
  }
  if (!path.startsWith("/")) {
    path = "/" + path;
  }
  while (path.indexOf("//") >= 0) {
    path.replace("//", "/");
  }
  if (path.endsWith("/") && path.length() > 1) {
    path.remove(path.length() - 1);
  }
  return path;
}

bool isAllowedStoragePath(String path) {
  path = cleanStoragePath(path);
  return path.startsWith("/") && path.indexOf("..") < 0;
}

String contentTypeFor(const String &path) {
  if (path.endsWith(".html") || path.endsWith(".htm")) return "text/html";
  if (path.endsWith(".css")) return "text/css";
  if (path.endsWith(".js")) return "application/javascript";
  if (path.endsWith(".json")) return "application/json";
  if (path.endsWith(".txt") || path.endsWith(".log") || path.endsWith(".csv")) return "text/plain";
  if (path.endsWith(".jpg") || path.endsWith(".jpeg")) return "image/jpeg";
  if (path.endsWith(".png")) return "image/png";
  if (path.endsWith(".gif")) return "image/gif";
  if (path.endsWith(".mjpeg")) return "multipart/x-mixed-replace; boundary=frame";
  if (path.endsWith(".bin")) return "application/octet-stream";
  return "application/octet-stream";
}

void saveCameraSettings() {
  prefs.putString("framesize", frameSizeName(frameSize));
  prefs.putString("stream_size", frameSizeName(streamFrameSize));
  prefs.putBool("stream_prev", streamPreviewEnabled);
  prefs.putInt("quality", jpegQuality);
  prefs.putBool("low_power", lowPowerMode);
  prefs.putBool("thermal_stop", thermalAutoStop);
}

void loadSettings() {
  prefs.begin(kPrefsNamespace, false);
  wifiSsid = prefs.isKey("ssid") ? prefs.getString("ssid", "") : "";
  wifiPass = prefs.isKey("pass") ? prefs.getString("pass", "") : "";
  apSsid = prefs.isKey("ap_ssid") ? prefs.getString("ap_ssid", kDefaultApSsid) : kDefaultApSsid;
  apPass = prefs.isKey("ap_pass") ? prefs.getString("ap_pass", kDefaultApPass) : kDefaultApPass;
  frameSize = parseFrameSize(prefs.isKey("framesize") ? prefs.getString("framesize", "SVGA") : "SVGA");
  streamFrameSize = parseFrameSize(prefs.isKey("stream_size") ? prefs.getString("stream_size", "QVGA") : "QVGA");
  streamPreviewEnabled = prefs.getBool("stream_prev", false);
  jpegQuality = prefs.getInt("quality", 10);
  thermalAutoStop = prefs.getBool("thermal_stop", true);
  lowPowerMode = true;
  frameSize = FRAMESIZE_QVGA;
  activeFrameSize = frameSize;
  jpegQuality = max(jpegQuality, 18);
}

void applyWifiPower() {
  WiFi.setTxPower(lowPowerMode ? WIFI_POWER_2dBm : WIFI_POWER_8_5dBm);
  WiFi.setSleep(lowPowerMode || bleStarted);
}

void applyLowPowerCameraPreset() {
  lowPowerMode = true;
  frameSize = FRAMESIZE_QVGA;
  streamFrameSize = FRAMESIZE_QVGA;
  jpegQuality = 18;
  saveCameraSettings();
}

void connectWifi() {
  const bool useStation = wifiSsid.length() > 0;
  WiFi.persistent(false);
  WiFi.setAutoReconnect(true);
  WiFi.setHostname(kWifiHostname);
  WiFi.mode(useStation ? WIFI_AP_STA : WIFI_AP);
  applyWifiPower();

  IPAddress apIp(169, 254, 4, 1);
  IPAddress apGateway(169, 254, 4, 1);
  IPAddress apSubnet(255, 255, 0, 0);
  if (!WiFi.softAPConfig(apIp, apGateway, apSubnet)) {
    Serial.println("AP network config failed");
  }
  if (!WiFi.softAP(apSsid.c_str(), apPass.c_str(), kApChannel, kApHidden, kApMaxClients)) {
    Serial.println("AP start failed");
  }

  if (useStation) {
    WiFi.begin(wifiSsid.c_str(), wifiPass.c_str());
    Serial.printf("Connecting to WiFi SSID %s", wifiSsid.c_str());
    const uint32_t started = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - started < kStationConnectTimeoutMs) {
      delay(300);
      Serial.print(".");
    }
    Serial.println();
    lastStationReconnectMs = millis();
  }

  stationConnected = WiFi.status() == WL_CONNECTED;
  Serial.printf("AP URL: http://%s channel=%u clients=%u power=%s sleep=%s\n",
                WiFi.softAPIP().toString().c_str(),
                kApChannel,
                kApMaxClients,
                wifiPowerName().c_str(),
                (lowPowerMode || bleStarted) ? "on" : "off");
  if (stationConnected) {
    Serial.printf("LAN URL: http://%s RSSI=%d dBm\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());
  }
}

void serviceWifi() {
  bool connectedNow = WiFi.status() == WL_CONNECTED;
  if (connectedNow != stationConnected) {
    stationConnected = connectedNow;
    Serial.printf("WiFi STA %s\n", stationConnected ? "connected" : "disconnected");
    if (stationConnected) {
      Serial.printf("LAN URL: http://%s RSSI=%d dBm\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());
    }
  }

  if (wifiSsid.length() == 0 || stationConnected) {
    return;
  }
  uint32_t now = millis();
  if (now - lastStationReconnectMs < kStationReconnectIntervalMs) {
    return;
  }
  lastStationReconnectMs = now;
  Serial.println("Retrying saved WiFi station connection...");
  WiFi.disconnect(false);
  WiFi.begin(wifiSsid.c_str(), wifiPass.c_str());
}

void ensureStorageDirs() {
  if (!SD.exists(kStorageDir)) SD.mkdir(kStorageDir);
  if (!SD.exists(kPhotoDir)) SD.mkdir(kPhotoDir);
  if (!SD.exists(kVideoDir)) SD.mkdir(kVideoDir);
  if (!SD.exists(kAssetsDir)) SD.mkdir(kAssetsDir);
  if (!SD.exists(kModulesDir)) SD.mkdir(kModulesDir);
}

void scanModules() {
  moduleInventoryJson = "[]";
  moduleCount = 0;
  if (!sdReady || !SD.exists(kModulesDir)) {
    Serial.println("Module scan skipped: SD modules directory unavailable.");
    return;
  }

  File root = SD.open(kModulesDir);
  if (!root || !root.isDirectory()) {
    Serial.println("Module scan skipped: /camera/modules is not a directory.");
    return;
  }

  String json = "[";
  bool first = true;
  File entry = root.openNextFile();
  while (entry) {
    if (entry.isDirectory()) {
      String folderName = entry.name();
      String folderPath = folderName.startsWith("/") ? folderName : String(kModulesDir) + "/" + folderName;
      String manifestPath = folderPath + "/module.json";
      if (SD.exists(manifestPath)) {
        File manifest = SD.open(manifestPath, FILE_READ);
        String manifestText;
        while (manifest && manifest.available() && manifestText.length() < 2048) {
          manifestText += static_cast<char>(manifest.read());
        }
        if (manifest) manifest.close();
        String name = extractJsonString(manifestText, "name", basenameOf(folderPath));
        String version = extractJsonString(manifestText, "version", "");
        String type = extractJsonString(manifestText, "type", "config");
        if (!first) json += ",";
        first = false;
        json += "{\"name\":\"" + jsonEscape(name) + "\",\"version\":\"" + jsonEscape(version) + "\",";
        json += "\"type\":\"" + jsonEscape(type) + "\",\"path\":\"" + jsonEscape(folderPath) + "\",";
        json += "\"manifest\":\"" + jsonEscape(manifestPath) + "\"}";
        moduleCount++;
      }
    }
    entry = root.openNextFile();
  }
  root.close();
  json += "]";
  moduleInventoryJson = json;
  Serial.printf("Module scan: %u module manifest(s) found in %s\n", moduleCount, kModulesDir);
}

bool startStorage() {
  SPI.begin(SD_SCK_GPIO_NUM, SD_MISO_GPIO_NUM, SD_MOSI_GPIO_NUM, SD_CS_GPIO_NUM);
  sdReady = SD.begin(SD_CS_GPIO_NUM);
  if (!sdReady) {
    Serial.println("SD mount failed. Use FAT32, 32GB or smaller, and check the Sense SD jumper.");
    return false;
  }
  ensureStorageDirs();
  scanModules();
  uint64_t cardSizeMb = SD.cardSize() / (1024 * 1024);
  Serial.printf("SD mounted: %llu MB\n", cardSizeMb);
  return true;
}

String makeCaptureName(const char *dir, const char *extension) {
  char path[80];
  snprintf(path, sizeof(path), "%s/%lu_%lu.%s", dir, millis() / 1000UL, micros() % 1000000UL, extension);
  return String(path);
}

bool writeFrameToFile(File &file, camera_fb_t *fb) {
  if (!fb || !file) {
    return false;
  }
  file.print("--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ");
  file.print(fb->len);
  file.print("\r\n\r\n");
  size_t written = file.write(fb->buf, fb->len);
  file.print("\r\n");
  return written == fb->len;
}

bool savePhoto(String &path) {
  if (!sdReady) {
    return false;
  }
  if (cameraMutex && xSemaphoreTake(cameraMutex, pdMS_TO_TICKS(2000)) != pdTRUE) {
    return false;
  }
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    if (cameraMutex) xSemaphoreGive(cameraMutex);
    return false;
  }
  path = makeCaptureName(kPhotoDir, "jpg");
  File file = SD.open(path, FILE_WRITE);
  bool ok = file && file.write(fb->buf, fb->len) == fb->len;
  if (file) file.close();
  esp_camera_fb_return(fb);
  if (cameraMutex) xSemaphoreGive(cameraMutex);
  return ok;
}

bool startRecording(uint32_t fps) {
  if (!sdReady || recording) {
    return false;
  }
  streamEnabled = false;
  setSensorFrameSize(desiredIdleFrameSize());
  fps = constrain(fps, 1UL, maxRecordFpsForFrameSize(desiredIdleFrameSize()));
  recordingTargetFps = fps;
  recordingFrameIntervalMs = 1000UL / fps;
  recordingPath = makeCaptureName(kVideoDir, "mjpeg");
  recordingFile = SD.open(recordingPath, FILE_WRITE);
  if (!recordingFile) {
    recordingPath = "";
    return false;
  }
  recording = true;
  recordingFrameCount = 0;
  lastRecordingFrameMs = 0;
  recordingStartedMs = millis();
  return true;
}

void stopRecording() {
  if (!recording) {
    return;
  }
  recordingFile.print("--frame--\r\n");
  recordingFile.close();
  recording = false;
  recordingStartedMs = 0;
}

void serviceRecording() {
  if (!recording || !recordingFile) {
    return;
  }
  uint32_t now = millis();
  if (lastRecordingFrameMs != 0 && now - lastRecordingFrameMs < recordingFrameIntervalMs) {
    return;
  }
  if (cameraMutex && xSemaphoreTake(cameraMutex, 0) != pdTRUE) {
    return;
  }
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    if (cameraMutex) xSemaphoreGive(cameraMutex);
    return;
  }
  if (writeFrameToFile(recordingFile, fb)) {
    recordingFrameCount++;
    lastRecordingFrameMs = now;
  }
  esp_camera_fb_return(fb);
  if (cameraMutex) xSemaphoreGive(cameraMutex);
  if (recordingFrameCount % 30 == 0) {
    recordingFile.flush();
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
  activeFrameSize = streamEnabled ? desiredStreamFrameSize() : desiredIdleFrameSize();
  config.frame_size = activeFrameSize;
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
    sensor->set_framesize(sensor, activeFrameSize);
    sensor->set_quality(sensor, jpegQuality);
  }
  return true;
}

void restartCamera() {
  if (recording) {
    stopRecording();
  }
  streamEnabled = false;
  if (cameraMutex) xSemaphoreTake(cameraMutex, pdMS_TO_TICKS(2000));
  esp_camera_deinit();
  delay(100);
  startCamera();
  if (cameraMutex) xSemaphoreGive(cameraMutex);
}

void handleRoot() {
  String page = R"HTML(
<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>XIAO ESP32-S3 Sense Camera</title>
<style>
:root{--ink:#fff8ff;--muted:#ffd5f2;--panel:rgba(42,18,64,.78);--line:rgba(255,255,255,.22);--hot:#ff4fb8;--sun:#ffd166;--aqua:#4ee7ff;--sea:#10395d}
*{box-sizing:border-box}
body{margin:0;font-family:Arial,sans-serif;color:var(--ink);background-image:linear-gradient(rgba(42,16,68,.62),rgba(24,10,48,.76)),url('/assets/theme.png'),radial-gradient(circle at 12% 6%,rgba(255,209,102,.42),transparent 25%),radial-gradient(circle at 86% 8%,rgba(78,231,255,.38),transparent 24%),linear-gradient(155deg,#2a1044 0%,#822067 44%,#f06491 68%,#18a8b8 100%);background-size:cover,cover,auto,auto,auto;background-position:center;background-attachment:fixed}
body:before{content:"";position:fixed;inset:0;pointer-events:none;background:linear-gradient(rgba(255,255,255,.05) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.05) 1px,transparent 1px);background-size:36px 36px;mask-image:linear-gradient(to bottom,rgba(0,0,0,.35),transparent 75%)}
header,main{max-width:1120px;margin:auto;padding:16px;position:relative}
header{display:flex;gap:12px;align-items:center;justify-content:space-between}
h2,h3{margin-top:0;text-shadow:0 2px 14px rgba(255,79,184,.45)}
.grid{display:grid;grid-template-columns:2fr 1fr;gap:14px}
section{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px;box-shadow:0 12px 36px rgba(40,8,58,.28),inset 0 1px 0 rgba(255,255,255,.13);backdrop-filter:blur(8px)}
img{width:100%;height:auto;background:#160720;border:2px solid rgba(78,231,255,.55);border-radius:8px;box-shadow:0 0 28px rgba(78,231,255,.24)}
label{display:block;margin:10px 0 4px;color:var(--muted);font-weight:bold}
input,select,button{font:inherit;border-radius:8px;border:1px solid rgba(255,255,255,.28);background:rgba(13,15,44,.78);color:var(--ink);padding:9px;min-width:0}
button{cursor:pointer;background:linear-gradient(135deg,var(--hot),#8b5cf6 55%,var(--aqua));border-color:rgba(255,255,255,.38);font-weight:bold;box-shadow:0 6px 18px rgba(255,79,184,.22)}
button:hover{filter:brightness(1.12)}
.row{display:flex;gap:8px;flex-wrap:wrap}.row>*{flex:1}
table{width:100%;border-collapse:collapse;background:rgba(16,57,93,.2);border-radius:8px;overflow:hidden}td,th{border-bottom:1px solid rgba(255,255,255,.18);padding:7px;text-align:left}
th{color:var(--sun)}.muted{color:var(--muted);font-size:13px}
a{color:var(--aqua);font-weight:bold}
@media(max-width:820px){.grid{grid-template-columns:1fr}header{display:block}}
</style></head><body>
<header><div><h2>XIAO ESP32-S3 Sense Camera</h2><div id="status" class="muted"></div></div><button onclick="location.reload()">Refresh</button></header>
<main class="grid">
<section><img id="stream" src="" alt="Camera stream disabled"><div class="row"><button onclick="startStream()">Start Stream</button><button onclick="stopStream()">Stop Stream</button><button onclick="snap()">Capture JPEG</button><button onclick="savePhoto()">Save Photo to SD</button><button onclick="restart()">Restart Camera</button></div></section>
<section>
<h3>Camera</h3>
<label>Capture / record resolution</label><select id="framesize"><option>UXGA</option><option>SXGA</option><option>XGA</option><option>SVGA</option><option>VGA</option><option>CIF</option><option>QVGA</option></select>
<label>Stream preview mode</label><select id="previewMode"><option value="off">Use capture resolution</option><option value="on">Use lower preview resolution</option></select>
<label>Stream preview resolution</label><select id="streamFramesize"><option>VGA</option><option>CIF</option><option>QVGA</option></select>
<label>JPEG quality, lower is sharper</label><input id="quality" type="number" min="4" max="63">
<label>Power mode</label><select id="powerMode"><option value="normal">Normal</option><option value="low">Low power</option></select>
<div id="cameraNote" class="muted"></div>
<button onclick="saveCamera()">Apply Camera Settings</button>
<h3>Thermals</h3>
<div id="thermal" class="muted"></div>
<label>Critical temperature behavior</label><select id="thermalStop"><option value="on">Auto-stop stream/recording</option><option value="off">Warn only</option></select>
<button onclick="saveThermal()">Apply Thermal Settings</button>
<h3>Wi-Fi</h3>
<label>Router SSID</label><input id="ssid">
<label>Router password</label><input id="pass" type="password">
<button onclick="saveWifi()">Save Wi-Fi and Reboot</button>
<h3>Bluetooth LE</h3>
<div id="ble" class="muted"></div>
<div class="row"><button onclick="startBle()">Start BLE</button><button onclick="stopBle()">Stop BLE</button></div>
</section>
<section>
<h3>SD Storage</h3>
<div id="storage" class="muted"></div>
<label>Target record FPS</label><input id="recordFps" type="number" min="1" max="25" value="5">
<div id="fpsNote" class="muted"></div>
<div class="row"><button onclick="startRecord()">Start Recording</button><button onclick="stopRecord()">Stop Recording</button><button onclick="refreshFiles()">Refresh Files</button></div>
<table><thead><tr><th>File</th><th>Size</th><th>Actions</th></tr></thead><tbody id="files"></tbody></table>
</section>
<section>
<h3>GPIO Assignment</h3>
<div class="row"><select id="pin"></select><select id="mode"><option>input</option><option>input_pullup</option><option>output</option></select><select id="value"><option>0</option><option>1</option></select><button onclick="setPin()">Set</button></div>
<table><thead><tr><th>GPIO</th><th>Mode</th><th>Value</th></tr></thead><tbody id="pins"></tbody></table>
</section>
<section>
<h3>Links</h3>
<p><a href="/capture">/capture</a></p>
<p><a href="/explorer">/explorer</a></p>
<p><a href="/files">/files</a></p>
<p><a href="/status">/status</a></p>
<p class="muted">BLE service: b2b7f440-1c2a-45a8-a7c7-8fd6f7d90201. Write lines like ssid=Name, pass=Password, framesize=VGA, quality=10, reboot=1.</p>
</section>
</main>
<script>
async function refresh(){
 const s=await (await fetch('/status')).json();
  status.textContent=(s.stationConnected?'LAN ':'AP ')+s.ip+' | Wi-Fi '+s.wifiPower+(s.wifiSleep?' sleep':' active')+' | clients '+s.apClients+' | capture '+s.frameSize+' | active '+s.activeFrameSize+' | quality '+s.jpegQuality;
 if(s.streamEnabled && stream.src!==s.streamUrl){stream.src=s.streamUrl;}
 if(!s.streamEnabled && stream.src){stream.removeAttribute('src');}
 storage.textContent=(s.sdReady?'SD mounted':'SD not mounted')+' | max '+s.recordingMaxFps+' FPS at '+s.frameSize+(s.recording?' | recording '+s.recordingFrames+' frames @ '+s.recordingActualFps.toFixed(1)+' FPS to '+s.recordingPath:'');
 ble.textContent=s.bleStarted?'BLE advertising; Wi-Fi modem sleep is enabled':'BLE off; Wi-Fi max-performance mode';
 thermal.textContent=(s.chipTempValid?'Chip '+s.chipTempC.toFixed(1)+' C':'Chip temp unavailable')+' | '+s.thermalState+' | sample age '+Math.round(s.thermalSampleAgeMs/1000)+' s | interval '+Math.round(s.thermalSampleIntervalMs/1000)+' s'+(s.thermalStoppedStream?' | auto-stop triggered':'');
 framesize.value=s.frameSize; quality.value=s.jpegQuality; powerMode.value=s.lowPowerMode?'low':'normal';
 streamFramesize.value=s.streamFrameSize; previewMode.value=s.streamPreviewEnabled?'on':'off';
 thermalStop.value=s.thermalAutoStop?'on':'off';
 recordFps.max=s.recordingMaxFps; if(Number(recordFps.value)>s.recordingMaxFps){recordFps.value=s.recordingMaxFps;}
 updateFpsNote();
 const p=await (await fetch('/gpio')).json();
 pin.innerHTML=p.pins.map(x=>`<option>${x.pin}</option>`).join('');
 pins.innerHTML=p.pins.map(x=>`<tr><td>${x.pin}</td><td>${x.mode}</td><td>${x.value}</td></tr>`).join('');
 await refreshFiles();
 updateCameraNote();
}
function updateCameraNote(){
 if(framesize.value!=='QVGA' && powerMode.value==='low'){powerMode.value='normal';}
 cameraNote.textContent=powerMode.value==='low'?'Low power forces QVGA. Choose Normal for VGA or higher.':'Normal mode allows VGA and higher resolutions; stream can still use a lower preview.';
 updateFpsNote();
}
function maxFpsFor(size){return {QVGA:25,CIF:20,VGA:15,SVGA:10,XGA:6,SXGA:4,UXGA:2}[size]||10;}
function updateFpsNote(){
 const max=maxFpsFor(framesize.value); recordFps.max=max; if(Number(recordFps.value)>max){recordFps.value=max;}
 fpsNote.textContent='Max target for '+framesize.value+' is '+max+' FPS. Actual saved FPS may be lower if SD writes or capture time cannot keep up.';
}
framesize.onchange=updateCameraNote; powerMode.onchange=updateCameraNote; recordFps.onchange=updateFpsNote;
async function saveCamera(){updateCameraNote();await fetch('/config',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({framesize:framesize.value,streamFramesize:streamFramesize.value,preview:previewMode.value,quality:quality.value,power:powerMode.value})}); location.reload();}
async function saveThermal(){await fetch('/thermal',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({autoStop:thermalStop.value})}); refresh();}
async function saveWifi(){await fetch('/wifi',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({ssid:ssid.value,pass:pass.value})}); alert('Saved. Device is rebooting.');}
async function startBle(){await fetch('/ble/start',{method:'POST'}); refresh();}
async function stopBle(){await fetch('/ble/stop',{method:'POST'}); refresh();}
async function startStream(){const s=await (await fetch('/stream/start',{method:'POST'})).json(); stream.src=s.streamUrl; refresh();}
async function stopStream(){await fetch('/stream/stop',{method:'POST'}); stream.removeAttribute('src'); refresh();}
async function setPin(){await fetch('/gpio',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({pin:pin.value,mode:mode.value,value:value.value})}); refresh();}
async function restart(){await fetch('/restart-camera',{method:'POST'}); setTimeout(()=>location.reload(),1500);}
async function savePhoto(){const r=await fetch('/photo/save',{method:'POST'}); alert(await r.text()); await refreshFiles();}
async function startRecord(){await fetch('/record/start',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({fps:recordFps.value})}); refresh();}
async function stopRecord(){await fetch('/record/stop',{method:'POST'}); refresh();}
async function deleteFile(path){await fetch('/file/delete',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({path})}); refreshFiles();}
async function refreshFiles(){
 const r=await fetch('/files'); const j=await r.json();
 files.innerHTML=j.files.map(f=>`<tr><td>${f.path}</td><td>${f.size}</td><td><a href="/file/download?path=${encodeURIComponent(f.path)}">download</a> <a href="/play?path=${encodeURIComponent(f.path)}" target="_blank">play</a> <button onclick="deleteFile('${f.path}')">Delete</button></td></tr>`).join('');
}
function snap(){window.open('/capture','_blank')}
refresh();
setInterval(refresh, 30000);
</script></body></html>
)HTML";
  server.send(200, "text/html", page);
}

void handleStatus() {
  sampleThermals();
  server.send(200, "application/json", jsonStatus());
}

void handleWifiStatus() {
  server.send(200, "application/json", jsonStatus());
}

void handleWifiScan() {
  int count = WiFi.scanNetworks(false, true);
  String json = "{\"count\":" + String(count < 0 ? 0 : count) + ",\"networks\":[";
  for (int i = 0; i < count; ++i) {
    if (i) json += ",";
    json += "{\"ssid\":\"" + jsonEscape(WiFi.SSID(i)) + "\",";
    json += "\"rssi\":" + String(WiFi.RSSI(i)) + ",";
    json += "\"channel\":" + String(WiFi.channel(i)) + ",";
    json += "\"encrypted\":" + String(WiFi.encryptionType(i) == WIFI_AUTH_OPEN ? "false" : "true") + "}";
  }
  json += "]}";
  WiFi.scanDelete();
  server.send(200, "application/json", json);
}

void handleModules() {
  server.send(200, "application/json",
              "{\"sdReady\":" + String(sdReady ? "true" : "false") +
                  ",\"dir\":\"" + String(kModulesDir) + "\",\"count\":" +
                  String(moduleCount) + ",\"modules\":" + moduleInventoryJson + "}");
}

void handleCapture() {
  if (cameraMutex && xSemaphoreTake(cameraMutex, pdMS_TO_TICKS(2000)) != pdTRUE) {
    server.send(503, "text/plain", "Camera busy");
    return;
  }
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    if (cameraMutex) xSemaphoreGive(cameraMutex);
    server.send(503, "text/plain", "Camera capture failed");
    return;
  }
  server.sendHeader("Content-Disposition", "inline; filename=capture.jpg");
  server.send_P(200, "image/jpeg", reinterpret_cast<const char *>(fb->buf), fb->len);
  esp_camera_fb_return(fb);
  if (cameraMutex) xSemaphoreGive(cameraMutex);
}

void handleSavePhoto() {
  String path;
  if (!savePhoto(path)) {
    server.send(503, "text/plain", "SD photo save failed");
    return;
  }
  server.send(200, "text/plain", "Saved " + path);
}

void handleExplorer() {
  String page = R"HTML(
<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SD Explorer</title>
<style>
:root{--ink:#fff8ff;--muted:#ffd5f2;--panel:rgba(42,18,64,.78);--line:rgba(255,255,255,.22);--hot:#ff4fb8;--sun:#ffd166;--aqua:#4ee7ff}
*{box-sizing:border-box}
body{margin:0;font-family:Arial,sans-serif;color:var(--ink);background-image:linear-gradient(rgba(42,16,68,.62),rgba(24,10,48,.76)),url('/assets/theme.png'),radial-gradient(circle at 14% 8%,rgba(255,209,102,.42),transparent 25%),radial-gradient(circle at 86% 8%,rgba(78,231,255,.36),transparent 24%),linear-gradient(155deg,#2a1044 0%,#822067 44%,#f06491 68%,#18a8b8 100%);background-size:cover,cover,auto,auto,auto;background-position:center;background-attachment:fixed}
body:before{content:"";position:fixed;inset:0;pointer-events:none;background:linear-gradient(rgba(255,255,255,.05) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.05) 1px,transparent 1px);background-size:36px 36px;mask-image:linear-gradient(to bottom,rgba(0,0,0,.35),transparent 75%)}
header,main{max-width:1100px;margin:auto;padding:16px;position:relative}
header{display:flex;gap:12px;align-items:center;justify-content:space-between}
h2{margin-top:0;text-shadow:0 2px 14px rgba(255,79,184,.45)}
section{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px;margin-bottom:14px;box-shadow:0 12px 36px rgba(40,8,58,.28),inset 0 1px 0 rgba(255,255,255,.13);backdrop-filter:blur(8px)}
input,button{font:inherit;border-radius:8px;border:1px solid rgba(255,255,255,.28);background:rgba(13,15,44,.78);color:var(--ink);padding:9px;min-width:0}
button{cursor:pointer;background:linear-gradient(135deg,var(--hot),#8b5cf6 55%,var(--aqua));border-color:rgba(255,255,255,.38);font-weight:bold;box-shadow:0 6px 18px rgba(255,79,184,.22)}
button:hover{filter:brightness(1.12)}
table{width:100%;border-collapse:collapse;background:rgba(16,57,93,.2);border-radius:8px;overflow:hidden}td,th{border-bottom:1px solid rgba(255,255,255,.18);padding:8px;text-align:left}
th{color:var(--sun)}a{color:var(--aqua);font-weight:bold}.muted{color:var(--muted);font-size:13px}.row{display:flex;gap:8px;flex-wrap:wrap}.row>*{flex:1}
</style></head><body>
<header><div><h2>SD Explorer</h2><div id="status" class="muted"></div></div><a href="/">Camera</a></header>
<main>
<section>
<div class="row"><input id="path" value="/camera"><button onclick="go()">Open</button><button onclick="up()">Up</button><button onclick="loadDir()">Refresh</button></div>
<div class="row"><input id="folder" placeholder="new folder name"><button onclick="mkdir()">Create Folder</button></div>
<form id="uploadForm"><div class="row"><input id="file" type="file" name="file"><button>Upload</button></div></form>
</section>
<section><table><thead><tr><th>Name</th><th>Type</th><th>Size</th><th>Actions</th></tr></thead><tbody id="rows"></tbody></table></section>
<section><div class="muted">Files on SD are data/config/media only. ESP32 Arduino C++ libraries cannot be loaded from SD at runtime; compile hardware support into firmware, then use SD files for configuration and presets.</div></section>
</main>
<script>
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function enc(s){return encodeURIComponent(s)}
function go(){loadDir(path.value)}
function up(){let p=path.value.replace(/\/$/,''); let i=p.lastIndexOf('/'); loadDir(i>0?p.slice(0,i):'/')}
async function loadDir(p){
 if(p) path.value=p;
 const r=await fetch('/files?dir='+enc(path.value)); const j=await r.json();
 status.textContent=j.sdReady?'Open '+j.dir:'SD not mounted';
 path.value=j.dir || '/';
 rows.innerHTML='';
 if(j.dir!=='/'){rows.innerHTML+=`<tr><td><a href="#" onclick="up();return false">..</a></td><td>folder</td><td></td><td></td></tr>`}
 for(const e of j.entries||[]){
  const name=esc(e.name), pth=esc(e.path);
  let actions=e.dir?`<a href="#" onclick="loadDir('${pth}');return false">open</a>`:`<a href="/file/view?path=${enc(e.path)}" target="_blank">view</a> <a href="/play?path=${enc(e.path)}" target="_blank">play</a> <a href="/file/download?path=${enc(e.path)}">download</a>`;
  actions+=` <button onclick="del('${pth}')">Delete</button>`;
  rows.innerHTML+=`<tr><td>${name}</td><td>${e.dir?'folder':'file'}</td><td>${e.dir?'':e.size}</td><td>${actions}</td></tr>`;
 }
}
async function mkdir(){await fetch('/mkdir',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({dir:path.value,name:folder.value})}); folder.value=''; loadDir();}
async function del(p){if(!confirm('Delete '+p+'?'))return; await fetch('/file/delete',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({path:p})}); loadDir();}
uploadForm.onsubmit=async e=>{e.preventDefault(); const fd=new FormData(uploadForm); await fetch('/upload?dir='+enc(path.value),{method:'POST',body:fd}); file.value=''; loadDir();};
loadDir(new URLSearchParams(location.search).get('dir')||'/camera');
</script></body></html>
)HTML";
  server.send(200, "text/html", page);
}

void handleStream() {
  WiFiClient client = streamServer.client();
  if (!streamEnabled) {
    client.print("HTTP/1.1 503 Service Unavailable\r\n"
                 "Content-Type: text/plain\r\n"
                 "Connection: close\r\n\r\n"
                 "Camera stream is disabled. Start it from the web UI first.\n");
    return;
  }
  if (!setSensorFrameSize(desiredStreamFrameSize())) {
    client.print("HTTP/1.1 503 Service Unavailable\r\n"
                 "Content-Type: text/plain\r\n"
                 "Connection: close\r\n\r\n"
                 "Unable to switch camera to stream resolution.\n");
    return;
  }
  client.print("HTTP/1.1 200 OK\r\n"
               "Content-Type: multipart/x-mixed-replace; boundary=frame\r\n"
               "Cache-Control: no-cache\r\n"
               "Connection: close\r\n\r\n");

  uint32_t frames = 0;
  int64_t started = esp_timer_get_time();
  while (client.connected() && streamEnabled) {
    if (cameraMutex && xSemaphoreTake(cameraMutex, pdMS_TO_TICKS(500)) != pdTRUE) {
      delay(10);
      continue;
    }
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
      if (cameraMutex) xSemaphoreGive(cameraMutex);
      break;
    }
    client.printf("--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n", fb->len);
    client.write(fb->buf, fb->len);
    client.print("\r\n");
    esp_camera_fb_return(fb);
    if (cameraMutex) xSemaphoreGive(cameraMutex);
    frames++;
    if (frames % 120 == 0) {
      const float seconds = (esp_timer_get_time() - started) / 1000000.0f;
      Serial.printf("Stream %.1f FPS\n", frames / seconds);
    }
    delay(1);
  }
  if (streamPreviewEnabled && !recording) {
    setSensorFrameSize(desiredIdleFrameSize());
  }
}

void addFileJson(String &json, const String &path, size_t size, bool &first) {
  if (!first) json += ",";
  first = false;
  json += "{\"path\":\"" + jsonEscape(path) + "\",\"size\":" + String(size) + "}";
}

void listDirJson(const char *dirname, String &json, bool &first) {
  File root = SD.open(dirname);
  if (!root || !root.isDirectory()) {
    return;
  }
  File file = root.openNextFile();
  while (file) {
    if (!file.isDirectory()) {
      String name = file.name();
      String path = name.startsWith("/") ? name : String(dirname) + "/" + name;
      addFileJson(json, path, file.size(), first);
    }
    file = root.openNextFile();
  }
  root.close();
}

void handleFiles() {
  if (!sdReady) {
    server.send(200, "application/json", "{\"sdReady\":false,\"dir\":\"/\",\"entries\":[],\"files\":[]}");
    return;
  }
  String dir = cleanStoragePath(getArg("dir", ""));
  if (server.hasArg("dir")) {
    if (!isAllowedStoragePath(dir) || !SD.exists(dir)) {
      server.send(404, "application/json", "{\"error\":\"Directory not found\"}");
      return;
    }
    File root = SD.open(dir);
    if (!root || !root.isDirectory()) {
      server.send(400, "application/json", "{\"error\":\"Path is not a directory\"}");
      return;
    }
    String json = "{\"sdReady\":true,\"dir\":\"" + jsonEscape(dir) + "\",\"entries\":[";
    bool first = true;
    File file = root.openNextFile();
    while (file) {
      String name = file.name();
      String path = name.startsWith("/") ? name : (dir == "/" ? "/" + name : dir + "/" + name);
      if (!first) json += ",";
      first = false;
      json += "{\"name\":\"" + jsonEscape(basenameOf(path)) + "\",\"path\":\"" + jsonEscape(path) + "\",\"dir\":";
      json += file.isDirectory() ? "true" : "false";
      json += ",\"size\":" + String(file.isDirectory() ? 0 : file.size()) + "}";
      file = root.openNextFile();
    }
    root.close();
    json += "]}";
    server.send(200, "application/json", json);
    return;
  }

  String json = "{\"sdReady\":true,\"files\":[";
  bool first = true;
  listDirJson(kPhotoDir, json, first);
  listDirJson(kVideoDir, json, first);
  json += "]}";
  server.send(200, "application/json", json);
}

void handleDownload() {
  String path = cleanStoragePath(getArg("path"));
  if (!sdReady || !isAllowedStoragePath(path) || !SD.exists(path)) {
    server.send(404, "text/plain", "File not found");
    return;
  }
  File file = SD.open(path, FILE_READ);
  if (!file || file.isDirectory()) {
    server.send(400, "text/plain", "Path is not a file");
    return;
  }
  String type = contentTypeFor(path);
  server.sendHeader("Content-Disposition", "attachment; filename=\"" + basenameOf(path) + "\"");
  server.sendHeader("X-Content-Type-Options", "nosniff");
  server.streamFile(file, type);
  file.close();
}

void handleViewFile() {
  String path = cleanStoragePath(getArg("path"));
  if (!sdReady || !isAllowedStoragePath(path) || !SD.exists(path)) {
    server.send(404, "text/plain", "File not found");
    return;
  }
  File file = SD.open(path, FILE_READ);
  if (!file || file.isDirectory()) {
    server.send(400, "text/plain", "Path is not a file");
    return;
  }
  server.sendHeader("Content-Disposition", "inline; filename=\"" + basenameOf(path) + "\"");
  server.sendHeader("X-Content-Type-Options", "nosniff");
  server.streamFile(file, contentTypeFor(path));
  file.close();
}

bool handleSdAsset(const String &uri) {
  if (!sdReady || !uri.startsWith("/assets/") || uri.indexOf("..") >= 0) {
    return false;
  }
  String relative = uri.substring(String("/assets").length());
  String path = String(kAssetsDir) + relative;
  path = cleanStoragePath(path);
  if (!SD.exists(path)) {
    return false;
  }
  File file = SD.open(path, FILE_READ);
  if (!file || file.isDirectory()) {
    if (file) file.close();
    return false;
  }
  server.sendHeader("Cache-Control", "public, max-age=3600");
  server.sendHeader("X-Content-Type-Options", "nosniff");
  server.streamFile(file, contentTypeFor(path));
  file.close();
  return true;
}

void handlePlayback() {
  String path = cleanStoragePath(getArg("path"));
  if (!sdReady || !isAllowedStoragePath(path) || !SD.exists(path)) {
    server.send(404, "text/plain", "File not found");
    return;
  }
  File file = SD.open(path, FILE_READ);
  if (!file || file.isDirectory()) {
    server.send(400, "text/plain", "Path is not a file");
    return;
  }
  if (path.endsWith(".jpg")) {
    server.sendHeader("Content-Disposition", "inline; filename=\"" + basenameOf(path) + "\"");
    server.streamFile(file, "image/jpeg");
  } else if (path.endsWith(".mjpeg")) {
    server.sendHeader("Content-Disposition", "inline; filename=\"" + basenameOf(path) + "\"");
    server.streamFile(file, "multipart/x-mixed-replace; boundary=frame");
  } else {
    server.sendHeader("Content-Disposition", "attachment; filename=\"" + basenameOf(path) + "\"");
    server.streamFile(file, "application/octet-stream");
  }
  file.close();
}

void handleDeleteFile() {
  String path = cleanStoragePath(getArg("path"));
  if (recording && path == recordingPath) {
    server.send(409, "text/plain", "Cannot delete active recording");
    return;
  }
  if (!sdReady || !isAllowedStoragePath(path) || !SD.exists(path)) {
    server.send(404, "text/plain", "File not found");
    return;
  }
  File file = SD.open(path);
  bool ok = false;
  if (file && file.isDirectory()) {
    ok = SD.rmdir(path);
  } else {
    ok = SD.remove(path);
  }
  if (file) file.close();
  server.send(ok ? 200 : 500, "text/plain", ok ? "deleted" : "delete failed");
}

void handleMkdir() {
  if (!sdReady) {
    server.send(503, "text/plain", "SD not mounted");
    return;
  }
  String dir = cleanStoragePath(getArg("dir", "/"));
  String name = getArg("name");
  name.trim();
  name.replace("\\", "/");
  if (name.length() == 0 || name.indexOf("/") >= 0 || name.indexOf("..") >= 0) {
    server.send(400, "text/plain", "Invalid folder name");
    return;
  }
  String path = dir == "/" ? "/" + name : dir + "/" + name;
  if (!isAllowedStoragePath(path)) {
    server.send(400, "text/plain", "Invalid path");
    return;
  }
  server.send(SD.mkdir(path) ? 200 : 500, "text/plain", path);
}

void handleUploadComplete() {
  if (uploadFile) {
    uploadFile.close();
  }
  server.send(200, "text/plain", uploadPath.length() ? uploadPath : "upload complete");
}

void handleUploadData() {
  if (!sdReady) {
    return;
  }
  HTTPUpload &upload = server.upload();
  if (upload.status == UPLOAD_FILE_START) {
    String dir = cleanStoragePath(server.hasArg("dir") ? server.arg("dir") : "/camera/uploads");
    if (!SD.exists(dir)) {
      SD.mkdir(dir);
    }
    String name = upload.filename;
    name.replace("\\", "/");
    name = basenameOf(name);
    if (name.length() == 0 || name.indexOf("..") >= 0 || !isAllowedStoragePath(dir)) {
      uploadPath = "";
      return;
    }
    uploadPath = dir == "/" ? "/" + name : dir + "/" + name;
    uploadFile = SD.open(uploadPath, FILE_WRITE);
  } else if (upload.status == UPLOAD_FILE_WRITE) {
    if (uploadFile) {
      uploadFile.write(upload.buf, upload.currentSize);
    }
  } else if (upload.status == UPLOAD_FILE_END || upload.status == UPLOAD_FILE_ABORTED) {
    if (uploadFile) {
      uploadFile.close();
    }
  }
}

void handleStartRecording() {
  uint32_t fps = getArg("fps", "5").toInt();
  if (!startRecording(fps)) {
    server.send(503, "application/json", jsonStatus());
    return;
  }
  server.send(200, "application/json", jsonStatus());
}

void handleStopRecording() {
  stopRecording();
  server.send(200, "application/json", jsonStatus());
}

void handleConfig() {
  if (server.method() == HTTP_POST) {
    streamEnabled = false;
    delay(80);
    const bool requestedLowPower = getArg("power", lowPowerMode ? "low" : "normal") == "low";
    frameSize = parseFrameSize(getArg("framesize", frameSizeName(frameSize)));
    streamFrameSize = parseFrameSize(getArg("streamFramesize", frameSizeName(streamFrameSize)));
    streamPreviewEnabled = getArg("preview", streamPreviewEnabled ? "on" : "off") == "on";
    jpegQuality = constrain(getArg("quality", String(jpegQuality)).toInt(), 4, 63);
    lowPowerMode = requestedLowPower && isLowPowerFrameSize(frameSize);
    if (lowPowerMode) {
      frameSize = FRAMESIZE_QVGA;
      streamFrameSize = FRAMESIZE_QVGA;
      jpegQuality = max(jpegQuality, 18);
    }
    saveCameraSettings();
    applyWifiPower();
    restartCamera();
  }
  server.send(200, "application/json", jsonStatus());
}

void handleThermal() {
  if (server.method() != HTTP_POST) {
    server.send(405, "text/plain", "POST required");
    return;
  }
  thermalAutoStop = getArg("autoStop", thermalAutoStop ? "on" : "off") == "on";
  thermalStoppedStream = false;
  prefs.putBool("thermal_stop", thermalAutoStop);
  sampleThermals(true);
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
  if (isCameraPin(pin) || isStoragePin(pin)) {
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
  server.on("/explorer", HTTP_GET, handleExplorer);
  server.on("/status", HTTP_GET, handleStatus);
  server.on("/wifi/status", HTTP_GET, handleWifiStatus);
  server.on("/wifi/scan", HTTP_GET, handleWifiScan);
  server.on("/modules", HTTP_GET, handleModules);
  server.on("/capture", HTTP_GET, handleCapture);
  server.on("/photo/save", HTTP_POST, handleSavePhoto);
  server.on("/stream", HTTP_GET, []() {
    server.sendHeader("Location", streamUrl(), true);
    server.send(302, "text/plain", "Stream moved to " + streamUrl());
  });
  server.on("/stream/start", HTTP_POST, []() {
    sampleThermals(true);
    if (thermalAutoStop && chipTempC >= kThermalCriticalC) {
      streamEnabled = false;
      server.send(503, "application/json", jsonStatus());
      return;
    }
    if (!setSensorFrameSize(desiredStreamFrameSize())) {
      streamEnabled = false;
      server.send(503, "application/json", jsonStatus());
      return;
    }
    thermalStoppedStream = false;
    streamEnabled = true;
    server.send(200, "application/json", jsonStatus());
  });
  server.on("/stream/stop", HTTP_POST, []() {
    streamEnabled = false;
    setSensorFrameSize(desiredIdleFrameSize());
    server.send(200, "application/json", jsonStatus());
  });
  server.on("/files", HTTP_GET, handleFiles);
  server.on("/file/download", HTTP_GET, handleDownload);
  server.on("/file/view", HTTP_GET, handleViewFile);
  server.on("/file/delete", HTTP_POST, handleDeleteFile);
  server.on("/mkdir", HTTP_POST, handleMkdir);
  server.on("/upload", HTTP_POST, handleUploadComplete, handleUploadData);
  server.on("/play", HTTP_GET, handlePlayback);
  server.on("/record/start", HTTP_POST, handleStartRecording);
  server.on("/record/stop", HTTP_POST, handleStopRecording);
  server.on("/ble/start", HTTP_POST, []() {
    startBle();
    server.send(200, "application/json", jsonStatus());
  });
  server.on("/ble/stop", HTTP_POST, []() {
    stopBle();
    server.send(200, "application/json", jsonStatus());
  });
  server.on("/config", HTTP_POST, handleConfig);
  server.on("/thermal", HTTP_POST, handleThermal);
  server.on("/wifi", HTTP_POST, handleWifi);
  server.on("/gpio", HTTP_GET, handleGpio);
  server.on("/gpio", HTTP_POST, handleGpio);
  server.on("/restart-camera", HTTP_POST, []() {
    restartCamera();
    server.send(200, "text/plain", "restarted");
  });
  server.onNotFound([]() {
    if (handleSdAsset(server.uri())) {
      return;
    }
    server.send(404, "text/plain", "Not found");
  });
  server.begin();
}

void routeStream() {
  streamServer.on("/stream", HTTP_GET, handleStream);
  streamServer.begin();
}

void streamTask(void *) {
  for (;;) {
    streamServer.handleClient();
    delay(1);
  }
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
  } else if (key == "power") {
    if (value == "low") {
      applyLowPowerCameraPreset();
    } else {
      lowPowerMode = false;
      saveCameraSettings();
    }
    applyWifiPower();
    saveCameraSettings();
    restartCamera();
  } else if (key == "thermal") {
    thermalAutoStop = value != "warn";
    thermalStoppedStream = false;
    prefs.putBool("thermal_stop", thermalAutoStop);
    sampleThermals(true);
  } else if (key == "photo" && value == "1") {
    String path;
    savePhoto(path);
  } else if (key == "record" && value == "start") {
    startRecording(5);
  } else if (key == "record" && value == "stop") {
    stopRecording();
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
  if (bleStarted) {
    return;
  }
  WiFi.setSleep(true);
  BLEDevice::init("XIAO-S3-Camera");
  bleServer = BLEDevice::createServer();
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
  bleStarted = true;
  applyWifiPower();
  Serial.println("BLE started. Wi-Fi modem sleep is enabled for coexistence.");
}

void stopBle() {
  if (!bleStarted) {
    return;
  }
  BLEDevice::stopAdvertising();
  if (bleServer) {
    bleServer->disconnect(0);
  }
  BLEDevice::deinit(true);
  bleServer = nullptr;
  configCharacteristic = nullptr;
  bleStarted = false;
  applyWifiPower();
  Serial.println("BLE stopped. Wi-Fi power policy restored.");
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("XIAO ESP32-S3 Sense Camera Server starting");
  cameraMutex = xSemaphoreCreateMutex();
  loadSettings();
  startStorage();
  restorePins();
  connectWifi();
  sampleThermals(true);
  if (!startCamera()) {
    Serial.println("Camera unavailable; check Sense board seating and power.");
  }
  routeWeb();
  routeStream();
  xTaskCreatePinnedToCore(streamTask, "stream-server", 8192, nullptr, 1, &streamTaskHandle, 0);
  Serial.printf("Open %s\n", localUrl().c_str());
  Serial.printf("Stream %s\n", streamUrl().c_str());
}

void loop() {
  server.handleClient();
  serviceWifi();
  sampleThermals();
  serviceRecording();
  delay(1);
}
