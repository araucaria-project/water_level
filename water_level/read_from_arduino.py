#!/usr/bin/env python3
import asyncio
import time
import configparser
import serial
from serverish.messenger import Messenger, get_publisher

config = configparser.ConfigParser()  # init configuration rader
config.read('../water_config.ini')  # read config file


async def send2nats(level: int, ts: list):
    # create connection to nats by using async context manager (async witch).
    async with Messenger().context(host=config.get("SERVER-CONNECTION", "host"),
                                   port=config.getint("SERVER-CONNECTION", "port")):
        # getting publisher class
        pub = await get_publisher(config.get("SERVER-CONNECTION", "target_water_stream"))
        # publish message as 'telemetry' type (message_type = telemetry) witch som tags and date. Message  structure
        # is predefined in serverish project, for every types of message is different structure
        await pub.publish(data={'measurements': {"water_level": level}, 'ts': ts},
                          meta={
                              "message_type": "telemetry",  # IMPORTANT type message, one of pre declared types
                              "tags": ["water_level", "first_water_level", "inaccurate_measurement_water"],  # tags
                              'sender': 'Raspberry_unit_water_reader',  # name who send message
                          })
    return True


def main():
    # make sure that arduino is on /dev/ttyACM0 by connecting it and "ls /dev/tty*" and then disconnecting and again "ls /dev/tty*" and check which tty disappear when arduino is disconnected
    serialport = config.get("ARDUINO-CONNECTION", 'serialport')
    ser = None
    try:
        ser = serial.Serial(serialport, 9600, timeout=30)
        if not ser.isOpen():
            ser.open()

        ser.write("0".encode())
        line1 = ser.read(size=18)
        # print(line1)
        ser.write("0".encode())
        line2 = ser.read(size=18)

        ts = [*time.gmtime()]  # read timestamp as list, used to sent to NATS

        # print(line2)
        line = line2.decode('utf-8')

        line1 = line.split('\n')[:-1]
        suma = 1500
        for i, elem in enumerate(line1):
            suma = suma + (1 - int(elem.replace('\r', '', 1))) * 1750
            line1[i] = elem.replace('\r', '', 1)
        asyncio.run(send2nats(suma, ts))  # run asyncio method

    except Exception as e:
        print(e)
    finally:
        if ser is not None and ser.isOpen():
            ser.close()


if __name__ == '__main__':
    main()
