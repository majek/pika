#!/usr/bin/env python
import sys
import os
import pika
import time


host = sys.argv[1] if len(sys.argv) > 1 else '127.0.0.1'
msgsize = (sys.argv[2]) if len(sys.argv) > 2 else 1024*1024*8
credentials = pika.PlainCredentials('guest', 'guest')

body = "a" * msgsize
t0 = None
ct = 20
def send(conn, ch):
    global t0, ct
    if not conn.writable():
        if t0 != None:
            if not ct:
                os.abort()
            td = time.time() - t0
            print "basic_publish took %.3fs"  % (td,)
        t0 = time.time()
        ch.basic_publish(exchange='',
                        routing_key="test",
                        body=body)
        ct -= 1
    reactor.add_oneshot_timer_rel(0.1, lambda:send(conn, ch))


reactor = pika.PollReactor()

conn = reactor.Connection(pika.ConnectionParameters(host,
                               credentials=credentials))
ch_prod = conn.channel()
ch_prod.queue_declare(queue="test", durable=False, exclusive=False, auto_delete=True)
reactor.add_oneshot_timer_rel(1.0, lambda :send(conn, ch_prod))


while True:
    reactor.loop()
