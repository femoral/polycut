import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Polycut

// Simplify inspector section: hero face-count delta + reduction slider with a
// live −NN% badge + an absolute target-face input. Slider and input stay in
// sync; the 5–6s decimation runs on release / accept (never mid-drag).
// (design-system.md §2, §4, §6, §7)
ColumnLayout {
    id: panel
    Layout.fillWidth: true
    spacing: Theme.sectionGap

    // the reduction the user is requesting, in percent; everything derives from it
    property int pendingPct: 0

    function targetForPct(pct) {
        return Math.max(1, Math.round(processor.originalFaceCount * (1 - pct / 100)));
    }
    function pctForTarget(faces) {
        if (processor.originalFaceCount <= 0)
            return 0;
        return Math.round((1 - faces / processor.originalFaceCount) * 100);
    }
    function commit() {
        processor.simplify(panel.targetForPct(panel.pendingPct));
    }

    // resync to the bridge's target whenever it changes — but never yank the
    // control out from under an active drag / edit.
    Connections {
        target: processor
        function onStatsChanged() {
            if (!slider.pressed && !targetInput.activeFocus)
                panel.pendingPct = panel.pctForTarget(processor.targetFaceCount);
        }
    }

    // ---- hero readout: current faces · from N original (§4, §7) ----------
    ColumnLayout {
        Layout.fillWidth: true
        spacing: Theme.gapXs

        Text {
            text: Number(processor.faceCount).toLocaleString(Qt.locale("en_US"), 'f', 0)
            color: Theme.fg0
            font.family: Theme.fontMono
            font.pixelSize: Theme.fontHero
        }
        RowLayout {
            spacing: Theme.gapXs
            Text {
                text: "faces · from"
                color: Theme.fg3
                font.family: Theme.fontUi
                font.pixelSize: Theme.fontSmall
            }
            Text {
                text: Number(processor.originalFaceCount).toLocaleString(Qt.locale("en_US"), 'f', 0)
                color: Theme.fg3
                font.family: Theme.fontMono
                font.pixelSize: Theme.fontSmall
            }
            Text {
                text: "original"
                color: Theme.fg3
                font.family: Theme.fontUi
                font.pixelSize: Theme.fontSmall
            }
        }
    }

    // ---- SIMPLIFY section -----------------------------------------------
    Section {
        title: "simplify"

        // reduction slider + live −NN% badge (§6)
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.gap

            Slider {
                id: slider
                Layout.fillWidth: true
                from: 0
                to: 95
                stepSize: 1
                value: panel.pendingPct
                onMoved: panel.pendingPct = Math.round(value)
                onPressedChanged: if (!pressed) panel.commit()

                background: Rectangle {
                    x: slider.leftPadding
                    y: slider.topPadding + slider.availableHeight / 2 - height / 2
                    width: slider.availableWidth
                    height: Theme.borderThick * 2
                    radius: height / 2
                    color: Theme.bg2
                    Rectangle {
                        width: slider.position * parent.width
                        height: parent.height
                        radius: height / 2
                        color: Theme.teal
                    }
                }
                handle: Rectangle {
                    x: slider.leftPadding + slider.position * (slider.availableWidth - width)
                    y: slider.topPadding + slider.availableHeight / 2 - height / 2
                    implicitWidth: Theme.dotSize + Theme.gapXs
                    implicitHeight: Theme.dotSize + Theme.gapXs
                    radius: width / 2
                    color: slider.pressed ? Theme.tealDim : Theme.teal
                }
            }

            // −NN% badge (mono pill, §6)
            Rectangle {
                radius: Theme.rSm
                color: Theme.bg2
                implicitHeight: Theme.chipHeight
                implicitWidth: badge.implicitWidth + Theme.chipPadH
                Text {
                    id: badge
                    anchors.centerIn: parent
                    text: "−" + panel.pendingPct + "%"
                    color: Theme.teal
                    font.family: Theme.fontMono
                    font.pixelSize: Theme.fontMicro
                }
            }
        }

        // absolute target-face input, synced with the slider
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.gap

            Text {
                text: "target"
                color: Theme.fg2
                font.family: Theme.fontUi
                font.pixelSize: Theme.fontSmall
            }
            TextField {
                id: targetInput
                Layout.fillWidth: true
                horizontalAlignment: TextInput.AlignRight
                color: Theme.fg0
                font.family: Theme.fontMono
                font.pixelSize: Theme.fontBase
                selectByMouse: true
                validator: IntValidator {
                    bottom: 1
                    top: processor.originalFaceCount
                }
                text: panel.targetForPct(panel.pendingPct)
                onActiveFocusChanged: if (!activeFocus)
                    text = Qt.binding(function () {
                        return panel.targetForPct(panel.pendingPct);
                    })
                onAccepted: {
                    var t = Math.max(1, Math.min(parseInt(text), processor.originalFaceCount));
                    panel.pendingPct = panel.pctForTarget(t);
                    processor.simplify(t);
                    focus = false;
                }
                background: Rectangle {
                    radius: Theme.rMd
                    color: Theme.bg2
                    border.color: targetInput.activeFocus ? Theme.teal : Theme.hairline
                    border.width: Theme.borderThin
                }
            }
            Text {
                text: "faces"
                color: Theme.fg3
                font.family: Theme.fontUi
                font.pixelSize: Theme.fontSmall
            }
        }
    }
}
