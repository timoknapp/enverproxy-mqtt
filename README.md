# enverproxy-mqtt

This is heavily based on the work of [@MEitelwein](https://github.com/MEitelwein) and forked from [Enverbridge-Proxy](https://gitlab.eitelwein.net/MEitelwein/Enverbridge-Proxy) plus the initial MQTTT additions of [@zivillian](https://github.com/zivillian) (thanks to both of you). This repo simply made this proxy work for both EVB and EVT devices in combiniation with MQTT.

Using this python script, you can decode the traffic between your envertech bridges (EVB) and micro inverters (EVT) and envertecportal.com. All data will be send to an MQTT broker.

## How to use

### Linux machine

Clone this repo on a linux machine at `/opt/enverproxy-mqtt` and configure it as a [systemd unit](enverproxy-mqtt.service). Copy and update the config at [/etc/enverproxy-mqtt.conf](enverproxy-mqtt.conf) to your needs.
Requires `paho-mqtt` and `python-dateutil`.

```bash
# Clone the repo and copy the service file
git clone https://github.com/timoknapp/enverproxy-mqtt.git /opt/enverproxy-mqtt
cp /opt/enverproxy/enverproxy-mqtt.service /etc/systemd/system/enverproxy-mqtt.service
# Update the user in the service file ("username")
sed -i 's/username/yourusername/g' /etc/systemd/system/enverproxy-mqtt.service
# Copy the config file and install the required packages
cp /opt/enverproxy-mqtt/enverproxy-mqtt.conf /etc/enverproxy-mqtt.conf
pip3 install paho-mqtt python-dateutil
# Enable and start the service
systemctl enable enverproxy-mqtt
systemctl start enverproxy-mqtt
```

### Docker container

You can also use the provided [Dockerfile](Dockerfile) to build a container. You can also use the provided [docker-compose.yml](docker-compose.yml) to start the container.

```bash
# Clone the repo and build the container
git clone https://github.com/timoknapp/enverproxy-mqtt.git
docker build -t enverproxy-mqtt .
# Start the container (replace the environment variables with your settings)
docker run \
    --name enverproxy-mqtt \
    -d \
    --restart=unless-stopped \
    -e LISTEN_PORT=1898 \
    -e MQTTUSER=user \
    -e MQTTPASSWORD=password \
    -e MQTTHOST="127.0.0.1" \
    -e MQTTPORT=1883 \
    -e ID2DEVICE="{'123456' : 'bkw_panel_1', '123457' : 'bkw_panel_2'}" \
    -e VERBOSITY=3 \
    -p 1898:1898 -p 10013:1898 -p 14889:1898 \
    enverproxy-mqtt
```

### Configuration

There are two options on how to specify the configuration for the enverproxy. You can either use a config file or environment variables. The config file must be located at `/etc/enverproxy-mqtt.conf`.
You can use environment variables either in the Linux or Docker setup. The enviroment variables will override the settings in the `enverproxy-mqtt.conf` file if used in parallel. The following environment variables are available:

- `BUFFER_SIZE`: The size of the buffer used by the proxy. This determines how much data can be stored in memory at once.
- `DELAY`: The delay between data transmissions. This can be used to control the rate of data flow.
- `LISTEN_PORT`: The port on which the proxy listens for incoming connections.
- `VERBOSITY`: The level of detail in the proxy's log output. Higher values will result in more detailed logs. (Verbosity levels (1-5), 1 = only start/stop, 2 = + status and errors, 3 = + flow control, 4 = + data , 5 = anything)
- `LOG_TYPE`: The type of log output. This could be a file, standard output (`sys.stdout`), etc.
- `LOG_ADDRESS`: The address to which the logs are sent. This could be a file path, a server address, etc.
- `LOG_PORT`: The port to which the logs are sent. This is used if the logs are sent to a server.
- `FORWARD_IP`: The IP address of the forward server. The proxy forwards data to this server.
- `FORWARD_PORT`: The port of the forward server. The proxy forwards data to this port.
- `MQTTUSER`: The username used to authenticate with the MQTT broker.
- `MQTTPASSWORD`: The password used to authenticate with the MQTT broker.
- `MQTTHOST`: The host address of the MQTT broker.
- `MQTTPORT`: The port of the MQTT broker.
- `ID2DEVICE`: A mapping of device IDs to device names. This is used to identify devices in the MQTT messages. E.g. `"{'123456' : 'bkw_panel_1', '123457' : 'bkw_panel_2'}"`

## Nasty details

The EVB202 will connect to the server every second - even if there is no data to transmit. This will blow up your log file if the log level is set to 3 or higher. Every 20 seconds there is a transmission of some unknown data. If the microinverters are online there will be data approximately once every minute.

If the EVB202 is configured to Server Mode `Local`, it will connect to the configured Server IP via TCP on port 1898. If Server Mode is set to `Net` (the default value) it will try to connect to `www.envertecportal.com` via DNS and fallback to `47.91.242.120` (which is an outdated but hardcoded IP of envertecportal.com) via TCP on port `10013`.

Instead of changing the Server Mode, you may also intercept the DNS query (and reply with a local IP) or redirect the TCP connection to your local machine.

There is a proxy mode, but I'm not using it, so this is totally untested.

## I've found a bug

Just open an [issue](https://github.com/timoknapp/enverproxy-mqtt/issues/new) with as many details as possible.

## Helpful links

- [initial FHEM discussion 🇩🇪](https://forum.fhem.de/index.php?topic=61867.0)
- [alternative to SetID 🇬🇧](https://sven.stormbind.net/blog/posts/iot_envertech_enverbridge_evb202/)
- [lengthy discussion about EVB202 🇩🇪](https://www.photovoltaikforum.com/thread/125652-envertech-bridge-evb202-oder-evb201/)
