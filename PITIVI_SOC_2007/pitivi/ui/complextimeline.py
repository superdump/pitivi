# PiTiVi , Non-linear video editor
#
#       pitivi/ui/complextimeline.py
#
# Copyright (c) 2006, Edward Hervey <bilboed@bilboed.com>
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
Timeline widgets for the complex view
"""

import gtk
import gst

import pitivi.instance as instance

from pitivi.bin import SmartTimelineBin
from complexlayer import LayerInfoList
from layerwidgets import TopLayer, CompositionLayer
from complexinterface import ZoomableWidgetInterface

class CompositionLayers(gtk.VBox, ZoomableWidgetInterface):
    """ Souped-up VBox that contains the timeline's CompositionLayer """

    def __init__(self, leftsizegroup, hadj, layerinfolist):
        gtk.VBox.__init__(self)
        self.modify_bg(gtk.STATE_NORMAL, gtk.gdk.Color(1,0,0))
        self.leftSizeGroup = leftsizegroup
        self.hadj = hadj
        self.layerInfoList = layerinfolist
        self.layerInfoList.connect('layer-added', self._layerAddedCb)
        self.layerInfoList.connect('layer-removed', self._layerRemovedCb)
        self._createUI()

    def _createUI(self):
        self.set_spacing(5)
        self.set_border_width(2)
        self.layers = []
        for layerinfo in self.layerInfoList:
            complayer = CompositionLayer(self.leftSizeGroup, self.hadj,
                                         layerinfo)
            self.layers.append(complayer)
            self.pack_start(complayer, expand=False)


    ## ZoomableWidgetInterface overrides

    def getDuration(self):
        return max([layer.getDuration() for layer in self.layers])

    def getStartTime(self):
        # the start time is always 0 (for display reason)
        return 0

    def zoomChanged(self):
        for layer in self.layers:
            layer.zoomChanged()

    def timelinePositionChanged(self, value, frame):
        for layer in self.layers:
            layer.timelinePositionChanged(value, frame)

    ## LayerInfoList callbacks

    def _layerAddedCb(self, layerInfoList, position):
        complayer = CompositionLayer(self.leftSizeGroup, self.hadj,
                                     layerInfoList[position])
        self.layers.insert(position, complayer)
        self.pack_start(complayer, expand=False)
        self.reorder_child(complayer, position)

    def _layerRemovedCb(self, unused_layerInfoList, position):
        # find the proper child
        child = self.layers[position]
        # remove it
        self.remove(child)

#
# Complex Timeline Design v2 (08 Feb 2006)
#
#
# Tree of contents (ClassName(ParentClass))
# -----------------------------------------
#
# ComplexTimelineWidget(gtk.VBox)
# |  Top container
# |
# +--TopLayer (TimelineLayer (gtk.HBox))
# |   |
# |   +--TopLeftTimelineWidget(?)
# |   |
# |   +--ScaleRuler(gtk.Layout)
# |
# +--gtk.ScrolledWindow
#    |
#    +--CompositionsLayer(gtk.VBox)
#       |
#       +--CompositionLayer(TimelineLayer(gtk.HBox))
#          |
#          +--InfoLayer(gtk.Expander)
#          |
#          +--TrackLayer(gtk.Layout)

class ComplexTimelineWidget(gtk.VBox, ZoomableWidgetInterface):

    def __init__(self, topwidget):
        gst.log("Creating ComplexTimelineWidget")
        gtk.VBox.__init__(self)

        self.zoomratio = 10.0

        self.hadj = topwidget.hadjustment
        self.vadj = topwidget.vadjustment

        # common LayerInfoList
        self.layerInfoList = LayerInfoList(instance.PiTiVi.current.timeline)
        instance.PiTiVi.playground.connect('position', self._playgroundPositionCb)
        for layer in self.layerInfoList:
            layer.composition.connect('start-duration-changed',
                                      self._layerStartDurationChangedCb)

        self._createUI()

    def _createUI(self):
        self.set_border_width(4)
        self.leftSizeGroup = gtk.SizeGroup(gtk.SIZE_GROUP_HORIZONTAL)

        # top layer (TopLayer)
        self.topLayer = TopLayer(self.leftSizeGroup, self.hadj)
        # overriding topLayer's ZoomableWidgetInterface methods
        self.topLayer.getDuration = self.getDuration
        self.topLayer.getStartTime = self.getStartTime
        self.topLayer.overrideZoomableWidgetInterfaceMethods()
        self.pack_start(self.topLayer, expand=False)

        # List of CompositionLayers
        self.compositionLayers = CompositionLayers(self.leftSizeGroup,
                                                   self.hadj, self.layerInfoList)

        # ... in a scrolled window
        self.scrolledWindow = gtk.ScrolledWindow()
        self.scrolledWindow.set_policy(gtk.POLICY_NEVER, gtk.POLICY_AUTOMATIC)
        self.scrolledWindow.add_with_viewport(self.compositionLayers)
        self.pack_start(self.scrolledWindow, expand=True)

    def _layerStartDurationChangedCb(self, unused_composition, unused_start,
                                     unused_duration):
        # Force resize of ruler
        self.topLayer.startDurationChanged()

    ## ZoomableWidgetInterface overrides
    ## * we send everything to self.compositionLayers
    ## * topLayer's function calls will also go there

    def getDuration(self):
        return self.compositionLayers.getDuration()

    def getStartTime(self):
        return self.compositionLayers.getStartTime()

    def zoomChanged(self):
        self.topLayer.rightWidget.zoomChanged()
        self.compositionLayers.zoomChanged()


    ## ToolBar callbacks

    def toolBarZoomChangedCb(self, unused_toolbar, zoomratio):
        self.setZoomRatio(zoomratio)

    ## PlayGround timeline position callback

    def _playgroundPositionCb(self, unused_playground, smartbin, value):
        if isinstance(smartbin, SmartTimelineBin):
            # for the time being we only inform the ruler
            self.topLayer.timelinePositionChanged(value, 0)
            self.compositionLayers.timelinePositionChanged(value, 0)