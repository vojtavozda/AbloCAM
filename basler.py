#!/usr/bin/python3

"""
Basler camera
=============

Self-standing module for full control of **Basler camera** employing ``pypylon``
(see its `github page <https://github.com/basler/pypylon>`_ for further usage).
Library ``pyqtgraph`` used to display video output.

If run separately, :func:`main` is executed. It inits :class:`BaslerMainWindow`
which sets :class:`BaslerGUI` as a central widget. This widget which holds all
buttons and sliders. It also calls :class:`Basler` which inits the camera using 
``pypylon`` library. Video from the camera is shown in a standalone window
:class:`BaslerView`. A relatively fast video stream is reached by grabbing
images in a separate thread run by :class:`Thread`.

If this module is a part of larger project, :class:`BaslerGUI` can be implemented
as a widget into a custom window.
"""


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
    """
    **Bases:** :class:`pyqtgraph.ImageItem`

    Modification of the ``ImageItem`` so mouse click events can be caught.

    Args:
        par: Pointer to parrent. Defaults to None.
    """


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
    Object which connects to the camera, gets images etc. This is initiated by
    :class:`BaslerGUI`. Call it only if you want to create your own GUI. This
    class employs the ``pypylon`` library to comunicate with the camera.

    Args:
        connectionSignal: Emits True (False) upon (dis)connection. Defaults to
            None.
        messageSignal: Status messages are emitted here. Defaults to None.

    Attributes:
        cam (:class:`pylon.InstantCamera`): Camera object. Initiated in
            :func:`connect`. 
        connected (bool): True if connected, False otherwise.
        resolution (:class:`ablolib.DynVar`): Dynamic variable, should be accessed
            via `set() and `get()` methods. The value corresponds to percentual 
            ratio between maximum and minimum resolution.
        exposure (:class:`ablolib.DynVar`): Dynamic variable,...
    """

    def __init__(self,connectionSignal=None,messageSignal=None):
        self.cam = None
        self.connected = False
        self.connectionSignal = connectionSignal
        self.connectionSignal.connect(self.__setConnectionStatus)
        self.messageSignal = messageSignal

        # Init resolution and connect it to a slot function.
        self.resolution = al.DynVar(30)
        self.resolution.signal.connect(self.__setResolution)

        # Init exposureT and connect it to a slot function.
        self.exposureT = al.DynVar(0)
        self.exposureT.signal.connect(self.__setExposureT)

        self.connected = self.connect()

    def __setConnectionStatus(self,connection_status):
        self.connected = connection_status

    def connect(self):
        """
        Connect Basler camera. Initialization of :attr:`cam`.

        Returns:
            bool: The return value. True for success, False otherwise.
        """

        self.connected = False
        print('Connecting Basler camera:',end='')

        # Attempt to connect several times
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
            self.__setResolution()              # Set camera default resolution
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

        """ Grab image and return image data.
        
        Returns:
            :class:`np.ndarray`: 2D array of image data.
         """

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
        """ Get dimensions of the camera image. Can be changed by changing
        :attr:`resolution`.

        Returns:
            int,int: Width and height of image
        """
        return self.cam.Width.GetValue(),self.cam.Height.GetValue()

class BaslerView(QWidget):
    """
    **Bases:** :class:`QWidget`

    Separate window showing video output from the Basler camera. Typically
    opened from :class:`BaslerGUI` which directly sets new image to
    :attr:`img`. It employs ``pyqtgraph`` for imaging.

    Args:
        standalone (bool): Is this widget a standalone window (True) or part of
            some other widget (False). Defaults to True.
        closeSignal: This signal emits when this window is closed so, for
            example, streaming can be automatically stopped by catching this signal.
            Defaults to None.

    Attributes:
        img (:class:`MyImageItem`): New image (:class:`np.ndarray`) can be set
            using command `img.setImage(my_img)`.
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
    """
    **Bases:** :class:`QThread`

    Object used to grab images from the **Basler** camera. It is optimized to be
    run in a separate thread. After successfull grabbing signal :attr:`newImg`
    emits the image which is caught by :func:`Basler.setImg`.

    Args:
        basler (:class:`Basler`): Pointer to camera instance
        sigStop (:class:`pyqtSignal`): Signal used to stop streaming (exit while
            loop)
        sigPause (:class:`pyqtSignal`): Signal used to pause streaming (do not
            exit while loop but stop grabbing)

    Attributes:
        newImg (:class:`pyqtSignal`): Emits :class:`np.ndarray` after successfull
            grabbing. 
    """
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
        """ Reimplementation of :func:`run`. It grabs images calling
        :func:`Basler.grabImg` and emits :attr:`newImg`. """
        while self.streaming:
            if not self.pause:
                img = self.Basler.grabImg()
                if img is not None:
                    self.newImg.emit(img)

class BaslerGUI(QWidget):
    """
    **Bases:** :class:`QWidget`

    This widget contains controls of the Basler camera and can be placed to any
    :class:`QMainWindow`, :class:`QFrame`, etc.

    **Threading:**

    PyQt5 does not support interference to the GUI from any other but the `main`
    thread. Therefore, video (grab&display) cannot fully run in a separate
    thread. Instead, signal (:attr:`Thread.newImg`) from the separate thread
    (:class:`Thread`) emits pointer to grabbed image which is then displayed in
    the `main` thread (via :func:`setImg`).

    Flow of the application is limitted only by the speed of plotting which
    **must** be done in the main thread. See also `this
    <https://groups.google.com/g/pyqtgraph/c/FSjIaxYfYKQ>`_ for possible speed
    up.

    **Resolution:**

    In order to prevent exceptions during Basler resolution changes, streaming
    must be paused first (:attr:`signals_sig2` emits), then change
    :attr:`Basler.resolution` and continue streaming.

    Args:
        parentCloseSignal (:class:`pyqtSignal`,optional): This signal is connected to
            :func:`parrentClose`. Defaults to None.
        messageSignal (:class:`pyqtSignal`,optional): Handle of signal which is connected to
            :func:`BaslerMainWindow.messageCallback` so any message emitted by this
            signal can be shown in the statusbar. Defaults to None.

    Attributes:
        viewWindow: Instance of :class:`BaslerView`. This is a separate window
            which shows grabbed images.
        signals_sig1: Emit implies stop of :class:`Thread`
        signals_sig2: Emit toggle pause of :class:`Thread`

    **Steps:**

        1. Init Basler camera (:class:`Basler`)
        2. Create GUI (buttons etc.)
    """

    def __init__(self,parentCloseSignal=None,messageSignal=None):
        super().__init__()

        self.streaming = False
        self.layout = None

        if parentCloseSignal is not None:
            parentCloseSignal.connect(self.__parentClose)

        self.messageSignal = messageSignal

        self.lastT = 0      # Measure streaming fps
        self.fps = None     # Measure streaming fps

        self.signals = al.Signals()

        # Initiate Basler camera -----------------------------------------------
        self.Basler = Basler(
            connectionSignal=self.signals.connection,
            messageSignal= self.messageSignal)
        self.signals.connection.connect(self.__toggleConnection)

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

        self.__toggle_btnStream()
        self.btnGrabImg.setIcon(qta.icon('fa.photo'))
        self.btnGrabImg.clicked.connect(self.__btnClicked)
        self.btnSaveImg.setIcon(al.standardIcon('SP_DriveFDIcon'))
        self.btnSaveImg.clicked.connect(self.__btnClicked)

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
        self.sldExp.valueChanged.connect(self.__sldExpValueChanged)
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
        self.sldRes.valueChanged.connect(self.__sldResValueChanged)
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

        self.viewWindow = self.__newViewWindow()
        self.signals.closeWindow.connect(self.__viewWindowClosed)
        
        # Set states of buttons according to connection state of the camera
        self.__toggleConnection(self.Basler.connected)

    def __newViewWindow(self):
        """ Init new :attr:`viewWindow` of :class:`BaslerView` class. """
        viewWindow = BaslerView(closeSignal=self.signals.closeWindow)
        # This window has to be shown and then potentially hidden. Error with
        # timers and different threads is otherwise given.
        viewWindow.show()
        viewWindow.hide()
        return viewWindow

    def __btnClicked(self):
        """ Callback connected to buttons """
        sender = self.sender()
        if sender.objectName() == 'btn_grab':
            self.showImg()
        elif sender.objectName() == 'btn_save':
            self.saveImg()

    def __sldExpValueChanged(self,value):
        # TODO: Need to map value from slider limits to camera limits:
        # $ print(self.cam.ExposureTime.Min)
        # $ print(self.cam.ExposureTime.Max)
        pass

    def __sldResValueChanged(self,value):
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

    def __toggleConnection(self,connection):
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

    def __toggle_btnStream(self):
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
        """ Start streaming. This function opens separate window
        :attr:`viewWindow` (if not opened yet) and starts new thread
        :class:`Thread` which signal :attr:`Thread.newImg` is connected to
        :func:`setImage`. """

        if not self.streaming:
            self.streaming = True
            self.__toggle_btnStream()

            if not self.viewWindow.isVisible():
                self.viewWindow.show()

            th = Thread(self,basler=self.Basler,
                sigStop=self.signals.sig1,sigPause=self.signals.sig2)
            th.newImg.connect(self.setImage)
            th.start()

            al.emitMsg(self.messageSignal,'Streaming started')

    @pyqtSlot(np.ndarray)
    def setImage(self,image):
        """ Function is connected to :attr:`Thread.newImg` which emits when the
        :class:`Thread` grabs new image. This function also calculates `fps`
        which is displayed as a title of the :attr:`viewWindow`. """
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
        """ Stop streaming. :attr:`signals_sig1` emits so :class:`Thread` knows
        it should stop grabbing. """
        if self.streaming:
            self.streaming = False
            self.signals.sig1.emit()
            self.__toggle_btnStream()
            al.emitMsg(self.messageSignal,'Streaming stopped')

    def showImg(self):
        """ Show image in the :attr:`viewWindow`.
        Called, e.g., by `btnGrabImg` or by :func:`stream` in a separate
        thread.
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

    def __viewWindowClosed(self):
        """ Stop streaming when closing view window """
        self.stopStream()

    def __parentClose(self):
        print('BaslerGUI::__parentClose')
        self.stopStream()
        self.viewWindow.hide()
        self.Basler.disconnect()

class BaslerMainWindow(QMainWindow):
    """
    **Bases:** :class:`QMainWindow`

    Main window which sets :class:`BaslerGUI` as the central widget. It uses
    statusbar and signals :class:`ablolib.Signals` in a similar way as
    :class:`AbloMIC.MicMainWindow` does. """

    def __init__(self):
        super().__init__()

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
        """ Function connected to :attr:`signals_message` to display ``msg`` in
        the statusbar. """
        self.statusbar.showMessage(msg)

    def closeEvent(self,*_):
        """ Reimplementation of `closeEvent` function so
        :attr:`signals_closeParent` can emit when this main window is closed.
        """
        self.signals.closeParent.emit()

def main():
    """ Function used for standalone execution. It opens main window
    :class:`BaslerMainWindow` and ensures clean exit.
    """
    app = QApplication(sys.argv)
    handle = BaslerMainWindow()
    sys.exit(app.exec_())

if __name__ == "__main__":
    """ Run `main()` for standalone execution. """
    main()
