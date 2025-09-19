#!/usr/bin/env python3
import time
import configparser
import serial
import logging
import RPi.GPIO as GPIO
import math
import asyncio
import datetime
from serverish.messenger import Messenger, get_publisher

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

config = configparser.ConfigParser()
config.read('water_config.ini')

async def send2nats(level: int, ts: list):
    host = config.get("SERVER-CONNECTION", "host")
    port = config.getint("SERVER-CONNECTION", "port")
    stream = config.get("SERVER-CONNECTION", "target_water_stream")
    
    try:
        async with Messenger().context(host=host, port=port):
            pub = get_publisher(stream)
            await pub.publish(
                data={'measurements': {"water_level": level}, 'ts': ts},
                meta={
                    "message_type": "telemetry",
                    "tags": ["water_level", "first_water_level", "inaccurate_measurement_water"],
                    'sender': 'Raspberry_unit_water_reader',
                }
            )
            logging.info(f"Successfully sent water level ({level} L) to NATS.")
    except Exception as e:
        logging.error(f"Failed to send data to NATS: {e}")

async def process_data_frame(line: str):
    logging.info(f"Received data frame from Arduino: {line}")
    try:
        parts = line.strip('<>').split(',')
        values = [int(p) for p in parts]
        
        if len(values) != 8:
            logging.warning(f"[Arduino] Received frame with incorrect length.")
            return

        readings = values[:7]
        received_checksum = values[7]
        calculated_checksum = sum(readings)
        
        if received_checksum != calculated_checksum:
            logging.error(f"[Arduino] CHECKSUM ERROR! Received: {received_checksum}, Calculated: {calculated_checksum}.")
            return

        analog_reading = readings[6]
        voltage = (analog_reading / 1023.0) * 5.0
        water_level_liters = max(0, voltage / 0.27) * 1000
        rounded_level_liters = round(water_level_liters / 100) * 100

        logging.info(f"Voltage on A5: {voltage:.2f}V")
        logging.info(f"Water level from pressure sensor: {water_level_liters:.0f} L")
        logging.info(f"Water level from pressure sensor (rounded value): {rounded_level_liters} L")
        
        now = datetime.datetime.utcnow()
        ts = [now.year, now.month, now.day, now.hour, now.minute, now.second, now.microsecond]
        
        await send2nats(int(rounded_level_liters), ts)

    except (ValueError, IndexError) as e:
        logging.error(f"Error processing frame: {e}")

def process_log_message(line: str):
    log_content = line.strip('{}')
    log_type, message = log_content.split(':', 1) if ':' in log_content else ('INFO', log_content)
    
    if log_type == "ERROR": logging.error(f"[Arduino LOG] {message}")
    elif log_type == "WARN": logging.warning(f"[Arduino LOG] {message}")
    else: logging.info(f"[Arduino LOG] {message}")

def measure_distance_cm(trig_pin, echo_pin):
    GPIO.output(trig_pin, True)
    time.sleep(0.00001)
    GPIO.output(trig_pin, False)
    start_time, stop_time = time.time(), time.time()
    timeout_start = time.time()
    while GPIO.input(echo_pin) == 0:
        start_time = time.time()
        if time.time() - timeout_start > 1:
            logging.error("[Ultrasound] Timeout waiting for ECHO (start)")
            return -1
    timeout_start = time.time()
    while GPIO.input(echo_pin) == 1:
        stop_time = time.time()
        if time.time() - timeout_start > 1:
            logging.error("[Ultrasound] Timeout waiting for ECHO (end)")
            return -1
    return ((stop_time - start_time) * 34300) / 2

def process_ultrasonic_reading(config_section):
    trig_pin = config_section.getint('gpio_trig')
    echo_pin = config_section.getint('gpio_echo')
    
    distance_cm = measure_distance_cm(trig_pin, echo_pin)
    
    if distance_cm == -1:
        logging.warning("[Ultrasound] Measurement error (timeout).")
        return

    tank_height_m = config_section.getfloat('tank_height_m')
    tank_radius_m = config_section.getfloat('tank_radius_m')
    sensor_min_range_m = config_section.getfloat('sensor_min_range_m')
    
    distance_m = distance_cm / 100.0
    water_height_m = 0.0
    
    if distance_m <= sensor_min_range_m:
        water_height_m = tank_height_m
    elif distance_m < tank_height_m:
        water_height_m = tank_height_m - distance_m

    volume_m3 = (math.pi * (tank_radius_m ** 2)) * water_height_m
    volume_liters = volume_m3 * 1000.0
    
    logging.info(f"Water level from ultrasonic sensor: {volume_liters:.0f} L")
    
async def main():
    ser = None
    try:
        arduino_config = config['ARDUINO-CONNECTION']
        serial_port = arduino_config.get('serialport')
        request_interval = arduino_config.getint('interval', fallback=60)
        ser = serial.Serial(serial_port, 9600, timeout=5)
        logging.info(f"Connected to Arduino on port {serial_port}")
        time.sleep(2)

        ultrasonic_config = config['ULTRASONIC_SENSOR']
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(ultrasonic_config.getint('gpio_trig'), GPIO.OUT)
        GPIO.setup(ultrasonic_config.getint('gpio_echo'), GPIO.IN)
        GPIO.output(ultrasonic_config.getint('gpio_trig'), False)
        logging.info("Configured GPIO pins for the ultrasonic sensor.")
        
        while ser.in_waiting > 0:
            line = ser.readline().decode('utf-8').strip()
            if line: process_log_message(line)
        time.sleep(1)

        while True:
            logging.info("Starting new measurement cycle")

            ser.write(b'?')
            time.sleep(1)
            while ser.in_waiting > 0:
                line = ser.readline().decode('utf-8').strip()
                if line.startswith('<'):
                    await process_data_frame(line)
                elif line.startswith('{'):
                    process_log_message(line)
            
            process_ultrasonic_reading(ultrasonic_config)
            
            logging.info(f"End of cycle. Next measurement in {request_interval} seconds.")
            await asyncio.sleep(request_interval)
            
    except serial.SerialException as e:
        logging.critical(f"CRITICAL SERIAL PORT ERROR: {e}.")
    except KeyboardInterrupt:
        logging.info("Interrupted by user. Closing...")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
    finally:
        if ser and ser.is_open:
            ser.close()
            logging.info("Serial port closed.")
        GPIO.cleanup()
        logging.info("GPIO cleaned up.")

if __name__ == '__main__':
    asyncio.run(main())
