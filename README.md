# water_level
Water level sensor based on Arduino UNO and Raspberry Pi 4B in OCA


## Installation

First you need to clone the repository from git.
```bash
git clone https://github.com/araucaria-project/oca_nats_config.git
```
Then go to the project folder and install it.
WARNING the `poetry` package is required for installation.

```bash
cd water_level
poetry install
```
WARNING! Sometimes `poetry` hangs when installing packages, in which case you should run them with the `sudo` option
```bash
sudo poetry install
```

### Automatic update

Attention. The service is configured to run as a `observer`. This means that a user with this name must exist in 
the environment and must be the owner of the project. Therefore, the installation process should be done as `observer`.

To run the auto-update service on linux you need to first complete installation 
(see [installation](#installation) section).

Go to the `/etc/systemd/system/` directory in the project and make symlinks to service scripts.
WARNING `[path-to-project]` is the project path
```bash
cd /etc/systemd/system/
sudo ln -s [path-to-project]/water_level/scripts/water_level.service water_level.service
sudo ln -s [path-to-project]/water_level/scripts/water_level.timer water_level.timer
```
Next go to and make symlink to auto update script:
```bash
cd /usr/bin/
sudo ln -s [path-to-project]/water_level/scripts/update_water_level.sh update_water_level.sh
```

Now start the services.

```bash
sudo systemctl daemon-reload
sudo systemctl enable water_level.timer
sudo systemctl start water_level.timer
```

At the end, you can check status nev service by:

```bash
sudo systemctl status water_level.timer
```
