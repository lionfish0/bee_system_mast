import numpy as np
import retrodetect as rd
import time

def ascii_draw(mat):
    symbols = np.array([s for s in ' .,:-=+*X#@'])[::-1]
    msg = ""    
    mat = (11*mat/(np.max(mat)+1)).astype(int)
    mat[mat<0] = 0
    for i in range(0,len(mat),2):
        msg+=''.join(symbols[mat][i])+"\n"
    return msg

def score_img(mat):
    width = min(mat.shape[0],mat.shape[1]) 
    if width<14: #can't check a circle around the point - more importantly we don't know where the middle is
        return 0
    a = np.linspace(0,2*np.pi,16)
    xs = width/2 + 4*np.cos(a)
    ys = width/2 + 4*np.sin(a)    
    m = -255
    for x,y in zip(xs.astype(int),ys.astype(int)):
        #if x<0: continue
        #if y<0: continue
        #if x>mat.shape[0]: continue
        #if y>mat.shape[1]: continue
        m = max(m,mat[x,y])
    return np.max(mat) - m
        
def erase_around(mat,x,y,extent=7):
    """
    Erase [default 5] pixels around x,y in mat (set to zero).
    Returns these pixels
    """
    print("Erasing around %d,%d" % (x,y))
    startx = x-extent
    endx = x+extent
    starty = y-extent
    endy = y+extent
    if startx<0: startx=0
    if starty<0: starty=0
    if startx>mat.shape[0]: startx=mat.shape[0]
    if starty>mat.shape[1]: starty=mat.shape[1]    
    erased_pixels = mat[startx:endx,starty:endy].copy()
    mat[startx:endx,starty:endy] = -255
    
  #  #TODO replace loop implementation with numpy array access
  #  for i in range(max(x-erase_extent,0),min(x+erase_extent,mat.shape[0])):
  #      for j in range(max(y-erase_extent,0),min(y+erase_extent,mat.shape[1])):
  #          mat[i,j] = 0
    
    return erased_pixels
    
    
class Tracking_Control():
    def __init__(self,camera_queue):
        """
        ...
        """
        print("Creating Tracking Object")
        self.camera_queue = camera_queue
        self.tracking_results = []
        self.blocksize = 30
        self.offset = 2
        self.stepsize = 10
        self.skipcalc = False
    
    def get_status_string(self,index):
        if index>=len(self.tracking_results): return "index greater than maximum tracked image"
        
        
        res = self.tracking_results[index]
        msg = ""
        for mvi,mv in enumerate(res['maxvals']):
            msg+= "--------\n"
            msg+= "Max value #%d\n" % mvi
            msg+= "Value: %d, Location: %d, %d\n" % (int(mv['val']), int(mv['location'][0]),int(mv['location'][1]))
        return msg

    def analyse_image_pair(self,pair,save=True):
        searchbox = 100
        starttime = time.time()
        msg = ""
        msg += "Processing Images\n"
        msg += "time: %0.4f\n" % (time.time()-starttime)
        filename = "/home/pi/"+time.strftime("%Y%m%d_%H%M%S",time.gmtime(pair[0].time))+("%0.4f" % (pair[0].time%1))[1:]
        if save: np.save(filename,pair[0].img,allow_pickle=False)
        msg += "time: %0.4f\n" % (time.time()-starttime)
        msg += "Computing Shift\n"
        
        shift = rd.getshift(pair[0].img,pair[1].img,step=self.stepsize,searchbox=searchbox)
        msg += "    shift: %d %d\n" % (shift[0], shift[1])
        msg += "time: %0.4f\n" % (time.time()-starttime)
        msg += "Computing output non-flash blocked image\n"
        if not self.skipcalc:
            out_img = rd.getblockmaxedimage(pair[1].img,self.blocksize,self.offset)
        else:
            out_img = pair[1].img
            
        msg += "time: %0.4f\n" % (time.time()-starttime)
        
        if not self.skipcalc:
            msg+="Aligning and subtracting\n"
            done = rd.alignandsubtract(out_img,shift,pair[0].img)
            msg += "time: %0.4f\n" % (time.time()-starttime)
            
            maxvals = []
            for it in range(1):
                print(".")
                argmax = done.argmax()
                p = np.array(np.unravel_index(argmax, done.shape))
                maxval = done[p[0],p[1]]
                peak_sample_img = erase_around(done,p[0],p[1])
                score = score_img(peak_sample_img)
                p += searchbox
                if (p[0]>=done.shape[0]) or (p[1]>=done.shape[1]):
                    print("error (out of range) location")
                    msg+="  [error (out of range) location]\n"
                    continue #can't use this one
                
                maxvals.append({'val':maxval, 'location':p.copy(), 'sample_img':peak_sample_img,'score':score})
                msg += " - Preparing stats"
                msg += "peak at [%d, %d] = %d [score=%0.5f]\n" % (p[0],p[1],maxval,score)
                msg += ascii_draw(peak_sample_img)
                msg += "\n"
                msg += "time: %0.4f\n" % (time.time()-starttime)
             
            msg += "time: %0.4f\n" % (time.time()-starttime)                    
            lowresimages = []
            #print("Generating low res images")
            msg += " - Generating low res images\n"
            for img in [0,1]:
                #print("Image %d" % img)
                #lowresimages.append(pair[img].img[::10,::10].copy())
                if img==0:
                    lowresimages.append(pair[img].img[::10,::10].copy())
                    #lowresimages.append(rd.getblockmaxedimage(pair[img].img,10,1)[::10,::10])
                else:
                    #lowresimages.append(out_img[::10,::10].copy()) 
                    #lowresimages.append(None)
                    lowresimages.append(rd.shiftimg(out_img,shift,cval=255)[::10,::10].copy()) 
                #lowresimages.append(rd.getblockmaxedimage(pair[img].img)[::10,::10])
                msg += "time: %0.4f\n" % (time.time()-starttime)
                
        else:
            print("Skipping compute")
            maxvals = []
            lowresimages = []
            shift = [np.nan,np.nan]
            
        
        msg += "Computation Complete, recording\n"
        msg += "time: %0.4f\n" % (time.time()-starttime)                    
        print("Computation Complete, saving")  
        highresimages = []
        for img in [0,1]:
            im = pair[img].img
            if img == 1:
                im = rd.shiftimg(im,shift,cval=255)
            s = im.shape
            highresimages.append(im[int(s[0]/2-100):int(s[0]/2+100),int(s[1]/2-100):int(s[1]/2+100)].copy())
            
        #self.tracking_results.append({'lowresimages':lowresimages,'highresimages':highresimages,'maxvals':maxvals,'shift':shift})
        self.tracking_results.append({'lowresimages':lowresimages,'highresimages':highresimages,'maxvals':maxvals,'shift':shift})
         
        
        

        msg += "time: %0.4f\n" % (time.time()-starttime)    
            
        msg += "Recording Complete\n Returning Buffers\n"
        msg += "time: %0.4f\n" % (time.time()-starttime)    
        msg += "Buffers returned\n"            
        self.tracking_results[-1]['msg'] = msg
                
    def worker(self):
        searchbox = 100
        while True:
            print("Awaiting image")
            #Awaiting image for processing [blocking]
            index, img = self.camera_queue.pop()
            print("New image: %d" % index)
            #we'll just look at the current and the previous photo (if it was in the same direction)
            if index<2:
                print("not enough images")
                continue

            oldimg = self.camera_queue.read(index-1)
            if oldimg.direction!=img.direction:
                print("previous image was in a different direction")
                continue
            self.analyse_image_pair([img,oldimg])
            


