import datetime
import json
from slog import slog
from dateutil import tz

#
# Class to handle communication protocol of Enverbridge
#
class enverbridge:
    # Static control codes
    # Enverbridge EVB starting communication
    COM_START_EVB       = bytearray.fromhex('680030' + '681006')
    # Envertec Converter EVT800 starting communication
    COM_START_EVT       = bytearray.fromhex('680020' + '681006')
    # Portal acknowledging COM_START
    COM_ACK_START       = []
    # ACK type 0
    COM_ACK_START.append( bytearray.fromhex('680030' + '681007') )
    # ACK type 1
    COM_ACK_START.append( bytearray.fromhex('680018' + '681009') )
    # ACK type 2 contains a time stamp and triggers payload
    COM_ACK_START.append( bytearray.fromhex('68001e' + '681070') )
    # ACK type 3 does not trigger sending of payload with EVB300
    COM_ACK_START.append( bytearray.fromhex('680020' + '681027') )
    # Portal sends new MI IDs to configure bridge 
    # Starts with 680024 681009 + Bridge ID + 00000000000000000000 + ???????????????? + MI IDs (8 Byte) + c516
    # Warning: Unknown message from forward server for device 94002953 (38 bytes): 68 00 24 68 10 09 94 00 29 53 00 00 00 00 00 00 00 00 00 00 11 12 79 83 13 81 07 26 30 52 53 65 30 52 53 64 c5 16
    COM_ADD_MI         = bytearray.fromhex('680024' + '681009')
    # Enverbridge sends payload
    COM_PAYLOAD         = []
    # Payload type 0 from EVB201
    COM_PAYLOAD.append(   bytearray.fromhex('6803d6' + '681004') )
    # Payload type 1 from EVB300
    COM_PAYLOAD.append(   bytearray.fromhex('6802dc' + '681072') )
    # Payload type 2 from EVT800
    COM_PAYLOAD.append(   bytearray.fromhex('680056' + '681004'))
    # Portal acknowledges payload
    COM_ACK_PAYLOAD     = bytearray.fromhex('680012' + '681015')
    COM_ACK_PAYLOAD_END = bytearray.fromhex('0000000000008916')

    def __init__(self, mqtt = None, id2device = '', log = None):
        if log == None:
            self.__log = slog('Enverbridge class')
        else:
            self.__log = log
        if mqtt == None:
            self.__log.logMsg('Error in Enverbridge class: No MQTT server instantiated!', 2)
        else:
            self.__mqtt = mqtt
        # Translate between ID of microinverter and MQTT device name
        # Dictionary of inverter id -> MQTT device name
        self.__id2device = id2device
        self.__log.logMsg('Configured microinverter devices: ' + str(id2device), 1)

    def get_bridgeID(self, data):
        if len(data) >= 9:
            return data[6:6+4].hex()
        else:
            self.__log.logMsg('Error: Message to short to extract brdige ID: ' + len(data) + ' bytes', 2)
            return ''

    def hexstr(self, data):
        # return bytearray as hex values with spaces in-between
        if (data is None) or (len(data) == 0):
            return ''
        data  = data.hex()
        reply = data[0:2]
        for i in range(2, len(data), 2):
            reply += ' ' + data[i:i+2]
        return reply

    def decode_time(self, data):
        # There is a time stamp in COM_START_ACK type 2
        # It is year since 1900 plus month, day and time in UTC+8 (China)
        # Hexstring starting at byte 14 - char 28
        #       2        3
        #       8        4
        #   ----------------------
        #       date     time
        #   ----------------------
        #   ... yy mm dd hh mm ss
        #
        if len(data) >= 19:
            # Decoding on hex string, as int() cannot work on bytearray
            data = data.hex()
            # Extract starting at char 30
            p    = 28
            # year starts at 1900
            y    = int(data[p   :p+2 ], 16) + 1900
            m    = int(data[p+2 :p+4 ], 16)
            d    = int(data[p+4 :p+6 ], 16)
            H    = int(data[p+6 :p+8 ], 16)
            M    = int(data[p+8 :p+10], 16)
            S    = int(data[p+10:p+12], 16)
            t = datetime.datetime(year=y, month=m, day=d, hour=H, minute=M, second=S)
            # time is in UTC+8
            t = t.replace(tzinfo=tz.tz.tzoffset('Envertec server time', 60*60*8))
            # return as time in local timezone
            return t.astimezone(tz.tz.tzlocal()).strftime('%d.%m.%Y %H:%M:%S')
        else:
            self.__log.logMsg('Error in decode_time: Message to short to extract date & time: ' + len(data) + ' bytes', 2)
            return ''

    def encode_time(self, time):
        # encode datetime time to bytearray string to generate COM_ACK_START type 2
        # convert time to UTC+8
        time   = time.astimezone(tz.tz.tzoffset('Envertec server time', 60*60*8))
        reply  = '{:0>2x}'.format(time.year - 1900)
        reply += '{:0>2x}'.format(time.month)
        reply += '{:0>2x}'.format(time.day)
        reply += '{:0>2x}'.format(time.hour)
        reply += '{:0>2x}'.format(time.minute)
        reply += '{:0>2x}'.format(time.second)
        return bytearray.fromhex(reply)

    def decode_data(self, data):
        # Decode the 20 bytes of microinverter data (40 chars in hex string)
        #                 1    1    2        2    3    3  3 
        #   1        8    2    6    0        8    2    6  9 
        #   ------------------------------------------------
        #   wrid     ?    dc   pwr  totalkWh temp ac   freq 
        #   ------------------------------------------------
        #   wwwwwwww 2202 dddd pppp kkkkkkkk tttt aaaa ffff
        #
        if len(data) < 20:
            # Data package is shorter than expected
            self.__log.logMsg('Error in decode_data: Data package is too short (' + str(len(data)) + ')', 2)
            d_wr_id     = 0
            d_dez_dc    = 0
            d_dez_power = 0
            d_dez_total = 0
            d_dez_temp  = 0
            d_dez_ac    = 0
            d_dez_freq  = 0
        else:
            self.__log.logMsg('Decoding microinverter data package: ' + self.hexstr(data[0:20]), 5)
            # Decoding on string, as int() cannot work on bytearray
            data        = data.hex()
            d_wr_id     = data[:8]
            d_hex_dc    = data[12:12+4]
            d_hex_power = data[16:16+4]
            d_hex_total = data[20:20+8]
            d_hex_temp  = data[28:28+4]
            d_hex_ac    = data[32:32+4]
            d_hex_freq  = data[36:36+4]
            # Calculation
            d_dez_dc    = '{0:.2f}'.format(int(d_hex_dc, 16) / 512)
            d_dez_power = '{0:.2f}'.format(int(d_hex_power, 16) / 64)
            d_dez_total = '{0:.3f}'.format(int(d_hex_total, 16) / 8192)
            d_dez_temp  = '{0:.2f}'.format(((int(d_hex_temp[0:2], 16) * 256 + int(d_hex_temp[2:4], 16)) / 128) - 40)
            d_dez_ac    = '{0:.2f}'.format(int(d_hex_ac, 16) / 64)
            d_dez_freq  = '{0:.2f}'.format(int(d_hex_freq[0:2], 16) + int(d_hex_freq[2:4], 16) / 256)
        # Return as dictionary
        return { 'wrid' : d_wr_id, 
                 'dc' : d_dez_dc, 
                 'power' : d_dez_power, 
                 'totalkwh' : d_dez_total, 
                 'temp' : d_dez_temp, 
                 'ac' : d_dez_ac, 
                 'freq' : d_dez_freq }

    def submit_data(self, wrdata):
        # Submit wrdata to MQTT server at url, user, password.
        # Can be https as well. Also: if you use another port then 80 or 443 do not forget to add the port number.
        # user and password.
        cmd_count = 0
        for wrdict in wrdata:
            self.__log.logMsg('Submitting data for inverter: ' + str(wrdict['wrid']) + ' to MQTT', 3)
            values = ['wrid', 'ac', 'dc', 'temp', 'power', 'totalkwh', 'freq']
            for value in values:
                if wrdict['wrid'] in self.__id2device:
                    topic = 'enverbridge/' + wrdict['wrid']
                    self.__log.logMsg('MQTT topic: ' + topic, 4)
                    self.__mqtt.send_command(topic, json.dumps(wrdict))
                    cmd_count += 1
                else:
                    self.__log.logMsg('No MQTT device known for inverter ID ' + wrdict['wrid'], 2)
        self.__log.logMsg('Finished sending to MQTT, ' + str(cmd_count) + ' commands sent', 3)

    def process_data(self, data):
        brid         = self.get_bridgeID(data)
        wr           = []
        wr_index     = 0
        wr_index_max = 20
        # Decoding on chars of hex string, not bytearray
        self.__log.logMsg("Processing data from microinverter", 5)
        while True:
            # Payload contains multiple sets of inverter data 
            # starting at 20 bytes (40 char) and each 32 bytes (64 char) long
            # Decode the 20 bytes of microinverter data into a dictionary
            # Position as char in hex string
            #                                                                 1
            #               1        2                    4                   0
            # 0      6      2        0                    0                   4
            # -----------------------------------------------------------------------------------
            # cmd    cmd    bridgeID                      data 1st inverter   data 2nd inverter
            # -----------------------------------------------------------------------------------
            # 6803d6 681004 bbbbbbbb 00000000000000000000 xxxxxxxxx...xxxxxxx xxxxxxxxx...xxxxxxx
            pos1 = 20 + (wr_index * 32)
            if (pos1 + 32) >= len(data):
                # data is too short to continue parsing
                self.__log.logMsg('process_data: Reached end of data package of ' +
                                  str(len(data)) + ' bytes at index ' + 
                                  str(wr_index) + ' / ' + str(pos1) + ' bytes.' +
                                  ' Remaining part of data package: ' + self.hexstr(data[pos1:]), 4)
                break
            inverter         = self.decode_data(data[pos1:pos1+32])
            inverter['brid'] = self.get_bridgeID(data)
            if int(inverter['wrid']) != 0:
                self.__log.logMsg('Decoded data from microinverter with ID ' + str(inverter['wrid']), 3)
                wr.append(inverter)
            wr_index += 1
        if self.__log.get_verbosity() > 3:
            self.__log.logMsg('Finished processing data for ' + str(len(wr)) + ' microinverter: ' + str(wr), 4)
        else:
            self.__log.logMsg('Processed data for ' + str(len(wr)) + ' microinverter', 3)
        self.submit_data(wr)

    def handshake(self, data):
        # There are 2 handshake packages, the first one consists of (hex string)
        #   cmd           bridgeID  ?         ?    ?
        #   680020 681027 bbbbbbbb 0001ea800 c1c0 50700000000000000000000000000004816
        data = bytearray(data)
        # Microinverter session starts with COM_START
        if data[:6] == self.COM_START_EVB:
            # enverbridge expects reply COM_ACK_START type 0
            self.__log.logMsg('Simulating handshake reply type 0', 3)
            return bytearray.fromhex(self.COM_ACK_START[0].hex() + data[6:].hex())
        elif data[:6] == self.COM_START_EVT:
            # microinverter expects reply COM_ACK_START type 2 with timestamp
            reply = bytearray.fromhex(self.COM_ACK_START[2].hex() + data[6:].hex())
            if len(reply) >= 19:
                reply[14:] = self.encode_time(datetime.datetime.now())
            self.__log.logMsg('Simulating handshake reply type 2 with time stamp ' + self.decode_time(reply), 3)
            return reply
        else:
            self.__log.logMsg('Cannot handshake with wrong start sequence ' + self.hexstr(data[:6]), 2)

    def acknowledge(self, data):
        # The acknowledge packet consists of (hex string)
        #   cmd           bridgeID constant
        #   680012 681015 bbbbbbbb 0000000000008916
        # Microinverter payload starts with COM_PAYLOAD
        if data[:6] == self.COM_PAYLOAD:
            return bytearray.fromhex(self.COM_ACK_PAYLOAD.hex() + data[6:10].hex() + self.COM_ACK_PAYLOAD_END.hex())
        elif data[:6] == self.COM_START_EVB or data[:6] == self.COM_START_EVT:
            self.__log.logMsg('Cannot acknowledge to payload with wrong start sequence ' + self.hexstr(data[:6]), 2)
        else:
            self.__log.logMsg('Unknown packet received: ' + self.hexstr(data), 2)

    def recv_from_device(self, data, simulate):
        reply = ''
        if data[:6] == self.COM_START_EVB:
            # EVB device initiates connection
            self.__log.logMsg('Handshake request from EVB device ' + self.get_bridgeID(data) + ' (' + str(len(data)) + ' bytes): ' + self.hexstr(data), 3)
            # There is some data already in the COM_START message
            inverter         = self.decode_data(data[20:])
            inverter['brid'] = self.get_bridgeID(data)
            if int(inverter['wrid']) != 0:
                self.__log.logMsg('Embedded device data: ' + str(inverter), 4)
            if simulate: 
                # This part is simulating handshake with forward server
                # if no connection can be established with forward server
                reply = self.handshake(data)
                self.__log.logMsg('No forward server, simulating handshake reply: ' + self.hexstr(reply), 4)
            return reply
        elif data[:6] == self.COM_START_EVT:
            # EVT device initiates connection
            self.__log.logMsg('Handshake request from EVT device ' + self.get_bridgeID(data) + ' (' + str(len(data)) + ' bytes): ' + self.hexstr(data), 3)
            if simulate: 
                # This part is simulating handshake with forward server
                # if no connection can be established with forward server
                reply = self.handshake(data)
                self.__log.logMsg('No forward server, simulating handshake reply: ' + self.hexstr(reply), 4)
            return reply
        else:
            for i in range(0, len(self.COM_PAYLOAD)):
                if data[:6] == self.COM_PAYLOAD[i]:
                    # payload from device
                    self.__log.logMsg('Payload type ' + str(i) + ' from device ' + self.get_bridgeID(data) + ' (' + str(len(data)) + ' bytes): ' + self.hexstr(data), 3)
                    self.process_data(data)
            if simulate:
                # simulate acknowledgement
                reply = self.acknowledge(data)
                self.__log.logMsg('No forward server, simulating acknowledgement: ' + self.hexstr(reply), 5)
            return reply
        self.__log.logMsg('Warning: Unknown message from proxy client ' + self.get_bridgeID(data) + ' (' + str(len(data)) + ' bytes): ' + self.hexstr(data), 2)
        return reply

    def recv_from_forward(self, data):
        reply = ''
        # Data received on one of the forwarding ports
        # check for COM_ACK_START messages
        for i in range(0, len(self.COM_ACK_START)):
            if data[:6] == self.COM_ACK_START[i]:
                msg = 'Handshake reply type ' + str(i) + ' for device ' + self.get_bridgeID(data) + ' from forward server'
                if i == 2:
                    # type 2 contains a time stamp
                    msg += ' with time stamp ' + self.decode_time(data)
                msg += ' (' + str(len(data)) + ' bytes): ' + self.hexstr(data)
                self.__log.logMsg(msg, 3)
                return reply
        if data[:6] == self.COM_ACK_PAYLOAD:
            # Usually rececveid after forward server processed payload
            self.__log.logMsg('Payload acknowledgement for device ' + self.get_bridgeID(data) + ' from forward server (' + str(len(data)) + ' bytes): ' + self.hexstr(data), 3)
            return reply
        if data[:6] == self.COM_ADD_MI:
            # Portal sends new MI IDs to be added
            self.__log.logMsg('New MI IDs to be added to device ' + self.get_bridgeID(data) + ' (' + str(len(data)) + ' bytes): ' + self.hexstr(data), 2)
            return reply
        # received an unknown reply from forward server
        self.__log.logMsg('Warning: Unknown message from forward server for device ' + self.get_bridgeID(data) + ' (' + str(len(data)) + ' bytes): ' + self.hexstr(data), 2)
        return reply