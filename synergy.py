import asyncio
import html
import json
import requests
import websockets
import os
import Smelter
import aiohttp
from typing import List, Dict, Tuple, Set


def loads(x: str):
	try:
		return json.loads(x)
	except:
		return {}


def dumps(x: dict):
	try:
		return json.dumps(x)
	except:
		return "{}"


class Client:
	def __init__(self, socket, aid, username):
		self.socket = socket
		self.aid = aid
		self.username = username

	async def send_authentication_success_message(self):
		await self.socket.send(dumps({
			'request': 'authenticate',
			'authenticated': True,
		}))

	async def send_room_mapping(self, rooms: List):
		await self.socket.send(dumps({
			'request': 	'room_list',
			'rooms': rooms
		}))

	async def send_dict(self, x: dict):
		await self.socket.send(dumps(x))


class Room:
	def __init__(self, synergy: 'Synergy', room_name: str):
		self.synergy = synergy  # type: Synergy
		self.name = room_name
		self.member_aids = set()  # type: Set[str]

	def add_member(self, aid: str):
		self.member_aids.add(aid)

	def remove_client(self, aid: str):
		self.member_aids.remove(aid)

	def is_in_room_by_aid(self, aid):
		for member_aid in self.member_aids:
			if member_aid == aid:
				return True
		return False

	def get_member_clients(self):
		member_clients = []
		for member_aid in self.member_aids:
			member_client = self.synergy.connected_clients.get(member_aid, None)
			if member_client is not None:
				member_clients.append(member_client)
		return member_clients

	async def send_message(self, client: Client, message: str):
		message_dict = {
			'author': client.username,
			'color': 'green',
			'message': message
		}

		await asyncio.wait([
			member_client.send_dict(message_dict) for member_client in self.get_member_clients()
		])


class Synergy:
	def __init__(self, port=4545, authentication_server_address='http://localhost:7004'):
		"""

		:param port: The port for the websocket connections
		:param authentication_server_address: The address of the authentication server, explained below.
		Get requests are sent to authentication_server_address/get/username with the url param "aid" with the aid key.
		An example url would be: http://localhost:7004/get/username?aid=c9f93756-2ff6-40aa-8824-2409d7113818
		Synergy expects a stringified json response in the format. This will be much more flexible in the future.
		{
			"valid_aid": true,
			"username": "JCharante"
		}
		"""
		self.rooms = {}
		self.default_rooms = {}
		self.connected_clients = {}

		self.authentication_server_address = authentication_server_address

		self.port = port

	def start(self):
		start_server = websockets.serve(self.on_new_connection, 'localhost', self.port)

		asyncio.get_event_loop().run_until_complete(start_server)
		asyncio.get_event_loop().run_forever()

	async def get_username(self, aid: str):
		url_encoded_params = [('aid', aid)]
		async with aiohttp.ClientSession() as session:
			async with session.get(self.authentication_server_address + '/get/username', params=url_encoded_params) as resp:
				return loads(await resp.text())

	def get_rooms_client_is_in(self, client: Client) -> List[str]:
		room_list = []
		for room_name, room in self.rooms.items():
			if room.is_in_room_by_aid(client.aid):
				room_list.append(room_name)
		return room_list

	def join_default_rooms(self, aid):
		for room_name, room in self.default_rooms.items():
			room.add_member(aid)

	async def add_authenticated_client(self, client: Client):
		self.connected_clients[client.aid] = client
		self.join_default_rooms(client.aid)
		rooms_client_is_in = self.get_rooms_client_is_in(client)
		await client.send_room_mapping(rooms_client_is_in)

	async def on_new_connection(self, websocket, path):
		aid = None
		client = None
		try:
			while True:
				string = await websocket.recv()
				if aid is None:
					# Client is not authenticated
					request = loads(string)
					request_type = request.get('request', '')
					if request_type == 'authenticate':
						alleged_aid = request.get('aid', '')

						authentication_server_response = await self.get_username(alleged_aid)
						valid_aid = authentication_server_response.get('valid_aid', False)
						username = authentication_server_response.get('username', '')

						if valid_aid is not False and username != '':
							aid = alleged_aid
							client = Client(websocket, aid, username)
							await client.send_authentication_success_message()
							await self.add_authenticated_client(client)
				else:
					# Client is authenticated
					request = loads(string)
					request_type = request.get('request', '')

					if request_type == 'send_message':
						room_name = request.get('room', '')
						message = request.get('message', '')

						room = self.rooms.get(room_name, None)
						if room is not None:
							room = room  # type: Room
							if room.is_in_room_by_aid(client.aid):
								await room.send_message(client, message)
		finally:
			if aid is not None:
				self.connected_clients.pop(aid, None)

	def create_room(self, room_name, default_room=False):
		room = Room(self, room_name)

		self.rooms[room_name] = room

		if default_room:
			self.default_rooms[room_name] = room
