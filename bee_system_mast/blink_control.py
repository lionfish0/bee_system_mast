import time
import RPi.GPIO as GPIO
import threading


class Blink_Control:
    def __init__(self):
        """Controls flashes and servo pointing"""
        self.flash_select_pins = [2,3,14,15]
        self.trigger_pin = 4
        self.preptime = 0.05
        self.triggertime = 0.001
        self.totaltime = 1
        self.flashselection = [0,1,2,3] #all of them.
        
        self.direction = None

        
        GPIO.setmode(GPIO.BCM)
        for pin in self.flash_select_pins:
            GPIO.setup(pin, GPIO.OUT)
        GPIO.setup(self.trigger_pin, GPIO.OUT)
        time.sleep(0.5)
        for pin in self.flash_select_pins:
            GPIO.output(pin, False)
        GPIO.output(self.trigger_pin, False)
        self.run_blink = threading.Event()
        
    
    def worker(self):
        st = 0.03
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
            time.sleep(self.totaltime-self.triggertime-self.preptime)
            print(self.totaltime-self.triggertime-self.preptime)
