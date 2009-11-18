'''
Asyncore_adapter is not good enough!
'''
import sys
import traceback
import socket
import select
import time
import heapq
from errno import EAGAIN
import pika.connection


class PollReactor():
    def __init__(self):
        self.timer_heap = []
        self.poll = select.poll()
        self.fds = {}

    def register(self, fd, conn):
        self.poll.register(fd, select.POLLIN)
        self.fds[fd] = conn

    def unregister(self, fd):
        self.poll.unregister(fd)
        del self.fds[fd]

    def register_write(self, fd):
        self.poll.unregister(fd)
        self.poll.register(fd, select.POLLIN | select.POLLOUT)

    def unregister_write(self, fd):
        self.poll.unregister(fd)
        self.poll.register(fd, select.POLLIN)

    def Connection(self, *args, **kwargs):
        return _PollConnection(self, *args, **kwargs)

    def add_oneshot_timer_abs(self, firing_time, callback):
        heapq.heappush(self.timer_heap, (firing_time, callback))

    def add_oneshot_timer_rel(self, firing_delay, callback):
        self.add_oneshot_timer_abs(time.time() + firing_delay, callback)

    def next_event_timeout(self):
        cutoff = self.run_timers_internal()
        if self.timer_heap:
            timeout = self.timer_heap[0][0] - cutoff
        else:
            timeout = 30.0 # default timeout
        return timeout

    def log_timer_error(self, info):
        sys.stderr.write('EXCEPTION IN ASYNCORE_ADAPTER TIMER\n')
        traceback.print_exception(*info)

    def run_timers_internal(self):
        cutoff = time.time()
        while self.timer_heap and self.timer_heap[0][0] < cutoff:
            try:
                heapq.heappop(self.timer_heap)[1]()
            except:
                self.log_timer_error(sys.exc_info())
            cutoff = time.time()
        return cutoff

    def loop1(self):
        if self.fds:
            fds_events = self.poll.poll(self.next_event_timeout()*1000.0) # ms
            for fd, event in fds_events:
                conn = self.fds[fd]
                if event == select.POLLIN:
                    conn._do_recv()
                elif event == select.POLLOUT:
                    conn._do_send()
                else:
                    conn.disconnect_transport()
        else:
            time.sleep(self.next_event_timeout())


    def loop(self, count = None):
        if count is None:
            while self.timer_heap:
                self.loop1()
        else:
            while (self.fds or self.timer_heap) and count > 0:
                self.loop1()
                count = count - 1
            self.run_timers_internal()



class _PollConnection(pika.connection.Connection):
    def __init__(self, reactor, *args, **kwargs):
        self.reactor = reactor
        self.registered_write = False
        pika.connection.Connection.__init__(self, *args, **kwargs)

    def delayed_call(self, delay_sec, callback):
        self.reactor.add_oneshot_timer_rel(delay_sec, callback)


    def connect(self, host, port):
        self.socket = socket.socket()
        self.socket.connect((host, port)) # yep, this is blocking.
        self.reactor.register(self.socket.fileno(), self)
        self.socket.setblocking(False)
        self.on_connected()

    def disconnect_transport(self):
        self.reactor.unregister(self.socket.fileno())
        self.socket.close()
        self.on_disconnected()

    def drain_events(self):
        self.reactor.loop(count = 1)

    def _do_recv(self):
        while True:
            try:
                buf = self.socket.recv(self.suggested_buffer_size())
            except socket.error, (errno, _):
                if errno == EAGAIN:
                    return
                else:
                    self.disconnect_transport()
                    return
            self.on_data_available(buf)

    def _do_send(self):
        try:
            while self.outbound_buffer:
                fragment = self.outbound_buffer.read()
                r = self.socket.send(fragment)
                self.outbound_buffer.consume(r)
        except socket.error, (errno, _):
            if errno == EAGAIN:
                if not self.registered_write:
                    self.registered_write = True
                    self.reactor.register_write(self.socket.fileno())
                return
            else:
                self.disconnect_transport()
                return
        if self.registered_write:
            self.registered_write = False
            self.reactor.unregister_write(self.socket.fileno())


