# enverproxy-mqtt

This is heavily based on the work of [@MEitelwein](https://github.com/MEitelwein) and forked from [Enverbridge-Proxy](https://gitlab.eitelwein.net/MEitelwein/Enverbridge-Proxy) plus the initial MQTTT additions of [@zivillian](https://github.com/zivillian) (thanks to both of you). This repo simply made this proxy work for both EVB and EVT devices in combiniation with MQTT.

Using this python script, you can decode the traffic between your envertech bridges (EVB) and micro inverters (EVT) and envertecportal.com. All data will be send to an MQTT broker.

## How to use

### Receiving side

Clone this repo on a linux machine at `/opt/enverproxy` and configure it as a [systemd unit](enverproxy.service). Copy and update the config at [/etc/enverproxy.conf](enverproxy.conf) to your needs.
Requires `paho-mqtt` and `python-dateutil`. You can install both via `pip3 install paho-mqtt python-dateutil`

## Nasty details

The EVB202 will connect to the server every second - even if there is no data to transmit. This will blow up your log file if the log level is set to 3 or higher. Every 20 seconds there is a transmission of some unknown data. If the microinverters are online there will be data approximately once every minute.

If the EVB202 is configured to Server Mode `Local`, it will connect to the configured Server IP via TCP on port 1898. If Server Mode is set to `Net` (the default value) it will try to connect to www.envertecportal.com via DNS and fallback to 47.91.242.120 (which is an outdated but hardcoded IP of envertecportal.com) via TCP on port 10013.

Instead of changing the Server Mode, you may also intercept the DNS query (and reply with a local IP) or redirect the TCP connection to your local machine.

There is a proxy mode, but I'm not using it, so this is totally untested.

## I've found a bug

Just open an [issue](https://github.com/zivillian/enverproxy/issues/new) with as many details as possible.

## Helpful links

- [initial FHEM discussion 🇩🇪](https://forum.fhem.de/index.php?topic=61867.0)
- [alternative to SetID 🇬🇧](https://sven.stormbind.net/blog/posts/iot_envertech_enverbridge_evb202/)
- [lengthy discussion about EVB202 🇩🇪](https://www.photovoltaikforum.com/thread/125652-envertech-bridge-evb202-oder-evb201/)
