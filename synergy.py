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
		"""
		Sends the client a message notifying them that they've been authenticated.
		:return:
		"""
		await self.socket.send(dumps({
			'request': 'authenticate',
			'authenticated': True,
		}))

	async def send_room_mapping(self, rooms: List):
		"""
		Sends the client the supplied list of rooms that they are in so the client can display those in it's gui.
		:param rooms:
		:return:
		"""
		await self.socket.send(dumps({
			'request': 	'room_list',
			'rooms': rooms
		}))

	async def send_dict(self, x: dict):
		"""
		Sends the client the supplied dict in a form of a json string.
		:param x:
		:return:
		"""
		await self.socket.send(dumps(x))


class Room:
	def __init__(self, synergy: 'Synergy', room_name: str):
		self.synergy = synergy  # type: Synergy
		self.name = room_name
		self.member_aids = set()  # type: Set[str]

	def add_member(self, aid: str) -> None:
		"""
		Add a client to the member list of the room
		:param aid: The aid of the client
		:return:
		"""
		self.member_aids.add(aid)

	def remove_client(self, aid: str) -> None:
		self.member_aids.remove(aid)

	def is_in_room_by_aid(self, aid) -> bool:
		"""
		Checks if there is a member in the room that has the same aid as the one supplied.
		:param aid: The aid of the client
		:return: True
		"""
		for member_aid in self.member_aids:
			if member_aid == aid:
				return True
		return False

	def get_member_clients(self) -> List[Client]:
		"""
		Returns a list of clients for the room members for those that are connected.
		:return:
		"""
		member_clients = []
		for member_aid in self.member_aids:
			member_client = self.synergy.connected_clients.get(member_aid, None)
			if member_client is not None:
				member_clients.append(member_client)
		return member_clients

	async def send_message(self, client: Client, message: str) -> None:
		"""
		Send a message to everyone in the room
		:param client: The client sending the message
		:param message: The message
		:return:
		"""
		message_dict = {
			'author': client.username,
			'color': 'green',
			'message': message
		}

		await asyncio.wait([
			member_client.send_dict(message_dict) for member_client in self.get_member_clients()
		])


class Synergy:
	def __init__(self, client_port=4545, master_port=4546, authentication_server_address='http://localhost:7004'):
		"""
		Library for creating chat systems for games.
		:param client_port: The port for the client websocket connections
		:param master_port: The port for the websocket connection used for managing Synergy (creating/removing rooms, adding/removing clients from rooms)
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

		self.client_port = client_port
		self.master_port = master_port

	def start(self) -> None:
		"""
		Starts the websocket server
		:return:
		"""
		start_server = websockets.serve(self.on_new_connection, 'localhost', self.client_port)

		asyncio.get_event_loop().run_until_complete(start_server)
		asyncio.get_event_loop().run_forever()

	async def get_username(self, aid: str) -> dict:
		"""
		Sends a get request to /get/username of the supplied auth server address with the aid as a url encoded param
		:param aid: The aid of the user you'd like the username of
		:return:
		"""
		url_encoded_params = [('aid', aid)]
		async with aiohttp.ClientSession() as session:
			async with session.get(self.authentication_server_address + '/get/username', params=url_encoded_params) as resp:
				return loads(await resp.text())

	def get_rooms_client_is_in(self, client: Client) -> List[str]:
		"""
		Returns a list of room names that the supplied client in in.
		:param client:
		:return:
		"""
		room_list = []
		for room_name, room in self.rooms.items():
			if room.is_in_room_by_aid(client.aid):
				room_list.append(room_name)
		return room_list

	def join_default_rooms(self, aid) -> None:
		"""
		Joins the default rooms for the client with the supplied aid.
		:param aid:
		:return:
		"""
		for room_name, room in self.default_rooms.items():
			room.add_member(aid)

	async def add_authenticated_client(self, client: Client):
		"""
		Add a client once authenticated, where the clent is then in a position to be controlled by the master ws.
		:param client:
		:return:
		"""
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
		"""
		Creates a room with the supplied room name. Optional: Whether this is a default room or not.
		:param room_name:
		:param default_room:
		:return:
		"""
		room = Room(self, room_name)

		self.rooms[room_name] = room

		if default_room:
			self.default_rooms[room_name] = room
