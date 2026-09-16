#!/usr/bin/env python3
"""Water level monitoring: INA219 -> WS281x LEDs + NATS telemetry."""

import asyncio
import colorsys
import datetime
import json
import logging
import signal
import statistics
import uuid
from collections import deque

import RPi.GPIO as GPIO
from ina219 import INA219
from nats.aio.client import Client as NATS
from rpi_ws281x import Color, PixelStrip

# --------------------------------------------------------------------------- #
# CONFIG
# --------------------------------------------------------------------------- #

NATS_SERVER = "nats://nats.oca.lan:4222"
NATS_TOPIC = "telemetry.water.level"

# Loop intervals [seconds]
NATS_PUBLISH_INTERVAL = 10.0
SENSOR_INTERVAL = 2.0
LED_INTERVAL = 0.03

MAX_M3 = 20.0
VOLT_PER_M3 = 0.27

# Readings outside this range are reported as "out_of_range" instead of being
# silently clamped. With a live-zero sensor (e.g. 0.5-4.5 V) raise VOLTAGE_MIN
# to ~0.4 so a broken wire is detected; at 0.0 it looks like an empty tank.
VOLTAGE_MIN = 0.0
VOLTAGE_MAX = MAX_M3 * VOLT_PER_M3 * 1.05

STALE_AFTER = SENSOR_INTERVAL * 5

MEDIAN_WINDOW = 9  # odd -> true median, no averaging
EMA_ALPHA = 0.2

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

COLOR_LOW_M3 = MAX_M3 * 0.1875   # below -> red
COLOR_HIGH_M3 = MAX_M3 * 0.75    # above -> blue

BTN_1_PIN = 24
BTN_2_PIN = 25
BTN_BOUNCETIME = 300

LOG_LEVEL = logging.INFO

# --------------------------------------------------------------------------- #

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s %(levelname)-8s %(message)s",
)
log = logging.getLogger("water-level")

water_state = {
    "voltage": None,
    "m3": None,
    "liters": None,
    "status": "init",     # init | ok | sensor_error | out_of_range | stale
    "last_ok_ts": None,   # monotonic time of last successful reading
}

shutdown_event = None  # created inside main(), needs a running loop

# --------------------------------------------------------------------------- #
# Hardware
# --------------------------------------------------------------------------- #

ina = INA219(shunt_ohms=0.1, max_expected_amps=0.4, address=0x40)
ina.configure()

strip1 = PixelStrip(LED_1_COUNT, LED_1_PIN, LED_FREQ_HZ, LED_DMA,
                    LED_INVERT, LED_BRIGHTNESS, LED_1_CHANNEL)
strip2 = PixelStrip(LED_2_COUNT, LED_2_PIN, LED_FREQ_HZ, LED_DMA,
                    LED_INVERT, LED_BRIGHTNESS, LED_2_CHANNEL)
strip1.begin()
strip2.begin()

GPIO.setmode(GPIO.BCM)
GPIO.setup(BTN_1_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(BTN_2_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)


def clear_strips():
    for strip in (strip1, strip2):
        try:
            for i in range(strip.numPixels()):
                strip.setPixelColor(i, Color(0, 0, 0))
            strip.show()
        except Exception:
            log.exception("Failed to clear LED strip")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def m3_to_rgb(m3):
    """Red (empty) -> blue (full). None -> dim grey."""
    if m3 is None:
        return 40, 40, 40

    if m3 <= COLOR_LOW_M3:
        h = 0.0
    elif m3 >= COLOR_HIGH_M3:
        h = 240.0 / 360.0
    else:
        pct = (m3 - COLOR_LOW_M3) / (COLOR_HIGH_M3 - COLOR_LOW_M3)
        h = (pct * 240.0) / 360.0

    r, g, b = colorsys.hsv_to_rgb(h, 1.0, 1.0)
    return int(r * 255), int(g * 255), int(b * 255)


def utc_ts_array():
    now = datetime.datetime.now(datetime.timezone.utc)
    return [now.year, now.month, now.day, now.hour,
            now.minute, now.second, now.microsecond]


def data_age_s():
    last = water_state["last_ok_ts"]
    if last is None:
        return None
    return round(asyncio.get_running_loop().time() - last, 1)


async def sleep_or_shutdown(seconds):
    """Sleep, but wake up immediately on shutdown."""
    try:
        await asyncio.wait_for(shutdown_event.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


# --------------------------------------------------------------------------- #
# Tasks
# --------------------------------------------------------------------------- #


async def sensor_task():
    readings = deque(maxlen=MEDIAN_WINDOW)
    ema = None
    sensor_failures = 0
    loop = asyncio.get_running_loop()

    while not shutdown_event.is_set():
        try:
            # I2C blocks -> off the event loop
            raw_voltage = await asyncio.to_thread(ina.voltage)

            if not (VOLTAGE_MIN <= raw_voltage <= VOLTAGE_MAX):
                sensor_failures += 1
                if sensor_failures == 1 or sensor_failures % 10 == 0:
                    log.warning("Voltage out of range: %.3f V "
                                "(allowed %.2f-%.2f V), failure #%d",
                                raw_voltage, VOLTAGE_MIN, VOLTAGE_MAX,
                                sensor_failures)
                water_state["voltage"] = round(raw_voltage, 3)
                water_state["status"] = "out_of_range"
            else:
                if sensor_failures:
                    log.info("Sensor recovered after %d failures",
                             sensor_failures)
                    sensor_failures = 0

                readings.append(raw_voltage)
                median_voltage = statistics.median(readings)

                if ema is None:
                    ema = median_voltage
                else:
                    ema = EMA_ALPHA * median_voltage + (1.0 - EMA_ALPHA) * ema

                m3 = min(max(ema / VOLT_PER_M3, 0.0), MAX_M3)

                water_state["voltage"] = round(ema, 3)
                water_state["m3"] = round(m3, 2)
                water_state["liters"] = int(m3 * 1000)
                water_state["status"] = "ok"
                water_state["last_ok_ts"] = loop.time()

        except Exception as e:
            sensor_failures += 1
            # Full traceback once, then one line, to keep the journal readable
            if sensor_failures == 1:
                log.exception("Sensor read failed")
            elif sensor_failures % 10 == 0:
                log.warning("Sensor read failed (#%d): %s", sensor_failures, e)
            water_state["status"] = "sensor_error"

        age = data_age_s()
        if water_state["status"] == "ok" and age is not None and age > STALE_AFTER:
            water_state["status"] = "stale"

        await sleep_or_shutdown(SENSOR_INTERVAL)


async def led_task():
    brightness = 50
    direction = 5

    while not shutdown_event.is_set():
        try:
            r, g, b = m3_to_rgb(water_state["m3"])
            water_color = Color(r, g, b)
            for i in range(strip1.numPixels()):
                strip1.setPixelColor(i, water_color)
            strip1.show()

            status = water_state["status"]
            if status == "ok":
                status_color = Color(0, 0, brightness)
            elif status == "init":
                status_color = Color(brightness, brightness, 0)
            else:
                status_color = Color(brightness, 0, 0)

            for i in range(strip2.numPixels()):
                strip2.setPixelColor(i, status_color)
            strip2.show()

            brightness += direction
            if brightness >= 255:
                brightness, direction = 255, -5
            elif brightness <= 50:
                brightness, direction = 50, 5

        except Exception:
            # LED failure must not stop measurements or telemetry
            log.exception("LED update failed")
            await sleep_or_shutdown(1.0)
            continue

        await asyncio.sleep(LED_INTERVAL)


async def nats_task():
    nc = NATS()

    async def on_error(e):
        log.error("NATS: %s", e)

    async def on_disconnect():
        log.warning("NATS: disconnected")

    async def on_reconnect():
        log.info("NATS: reconnected")

    async def on_close():
        log.info("NATS: connection closed")

    connect_failures = 0

    while not shutdown_event.is_set():
        # nats-py reconnects on its own after a drop, but not after a failed
        # initial connect() - hence retrying here.
        if (not nc.is_connected
                and not nc.is_reconnecting
                and not getattr(nc, "is_connecting", False)):
            try:
                await nc.connect(
                    NATS_SERVER,
                    connect_timeout=2,
                    max_reconnect_attempts=-1,
                    reconnect_time_wait=2,
                    error_cb=on_error,
                    disconnected_cb=on_disconnect,
                    reconnected_cb=on_reconnect,
                    closed_cb=on_close,
                )
                connect_failures = 0
                log.info("Connected to NATS: %s", NATS_SERVER)
            except Exception as e:
                connect_failures += 1
                if connect_failures == 1 or connect_failures % 10 == 0:
                    log.warning("NATS unreachable (%s), attempt %d: %s",
                                NATS_SERVER, connect_failures, e)

        try:
            if nc.is_connected:
                ts_array = utc_ts_array()
                payload_dict = {
                    "data": {
                        "ts": ts_array,
                        "version": "1.0.0",
                        "measurements": {
                            "voltage": water_state["voltage"],
                            "m3": water_state["m3"],
                            "liters": water_state["liters"],
                            "status": water_state["status"],
                            "age_s": data_age_s(),
                        },
                    },
                    "meta": {
                        "id": "water-" + uuid.uuid4().hex[:6],
                        "sender": "WaterLevel-RPI",
                        "ts": ts_array,
                        "trace_level": 10,
                        "message_type": "",
                        "tags": [],
                    },
                }

                payload = json.dumps(payload_dict).encode("utf-8")
                await nc.publish(NATS_TOPIC, payload)
                # publish() only buffers; without flush() data can be lost
                await nc.flush(timeout=2)
                log.debug("Published: %s", payload_dict["data"]["measurements"])
            elif connect_failures <= 1:
                log.warning("NATS unavailable - skipping publish")

        except Exception:
            log.exception("NATS publish failed")

        await sleep_or_shutdown(NATS_PUBLISH_INTERVAL)

    try:
        if nc.is_connected:
            await nc.drain()
    except Exception:
        log.exception("NATS drain failed")


# --------------------------------------------------------------------------- #
# Buttons - callbacks arrive on a GPIO library thread
# --------------------------------------------------------------------------- #


def make_button_handler(loop, name):
    def handler(channel):
        try:
            loop.call_soon_threadsafe(log.info, "%s pressed (GPIO %s)",
                                      name, channel)
        except RuntimeError:
            pass  # loop already closed during shutdown
    return handler


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


async def main():
    global shutdown_event
    shutdown_event = asyncio.Event()

    log.info("Starting water monitoring system "
             "(sensor %.1fs / NATS %.1fs / LED %.0fms)",
             SENSOR_INTERVAL, NATS_PUBLISH_INTERVAL, LED_INTERVAL * 1000)

    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown_event.set)

    GPIO.add_event_detect(BTN_1_PIN, GPIO.FALLING,
                          callback=make_button_handler(loop, "Button 1"),
                          bouncetime=BTN_BOUNCETIME)
    GPIO.add_event_detect(BTN_2_PIN, GPIO.FALLING,
                          callback=make_button_handler(loop, "Button 2"),
                          bouncetime=BTN_BOUNCETIME)

    await asyncio.gather(sensor_task(), led_task(), nats_task())
    log.info("Tasks stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        clear_strips()
        GPIO.cleanup()
        log.info("Shutdown complete.")
