#include <AccelStepper.h>

#define MOTOR_COUNT 3
#define ENABLE_PIN 8

#define STEP_0_PIN 2
#define DIR_0_PIN 5

#define STEP_1_PIN 3
#define DIR_1_PIN 6

#define STEP_2_PIN 4
#define DIR_2_PIN 7

AccelStepper stepper0(AccelStepper::DRIVER, STEP_0_PIN, DIR_0_PIN);
AccelStepper stepper1(AccelStepper::DRIVER, STEP_1_PIN, DIR_1_PIN);
AccelStepper stepper2(AccelStepper::DRIVER, STEP_2_PIN, DIR_2_PIN);

AccelStepper* motors[MOTOR_COUNT] = {&stepper0, &stepper1, &stepper2};
bool motorsRunning[MOTOR_COUNT] = {false, false, false};
bool motorNumberAcknowledged = false;

void setup() {
  pinMode(ENABLE_PIN, OUTPUT);
  digitalWrite(ENABLE_PIN, HIGH);

  Serial.begin(115200);
  delay(100);
  Serial.println("XIAO ESP32-S3 MIDI Stepper Player starting...");

  for (int i = 0; i < MOTOR_COUNT; ++i) {
    motors[i]->setMaxSpeed(4000);
    motors[i]->setAcceleration(1500);
  }
}

void handleSerialCommand(const String& command) {
  if (command.startsWith("s,")) {
    // Format: s,<motor>,<speed>
    int motorIndex = command.substring(2, 3).toInt();
    float speed = command.substring(4).toFloat();
    if (motorIndex < 0 || motorIndex >= MOTOR_COUNT) {
      return;
    }
    digitalWrite(ENABLE_PIN, LOW);
    motors[motorIndex]->setSpeed(speed);
    motors[motorIndex]->runSpeed();
    motorsRunning[motorIndex] = true;
  } else if (command.startsWith("e,")) {
    int motorIndex = command.substring(2).toInt();
    if (motorIndex < 0 || motorIndex >= MOTOR_COUNT) {
      return;
    }
    motors[motorIndex]->stop();
    motorsRunning[motorIndex] = false;
  } else if (command == "d") {
    digitalWrite(ENABLE_PIN, HIGH);
    for (int i = 0; i < MOTOR_COUNT; ++i) {
      motorsRunning[i] = false;
    }
  }
}

void loop() {
  if (!motorNumberAcknowledged) {
    Serial.println("motors: " + String(MOTOR_COUNT));
    while (Serial.available()) {
      String command = Serial.readStringUntil('\n');
      command.trim();
      command.toLowerCase();
      if (command == "ack") {
        motorNumberAcknowledged = true;
      }
    }
    delay(200);
    return;
  }

  while (Serial.available()) {
    String command = Serial.readStringUntil('\n');
    command.trim();
    command.toLowerCase();
    handleSerialCommand(command);
  }

  for (int i = 0; i < MOTOR_COUNT; ++i) {
    if (motorsRunning[i]) {
      if (motors[i]->isRunning()) {
        motors[i]->runSpeed();
      } else {
        motorsRunning[i] = false;
      }
    }
  }
}
