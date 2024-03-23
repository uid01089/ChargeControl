from datetime import datetime
from ContextIf import ContextIf

INPUT_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
NR_PHASES = 3
CURRENT = 16


class TimeCharge:
    def __init__(self, context: ContextIf) -> None:
        self.mqttClient = context.getMqttClient()
        self.scheduler = context.getScheduler()
        self.startTime = None
        self.endTime = None
        self.doCharging = False
        self.current = CURRENT
        self.nrPhases = NR_PHASES

    def setup(self) -> None:
        self.mqttClient.subscribe('control/TimeCharge/StartTime', self.__StartTime)
        self.mqttClient.subscribe('control/TimeCharge/EndTime', self.__EndTime)

        self.scheduler.scheduleEach(self.__keepAlive, 60 * 1000)

    def __keepAlive(self) -> None:
        self.mqttClient.publish('data/TimeCharge/isCharging', self.doCharging)
        self.mqttClient.publish('data/TimeCharge/Time', str(datetime.now()))
        self.mqttClient.publish('data/TimeCharge/Current', self.current)
        self.mqttClient.publish('data/TimeCharge/NrPhases', self.nrPhases)

    def loop(self) -> None:
        pass

    def __StartTime(self, payload: str) -> None:
        self.startTime = datetime.strptime(payload, INPUT_FORMAT)
        self.mqttClient.publish('data/TimeCharge/StartTime', payload)

    def __EndTime(self, payload: str) -> None:
        self.endTime = datetime.strptime(payload, INPUT_FORMAT)
        self.mqttClient.publish('data/TimeCharge/EndTime', payload)

    def getNrPhases(self) -> int:
        return self.nrPhases

    def getCurrent(self) -> int:
        return self.current

    def isCharging(self) -> bool:
        if self.endTime and self.startTime:
            self.doCharging = self.startTime <= datetime.now() <= self.endTime
        self.doCharging = False

        return self.doCharging
