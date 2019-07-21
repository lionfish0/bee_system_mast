from flask import Flask, make_response
from bee_system_mast.blink_control import Blink_Control
from bee_system_mast.camera_control_arducam import Camera_Control
from bee_system_mast.tracking_control import Tracking_Control
import threading
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure
import io
import retrodetect as rd
from flask_cors import CORS
import base64
import sys
import os
from mem_top import mem_top

def setup():
    global blink_control
    blink_control = Blink_Control()
    t = threading.Thread(target=blink_control.worker)#,args=(blink_control.run_blink,))
    t.start()
    return blink_control
    
def start():
    global blink_control
    blink_control.run_blink.set()

def stop():
    global blink_control
    blink_control.run_blink.clear()
