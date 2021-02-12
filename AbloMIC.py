"""
AbloMIC
=======

Module used to build GUI for microscope control. Optimized for executing as
`main` file (see :func:`main`). It opens main window (:class:`MicMainWindow`)
which contains :class:`MicGUI` as a central widget which encapsulates all other
widgets imported from different modules. The application is built on ``PyQt5``.

The microscope employs **Xeryon** and **Navitar** motors for precise movements
and **Basler** camera for grabbing pictures and video.

Todo:
    Microscope should have an autofocus feature. This can be done, for example,
    by **OpenCV** and blur detection as described `here
    <https://www.pyimagesearch.com/2015/09/07/blur-detection-with-opencv/>`_.

"""


# TODO =========================================================================
# @ [x] Get started with readtheocs.io and create documentation
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

class MicGUI(QWidget):
    """ 
    **Bases:** :class:`QWidget`

    GUI which is set as the central widget of :class:`MicMainWindow`. It inits
    all devices (**Basler**, **Navitar**, **Xeryon**), imports appropriate
    widgets and puts it together.

    Attributes:
        basler: Instance of :class:`basler.BaslerGUI` which inits and controls
            Basler camera.
        motorX: Instance of :class:`xeryon.Motor`
        motorY: Instance of :class:`xeryon.Motor`
        motorR: Instance of :class:`xeryon.Motor`
        motorZ: Instance of :class:`xeryon.Motor`

        xystage: Widget of :class:`xeryon.XYWidget`

    Args:
        parentCloseSignal (:class:`pyqtSignal`): Handle of this signal is
            forwarded to other widgets and motor instances so clean exit is ensured
            when :class:`MicMainWindow` is closed. Defaults to None.
        messageSignal (:class:`pyqtSignal`): Handle of signal which is connected
            to :func:`MicMainWindow.messageCallback` so any message emitted by this
            signal can be shown in the statusbar. Defaults to None.

    """

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
    **Bases:** :class:`QMainWindow`

    Main window for microscope control. It is useful for initialization of
    `menubar` and `statusbar` which are not parts of :class:`QWidget`.
    Reimplementation of :func:`eventFilter` also makes catching of all key
    presses possible.

    Attributes:
        signals_message: Connected to :func:`messageCallback` to show
            message emitted by childrens. In order to show a message in the
            `statusbar` just forward pointer of this signal as an argument to a
            custom function end `emit` message as `mySignal.emit("my message")`.
        signals_closeParent: This signal emits when this main window is closed.
            Connect it to custom function which closes other windows, disconnects
            motors, etc.

    """

    def __init__(self):
        """
        **Steps:**

            - set window position, title, etc.
            - set central widget :class:`MicGUI`
            - init `statusbar` and `menubar`
        """

        super().__init__()

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
        """ Reimplementation of `eventFilter` makes possible to catch all key
        presses. Specifically, it is important to catch ``ESC`` and set focus to
        widget which handles key navigation. """
        if event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Escape:
                self.micGUI.xystage.setFocus()

        return super(MicMainWindow,self).eventFilter(source,event)

    def showLogFile(self):
        """
        Todo:
            This method opens window with log file. Individual logs are pushed
            from :func:`messageCallback`.
        """
        al.printW("MicMainWindow::showLogFile -> Not done yet!")

    def messageCallback(self,msg):
        """ Print `msg` to statusbar. Connected to :attr:`signals_message`.
        Timestamp is added automatically.

        Todo:
            Messages should be looged into a logfile which can be viewed using
            function :func:`showLogFile`.

        Args:
            msg (str): Message to be printed.
        """
        time = datetime.now().strftime('%H:%M:%S')
        msg = time + " " + msg
        # TODO: Save message into logfile
        self.statusbar.showMessage(msg)

    def closeEvent(self,*_):
        """ Reimplementation of `closeEvent` is used to emit
        :attr:`signals_closeParent`.
        """
        print("MicMainWindow::closeEvent")
        self.signals.closeParent.emit()
        QApplication.instance().quit()

def main():
    """ Call this function to open full microscope GUI.

    **Steps:**

        1.  Set style sheet from :download:`ablo.css <../ablo.css>`
        2.  Init main window :class:`MicMainWindow()`
        3.  Start application and ensure clean exit
    """
    app = QApplication(sys.argv)

    app.setStyle('Fusion')

    # Set style which is defined in a separate file
    styleFile = "AbloGUI_pyqt/ablo.css"
    with open(styleFile,'r') as fh:
        app.setStyleSheet(fh.read())

    handle = MicMainWindow()
    sys.exit(app.exec_())   # Run main loop and ensure clean exit

if __name__ == "__main__":
    """ Run `main()` for standalone execution. """
    main()
