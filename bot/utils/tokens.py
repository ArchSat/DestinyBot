import datetime

import bungio
from Crypto import Random
from Crypto.Cipher import AES
from Crypto.Hash import MD5, SHA256
from bungio.models import DestinyUser, BungieMembershipType, AuthData
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ORM.schemes.Token import Token


async def get_encode_key(membership_id):
    destiny_user = DestinyUser(membership_id=membership_id,
                               membership_type=BungieMembershipType.BUNGIE_NEXT)

    return (await destiny_user.get_membership_data_by_id()).bungie_net_user.unique_name


def encode_key(key_value=None):
    key = MD5.new()
    key.update(key_value.encode())
    return key.hexdigest().encode()


def sym_encrypt(token, key_value):
    token_hash = SHA256.new(token.encode())
    token_with_hash = token.encode() + token_hash.hexdigest().encode()
    iv = Random.new().read(AES.block_size)
    cipher = AES.new(key_value, AES.MODE_CFB,
                     iv)
    encrypted_message = iv + cipher.encrypt(
        token_with_hash)

    return encrypted_message.hex()


def sym_decrypt(cryp_token, key_value):
    bsize = AES.block_size
    dsize = SHA256.digest_size * 2
    cryp_token = bytes.fromhex(cryp_token)
    iv = Random.new().read(bsize)
    cipher = AES.new(key_value, AES.MODE_CFB, iv)
    decrypted_message_with_hash = cipher.decrypt(cryp_token)[
                                  bsize:]
    decrypted_message = decrypted_message_with_hash[
                        :-dsize]
    digest = SHA256.new(
        decrypted_message).hexdigest()

    if digest == decrypted_message_with_hash[
                 -dsize:].decode():
        return decrypted_message.decode()
    else:
        pass
