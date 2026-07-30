#include "Arduino_SensorKit.h"
#include <math.h> // for trigo

const int button = 2;   // Button on Pin 2
const int fanPin = 3;   // Fan control pin

volatile bool fanStateChanged = false; // fan TRIGGER
volatile bool currentFanState = false; // fan STATE

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
  // Read the current accelerometer values continuously to calculate angles
  float x = Accelerometer.readX();
  float y = Accelerometer.readY();
  float z = Accelerometer.readZ();

  // Angle calculations
  float pitch = atan2(x, sqrt(y * y + z * z)) * 180.0 / M_PI;
  float roll  = atan2(y, sqrt(x * x + z * z)) * 180.0 / M_PI;

  // --- UPDATE OLED DISPLAY ---
  // Display current fan status
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

  delay(200); // Small delay to prevent screen flicker and stabilize readouts
}
