import paho.mqtt.client as pahoMqtt
from ContextIf import ContextIf
from Model import Model
from PVSurPlusCharge import PVSurPlusCharge

from PythonLib.AnalogSchmittTrigger import AnalogSchmittTrigger
from PythonLib.Scheduler import Scheduler
from PythonLib.Mqtt import Mqtt
from TimeCharge import TimeCharge


class Context(ContextIf):
    def __init__(self) -> None:
        self.scheduler = Scheduler()
        self.mqttClient = Mqtt("koserver.iot", "/house/agents/ChargeControl", pahoMqtt.Client("ChargeControl"))
        self.analogSchmittTrigger = AnalogSchmittTrigger(1)
        self.model: Model = None
        self.pvSurPlusCharge = PVSurPlusCharge(self)
        self.timeCharge = TimeCharge(self)

    def getAnalogSchmittTrigger(self) -> AnalogSchmittTrigger:
        return self.analogSchmittTrigger

    def getModel(self) -> Model:
        if not self.model:
            self.model = Model(self.mqttClient)
        return self.model

    def getScheduler(self) -> Scheduler:
        return self.scheduler

    def getMqttClient(self) -> Mqtt:
        return self.mqttClient

    def setup(self) -> None:
        self.scheduler.scheduleEach(self.mqttClient.loop, 500)
        self.timeCharge.setup()
        self.pvSurPlusCharge.setup()

    def loop(self) -> None:
        self.scheduler.loop()

    def getTimeCharge(self) -> TimeCharge:
        return self.timeCharge

    def getPVSurPlusCharge(self) -> PVSurPlusCharge:
        return self.pvSurPlusCharge
