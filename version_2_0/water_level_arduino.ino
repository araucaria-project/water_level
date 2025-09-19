#include <avr/wdt.h>

int inputPins[6] = {2, 3, 4, 5, 6, 7};
#define LED_PIN 13 

long heartbeat_previousMillis = 0;
unsigned long uptime_previousMillis = 0;
unsigned long vcc_previousMillis = 0;

void sendLog(String logType, String message) {
  Serial.print("{");
  Serial.print(logType);
  Serial.print(":");
  Serial.print(message);
  Serial.println("}");
}

long readVcc() {
  ADMUX = _BV(REFS0) | _BV(MUX3) | _BV(MUX2) | _BV(MUX1);
  delay(2);
  ADCSRA |= _BV(ADSC);
  while (bit_is_set(ADCSRA, ADSC));
  long result = ADCL;
  result |= ADCH << 8;
  result = 1125300L / result;
  return result;
}

void setup() {
  if (MCUSR & (1 << WDRF)) {
    sendLog("ERROR", "Rebooted by Watchdog");
  }
  MCUSR = 0;
  
  Serial.begin(9600);
  
  pinMode(LED_PIN, OUTPUT);
  for (int i = 0; i < 6; i++) {
    pinMode(inputPins[i], INPUT_PULLUP);
  }
  
  wdt_enable(WDTO_8S); 
  
  sendLog("STATUS", "Ready");
}

void sendDataFrame() {
  digitalWrite(LED_PIN, HIGH);

  int checksum = 0;
  int digitalReadings[6];
  
  for (int i = 0; i < 6; i++) {
    digitalReadings[i] = digitalRead(inputPins[i]);
    checksum += digitalReadings[i];
  }
  
  int analogReading = analogRead(A5);
  checksum += analogReading;

  if (analogReading == 0 || analogReading == 1023) {
    sendLog("WARN", "Analog sensor out of range");
  }

  Serial.print('<');
  for (int i = 0; i < 6; i++) {
    Serial.print(digitalReadings[i]);
    Serial.print(',');
  }
  Serial.print(analogReading);
  Serial.print(',');
  Serial.print(checksum);
  Serial.println('>');

  digitalWrite(LED_PIN, LOW);
}

void loop() {
  wdt_reset(); 

  if (Serial.available() > 0) {
    char receivedChar = Serial.read();
    if (receivedChar == '?') {
      sendDataFrame();
    }
  }

  unsigned long currentMillis = millis();

  if (currentMillis - heartbeat_previousMillis >= 1000) {
    heartbeat_previousMillis = currentMillis;
    if (digitalRead(LED_PIN) == LOW) {
      digitalWrite(LED_PIN, HIGH);
      delay(10);
      digitalWrite(LED_PIN, LOW);
    }
  }

  if (currentMillis - vcc_previousMillis >= 300000UL) { // Co 5 minut
    vcc_previousMillis = currentMillis;
    long vcc = readVcc();
    if (vcc < 4500) {
      sendLog("ERROR", "Low supply voltage: " + String(vcc) + "mV");
    }
  }

  if (currentMillis - uptime_previousMillis >= 3600000UL) { // Co 1 godzinę
    uptime_previousMillis = currentMillis;
    long hours = millis() / 3600000UL;
    sendLog("STATUS", "Uptime: " + String(hours) + "h");
  }
}
