# -*- coding: utf-8 -*-
"""
 Probe OpenGL version on Windows
 Copyright Schrodinger, LLC. All rights reserved.
"""

import re

from OpenGL.GL import GL_RENDERER
from OpenGL.GL import GL_VENDOR
from OpenGL.GL import GL_VERSION
from OpenGL.GL import glGetString

from schrodinger.Qt.QtWidgets import QOpenGLWidget
from schrodinger.ui.qt.appframework2 import application


class OpenGLWidgetTest(QOpenGLWidget):

    def initializeGL(self):
        self.driver = (glGetString(GL_VENDOR).decode('utf-8'),
                       glGetString(GL_RENDERER).decode('utf-8'),
                       glGetString(GL_VERSION).decode('utf-8'))
        reg = re.compile(r'^'
                         r'(?P<major>[0-9]+)'
                         r'(?:.(?P<minor>[0-9]+))'
                         r'(?:.(?P<release>[0-9]+))?')
        self.version = reg.search(self.driver[2])


def probe_driver_capabilities():
    """
    Tell if the GL version is greater than (>=) 2.0
    and if the driver is a good driver (ie it is not in the bad driver list)

    :return: (version >= 2.0, good driver)
    :rtype: (bool, bool)
    """
    app = application.get_application()
    w = OpenGLWidgetTest()
    w.show()  # trigger call to initializeGL(), no need to start app.exec()
    w.hide()

    # a set of tuples (vendor, renderer, version string)
    bad_drivers = {("dummy vendor", "dummy renderer", "dummy version")}
    good_driver = not (w.driver in bad_drivers)
    return (int(w.version['major']) >= 2, good_driver)
