from abc import ABC, abstractmethod


class Charge(ABC):

    @abstractmethod
    def getNrPhases(self) -> int:
        pass

    @abstractmethod
    def getCurrent(self) -> int:
        pass

    @abstractmethod
    def isCharging(self) -> bool:
        pass
