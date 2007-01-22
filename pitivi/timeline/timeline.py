# PiTiVi , Non-linear video editor
#
#       pitivi/timeline.py
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
Timeline and timeline objects
"""

import gobject
import gst

from pitivi.elements.singledecodebin import SingleDecodeBin
from pitivi.settings import ExportSettings

MEDIA_TYPE_NONE = 0
MEDIA_TYPE_AUDIO = 1
MEDIA_TYPE_VIDEO = 2

## * Object Hierarchy

##   Object
##    |
##    +---- Source
##    |	   |
##    |	   +---- FileSource
##    |	   |
##    |	   +---- LiveSource
##    |	   |
##    |	   +---- Composition
##    |
##    +---- Effect
## 	   |
## 	   +---- Simple Effect (1->1)
## 	   |
## 	   +---- Transition
## 	   |
## 	   +---- Complex Effect (N->1)

class Timeline(gobject.GObject):
    """
    Fully fledged timeline
    """

    # TODO make the compositions more versatile
    # for the time being we hardcode an audio and a video composition
    
    def __init__(self, project):
        gst.log("new Timeline for project %s" % project)
        gobject.GObject.__init__(self)
        self.project = project

        self.timeline = gst.Bin("timeline-" + project.name)
        self._fillContents()

    def _fillContents(self):
        # TODO create the initial timeline according to the project settings
        self.audiocomp = TimelineComposition(media_type = MEDIA_TYPE_AUDIO, name="audiocomp")
        self.videocomp = TimelineComposition(media_type = MEDIA_TYPE_VIDEO, name="videocomp")
        self.videocomp.linkObject(self.audiocomp)

        # add default audio/video sources
        defaultaudio = gst.element_factory_make("audiotestsrc")
        defaultaudio.props.volume = 0
        defaultaudiosource = gst.element_factory_make("gnlsource", "defaultaudiosource")
        defaultaudiosource.add(defaultaudio)
        self.audiocomp.setDefaultSource(defaultaudiosource)

        defaultvideo = gst.element_factory_make("videotestsrc")
        defaultvideo.props.pattern = 2
        defaultvideosource = gst.element_factory_make("gnlsource", "defaultvideosource")
        defaultvideosource.add(defaultvideo)
        self.videocomp.setDefaultSource(defaultvideosource)

        self.timeline.add(self.audiocomp.gnlobject,
                          self.videocomp.gnlobject)
        self.audiocomp.gnlobject.connect("pad-added", self._newAudioPadCb)
        self.videocomp.gnlobject.connect("pad-added", self._newVideoPadCb)
        self.audiocomp.gnlobject.connect("pad-removed", self._removedAudioPadCb)
        self.videocomp.gnlobject.connect("pad-removed", self._removedVideoPadCb)

    def _newAudioPadCb(self, unused_audiocomp, pad):
        asrc = gst.GhostPad("asrc", pad)
        asrc.set_active(True)
        self.timeline.add_pad(asrc)

    def _newVideoPadCb(self, unused_videocomp, pad):
        vsrc = gst.GhostPad("vsrc", pad)
        vsrc.set_active(True)
        self.timeline.add_pad(vsrc)

    def _removedAudioPadCb(self, unused_audiocomp, unused_pad):
        self.timeline.remove_pad(self.timeline.get_pad("asrc"))

    def _removedVideoPadCb(self, unused_audiocomp, unused_pad):
        self.timeline.remove_pad(self.timeline.get_pad("vsrc"))

    def getAutoSettings(self):
        v = self.videocomp._getAutoSettings()
        a = self.audiocomp._getAutoSettings()
        if not v and not a:
            return None
        # return an ExportSettings containing the combination of
        # the autosettings from the audio and video composition.
        s = ExportSettings()
        if v:
            s.videowidth = v.videowidth
            s.videoheight = v.videoheight
            s.videorate = v.videorate
            s.videopar = v.videopar
        if a:
            s.audiochannels = a.audiochannels
            s.audiorate = a.audiorate
            s.audiodepth = a.audiodepth
        return s


class TimelineObject(gobject.GObject):
    """
    Base class for all timeline objects

    * Properties
      _ Start/Duration Time
      _ Media Type
      _ Gnonlin Object
      _ Linked Object
	_ Can be None
	_ Must have same duration
      _ Brother object
        _ This is the same object but with the other media_type

    * signals
      _ 'start-duration-changed' : start position, duration position
      _ 'linked-changed' : new linked object
    """

    __gsignals__ = {
        "start-duration-changed" : ( gobject.SIGNAL_RUN_LAST,
                                 gobject.TYPE_NONE,
                                 (gobject.TYPE_PYOBJECT, gobject.TYPE_PYOBJECT, )),
        "linked-changed" : ( gobject.SIGNAL_RUN_LAST,
                             gobject.TYPE_NONE,
                             (gobject.TYPE_PYOBJECT, ))
        }
    
##     start = -1  # start time
##     duration = -1   # duration time
##     linked = None       # linked object
##     brother = None      # brother object, the other-media equivalent of this object
##     factory = None      # the Factory with more details about this object
##     gnlobject = None    # The corresponding GnlObject
##     media_type = MEDIA_TYPE_NONE        # The Media Type of this object

    def __init__(self, factory=None, start=-1, duration=-1,
                 media_type=MEDIA_TYPE_NONE, name=""):
        gobject.GObject.__init__(self)
        gst.log("new TimelineObject :%s" % name)
        self.start = -1
        self.duration = -1
        self.linked = None
        self.brother = None
        self.name = name
        # Set factory and media_type and then create the gnlobject
        self.factory = factory
        self.media_type = media_type
        self.gnlobject = self._makeGnlObject()
        self.gnlobject.connect("notify::start", self._startDurationChangedCb)
        self.gnlobject.connect("notify::duration", self._startDurationChangedCb)
        self._setStartDurationTime(start, duration)

    def __repr__(self):
        return '<%s %s>' % (type(self).__name__, self.name)

    def _makeGnlObject(self):
        """ create and return the gnl_object """
        raise NotImplementedError

    def _unlinkObject(self):
        # really unlink the objects
        if self.linked:
            self.linked = None
            self.emit("linked-changed", None)

    def _linkObject(self, object):
        # really do the link
        self.linked = object
        self.emit("linked-changed", self.linked)

    def linkObject(self, object):
        """
        link another object to this one.
        If there already is a linked object ,it will unlink it
        """
        if self.linked and not self.linked == object:
            self.unlinkObject()
        self._linkObject(object)
        pass

    def unlinkObject(self):
        """
        unlink from the current linked object
        """
        self.linked._unlinkObject()
        self._unlinkObject()

    def relinkBrother(self):
        """
        links the object back to it's brother
        """
        # if already linked, unlink from previous
        if self.linked:
            self.unlinkObject()

        # link to brother
        if self.brother:
            self.linkObject(self.brother)

    def getBrother(self, autolink=True):
        """
        returns the brother element if it's possible,
        if autolink, then automatically link it to this element
        """
        if not self.brother:
            self.brother = self._makeBrother()
            if not self.brother:
                return None
        if autolink and not self.linked == self.brother:
            self.relinkBrother()
        return self.brother

    def _makeBrother(self):
        """
        Make the exact same object for the other media_type
        implemented in subclasses
        """
        raise NotImplementedError
    
    def _setStartDurationTime(self, start=-1, duration=-1):
        # really modify the start/duration time
        self.gnlobject.info("start:%s , duration:%s" %( gst.TIME_ARGS(start),
                                                        gst.TIME_ARGS(duration)))
        if not duration == -1 and not self.duration == duration:
            self.duration = duration
            self.gnlobject.set_property("duration", long(duration))
        if not start == -1 and not self.start == start:
            self.start = start
            self.gnlobject.set_property("start", long(start))
            
    def setStartDurationTime(self, start=-1, duration=-1):
        """ sets the start and/or duration time """
        self._setStartDurationTime(start, duration)
        if self.linked:
            self.linked._setStartDurationTime(start, duration)

    def _startDurationChangedCb(self, gnlobject, property):
        """ start/duration time has changed """
        self.gnlobject.debug("property:%s" % property.name)
        start = -1
        duration = -1
        if property.name == "start":
            start = gnlobject.get_property("start")
            if start == self.start:
                start = -1
            else:
                self.start = long(start)
        elif property.name == "duration":
            duration = gnlobject.get_property("duration")
            if duration == self.duration:
                duration = -1
            else:
                self.gnlobject.debug("duration changed:%s" % gst.TIME_ARGS(duration))
                self.duration = long(duration)
        #if not start == -1 or not duration == -1:
        self.emit("start-duration-changed", self.start, self.duration)
            

        
class TimelineSource(TimelineObject):
    """
    Base class for all sources (O input)
    """

    def __init__(self, **kw):
        TimelineObject.__init__(self, **kw)
        

class TimelineFileSource(TimelineSource):
    """
    Seekable sources (mostly files)
    """
    __gsignals__ = {
        "media-start-duration-changed" : ( gobject.SIGNAL_RUN_LAST,
                                       gobject.TYPE_NONE,
                                       (gobject.TYPE_UINT64, gobject.TYPE_UINT64))
        }

    media_start = -1
    media_duration = -1
    
    def __init__(self, media_start=-1, media_duration=-1, **kw):
        TimelineSource.__init__(self, **kw)
        self.gnlobject.connect("notify::media-start", self._mediaStartDurationChangedCb)
        self.gnlobject.connect("notify::media-duration", self._mediaStartDurationChangedCb)
        if media_start == -1:
            media_start = 0
        if media_duration == -1:
            media_duration = self.factory.length
        self.setMediaStartDurationTime(media_start, media_duration)
        
    def _makeGnlObject(self):
        if self.media_type == MEDIA_TYPE_AUDIO:
            caps = gst.caps_from_string("audio/x-raw-int;audio/x-raw-float")
            postfix = "audio"
        elif self.media_type == MEDIA_TYPE_VIDEO:
            caps = gst.caps_from_string("video/x-raw-yuv;video/x-raw-rgb")
            postfix = "video"
        else:
            raise NameError, "media type is NONE !"
        self.factory.lastbinid = self.factory.lastbinid + 1

        gnlobject = gst.element_factory_make("gnlsource", "source-" + self.name + "-" + postfix + str(self.factory.lastbinid))
        decodebin = SingleDecodeBin(caps=caps, uri=self.factory.name)
        gnlobject.add(decodebin)
##         gnlobject.set_property("location", self.factory.name)
        gnlobject.set_property("caps", caps)
        gnlobject.set_property("start", long(0))
        gnlobject.set_property("duration", long(self.factory.length))
        return gnlobject
        
    def _makeBrother(self):
        """ make the brother element """
        self.gnlobject.info("making filesource brother")
        # find out if the factory provides the other element type
        if self.media_type == MEDIA_TYPE_NONE:
            return None
        if self.media_type == MEDIA_TYPE_VIDEO:
            if not self.factory.is_audio:
                return None
            brother = TimelineFileSource(media_start=self.media_start, media_duration=self.media_duration,
                                         factory=self.factory, start=self.start, duration=self.duration,
                                         media_type=MEDIA_TYPE_AUDIO, name=self.name)
        elif self.media_type == MEDIA_TYPE_AUDIO:
            if not self.factory.is_video:
                return None
            brother = TimelineFileSource(media_start=self.media_start, media_duration=self.media_duration,
                                         factory=self.factory, start=self.start, duration=self.duration,
                                         media_type=MEDIA_TYPE_VIDEO, name=self.name)
        else:
            brother = None
        return brother

    def _setMediaStartDurationTime(self, start=-1, duration=-1):
        gst.info("TimelineFileSource start:%d , duration:%d" % (start, duration))
        if not duration == -1 and not self.media_duration == duration:
            self.media_duration = duration
            self.gnlobject.set_property("media-duration", long(duration))
        if not start == -1 and not self.media_start == start:
            self.media_start = start
            self.gnlobject.set_property("media-start", long(start))

    def setMediaStartDurationTime(self, start=-1, duration=-1):
        """ sets the media start/duration time """
        self._setMediaStartDurationTime(start, duration)
        if self.linked and isinstance(self.linked, TimelineFileSource):
            self.linked._setMediaStartDurationTime(start, duration)

    def _mediaStartDurationChangedCb(self, gnlobject, property):
        mstart = None
        mduration = None
        if property.name == "media-start":
            mstart = gnlobject.get_property("media-start")
            if mstart == self.media_start:
                mstart = None
            else:
                self.media_start = mstart
        elif property.name == "media-duration":
            mduration = gnlobject.get_property("media-duration")
            if mduration == self.media_duration:
                mduration = None
            else:
                self.media_duration = mduration
        if mstart or mduration:
            self.emit("media-start-duration-changed",
                      self.media_start, self.media_duration)

    def getExportSettings(self):
        return self.factory.getExportSettings()


class TimelineLiveSource(TimelineSource):
    """
    Non-seekable sources (like cameras)
    """

    def __init__(self, **kw):
        TimelineSource.__init__(self, **kw)


class TimelineComposition(TimelineSource):
    """
    Combines sources and effects
    _ Sets the priority of the GnlObject(s) contained within
    _ Effects have always got priorities higher than the sources
    _ Can contain global effects that have the highest priority
      _ Those global effect spread the whole duration of the composition
    _ Simple effects (applies on one source), can overlap each other
    _ Complex Effect(s) have a lower priority than Simple Effect(s)
      _ For sanity reasons, Complex Effect(s) can't overlap each other
    _ Transitions have the lowest effect priority
    _ Source(s) contained in it follow each other if possible
    _ Source can overlap each other
      _ Knows the "visibility" of the sources contained within

    _ Provides a "condensed list" of the objects contained within
      _ Allows to quickly show a top-level view of the composition
    
    * Sandwich view example (top: high priority):
	     [ Global Simple Effect(s) (RGB, YUV, Speed,...)	]
	     [ Simple Effect(s), can be several layers		]
	     [ Complex Effect(s), non-overlapping		]
	     [ Transition(s), non-overlapping			]
	     [ Layers of sources				]

    * Properties:
      _ Global Simple Effect(s) (Optionnal)
      _ Simple Effect(s)
      _ Complex Effect(s)
      _ Transition(s)
      _ Condensed list

    * Signals:
      _ 'condensed-list-changed' : condensed list
      _ 'global-effect-added' : a global-effect was added to the composition
      _ 'global-effect-removed' : a global-effect was removed from the composition
      _ 'simple-effect-added' : a simple-effect was added to the composition
      _ 'simple-effect-removed' : a simple-effect was removed from the composition
      _ 'complex-effect-added' : a complex-effect was added to the composition
      _ 'complex-effect-removed' : a complex-effect was removed from the composition
      _ 'transition-added' : a transition was added to the composition
      _ 'transition-removed' : a transitions was removed from the composition
      _ 'source-added' : a TimelineSource was added to the composition
      _ 'source-removed' : a TimelineSource was removed from the composition
    """

    __gsignals__ = {
        'condensed-list-changed' : ( gobject.SIGNAL_RUN_LAST,
                                     gobject.TYPE_NONE,
                                     (gobject.TYPE_PYOBJECT, )),
        'global-effect-added' : ( gobject.SIGNAL_RUN_LAST,
                                  gobject.TYPE_NONE,
                                  (gobject.TYPE_PYOBJECT, )),
        'global-effect-removed' : ( gobject.SIGNAL_RUN_LAST,
                                    gobject.TYPE_NONE,
                                    (gobject.TYPE_PYOBJECT, )),
        'simple-effect-added' : ( gobject.SIGNAL_RUN_LAST,
                                  gobject.TYPE_NONE,
                                  (gobject.TYPE_PYOBJECT, )),
        'simple-effect-removed' : ( gobject.SIGNAL_RUN_LAST,
                                    gobject.TYPE_NONE,
                                    (gobject.TYPE_PYOBJECT, )),
        'complex-effect-added' : ( gobject.SIGNAL_RUN_LAST,
                                   gobject.TYPE_NONE,
                                   (gobject.TYPE_PYOBJECT, )),
        'complex-effect-removed' : ( gobject.SIGNAL_RUN_LAST,
                                     gobject.TYPE_NONE,
                                     (gobject.TYPE_PYOBJECT, )),
        'transitions-added' : ( gobject.SIGNAL_RUN_LAST,
                                gobject.TYPE_NONE,
                                (gobject.TYPE_PYOBJECT, )),
        'transition-removed' : ( gobject.SIGNAL_RUN_LAST,
                                 gobject.TYPE_NONE,
                                 (gobject.TYPE_PYOBJECT, )),
        'source-added' : ( gobject.SIGNAL_RUN_LAST,
                           gobject.TYPE_NONE,
                           (gobject.TYPE_PYOBJECT, )),
        'source-removed' : ( gobject.SIGNAL_RUN_LAST,
                             gobject.TYPE_NONE,
                             (gobject.TYPE_PYOBJECT, )),
        }

    # mid-level representation/storage of sources/effecst lists
    #
    # Global effects:
    #   Apply on the whole duration of the composition.
    #   Sorted by priority (first: most important)
    #
    # Simple effects:
    #   2 dimensional list
    #   Priority, then time
    #
    # Complex effect:
    # Transitions:
    #   Simple list sorted by time
    #
    # Source List:
    #   List of layers
    #   Layers:
    #      Handles priority attribution to contained sources
    #      3-tuple:
    #      _ minimum priority
    #      _ maximum priority
    #      _ list of sources sorted by time

    def __init__(self, **kw):
        self.global_effects = [] # list of effects starting from highest priority
        self.simple_effects = [[]] # list of layers of simple effects (order: priority, then time)
        self.complex_effects = [] # complex effect sorted by time
        self.transitions = [] # transitions sorted by time
        # list of layers of simple effects (order: priority, then time)
        # each layer contains (min priority, max priority, list objects)
        #sources = [(2048, 2060, [])] 
        self.condensed = [] # list of sources/transitions seen from a top-level view
        self.sources = [(2048, 2060, [])]
        self.defaultSource = None
        TimelineSource.__init__(self, **kw)

    def __len__(self):
        """ return the number of sources in this composition """
        l = 0
        for min, max, sources in self.sources:
            l += len(sources)
        return l

    def __nonzero__(self):
        """ Always returns True, else bool(object) will return False if len(object) == 0 """
        return True

    def _makeGnlObject(self):
        return gst.element_factory_make("gnlcomposition", "composition-" + self.name)

    # global effects
    
    def addGlobalEffect(self, global_effect, order, auto_linked=True):
        """
        add a global effect
        order :
           n : put at the given position (0: first)
           -1 : put at the end (lowest priority)
        auto_linked : if True will add the brother (if any) of the given effect
                to the linked composition with the same order
        """
        raise NotImplementedError

    def removeGlobalEffect(self, global_effect, remove_linked=True):
        """
        remove a global effect
        If remove_linked is True and the effect has a linked effect, will remove
        it from the linked composition
        """
        raise NotImplementedError

    # simple effects
    
    def addSimpleEffect(self, simple_effect, order, auto_linked=True):
        """
        add a simple effect

        order works if there's overlapping:
           n : put at the given position (0: first)
           -1 : put underneath all other simple effects
        auto_linked : if True will add the brother (if any) of the given effect
                to the linked composition with the same order
        """
        raise NotImplementedError

    def removeSimpleEffect(self, simple_effect, remove_linked=True):
        """
        removes a simple effect
        If remove_linked is True and the effect has a linked effect, will remove
        it from the linked composition
        """
        raise NotImplementedError

    # complex effect

    def addComplexEffect(self, complex_effect, auto_linked=True):
        """
        adds a complex effect
        auto_linked : if True will add the brother (if any) of the given effect
                to the linked composition with the same order
        """
        # if it overlaps with existing complex effect, raise exception
        raise NotImplementedError

    def removeComplexEffect(self, complex_effect, remove_linked=True):
        """
        removes a complex effect
        If remove_linked is True and the effect has a linked effect, will remove
        it from the linked composition
        """
        raise NotImplementedError

    def _makeCondensedList(self):
        """ makes a condensed list """
        def condensed_sum(list1, list2):
            """ returns a condensed list of the two given lists """
            self.gnlobject.info( "condensed_sum")
            self.gnlobject.info( "comparing %s with %s" % (list1, list2))
            if not len(list1):
                return list2[:]
            if not len(list2):
                return list1[:]
            
            res = list1[:]

            # find the objects in list2 that go under list1 and insert them at
            # the good position in res
            for obj in list2:
                # go through res to see if it can go somewhere
                for pos in range(len(res)):
                    if obj.start <= res[pos].start:
                        res.insert(pos, obj)
                        break
                if pos == len(res) and obj.start > res[-1].start:
                    res.append(obj)
            self.gnlobject.info("returning %s" % res)
            return res
                
            
        lists = [x[2] for x in self.sources]
        lists.insert(0, self.transitions)
        return reduce(condensed_sum, lists)

    def _updateCondensedList(self):
        """ updates the condensed list """
        self.gnlobject.info("_update_condensed_list")
        # build a condensed list
        clist = self._makeCondensedList()
        self.gnlobject.info("clist:%r" % clist)
        if self.condensed:
            # compare it to the self.condensed
            list_changed = False
##             print "comparing:"
##             for i in self.condensed:
##                 print i.gnlobject, i.start, i.duration
##             print "with"
##             for i in clist:
##                 print i.gnlobject, i.start, i.duration
            if not len(clist) == len(self.condensed):
                list_changed = True
            else:
                for a, b in zip(clist, self.condensed):
                    if not a == b:
                        list_changed = True
                        break
        else:
            list_changed = True
        self.gnlobject.log("list_change : %s" % list_changed)
        # if it's different or new, set it to self.condensed and emit the signal
        if list_changed:
            self.condensed = clist
            self.emit("condensed-list-changed", self.condensed)

    # Transitions

    def addTransition(self, transition, source1, source2, auto_linked=True):
        """
        adds a transition between source1 and source2
        auto_linked : if True will add the brother (if any) of the given transition
                to the linked composition with the same parameters
        """
        # if it overlaps with existing transition, raise exception
        raise NotImplementedError

    def moveTransition(self, transition, source1, source2):
        """ move a transition between source1 and source2 """
        # if it overlays with existing transition, raise exception
        raise NotImplementedError

    def removeTransition(self, transition, reorder_sources=True, remove_linked=True):
        """
        removes a transition,
        If reorder sources is True it puts the sources
        between which the transition was back one after the other
        If remove_linked is True and the transition has a linked effect, will remove
        it from the linked composition
        """
        raise NotImplementedError

    # Sources

    def _getSourcePosition(self, source):
        position = 0
        foundit = False
        for slist in self.sources:
            if source in slist[2]:
                foundit = True
                break
            position = position + 1
        if foundit:
            return position + 1
        return 0

    def _haveGotThisSource(self, source):
        for slist in self.sources:
            if source in slist[2]:
                return True
        return False


    def _addSource(self, source, position):
        """ private version of addSource """
        def my_add_sorted(sources, object):
            slist = sources[2]
            i = 0
            for item in slist:
                if item.start > object.start:
                    break
                i = i + 1
            object.gnlobject.set_property("priority", sources[0])
            slist.insert(i, object)
            
        # TODO : add functionnality to add above/under
        # For the time being it's hardcoded to a single layer
        position = 1

        # add it to the correct self.sources[position]
        my_add_sorted(self.sources[position-1], source)
        
        # add it to self.gnlobject
        self.gnlobject.info("adding %s to our composition" % source.gnlobject)
        self.gnlobject.add(source.gnlobject)

        self.gnlobject.info("added source %s" % source.gnlobject)
        gst.info("%s" % str(self.sources))
        self.emit('source-added', source)

        # update the condensed list
        self._updateCondensedList()

    def addSource(self, source, position, auto_linked=True):
        """
        add a source (with correct start/duration time already set)
        position : the vertical position
          _ 0 : insert above all other layers
          _ n : insert at the given position (1: top row)
          _ -1 : insert at the bottom, under all sources
        auto_linked : if True will add the brother (if any) of the given source
                to the linked composition with the same parameters
        """
        self.gnlobject.info("source %s , position:%d, self.sources:%s" %(source, position, self.sources))
        
        self._addSource(source, position)

        # if auto_linked and self.linked, add brother to self.linked with same parameters
        if auto_linked and self.linked:
            if source.getBrother():
                self.linked._addSource(source.brother, position)

    def insertSourceAfter(self, source, existingsource, push_following=True, auto_linked=True):
        """
        inserts a source after the existingsource, pushing the following ones
        if existingsource is None, it puts the source at the beginning
        """
        if existingsource:
            self.gnlobject.info("insert_source after %s" % existingsource.gnlobject)
        else:
            self.gnlobject.info("insert_source at the beginning")
            
        # find the time where it's going to be added
        if not existingsource or not self._haveGotThisSource(existingsource):
            start = 0
            position = 1
            existorder = 0
        else:
            start = existingsource.start + existingsource.duration
            position = self._getSourcePosition(existingsource)
            existorder = self.sources[position - 1][2].index(existingsource) + 1

        gst.info("start=%s, position=%d, existorder=%d, sourcelength=%s" % (gst.TIME_ARGS(start),
                                                                            position,
                                                                            existorder,
                                                                            gst.TIME_ARGS(source.factory.length)))
##         for i in self.sources[position -1][2]:
##             print i.gnlobject, i.start, i.duration
        # set the correct start/duration time
        duration = source.factory.length
        source.setStartDurationTime(start, duration)
        
        # pushing following
        if push_following and not position in [-1, 0]:
            #print self.gnlobject, "pushing following", existorder, len(self.sources[position - 1][2])
            for i in range(existorder, len(self.sources[position - 1][2])):
                mvsrc = self.sources[position - 1][2][i]
                self.gnlobject.info("pushing following")
                #print "run", i, "start", mvsrc.start, "duration", mvsrc.duration
                # increment self.sources[position - 1][i] by source.factory.length
                mvsrc.setStartDurationTime(mvsrc.start + source.factory.length)
        
        self.addSource(source, position, auto_linked=auto_linked)

    def appendSource(self, source, position=1, auto_linked=True):
        """
        puts a source after all the others
        """
        self.gnlobject.info("source:%s" % source.gnlobject)
        # find the source with the highest duration time on the first layer
        if self.sources[position - 1]:
            existingsource = self.sources[position - 1][2][-1]
        else:
            existingsource = None

        self.insertSourceAfter(source, existingsource, push_following=False,
                               auto_linked=auto_linked)

    def prependSource(self, source, push_following=True, auto_linked=True):
        """
        adds a source to the beginning of the sources
        """
        self.gnlobject.info("source:%s" % source.gnlobject)
        self.insertSourceAfter(source, None, push_following, auto_linked)

    def moveSource(self, source, newpos, move_linked=True, push_neighbours=True, collapse_neighbours=True):
        """
        Moves the source to the new position. The position is the existing source before which to move
        the source.
        
        If move_linked is True and the source has a linked source, the linked source will
        be moved to the same position.
        If collapse_neighbours is True, all sources located AFTER the OLD position of the
        source will be shifted in the past by the duration of the removed source.
        If push_neighbours is True, then sources located AFTER the NEW position will be shifted
        forward in time, in order to have enough free space to insert the source.
        """
        self.gnlobject.info("source:%s , newpos:%d, move_linked:%s, push_neighbours:%s, collapse_neighbours:%s" % (source,
                                                                                                                   newpos,
                                                                                                                   move_linked,
                                                                                                                   push_neighbours,
                                                                                                                   collapse_neighbours))
        sources = self.sources[0][2]
        oldpos = sources.index(source)
        if newpos == -1:
            newpos = len(sources)

        self.gnlobject.info("source was at position %d in his layer" % oldpos)

        # if we're not moving, return
        if (oldpos == newpos):
            self.gnlobject.warning("source is already at the correct position, not moving")
            return

        # 0. Temporarily remove moving source from composition
        self.gnlobject.log("Setting source priority at maximum [%d]" % self.sources[0][1])
        source.gnlobject.set_property("priority", self.sources[0][1])

        # 1. if collapse_neighbours, shift all downstream sources by duration
        if collapse_neighbours and oldpos != len(sources) - 1:
            self.gnlobject.log("collapsing all following neighbours after the old position [%d]" % oldpos)
            for i in range(oldpos + 1, len(sources)):
                obj = sources[i]
                self.gnlobject.log("moving source %d %s" % (i, obj))
                obj.setStartDurationTime(start = (obj.start - source.duration))

        # 2. if push_neighbours, make sure there's enough room at the new position
        if push_neighbours and newpos != len(sources):
            pushmin = source.duration
            if newpos != 0:
                pushmin += sources[newpos - 1].start + sources[newpos - 1].duration
            self.gnlobject.log("We need to make sure sources after newpos are at or after %s" % gst.TIME_ARGS(pushmin))
            if sources[newpos].start < pushmin:
                # don't push sources after old position
                if oldpos > newpos:
                    stoppos = oldpos
                else:
                    stoppos = len(sources)
                self.gnlobject.log("pushing neighbours between new position [%d] and stop [%d]" % (newpos, stoppos))
                for i in range(newpos, stoppos):
                    obj = sources[i]
                    obj.setStartDurationTime(start = pushmin)
                    pushmin += obj.duration

        # 3. move the source
        newtimepos = 0
        if newpos:
            newtimepos += sources[newpos - 1].start + sources[newpos - 1].duration
        self.gnlobject.log("Setting source start position to %s" % gst.TIME_ARGS(newtimepos))
        source.setStartDurationTime(start = newtimepos)

        self.gnlobject.log("Removing source from position [%d] and putting it to position [%d]" % (oldpos, newpos - 1))
        del sources[oldpos]
        sources.insert(newpos - 1, source)
        source.gnlobject.set_property("priority", self.sources[0][0])

        # 4. same thing for brother
        # FIXME : TODO

        # 5. update condensed list
        self.gnlobject.log("Done moving %s , updating condensed list" % source)
        self._updateCondensedList()

    def removeSource(self, source, remove_linked=True, collapse_neighbours=False):
        """
        Removes a source.
        
        If remove_linked is True and the source has a linked source, will remove
        it from the linked composition.
        If collapse_neighbours is True, then all object after the removed source
        will be shifted in the past by the duration of the removed source.
        """
        self.gnlobject.info("source:%s, remove_linked:%s, collapse_neighbours:%s" % (source, remove_linked, collapse_neighbours))
        sources = self.sources[0]

        pos = sources[2].index(source)
        self.gnlobject.info("source was at position %d in his layer" % pos)

        # actually remove it
        self.gnlobject.info("Really removing %s from our composition" % source.gnlobject)
        self.gnlobject.remove(source.gnlobject)
        del sources[2][pos]

        # collapse neighbours
        if collapse_neighbours:
            self.gnlobject.info("Collapsing neighbours")
            for i in range(pos, len(sources[2])):
                obj = sources[2][i]
                obj.setStartDurationTime(start = (obj.start - source.duration))

        # if we have a brother
        if remove_linked and self.linked and self.linked.gnlobject:
            self.linked.gnlobject.remove(source.linked.gnlobject)
            self.linked.emit('source-removed', source.linked)
            self.linked._updateCondensedList()

        self.emit('source-removed', source)
        # update the condensed list
        self._updateCondensedList()


    def setDefaultSource(self, source):
        """
        Adds a default source to the composition.
        Default sources will be used for gaps within the composition.
        """
        if self.defaultSource:
            self.gnlobject.remove(self.defaultSource)
        source.props.priority = 2 ** 32 - 1
        self.gnlobject.add(source)
        self.defaultSource = source

    def getDefaultSource(self):
        """
        Returns the default source.
        """
        return self.defaultSource


    # AutoSettings methods

    def _autoVideoSettings(self):
        # return a ExportSettings in which all videos of the composition
        # will be able to be exported without loss
        biggest = None
        # FIXME : we suppose we only have only source layer !!!
        # FIXME : we in fact return the first file's settings
        for source in self.sources[0][2]:
            if not biggest:
                biggest = source.getExportSettings()
            else:
                set = source.getExportSettings()
                for prop in ['videowidth', 'videoheight',
                             'videopar', 'videorate']:
                    if set.__getattribute__(prop) != biggest.__getattribute__(prop):
                        return biggest
        return biggest

    def _autoAudioSettings(self):
        # return an ExportSettings in which all audio source of the composition
        # will be able to be exported without (too much) loss
        biggest = None
        # FIXME : we suppose we only have only source layer !!!
        # FIXME : we in fact return the first file's settings
        for source in self.sources[0][2]:
            if not biggest:
                biggest = source.getExportSettings()
            else:
                set = source.getExportSettings()
                for prop in ['audiorate', 'audiochannels', 'audiodepth']:
                    if set.__getattribute__(prop) != biggest.__getattribute__(prop):
                        return biggest
        return biggest


    def _getAutoSettings(self):
        gst.log("len(self) : %d" % len(self))
        if not len(self):
            return None
        if len(self) == 1:
            # return the settings of our only source
            return self.sources[0][2][0].getExportSettings()
        else:
            if self.media_type == MEDIA_TYPE_AUDIO:
                return self._autoAudioSettings()
            else:
                return self._autoVideoSettings()
        

class TimelineEffect(TimelineObject):
    """
    Base class for effects (1->n input(s))
    """

    def __init__(self, nbinputs=1, **kw):
        self.nbinputs = nbinputs
        TimelineObject.__init__(self, **kw)

    def _makeGnlObject(self):
        gnlobject = gst.element_factory_make("gnloperation", "operation-" + self.name)
        self._setUpGnlOperation(gnlobject)
        return gnlobject

    def _setUpGnlOperation(self, gnlobject):
        """ fill up the gnloperation for the first go """
        raise NotImplementedError

class TimelineSimpleEffect(TimelineEffect):
    """
    Simple effects (1 input)
    """

    def __init__(self, factory, **kw):
        self.factory = factory
        TimelineEffect.__init__(self, **kw)


class TimelineTransition(TimelineEffect):
    """
    Transition Effect
    """
    source1 = None
    source2 = None

    def __init__(self, factory, source1=None, source2=None, **kw):
        self.factory = factory
        TimelineEffect.__init__(self, nbinputs=2, **kw)
        self.setSources(source1, source2)

    def setSources(self, source1, source2):
        """ changes the sources in between which the transition lies """
        self.source1 = source1
        self.source2 = source2


class TimelineComplexEffect(TimelineEffect):
    """
    Complex Effect
    """

    def __init__(self, factory, **kw):
        self.factory = factory
        # Find out the number of inputs
        nbinputs = 2
        TimelineEffect.__init__(self, nbinputs=nbinputs, **kw)