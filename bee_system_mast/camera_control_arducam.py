import sys
import os
import time
import threading
import numpy as np
import signal
import json

import sys
sys.path.insert(0, "/home/pi/ArduCAM_USB_Camera_Shield/RaspberryPi/Python/External_trigger_demo") #to do - this is not very good.

import ArducamSDK
from QueueBuffer import QueueBuffer as QB
from bee_system_mast.photoresult import PhotoResult
     
        

class Camera_Control():
    def set_exposure(self,exposure):
        #self.camera.set_exposure_time(exposure)#us
        setval = round(exposure/22.22)
        print(setval)
        ArducamSDK.Py_ArduCam_writeSensorReg(self.handle,0x3012,setval)
        print(ArducamSDK.Py_ArduCam_readSensorReg(self.handle,0x3012))

    def set_gain(self,gain):
        #assert False, "NOT IMPLEMENTED"    
        #self.camera.set_gain(gain)
        #0x20 = 32 = no gain, 
        ArducamSDK.Py_ArduCam_writeSensorReg(self.handle,0x305e,round(32*gain))
        

    def configBoard(self,handle,fileNodes):
        for i in range(0,len(fileNodes)):
            fileNode = fileNodes[i]
            buffs = []
            command = fileNode[0]
            value = fileNode[1]
            index = fileNode[2]
            buffsize = fileNode[3]
            for j in range(0,len(fileNode[4])):
                buffs.append(int(fileNode[4][j],16))
            ArducamSDK.Py_ArduCam_setboardConfig(handle,int(command,16),int(value,16),int(index,16),int(buffsize,16),buffs)

    def writeSensorRegs(self,handle,fileNodes):
        for i in range(0,len(fileNodes)):
            fileNode = fileNodes[i]      
            if fileNode[0] == "DELAY":
                time.sleep(float(fileNode[1])/1000)
                continue
            regAddr = int(fileNode[0],16)
            val = int(fileNode[1],16)
            ArducamSDK.Py_ArduCam_writeSensorReg(handle,regAddr,val)

    def camera_initFromFile(self,fileName):
        #global cfg,Width,Height,color_mode
        #load config file
        config = json.load(open(fileName,"r"))

        camera_parameter = config["camera_parameter"]
        self.width = int(camera_parameter["SIZE"][0])
        self.height = int(camera_parameter["SIZE"][1])

        self.BitWidth = camera_parameter["BIT_WIDTH"]
        ByteLength = 1
        if self.BitWidth > 8 and self.BitWidth <= 16:
            ByteLength = 2
            save_raw = True
        FmtMode = int(camera_parameter["FORMAT"][0])
        self.color_mode = (int)(camera_parameter["FORMAT"][1])

        I2CMode = camera_parameter["I2C_MODE"]
        I2cAddr = int(camera_parameter["I2C_ADDR"],16)
        TransLvl = int(camera_parameter["TRANS_LVL"])
        print(self.width, "x", self.height)
        cfg = {"u32CameraType":0x4D091031,
                "u32Width":self.width,"u32Height":self.height,
                "usbType":0,
                "u8PixelBytes":ByteLength,
                "u16Vid":0,
                "u32Size":0,
                "u8PixelBits":self.BitWidth,
                "u32I2cAddr":I2cAddr,
                "emI2cMode":I2CMode,
                "emImageFmtMode":FmtMode,
                "u32TransLvl":TransLvl }

        ret,handle,rtn_cfg = ArducamSDK.Py_ArduCam_open(cfg,self.indextouse)
        if ret != 0:
            print("open fail,ret_val = ",ret)
            return None
           

        usb_version = rtn_cfg['usbType']
        #config board param
        self.configBoard(handle,config["board_parameter"])

        if usb_version == ArducamSDK.USB_1 or usb_version == ArducamSDK.USB_2:
            self.configBoard(handle,config["board_parameter_dev2"])
        if usb_version == ArducamSDK.USB_3:
            self.configBoard(handle,config["board_parameter_dev3_inf3"])
        if usb_version == ArducamSDK.USB_3_2:
            self.configBoard(handle,config["board_parameter_dev3_inf2"])
        
        self.writeSensorRegs(handle,config["register_parameter"])
        
        if usb_version == ArducamSDK.USB_3:
            self.writeSensorRegs(handle,config["register_parameter_dev3_inf3"])
        if usb_version == ArducamSDK.USB_3_2:
            self.writeSensorRegs(handle,config["register_parameter_dev3_inf2"])

        rtn_val,datas = ArducamSDK.Py_ArduCam_readUserData(handle,0x400-16, 16)
        return handle
 

    def getSingleFrame(self,handle):
        #global running,Width,Height,save_flag,cfg,color_mode,totalFrames,save_raw
        count = 0
        print("Take picture.")
        rtn_val,data,rtn_cfg = ArducamSDK.Py_ArduCam_getSingleFrame(handle)
        
        if rtn_val != 0:
            print("Take picture fail,ret_val = ",rtn_val)
            return
            
        datasize = rtn_cfg['u32Size']
        if datasize == 0:
            print("data length zero!")
            return
        print(datasize)
        print(type(data))
        im = np.frombuffer(data,np.uint8,count = datasize).reshape(self.height,self.width)
        if self.blink_control is not None:
            direction = self.blink_control.direction
            flash = self.blink_control.flashselection
        else:
            direction = None
            flash = None
        self.prs.put(PhotoResult(im,direction,flash))
        #self.ascii_draw_image(im[0::10,0::5])
        
        
    def ascii_draw_image(self, img):
        symbol = "$@B\%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/\\|()1{}[]?-_+~<>i!lI;:,\"^`'. "[::-1]
        st = ""
        for row in img:
            for v in row:
                v = v / 2
                if v>69:
                    v=69
                if v<0:
                    v=0            
                st = st + symbol[int(v)]
            st = st + "\n"
        print(st)
        
    def print_status(self):
        print("no status report implemented.")
        
    def __init__(self,blink_control=None,serialtouse=None,config_file_name = "AR0135_1280x964_ext_trigger_M.json"):
        if not os.path.exists(config_file_name):
            print("Config file does not exist.")
            exit()
        
        devices_num,index,serials = ArducamSDK.Py_ArduCam_scan()
        print("Found %d devices"%devices_num)
        self.indextouse = None
        for i in range(devices_num):
            datas = serials[i]
            serial = ""
            for it,d in enumerate(datas[0:12]):
                serial = serial + "%c" % d
                if (it%4)==3 and it<11: serial = serial+"-"
            if serialtouse is None:
                if i==0: usethis=True
            else:
                if serial == serialtouse: usethis=True
            if usethis: self.indextouse=i
            print("Index:",index[i],"Serial:",serial,"Use:",usethis)
            
        time.sleep(2)
            
        self.handle = self.camera_initFromFile(config_file_name)
        if self.handle != None:
            ret_val = ArducamSDK.Py_ArduCam_setMode(self.handle,ArducamSDK.EXTERNAL_TRIGGER_MODE)
            if(ret_val == ArducamSDK.USB_BOARD_FW_VERSION_NOT_SUPPORT_ERROR):
                print("USB_BOARD_FW_VERSION_NOT_SUPPORT_ERROR")
                exit(0)
        self.prs = QB()
        self.blink_control = blink_control
          
    def worker(self):  
        while True:
            ArducamSDK.Py_ArduCam_softTrigger(self.handle)
            if ArducamSDK.Py_ArduCam_isFrameReady(self.handle):
                self.getSingleFrame(self.handle)
            
if __name__ == "__main__":
    c = Camera_Control()
    c.worker()
