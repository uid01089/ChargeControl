from enum import Enum
import logging
import time
from datetime import datetime
from pathlib import PurePath
from Model import GoEchargerCarStatus, Model
from PythonLib.AnalogSchmittTrigger import AnalogSchmittTrigger
from PythonLib.DateUtil import DateTimeUtilities


import pathlib


import paho.mqtt.client as pahoMqtt
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


class ChargeControl:

    def __init__(self, mqttClient: Mqtt, scheduler: Scheduler, model: Model, schmittTrigger: AnalogSchmittTrigger) -> None:
        self.mqttClient = mqttClient
        self.scheduler = scheduler
        self.model = model
        self.schmittTrigger = schmittTrigger

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

    def __loop(self) -> None:
        if self.model.isModelConsistent():
            self.control()
            self.mqttClient.publishIndependentTopic('/house/agents/ChargeControl/chargeCurrent', self.chargeCurrent)
            self.mqttClient.publishIndependentTopic('/house/agents/ChargeControl/loadingPower1', self.model.getLoadingPower1())
            self.mqttClient.publishIndependentTopic('/house/agents/ChargeControl/loadingPower2', self.model.getLoadingPower2())
            self.mqttClient.publishIndependentTopic('/house/agents/ChargeControl/loadingPower3', self.model.getLoadingPower3())
            self.mqttClient.publishIndependentTopic('/house/agents/ChargeControl/doCharging', self.__isCharging())
            self.mqttClient.publishIndependentTopic('/house/agents/ChargeControl/prioEssLoading', self.prioEssLoading)
            self.mqttClient.publishIndependentTopic('/house/agents/ChargeControl/essAccuThreshold', ESS_ACCU_THRESHOLD_PROZ)
            self.mqttClient.publishIndependentTopic('/house/agents/ChargeControl/nrPhases', NR_PHASES)
            self.mqttClient.publishIndependentTopic('/house/agents/ChargeControl/minCurrent', MIN_CURRENT)
            self.mqttClient.publishIndependentTopic('/house/agents/ChargeControl/switchOnCurrent', SWITCH_ON_CURRENT)
            self.mqttClient.publishIndependentTopic('/house/agents/ChargeControl/controllerState', self.controllerState.name)

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

    scheduler = Scheduler()

    mqttClient = Mqtt("koserver.iot", "/house/agents/ChargeControl", pahoMqtt.Client("ChargeControl"))
    scheduler.scheduleEach(mqttClient.loop, 500)

    model = Model(mqttClient)
    analogSchmittTrigger = AnalogSchmittTrigger(1)
    ChargeControl(mqttClient, scheduler, model, analogSchmittTrigger).setup()

    while (True):
        scheduler.loop()
        time.sleep(0.25)


if __name__ == '__main__':
    main()
