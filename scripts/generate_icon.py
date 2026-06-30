from __future__ import annotations

from pathlib import Path
import struct

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)


ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "src" / "confluence_daily" / "assets"
PNG_PATH = ASSET_DIR / "app_icon_256.png"
ICO_PATH = ASSET_DIR / "app_icon.ico"
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def scaled_rect(x: float, y: float, width: float, height: float, scale: float) -> QRectF:
    return QRectF(x * scale, y * scale, width * scale, height * scale)


def draw_icon(size: int) -> QImage:
    scale = size / 256
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    tile = QPainterPath()
    tile.addRoundedRect(scaled_rect(10, 10, 236, 236, scale), 52 * scale, 52 * scale)
    tile_gradient = QLinearGradient(QPointF(28 * scale, 18 * scale), QPointF(230 * scale, 238 * scale))
    tile_gradient.setColorAt(0.0, QColor("#2563eb"))
    tile_gradient.setColorAt(0.58, QColor("#0ea5a6"))
    tile_gradient.setColorAt(1.0, QColor("#0f766e"))
    painter.fillPath(tile, QBrush(tile_gradient))

    painter.setPen(QPen(QColor(255, 255, 255, 48), max(1, round(2 * scale))))
    painter.drawPath(tile)

    glow = QPainterPath()
    glow.addEllipse(scaled_rect(-34, -40, 170, 150, scale))
    painter.fillPath(glow, QColor(255, 255, 255, 34))

    shadow = QPainterPath()
    shadow.addRoundedRect(scaled_rect(62, 50, 124, 148, scale), 18 * scale, 18 * scale)
    painter.fillPath(shadow.translated(0, 7 * scale), QColor(0, 30, 50, 50))

    page = QPainterPath()
    page.addRoundedRect(scaled_rect(58, 45, 126, 150, scale), 18 * scale, 18 * scale)
    painter.fillPath(page, QColor("#f8fafc"))

    fold = QPainterPath()
    fold.moveTo(151 * scale, 45 * scale)
    fold.lineTo(184 * scale, 78 * scale)
    fold.lineTo(151 * scale, 78 * scale)
    fold.closeSubpath()
    painter.fillPath(fold, QColor("#dbeafe"))

    painter.setPen(QPen(QColor("#94a3b8"), max(2, round(7 * scale)), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    for y in (96, 118, 140):
        painter.drawLine(QPointF(82 * scale, y * scale), QPointF(152 * scale, y * scale))

    badge = QPainterPath()
    badge.addEllipse(scaled_rect(119, 132, 86, 86, scale))
    badge_gradient = QLinearGradient(QPointF(128 * scale, 134 * scale), QPointF(196 * scale, 214 * scale))
    badge_gradient.setColorAt(0.0, QColor("#f97316"))
    badge_gradient.setColorAt(1.0, QColor("#facc15"))
    painter.fillPath(badge, QBrush(badge_gradient))
    painter.setPen(QPen(QColor(0, 45, 60, 38), max(1, round(3 * scale))))
    painter.drawPath(badge)

    arrow_pen = QPen(QColor("white"), max(3, round(11 * scale)), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    painter.setPen(arrow_pen)
    painter.drawLine(QPointF(162 * scale, 187 * scale), QPointF(162 * scale, 151 * scale))
    painter.drawLine(QPointF(142 * scale, 169 * scale), QPointF(162 * scale, 149 * scale))
    painter.drawLine(QPointF(182 * scale, 169 * scale), QPointF(162 * scale, 149 * scale))

    painter.end()
    return image


def image_to_png_bytes(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise RuntimeError("Failed to encode icon frame as PNG.")
    return bytes(data.data())


def write_ico(path: Path, frames: list[tuple[int, bytes]]) -> None:
    header = struct.pack("<HHH", 0, 1, len(frames))
    entries = []
    offset = 6 + (16 * len(frames))

    for size, data in frames:
        width_byte = 0 if size >= 256 else size
        height_byte = 0 if size >= 256 else size
        entries.append(struct.pack("<BBBBHHII", width_byte, height_byte, 0, 0, 1, 32, len(data), offset))
        offset += len(data)

    path.write_bytes(header + b"".join(entries) + b"".join(data for _, data in frames))


def main() -> int:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)

    preview = draw_icon(256)
    if not preview.save(str(PNG_PATH), "PNG"):
        raise RuntimeError(f"Failed to write {PNG_PATH}")

    frames = [(size, image_to_png_bytes(draw_icon(size))) for size in ICON_SIZES]
    write_ico(ICO_PATH, frames)

    print(f"Wrote {PNG_PATH}")
    print(f"Wrote {ICO_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
