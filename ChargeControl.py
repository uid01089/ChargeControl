from enum import Enum
import logging
import time

from Model import GoEchargerCarStatus, Model
from PythonLib.AnalogSchmittTrigger import AnalogSchmittTrigger
from PythonLib.DateUtil import DateTimeUtilities


import paho.mqtt.client as pahoMqtt
from PythonLib.JsonUtil import JsonUtil
from PythonLib.Mqtt import Mqtt
from PythonLib.Scheduler import Scheduler
from PythonLib.StringUtil import StringUtil

logger = logging.getLogger('ChargeControl')

AMP_MAX = 16
V_GRID = 230
NR_PHASES = 1
MIN_CURRENT = 6
SWITCH_ON_CURRENT = 7
ESS_ACCU_THRESHOLD_PROZ = 50


class ControllerState (Enum):
    SwitchIntoIdle = 0
    Idle = 1
    WaitTillChargingStarts = 2
    Charging = 3
    Finished = 4


class Module:
    def __init__(self) -> None:
        self.scheduler = Scheduler()
        self.mqttClient = Mqtt("koserver.iot", "/house/agents/ChargeControl", pahoMqtt.Client("ChargeControl"))
        self.analogSchmittTrigger = AnalogSchmittTrigger(1)
        self.model: Model = None

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

    def loop(self) -> None:
        self.scheduler.loop()


class ChargeControl:

    def __init__(self, module: Module) -> None:
        self.mqttClient = module.getMqttClient()
        self.scheduler = module.getScheduler()
        self.model = module.getModel()
        self.schmittTrigger = module.getAnalogSchmittTrigger()

        self.chargedEnergy3 = None
        self.totalChargedEnergy3 = None
        self.temperature = None

        self.rebootCtr = None
        self.allowCharging = None
        self.allowedAmpereToCharge = None

        self.prioEssLoading = False
        self.chargeCurrent = 0

        self.controllerState = ControllerState.SwitchIntoIdle

    def setup(self) -> None:

        self.mqttClient.subscribeIndependentTopic('/house/garage/go-eCharger/226305/wh', self.__receiveWh)
        self.mqttClient.subscribeIndependentTopic('/house/garage/go-eCharger/226305/eto', self.__receiveEto)
        self.mqttClient.subscribeIndependentTopic('/house/garage/go-eCharger/226305/rbc', self.__receiveRbc)
        self.mqttClient.subscribeIndependentTopic('/house/garage/go-eCharger/226305/alw', self.__receiveAlw)

        self.scheduler.scheduleEach(self.__keepAlive, 10000)
        self.scheduler.scheduleEach(self.__loop, 60 * 1000)

        self.model.setup()

    def __receiveWh(self, payload: str) -> None:
        try:
            self.chargedEnergy3 = (float(payload) / 1000)
        except BaseException:
            logging.exception('')

    def __receiveEto(self, payload: str) -> None:
        try:
            self.totalChargedEnergy3 = (float(payload) / 1000)
        except BaseException:
            logging.exception('')

    def __receiveRbc(self, payload: str) -> None:
        try:
            self.rebootCtr = int(payload)
        except BaseException:
            logging.exception('')

    def __receiveAlw(self, payload: str) -> None:
        try:
            self.allowCharging = StringUtil.isBoolean(payload)
        except BaseException:
            logging.exception('')

    def __keepAlive(self) -> None:
        self.mqttClient.publishIndependentTopic('/house/agents/ChargeControl/heartbeat', DateTimeUtilities.getCurrentDateString())
        self.mqttClient.publishIndependentTopic('/house/agents/ChargeControl/subscriptions', JsonUtil.obj2Json(self.mqttClient.getSubscriptionCatalog()))

    def __loop(self) -> None:
        if self.model.isModelConsistent():
            self.control()
            self.mqttClient.publishIndependentTopic('/house/agents/ChargeControl/data/chargeCurrent', self.chargeCurrent)
            self.mqttClient.publishIndependentTopic('/house/agents/ChargeControl/data/loadingPower1', self.model.getLoadingPower1())
            self.mqttClient.publishIndependentTopic('/house/agents/ChargeControl/data/loadingPower2', self.model.getLoadingPower2())
            self.mqttClient.publishIndependentTopic('/house/agents/ChargeControl/data/loadingPower3', self.model.getLoadingPower3())
            self.mqttClient.publishIndependentTopic('/house/agents/ChargeControl/data/doCharging', self.__isCharging())
            self.mqttClient.publishIndependentTopic('/house/agents/ChargeControl/data/prioEssLoading', self.prioEssLoading)
            self.mqttClient.publishIndependentTopic('/house/agents/ChargeControl/data/essAccuThreshold', ESS_ACCU_THRESHOLD_PROZ)
            self.mqttClient.publishIndependentTopic('/house/agents/ChargeControl/data/nrPhases', NR_PHASES)
            self.mqttClient.publishIndependentTopic('/house/agents/ChargeControl/data/minCurrent', MIN_CURRENT)
            self.mqttClient.publishIndependentTopic('/house/agents/ChargeControl/data/switchOnCurrent', SWITCH_ON_CURRENT)
            self.mqttClient.publishIndependentTopic('/house/agents/ChargeControl/data/controllerStateName', self.controllerState.name)
            self.mqttClient.publishIndependentTopic('/house/agents/ChargeControl/data/eGoChargerStateName', self.model.getStatus().name)
            self.mqttClient.publishIndependentTopic('/house/agents/ChargeControl/data/controllerState', self.controllerState.value)
            self.mqttClient.publishIndependentTopic('/house/agents/ChargeControl/data/eGoChargerState', self.model.getStatus().value)
            self.mqttClient.publishIndependentTopic('/house/agents/ChargeControl/data/availablePowerForCharging', self.model.calcAvailablePower())

    def calcChargeCurrent(self, prioEssLoading: bool, availableCurrent: int) -> int:

        chargeCurrent = 0

        if prioEssLoading:

            # the ESS-Battery shall be loaded. Limit the charge current to the switchOnCurrent. Rest is going into the ESS-Battery.
            chargeCurrent = min(availableCurrent, SWITCH_ON_CURRENT)
        else:
            # No special mode, just use the available current
            chargeCurrent = availableCurrent

        # Not more then 16 Ampere!
        return min(chargeCurrent, AMP_MAX)

    def control(self) -> None:
        prioEssLoading = self.model.getSoc() < ESS_ACCU_THRESHOLD_PROZ

        # prioEssLoading: Limit chargeCurrent to this.switchOnCurrent
        # !prioEssLoading (Car-Loading): as much as available

        availablePowerForCharging = self.model.calcAvailablePower()
        availableCurrentForCharging = (availablePowerForCharging / NR_PHASES) / V_GRID
        finalCalculatedCurrentForCharging = self.calcChargeCurrent(prioEssLoading, availableCurrentForCharging)
        chargeCurrent = 0

        if availablePowerForCharging > 0:

            # We have additional power available. Do charging

            if self.controllerState == ControllerState.SwitchIntoIdle:
                self.controllerState = ControllerState.Idle
            # falls through

            elif self.controllerState == ControllerState.Idle:

                if self.model.getStatus() != GoEchargerCarStatus.Unknown:

                    # we have to reach switchOnCurrent
                    if availableCurrentForCharging >= SWITCH_ON_CURRENT:

                        self.controllerState = ControllerState.WaitTillChargingStarts
                        chargeCurrent = self.schmittTrigger.getFilteredValue(finalCalculatedCurrentForCharging)

            elif self.controllerState == ControllerState.WaitTillChargingStarts:
                if self.model.getStatus() == GoEchargerCarStatus.Charging:
                    self.controllerState = ControllerState.Charging

            elif self.controllerState == ControllerState.Charging:

                # If status of wallbox is not in charging state anymore
                if self.model.getStatus() != GoEchargerCarStatus.Charging:
                    self.controllerState = ControllerState.SwitchIntoIdle

                else:
                    # we are in charging mode, have to stay above minCurrent
                    if availableCurrentForCharging >= MIN_CURRENT:

                        # go on charging with current calculated charging current
                        chargeCurrent = self.schmittTrigger.getFilteredValue(finalCalculatedCurrentForCharging)

                    else:

                        # Oh no, we are under minCurrent. Usually we shall stop charging

                        if prioEssLoading:

                            # ESS loading has higher priority, stop charging of the car
                            self.controllerState = ControllerState.SwitchIntoIdle

                        else:

                            # Everything for the car
                            # we are over 80%, we can go on loading with this.minCurrent, even minCurrent is not reached
                            # ESS us discharged
                            chargeCurrent = max(self.schmittTrigger.getFilteredValue(finalCalculatedCurrentForCharging), MIN_CURRENT)
                            # chargeCurrent =
                            # Math.max(this.piController.updateWithValue(currentEGOChargingPower,
                            # Math.max(finalCalculatedCurrentForCharging, this.minCurrent),
                            # this.minCurrent)

        else:
            # No charging
            self.controllerState = ControllerState.SwitchIntoIdle

        # Rounding and converting to integer values
        chargeCurrent = round(min(chargeCurrent, AMP_MAX))

        self.prioEssLoading = prioEssLoading
        self.chargeCurrent = chargeCurrent

    def __isCharging(self) -> bool:
        return (self.controllerState == ControllerState.WaitTillChargingStarts) or (self.controllerState == ControllerState.Charging)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('ChargeControl').setLevel(logging.DEBUG)

    module = Module()
    module.setup()

    ChargeControl(module).setup()

    print("ChargeControl running")

    while (True):
        module.loop()
        time.sleep(0.25)


if __name__ == '__main__':
    main()
