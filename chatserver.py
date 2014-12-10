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
PK_JOINGAME=16
PK_INGAME=17
PK_LEAVEGAME=18

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
            elif number == PK_JOINGAME:
                # <server_id>
                (server_id, data) = self.get_int(data)
                # TODO send out PK_LEAVE and list of those in game
            #elif number == PK_INGAME:
                # TODO update client status to in-game?
            #elif number == PK_LEAVEGAME:
                # TODO
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
        # ugly hack to match data type otherwise query wouldn't fetch rows unless cookie is hardcoded
        # would someone more experienced please fix this?!
        cookie = cookie.decode('ascii')
        str =  marshal.dumps(cookie)
        str = str.replace("u!", "t ")
        cookie = marshal.loads(str)
        query = "SELECT * FROM users WHERE cookie='" + cookie + "'"
        cur.execute(query)
        #cur.execute("SELECT * FROM users WHERE cookie='%s'", (cookie, ))
        #cnx.commit() 
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
        # PK_LIST "Savage 2" numplayers (int4le) array_nickname_accountid ..unknown bytes..
        sav2 = "Savage 2"
        sav2len = len(sav2) + 1
        #nPlayers = len(userlist)
        nPlayers = len(self.clients) - 1
        fmt = "<" + "b" + str(sav2len) + "si"
        data = struct.pack(fmt, PK_LIST, sav2 + chr(0), nPlayers)
        print "Sending online users list to user:"
        print self.user
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
            data = data + struct.pack(fmt, str(nickname + chr(0)), int(account_id))
            # also send that existing client a join notification
            userlen = len(self.user) + 1
            joinfmt = "<b" + str(userlen) + "si"
            client.transport.write(struct.pack(joinfmt, PK_JOIN, str(self.user + chr(0)), int(self.account_id))) 
        self.transport.write(data)

    def message(self, text):
        print "Received message: " + text
        # relay message to connected clients
        for client in self.clients:
            if client == self:
                continue
            print "Relaying message to connected client"
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
        
    def join(self, name, id):
        for client in self.clients:
            if client.account_id == self.account_id:
                continue
            userlen = len(self.user) + 1
            joinfmt = "<b" + str(userlen) + "si"
            client.transport.write(struct.pack(joinfmt, PK_JOIN, self.user + chr(0), int(self.account_id)))
        
    def leave(self, id):
        for client in self.clients:
            if client.account_id == self.account_id:
                continue
            client.transport.write(struct.pack("<bi", PK_LEAVE, self.account_id))
        
    def ping(self):
        self.transport.write(struct.pack("b", PK_PINGSERVER))


class TONChatServerFactory(Factory):

    def __init__(self):
        self.clients = []
    
    def buildProtocol(self, addr):
        return TONChatServer(self.clients)

from twisted.application import service

application = service.Application("chatserver")
reactor.listenTCP(11030, TONChatServerFactory())
reactor.run()
