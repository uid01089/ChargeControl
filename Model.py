
from enum import Enum
from PythonLib.Mqtt import Mqtt
import logging
import json

logger = logging.getLogger('Model')


class GoEchargerCarStatus(Enum):
    Unknown = 0
    Idle = 1
    Charging = 2
    WaitCar = 3
    Complete = 4
    Error = 4


class Model:
    def __init__(self, mqttClient: Mqtt) -> None:
        self.mqttClient = mqttClient

        self.loadPower = None
        self.pcs_pv_total_power = None
        self.soc = None

        self.loadingPower1 = None
        self.loadingPower2 = None
        self.loadingPower3 = None
        self.status = None

    def setup(self) -> None:
        self.mqttClient.subscribeIndependentTopic('/house/basement/ess/essinfo_home/statistics/load_power', self.__receiveLoadPower)
        self.mqttClient.subscribeIndependentTopic('/house/basement/ess/essinfo_home/statistics/pcs_pv_total_power', self.__receivePcsPvTotalPower)
        self.mqttClient.subscribeIndependentTopic('/house/basement/ess/essinfo_common/BATT/soc', self.__receiveSoc)
        self.mqttClient.subscribeIndependentTopic('/house/garage/go-eCharger/226305/nrg', self.__receiveNrg)
        self.mqttClient.subscribeIndependentTopic('/house/garage/go-eCharger/226305/car', self.__receiveCar)

    def __receiveLoadPower(self, payload: str) -> None:
        try:
            self.loadPower = int(float(payload))
        except BaseException:
            logging.exception('')

    def __receivePcsPvTotalPower(self, payload: str) -> None:
        try:
            self.pcs_pv_total_power = int(payload)
        except BaseException:
            logging.exception('')

    def __receiveSoc(self, payload: str) -> None:
        try:
            self.soc = float(payload)
        except BaseException:
            logging.exception('')

    def __receiveNrg(self, payload: str) -> None:
        try:
            jsonVar = json.loads(payload)
            self.loadingPower1 = int(jsonVar[7])
            self.loadingPower2 = int(jsonVar[8])
            self.loadingPower3 = int(jsonVar[9])
        except BaseException:
            logging.exception('')

    def __receiveCar(self, payload: str) -> None:
        try:
            # Unknown/Error=0, Idle=1, Charging=2, WaitCar=3, Complete=4, Error=5
            self.status = GoEchargerCarStatus(int(payload))

        except BaseException:
            logging.exception('')

    def isModelConsistent(self) -> bool:
        return True \
            and self.loadPower is not None\
            and self.pcs_pv_total_power is not None\
            and self.soc is not None\
            and self.loadingPower1 is not None\
            and self.loadingPower2 is not None\
            and self.loadingPower3 is not None\
            and self.status is not None

    def currentEGOChargingPower(self) -> int:
        return self.loadingPower1 + self.loadingPower2 + self.loadingPower3

    def calcAvailablePower(self) -> int:
        availablePowerForLoading = 0
        if self.isModelConsistent():

            # Load power contains the power for home including the E-Go charging power.
            # Charging power has to subtracted

            neededPowerForHome = (-1 * self.loadPower) - self.currentEGOChargingPower()  # loadPower is negative, consumption of home power
            availablePowerForLoading = self.pcs_pv_total_power - neededPowerForHome

        return availablePowerForLoading

    def getSoc(self) -> float:
        return self.soc

    def getStatus(self) -> GoEchargerCarStatus:
        return self.status

    def getLoadingPower1(self) -> int:
        return self.loadingPower1

    def getLoadingPower2(self) -> int:
        return self.loadingPower2

    def getLoadingPower3(self) -> int:
        return self.loadingPower3
