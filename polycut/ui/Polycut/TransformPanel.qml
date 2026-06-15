import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Polycut

// Transform inspector section — scale only (the rest of Transform is MVP-2; no
// up-axis control, that's handled in SketchUp). A scale multiplier plus source
// and target unit selectors; the export bakes the result and declares the unit.
// (design-system.md §2, §6)
ColumnLayout {
    id: panel
    Layout.fillWidth: true
    spacing: Theme.sectionGap

    Section {
        title: "transform"

        // scale multiplier
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.gap

            Text {
                text: "scale"
                color: Theme.fg2
                font.family: Theme.fontUi
                font.pixelSize: Theme.fontSmall
            }
            TextField {
                id: multiplierInput
                Layout.fillWidth: true
                horizontalAlignment: TextInput.AlignRight
                color: Theme.fg0
                font.family: Theme.fontMono
                font.pixelSize: Theme.fontBase
                selectByMouse: true
                inputMethodHints: Qt.ImhFormattedNumbersOnly
                validator: DoubleValidator {
                    bottom: 0.0001
                    decimals: 4
                    notation: DoubleValidator.StandardNotation
                }
                text: Number(processor.scaleMultiplier).toLocaleString(Qt.locale("en_US"), 'f', 2)
                onActiveFocusChanged: if (!activeFocus)
                    text = Qt.binding(function () {
                        return Number(processor.scaleMultiplier).toLocaleString(Qt.locale("en_US"), 'f', 2);
                    })
                onAccepted: {
                    var v = parseFloat(text);
                    if (!isNaN(v) && v > 0)
                        processor.scaleMultiplier = v;
                    focus = false;
                }
                background: Rectangle {
                    radius: Theme.rMd
                    color: Theme.bg2
                    border.color: multiplierInput.activeFocus ? Theme.teal : Theme.hairline
                    border.width: Theme.borderThin
                }
            }
            Text {
                text: "×"
                color: Theme.fg3
                font.family: Theme.fontMono
                font.pixelSize: Theme.fontBase
            }
        }

        // source → target units
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.gap

            UnitSelect {
                Layout.fillWidth: true
                unit: processor.sourceUnit
                onUnitPicked: (u) => processor.sourceUnit = u
            }
            Text {
                text: "→"
                color: Theme.fg3
                font.family: Theme.fontMono
                font.pixelSize: Theme.fontBase
            }
            UnitSelect {
                Layout.fillWidth: true
                unit: processor.targetUnit
                onUnitPicked: (u) => processor.targetUnit = u
            }
        }

        // resulting real-world size — the §7 delta for scale
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.gapXs
            Text {
                text: "size"
                color: Theme.fg3
                font.family: Theme.fontUi
                font.pixelSize: Theme.fontSmall
            }
            Text {
                text: processor.scaledDimensions
                color: Theme.fg2
                font.family: Theme.fontMono
                font.pixelSize: Theme.fontSmall
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignRight
            }
        }
    }
}
