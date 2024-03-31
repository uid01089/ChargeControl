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

        self.scheduler.scheduleEach(self.loop, 60 * 1000)

    def loop(self) -> None:
        self.mqttClient.publish('data/TimeCharge/isCharging', self.doCharging)
        self.mqttClient.publish('data/TimeCharge/Time', str(datetime.now()))
        self.mqttClient.publish('data/TimeCharge/Current', self.current)
        self.mqttClient.publish('data/TimeCharge/NrPhases', self.nrPhases)
        self.mqttClient.publish('data/TimeCharge/StartTime', self.startTime)
        self.mqttClient.publish('data/TimeCharge/EndTime', self.endTime)

    def __StartTime(self, payload: str) -> None:
        self.startTime = payload
        self.mqttClient.publish('data/TimeCharge/StartTime', self.startTime)

    def __EndTime(self, payload: str) -> None:
        self.endTime = payload
        self.mqttClient.publish('data/TimeCharge/EndTime', self.endTime)

    def getNrPhases(self) -> int:
        return self.nrPhases

    def getCurrent(self) -> int:
        return self.current

    def isCharging(self) -> bool:

        if self.endTime and self.startTime:

            startTime = datetime.strptime(self.startTime, INPUT_FORMAT)
            endTime = datetime.strptime(self.endTime, INPUT_FORMAT)

            self.doCharging = startTime <= datetime.now() <= endTime
        else:

            self.doCharging = False

        return self.doCharging
