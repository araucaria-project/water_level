import asyncio
import colorsys
import time
from collections import deque
import RPi.GPIO as GPIO
from rpi_ws281x import PixelStrip, Color
from ina219 import INA219
from nats.aio.client import Client as NATS
import json
import datetime
import uuid

NATS_SERVER = "nats://nats.oca.lan:4222"
NATS_TOPIC = "telemetry.water.level"

MAX_M3 = 20.0
VOLT_PER_M3 = 0.27

LED_FREQ_HZ = 800000
LED_DMA = 10
LED_BRIGHTNESS = 255
LED_INVERT = False

LED_1_COUNT = 3
LED_1_PIN = 18
LED_1_CHANNEL = 0

LED_2_COUNT = 2
LED_2_PIN = 13
LED_2_CHANNEL = 1

BTN_1_PIN = 24
BTN_2_PIN = 25

water_state = {
    "voltage": 0.0,
    "m3": 0.0,
    "liters": 0,
    "status": "ok"
}

ina = INA219(shunt_ohms=0.1, max_expected_amps=0.4, address=0x40)
ina.configure()

strip1 = PixelStrip(LED_1_COUNT, LED_1_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_1_CHANNEL)
strip2 = PixelStrip(LED_2_COUNT, LED_2_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_2_CHANNEL)
strip1.begin()
strip2.begin()

GPIO.setmode(GPIO.BCM)
GPIO.setup(BTN_1_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(BTN_2_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

def m3_to_rgb(m3):
    if m3 <= 3.75:
        h = 0.0
    elif m3 >= 15.0:
        h = 240.0 / 360.0
    else:
        percentage = (m3 - 3.75) / (15.0 - 3.75)
        h = (percentage * 240.0) / 360.0
        
    r, g, b = colorsys.hsv_to_rgb(h, 1.0, 1.0)
    return int(r * 255), int(g * 255), int(b * 255)

async def sensor_task():
    readings_history = deque(maxlen=10)
    ema_value = None
    alpha = 0.2

    while True:
        try:
            raw_voltage = ina.voltage()
            readings_history.append(raw_voltage)
            
            sorted_readings = sorted(list(readings_history))
            median_voltage = sorted_readings[len(sorted_readings)//2]
            
            if ema_value is None:
                ema_value = median_voltage
            else:
                ema_value = (alpha * median_voltage) + ((1 - alpha) * ema_value)
                
            m3 = ema_value / VOLT_PER_M3
            m3 = max(0.0, min(m3, MAX_M3))
            liters = int(m3 * 1000)
            
            water_state["voltage"] = round(ema_value, 3)
            water_state["m3"] = round(m3, 2)
            water_state["liters"] = liters
            water_state["status"] = "ok"
            
        except Exception as e:
            print(f"Sensor error: {e}")
            water_state["status"] = "sensor_error"
            
        await asyncio.sleep(10)

async def led_task():
    breath_brightness = 0
    breath_direction = 5

    while True:
        r, g, b = m3_to_rgb(water_state["m3"])
        water_color = Color(r, g, b)
        for i in range(strip1.numPixels()):
            strip1.setPixelColor(i, water_color)
        strip1.show()

        if water_state["status"] == "ok":
            status_color = Color(0, 0, breath_brightness)
        else:
            status_color = Color(breath_brightness, 0, 0)
            
        for i in range(strip2.numPixels()):
            strip2.setPixelColor(i, status_color)
        strip2.show()

        breath_brightness += breath_direction
        if breath_brightness >= 255:
            breath_brightness = 255
            breath_direction = -5
        elif breath_brightness <= 50:
            breath_brightness = 50
            breath_direction = 5

        await asyncio.sleep(10)

async def nats_task():
    nc = NATS()
    
    while True:
        try:
            if not nc.is_connected:
                await nc.connect(NATS_SERVER, connect_timeout=2)
                print("Connected to NATS!")
                
            now = datetime.datetime.now()
            ts_array = [now.year, now.month, now.day, now.hour, now.minute, now.second, now.microsecond]
            
            short_id = uuid.uuid4().hex[:6]
            
            payload_dict = {
                "data": {
                    "ts": ts_array,
                    "version": "1.0.0",
                    "measurements": {
                        "voltage": water_state["voltage"],
                        "m3": water_state["m3"],
                        "liters": water_state["liters"],
                        "status": water_state["status"]
                    }
                },
                "meta": {
                    "id": f"water-{short_id}",
                    "sender": "WaterLevel-RPI",
                    "ts": ts_array,
                    "trace_level": 10,
                    "message_type": "",
                    "tags": []
                }
            }
                
            payload = json.dumps(payload_dict).encode('utf-8')
            await nc.publish(NATS_TOPIC, payload)
            
        except Exception as e:
            print(f"NATS error: {e}")
            
        await asyncio.sleep(10)

def handle_button_1(channel):
    print("Button 1 clicked")

def handle_button_2(channel):
    print("Button 2 clicked")

GPIO.add_event_detect(BTN_1_PIN, GPIO.FALLING, callback=handle_button_1, bouncetime=300)
GPIO.add_event_detect(BTN_2_PIN, GPIO.FALLING, callback=handle_button_2, bouncetime=300)

async def main():
    print("Starting water monitoring system...")
    await asyncio.gather(
        sensor_task(),
        led_task(),
        nats_task()
    )

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Shutting down...")
        for i in range(strip1.numPixels()): strip1.setPixelColor(i, Color(0,0,0))
        for i in range(strip2.numPixels()): strip2.setPixelColor(i, Color(0,0,0))
        strip1.show()
        strip2.show()
        GPIO.cleanup()
