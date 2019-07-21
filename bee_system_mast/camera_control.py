import sys
import time
import numpy as np
from gi.repository import Aravis
import pickle
import ctypes
import numpy as np
import queue
import gc
###TODO Write a class that stores the camera etc
###TODO Rename file to avoid name collision with camera
###Check class methods work with threading

class PhotoResult():
    def __init__(self,stream):
        """A pair of photos (with and without flash)"""
        self.ok = False #not yet got an image
        self.buffer = None
        self.stream = stream
        self.status = -1
        
    def returnbuffer(self):
        """This must be called after data used so more images can be taken"""
        if self.buffer:
            self.stream.push_buffer(self.buffer) #return it to the buffer
        self.img = None #ensure we've no pointers at this data
        gc.collect()
            
    def get_photo(self,timeout):
        """Blocking: Stores an image in self.img"""
        #print("Awaiting Image from camera (timeout=%0.2fs)" % (timeout/1e6))
#        self.buffer = self.stream.timeout_pop_buffer(timeout) #blocking
        self.buffer = self.stream.pop_buffer() #blocking
        if self.buffer is None:
            self.ok = False
            print("buffer read failed")
            self.returnbuffer() #?
            return
        
        self.status = self.buffer.get_status()
        if self.status!=0:
            #print("failed status error")
            #print("Status:")
            print(self.status)
            self.ok = False
            self.returnbuffer()
            return
        #print("Success")
        self.ok = True #success
        raw = np.frombuffer(self.buffer.get_data(),dtype=np.uint8).astype(float)
        self.img = np.reshape(raw,[1544,2064])

class Camera_Control():
    def set_exposure(self,exposure):
        self.camera.set_exposure_time(exposure)#us

    def set_gain(self,gain):
        self.camera.set_gain(gain)

        
    def __init__(self,exposure=500,gain=0):
        """
        exposure (in us, default 500us)
        gain (image gain in dB, default 0)
        """
        print("Creating camera object")
        Aravis.enable_interface ("Fake")
        self.camera = Aravis.Camera.new (None)
        self.camera.set_region (0,0,2064,1544) #2064x1544
        print("Old packet size: %d" % self.camera.gv_get_packet_size())
        self.camera.gv_set_packet_size(1024)
        print("New packet size: %d" % self.camera.gv_get_packet_size())
        #camera.set_binning(1,1) #basically disable
        #camera.set_frame_rate (10.0)
        self.camera.set_exposure_time(exposure)#us
        self.camera.set_gain(gain)
        self.camera.set_pixel_format (Aravis.PIXEL_FORMAT_MONO_8)
        self.camera.set_trigger("Line1");
        print("Getting payload object")
        self.payload = self.camera.get_payload ()
        [self.x,self.y,self.width,self.height] = self.camera.get_region ()
        print("Creating stream")
        self.stream = self.camera.create_stream(None, None)
        if self.stream is None:
            print("Failed to construct stream")
            return
        print("Starting Acquisition")
        self.camera.start_acquisition ()
        print("Creating stream buffer")
        for i in range(0,50):
            self.stream.push_buffer (Aravis.Buffer.new_allocate(self.payload))
        print("Done")    
        self.prs = queue.Queue()
    
    def print_status(self):
        print("Camera vendor : %s" %(self.camera.get_vendor_name ()))
        print("Camera model  : %s" %(self.camera.get_model_name ()))
        print("Camera id     : %s" %(self.camera.get_device_id ()))
        print("Acquisit. mode: %s" %(self.camera.get_acquisition_mode ()))
        print("ROI           : %dx%d at %d,%d" %(self.width, self.height, self.x, self.y))
        print("Payload       : %d" %(self.payload))
        print("Pixel format  : %s" %(self.camera.get_pixel_format_as_string ()))

    def ascii_draw_image(self, img):
        symbol = "$@B\%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/\\|()1{}[]?-_+~<>i!lI;:,\"^`'. "[::-1]
        smallbslist = []
        string = []
        for row in img:
            for v in row:
                if v>69:
                    v=69
                if v<0:
                    v=0
                string.append(symbol[int(v)])
                string.append('\n')
        print(''.join(string))

    def worker(self):
        while True:
            pr = [None,None]
            skip = False
            #print("")
            #print("Debug info: Number of stream buffers")
            #print(self.stream.get_n_buffers())
            #print(self.stream.get_statistics())
            #print("Awaiting photo pair:")
            timeouts = [4000000,2000000]#in us: 10000s or 1s
            for i in [0,1]:
                pr[i] = PhotoResult(self.stream)
                #print("Awaiting photo %d" % i)
                pr[i].get_photo(timeouts[i]) #blocking
                #print("Got Photo %d of pair" % i)
                #print("Status: %d" % pr[i].status)

            streamsin, streamsout = self.stream.get_n_buffers()
            if pr[0].ok and pr[1].ok:
                print("o  Both ok, saving (%d, %d)" % (streamsin, streamsout))
                self.prs.put(pr)
            else:
                print("x  Failed (%d, %d)" % (streamsin, streamsout))
                pr[0].returnbuffer()
                pr[1].returnbuffer()                
                
    def close(self):
        self.camera.stop_acquisition ()

