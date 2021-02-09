#!/usr/bin/python3

""" Basler module """

# TODO =========================================================================
# - add functionality (connect camera)

import sys
import time
import numpy as np
from PyQt5.QtCore import (Qt, QThreadPool, QObject, QRunnable, pyqtSlot,
    pyqtSignal, QThread)
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QPushButton,
    QHBoxLayout, QVBoxLayout, QStyle, QLabel, QSlider)

from PyQt5.QtGui import QPixmap, QImage

import pyqtgraph as pg

import qtawesome as qta     # use bash: `qta-browser` to see icon list

from pypylon import pylon   # Camera communication

from PIL import Image       # Pillow library for image operations

import ablolib as al


class MyImageItem(pg.ImageItem):

    def __init__(self,*args,par=None,**kwargs):
        super().__init__(*args,**kwargs)
        self.par = par

    def mouseClickEvent(self,ev):
        """ Reimplement mouse click """
        if ev.button() == 1:
            # Left click
            print("Click",ev.pos())
        elif ev.button() == 2:
            # Right click
            # self.par.autoRange()
            try:
                self.par.autoRange()            # Reset pan/zoom
                # Set range automatically when adding/removing item
                self.par.enableAutoRange()
            except: pass

        return super(MyImageItem,self).mouseClickEvent(ev)

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
        self.resolution = al.DynVar(30)
        self.resolution.signal.connect(self.__setResolution)

        self.exposureT = al.DynVar(0)
        self.exposureT.signal.connect(self.__setExposureT)

        self.connected = self.connect()

    def setConnection(self,connection_status):
        self.connected = connection_status

    def connect(self):
        """
        Connect Basler camera. Initialization of `self.cam`.

        Returns
            - True:  connection successfull
            - False: connection unsuccessfull
        """

        self.connected = False
        print('Connecting Basler camera:',end='')

        for _ in range(10):
            try:
                # Connect camera
                self.cam = pylon.InstantCamera(pylon.TlFactory.GetInstance().CreateFirstDevice())
                self.cam.Open()
                self.connected = True
                break
            except:
                print('.',end='')

        if self.connected:
            self.exposureT.set(self.cam.ExposureTime.Min)
            # print(self.cam.ExposureTime.Min)
            # print(self.cam.ExposureTime.Max)
            self.__setResolution()                  # Set camera resolution
            al.printOK(" Connected!")
            msg = "Basler camera connected!"
            al.emitMsg(self.messageSignal,msg)
            self.connectionSignal.emit(True)
            return True
        else:
            msg = " Connection failed!"
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

    def __setExposureT(self,*_):
        self.cam.ExposureTime.SetValue(self.exposureT.get())

    def __setResolution(self,*_):
        if self.connected:
            # Load camera parameters
            minW = self.cam.Width.GetMin()
            maxW = self.cam.Width.GetMax()
            minH = self.cam.Height.GetMin()
            maxH = self.cam.Height.GetMax()
            # Calculate new width and height
            # Width: width-minW must be dividable without rest by 32
            nW = minW + 32*round(self.resolution.get()*((maxW-minW)/32)/100)
            # Height: Keep aspect ratio same as maxW/maxH
            nH = round(nW/maxW*maxH)
            # Write new values to camera settings
            self.cam.Width.SetValue(nW)
            self.cam.Height.SetValue(nH)

    def getDimensions(self):
        return self.cam.Width.GetValue(),self.cam.Height.GetValue()

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

        # self.img = pg.ImageItem(np.random.normal(size=(100,100)))

        viewbox = pg.ViewBox()
        viewbox.setAspectLocked()

        self.img = MyImageItem(np.random.normal(size=(100,100)),par=viewbox)

        viewbox.addItem(self.img)
        viewbox.setMenuEnabled(False)

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
            self.setGeometry(500,0,400,400)
            self.setWindowTitle("Basler camera view")

    def closeEvent(self,*_):
        """ Reimplementation of `closeEvent` method """
        # close signal emits (if defined)
        if self.closeSignal is not None:
            self.closeSignal.emit()

class Thread(QThread):
    newImg = pyqtSignal(np.ndarray)

    def __init__(self,*args,basler=None,sigStop=None,sigPause=None):
        super().__init__(*args)

        self.Basler = basler
        self.streaming = True
        self.pause = False
        sigStop.connect(self.stopStreaming)
        sigPause.connect(self.togglePause)

    def togglePause(self):
        self.pause = not self.pause

    def stopStreaming(self):
        self.streaming = False

    def run(self):
        while self.streaming:
            if not self.pause:
                img = self.Basler.grabImg()
                if img is not None:
                    self.newImg.emit(img)

class BaslerGUI(QWidget):

    """
    This widget contains controls of the Basler camera and can be placed to any
    QMainWindow, QFrame, etc.

    Grabbing of image and displaying it is done within a separate thread.

    Flow of the application is limitted only by speed of plotting which must be
    done in the main thread. See also
    https://groups.google.com/g/pyqtgraph/c/FSjIaxYfYKQ for possible speed up.
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

        self.btnConnect.setObjectName('btn_connect')
        self.btnGrabImg.setObjectName('btn_grab')
        self.btnStream.setObjectName('btn_stream')
        self.btnSaveImg.setObjectName('btn_save')

        self.btnConnect.setStatusTip('Connect Basler camera')
        self.btnGrabImg.setStatusTip('Grab one image')
        self.btnStream.setStatusTip('Start live video stream')
        self.btnSaveImg.setStatusTip('Save image')

        self.btnConnect.setCursor(Qt.PointingHandCursor)
        self.btnGrabImg.setCursor(Qt.PointingHandCursor)
        self.btnStream.setCursor(Qt.PointingHandCursor)
        self.btnSaveImg.setCursor(Qt.PointingHandCursor)

        self.toggle_btnStream()
        self.btnGrabImg.setIcon(qta.icon('fa.photo'))
        self.btnGrabImg.clicked.connect(self.btnClicked)
        self.btnSaveImg.setIcon(al.standardIcon('SP_DriveFDIcon'))
        self.btnSaveImg.clicked.connect(self.btnClicked)

        # Exposure settings ----------------------------------------------------
        # Add label
        self.lblExp = QLabel("Exposure")
        self.lblExp.setAlignment(Qt.AlignLeft)
        self.lblExp.setFixedSize(130,25)
        # Add slider to change exposure time
        self.sldExp = QSlider(Qt.Horizontal,self)
        self.sldExp.setCursor(Qt.PointingHandCursor)
        self.sldExp.setValue(self.Basler.exposureT.get())
        self.sldExp.setToolTip('Change exposure time')
        self.sldExp.valueChanged.connect(self.sldExpValueChanged)
        self.sldExp.setMinimum(0)
        self.sldExp.setMaximum(100)

        # Resolution settings --------------------------------------------------
        # Add label
        self.lblRes = QLabel("Resolution")
        self.lblRes.setAlignment(Qt.AlignLeft)
        self.lblRes.setFixedSize(130,25)
        # Add slider to change resolution
        self.sldRes = QSlider(Qt.Horizontal,self)
        self.sldRes.setCursor(Qt.PointingHandCursor)
        self.sldRes.setValue(self.Basler.resolution.get())
        self.sldRes.setToolTip('Change resolution')
        self.sldRes.valueChanged.connect(self.sldResValueChanged)
        self.sldRes.setMinimum(0)
        self.sldRes.setMaximum(100)

        hbox1 = QHBoxLayout()
        hbox1.addWidget(self.btnConnect)
        hbox1.addWidget(self.btnGrabImg)
        hbox1.addWidget(self.btnStream)

        hbox2 = QHBoxLayout()
        hbox2.addWidget(self.btnSaveImg)

        hbox3 = QHBoxLayout()
        hbox3.addWidget(self.lblExp)
        hbox3.addWidget(self.sldExp)

        hbox4 = QHBoxLayout()
        hbox4.addWidget(self.lblRes)
        hbox4.addWidget(self.sldRes)

        vbox = QVBoxLayout()
        vbox.addLayout(hbox1)
        vbox.addLayout(hbox2)
        vbox.addLayout(hbox3)
        vbox.addLayout(hbox4)
        vbox.addStretch(1)

        self.layout = vbox

        self.setLayout(self.layout)

        self.viewWindow = self.newViewWindow()
        self.signals.closeWindow.connect(self.viewWindowClosed)
        
        # Set states of buttons according to connection state of the camera
        self.toggleConnection(self.Basler.connected)

    def newViewWindow(self):
        """ Create new viewWindow """
        viewWindow = BaslerView(closeSignal=self.signals.closeWindow)
        # This window has to be shown and then potentially hidden. Error with
        # timers and different threads is otherwise given.
        viewWindow.show()
        viewWindow.hide()
        return viewWindow

    def btnClicked(self):
        """ Callback for buttons """
        sender = self.sender()
        if sender.objectName() == 'btn_grab':
            self.showImg()
        elif sender.objectName() == 'btn_save':
            self.saveImg()

    def sldExpValueChanged(self,value):
        # TODO: Need to map value from slider limits to camera limits:
        # $ print(self.cam.ExposureTime.Min)
        # $ print(self.cam.ExposureTime.Max)
        pass

    def sldResValueChanged(self,value):
        """ Set new resolution if slider sldRes moved by user """
        if self.sldRes.hasFocus():
            if self.streaming:
                self.signals.sig2.emit()    # Pause streaming
                time.sleep(0.1)             # Wait for thread (grab and show)
                # TODO: Is there a better option like threadpool.waitfordone?
            self.Basler.resolution.set(value)
            w,h = self.Basler.getDimensions()
            self.lblRes.setText(f"{value}% ({w}x{h})")
            if self.streaming:
                self.signals.sig2.emit()    # Continue streaming

    def toggleConnection(self,connection):
        """ Change appearance of widgets according to connection status """
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
        self.sldRes.setEnabled(connection)

    def toggle_btnStream(self):
        """ Change functionality of btnStream """
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

            if not self.viewWindow.isVisible():
                self.viewWindow.show()

            th = Thread(self,basler=self.Basler,
                sigStop=self.signals.sig1,sigPause=self.signals.sig2)
            th.newImg.connect(self.setImage)
            th.start()

            al.emitMsg(self.messageSignal,'Streaming started')

    @pyqtSlot(np.ndarray)
    def setImage(self,image):
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
        self.viewWindow.img.setImage(image)

    def stopStream(self):
        if self.streaming:
            self.streaming = False
            self.signals.sig1.emit()
            self.toggle_btnStream()
            al.emitMsg(self.messageSignal,'Streaming stopped')

    def showImg(self):
        """ Show image in separate window
        - called, e.g., by `btnGrabImg` or by `stream()` in a separate thread
        """
        # First, show window if not visible
        if not self.viewWindow.isVisible():
            self.viewWindow.show()
        img = self.Basler.grabImg()             # Grab image
        self.viewWindow.img.setImage(img)

    def saveImg(self):
        """ Grab new image and save """
        if self.streaming:
            self.signals.sig2.emit()    # Pause streaming
            time.sleep(0.1)
        img = Image.fromarray(self.Basler.grabImg())    # Pillow library used
        img.save('test.png')
        if self.streaming:
            self.signals.sig2.emit()    # Continue streaming

    def viewWindowClosed(self):
        """ Stop streaming when closing view window """
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
