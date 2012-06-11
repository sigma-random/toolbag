# __init__.py
#
# for public release, 2012
#
# Brandon Edwards
 
import os
import sys
import time
import socket
import signal
import struct
import binascii
import subprocess
import multiprocessing.managers as managers
import Queue


# Packet class 
# mostly for deconstructing data
# can also be used to compose a packet
class ToolbagPacket:
    # datafull is the packet read directly off queue (header,msg)
    def __init__(self, datafull=None):
        self.datafull = datafull
        self.ip = ""
        self.port = 0
        self.key = ""
        self.opcode = ""
        self.filename = ""
        self.msg = ""
        self.params = None

        if datafull != None:
            self.setData(datafull)

    # set data is used to populate this object's pieces
    def setData(self, datafull):
        # datafull is broken down as such:
        # [header] [message] [params]
    
        # extract these these main components
        # get the header
        header = datafull[0]
        # get the message
        self.msg = datafull[1] 

        # break down the header
        # first the queue data
        self.ip = header[0]
        self.port = header[1]
        self.key = header[2]

        # header opcode 
        self.opcode = header[3]

        # filename
        self.filename = header[4] 

        # params
        self.params = header[5]

    def getHeader(self):
        header = (self.ip, self.port, self.key, self.opcode, self.filename)
        return header

    def getPacket(self):
        header = self.getHeader()
        packet = (header, self.msg, self.params)
        return packet

    # setPiece: this lets you set individual packet components
    # if you do not provide a component, it is not updated forthe packet
    def setPiece(self, ip=None, port=None, key=None, opcode=None, filename=None, msg=None, params=None):
        if ip != None:
            self.ip = ip

        if port != None:
            self.port = int(port)
        
        if key != None:
            self.key = key
    
        if opcode != None:
            self.opcode = opcode

        if filename != None:
            self.filename = filename

        if msg != None:
            self.msg = msg

        if params != None:
            self.params = params
        

class QueueServer:
    def __init__(self, ip, port, key):
        if type(port) != type(int):
            port = int(port) 

        self.ip = ip
        self.port = port
        self.key = key

        self.queue = Queue.Queue()
        managers.BaseManager.register('msgq', callable=lambda:self.queue)
        self.manager = managers.BaseManager(address=(ip, port), authkey=key)
        self.server = self.manager.get_server()
        self.server.serve_forever()


class QueueClient:
    def __init__(self, ip, port, key):
        if type(port) != type(int):
            port = int(port) 

        self.ip = ip
        self.port = port
        self.key = key

        managers.BaseManager.register('msgq')
        self.manager = managers.BaseManager(address=(ip, port), authkey=key)
        self.manager.connect()
        self.queue = self.manager.msgq() 

    # send data
    def send(self, data):
        self.queue.put(data)

    # poll for data (non-blocking)
    # returns True if data is available
    def poll(self):
        if self.queue.qsize() != 0:
            return True
        return False

    # receive data (blocking)
    # returns the data read
    def recv(self):
        return self.queue.get() 


# USE THIS IN IDA
class ToolbagHost:
    # ip, port, key are for our listening server Process/Queue
    # said Process/Queue should already be started before calling this
    def __init__(self, pypath, serverpath, ip, port, key):

        print "[*] Spawning server process"

        plat = sys.platform

        if plat == 'win32':
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            cmdline = "c:\\Windows\\system32\\cmd.exe "

            if pypath == None or pypath == '':
                pypath = r"C:\python26\python.exe"

            self.proc = subprocess.Popen([cmdline, "/c", pypath, serverpath, ip, str(port), key], startupinfo=si)
             
        elif plat == 'darwin' or plat == 'linux':
            cmdline = "`which sh`"
            
            # if no pypath was provided
            if pypath == None or pypath == '':
                pypath = "`which python`"

            self.proc = subprocess.Popen([cmdline, pypath, serverpath, ip, str(port), key])

        self.pid = self.proc.pid
       
        print "[*] Server process PID: %d" % self.pid
        print "[*] Server process handle: %d" % self.proc._handle
        print "[*] Connecting to server queue"
        socket.setdefaulttimeout(None)
        self.serverqueue = QueueClient(ip, port, key)
        print "[*] Connected successfully"

        # we save these as "ours" even though in theory the server queue
        # could be on another machine
        # these are used as return/reply headers when we send data to agents
        self.ip = ip
        self.port = port
        self.key = key

        # things to track agents 
        self.agents = dict()
        self.agentidx = None

        # peers (other Toolbag ussers)
        self.peers = dict()
        self.peeridx = None

    def addPeer(self, ip, port, key):
        if self.peeridx == None:
            self.peeridx = 0

        self.peers[self.peeridx] = QueueClient(ip, port, key)

        ret = self.peeridx
        self.peeridx += 1

        return ret

    def delPeer(self, idx):
        del self.peers[idx]

    def sendPeer(self, msg, opcode, filename="", params=None, idx=None):

        if idx == None:
            if self.peeridx == None:
                raise NameError("No registered peers")
            idx = self.peeridx -1

        # XXX: added opcode and filename to this header -aaron
        header = (self.ip, self.port, self.key, opcode, filename, params)
        packet = (header, msg)
        self.peers[idx].send(packet)
        

    # add an agent
    def addAgent(self, ip, port, key):
        print "+ Adding an agent at %s:%d" % (ip, port)
        if self.agentidx == None:
            self.agentidx = 0

        self.agents[self.agentidx] = QueueClient(ip, port, key)
        print "+ Done creating queue client"
        
        ret = self.agentidx 
        self.agentidx += 1
        
        return ret

    def delAgent(self, idx):
        del self.agents[idx] 

    def sendAgent(self, msg, opcode, filename="", params=None, idx=None): 
        if idx == None:
            if self.agentidx == None:
                raise NameError("No registered agents")

            idx = self.agentidx - 1

        header = (self.ip, self.port, self.key, opcode, filename, params)
        packet = (header, msg)
        self.agents[idx].send(packet)
        

    def end(self):
        # close the server queue
        #

        plat = sys.platform

        socket.setdefaulttimeout(0.5)

        # yeah, we're doing this.
        if plat == 'win32':
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            subprocess.Popen(["taskkill.exe", "/F", "/T", "/PID", "%d" % self.pid], startupinfo=si)
        elif plat == 'darwin' or plat == 'linux':
            subprocess.Popen(["kill", "-TERM", "%d" % self.pid])


    # poll: non blocking check for data in the queue
    def poll(self):
        return self.serverqueue.poll()

    # recv: receives data from the queue (blocking)
    def recv(self):
        return self.serverqueue.recv()
    

# since toolbagAgent is _not_ within IDA
# we can use the real multiprocessing "Process()"
class ToolbagAgent:
    def __init__(self, ip, port, key):
        # the Agent queue server it listens on
        self.agentdata = (ip, port, key)
        self.queue = QueueClient(ip, port, key)
        self.callbacks = {}
        
    # kill the agent
    def end(self):
        self.process.terminate()
        sys.exit(0)

    # register a callback to handle a specific opcode
    def registerCallback(self, opcode, callback, args=()):
       self.callbacks[opcode] = (callback, args)

    # the main loop:
    # this is a while(1) to receive data from the queue
    # the opcode provided in the data is looked up in the callbacks
    # if a callback is found, it is executed
    def mainLoop(self):
        while (1):
            print "+ Agent waiting for data"
            # wait for data (blocking)
            data = self.queue.recv()

            # use ToolbagPacket to decompose the data
            pkt = ToolbagPacket(data)

            print "+ message from %s:%i" % (pkt.ip, pkt.port)

            # lookup the opcode in the callbacks 
            if pkt.opcode in self.callbacks.keys():

                # an opcode handler was found
                print "+ calling opcode handler.."
                callback, args = self.callbacks[pkt.opcode]

                # if there are no args, just pass it the packet
                # and the agentdata 
                if args == None:
                    callback(pkt, self.agentdata)

                # otherwise they provided args, pass them to the handler
                else:
                    callback(pkt, self.agentdata, *args)
            else:
                print "+ No handler registered for this opcode: %s" % pkt.opcode

# main function
if __name__ == "__main__":
    argc = len(sys.argv)
    
    # exit
    sys.exit(0)