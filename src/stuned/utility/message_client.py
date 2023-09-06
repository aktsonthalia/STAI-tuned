import json
import os
import socket
import time

class MessageType:
    JOB_STARTED = 0
    JOB_ERROR = 1
    JOB_RESULT_UPDATE = 2
    JOB_FINISHED = 3    
    

class MessageClient:
    def __init__(self, server_ip, server_port, logger):
        self.server_ip = server_ip
        self.server_port = server_port
        self.logger = logger
        self.socket = None
        self.connect()
        
        self.message_queue = []
        
        self.job_id = self.get_job_name()

    def connect(self):
        if self.socket:
            return
        
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.server_ip, self.server_port))
        except Exception as e:
            self.logger.log(f"Error trying to open the socket: {e}")
            self.socket = None
            
    def get_job_name(self):
        return int(os.environ.get('SLURM_JOB_ID', str(os.getpid())))
    
    def send_start_command(self):
        # job name is either SLURM job id or "local" PID
        self.send_message(MessageType.JOB_STARTED, None, None, sync=True)
    
    def send_key_val(self, key, val, sync=False):
        self.send_message(MessageType.JOB_RESULT_UPDATE, key, val, sync=sync)
        
    def sync_with_remote(self):
        if not self.socket:
            self.connect()
        if len(self.message_queue) == 0:
            return

        retries = 50
        retry_delay = 2

        for _ in range(retries):
            try:
                all_messages = []
                for message_type, message_key, message_value in self.message_queue:
                    # Serialize the message as JSON
                    message_data = {
                        "type": message_type,
                        "key": message_key,
                        "value": message_value
                    }
                    all_messages.append(message_data)
                    
                message_str = json.dumps({
                    "job_id": self.job_id, 
                    "messages": all_messages
                })
                
                # Send the length of the message first
                message_length = len(message_str)
                self.socket.sendall(message_length.to_bytes(4, 'big'))
                
                # Send the actual message
                self.socket.sendall(message_str.encode('utf-8'))

                data = self.socket.recv(1024)
                if data == b'ACK':
                    self.logger.log("Messages sent successfully!")
                    self.message_queue = []  # Clear the queue after successful send
                    return
                else:
                    self.logger.log("No ACK received. Retrying...")
            except Exception as e:
                self.logger.log(f"Error: {e}. Retrying in {retry_delay} seconds...")
                print(f"Error: {e}. Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                self.connect()  # Try to reconnect

        self.logger.log("Failed to send messages after multiple retries.")
        
    def send_message(self, message_type : MessageType, message_key, message_value, sync=False):
        self.message_queue.append((message_type, message_key, message_value))
        if sync:
            self.sync_with_remote()
