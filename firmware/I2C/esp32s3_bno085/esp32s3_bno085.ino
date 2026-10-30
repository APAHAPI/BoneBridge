/*
  BNO085 to ESP32-S3 over I2C (Stemma QT cable)

  Stemma QT wire   Function   ESP32-S3 pin
  Red              3.3V       3V3 (never use 5V)
  Black            GND        GND
  Blue             SDA        GPIO 8
  Yellow           SCL        GPIO 9

  Default I2C address: 0x4A. The PS0 and PS1 pins change it.
  If your board uses different pins, change SDA_PIN and SCL_PIN below.

  Output: roll,pitch,yaw in degrees at 115200 baud, one line per sample.
*/

#include <Wire.h>
#include <Adafruit_BNO08x.h>

#define BNO08X_RESET -1
Adafruit_BNO08x bno08x(BNO08X_RESET);
sh2_SensorValue_t sensorValue;

const int SDA_PIN = 8;
const int SCL_PIN = 9;

void setup(void) {
  Serial.begin(115200);
  while (!Serial) delay(10);

  Serial.println("Initializing BNO085 over I2C...");

  Wire.begin(SDA_PIN, SCL_PIN);

  if (!bno08x.begin_I2C()) {
    Serial.println("BNO085 not found - check I2C wiring!");
    while (1) delay(10);
  }
  
  Serial.println("BNO085 found successfully via I2C!");
  bno08x.enableReport(SH2_GAME_ROTATION_VECTOR);
}

void loop(void) {
  if (bno08x.getSensorEvent(&sensorValue)) {
    if (sensorValue.sensorId == SH2_GAME_ROTATION_VECTOR) {
      float qr = sensorValue.un.gameRotationVector.real;
      float raw_x = sensorValue.un.gameRotationVector.i;
      float raw_y = sensorValue.un.gameRotationVector.j;
      float raw_z = sensorValue.un.gameRotationVector.k;

      float qj = -raw_x; 
      float qi = raw_z;
      float qk = raw_y;

      float t0 = +2.0 * (qr * qi + qj * qk);
      float t1 = +1.0 - 2.0 * (qi * qi + qj * qj);
      float roll = atan2(t0, t1) * 180.0 / M_PI;

      float t2 = +2.0 * (qr * qj - qk * qi);
      t2 = t2 > 1.0 ? 1.0 : t2;
      t2 = t2 < -1.0 ? -1.0 : t2;
      float pitch = asin(t2) * 180.0 / M_PI;

      float t3 = +2.0 * (qr * qk + qi * qj);
      float t4 = +1.0 - 2.0 * (qj * qj + qk * qk);
      float yaw = atan2(t3, t4) * 180.0 / M_PI;

        Serial.print(roll);
        Serial.print(",");
        Serial.print(pitch);
        Serial.print(",");
        Serial.println(yaw);
    }
  }
  delay(20);
}