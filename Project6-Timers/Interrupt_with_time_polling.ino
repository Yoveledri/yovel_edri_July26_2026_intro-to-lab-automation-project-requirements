/*
using millis()
*/

int led_pin = 4;
int button = 2;

volatile bool buttonPressedFlag = false;

unsigned long ledStartTime = 0;
bool ledOn = false;


void buttonPressed()
{
  buttonPressedFlag = true;
}


void setup()
{
  pinMode(led_pin, OUTPUT);
  pinMode(button, INPUT_PULLUP);

  Serial.begin(9600);

  attachInterrupt(digitalPinToInterrupt(button), buttonPressed, CHANGE);
}


void loop(){
//{for (int i = 0; i< 10000; i++){
//  Serial.println("calculating...");
//}
  // Check if button interrupt happened
  if (buttonPressedFlag) {

    digitalWrite(led_pin, HIGH);
    ledOn = true;

    ledStartTime = millis();
    Serial.println("Button pressed");

    buttonPressedFlag = false;
  }
int time = millis();
Serial.println (time);

  // Check if 5 seconds passed
  if (ledOn && millis() - ledStartTime >= 5000) {

    digitalWrite(led_pin, LOW);
    ledOn = false;

    Serial.println("LED turned off");
  }
}