"""EQ settings as a preset file of ADI-2 Remote."""

import unittest

from commander.conversion import presetfile as R
from commander.device import models
from commander.device.simulator import DEMO_DUMP, DEMO_PRESETS, SimulatedAdi2

OUT, LEFT, RIGHT = 3, 4, 5
# preset 1 of the demo, Living Neutral, as the preset file of an ADI-2 Pro of revision 0
LIVING_NEUTRAL = (
    '\t<ADI-2PRO>\n'
    '\t\t<General>\n'
    '\t\t\t<val e="Version" v="2"/>\n'
    '\t\t\t<val e="Revision" v="0"/>\n'
    '\t\t</General>\n'
    '\t\t<EQPreset1Left>\n'
    '\t\t\t<val e="EQEnable" v="15.00,"/>\n'
    '\t\t\t<val e="EQBand1Type" v="0.00,"/>\n'
    '\t\t\t<val e="EQBand1Gain" v="-6.00,"/>\n'
    '\t\t\t<val e="EQBand1Freq" v="38.00,"/>\n'
    '\t\t\t<val e="EQBand1Q" v="4.50,"/>\n'
    '\t\t\t<val e="EQBand2Gain" v="-4.50,"/>\n'
    '\t\t\t<val e="EQBand2Freq" v="57.00,"/>\n'
    '\t\t\t<val e="EQBand2Q" v="5.00,"/>\n'
    '\t\t\t<val e="EQBand3Gain" v="-3.00,"/>\n'
    '\t\t\t<val e="EQBand3Freq" v="112.00,"/>\n'
    '\t\t\t<val e="EQBand3Q" v="3.50,"/>\n'
    '\t\t\t<val e="EQBand4Gain" v="0.00,"/>\n'
    '\t\t\t<val e="EQBand4Freq" v="5000.00,"/>\n'
    '\t\t\t<val e="EQBand4Q" v="1.00,"/>\n'
    '\t\t\t<val e="EQBand5Type" v="1.00,"/>\n'
    '\t\t\t<val e="EQBand5Gain" v="0.00,"/>\n'
    '\t\t\t<val e="EQBand5Freq" v="10000.00,"/>\n'
    '\t\t\t<val e="EQBand5Q" v="1.00,"/>\n'
    '\t\t\t<val e="BassTrebleEn" v="0.00,"/>\n'
    '\t\t\t<val e="EQBassGain" v="0.00,"/>\n'
    '\t\t\t<val e="EQBassFreq" v="85.00,"/>\n'
    '\t\t\t<val e="EQBassQ" v="0.90,"/>\n'
    '\t\t\t<val e="EQTrebleGain" v="0.00,"/>\n'
    '\t\t\t<val e="EQTrebleFreq" v="6500.00,"/>\n'
    '\t\t\t<val e="EQTrebleQ" v="0.70,"/>\n'
    '\t\t\t<val e="DualEQ" v="1.00,"/>\n'
    '\t\t\t<val e="EQ Preset Select" v="0.00,"/>\n'
    '\t\t\t<val e="Load BT w. EQ" v="1.00,"/>\n'
    '\t\t</EQPreset1Left>\n'
    '\t\t<EQPreset1Right>\n'
    '\t\t\t<val e="EQEnable" v="0.00,"/>\n'
    '\t\t\t<val e="EQBand1Type" v="0.00,"/>\n'
    '\t\t\t<val e="EQBand1Gain" v="-4.50,"/>\n'
    '\t\t\t<val e="EQBand1Freq" v="41.00,"/>\n'
    '\t\t\t<val e="EQBand1Q" v="4.00,"/>\n'
    '\t\t\t<val e="EQBand2Gain" v="-5.50,"/>\n'
    '\t\t\t<val e="EQBand2Freq" v="57.00,"/>\n'
    '\t\t\t<val e="EQBand2Q" v="5.50,"/>\n'
    '\t\t\t<val e="EQBand3Gain" v="-2.00,"/>\n'
    '\t\t\t<val e="EQBand3Freq" v="118.00,"/>\n'
    '\t\t\t<val e="EQBand3Q" v="3.00,"/>\n'
    '\t\t\t<val e="EQBand4Gain" v="0.00,"/>\n'
    '\t\t\t<val e="EQBand4Freq" v="5000.00,"/>\n'
    '\t\t\t<val e="EQBand4Q" v="1.00,"/>\n'
    '\t\t\t<val e="EQBand5Type" v="1.00,"/>\n'
    '\t\t\t<val e="EQBand5Gain" v="0.00,"/>\n'
    '\t\t\t<val e="EQBand5Freq" v="10000.00,"/>\n'
    '\t\t\t<val e="EQBand5Q" v="1.00,"/>\n'
    '\t\t</EQPreset1Right>\n'
    '\t\t<PresetNames>\n'
    '\t\t\t<val e="EQPresetName1" v="Living Neutral"/>\n'
    '\t\t</PresetNames>\n'
    '\t</ADI-2PRO>\n'
)


def output_with_slot(n):
    """The state of Line Out after selecting preset n of the demo, with Bass/Treble off and Load B/T on."""
    slot = SimulatedAdi2.from_dump(DEMO_DUMP, presets=DEMO_PRESETS).slots[n]
    state = {(LEFT if a == 13 else RIGHT, i): v for (a, i), v in slot["vals"].items()}
    state.update({(OUT, 11): slot["dual"], (LEFT, 20): 0, (LEFT, 27): 1})
    return state


class PresetFile(unittest.TestCase):
    def test_as_written_for_the_preset(self):
        self.assertEqual(R.write(output_with_slot(1), OUT, "Living Neutral", models.PRO, 0), LIVING_NEUTRAL)

    def test_the_model_and_its_revision(self):
        state = output_with_slot(1)
        head = R.write(state, OUT, "x", models.DAC, 2).splitlines()[:5]
        self.assertEqual(head, ["	<ADI-2DAC>", "		<General>", '			<val e="Version" v="2"/>',
                                '			<val e="Revision" v="2"/>', "		</General>"])
        self.assertTrue(R.write(state, OUT, "x", models.PRO_24, 1).startswith("	<ADI-24PROSE>"))
        self.assertNotIn("Revision", R.write(state, OUT, "x", models.PRO))           # not known: left out

    def test_incomplete(self):
        state = output_with_slot(1)
        del state[(RIGHT, 18)]
        with self.assertRaises(ValueError):
            R.write(state, OUT, "x")

    def test_a_name_the_device_takes(self):
        self.assertEqual(R.name_of("HD 800 S (Harman)"), "HD 800 S (Harm")
        self.assertEqual(R.name_of("Brüel_Kjær"), "BrelKjr")
        self.assertEqual(R.name_of("äöü"), "")


if __name__ == "__main__":
    unittest.main()
