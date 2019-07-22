import time
import RPi.GPIO as GPIO
import multiprocessing

class Blink_Control:
    def __init__(self,t=2.0):
        self.manager = multiprocessing.Manager()
        self.flashselection = self.manager.list()
        self.flash_select_pins = [2,3,14,15]
        self.trigger_pin = 4
        self.flashselection.append(0)
        self.flashselection.append(1)
        self.flashselection.append(2)
        self.flashselection.append(3)                        
        self.t = multiprocessing.Value('d',t)
        self.preptime = 0.05
        self.triggertime = 0.001
        GPIO.setmode(GPIO.BCM)
        for pin in self.flash_select_pins:
            GPIO.setup(pin, GPIO.OUT)
        GPIO.setup(self.trigger_pin, GPIO.OUT)
        time.sleep(0.5)
        for pin in self.flash_select_pins:
            GPIO.output(pin, False)
        GPIO.output(self.trigger_pin, False)
        self.run_blink = multiprocessing.Event()
    
    def worker(self):
        while (True):
            self.run_blink.wait()
            for flash in self.flashselection:
                GPIO.output(self.flash_select_pins[flash],True)
            time.sleep(self.preptime)
            GPIO.output(self.trigger_pin,True)
            time.sleep(self.triggertime)
            for pin in self.flash_select_pins:
                GPIO.output(pin, False)
            GPIO.output(self.trigger_pin, False)
            time.sleep(self.t.value-self.triggertime-self.preptime)
