from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap


@lru_cache(maxsize=1)
def application_icon() -> QIcon:
    """Return the shared SDM documentation-site brand icon."""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        px = QPixmap(size, size)
        px.fill(Qt.GlobalColor.transparent)
        painter = QPainter(px)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#55e59a"))
        radius = max(3.0, size * 0.20)
        painter.drawRoundedRect(QRectF(0.5, 0.5, size - 1.0, size - 1.0), radius, radius)
        painter.setPen(QColor("#041c0e"))
        font = QFont("Segoe UI", max(6, int(size * 0.27)))
        font.setBold(True)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, max(0.0, size * 0.005))
        painter.setFont(font)
        painter.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, "SDM")
        painter.end()
        icon.addPixmap(px)
    return icon


@lru_cache(maxsize=128)
def glyph_icon(name: str, color: str = "#dce8e2", size: int = 20) -> QIcon:
    """Create crisp vector-like icons without depending on OS emoji fonts."""
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    c = QColor(color)
    pen = QPen(c, max(1.5, size / 11), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    s = float(size)

    if name == "add":
        p.drawLine(QPointF(.5*s, .22*s), QPointF(.5*s, .78*s)); p.drawLine(QPointF(.22*s, .5*s), QPointF(.78*s, .5*s))
    elif name in {"play", "resume"}:
        path = QPainterPath(); path.moveTo(.34*s,.22*s); path.lineTo(.76*s,.5*s); path.lineTo(.34*s,.78*s); path.closeSubpath(); p.drawPath(path)
    elif name == "pause":
        p.drawLine(QPointF(.36*s,.24*s), QPointF(.36*s,.76*s)); p.drawLine(QPointF(.64*s,.24*s), QPointF(.64*s,.76*s))
    elif name == "stop":
        p.setBrush(c); p.drawRoundedRect(QRectF(.29*s,.29*s,.42*s,.42*s), .06*s,.06*s)
    elif name == "trash":
        p.drawRoundedRect(QRectF(.31*s,.32*s,.38*s,.48*s),.04*s,.04*s); p.drawLine(QPointF(.25*s,.28*s),QPointF(.75*s,.28*s)); p.drawLine(QPointF(.41*s,.2*s),QPointF(.59*s,.2*s)); p.drawLine(QPointF(.43*s,.42*s),QPointF(.43*s,.7*s)); p.drawLine(QPointF(.57*s,.42*s),QPointF(.57*s,.7*s))
    elif name == "folder":
        path=QPainterPath(); path.moveTo(.16*s,.34*s); path.lineTo(.42*s,.34*s); path.lineTo(.5*s,.43*s); path.lineTo(.84*s,.43*s); path.lineTo(.78*s,.76*s); path.lineTo(.18*s,.76*s); path.closeSubpath(); p.drawPath(path)
    elif name == "search":
        p.drawEllipse(QRectF(.2*s,.18*s,.48*s,.48*s)); p.drawLine(QPointF(.61*s,.61*s),QPointF(.82*s,.82*s))
    elif name == "filter":
        path=QPainterPath(); path.moveTo(.17*s,.22*s); path.lineTo(.83*s,.22*s); path.lineTo(.59*s,.5*s); path.lineTo(.59*s,.76*s); path.lineTo(.41*s,.84*s); path.lineTo(.41*s,.5*s); path.closeSubpath(); p.drawPath(path)
    elif name == "media":
        p.drawRoundedRect(QRectF(.17*s,.2*s,.66*s,.58*s),.08*s,.08*s); path=QPainterPath(); path.moveTo(.43*s,.37*s); path.lineTo(.66*s,.49*s); path.lineTo(.43*s,.62*s); path.closeSubpath(); p.drawPath(path)
    elif name == "duplicate":
        p.drawRoundedRect(QRectF(.29*s,.19*s,.49*s,.49*s),.06*s,.06*s); p.drawRoundedRect(QRectF(.17*s,.31*s,.49*s,.49*s),.06*s,.06*s)
    elif name == "settings":
        p.drawEllipse(QRectF(.38*s,.38*s,.24*s,.24*s));
        for a,b,c1,d in ((.5,.13,.5,.3),(.5,.7,.5,.87),(.13,.5,.3,.5),(.7,.5,.87,.5),(.24,.24,.35,.35),(.65,.65,.76,.76),(.65,.35,.76,.24),(.24,.76,.35,.65)): p.drawLine(QPointF(a*s,b*s),QPointF(c1*s,d*s))
    elif name == "minimize": p.drawLine(QPointF(.24*s,.64*s),QPointF(.76*s,.64*s))
    elif name == "maximize": p.drawRect(QRectF(.25*s,.25*s,.5*s,.5*s))
    elif name == "restore": p.drawRect(QRectF(.2*s,.31*s,.45*s,.45*s)); p.drawRect(QRectF(.35*s,.2*s,.45*s,.45*s))
    elif name == "close": p.drawLine(QPointF(.25*s,.25*s),QPointF(.75*s,.75*s)); p.drawLine(QPointF(.75*s,.25*s),QPointF(.25*s,.75*s))
    elif name == "download":
        p.drawLine(QPointF(.5*s,.16*s),QPointF(.5*s,.62*s)); p.drawLine(QPointF(.32*s,.46*s),QPointF(.5*s,.64*s)); p.drawLine(QPointF(.68*s,.46*s),QPointF(.5*s,.64*s)); p.drawLine(QPointF(.22*s,.78*s),QPointF(.78*s,.78*s))
    elif name == "table":
        for y in (.28,.5,.72): p.drawLine(QPointF(.35*s,y*s),QPointF(.82*s,y*s)); p.drawEllipse(QRectF(.16*s,.22*s,.1*s,.1*s)); p.drawEllipse(QRectF(.16*s,.44*s,.1*s,.1*s)); p.drawEllipse(QRectF(.16*s,.66*s,.1*s,.1*s))
    elif name == "columns":
        p.drawRoundedRect(QRectF(.18*s,.22*s,.64*s,.56*s),.04*s,.04*s); p.drawLine(QPointF(.5*s,.22*s),QPointF(.5*s,.78*s))
    elif name == "more":
        p.setBrush(c)
        for y in (.28, .5, .72): p.drawEllipse(QRectF(.44*s,y*s-.06*s,.12*s,.12*s))
    elif name in {"file", "file_video", "file_audio", "file_archive", "file_document", "file_image"}:
        path=QPainterPath(); path.moveTo(.24*s,.14*s); path.lineTo(.61*s,.14*s); path.lineTo(.79*s,.32*s); path.lineTo(.79*s,.84*s); path.lineTo(.24*s,.84*s); path.closeSubpath(); p.drawPath(path)
        p.drawLine(QPointF(.61*s,.14*s),QPointF(.61*s,.32*s)); p.drawLine(QPointF(.61*s,.32*s),QPointF(.79*s,.32*s))
        if name == "file_video":
            q=QPainterPath(); q.moveTo(.41*s,.46*s); q.lineTo(.62*s,.57*s); q.lineTo(.41*s,.68*s); q.closeSubpath(); p.drawPath(q)
        elif name == "file_audio":
            p.drawLine(QPointF(.56*s,.43*s),QPointF(.56*s,.66*s)); p.drawLine(QPointF(.56*s,.43*s),QPointF(.68*s,.4*s)); p.drawEllipse(QRectF(.42*s,.62*s,.14*s,.12*s))
        elif name == "file_archive":
            for y in (.4,.51,.62): p.drawLine(QPointF(.43*s,y*s),QPointF(.61*s,y*s))
        elif name == "file_document":
            for y in (.43,.54,.65): p.drawLine(QPointF(.36*s,y*s),QPointF(.67*s,y*s))
        elif name == "file_image":
            p.drawEllipse(QRectF(.38*s,.39*s,.1*s,.1*s)); q=QPainterPath(); q.moveTo(.34*s,.7*s); q.lineTo(.48*s,.55*s); q.lineTo(.57*s,.64*s); q.lineTo(.67*s,.52*s); q.lineTo(.72*s,.7*s); p.drawPath(q)
    elif name == "activity":
        p.drawLine(QPointF(.15*s,.65*s),QPointF(.32*s,.65*s)); p.drawLine(QPointF(.32*s,.65*s),QPointF(.43*s,.35*s)); p.drawLine(QPointF(.43*s,.35*s),QPointF(.58*s,.75*s)); p.drawLine(QPointF(.58*s,.75*s),QPointF(.7*s,.48*s)); p.drawLine(QPointF(.7*s,.48*s),QPointF(.85*s,.48*s))
    else:
        p.drawEllipse(QRectF(.42*s,.42*s,.16*s,.16*s))
    p.end()
    return QIcon(px)
