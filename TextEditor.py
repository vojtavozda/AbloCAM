#!/usr/bin/env python3

import sys
from PyQt5.QtWidgets import (QMainWindow,QWidget, QApplication, QVBoxLayout, 
    QHBoxLayout, QTextEdit, QLabel, QShortcut, QFileDialog, QMessageBox,
    QAction)
from PyQt5.QtGui import QKeySequence, QFont
from PyQt5 import Qt

import ablolib as al


class TextEditorGUI(QMainWindow):

    def __init__(self):
        super().__init__()

        self.filename = None

        self.setGeometry(200,200,500,700)

        # Add central widget ---------------------------------------------------
        # self.w = TextEditorW()
        # self.setCentralWidget(self.w)

        cw = QWidget(self)

        text = "Untitled File"
        self.title = QLabel(text)
        self.title.setWordWrap(True)
        self.title.setAlignment(Qt.Qt.AlignCenter)
        self.scrollableTextArea = QTextEdit()
        font = QFont()
        font.setFamily('Courier New')
        self.scrollableTextArea.setFont(font)
        # self.scrollableTextArea.setWordWrapMode(0)
        vbox = QVBoxLayout()
        vbox.addWidget(self.title)
        vbox.addWidget(self.scrollableTextArea)
        cw.setLayout(vbox)

        self.setCentralWidget(cw)

        # Menubar --------------------------------------------------------------
        openAct = QAction('&Open',self)
        openAct.setShortcut('Ctrl+O')
        openAct.setStatusTip('Open file')
        openAct.setIcon(al.standardIcon('SP_DirOpenIcon'))
        openAct.triggered.connect(self.OpenFile)

        saveAct = QAction('&Save',self)
        saveAct.setShortcut('Ctrl+S')
        saveAct.setStatusTip('Save file')
        saveAct.setIcon(al.standardIcon('SP_DriveFDIcon'))
        saveAct.triggered.connect(self.SaveFile)

        exitAct = QAction('&Exit',self)
        exitAct.setStatusTip('Close application')
        exitAct.setShortcut('Ctrl+Q')
        exitAct.setIcon(al.standardIcon('SP_BrowserStop'))
        exitAct.triggered.connect(self.close)

        menubar = self.menuBar()
        fileMenu = menubar.addMenu('&File')
        fileMenu.addAction(openAct)
        fileMenu.addAction(saveAct)
        fileMenu.addAction(exitAct)

        # Statusbar ------------------------------------------------------------
        self.statusbar = self.statusBar()

        self.show()

    def OpenFile(self,filename=None):
        if filename is None or filename is False:
            self.filename,_ = QFileDialog.getOpenFileName(self, "Open new file",
                "", "All files (*)")
        else:
            self.filename = filename

        if self.filename:
            with open(self.filename, "r") as f:
                contents = f.read()
                self.title.setText(self.filename)
                self.scrollableTextArea.setText(contents)
            self.statusbar.showMessage("File has been opened.")
        else:
            self.invalidPathAlertMessage()
            self.statusbar.showMessage("Invalid file!")

    def SaveFile(self):
        if not self.filename or self.filename is None:
            newFilename,_ = QFileDialog.getSaveFileName(self, "Save this file as...", "", "All files (*)")
            if newFilename:
                self.filename = newFilename
            else:
                self.invalidPathAlertMessage()
                self.statusbar.showMessage("Invalid name!")
                return False
        contents = self.scrollableTextArea.toPlainText()
        with open(self.filename, "w") as f:
            f.write(contents)
        self.title.setText(self.filename)
        self.statusbar.showMessage("File has been saved.")
        return True

    def invalidPathAlertMessage(self):
        messageBox = QMessageBox()
        messageBox.setWindowTitle("Invalid file")
        messageBox.setText("Selected filename or path is not valid. Please select a valid file.")
        messageBox.exec()

    def closeEvent(self,event):
        messageBox = QMessageBox()
        title = "Quit editor?"
        message = """Save file before exit?"""
       
        _exit = True
        reply = messageBox.question(self, title, message,
            messageBox.Yes | messageBox.No | messageBox.Cancel,
            messageBox.Cancel)
        if reply == messageBox.Yes:
            return_value = self.SaveFile()
            if not return_value:
                _exit = False
        elif reply == messageBox.Cancel:
            _exit = False

        if not _exit:
            try:    event.ignore()
            except: pass
        else:
            try:    event.accept()
            except: self.close()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = TextEditorGUI()
    # w.showMaximized()
    sys.exit(app.exec_())