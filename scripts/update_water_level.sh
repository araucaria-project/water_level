#!/bin/bash
# find and go to project directory
SCRIPT_PATH="${BASH_SOURCE:-$0}"
ABS_SCRIPT_PATH="$(realpath "${SCRIPT_PATH}")"
DIR_PATH="$(dirname "$ABS_SCRIPT_PATH")"
cd $DIR_PATH
cd ..

# run program
sudo poetry run water_level
echo "Water level was sent to NATS"