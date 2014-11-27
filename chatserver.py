import logging
from struct import pack, unpack

from twisted.internet.protocol import Protocol, ReconnectingClientFactory

from twisted.internet.protocol import Factory
from twisted.internet import reactor
import struct

from event import Event

# Packet types
PK_LOGIN=0
PK_WELCOME=1
PK_PINGSERVER=2
PK_PINGCLIENT=3
PK_MESSAGE=4
PK_LIST=5
PK_JOIN=6
PK_LEAVE=7
PK_WHISPER=9

# Protocol
class ChatServer(Protocol):
    # Sending packets
    def send_packet(self, number, params):
        logging.debug("Sending packet nr %s" % number)
        data = pack('b', number)
        for val in params:
            if isinstance(val, int):
                data += self.pack_int(val)
            else:
                data += self.pack_string(val)
        self.transport.write(data)
                
    def pack_byte(self, value):
        return chr(value)
    
    def pack_string(self, value):	
        return value + chr(0)
    
    def pack_int(self, value):
        return pack('i', value)
        
    # Receiving data
    def dataReceived(self, data):    	
        while(len(data) > 0):
            (number, data) = self.get_byte(data)
            logging.debug("Received packet nr %s" % number)    	    
        
            if number == PK_WELCOME:
                # no data
                self.welcome()
            elif number == PK_PINGSERVER:
                # no data
                self.ping()
            elif number == PK_LIST:
                # not supported at the moment
                data = ""
            elif number == PK_JOIN:
                # <name><id>
                (name, data) = self.get_string(data)
                (id, data) = self.get_int(data)
                self.join(name, id)
            elif number == PK_LEAVE:
                # <id>
                (id, data) = self.get_int(data)	            
                self.leave(id)
            elif number == PK_MESSAGE:
                # <id><message>
                (id, data) = self.get_int(data)
                (message, data) = self.get_string(data)
                self.message(id, message)
            elif number == PK_WHISPER:
                # <nick><message>
                (nick, data) = self.get_string(data)
                (message, data) = self.get_string(data)
                self.whisper(nick, message)
            else:
                logging.warning("Packet is unknown: %s" % number)
                data = ""
    
    def get_byte(self, data):
        number = unpack('b', data[0])[0]
        return (number, data[1:len(data)])
        
    def get_string(self, data):
        offset = data.find(chr(0))
        return (data[0:offset], data[offset+1:len(data)])
        
    def get_int(self, data):
        number = unpack('i', data[0:4])[0]
        return (number, data[4:len(data)])
        
    # Callbacks for individual packets
    def welcome(self):
        logging.warning("Unhandeld welcome packet")
    
    def message(self, id, text):
        logging.warning("Unhandeld message packet")
        
    def whisper(self, source, text):
        logging.warning("Unhandeld whisper packet")
        
    def join(self, name, id):
        logging.warning("Unhandeld join packet")
        
    def leave(self, id):
        logging.warning("Unhandeld leave packet")
        
    def ping(self):
        logging.warning("Unhandeld ping packet")

# Basic Implementation
class ChatServerClient(ChatServer):

    # Connection management
    def connectionMade(self):
        logging.info("Successfully connected to chat server")
        self.send_packet(PK_LOGIN, [self.factory.account_id, self.factory.token])

    # Answer callbacks
    def join(self, name, id):
        self.factory.users[id] = name
        
    def ping(self):
        self.send_packet(PK_PINGCLIENT, [])
        
    def leave(self, id):
        pass

    def message(self, id, text):
        pass
        
    def whisper(self, source, text):
        pass
        
    def welcome(self):
        pass

    # Resolve names
    def get_user_name(self, id):
        if id in self.factory.users:            
            return self.factory.users[id]
        else:
            logging.warning("Could not resolve user id %s" % id)
            return "%s" % id	
        
    # Send public and private message
    def send_message(self, message):
        self.send_packet(PK_MESSAGE, [message])
    
    def send_whisper(self, target, message):
        self.send_packet(PK_WHISPER, [target, message])


# Implementation supporting events and communication with factory
class ChatServerEventClient(ChatServerClient):
    
    # Connection management
    def connectionMade(self):
        ChatServerClient.connectionMade(self)        
        self.factory.echoers.append(self)
        self.factory.clients.append(self)
        
    def connectionLost(self, reason):
        ChatServerClient.connectionLost(self)
        self.factory.echoers.remove(self)        
        self.factory.clients.remove(self)       
    
    # Mapping callbacks to events
    def join(self, name, id):
        ChatServerClient.join(self, name, id)
        self.factory.on_join(name)
    
    def leave(self, id):
        ChatServerClient.leave(self, id)
        self.factory.on_leave(self.get_user_name(id))
        
    def message(self, id, message):
        ChatServerClient.message(self, id, message)
        self.factory.on_message(self.get_user_name(id), message)
        
    def whisper(self, source, message):
        ChatServerClient.whisper(self, source, message)
        self.factory.on_whisper(source, message)
    
# Client factory
class ChatClientFactory(ReconnectingClientFactory):
        
    protocol = ChatServerEventClient
    
    def __init__(self, token, account_id):
        # Persistent data
        self.token = token
        self.account_id = account_id
        self.echoers = []
        self.users = {}
        
        # Events
        self.on_join = Event()
        self.on_leave = Event()
        self.on_message = Event()
        self.on_whisper = Event()

    # Connection management
    def clientConnectionLost(self, connector, reason):
        logging.error("Lost connection to chat server: %s", reason)
        ReconnectingClientFactory.clientConnectionLost(self, connector, reason)

    def clientConnectionFailed(self, connector, reason):
        logging.error("Failed connection to chat server: %s", reason)
        ReconnectingClientFactory.clientConnectionFailed(self, connector, reason)	
        
    # Send messages        
    def send_message(self, message):
        logging.debug("Sending message to chat: %s" % message)
        for echoer in self.echoers:
            echoer.send_message(message)
            
    def send_whisper(self, target, message):
        logging.debug("Sending whisper to chat: %s %s" % (target, message))
        for echoer in self.echoers:
            echoer.send_whisper(target, message)

class TONChatServer(Protocol):
    
    def __init__(self, clients):
        self.clients = clients

    # Connection management
    def connectionMade(self):
        print "New client has connected"        
        self.clients.append(self)
        
    def connectionLost(self, reason):
        print "Lost a client"     
        self.clients.remove(self)       
    
    # Receiving data
    def dataReceived(self, data):    	
        print "Received data from client"
        while(len(data) > 0):
            (number, data) = self.get_byte(data)
            logging.debug("Received packet nr %s" % number)    	    
        
            if number == PK_LOGIN:
                # <account id><cookie string>
                (id, cookie) = self.get_int(data)
                #TODO verify cookie
                verified = True
                if verified == True:
                    print "Client logged in successfully!"
                    self.transport.write(chr(1))
                    #TODO send player list
                    #sending welcome message for now
                    self.transport.write(struct.pack('cs', chr(PK_WELCOME), "Welcome to TON"))
                else:
                    self.transport.write(chr(0))
            elif number == PK_PINGCLIENT:
                see.transport.write(chr(2))
            elif number == PK_WELCOME:
                # no data
                self.welcome()
            elif number == PK_PINGSERVER:
                # no data
                self.ping()
            elif number == PK_LIST:
                # not supported at the moment
                data = ""
            elif number == PK_JOIN:
                # <name><id>
                (name, data) = self.get_string(data)
                (id, data) = self.get_int(data)
                self.join(name, id)
            elif number == PK_LEAVE:
                # <id>
                (id, data) = self.get_int(data)	            
                self.leave(id)
            elif number == PK_MESSAGE:
                # <id><message>
                (id, data) = self.get_string(data)
                (message, data) = self.get_string(data)
                #self.message(id, message)
                # relay message to connected clients
                for client in self.clients:
                    #TODO don't echo to sending client
                    client.transport.write(struct.pack('css', chr(PK_MESSAGE), id, message))
            elif number == PK_WHISPER:
                # <nick><message>
                (nick, data) = self.get_string(data)
                (message, data) = self.get_string(data)
                self.whisper(nick, message)
            else:
                logging.warning("Packet is unknown: %s" % number)
                data = ""
    
    def get_byte(self, data):
        number = unpack('b', data[0])[0]
        return (number, data[1:len(data)])
        
    def get_string(self, data):
        offset = data.find(chr(0))
        return (data[0:offset], data[offset+1:len(data)])
        
    def get_int(self, data):
        number = unpack('i', data[0:4])[0]
        return (number, data[4:len(data)])
        
    # Callbacks for individual packets
    def welcome(self):
        logging.warning("Unhandeld welcome packet")
    
    def message(self, id, text):
        logging.warning("Unhandeld message packet")
        
    def whisper(self, source, text):
        logging.warning("Unhandeld whisper packet")
        
    def join(self, name, id):
        logging.warning("Unhandeld join packet")
        
    def leave(self, id):
        logging.warning("Unhandeld leave packet")
        
    def ping(self):
        logging.warning("Unhandeld ping packet")


class TONChatServerFactory(Factory):

    def __init__(self):
        self.clients = []
    
    def buildProtocol(self, addr):
        return TONChatServer(self.clients)

reactor.listenTCP(11030, TONChatServerFactory())
reactor.run()