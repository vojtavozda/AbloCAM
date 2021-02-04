#!/usr/bin/python3

""" Basler module """

# TODO =========================================================================
# - add functionality (connect camera)

import sys
import time
import numpy as np
from PyQt5.QtCore import (Qt, QThreadPool, QObject, QRunnable, pyqtSlot,
    pyqtSignal)
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QPushButton,
    QHBoxLayout, QVBoxLayout, QStyle)

import pyqtgraph as pg

import qtawesome as qta     # use bash: `qta-browser` to see icon list

from pypylon import pylon   # Camera communication

from PIL import Image       # Pillow library for image operations

import ablolib as al




class Basler():
    """
    Object which connects to camera, gets images etc.
    This is called by BaslerGUI to get data from the camera.
    Call it only if you want to create your own GUI.
    """

    def __init__(self,connectionSignal=None,messageSignal=None):
        self.cam = None
        self.connected = False
        self.connectionSignal = connectionSignal
        self.connectionSignal.connect(self.setConnection)
        self.messageSignal = messageSignal

        # Resolution is dynamic variable, should be accessed via set() and get()
        # methods. The value corresponds to percentual ratio between maximum and
        # minimum resolution.
        self.resolution = al.DynVar(60)

        self.connected = self.connect()

        print(self.cam.Width.GetValue())
        print(self.cam.Height.GetValue())
        # self.cam.Width.SetValue(round(self.cam.Width.GetValue()/10))
        # self.cam.Height.SetValue(round(self.cam.Height.GetValue()/10))
        print(self.cam.Width.GetValue())
        print(self.cam.Height.GetValue())

    def setConnection(self,connection_status):
        self.connected = connection_status

    def connect(self):
        """
        Connect Basler camera. Initializatiofn of `self.cam`.

        Returns
            - True:  connection successfull
            - False: connection unsuccessfull
        """

        try:
            # Connect camera
            self.cam = pylon.InstantCamera(pylon.TlFactory.GetInstance().CreateFirstDevice())
            self.cam.Open()

            print("GetValue",self.cam.Width.GetValue())
            print("GetInc  ",self.cam.Width.GetInc())
            print("GetMin  ",self.cam.Width.GetMin())
            print("GetMax  ",self.cam.Width.GetMax())
            # something
            new_width = self.cam.Width.GetValue() - self.cam.Width.GetInc()
            if new_width >= self.cam.Width.GetMin():
                self.cam.Width.SetValue(new_width)
            print("new",new_width)
            msg = "Basler camera connected!"
            al.printOK(msg)
            al.emitMsg(self.messageSignal,msg)

            self.connectionSignal.emit(True)

            # TODO: Configure GUI

            return True
        except: # pylint: disable=bare-except
            msg = "Unable to connect Basler camera!"
            al.printE(msg)
            al.emitMsg(self.messageSignal,msg)
            self.disconnect()
            return False

    def disconnect(self):
        """ Disconnect """
        try:
            self.cam.StopGrabbing()
            self.cam.Close()
            self.cam = None
            msg = "Basler camera disconnected!"
            print(msg)
            al.emitMsg(self.messageSignal,msg)
        except AttributeError:
            # Function called although camera was not connected. That's OK.
            pass
        finally:
            self.connectionSignal.emit(False)

    def grabImg(self):

        """ Returns image data """

        # Find more pypylon examples at:
        # https://github.com/basler/pypylon/tree/master/samples

        n_img = 1
        try:
            self.cam.StartGrabbingMax(n_img)
            # `StopGrabbing()` is called automatically by `RetrieveResult()`
            while self.cam.IsGrabbing():
                # Wait for an image, timeout is 5000 ms
                grabResult = self.cam.RetrieveResult(
                    5000, pylon.TimeoutHandling_ThrowException)

                if grabResult.GrabSucceeded():
                    # Access the image data.
                    return grabResult.Array

                grabResult.Release()

        except Exception as ex:
            self.disconnect()
            msg = "Camera not connected!"
            al.printW(msg)
            al.printException(ex)
            al.emitMsg(self.messageSignal,msg)
            return np.random.normal(size=(100,100))

    def changeRe

class BaslerView(QWidget):
    """
    Widget for showing image from the Basler camera.
    It should be openned from BaslerGUI.
    """


    def __init__(self,standalone=True,closeSignal=None):
        super().__init__()

        # Structure ────────────────────────────────────────────────────────────
        # BaslerView (self) ├
        # └── layout
        #     └── pgWidget
        #         └── viewbox
        #             └── img

        self.img = pg.ImageItem(np.random.normal(size=(100,100)))

        viewbox = pg.ViewBox()
        viewbox.setAspectLocked()
        viewbox.addItem(self.img)

        pgWidget = pg.GraphicsView()        # pg widget for showing graphics
        pgWidget.setCentralItem(viewbox)

        layout = QHBoxLayout()
        layout.setContentsMargins(0,0,0,0)
        layout.addWidget(pgWidget)
        self.setLayout(layout)

        # Close signal emits when this widget is closed. This event is cought by
        # the GUI which further proceeds what happens next. Makes sense in the
        # standalone regime only.
        self.closeSignal = closeSignal

        # Set geometry of this widget when it is a standalone window
        if standalone:
            self.setGeometry(300,0,400,400)
            self.setWindowTitle("Basler camera view")

    def closeEvent(self,*_):
        """ Reimplementation of `closeEvent` method """
        # close signal emits (if defined)
        if self.closeSignal is not None:
            self.closeSignal.emit()

class BaslerGUI(QWidget):

    """
    This widget contains controls of the Basler camera and can be placed to any
    QMainWindow, QFrame, etc.
    """

    def __init__(self,parentCloseSignal=None,messageSignal=None):
        super().__init__()

        self.streaming = False
        self.layout = None

        if parentCloseSignal is not None:
            parentCloseSignal.connect(self.parentClose)

        self.messageSignal = messageSignal

        self.lastT = 0      # Measure streaming fps
        self.fps = None     # Measure streaming fps

        self.threadpool = QThreadPool()

        self.signals = al.Signals()

        # Initiate Basler camera -----------------------------------------------
        self.Basler = Basler(
            connectionSignal=self.signals.connection,
            messageSignal= self.messageSignal)
        self.signals.connection.connect(self.toggleConnection)

        # Buttons --------------------------------------------------------------
        self.btnConnect = QPushButton('Connect',self)
        self.btnGrabImg = QPushButton('GrabImg',self)
        self.btnStream  = QPushButton('Stream' ,self)
        self.btnSaveImg = QPushButton('Save'   ,self)

        self.btnConnect.setStatusTip('Connect Basler camera')
        self.btnGrabImg.setStatusTip('Grab one image')
        self.btnStream.setStatusTip('Start live video stream')
        self.btnSaveImg.setStatusTip('Save image')

        self.btnConnect.setCursor(Qt.PointingHandCursor)
        self.btnGrabImg.setCursor(Qt.PointingHandCursor)
        self.btnStream.setCursor(Qt.PointingHandCursor)
        self.btnSaveImg.setCursor(Qt.PointingHandCursor)

        # Set states of buttons according to connection state of the camera
        self.toggle_btnStream()
        self.toggleConnection(False)
        self.btnGrabImg.setIcon(qta.icon('fa.photo'))
        self.btnGrabImg.clicked.connect(self.showImg)
        self.btnSaveImg.setIcon(al.standardIcon('SP_DriveFDIcon'))
        self.btnSaveImg.clicked.connect(self.saveImg)

        hbox1 = QHBoxLayout()
        hbox1.addWidget(self.btnConnect)
        hbox1.addWidget(self.btnGrabImg)
        hbox1.addWidget(self.btnStream)

        hbox2 = QHBoxLayout()
        hbox2.addWidget(self.btnSaveImg)

        vbox = QVBoxLayout()
        vbox.addLayout(hbox1)
        vbox.addLayout(hbox2)
        vbox.addStretch(1)

        self.layout = vbox

        self.setLayout(self.layout)

        self.viewWindow = BaslerView(closeSignal=self.signals.closeWindow)
        # This window has to be shown and then potentially hidden. Error with
        # timers and different threads is otherwise given.
        self.viewWindow.show()
        self.viewWindow.hide()
        self.signals.closeWindow.connect(self.viewWindowClosed)


    def toggleConnection(self,connection):
        if connection:
            self.btnConnect.setText('Disconnect')
            self.btnConnect.setIcon(al.standardIcon('SP_BrowserStop'))
            try:    self.btnConnect.clicked.disconnect()
            except: pass
            self.btnConnect.clicked.connect(self.Basler.disconnect)
        else:
            self.stopStream()
            self.btnConnect.setText('Connect')
            self.btnConnect.setIcon(al.standardIcon('SP_ArrowForward'))
            # self.btnConnect.setIcon(self.style().standardIcon(getattr(QStyle,'SP_ArrowForward')))
            try:    self.btnConnect.clicked.disconnect()
            except: pass
            self.btnConnect.clicked.connect(self.Basler.connect)

        self.btnGrabImg.setEnabled(connection)
        self.btnStream.setEnabled(connection)
        self.btnSaveImg.setEnabled(connection)

    def toggle_btnStream(self):
        if self.streaming:
            self.btnStream.setText('Stop')
            self.btnStream.setIcon(al.standardIcon('SP_MediaStop'))
            try:    self.btnStream.clicked.disconnect()
            except: pass
            self.btnStream.clicked.connect(self.stopStream)
            self.btnGrabImg.setEnabled(False)
        else:
            self.btnStream.setText('Stream')
            self.btnStream.setIcon(al.standardIcon('SP_MediaPlay'))
            try:    self.btnStream.clicked.disconnect()
            except: pass
            self.btnStream.clicked.connect(self.startStream)
            self.btnGrabImg.setEnabled(True)

    def startStream(self):
        if not self.streaming:
            self.streaming = True
            self.toggle_btnStream()
            self.stream()
            al.emitMsg(self.messageSignal,'Streaming started')

    def stream(self):
        if self.streaming:

            # Calculate fps
            nowT = pg.ptime.time()
            dt = nowT - self.lastT
            self.lastT = nowT
            if self.fps is None:
                self.fps = 1.0/dt
            else:
                s = np.clip(dt*3,0,1)
                self.fps = self.fps * (1-s) + (1.0/dt) * s
            self.viewWindow.setWindowTitle(
                "Basler camera view (%0.2f fps)"%self.fps)

            # Start worker
            worker = al.Worker(self.showImg,name="Basler")
            self.threadpool.start(worker)
            worker.signals.finished.connect(self.stream)

    def stopStream(self):
        if self.streaming:
            self.threadpool.waitForDone()
            self.streaming = False
            self.toggle_btnStream()
            al.emitMsg(self.messageSignal,'Streaming stopped')

    def saveImg(self):
        """ Grab new image and save """
        img = Image.fromarray(self.Basler.grabImg())    # Pillow library used
        img.save('test.png')

    def showImg(self):
        """ Show image in separate window
        - called by `btnGrabImg`
        """
        # First, show window if not visible
        if not self.viewWindow.isVisible():
            self.viewWindow.show()
        img = self.Basler.grabImg()         # Grab image
        self.viewWindow.img.setImage(img)   # Show image

    def viewWindowClosed(self):
        self.stopStream()

    def parentClose(self):
        print('BaslerGUI::parentClose')
        self.stopStream()
        self.viewWindow.hide()
        self.Basler.disconnect()

class BaslerMainWindow(QMainWindow):

    """ Main window which encapsulates Basler GUI """

    def __init__(self):
        super().__init__()

        self.initUI()

    def initUI(self):

        self.setGeometry(100,100,300,300)
        self.setWindowTitle("Basler GUI")

        self.signals = al.Signals()

        self.baslerGUI = BaslerGUI(
            parentCloseSignal=self.signals.closeParent,
            messageSignal=self.signals.message)
        self.setCentralWidget(self.baslerGUI)

        self.statusbar = self.statusBar()
        self.signals.message.connect(self.statusbarShow)

        self.show()

    def statusbarShow(self,msg):
        self.statusbar.showMessage(msg)

    def closeEvent(self,*_):
        self.signals.closeParent.emit()

def main():
    app = QApplication(sys.argv)
    handle = BaslerMainWindow()
    sys.exit(app.exec_())

if __name__ == "__main__":

    main()
