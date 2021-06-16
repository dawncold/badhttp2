import json
import socket
import ssl

import h2.config
import h2.connection
import h2.events
import h2.settings


def send_response(conn: h2.connection.H2Connection, event):
    stream_id = event.stream_id

    resp_data = json.dumps([dict([(header[0].decode('utf8'), header[1].decode('utf8')) for header in event.headers])] * 100).encode('utf-8')
    conn.send_headers(
        stream_id=stream_id,
        headers=[
            (':status', '200'),
            ('server', 'basic-h2-server/1.0'),
            ('content-length', str(len(resp_data))),
            ('content-type', 'application/json; charset=utf8')
        ]
    )

    if len(resp_data) > conn.local_settings.max_frame_size:
        chunks = [resp_data[i:i + conn.local_settings.max_frame_size] for i in range(0, len(resp_data), conn.local_settings.max_frame_size)]
        for chunk in chunks[:-1]:
            conn.send_data(
                stream_id=stream_id,
                data=chunk
            )
        conn.send_data(
            stream_id=stream_id,
            data=chunks[-1],
            end_stream=True
        )
    else:
        conn.send_data(
            stream_id=stream_id,
            data=resp_data,
            end_stream=True
        )


def handle(_sock: socket.socket):
    config = h2.config.H2Configuration(client_side=False)
    conn = h2.connection.H2Connection(config=config)
    conn.initiate_connection()
    _sock.sendall(conn.data_to_send())

    while True:
        data = _sock.recv(65535)
        if not data:
            break
        events = conn.receive_data(data)
        for event in events:
            if isinstance(event, h2.events.RequestReceived):
                send_response(conn, event)

        data_to_send = conn.data_to_send()
        if data_to_send:
            print('original: ', data_to_send.hex(':'))
            new_length = bytes.fromhex('004001')
            type_flag_bytes = bytes.fromhex('0401')
            stream_id_bytes = bytes.fromhex('00000000')
            new_payload_bytes = bytes.fromhex('00' * ((1 << 14) + 1))
            data_to_send = new_length + type_flag_bytes + stream_id_bytes + new_payload_bytes + data_to_send[9:]
            print('new: ', data_to_send.hex(':'))
            _sock.sendall(data_to_send)


sock = socket.socket()
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(('127.0.0.1', 8443))
sock.listen(5)

ssl_context = ssl.create_default_context(purpose=ssl.Purpose.CLIENT_AUTH)
ssl_context.options |= (
    ssl.OP_NO_SSLv2 |
    ssl.OP_NO_SSLv3 |
    ssl.OP_NO_TLSv1 |
    ssl.OP_NO_TLSv1_1
)
ssl_context.options |= ssl.OP_NO_COMPRESSION
ssl_context.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20')
ssl_context.load_cert_chain(certfile='localhost.crt', keyfile='localhost.key')
ssl_context.set_alpn_protocols(['h2', 'http/1.1'])
try:
    ssl_context.set_npn_protocols(['h2', 'http/1.1'])
except NotImplementedError:
    pass

accepted_sock = sock.accept()[0]

tls_conn = ssl_context.wrap_socket(accepted_sock, server_side=True)
negotiated_protocol = tls_conn.selected_alpn_protocol()
if negotiated_protocol is None:
    negotiated_protocol = tls_conn.selected_npn_protocol()

if negotiated_protocol != 'h2':
    raise RuntimeError('Did not negotiate HTTP/2')

handle(tls_conn)
