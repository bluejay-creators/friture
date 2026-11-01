import QtQuick 2.15
import QtQuick.Window 2.2
import QtQuick.Layouts 1.15
import QtQuick.Shapes 1.15
import Friture 1.0

Rectangle {
    id: plot
    anchors.fill: parent

    SystemPalette { id: systemPalette; colorGroup: SystemPalette.Active }
    color: systemPalette.window

    required property ScopeData scopedata
    default property alias content: plotItemPlaceholder.children

    // Local patch (2026-09-13): place the vertical scale (and its axis name) to the
    // right of the plot area instead of the left. Used by the pitch tracker.
    property bool verticalScaleOnRight: false
    // Local patch (2026-10-31): float the legend over the top-right corner of the
    // plot area instead of giving it a layout column, so curves coming and going
    // (beats, tanpura) don't shift the plot or push the vertical scale away.
    property bool legendInPlot: false

    GridLayout {
        anchors.fill: parent
        rowSpacing: 2
        columnSpacing: 2

        Item {
            Layout.row: 0
            Layout.column: 2

            // spacer so that the labels of the vertical scale are not clipped
            implicitHeight: verticalScale.topOverflow
            Layout.maximumHeight: implicitHeight
        }

        Item {
            Layout.row: 1
            Layout.column: 0
            visible: plot.verticalScaleOnRight

            // spacer so that the first label of the horizontal scale is not clipped
            // when the vertical scale is on the right
            Layout.maximumWidth: implicitWidth
            implicitWidth: horizontalScale.leftOverflow
        }

        Item {
            Layout.row: 1
            Layout.column: plot.verticalScaleOnRight ? 9 : 0

            // width vs. height: childrenRect doesn't take transformations into account.
            // https://bugreports.qt-project.org/browse/QTBUG-38953
            implicitWidth: verticalAxisLabel.height
            implicitHeight: verticalAxisLabel.width

            Text {
                id: verticalAxisLabel
                text: scopedata.vertical_axis.name
                transformOrigin: Item.Center
                rotation: plot.verticalScaleOnRight ? 90 : -90
                anchors.centerIn: parent
                color: systemPalette.windowText
            }
        }

        VerticalScale {
            id: verticalScale
            Layout.row: 1
            Layout.column: plot.verticalScaleOnRight ? 8 : 1
            Layout.fillHeight: true
            mirrored: plot.verticalScaleOnRight

            scale_division: scopedata.vertical_axis.scale_division
        }

        PlotArea {
            Layout.row: 1
            Layout.column: 2
            Layout.fillHeight: true
            Layout.fillWidth: true

            vertical_axis: scopedata.vertical_axis
            horizontal_axis: scopedata.horizontal_axis

            Item {
                id: plotItemPlaceholder
                anchors.fill: parent
            }

            Rectangle {
                anchors.top: parent.top
                anchors.right: parent.right
                anchors.margins: 4
                z: 1
                width: overlayLegend.implicitWidth
                height: overlayLegend.implicitHeight
                visible: plot.legendInPlot && scopedata.show_legend && scopedata.plot_items.length > 1
                color: Qt.rgba(systemPalette.window.r, systemPalette.window.g, systemPalette.window.b, 0.85)
                border.color: systemPalette.mid
                radius: 3

                Legend {
                    id: overlayLegend
                    scopedata: plot.scopedata
                }
            }
        }

        Item {
            Layout.row: 1
            Layout.column: 3

            // spacer so that the last label of the horizontal scale is not clipped
            Layout.maximumWidth: implicitWidth
            implicitWidth: Math.max(0., horizontalScale.rightOverflow - (legend.visible ? legend.width : 0.))
        }

        Legend {
            id: legend
            Layout.row: 1
            Layout.column: 4
            Layout.alignment: Qt.AlignTop | Qt.AlignLeft
            visible: !plot.legendInPlot && scopedata.show_legend && scopedata.plot_items.length > 1

            scopedata: plot.scopedata
        }

        ColorScale {
            id: colorScale
            Layout.row: 1
            Layout.column: 5
            Layout.fillHeight: true
            visible: scopedata.show_color_axis

            scale_division: scopedata.color_axis.scale_division
        }

        Item {
            Layout.row: 1
            Layout.column: 6
            visible: scopedata.show_color_axis

            // width vs. height: childrenRect doesn't take transformations into account.
            // https://bugreports.qt-project.org/browse/QTBUG-38953
            implicitWidth: colorAxisLabel.height
            implicitHeight: colorAxisLabel.width

            Text {
                id: colorAxisLabel
                text: scopedata.color_axis.name
                transformOrigin: Item.Center
                rotation: 90
                anchors.centerIn: parent
                color: systemPalette.windowText
            }
        }

        HorizontalScale {
            id: horizontalScale
            Layout.row: 2
            Layout.column: 2
            Layout.fillWidth: true

            scale_division: scopedata.horizontal_axis.scale_division
        }

        Text {
            Layout.row: 3
            Layout.column: 2
            text: scopedata.horizontal_axis.name
            horizontalAlignment: Text.AlignHCenter
            Layout.fillWidth: true
            color: systemPalette.windowText
        }
    }
}