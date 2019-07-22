from flask import Flask, make_response
from bee_system.blink_control import Blink_Control, configure_gpio
from bee_system.camera_control import Camera_Control
from bee_system.tracking_control import Tracking_Control
import multiprocessing
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

app = Flask(__name__)
CORS(app)

startupdone = False
cam_control = None
tracking_controls = []

import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

@app.route('/startup/<int:exposure>/<int:gain>')
def startup(exposure,gain):
    global startupdone
    if startupdone:
        return "Already Running"
    configure_gpio()
    global blink_control
    blink_control = Blink_Control()
    t = multiprocessing.Process(target=blink_control.worker)#,args=(blink_control.run_blink,))
    t.start()
    global cam_control
    cam_control = Camera_Control()
    t = multiprocessing.Process(target=cam_control.worker,args=(exposure,gain))
    t.start()
    global tracking_controls
    tracking_results = []
    for i in range(3): #sets of processes analysing the images:
        tracking_control = Tracking_Control(cam_control.prs,tracking_results)
        t = multiprocessing.Process(target=tracking_control.worker)
        t.start()
        tracking_controls.append(tracking_control)
    startupdone = True
    print("Startup Complete")
    return "Startup complete"

@app.route('/setinterval/<float:interval>')
def setinterval(interval):
    print("Set interval %0.2f" % interval)
    if startupdone:
        global blink_control
        blink_control.t.value = interval
    return "0"
    
@app.route('/setinterval/<int:interval>')
def setinterval_int(interval):
    return setinterval(1.0*interval)


@app.route('/setcamera/<int:exposure>/<int:gain>/<int:blocksize>/<int:offset>/<int:stepsize>/<int:skipcalc>/<int:searchcount>/<int:startx>/<int:starty>/<int:endx>/<int:endy>')
def setcamera(exposure,gain,blocksize,offset,stepsize,skipcalc,searchcount,startx,starty,endx,endy):

    global startupdone
    if not startupdone:
        return "Not online"
    global cam_control    
    print("Setting camera parameters")    
    cam_control.set_exposure(exposure)
    cam_control.set_gain(gain)
    global tracking_controls
    print("Setting tracking parameters")
    for tracking_control in tracking_controls:
        tracking_control.blocksize.value = blocksize
        tracking_control.stepsize.value = stepsize
        tracking_control.searchcount.value = searchcount
        tracking_control.startx.value = startx
        tracking_control.starty.value = starty
        tracking_control.endx.value = endx
        tracking_control.endy.value = endy                    
        tracking_control.offset.value = offset
        skipcalc = (skipcalc>0)
        tracking_control.skipcalc.value = skipcalc
        print("START and END: ")
        print(tracking_control.startx.value,tracking_control.starty.value)
        print(tracking_control.endx.value,tracking_control.endy.value)
    return "Setup complete"

@app.route('/')
def hello_world():
    return 'Hello, World!'

@app.route('/start')
def start():
    print("Start")
    global blink_control
    print("Setting blink control")
    blink_control.run_blink.set()
    return "Blinking Started"

@app.route('/nextimage')
def nextimage():
    if not startupdone:
        return "Not online"
    if cam_control.prs.empty():
        return "No new image"
    else:
        pair = cam_control.prs.get()
        pair[0].returnbuffer()
        pair[1].returnbuffer()
        return "done"

    
@app.route('/getcurrentimage/<int:img>/<int:cmax>/<int:raw>')
def getcurrentimage(img,cmax):
    if not startupdone:
        return "Not online"
    if cam_control.prs.empty():
        return "No new image"
    if cmax<1 or cmax>255:
        return "cmax parameter must be between 1 and 255."
    if img<0 or img>1:
        return "image must be 0 or 1"
    pair = cam_control.prs.queue[0]#get() #dodgy peekingg
    #msg = ""
    #msg += "%0.5f\n" % (np.mean(pair[0].img))
    #msg += "%0.2f\n" % (np.mean(pair[1].img))
    #return msg
    rawimg = pair[img].img[::10,::10]
    if raw:
        response = str(rawimg)
    else:
        fig = Figure(figsize=[3,2.25])
        axis = fig.add_subplot(1, 1, 1)   
        axis.imshow(rawimg,clim=[0,cmax])
        fig.subplots_adjust(left=0, bottom=0, right=1, top=1)
        canvas = FigureCanvas(fig)
        output = io.BytesIO()
        fig.patch.set_alpha(0)
        canvas.print_png(output)
        response = make_response(output.getvalue())

    response.mimetype = 'image/png'
    return response

@app.route('/gettrackingimagecount')
def gettrackingimagecount():
    global startupdone
    if startupdone:
        return str(len(tracking_controls[0].tracking_results))
    else:
        return "0"
        
@app.route('/getsystemstatus')
def getsystemstatus():
    global startupdone
    if startupdone:
        msg = ""
        msg += "Processing Queue: %d\n" % tracking_controls[0].camera_queue.qsize()
        cpu_usage_string = os.popen("cat /proc/loadavg").readline()
        msg += "CPU Usage:        %s" % cpu_usage_string        
        if len(tracking_controls[0].tracking_results)>0:
            msg += "\n\nDiagnostic Message from last tracking computation\n"
            msg += "<pre>"+tracking_controls[0].tracking_results[-1]['msg']+"</pre>"
        msg+="\n\n+<pre>"+mem_top()+"</pre>"
        return msg
    else:
        return "0"
    
@app.route('/gettrackingimage/<int:index>/<int:img>/<int:cmax>/<int:lowres>/<int:raw>')
def gettrackingimage(index,img,cmax,lowres,raw):
    if cmax<1 or cmax>255:
        return "cmax parameter must be between 1 and 255."
    if img<0 or img>1:
        return "image must be 0 or 1"
    if (index>=len(tracking_controls[0].tracking_results)) or (index<0):
        return "out of range"
    
    if lowres:    
        pair = tracking_controls[0].tracking_results[index]['lowresimages']
        figsize = [3,2.25]
    else:
        pair = tracking_controls[0].tracking_results[index]['highresimages']
        figsize = [2,2]
    if not raw: 
        fig = Figure(figsize=figsize)
        axis = fig.add_subplot(1, 1, 1)   
        axis.imshow(pair[img],clim=[0,cmax])
    else:
        rawimg = pair[img].copy()#slow?
        
    
    
    if lowres:    
        marker = 'w+'
        for i,loc in enumerate(tracking_controls[0].tracking_results[index]['maxvals']):
            if not raw:
                axis.plot(loc['location'][1]/10,loc['location'][0]/10,marker,markersize=(10/(i+1)))
                if i>3: marker = 'b+'
                axis.plot(loc['location'][1]/10,loc['location'][0]/10,'xw',markersize=(loc['score']/5))
            else:
                rawimg[int(loc['location'][1]/10-(10/(i+1))):int(loc['location'][1]/10+(10/(i+1))),int(loc['location'][0]/10)]=255
                rawimg[int(loc['location'][1]/10),int(loc['location'][0]/10-(10/(i+1))):int(loc['location'][0]/10+(10/(i+1)))]=255
                rawimg[int(loc['location'][1]/10-(loc['score']/5)):int(loc['location'][1]/10+(loc['score']/5)),int(loc['location'][0]/10)]=255
                rawimg[int(loc['location'][1]/10),int(loc['location'][0]/10-(loc['score']/5)):int(loc['location'][0]/10+(loc['score']/5))]=128

                
    else:
        if img==0:
            #shift = tracking_controls[0].tracking_results[index]['shift']
            if not raw:
                axis.plot(pair[img].shape[0]/2,pair[img].shape[1]/2,'w+',markersize=20)
            else:
                pass
        if img==1:
            axis.plot(pair[img].shape[0]/2,pair[img].shape[1]/2,'w+',markersize=20)
            
    if not raw:
        fig.subplots_adjust(left=0, bottom=0, right=1, top=1)
        canvas = FigureCanvas(fig)
        output = io.BytesIO()
        fig.patch.set_alpha(0)
        canvas.print_png(output)
        response = make_response(output.getvalue())
        response.mimetype = 'image/png'
    else:
        response = str(rawimg)
    return response

import pickle
@app.route('/getpickleddataset.p')
def getpickleddataset():
    data = pickle.dumps(tracking_controls[0].tracking_results)
    response = make_response(data)
    response.mimetype = 'text/plain'
    return response


#@app.route('/findretroreflectors')
#def findretroreflectors():
#    if not startupdone:
#        return "Not online"
#    pair = cam_control.prs.queue[0]
#    shift = rd.getshift(pair[0].img,pair[1].img)
#    out_img = rd.getblockmaxedimage(pair[1].img)
#    done = rd.alignandsubtract(out_img,shift,pair[0].img)    
#    p = np.unravel_index(done.argmax(), done.shape)
#    return "Location: %d %d" % p


@app.route('/imagestats/<int:index>')
def imagestats(index):
    msg = ""
    msg+=tracking_controls[0].get_status_string(index)
    return msg
    
@app.route('/stop')
def stop():
    global blink_control
    blink_control.run_blink.clear()
    return "Blinking Stopped"  
    
@app.route('/shutdown')
def shutdown():
    """
    INCOMPLETE NEEDS TO FREE CAMERA ETC!
    """
    global startupdone
    if startupdone:
        global cam_control
        cam_control.close()
        cam_control = None
        stop()
        global blink_control
        blink_control = None
        startupdone = False
        sys.exit()        
        return "Shutdown Complete"
    else:
        sys.exit()
        return "System already offline"

    
if __name__ == "__main__":
    app.run(host="0.0.0.0")
