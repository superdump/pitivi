# PiTiVi , Non-linear video editor
#
#       pitivi/pitivi.py
#
# Copyright (c) 2005, Edward Hervey <bilboed@bilboed.com>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this program; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place - Suite 330,
# Boston, MA 02111-1307, USA.

"""
Main application
"""
import gobject
import gtk
import gst
import check
from ui import mainwindow
from pitivigstutils import patch_gst_python
from playground import PlayGround
from project import Project, file_is_project
from effects import Magician
from configure import APPNAME
from settings import GlobalSettings
from threads import ThreadMaster
from pluginmanager import PluginManager
import instance

from gettext import gettext as _

class Pitivi(gobject.GObject):
    """
    Pitivi's main class

    Signals
        void new-project-loading()
            Pitivi is attempting to load a new project
        void new-project-loaded (project)
            a new project has been loaded, and the UI should refresh it's views
            * project - the project which has been loaded
        void new-project-failed(reason, uri)
            a new project could not be created
            * reason - the reason for failure
            * uri - the uri which failed to load (or None)
        boolean closing-project(project)
            pitivi would like to close a project. handlers should return false
            if they do not want this project to close. by default, assumes
            true.
            * project - the project Pitivi would like to close
        shutdown
            used internally, do not catch this signals"""

    __gsignals__ = {
        "new-project-loading" : (gobject.SIGNAL_RUN_LAST,
                          gobject.TYPE_NONE,
                          ()),
        "new-project-loaded" : ( gobject.SIGNAL_RUN_LAST,
                          gobject.TYPE_NONE,
                          (gobject.TYPE_PYOBJECT, )),
        "closing-project" : ( gobject.SIGNAL_RUN_LAST,
                              gobject.TYPE_BOOLEAN,
                              (gobject.TYPE_PYOBJECT, )),
        "new-project-failed" : ( gobject.SIGNAL_RUN_LAST,
                          gobject.TYPE_NONE,
                          (gobject.TYPE_STRING, gobject.TYPE_STRING)),
        "shutdown" : ( gobject.SIGNAL_RUN_LAST,
                       gobject.TYPE_NONE,
                       ( ))
        }

    project = None

    def __init__(self, use_ui=True, *args, **kwargs):
        """
        initialize pitivi with the command line arguments
        """
        gst.log("starting up pitivi...")
        gobject.GObject.__init__(self)

        self._use_ui = use_ui

        # patch gst-python for new behaviours
        patch_gst_python()

        # store ourself in the instance global
        if instance.PiTiVi:
            raise RuntimeWarning(
                _("There is already a %s instance, inform developers") % APPNAME)
        instance.PiTiVi = self

        # TODO parse cmd line arguments

        # get settings
        self.settings = GlobalSettings()
        self.threads = ThreadMaster()

        self.plugin_manager = PluginManager(self.settings.get_local_plugin_path(),\
                                            self.settings.get_plugin_settings_path())

        self.playground = PlayGround()
        self.current = Project(_("New Project"))
        self.effects = Magician()

        if self._use_ui:
            # we're starting a GUI for the time being
            self.gui = mainwindow.PitiviMainWindow()
            self.gui.show()

    def do_closing_project(self, project):
        return True

    def loadProject(self, uri=None, filepath=None):
        """ Load the given file through it's uri or filepath """
        gst.info("uri:%s, filepath:%s" % (uri, filepath))
        if not uri and not filepath:
            self.emit("new-project-failed", _("Not a valid project file."),
                uri)
            return
        if filepath:
            uri = "file://" + filepath
        # is the given filepath a valid pitivi project
        if not file_is_project(uri):
            self.emit("new-project-failed", _("Not a valid project file."),
                uri)
            return
        # if current project, try to close it
        if self._closeRunningProject():
            self.emit("new-project-loading")
            try:
                self.current = Project(uri)
                self.emit("new-project-loaded", self.current)
            except:
                self.emit("new-project-failed", 
                    _("There was an error loading the file."), uri)

    def _closeRunningProject(self):
        """ close the current project """
        gst.info("closing running project")
        if self.current:
            if self.current.hasUnsavedModifications():
                result = self.current.save()
                if not result:
                    return False
            result = not self.emit("closing-project", self.current)
            if result:
                return False
            self.playground.pause()
            self.current = None
        return True

    def newBlankProject(self):
        """ start up a new blank project """
        # if there's a running project we must close it
        if self._closeRunningProject():
            self.playground.pause()
            self.emit("new-project-loading")
            self.current = Project(_("New Project"))
            self.emit("new-project-loaded", self.current)

    def shutdown(self):
        """ close PiTiVi """
        gst.debug("shutting down")
        # we refuse to close if we're running a user interface and the user
        # doesn't want us to close the current project.
        if not self._closeRunningProject():
            gst.warning("Not closing since running project doesn't want to close")
            return
        self.threads.stopAllThreads()
        self.playground.shutdown()
        instance.PiTiVi = None
        self.emit("shutdown")

def shutdownCb(pitivi):
    gst.debug("Exiting main loop")
    gtk.main_quit()

def main(argv):
    check.initial_checks()
    ptv = Pitivi(argv)
    ptv.connect('shutdown', shutdownCb)
    gtk.main()