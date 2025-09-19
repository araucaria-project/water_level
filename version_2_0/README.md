# WATER LEVEL

## Sensors

- pressure sensor
  - currently used for measurement
- ultrasonic sensor

## DEPENDENICES

- ```pip install pyserial "RPi.GPIO" serverish nats-py```
- ```python3 water_level.py```

## ARDUINO FUNCTIONALITY

- **Request Handling:** Listens on the serial port. Upon receiving a "?" character, it reads sensor data and sends it back.
- **Data Collection:** Reads the state of six digital inputs and the value of one analog input (A5).
- **Data & Log Transmission:** Sends measurement data in a specific format (<... >) along with a checksum. Additionally, it sends operational status logs (e.g., uptime, ready) and errors (e.g., low voltage) in a separate format ({...}).
- **Supervision & Safety:** Uses a built-in watchdog timer that automatically resets the microcontroller if the program freezes. Checks every 8 seconds.
- **Self-Diagnostics:** Periodically (every 5 minutes) measures its own supply voltage and sends a warning if it's too low.
- **Visual Signaling:** Flashes the built-in LED every second (a "heartbeat") to indicate that the device is operating correctly.


## RPI FUNCTIONALITY

- **Arduino Communication:** Connects to the Arduino via a serial port, sends a measurement request ("?" character), and receives a data frame: <float_1, float_2, float_3, float_4, float_5, float_6, digital_voltage_value, checksum>.
- **Pressure Measurement Processing:** Processes data from the Arduino, verifies the checksum, and calculates the water level in liters based on the voltage reading.
- **Ultrasonic Measurement:** Controls an ultrasonic sensor connected to the Raspberry Pi's GPIO pins to measure distance and calculate water volume.
- **Data Transmission:** Sends the rounded measurement result from the Arduino (to the nearest hundred liters) along with a timestamp to the NATS server.
- **Logging & Configuration:** Logs all operations to the console in English and loads all settings (ports, pins, tank dimensions) from an external file.
