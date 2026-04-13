# Water sensor

## Actual information

**IP ADDRESS:** 192.168.20.66
**LOGIN:** poweruser
**PASSWORD:** standard one

## RPI Configuration
1) Initialize SD Card with **Raspberry Pi Imager**
   - Use RPI Zero W & Raspbian Image 32 Lite 
2) Wait ~5 minutes before trying find your RPI
3) ```sudo apt update && sudo apt upgrade -y```
4) ```sudo apt install pipx i2c-tools python3-dev build-essential -y```
5) ```sudo raspi-config``` ==> Interface Options ==> I2C ==> YES ==> FINISH
6) ```sudo nano /boot/firmware/config.txt``` ==> find ```dtparam=audio=on``` and change to ```dtparam=audio=off```
7) ```pipx install poetry``` (DO NOT USE SUDO)
8) ```pipx ensurepath``` (DO NOT USE SUDO)
9) Go to directory *water-level*
10) Add all files
11) Initialize poetry ```poetry install```
12) Run program with ```sudo $(poetry env info --path)/bin/python main.py```
