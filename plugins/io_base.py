import threading
from multiprocessing import Queue
import queue


class IOBase:
    def __init__(self, bus):
        self.bus = bus
        self.bus.subscribe(self.process_event, thread=False)
        self.write_queue = Queue(10)
        self.reader = threading.Thread(target=self.reader_thread)
        self.reader.daemon = True
        self.reader.start()
        self.writer = threading.Thread(target=self.writer_thread)
        self.writer.daemon = True
        self.writer.start()

    def reader_thread(self):
        raise NotImplementedError()

    def writer_thread(self):
        raise NotImplementedError()

    def convert_data(self, data):
        return data

    def process_event(self, ev):
        try:
            if ev.name == "leds_enabled":
                data = self.convert_data(ev.data)
                self.write_queue.put_nowait(data)
        except queue.Full:
            #TODO alert somehow without flooding?
            pass
