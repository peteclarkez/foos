import ctypes
import numpy
from pi3d.constants import *
from pi3d.util.Ctypes import c_ints
from PIL import Image
from contextlib import contextmanager
import time
import os

DISPMANX_FLAGS_ALPHA_FROM_SOURCE = 0
DISPMANX_NO_ROTATE = 0
VC_IMAGE_RGB888 = 5

class UpdatingBGDisplay():
    def __init__(self, imgw, imgh, layer):
        self.layer = layer
        self.w, self.h = ctypes.c_int(), ctypes.c_int()
        # choose the next smalles multiple of 16 for width and height (might some of the bg)
        self.imgw, self.imgh = self._alignDown(imgw, 16), self._alignDown(imgh, 16)
        s = bcm.graphics_get_display_size(0, ctypes.byref(self.w), ctypes.byref(self.h)) 
        assert s >= 0
        
        self.dispman_display = bcm.vc_dispmanx_display_open(0) #LCD setting
        assert self.dispman_display != 0

        self.img_element = None
        self.img_resource = None
        self.createBuffer()

    def close(self):
        with self.bcmUpdate() as dispman_update:
            bcm.vc_dispmanx_element_remove(dispman_update, self.img_element)
            
        bcm.vc_dispmanx_resource_delete(self.img_resource)
        bcm.vc_dispmanx_display_close(self.dispman_display)
        
    @contextmanager
    def bcmUpdate(self):
        dispman_update = bcm.vc_dispmanx_update_start(10)
        assert dispman_update != 0
        yield dispman_update
        result = bcm.vc_dispmanx_update_submit_sync(dispman_update);
        assert result == 0

    def _alignUp(self, n, alignTo):
        return ((n + alignTo - 1) & ~(alignTo - 1))

    def _alignDown(self, n, alignTo):
        return n & ~(alignTo - 1)

    def createBuffer(self):
        self.vc_image_ptr = ctypes.c_uint()
        self.pitch = self.imgw * 3;
        assert(self.pitch % 32 == 0)
        self.imgtype = VC_IMAGE_RGB888

        with self.bcmUpdate() as dispman_update:
            self.img_resource = bcm.vc_dispmanx_resource_create(
                self.imgtype,
                self.imgw,
                self.imgh,
                ctypes.byref(self.vc_image_ptr))
            assert (self.img_resource != 0)
            self.src_rect = c_ints((0, 0, self.imgw << 16, self.imgh << 16))
            # scale width so that aspect ratio is retained with display height - might crop right part of the bg
            dstw = int(self.h.value * self.imgw / self.imgh)
            self.dst_rect = c_ints((0, 0, dstw, self.h))

            self.alpha = c_ints((DISPMANX_FLAGS_ALPHA_FROM_SOURCE, 255, 0))

            self.img_element = bcm.vc_dispmanx_element_add(dispman_update,
                                                    self.dispman_display,
                                                    self.layer,
                                                    ctypes.byref(self.dst_rect),
                                                    self.img_resource,
                                                    ctypes.byref(self.src_rect),
                                                    DISPMANX_PROTECTION_NONE,
                                                    ctypes.byref(self.alpha),
                                                    0,
                                                    DISPMANX_NO_ROTATE)
            assert(self.img_element != 0)

        
    def loadImg(self, path):
        image = Image.open(path)

        if image.size[0] < self.imgw or image.size[1] < self.imgh:
            # if the image is too smal we'd have to change the element, so rescale
            # this shouldn't happen as all bgs are expected to be of a fixed size
            print("Image {} is too small: expected at least {} but got {} - will resize image".format(path, (self.imgw, self.imgh), image.size))
            image = image.resize((self.imgw, self.imgh), Image.BILINEAR)

        if image.mode != "RGB":
            print("Image {} is not of correct mode: expected {} but got {}".format(path, "RGB", image.mode)) 
            image = image.convert("RGB")

        return image
        
    def setImg(self, path):
        img = self.loadImg(path)
        
        bmpRect = c_ints((0, 0, self.imgw, self.imgh))
        imgbuffer = numpy.array(img)

        result = bcm.vc_dispmanx_resource_write_data(self.img_resource,
                                                     self.imgtype,
                                                     self.pitch,
                                                     imgbuffer.ctypes.data,
                                                     ctypes.byref(bmpRect))
        with self.bcmUpdate() as dispman_update:
            bcm.vc_dispmanx_element_modified(dispman_update, self.img_element, ctypes.byref(self.dst_rect));


class BGRotater:
    def __init__(self, w, h, layer, imgdir, interval):
        self.dsp = UpdatingBGDisplay(w, h, layer)
        self.allFiles = self.getFiles(imgdir)
        self.interval = interval
        self.last_change = 0
        
    def getFiles(self, imgdir):
        while True:
            files = [os.path.join(imgdir, f) for f in os.listdir(imgdir) if 'jpg' in f.lower() or 'png' in f.lower()]
            for f in files:
                yield f
        
    def change(self):
        self.last_change = time.time()
        self.dsp.setImg(next(self.allFiles))

    def encourageChange(self):
        """Call this at a good time to do the bg change"""
        if self.interval > 0 and time.time() > (self.last_change + self.interval):
            self.change()
            
        
    def close(self):
        self.dsp.close()

