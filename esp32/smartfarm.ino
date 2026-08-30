/*
 * LionKing Smart Farm — ESP32 โรงเรือนผัก (POC)
 * - อ่านเซ็นเซอร์: DHT22 (อุณหภูมิ/ความชื้น), ความชื้นดิน (analog), แสง LDR (analog)
 * - ส่งข้อมูลไป Dashboard: POST /api/sensor
 * - ดึงสถานะควบคุม: GET /api/control → เปิด/ปิด RELAY (ปั๊มน้ำ/พัดลม/ไฟ)
 *
 * ติดตั้ง Library: DHT sensor library (adafruit), ArduinoJson
 * การต่อ:
 *   DHT22 DATA -> GPIO 4
 *   ความชื้นดิน (analog out) -> GPIO 34
 *   LDR (กับ 10k pulldown)  -> GPIO 35
 *   Relay1 (ปั๊มน้ำ)         -> GPIO 25
 *   Relay2 (พัดลม)           -> GPIO 26
 *   Relay3 (ไฟปลูก)          -> GPIO 27
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <DHT.h>

// ==== ค่าที่ต้องตั้ง =====
const char* WIFI_SSID = "YOUR_WIFI";
const char* WIFI_PASS = "YOUR_PASSWORD";
const char* SERVER   = "http://192.168.255.104:5052"; // URL Dashboard
// ========================

const int DHT_PIN = 4, SOIL_PIN = 34, LDR_PIN = 35;
const int R_PUMP = 25, R_FAN = 26, R_LIGHT = 27;
DHT dht(DHT_PIN, DHT22);

unsigned long lastPost = 0, lastPoll = 0;

void setup() {
  Serial.begin(115200);
  dht.begin();
  pinMode(R_PUMP, OUTPUT); pinMode(R_FAN, OUTPUT); pinMode(R_LIGHT, OUTPUT);
  digitalWrite(R_PUMP, LOW); digitalWrite(R_FAN, LOW); digitalWrite(R_LIGHT, LOW);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) { delay(400); Serial.print("."); }
  Serial.println("\nWiFi connected: " + String(WiFi.localIP()));
}

void sendSensor() {
  float t = dht.readTemperature();
  float h = dht.readHumidity();
  if (isnan(t) || isnan(h)) { Serial.println("DHT read fail"); t = 0; h = 0; }
  int soil = map(analogRead(SOIL_PIN), 0, 4095, 100, 0); // เปียก->100
  int light = analogRead(LDR_PIN);
  HTTPClient http;
  http.begin(String(SERVER) + "/api/sensor");
  http.addHeader("Content-Type", "application/json");
  String body = "{\"temp\":\"" + String(t,1) + "\",\"hum\":\"" + String(h,1) +
                "\",\"soil\":\"" + String(soil) + "\",\"light\":\"" + String(light) + "\"}";
  int code = http.POST(body);
  Serial.printf("POST sensor -> %d\n", code);
  http.end();
}

void pollControl() {
  HTTPClient http;
  http.begin(String(SERVER) + "/api/control");
  int code = http.GET();
  if (code == 200) {
    DynamicJsonDocument doc(128);
    deserializeJson(doc, http.getString());
    digitalWrite(R_PUMP,  doc["pump"]  ? HIGH : LOW);
    digitalWrite(R_FAN,   doc["fan"]   ? HIGH : LOW);
    digitalWrite(R_LIGHT, doc["light"] ? HIGH : LOW);
    Serial.printf("Control: pump=%d fan=%d light=%d\n",
                  (int)doc["pump"], (int)doc["fan"], (int)doc["light"]);
  }
  http.end();
}

void loop() {
  if (millis() - lastPost >= 5000) { sendSensor(); lastPost = millis(); }
  if (millis() - lastPoll >= 3000) { pollControl(); lastPoll = millis(); }
}