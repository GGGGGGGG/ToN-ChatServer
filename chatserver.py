import logging
from struct import pack, unpack

from twisted.internet.protocol import Protocol, ReconnectingClientFactory

from twisted.internet.protocol import Factory
from twisted.internet import reactor
import struct
import mysql.connector
from event import Event
import re
import urllib2
#try:
#    from urllib.request import urlopen
#except ImportError:
#    from urllib2 import urlopen


# MySQL database config
config = {
  'user': 'masterserver',
  'password': 'amtsreesvrre',
  'host': '127.0.0.1',
  'database': 'masterserver',
  'raise_on_warnings': True,
}

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
        self.user = ""
        self.account_id = 0

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
                #verified = False
                #self.user = "peeps123"
                #self.account_id = 868325
                verified = self.handleLogin(id, cookie)
                #verified = True
                if verified == True:
                    print "Client logged in successfully!"
                    self.transport.write(chr(1))
                    #TODO send player list
                    #sending welcome message for now
                    welcomeMsg = "Welcome to"
                    msglen = len(welcomeMsg)
                    fmt = "b11s"
                    #self.transport.write(struct.pack(fmt, PK_WELCOME, welcomeMsg + chr(0)))
                    # + str(msglen) + "s"
                    #, bytes(welcomeMsg, "ascii")))
                    self.sendlist(id)
                else:
                    self.transport.write(chr(0))
            elif number == PK_PINGCLIENT:
                see.transport.write(chr(2))
            elif number == PK_WELCOME:                # no data
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
                # <message>
                (message,dummy) = self.get_string(data)
                message = data
                self.message(message)
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

    def handleLogin(self, id, cookie):
        return self.handleLoginWeb(id, cookie)

    def handleLoginWeb(self, id, cookie):
        resp = urllib2.urlopen("http://savage2.com/en/player_stats.php?id=" + str(id))
        res = re.findall(r"<span class=g16><b>\w+</b>", resp.read())
        print "res:"
        print res
        if len(res) == 0:
            return False
        data = res[0][19:]
        offset = data.find('<')
        self.user = data[:offset]
        self.account_id = id
        print "Found user through web:" + self.user
        return True

    def handleLoginDb(self, id, cookie):
        verified = False
        cnx = mysql.connector.connect(**config)
        cur = db.cursor()
        query = "select username,id from users where cookie=" + cookie
        cur.execute(query)
        rows = cur.fetchall()
        if len(rows) == 1:
            self.user = rows[0].col[0]
            self.account_id = rows[0].col[0]
            verified = True
        cnx.close()
        return verified

    
    def sendlist(self, id):
        # assume the following player list
        ##userlist = [("nick1", "1"), ("nick2", "2")]
        # message format is as follows
        # PK_LIST "Savage 2" numplayers (int4le) array_nickname_accountid ..unknown bytes..
        sav2 = "Savage 2"
        sav2len = len(sav2) + 1
        #nPlayers = len(userlist)
        nPlayers = len(self.clients)
        fmt = "<" + "b" + str(sav2len) + "si"
        data = struct.pack(fmt, PK_LIST, sav2 + chr(0), nPlayers)
        #for user in userlist:
        for client in self.clients:
            #(nickname, account_id) = user
            if client.account_id == id:
                continue
            nickname = client.user
            account_id = client.account_id
            print nickname
            print account_id
            nicklen = len(nickname) + 1
            fmt = "<" + str(nicklen) + "si"
            data = data + struct.pack(fmt, nickname + chr(0), int(account_id))
            # also send that existing client a join notification
            userlen = len(self.user) + 1
            joinfmt = "<b" + str(userlen) + "si"
            client.transport.write(struct.pack(joinfmt, PK_JOIN, self.user + chr(0), int(self.account_id))) 
        self.transport.write(data)

    def message(self, text):
        print "Received message: " + text
        # relay message to connected clients
        for client in self.clients:
            if client == self:
                continue
            print "Relaying message to connected client"
            message = text
            msglen = len(message) + 1
            fmt = "<bi" + str(msglen) + "s" 
            client.transport.write(struct.pack(fmt, PK_MESSAGE, self.account_id, message))
        
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
