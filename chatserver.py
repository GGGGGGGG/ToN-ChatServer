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
import marshal
#try:
#    from urllib.request import urlopen
#except ImportError:
#    from urllib2 import urlopen


# MySQL database config
config = {
  'user': 'masterserver',
  'password': '',
  'host': '127.0.0.1',
  'database': 'masterserver',
  'raise_on_warnings': True,
  #'charset' : 'latin1'
}

###  Packet types ###
PK_LOGIN=0
PK_WELCOME=1
PK_PINGSERVER=2
PK_PINGCLIENT=3
PK_MESSAGE=4
PK_LIST=5
PK_JOIN=6
PK_LEAVE=7
PK_WHISPER=9
PK_FRIENDLIST=12
PK_FRIENDNOTF=13
# client to server
PK_ADDBUDDY=14
PK_REMBUDDY=15
PK_JOINGAME=16
PK_INGAME=17
PK_LEAVEGAME=18

# status used to distinguish between players in lobby and those in game
LOBBY=3
INGAME=5
OFFLINE=1
ONLINE=3

class TONChatServer(Protocol):
    
    def __init__(self, clients):
        self.clients = clients
        self.user = ""
        self.account_id = 0
        self.status = OFFLINE
        self.server_id = 0

    # Connection management
    def connectionMade(self):
        print "New client has connected"        
        self.clients.append(self)
        
    def connectionLost(self, reason):
        print "Lost a client"
        self.leave(self.account_id)
        self.status = OFFLINE
        self.broadcast_notification()
        self.clients.remove(self)       
    
    # Receiving data
    def dataReceived(self, data):    	
        print "Received data from client"
        while(len(data) > 0):
            (number, data) = self.get_byte(data)
            logging.debug("Received packet nr %s" % number)    	    
        
            if number == PK_LOGIN:
                # <account id><cookie string>
                (id, data) = self.get_int(data)
                (cookie, data) = self.get_string(data)
                verified = self.handleLogin(id, cookie)
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
                    #self.sendlist(id)
                    #self.send_friend_notification(3)
                    self.status = ONLINE
                    self.server_id = 0
                    pkt = self.build_server_pklist(self.server_id) + self.build_friendlist_notifications()
                    self.transport.write(pkt)
                    self.join()
                    self.broadcast_notification()
                else:
                    self.transport.write(chr(0))
            elif number == PK_PINGCLIENT:
                self.transport.write(chr(PK_PINGSERVER))
            elif number == PK_WELCOME:                # no data
                self.welcome()
            elif number == PK_LEAVE:
                # <id>
                (id, data) = self.get_int(data)	            
                self.leave(id)
            elif number == PK_MESSAGE:
                # <message>
                (message, data) = self.get_string(data)
                self.message(message)
            elif number == PK_WHISPER:
                # <nick><message>
                (nick, data) = self.get_string(data)
                (message, data) = self.get_string(data)
                self.whisper(nick, message)
            elif number == PK_JOINGAME:
                # <server_id>
                (server_id, data) = self.get_int(data)
                self.server_id = server_id
		self.leave(self.account_id)
                # TODO PK_LIST list of those in game
            elif number == PK_INGAME:
                self.status = INGAME
                self.broadcast_notification()
            elif number == PK_LEAVEGAME:
                self.status = ONLINE
                self.server_id = 0
                pkt = self.build_server_pklist(self.server_id)
                self.transport.write(pkt)
                self.join()
                self.broadcast_notification()
            elif number == PK_ADDBUDDY:
                logging.warning("Packet ADDBUDDY unhandled")
            elif number == PK_REMBUDDY:
                logging.warning("Packet REMBUDDY unhandled")
            else:
                logging.warning("Packet is unknown: %02x" % number)
                print ":".join("{:02x}".format(ord(c)) for c in data)
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
        return self.handleLoginDb(id, cookie)

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
        password = open("/var/www/masterserver1.talesofnewerth.com/dbp").read(100).strip()
        config['password'] = password
        cnx = mysql.connector.connect(**config)
        cur = cnx.cursor(buffered=True)
        query = "SELECT * FROM users WHERE cookie='" + cookie + "'"
        cur.execute(query)
        row = cur.fetchone()
        if row:
            self.user = row[1]
            self.account_id = row[0]
            print "Found user in database"
            print self.user
            print "Account id is"
            print self.account_id
            verified = True
        cur.close()
        cnx.close()
        return verified

    
    def sendlist(self, id):
        # assume the following player list
        ##userlist = [("nick1", "1"), ("nick2", "2")]
        # message format is as follows
        # PK_LIST "Savage 2" numplayers (int4le) array_nickname_accountid ..buddylist notification..
        sav2 = "Savage 2"
        sav2len = len(sav2) + 1
        #nPlayers = len(userlist)
        nPlayers = len(self.clients) - 1
        fmt = "<" + "b" + str(sav2len) + "si"
        data = struct.pack(fmt, PK_LIST, sav2 + chr(0), nPlayers)
        print "Sending online users list to user:"
        print self.user
        buddy_id = 0
        buddydata = struct.pack("<bi", 12, nPlayers);
        for client in self.clients:
            #(nickname, account_id) = user
            if client.account_id == id or client.status == INGAME:
                continue
            nickname = client.user
            account_id = client.account_id
            print nickname
            print account_id
            buddy_id = account_id
            nicklen = len(nickname) + 1
            fmt = "<" + str(nicklen) + "si"
            data = data + struct.pack(fmt, str(nickname + chr(0)), int(account_id))
            # TODO buddy notification data
            buddy_status = 3
            if client.server_id != 0:
                buddy_status = 5
            buddydata = buddydata + struct.pack("<ibbi", int(client.account_id), buddy_status, 0, client.server_id)
            # also send that existing client a join notification
            if client.status == LOBBY:
                userlen = len(self.user) + 1
                joinfmt = "<b" + str(userlen) + "si"
                client.transport.write(struct.pack(joinfmt, PK_JOIN, str(self.user + chr(0)), int(self.account_id)))
        # TODO for all buddies get friend status and append to list (for all users for now)
        data = data + buddydata
        self.transport.write(data)

    def build_server_pklist(self, server_id):
        num_users = 0
        data = ""
        for client in self.clients:
            if client == self or client.server_id != server_id:
                continue
            num_users = num_users + 1
            nickname = client.user
            account_id = int(client.account_id)
            nicklen = len(nickname) + 1
            fmt = "<" + str(nicklen) + "si"
            data = data + struct.pack(fmt, str(nickname + chr(0)), account_id)
        channel_name = "Server" + str(server_id)
        if server_id == 0:
            channel_name = "Savage 2"
        channel_len = len(channel_name) + 1
        fmt = "<b" + str(channel_len) + "si"
        data = struct.pack(fmt, PK_LIST, str(channel_name + chr(0)), num_users) + data
        return data

    def build_friend_notification(self, status):
        num_notifications = 1
        data = struct.pack("<biibbi", PK_FRIENDLIST, num_notifications, int(self.account_id), status, 0, int(self.server_id))
        return data

    def broadcast_notification(self):
        for client in self.clients:
            if client == self:
                continue
            friendnotf = struct.pack("<bibb", PK_FRIENDNOTF, int(self.account_id), self.status, 0)
            if self.status == INGAME:
                friendnotf = struct.pack("<bibbi", PK_FRIENDNOTF, int(self.account_id), self.status, 0, int(self.server_id)) 
            client.transport.write(friendnotf)

    def build_friendlist_notifications(self):
        buddydata = ""
        num_users = 0
        for client in self.clients:
            if client == self:
                continue
            num_users = num_users + 1
            buddy_status = 3
            if client.server_id != 0:
                buddy_status = 5
            if client.status == OFFLINE:
                buddy_status = 1
            friendnotf = struct.pack("<ibb", int(client.account_id), client.status, 0)
            if client.status == INGAME:
                friendnotf = struct.pack("<ibbi", int(client.account_id), buddy_status, 0, client.server_id)            
            buddydata = buddydata + friendnotf
        buddydata = struct.pack("<bi", PK_FRIENDLIST, num_users) + buddydata;
        return buddydata

    def handleCommand(self, text):
        if text == 'disconnect':
            self.clientConnection.disconnect()

    def message(self, text):
        print "Received message: " + text
        # check if command message
        if text[0][0] == '$':
            self.handleCommand(text[1:])
            return
        # relay message to connected clients
        for client in self.clients:
            if client == self or client.status == INGAME:
                continue
            #print "Relaying message to connected client"
            message = str(text)
            msglen = len(message) + 1
            fmt = "<bi" + str(msglen) + "s" 
            client.transport.write(struct.pack(fmt, PK_MESSAGE, self.account_id, message))
        
    def whisper(self, destnick, msg):
        for client in self.clients:
            if client.user != destnick:
                continue
            nicklen = len(self.user) + 1
            msglen = len(msg) + 1
            fmt = "b" + str(nicklen) + "s" + str(msglen) + "s"
            client.transport.write(struct.pack(fmt, PK_WHISPER, str(self.user + chr(0)), msg + chr(0)))
            break
        
    def join(self):
        for client in self.clients:
            if client.account_id == self.account_id or client.status == INGAME:
                continue
            userlen = len(self.user) + 1
            joinfmt = "<b" + str(userlen) + "si"
            client.transport.write(struct.pack(joinfmt, PK_JOIN, str(self.user + chr(0)), int(self.account_id)))
        
    def leave(self, id):
        for client in self.clients:
            if client.account_id == self.account_id or client.status == INGAME:
                continue
            client.transport.write(struct.pack("<bi", PK_LEAVE, self.account_id))
        

class TONChatServerFactory(Factory):

    def __init__(self):
        self.clients = []
    
    def buildProtocol(self, addr):
        return TONChatServer(self.clients)

from twisted.application import service

application = service.Application("chatserver")
reactor.listenTCP(11030, TONChatServerFactory())
reactor.run()
