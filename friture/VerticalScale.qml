import QtQuick 2.15
import QtQuick.Window 2.2
import QtQuick.Layouts 1.15
import QtQuick.Shapes 1.15
import Friture 1.0

Item {
    id: yscaleColumn

    SystemPalette { id: systemPalette; colorGroup: SystemPalette.Active }

    required property ScaleDivision scale_division

    readonly property int majorTickLength: 8
    readonly property int minorTickLength: 4

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
        id: smallFontMetrics
        font.pointSize: fontMetrics.font.pointSize * 0.85
    }

    FontMetrics {
        id: fontMetrics
    }

    Shape {
        anchors.right: yscaleColumn.right

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

        Item {
            anchors.right: yscaleColumn.right
            implicitWidth: 1 + majorTickLength

            y: (1. - modelData.logicalValue) * yscaleColumn.height

            Shape {
                anchors.right: parent.right

                ShapePath {
                    strokeWidth: 1
                    strokeColor: systemPalette.windowText
                    fillColor: "transparent"

                    PathMove { x: 0; y: 0 }
                    PathLine { x: -majorTickLength; y: 0 }
                }
            }
        }
    }

    Item {
        id: tickLabels

        // QML docs discourage the use of multiple Shape objects. But the Repeater cannot be used inside Shape.
        Repeater {
            model: scale_division.logicalMajorTicks

            Item {
                implicitWidth: tickLabelMaxWidth
                y: (1. - modelData.logicalValue) * yscaleColumn.height

                Text {
                    id: tickLabel
                    text: modelData.label !== "" ? modelData.label : modelData.value
                    font.bold: modelData.label !== ""
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.right: parent.right
                    verticalAlignment: Text.AlignVCenter
                    horizontalAlignment: Text.AlignRight
                    color: modelData.color !== "" ? modelData.color : systemPalette.windowText
                }
            }
        }

        // labelled minor ticks (sargam scale): every semitone gets its swara
        Repeater {
            model: scale_division.logicalMinorTicks

            Item {
                implicitWidth: tickLabelMaxWidth
                y: (1. - modelData.logicalValue) * yscaleColumn.height
                visible: modelData.label !== ""

                Text {
                    text: modelData.label
                    font.pointSize: fontMetrics.font.pointSize * 0.85
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.right: parent.right
                    verticalAlignment: Text.AlignVCenter
                    horizontalAlignment: Text.AlignRight
                    color: modelData.color !== "" ? modelData.color : systemPalette.windowText
                }
            }
        }
    }

    // QML docs discourage the use of multiple Shape objects. But the Repeater cannot be used inside Shape.
    Repeater {
        model: scale_division.logicalMinorTicks

        Item {
            y: (1. - modelData.logicalValue) * yscaleColumn.height
            anchors.right: parent.right
        
            Shape {
                anchors.right: parent.right

                ShapePath {
                    strokeWidth: 1
                    strokeColor: systemPalette.windowText
                    fillColor: "transparent"

                    PathMove { x: 0; y: 0 }
                    PathLine { x: -minorTickLength; y: 0 }
                }
            }
        }
    }
}