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