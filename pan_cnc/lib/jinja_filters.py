# Copyright (c) 2018, Palo Alto Networks
#
# Permission to use, copy, modify, and/or distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
# ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
# OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

# Author: Nathan Embery nembery@paloaltonetworks.com

from passlib.hash import md5_crypt
from passlib.hash import des_crypt
from passlib.hash import sha512_crypt
from base64 import urlsafe_b64decode, urlsafe_b64encode

defined_filters = ['md5_hash', 'des_hash', 'sha512_hash', 'b64encode', 'b64decode']


def md5_hash(txt):
    return md5_crypt.hash(txt)


def des_hash(txt):
    return des_crypt.hash(txt)


def sha512_hash(txt):
    return sha512_crypt.hash(txt)


def b64encode(txt):
    if type(txt) is str:
        txt = txt.encode('UTF-8')
    return urlsafe_b64encode(txt).decode('UTF-8')


def b64decode(txt):
    if type(txt) is str:
        txt = txt.encode('UTF-8')
    return urlsafe_b64decode(txt).decode('UTF-8')
