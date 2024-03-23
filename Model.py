
import logging
from enum import Enum
from PythonLib.Mqtt import Mqtt


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

        self.loadingPowerTotal = None

        self.status = None

    def setup(self) -> None:
        self.mqttClient.subscribeIndependentTopic('/house/basement/ess/essinfo_home/statistics/load_power', self.__receiveLoadPower)
        self.mqttClient.subscribeIndependentTopic('/house/basement/ess/essinfo_home/statistics/pcs_pv_total_power', self.__receivePcsPvTotalPower)
        self.mqttClient.subscribeIndependentTopic('/house/basement/ess/essinfo_common/BATT/soc', self.__receiveSoc)
        self.mqttClient.subscribeIndependentTopic('/house/agents/eGoCharger/data/PowerChargingTotal', self.__receivePowerChargingTotal)
        self.mqttClient.subscribeIndependentTopic('/house/agents/eGoCharger/data/StatusAsNumber', self.__receiveStatus)

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

    def __receivePowerChargingTotal(self, payload: str) -> None:
        try:
            self.loadingPowerTotal = float(payload)

        except BaseException:
            logging.exception('')

    def __receiveStatus(self, payload: str) -> None:
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
            and self.loadingPowerTotal is not None\
            and self.status is not None

    def calcAvailablePower(self) -> int:
        availablePowerForLoading = 0
        if self.isModelConsistent():

            # Load power contains the power for home including the E-Go charging power.
            # Charging power has to subtracted

            neededPowerForHome = (-1 * self.loadPower) - self.loadingPowerTotal  # loadPower is negative, consumption of home power
            availablePowerForLoading = self.pcs_pv_total_power - neededPowerForHome

        return availablePowerForLoading

    def getSoc(self) -> float:
        return self.soc

    def getStatus(self) -> GoEchargerCarStatus:
        return self.status
