/*
Interrupt
*/

#include <MsTimer2.h>

int led_pin = 4; // LED is defined
int button = 2; // Button is connected from 6 to 2

volatile bool ledOn = false;


void turnOffLED() // Turn off LED automatically after 5 seconds
{
  digitalWrite(led_pin, LOW);
  ledOn = false;

  MsTimer2::stop();  // resets timer until next button press
}


void buttonPressed() // Turn on LED when button pressed; only for 5 seconds
{
  digitalWrite(led_pin, HIGH);
  ledOn = true;

  Serial.println("Interrupted - Button pressed");

  MsTimer2::set(30, turnOffLED); // after 30 ms seconds
  MsTimer2::start();
}


void setup()
{
  pinMode(led_pin, OUTPUT);
  pinMode(button, INPUT_PULLUP);

  Serial.begin(9600);

  attachInterrupt(digitalPinToInterrupt(button), buttonPressed, CHANGE);
}


void loop()
{
for (int i = 0; i< 10000; i++){
Serial.println("calculating...");

}}