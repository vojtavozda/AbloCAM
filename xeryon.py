"""
Xeryon motor control
====================

Module to work with **Xeryon** motors. It employs ``Xeryon`` library (`link
<https://xeryon.com/software/xeryon-python-library/>`_) provided by the *Xeryon
company*.

This module can be run separately, it opens :func:`main` and
:class:`XeryonMainWindow`  which connects Xeryon motors of :class:`Motor`.
Examples of widgets are encapsulated in :class:`XeryonGUI` which is set as a
central widget of the :class:`XeryonMainWindow`.

Communication between :class:`Motor` and widgets is intermediated by ``PyQt5``
signals like :class:`LED_signals` etc.

A typical usage of this module contains following steps:
    1.  Init :class:`Motor` (it communicates with the ``Xeryon`` library).
    2.  Create widgets which require pointers to Xeryon motors (i.e.
        :class:`StatusGUI` or :class:`XYWidget`).
    3.  Connect motors (:func:`Motor.connect`).
"""

# TODO =========================================================================
# ? [ ] Think about moving keyPressEvent (arrows) to a separate class
# $     `KeyboardControl`.
# $ [ ] add speed control (settings button in StatusGUI)
# @ [x] Rotational stage works with old tkinter script but not here :/
# TODO -------------------------------------------------------------------------

# TODO: Run this script, connect motor and check output:
# $ this is from Xeryon.py, line 707
# $ instead of printing these values, signals (XeSignals) shoud be emitted
# $ check documentation what does STAT tag mean

import sys
import time
import numpy as np
from PyQt5.QtCore import (Qt, QThreadPool, QObject, QRunnable, pyqtSlot,
    pyqtSignal, QPoint, QEvent, QTimer)
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QPushButton,
    QHBoxLayout, QVBoxLayout, QStyle, QAbstractButton, QLabel, QSlider,
    QGridLayout, QLineEdit, qApp, QMenu, QAction, QDial)
from PyQt5.QtGui import QPainter, QPen, QBrush, QColor, QPicture, QFont

from TextEditor import TextEditorGUI

import pyqtgraph as pg
import qtawesome as qta     # use bash: `qta-browser` to see icon list

from functools import partial

from LedWidget import QLED

import Xeryon as xe

import ablolib as al

# Library to find information about devices connected to serial ports
from serial.tools import list_ports

# Set timeout after which motor updates its values and emits signals for LEDs
MOTOR_UPDATE_TIMER = 500    # [ms]

def get_serial_port(serial_number):
    """ Find serial port corresponding to given serial number """

    device_list = list_ports.comports()
    for device in device_list:
        if device.serial_number == serial_number:
            return device.device
    al.printE(f"Device with serial number '{serial_number}' not found!")
    return None

class LED_signals(QObject):
    """
    Signals for LEDs of :class:`pyqtSignal`. Used by :class:`xeryon` which emits
    signals according to current action. These might be connected to
    :class:`LedWidget.QLED`, for example in :class:`StatusGUI`.

    Args:
        arg1 (bool): turn LED on/off
        arg2 (str):  LED color (see :class:`LedWidget.QLED`)
        arg3 (str):  tooltip
    """
    connected = pyqtSignal(bool,str,str)    # stage is connected or not
    findIndex = pyqtSignal(bool,str,str)    # index was found or not
    moving = pyqtSignal(bool,str,str)       # moving status
    LLIM = pyqtSignal(bool,str,str)         # stage is at its low limit
    HLIM = pyqtSignal(bool,str,str)         # stage is at its high limit

class Motor():
    """
    Classed used to control **Xeryon motors**, it mediates communication with
    the ``Xeryon`` library.

    **Dynamic variables:** Motor employs several vars of
    :class:`ablolib.DynVar`. They should be accessed exclusively via
    :func:`ablolib.DynVar.set` and :func:`ablolib.DynVar.get` methods. The
    `set()` method emits signal which can be connected to a slot function (i.e.
    read :attr:`EPOS`).

    **Timer:** The ``Xeryon`` library does not use ``PyQt5`` signals so there is
    no way to automatically catch change of motor status (like :attr:`EPOS`).
    Therefore, :attr:`timer` starts upon :func:`connect` and after runout it
    periodically reads motor status via :func:`updateData`. **TODO:** This
    spends lots of time which results in decreased application smoothness.

    Args:
        axis_letter (str): Letter connected with a particular motor. Used in
            configuration file read by ``Xeryon`` library. The file contains
            information of the motor serial number so communication port can be
            obtain using :func:`get_serial_port` function.
        closeSignal: Signal which is here connected to :func:`disconnect` so it
            is automatically disconnected when this signal emits. Recommended.
            Defaults to None.
        speed (int): Speed. Defaults to 100.
        units: Units used by the motor. Defaults to `mm`.
        stepSize (int): Step size. Defaults to 1.

    Attributes:
        connected (bool): Connection status
        LedSig (:class:`LED_signals`): Emits signals according to the motor
            status.
        DPOS (:class:`ablolib.DynVar`): Desired position written to the encoder.
        EPOS (:class:`ablolib.DynVar`): Actual position returned from the
            encoder. 
        speed (:class:`ablolib.DynVar`): Speed of the motor
        stepSize (:class:`ablolib.DynVar`): Size of a single step (see
            :func:`step` method).
        limits ([int,int]): Limits of the motor. Read from the config file.
        timer (:class:`QTimer`): Connected to :func:`updateData`.
        threadpool (:class:`QThreadPool`): Used within :func:`findIndex`.

    """

    def __init__(self,axis_letter='',closeSignal=None,units=xe.Units.mm,
                 speed=10,stepSize=1):

        self.connected = False      # Connection status
        self.indexFound = False     # Is index found? (not needed?)

        self.controller = None      # Xeryon object, init in `connect()`
        self.stage = None           # Xeryon object, defined below
        self.serial = None          # Serial port, defined below
        self.axis = None            # Xeryon object

        self.units = units          # Will be set upon connection

        self.limits = [-5,5]        # Default, set in `connect()`

        self.LedSig = LED_signals() # Signals

        self.timer = QTimer()       # Timer is used to update data (LEDs, etc.)
        self.timer.timeout.connect(self.updateData)

        # Following arguments are used to track changes of given states
        # They are used in updateData() method
        self.isEncoderError_prev = None
        self.isEncoderValid_prev = None
        self.EPOS_prev = None

        # Threading is used for finding index
        self.threadpool = QThreadPool()

        # Clear disconnection of motor can be done manually as:
        #  >>> motor.disconnect()
        # or by emitting close signal
        if closeSignal is not None:
            closeSignal.connect(self.disconnect)

        if axis_letter != '':

            print(f"Xeryon motor {axis_letter} object created!")

            self.axis_letter = axis_letter

            self.speed = al.DynVar(speed)
            self.speed.signal.connect(self.__setSpeed)

            self.DPOS = al.DynVar(0)
            self.DPOS.signal.connect(self.__setDPOS)

            self.EPOS = al.DynVar(0)

            self.stepSize = al.DynVar(stepSize)

            self.__getSerial()

        else:
            # Just initialization of a motor instance
            pass

    def connect(self,baudrate=9600):
        """ Connect Xeryon motor """

        if self.serial is None:
            self.__getSerial()
            if self.serial is None:
                return False

        # Connect Xeryon controller
        self.controller = xe.Xeryon(self.serial,baudrate)
        self.axis = self.controller.addAxis(self.stage,self.axis_letter)
        self.controller.start()

        self.axis.setUnits(self.units)
        self.__setSpeed()

        # Define limits
        if self.axis.stage.isLineair:
            # Linear stage
            LLIM = int(self.axis.convertEncoderUnitsToUnits(self.axis.getSetting("LLIM"), xe.Units.mm)) if self.axis.getSetting("LLIM") is not None else -5
            HLIM = int(self.axis.convertEncoderUnitsToUnits(self.axis.getSetting("HLIM"), xe.Units.mm)) if self.axis.getSetting("HLIM") is not None else +5
        else:
            # Rotational stage
            self.LedSig.LLIM.emit(False,'gray','Unlimited rotation')
            self.LedSig.HLIM.emit(False,'gray','Unlimited rotation')
            if self.units != xe.Units.deg:
                self.axis.setUnits(xe.Units.deg)
                al.printW("Warning: Units of rotational stage must be degrees!")
                al.printW(f"--> Units of motor {self.axis_letter} changed.")
            LLIM = int(0)
            HLIM = int(360)

        if LLIM >= HLIM:
            al.printE("""Motor: LLIM must be smaller than HLIM!
                         See configuration file for setting""")
            self.limits = [-1,1]
        else:
            self.limits = [LLIM,HLIM]

        self.timer.start(MOTOR_UPDATE_TIMER)    # Start timer to `updateData()`

        self.connected = True # TODO: This should be confirmed by the Xeryon lib
        self.LedSig.connected.emit(True,'green','Connected')
        self.stepSize.signal.emit(self.stepSize.get())

    def disconnect(self):
        """ Stop communication """
        if self.controller is not None:
            self.controller.stop()
        self.connected = False
        self.timer.stop()
        self.indexFound = False
        self.updateData()
        # self.LedSig.connected.emit(False,'green','Disconnected')
        # self.LedSig.findIndex.emit(False,'green','Index not found')

        self.isEncoderError_prev = None
        self.isEncoderValid_prev = None

    def findIndex(self):
        """ Find index """
        if self.connected:
            self.isEncoderValid_prev = None
            self.LedSig.findIndex.emit(True,'orange','Searching index')
            # TODO: There are several problems with threading - should be tested
            # $ (xe.DISABLE_WAITING)
            # # Start a worker
            worker = al.Worker(self.findIndexThread,name="Motor"+self.axis_letter)
            self.threadpool.start(worker)
            # self.findIndexThread() # find index without threading

    def findIndexThread(self):
        """ Thread used to find index because waiting is needed """

        xe.DISABLE_WAITING = False
        _spd = self.speed.get()
        self.speed.set(500)
        self.axis.setDPOS(-300)

        # TODO: modify xe.Axis.findIndex() to return 0 (found) or 1 (error)
        self.axis.findIndex()
        # TODO: indexFound should be confirmed from the axis.findIndex() method
        self.indexFound = True

        self.DPOS.set(0)
        self.speed.set(_spd)
        xe.DISABLE_WAITING = True

        self.isEncoderValid_prev = None

    def updateData(self):
        """ Read motor data employin Xeryon library """

        if self.connected:
            
            _EPOS = float(self.axis.getData('EPOS'))
            _EPOS = self.axis.convertEncoderUnitsToUnits(_EPOS,self.units)
            _EPOS = round(_EPOS*1000)/1000
            if _EPOS != self.EPOS_prev:
                self.EPOS.set(round(_EPOS*1000)/1000)
                self.EPOS_prev = _EPOS

            if self.isEncoderError_prev != self.axis.isEncoderError():
                self.isEncoderError_prev = self.axis.isEncoderError()

                if self.axis.isEncoderError():
                    self.LedSig.connected.emit(True,'red','Encoder error')
                else:
                    self.LedSig.connected.emit(True,'green','Connected')

            if self.axis.isEncoderValid():
                self.LedSig.findIndex.emit(True,'green','Encoder valid')
            elif self.axis.isSearchingIndex():
                self.LedSig.findIndex.emit(True,'orange','Searching index')
            elif not self.axis.isEncoderValid():
                self.LedSig.findIndex.emit(False,'green','Index not found')
            
            if self.axis.isEncoderValid():
                if self.axis.isPositionReached():
                    self.LedSig.moving.emit(True,'green','Ready')
                else:
                    self.LedSig.moving.emit(True,'orange','Moving')
            else:
                if self.axis.isPositionReached():
                    self.LedSig.moving.emit(False,'green','Unknown position')
                else:
                    self.LedSig.moving.emit(True,'orange','Moving')

            if self.axis.stage.isLineair:
                if self.axis.isAtLeftEnd():
                    self.LedSig.LLIM.emit(True,'red','Low limit reached!')
                elif self.DPOS.get() <= self.limits[0]:
                    self.LedSig.LLIM.emit(True,'orange','Trying to set lower limit!')
                else:
                    self.LedSig.LLIM.emit(False,'red','Low limit OK')

                if self.axis.isAtRightEnd():
                    self.LedSig.HLIM.emit(True,'red','High limit reached!')
                elif self.DPOS.get() >= self.limits[1]:
                    self.LedSig.HLIM.emit(True,'orange','Trying to set higher limit!')
                else:
                    self.LedSig.HLIM.emit(False,'red','High limit OK')

        else:
            self.LedSig.connected.emit(False,'green','Disconnected')
            self.LedSig.findIndex.emit(False,'green','Disconnected')
            self.LedSig.moving.emit(False,'green','Disconnected')
            self.LedSig.LLIM.emit(False,'red','Disconnected')
            self.LedSig.HLIM.emit(False,'red','Disconnected')

    def step(self,stepSize=None):
        """
        Perform a step of a give size.

        Args:
            stepSize (float, optional): Size of the step. Defaults to
                self.stepSize.get().
        """
        if stepSize is None:
            stepSize = self.stepSize.get()
        
        # print("Motor::step",stepSize)
        self.DPOS.set(float(self.DPOS.get())+stepSize)

    def __setSpeed(self):
        self.axis.setSpeed(self.speed.get())

    def __setDPOS(self):
        """ Private function is called when `self.DPOS.signal` emits """
        # print("Motor::__setDPOS",self.DPOS.get())

        # Check if DPOS does not exceed limits. If yes, correct DPOS.
        # (note that this function is called again when DPOS.set() is called)
        if self.DPOS.get() < self.limits[0]:    # Correct low limit
            if self.axis.stage.isLineair:
                self.DPOS.set(self.limits[0])
            else:
                self.DPOS.set(self.DPOS.get()+360)
        elif self.DPOS.get() > self.limits[1]:  # Correct high limit
            if self.axis.stage.isLineair:
                self.DPOS.set(self.limits[1])
            else:
                self.DPOS.set(self.DPOS.get()-360)
        else:
            self.axis.setDPOS(self.DPOS.get())  # Write position to encoder

    def __getSerial(self):

        # TODO: Serial numbers should be read from config file
        # TODO: Stage should be defined in the config file and be returned from
        # TODO: `readConfig()` function.
        if self.axis_letter == "X":
            serial_number = "7583835373835180D020"
            stage = xe.Stage.XLS_1250
        elif self.axis_letter == "Y":
            serial_number = "75838353738351213130"
            stage = xe.Stage.XLS_1250
        elif self.axis_letter == "Z":
            serial_number = "75838353738351319090"
            stage = xe.Stage.XLS_1250
        elif self.axis_letter == "Z3":
            serial_number = "9593332343335101A020"
            stage = xe.Stage.XLS_1250_3N
        elif self.axis_letter == "R":
            self.units = xe.Units.deg
            serial_number = "95933323433351212070"
            stage = xe.Stage.XRTU_30_109
        else:
            serial_number = None
            stage = None
        
        serial = get_serial_port(serial_number)

        if serial is None:
            al.printE(f"Xeryon motor '{self.axis_letter}' not connected!")
        else:
            self.serial = serial
            self.stage = stage

class HoverButton(QPushButton):
    """
    **Bases:** :class:`QWidget`
    
    Button used for clickable LEDs in :class:`StatusGUI`. This button emits bool
    signal :attr:`mouseHover` when hovered (`enter` or `leave`)."""

    mouseHover = pyqtSignal(bool)

    def __init__(self,parent=None):
        QPushButton.__init__(self,parent)
        self.setFocusPolicy(Qt.NoFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

    def enterEvent(self,*_):
        self.mouseHover.emit(True)

    def leaveEvent(self,*_):
        self.mouseHover.emit(False)

class StatusGUI(QWidget):
    """
    **Bases:** :class:`QWidget`

    Interactive status of Xeryon stage - LEDs.

    Args:
        motor (:class:`Motor`): Pointer to initialized xeryon motor. It **must**
            be initialized already because signals of the motor are connected to
            LEDs. 

    Attributes:
        led_connected: Connected to :func:`Motor.connected` signal.
        led_findIndex: Connected to :func:`Motor.findIndex` signal.
        led_moving: Connected to :func:`Motor.moving` signal.
        led_LLIM: Connected to :func:`Motor.LLIM` signal.
        led_HLIM: Connected to :func:`Motor.HLIM` signal.

    Note:
        **Clickable LED:** There is a problem, that when enabling LED for click
        so it changes its status which is not desired. Therefore, an overlaying
        button of a :class:`HoverButton` class is placed over the given LED, its
        size and position is updated within :func:`resizeEvent`. Usual
        :class:`QPushButton` has a problem that it does not return hover signal
        which is needed to toggle hover of the LED and also update tooltip of
        the button because tooltip of the LED cannot be accessed as the LED is
        below the button. Howgh.
    """

    def __init__(self,motor=Motor()):
        super().__init__()

        self.motor = motor

        hbox = QHBoxLayout()

        lbl = QLabel(self.motor.axis_letter)
        lbl.setFixedSize(20,15)
        lbl.setAlignment(Qt.AlignCenter)

        self.led_connected = QLED(self)
        self.led_findIndex = QLED(self)
        self.led_moving = QLED(self)
        self.led_LLIM = QLED(self,color='red')
        self.led_HLIM = QLED(self,color='red')

        self.led_connected.setToolTip('Connection status')
        self.led_findIndex.setToolTip('Find index status')
        self.led_moving.setToolTip('Moving status')
        self.led_LLIM.setToolTip('Low limit status')
        self.led_HLIM.setToolTip('High limit status')

        self.motor.LedSig.connected.connect(self.led_connected.changeState)
        self.motor.LedSig.findIndex.connect(self.led_findIndex.changeState)
        self.motor.LedSig.moving.connect(self.led_moving.changeState)
        self.motor.LedSig.LLIM.connect(self.led_LLIM.changeState)
        self.motor.LedSig.HLIM.connect(self.led_HLIM.changeState)

        self.btn_reload = QPushButton('',self)
        self.btn_reload.setIcon(al.standardIcon('SP_BrowserReload'))
        self.btn_reload.setStatusTip('Reload settings')
        self.btn_reload.clicked.connect(self.__reloadSettings)
        self.btn_reload.setCursor(Qt.PointingHandCursor)

        hbox.addStretch()
        hbox.addWidget(lbl)
        hbox.addWidget(self.led_connected)
        hbox.addWidget(self.led_findIndex)
        hbox.addWidget(self.led_moving)
        hbox.addWidget(self.led_LLIM)
        hbox.addWidget(self.led_HLIM)
        hbox.addWidget(self.btn_reload)
        hbox.addStretch()
        hbox.setContentsMargins(0,0,0,0)

        self.setLayout(hbox)

        self.btn_connect = HoverButton(self)
        self.btn_connect.setObjectName('btn_connect')
        self.btn_connect.clicked.connect(self.__btnClicked)
        self.btn_connect.setStyleSheet("border: 0px;")      # FIXME: Tooltip
        self.btn_connect.mouseHover.connect(self.__btnHover)

        self.btn_findIndex = HoverButton(self)
        self.btn_findIndex.setObjectName('btn_find_index')
        self.btn_findIndex.clicked.connect(self.__btnClicked)
        self.btn_findIndex.setStyleSheet("border: 0px;")    # FIXME: Tooltip
        self.btn_findIndex.mouseHover.connect(self.__btnHover)

        self.btn_moving = HoverButton(self)
        self.btn_moving.setObjectName('btn_moving')
        self.btn_moving.clicked.connect(self.__btnClicked)
        self.btn_moving.setStyleSheet("border: 0px;")
        self.btn_moving.mouseHover.connect(self.__btnHover)

    def __reloadSettings(self):
        try:
            self.motor.controller.reset()
            self.motor.disconnect()
            self.motor.connect()
        except Exception as ex:
            al.printException(ex)

    def __btnHover(self,hover):
        sender = self.sender()
        if sender.objectName() == 'btn_connect':
            self.led_connected.changeHover(hover)
            self.btn_connect.setToolTip(self.led_connected.toolTip())
            if self.motor.connected:
                self.btn_connect.setStatusTip('Click to disconnect')
            else:
                self.btn_connect.setStatusTip('Click to connect')
        elif sender.objectName() == 'btn_find_index':
            self.led_findIndex.changeHover(hover)
            self.btn_findIndex.setToolTip(self.led_findIndex.toolTip())
            self.btn_findIndex.setStatusTip('Click to find index')
        elif sender.objectName() == 'btn_moving':
            self.led_moving.changeHover(hover)
            self.btn_moving.setToolTip(self.led_moving.toolTip())
            self.btn_moving.setStatusTip('Click to STOP')

    def __btnClicked(self):
        sender = self.sender()
        if sender.objectName() == 'btn_connect':
            if self.motor.connected:
                self.motor.disconnect()
            else:
                self.motor.connect()
        elif sender.objectName() == 'btn_find_index':
            self.motor.findIndex()
        elif sender.objectName() == 'btn_moving':
            self.motor.controller.stopMovements()

    def resizeEvent(self,*_):
        """ Reimplementation of built-in function.
        Change positions of buttons so they overlay according LEDs. """
        self.btn_connect.move(self.led_connected.x(),self.led_connected.y())
        self.btn_connect.resize(self.led_connected.width(),self.led_connected.height())
        
        self.btn_findIndex.move(self.led_findIndex.x(),self.led_findIndex.y())
        self.btn_findIndex.resize(self.led_findIndex.width(),self.led_findIndex.height())
        
        self.btn_moving.move(self.led_moving.x(),self.led_moving.y())
        self.btn_moving.resize(self.led_moving.width(),self.led_moving.height())

class FocusableQLineEdit(QLineEdit):
    """
    **Bases:** :class:`QLineEdit`

    This modification of :class:`QLineEdit` emits signal :attr:`lostFocus` when
    :class:`QLineEdit` widget looses focus. This signal can be caught by a slot
    function which, for example, can set some other variable to value set by
    user to the entry field.

    Attributes:
        lostFocus (:class:`pyqtSignal`): Signal which emits upon loosing focus.
    """

    lostFocus = pyqtSignal()

    def focusOutEvent(self,event):
        """ Reimplementation of built-in function. """
        self.lostFocus.emit()           # Emit signal
        # Pass arguments to super()
        super(FocusableQLineEdit,self).focusOutEvent(event)

class MoveHGUI(QWidget):
    """
    **Bases:** :class:`QWidget`

    GUI for horizontal movements. Analogical to :class:`MoveVGUI` and
    :class:`MoveRGUI`.

    It contains position of motor, step buttons, step field.

    Note:
        **Modification of** :class:`QLineEdit` **employing**
        :class:`FocusableQLineEdit` **:** One entry field is used to show
        position of a motor (which is set by signal callback) and also to set
        desired position. Value of the field is changed automatically only if it
        does not have a focus. If it has a focus, value can be changed and
        appropriate callback (set this value) is called when the field looses
        its focus (here we need the modified :class:`FocusableQLineEdit`) or
        when pressing enter/return (see :func:`keyPressEvent`).
    """

    def __init__(self,motor=Motor()):
        super().__init__()

        self.motor = motor

        self.motor.LedSig.connected.connect(self.update)

        hbox = QHBoxLayout()
        hbox.setSpacing(0)

        lbl = QLabel(self.motor.axis_letter)
        lbl.setFixedSize(20,20)
        lbl.setAlignment(Qt.AlignCenter)

        # QLineEdit - show/set position
        self.qlePos = FocusableQLineEdit(self)
        self.qlePos.setFixedSize(50,25)
        self.qlePos.setToolTip('Motor position')
        self.qlePos.setObjectName('qle_pos')
        # When qlePos looses focus, `self.__qlePosSet` is called (motor.DPOS.set)
        self.qlePos.lostFocus.connect(self.__qlePosSet)
        # Update field value as motor.EPOS changes
        self.motor.EPOS.signal.connect(partial(self.__qleChange,self.qlePos))

        # Buttons for steps to the LEFT
        self.btnL1 = QPushButton('',self)
        self.btnL2 = QPushButton('',self)
        self.btnL3 = QPushButton('',self)

        self.btnL1.setIcon(qta.icon('mdi.chevron-left'))
        self.btnL2.setIcon(qta.icon('mdi.chevron-double-left'))
        self.btnL3.setIcon(qta.icon('mdi.chevron-triple-left'))

        self.btnL1.setToolTip(al.unicode('Ctrl + &larr;'))
        self.btnL2.setToolTip(al.unicode('&larr;'))
        self.btnL3.setToolTip(al.unicode('Shift + &larr;'))

        self.btnL1.clicked.connect(self.__btnClicked)
        self.btnL2.clicked.connect(self.__btnClicked)
        self.btnL3.clicked.connect(self.__btnClicked)

        self.btnL1.setObjectName('L1')
        self.btnL2.setObjectName('L2')
        self.btnL3.setObjectName('L3')

        self.btnL1.setCursor(Qt.PointingHandCursor)
        self.btnL2.setCursor(Qt.PointingHandCursor)
        self.btnL3.setCursor(Qt.PointingHandCursor)
        
        # Buttons for steps to the RIGHT
        self.btnR1 = QPushButton('',self)
        self.btnR2 = QPushButton('',self)
        self.btnR3 = QPushButton('',self)

        self.btnR1.setIcon(qta.icon('mdi.chevron-right'))
        self.btnR2.setIcon(qta.icon('mdi.chevron-double-right'))
        self.btnR3.setIcon(qta.icon('mdi.chevron-triple-right'))

        self.btnR1.setToolTip(al.unicode('Ctrl + &rarr;'))
        self.btnR2.setToolTip(al.unicode('&rarr;'))
        self.btnR3.setToolTip(al.unicode('Shift + &rarr;'))

        self.btnR1.clicked.connect(self.__btnClicked)
        self.btnR2.clicked.connect(self.__btnClicked)
        self.btnR3.clicked.connect(self.__btnClicked)

        self.btnR1.setObjectName('R1')
        self.btnR2.setObjectName('R2')
        self.btnR3.setObjectName('R3')

        self.btnR1.setCursor(Qt.PointingHandCursor)
        self.btnR2.setCursor(Qt.PointingHandCursor)
        self.btnR3.setCursor(Qt.PointingHandCursor)
        
        # QLineEdit - set step
        self.qleStep = FocusableQLineEdit(self)
        self.qleStep.setFixedSize(50,25)
        self.qleStep.setToolTip('Step size')
        # When qleStep looses focus, `self.__qleStepSet` is called
        # (motor.stepSize.set).
        self.qleStep.lostFocus.connect(self.__qleStepSet)
        # Update field value as motor.stepSize changes
        self.motor.stepSize.signal.connect(partial(self.__qleChange,self.qleStep))

        # Add all widgets to the layout
        hbox.addStretch()
        hbox.addWidget(lbl)
        hbox.addWidget(self.qlePos)
        hbox.addSpacing(10)
        hbox.addWidget(self.btnL3)
        hbox.addWidget(self.btnL2)
        hbox.addWidget(self.btnL1)
        hbox.addSpacing(10)
        hbox.addWidget(self.btnR1)
        hbox.addWidget(self.btnR2)
        hbox.addWidget(self.btnR3)
        hbox.addSpacing(10)
        hbox.addWidget(self.qleStep)
        hbox.addStretch()
        hbox.setContentsMargins(0,0,0,0)

        self.setLayout(hbox)

        self.update()   # Enable or disable buttons on start

    def __qlePosSet(self):
        """ Set motor.DPOS as qlePos looses focus or when pressing enter """
        if self.motor.connected:
            try:    val = float(self.qlePos.text())
            except: val = 0
            self.motor.DPOS.set(val)

    def __qleStepSet(self):
        """
        Set motor.stepSize as qleStep looses focus or when pressing enter
        """
        if self.motor.connected:
            self.motor.stepSize.set(float(self.qleStep.text()))

    def __qleChange(self,obj:QLineEdit,value=None):
        """ Change value of a QLineEdit
        It is invoked by motor.EPOS.signal which emits periodically as
        motor.updateData is called.
        """
        if not obj.hasFocus():
            # Change the value only if the entry does not have focus
            obj.setText(str(value))
            obj.setCursorPosition(0)    # Show beginning of the text, not end

    def __btnClicked(self):
        """ Callback of button click """

        objectName = self.sender().objectName()
        if objectName[0] == 'L':
            sign = -1
        elif objectName[0] == 'R':
            sign = +1
        if objectName[1] == '1':
            multiplier = 0.1
        elif objectName[1] == '2':
            multiplier = 1
        elif objectName[1] == '3':
            multiplier = 5
        self.motor.step(sign * multiplier * self.motor.stepSize.get())

    def keyPressEvent(self,event):
        """ Reimplementation of the keyPressEvent """

        # If one of QLineEdits has focus, enter key calls appropriate function
        if event.key() in [Qt.Key_Enter,Qt.Key_Return]:
            if self.qlePos.hasFocus():
                self.__qlePosSet()    # Set motor position
            elif self.qleStep.hasFocus():
                self.__qleStepSet()   # Update motor step size

    def update(self,*_):
        """ Update `enable` of controls according to status of the motor """
        self.qlePos.setEnabled(self.motor.connected)
        self.qleStep.setEnabled(self.motor.connected)
        self.btnL1.setEnabled(self.motor.connected)
        self.btnL2.setEnabled(self.motor.connected)
        self.btnL3.setEnabled(self.motor.connected)
        self.btnR1.setEnabled(self.motor.connected)
        self.btnR2.setEnabled(self.motor.connected)
        self.btnR3.setEnabled(self.motor.connected)

class MoveVGUI(QWidget):
    """
    **Bases:** :class:`QWidget`

    GUI for vertical movements. Analogical to :class:`MoveHGUI`.
    """

    # FUTURE: Buttons can be replaced by a vertical joystick

    def __init__(self,motor=Motor()):
        super().__init__()

        self.motor = motor
        self.motor.LedSig.connected.connect(self.update)

        lbl = QLabel(self.motor.axis_letter)
        # lbl.setFixedSize(20,20)
        lbl.setAlignment(Qt.AlignCenter)

        # QLineEdit - show/set position
        self.qlePos = FocusableQLineEdit(self)
        self.qlePos.setFixedSize(50,25)
        self.qlePos.setToolTip('Motor position')
        self.qlePos.setObjectName('qle_pos')
        # When qlePos looses focus, `self.__qlePosSet` is called (motor.DPOS.set)
        self.qlePos.lostFocus.connect(self.__qlePosSet)
        # Update field value as motor.EPOS changes
        self.motor.EPOS.signal.connect(partial(self.__qleChange,self.qlePos))
        
        # QLineEdit - set step
        self.qleStep = FocusableQLineEdit(self)
        self.qleStep.setFixedSize(50,25)
        self.qleStep.setToolTip('Step size')
        # When qleStep looses focus, `self.__qleStepSet` is called
        # (motor.stepSize.set).
        self.qleStep.lostFocus.connect(self.__qleStepSet)
        # Update field value as motor.stepSize changes
        self.motor.stepSize.signal.connect(partial(self.__qleChange,self.qleStep))

        vbox = QVBoxLayout()
        vbox.addWidget(lbl)
        vbox.addWidget(self.qlePos)
        vbox.addWidget(self.qleStep)
        vbox.addStretch()
        vbox.setContentsMargins(0,0,0,0)
        ctrW = QWidget()
        ctrW.setLayout(vbox)

        self.sld = QSlider(Qt.Vertical,self)
        self.sld.setCursor(Qt.PointingHandCursor)
        self.sld.valueChanged.connect(self.__sldValueChanged)

        # Buttons for steps UP
        self.btnU1 = QPushButton('',self)
        self.btnU2 = QPushButton('',self)
        self.btnU3 = QPushButton('',self)

        self.btnU1.setIcon(qta.icon('mdi.chevron-up'))
        self.btnU2.setIcon(qta.icon('mdi.chevron-double-up'))
        self.btnU3.setIcon(qta.icon('mdi.chevron-triple-up'))

        self.btnU1.setToolTip('Ctrl + -')
        self.btnU2.setToolTip('-')
        self.btnU3.setToolTip('Shift + -')

        self.btnU1.clicked.connect(self.__btnClicked)
        self.btnU2.clicked.connect(self.__btnClicked)
        self.btnU3.clicked.connect(self.__btnClicked)

        self.btnU1.setObjectName('U1')
        self.btnU2.setObjectName('U2')
        self.btnU3.setObjectName('U3')

        self.btnU1.setCursor(Qt.PointingHandCursor)
        self.btnU2.setCursor(Qt.PointingHandCursor)
        self.btnU3.setCursor(Qt.PointingHandCursor)
    
        # Buttons for steps DOWN
        self.btnD1 = QPushButton('',self)
        self.btnD2 = QPushButton('',self)
        self.btnD3 = QPushButton('',self)

        self.btnD1.setIcon(qta.icon('mdi.chevron-down'))
        self.btnD2.setIcon(qta.icon('mdi.chevron-double-down'))
        self.btnD3.setIcon(qta.icon('mdi.chevron-triple-down'))

        self.btnD1.setToolTip('Ctrl + +')
        self.btnD2.setToolTip('+')
        self.btnD3.setToolTip('Shift + +')

        self.btnD1.clicked.connect(self.__btnClicked)
        self.btnD2.clicked.connect(self.__btnClicked)
        self.btnD3.clicked.connect(self.__btnClicked)

        self.btnD1.setObjectName('D1')
        self.btnD2.setObjectName('D2')
        self.btnD3.setObjectName('D3')

        self.btnD1.setCursor(Qt.PointingHandCursor)
        self.btnD2.setCursor(Qt.PointingHandCursor)
        self.btnD3.setCursor(Qt.PointingHandCursor)

        vbox = QVBoxLayout()
        vbox.addWidget(self.btnU3)
        vbox.addWidget(self.btnU2)
        vbox.addWidget(self.btnU1)
        vbox.addSpacing(10)
        vbox.addWidget(self.btnD1)
        vbox.addWidget(self.btnD2)
        vbox.addWidget(self.btnD3)
        vbox.setContentsMargins(0,0,0,0)
        vbox.setSpacing(0)
        
        btnW = QWidget()
        btnW.setLayout(vbox)

        hbox = QHBoxLayout()
        hbox.addWidget(ctrW)
        hbox.addWidget(btnW)
        hbox.addWidget(self.sld)
        hbox.addStretch(1)
        # hbox.setContentsMargins(0,0,0,0)

        self.setLayout(hbox)

        self.update()

    def __sldValueChanged(self,value):
        """ Set motor.DPOS if slider moved by user """
        if self.sld.hasFocus():
            self.motor.DPOS.set(value)

    def __sldSetValue(self,value):
        if not self.sld.hasFocus():
            self.sld.setValue(int(value))

    def __qlePosSet(self):
        """ Set motor.DPOS as qlePos looses focus or when pressing enter """
        if self.motor.connected:
            try:    val = float(self.qlePos.text())
            except: val = 0
            self.motor.DPOS.set(val)

    def __qleStepSet(self):
        """
        Set motor.stepSize as qleStep looses focus or when pressing enter
        """
        if self.motor.connected:
            self.motor.stepSize.set(float(self.qleStep.text()))

    def __qleChange(self,obj:QLineEdit,y=None):
        """ Change value of a QLineEdit
        It is invoked by motor.EPOS.signal which emits periodically as
        motor.updateData is called.
        """
        if not obj.hasFocus():
            # Change the value only if the entry does not have focus
            obj.setText(str(y))
            obj.setCursorPosition(0)    # Show beginning of the text, not end

    def __btnClicked(self):
        """ Callback of button click """

        objectName = self.sender().objectName()
        if objectName[0] == 'U':
            sign = -1
        elif objectName[0] == 'D':
            sign = +1
        if objectName[1] == '1':
            multiplier = 0.1
        elif objectName[1] == '2':
            multiplier = 1
        elif objectName[1] == '3':
            multiplier = 5
        self.motor.step(sign * multiplier * self.motor.stepSize.get())      

    def keyPressEvent(self,event):
        """ Reimplementation of the keyPressEvent """

        # If one of QLineEdits has focus, enter key calls appropriate function
        if event.key() in [Qt.Key_Enter,Qt.Key_Return]:
            if self.qlePos.hasFocus():
                self.__qlePosSet()    # Set motor position
            elif self.qleStep.hasFocus():
                self.__qleStepSet()   # Update motor step size

    def update(self,*_):
        """ Update parameters of GUI """

        # Disconnect signals connected with the motor
        try:    self.motor.EPOS.signal.disconnect(self.__sldSetValue)
        except: pass

        # Set up slider according to motor settings
        if self.motor.connected:
            self.lims = self.motor.limits
            self.motor.EPOS.signal.connect(self.__sldSetValue)
            self.sld.setMinimum(self.lims[0])
            self.sld.setMaximum(self.lims[1])
        
        self.sld.setEnabled(self.motor.connected)
        self.qlePos.setEnabled(self.motor.connected)
        self.qleStep.setEnabled(self.motor.connected)

        self.btnD1.setEnabled(self.motor.connected)
        self.btnD2.setEnabled(self.motor.connected)
        self.btnD3.setEnabled(self.motor.connected)
        self.btnU1.setEnabled(self.motor.connected)
        self.btnU2.setEnabled(self.motor.connected)
        self.btnU3.setEnabled(self.motor.connected)

class MoveRGUI(QWidget):
    """
    **Bases:** :class:`QWidget`

    GUI for rotational movements. Analogical to :class:`MoveHGUI`.
    """

    # FUTURE: Buttons can be replaced by a vertical joystick

    def __init__(self,motor=Motor()):
        super().__init__()

        self.motor = motor
        self.motor.LedSig.connected.connect(self.update)

        lbl = QLabel(self.motor.axis_letter)
        lbl.setAlignment(Qt.AlignCenter)

        # QLineEdit - show/set position
        self.qlePos = FocusableQLineEdit(self)
        self.qlePos.setFixedSize(50,25)
        self.qlePos.setToolTip('Motor position')
        self.qlePos.setObjectName('qle_pos')
        # When qlePos looses focus, `self.__qlePosSet` is called (motor.DPOS.set)
        self.qlePos.lostFocus.connect(self.__qlePosSet)
        # Update field value as motor.EPOS changes
        self.motor.EPOS.signal.connect(partial(self.__qleChange,self.qlePos))
        
        # QLineEdit - set step
        self.qleStep = FocusableQLineEdit(self)
        self.qleStep.setFixedSize(50,25)
        self.qleStep.setToolTip('Step size')
        # When qleStep looses focus, `self.__qleStepSet` is called
        # (motor.stepSize.set).
        self.qleStep.lostFocus.connect(self.__qleStepSet)
        # Update field value as motor.stepSize changes
        self.motor.stepSize.signal.connect(partial(self.__qleChange,self.qleStep))

        vbox = QVBoxLayout()
        vbox.addWidget(lbl)
        vbox.addWidget(self.qlePos)
        vbox.addWidget(self.qleStep)
        vbox.addStretch()
        vbox.setContentsMargins(0,0,0,0)
        ctrW = QWidget()
        ctrW.setLayout(vbox)

        # Buttons for left/right steps
        self.btnL = QPushButton('',self)
        self.btnR = QPushButton('',self)

        self.btnL.setIcon(qta.icon('fa.rotate-left'))
        self.btnR.setIcon(qta.icon('fa.rotate-right'))

        self.btnL.setToolTip('<')
        self.btnR.setToolTip('>')

        self.btnL.clicked.connect(self.__btnClicked)
        self.btnR.clicked.connect(self.__btnClicked)

        self.btnL.setObjectName('L')
        self.btnR.setObjectName('R')

        self.btnL.setCursor(Qt.PointingHandCursor)
        self.btnR.setCursor(Qt.PointingHandCursor)

        # Dial widget
        self.qdial = QDial()
        self.qdial.setWrapping(True)
        self.qdial.setCursor(Qt.PointingHandCursor)
        self.qdial.setValue(0)
        self.qdial.valueChanged.connect(self.__qdialChange)
        self.qdial.setMinimum(0)
        self.qdial.setMaximum(360)

        # Put widgets into horizontal layout
        hbox = QHBoxLayout()
        hbox.addWidget(ctrW)
        hbox.addStretch(1)
        hbox.addWidget(self.btnL)
        hbox.addWidget(self.qdial)
        hbox.addWidget(self.btnR)
        hbox.addStretch(1)
        hbox.setContentsMargins(0,0,0,0)

        self.setLayout(hbox)

        self.update()

    def __qlePosSet(self):
        """ Set motor.DPOS as qlePos looses focus or when pressing enter """
        if self.motor.connected:
            try:    val = float(self.qlePos.text())
            except: val = 0
            self.motor.DPOS.set(val)

    def __qleStepSet(self):
        """
        Set motor.stepSize as qleStep looses focus or when pressing enter
        """
        if self.motor.connected:
            self.motor.stepSize.set(float(self.qleStep.text()))

    def __qleChange(self,obj:QLineEdit,y=None):
        """ Change value of a QLineEdit
        It is invoked by motor.EPOS.signal which emits periodically as
        motor.updateData is called.
        """
        if not obj.hasFocus():
            # Change the value only if the entry does not have focus
            obj.setText(str(y))
            obj.setCursorPosition(0)    # Show beginning of the text, not end

    def __btnClicked(self):
        """ Callback of button click """

        objectName = self.sender().objectName()
        if objectName[0] == 'L':
            sign = -1
        elif objectName[0] == 'R':
            sign = +1
        self.motor.step(sign * self.motor.stepSize.get())

    def __qdialChange(self,value):
        """ Called when qdial value is changed -> set motor DPOS"""
        if self.qdial.hasFocus():
            self.motor.DPOS.set(value)

    def __qdialSet(self,value):
        """ Set value of self.qdial if not affected by user.
        Usually signal of motor.EPOS emits and calls this function.
        """
        if not self.qdial.hasFocus():
            self.qdial.setValue(int(value))

    def keyPressEvent(self,event):
        """ Reimplementation of the keyPressEvent """

        # If one of QLineEdits has focus, enter key calls appropriate function
        if event.key() in [Qt.Key_Enter,Qt.Key_Return]:
            if self.qlePos.hasFocus():
                self.__qlePosSet()    # Set motor position
            elif self.qleStep.hasFocus():
                self.__qleStepSet()   # Update motor step size

    def update(self,*_):
        """ Update parameters of GUI """

        # Disconnect signals connected with the motor
        try:    self.motor.EPOS.signal.disconnect(self.__qdialSet)
        except: pass

        if self.motor.connected:
            self.motor.EPOS.signal.connect(self.__qdialSet)
        
        self.qlePos.setEnabled(self.motor.connected)
        self.qleStep.setEnabled(self.motor.connected)
        self.qdial.setEnabled(self.motor.connected)

        self.btnL.setEnabled(self.motor.connected)
        self.btnR.setEnabled(self.motor.connected)

class XYWidget(QWidget):
    """
    **Bases:** :class:`QWidget`

    It contains canvas with sample geometry, sliders horizontal and vertical
    movements. Enable and disable of control widgets is handled by
    :func:`update`. Function :func:`keyPressEvent` catches navigation arrows so
    motors can be moved with keyboard.

    Tip:
        Keypress can be caught by :func:`keyPressEvent` only if this widget has
        a focus. Therefore, ``eventFilter`` should be installed within the main
        window and ``ESC`` key press should set focus to this widget.

    Args:
        motorX (:class:`Motor`): Pointer to the motor for horizontal movements.
        motorY (:class:`Motor`): Pointer to the motor for vertical movements.

    """

    # TODO: Canvas -> right click -> add custom point

    def __init__(self,motorX=Motor(),motorY=Motor()):
        super().__init__()      # Init QWidget

        # Widget's variables ---------------------------------------------------
        self.CS = 1             # Coordinate system number
        self.motorX = motorX    # Xeryon motor X
        self.motorY = motorY    # Xeryon motor Y

        self.motorX.LedSig.connected.connect(self.update)
        self.motorY.LedSig.connected.connect(self.update)

        # Limits of motors (used for drawing canvas and sliders)
        self.xlim = [-1,1]
        self.ylim = [-1,1]

        # Option to cange coordinate system ------------------------------------
        lbl = QLabel('Coordinate system:')
        self.lblCoords = QLabel('Motors')
        self.lblCoords.setStyleSheet('font-weight: bold')
        self.btnChange = QPushButton('Change',self)
        self.btnChange.setObjectName('btn_coord_change')
        self.btnChange.clicked.connect(self.__btnClicked)
        self.btnChange.setCursor(Qt.PointingHandCursor)
        cdL = QHBoxLayout()
        cdL.addWidget(lbl)
        cdL.addWidget(self.lblCoords)
        cdL.addWidget(self.btnChange)
        cdL.setContentsMargins(0,0,0,0)
        cdW = QWidget()
        cdW.setLayout(cdL)

        # XY sliders -----------------------------------------------------------

        # Sliders
        self.sldX = QSlider(Qt.Horizontal,self)
        self.sldX.setObjectName("slider_X")
        self.sldX.setCursor(Qt.PointingHandCursor)
        # self.sldY = al.DoubleSlider(Qt.Vertical,self)
        self.sldY = QSlider(Qt.Vertical,self)
        self.sldY.setObjectName("slider_Y")
        self.sldY.setCursor(Qt.PointingHandCursor)

        # Connect action to sliders
        self.sldX.valueChanged.connect(self.__sldValueChanged)
        self.sldY.valueChanged.connect(self.__sldValueChanged)

        self.update()

        # Menu bar for plot actions --------------------------------------------
        # TODO: Complete menu bar actions:
        # $ [ ] Move motors
        # $ [ ] Horizontal alignment
        # $ [ ] Add point
        self.pbtnMove = QPushButton('Move',self)
        self.pbtnMove.setObjectName('pbtn_move')
        self.pbtnMove.clicked.connect(self.__btnClicked)
        self.pbtnMove.setCursor(Qt.PointingHandCursor)

        self.pbtnHAlign = QPushButton('HAlign',self)
        self.pbtnHAlign.setObjectName('pbtn_halign')
        self.pbtnHAlign.clicked.connect(self.__btnClicked)
        self.pbtnHAlign.setCursor(Qt.PointingHandCursor)

        pbtnHBox = QHBoxLayout()
        pbtnHBox.setContentsMargins(0,0,0,0)
        pbtnHBox.addWidget(self.pbtnMove)
        pbtnHBox.addWidget(self.pbtnHAlign)
        pbtnHBox.addStretch()

        pbtnW = QWidget()
        pbtnW.setLayout(pbtnHBox)

        # Canvas ---------------------------------------------------------------
        pgW = pg.GraphicsLayoutWidget()             # New widget for graphics
        pgW.setBackground('w')                      # White background
        pgW.ci.layout.setContentsMargins(0,0,0,0)   # Remove margins of pgW
        self.plt = pgW.addPlot()                    # Create new plot
        self.plt.setAspectLocked()                  # Lock axes aspect ratio
        self.plt.setMenuEnabled(False)              # Disable right click

        # Add text field to show mouse pointer coordinates
        self.txt = pg.TextItem('dsf', color='k', fill=(255,255,255, 200))
        self.txt.setFont(QFont('Arial',10))
        self.txt.setParentItem(self.plt)
        self.txt.setVisible(False)              # Visible only on mouse hover

        # Cross hairs
        self.vlineMouse = pg.InfiniteLine(angle=90,movable=False)
        self.hlineMouse = pg.InfiniteLine(angle= 0,movable=False)
        pen = pg.mkPen('k',width=1,style=Qt.DashLine)
        self.vlineEPOS = pg.InfiniteLine(angle=90,movable=False,pen=pen)
        self.hlineEPOS = pg.InfiniteLine(angle= 0,movable=False,pen=pen)
        self.plt.addItem(self.vlineMouse,ignoreBounds=True)
        self.plt.addItem(self.hlineMouse,ignoreBounds=True)
        self.plt.addItem(self.vlineEPOS,ignoreBounds=True)
        self.plt.addItem(self.hlineEPOS,ignoreBounds=True)

        # Connect mouse events
        # self.plt.scene().sigMouseMoved.connect(self.__canvasMouseMoved)
        self.proxy = pg.SignalProxy(self.plt.scene().sigMouseMoved,
            rateLimit=60,slot=self.__canvasMouseMoved)
        self.plt.scene().sigMouseClicked.connect(self.__canvasMouseClick)

        self.rectMotorLims = None

        # Hide axes
        self.plt.showAxis('bottom',False)
        self.plt.showAxis('left',False)

        # Put canvas and sliders into a grid layout
        xyL = QGridLayout()
        xyL.addWidget(self.sldY,0,0)
        xyL.addWidget(self.sldX,1,1)
        xyL.addWidget(pgW,0,1)
        xyL.setContentsMargins(0,0,0,0)
        xyW = QWidget()
        xyW.setLayout(xyL)

        # Widget's main layout -------------------------------------------------
        mainL = QVBoxLayout()
        mainL.setContentsMargins(0,0,0,0)
        mainL.addWidget(cdW)    # Coordinate system settings
        mainL.addWidget(pbtnW)  # Menu buttons for plot
        mainL.addWidget(xyW)    # Canvas and XY sliders

        self.setLayout(mainL)

        self.setMinimumHeight(250)
        self.setMaximumHeight(300)

    def __canvasMouseMoved(self,event):
        """ Called when mouse moves over the canvas """
        pos = event[0]
        if self.plt.sceneBoundingRect().contains(pos):
            mousePoint = self.plt.vb.mapSceneToView(pos)
            x = mousePoint.x()
            if   x < self.xlim[0]:  x = self.xlim[0]
            elif x > self.xlim[1]:  x = self.xlim[1]
            self.vlineMouse.setPos(x)

            y = mousePoint.y()
            if   y < self.ylim[0]:  y = self.ylim[0]
            elif y > self.ylim[1]:  y = self.ylim[1]
            self.hlineMouse.setPos(y)

            # Show mouse pointer coordinates
            self.txt.setVisible(True)
            self.txt.setText('[%0.1f,%0.1f]'%(x,y))
        else:
            # Hide coordinates when mouse is out
            self.txt.setVisible(False)

    def __canvasMouseClick(self,event):
        """ Called when mouse clicks on the canvas """
        if event.button() == 1:
            # Left click
            pos = event.scenePos()
            mousePoint = self.plt.vb.mapSceneToView(pos)
            x = mousePoint.x()
            y = mousePoint.y()
            print(f"XYWidget:__canvasMouseClick(): ({x},{y})")
            self.__moveX(x)
            self.__moveY(y)
        elif event.button() == 2:
            # Right click
            self.plt.autoRange()
        elif event.button() == 4:
            # Middle click
            pass

    def __XEPOSChanged(self,value):
        """ EPOS of motor X changed """
        # --> change position of vertical line
        self.vlineEPOS.setPos(value)
        # --> change position of sldX (if not moved by user)
        if not self.sldX.hasFocus():
            self.sldX.setValue(int(value))

    def __YEPOSChanged(self,value):
        """ EPOS of motor Y changed """
        # --> change position of horizontal line
        self.hlineEPOS.setPos(value)
        # --> change position of sldY (if not moved by user)
        if not self.sldY.hasFocus():
            self.sldY.setValue(int(value))

    def __btnClicked(self):
        """ Any button click callback """
        sender = self.sender()
        if sender.objectName() == 'btn_coord_change':
            # Change coordinate system
            self.CS += 1
            if self.CS > 2: self.CS = 1
            if self.CS == 1:
                self.lblCoords.setText('Motors')
            elif self.CS == 2:
                self.lblCoords.setText('Sample')

    def __sldValueChanged(self,value):
        """ If slider moved manually by user, set DPOS """
        sender = self.sender()
        if sender.hasFocus():
            if sender.objectName() == 'slider_X':
                self.__moveX(value)
            elif sender.objectName() == 'slider_Y':
                self.__moveY(value)

    def __moveX(self,value):
        """ Move in x-direction """
        # This function handles which coordinate system is set and then moves
        # with xeryon motors accordingly
        if self.motorX.connected:
            if self.CS == 1:
                self.motorX.DPOS.set(value)

    def __moveY(self,value):
        """ Move in y-direction """
        # This function handles which coordinate system is set and then moves
        # with xeryon motors accordingly
        if self.motorY.connected:
            if self.CS == 1:
                self.motorY.DPOS.set(value)

    def __stepX(self,value):
        """ Step `value` in x-direction """
        self.motorX.step(value)

    def __stepY(self,value):
        """ Step `value` in y-direction """
        self.motorY.step(value)

    def keyPressEvent(self,event):
        """ Reimplementation of the keyPressEvent
        This method can be moved to a separate class in future.
        """

        # print("XY:",event.key())

        # Define step multiplier according to active keyboard modifier
        multiplier = 1
        if (event.modifiers() & Qt.ShiftModifier):
            multiplier = 5
        elif (event.modifiers() & Qt.ControlModifier):
            multiplier = 0.1

        # Step according to pressed arrow
        if event.key() == Qt.Key_Left:
            self.__stepX(-self.motorX.stepSize.get() * multiplier)
        elif event.key() == Qt.Key_Right:
            self.__stepX(+self.motorX.stepSize.get() * multiplier)
        elif event.key() == Qt.Key_Down:
            self.__stepY(-self.motorY.stepSize.get() * multiplier)
        elif event.key() == Qt.Key_Up:
            self.__stepY(+self.motorY.stepSize.get() * multiplier)

    def update(self,*_):
        """ Update canvas, sliders (limits and enable) """

        # Disconnect signals connected with motorX
        try:    self.motorX.EPOS.signal.disconnect(self.__XEPOSChanged)
        except: pass
        # Set up sliders according to motor settings
        if self.motorX.connected:
            self.xlim = self.motorX.limits
            self.sldX.setEnabled(True)
            self.sldX.setMinimum(self.xlim[0])  # Set low limit
            self.sldX.setMaximum(self.xlim[1])  # Set high limit
            # Connect signals
            self.motorX.EPOS.signal.connect(self.__XEPOSChanged)
        else:
            self.sldX.setEnabled(False)         # Disable sliderX
        
        # Disconnect signals connected with motorX
        try:    self.motorY.EPOS.signal.disconnect(self.__YEPOSChanged)
        except: pass
        # Set up sliders according to motor settings
        if self.motorY.connected:
            self.sldY.setEnabled(True)
            self.ylim = self.motorY.limits
            self.sldY.setMinimum(self.ylim[0])  # Set low limit
            self.sldY.setMaximum(self.ylim[1])  # Set high limit
            # Connect signals
            self.motorY.EPOS.signal.connect(self.__YEPOSChanged)
        else:
            self.sldY.setEnabled(False)         # Disable sliderY

        # Remove rectangle indicating motor limits
        try:    self.plt.removeItem(self.rectMotorLims)
        except: pass
        # Draw rectangle
        if self.motorX.connected and self.motorY.connected:
            # Plot motor range to the canvas
            pen = pg.mkPen('k',width=2)
            brush = pg.mkBrush(50,50,200,50)
            self.rectMotorLims = al.PgRectangle(
                [self.xlim[0],self.ylim[0]],
                [self.xlim[1]-self.xlim[0],self.ylim[1]-self.ylim[0]],
                pen=pen,brush=brush)
            self.plt.addItem(self.rectMotorLims)
        else:
            # TODO: Hide cross lines and display a "connection needed" message
            pass

class MenuActionSettingsFile(QAction):
    """
    **Bases:** :class:`QAction`

    QAction to edit *Xeryon settings file* using embedded editor.
    Import this QAction into menu.

    Args:
        parentCloseSignal: Signal is connected to :func:`parentClose`
            which closes the editor if opened.
    """

    def __init__(self, parent=None, parentCloseSignal=None):
        super().__init__('&Edit Xeryon settings...',parent)

        self.setStatusTip('Edit Xeryon settings file')
        self.triggered.connect(self.edit)
        self.setIcon(al.standardIcon('SP_FileDialogContentsView'))

        self.editor = None

        if parentCloseSignal is not None:
            parentCloseSignal.connect(self.parentClose)

    def edit(self):
        """ Action connected to the QAction - open and edit Xeryon file """
        self.editor = TextEditorGUI()
        self.editor.show()
        self.editor.OpenFile(xe.SETTINGS_FILENAME)

    def parentClose(self):
        try:    self.editor.close()
        except: pass

class XeryonGUI(QWidget):
    """
    **Bases:** :class:`QWidget`

    Main GUI for Xeryon motors. It is optimized to show what all can be done
    rather than to be implemented into larger application.
    """

    def __init__(self,parentCloseSignal=None,
                 motorX=Motor(),motorY=Motor(),motorZ=Motor(),motorR=Motor()):
        super().__init__()

        layout = QVBoxLayout()


        self.xywidget = XYWidget(motorX=motorX,motorY=motorY)
        layout.addWidget(self.xywidget)

        layout.addWidget(MoveHGUI(motor=motorX))
        layout.addWidget(MoveHGUI(motor=motorY))

        layout.addWidget(MoveVGUI(motor=motorZ))

        layout.addWidget(MoveRGUI(motor=motorR))

        layout.addWidget(StatusGUI(motor=motorX))
        layout.addWidget(StatusGUI(motor=motorY))
        layout.addWidget(StatusGUI(motor=motorZ))
        layout.addWidget(StatusGUI(motor=motorR))

        layout.addStretch(1)

        self.setLayout(layout)

        if parentCloseSignal is not None:
            parentCloseSignal.connect(self.parentClose)

    def parentClose(self):
        pass

class XeryonMainWindow(QMainWindow):
    """
    **Bases:** :class:`QMainWindow`

     Main window which encapsulates :class:`XeryonGUI` as the central widget.
     Opens upon standalone execution of the ``xeryon`` module. It also connects
     several xeryon stages, inits menubar, statusbar and installs event filter
     to catch key press."""

    def __init__(self):
        super().__init__()

        self.setGeometry(100,100,300,300)
        self.setWindowTitle("Xeryon GUI")

        self.signals = al.Signals()

        # Motors ---------------------------------------------------------------

        self.motorX = Motor(
            axis_letter='X',
            closeSignal=self.signals.closeParent)

        self.motorY = Motor(
            axis_letter='Y',
            closeSignal=self.signals.closeParent)
        
        self.motorZ = Motor(
            axis_letter='Z',
            closeSignal=self.signals.closeParent)

        self.motorR = Motor(
            axis_letter='R',
            closeSignal=self.signals.closeParent,
            stepSize=10,
            speed=100)

        self.xeryonGUI = XeryonGUI(
            parentCloseSignal=self.signals.closeParent,
            motorX = self.motorX,
            motorY = self.motorY,
            motorZ = self.motorZ,
            motorR = self.motorR)

        self.motorX.connect()
        self.motorY.connect()
        self.motorZ.connect()
        self.motorR.connect()

        # self.motorY.findIndex()

        self.setCentralWidget(self.xeryonGUI)

        # Create menubar -------------------------------------------------------

        settingsAct = MenuActionSettingsFile(self,
            parentCloseSignal=self.signals.closeParent)

        menubar = self.menuBar()
        settingsMenu = menubar.addMenu('&Settings')
        settingsMenu.addAction(settingsAct)

        # Statusbar ------------------------------------------------------------
        self.statusbar = self.statusBar()

        self.show()

        qApp.installEventFilter(self)
        # self.xeryonGUI.xywidget.setFocus()
        # self.micGUI.xystage.setFocus()  # Default focus to XY widget

    def eventFilter(self,source,event):
        """ Reimplementation of `eventFilter` to catch ``ESC``. """
        if event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Escape:
                self.xeryonGUI.xywidget.setFocus()

        return super(XeryonMainWindow,self).eventFilter(source,event)

    def closeEvent(self,*_):
        """ Reimplement closeEvent() so :attr:`~signals_closeParent` can emit.
        """
        self.signals.closeParent.emit()

def main():
    """ Function used for standalone execution. It opens main window
    :class:`XeryonMainWindow` and ensures clean exit.
    """
    app = QApplication(sys.argv)
    handle = XeryonMainWindow()     # pylint: disable=unused-variable
    sys.exit(app.exec_())

if __name__ == "__main__":
    """ Run `main()` for standalone execution. """
    main()
