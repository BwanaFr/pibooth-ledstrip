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
    WAIT_OR_PRINT = 3   #Show wait animation (print possible)
    CHOOSE = 4          #Show choose animation
    CHOSEN = 5          #Show chosen animation
    PREVIEW = 6         #Show the preview animation
    CAPTURE = 7         #Show the capture animation
    PROCESSING = 8      #Show the processing animation
    PRINT = 9           #Show the print animation
    FINISH = 10         #Show the finish animation
    FAILSAFE = 11       #Show fail safe animation
    TERMINATE = 12      #Exit application (switch off LED)

# A stupid LED blinker for buttons
class LedBlinker:

    def __init__(self):
        self.time_off = 0.5
        self.time_on = 0.5
        self.color_on = None
        self.color_off = None
        self.is_on = False
        self.elapsed = 0
        self.enabled = False
    
    def animate(self, lastRefresh=0.01):
        changed = False
        if self.enabled:
            self.elapsed += lastRefresh
            if self.is_on:
                if self.elapsed >= self.time_on:
                    self.is_on = False
                    self.elapsed = 0
                    changed = True
            else:
                if self.elapsed >= self.time_off:
                    self.is_on = True
                    self.elapsed = 0
                    changed = True
        return changed

    def get_color(self):
        if not self.enabled:
            return (0,0,0)
        if self.is_on:
            return self.color_on
        else:
            return self.color_off

    def set_time_on(self, time):
        self.time_on = time
    
    def set_time_off(self, time):
        self.time_off = time

    def set_color_on(self, color):
        self.color_on = color

    def set_color_off(self, color):
        self.color_off = color

    def set_enabled(self, enabled):
        self.enabled = enabled
    
    def reset(self):
        self.elapsed = 0
        self.is_on = False

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
        self.left_btn_blinker = LedBlinker()
        self.right_btn_blinker = LedBlinker()

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
                do_refresh = False
                sleep(0.01) #Do action every 10ms
                if not self.state_queue.empty():
                    #Got a new state in the queue
                    new_state = self.state_queue.get()
                    if(self.actual_state != new_state):
                        LOGGER.info("Switching state to '%s'", new_state)
                        changed = True
                    self.actual_state = new_state
                if self.actual_state == LedState.RECONFIGURE:
                    break
                if self.actual_state == LedState.TERMINATE:
                    if self.leds:
                        self.leds.fill((0x00, 0x00, 0x00))
                        self.leds.show()
                    return
                elif self.leds == None:
                    LOGGER.info("No LED...")
                    sleep(2)
                    # No leds available, ignore states
                    continue
                elif self.actual_state == LedState.WAIT or \
                    self.actual_state == LedState.WAIT_OR_PRINT:
                    do_refresh = self.animate_wait(changed)
                    if changed:
                        self.left_btn_blinker.set_color_on((0xFF, 0xFF, 0xFF))
                        self.left_btn_blinker.set_color_off((0, 0, 0))
                        self.left_btn_blinker.set_enabled(True)
                        self.left_btn_blinker.set_time_on(0.5)
                        self.left_btn_blinker.set_time_off(0.5)
                        if self.actual_state == LedState.WAIT_OR_PRINT:
                            self.right_btn_blinker.set_color_on((0, 0, 0))
                            self.right_btn_blinker.set_color_off((0xFF, 0xFF, 0xFF))
                            self.right_btn_blinker.set_enabled(True)
                            self.right_btn_blinker.set_time_on(0.5)
                            self.right_btn_blinker.set_time_off(0.5)
                        else:
                            self.right_btn_blinker.set_enabled(False)
                elif self.actual_state == LedState.CHOOSE:
                    do_refresh = self.animate_choose(changed)
                    if changed:
                        self.left_btn_blinker.set_color_on((0xFF, 0x0, 0x0))
                        self.left_btn_blinker.set_color_off((0, 0, 0))
                        self.left_btn_blinker.set_enabled(True)
                        self.left_btn_blinker.set_time_on(0.2)
                        self.left_btn_blinker.set_time_off(0.2)

                        self.right_btn_blinker.set_color_on((0, 0xFF, 0))
                        self.right_btn_blinker.set_color_off((0, 0, 0))
                        self.right_btn_blinker.set_enabled(True)
                        self.right_btn_blinker.set_time_on(0.2)
                        self.right_btn_blinker.set_time_off(0.2)
                elif self.actual_state == LedState.CHOSEN:
                    do_refresh = self.animate_chosen(changed)
                    if changed:
                        self.left_btn_blinker.set_enabled(False)
                        self.right_btn_blinker.set_enabled(False)                        
                elif self.actual_state == LedState.PREVIEW:
                    do_refresh = self.animate_preview(changed)
                elif self.actual_state == LedState.CAPTURE:                    
                    do_refresh = self.animate_capture(changed)
                elif self.actual_state == LedState.PROCESSING:
                    do_refresh = self.animate_processing(changed)
                elif self.actual_state == LedState.PRINT:
                    do_refresh = self.animate_print(changed)
                    if changed:
                        self.left_btn_blinker.set_color_on((0x00, 0xAA, 0x55))
                        self.left_btn_blinker.set_color_off((0, 0, 0))
                        self.left_btn_blinker.set_enabled(True)
                        self.left_btn_blinker.set_time_on(0.2)
                        self.left_btn_blinker.set_time_off(0.6)

                        self.right_btn_blinker.set_color_on((0, 0xFF, 0xBC))
                        self.right_btn_blinker.set_color_off((0, 0, 0))
                        self.right_btn_blinker.set_enabled(True)
                        self.right_btn_blinker.set_time_on(0.2)
                        self.right_btn_blinker.set_time_off(0.6)
                elif self.actual_state == LedState.FINISH:
                    self.leds.fill((0xCC, 0xAA, 0x10))
                    do_refresh = changed
                    if changed:
                        self.left_btn_blinker.set_enabled(False)
                        self.right_btn_blinker.set_enabled(False)  

                left_led = None
                right_led = None
                #Animate buttons
                if self.left_btn_led > -1:
                    left_led = self.leds[self.left_btn_led]
                    if changed:
                        self.left_btn_blinker.reset()
                    do_refresh |= self.left_btn_blinker.animate()
                    self.leds[self.left_btn_led] = self.left_btn_blinker.get_color()
                
                if self.right_btn_led > -1:
                    right_led = self.leds[self.right_btn_led]
                    if changed:
                        self.right_btn_blinker.reset()
                    do_refresh |= self.right_btn_blinker.animate()
                    self.leds[self.right_btn_led] = self.right_btn_blinker.get_color()
                
                #Refresh LED strip if needed
                if do_refresh:
                    self.leds.show()
                #Restore leds values for button, use for shifting
                if left_led:
                    self.leds[self.left_btn_led] = left_led
                if right_led:
                    self.leds[self.right_btn_led] = right_led

    #Convert a hue value to RGB useable by the adafruit lib
    @staticmethod
    def hsv(h, s=1.0, v=1.0):
        return tuple(round(i * 255) for i in colorsys.hsv_to_rgb(h,s,v))

    #Animate the wait state
    def animate_wait(self, changed):
        update = False
        if(changed):
            self.delay = 0
        self.delay = self.delay + 1
        if self.delay > 10 :
            self.delay = 0
            for i in range(self.led_count):
                    self.leds[i] = self.hsv(random.random(), s=(random.randint(50, 100)/100), v=random.random())
            update = True
        return update

    #Animate the choose state
    def animate_choose(self, changed):
        for i in range(self.led_count):
                self.leds[i] = self.hsv(self.hue_value + (i/self.led_count))
        self.hue_value = self.hue_value + 0.01
        if self.hue_value > 1.0 :
                self.hue_value = 0.0
        return True

    #Animate the chosen state
    def animate_chosen(self, changed):
        self.leds.fill(self.hsv(self.actual_state.capture_nbr/4+0.5))
        return True

    #Animate the previwe state
    def animate_preview(self, changed):
        #Put all on
        self.leds.fill((0xFF, 0xFF, 0xFF))
        return True
    
    #Animate the preview state
    def animate_capture(self, changed):
        #Put all on
        if(changed):
            self.delay = 0
        self.delay = self.delay + 1
        if self.delay > 4:
            self.leds.fill((0xFF, 0xFF, 0xFF))
        else:
            self.leds.fill((0x0, 0x0, 0x0))
        return True

    #Animate the processing state
    def animate_processing(self, changed):
        update = False
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
            update = True
        return update

     #Animate the print state
    def animate_print(self, changed):
        update = False
        if(changed):
            self.delay = 0
            self.leds.fill((0x0, 0x0, 0x0))
            for i in range(0, self.led_count, 3):
                self.leds[i] = (0xFF, 0xFF, 0xFF)
        self.delay = self.delay + 1
        if self.delay > 20:
            self.delay = 0
            first = self.leds[0]
            for i in range(0, self.led_count-1):
                self.leds[i] = self.leds[i+1]
            self.leds[-1] = first
            update = True
        return update

    #Set the new state
    def switchState(self, state):
        self.state_queue.put_nowait(state)

    #Sets the LED configuration
    def setConfiguration(self, cfg):
        spi_name = cfg.get("LEDStrip", "SPI_device")
        if(spi_name == "None"):
            spi_index = -1
        else:
            spi_index = int(spi_name)
        led_count = int(cfg.get("LEDStrip", "led_count"))
        left_btn_led = int(cfg.get("LEDStrip", "left_btn_led"))
        right_btn_led = int(cfg.get("LEDStrip", "right_btn_led"))
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
    if app.printer.is_ready() and \
         app.previous_picture:
        app.ledstrip.switchState(LedState.WAIT_OR_PRINT)     
    else:
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
def state_print_enter(cfg, app):
    LOGGER.info("In state_print_enter")
    app.ledstrip.switchState(LedState.PRINT)

@pibooth.hookimpl
def state_finish_enter(cfg, app):
    LOGGER.info("In state_finish_enter")
    app.ledstrip.switchState(LedState.FINISH)

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
