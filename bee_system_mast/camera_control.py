import sys
import time
import numpy as np
from gi.repository import Aravis
import pickle
import ctypes
import numpy as np
from multiprocessing import Queue
import threading
#import queue
import gc
from datetime import datetime as dt
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
        self.img = {}
        self.img['raw'] = np.reshape(raw,[1544,2064])
        self.img['datetime'] = dt.now()

class Camera_Control():
    def set_exposure(self,exposure):
        print("set exposure")
        self.camera_config_queue.put({'instruction':'exposure', 'exposure':exposure})
        
    def set_gain(self,gain):
        self.camera_config_queue.put({'instruction':'gain', 'gain':gain})

    def print_status(self,camera):
        print("Camera vendor : %s" %(camera.get_vendor_name ()))
        print("Camera model  : %s" %(camera.get_model_name ()))
        print("Camera id     : %s" %(camera.get_device_id ()))
        print("Acquisit. mode: %s" %(camera.get_acquisition_mode ()))
        print("Pixel format  : %s" %(camera.get_pixel_format_as_string ()))
     
    def __init__(self):
        self.prs = Queue()
        self.camera_config_queue = Queue()
          
    def camera_config_worker(self,camera):#awkwardly need this to allow other processes to update camera config
        print("Camera config worker started")
        while True:
            command = self.camera_config_queue.get()
            print("received command")
            if command['instruction']=='exposure':
                camera.set_exposure_time(command['exposure'])
            if command['instruction']=='gain':
                camera.set_gain(command['gain'])
            print(command)
                
                
    def worker(self,exposure=500,gain=0):
        """
        exposure (in us, default 500us)
        gain (image gain in dB, default 0)
        """
        print("Creating camera object")
        import os
        print("PROCESS ID: ", os.getpid())
        os.system("sudo chrt -f -p 1 %d" % os.getpid())
        Aravis.enable_interface ("Fake")
        camera = Aravis.Camera.new (None)
        camera.set_region (0,0,2064,1544) #2064x1544
        print("Old packet size: %d" % camera.gv_get_packet_size())
        camera.gv_set_packet_size(1024)
        print("New packet size: %d" % camera.gv_get_packet_size())
        #camera.set_binning(1,1) #basically disable
        #camera.set_frame_rate (10.0)
        camera.set_exposure_time(exposure)#us
        camera.set_gain(gain)
        camera.set_pixel_format (Aravis.PIXEL_FORMAT_MONO_8)
        camera.set_trigger("Line1")
        t = threading.Thread(target=self.camera_config_worker,args=(camera,))
        t.start()
        self.print_status(camera)
        print("Getting payload object")
        payload = camera.get_payload ()
        print("Creating stream")
        stream = camera.create_stream(None, None)
        if stream is None:
            print("Failed to construct stream")
            return
        print("Starting Acquisition")
        camera.start_acquisition ()
        print("Creating stream buffer")
        for i in range(0,8):
            stream.push_buffer (Aravis.Buffer.new_allocate(payload))
        print("Done")    
        
    

        print("Camera Control Worker Starting")
        while True:
            pr = [None,None]
            skip = False
            #print("")
            #print("Debug info: Number of stream buffers")
            print(stream.get_n_buffers(),self.prs.qsize())
            print("Awaiting photo pair:")
            timeouts = [4000000,2000000]#in us: 10000s or 1s
            for i in [0,1]:
                pr[i] = PhotoResult(stream)
                #print("Awaiting photo %d" % i)
                pr[i].get_photo(timeouts[i]) #blocking
                #print("Got Photo %d of pair" % i)
                #print("Status: %d" % pr[i].status)

            streamsin, streamsout = stream.get_n_buffers()
            if pr[0].ok and pr[1].ok:
                print("o  Both ok, saving (%d, %d)" % (streamsin, streamsout))
                self.prs.put([pr[0].img,pr[1].img])
                pr[0].returnbuffer()
                pr[1].returnbuffer()                
            else:
                print("x  Failed (%d, %d)" % (streamsin, streamsout))
                pr[0].returnbuffer()
                pr[1].returnbuffer()                
                
    def close(self):
        pass #todo

