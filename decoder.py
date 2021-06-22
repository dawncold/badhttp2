from hpack import Decoder, Encoder
from hpack.exceptions import HPACKDecodingError
e = Encoder()
d = Decoder()

try:
    print(d.decode(bytes.fromhex('')))
except HPACKDecodingError as err:
    print(err)
