from slog import slog
import paho.mqtt.client as mqtt


class MQTT:
    
    def __init__(self, host = '', user = '', password = '', port = '1883', log = None):
        if log == None:
            self.__log = slog('MQTT class', True)
        else:
            self.__log = log
        if host == '':
            self.__log.logMsg('Error in MQTT class: No host url set!',2)
        else:
            self.__host           = host
        self.__port           = port
        self.__user           = user
        self.__password       = password
        
    def __repr__(self):
        return 'MQTT('+self.__log+')'
    
    def connect_mqtt(self):
        self.mqtt = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION1, client_id='enverproxy')
        if (self.__user != None or self.__password != None):
            self.mqtt.username_pw_set(self.__user, self.__password)
        self.mqtt.connect(self.__host, self.__port)
        self.__log.logMsg('Starting mqtt loop', 5)
        self.mqtt.loop_start()
        self.__log.logMsg('mqtt loop started', 5)

    def send_command(self, topic, data):
        # topic is the MQTT topic
        # data: dictionary with the data to send
        try:
            self.__log.logMsg('Sending data to MQTT server: ' + topic, 4)
            self.mqtt.publish(topic, data)
        except OSError as e:
            self.__log.logMsg('Requests error when posting MQTT data: ' + str(e), 2)
