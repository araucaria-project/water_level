#!/usr/bin/env python3
import asyncio
import serial
from serverish.connection_nats import ConnectionNATS

# make sure that arduino is on /dev/ttyACM0 by connecting it and "ls /dev/tty*" and then disconnecting and again "ls /dev/tty*" and check which tty disappear when arduino is disconnected
serialport = '/dev/ttyACM0'


async def send2nats(level: int):
    cnc = ConnectionNATS(port=4222, host="nats.oca.lan")
    await cnc.connect()
    nc = cnc.nc
    js = nc.jetstream()
    try:
        await js.publish("telemetry.weather.temperature", f"{level}".encode())
    finally:
        await nc.close()
    return 1


def main():
    global serialport
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
        # print(line2)
        line = line2.decode('utf-8')

        line1 = line.split('\n')[:-1]
        suma = 1500
        for i, elem in enumerate(line1):
            suma = suma + (1 - int(elem.replace('\r', '', 1))) * 1750
            line1[i] = elem.replace('\r', '', 1)
        asyncio.run(send2nats(suma))
        # print(line1)
        print(suma)

    except Exception as e:
        pass
    finally:
        if ser is not None and ser.isOpen():
            ser.close()


if __name__ == '__main__':
    main()
