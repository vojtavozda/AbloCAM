""" LED indicator """
import sys
from PyQt5.QtCore import QPointF, pyqtProperty, Qt
from PyQt5.QtGui import (QPainter, QPen, QBrush,
    QRadialGradient, QColor)
from PyQt5.QtWidgets import QAbstractButton, QApplication


class QLED(QAbstractButton):
    scaledSize = 1000.0

    def __init__(self, parent=None, color='green'):
        
        # if parent is not None:
        QAbstractButton.__init__(self, parent)
        self.setEnabled(False)
        self.setMinimumSize(24, 24)
        self.setCheckable(True)
        self.color = ''
        self.changeColor(color)
        self.hover = False

    def resizeEvent(self, *_):
        self.update()

    def paintEvent(self, *_):
        realSize = min(self.width(), self.height())

        painter = QPainter(self)
        pen = QPen(Qt.black)
        pen.setWidth(1)

        painter.setRenderHint(QPainter.Antialiasing)
        painter.translate(self.width() / 2, self.height() / 2)
        painter.scale(realSize / self.scaledSize, realSize / self.scaledSize)

        gradient = QRadialGradient(QPointF(-500, -500), 1500, QPointF(-500, -500))
        if self.hover:
            gradient.setColorAt(0, QColor(0, 0, 0))
            gradient.setColorAt(1, QColor(255, 255, 255))
        else:
            gradient.setColorAt(0, QColor(224, 224, 224))
            gradient.setColorAt(1, QColor(28, 28, 28))
        painter.setPen(pen)
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(QPointF(0, 0), 500, 500)

        gradient = QRadialGradient(QPointF(500, 500), 1500, QPointF(500, 500))
        gradient.setColorAt(0, QColor(224, 224, 224))
        gradient.setColorAt(1, QColor(28, 28, 28))
        painter.setPen(pen)
        painter.setBrush(QBrush(gradient))
        painter.drawEllipse(QPointF(0, 0), 450, 450)

        painter.setPen(pen)
        if self.isChecked():
            gradient = QRadialGradient(QPointF(-500, -500), 1500, QPointF(-500, -500))
            gradient.setColorAt(0, self.on_color_1)
            gradient.setColorAt(1, self.on_color_2)
        else:
            gradient = QRadialGradient(QPointF(500, 500), 1500, QPointF(500, 500))
            gradient.setColorAt(0, self.off_color_1)
            gradient.setColorAt(1, self.off_color_2)

        painter.setBrush(gradient)
        painter.drawEllipse(QPointF(0, 0), 400, 400)

    def changeState(self,checked,color,tooltip):

        if checked is not None:
            self.setChecked(checked)

        if color is not None:
            self.changeColor(color)

        if tooltip is not None:
            self.setToolTip(tooltip)

    def changeHover(self,hover):

        self.hover = hover

    def changeColor(self,color):
        if self.color != color:
            # print("QLED:changeColor",self.color,"->",color)
            _color = self.color
            self.color = color
            if color == 'green':
                self.on_color_1  = QColor(0, 255, 0)
                self.on_color_2  = QColor(0, 192, 0)
                self.off_color_1 = QColor(0,  28, 0)
                self.off_color_2 = QColor(0, 128, 0)
                self.update()
            elif color == 'red':
                self.on_color_1  = QColor(255, 0, 0)
                self.on_color_2  = QColor(176, 0, 0)
                self.off_color_1 = QColor( 28, 0, 0)
                self.off_color_2 = QColor(156, 0, 0)
                self.update()
            elif color == 'orange':
                self.on_color_1  = QColor(255, 162, 0)
                self.on_color_2  = QColor(207, 131, 0)
                self.off_color_1 = QColor( 56,  36, 0)
                self.off_color_2 = QColor(156,  99, 0)
                self.update()
            elif color == 'gray':
                self.on_color_1  = QColor(250, 250, 250)
                self.on_color_2  = QColor(207, 207, 207)
                self.off_color_1 = QColor( 56,  56,  56)
                self.off_color_2 = QColor(156, 156, 156)
                self.update()
            else:
                self.color = _color

    @pyqtProperty(QColor)
    def onColor1(self):
        return self.on_color_1

    @onColor1.setter
    def onColor1(self, color):
        self.on_color_1 = color

    @pyqtProperty(QColor)
    def onColor2(self):
        return self.on_color_2

    @onColor2.setter
    def onColor2(self, color):
        self.on_color_2 = color

    @pyqtProperty(QColor)
    def offColor1(self):
        return self.off_color_1

    @offColor1.setter
    def offColor1(self, color):
        self.off_color_1 = color

    @pyqtProperty(QColor)
    def offColor2(self):
        return self.off_color_2

    @offColor2.setter
    def offColor2(self, color):
        self.off_color_2 = color