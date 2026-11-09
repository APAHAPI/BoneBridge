/*
  BNO085 to ESP32-S3 over SPI (normal wiring)

Function   ESP32-S3 pin
3.3V/VIN   3V3 (never use 5V)
GND        GND
SDA        GPIO 13
SCL        GPIO 12
DI	   GPIO 11
CS	   GPIO 10
INT	   GPIO 9
RST	   GPIO 8
P0	   3.3V/VIN
P1	   3.3V/VIN


  The PS0 and PS1 pins must be HIGH to trigger SPI protocol.
  If your board uses different pins, change SDA_PIN and SCL_PIN below.

  Output: roll,pitch,yaw in degrees at 115200 baud, one line per sample.
*/

#include <Adafruit_BNO08x.h>
#include <SPI.h>

#define BNO_CS  10
#define BNO_INT 9
#define BNO_RST 8

Adafruit_BNO08x bno(BNO_RST);
sh2_SensorValue_t sensorValue;

float roll = 0, pitch = 0, yaw = 0;

void setup(void) {
  Serial.begin(115200);
  while (!Serial) delay(10);

  Serial.println("Initializing BNO085 via SPI...");

  // Initialize via SPI using CS and INT pins
  if (!bno.begin_SPI(BNO_CS, BNO_INT)) {
    Serial.println("Failed to find BNO085 over SPI!");
    while (1) delay(10);
  }
  
  Serial.println("BNO085 found over SPI!");
  bno.enableReport(SH2_GAME_ROTATION_VECTOR);
}

void quaternionToEuler(float qr, float qi, float qj, float qk, float &r, float &p, float &y) {
  float sqr = qr * qr;
  float sqi = qi * qi;
  float sqj = qj * qj;
  float sqk = qk * qk;

  p = asin(2.0 * (qi * qk - qr * qj)) * RAD_TO_DEG;
  r = atan2(2.0 * (qr * qi + qj * qk), sqr - sqi - sqj + sqk) * RAD_TO_DEG;
  y = atan2(2.0 * (qr * qk + qi * qj), sqr + sqi - sqj - sqk) * RAD_TO_DEG;
}

void loop(void) {
  if (bno.getSensorEvent(&sensorValue)) {
    if (sensorValue.sensorId == SH2_GAME_ROTATION_VECTOR) {
      quaternionToEuler(
        sensorValue.un.gameRotationVector.real,
        sensorValue.un.gameRotationVector.i,
        sensorValue.un.gameRotationVector.j,
        sensorValue.un.gameRotationVector.k,
        roll, pitch, yaw
      );
    }
  }

  Serial.print(roll); Serial.print(",");
  Serial.print(pitch); Serial.print(",");
  Serial.println(yaw);

  delay(20);
}