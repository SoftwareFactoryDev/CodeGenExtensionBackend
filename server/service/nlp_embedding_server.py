#!/usr/bin/env python3
# server_roberta.py
import os
import json
import socket
import struct
import torch
from  import SentenceTransformer

HOST = '0.0.0.0'
PORT = 14514
MODEL = '/data/zhouzl/code/Model/bge-large-zh-v1.5'
os.environ['CUDA_VISIBLE_DEVICES'] = "0, 1"
print('Loading BGE-Encoder ...')
model = SentenceTransformer(MODEL, device='cuda')
print('BGE-Encoder ready on', HOST, PORT)


# ---------- 通信辅助 ----------
def send_msg(sock, obj):
    msg = json.dumps(obj).encode('utf-8')
    sock.sendall(struct.pack('!I', len(msg)) + msg)


def recv_msg(sock):
    raw_len = recvall(sock, 4)
    if not raw_len:
        return None
    msg_len = struct.unpack('!I', raw_len)[0]
    data = recvall(sock, msg_len)
    return json.loads(data.decode('utf-8'))


def recvall(sock, n):
    buf = bytearray()
    while len(buf) < n:
        pkt = sock.recv(n - len(buf))
        if not pkt:
            raise ConnectionError('Socket closed')
        buf.extend(pkt)
    return buf


# ---------- 推理 ----------
@torch.no_grad()
def get_embeddings(texts):

    return model.encode(texts, normalize_embeddings=True)


def handle_client(conn, addr):
    print('Connected by', addr)
    try:
        texts = recv_msg(conn)
        if not isinstance(texts, list):
            raise ValueError('Expected list of strings')
        embs = get_embeddings(texts)
        send_msg(conn, embs)
        print(f'Sent {len(embs)} embeddings to {addr}')
    except Exception as e:
        print('Error:', e)
        send_msg(conn, {'error': str(e)})
    finally:
        conn.close()


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        while True:
            conn, addr = s.accept()
            handle_client(conn, addr)


if __name__ == '__main__':
    main()