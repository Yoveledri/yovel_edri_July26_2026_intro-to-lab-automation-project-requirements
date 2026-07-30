#include "Arduino_SensorKit.h"
#include <math.h> // for trigo
#include <Servo.h>

Servo myservo; // create Servo object to control a servo

const int button = 2;   // Button on Pin 2
const int fanPin = 3;   // Fan control pin

volatile bool fanStateChanged = false; // fan TRIGGER
volatile bool currentFanState = false; // fan STATE

int servoAngle = 90;    // Default mid-point angle

void buttonChanged() {
  if (digitalRead(button) == HIGH) { // if button pressed
    digitalWrite(fanPin, HIGH); // activate fan
    currentFanState = true; // change fan STATE
  } else {
    digitalWrite(fanPin, LOW);
    currentFanState = false; // change fan STATE
  }
  fanStateChanged = true; // fan TRIGGER ON
}

void setup() {
  Serial.begin(9600);
  
  // Initialize the SensorKit components
  Accelerometer.begin(); 
  Oled.begin();
  Oled.setFlipMode(true); // Flips the screen right-side up

  // Initialize the Servo
  myservo.attach(7);        // Attaches the servo signal wire on digital pin 7
  myservo.write(servoAngle); // Set to initial position (90 deg center)

  pinMode(button, INPUT);  
  pinMode(fanPin, OUTPUT);
  digitalWrite(fanPin, LOW); // reliably turn off fan at boot

  attachInterrupt(digitalPinToInterrupt(button), buttonChanged, CHANGE);

  // Print initial static label
  Oled.setFont(u8x8_font_chroma48medium8_r);
  Oled.setCursor(0, 0);
  Oled.print("Fan Status:");
}

void loop() {
  // --- SENSOR KIT & LOGIC HANDLING ---
  // Read the current accelerometer values continuously to calculate angles
  float x = Accelerometer.readX();
  float y = Accelerometer.readY();
  float z = Accelerometer.readZ();

  // Angle calculations (in degrees, roughly -90 to +90)
  float pitch = atan2(x, sqrt(y * y + z * z)) * 180.0 / M_PI;
  float roll  = atan2(y, sqrt(x * x + z * z)) * 180.0 / M_PI;

  // --- SERVO CONTROL VIA BOARD TILT (INDEPENDENT OF BUTTON) ---
  // 1. CHOOSE YOUR AXIS: Swap 'roll' with 'pitch' below depending on how your board is oriented
  float targetAxis = roll; 

  // 2. MAP TILT TO SERVO ANGLE:
  // Maps tilt angle (-45 deg to +45 deg) directly to servo angle limits (10 to 170 deg)
  servoAngle = map((int)targetAxis, -45, 45, 10, 170);

  // 3. SAFETY CONSTRAINTS: Keep the angle strictly bounded between 10 and 170 degrees
  servoAngle = constrain(servoAngle, 10, 170);

  // 4. WRITE TO SERVO (Runs on every loop iteration regardless of fan state)
  myservo.write(servoAngle);

  // --- UPDATE OLED DISPLAY ---
  Oled.setCursor(12, 0); 
  if (currentFanState) {
    Oled.print("ON ");
  } else {
    Oled.print("OFF");
  }

  // Display tracking angles on rows 3 and 5
  Oled.setCursor(0, 3);
  Oled.print("Pitch: ");
  Oled.print(pitch, 1);
  Oled.print("  "); // Extra spaces clear leftover trailing characters

  Oled.setCursor(0, 5);
  Oled.print("Roll:  ");
  Oled.print(roll, 1);
  Oled.print("  ");

  // --- SERIAL MONITOR OUTPUT (ONLY RUNS ON CHANGE) ---
  if (fanStateChanged) {
    fanStateChanged = false; // Reset the flag

    if (currentFanState) {
      Serial.println(">>> Button PRESSED -> Fan turned ON"); 
    } else {
      Serial.println("<<< Button RELEASED -> Fan turned OFF"); 
    }

    Serial.print("    Tilt Angles -> Pitch: ");
    Serial.print(pitch, 1); 
    Serial.print(" deg | Roll: ");
    Serial.print(roll, 1);
    Serial.println(" deg");
  }

  delay(20); 
}