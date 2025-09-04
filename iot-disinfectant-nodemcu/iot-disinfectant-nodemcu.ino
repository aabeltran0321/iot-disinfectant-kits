#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <ArduinoJson.h>
#include <EEPROM.h>

#define EEPROM_SIZE 128
#define RELAY_PIN D1
#define TANK_ID 2   // which tank this ESP8266 controls

// Define server domain (can be IP or hostname)
const char* serverDomain = "http://10.10.121.81:5000";
const char* serverDomain11 = "http://bigboysautomation.pythonanywhere.com";

// Build URLs from domain
String scheduleURL = String(serverDomain11) + "/iotdisinfectant/get_schedule/" + String(TANK_ID);
String updateLevelURL = String(serverDomain11) + "/iotdisinfectant/update_level";



unsigned long lastCheck = 0;
unsigned long lastUpdate = 0;
bool relayActive = false;
unsigned long relayEndTime = 0;

String wifiSSID;
String wifiPASS;

void saveWiFiCredentials(String ssid, String pass) {
  EEPROM.begin(EEPROM_SIZE);
  for (int i = 0; i < ssid.length(); ++i) EEPROM.write(i, ssid[i]);
  EEPROM.write(ssid.length(), '\0');
  for (int i = 0; i < pass.length(); ++i) EEPROM.write(32 + i, pass[i]);
  EEPROM.write(32 + pass.length(), '\0');
  EEPROM.commit();
}

void loadWiFiCredentials() {
  char ssid[32], pass[32];
  EEPROM.begin(EEPROM_SIZE);
  EEPROM.get(0, ssid);
  EEPROM.get(32, pass);
  wifiSSID = String(ssid);
  wifiPASS = String(pass);
}

void clearWiFiCredentials() {
  EEPROM.begin(EEPROM_SIZE);
  for (int i = 0; i < EEPROM_SIZE; i++) EEPROM.write(i, 0);
  EEPROM.commit();
  wifiSSID = "";
  wifiPASS = "";
  Serial.println("WiFi credentials cleared. Type reset to enter new ones.");
}

void requestWiFiCredentials() {
  Serial.println("Enter WiFi SSID:");
  while (wifiSSID.length() == 0) {
    if (Serial.available()) {
      wifiSSID = Serial.readStringUntil('\n');
      wifiSSID.trim();
    }
  }
  Serial.println("Enter WiFi Password:");
  while (wifiPASS.length() == 0) {
    if (Serial.available()) {
      wifiPASS = Serial.readStringUntil('\n');
      wifiPASS.trim();
    }
  }
  saveWiFiCredentials(wifiSSID, wifiPASS);
}

void connectWiFi() {
  WiFi.begin(wifiSSID.c_str(), wifiPASS.c_str());
  Serial.print("Connecting to WiFi");
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\nConnected to WiFi!");
    Serial.print("IP Address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\nFailed to connect. Type resetwifi to try again.");
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(RELAY_PIN, OUTPUT);
  pinMode(D5, INPUT_PULLUP);
  digitalWrite(RELAY_PIN, LOW);

  loadWiFiCredentials();
  if (wifiSSID.length() == 0 || wifiPASS.length() == 0) {
    requestWiFiCredentials();
  }

  connectWiFi();
}

void loop() {
  unsigned long currentMillis = millis();

  // Check for Serial commands
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd == "resetwifi") {
      clearWiFiCredentials();
      requestWiFiCredentials();
      connectWiFi();
    }
  }

  // Check schedule every 5 seconds
  if (currentMillis - lastCheck >= 5000) {
    lastCheck = currentMillis;
    checkSchedule();
  }

  // Update tank level every 10 seconds
  if (currentMillis - lastUpdate >= 10000) {
    lastUpdate = currentMillis;
    updateTankLevel();
  }

  // Handle relay timing (non-blocking)
  if (relayActive && currentMillis >= relayEndTime) {
    digitalWrite(RELAY_PIN, HIGH);
    delay(100);
    digitalWrite(RELAY_PIN, LOW);
    delay(100);
    digitalWrite(RELAY_PIN, HIGH);
    delay(100);
    digitalWrite(RELAY_PIN, LOW);
    relayActive = false;
    Serial.println("Relay OFF");
  }
}

void checkSchedule() {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(scheduleURL);
    int httpResponseCode = http.GET();

    if (httpResponseCode > 0) {
      String payload = http.getString();
      Serial.println("Schedule Response: " + payload);

      StaticJsonDocument<200> doc;
      DeserializationError error = deserializeJson(doc, payload);
      if (!error) {
        bool activate = doc["activate"];
        int duration = doc["duration"];

        if (activate) {
          Serial.println("Activating relay!");
          digitalWrite(RELAY_PIN, HIGH);
          delay(100);
          digitalWrite(RELAY_PIN, LOW);
          relayActive = true;
          relayEndTime = millis() + (duration * 1000);
        }
      }
    } else {
      Serial.print("Error on GET request: ");
      Serial.println(httpResponseCode);
    }
    http.end();
  }
}

void updateTankLevel() {
  if (WiFi.status() == WL_CONNECTED) {
    int level = digitalRead(D5);  
    //int level = map(sensorValue, 0, 1023, 0, 100); // Example: 0–100% scale

    HTTPClient http;
    http.begin(updateLevelURL);
    http.addHeader("Content-Type", "application/json");

    StaticJsonDocument<200> doc;
    doc["tank"] = TANK_ID;
    doc["level"] = level;

    String requestBody;
    serializeJson(doc, requestBody);

    int httpResponseCode = http.POST(requestBody);

    if (httpResponseCode > 0) {
      String response = http.getString();
      Serial.println("Level Update Response: " + response);
    } else {
      Serial.print("Error on POST request: ");
      Serial.println(httpResponseCode);
    }
    http.end();
  }
}
