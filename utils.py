from datetime import timedelta, datetime, date
import time
import pickle
import os, sys, stat, traceback
import socket
import zipfile
import struct
import binascii
from threading import Lock
import threading

class utils:
    logLock = Lock()
    sessionID = 0
    timeStamp = None
    
    @staticmethod
    def ensure_dir(f):
        d = os.path.dirname(f)
        if len(d) == 0: return
        #print d[2]
        if len(d) > 3 and d[2] == ':':
            d = d[3:]
        if not os.path.exists(d):
            utils.log('Creating directory ' + d)
            os.makedirs(d)

    @staticmethod
    def __init__(self):
        return
    
    @staticmethod
    def reset():
        sessionID = 0
        utils.timeStamp = utils.getDateTimeTag()
        return
    
    @staticmethod
    def setSessionID(sessionIDIn):
        utils.sessionID = sessionIDIn
        return
    
    @staticmethod
    def getSessionID():
        return utils.sessionID
    
    @staticmethod
    def getLocalTimeNew():
        now=datetime.now()
        return now
        
    @staticmethod
    def getHostName():
        hostName = socket.gethostname()
        utils.log('Host name ' + hostName)
        return hostName
        
    @staticmethod
    def getDateTimeTag():
        now=datetime.now()
        nowUTC=datetime.utcnow()
        UTC_OFFSET_TIMEDELTA = nowUTC - now
        localDateTimeObject = nowUTC - UTC_OFFSET_TIMEDELTA
        tag = localDateTimeObject.strftime("%Y%m%d%H%M%S")
        return tag

    @staticmethod
    def getAbbrDateTimeTag(offset):
        #offset = timedelta(seconds=120)
        now=datetime.now()
        now = now + offset
        tag = now.strftime("%H:%M:%S")
        return tag

    @staticmethod
    def getDateTimeTagRelative(now):
        nowUTC=datetime.utcnow()
        UTC_OFFSET_TIMEDELTA = nowUTC - now
        localDateTimeObject = nowUTC - UTC_OFFSET_TIMEDELTA
        tag = localDateTimeObject.strftime("%Y%m%d%H%M%S")
        return tag

    @staticmethod
    def openSocket(host, port):
        try:
            utils.log('Attempting connection to ' + host + ' on ' + repr(port))
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            #self.s.settimeout(20)
            s.connect((host, port))
            utils.log('Connected to ' + host + ' on ' + repr(port))
            return s
        except:
            utils.logTrace('Exception in openSocket')
        return None

    @staticmethod
    def sendFile(fname, socket):
        blockSize = 32000
        msg = ''
        try:
            source = open(fname, 'rb')
            sizeBytes = os.path.getsize(fname)
            utils.log('Sending file ' + fname + ' of ' + str(sizeBytes) + ' bytes')
            bytesOut = 0
            start = utils.getUTCTime()
            prev = 0
            for data in utils.chunked(source, blockSize):
                utils.log('sending data ' + str(len(data)))
                socket.sendall(data)
                bytesOut += len(data)
                if (bytesOut - sizeBytes) > 1024:
                    utils.log('WARNING - truncating send because send file appears to be growing.')
                    break;
                diff = utils.getSecondsBetweenTwoDates(start, utils.getUTCTime())
                diff = (int(diff/30))*30
                if diff > prev:
                    prev = diff
                    utils.log('So far sent ' + str(bytesOut) + ' read')
            utils.log('Completed send of ' + str(bytesOut) + ' bytes')
            
            socket.settimeout(20)
            c = socket.recv(4096)
            utils.log('Received ' + repr(c))
            return msg
        #except(socket.error):
            #utils.log("timeout in sendFile - possibly no received confirmation data")
        except Exception, errorcode:
            if errorcode[0] != "timed out":
                utils.logTrace('Exception ' + repr(errorcode))
        except:
            utils.logTrace('Exception')  
            return msg
        finally:
            socket.close()
            source.close          

    @staticmethod
    def receiveToFile(fname, socket, remain):
        blockSize = 32000
        msg = ''
        try:
            utils.ensure_dir(fname)
            source = open(fname, 'wb')
            if source == None:
                utils.logTrace('Could not open file ' + fname)
                return
            utils.log('Receiving file ' + fname)
            bytesIn = 0
            if remain != None and len(remain) > 0:
                source.write(remain)
                bytesIn += len(remain)
            start = utils.getUTCTime()
            prev = 0
            while 1:
                c = socket.recv(blockSize)
                if c == None or len(c) == 0: break
                source.write(c)
                bytesIn += len(c)
                diff = utils.getSecondsBetweenTwoDates(start, utils.getUTCTime())
                diff = (int(diff/30))*30
                if diff > prev:
                    prev = diff
                    utils.log('So far received ' + str(bytesIn) + ' read')
            #utils.log('Completed send to ' + self.host + ' on ' + repr(self.port) + ' of ' + str(bytesOut) + ' bytes')
            utils.log('File of ' + str(bytesIn) + ' bytes received')
            return msg
        except Exception, errorcode:
            if errorcode[0] != "timed out":
                utils.logTrace('Exception ' + errorcode)
        except:
            utils.logTrace('Exception')  
            return msg
        finally:
            source.close          

    @staticmethod
    def getDirContents(path):
        fname = ''
        contentPath = ''
        try:
            fname = os.path.basename(path)
            contentPath = 'c:/temp/' + fname
            if contentPath.rfind(".") == -1:
                contentPath += '.txt'
            utils.ensure_dir(contentPath)
            files = os.listdir(path)
            files = sorted(files)
            fileList = ''
            for f in files:
                p = path + '/' + f
                s = os.stat(p)
                mtime = time.strftime("%m/%d/%Y",time.localtime(s[stat.ST_ATIME]))
                if os.path.isdir(p) == True:
                    fname = '{:<40}'.format('[' + f + ']')
                    dirSize = len(os.listdir(p))
                    fileList += fname + '\t' + repr(dirSize) + '\t' + mtime + '\n'
                else:
                    fname = '{:<40}'.format(f)
                    sizeBytes = repr(s.st_size).replace('L', '')
                    fileList += fname + '\t' + sizeBytes + '\t' + mtime + '\n'
                    
            #fileList = repr(files)
            out=open(contentPath, 'w')
            utils.log('Getting directory of ' + path + ' to file ' + contentPath)
            out.write(fileList)
            return contentPath
        except:
            utils.logTrace('Failed getting directory of ' + path + ' to file ' + contentPath)
            return None
        finally:
            pass
                
    @staticmethod
    def chunked(fileX, chunk_size):
        return iter(lambda: fileX.read(chunk_size), '')

    @staticmethod
    def dictIsSubset(master, db, missingKeyOK=True, nullValueOK=True):
        keyValues = {}
        for key in master.keys():
            if not key in db and missingKeyOK:
                utils.log('key ' + key + ' not found in ' + repr(db) + ' OK because missingKeyOK=True')
                return True
            if key in db and db[key] == None and nullValueOK:
                continue
            if not key in db:
                utils.log('value for ' + key + ' missing in ' + repr(db) + ' (' + repr(master[key]))
            if not key in keyValues or keyValues[key] == None:
                keyValues[key] = {}
                values = keyValues[key]
                values[db[key]] = db[key]
                continue
            if values[db[key]] == None:
                utils.log('value for ' + key + ' not equal in ' + repr(db) + ' (' + repr(master[key]))
                return keyValues
        return True
                    
    @staticmethod
    def copyFile(fileIn, fileOut):
        try:
            fIn = open(fileIn, 'rb')
            fOut = open(fileOut, 'wb')
            for data in utils.chunked(fIn, 65536):
                fOut.write(data)
            fOut.close()
            fIn.close()
        except:
            utils.logTrace('Exception in copyFile for ' + fileIn + ' and ' + fileOut)

    @staticmethod
    def logTrace(text):
        msg = ''
        trace = traceback.format_exc().splitlines()
        for l in trace:
            msg += l + '\n'
        trace = str(sys.exc_info()) + '\n' + msg
        return utils.log('ERROR ' + text + trace)
    
    @staticmethod
    def log(textIn, inPath = None):
        utils.logLock.acquire() # will block if lock is already held
        try:
            text = textIn
            if textIn == None or len(textIn) == 0: text = 'None'
            if text[-1:] == '\n':
                text = text[0:-1]
            t = str(datetime.now()) + '- ' + repr(os.getpid()) + '- ' + repr(threading.current_thread().getName()) + '- ' + repr(threading._get_ident()) + ': ' + str(text)
            print t
            if utils.timeStamp == None:
                utils.reset()
            path = inPath
            if path == None:
                path = utils.getLogPath()
            utils.Log = open(path, 'a')
            utils.Log.write(t + '\n')
            utils.Log.flush()
            utils.Log.close()
            masterPath = utils.getMasterLogPath()
            utils.MasterLog = open(masterPath, 'a')
            utils.MasterLog.write(t + '\n')
            utils.MasterLog.flush()
            utils.MasterLog.close()
            #time.sleep(5)
        finally:
            utils.logLock.release()

    @staticmethod
    def logClose():
        if hasattr(utils, 'Log'):
            utils.Log.close()

    @staticmethod
    def resetLog(path):
        if os.path.exists(path):
            os.remove(path)

    @staticmethod
    def getLogPath(sessionIDIn=-1):
        sessionIDTemp = utils.sessionID
        if not sessionIDIn == -1:
            sessionIDTemp = sessionIDIn
        if not hasattr(utils, 'timeStamp'):
            utils.reset()
            #self.log('timeStamp not set in getLogPath')
        path = 'petri_' + str(utils.timeStamp)+'_'+str(utils.sessionID)+'.log'
        return path
    
    @staticmethod
    def getMasterLogPath():
        path = 'petri.log'
        return path
    
    @staticmethod
    def sleepLogSeconds(previous):
        startSeconds = 60
        limitSeconds = 60*60
        if previous > limitSeconds:
            return startSeconds
        return previous*2
    
