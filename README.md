## ERR_HTTP2_FRAME_SIZE_ERROR

This is an error in Chrome/Chromium browser.

```python
if data_to_send:
    print('original: ', data_to_send.hex(':'))
    new_length = bytes.fromhex('004001')
    type_flag_bytes = bytes.fromhex('0401')
    stream_id_bytes = bytes.fromhex('00000000')
    new_payload_bytes = bytes.fromhex('00' * ((1 << 14) + 1))
    data_to_send = new_length + type_flag_bytes + stream_id_bytes + new_payload_bytes + data_to_send[9:]
    print('new: ', data_to_send.hex(':'))
    _sock.sendall(data_to_send)
```
This piece of code modified data to send to remote, thanks for h2 library, I can modify the original data.

Actually, modify the frame length is enough for reproduce issue. I modified the first frame send to remote:
* use new length: (1 << 14) + 1 = 16385
* keep type and flag: 0x04 and 0x01
* keep stream id: 0x00000000
* padding payload: (1 << 14) + 1 = 16385

Because the first frame is a `SETTING` ACK(0x01), there is no payload, so the frame size is the fixed size(9 octets),
I just skip first 9 octets of original data to send.

## Useful tools / links
* Chrome netlog & netlog viewer: https://netlog-viewer.appspot.com
* RFC for http2: https://datatracker.ietf.org/doc/html/rfc7540
* h2 library for python: https://github.com/python-hyper/h2
* nghttp2 cli for debugging http2: https://github.com/nghttp2/nghttp2
* wireshark