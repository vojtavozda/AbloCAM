"""
AbloCAM
=======

just some edit
signed?
"""


# TODO =========================================================================
# ! [ ] Get started with readtheocs.io and create documentation
# ! [ ] How to speed up PyQt5 ???
# $ [.] Add Z-movements
# @   [x] Create new file navitary.py
# !   [.] Build a small GUI for Navitar motors
# @   [x] Add Xeryon Z-stage (the same GUI as for Navitar?)
# $ [ ] Add settings for Basler camera (exposure time, max fps)
# @ [x] Improve GUI for rotational stage
# $ [ ] Define points (display on XY widget, two points -> rotate to horizontal)
# $ [ ] Define sample dimensions -> Show sample on XY widget, define sample coords
# TODO =========================================================================

import sys

from datetime import datetime

from basler import BaslerGUI

from PyQt5.QtCore import Qt, QEvent
from PyQt5 import QtCore

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout,
    QVBoxLayout, QGroupBox, QDesktopWidget, QPushButton, QSlider, QGridLayout,
    QDial, QAction, qApp, QLabel)

from PyQt5.QtGui import QPixmap, QIcon

from ablolib import Signals

import qtawesome as qta

import ablolib as al
import xeryon

class GoogleDocExample():
    """This is an example of a module level function.
    edit number 2

    Function parameters should be documented in the ``Args`` section. The name
    of each parameter is required. The type and description of each parameter
    is optional, but should be included if not obvious.

    If \*args or \*\*kwargs are accepted,
    they should be listed as ``*args`` and ``**kwargs``.

    The format for a parameter is::

        name (type): description
            The description may span multiple lines. Following
            lines should be indented. The "(type)" is optional.

            Multiple paragraphs are supported in parameter
            descriptions.

    Args:
        param1 (int): The first parameter.
        param2 (:obj:`str`, optional): The second parameter. Defaults to None.
            Second line of description should be indented.
        *args: Variable length argument list.
        **kwargs: Arbitrary keyword arguments.

    Returns:
        bool: True if successful, False otherwise.

        The return type is optional and may be specified at the beginning of
        the ``Returns`` section followed by a colon.

        The ``Returns`` section may span multiple lines and paragraphs.
        Following lines should be indented to match the first line.

        The ``Returns`` section supports any reStructuredText formatting,
        including literal blocks::

            {
                'param1': param1,
                'param2': param2
            }
    Muhaha!
    Raises:
        AttributeError: The ``Raises`` section is a list of all exceptions
            that are relevant to the interface.
        ValueError: If `param2` is equal to `param1`.

    """

    def meth(self):
        print("edit no. 3")

class MicGUI(QWidget):

    def __init__(self,parentCloseSignal=None,messageSignal=None):
        super().__init__()


        # Build GUI ============================================================

        # Structure: self -> mainVBox -> GB -> vbox -> Basler

        # MicGUI
        # └── mainVBox
        #     ├─── baslerGB
        #     │    ├─── box A
        #     │    └─── box B
        #     └─── xeryonGB

        # Basler camera --------------------------------------------------------
        self.basler = BaslerGUI(
            parentCloseSignal=parentCloseSignal,
            messageSignal=messageSignal)
        self.basler.layout.setContentsMargins(0,0,0,0)
        self.basler.plotFromThread = False

        vbox = QVBoxLayout()
        vbox.addWidget(self.basler)

        baslerGB = QGroupBox('Basler camera')
        baslerGB.setLayout(vbox)

        # XY stage control -----------------------------------------------------
       
        # Init Xeryon motor X (motor is connected below)
        self.motorX = xeryon.Motor(
            axis_letter='Z3',
            closeSignal = parentCloseSignal)

        # Init Xeryon motor Y (motor is connected below)
        self.motorY = xeryon.Motor(
            axis_letter='Y',
            closeSignal = parentCloseSignal)

        # Init XYWidget (coordinate system settings, canvas, XY sliders)
        self.xystage = xeryon.XYWidget(motorX=self.motorX,motorY=self.motorY)
        
        vbox = QVBoxLayout()
        vbox.addWidget(self.xystage)
        # Add movement buttons for motorX and motorY
        vbox.addWidget(xeryon.MoveHGUI(motor=self.motorX))
        vbox.addWidget(xeryon.MoveHGUI(motor=self.motorY))

        xyGB = QGroupBox('XY stage')
        xyGB.setLayout(vbox)

        # Z stage & Navitar control --------------------------------------------

        # Rotational stage -----------------------------------------------------

        self.motorR = xeryon.Motor(
            axis_letter = 'R',
            closeSignal = parentCloseSignal)

        qdial = QDial()
        qdial.setWrapping(True)
        qdial.setValue(50)
        # qdial.valueChanged.connect(print)

        vbox = QVBoxLayout()
        vbox.addWidget(qdial)

        rotateGB = QGroupBox('Rotational stage')
        rotateGB.setLayout(vbox)

        # Xeryon motors --------------------------------------------------------
        vbox = QVBoxLayout()
        vbox.addWidget(xeryon.StatusGUI(motor=self.motorX))
        vbox.addWidget(xeryon.StatusGUI(motor=self.motorY))

        xeryonGB = QGroupBox('Xeryon motors')
        xeryonGB.setLayout(vbox)

        # Put everything together ----------------------------------------------

        mainVBox = QVBoxLayout()
        mainVBox.addWidget(baslerGB)
        mainVBox.addWidget(xyGB)
        mainVBox.addWidget(rotateGB)
        mainVBox.addWidget(xeryonGB)
        mainVBox.addStretch(1)

        self.setLayout(mainVBox)

        # Functions ============================================================

        self.motorX.connect()
        self.motorY.connect()
        self.xystage.update()

    def closeEvent(self,*_):
        print("MicGUI::closeEvent")

class MicMainWindow(QMainWindow):
    """
    MicMainWindow
    =============

    Main window for microscope control

    """

    def __init__(self):
        super().__init__()

        self.initUI()

    def initUI(self):

        self.setGeometry(0,0,400,1000)

        # Move window to desired monitor
        display_monitor = 1
        monitor = QDesktopWidget().screenGeometry(display_monitor)
        self.move(monitor.left(),monitor.top())

        self.setWindowTitle("Ablo Microscope")

        self.signals = Signals()

        self.micGUI = MicGUI(
            parentCloseSignal = self.signals.closeParent,
            messageSignal = self.signals.message
        )
        self.setCentralWidget(self.micGUI)

        # self.setFocusPolicy(Qt.NoFocus)

        # Create status bar ----------------------------------------------------
        self.statusbar = self.statusBar()
        self.signals.message.connect(self.messageCallback)

        # Create menubar -------------------------------------------------------

        # File -> Exit
        exitAct = QAction('&Exit',self)
        exitAct.setStatusTip('Close application')
        exitAct.setShortcut('Ctrl+Q')
        exitAct.setIcon(al.standardIcon('SP_BrowserStop'))
        exitAct.triggered.connect(self.closeEvent)

        # View -> Logfile
        logAct = QAction('&Logfile',self)
        logAct.setStatusTip('View logfile')
        logAct.setIcon(al.standardIcon('SP_FileDialogContentsView'))
        logAct.triggered.connect(self.showLogFile)

        # Settings -> Xeryon
        xesAct = xeryon.MenuActionSettingsFile(self)

        # Compose menu
        menubar = self.menuBar()
        fileMenu = menubar.addMenu('&File')
        viewMenu = menubar.addMenu('&View')
        stgsMenu = menubar.addMenu('&Settings')

        fileMenu.addAction(exitAct)     # File -> Exit
        viewMenu.addAction(logAct)      # View -> Logfile
        stgsMenu.addAction(xesAct)      # Settings -> Edit Xeryon settings

        self.show()

        # Set up focus policy: Arrows should be used for stage control and not
        # for switching focus between buttons. Following event filter catches
        # all keys and sets focus to `micGUI.xystage` when pressing `Esc`.
        qApp.installEventFilter(self)
        self.micGUI.xystage.setFocus()  # Default focus to XY widget


    def eventFilter(self,source,event):
        if event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Escape:
                self.micGUI.xystage.setFocus()

        return super(MicMainWindow,self).eventFilter(source,event)

    def showLogFile(self):
        # TODO
        al.printW("MicMainWindow::showLogFile -> Not done yet!")

    def messageCallback(self,msg):
        time = datetime.now().strftime('%H:%M:%S')
        msg = time + " " + msg
        # TODO: Save message into logfile
        self.statusbar.showMessage(msg)

    def closeEvent(self,*_):
        print("MicMainWindow::closeEvent")
        self.signals.closeParent.emit()
        QApplication.instance().quit()

def main():
    """ Call this function to open full microscope GUI """
    app = QApplication(sys.argv)

    app.setStyle('Fusion')

    # Set style which is defined in a separate file
    styleFile = "AbloGUI_pyqt/ablo.css"
    with open(styleFile,'r') as fh:
        app.setStyleSheet(fh.read())

    handle = MicMainWindow()
    sys.exit(app.exec_())   # Run main loop and ensure clean exit

if __name__ == "__main__":
    pass
    # main()
