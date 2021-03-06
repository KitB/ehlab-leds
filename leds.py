#!/usr/bin/env python3
import argparse
import colorsys
import json
import logging
import math
import queue
import socket
import threading
import time

from paho import mqtt
import paho.mqtt.client as mqtt_client
import neopixel
import webcolors

logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger(__name__)

port = 2812
pixels = 776
preset_path = "/data/g1leds/presets"

brightness_pct = 100

show_event = threading.Event()


def parse_colour(name):
    if type(name) is str:
        try:
            return webcolors.name_to_rgb(name)
        except ValueError:
            pass
        try:
            return webcolors.hex_to_rgb(name)
        except ValueError:
            pass
        try:
            return webcolors.hex_to_rgb("# " + name)
        except ValueError:
            pass
    return None


def rgb_to_24bit(red, green, blue, white=0):
    """Convert the provided red, green, blue color to a 24-bit color value.
    Each color component should be a value 0-255 where 0 is the lowest intensity
    and 255 is the highest intensity.
    """
    # return (white << 24) | (red << 16)| (green << 8) | blue
    return (int(white * (brightness_pct/100)) << 24) \
        | (int(green * (brightness_pct/100)) << 16) \
        | (int(red * (brightness_pct/100)) << 8) \
        | int(blue * (brightness_pct/100))


class LedExit(Exception):
    pass


class Frame:
    def __init__(self, pixels, timeout=None):
        self.last_write = 0
        self.pixels = pixels
        self.data = [0] * pixels
        self.data2 = self.data.copy()
        self.timeout = timeout
        self.frame_ready = threading.Event()

    def set_pixel(self, pixel, colour):
        try:
            self.data[pixel] = colour
        except IndexError:
            pass

    def set_all(self, colour):
        for pixel in range(0, self.pixels):
            self.data[pixel] = colour

    def show(self):
        self.last_write = time.time()
        self.data2 = self.data.copy()
        self.frame_ready.set()

    def get_pixels(self):
        return self.data

    def get_size(self):
        return self.pixels

    def active(self):
        if self.timeout is None:
            return True
        elif time.time() - self.last_write < self.timeout:
            return True
        else:
            return False

    def render_strip(self, strip):
        if self.frame_ready.is_set():
            self.frame_ready.clear()
            for i in range(0, self.pixels):
                strip.setPixelColor(i, self.data2[i])
            strip.show()


class LedProgram:
    def __init__(self, frame, *args, **kwargs):
        self.frame = frame
        self.args = args
        self.kwargs = kwargs
        self.pixel_count = frame.get_size()
        self.exit_requested = False

    def set_pixel(self, pixel, colour):
        self.frame.set_pixel(pixel, colour)

    def set_all(self, colour):
        self.frame.set_all(colour)

    def show(self):
        if self.exit_requested:
            raise LedExit()
        self.frame.show()

    def run(self):
        self.exit_requested = False
        self.setup(*self.args, **self.kwargs)
        while not self.exit_requested:
            self.loop()

    def setup(self):
        pass

    def loop(self):
        raise LedExit()

    def stop(self):
        self.exit_requested = True

    def sleep(self, t):
        if self.exit_requested:
            raise LedExit()
        time.sleep(t)


class Zap(LedProgram):
    def setup(self):
        self.black = rgb_to_24bit(0, 0, 0)
        self.white = rgb_to_24bit(255, 255, 255)
        self.set_all(self.black)

    def loop(self):
        for p in range(0, self.pixel_count):
            self.set_pixel(p, self.white)
            self.set_pixel((p-1) % self.pixel_count, self.black)
            self.show()
            self.sleep(0.001)


class Rainbow(LedProgram):
    def setup(self, multiplier=2, interval=0.040):
        self.multiplier = multiplier
        self.interval = interval
        self.speed = 1
        self.scaling = 360.0/self.pixel_count * self.multiplier

    def loop(self):
        for hue in range(0, 360):
            scaling = 360.0/self.pixel_count * self.multiplier
            for pixel in range(0, self.pixel_count):
                if pixel >= 0:
                    hue2 = ((hue*self.speed)+(pixel*scaling)) % 360
                    (r, g, b) = colorsys.hsv_to_rgb(hue2/360.0, 1.0, 1.0)
                    self.set_pixel(pixel, rgb_to_24bit(int(r*255), int(g*255), int(b*255)))
            self.show()
            self.sleep(self.interval)


class DimRainbow(LedProgram):
    def setup(self, multiplier=2, interval=0.040):
        self.multiplier = multiplier
        self.interval = interval
        self.speed = 1
        self.scaling = 360.0/self.pixel_count * self.multiplier

    def loop(self):
        for hue in range(0, 360):
            scaling = 360.0/self.pixel_count * self.multiplier
            for pixel in range(0, self.pixel_count):
                if pixel >= 0:
                    hue2 = ((hue*self.speed)+(pixel*scaling)) % 360
                    (r, g, b) = colorsys.hsv_to_rgb(hue2/360.0, 1.0, 1.0)
                    self.set_pixel(pixel, rgb_to_24bit(int(r*255/5), int(g*255/5), int(b*255/5)))
            self.show()
            self.sleep(self.interval)


class ProjectorBow(Rainbow):
    def setup(self, multiplier=2, interval=0.040):
        self.multiplier = multiplier
        self.interval = interval
        self.speed = 1
        self.scaling = 360.0/self.pixel_count * self.multiplier

    def loop(self):
        for hue in range(0, 360):
            scaling = 360.0/self.pixel_count * self.multiplier
            for pixel in range(0, self.pixel_count):
                if pixel >= 0 and (pixel <= 386 or pixel >= 505):
                    hue2 = ((hue*self.speed)+(pixel*scaling)) % 360
                    (r, g, b) = colorsys.hsv_to_rgb(hue2/360.0, 1.0, 1.0)
                    self.set_pixel(pixel, rgb_to_24bit(int(r*255), int(g*255), int(b*255)))
                elif pixel > 386 and pixel < 505:
                    self.set_pixel(pixel, rgb_to_24bit(0, 0, 0))
            self.show()
            self.sleep(self.interval)


class Chase(LedProgram):
    def setup(self, n=5, t=0.05):
        self.n = n
        self.t = t
        self.speed = 1

    def loop(self):
        while True:
            for i in range(0, self.n):
                for p in range(0, self.pixel_count):
                    if p % self.n == i:
                        self.set_pixel(p, rgb_to_24bit(255, 255, 255))
                    elif (p+1) % self.n == i:
                        self.set_pixel(p, rgb_to_24bit(15, 15, 15))
                    else:
                        self.set_pixel(p, rgb_to_24bit(0, 0, 0))
                self.show()
                time.sleep(self.t / self.speed)


class Emergency(LedProgram):
    def setup(self):
        self.red = rgb_to_24bit(255, 0, 0)
        self.blue = rgb_to_24bit(0, 0, 255)
        self.white = rgb_to_24bit(255, 255, 255)

    def loop(self):
        while True:
            self.set_all(self.blue)
            self.show()
            self.sleep(0.25)
            self.set_all(self.red)
            self.show()
            self.sleep(0.25)


class Emergency2(LedProgram):
    def setup(self):
        self.red = rgb_to_24bit(255, 0, 0)
        self.fade = rgb_to_24bit(0, 0, 0)
        self.black = rgb_to_24bit(0, 0, 0)
        self.reverse = False
        self.current = 0

    def loop(self):
        while True:
            if self.current >= 100:
                self.reverse = True
            if self.current <= 1:
                self.reverse = False

            if self.reverse:
                self.current -= 1
            else:
                self.current += 1

            self.fade = rgb_to_24bit(self.current, 0, 0)
            self.set_all(self.fade)
            self.show()
            self.sleep(0.001)


class Bercostat(LedProgram):
    def setup(self):
        self.black = rgb_to_24bit(0, 0, 0)
        self.set_all(self.black)

    def loop(self):
        rheostat = mqtt.subscribe.simple("sensor/rheostat", hostname="mqtt")
        chosen_pixel = float(rheostat.payload.decode('utf-8')) * 7.76
        chosen_pixel = math.floor(chosen_pixel)
        for p in range(0, self.pixel_count):
            if p <= chosen_pixel:
                self.set_pixel(p, rgb_to_24bit(255, 255, 255))
                self.show()
            else:
                self.set_pixel(p, rgb_to_24bit(0, 0, 0))
                self.show()


class BercostatBow(Rainbow):
    def setup(self, multiplier=2, interval=0.040):
        self.multiplier = multiplier
        self.interval = interval
        self.speed = 1
        self.scaling = 360.0/self.pixel_count * self.multiplier
        self.black = rgb_to_24bit(0, 0, 0)
        self.set_all(self.black)

    def loop(self):
        for hue in range(0, 360):
            scaling = 360.0/self.pixel_count * self.multiplier

            rheostat = mqtt.subscribe.simple("sensor/rheostat", hostname="mqtt")
            chosen_pixel = float(rheostat.payload.decode('utf-8')) * 7.76
            chosen_pixel = math.floor(chosen_pixel)

            for pixel in range(0, self.pixel_count):
                if pixel <= chosen_pixel:
                    hue2 = ((hue*self.speed)+(pixel*scaling)) % 360
                    (r, g, b) = colorsys.hsv_to_rgb(hue2/360.0, 1.0, 1.0)
                    self.set_pixel(pixel, rgb_to_24bit(int(r*255), int(g*255), int(b*255)))
                else:
                    self.set_pixel(pixel, rgb_to_24bit(0, 0, 0))
            self.show()
            self.sleep(self.interval)


class PixelPicker(LedProgram):
    def setup(self, data=None):
        if data is None:
            data = {}

        self.data = data
        self.black = rgb_to_24bit(0, 0, 0)
        self.set_all(self.black)
        self.show()

    @property
    def action_queue(self):
        try:
            return self._action_queue
        except AttributeError:
            self._action_queue = queue.Queue()
            return self._action_queue

    def post(self, data):
        self.action_queue.put(data)

    def loop(self):
        try:
            data = self.action_queue.get(timeout=0.1)
        except queue.Empty:
            pass
        else:
            for key in data:
                self.set_pixel(
                    int(key),
                    rgb_to_24bit(data[key][0], data[key][1], data[key][2])
                )
        self.show()


class TestChecker(LedProgram):
    def setup(self):
        self.black = rgb_to_24bit(0, 0, 0)
        self.white = rgb_to_24bit(255, 255, 255)

    def loop(self):
        for p in range(0, self.pixel_count):
            if p % 2 == 0:
                self.set_pixel(p, self.black)
            else:
                self.set_pixel(p, self.white)
        self.show()
        self.sleep(1)
        for p in range(0, self.pixel_count):
            if p % 2 == 0:
                self.set_pixel(p, self.white)
            else:
                self.set_pixel(p, self.black)
        self.show()
        self.sleep(1)


class StaticColour(LedProgram):
    def setup(self, colour):
        self.colour = colour

    def loop(self):
        self.set_all(self.colour)
        self.show()
        self.sleep(0.5)


class ServerProgram(LedProgram):
    port = 2812

    def run(self):
        while True:
            try:
                self.loop()
            except Exception as e:
                logger.exception("Exception in ServerThread")
            if self.exit_requested:
                return
            time.sleep(1)

    def loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", self.port))
        while True:
            data, address = sock.recvfrom(1500)
            if len(data) > 0:
                if data[0] == 0x01:
                    # single colour
                    r, g, b = data[1:4]
                    self.set_all(r, g, b)
                    self.show()
                elif data[0] == 0x03:
                    # full frame
                    pos = 1
                    pixel = 0
                    while pos + 2 < len(data):
                        r, g, b = data[pos:pos+3]
                        self.set_pixel(pixel, rgb_to_24bit(r, g, b))
                        pixel = pixel + 1
                        pos = pos + 3
                    self.show()
                elif data[0] == 0x04:
                    # partial frame + render
                    pixel = (data[1] << 8) + data[2]
                    pos = 3
                    while pos + 2 < len(data):
                        r, g, b = data[pos:pos+3]
                        self.set_pixel(pixel, rgb_to_24bit(r, g, b))
                        pixel = pixel + 1
                        pos = pos + 3
                    self.show()
                elif data[0] == 0x05:
                    # partial frame + render
                    pixel = (data[1] << 8) + data[2]
                    pos = 3
                    while pos + 2 < len(data):
                        r, g, b = data[pos:pos+3]
                        self.set_pixel(pixel, rgb_to_24bit(r, g, b))
                        pixel = pixel + 1
                        pos = pos + 3


class ProgramRunnerThread(threading.Thread):
    def __init__(self):
        super().__init__()
        self.program = None
        self.exit_requested = False

    def run(self):
        if self.program is None:
            return
        try:
            while not self.exit_requested:
                self.program.run()
        except LedExit:
            pass
        finally:
            del self._target, self._args, self._kwargs
            time.sleep(0.1)

    def stop(self):
        self.program.stop()
        self.exit_requested = True
        self.join()


class Renderer(threading.Thread):
    frames = []

    def run(self):
        # Adafruit_NeoPixel(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS)
        self.strip = neopixel.Adafruit_NeoPixel(pixels, 18, 800000, 5, False, 255)
        self.strip.begin()
        while True:
            for frame in self.frames:
                if frame.active():
                    frame.render_strip(self.strip)
                    break


class MainLedThread(threading.Thread):
    def __init__(self):
        super().__init__()
        self.progthread = None
        self.task_queue = queue.Queue()

    def post(self, job):
        self.task_queue.put(job)

    def run(self):
        while True:
            try:
                self.loop()
            except Exception as e:
                logger.exception("Exception in MainLedThread: %s", e)
                time.sleep(1)

    def loop(self):
        while True:
            try:
                program = self.task_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            logger.info("new program requested")

            if self.progthread is not None:
                logger.info("stopping old program")
                self.progthread.stop()
                logger.info("old program stopped")

            self.progthread = ProgramRunnerThread()
            self.progthread.program = program
            self.progthread.daemon = True
            self.progthread.start()
            logger.info("new program started")


def on_connect(client, userdata, flags, rc):
    logger.info("mqtt connected")
    client.subscribe("display/g1/leds")
    client.subscribe("display/g1/leds/brightness")
    client.subscribe("display/g1/leds/rainbow/multiplier")
    client.subscribe("display/g1/leds/rainbow/speed")
    client.subscribe("display/g1/leds/chase/speed")
    client.subscribe("display/g1/leds/chase/pixels")
    client.subscribe("display/g1/leds/picker")
    client.subscribe("display/g1/leds/picker/json")


class MessageHandler:
    prefix = 'display/g1/leds/'

    def __init__(self, main_led_thread):
        self.main_led_thread = main_led_thread

    def on_message(self, client, userdata, message):
        logger.debug('Received message: %s\t%s', message.topic, message.payload)

        def to_name(topic):
            extension = topic[len(self.prefix):]
            if extension == '':
                return 'on_root'
            return 'on_' + extension.replace('/', '_')
        name = to_name(message.topic)

        handler = getattr(self, name)
        try:
            handler(message)
        except ValueError:
            logger.exception('{} could not be parsed: {}'.format(name, message.payload))
        except Exception as e:
            logger.exception("Exception ({}) handling topic {}".format(e.message, message.topic))

    def on_root(self, message):
        try:
            data = json.loads(message.payload.decode())
        except ValueError:
            data = message.payload.decode()

        if data in presets:
            logger.info("selecting preset {}".format(data))
            self.main_led_thread.post(presets[data])
        else:
            rgb = parse_colour(data)
            if rgb is None:
                logger.info("preset/colour {} not found".format(data))
            else:
                logger.info("selecting colour {} = {})".format(data, rgb))
                p = StaticColour(frame_main, rgb_to_24bit(rgb[0], rgb[1], rgb[2]))
                self.main_led_thread.post(p)

    def on_brightness(self, message):
        global brightness_pct
        payload = int(message.payload)
        if payload >= 0 and payload <= 100:
            brightness_pct = payload
            logger.info("LED brightness set to {}%".format(brightness_pct))
        else:
            logger.warning("Brightness value {} was outside of bounds".format(payload))

    def on_rainbow_multiplier(self, message):
        presets["rainbow"].multiplier = float(message.payload)
        logger.info("rainbow multiplier set to {}".format(presets["rainbow"].multiplier))

    def on_rainbow_speed(self, message):
        presets["rainbow"].speed = float(message.payload)
        logger.info("rainbow speed set to {}".format(presets["rainbow"].speed))

    def on_chase_speed(self, message):
        presets["chase"].speed = float(message.payload)
        logger.info("chase speed set to {}".format(presets["chase"].speed))

    def on_chase_pixels(self, message):
        presets["chase"].n = int(message.payload)
        logger.info("chase pixels set to {}".format(presets["chase"].n))

    def on_picker(self, message):
            presets["pixelpicker"].chosen_pixel = int(message.payload)
            logger.info("pixel number {} chosen".format(int(message.payload)))

    def on_picker_json(self, message):
            data = json.loads(message.payload.decode())
            presets["pixelpicker"].post(data)


frame_net = Frame(776, timeout=1)
frame_music = Frame(776, timeout=1)
frame_main = Frame(776, timeout=5)
frame_fallback = Frame(776)

presets = {
    "rainbow": Rainbow(frame_main),
    "zap": Zap(frame_main),
    "test": TestChecker(frame_main),
    "chase": Chase(frame_main),
    "projector": ProjectorBow(frame_main),
    "emergency": Emergency(frame_main),
    "emergency2": Emergency2(frame_main),
    "bercostat": Bercostat(frame_main),
    "bercostatbow": BercostatBow(frame_main),
    "dimrainbow": DimRainbow(frame_main),
    "pixelpicker": PixelPicker(frame_main)
}


def get_args():
    ap = argparse.ArgumentParser()
    ap.add_argument('-D', '--debug', action='store_true', default=False,
                    help='Enable debug logging')
    return ap.parse_args()


def main():
    args = get_args()

    if args.debug:
        logger.setLevel(logging.DEBUG)

    rendererthread = Renderer()
    rendererthread.frames = [frame_net, frame_music, frame_main]
    rendererthread.daemon = True
    rendererthread.start()

    netthread = ProgramRunnerThread()
    netthread.program = ServerProgram(frame_net)
    netthread.daemon = True
    netthread.start()

    musicthread = ProgramRunnerThread()
    musicthread.program = ServerProgram(frame_music)
    musicthread.program.port = 2813
    musicthread.daemon = True
    musicthread.start()

    mainledthread = MainLedThread()
    mainledthread.post(presets["rainbow"])
    mainledthread.daemon = True
    mainledthread.start()

    message_handler = MessageHandler(mainledthread)

    m = mqtt_client.Client()
    m.on_connect = on_connect
    m.on_message = message_handler.on_message
    m.connect("mqtt")
    m.loop_forever()


if __name__ == '__main__':
    main()
