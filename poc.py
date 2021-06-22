from __future__ import print_function
import os
from h2.connection import H2Connection
from h2.events import (
    ResponseReceived, DataReceived, StreamEnded,
    StreamReset, SettingsAcknowledged, ConnectionTerminated,
)
from hyperframe.frame import Frame, DataFrame
from hyperframe.frame import SettingsFrame
from twisted.internet import reactor
from twisted.internet._sslverify import OpenSSLCertificateOptions, platformTrust, ClientTLSOptions
from twisted.internet.endpoints import connectProtocol, SSL4ClientEndpoint
from twisted.internet.protocol import Protocol

AUTHORITY = u''
PATH = '/'
SIZE = 4096


class H2Protocol(Protocol):
    def __init__(self):
        self.conn = H2Connection()
        self.known_proto = None
        self.request_made = False

    def connectionMade(self):
        self.conn.initiate_connection()

        # This reproduces the error in #396, by changing the header table size.
        self.conn.update_settings({SettingsFrame.HEADER_TABLE_SIZE: SIZE, SettingsFrame.MAX_FRAME_SIZE: 32768})

        self.transport.write(self.conn.data_to_send())

    def dataReceived(self, data):
        if not self.known_proto:
            self.known_proto = self.transport.negotiatedProtocol
            assert self.known_proto == b'h2'

        events = self.conn.receive_data(data)

        for event in events:
            if isinstance(event, ResponseReceived):
                self.handleResponse(event.headers, event.stream_id)
            elif isinstance(event, DataReceived):
                self.handleData(event.data, event.stream_id)
                self.conn.acknowledge_received_data(event.flow_controlled_length, event.stream_id)
            elif isinstance(event, StreamEnded):
                self.endStream(event.stream_id)
            elif isinstance(event, SettingsAcknowledged):
                self.settingsAcked(event)
            elif isinstance(event, StreamReset):
                reactor.stop()
                raise RuntimeError("Stream reset: %d" % event.error_code)
            elif isinstance(event, ConnectionTerminated):
                print(event.error_code, event.additional_data)
                reactor.stop()
            else:
                print(event)

        data = self.conn.data_to_send()
        if data:
            print(data.hex(':'))
            ptr = 0
            while True:
                frame, length = Frame.parse_frame_header(memoryview(data[ptr:ptr + 9]))
                frame.parse_body(memoryview(data[ptr + 9:ptr + 9 + length]))
                print(f'Parsed frame: {frame}')
                if isinstance(frame, DataFrame):
                    dataframe_bytes = bytes.fromhex('008001') + bytes.fromhex('0001') + bytes.fromhex('00000001') + bytes.fromhex('00' * ((1 << 15) + 1))
                    self.transport.write(dataframe_bytes)
                else:
                    self.transport.write(frame.serialize())
                ptr += 9 + length
                if ptr >= len(data):
                    break

    def settingsAcked(self, event):
        # Having received the remote settings change, lets send our request.
        if not self.request_made:
            self.sendRequest()

    def handleResponse(self, response_headers, stream_id):
        for name, value in response_headers:
            print("%s: %s" % (name.decode('utf-8'), value.decode('utf-8')))

        print("")

    def handleData(self, data, stream_id):
        print(f'received {len(data)} bytes from stream: {stream_id}')

    def endStream(self, stream_id):
        self.conn.close_connection()
        self.transport.write(self.conn.data_to_send())
        self.transport.loseConnection()
        reactor.stop()

    def sendRequest(self):
        request_headers = [
            (':method', 'POST'),
            (':authority', AUTHORITY),
            (':scheme', 'https'),
            (':path', PATH),
            ('user-agent', 'hyper-h2/1.0.0'),
        ]
        self.conn.send_headers(1, request_headers)
        self.conn.send_data(1, b'a', end_stream=True)
        self.request_made = True


certificateOptions = OpenSSLCertificateOptions(
    trustRoot=platformTrust(),
    acceptableProtocols=[b'h2'],
)
ctx = certificateOptions.getContext()


def append_to_key_log_file(key):
    log_file_path = os.getenv('SSLKEYLOGFILE')
    with open(log_file_path, 'ab+') as f:
        f.write(key + b'\n')


ctx.set_keylog_callback(lambda _, key: append_to_key_log_file(key))
options = ClientTLSOptions(AUTHORITY, ctx)
connectProtocol(
    SSL4ClientEndpoint(reactor, AUTHORITY, 443, options),
    H2Protocol()
)
reactor.run()
