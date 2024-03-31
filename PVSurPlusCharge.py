from enum import Enum
import logging
from Charge import Charge
from ContextIf import ContextIf
from Model import GoEchargerCarStatus


logger = logging.getLogger('PVSurPlusCharge')

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


class PVSurPlusCharge(Charge):

    def __init__(self, context: ContextIf) -> None:
        self.mqttClient = context.getMqttClient()
        self.model = context.getModel()
        self.schmittTrigger = context.getAnalogSchmittTrigger()
        self.scheduler = context.getScheduler()

        self.prioEssLoading = False
        self.chargeCurrent = 0

        self.controllerState = ControllerState.SwitchIntoIdle

    def setup(self) -> None:

        self.model.setup()
        self.scheduler.scheduleEach(self.loop, 1000)

    def loop(self) -> None:
        if self.model.isModelConsistent():
            self.__control()

        self.mqttClient.publish('data/PVSurPlusCharge/chargeCurrent', self.chargeCurrent)
        self.mqttClient.publish('data/PVSurPlusCharge/doCharging', self.isCharging())
        self.mqttClient.publish('data/PVSurPlusCharge/prioEssLoading', self.prioEssLoading)
        self.mqttClient.publish('data/PVSurPlusCharge/essAccuThreshold', ESS_ACCU_THRESHOLD_PROZ)
        self.mqttClient.publish('data/PVSurPlusCharge/nrPhases', NR_PHASES)
        self.mqttClient.publish('data/PVSurPlusCharge/minCurrent', MIN_CURRENT)
        self.mqttClient.publish('data/PVSurPlusCharge/switchOnCurrent', SWITCH_ON_CURRENT)
        self.mqttClient.publish('data/PVSurPlusCharge/controllerStateName', self.controllerState.name)
        self.mqttClient.publish('data/PVSurPlusCharge/controllerState', self.controllerState.value)
        self.mqttClient.publish('data/PVSurPlusCharge/availablePowerForCharging', self.model.calcAvailablePower())
        self.mqttClient.publish('data/PVSurPlusCharge/isModelConsistent', self.model.isModelConsistent())
        self.mqttClient.publish('data/PVSurPlusCharge/isModelConsistent/why', self.model.whyIsModelConsistent())

    def __control(self) -> None:
        self.prioEssLoading = self.model.getSoc() < ESS_ACCU_THRESHOLD_PROZ

        # prioEssLoading: Limit chargeCurrent to this.switchOnCurrent
        # !prioEssLoading (Car-Loading): as much as available

        availablePowerForCharging = self.model.calcAvailablePower()
        availableCurrentForCharging = (availablePowerForCharging / NR_PHASES) / V_GRID
        finalCalculatedCurrentForCharging = self.__calcChargeCurrent(self.prioEssLoading, availableCurrentForCharging)
        self.chargeCurrent = self.schmittTrigger.getFilteredValue(finalCalculatedCurrentForCharging)

        if not availablePowerForCharging > 0:
            # No charging
            self.controllerState = ControllerState.SwitchIntoIdle

        match(self.controllerState):

            case  ControllerState.SwitchIntoIdle:
                self.controllerState = ControllerState.Idle

            case  ControllerState.Idle:
                if self.model.getEgoChargerCarStatus() != GoEchargerCarStatus.Unknown:

                    # we have to reach switchOnCurrent
                    if availableCurrentForCharging >= SWITCH_ON_CURRENT:

                        self.controllerState = ControllerState.WaitTillChargingStarts

            case  ControllerState.WaitTillChargingStarts:
                if self.model.getEgoChargerCarStatus() == GoEchargerCarStatus.Charging:
                    self.controllerState = ControllerState.Charging

            case  ControllerState.Charging:
                # If status of wallbox is not in charging state anymore
                if self.model.getEgoChargerCarStatus() != GoEchargerCarStatus.Charging:
                    self.controllerState = ControllerState.SwitchIntoIdle

                else:
                    # we are in charging mode, have to stay above minCurrent
                    if availableCurrentForCharging >= MIN_CURRENT:

                        # go on charging with current calculated charging current
                        pass

                    else:

                        # Oh no, we are under minCurrent. Usually we shall stop charging

                        if self.prioEssLoading:

                            # ESS loading has higher priority, stop charging of the car
                            self.controllerState = ControllerState.SwitchIntoIdle

                        else:

                            # Everything for the car
                            # we are over 80%, we can go on loading with this.minCurrent, even minCurrent is not reached
                            # ESS us discharged
                            self.chargeCurrent = max(self.chargeCurrent, MIN_CURRENT)
                            # chargeCurrent =
                            # Math.max(this.piController.updateWithValue(currentEGOChargingPower,
                            # Math.max(finalCalculatedCurrentForCharging, this.minCurrent),
                            # this.minCurrent)

            case  ControllerState.Finished:
                pass

        # Rounding and converting to integer values
        self.chargeCurrent = round(min(self.chargeCurrent, AMP_MAX))

    def __calcChargeCurrent(self, prioEssLoading: bool, availableCurrent: int) -> int:

        chargeCurrent = 0

        if prioEssLoading:

            # the ESS-Battery shall be loaded. Limit the charge current to the switchOnCurrent. Rest is going into the ESS-Battery.
            chargeCurrent = min(availableCurrent, SWITCH_ON_CURRENT)
        else:
            # No special mode, just use the available current
            chargeCurrent = availableCurrent

        # Not more then 16 Ampere!
        return min(chargeCurrent, AMP_MAX)

    def isCharging(self) -> bool:
        return self.controllerState == ControllerState.WaitTillChargingStarts \
            or self.controllerState == ControllerState.Charging

    def getNrPhases(self) -> int:
        return NR_PHASES

    def getCurrent(self) -> int:
        return self.chargeCurrent
