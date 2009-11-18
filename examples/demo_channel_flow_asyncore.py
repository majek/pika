#!/usr/bin/env python
'''
Example show how Pika behaves when channel.flow occurs.
Two channels are created: producer and consumer.

Producer floods server with huge messages to cause out-of-memory issues.
Client slowly receives messages.

This example shows that on channel.flow:
  - client still receives messages.
  - producer blocks on basic_publish.

Hold on, playing with channel.flow without setting qos is just stupid.
All the messages will be bufferred on producer.
'''

import sys
import pika
from pika.asyncore_adapter import add_oneshot_timer_rel
import time

host = sys.argv[1] if len(sys.argv) > 1 else '127.0.0.1'
credentials = pika.PlainCredentials('guest', 'guest')

body = "a" * 1024*1024*4
def send(conn, ch):
    if not conn.writable():
        for i in range(10):
            t0 = time.time()
            ch.basic_publish(exchange='',
                            routing_key="test",
                            body=body)
            td = time.time() - t0
            print "basic_publish took %.3fs"  % (td,)
    add_oneshot_timer_rel(0.1, lambda:send(conn, ch))



conn = pika.AsyncoreConnection(pika.ConnectionParameters(host,
                               credentials=credentials))
ch_prod = conn.channel()
ch_prod.queue_declare(queue="test", durable=False, exclusive=False, auto_delete=True)
add_oneshot_timer_rel(1.0, lambda :send(conn, ch_prod))



def handle_delivery(ch, method, header, body):
    def ack():
        ch.basic_ack(delivery_tag = method.delivery_tag)
        print "basic_ack"
    add_oneshot_timer_rel(0.1, ack)


ch_cons = conn.channel()
ch_cons.basic_qos(prefetch_count=1)
tag = ch_cons.basic_consume(handle_delivery, queue='test')




while True:
    pika.asyncore_loop()
