/*
  HW-123 (MPU-6050) to ESP32-S3 over I2C

  HW-123 pin   Function    ESP32-S3 pin
  VCC          3.3V        3V3
  GND          Ground      GND
  SCL          I2C clock   GPIO 9
  SDA          I2C data    GPIO 8

  Default I2C address: 0x68. The AD0 pin changes it.
  If your board uses different pins, change SDA_PIN and SCL_PIN below.

  Output: roll,pitch,yaw in degrees at 115200 baud, one line per sample.
  Yaw is always 0 because this sketch has no magnetometer.
*/

#include <Wire.h>
#include <MPU6050.h>

MPU6050 mpu;

const int SDA_PIN = 8;
const int SCL_PIN = 9;

void setup() {
  Serial.begin(115200);
  Wire.begin(SDA_PIN, SCL_PIN);
  
  mpu.initialize();
  mpu.setSleepEnabled(false);
  
  if (!mpu.testConnection()) {
    while(1);
  }
}

void loop() {
  int16_t ax, ay, az, gx, gy, gz;
  mpu.getMotion6(&ax, &ay, &az, &gx, &gy, &gz);

  float roll = atan2(ay, az) * 180.0 / PI;
  float pitch = atan2(-ax, sqrt(ay * ay + az * az)) * 180.0 / PI;
  float yaw = 0.0;

  Serial.print(roll);
  Serial.print(",");
  Serial.print(pitch);
  Serial.print(",");
  Serial.println(yaw);

  delay(20);
}