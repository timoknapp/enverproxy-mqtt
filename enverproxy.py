#!/usr/bin/python3
# This is a simple port-forward / proxy for EnvertecBridge

import socket
import select
import time
import sys
import os
import errno
import configparser
import ast
import syslog
import signal
from slog import slog
from MQTT import MQTT
from enverbridge import enverbridge

config = configparser.ConfigParser()
config['internal']              = {}
config['internal']['conf_file'] = '/etc/enverproxy-mqtt.conf'
config['internal']['section']   = 'enverproxy'
config['internal']['version']   = '3.1'
config['internal']['keys']      = "['buffer_size', 'delay', 'listen_port', 'verbosity', 'log_type', 'log_address', 'log_port', 'forward_IP', 'forward_port', 'mqttuser', 'mqttpassword', 'mqtthost', 'mqttport', 'id2device']"

#
# Class to handle receiving server
#
class Forward:
    def __init__(self, log = None):
        if log == None:
            self.__log = slog('Forward class')
        else:
            self.__log = log    
        self.forward = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    def start(self, host, port):
        try:
            self.forward.connect((host, port))
        except OSError as e:
            self.__log.logMsg('Forward server produced error: ' + str(e), 2)
            return False
        self.__log.logMsg('Connected to Forward server: ' + str(host) + ' on port: ' + str(port), 3)
        # return the socket connection to the forward server
        return self.forward


#
# Class of the proxy server
#
class TheServer:
    # static input_list contains list of connections of socket class
    input_list       = []
    # static channel is a dictionary with socket to socket connections
    channel          = {}
    # static simulate_forward is a dictionary flaggin whether a forward is simulated
    simulate_forward = {}

    def __init__(self, host, port, forward_to, delay = 0.0001, buffer_size = 4096, log = None):
        if log == None:
            self.__log = slog('TheServer class')
        else:
            self.__log = log
        self.__delay           = delay
        self.__buffer_size     = buffer_size
        self.__forward_to      = forward_to
        self.__port            = port
        self.__host            = host
        self.__device          = None
        self.server            = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((host, port))
        self.server.listen(200)

    def set_device(self, device):
        # Set the device to handle communications protocol
        self.__device = device

    def is_client(self, sock):
        # check whether the connection is a client or a forward server
        if sock.getsockname()[1] == self.__port:
            return True
        else:
            return False

    def is_simforward(self, sock):
        # check whether the proxy peer is a simulated forward server
        return self.simulate_forward[sock]

    def connect_forward(self, sock):
        # try to establish a connection with the forward server
        if self.is_client(sock):
            self.simulate_forward[sock] = True
            forward = Forward(self.__log).start(self.__forward_to[0], self.__forward_to[1])
            self.__log.logMsg('connect_forward: Forward.start returned: ' + str(forward), 5)
            if forward:
                self.input_list.append(forward)
                self.simulate_forward[sock]    = False
                self.simulate_forward[forward] = False
                self.channel[sock]             = forward
                self.channel[forward]          = sock
                self.__log.logMsg('connect_forward: New connection list: ' + str(self.input_list), 5)
                self.__log.logMsg('connect_forward: New channel dictionary: ' + str(self.channel), 5)
                self.__log.logMsg('connect_forward: New simulated forwarding dictionary: ' + str(self.simulate_forward), 5)
                return True
            else:
                self.__log.logMsg('connect_forward: Could not establish connection with forward server, will simulate forwarding of messages.', 3)
        else:
            self.__log.logMsg('connect_forward Error: Socket ' + str(sock) + ' is not a client!', 2)
        # At this point sock is either not a client or forward server did not respond
        return False

    def main_loop(self):
        self.input_list.append(self.server)
        while True:
            self.__log.logMsg('Entering main loop', 5)
            time.sleep(self.__delay)
            ss = select.select
            # Wait for incoming connections or data
            # inputready, outputready and exceptready return lists of socket connections
            inputready, outputready, exceptready = ss(self.input_list, [], [])
            self.__log.logMsg('main_loop: Input received: ' + str(inputready), 4)
            # Process new incoming data
            for sock in inputready:
                if sock == self.server:
                    # sock in inputready points to the proxy server itself, e.g.
                    # <socket.socket fd=4, family=AddressFamily.AF_INET, type=SocketKind.SOCK_STREAM, proto=0, laddr=('0.0.0.0', 10013)>
                    # meaning that the proxy has a new connection request.
                    self.on_accept()
                    break
                # sock points to an existing socket connection, e.g.
                # <socket.socket fd=6, family=AddressFamily.AF_INET, type=SocketKind.SOCK_STREAM, proto=0, laddr=('172.80.1.2', 10013), raddr=('192.168.123.55', 49216)>
                # Test if data comes from client and forward server is being simulated
                if (self.is_client(sock)) and (self.is_simforward(sock)):
                    # forward server is being simulated
                    # try again to connect to forward server
                    self.__log.logMsg('main_loop: Simulating so far, trying to connect to forward server', 3)
                    self.connect_forward(sock)
                # get the data from the socket connection
                try:
                    data = sock.recv(self.__buffer_size)
                except OSError as e:
                    self.__log.logMsg('main_loop: Socket error on input ' + str(sock) + ': ' + str(e), 2)
                    time.sleep(1) 
                    if e.errno in (errno.ENOTCONN, errno.ECONNRESET, errno.EBADF):
                        # Connection was closed abnormally or file descriptor is bad
                        self.on_close(sock)
                else:
                    if (data is None) or (len(data)) == 0:
                        # Client closed the connection
                        self.__log.logMsg('main_loop: No data received, probably peer closed the connection', 2)
                        self.on_close(sock)
                        break
                    else:
                        self.__log.logMsg('main_loop: ' + str(len(data)) + ' bytes received from ' + str(sock.getpeername()), 4)
                        self.on_recv(sock, data)

    def on_accept(self):
        self.__log.logMsg('Entering on_accept', 5)
        # accept the incoming client's connection request
        clientsock, clientaddr = self.server.accept()
        self.__log.logMsg('on_accept: ' + str(clientaddr) + ' has connected', 2)
        self.input_list.append(clientsock)
        # proxy client connected, establish a connection to the forward server
        if not self.connect_forward(clientsock):
            self.__log.logMsg('on_accept: New connection list: ' + str(self.input_list), 5)
            self.__log.logMsg('on_accept: New channel dictionary: ' + str(self.channel), 5)
            self.__log.logMsg('on_accept: New simulated forwarding dictionary: ' + str(self.simulate_forward), 5)
        self.__log.logMsg('Leaving on_accept', 5)

    def on_close(self, sock):
        # Close the client connection sock
        self.__log.logMsg('Entering on_close with sock: ' + str(sock), 5)
        self.__log.logMsg('on_close: Connection list: ' + str(self.input_list), 5)
        self.__log.logMsg('on_close: Channel dictionary: ' + str(self.channel), 5)
        self.__log.logMsg('on_close: Simulated forwarding dictionary: ' + str(self.simulate_forward), 5)
        if sock == self.input_list[0]:
            # First connection cannot be closed: proxy listening on its port
            self.__log.logMsg('on_close: Server listening port will not be closed', 4)
        else:
            # if sock is a client, close forward first
            if self.is_client(sock):
                if not self.is_simforward(sock):
                    # not simulating forward, so remove forward server
                    peer = self.channel[sock]
                    self.__log.logMsg("on_close: Closing forward server's socket: " + str(peer), 3)
                    del self.channel[peer]
                    del self.simulate_forward[peer]
                    if peer in self.input_list:
                        self.input_list.remove(peer)
                    # close the connection with peer
                    try:
                        peer.close()
                    except OSError as e:
                        self.__log.logMsg('on_close: Socket error with forward server: ' + str(peer) + ' - ' + str(e), 2)
            else:
                # As sock is a forwarding server, set its client to simulate_forward 
                self.simulate_forward[self.channel[sock]] = True
            # remove objects of sock, which is either client or forward server
            self.__log.logMsg('on_close: Closing sock socket: ' + str(sock), 3)            
            if sock in self.channel:
                del self.channel[sock]
            if sock in self.simulate_forward:
                del self.simulate_forward[sock]
            if sock in self.input_list:
                self.input_list.remove(sock)
            # close socket sock
            try:
                # close the connection with client
                sock.close()
            except OSError as e:
                # Connection was most likely already closed
                self.__log.logMsg('on_close: Socket error with sock: ' + str(sock) + ' - ' + str(e), 2)
        self.__log.logMsg('on_close: Remaining connection list: ' + str(self.input_list), 5)
        self.__log.logMsg('on_close: Remaining channel dictionary: ' + str(self.channel), 5)
        self.__log.logMsg('on_close: Remaining simulated forwarding dictionary: ' + str(self.simulate_forward), 5)
        self.__log.logMsg('Leaving on_close', 5)
        
    def close_all(self):
        # Close all connections
        self.__log.logMsg('Entering close_all', 5)
        if len(self.input_list) > 1:
            # First connection cannot be closed: proxy listening on its port
            self.__log.logMsg('close_all: Closing all connections: ' + str(self.input_list[1:]), 3)
            for con in self.input_list[1:]:
                # test, as connection might have been closed already
                # by previous call to on_close
                if con in self.input_list:
                    self.__log.logMsg('close_all: Remaining connection list: ' + str(self.input_list[1:]),5)
                    self.on_close(con)
        self.__log.logMsg('Leaving close_all', 5)

    def on_recv(self, sock, data):
        # Data is accessible as a bytearray in data
        self.__log.logMsg('Entering on_recv', 5)
        reply = ''
        self.__log.logMsg(str(len(data)) + ' bytes of data in on_recv as hex: ' + str(data.hex()), 5) 
        if self.is_client(sock):
            # receving data from a proxy client
            self.__log.logMsg('on_recv: Client data received by proxy on port: ' + str(self.__port), 4)
            # Analyse incoming data
            if self.__device == None:
                self.__log.logMsg('on_recv Warning: No device set to handle communication protocol! Forwarding message to forward server (' + str(len(self.data)) + ' bytes): ' + str(self.data.hex()),2)
            else:
                # Call device object to interpret data
                reply = self.__device.recv_from_device(data = data, simulate = self.is_simforward(sock))
        else:
            # receiving data from forward server
            if self.__device == None:
                self.__log.logMsg('on_recv Warning: No device set to handle communication protocol! Forwarding message to device (' + str(len(self.data)) + ' bytes): ' + str(self.data.hex()),2)
            else:
                # Call device object to interpret data
                reply = self.__device.recv_from_forward(data = data)
        # Forward data to peer
        if self.is_simforward(sock):
            # directly reply with simulated data to sock
            if not reply is None and reply != '':
                try:
                    sock.send(reply)
                except OSError as e:
                    self.__log.logMsg('on_recv: Socket error when sending simulated reply to client ' + str(sock) + ': ' + str(e), 2)
                else:
                    self.__log.logMsg('on_recv: Simulated reply sent to: ' + str(sock), 4)
            else:
                self.__log.logMsg('on_recv Warning: Simulated reply is empty, nothing sent to: ' + str(sock), 2)
        else:
            # forward data to proxy peer of sock
            peer = self.channel[sock]
            try:
                peer.send(data)
            except OSError as e:
                self.__log.logMsg('on_recv: Socket error when sending to proxy peer ' + str(peer) + ': ' + str(e), 2)
                time.sleep(1) 
                if e.errno in (errno.ENOTCONN, errno.ECONNRESET, errno.EBADF):
                    # Connection was closed abnormally or file descriptor is bad
                    # Proxy peer is dead, so if sock is a client, move to simulating the forward server
                    self.__log.logMsg('on_recv: Closing socket of proxy peer ' + str(peer), 3)
                    # close the connection with peer
                    try:
                        peer.close()
                    except OSError as e:
                        self.__log.logMsg('on_recv: Socket error when closing proxy peer ' + str(peer) + ': ' + str(e), 2)
                    self.simulate_forward[sock] = True
                    del self.simulate_forward[peer]
                    self.input_list.remove(peer)
                    del self.channel[sock]
                    del self.channel[peer]
                    self.__log.logMsg('on_recv: Remaining connection list: ' + str(self.input_list), 5)
                    self.__log.logMsg('on_recv: Remaining channel dictionary: ' + str(self.channel), 5)
                    self.__log.logMsg('on_recv: Remaining simulated forwarding dictionary: ' + str(self.simulate_forward), 5)
            else:
                self.__log.logMsg('on_recv: Data forwarded to: ' + str(peer), 4)
        self.__log.logMsg('Leaving on_recv', 5)

class Signal_handler:
    def __init__(self, server, log = None):
        if log == None:
            self.__log = slog('Signal_handler class')
        else:
            self.__log = log
        self.__server = server
            
    def sigterm_handler(self, signal, frame):
        self.__log.logMsg('Received SIGTERM, closing connections', 2)
        self.__server.close_all()
        self.__log.logMsg('Stopping server', 1)
        sys.exit(0)

# MAIN
if __name__ == '__main__':
    # Initial verbositiy level is always 2
    # Start logging to std.out by default and until config is read 
    log = slog('Envertec Proxy', verbosity = 2, log_type='sys.stdout')
    # Get configuration data
    if os.path.isfile(config['internal']['conf_file']):
       config.read(config['internal']['conf_file'])
       section = config['internal']['section']
       if section not in config:
           log.logMsg('Section ' + section + ' is missing in config file ' + config['internal']['conf_file'], 2)
           log.logMsg('Stopping server', 1)
           sys.exit(1)
       for k in ast.literal_eval(config['internal']['keys']):
           if k not in config[section]:
               log.logMsg('Config variable "' + k + '" is missing in config file ' + config['internal']['conf_file'], 2)
               log.logMsg('Stopping server', 1)
               sys.exit(1)
    else:
        log.logMsg('Configuration file ' + config['internal']['conf_file'] + ' not found', 2)
        log.logMsg('Stopping server', 1)
        sys.exit(1)
    # Process configuration data
    buffer_size = int(os.getenv('BUFFER_SIZE', config.get('enverproxy', 'buffer_size')))
    delay = float(os.getenv('DELAY', config.get('enverproxy', 'delay')))
    port = int(os.getenv('LISTEN_PORT', config.get('enverproxy', 'listen_port')))
    verbosity = int(os.getenv('VERBOSITY', config.get('enverproxy', 'verbosity')))
    log_type = os.getenv('LOG_TYPE', config.get('enverproxy', 'log_type'))
    log_address = os.getenv('LOG_ADDRESS', config.get('enverproxy', 'log_address'))
    log_port = int(os.getenv('LOG_PORT', config.get('enverproxy', 'log_port')))
    # Forward server configuration
    forward_IP = os.getenv('FORWARD_IP', config.get('enverproxy', 'forward_IP'))
    forward_port = int(os.getenv('FORWARD_PORT', config.get('enverproxy', 'forward_port')))
    forward_to  = (forward_IP, forward_port)
    # MQTT configuration
    mqttuser = os.getenv('MQTTUSER', config.get('enverproxy', 'mqttuser'))
    mqttpassword = os.getenv('MQTTPASSWORD', config.get('enverproxy', 'mqttpassword'))
    mqtthost = os.getenv('MQTTHOST', config.get('enverproxy', 'mqtthost'))
    mqttport = int(os.getenv('MQTTPORT', config.get('enverproxy', 'mqttport')))
    id2device = ast.literal_eval(os.getenv('ID2DEVICE', config.get('enverproxy', 'ID2device')))
    # Instantiate the logging object
    log         = slog('Envertec Proxy', verbosity, log_type, log_address, log_port)
    log.logMsg('Starting server (v' + config['internal']['version'] + ')', 1)
    log.logMsg('Log verbosity: ' + str(verbosity), 1)
    # Instantiate the proxy server
    server      = TheServer(host = '', port = port, forward_to = forward_to, delay = delay, buffer_size = buffer_size, log = log)
    # Instantiate the connection to MQTT and the Enverbridge protocol handling
    mqtt        = MQTT(host = mqtthost, user = mqttuser, password = mqttpassword, port = mqttport, log = log)
    mqtt.connect_mqtt()
    device      = enverbridge(mqtt = mqtt, id2device = id2device, log = log)
    server.set_device(device)
    # Catch SIGTERM signals    
    signal.signal(signal.SIGTERM, Signal_handler(server, log).sigterm_handler)
    # Start proxy server
    try:
        server.main_loop()
    except KeyboardInterrupt:
        log.logMsg('Ctrl-C received, closing connections', 2)
        server.close_all()
        log.logMsg('Stopping server', 1)
        sys.exit(0)
