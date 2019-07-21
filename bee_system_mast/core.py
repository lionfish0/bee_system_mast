from flask import Flask, make_response, jsonify
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
from datetime import datetime as dt

"""Column CorrectionThe AR0134 uses a column parallel readout architecture to achieve fast frame rates. Without any corrections, the consequence of this architecture is that different column signal paths have slightly different offsets that might show up on the final image as structured fixed pattern noise.The AR0134 has column correction circuitry that measures this offset and removes it from the image before output. This is done by sampling dark rows containing tied pixels and measuring an offset coefficient per column to be corrected later in the signal path.Column correction can be enabled/disabled via R0x30D4[15]. Additionally, the number of rows used for this offset coefficient measurement is set in R0x30D4[3:0]. By default this register is set to 0x7, which means that 8 rows are used. This is the recommended value. Other control features regarding column correction can be viewed in the AR0134 Register reference. Any changes to column correction settings need to be done when the sensor streaming is disabled and the appropriate triggering sequence must be followed as described below -  https://cdn.hackaday.io/files/21966939793344/AR0134_DG_C.PDF
"""

app = Flask(__name__)
CORS(app)

startupdone = False
cam_control = None
tracking_control = None

import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

@app.route('/startup/<int:exposure>/<int:gain>/<string:timestring>')
def startup(exposure,gain,timestring):
    d = dt.strptime(timestring,"%Y-%m-%dT%H:%M:%S")
    #NOTE: This requires:
    #        sudo visudo
    # then add:
    #        pi ALL=(ALL) NOPASSWD: /bin/date
    os.system('sudo /bin/date -s %s' % d.strftime("%Y-%m-%dT%H:%M:%S"))
    global startupdone
    if startupdone:
        return "Already Running"

    global blink_control
    blink_control = Blink_Control()
    t = threading.Thread(target=blink_control.worker)#,args=(blink_control.run_blink,))
    t.start()
    global cam_control
    cam_control = Camera_Control(blink_control=blink_control)
    cam_control.print_status()
    t = threading.Thread(target=cam_control.worker)
    t.start()
    global tracking_control
    tracking_control = Tracking_Control(cam_control.prs)
    for _ in range(4):
        t = threading.Thread(target=tracking_control.worker)
        t.start()        
    startupdone = True
    return "Startup complete"

@app.route('/setinterval/<float:interval>')
@app.route('/setinterval/<int:interval>')
def setinterval(interval):
    print("setting")
    if startupdone:
        global blink_control
        blink_control.totaltime = interval
    return "0"


@app.route('/setcamera/<int:exposure>/<int:gain>/<int:blocksize>/<int:offset>/<int:stepsize>/<int:skipcalc>')
def setcamera(exposure,gain,blocksize,offset,stepsize,skipcalc):
    global startupdone
    if not startupdone:
        return "Not online"
    global cam_control
    cam_control.set_exposure(exposure)
    cam_control.set_gain(gain)
    global tracking_control
    tracking_control.blocksize = blocksize
    tracking_control.stepsize = stepsize
    tracking_control.offset = offset
    skipcalc = (skipcalc>0)
    tracking_control.skipcalc = skipcalc
    
    return "Setup complete"

@app.route('/')
def hello_world():
    return 'Hello, World!'

@app.route('/start')
def start():
    global blink_control
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

    
@app.route('/getcurrentimage/<int:img>/<int:cmax>')
def getcurrentimage(img,cmax):
    if not startupdone:
        return "Not online"
    if cam_control.prs.empty():
        return "No new image"
    if cmax<1 or cmax>255:
        return "cmax parameter must be between 1 and 255."
    if img<0 or img>1:
        return "image must be 0 or 1"
    img = cam_control.prs.queue[0]#get() #dodgy peekingg
    #msg = ""
    #msg += "%0.5f\n" % (np.mean(pair[0].img))
    #msg += "%0.2f\n" % (np.mean(pair[1].img))
    #return msg
    fig = Figure(figsize=[3,2.25])
    axis = fig.add_subplot(1, 1, 1)   
    axis.imshow(img[::10,::10],clim=[0,cmax])
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
        return str(len(tracking_control.tracking_results))
    else:
        return "0"
        
@app.route('/getsystemstatus')
def getsystemstatus():
    global startupdone
    if startupdone:
        msg = ""
        msg += "Processing Queue: %d\n" % tracking_control.camera_queue.unpopped()
        cpu_usage_string = os.popen("cat /proc/loadavg").readline()
        msg += "CPU Usage:        %s" % cpu_usage_string        
        if len(tracking_control.tracking_results)>0:
            msg += "\n\nDiagnostic Message from last tracking computation\n"
            msg += "<pre>"+tracking_control.tracking_results[-1]['msg']+"</pre>"
        msg+="\n\n+<pre>"+mem_top()+"</pre>"
        return msg
    else:
        return "0"
    
@app.route('/gettrackingimage/<int:index>/<int:img>/<int:cmax>/<int:lowres>')
def gettrackingimage(index,img,cmax,lowres):
    if cmax<1 or cmax>255:
        return "cmax parameter must be between 1 and 255."
    if img<0 or img>1:
        return "image must be 0 or 1"
    if (index>=len(tracking_control.tracking_results)) or (index<0):
        return "out of range"
    
    if lowres:    
        pair = tracking_control.tracking_results[index]['lowresimages']
        fig = Figure(figsize=[3,2.25])        
    else:
        pair = tracking_control.tracking_results[index]['highresimages']
        fig = Figure(figsize=[2,2])
    axis = fig.add_subplot(1, 1, 1)   
    axis.imshow(pair[img],clim=[0,cmax])
    
    
    
    if lowres:    
        marker = 'w+'
        for i,loc in enumerate(tracking_control.tracking_results[index]['maxvals']):
            axis.plot(loc['location'][1]/10,loc['location'][0]/10,marker,markersize=(10/(i+1)))
            if i>3: marker = 'b+'
            axis.plot(loc['location'][1]/10,loc['location'][0]/10,'xw',markersize=(loc['score']/5))            
    else:
        if img==0:
            #shift = tracking_control.tracking_results[index]['shift']
            axis.plot(pair[img].shape[0]/2,pair[img].shape[1]/2,'w+',markersize=20)
        if img==1:
            axis.plot(pair[img].shape[0]/2,pair[img].shape[1]/2,'w+',markersize=20)
            
    fig.subplots_adjust(left=0, bottom=0, right=1, top=1)
    canvas = FigureCanvas(fig)
    output = io.BytesIO()
    fig.patch.set_alpha(0)
    canvas.print_png(output)
    response = make_response(output.getvalue())

    response.mimetype = 'image/png'
    return response

@app.route('/getrawtrackingimage/<int:index>/<int:img>/<int:lowres>')
def getrawtrackingimage(index,img,lowres):
    if img<0 or img>1:
        return "image must be 0 or 1"
    if (index>=len(tracking_control.tracking_results)) or (index<0):
        return "out of range"
    
    if lowres:    
        pair = tracking_control.tracking_results[index]['lowresimages']
    else:
        pair = tracking_control.tracking_results[index]['highresimages']
    trackingresults = []
    for i,loc in enumerate(tracking_control.tracking_results[index]['maxvals']):
        trackingresults.append([int(loc['location'][0]),int(loc['location'][1]),int(loc['score'])])
    print(trackingresults)
    return jsonify({'image':pair[img].astype(int).tolist(), 'tracking':trackingresults}) #TODO: add locations from below to JSON object
    

import pickle
@app.route('/getpickleddataset.p')
def getpickleddataset():
    data = pickle.dumps(tracking_control.tracking_results)
    response = make_response(data)
    response.mimetype = 'text/plain'
    return response


@app.route('/findretroreflectors')
def findretroreflectors():
    if not startupdone:
        return "Not online"
    pair = cam_control.prs.queue[0]
    shift = rd.getshift(pair[0].img,pair[1].img)
    out_img = rd.getblockmaxedimage(pair[1].img)
    done = rd.alignandsubtract(out_img,shift,pair[0].img)    
    p = np.unravel_index(done.argmax(), done.shape)
    return "Location: %d %d" % p


@app.route('/imagestats/<int:index>')
def imagestats(index):
    msg = ""
    msg+=tracking_control.get_status_string(index)
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
