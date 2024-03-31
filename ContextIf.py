
from abc import ABC, abstractmethod
from Charge import Charge
from Model import Model
from PythonLib.Scheduler import Scheduler
from PythonLib.Mqtt import Mqtt


class ContextIf(ABC):

    @abstractmethod
    def getScheduler(self) -> Scheduler:
        pass

    @abstractmethod
    def getMqttClient(self) -> Mqtt:
        pass

    @abstractmethod
    def getTimeCharge(self) -> Charge:
        pass

    @abstractmethod
    def getPVSurPlusCharge(self) -> Charge:
        pass

    @abstractmethod
    def getModel(self) -> Model:
        pass
