from flask import Flask, make_response, jsonify
from bee_system_mast.blink_control import Blink_Control
from bee_system_mast.camera_control_arducam import Camera_Control
from bee_system_mast.tracking_control import Tracking_Control
import multiprocessing
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
import subprocess

app = Flask(__name__)
CORS(app)

startupdone = False
cam_control = None
tracking_controls = []

import logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

@app.route('/startup/<int:exposure>/<int:gain>/<string:timestring>')
def startupint(exposure,gain,timestring):
    return startup(exposure,gain,timestring)

@app.route('/startup/<int:exposure>/<float:gain>/<string:timestring>')
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
    t = multiprocessing.Process(target=blink_control.worker)#,args=(blink_control.run_blink,))
    t.start()
    global cam_control
    cam_control = Camera_Control()
    t = multiprocessing.Process(target=cam_control.worker)
    t.start()
    global tracking_controls
    tracking_results = []
    for i in range(10): #sets of processes analysing the images:
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


@app.route('/setcamera/<int:exposure>/<int:gain>/<int:blocksize>/<int:offset>/<int:stepsize>/<int:searchbox>/<int:skipcalc>/<int:searchcount>/<int:startx>/<int:starty>/<int:endx>/<int:endy>')
def setcameraint(exposure,gain,blocksize,offset,stepsize,searchbox,skipcalc,searchcount,startx,starty,endx,endy):
    return setcamera(exposure,gain,blocksize,offset,stepsize,searchbox,skipcalc,searchcount,startx,starty,endx,endy)
@app.route('/setcamera/<int:exposure>/<float:gain>/<int:blocksize>/<int:offset>/<int:stepsize>/<int:searchbox>/<int:skipcalc>/<int:searchcount>/<int:startx>/<int:starty>/<int:endx>/<int:endy>')
def setcamera(exposure,gain,blocksize,offset,stepsize,searchbox,skipcalc,searchcount,startx,starty,endx,endy):

    global startupdone
    if not startupdone:
        return "Not online"
    global cam_control    
    print("Setting camera parameters")    
    cam_control.set_exposure(exposure)
    cam_control.set_gain(gain)
    global tracking_controls
    print("Setting tracking parameters")
    print(searchbox)
    for tracking_control in tracking_controls:
        tracking_control.blocksize.value = blocksize
        tracking_control.stepsize.value = stepsize
        tracking_control.searchbox.value = searchbox     
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
    print(tracking_controls[0].searchbox.value)
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
    pair = cam_control.prs.queue[0]#get() #dodgy peekingg
    #msg = ""
    #msg += "%0.5f\n" % (np.mean(pair[0].img))
    #msg += "%0.2f\n" % (np.mean(pair[1].img))
    #return msg
    fig = Figure(figsize=[3,2.25])
    axis = fig.add_subplot(1, 1, 1)   
    axis.imshow(pair[img].img[::10,::10],clim=[0,cmax])
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
        msg += "Processing Queue: %d\n" % cam_control.prs.unpopped() #tracking_controls[0].camera_queue.unpopped()
        cpu_usage_string = subprocess.check_output('cat /proc/loadavg', shell=True)
        msg += "CPU Usage:        %s" % cpu_usage_string        
        if len(tracking_controls[0].tracking_results)>0:
            msg += "\n\nDiagnostic Message from last tracking computation\n"
            msg += "<pre>"+tracking_controls[0].tracking_results[-1]['msg']+"</pre>"
        #msg+="\n\n+<pre>"+mem_top()+"</pre>"
        return msg
    else:
        return "0"
    
@app.route('/getrawtrackingimage/<int:index>/<int:img>/<int:lowres>')
def getrawtrackingimage(index,img,lowres):
    if img<0 or img>1:
        return "image must be 0 or 1"
    if (index>=len(tracking_controls[0].tracking_results)) or (index<0):
        return "out of range"

    if lowres:    
        pair = tracking_controls[0].tracking_results[index]['lowresimages']
    else:
        pair = tracking_controls[0].tracking_results[index]['highresimages']
    trackingresults = []    
    for i,loc in enumerate(tracking_controls[0].tracking_results[index]['maxvals']):
        #print(i)
        trackingresults.append([int(loc['location'][0]),int(loc['location'][1]),int(loc['score'])])
    
    return jsonify({'image':pair[img].astype(int).tolist(),'tracking':trackingresults}) #TODO: add locations from below to JSON object
    
    
    
##########    
@app.route('/gettrackingimage/<int:index>/<int:img>/<int:cmax>/<int:lowres>')
def gettrackingimage(index,img,cmax,lowres):
    if cmax<1 or cmax>255:
        return "cmax parameter must be between 1 and 255."
    if img<0 or img>1:
        return "image must be 0 or 1"
    if (index>=len(tracking_controls[0].tracking_results)) or (index<0):
        return "out of range"
    
    if lowres:    
        pair = tracking_controls[0].tracking_results[index]['lowresimages']
        fig = Figure(figsize=[3,2.25])        
    else:
        pair = tracking_controls[0].tracking_results[index]['highresimages']
        fig = Figure(figsize=[2,2])
    axis = fig.add_subplot(1, 1, 1)   
    axis.imshow(pair[img],clim=[0,cmax])
    
    
    
    if lowres:    
        marker = 'w+'
        for i,loc in enumerate(tracking_controls[0].tracking_results[index]['maxvals']):
            axis.plot(loc['location'][1]/10,loc['location'][0]/10,marker,markersize=(10/(i+1)))
            if i>3: marker = 'b+'
            axis.plot(loc['location'][1]/10,loc['location'][0]/10,'xw',markersize=(loc['score']/5))            
    else:
        if img==0:
            #shift = tracking_controls[0].tracking_results[index]['shift']
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
    
    
    
    
##########

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
