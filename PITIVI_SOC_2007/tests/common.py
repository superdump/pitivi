"""
A collection of objects to use for testing
"""

from pitivi.timeline.objects import TimelineObject, MEDIA_TYPE_NONE, MEDIA_TYPE_VIDEO, MEDIA_TYPE_AUDIO
from pitivi.timeline.source import TimelineSource, TimelineFileSource
from pitivi.objectfactory import ObjectFactory
import gst

class TestTimelineObject(TimelineObject):

    __data_type__ = "test-timeline-object"

    def _makeBrother(self):
        if self.media_type == MEDIA_TYPE_AUDIO:
            return TestTimelineObject(factory=self.factory,
                                      start=self.start,
                                      duration=self.duration,
                                      media_type=MEDIA_TYPE_VIDEO,
                                      name=self.name)
        if self.media_type == MEDIA_TYPE_VIDEO:
            return TestTimelineObject(factory=self.factory,
                                      start=self.start,
                                      duration=self.duration,
                                      media_type=MEDIA_TYPE_AUDIO,
                                      name=self.name)

    def _makeGnlObject(self):
        if self.media_type == MEDIA_TYPE_AUDIO:
            return self.factory.makeAudioBin()
        if self.media_type == MEDIA_TYPE_VIDEO:
            return self.factory.makeVideoBin()

class TestTimelineSource(TimelineSource):
    __data_type__ = "test-timeline-source"

    pass

class TestTimelineFileSource(TimelineFileSource):
    """
    Dummy TimelineFileSource
    """

    __data_type__ = "test-timeline-file-source"

    # we only override the gnlobject creation since we want to test all
    # other behaviour.

    def _makeGnlObject(self):
        gnlobject = gst.element_factory_make("gnlsource")
        fakesrc = gst.element_factory_make("fakesrc")
        gnlobject.add(fakesrc)
        if self.media_start == -1:
            self.media_start = 0
        if self.media_duration == -1:
            self.media_duration = self.factory.length
        if not self.start == -1:
            gnlobject.set_property("start", long(self.start))
        if not self.duration == -1:
            gnlobject.set_property("duration", long(self.duration))
        gnlobject.set_property("media-duration", long(self.media_duration))
        gnlobject.set_property("media-start", long(self.media_start))
        gnlobject.connect("notify::media-start", self._mediaStartDurationChangedCb)
        gnlobject.connect("notify::media-duration", self._mediaStartDurationChangedCb)
        return gnlobject

    def _makeBrother(self):
        # find out if the factory provides the other element type
        if self.media_type == MEDIA_TYPE_NONE:
            return None
        if self.media_type == MEDIA_TYPE_VIDEO:
            if not self.factory.is_audio:
                return None
            brother = TestTimelineFileSource(media_start=self.media_start, media_duration=self.media_duration,
                                         factory=self.factory, start=self.start, duration=self.duration,
                                         media_type=MEDIA_TYPE_AUDIO,
                                         name=self.name + "-brother")
        elif self.media_type == MEDIA_TYPE_AUDIO:
            if not self.factory.is_video:
                return None
            brother = TestTimelineFileSource(media_start=self.media_start, media_duration=self.media_duration,
                                         factory=self.factory, start=self.start, duration=self.duration,
                                         media_type=MEDIA_TYPE_VIDEO,
                                         name=self.name + "-brother")
        else:
            brother = None
        return brother


class TestObjectFactory(ObjectFactory):
    """
    Test ObjectFactory
    """

    __data_type__ = "test-object-factory"

    def __init__(self, audio=True, video=False):
        self.__audio = audio
        self.__video = video
        self.__id = 0
        ObjectFactory.__init__(self)
        self.is_video = video
        self.is_audio = audio
        self.lastbinid = 0

    def makeAudioBin(self):
        gnlobj = gst.element_factory_make("gnlsource", "test-audio-%d" % self.__id)
        self.__id = self.__id + 1
        gnlobj.add(gst.element_factory_make("audiotestsrc"))
        return gnlobj

    def makeVideoBin(self):
        gnlobj = gst.element_factory_make("gnlsource", "test-video-%d" % self.__id)
        self.__id = self.__id + 1
        gnlobj.add(gst.element_factory_make("videotestsrc"))
        return gnlobj

class TestFileSourceFactory(TestObjectFactory):

    __data_type__ = "test-file-source-factory"

    def __init__(self, duration=gst.SECOND, *args, **kwargs):
        TestObjectFactory.__init__(self, *args, **kwargs)
        self.length = duration
