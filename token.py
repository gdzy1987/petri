'''
Created on Nov 8, 2012

@author: pgrossman
'''
from utils import utils
from threading import Lock
import copy

debug = True

class TokenList(object):
    tlLock = Lock()

    def __init__(self, initialTokenAssignments):
        utils.log('New TokenList')
        self.initialTokenAssignments = initialTokenAssignments
        self.list = {}
        self.requiredTokensByState = {}
        if initialTokenAssignments != None:
            for tokenName, attributes in self.initialTokenAssignments.iteritems():
                numTokens = attributes[0]
                if not tokenName in self.list:
                    self.list[tokenName] = []
                for t in xrange(int(numTokens)):
                    token = Token(tokenName, copy.deepcopy(attributes[1]))
                    token.unlock()
                    self.list[tokenName].append(token)

    def dump(self, title = None, indent = 5):
        if not debug: return
        pad = ''
        for i in xrange(indent): pad += ' '
        msg = '\n'
        try:
            if title != None and len(title) > 0:
                msg += title + '\n'
            msg += 'Token List Dump'.rjust(indent+15, ' ') + '\n'
            for tokenName,tokens in self.list.items():
                for token in tokens:
                    msg += token.dump('', indent)
            utils.log(msg)
            return msg
        finally:
            pass

    def lock(self, tokenName, tokenSpec, transitionObject, reqPropertyValues = {}):
        try:
            self.tlLock.acquire()
            nRequired = tokenSpec[1]
            reqProperties = {}
            if len(reqPropertyValues) > 1:
                utils.log('WARNING - Too much choice in tokenList.lock for ' + tokenName + ': ' + repr(reqPropertyValues))
            if len(reqPropertyValues) > 0:
                reqProperties.update(reqPropertyValues[0]) #Choose a single property value if there is a list of more than one - shouldn't happen
            if len(tokenSpec[0].keys()) > 0:
                for prop,value in tokenSpec[0].items():
                    if not prop in reqProperties:
                        reqProperties[prop] = []
                    reqProperties[prop].append(value)
            n = 0
            for i in xrange(len(self.list[tokenName])):
                token = self.list[tokenName][i]
                if token.isLocked(): continue
                acceptable = True
                if len(reqProperties.items()) > 0:
                    for prop,value in reqProperties.items():
                        if len(prop) != 0 and (prop in token.getProperties()) and (not token.getProperty(prop) in value):
                            acceptable = False
                    if acceptable: 
                        token.lock()
                        token.setTransitionOwner(transitionObject)
                        n += 1
                        if n >= nRequired: return n
                else: 
                    token.lock()
                    token.setTransitionOwner(transitionObject)
                    n += 1
                    if n >= nRequired: return n
            return n
        finally:
            self.tlLock.release()       

    def unlock(self, tokenName, nRequired, transitionOwnerObject):
        try:
            self.tlLock.acquire()
            tokenList = self
            if transitionOwnerObject != None:
                tokenList = self.getTokenListByOwner(transitionOwnerObject)
            if not tokenName in tokenList.list:
                utils.log('Token ' + tokenName + ' not in list')
                return
            n = 0
            for i in xrange(len(tokenList.list[tokenName])):
                token = tokenList.list[tokenName][i]
                if token.isLocked(): 
                    token.unlock()
                    n += 1
                    if n >= nRequired: return n
            utils.log('Not enough tokens to unlock for ' + tokenName)
            return n
        finally:
            self.tlLock.release()       

    def unlockAllByTransitionObject(self, transitionOwnerObject):
        try:
            self.tlLock.acquire()
            for tokenName, tokens in self.list.iteritems():
                for t in xrange(len(tokens)):
                    token = tokens[t]
                    if token.getTransitionOwner() == transitionOwnerObject:
                        token.unlock()
        finally:
            self.tlLock.release()       

    def removeAllByTransitionObject(self, transitionOwnerObject):
        try:
            self.tlLock.acquire()
            l = {}
            for tokenName, tokens in self.list.iteritems():
                for t in xrange(len(tokens)):
                        token = tokens[t]
                        petriOption = token.getProperty('petriOption')
                        unlockOnly = False
                        if petriOption != None and 'unlockOnly' in petriOption:
                            unlockOnly = True
                            petriOption.remove('unlockOnly')
                        token.getProperty('petriOption')
                        if token.getTransitionOwner() == transitionOwnerObject:
                            if not unlockOnly:
                                print 'Removing token ' + tokenName
                                continue
                            else:
                                token.unlock()
                        if not tokenName in l:
                            l[tokenName] = []
                        l[tokenName].append(token)
            self.list = l
        finally:
            self.tlLock.release()       

    def addToken(self, token, lock=False):
        try:
            if lock:
                self.tlLock.acquire()
            tokenName = token.getName()
            if not tokenName in self.list:
                self.list[tokenName] = []
            self.list[tokenName].append(token)
            utils.log('Adding token ' + tokenName)
        finally:
            if lock:
                self.tlLock.release()       

    def add(self, tokenName, amount, properties = {}):
        try:
            self.tlLock.acquire()
            n = 0
            if not tokenName in self.list:
                self.list[tokenName] = []
            for i in xrange(amount):
                token = Token(tokenName)
                token.unlock()
                for propName, propValue in properties.items():
                    token.setProperty(propName, propValue)
                self.list[tokenName].append(token)
                utils.log('Adding token ' + tokenName)
            return n
        finally:
            self.tlLock.release()       

    def removeByName(self, tokenName, amount):
        try:
            self.tlLock.acquire()
            n = 0
            if not tokenName in self.list:
                utils.logTrace('token ' + tokenName + ' not found')
                return
            l = self.list[tokenName]
            for i in xrange(amount):
                if len(l) > 0:
                    del l[0]
        finally:
            self.tlLock.release()       

    def remove(self, token):
        try:
            self.tlLock.acquire()
            n = 0
            if not token.getName() in self.list:
                utils.logTrace('token ' + token.getName() + ' not found')
                return
            l = self.list[token.getName()]
            if not token in l:
                utils.log('token ' + token.getName() + ' not found in remove')
            ndx = l.index(token)
            del l[ndx]
        finally:
            self.tlLock.release()       

    # lockedState = [True|False|None] - None = Do not care
    def getTokensByOwnerAndSpec(self, tokenName, transitionOwnerObject=None, properties=None, lockedState=False):
        try:
            tokensOut = []
            tokens = []
            if tokenName == None:
                for tokenName, tokenItems in self.list.items():
                    for token in tokenItems:
                        if transitionOwnerObject != None and token.getTransitionOwner() == transitionOwnerObject:
                            tokens.append(token)
            elif tokenName in self.list and len(self.list[tokenName]) > 0:
                for token in self.list[tokenName]:
                    if transitionOwnerObject == None or (transitionOwnerObject != None and token.getTransitionOwner() == transitionOwnerObject):
                        tokens.append(token)
            for token in tokens:
                foundIt = True
                if lockedState != None:
                    if token.isLocked() and not lockedState:
                        continue
                    if not token.isLocked() and lockedState:
                        continue
                if properties != None and len(properties) > 0:
                    tProperties = token.getProperties()
                    for prop, value in properties.items():
                        if not prop in tProperties or tProperties[prop] != value:
                            foundIt = False
                            break
                if foundIt:
                    tokensOut.append(token)
            return tokensOut
        finally:
            pass
    
    def getNumUnlocked(self, tokenName, properties):
        try:
            n = 0
            if tokenName in self.list and len(self.list[tokenName]) > 0:
                for i in xrange(len(self.list[tokenName])):
                    token = self.list[tokenName][i]
                    if token.isLocked():
                        continue
                    if properties != None and len(properties) > 0:
                        tProperties = token.getProperties()
                        if utils.dictIsSubset(properties, tProperties):
                            n += 1
                    else:
                        n += 1
            return n
        finally:
            pass
    
    def getNumLocked(self, tokenName):
        try:
            n = 0
            if tokenName in self.list:
                for i in xrange(len(self.list[tokenName])):
                    token = self.list[tokenName][i]
                    if token.isLocked(): n += 1
            return n
        finally:
            pass

    def getNumTokens(self, tokenName):
        try:
            if tokenName in self.list:
                return len(self.list[tokenName])
            return 0
        finally:
            pass
    
    def getTokenListByOwner(self, transitionOwnerObject=None, name=None):
        try:
            lock = False
            tokenList = TokenList(None)
            for tokenName, tokens in self.list.iteritems():
                for t in xrange(len(tokens)):
                    token = tokens[t]
                    if transitionOwnerObject != None and token.getTransitionOwner() != transitionOwnerObject: continue
                    if name != None and tokenName != name:
                        continue
                    if not tokenName in tokenList.list:
                        tokenList.list[tokenName] = []
                    tokenList.addToken(token, lock)
            return tokenList
        finally:
            pass      

    def getUnlockedTokensByKey(self, name):
        try:
            tokenList = []
            for tokenName, tokens in self.list.iteritems():
                for t in xrange(len(tokens)):
                    token = tokens[t]
                    if token.isLocked(): continue
                    if name != None and tokenName != name:
                        continue
                    tokenList.append(token)
            return tokenList
        finally:
            pass      

class Token(object):
    def __init__(self, name, properties = {}, transitionOwner = None):
        self.unlock()
        self.setName(name)
        self.setTransitionOwner(transitionOwner)
        self.properties = properties.copy()
        
    def dump(self, title, indent):
        if not debug: return ''
        msg = ''.ljust(indent, ' ')
        try:
            if title != None and len(title) > 0:
                msg += title + ': '
            msg += ' ' + self.name.ljust(15, ' ')
            if self.getTransitionOwner() != None:
                msg += 'Owner ' + repr(self.getTransitionOwner().getName()) + ': '
            else:
                msg += 'Owner unassigned: '
            if self.isLocked(): msg += 'Token Locked'
            else: msg += 'Token Unlocked'
            if self.properties != None and len(self.properties) > 0:
                msg += ' Properties: '
                keys = self.properties.keys()
                keys.sort()
                for prop in keys:
                    value = self.properties[prop]
                    msg += '[' + repr(prop) + ':' + repr(value) + ']'
            #utils.log(msg)
            msg += '\n'
            return msg
        finally:
            pass

    def clone(self):
        properties = self.properties.copy()
        token = Token(self.name, properties, self.transitionOwner)
        return token
    
    def setName(self, name):
        self.name = name
        
    def getTransitionOwner(self):
        return self.transitionOwner
    
    def getName(self):
        return self.name
    
    def setProperty(self, prop, value):
        if prop == None or value == None:
            if prop in self.properties:
                del self.properties[prop]
                utils.logTrace('Removing property ' + repr(prop) + ' value: ' + repr(value))
        if prop in self.properties:
            old = ''
            if self.properties[prop] != None:
                old = self.properties[prop]
            utils.log('Token "' + self.name + '" Replacing ' + prop + ' old value: ' + repr(old) + ' new value ' + repr(value))
        self.properties[prop] = value
    
    def getProperty(self, prop):
        if prop in self.properties:
            return self.properties[prop]
        return None
    
    def removeProperty(self, prop):
        if prop in self.properties:
            del self.properties[prop]
        return None
    
    def getProperties(self):
        return self.properties
    
    def setTransitionOwner(self, transitionOwner):
        self.transitionOwner = transitionOwner

    def isLocked(self):
        return self.locked
    
    def lock(self):
        utils.log('Locking ' + self.getName() + ' ' + repr(self.getProperties()))
        self.locked = True

    def unlock(self):
        self.locked = False
        self.setTransitionOwner(None)

