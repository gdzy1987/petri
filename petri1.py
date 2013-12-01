import string
import threading
import os
from random import random,randrange
import token
from petri.token import TokenList,Token
from threading import Lock
from petri.utils import utils
from inventory import Inventory
import time

debug = False
class TransitionMaster(object):
    tmLock = Lock()
    ids = 0
    activeThreads = {}
    def __init__(self, transitionName, petriNet, properties):
        self.activeThreads = {}
        self.petriNet = petriNet
        self.transitionName = transitionName
        self.requiredTokensByState = {}
        self.deliveredTokensByState = {}
        self.transitionItemsRunning = []
        self.properties = properties
        self.id = TransitionMaster.ids
        self.proto = TransitionItemFactory.getObject(transitionName, self)
        TransitionMaster.ids += 1
        
    def getPetriNet(self):
        return self.petriNet
    
    def getPrototype(self):
        return self.proto
        
    def IsEnabled(self, tokenList):
        # First get common properties across required tokens
        commonValuesByTokenName = {}
        for transitionProperty in self.properties.keys():
            commonValuesByTokenName[transitionProperty] = {}
        for reqTokenName, tokenSpec in self.requiredTokensByState.items():
            tokensAvailable = 0
            numRequired = tokenSpec[1]
            if reqTokenName in tokenList.list:
                tokens = tokenList.getTokensByOwnerAndSpec(reqTokenName, transitionOwnerObject=None, properties=tokenSpec[0], lockedState=False)
                for token in tokens:
                    tokensAvailable += 1
                    for transitionPropertyName in self.properties.keys():
                        if transitionPropertyName in token.getProperties():
                            if not token.getName() in commonValuesByTokenName[transitionPropertyName]:
                                commonValuesByTokenName[transitionPropertyName][token.getName()] = []
                            commonValuesByTokenName[transitionPropertyName][token.getName()].append(token.getProperty(transitionPropertyName))
                if tokensAvailable < numRequired: 
                    utils.log('Cannot run ' + self.getName() + ' because not enough ' + reqTokenName + "'s available.'")
                    return False,{}
            else:
                utils.log('Cannot run ' + self.getName() + ' because token ' + reqTokenName + ' not available.')
                return False, {}
             
        # So commonValuesByTokenName is owned by the transitionItem and manages the properties that it cares about.
        # For each one of these properties, it contains a list of all of its required tokens and the values of that property
        # across those tokens.  The idea is that the transition can specify that for a given property if the tokens available
        # contain that property then their values must match.  For example, if the "dosing" transition requires an "assay plate"
        # and a "source plate" token then it may require that the common assay plate barcode be the same in both tokens for 
        # those tokens to be acquired by the instance of the transition.
        intersections = {}
        intersect = []
        for transitionPropertyName in commonValuesByTokenName.keys():
            prev = []
            req = ['any']
            if transitionPropertyName in self.properties and self.properties[transitionPropertyName] != None:
                req = self.properties[transitionPropertyName]
            if transitionPropertyName == 'prevTransition' and 'prevTransition' in self.properties:
                prev = prev + self.properties['prevTransition']
                if 'any' in req:
                    intersections[transitionPropertyName] = intersect
            for tokenName in commonValuesByTokenName[transitionPropertyName].keys():
                current = commonValuesByTokenName[transitionPropertyName][tokenName]
                if len(prev) > 0 and len(current) > 0:
                    intersect = [val for val in prev if val in current]
                    if len(intersect) == 0:
                        utils.log('Cannot run ' + self.getName() + ' because no matching on ' + transitionPropertyName + ' for ' +  tokenName)
                        return False, {} 
                    prev = intersect
                else:
                    prev = current
                    intersect = current
            intersections[transitionPropertyName] = intersect
        for tokenName in intersections.keys():
            valueList = intersections[tokenName]
            # We may have found more than one set of common property values.  Choose one set only.
            intersections[tokenName] = [valueList[0]] # Choose single member of overlap
        utils.log('Candidate ' + self.getName() + ' intersection ' + repr(intersections))
        return True, intersections
    
    def completeTransitionItemObject(self, transitionItemObject):
        try:
            utils.log('Completing ' + transitionItemObject.getName())
            self.tmLock.acquire()
            if transitionItemObject.getErrorCode() != 0:
                utils.log('Transition ' + transitionItemObject.getName() + ' failed with code ' + str(transitionItemObject.getErrorCode()))
                transitionItemObject.getTokenList().unlockAllByTransitionObject(transitionItemObject)
            else:
                acquired = self.petriNet.getTokenList().getTokensByOwnerAndSpec(None, transitionItemObject, properties={}, lockedState=True)
                self.adjustTokens(transitionItemObject, acquired, self.deliveredTokensByState)

            properties = {}
            tokens = self.petriNet.getTokenList().getTokensByOwnerAndSpec(None, transitionItemObject, properties, lockedState = True)
            for token in tokens:
                token.unlock()
           
            if not transitionItemObject in transitionItemObject.getTransitionMaster().transitionItemsRunning:
                utils.log('Attempt to delete transition item that is not in the run queue ' + transitionItemObject.getName())
            ndx = transitionItemObject.getTransitionMaster().transitionItemsRunning.index(transitionItemObject)
            del transitionItemObject.getTransitionMaster().transitionItemsRunning[ndx]
            self.removeActiveThread(transitionItemObject)
            utils.log('Tokens after completion of ' + transitionItemObject.getName() + ' ' + self.petriNet.PrintTokenList(self.transitionName))
            msg = tokenList.dump('-------Completion ' + transitionItemObject.getName() + ' ID: ' + transitionItemObject.getId() + ' Active Transitions ' + str(self.petriNet.getTotalActive()))
            utils.log(msg, 'trace_' + str(utils.sessionID)+'.txt')
        finally:
            self.tmLock.release()
            
    # Support the "Pass through" of token properties for tokens that are both acquired and emitted.
    def adjustTokens(self, transitionItemObject, acquired, emitted):
        preserved = {}
        emittedNames = {}
        for tokenName in emitted.keys():
            emittedNames[tokenName] = tokenName
        for token in acquired:
            if not token.getName() in emittedNames:
                self.petriNet.getTokenList().remove(token)
            else:
                preserved[token.getName()] = token
                token.setProperty('prevTransition', self.getName())
        # create or re-emit the required number of tokens with inherited or transition specified properties
        for stateName in emittedNames.keys():
            if not stateName in preserved:
                properties = {}
                properties['prevTransition'] = self.getName();
                tokenSpec = emitted[stateName]
                for i in xrange(tokenSpec[1]):
                    token = Token(stateName, properties, None)
                    self.petriNet.getTokenList().addToken(token) # implies unlock
            properties = {}
            tokens = self.petriNet.getTokenList().getTokensByOwnerAndSpec(stateName, transitionItemObject, properties, lockedState = True)
            properties = emitted[stateName][0]
            for prop,value in properties.items():
                for token in tokens:
                    token.setProperty(prop, value)
            
    def launchTransitionItemObject(self, transitionItemObject, reqPropertyValues = {}):
        try:
            utils.log('Launching ' + transitionItemObject.getName())
            msg = tokenList.dump('-------Before Launch ' + transitionItemObject.getName() + ' ID: ' + transitionItemObject.getId() + ' Active Transitions ' + str(self.petriNet.getTotalActive()))
            utils.log(msg, 'trace_' + str(utils.sessionID)+'.txt')
            for stateName in self.requiredTokensByState.keys():
                tokenSpec = self.requiredTokensByState[stateName]
                numLocked = transitionItemObject.getTokenList().lock(stateName, tokenSpec, transitionItemObject, reqPropertyValues)
                if tokenSpec[1] != numLocked:
                    utils.logTrace('Could not lock sufficient tokens for ' + stateName)
            transitionItemObject.getTransitionMaster().transitionItemsRunning.append(transitionItemObject)    
            self.addActiveThread(transitionItemObject)   
            utils.log('Tokens after launch of ' + transitionItemObject.getName() + ' ' + self.petriNet.PrintTokenList(self.transitionName))
            msg = tokenList.dump('-------Running ' + transitionItemObject.getName() + ' ID: ' + transitionItemObject.getId() + ' Active Transitions ' + str(self.petriNet.getTotalActive()))
            utils.log(msg, 'trace_' + str(utils.sessionID)+'.txt')
            # Run the transition as independently as possible
            transitionItemObject.runTopLevel()
        finally:
            pass
        
    def addActiveThread(self, obj):
        self.activeThreads[obj.getId()] = obj
        
    def removeActiveThread(self, obj):
        del self.activeThreads[obj.getId()]
               
    def dumpActiveThreads(self):
        l = '' 
        main_thread = threading.currentThread()       
        for t in threading.enumerate():
            if t is main_thread or not t.getName().startswith('trans_'):
                continue            
            l += t.getName() + '(' + t.getRemainStr() + ') '
            if t.isAlive():
                l += 'Active'
            else:
                l += 'Dead'
            l += '\n'
        utils.log('Threads:\n' + l + '\n')

    def Fire(self, tokenList, reqPropertyValues = {}):
        try:
            self.tmLock.acquire()
            self.dumpActiveThreads()
            transitionItemObject = TransitionItemFactory.getObject(self.transitionName, self)
            transitionItemObject.setTransitionMaster(self)
            transitionItemObject.setTokenList(self.getPetriNet().getTokenList())
            utils.log('Firing ' + transitionItemObject.getName() + ' ID: ' + transitionItemObject.getId())
            self.launchTransitionItemObject(transitionItemObject, reqPropertyValues)
        finally:
            self.tmLock.release()
        
    def getName(self):
        return self.transitionName
    
    def getTransitionItemsRunning(self):
        return self.transitionItemsRunning

    def getId(self):
        return str(self.id)

class TransitionItemFactory(object):
    @staticmethod
    def getObject(transitionName, transitionMaster):
        if transitionName == 'split':
            obj = Split()
        if transitionName == 'combine':
            obj = Combine()
        if transitionName == 'birth':
            obj = Birth()
        if transitionName == 'predation':
            obj = Predation()
        if transitionName == 'death':
            obj = Death()
        if transitionName == 'production':
            obj = Production()
        if transitionName == 'deathH':
            obj = DeathH()
        if transitionName == 'deathV':
            obj = DeathV()
        if transitionName == 'deathI':
            obj = DeathI()
        if transitionName == 'infection':
            obj = Infection()
        if transitionName == 'lims':
            obj = Lims()
        if transitionName == 'dispenser':
            obj = Dispenser()
        if transitionName == 'incubatorIn':
            obj = IncubatorIn()
        if transitionName == 'incubatorOut':
            obj = IncubatorOut()
        if transitionName == 'plateHub':
            obj = PlateHub()
        if transitionName == 'dispenser':
            obj = Dispenser()

        threadid = transitionMaster.getPetriNet().getRound()
        obj.setId (threadid)
        obj.setName (transitionName + '_' + str(threadid))
        obj.setTransitionMaster(transitionMaster)
        return obj

class TransitionItem():
    tiLock = Lock()
    stepsRequired = 3
    stepsRemain = stepsRequired
    errorCode = 0
    properties = {}
    store = None
    thisID = None
    def getName(self):
        return self.transitionName

    def setName(self, transitionName):
        self.transitionName = transitionName

    def getTransitionMaster(self):
        return self.transitionMaster

    def setTransitionMaster(self, transitionMaster):
        self.transitionMaster = transitionMaster

    def setTokenList(self, tokenList):
        self.tokenList = tokenList

    def getTokenList(self):
        return self.tokenList

    def getId(self):
        return str(self.thisID)

    def getRemain(self):
        return self.stepsRemain

    def getErrorCode(self):
        return self.errorCode

    def getRemainStr(self):
        return str(self.stepsRemain) + '/' + str(self.stepsRequired)

    def setProperty(self, prop, value):
        if prop == None or value == None:
            utils.logTrace('Attempt to set illegal property ' + repr(prop) + ' value: ' + repr(value))
        if prop in self.properties:
            old = ''
            if self.properties[prop] != None:
                old = self.properties[prop]
            utils.log('Replacing ' + prop + ' old value: ' + old + ' new value ' + value)
        self.properties[prop] = value
    
    def getProperty(self, prop):
        if prop in self.properties:
            return self.properties[prop]
        return None
    
    def getProperties(self):
        return self.properties
    
    def setId(self, thisID):
        self.thisID = thisID

    def setStore(self, store):
        self.store = store
        
    def getEnabledProperties(self):
        return {}
    
    def complete(self):
        self.getTransitionMaster().completeTransitionItemObject(self)
        

    def cycleResult(self):
        if self.stepsRemain <= 0:
            return 0
        randomComplete = randrange(10)
        randomComplete = 8
        if randomComplete <= 2:
            self.errorCode = randomComplete
            return -1
        if randomComplete >= 7:
            self.stepsRemain -= 1
            utils.log(self.getName() + ' completed a step ' + self.getRemainStr())
            if self.stepsRemain <= 0:
                return 0
        return self.stepsRemain

    def runTopLevel(self):
        utils.log('Entry TransitionItem.runTopLevel ' + threading.currentThread().getName())
        self.start()
        utils.log('Exit TransitionItem.runTopLevel ' + threading.currentThread().getName())

    # simulated run method
    def runSimulate(self):
        utils.log('Entry ' + self.getName() + '.run ' + repr(os.getpid()) + ' ' + threading.currentThread().getName())
        while self.getRemain() > 0:
            #time.sleep(2)
            if self.cycleResult() <= 0:
                return

    # default run method
    def run(self):
        utils.log('Entry ' + self.getName() + '.run ' + repr(os.getpid()) + ' ' + threading.currentThread().getName())
        while self.getRemain() > 0:
            #time.sleep(2)
            if self.cycleResult() <= 0:
                self.getTransitionMaster().completeTransitionItemObject(self)
                #utils.log('Exit ' + self.getName() + ' ' + repr(os.getpid()) + ' ' + threading.currentThread().getName())
                #exit()

class Split(TransitionItem, threading.Thread):
    pass

class Combine(TransitionItem, threading.Thread):
    def run(self):
        super(Combine, self).complete()
class IncubatorIn(TransitionItem, threading.Thread):
    pass

class Lims(TransitionItem, threading.Thread):
    def run(self):
        super(Lims, self).runSimulate()
        # Do the work
        
        #post processing
        properties = {}
        tokens = self.getTokenList().getTokensByOwnerAndSpec('ap', self, properties, lockedState=True)
        if tokens == None or len(tokens) == 0:
            utils.logTrace('No Assay Plate barcode')
        tokenApInProcess = tokens[0]
        barcodeAP = tokenApInProcess.getProperty('barcodeAP')
        properties = {}
        tokens = self.getTokenList().getTokensByOwnerAndSpec('sp', None, properties, lockedState=False)
        numreq = 3
        for token in tokens:
            color = token.getProperty('color')
            if color == 'free':
                token.setProperty('barcodeAP', barcodeAP)
                token.setProperty('prevTransition', 'lims')
                token.setProperty('color', 'reserved')
                numreq -= 1
                if numreq <= 0:
                    break
        
        #Complete transition
        super(Lims, self).complete()
        utils.log('Exit ' + self.getName() + ' ' + repr(os.getpid()) + ' ' + threading.currentThread().getName())
        exit()

class Dispenser(TransitionItem, threading.Thread):
    def run(self):
        super(Dispenser, self).runSimulate()
        #post process                
        properties = {}
        tokens = self.getTokenList().getTokensByOwnerAndSpec('ap', self, properties, lockedState=True)
        tokenAP = tokens[0]
        properties = {'barcodeAP' : tokenAP.getProperty('barcodeAP')}
        tokens = self.getTokenList().getTokensByOwnerAndSpec('sp', self, properties, lockedState=True)
        if len(tokens) == 0:
            utils.log('Cannot find allocated sp token in Dispenser')
            # For debugging
            tokens = self.getTokenList().getTokensByOwnerAndSpec('sp', self, properties, lockedState=True)
        tokenCompleted = tokens[0]
        tokenCompleted.removeProperty('barcodeAP')        
        tokenCompleted.removeProperty('color')
        #Get remaining reserved but not allocated source plates before completing transition and adding locked sp
        tokens = self.getTokenList().getTokensByOwnerAndSpec('sp', None, properties, lockedState=False)
            
        #Complete transition
        #CAREFUL - Attempts to override the petri model by changing the color of a token must be done after completeTransitionItemObject
        complete = False
        if len(tokens) == 0:
            complete = True
        self.getTransitionMaster().completeTransitionItemObject(self)
        if complete:
            tokenAP.setProperty('color', 'complete')
        utils.log('Exit ' + self.getName() + ' ' + repr(os.getpid()) + ' ' + threading.currentThread().getName())
        exit()
        return True

class IncubatorOut(TransitionItem, threading.Thread):
    pass

class PlateHub(TransitionItem, threading.Thread):
    def run(self):
        super(PlateHub, self).run()
        pass

class Birth(TransitionItem, threading.Thread):
    pass

class Predation(TransitionItem, threading.Thread):
    pass

class Death(TransitionItem, threading.Thread):
    pass

class Production(TransitionItem, threading.Thread):
    pass

class DeathH(TransitionItem, threading.Thread):
    pass

class DeathI(TransitionItem, threading.Thread):
    pass

class DeathV(TransitionItem, threading.Thread):
    pass

class Infection(TransitionItem, threading.Thread):
    pass

class DosingNet(object):
    def __init__(self, tokenList, assayPlates):
        self.tokenList = tokenList
        self.assayPlates = assayPlates
        self.assignSourceBarcodes()
        self.assignAssayBarcodes()
        
    def assignSourceBarcodes(self):
        sourcePlates = self.tokenList.getTokensByOwnerAndSpec('sp', transitionOwnerObject=None, properties={}, lockedState=False)
        barcode = 0
        for sourcePlateToken in sourcePlates:
            sourcePlateToken.setProperty('barcodeSP', str(barcode))
            sourcePlateToken.setProperty('color', 'free')
            barcode += 1

    def assignAssayBarcodes(self):
        assayPlateTokens = self.tokenList.getTokensByOwnerAndSpec('ap', transitionOwnerObject=None, properties={}, lockedState=False)
        barcode = 0
        for assayPlateToken in assayPlateTokens:
            assayPlateToken.setProperty('barcodeAP', self.assayPlates[barcode][0])
            barcode += 1

class PetriNet(object):
    # constructor
    def __init__(self, transitionSpecs):
        self.stateNames = {}
        self.transitionSpecs = transitionSpecs
        self.store = None
        self.round = 0
        self.transitionMasters = self.InitializeTransitions(transitionSpecs)
        
    def dump(self, initialTokenAssignments):
        msg = '\n'
        for transition in self.transitionSpecs:
            msg += transition[0] + '\n'
            msg += '\tInbound Tokens\n'
            for inbound in transition[1]:
                msg += '\t\t' + inbound[0] + '\t' + repr(inbound[1]) + '\t' + repr(inbound[2]) + '\n'
            msg += '\tOutbound Tokens\n'
            for outbound in transition[2]:
                    msg += '\t\t' + outbound[0] + '\t' + repr(outbound[1]) + '\t' + repr(outbound[2]) + '\n'
            if len(transition[3].items()) > 0:
                msg += '\tProperties\n'
                for prop,value in transition[3].items():
                        msg += '\t\t' + repr(prop) + ': ' + repr(value) + '\n'
                    
        msg += 'Initial Tokens\n'
        for tokenName,properties in initialTokenAssignments.items():
                msg += '\t' + tokenName + ': ' + repr(properties) + '\n'        
        #print msg
        return msg
            
    def getTotalActive(self):
        n = 0
        for transitionName in self.transitionMasters.keys():
            transitionMaster = self.transitionMasters[transitionName]
            n += len(transitionMaster.getTransitionItemsRunning())
        return n

    def InitializeTransitions(self, transitionSpecs):
        transitionMasters = {}
        for (transitionName, requiredTokensByState, deliveredTokensByState, properties) in transitionSpecs:
            transitionMaster = TransitionMaster(transitionName, self, properties)
            for stateTokenSpec in requiredTokensByState:
                self.SetRequiredTokens(transitionMaster.requiredTokensByState, stateTokenSpec)
                self.stateNames[stateTokenSpec[0]] = stateTokenSpec[0]
            for stateTokenSpec in deliveredTokensByState:
                self.SetRequiredTokens(transitionMaster.deliveredTokensByState, stateTokenSpec)
                self.stateNames[stateTokenSpec[0]] = stateTokenSpec[0]
            transitionMasters[transitionName] = transitionMaster
        return transitionMasters 

    def SetRequiredTokens(self, requiredTokenByStateName, stateTokenSpec):
        if len(stateTokenSpec) != 3:
            utils.log('Bad token spec for ' + requiredTokenByStateName + ' ' + repr(stateTokenSpec))
        stateName = stateTokenSpec[0]
        properties = stateTokenSpec[2]
        requiredTokens = stateTokenSpec[1]
        requiredTokenByStateName[stateName] = [requiredTokens, properties]

    def PrintHeader(self):
        a = '<State: unlocked(total, locked),>*, Transition'
        utils.log(a)
        
    def getTokenList(self):
        return self.tokenList
           
    def getRound(self):
        return self.round
    
    def getStore(self):
        return self.store
    
    def RunSimulation(self, iterations, tokenList, assayPlates=[]): 
        # Initialize
        self.PrintHeader()  # prints e.g. "H, O, H2O"
        self.tokenList = tokenList
        if assayPlates != None:
            dosingNet = DosingNet(self.tokenList, assayPlates)
            self.store = dosingNet
        utils.log(self.PrintTokenList('Initial')) # prints e.g. "3, 5, 2"
        # Run the engine
        idle = 0
        for i in range(iterations):
            self.round = i
            utils.log('--- Round ' + str(i))
            runnableTransitionData = self.getRunnableTransitionData()
            self.idle()
            if len(runnableTransitionData) == 0:
                if idle > 3:
                    utils.log('Nothing to do')
                idle += 1
                #time.sleep(1)
                continue 
            idle = 0
            transitionName = self.FireOneRule(runnableTransitionData)
            utils.log('--- Completed ' + transitionName + ' round ' + str(i) + ' iterations')

    def idle(self):
        res = False
        for transitionName in self.transitionMasters.keys():
            transitionMaster = self.transitionMasters[transitionName]
            for transitionItemObject in transitionMaster.getTransitionItemsRunning():
                completed = transitionItemObject.cycleResult()  
                if completed < 0: return True
                if completed == 0: res = True         
        return res
        
    def EnabledTransitions(self):
        res = {}
        for transitionName in self.transitionMasters.keys():
            transitionMaster = self.transitionMasters[transitionName]
            enabled, requiredProperties = transitionMaster.IsEnabled(self.tokenList)
            if enabled:
                if not transitionName in res:
                    res[transitionName] = []
                res[transitionName].append(requiredProperties)
        return res

    def getRunnableTransitionData(self):
        return self.EnabledTransitions()

    def FireOneRule(self, runnableTransitionData):
        if len(runnableTransitionData) > 0:
            transitionName, reqPropertyValues = self.SelectRandom(runnableTransitionData) # Make intelligent decision - yes or no
            transitionMaster = self.transitionMasters[transitionName]
            transitionMaster.Fire(self.tokenList, reqPropertyValues) # Modify token assignments
        return transitionMaster.getName()

    def SelectRandom(self, items):
        utils.log('Selecting from ' + repr(items.keys()))
        randomIndex = randrange(len(items.keys()))
        transitionName = items.keys()[randomIndex]
        return transitionName, items[transitionName]

    def PrintTokenList(self, transitionName):
        l = ''
        th = 0
        to = 0
        for stateName in sorted(self.stateNames.keys()):
            locked = self.tokenList.getNumLocked(stateName)
            unlocked = self.tokenList.getNumUnlocked(stateName, {})
            total = self.tokenList.getNumTokens(stateName)
            if stateName == 'H2O':
                th += 2 * total
                to += 1 * total
            if stateName == 'O':
                to += 1 * total
            if stateName == 'H':
                th += 1 * total
            l += stateName + ': ' + str(unlocked) + '(' + str(total) + ',' + str(locked) + '), '
        l += ' ' + transitionName + ' result'
        #if th + to != 20:
            #utils.log("H2O count wrong")
        return l
        #utils.log(l + ' ' + transitionName + ' result')

# now build a Petri net for two opposite transitions: 
# combine: formation of water molecule
# split: dissociation of water molecule 

assayPlates = []
if True:
# combine: 2H + 1O -> 1H2O
# split: 1H2O -> 2H + 1O 
# label, tokens in, tokens out
    specs = (
             ("combine", [["H",{},2],["O",{},1]], [["H2O",{},1]], {}),
             ("split", [["H2O",{},1]], [["H",{},2],["O",{},1]], {})
             )
    initialTokenAssignments = {"H": [5, {'attr1' : 'a'}], "O": [3, {'attr2' : 'b'}], "H2O": [4, {'attr3' : 'c'}]}
    petriNet = PetriNet(specs)

if False:
    specs = (
             ("incubatorIn", [ ["runSlot",{},1],["arm",{},1], ["ap", {'color' : 'new'},1]], [["arm",{},1],["ap", {'color' : 'inProcess'},1]], {}),
             ("lims", [["arm",{},1], ["ap", {'color' : 'inProcess'},1]], [["arm",{},1], ["ap", {'color' : 'waiting for source'},1]], {}),
             ("plateHub", [["arm",{},1], ["ap", {'color' : 'waiting for source'},1],["sp",{'color' : 'reserved'},1]], [["arm",{},1],["ap", {'color' : 'dose'},1], ["sp",{'color' : 'dosing'},1]], {'barcodeAP' : ['match']}),
             ("dispenser", [["arm",{},1],["ap", {'color' : 'dose'},1],["sp",{'color' : 'dosing'},1]], [["arm",{},1],["ap",{'color' : 'waiting for source'},1],["sp",{'color' : 'free'},1]], {'barcodeAP' : ['match']}),
             ("incubatorOut", [["arm",{},1], ["ap", {'color' : 'complete'},1]], [["arm",{},1], ["runSlot",{},1]], {}),
             )
    
    inventory = Inventory('assayPlates.db')
    inventory.reset()
    inventory.testLoad('ZLCS000', 4, 'platehub1', 5, 10)
    assayPlates = inventory.availableAssayPlates()
    
    
    initialTokenAssignments = {"ap": [len(assayPlates), {'color' : 'new'}], "arm": [1,{}], "runSlot": [2,{}], "sp":[12,{}]}
    utils.resetLog('trace_' + str(utils.sessionID)+'.txt')
    petriNet = PetriNet(specs)

if False:
    specs = (
             ("lims", [["arm",1], ["runSlot",1], ["ap",1]], [["arm",1], ["ap",1]], {}),
             ("dispenser", [["ap",1],["arm",1],["sp",1]], [["ap",1],["arm",1]], {'barcodeAP' : None})
             )
    initialTokenAssignments = {"ap": [5, {}], "arm": [1,{}], "runSlot": [1,{}], "sp":[0,{}]}
    petriNet = PetriNet(specs)

if False:
    specs = (
             ("birth", [["Rabbit",1]], [["Rabbit",2]], {}),
             ("predation", [["Rabbit",1],["Wolf",1]], [["Wolf",2]], {}),
             ("death", [["Wolf",1]], [], {})
             )
    initialTokenAssignments = {"Rabbit": 50, "Wolf": 3}
    petriNet = PetriNet(specs)

if False:
    specs = (
             ("production", [], [["Healthy",1]], {}),
             ("deathH", [["Healthy",1]], [], {}),
             ("deathI", [["Infected",1]], [], {}),
             ("deathV", [["Virion",1]], [], {}),
             ("infection", [["Healthy",1],["Virion",1]], [["Infected",1]], {}),
             ("production", [["Infected",1]], [["Infected",1],["Virion",1]], {})
             )
    initialTokenAssignments = {"Healthy": 50, "Infected": 3, "Virion": 3}
    petriNet = PetriNet(specs)

tokenList = TokenList(initialTokenAssignments)
msg = petriNet.dump(initialTokenAssignments)
utils.log(msg, 'trace_' + str(utils.sessionID)+'.txt')
steps = 90
petriNet.RunSimulation(steps, tokenList, assayPlates)

"""
H, O, H2O, Transition
5, 3, 4, split
7, 4, 3, combine
5, 3, 4, split
7, 4, 3, combine
5, 3, 4, combine
3, 2, 5, combine
1, 1, 6, split
3, 2, 5, combine
1, 1, 6, split
3, 2, 5, combine
1, 1, 6, split
3, 2, 5, combine
1, 1, 6, split
3, 2, 5, combine
1, 1, 6, split
3, 2, 5, split
5, 3, 4, split
7, 4, 3, combine
5, 3, 4, split
7, 4, 3, split
9, 5, 2, iterations completed
"""