"""Plugin to log a message when entering in the 'wait' state."""

import pibooth
from pibooth.utils import LOGGER
from threading import Thread
from time import sleep
from enum import Enum
from queue import Queue
import colorsys
import random

try:
    import board
    import adafruit_ws2801
except ImportError:
    LOGGER.info("No WS2801 LED support found")
    adafruit_ws2801 = None

__version__ = "1.0.0"

#State of LED
class LedState(Enum):
    RECONFIGURE = 1     #Reconfigure the SPS connection
    WAIT = 2            #Show wait animation
    CHOOSE = 3          #Show chosoe animation
    CHOSEN = 4          #Show chosen animation
    PREVIEW = 5         #Show the preview animation
    CAPTURE = 6         #Show the capture animation
    PROCESSING = 7      #Show the processing animation
    PRINT = 8           #Show the print animation
    FINISH = 9          #Show the finish animation
    FAILSAFE = 10       #Show fail safe animation
    TERMINATE = 11      #Exit application (switch off LED)


#Class for controling WS2801 LED strip
class LedsWS2801(Thread):

    def __init__(self):
        super().__init__(daemon=True)
        self.name = "LEDStrip"
        self.state_queue = Queue()
        self.leds = None
        self.spi_index = -1
        self.led_count = -1
        self.left_btn_led = -1      #Left button LED
        self.right_btn_led = -1     #Right button LED
        self.actual_state = None    #Actual state
        self.hue_value = 0.0        #Hue value for animation
        self.delay = 0              #Variable to introduce delay

    def configure(self):
        #configure the SPI
        if(self.spi_index > -1) and (self.led_count > 0):
            #SPI index set
            if(not adafruit_ws2801):
                LOGGER.info("adafruit_ws2801 is not installed. No LED supported")
                self.spi_index = -1
                self.leds = None
            else:
                LOGGER.info("Intializing LED strip on SPI '%d'", self.spi_index)
                if(self.spi_index == 0):
                    self.leds = adafruit_ws2801.WS2801(board.SCK, board.MOSI, self.led_count, auto_write=False)
                elif(self.spi_index == 1):
                    self.leds = adafruit_ws2801.WS2801(board.SCK_1, board.MOSI_1, self.led_count, auto_write=False)

        else:
            #No SPI
            LOGGER.info("No SPI or LED count, disabling LED strip")
            self.leds = None
        # We will wait for next state
        self.actual_state = None

    #Thread function
    def run(self):
        while True:
            # Waits for the configuration message
            LOGGER.info("Waiting for LED strip configuration")
            state = self.state_queue.get()
            LOGGER.info("Got state '%s'", str(state))
            if(state == LedState.RECONFIGURE):
                LOGGER.info("Reconfiguring")
                break
        while True:
            #Configure LEDs            
            self.configure()
            while True:
                changed = False
                sleep(0.01) #Do action every 10ms
                if(not self.state_queue.empty()):
                    #Got a new state in the queue
                    new_state = self.state_queue.get()
                    if(self.actual_state != new_state):
                        LOGGER.info("Switching state to '%s'", new_state)
                        changed = True
                    self.actual_state = new_state
                if(self.actual_state == LedState.RECONFIGURE):
                    break
                if(self.actual_state == LedState.TERMINATE):
                    if self.leds:
                        self.leds.fill((0x00, 0x00, 0x00))
                        self.leds.show()
                    return
                elif(self.leds == None):
                    LOGGER.info("No LED...")
                    sleep(2)
                    # No leds available, ignore states
                    continue
                elif(self.actual_state == LedState.WAIT):
                    self.animate_wait(changed)
                elif(self.actual_state == LedState.CHOOSE):
                    self.animate_choose(changed)
                elif(self.actual_state == LedState.CHOSEN):
                    self.animate_chosen(changed)
                elif(self.actual_state == LedState.PREVIEW):
                    self.animate_preview(changed)
                elif(self.actual_state == LedState.CAPTURE):                    
                    self.animate_capture(changed)
                elif(self.actual_state == LedState.PROCESSING):
                    self.animate_processing(changed)

    #Convert a hue value to RGB useable by the adafruit lib
    @staticmethod
    def hsv(h, s=1.0, v=1.0):
        return tuple(round(i * 255) for i in colorsys.hsv_to_rgb(h,s,v))

    #Animate the wait state
    def animate_wait(self, changed):
        if(changed):
            self.delay = 0
        self.delay = self.delay + 1
        if self.delay > 10 :
                self.delay = 0
                for i in range(self.led_count):
                        self.leds[i] = self.hsv(random.random(), s=(random.randint(50, 100)/100), v=random.random())
                self.leds.show()

    #Animate the choose state
    def animate_choose(self, changed):        
        for i in range(self.led_count):
                self.leds[i] = self.hsv(self.hue_value + (i/self.led_count))
        self.leds.show()
        self.hue_value = self.hue_value + 0.01
        if self.hue_value > 1.0 :
                self.hue_value = 0.0

    #Animate the chosen state
    def animate_chosen(self, changed):
        self.leds.fill(self.hsv(self.actual_state.capture_nbr/4+0.5))
        self.leds.show()

    #Animate the previwe state
    def animate_preview(self, changed):
        #Put all on
        self.leds.fill((0xFF, 0xFF, 0xFF))
        self.leds.show()
    
    #Animate the previwe state
    def animate_capture(self, changed):
        #Put all on
        if(changed):
            self.delay = 0
        self.delay = self.delay + 1
        if self.delay > 4:
            self.leds.fill((0xFF, 0xFF, 0xFF))
        else:
            self.leds.fill((0x0, 0x0, 0x0))
        self.leds.show()

    def animate_processing(self, changed):
        if(changed):
            self.delay = 0
            for i in range(0, self.led_count-2, 3):
                self.leds[i] = (0xFF, 0x0, 0x0)
                self.leds[i+1] = (0x0, 0xFF, 0x0)
                self.leds[i+2] = (0x0, 0x0, 0xFF)
        self.delay = self.delay + 1
        if self.delay > 50:
            self.delay = 0
            first = self.leds[0]
            for i in range(0, self.led_count-1):
                self.leds[i] = self.leds[i+1]
            self.leds[-1] = first
            self.leds.show()

    #Set the new state
    def switchState(self, state):
        self.state_queue.put_nowait(state)

    #Sets the LED configuration
    def setConfiguration(self, cfg):
        spi_name = cfg.get("LEDStrip", "SPI_device")
        LOGGER.info("SPI device : '%s'", spi_name)
        if(spi_name == "None"):
            spi_index = -1
        else:
            spi_index = int(spi_name)
        led_count = int(cfg.get("LEDStrip", "led_count"))
        LOGGER.info("LED counts : '%d'", led_count)
        left_btn_led = int(cfg.get("LEDStrip", "left_btn_led"))
        LOGGER.info("Left button LED : '%d'", left_btn_led)
        right_btn_led = int(cfg.get("LEDStrip", "right_btn_led"))
        LOGGER.info("Left button LED : '%d'", right_btn_led)
        if((self.spi_index != spi_index) or \
            (self.led_count != led_count) or \
            (self.left_btn_led != left_btn_led) or \
            (self.right_btn_led != right_btn_led)):

            self.spi_index = spi_index
            self.led_count = led_count
            self.left_btn_led = left_btn_led
            self.right_btn_led = right_btn_led
            LOGGER.info("Configuration changed, loading it")
            self.switchState(LedState.RECONFIGURE)

# pibooth hooks
@pibooth.hookimpl
def state_wait_enter(cfg, app):
    LOGGER.info("In state_wait_enter")
    if not hasattr(app, 'ledstrip'):
        app.ledstrip = LedsWS2801()
        app.ledstrip.start()
    # Refresh the configuration, if changed
    app.ledstrip.setConfiguration(cfg)
    #Set the state
    app.ledstrip.switchState(LedState.WAIT)

@pibooth.hookimpl
def state_choose_enter(cfg, app):
    LOGGER.info("In state_choose_enter")
    #Set the state
    app.ledstrip.switchState(LedState.CHOOSE)

@pibooth.hookimpl
def state_chosen_enter(cfg, app):
    LOGGER.info("In state_chosen_enter with {} captures".format(app.capture_nbr))
    state = LedState.CHOSEN
    state.capture_nbr = app.capture_nbr
    #Set the state
    app.ledstrip.switchState(LedState.CHOSEN)

@pibooth.hookimpl
def state_preview_enter(cfg, app):
    LOGGER.info("In state_preview_enter")
    #Set the state
    app.ledstrip.switchState(LedState.PREVIEW)

@pibooth.hookimpl
def state_capture_enter(cfg, app):
    LOGGER.info("In state_capture_enter")
    #Set the state
    app.ledstrip.switchState(LedState.CAPTURE)

@pibooth.hookimpl
def state_processing_enter(cfg, app):
    LOGGER.info("In state_processing_enter")
    #Set the state
    app.ledstrip.switchState(LedState.PROCESSING)

@pibooth.hookimpl
def pibooth_cleanup(app):
    app.ledstrip.switchState(LedState.TERMINATE)

@pibooth.hookimpl
def pibooth_configure(cfg):
    LOGGER.info("In pibooth_configure")
    cfg.add_option("LEDStrip", "SPI_device", "None", "SPI device", menu_name="SPI device", menu_choices=("None","0","1"))
    cfg.add_option("LEDStrip", "led_count", "0", "LED count", menu_name="LED count", menu_choices=tuple(["{}".format(i+1) for i in range(50)]))
    cfg.add_option("LEDStrip", "left_btn_led", "0", "Left LED", menu_name="Left button LED", menu_choices=tuple(["{}".format(i) for i in range(50)]))
    cfg.add_option("LEDStrip", "right_btn_led", "0", "Right LED", menu_name="Right button LED", menu_choices=tuple(["{}".format(i) for i in range(50)]))

@pibooth.hookimpl
def pibooth_startup(cfg, app):
    spi_device = cfg.get("LEDStrip", "SPI_device")
    LOGGER.info("In pibooth_startup SPI device is %s", spi_device)

@pibooth.hookimpl
def pibooth_reset(cfg, hard):
    LOGGER.info("In pibooth_reset")
