#include <stdio.h>
//6 levels water level sensor

//sensors
int inputPins[6] = {2,3,4,5,6,7};
//diods
int outputPins[8]= {8,9,10,11,12,13,0,1};
int j = 0;

void setup() { 
    //sensors (contactrons, cables etc.)
    pinMode(inputPins[0], INPUT);
    pinMode(inputPins[1], INPUT);
    pinMode(inputPins[2], INPUT);
    pinMode(inputPins[3], INPUT);
    pinMode(inputPins[4], INPUT);
    pinMode(inputPins[5], INPUT);
    //diods
    pinMode(outputPins[0], OUTPUT);
    pinMode(outputPins[1], OUTPUT);
    pinMode(outputPins[2], OUTPUT);
    pinMode(outputPins[3], OUTPUT);
    pinMode(outputPins[4], OUTPUT);
    pinMode(outputPins[5], OUTPUT);
    pinMode(outputPins[6], OUTPUT);
    pinMode(outputPins[7], OUTPUT);
    Serial.begin(9600);
    }

    
void loop(){ 
    if (Serial.available() > 0) {
       for(j=0;j<6;j=j+1){
          int reading = digitalRead(inputPins[j]);
          if(reading == 0){
             digitalWrite(outputPins[j], HIGH);
          }
          else{
             digitalWrite(outputPins[j], LOW);
          }
          Serial.println(reading);
       // read the incoming byte:
       }
       digitalWrite(outputPins[6],LOW);
       digitalWrite(outputPins[7],LOW);
    }
    else{
       digitalWrite(outputPins[6],HIGH);
       digitalWrite(outputPins[7],HIGH);
       for(j=0;j<6;j=j+1){
          int reading = digitalRead(inputPins[j]);
          if(reading == 0){
             digitalWrite(outputPins[j], HIGH);
          }
          else{
             digitalWrite(outputPins[j], LOW);
          }
       }
    }
          
    
    delay(10000);
    
}

  
