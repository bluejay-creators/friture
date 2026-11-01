import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal, pyqtProperty # type: ignore  # type: ignore
from PyQt6.QtGui import QColor
from PyQt6.QtQuick import QQuickItem, QSGGeometryNode, QSGGeometry, QSGVertexColorMaterial, QSGNode # type: ignore

# Local patch (2026-09-25): vertices carry their own colour so a curve can be
# shaded per sample (the pitch tracker shades by intonation). Curves without a
# colour array simply repeat their flat colour on every vertex.
VERTEX_DTYPE = np.dtype([("x", np.float32), ("y", np.float32),
                         ("r", np.uint8), ("g", np.uint8), ("b", np.uint8), ("a", np.uint8)])

from friture.curve import Curve

class PlotCurve(QQuickItem):
    colorChanged = pyqtSignal()
    curveChanged = pyqtSignal()

    def __init__(self, parent = None):
        super().__init__(parent)

        self.setFlag(QQuickItem.Flag.ItemHasContents, True)

        self._x_array = np.array([0])
        self._y_array = np.array([0])

        self._color = QColor("black")
        self._curve = Curve()
        self._material = None

    @pyqtProperty(QColor, notify=colorChanged)
    def color(self):
        return self._color

    @color.setter # type: ignore
    def color(self, color):
        if color != self._color:
            self._color = color
            self.update()
            self.colorChanged.emit()

    @pyqtProperty(QObject, notify=curveChanged)
    def curve(self):
        return self._curve

    @curve.setter # type: ignore
    def curve(self, curve):
        if curve != self._curve:
            self._curve = curve
            if self._curve is not None:
                self._curve.data_changed.connect(self.update)

            self.update()
            self.curveChanged.emit()

    def updatePaintNode(self, paint_node, update_data):
        # Local patch (2026-09-13): NaN samples are gaps. A GL line strip cannot
        # have gaps (NaN vertices render as lines to the plot edge, which is what
        # the pitch tracker showed on every silent frame), so draw independent
        # segments between consecutive finite points instead.
        x = np.asarray(self.curve.x_array() * self.width(), dtype=np.float32)
        y = np.asarray(self.curve.y_array() * self.height(), dtype=np.float32)
        valid = np.isfinite(x) & np.isfinite(y)
        pair_ok = valid[:-1] & valid[1:]
        idx = np.flatnonzero(pair_ok)
        size = 2 * idx.size

        if paint_node is None:
            paint_node = QSGGeometryNode()

            geometry = QSGGeometry(QSGGeometry.defaultAttributes_ColoredPoint2D(), size)
            geometry.setLineWidth(2)
            geometry.setDrawingMode(QSGGeometry.DrawingMode.DrawLines)
            paint_node.setGeometry(geometry)
            paint_node.setFlag(QSGNode.Flag.OwnsGeometry)

            # keep a Python reference: without it the material is collected and
            # the render thread paints from freed memory
            self._material = QSGVertexColorMaterial()
            paint_node.setMaterial(self._material)
            paint_node.setFlag(QSGNode.Flag.OwnsMaterial)
            paint_node.markDirty(QSGNode.DirtyStateBit.DirtyMaterial)

        else:
            geometry = paint_node.geometry()
            geometry.allocate(size) # geometry will be marked as dirty below

        if size > 0:
            # ideally we would use geometry.vertexDataAsPoint2D
            # but there is a bug with the returned sip.array
            # whose total size is not interpreted correctly
            # `memoryview(geometry.vertexDataAsPoint2D()).nbytes` does not take itemsize into account
            vertices = geometry.vertexData()
            vertices.setsize(VERTEX_DTYPE.itemsize * size)

            polygon_array = np.frombuffer(vertices, dtype=VERTEX_DTYPE).reshape(-1, 2)  # segment, endpoint
            polygon_array["x"][:, 0] = x[idx]
            polygon_array["y"][:, 0] = y[idx]
            polygon_array["x"][:, 1] = x[idx + 1]
            polygon_array["y"][:, 1] = y[idx + 1]

            colors = self.curve.color_array()
            for channel, flat in zip(("r", "g", "b", "a"), (self._color.red(), self._color.green(),
                                                            self._color.blue(), self._color.alpha())):
                polygon_array[channel][:, :] = flat
            if colors is not None and len(colors) == x.size:
                for c, channel in enumerate(("r", "g", "b", "a")):
                    polygon_array[channel][:, 0] = colors[idx, c]
                    polygon_array[channel][:, 1] = colors[idx + 1, c]

        paint_node.markDirty(QSGNode.DirtyStateBit.DirtyGeometry)

        return paint_node
