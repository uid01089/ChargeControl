from enum import Enum
import logging
import time

from Context import Context
from ContextIf import ContextIf
from PythonLib.StringUtil import StringUtil
from PythonLib.DateUtil import DateTimeUtilities


from PythonLib.JsonUtil import JsonUtil


logger = logging.getLogger('ChargeControl')


class OverallChargeControlState (Enum):
    Manuel = 0
    TimeBased = 1
    PvBased = 2
    ChangeIntoPvBased = 3
    ChangeIntoTimeBased = 4
    ChangeIntoManuel = 5


class ChargeControl:

    def __init__(self, context: ContextIf) -> None:
        self.mqttClient = context.getMqttClient()
        self.scheduler = context.getScheduler()
        self.context = context
        self.automaticMode = False
        self.overAllState = OverallChargeControlState.Manuel

    def setup(self) -> None:

        self.mqttClient.subscribe('control/AutomaticMode[On,Off]', self.__setMode)

        self.scheduler.scheduleEach(self.__keepAlive, 10000)
        self.scheduler.scheduleEach(self.__loop, 60 * 1000)

    def __keepAlive(self) -> None:
        self.mqttClient.publishIndependentTopic('/house/agents/ChargeControl/heartbeat', DateTimeUtilities.getCurrentDateString())
        self.mqttClient.publishIndependentTopic('/house/agents/ChargeControl/subscriptions', JsonUtil.obj2Json(self.mqttClient.getSubscriptionCatalog()))

    def __phaseSwitchStr(self, phase: int) -> str:
        match (phase):
            case 1: return 'Force_1'
            case 3: return 'Force_3'
            case _: return 'Auto'

    def __loop(self) -> None:

        if not self.automaticMode:
            if self.overAllState != OverallChargeControlState.Manuel:
                self.overAllState = OverallChargeControlState.ChangeIntoManuel

        match(self.overAllState):
            case OverallChargeControlState.Manuel:
                if self.automaticMode:
                    self.overAllState = OverallChargeControlState.ChangeIntoPvBased

            case OverallChargeControlState.TimeBased:
                if not self.context.getTimeCharge().isCharging():
                    self.overAllState = OverallChargeControlState.ChangeIntoPvBased
                else:
                    # Stay in currernt state
                    # Charging values were already set
                    pass

            case OverallChargeControlState.PvBased:
                if self.context.getTimeCharge().isCharging():
                    self.overAllState = OverallChargeControlState.ChangeIntoTimeBased
                else:
                    # Stay in currernt state
                    charger = self.context.getPVSurPlusCharge()

                    if charger.isCharging():
                        self.mqttClient.publishOnChangeIndependentTopic('/house/agents/eGoCharger/control/Ampere',
                                                                        str(int(charger.getCurrent())))
                        self.mqttClient.publishOnChangeIndependentTopic('/house/agents/eGoCharger/control/ForceState[Neutral,Off,On]', 'On')
                    else:
                        self.mqttClient.publishOnChangeIndependentTopic('/house/agents/eGoCharger/control/ForceState[Neutral,Off,On]', 'Off')

            case OverallChargeControlState.ChangeIntoPvBased:
                self.overAllState = OverallChargeControlState.PvBased

                charger = self.context.getPVSurPlusCharge()
                self.mqttClient.publishOnChangeIndependentTopic('/house/agents/eGoCharger/control/PhaseSwitchMode[Auto,Force_1,Force_3]',
                                                                self.__phaseSwitchStr(charger.getNrPhases()))
                self.mqttClient.publishOnChangeIndependentTopic('/house/agents/eGoCharger/control/Ampere',
                                                                str(int(charger.getCurrent())))
                self.mqttClient.publishOnChangeIndependentTopic('/house/agents/eGoCharger/control/ForceState[Neutral,Off,On]', 'On')

                self.mqttClient.publishOnChangeIndependentTopic('/house/agents/Ess2Mqtt/controlT/setWinter[On,Off]', 'Off')

            case OverallChargeControlState.ChangeIntoTimeBased:
                self.overAllState = OverallChargeControlState.TimeBased

                charger = self.context.getTimeCharge()
                self.mqttClient.publishOnChangeIndependentTopic('/house/agents/eGoCharger/control/PhaseSwitchMode[Auto,Force_1,Force_3]',
                                                                self.__phaseSwitchStr(charger.getNrPhases()))
                self.mqttClient.publishOnChangeIndependentTopic('/house/agents/eGoCharger/control/Ampere',
                                                                str(int(charger.getCurrent())))
                self.mqttClient.publishOnChangeIndependentTopic('/house/agents/eGoCharger/control/ForceState[Neutral,Off,On]', 'Off')

                self.mqttClient.publishOnChangeIndependentTopic('/house/agents/Ess2Mqtt/controlT/setWinter[On,Off]', 'On')

            case OverallChargeControlState.ChangeIntoManuel:
                self.overAllState = OverallChargeControlState.Manuel

                self.mqttClient.publishOnChangeIndependentTopic('/house/agents/eGoCharger/control/ForceState[Neutral,Off,On]', 'Off')
                self.mqttClient.publishOnChangeIndependentTopic('/house/agents/Ess2Mqtt/controlT/setWinter[On,Off]', 'Off')

            case _:
                pass

        self.mqttClient.publish('data/OverallChargeControlState', self.overAllState.name)

    def __setMode(self, payload: str) -> None:
        self.mqttClient.publish('data/AutomaticMode', payload)
        self.automaticMode = StringUtil.isBoolean(payload)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger('ChargeControl').setLevel(logging.DEBUG)

    context = Context()
    context.setup()

    ChargeControl(context).setup()

    print("ChargeControl running")

    while (True):
        context.loop()
        time.sleep(0.25)


if __name__ == '__main__':
    main()
