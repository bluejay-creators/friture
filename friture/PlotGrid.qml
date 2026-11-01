import QtQuick 2.15
import QtQuick.Layouts 1.15
import QtQuick.Shapes 1.15
import Friture 1.0

Item {
    id: plotGrid

    SystemPalette { id: systemPalette; colorGroup: SystemPalette.Active }

    property double lineWidth: 1
    // Local patch (2026-09-13): `button` equals the plot background on Linux
    // (Fusion + GTK palette, both #fcfcfc), which made every grid line invisible.
    property color lineColor: systemPalette.dark

    required property ScaleDivision vertical_scale_division
    property bool show_minor_vertical: false
    required property ScaleDivision horizontal_scale_division
    property bool show_minor_horizontal: false

    // QML docs discourage the use of multiple Shape objects. But the Repeater cannot be used inside Shape.
    // Ticks may carry their own grid style (sargam scale): Sa and Pa anchor the
    // grid in colour and double width, the rest are grey and thin.
    Repeater {
        model: vertical_scale_division.logicalMajorTicks

        Shape {
            y: (1. - modelData.logicalValue) * plotGrid.height

            ShapePath {
                strokeWidth: modelData.gridWidth > 0 ? modelData.gridWidth * lineWidth : lineWidth
                strokeColor: modelData.gridColor !== "" ? modelData.gridColor : lineColor
                fillColor: "transparent"
                scale: Qt.size(plotGrid.width, 1)

                PathMove { x: 0; y: 0 }
                PathLine { x: 1; y: 0 }
            }
        }
    }

    Repeater {
        model: show_minor_vertical ? vertical_scale_division.logicalMinorTicks : []

        Shape {
            y: (1. - modelData.logicalValue) * plotGrid.height

            ShapePath {
                strokeWidth: modelData.gridWidth > 0 ? modelData.gridWidth * lineWidth : lineWidth
                strokeColor: modelData.gridColor !== "" ? modelData.gridColor : lineColor
                fillColor: "transparent"
                scale: Qt.size(plotGrid.width, 1)

                PathMove { x: 0; y: 0 }
                PathLine { x: 1; y: 0 }
            }
        }
    }

    // QML docs discourage the use of multiple Shape objects. But the Repeater cannot be used inside Shape.
    Repeater {
        model: horizontal_scale_division.logicalMajorTicks

        Shape {
            x: modelData.logicalValue * plotGrid.width

            ShapePath {
                strokeWidth: lineWidth
                strokeColor: lineColor
                fillColor: "transparent"
                scale: Qt.size(1, plotGrid.height)

                PathMove { x: 0; y: 0 }
                PathLine { x: 0; y: 1 }
            }
        }
    }

    // QML docs discourage the use of multiple Shape objects. But the Repeater cannot be used inside Shape.
    Repeater {
        model: show_minor_horizontal ? horizontal_scale_division.logicalMinorTicks : []

        Shape {
            x: modelData.logicalValue * plotGrid.width

            ShapePath {
                strokeWidth: lineWidth
                strokeColor: lineColor
                fillColor: "transparent"
                scale: Qt.size(1, plotGrid.height)

                PathMove { x: 0; y: 0 }
                PathLine { x: 0; y: 1 }
            }
        }
    }
}