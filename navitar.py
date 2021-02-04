"""
Control for Navitar motors
"""

import sys
import time
import datetime
import numpy as np
from PyQt5.QtCore import (Qt, QThreadPool, QObject, QRunnable, pyqtSlot,
    pyqtSignal, QPoint, QEvent, QTimer)
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QPushButton,
    QHBoxLayout, QVBoxLayout, QStyle, QAbstractButton, QLabel, QSlider,
    QGridLayout, QLineEdit, qApp, QMenu, QAction)
from PyQt5.QtGui import QPainter, QPen, QBrush, QColor, QPicture

import qtawesome as qta     # use bash: `qta-browser` to see icon list

import ablolib as al

import serial
from serial.tools import list_ports

def GetSerialPort(serial_number):
    """ Find serial port corresponding to given serial number """
    # TODO: Similar function is used in `xeryon. py` --> consider merge

    device_list = list_ports.comports()
    for device in device_list:
        if device.serial_number == serial_number:
            return device.device
    al.printE(f"GetSerialPort: Device with serial number '{serial_number}' not found!")
    return None

class DynVar(QObject):
    """
    Dynamic variable with:
    `set()` - set new value
    `get()` - read value
    `signal` - signal can emit and be caught be a slot function
    """

    # TODO: The same function is used in `xeryon.py` --> move both to ablolib?

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

class Motor:
    """
    Navitar motor
    =============
    """

    def __init__(self,axis_letter='N',closeSignal=None):
        # TODO: `axis_letter` should characterize particular Navitar motor
        self.connected = False

        self.ser = None         # Initiated in `self.connect`
        self.serial = None      # Name of serial port

        self.limits = [-5,5]    # TODO: Set proper limits (get in `connect`?)

        if closeSignal is not None:
            closeSignal.connect(self.disconnect)

        if axis_letter != '':

            print(f"Navitar motor {axis_letter} object created!")

            self.axis_letter = axis_letter

            self.DPOS = DynVar(0)   # Desired position set by user
            self.DPOS.signal.connect(self.__setDPOS)

            self.EPOS = DynVar(0)   # Estimated position returned by controller

            self.stepSize = DynVar(1)

            ser = GetSerialPort(0)

            if ser is None:
                al.printW(f"Navitar motor '{axis_letter}' not connected!")
            else:
                self.serial = ser
        else:
            # Just initialization of a motor instance
            pass

    def connect(self):
        """ Connect Navitar motor """

        self.ser = serial.Serial(
            port=self.serial,               # serial port
            baudrate=115200,                # it works
            parity=serial.PARITY_NONE,      # common serial settings
            stopbits=serial.STOPBITS_ONE,   # common serial settings
            bytesize=serial.EIGHTBITS,      # common serial settings
            xonxoff=True,                   # I'm not sure about this
            timeout=0)                      # do not wait forever for a new line

        self.connected = True # TODO: Check if this is realy True

    def disconnect(self):
        """ Disconnect Navitar motor """
        
        self.ser.close()
        self.connected = False

    def sendCommand(self,cmd):
        """ Send command to serial """
        # TODO: Run this function in a separate thread (waiting needed)?
        # Remove all residual data waiting on input
        while self.ser.in_waiting > 0:
            self.ser.readline()
        cmd = cmd.rstrip() + "\n"       # Strip all new lines and add own
        self.ser.write(cmd.encode())    # Write command to serial
        self.ser.flush()                # Wait for all data to be sent
    
        timeout = 0.5*1e6 + datetime.datetime.now().microsecond
        while datetime.datetime.now().microsecond < timeout:

            self.ser.readline()             # Get rid of one line
            response = self.ser.readline().decode().rstrip()    # Read response
            try:
                number = int(response)
                return number
            except:
                return None

        # Timeout reached
        return None

    def step(self,stepSize=None):
        """
        Perform a step of a give size.

        Args:
            stepSize (float, optional): Size of the step. Defaults to
                self.stepSize.get().
        """
        if stepSize is None:
            stepSize = self.stepSize.get()

        self.DPOS.set(float(self.DPOS.get())+stepSize)

    def __setDPOS(self):
        """ Private function is called when `self.DPOS.signal` emits """
        # print("Motor::__setDPOS",self.DPOS.get())

        # Check if DPOS does not exceed limits
        # (note that this function is called again when DPOS.set() is called)
        if self.DPOS.get() < self.limits[0]:
            self.DPOS.set(self.limits[0])       # Correct low limit
        elif self.DPOS.get() > self.limits[1]:
            self.DPOS.set(self.limits[1])       # Correct high limit
        else:
            self.sendCommand("my_DPOS_message") # TODO: Send proper message

class VControl(QWidget):
    """ GUI for vertical movements """

    # FUTURE: Buttons can be replaced by a vertical joystick

    def __init__(self,motor=Motor()):
        super().__init__()

        self.motor = motor

        self.sld = QSlider(Qt.Vertical,self)
        self.sld.setFocusPolicy(Qt.NoFocus)

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

        self.btnU1.clicked.connect(self.btnClicked)
        self.btnU2.clicked.connect(self.btnClicked)
        self.btnU3.clicked.connect(self.btnClicked)

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

        self.btnD1.clicked.connect(self.btnClicked)
        self.btnD2.clicked.connect(self.btnClicked)
        self.btnD3.clicked.connect(self.btnClicked)

        self.btnD1.setObjectName('U1')
        self.btnD2.setObjectName('U2')
        self.btnD3.setObjectName('U3')

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
        hbox.addWidget(self.sld)
        hbox.addWidget(btnW)
        # hbox.setContentsMargins(0,0,0,0)

        self.setLayout(hbox)

        self.update()
        
    def btnClicked(self):
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

    def update(self,*_):
        """ Update parameters of GUI """

        # Disconnect signals connected with the motor
        try:    self.motor.EPOS.signal.disconnect(self.sld.setValue)
        except: pass

        # Set up slider according to motor settings
        if self.motor.connected:
            self.lims = self.motor.limits
            self.motor.EPOS.signal.connect(self.sld.setValue)
            self.sld.setMinimum(self.lims[0])
            self.sld.setMaximum(self.lims[1])

        self.btnD1.setEnabled(self.motor.connected)
        self.btnD2.setEnabled(self.motor.connected)
        self.btnD3.setEnabled(self.motor.connected)
        self.btnU1.setEnabled(self.motor.connected)
        self.btnU2.setEnabled(self.motor.connected)
        self.btnU3.setEnabled(self.motor.connected)


class NavitarGUI(QWidget):

    """ Main GUI for Navitar motors """

    def __init__(self,motorZ1=Motor(),motorZ2=Motor()):
        super().__init__()

        self.vcontrol1 = VControl(motor=motorZ1)
        self.vcontrol2 = VControl(motor=motorZ2)

        hbox = QHBoxLayout()
        hbox.addWidget(self.vcontrol1)
        hbox.addWidget(self.vcontrol2)
        hbox.addStretch(1)

        vbox = QVBoxLayout()
        vbox.addLayout(hbox)
        vbox.addStretch(1)

        self.setLayout(vbox)

class NavitarMainWindow(QMainWindow):

    """ Main window which encapsulates Navitar GUI """

    def __init__(self):
        super().__init__()

        self.initUI()

    def initUI(self):

        self.setGeometry(100,100,300,300)
        self.setWindowTitle("Navitar GUI")

        self.signals = al.Signals()

        # Motors ---------------------------------------------------------------

        self.motorZ1 = Motor(
            axis_letter='Z1',
            closeSignal = self.signals.closeParent)
        self.motorZ2 = Motor(
            axis_letter='Z2',
            closeSignal = self.signals.closeParent)

        self.navitarGUI = NavitarGUI(
            motorZ1 = self.motorZ1,
            motorZ2 = self.motorZ2)

        self.motorZ1.connect()
        self.motorZ2.connect()

        self.setCentralWidget(self.navitarGUI)



        # Statusbar ------------------------------------------------------------
        self.statusbar = self.statusBar()

        self.show()

    def closeEvent(self,*_):
        """ Reimplement closeEvent() """
        self.signals.closeParent.emit()

def main():
    """ Run this if this is the main file """
    app = QApplication(sys.argv)
    handle = NavitarMainWindow()     # pylint: disable=unused-variable
    sys.exit(app.exec_())

if __name__ == "__main__":

    main()
