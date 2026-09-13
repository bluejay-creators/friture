import QtQuick 2.15
import QtQuick.Window 2.2
import QtQuick.Layouts 1.15
import QtQuick.Shapes 1.15
import Friture 1.0
import "plotItemColors.js" as PlotItemColors

Item {
    id: container
    anchors.fill: parent

    Plot {
        id: plot
        scopedata: viewModel
        // Local patch (2026-09-13): note readout on the left, frequency scale on the right
        verticalScaleOnRight: true

        anchors.fill: null // override 'fill: parent' in Plot.qml
        anchors.left: pitchItem.right
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom

        Repeater {
            model: plot.scopedata.plot_items

            PlotCurve {
                anchors.fill: parent
                color: PlotItemColors.color(index)
                curve: modelData
            }
        }
    }

    Rectangle {
        id: pitchItem

        implicitWidth: pitchCol.implicitWidth
        implicitHeight: parent ? parent.height : 0

        anchors.left: parent.left

        SystemPalette { id: systemPalette; colorGroup: SystemPalette.Active }
        color: systemPalette.window

        ColumnLayout {
            id: pitchCol
            spacing: 0

            FontMetrics {
                id: fontMetrics
                font.pointSize: 14
                font.bold: true
            }

            Text {
                id: note
                text: plot.scopedata.note
                textFormat: Text.PlainText
                font.pointSize: 14
                font.bold: true
                leftPadding: 6
                horizontalAlignment: Text.AlignLeft
                // Local patch (2026-09-13): fixed width sized to the widest sargam
                // label, so the plot doesn't resize (jitter) as the note changes.
                Layout.preferredWidth: fontMetrics.boundingRect("Dha''  G♯5").width + leftPadding
                Layout.minimumWidth: Layout.preferredWidth
                Layout.alignment: Qt.AlignTop | Qt.AlignLeft
                color: systemPalette.windowText
            }

            Text {
                id: pitchHz
                text: plot.scopedata.pitch
                textFormat: Text.PlainText
                font.pointSize: 14
                font.bold: true
                leftPadding: 6
                horizontalAlignment: Text.AlignLeft
                Layout.preferredWidth: fontMetrics.boundingRect("000.0").width
                Layout.alignment: Qt.AlignTop | Qt.AlignLeft
                color: systemPalette.windowText
            }

            Text {
                id: pitchUnit
                text: plot.scopedata.pitch_unit
                textFormat: Text.PlainText
                leftPadding: 6
                horizontalAlignment: Text.AlignLeft
                Layout.alignment: Qt.AlignTop | Qt.AlignLeft
                color: systemPalette.windowText
            }
        }
    }
}
