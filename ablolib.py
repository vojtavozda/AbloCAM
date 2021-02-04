""" Library for AbloCAM """

from PyQt5 import QtGui
from PyQt5 import QtCore
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QRunnable
from PyQt5.QtWidgets import QWidget, QStyle, QSlider

import pyqtgraph as pg

class DynVar(QObject):
    """
    Dynamic variable with:
    `set()` - set new value
    `get()` - read value
    `signal` - signal can emit and be caught be a slot function

    Used in xeryon.py, basler.py
    """

    signal = pyqtSignal(float)

    def __init__(self,value:float=0):
        super().__init__()
        self.value = value

    def get(self):
        return self.value

    def set(self,value:float):
        """
        Set value of this variable.
        This function also emits signal which can be cought by some slot method.
        """
        self.value = value
        self.signal.emit(value)

class PgRectangle(pg.GraphicsObject):
    def __init__(self, topLeft, size, pen=None,brush=None):
        pg.GraphicsObject.__init__(self)
        self.topLeft = topLeft
        self.size = size
        
        if pen is None:
            pen = pg.mkPen('k')

        if brush is None:
            brush = pg.mkBrush(None)

        self.picture = QtGui.QPicture()
        p = QtGui.QPainter(self.picture)
        p.setPen(pen)
        p.setBrush(brush)
        tl = QtCore.QPointF(self.topLeft[0], self.topLeft[1])
        size = QtCore.QSizeF(self.size[0], self.size[1])
        p.drawRect(QtCore.QRectF(tl, size))
        p.end()

    def paint(self, p, *args):
        p.drawPicture(0, 0, self.picture)

    def boundingRect(self):
        return QtCore.QRectF(self.picture.boundingRect())

def printAttributes(obj):
    """ Print attributes and methods (returns) of an object """

    attributes = dir(obj)
    for atrbt in attributes:
        if atrbt[0]!='_':
            try:
                print(bcolors.BOLD,atrbt+"():",bcolors.ENDC,eval('obj.'+atrbt+'()'))
            except:
                print(bcolors.BOLD,atrbt+":",bcolors.ENDC,eval('obj.'+atrbt))

def unicode(string):

    return "<html><head/><body>"+string+"</body></html>"

class WorkerSignals(QObject):
    """ Signals used by a worker """
    finished = pyqtSignal()

class Worker(QRunnable):
    """ Worker thread """

    def __init__(self, fn, *args, name="Noname", **kwargs):
        super(Worker, self).__init__()

        self.fn = fn    # Which function should be called
        self.name = name
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self):

        try:
            self.fn(*self.args, **self.kwargs)
        except:
            print(f"{self.name} worker: Something went wrong")
        finally:
            self.signals.finished.emit()

class Signals(QObject):
    """ Just signals used for various things """
    closeWindow = pyqtSignal()
    closeParent = pyqtSignal()
    connection = pyqtSignal(bool)
    message = pyqtSignal(str)


# List of colors for plotting (adapted from matlab)
plt_clrs = ['#0072BD','#D95319','#EDB120','#7E2F8E','#77AC30','#4DBEEE','#A2142F']

# Print functions
def printW(msg):
    """ Print warning message """
    print(bcolors.WARNING + msg + bcolors.ENDC)

def printE(msg):
    """ Print error message """
    print(bcolors.FAIL + msg + bcolors.ENDC)

def printOK(msg):
    """ Print OK message """
    print(bcolors.OKGREEN + msg + bcolors.ENDC)

def printException(ex):
    template = "An exception of type {0} occurred. Arguments:\n{1!r}"
    message = template.format(type(ex).__name__, ex.args)
    print(message)

class bcolors:
    """ Definition of terminal colors """
    HEADER = '\033[95m'     # Pink
    OKBLUE = '\033[94m'     # Blue
    OKCYAN = '\033[96m'     # Cyan
    OKGREEN = '\033[92m'    # Green
    WARNING = '\033[93m'    # Yellow
    FAIL = '\033[91m'       # Red
    ENDC = '\033[0m'        # White
    BOLD = '\033[1m'        # Bold
    UNDERLINE = '\033[4m'   # Underline


def standardIcon(icon):

    return QWidget().style().standardIcon(getattr(QStyle,icon))

def emitMsg(signal,msg):
    try:
        signal.emit(msg)
    except:
        pass


class DoubleSlider(QSlider):
    """ NOT USED AT THE TIME """
    # create our our signal that we can connect to if necessary
    doubleValueChanged = pyqtSignal(float)

    def __init__(self, decimals=3, *args, **kargs):
        super(DoubleSlider, self).__init__( *args, **kargs)
        self._multi = 10 ** decimals

        self.valueChanged.connect(self.emitDoubleValueChanged)

    def emitDoubleValueChanged(self):
        value = float(super(DoubleSlider, self).value())/self._multi
        self.doubleValueChanged.emit(value)

    def value(self):
        return float(super(DoubleSlider, self).value()) / self._multi

    def setMinimum(self, value):
        return super(DoubleSlider, self).setMinimum(value * self._multi)

    def setMaximum(self, value):
        return super(DoubleSlider, self).setMaximum(value * self._multi)

    def setSingleStep(self, value):
        return super(DoubleSlider, self).setSingleStep(value * self._multi)

    def singleStep(self):
        return float(super(DoubleSlider, self).singleStep()) / self._multi

    def setValue(self, value):
        super(DoubleSlider, self).setValue(int(value * self._multi))


class QDoubleSlider(QSlider):
    """
    QDoubleSlider
    =============

    Typical QSlider works only with integers. Here it is modified to doubles.
    https://gist.github.com/dennis-tra/994a65d6165a328d4eabaadbaedac2cc
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.decimals = 5
        self._max_int = 10 ** self.decimals

        super().setMinimum(0)
        super().setMaximum(self._max_int)

        self._min_value = 0.0
        self._max_value = 1.0

    @property
    def _value_range(self):
        return self._max_value - self._min_value

    def value(self):
        return float(super().value()) / self._max_int * self._value_range + self._min_value

    def setValue(self, value):
        super().setValue(int((value - self._min_value) / self._value_range * self._max_int))

    # def setMinimum(self, value):
    #     if value > self._max_value:
    #         raise ValueError("Minimum limit cannot be higher than maximum")

    #     self._min_value = value
        # super(QDoubleSlider,self).setMinimum(value)
        # self.setValue(self.value())

    # def setMaximum(self, value):
    #     if value < self._min_value:
    #         raise ValueError("Minimum limit cannot be higher than maximum")

    #     self._max_value = value
    #     super(QDoubleSlider,self).setMinimum(value)
        # self.setValue(self.value())

    def minimum(self):
        return self._min_value

    def maximum(self):
        return self._max_value