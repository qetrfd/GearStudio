import math
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QBrush, QPen, QPolygonF, QPainterPath, QPainter
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene, QGraphicsSimpleTextItem

def _gear_polygon(teeth: int, r_outer: float, r_root: float, phase: float = 0.0) -> QPolygonF:
    steps = max(12, 4 * int(teeth))
    pts = []
    for k in range(steps):
        ang = phase + 2.0 * math.pi * (k / steps)
        mod = k % 4
        r = r_outer if mod in (0, 1) else r_root
        pts.append(QPointF(r * math.cos(ang), r * math.sin(ang)))
    return QPolygonF(pts)

class GearItem(QGraphicsItem):
    def __init__(self, teeth: int, pitch_r: float, base_r: float, add_r: float, root_r: float, label: str):
        super().__init__()
        self.teeth = int(teeth)
        self.pitch_r = float(pitch_r)
        self.base_r = float(base_r)
        self.add_r = float(add_r)
        self.root_r = float(root_r)
        self._poly = _gear_polygon(self.teeth, self.add_r, self.root_r, phase=0.0)
        self._bbox = self._poly.boundingRect().adjusted(-18, -18, 18, 18)
        self.setTransformOriginPoint(QPointF(0, 0))
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)

        self._label_item = QGraphicsSimpleTextItem(label, self)
        self._label_item.setBrush(Qt.white)
        self._label_item.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        br = self._label_item.boundingRect()
        self._label_item.setPos(-br.width() / 2.0, -br.height() / 2.0)

    def boundingRect(self) -> QRectF:
        return self._bbox

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        outline = QPen(Qt.white)
        outline.setCosmetic(True)
        outline.setWidthF(2.0)
        painter.setPen(outline)
        painter.setBrush(Qt.transparent)
        painter.drawPolygon(self._poly)

        pen_pitch = QPen(Qt.gray)
        pen_pitch.setCosmetic(True)
        pen_pitch.setWidthF(1.2)
        pen_pitch.setStyle(Qt.DotLine)
        painter.setPen(pen_pitch)
        painter.drawEllipse(QPointF(0, 0), self.pitch_r, self.pitch_r)

        pen_base = QPen(Qt.darkGray)
        pen_base.setCosmetic(True)
        pen_base.setWidthF(1.0)
        pen_base.setStyle(Qt.DashLine)
        painter.setPen(pen_base)
        painter.drawEllipse(QPointF(0, 0), self.base_r, self.base_r)

        pen_add = QPen(Qt.darkGray)
        pen_add.setCosmetic(True)
        pen_add.setWidthF(1.0)
        painter.setPen(pen_add)
        painter.drawEllipse(QPointF(0, 0), self.add_r, self.add_r)

        hub_r = max(6.0, self.root_r * 0.18)
        pen_hub = QPen(Qt.white)
        pen_hub.setCosmetic(True)
        pen_hub.setWidthF(1.6)
        painter.setPen(pen_hub)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QPointF(0, 0), hub_r, hub_r)

class RotationArrowItem(QGraphicsItem):
    def __init__(self, radius: float, direction: int = 1):
        super().__init__()
        self.radius = float(radius)
        self.direction = 1 if direction >= 0 else -1
        self._bbox = QRectF(-self.radius - 18, -self.radius - 18, 2 * (self.radius + 18), 2 * (self.radius + 18))
        self.setZValue(1000)

    def set_direction(self, direction: int):
        d = 1 if direction >= 0 else -1
        if d != self.direction:
            self.direction = d
            self.update()

    def set_radius(self, radius: float):
        r = float(radius)
        if abs(r - self.radius) > 0.1:
            self.prepareGeometryChange()
            self.radius = r
            self._bbox = QRectF(-self.radius - 18, -self.radius - 18, 2 * (self.radius + 18), 2 * (self.radius + 18))
            self.update()

    def boundingRect(self) -> QRectF:
        return self._bbox

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        r = max(10.0, self.radius * 0.78)
        start = -35.0
        span = 260.0 * self.direction

        path = QPainterPath()
        rect = QRectF(-r, -r, 2 * r, 2 * r)
        path.arcMoveTo(rect, start)
        path.arcTo(rect, start, span)

        pen = QPen(Qt.white)
        pen.setCosmetic(True)
        pen.setWidthF(2.0)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

        end_angle = math.radians(start + span)
        tx = r * math.cos(end_angle)
        ty = -r * math.sin(end_angle)

        tang = end_angle + (math.pi / 2.0) * self.direction
        ah = 12.0
        aw = 8.0

        p0 = QPointF(tx, ty)
        p1 = QPointF(tx - ah * math.cos(tang) + aw * math.cos(tang + math.pi / 2.0),
                    ty - ah * math.sin(tang) + aw * math.sin(tang + math.pi / 2.0))
        p2 = QPointF(tx - ah * math.cos(tang) + aw * math.cos(tang - math.pi / 2.0),
                    ty - ah * math.sin(tang) + aw * math.sin(tang - math.pi / 2.0))

        painter.setBrush(Qt.white)
        painter.drawPolygon(QPolygonF([p0, p1, p2]))

class RatioTextItem(QGraphicsSimpleTextItem):
    def __init__(self, text: str):
        super().__init__(text)
        self.setBrush(Qt.white)
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setZValue(1001)

class GearTrainScene(QGraphicsScene):
    def __init__(self):
        super().__init__()
        self.setBackgroundBrush(QBrush(Qt.black))
        self.gears: list[GearItem] = []
        self.lines = []
        self.arrows: list[RotationArrowItem] = []
        self.ratio_labels: list[RatioTextItem] = []
        self.scale_px_per_unit = 18.0
        self.setSceneRect(QRectF(-200, -200, 400, 400))

    def clear_all(self):
        self.clear()
        self.gears.clear()
        self.lines.clear()
        self.arrows.clear()
        self.ratio_labels.clear()
        self.setSceneRect(QRectF(-200, -200, 400, 400))

    def add_gear(self, item: GearItem):
        self.gears.append(item)
        self.addItem(item)

    def layout_chain(self, pitch_radii: list[float]):
        if not self.gears:
            return

        x = 0.0
        for i, g in enumerate(self.gears):
            if i == 0:
                g.setPos(QPointF(0.0, 0.0))
                x = 0.0
            else:
                x += (pitch_radii[i - 1] + pitch_radii[i])
                g.setPos(QPointF(x, 0.0))

        self._draw_centerline()

        br = self.itemsBoundingRect()
        if br.isValid():
            self.setSceneRect(br.adjusted(-180, -180, 180, 180))

    def sync_overlays(self, pitch_radii: list[float], directions: list[int], ratio_texts: list[str]):
        while len(self.arrows) < len(self.gears):
            it = RotationArrowItem(radius=40.0, direction=1)
            self.arrows.append(it)
            self.addItem(it)

        while len(self.arrows) > len(self.gears):
            it = self.arrows.pop()
            self.removeItem(it)

        for i, g in enumerate(self.gears):
            r = pitch_radii[i] if i < len(pitch_radii) else g.pitch_r
            self.arrows[i].setPos(g.pos())
            self.arrows[i].set_radius(r)
            d = directions[i] if i < len(directions) else 1
            self.arrows[i].set_direction(d)

        while len(self.ratio_labels) < max(0, len(self.gears) - 1):
            it = RatioTextItem("")
            self.ratio_labels.append(it)
            self.addItem(it)

        while len(self.ratio_labels) > max(0, len(self.gears) - 1):
            it = self.ratio_labels.pop()
            self.removeItem(it)

        for i in range(1, len(self.gears)):
            a = self.gears[i - 1].pos()
            b = self.gears[i].pos()
            mid = QPointF((a.x() + b.x()) / 2.0, (a.y() + b.y()) / 2.0 - 26.0)
            txt = ratio_texts[i - 1] if i - 1 < len(ratio_texts) else ""
            self.ratio_labels[i - 1].setText(txt)
            br = self.ratio_labels[i - 1].boundingRect()
            self.ratio_labels[i - 1].setPos(mid.x() - br.width() / 2.0, mid.y() - br.height() / 2.0)

    def _draw_centerline(self):
        for ln in self.lines:
            self.removeItem(ln)
        self.lines.clear()

        if len(self.gears) < 2:
            return

        pen = QPen(Qt.darkGray)
        pen.setCosmetic(True)
        pen.setStyle(Qt.DotLine)
        pen.setWidthF(1.2)

        for i in range(1, len(self.gears)):
            a = self.gears[i - 1].pos()
            b = self.gears[i].pos()
            ln = self.addLine(a.x(), a.y(), b.x(), b.y(), pen)
            self.lines.append(ln)