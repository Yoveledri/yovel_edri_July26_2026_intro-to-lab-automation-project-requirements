/*
Interrupt
*/

#include <MsTimer2.h>

int led_pin = 4; // LED is defined
int button = 2; // Button is connected from 6 to 2

volatile bool ledOn = false;

void turnOffLED()
{
  digitalWrite(led_pin, LOW);
  ledOn = false;

  MsTimer2::stop();  // stop timer until next button press
}


void buttonPressed()
{
  digitalWrite(led_pin, HIGH);
  ledOn = true;

  Serial.println("Interrupted - Button pressed");

  MsTimer2::set(5000, turnOffLED); // after 5 seconds
  MsTimer2::start();
}


void setup()
{
  pinMode(led_pin, OUTPUT);
  pinMode(button, INPUT_PULLUP);

  Serial.begin(9600);

  attachInterrupt(digitalPinToInterrupt(button), buttonPressed, FALLING);
}


void loop()
{
}