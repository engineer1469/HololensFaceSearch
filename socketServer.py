import socket
import struct

def start_server(host='0.0.0.0', port=12345):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind((host, port))
    server_socket.listen(1)
    print('Server listening on {}:{}'.format(host, port))

    while True:
        client_socket, addr = server_socket.accept()
        print('Connection from', addr)

        try:
            # Read the size of the incoming image data
            data_size_bytes = client_socket.recv(4)
            if len(data_size_bytes) < 4:
                print('Failed to receive data size.')
                client_socket.close()
                continue

            data_size = struct.unpack('<I', data_size_bytes)[0]
            print(f'Expected data size: {data_size} bytes')

            # Receive the image data
            data = b''
            while len(data) < data_size:
                chunk = client_socket.recv(min(data_size - len(data), 4096))
                if not chunk:
                    break
                data += chunk

            if len(data) != data_size:
                # Save received image
                with open('received_face.jpg', 'wb') as f:
                    f.write(data)
                print('Image received and saved.')
            else:
                print('Incomplete data received.')

        except Exception as e:
            print(f'Error: {e}')

        client_socket.close()

if __name__ == '__main__':
    start_server()
