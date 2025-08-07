# mDNS for Ubuntu MATE

```BASH
sudo apt update
sudo apt install avahi-daemon avahi-utils
sudo systemctl enable avahi-daemon
sudo systemctl start avahi-daemon
systemctl status avahi-daemon
```

## Configure `avahi-daemon`
Put the following in `/etc/avahi/avahi-daemon.conf`
```BASH
[server]
host-name=youreachedthinkcentre
domain-name=local
```
Then restart `avahi-daemon`
```BASH
sudo systemctl restart avahi-daemon
systemctl status avahi-daemon
ping youreachedthinkcentre.local
```
