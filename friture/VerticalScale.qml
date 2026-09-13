import QtQuick 2.15
import QtQuick.Window 2.2
import QtQuick.Layouts 1.15
import QtQuick.Shapes 1.15
import Friture 1.0

Item {
    id: yscaleColumn

    SystemPalette { id: systemPalette; colorGroup: SystemPalette.Active }

    required property ScaleDivision scale_division

    // Local patch (2026-09-13): `mirrored` puts the axis line on the LEFT edge with
    // ticks and labels extending to the right, for a scale placed right of the plot.
    property bool mirrored: false

    readonly property int majorTickLength: 8
    readonly property int minorTickLength: 4
    readonly property int tickDir: mirrored ? 1 : -1

    property int tickLabelMaxWidth: Math.max(maxTextWidth(scale_division.logicalMajorTicks),
                                             maxLabelWidth(scale_division.logicalMinorTicks))

    implicitWidth: tickLabelMaxWidth + 1 + majorTickLength

    property double topOverflow: fontMetrics.height / 2

    function maxTextWidth(majorTicks) {
        var maxWidth = 0
        for (var i = 0; i < majorTicks.length; i++) {
            // a tick with its own label (sargam scale) shows that instead of the number
            var text = majorTicks[i].label !== "" ? majorTicks[i].label : majorTicks[i].value
            var textWidth = fontMetrics.boundingRect(text).width;
            if (textWidth > maxWidth) {
                maxWidth = textWidth;
            }
        }
        return Math.ceil(maxWidth)
    }

    // minor ticks may carry labels too (sargam scale)
    function maxLabelWidth(ticks) {
        var maxWidth = 0
        for (var i = 0; i < ticks.length; i++) {
            if (ticks[i].label === "") continue
            var textWidth = smallFontMetrics.boundingRect(ticks[i].label).width;
            if (textWidth > maxWidth) {
                maxWidth = textWidth;
            }
        }
        return Math.ceil(maxWidth)
    }

    FontMetrics {
        id: fontMetrics
    }

    FontMetrics {
        id: smallFontMetrics
        font.pointSize: fontMetrics.font.pointSize * 0.85
    }

    // axis line: right edge normally, left edge when mirrored
    Shape {
        x: mirrored ? 0 : yscaleColumn.width

        ShapePath {
            strokeWidth: 1
            strokeColor: systemPalette.windowText
            fillColor: "transparent"

            PathMove { x: 0; y: 0 }
            PathLine { x: 0; y: yscaleColumn.height }
        }
    }

    // QML docs discourage the use of multiple Shape objects. But the Repeater cannot be used inside Shape.
    Repeater {
        model: scale_division.logicalMajorTicks

        Shape {
            x: mirrored ? 0 : yscaleColumn.width
            y: (1. - modelData.logicalValue) * yscaleColumn.height

            ShapePath {
                strokeWidth: 1
                strokeColor: systemPalette.windowText
                fillColor: "transparent"

                PathMove { x: 0; y: 0 }
                PathLine { x: tickDir * majorTickLength; y: 0 }
            }
        }
    }

    Item {
        id: tickLabels
        // labels sit inside the axis line, past the tick marks
        x: mirrored ? majorTickLength + 1 : 0
        width: tickLabelMaxWidth

        // QML docs discourage the use of multiple Shape objects. But the Repeater cannot be used inside Shape.
        Repeater {
            model: scale_division.logicalMajorTicks

            Item {
                width: tickLabelMaxWidth
                y: (1. - modelData.logicalValue) * yscaleColumn.height

                Text {
                    id: tickLabel
                    text: modelData.label !== "" ? modelData.label : modelData.value
                    font.bold: modelData.label !== ""
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.left: mirrored ? parent.left : undefined
                    anchors.right: mirrored ? undefined : parent.right
                    verticalAlignment: Text.AlignVCenter
                    horizontalAlignment: mirrored ? Text.AlignLeft : Text.AlignRight
                    color: modelData.color !== "" ? modelData.color : systemPalette.windowText
                }
            }
        }

        // labelled minor ticks (sargam scale): every semitone gets its swara
        Repeater {
            model: scale_division.logicalMinorTicks

            Item {
                width: tickLabelMaxWidth
                y: (1. - modelData.logicalValue) * yscaleColumn.height
                visible: modelData.label !== ""

                Text {
                    text: modelData.label
                    font.pointSize: fontMetrics.font.pointSize * 0.85
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.left: mirrored ? parent.left : undefined
                    anchors.right: mirrored ? undefined : parent.right
                    verticalAlignment: Text.AlignVCenter
                    horizontalAlignment: mirrored ? Text.AlignLeft : Text.AlignRight
                    color: modelData.color !== "" ? modelData.color : systemPalette.windowText
                }
            }
        }
    }

    // QML docs discourage the use of multiple Shape objects. But the Repeater cannot be used inside Shape.
    Repeater {
        model: scale_division.logicalMinorTicks

        Shape {
            x: mirrored ? 0 : yscaleColumn.width
            y: (1. - modelData.logicalValue) * yscaleColumn.height

            ShapePath {
                strokeWidth: 1
                strokeColor: systemPalette.windowText
                fillColor: "transparent"

                PathMove { x: 0; y: 0 }
                PathLine { x: tickDir * minorTickLength; y: 0 }
            }
        }
    }
}
